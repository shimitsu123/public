"""loop5_r03_betadisp.py — 第五个研究循环（仓位结构）第 3 轮：按个股对日経的 β 调仓位 BTS / 按日経成分的横截面离散度调仓位 DSP
（2026-10-03 登记；先提交后只运行一次；家族「仓位·按信号」2 / 3、新家族「仓位·市场离散度」1 / 3）。

用户（2026-10-03）：「选③，开新循环研究仓位结构」。循环的规则：scripts/research_loop5.py；基准 B1：scripts/loop2_common.py。
为什么（照实写）：
  - BTS（低 β 加、高 β 减）：信号的 β（对日経，104 周；C 的特征 b_n225）在学习样本（同一折、全部 W2 信号）的最低三分之一 → 每只 34%（× 1.36）、
    最高三分之一 → 12.5%（× 0.5）、中间不变；算不出 → 不变。文献：Frazzini & Pedersen（2014, JFE「Betting against beta」）—— 低 β 股票的风险调整后收益更高，
    日本在内的国际样本都成立；对账户而言，同样的仓位里低 β 的票带来的大盘风险更小（回撤浅）。先验中等。
    以前：09-28 探索的 P1（K2 = 量比 ≥ 2.0 且 β ≤ 0.70 → 加大）是唯一超过打乱 95% 分位的分配规则，但只 +0.012 / −0.001；K2 在前向记录里。这里只用 β、两头都动、用学习样本的三分位。
  - DSP（离散度高减、低加）：每天日経成分（三个年代的日経225 日线合起来）20 日涨跌的横截面标准差（当天 ≥ 50 只）；与最近 1260 个交易日（≥ 504 个）比：
    高于 2/3 分位 → 每只 12.5%、低于 1/3 分位 → 34%、中间不变。文献：Stivers & Sun（2010, JFQA）—— 横截面离散度高之后动量溢价低、低之后高；突破买入属于动量类。先验中等偏弱（美国样本）。
做法（只改每只的仓位；其余 —— 买点、C、离场、核心、判断层 —— 全部同 B1；参数一次写定、S6 不适用；都不是事后组合、S7 不适用）：
  - BTS（kind = size_trade）：每个年代 B1 会买的信号 → 倍数（1.36 / 1 / 0.5）→ research_loop5.ticks_from → sizing_kw(1.36, tick_mult=…)；三分位用那一折的学习样本（另外两个年代的研究面板）。
  - DSP（kind = size_time）：每日倍数（信号日收盘时已知）→ fill_day → sizing_kw(1.36, day_mult=…)。
S5（仓位版）：research_loop5.other_pools（W / Jx 里 B1 会买的信号，每笔超额 = 净收益 − O0 同期）× 倍数（BTS = 那一折的三分位；DSP = 信号日的倍数）→ research_loop5.s5_sizing。
第一关：research_loop5.stage1（trade = S5，lenses = None，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：BTS = 倍数在同一年代 B1 会买的信号之间随机打乱（种子 [20261005, 1, s]）；DSP = 每日倍数序列整体循环平移（种子 [20261005, s]）；400 次，严格大于最大值。
接线核对（登记前，不看候选的收益）：J 年代 ① 倍数全为 1（同一条代码路径）→ 与 B1 逐项相同；② 倍数 ≠ 1 的信号数 / 天数 > 0。
只描述（不参与判定）：倍数的分布、B1 实际成交的倍数、个股笔数、每年收益差；W / Jx 的 dmean / dwin。
事前预期（照实写，写在看结果之前）：BTS 加减各约三分之一、加减抵消 → 差小，E 回撤可能变浅；DSP 方向不确定；第一关各约 8%、第二关约 15% → 「更好候选」各约 1%。
运行：python scripts/loop5_r03_betadisp.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）；--stage2 ID [--workers N]（第二关，第一关全过才做）。
输出 var/out/loop5_r03_betadisp.md / .json（第二关 loop5_r03_betadisp_stage2_ID.md / .json）。非投资建议。
"""
from __future__ import annotations

import argparse
import json
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
import research_loop5 as R5                                                  # noqa: E402

ROUND = 3
IDS = ("BTS", "DSP")
FAMILY = {"BTS": "仓位·按信号", "DSP": "仓位·市场离散度"}
KIND = {"BTS": "size_trade", "DSP": "size_time"}
POSTHOC = False
M_LO, M_HI = 0.5, 1.36
BETA = "b_n225"
DISP_WIN, REF_WIN, REF_MIN, MIN_STOCKS = 20, 1260, 504, 50
OUT = "loop5_r03_betadisp"


# ───────────────────────── 纯函数（tests/test_loop5_r03.py） ─────────────────────────
def beta_cuts(trains: list[pd.DataFrame]) -> tuple[float, float]:
    """学习样本（合起来）β 的 1/3、2/3 分位（算不出 → NaN）。"""
    b = pd.concat([T[BETA] for T in trains], ignore_index=True).to_numpy(float) if trains else np.array([])
    b = b[np.isfinite(b)]
    return (float(np.quantile(b, 1 / 3)), float(np.quantile(b, 2 / 3))) if len(b) else (np.nan, np.nan)


def bab_mult(X: pd.DataFrame, cuts: tuple[float, float]) -> np.ndarray:
    """β ≤ 1/3 分位 → M_HI；≥ 2/3 分位 → M_LO；其余 / 算不出 → 1。"""
    b = X[BETA].to_numpy(float)
    lo, hi = cuts
    m = np.ones(len(X))
    if np.isfinite(lo) and np.isfinite(hi):
        ok = np.isfinite(b)
        m[ok & (b <= lo)] = M_HI
        m[ok & (b >= hi)] = M_LO
    return m


def dispersion(closes: dict[str, pd.Series], days) -> pd.Series:
    """每天：各票（自己的交易日上）DISP_WIN 日涨跌的横截面标准差；当天有值的 < MIN_STOCKS 只 → NaN。"""
    d = pd.DatetimeIndex(days)
    R = pd.DataFrame({t: (c / c.shift(DISP_WIN) - 1).reindex(d) for t, c in closes.items()}, index=d)
    n = R.notna().sum(axis=1)
    return R.std(axis=1, ddof=1).where(n >= MIN_STOCKS)


def dsp_mult(disp: pd.Series) -> pd.Series:
    """与最近 REF_WIN 天（≥ REF_MIN 个）比：> 2/3 分位 → M_LO；< 1/3 分位 → M_HI；其余 / 算不出 → 1。"""
    lo = disp.rolling(REF_WIN, min_periods=REF_MIN).quantile(1 / 3)
    hi = disp.rolling(REF_WIN, min_periods=REF_MIN).quantile(2 / 3)
    v = disp.to_numpy(float)
    m = np.where(np.isfinite(v) & np.isfinite(hi.to_numpy(float)) & (v > hi.to_numpy(float)), M_LO,
                 np.where(np.isfinite(v) & np.isfinite(lo.to_numpy(float)) & (v < lo.to_numpy(float)), M_HI, 1.0))
    return pd.Series(m, index=disp.index)


# ───────────────────────── 输入 ─────────────────────────
def union_closes(W: dict) -> dict[str, pd.Series]:
    """三个年代的日経225 日线收盘合起来（同一只票：先出现的年代优先，缺的日子用后面的补）。"""
    out: dict[str, pd.Series] = {}
    for e in L2.ERAS:
        for t, df in W["SM"][e]["fa"].items():
            if not str(t).endswith(".T") or t in X3.CORE:
                continue
            c = df["Close"].astype(float)
            c = c[~c.index.duplicated(keep="last")]
            out[t] = c if t not in out else out[t].combine_first(c)
    return out


def inputs(W: dict) -> dict:
    days = R1.union_days(W)
    cuts = {e: beta_cuts([W["D"][x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    bab = {}
    for e in L2.ERAS:
        S = R5.b1_signals(W, e)
        bab[e] = (S, bab_mult(S, cuts[e]))
    disp = dispersion(union_closes(W), days)
    return {"days": days, "BTS": bab, "cuts": cuts, "disp": disp, "DSP": dsp_mult(disp)}


def runs(W: dict, e: str, M: dict) -> dict:
    days = W["ctx"][e]["days"]
    S, m = M["BTS"][e]
    return {"BTS": R2V.csz_kw(S, m, days), "DSP": R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(M["DSP"], days))}


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, M: dict) -> dict:
    pools = R5.other_pools(W)
    out = {k: {} for k in IDS}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = pools[s]
        out["BTS"][s] = R5.s5_sizing(X["xs"].to_numpy(float), bab_mult(X, M["cuts"][fold]))
        out["DSP"][s] = R5.s5_sizing(X["xs"].to_numpy(float), R1.at_dates(M["DSP"], X["date"]))
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
        md = R1.at_dates(M["DSP"], win)
        mt = R1.at_dates(M["DSP"], sig) if len(sig) else np.array([])
        S, m = M["BTS"][e]
        key = {(str(t), pd.Timestamp(d).normalize()): x for t, d, x in zip(S["ticker"], pd.to_datetime(S["date"]), m)}
        tb = np.array([key.get((str(t), pd.Timestamp(d).normalize()), np.nan) for t, d in zip(tr["ticker"], sig)]) if len(sig) else np.array([])
        out[e] = {"days": int(len(win)), "b1_trades": int(len(tr)),
                  "BTS": {"signals": int(len(S)), "up": int((m > 1).sum()), "down": int((m < 1).sum()),
                          "trades_matched": int(np.isfinite(tb).sum()), "trades_up": int((tb > 1).sum()), "trades_down": int((tb < 1).sum())},
                  "DSP": {"up_days": round(float((md > 1).mean() * 100), 1), "down_days": round(float((md < 1).mean() * 100), 1),
                          "trades_up": int((mt > 1).sum()), "trades_down": int((mt < 1).sum())}}
    return out


# ───────────────────────── 运行 ─────────────────────────
_acct = R1._acct
_f = R1._f
NAMES = {"BTS": "β 最低三分之一 34%、最高三分之一 12.5%", "DSP": "成分股离散度高 → 12.5%、低 → 34%"}


def git_head() -> tuple[str, bool]:
    code, _ = R1.git_head()
    root = Path(__file__).resolve().parents[1]
    import subprocess
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop5_r03_betadisp.py", "scripts/loop5_r02_volc.py", "scripts/loop5_r01_layer.py",
                                 "scripts/research_loop5.py", "scripts/combo_all_common.py", "scripts/candle_portfolio.py", "scripts/loop2_common.py",
                                 "scripts/loop_common.py", "qbreak/unified.py", "qbreak/fees.py"], capture_output=True, text=True, cwd=root).stdout.strip())
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
           "scale": scale(W, M, b1_trades), "cuts": M["cuts"], "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 第五个研究循环（仓位结构）第 3 轮：按 β 调仓位 BTS / 按成分股离散度调仓位 DSP（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop5_r03_betadisp.py 开头）", ""]
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
    L += ["", "规模（不参与判定）：" + "、".join(f"{e} 折 β 三分位 {_f(c[0], '{:.2f}')} / {_f(c[1], '{:.2f}')}" for e, c in res["cuts"].items())]
    for e in L2.ERAS:
        x = res["scale"][e]
        bb, dd = x["BTS"], x["DSP"]
        L.append(f"- {e}：B1 的日本个股 {x['b1_trades']} 笔；BTS B1 会买的信号 {bb['signals']} 个里加 {bb['up']} / 减 {bb['down']}、成交（对上 {bb['trades_matched']} 笔）加 {bb['trades_up']} / 减 {bb['trades_down']}；"
                 f"DSP 加大的天 {dd['up_days']}% / 减小 {dd['down_days']}%、成交加 {dd['trades_up']} / 减 {dd['trades_down']}")
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
    dd = M["disp"]
    print(json.dumps({"scale": scale(W, M, b1), "cuts": M["cuts"], "disp_days": int(dd.notna().sum()),
                      "disp_first": str(dd.dropna().index[0].date()) if dd.notna().any() else None}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 倍数全为 1（同一条代码路径）→ 与 B1 逐项相同；② 倍数 ≠ 1 的信号数 / 天数 > 0（不看收益）。"""
    W = L2.load()
    M = inputs(W)
    days = pd.DatetimeIndex(W["ctx"]["J"]["days"])
    rb = L2.run(W, "J")
    S, m = M["BTS"]["J"]
    r1 = L2.run(W, "J", **R2V.csz_kw(S, np.ones(len(S)), days))
    r2 = L2.run(W, "J", **R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(pd.Series(1.0, index=M["days"]), days)))
    same = {"BTS": all(rb.get(x) == r1.get(x) for x in R5.WIRING_KEYS), "DSP": all(rb.get(x) == r2.get(x) for x in R5.WIRING_KEYS)}
    n = {"BTS": int((m != 1).sum()), "DSP": int((R1.at_dates(M["DSP"], days) != 1).sum())}
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
            if k == "DSP":
                kw = R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(R5.shift_mult(M["DSP"], ks[int(seed)]), days))
            else:
                S, m = M["BTS"][e]
                kw = R2V.csz_kw(S, R5.permute_mult(m, int(seed)), days)
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
    ks = R5.size_shift_ks(len(M["days"])) if k == "DSP" else None
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
    shape = "每日倍数循环平移" if k == "DSP" else "倍数在信号之间随机打乱"
    L = [f"# 第五个研究循环第 3 轮 第二关：{k} vs 400 次{shape}（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
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
    ap = argparse.ArgumentParser(description="第五个研究循环第 3 轮：BTS / DSP（仓位：按 β / 按成分股离散度）")
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
