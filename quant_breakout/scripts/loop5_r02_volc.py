"""loop5_r02_volc.py — 第五个研究循环（仓位结构）第 2 轮：按市场波动调个股仓位 VMS / 按选股模型 C 的分数加大最好的三分之一 CSZ
（2026-10-03 登记；先提交后只运行一次；新家族「仓位·波动率择时」「仓位·按信号」）。

用户（2026-10-03）：「选③，开新循环研究仓位结构」。循环的规则：scripts/research_loop5.py；基准 B1：scripts/loop2_common.py。
为什么（照实写）：
  - VMS（波动管理）：每只日本个股的仓位 × clip(过去 5 年日経 63 日波动率的中位数 ÷ 现在的 63 日波动率, 0.5, 1.36)。
    文献：Moreira & Muir（2017, J. Finance「Volatility-managed portfolios」）；动量策略尤其明显 —— Barroso & Santa-Clara（2015, JFE「Momentum has its moments」）、
    Daniel & Moskowitz（2016）：按最近的波动缩放动量仓位，夏普大幅提高、避开崩盘。突破买入属于动量类。反面：Cederburg 等（2020, JFE）多数因子在实时样本外不灵。
    以前做过的波动调仓都只针对核心（第一个循环 VT20、第二个循环 VTU / VTD，都没过）；按信号的波动（09-30 F2 波动平价、09-28 P6 按 ATR 等风险）看的是个股自己的波动、
    这里看的是整个市场的波动（时间维度）。先验中等偏弱：B1 的 C 已经只在平静的牛市里挑、判断层也会在危险时减仓 → 能加的信息有限；而且平静时倍数多半 > 1。
  - CSZ（按 C 的分数加大）：B1 的选股模型 C（留一年代那一折）给每个信号打分（入选特征的投票数），分数 ≥ 学习样本 1/3 分位才买；
    这里分数 > 学习样本 2/3 分位（同一格、同一折的学习样本）的信号每只 34%（× 1.36），其余照旧 25%；没有规则的格子不动。
    先验中等偏弱：C 被采用说明分数的方向有信息，但 09-28 的探索（三个指标合成的分数）里分数与每笔收益的秩相关只有 E +0.03 / J +0.26；第四个循环里 C 的规律在年代间不稳。
做法（只改每只的仓位；其余 —— 买点、C、离场、核心、判断层 —— 全部同 B1；参数一次写定、S6 不适用；都不是事后组合、S7 不适用）：
  - VMS（kind = size_time）：倍数只看日期 → research_loop5.fill_day 对到成交日 → research_loop5.sizing_kw(1.36, day_mult=…)。
    波动率 = 日経日对数收益最近 63 个交易日的标准差 × √252（信号日收盘时已知）；基准 = 最近 1260 个交易日的波动率中位数（≥ 504 个才算）；算不出 → 1。
  - CSZ（kind = size_trade）：每个年代 B1 会买的信号（全部 W2 信号里过 C 那一折的）→ 每个信号的倍数（1.36 或 1）→ research_loop5.ticks_from → sizing_kw(1.36, days=…, tick_mult=…)。
S5（仓位版）：research_loop5.other_pools（W / Jx 里 B1 会买的信号，每笔超额 = 净收益 − O0 同期）× 倍数（VMS = 信号日的倍数；CSZ = 那一折的规则在各自池子上打分）→ research_loop5.s5_sizing。
第一关：research_loop5.stage1（trade = S5，lenses = None，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：VMS = 每日倍数序列整体循环平移（research_loop5.size_shift_ks，种子 [20261005, s]）；
  CSZ = 每个年代把倍数在这个年代 B1 会买的信号之间随机打乱（research_loop5.permute_mult，种子 [20261005, 1, s]）；400 次，严格大于最大值。
接线核对（登记前，不看候选的收益）：J 年代 ① VMS 的倍数全为 1 / CSZ 不加任何信号（同一条代码路径）→ 与 B1 逐项相同；② 倍数 ≠ 1 的天数 / 信号数 > 0。
只描述（不参与判定）：各年代倍数的分布、B1 实际成交的倍数、个股笔数、每年收益差；W / Jx 的 dmean / dwin。
事前预期（照实写，写在看结果之前）：VMS 在平静的牛市里多半加大（像「全部加大」）→ J 可能变差；CSZ 只加三分之一左右的信号、差很小；
  第一关 VMS 约 8%、CSZ 约 8%；第二关约 15% → 「更好候选」各约 1%。
运行：python scripts/loop5_r02_volc.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）；--stage2 ID [--workers N]（第二关，第一关全过才做）。
输出 var/out/loop5_r02_volc.md / .json（第二关 loop5_r02_volc_stage2_ID.md / .json）。非投资建议。
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
import research_loop5 as R5                                                  # noqa: E402

ROUND = 2
IDS = ("VMS", "CSZ")
FAMILY = {"VMS": "仓位·波动率择时", "CSZ": "仓位·按信号"}
KIND = {"VMS": "size_time", "CSZ": "size_trade"}
POSTHOC = False
M_LO, M_HI = 0.5, 1.36
VOL_WIN, REF_WIN, REF_MIN = 63, 1260, 504
HI_Q = 2 / 3
OUT = "loop5_r02_volc"


# ───────────────────────── 纯函数（tests/test_loop5_r02.py） ─────────────────────────
def vms_mult(close: pd.Series, days) -> pd.Series:
    """日経收盘 → 每日倍数 clip(最近 REF_WIN 天波动率的中位数 ÷ 最近 VOL_WIN 天波动率, M_LO, M_HI)；算不出 → 1。"""
    d = pd.DatetimeIndex(days)
    c = close[~close.index.duplicated(keep="last")].astype(float)
    c = c.reindex(d.union(c.index)).ffill().reindex(d)
    r = np.log(c).diff()
    sig = r.rolling(VOL_WIN, min_periods=VOL_WIN).std() * np.sqrt(252)
    ref = sig.rolling(REF_WIN, min_periods=REF_MIN).median()
    m = (ref / sig).clip(M_LO, M_HI)
    return m.where(np.isfinite(m.to_numpy(float)), 1.0)


def c_hi(trains: list[pd.DataFrame], rules: dict) -> dict:
    """每一格：同一折学习样本（这一格）分数的 HI_Q 分位（没有规则 → None）。"""
    import combo_all_common as CA
    out = {}
    for k, r in rules.items():
        if r is None:
            out[k] = None
            continue
        pooled = pd.concat([T[CA.cell_of(T) == k] for T in trains], ignore_index=True)
        s = CA.score(pooled, r["sel"], r["cut"])
        out[k] = float(np.quantile(s, HI_Q)) if len(s) else None
    return out


def csz_mult(X: pd.DataFrame, rules: dict, hi: dict) -> np.ndarray:
    """每个信号：所在格有规则、分数 ≥ 门槛（会买）且 > 那一格的 HI_Q 分位 → M_HI；其余 1。"""
    import combo_all_common as CA
    m = np.ones(len(X))
    cell = CA.cell_of(X)
    for k, r in rules.items():
        if r is None or hi.get(k) is None:
            continue
        idx = np.flatnonzero(cell == k)
        if not len(idx):
            continue
        s = CA.score(X.iloc[idx], r["sel"], r["cut"])
        up = (s > hi[k]) & ~(s < r["thr"])
        m[idx[up]] = M_HI
    return m


# ───────────────────────── 输入 ─────────────────────────
def fold_rules(W: dict, fold: str) -> tuple[dict, dict]:
    import combo_all_common as CA
    trains = [W["D"][x] for x in L2.ERAS if x != fold]
    rules = CA.fit_c(trains)
    return rules, c_hi(trains, rules)


def inputs(W: dict) -> dict:
    """{"days", "VMS": 每日倍数（信号日收盘时已知）, "CSZ": {年代: (B1 会买的信号表, 每个信号的倍数)}, "rules": {折: (规则, 2/3 分位)}}。"""
    days = R1.union_days(W)
    rules = {e: fold_rules(W, e) for e in L2.ERAS}
    csz = {}
    for e in L2.ERAS:
        S = R5.b1_signals(W, e)
        csz[e] = (S, csz_mult(S, *rules[e]))
    return {"days": days, "VMS": vms_mult(W["inp"]["n225"]["Close"], days), "CSZ": csz, "rules": rules}


def csz_kw(S: pd.DataFrame, m, days) -> dict:
    return R5.sizing_kw(R5.M_CAP, days=days, tick_mult=R5.ticks_from(S["ticker"], S["date"], m))


def runs(W: dict, e: str, M: dict) -> dict:
    days = W["ctx"][e]["days"]
    S, m = M["CSZ"][e]
    return {"VMS": R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(M["VMS"], days)), "CSZ": csz_kw(S, m, days)}


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, M: dict) -> dict:
    pools = R5.other_pools(W)
    out = {k: {} for k in IDS}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = pools[s]
        out["VMS"][s] = R5.s5_sizing(X["xs"].to_numpy(float), R1.at_dates(M["VMS"], X["date"]))
        out["CSZ"][s] = R5.s5_sizing(X["xs"].to_numpy(float), csz_mult(X, *M["rules"][fold]))
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
        mv = R1.at_dates(M["VMS"], win)
        mt = R1.at_dates(M["VMS"], sig) if len(sig) else np.array([])
        S, m = M["CSZ"][e]
        key = {(str(t), pd.Timestamp(d).normalize()): x for t, d, x in zip(S["ticker"], pd.to_datetime(S["date"]), m)}
        tc = np.array([key.get((str(t), pd.Timestamp(d).normalize()), np.nan) for t, d in zip(tr["ticker"], sig)]) if len(sig) else np.array([])
        out[e] = {"days": int(len(win)), "b1_trades": int(len(tr)),
                  "VMS": {"mean": round(float(np.mean(mv)), 3), "up_days": round(float((mv > 1).mean() * 100), 1), "down_days": round(float((mv < 1).mean() * 100), 1),
                          "trades_mean": round(float(np.mean(mt)), 3) if len(mt) else None, "trades_up": int((mt > 1).sum()), "trades_down": int((mt < 1).sum())},
                  "CSZ": {"signals": int(len(S)), "signals_up": int((m > 1).sum()), "trades_matched": int(np.isfinite(tc).sum()), "trades_up": int((tc > 1).sum())}}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop5_r02_volc.py", "scripts/loop5_r01_layer.py", "scripts/research_loop5.py",
                                 "scripts/loop4_r04_xsmodel.py", "scripts/combo_all_common.py", "scripts/candle_portfolio.py", "scripts/loop3_r03_yenexit.py",
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
           "scale": scale(W, M, b1_trades), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


_f = R1._f
NAMES = {"VMS": "按日経的波动调仓位（平静 → 最多 34%、动荡 → 最少 12.5%）", "CSZ": "C 的分数最高的三分之一每只 34%"}


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 第五个研究循环（仓位结构）第 2 轮：按市场波动调仓位 VMS / 按 C 的分数加大 CSZ（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop5_r02_volc.py 开头）", ""]
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
    L += ["", "规模（不参与判定）："]
    for e in L2.ERAS:
        x = res["scale"][e]
        v, c = x["VMS"], x["CSZ"]
        L.append(f"- {e}：B1 的日本个股 {x['b1_trades']} 笔；VMS 倍数平均 {v['mean']}（加大的天 {v['up_days']}% / 减小 {v['down_days']}%；成交的倍数平均 {v['trades_mean']}、"
                 f"加大 {v['trades_up']} / 减小 {v['trades_down']} 笔）；CSZ B1 会买的信号 {c['signals']} 个里加大 {c['signals_up']} 个，成交（对上 {c['trades_matched']} 笔）里加大 {c['trades_up']} 笔")
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
    print(json.dumps({"scale": scale(W, M, b1), "rules_cells": {e: [k for k, r in M["rules"][e][0].items() if r is not None] for e in L2.ERAS},
                      "hi": {e: M["rules"][e][1] for e in L2.ERAS}}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① VMS 倍数全为 1、CSZ 不加任何信号（同一条代码路径）→ 与 B1 逐项相同；② 倍数 ≠ 1 的天数 / 信号数 > 0（不看收益）。"""
    W = L2.load()
    M = inputs(W)
    days = pd.DatetimeIndex(W["ctx"]["J"]["days"])
    rb = L2.run(W, "J")
    r1 = L2.run(W, "J", **R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(pd.Series(1.0, index=M["days"]), days)))
    S, m = M["CSZ"]["J"]
    r2 = L2.run(W, "J", **csz_kw(S, np.ones(len(S)), days))
    same = {"VMS": all(rb.get(x) == r1.get(x) for x in R5.WIRING_KEYS), "CSZ": all(rb.get(x) == r2.get(x) for x in R5.WIRING_KEYS)}
    n = {"VMS": int((R1.at_dates(M["VMS"], days) != 1).sum()), "CSZ": int((m != 1).sum())}
    print(json.dumps({"ones_same_as_b1": same, "nonunit_J": n}, ensure_ascii=False))
    return 0 if all(same.values()) and all(v > 0 for v in n.values()) else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, k, base, ks = _G["W"], _G["M"], _G["k"], _G["base"], _G["ks"]
    try:
        tot = 0.0
        for i, e in enumerate(L2.ERAS):
            days = W["ctx"][e]["days"]
            if k == "VMS":
                kw = R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(R5.shift_mult(M["VMS"], ks[int(seed)]), days))
            else:
                S, m = M["CSZ"][e]
                kw = csz_kw(S, R5.permute_mult(m, int(seed)), days)
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
    ks = R5.size_shift_ks(len(M["days"])) if k == "VMS" else None
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
    shape = "每日倍数循环平移" if k == "VMS" else "倍数在信号之间随机打乱"
    L = [f"# 第五个研究循环第 2 轮 第二关：{k} vs 400 次{shape}（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
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
    ap = argparse.ArgumentParser(description="第五个研究循环第 2 轮：VMS / CSZ（仓位：按市场波动 / 按 C 的分数）")
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
