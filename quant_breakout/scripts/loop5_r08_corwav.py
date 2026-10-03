"""loop5_r08_corwav.py — 第五个研究循环（仓位结构）第 8 轮：按日美股市的相关调仓位 COR / 按同时出现的突破数调仓位 WAV
（2026-10-03 登记；先提交后只运行一次；新家族「仓位·层间相关」「仓位·市场宽度」）。

用户（2026-10-03）：「选③，开新循环研究仓位结构」。循环的规则：scripts/research_loop5.py；基准 B1：scripts/loop2_common.py。
为什么（照实写）：
  - COR（日経与核心的相关低 → 日本个股多放、高 → 少放；「个股层和核心怎么分」）：日本个股层是用核心（纳指 1545，日元计）的钱买的；
    两者相关低的时候个股层能分散核心的风险（同样的收益、回撤更浅），相关高的时候个股层只是换成同方向的风险。组合理论（Markowitz 1952）+
    相关随时间变化（Longin & Solnik 1995 / 2001：熊市里各国股市的相关升高）→ 先验中等偏弱（相关的高低不保证收益）。
    相关 = 日経 与 1545 合成价的周收益（周五收盘）最近 52 周（≥ 40 周）的相关；与它自己最近 260 周（≥ 104 周）的 1/3、2/3 分位比：
    ≤ 1/3 分位 → 每只 34%（× 1.36）、≥ 2/3 分位 → 12.5%（× 0.5）、其余 / 算不出 → 不变；那一周的值从下一个交易日（周一）起才用。
    以前（照实写）：第三个循环第 12 轮 CRC 是「个股与核心的相关高 → 不买」（选股、按个股），合计 +0.000 没过；这里是市场层、按时间调仓位，不是个股。
  - WAV（同时出现的突破多 → 多放、少 → 少放）：信号日为止 5 个交易日里日経225 的 W2 突破个数（三个年代的研究信号合起来，同一只同一天只算一次；
    C 的特征 wave5 同一想法）与「信号日之前 730 个日历日里日経225 的 W2 信号」的同一个数的 1/3、2/3 分位比（≥ 30 个；第 6 轮的 past_cuts）：
    ≥ 2/3 分位 → 34%、≤ 1/3 分位 → 12.5%、其余 / 不够 → 不变。文献：市场宽度的「广度推进」（breadth thrust，Zweig 1986）——
    很多股票同时突破 = 整个市场一起动，趋势更持久。先验中等偏弱：以前（2026-09-27）「市场宽度确认的突破」B1〜B4 探索时宽度高的突破更好（5 年里 4 年），
    但登记后的确认没有通过；那是「挡」，这里是「调仓位」。
做法（只改仓位；其余 —— 买点、C、离场、核心、判断层 —— 全部同 B1；参数一次写定、S6 不适用；都不是事后组合、S7 不适用）：
  - COR（kind = size_time）：每日倍数（信号日收盘时已知）→ fill_day → sizing_kw(1.36, day_mult=…)。
  - WAV（kind = size_trade）：每个年代 B1 会买的信号 → 倍数 → ticks_from → sizing_kw(1.36, tick_mult=…)。
S5（仓位版）：research_loop5.other_pools（W / Jx 里 B1 会买的信号，每笔超额 = 净收益 − O0 同期）× 倍数（COR = 信号日的倍数；
  WAV = 信号日的日経225 突破个数，同样与日経225 过去 730 天的信号比）→ research_loop5.s5_sizing。
第一关：research_loop5.stage1（trade = S5，lenses = None，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：COR = 每日倍数循环平移（种子 [20261005, s]）；WAV = 倍数在同一年代 B1 会买的信号之间随机打乱
  （种子 [20261005, 1, s]）；各 400 次、严格大于最大值。
接线核对（登记前，不看候选的收益）：J 年代 ① 倍数全为 1（同一条代码路径）→ 与 B1 逐项相同；② 倍数 ≠ 1 的天数 / 信号数 > 0。
只描述（不参与判定）：倍数的分布、B1 实际成交的倍数、个股笔数、每年收益差；W / Jx 的 dmean / dwin。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop5_r08_corwav.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）；--stage2 ID [--workers N]（第二关，第一关全过才做）。
输出 var/out/loop5_r08_corwav.md / .json（第二关 loop5_r08_corwav_stage2_ID.md / .json）。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_common as L2                                                    # noqa: E402
import loop3_r03_yenexit as X3                                               # noqa: E402
import loop5_r01_layer as R1                                                 # noqa: E402
import loop5_r02_volc as R2V                                                 # noqa: E402
import loop5_r06_valrev as R6V                                               # noqa: E402
import research_loop5 as R5                                                  # noqa: E402

ROUND = 8
IDS = ("COR", "WAV")
FAMILY = {"COR": "仓位·层间相关", "WAV": "仓位·市场宽度"}
KIND = {"COR": "size_time", "WAV": "size_trade"}
POSTHOC = False
M_LO, M_HI = 0.5, 1.36
COR_WIN, COR_MIN = 52, 40
REF_WIN, REF_MIN = 260, 104
WAVE_DAYS = 5
CORE = R1.CORE
OUT = "loop5_r08_corwav"


# ───────────────────────── 纯函数（tests/test_loop5_r08.py） ─────────────────────────
def weekly_corr(jp: pd.Series, us: pd.Series) -> pd.Series:
    """两个收盘序列 → 周五（W-FRI 那一周最后一个）收盘的周对数收益 → 最近 COR_WIN 周（≥ COR_MIN 周）的相关（按周五日期）。"""
    def wk(c: pd.Series) -> pd.Series:
        c = c[~c.index.duplicated(keep="last")].astype(float).sort_index()
        return np.log(c.where(c > 0).resample("W-FRI").last()).diff()
    df = pd.concat([wk(jp), wk(us)], axis=1).dropna()
    return df.iloc[:, 0].rolling(COR_WIN, min_periods=COR_MIN).corr(df.iloc[:, 1])


def cor_mult(rho: pd.Series, days) -> pd.Series:
    """每周的相关 → 与最近 REF_WIN 周（≥ REF_MIN 周）的 1/3、2/3 分位比：≤ 1/3 → M_HI、≥ 2/3 → M_LO、其余 / 算不出 → 1；
    那一周（周五）的值从之后的第一个交易日起用 → 每个交易日（信号日收盘时已知）的倍数。"""
    lo = rho.rolling(REF_WIN, min_periods=REF_MIN).quantile(1 / 3).to_numpy(float)
    hi = rho.rolling(REF_WIN, min_periods=REF_MIN).quantile(2 / 3).to_numpy(float)
    v = rho.to_numpy(float)
    with np.errstate(invalid="ignore"):
        m = np.where(np.isfinite(v) & np.isfinite(lo) & (v <= lo), M_HI, np.where(np.isfinite(v) & np.isfinite(hi) & (v >= hi), M_LO, 1.0))
    ms = pd.Series(m, index=pd.DatetimeIndex(rho.index) + pd.Timedelta(days=1))
    d = pd.DatetimeIndex(days)
    return ms.reindex(ms.index.union(d)).ffill().reindex(d).fillna(1.0)


def wave_series(dates, days) -> pd.Series:
    """信号日列表（同一只同一天只算一次，调用方先去重）→ 每个交易日：到当天为止 WAVE_DAYS 个交易日里的信号数。"""
    d = pd.DatetimeIndex(days)
    s = pd.DatetimeIndex(pd.to_datetime(pd.Series(dates)).dt.normalize())
    cnt = pd.Series(1.0, index=s).groupby(level=0).sum().reindex(d).fillna(0.0)
    return cnt.rolling(WAVE_DAYS, min_periods=1).sum()


# ───────────────────────── 输入 ─────────────────────────
def ref_signals(W: dict) -> pd.DataFrame:
    """日経225 三个年代全部 W2 信号（W["A"]）合起来；同一只票同一个信号日只留一笔。"""
    P = pd.concat([W["A"][e][["ticker", "date"]] for e in L2.ERAS], ignore_index=True)
    P = P.assign(date=pd.to_datetime(P["date"]).dt.normalize())
    return P.drop_duplicates(["ticker", "date"], keep="first").reset_index(drop=True)


def wav_mult_for(dates, ref: pd.DataFrame, wave: pd.Series) -> np.ndarray:
    v = R1.at_dates(wave, dates)
    return R6V.rank_mult(v, R6V.past_cuts(ref["date"], ref["wv"].to_numpy(float), dates), True)


def inputs(W: dict) -> dict:
    days = R1.union_days(W)
    rho = weekly_corr(W["inp"]["n225"]["Close"], W["assets"][CORE]["Close"])
    ref = ref_signals(W)
    wave = wave_series(ref["date"], days)
    ref = ref.assign(wv=R1.at_dates(wave, ref["date"]))
    sig = {e: R5.b1_signals(W, e) for e in L2.ERAS}
    return {"days": days, "rho": rho, "COR": cor_mult(rho, days), "wave": wave, "ref": ref, "sig": sig,
            "WAV": {e: wav_mult_for(sig[e]["date"], ref, wave) for e in L2.ERAS}}


def runs(W: dict, e: str, M: dict) -> dict:
    days = W["ctx"][e]["days"]
    return {"COR": R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(M["COR"], days)), "WAV": R2V.csz_kw(M["sig"][e], M["WAV"][e], days)}


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, M: dict) -> dict:
    pools = R5.other_pools(W)
    out = {k: {} for k in IDS}
    for s in ("W", "Jx"):
        X = pools[s]
        xs = X["xs"].to_numpy(float)
        out["COR"][s] = R5.s5_sizing(xs, R1.at_dates(M["COR"], X["date"]))
        out["WAV"][s] = R5.s5_sizing(xs, wav_mult_for(X["date"], M["ref"], M["wave"]))
    return out


# ───────────────────────── 规模（只数个数） ─────────────────────────
def scale(W: dict, M: dict, b1_trades: dict) -> dict:
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        win = days[(days >= pd.Timestamp(a)) & ((days < pd.Timestamp(b)) if b else True)]
        tr = X3.jp_stock_trades(b1_trades[e], a, b)
        sig = [days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])] if len(tr) else []
        S, m = M["sig"][e], M["WAV"][e]
        key = {(str(t), pd.Timestamp(d).normalize()): x for t, d, x in zip(S["ticker"], pd.to_datetime(S["date"]), m)}
        tw = np.array([key.get((str(t), pd.Timestamp(d).normalize()), np.nan) for t, d in zip(tr["ticker"], sig)]) if len(sig) else np.array([])
        tc = R1.at_dates(M["COR"], sig) if len(sig) else np.array([])
        mc = R1.at_dates(M["COR"], win)
        out[e] = {"b1_trades": int(len(tr)), "signals": int(len(S)),
                  "COR": {"up_days": round(float((mc > 1).mean() * 100), 1), "down_days": round(float((mc < 1).mean() * 100), 1),
                          "trades_up": int((tc > 1).sum()), "trades_down": int((tc < 1).sum())},
                  "WAV": {"up": int((m > 1).sum()), "down": int((m < 1).sum()), "trades_matched": int(np.isfinite(tw).sum()),
                          "trades_up": int((tw > 1).sum()), "trades_down": int((tw < 1).sum())}}
    return out


def pool_scale(W: dict, M: dict) -> dict:
    pools = R5.other_pools(W)
    out = {}
    for s in ("W", "Jx"):
        X = pools[s]
        mc, mw = R1.at_dates(M["COR"], X["date"]), wav_mult_for(X["date"], M["ref"], M["wave"])
        out[s] = {"n": int(len(X)), "COR": {"up": int((mc > 1).sum()), "down": int((mc < 1).sum())}, "WAV": {"up": int((mw > 1).sum()), "down": int((mw < 1).sum())}}
    return out


def rho_summary(rho: pd.Series) -> dict:
    """相关的分布（只描述；按年代）。"""
    out = {}
    for e, (a, b) in {"Z": ("2001-01-01", "2006-10-01"), "E": ("2006-10-01", "2016-10-01"), "J": ("2017-01-01", "2026-10-01")}.items():
        r = rho[(rho.index >= a) & (rho.index < b)].dropna()
        out[e] = {"n_weeks": int(len(r)), "median": round(float(r.median()), 3) if len(r) else None,
                  "min": round(float(r.min()), 3) if len(r) else None, "max": round(float(r.max()), 3) if len(r) else None}
    return out


# ───────────────────────── 运行 ─────────────────────────
_acct = R1._acct
_f = R1._f
NAMES = {"COR": "日経与纳指（日元）52 周相关在最近 5 年的低三分之一 34%、高三分之一 12.5%",
         "WAV": "5 个交易日里日経225 的突破数在过去 730 天的高三分之一 34%、低三分之一 12.5%"}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop5_r08_corwav.py", "scripts/loop5_r06_valrev.py", "scripts/loop5_r02_volc.py",
                                 "scripts/loop5_r01_layer.py", "scripts/research_loop5.py", "scripts/combo_all_common.py", "scripts/candle_portfolio.py",
                                 "scripts/loop2_common.py", "scripts/loop_common.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    M = inputs(W)
    print(f"倍数算完（{time.time() - t0:.0f}s）", flush=True)
    reg = R5.load_state().get("baseline") or {}
    base, cand, trades, b1_trades = {}, {k: {} for k in IDS}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        trades[e] = {"B1": rb["n"]}
        for k, kw in runs(W, e, M).items():
            rc = L2.run(W, e, **kw)
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
            trades[e][k] = rc["n"]
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, M)
    s1 = {k: R5.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"loop": 5, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades,
           "scale": scale(W, M, b1_trades), "rho": rho_summary(M["rho"]), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 第五个研究循环（仓位结构）第 8 轮：按日美相关 COR / 按同时出现的突破数 WAV 调仓位（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop5_r08_corwav.py 开头）", ""]
    for k in IDS:
        s1, o = res["stage1"][k], res["other_stocks"][k]
        L.append(f"- **{k}（{NAMES[k]}）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R5.FAIL1}**"
                 f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
                 f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5（W dmean {_f(o['W']['dmean'], '{:+.3f}')} pp / dwin {_f(o['W']['dwin'], '{:+.2f}')} pp；"
                 f"Jx {_f(o['Jx']['dmean'], '{:+.3f}')} / {_f(o['Jx']['dwin'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | " + " | ".join(f"{k}（Calmar 差）" for k in IDS) + " | 个股笔数 B1 → " + " / ".join(IDS) + " |",
          "|---|---|" + "---|" * len(IDS) + "---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS)
                 + f" | {t['B1']} → " + " / ".join(str(t[k]) for k in IDS) + " |")
    L += ["", "规模（不参与判定）：日美周收益 52 周相关 " + "、".join(f"{e} 中位 {_f(x['median'], '{:.2f}')}（{_f(x['min'], '{:.2f}')}〜{_f(x['max'], '{:.2f}')}）"
                                               for e, x in res["rho"].items())]
    for e in L2.ERAS:
        x = res["scale"][e]
        L.append(f"- {e}：B1 会买的信号 {x['signals']} 个、B1 的日本个股 {x['b1_trades']} 笔；COR 加大的天 {x['COR']['up_days']}%、减小的天 {x['COR']['down_days']}%、"
                 f"成交加 {x['COR']['trades_up']} / 减 {x['COR']['trades_down']}；WAV 信号加 {x['WAV']['up']} / 减 {x['WAV']['down']}、"
                 f"成交（对上 {x['WAV']['trades_matched']} 笔）加 {x['WAV']['trades_up']} / 减 {x['WAV']['trades_down']}")
    for k in IDS:
        for s in ("W", "Jx"):
            z = res["other_stocks"][k][s]
            L.append(f"- {k} {s}：B1 会买的信号 {z['n']} 个（每笔超额平均 {_f(z.get('mean_x'), '{:+.2f}')} pp、跑赢核心 {_f(z.get('beat'), '{:.1f}')}%、"
                     f"倍数平均 {_f(z.get('m_mean'), '{:.3f}')}）→ dmean {_f(z['dmean'], '{:+.3f}')} pp、dwin {_f(z['dwin'], '{:+.2f}')} pp")
    for k in IDS:
        for e in L2.ERAS:
            yb, yc = res["base"][e].get("years") or {}, res["cand"][k][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            L.append(f"- {k} {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R5.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L2.load()
    M = inputs(W)
    b1 = {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
    print(json.dumps({"scale": scale(W, M, b1), "pools": pool_scale(W, M), "rho": rho_summary(M["rho"]), "ref_signals": int(len(M["ref"]))}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 倍数全为 1（同一条代码路径）→ 与 B1 逐项相同；② 倍数 ≠ 1 的天数 / 信号数 > 0（不看收益）。"""
    W = L2.load()
    M = inputs(W)
    days = pd.DatetimeIndex(W["ctx"]["J"]["days"])
    rb = L2.run(W, "J")
    S = M["sig"]["J"]
    r1 = L2.run(W, "J", **R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(pd.Series(1.0, index=M["days"]), days)))
    r2 = L2.run(W, "J", **R2V.csz_kw(S, np.ones(len(S)), days))
    same = {"COR": all(rb.get(x) == r1.get(x) for x in R5.WIRING_KEYS), "WAV": all(rb.get(x) == r2.get(x) for x in R5.WIRING_KEYS)}
    n = {"COR": int((R1.at_dates(M["COR"], days) != 1).sum()), "WAV": int((M["WAV"]["J"] != 1).sum())}
    print(json.dumps({"ones_same_as_b1": same, "nonunit_J": n}, ensure_ascii=False))
    return 0 if all(same.values()) and all(v > 0 for v in n.values()) else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, k, base, ks = _G["W"], _G["M"], _G["k"], _G["base"], _G["ks"]
    try:
        tot = 0.0
        for e in L2.ERAS:
            days = W["ctx"][e]["days"]
            if k == "COR":
                kw = R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(R5.shift_mult(M["COR"], ks[int(seed)]), days))
            else:
                kw = R2V.csz_kw(M["sig"][e], R5.permute_mult(M["WAV"][e], int(seed)), days)
            c = L2.run(W, e, **kw)["calmar"]
            if c is None or base[e] is None:
                return None
            tot += c - base[e]
        return round(float(tot), 6)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two(k: str, workers: int) -> int:
    import multiprocessing as mp
    from qbreak import paths
    t0 = time.time()
    s1 = json.loads((paths.out_dir() / f"{OUT}.json").read_text(encoding="utf-8"))["stage1"][k]
    if not s1["ok"]:
        print(f"{k} 第一关没过 → 不做第二关")
        return 1
    code, dirty = git_head()
    W = L2.load()
    M = inputs(W)
    base = {e: L2.run(W, e)["calmar"] for e in L2.ERAS}
    cand = {e: L2.run(W, e, **runs(W, e, M)[k])["calmar"] for e in L2.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L2.ERAS), 6)
    ks = R5.size_shift_ks(len(M["days"])) if k == "COR" else None
    _G.update({"W": W, "M": M, "k": k, "base": base, "ks": ks})
    seeds = list(range(R5.PLACEBO_N))
    vals = []
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            for i, v in enumerate(pool.imap(_placebo_one, seeds)):
                vals.append(v)
                if (i + 1) % 40 == 0:
                    print(f"随机改动 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    else:
        for i in seeds:
            vals.append(_placebo_one(i))
            if (i + 1) % 40 == 0:
                print(f"随机改动 {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    s2 = R5.stage2(stat, vals)
    vd = R5.verdict(s1, s2)
    v = np.array([x for x in vals if x is not None], float)
    res = {"loop": 5, "round": ROUND, "id": k, "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "stage1_stat": s1["sum"],
           "placebo": vals, "ks": ks, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    shape = "每日倍数循环平移" if k == "COR" else "倍数在信号之间随机打乱"
    L = [f"# 第五个研究循环第 8 轮 第二关：{k} vs 400 次{shape}（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B1 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第五个研究循环第 8 轮：COR / WAV（仓位：按日美相关 / 按同时出现的突破数）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    g.add_argument("--stage2", choices=IDS, help="第二关（第一关全过才做）")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    if a.stage2:
        return stage_two(a.stage2, a.workers)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
