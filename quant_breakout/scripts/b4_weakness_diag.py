"""b4_weakness_diag.py — 现行算法（B4 = B3 + TBF）的不足在哪里：把账户的收益与回撤拆到「核心 ETF / 日本个股 / 其余（费用、开盘成交、汇率）」，
再看个股交易按离场原因、到手的最高浮盈吐回多少、被跳过的信号（只描述的诊断；读法事先写定，脚本与读法先提交、只运行一次）。

来由：用户 2026-10-23「现在算法中不足的地方 通过探索相关的变量 看看是否能逐步提高现在算法的精准度」。
以前的诊断（只描述）：完美选股上限（2026-10-03：空间在、现有特征分不出来）、名额实际只用 0.64 只（2026-10-03：个股层平均只占权益 11〜19%）、
越近越弱（2026-09-28 decay_diag：不是结构性衰退）。没有做过的：**整个账户（含核心 ETF 与牛熊切换）按环节拆开**，看回撤主要是谁造成的。

〇 账户 = B4（loop9_common.run_block(W, e, TBF)，同 kshape_link_study 的基准；先决条件同那里：规则指纹 + 接线 + B4 重算 = B4_PREP）。
   每个交易日收盘记下：个股持股、核心 ETF 口数、收盘价、现金、权益（引擎每一步之后读，不改引擎的任何计算）；
   接线核对：现金 + 个股市值 + 核心市值 = 引擎自己的权益（每天，差 ≤ ¥1）。
一 每天的盈亏拆分（主窗口 = 那个年代的窗口）：个股 = 前一天收盘拿着的股数 ×（今天收盘 − 前一天收盘）（美股 × 汇率）；核心同理（按 ETF 分开）；
   其余 = 权益变化 − 上面两项（费用、滑点、开盘成交价与前收盘之差、美元现金的汇率）。
   ① 各部分对整个窗口收益的贡献（日盈亏 ÷ 前一天权益，加总，pp）与年化；平均占权益（个股 / 核心各 ETF / 现金）。
   ② 回撤段：权益从前高到新低、深度 ≥ 10% 的不重叠段（最多 5 段，按深度），每段各部分的盈亏 ÷ 段起点权益（pp）、当时拿什么核心、牛熊状态。
   ③ 核心按美股牛熊状态（W["bear"]["US"]）分：牛 / 熊的天数、核心盈亏 pp；牛熊切换次数、切换后 20 个交易日内又切回来的次数（来回）。
二 个股交易（主窗口里买入、已平仓的日本个股）：按离场原因的笔数 / 胜率 / 每笔 % / 合计 ¥（÷ 窗口起点权益，pp）；
   持有期间最高收盘的浮盈 MFE % 与实际 % 的差（吐回）；持有天数；开盘成交价比信号日收盘高多少（跳空）。
三 引擎跳过的信号（引擎的 skipped 计数：一手太贵 / 名额满 / 现金不够 / 跳空 / 闸门…）。
四 读法（事先写定；只决定「下一步先研究哪个环节」，不改任何判定 / 交易）：
   R1 三个年代里 ≥ 2 个的最大回撤段，核心 ETF 的亏损占（核心 + 个股）亏损 ≥ 60% →「回撤主要来自核心 ETF / 牛熊切换」→ 下一步先做核心一侧；
   R2 个股合计贡献在三个年代都 < 核心贡献的 1/3 →「个股层对账户的作用小」（与名额诊断一致）→ 选股精度的改进不是首选；
   R3 信号离场（dead_cross / chandelier / sar_flip / climax；止损 stop / trail / gap_stop、止盈、时间不算）的平均吐回 ≥ 5 pp 且占个股笔数 ≥ 50% →「卖得晚」→ 卖法一侧值得一做；
   R4 一手太贵跳过的信号 ≥ 实际成交笔数 →「买不起」是个股层最大的限制（与 noquota_study 一致）。
   多条成立 → 按 R1 → R3 → R4 → R2 的顺序作为下一步的候选方向（下一步的做法另外登记；因为是看了这次诊断才定的，下一步一律按事后 posthoc = True 判定）。
五 局限：日経225 用今天的成员；拆分里「其余」包含开盘成交的偏差（不是错误）；只描述、不参与任何判定。模拟盘 / 执行器不因这次诊断改。
用法：python scripts/b4_weakness_diag.py --run（只运行一次：输出已经存在就停）。输出：var/out/b4_weakness_diag.md / .json（只有汇总，没有个股名单）。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = "b4_weakness_diag"
ERAS = ("Z", "E", "J")
DD_MIN = 10.0
DD_MAX_EP = 5
WHIP_DAYS = 20
R1_SHARE = 60.0
R3_GIVEBACK = 5.0
R3_SHARE = 50.0
SIGNAL_EXITS = ("dead_cross", "chandelier", "sar_flip", "climax")      # 信号离场（止损 stop / trail / gap_stop、止盈、时间不算）


# ───────────────────────── 记录（引擎每一步之后；不改引擎的计算） ─────────────────────────
def install_recorder(cls) -> None:
    """给引擎类加一个 step 的包装：每一步之后记下 (日期, 现金円, 美元现金, 汇率, {个股: (股数, 收盘, 市场)}, {核心: (口数, 收盘)}, 权益)。"""
    if getattr(cls, "_diag_wrapped", False):
        return
    orig = cls.step

    def step(self, i):
        orig(self, i)
        st = self.st
        rec = getattr(self, "_diag", None)
        if rec is None:
            rec = self._diag = []
        fx = float(self.fx_close[i])
        pos = {t: (float(ps.shares), float(self._px_close(t, i)), ps.market) for t, ps in st.pos.items()}
        core = {t: (float(u), float(self._px_close(t, i))) for t, u in st.core_units.items() if u}
        rec.append((self.gidx[i], float(st.cash_jpy), float(st.cash_usd), fx, pos, core, float(self.equity(i))))

    cls.step = step
    cls._diag_wrapped = True


def split_pnl(rec: list) -> pd.DataFrame:
    """每天：权益、个股市值、核心市值（按 ETF）、现金；个股 / 核心 / 其余盈亏（前一天拿着的 × 收盘变化）。"""
    rows = []
    prev = None
    for d, cj, cu, fx, pos, core, eq in rec:
        sv = sum(sh * px * (fx if m == "US" else 1.0) for sh, px, m in pos.values())
        cv = {t: u * px for t, (u, px) in core.items()}
        r = {"date": d, "eq": eq, "cash": cj + cu * fx, "stock_v": sv, "core_v": sum(cv.values()), "core_names": ",".join(sorted(cv)),
             "check": cj + cu * fx + sv + sum(cv.values()) - eq}
        if prev is None:
            r.update(stock_pnl=0.0, core_pnl=0.0, other_pnl=0.0, core_by={})
        else:
            pfx, ppos, pcore, peq = prev
            sp = 0.0
            for t, (sh, ppx, m) in ppos.items():
                now = pos.get(t)
                px = now[1] if now else ppx                                   # 今天卖掉的：按前一天收盘算（今天的差进「其余」）
                sp += sh * (px * (fx if m == "US" else 1.0) - ppx * (pfx if m == "US" else 1.0))
            cb = {}
            for t, (u, ppx) in pcore.items():
                now = core.get(t)
                px = now[1] if now else ppx
                cb[t] = u * (px - ppx)
            r.update(stock_pnl=sp, core_pnl=sum(cb.values()), core_by=cb)
            r["other_pnl"] = eq - peq - sp - r["core_pnl"]
        rows.append(r)
        prev = (fx, pos, core, eq)
    return pd.DataFrame(rows).set_index("date")


def contrib(P: pd.DataFrame) -> dict:
    """各部分对窗口收益的贡献（日盈亏 ÷ 前一天权益，加总，pp）+ 年化 + 平均占权益 %。"""
    e0 = P["eq"].shift(1)
    out = {}
    yrs = max((P.index[-1] - P.index[0]).days / 365.25, 1e-9)
    for k in ("stock", "core", "other"):
        s = (P[f"{k}_pnl"] / e0).iloc[1:].sum() * 100
        out[k] = {"pp": float(s), "pp_per_year": float(s / yrs)}
    out["total_pp"] = float(sum(out[k]["pp"] for k in ("stock", "core", "other")))
    out["cagr"] = float(((P["eq"].iloc[-1] / P["eq"].iloc[0]) ** (1 / yrs) - 1) * 100)
    out["weight"] = {k: float((P[v] / P["eq"]).mean() * 100) for k, v in (("stock", "stock_v"), ("core", "core_v"), ("cash", "cash"))}
    names = {}
    for t in sorted({x for s in P["core_names"] for x in s.split(",") if x}):
        names[t] = float(P["core_names"].str.contains(t, regex=False).mean() * 100)
    out["core_days_pct"] = names
    return out


def dd_episodes(eq: pd.Series, min_depth: float = DD_MIN, k: int = DD_MAX_EP) -> list[tuple]:
    """不重叠的回撤段（前高 → 新低 → 回到前高或窗口结束）：深度 ≥ min_depth %，按深度取前 k 个 → [(峰, 谷, 深度 %)]。"""
    v = eq.to_numpy(float)
    idx = eq.index
    eps = []
    i, n = 0, len(v)
    while i < n:
        peak = i
        while peak + 1 < n and v[peak + 1] >= v[peak]:
            peak += 1
        j = peak + 1
        trough = peak
        while j < n and v[j] < v[peak]:
            if v[j] < v[trough]:
                trough = j
            j += 1
        depth = (v[trough] / v[peak] - 1) * 100 if trough > peak else 0.0
        if depth <= -min_depth:
            eps.append((idx[peak], idx[trough], float(depth)))
        i = j if j > peak else peak + 1
    return sorted(eps, key=lambda x: x[2])[:k]


def episode_split(P: pd.DataFrame, a, b, bear: pd.Series | None) -> dict:
    x = P.loc[(P.index > a) & (P.index <= b)]
    e0 = float(P.loc[a, "eq"])
    cb: dict = {}
    for d in x["core_by"]:
        for t, v in d.items():
            cb[t] = cb.get(t, 0.0) + v
    out = {"peak": str(pd.Timestamp(a).date()), "trough": str(pd.Timestamp(b).date()), "days": int(len(x)),
           "stock_pp": float(x["stock_pnl"].sum() / e0 * 100), "core_pp": float(x["core_pnl"].sum() / e0 * 100),
           "other_pp": float(x["other_pnl"].sum() / e0 * 100), "core_by_pp": {t: float(v / e0 * 100) for t, v in cb.items()},
           "stock_w": float((x["stock_v"] / x["eq"]).mean() * 100) if len(x) else None,
           "core_w": float((x["core_v"] / x["eq"]).mean() * 100) if len(x) else None}
    loss = -min(out["stock_pp"], 0) - min(out["core_pp"], 0)
    out["core_share"] = float(-min(out["core_pp"], 0) / loss * 100) if loss > 0 else None
    if bear is not None and len(x):
        bb = bear.reindex(x.index, method="ffill").fillna(False).astype(bool)
        out["bear_days_pct"] = float(bb.mean() * 100)
    return out


def regime_split(P: pd.DataFrame, bear: pd.Series) -> dict:
    b = bear.reindex(P.index, method="ffill").fillna(False).astype(bool)
    e0 = P["eq"].shift(1)
    r = (P["core_pnl"] / e0).fillna(0) * 100
    sw = np.flatnonzero(b.to_numpy()[1:] != b.to_numpy()[:-1]) + 1
    whip = int(sum(1 for k in range(len(sw) - 1) if sw[k + 1] - sw[k] <= WHIP_DAYS))
    return {"bull_days": int((~b).sum()), "bear_days": int(b.sum()), "core_pp_bull": float(r[~b].sum()), "core_pp_bear": float(r[b].sum()),
            "switches": int(len(sw)), "whipsaws": whip}


def trade_table(tr: pd.DataFrame, closes: dict, days: pd.DatetimeIndex, e0: float) -> dict:
    """个股交易：按离场原因 + 吐回（MFE − 实际）+ 持有天数 + 开盘跳空。"""
    if not len(tr):
        return {"n": 0}
    net = tr["pnl"].to_numpy(float) / (tr["shares"].to_numpy(float) * tr["entry_px"].to_numpy(float)) * 100
    mfe, gap = [], []
    for t, ed, xd, ep in zip(tr["ticker"], pd.to_datetime(tr["entry_date"]), pd.to_datetime(tr["exit_date"]), tr["entry_px"].to_numpy(float)):
        c = closes.get(str(t))
        if c is None:
            mfe.append(np.nan)
            gap.append(np.nan)
            continue
        seg = c.loc[(c.index >= ed) & (c.index <= xd)]
        mfe.append((float(seg.max()) / ep - 1) * 100 if len(seg) else np.nan)
        k = int(days.searchsorted(ed)) - 1
        prev = c.reindex([days[k]]).iloc[0] if k >= 0 else np.nan
        gap.append((ep / float(prev) - 1) * 100 if np.isfinite(prev) and prev > 0 else np.nan)
    mfe, gap = np.array(mfe), np.array(gap)
    give = mfe - net
    out = {"n": int(len(tr)), "win": float((net > 0).mean() * 100), "mean": float(net.mean()),
           "sum_pp": float(tr["pnl_jpy"].sum() / e0 * 100) if "pnl_jpy" in tr else None,
           "hold_med": float(np.median(tr["hold_days"])) if "hold_days" in tr else None,
           "mfe_mean": float(np.nanmean(mfe)), "giveback_mean": float(np.nanmean(give)), "gap_mean": float(np.nanmean(gap)), "by_reason": {}}
    for rsn in sorted(tr["reason"].astype(str).unique()):
        m = (tr["reason"].astype(str) == rsn).to_numpy()
        out["by_reason"][rsn] = {"n": int(m.sum()), "share": float(m.mean() * 100), "win": float((net[m] > 0).mean() * 100),
                                 "mean": float(net[m].mean()), "sum_pp": float(tr["pnl_jpy"].to_numpy(float)[m].sum() / e0 * 100),
                                 "giveback_mean": float(np.nanmean(give[m])) if np.isfinite(give[m]).any() else None,
                                 "mfe_mean": float(np.nanmean(mfe[m])) if np.isfinite(mfe[m]).any() else None}
    return out


def readings(res: dict) -> dict:
    """四的读法（事先写定）。"""
    E = res["eras"]
    r1_n = sum(1 for e in ERAS if E[e]["episodes"] and (E[e]["episodes"][0].get("core_share") or 0) >= R1_SHARE)
    r2 = all(E[e]["contrib"]["stock"]["pp"] < E[e]["contrib"]["core"]["pp"] / 3 for e in ERAS)
    sig = {e: [v for k, v in E[e]["trades"].get("by_reason", {}).items() if k in SIGNAL_EXITS] for e in ERAS}
    r3_each = {}
    for e in ERAS:
        s = sig[e]
        n = sum(v["n"] for v in s)
        tot = E[e]["trades"].get("n", 0) or 0
        gb = (sum(v["giveback_mean"] * v["n"] for v in s if v["giveback_mean"] is not None) / n) if n else None
        r3_each[e] = {"giveback": gb, "share": (n / tot * 100) if tot else None}
    r3 = sum(1 for v in r3_each.values() if v["giveback"] is not None and v["giveback"] >= R3_GIVEBACK and (v["share"] or 0) >= R3_SHARE) >= 2
    r4 = sum(1 for e in ERAS if E[e]["skipped"].get("lot", 0) >= (E[e]["trades"].get("n", 0) or 0)) >= 2
    order = [k for k, ok in (("R1", r1_n >= 2), ("R3", r3), ("R4", r4), ("R2", r2)) if ok]
    return {"R1": {"ok": r1_n >= 2, "eras": r1_n}, "R2": {"ok": r2}, "R3": {"ok": r3, "each": r3_each}, "R4": {"ok": r4}, "order": order}


# ───────────────────────── 运行 ─────────────────────────
def git_info() -> dict:
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/b4_weakness_diag.py"], capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def run(say=print) -> dict:
    import jq_study as JS
    import kshape_link_study as KS
    import loop9_common as C9
    import loop10_common as C10
    import trendline_study as TS
    t0 = time.time()
    W = C10.load()
    say(f"载入：{time.time() - t0:.0f}s")
    tbf, _ = TS.tbf_gates(W, say)
    pre = KS.prereq(W, tbf, say)
    if not pre["ok"]:
        raise SystemExit("先决条件不满足 → 停")
    install_recorder(JS.RealLotEngine)
    res: dict = {"study": OUT, "git": git_info(), "prereq": {k: v for k, v in pre.items() if k != "base"}, "eras": {}}
    bear = W["bear"]["US"]
    for e in ERAS:
        acc = C9.acct(C9.run_block(W, e, tbf[e]))
        eng = JS.RealLotEngine.LAST[-1]
        P = split_pnl(eng._diag)
        a, b = TS._win(*W["ctx"][e]["windows"][e])
        Pw = P.loc[(P.index >= a) & (P.index < b)]
        tr = pd.DataFrame(eng.st.trades)
        tr = tr[tr["ticker"].astype(str).str.endswith(".T") & ~tr["ticker"].isin(TS.STOCK_SKIP) & (tr["reason"] != "end")]
        ed = pd.to_datetime(tr["entry_date"])
        tr = tr[((ed >= a) & (ed < b)).to_numpy()].reset_index(drop=True)
        closes = {t: df["Close"] for t, df in W["fr"][e].items()}
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        eps = dd_episodes(Pw["eq"])
        res["eras"][e] = {"acct": acc, "same_as_prereq": KS.same_prep(acc, KS.B4_PREP[e]),
                          "check_max_abs_yen": float(P["check"].abs().max()),
                          "contrib": contrib(Pw), "episodes": [episode_split(Pw, p, q, bear) | {"depth": d} for p, q, d in eps],
                          "regime": regime_split(Pw, bear), "trades": trade_table(tr, closes, days, float(Pw["eq"].iloc[0])),
                          "skipped": {k: int(v) for k, v in eng.skipped.items() if v}}
        say(f"{e} 完成")
    res["readings"] = readings(res)
    res["elapsed_s"] = round(time.time() - t0)
    return res


def _f(v, fmt="{:+.1f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)


def report(res: dict) -> str:
    E = res["eras"]
    L = [f"# 现行算法（B4）的不足在哪里：账户按环节拆开（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；读法见 scripts/b4_weakness_diag.py 开头）", "",
         f"代码 {res['git']['rev']}（未提交的改动：{res['git']['dirty']}）；先决条件 {res['prereq'].get('ok')}；"
         f"接线（每天 现金 + 个股 + 核心 = 权益 的最大差 ¥）：" + " / ".join(f"{e} {E[e]['check_max_abs_yen']:.2f}" for e in ERAS)
         + f"；B4 = 登记值：" + " / ".join(f"{e} {E[e]['same_as_prereq']}" for e in ERAS) + f"；用时 {res['elapsed_s']} s。", "",
         "## 一 ① 收益从哪来（主窗口；pp = 日盈亏 ÷ 前一天权益 加总）", "",
         "| 年代 | 年化 % | Calmar | 个股 pp（/年） | 核心 pp（/年） | 其余 pp（/年） | 平均占权益 个股 / 核心 / 现金 % | 核心拿着的天数 % |", "|---|---|---|---|---|---|---|---|"]
    for e in ERAS:
        c, a = E[e]["contrib"], E[e]["acct"]
        L.append(f"| {e} | {_f(c['cagr'], '{:.2f}')} | {_f(a.get('calmar'), '{:.3f}')} | {_f(c['stock']['pp'])}（{_f(c['stock']['pp_per_year'], '{:+.2f}')}） | "
                 f"{_f(c['core']['pp'])}（{_f(c['core']['pp_per_year'], '{:+.2f}')}） | {_f(c['other']['pp'])}（{_f(c['other']['pp_per_year'], '{:+.2f}')}） | "
                 f"{c['weight']['stock']:.0f} / {c['weight']['core']:.0f} / {c['weight']['cash']:.0f} | "
                 + "、".join(f"{t} {v:.0f}" for t, v in c["core_days_pct"].items()) + " |")
    L += ["", "## 一 ② 回撤段（深度 ≥ 10%，最多 5 段；pp = 段内盈亏 ÷ 段起点权益）", "",
          "| 年代 | 前高 → 新低 | 深度 % | 个股 pp | 核心 pp（按 ETF） | 其余 pp | 核心占亏损 % | 平均占权益 个股 / 核心 % | 美股熊的天 % |", "|---|---|---|---|---|---|---|---|---|"]
    for e in ERAS:
        for x in E[e]["episodes"]:
            L.append(f"| {e} | {x['peak']} → {x['trough']}（{x['days']} 天） | {x['depth']:.1f} | {_f(x['stock_pp'])} | {_f(x['core_pp'])}（"
                     + "、".join(f"{t} {_f(v)}" for t, v in x["core_by_pp"].items()) + f"） | {_f(x['other_pp'])} | {_f(x['core_share'], '{:.0f}')} | "
                     f"{_f(x['stock_w'], '{:.0f}')} / {_f(x['core_w'], '{:.0f}')} | {_f(x.get('bear_days_pct'), '{:.0f}')} |")
    L += ["", "## 一 ③ 核心按美股牛熊", "", "| 年代 | 牛 / 熊 天数 | 核心 pp 牛 / 熊 | 切换次数 | 20 个交易日内又切回来 |", "|---|---|---|---|---|"]
    for e in ERAS:
        g = E[e]["regime"]
        L.append(f"| {e} | {g['bull_days']} / {g['bear_days']} | {_f(g['core_pp_bull'])} / {_f(g['core_pp_bear'])} | {g['switches']} | {g['whipsaws']} |")
    L += ["", "## 二 个股交易（主窗口买入、已平仓）", "",
          "| 年代 | 笔数 | 胜率 % | 每笔 % | 合计 pp | 持有天数中位 | 最高浮盈 % | 吐回 pp | 开盘跳空 % |", "|---|---|---|---|---|---|---|---|---|"]
    for e in ERAS:
        t = E[e]["trades"]
        if not t.get("n"):
            L.append(f"| {e} | 0 | | | | | | | |")
            continue
        L.append(f"| {e} | {t['n']} | {t['win']:.1f} | {_f(t['mean'], '{:+.2f}')} | {_f(t['sum_pp'])} | {_f(t['hold_med'], '{:.0f}')} | "
                 f"{_f(t['mfe_mean'], '{:+.2f}')} | {_f(t['giveback_mean'], '{:.2f}')} | {_f(t['gap_mean'], '{:+.2f}')} |")
    L += ["", "按离场原因（笔数 / 占比 % / 胜率 % / 每笔 % / 合计 pp / 最高浮盈 % / 吐回 pp）：", ""]
    for e in ERAS:
        L.append(f"- {e}：" + "；".join(
            f"{k} {v['n']} / {v['share']:.0f}% / {v['win']:.0f}% / {v['mean']:+.2f} / {v['sum_pp']:+.1f} / {_f(v['mfe_mean'], '{:+.1f}')} / {_f(v['giveback_mean'], '{:.1f}')}"
            for k, v in E[e]["trades"].get("by_reason", {}).items()))
    L += ["", "## 三 引擎跳过的信号（次数）", ""]
    for e in ERAS:
        L.append(f"- {e}：" + "、".join(f"{k} {v}" for k, v in E[e]["skipped"].items()))
    R = res["readings"]
    L += ["", "## 四 读法（事先写定）", "",
          f"- R1 最大回撤段核心占亏损 ≥ {R1_SHARE:.0f}% 的年代：{R['R1']['eras']} / 3 → {'成立' if R['R1']['ok'] else '不成立'}",
          f"- R2 个股贡献三个年代都 < 核心的 1/3：{'成立' if R['R2']['ok'] else '不成立'}",
          f"- R3 信号离场平均吐回 ≥ {R3_GIVEBACK} pp 且占 ≥ {R3_SHARE:.0f}%（≥ 2 个年代）：{'成立' if R['R3']['ok'] else '不成立'}（"
          + "；".join(f"{e} 吐回 {_f(v['giveback'], '{:.1f}')} / 占 {_f(v['share'], '{:.0f}')}%" for e, v in R["R3"]["each"].items()) + "）",
          f"- R4 一手太贵跳过 ≥ 成交笔数（≥ 2 个年代）：{'成立' if R['R4']['ok'] else '不成立'}",
          f"- 下一步的候选方向（顺序）：{' → '.join(R['order']) if R['order'] else '没有一条成立'}", "",
          "只描述，不改模拟盘 / 执行器 / 策略参数。非投资建议。"]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if not a.run:
        raise SystemExit("要 --run")
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    t0 = time.time()
    say = lambda s_: print(f"{s_}；{time.time() - t0:.0f}s", flush=True)     # noqa: E731
    from qbreak import paths
    out_dir = Path(a.out_dir) if a.out_dir else paths.PROJECT_ROOT / "var" / "out"
    md, js = out_dir / f"{OUT}.md", out_dir / f"{OUT}.json"
    if md.exists() or js.exists():
        raise SystemExit(f"{md.name} / {js.name} 已经存在：只运行一次 → 停")
    res = run(say)
    out_dir.mkdir(parents=True, exist_ok=True)
    js.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)) + "\n",
                  encoding="utf-8")
    md.write_text(report(res), encoding="utf-8")
    print("完成（写在 md / json 里）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
