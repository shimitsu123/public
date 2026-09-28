"""price_check.py — 每天拿 J-Quants 交叉核对 yfinance 的日本行情（数据体检 ㉚-1；2026-09-28 用户决定「先只报警」）。

为什么：模拟盘 / 执行器的日本行情来自 yfinance（拆股 + 分红调整后的价格）。数据体检（scripts/data_audit.py B 段，2026-09-28）发现
yfinance 偶尔把拆股 / 合并的调整放错（近 2 年日経225 有 1 只：5401.T 2025-09-29 前后比值变了），60 日箱体、MACD、周线量比与止损
会被错位的价格带偏。
做法（云端 sim-day 每天一次；只报警 —— 不改行情、不改交易、不挡下单）：
  对象 = 模拟盘载入的日本股票与 ETF（日経225 股票池 + 核心 ETF + 持仓 / 计划）；期间 = 今天之前 LOOKBACK_DAYS（200）个日历日
  （约 130 个交易日：60 日箱体 / RS、MACD、周线量比、最长持有 60 个交易日都在里面；更早的错位不影响今天的信号，交给数据体检）。
  只比完整的交易日（今天的 K 线不算）。J-Quants 每只 1 次请求（调整后收盘 = 只做拆股 / 合并调整）；几个线程共用一个限速
  （Standard 120 次/分 → 约 2 分钟）；超过 TIME_BUDGET 秒就停，报「只核对了 N 只」。
  ① 两边都有的日子里，日收益差 > JUMP_PP 的一天 → 分类（数据体检同一算法 classify_mismatch）：
     复权错位（之后的比值比之前变了 > 4%）→ 报警；日期错一天（前后三天合起来一致，例：涨跌停）→ 只提示；
     其它 → 最近 RECENT 个交易日内报警，更早只提示。
  ② 最新一天：比值 yfinance ÷ J-Quants 比前 5 天（中位数）跳了 > LAST_TOL_PCT → 报警；只往上跳 0〜DIV_MAX_PCT 时只提示「可能是除息」
     （yfinance 在除息日把之前的价格按分红整体调低，比值只会在除息日那一格往上跳；不直接比收盘价，否则每个除息日都会误报）；
     yfinance 的最新日期比 J-Quants 旧 → 报警（行情落后）。
  ③ J-Quants 有、yfinance 没有的交易日：最近 RECENT 个交易日里有 → 报警（指标少算一天），更早只计数。
  分红：yfinance 另做了分红调整，除息日前后比值变 1〜3%（低于 4% 的门槛，不算错位）；一次 > 5% 的特别分红会被报成复权错位 → 照实核对。
没有 JQUANTS_API_KEY / 取不到：只写原因（日报「数据完整性」列出），不影响交易。
输出只放比较的结果（日期、yfinance 自己的涨跌、差的大小），不放 J-Quants 的价格（J-Quants 规约禁止再分发；仓库是公开的）。
"""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

LOOKBACK_DAYS = 200
RECENT = 20
JUMP_PP = 5.0
LEVEL_SHIFT = 0.04
LAST_TOL_PCT = 1.0
DIV_MAX_PCT = 5.0
TIME_BUDGET = 420
WORKERS = 3
KIND_ZH = {"level": "复权错位", "timing": "日期错一天", "other": "单日不一致", "last": "最新收盘不一致", "stale": "yfinance 行情落后",
           "missing": "yfinance 缺交易日", "jq_behind": "J-Quants 还没更新", "missing_old": "更早缺的交易日", "extra": "yfinance 多出来的日子",
           "div_step": "最新一天比值上跳（可能是除息）"}


def classify_mismatch(J: pd.Series, Y: pd.Series, i: int) -> tuple[str, float]:
    """第 i 天两边的日收益差很大：前后三天合起来一致（1% 以内）→ timing（日期错一天 / 涨跌停）；
    之后与之前的比值（Y ÷ J 的中位数）变了 > 4% → level（拆股 / 合并的调整错位）；其余 → other。返回 (类别, 比值的变化)。"""
    lo, hi = max(i - 2, 0), min(i + 1, len(J) - 1)
    cj, cy = float(J.iloc[hi] / J.iloc[lo]), float(Y.iloc[hi] / Y.iloc[lo])
    R = Y / J
    before, after = float(R.iloc[max(i - 6, 0):i].median()), float(R.iloc[i:i + 6].median())
    shift = after / before - 1 if before else 0.0
    if abs(cy / cj - 1) < 0.01:
        return "timing", shift
    if abs(shift) > LEVEL_SHIFT:
        return "level", shift
    return "other", shift


def to_code5(ticker: str) -> str | None:
    """yfinance 代码 → J-Quants 5 位代码：'7203.T' → '72030'、'285A.T' → '285A0'；不是东证的 → None。"""
    if not ticker.endswith(".T"):
        return None
    s = ticker[:-2]
    return s + "0" if len(s) == 4 else None


def compare(Y: pd.Series, J: pd.Series, recent: int = RECENT) -> dict:
    """一只票：Y = yfinance 收盘、J = J-Quants 调整后收盘（日期索引，已截到同一段期间、只含完整交易日）。
    返回 {"n": 两边都有的天数, "alerts": [...], "info": [...]}；只有比较的结果，不含 J-Quants 的价格。"""
    Y = Y[np.isfinite(Y.to_numpy(float)) & (Y.to_numpy(float) > 0)]
    J = J[np.isfinite(J.to_numpy(float)) & (J.to_numpy(float) > 0)]
    alerts: list[dict] = []
    info: list[dict] = []
    if len(J) < 5 or len(Y) < 5:
        return {"n": 0, "alerts": alerts, "info": info}
    lo = max(Y.index[0], J.index[0])
    Yw, Jw = Y[Y.index >= lo], J[J.index >= lo]
    common = Yw.index.intersection(Jw.index)
    recent_days = set(Jw.index[-recent:])
    flagged: set = set()
    Jc, Yc = Jw.reindex(common), Yw.reindex(common)
    if len(common) >= 2:
        rj, ry = Jc.pct_change() * 100, Yc.pct_change() * 100
        gap = (ry - rj).abs()
        for i in np.flatnonzero(gap.to_numpy(float) > JUMP_PP):
            kind, shift = classify_mismatch(Jc, Yc, int(i))
            item = {"kind": kind, "date": str(common[i].date()), "yf_ret": round(float(ry.iloc[i]), 1),
                    "gap_pp": round(float(gap.iloc[i]), 1), "shift_pct": round(float(shift) * 100, 1)}
            flagged.add(common[i])
            (alerts if kind == "level" or (kind == "other" and common[i] in recent_days) else info).append(item)
    ly, lj = Yw.index[-1], Jw.index[-1]
    if ly == lj:
        if len(common) >= 6 and common[-1] == ly and ly not in flagged:     # ① 已经报过这一天就不重复
            R = Yc / Jc
            step = (float(R.iloc[-1]) / float(R.iloc[-6:-1].median()) - 1) * 100
            if 0 < step <= DIV_MAX_PCT and step > LAST_TOL_PCT:
                info.append({"kind": "div_step", "date": str(ly.date()), "step_pct": round(step, 2)})
            elif abs(step) > LAST_TOL_PCT:
                alerts.append({"kind": "last", "date": str(ly.date()), "diff_pct": round(step, 2)})
    elif ly < lj:
        alerts.append({"kind": "stale", "date": str(ly.date()), "jq_date": str(lj.date())})
    else:
        info.append({"kind": "jq_behind", "date": str(ly.date())})
    miss = [d for d in Jw.index.difference(Yw.index) if d <= ly]            # 比 yfinance 最新日期还新的那几天算在「行情落后」里
    rec = [d for d in miss if d in recent_days]
    if rec:
        alerts.append({"kind": "missing", "n": len(rec), "dates": [str(d.date()) for d in rec[:5]]})
    if len(miss) > len(rec):
        info.append({"kind": "missing_old", "n": len(miss) - len(rec)})
    extra = Yw.index.difference(Jw.index)
    extra = extra[extra <= lj]
    if len(extra):
        info.append({"kind": "extra", "n": int(len(extra)), "dates": [str(d.date()) for d in extra[:3]]})
    return {"n": int(len(common)), "alerts": alerts, "info": info}


class Limiter:
    """几个线程共用的限速：两次请求的开始至少隔 gap 秒。"""

    def __init__(self, per_min: int, clock=time.monotonic, sleep=time.sleep):
        self.gap = 60.0 / per_min * 1.05
        self.next = -1e18
        self.lock = threading.Lock()
        self.clock, self.sleep = clock, sleep

    def wait(self) -> None:
        with self.lock:
            t = max(self.clock(), self.next)
            self.next = t + self.gap
        d = t - self.clock()
        if d > 0:
            self.sleep(d)


def make_client():
    """J-Quants 客户端（共用限速；没设キー → 抛 JQuantsError）。不打印キー。"""
    from .jquants import RATE_PER_MIN, JQuants, _curl_get
    holder: dict = {}

    def http(url, params, headers):
        holder["lim"].wait()
        return _curl_get(url, params, headers, timeout=30)
    c = JQuants(http=http)
    holder["lim"] = Limiter(RATE_PER_MIN[c.plan])
    c.min_interval = 0.0                                                    # 限速交给共用的 Limiter
    return c


def jq_close(client, code5: str, frm: str, to: str) -> pd.Series:
    """J-Quants 调整后收盘（只拆股 / 合并调整）。"""
    from .jquants import to_ohlcv
    return to_ohlcv(client.daily(code=code5, frm=frm, to=to))["Close"]


def run(data: dict[str, pd.DataFrame], today: dt.date, client=None, fetch=None, lookback_days: int = LOOKBACK_DAYS,
        workers: int = WORKERS, budget_s: float = TIME_BUDGET, clock=time.monotonic) -> dict:
    """data：{yfinance 代码: OHLCV}（模拟盘载入的）。fetch(code5, frm, to) → J-Quants 调整后收盘（测试时注入）。
    返回日报用的汇总（只有比较结果）；没有キー → {"skipped": 原因}。"""
    t0 = clock()
    ticks = sorted(t for t in data if to_code5(t))
    frm, to = (today - dt.timedelta(days=lookback_days)).isoformat(), (today - dt.timedelta(days=1)).isoformat()
    out: dict = {"asof": today.isoformat(), "from": frm, "to": to, "wanted": len(ticks)}
    if not ticks:
        return {**out, "skipped": "没有日本行情"}
    if fetch is None:
        if client is None:
            if not os.environ.get("JQUANTS_API_KEY"):
                return {**out, "skipped": "没有设置 JQUANTS_API_KEY（云端环境设置 / Mac 钥匙串）"}
            from .jquants import JQuantsError
            try:
                client = make_client()
            except JQuantsError as e:
                return {**out, "skipped": str(e)[:160]}
        fetch = lambda c5, a, b: jq_close(client, c5, a, b)             # noqa: E731
    res: dict[str, dict] = {}
    errors: dict[str, str] = {}
    empty: list[str] = []
    late: list[str] = []

    def one(t: str) -> None:
        if clock() - t0 > budget_s:
            late.append(t)
            return
        try:
            J = fetch(to_code5(t), frm, to)
            if J is None or not len(J):
                empty.append(t)                                              # J-Quants 没有这只（新上市 / 代码变了）
                return
            J = pd.Series(np.asarray(J, float), index=pd.to_datetime(J.index))
            J = J[(J.index >= pd.Timestamp(frm)) & (J.index < pd.Timestamp(today))]
            df = data[t]
            Y = df["Close"][(df.index >= pd.Timestamp(frm)) & (df.index < pd.Timestamp(today))].astype(float)
            res[t] = compare(Y, J)
        except Exception as e:                                            # noqa: BLE001
            errors[t] = f"{type(e).__name__}: {e}"[:120]

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(one, ticks))
    alerts = [{"ticker": t, **a} for t in sorted(res) for a in res[t]["alerts"]]
    info = [{"ticker": t, **a} for t in sorted(res) for a in res[t]["info"]]
    cnt: dict[str, int] = {}
    for a in info:
        cnt[a["kind"]] = cnt.get(a["kind"], 0) + 1
    out.update({"checked": len(res), "alerts": alerts, "info_counts": cnt, "info": info[:30], "errors": dict(sorted(errors.items())[:20]),
                "n_errors": len(errors), "not_in_jq": sorted(empty), "timeout": len(late), "elapsed_s": round(clock() - t0, 1)})
    return out


def describe(a: dict) -> str:
    """一条告警 → 中文。"""
    k, t = a.get("kind"), a.get("ticker", "")
    if k in ("level", "other", "timing"):
        return (f"{t} {KIND_ZH[k]} {a['date']}（yfinance {a['yf_ret']:+.1f}%，与 J-Quants 同一天差 {a['gap_pp']:.1f} pp"
                + (f"，之后的比值变了 {a['shift_pct']:+.1f}%" if k == "level" else "") + "）")
    if k == "last":
        return f"{t} {KIND_ZH[k]} {a['date']}（两边的比值比前 5 天跳了 {a['diff_pct']:+.2f}%）"
    if k == "stale":
        return f"{t} {KIND_ZH[k]}（yfinance 最新 {a['date']}，J-Quants 已有 {a['jq_date']}）"
    if k == "missing":
        return f"{t} {KIND_ZH[k]} {a['n']} 天（{'、'.join(a['dates'])}）"
    return f"{t} {KIND_ZH.get(k, k)}"


def summary_lines(pc: dict) -> list[str]:
    """日报「数据完整性」用：没做 / 取不到 / 告警。"""
    if not pc:
        return []
    if pc.get("error"):
        return [f"行情交叉核对（J-Quants）：这次失败（{pc['error']}）—— 只报警的检查，不影响交易"]
    if pc.get("skipped"):
        return [f"行情交叉核对（J-Quants）：今天没做（{pc['skipped']}）—— 只报警的检查，不影响交易"]
    out = []
    if pc.get("timeout"):
        out.append(f"行情交叉核对（J-Quants）：时间到，只核对了 {pc.get('checked')} / {pc.get('wanted')} 只 —— 只报警的检查，不影响交易")
    if pc.get("n_errors"):
        out.append(f"行情交叉核对（J-Quants）：{pc['n_errors']} 只取不到（例 {'、'.join(list(pc.get('errors') or {})[:3])}）")
    al = pc.get("alerts") or []
    for a in al[:8]:
        out.append(f"行情交叉核对（告警，不是缺数据）：{describe(a)} —— 只报警，行情与交易照旧；在买单 / 持仓里的票先核对哪边对")
    if len(al) > 8:
        out.append(f"行情交叉核对（告警）：另有 {len(al) - 8} 条，见日报「行情交叉核对」")
    return out
