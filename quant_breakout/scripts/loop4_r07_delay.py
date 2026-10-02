"""loop4_r07_delay.py — 第四个研究循环（选股）第 7 轮：对大盘消息反应最快（价格延迟最小）的三分之一不买 —— PDL
（2026-10-03 登记；先提交后只运行一次；用掉 1 个做法 → 10 / 20；新家族「选股·信息扩散」1 / 3）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。
循环的规则：scripts/research_loop4.py（只限选股；判定同第三个循环；选股类第二关的随机挡事先写定）；基准 B1：scripts/loop2_common.py。
为什么（照实写）：
  - 文献：Hou & Moskowitz（2005，Review of Financial Studies「Market frictions, price delay, and the cross-section of expected returns」）—— 股价对市场消息反应慢
    （价格延迟大）的股票之后收益更高；Hong & Stein（1999）/ Hong, Lim & Stein（2000）—— 信息扩散慢的股票趋势更容易延续。突破是延续型的买法 →
    反应最快（延迟最小、信息已经被价格吃掉）的那部分突破之后更难延续。
  - C 的 53 个特征里没有价格延迟（有 β、相关、波动、成交额，但没有「对滞后的市场收益有多敏感」）。以前的选股盘点里也没有。
  - 照实写：这一轮是在第 1〜6 轮都不过、名额诊断（B1 平均只拿 0.64 只）之后选的；方向（挡延迟小的）按文献写定、只试这一个方向；先验中偏弱
    （日経225 都是大盘股，延迟差别小；延迟最小的多是成交最活跃的大票，Z 2005 的赢家里可能有不少）。
做法：每个月末 t：每只票过去 52 周（至少 40 周）的周收益（周五收盘）对日経225 周收益回归 ——
  只有当周（受限）R²_r 与当周 + 前 1〜4 周（不受限）R²_u → 价格延迟 D1 = 1 − R²_r ÷ R²_u（R²_u ≤ 0 → 算不出）；
  当月横截面（那个年代账户的日本个股池；W / Jx 各自的池子）里 D1 最低的三分之一（≤ 1/3 分位）→ 月 t+1 的信号不开新仓（em_tick 0）；算不出的不挡。
  其余 —— W2 + C 的买点、X6 等离场、核心 FJE、判断层 —— 全部同 B1。参数（52 周、40 周、4 个滞后、三分之一）都是文献的设定，一次写定（S6 不适用）。
S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C 那一折）按各自池子的横截面挡，保留的 vs 全部，胜率差、每笔差都要 ≥ 0。
第一关：research_loop4.stage1（trade = S5，lenses = None，posthoc = None）。
第二关（第一关全过才做；另行登记后只运行一次）：kind = "stock"，形状 = random_month_block（每个月从同一个池子里随机挑与真实同样多的票挡掉；种子 [20261003, s]）。
接线核对（登记前，不看候选的收益）：J 年代 ① 挡的集合为空 → 账户与 B1 逐项相同；② em_tick 对数 > 0。
只描述（不参与判定）：各年代被挡的信号与成交、个股笔数、每年收益差；W / Jx 被挡的信号的胜率 / 每笔。
事前预期（照实写，写在看结果之前）：日経225 里延迟差别小、挡掉的多是大票 → Z 可能少赚；第一关约 3%；第二关约 10% → 「更好候选」约 0.3%。
运行：python scripts/loop4_r07_delay.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）。输出 var/out/loop4_r07_delay.md / .json。非投资建议。
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
import loop3_r10_resmom as RM                                                # noqa: E402
import research_loop4 as R4                                                  # noqa: E402

ROUND = 7
IDS = ("PDL",)
FAMILY = {"PDL": "选股·信息扩散"}
POSTHOC = False
KIND = "stock"
WIN_W, MIN_W, LAGS = 52, 40, 4
LOW_Q = 1 / 3
OUT = "loop4_r07_delay"
CORE = X3.CORE


# ───────────────────────── 纯函数（tests/test_loop4_r07.py） ─────────────────────────
def weekly_ret(close: pd.Series) -> pd.Series:
    """日收盘 → 周收益（周五为止的最后一个收盘；索引 = 周五）。"""
    c = close.astype(float).dropna()
    return c.resample("W-FRI").last().pct_change()


def _r2(y: np.ndarray, X: np.ndarray) -> float:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    sse = float(((y - X @ beta) ** 2).sum())
    sst = float(((y - y.mean()) ** 2).sum())
    return 1.0 - sse / sst if sst > 0 else np.nan


def delay_d1(y: np.ndarray, M: np.ndarray) -> float:
    """y = 个股周收益；M = 市场周收益的当周与前 1〜LAGS 周（列 0 = 当周）。D1 = 1 − R²(当周) ÷ R²(当周 + 滞后)；R²_u ≤ 0 → NaN。"""
    one = np.ones((len(y), 1))
    ru = _r2(y, np.hstack([one, M]))
    rr = _r2(y, np.hstack([one, M[:, :1]]))
    if not np.isfinite(ru) or ru <= 1e-12 or not np.isfinite(rr):
        return np.nan
    return 1.0 - rr / ru


def delay_monthly(ri: pd.Series, rm: pd.Series, months: pd.PeriodIndex) -> pd.Series:
    """每个月末：最后 WIN_W 周（周五 ≤ 月末）、个股与市场（含滞后）都有值的周 ≥ MIN_W → D1；否则 NaN。"""
    F = pd.concat({"y": ri.reindex(rm.index), **{f"m{k}": rm.shift(k) for k in range(LAGS + 1)}}, axis=1).dropna()
    idx = F.index
    Y, M = F["y"].to_numpy(float), F[[f"m{k}" for k in range(LAGS + 1)]].to_numpy(float)
    out = np.full(len(months), np.nan)
    for j, m in enumerate(months):
        hi = int(idx.searchsorted(m.to_timestamp(how="end"), side="right"))
        lo = max(0, hi - WIN_W)
        if hi - lo >= MIN_W:
            out[j] = delay_d1(Y[lo:hi], M[lo:hi])
    return pd.Series(out, index=months)


def bottom_third(P: pd.DataFrame) -> pd.DataFrame:
    """每个月：≤ 当月横截面 1/3 分位 → 被挡（True）；NaN → 不挡。"""
    q = P.quantile(LOW_Q, axis=1, numeric_only=True)
    return P.le(q, axis=0) & P.notna()


# ───────────────────────── 输入 ─────────────────────────
def delay_table(fa: dict, names, rm: pd.Series, months: pd.PeriodIndex) -> pd.DataFrame:
    keys = [t for t in names if str(t).endswith(".T") and t not in CORE and t in fa]
    P = pd.DataFrame({t: delay_monthly(weekly_ret(fa[t]["Close"]), rm, months) for t in keys}, index=months)
    return bottom_third(P)


def inputs(W: dict) -> dict:
    """{年代 / W / Jx: PDL 被挡表（行 = 月，列 = 票）}。"""
    months = RM.market_m(W).index
    rm = weekly_ret(W["inp"]["n225"]["Close"])
    SM = W["SM"]
    return {key: delay_table(fa, names, rm, months)
            for key, fa, names in [(e, SM[e]["fa"], RM.era_names(W, e)) for e in L2.ERAS]
            + [("W", SM["W"]["fa"], list(SM["W"]["fa"])), ("Jx", SM["J2"]["fa"], list(SM["J2"]["fa"]))]}


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict, G: dict) -> dict:
    import combo_all_common as CA
    D = W["D"]
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    out = {"PDL": {}}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s][CA.apply_c(R1[fold], D[s])]
        net = X["net"].to_numpy(float)
        g = RM.gate_of(G[s], X["ticker"].to_numpy(), X["date"].to_numpy())
        dl = CA.delta(net, ~g)
        gone = net[g]
        out["PDL"][s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                         "gone_win": float((gone > 0).mean() * 100) if len(gone) else None, "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


# ───────────────────────── 规模（只看 B1 的信号与成交） ─────────────────────────
def scale(W: dict, G: dict, b1_trades: dict) -> dict:
    import combo_all_common as CA
    D, A = W["D"], W["A"]
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        X = A[e][CA.apply_c(CA.fit_c([D[x] for x in L2.ERAS if x != e]), A[e])]
        tr = X3.jp_stock_trades(b1_trades[e], a, b)
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        sig = np.asarray([days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])]) if len(tr) else np.array([])
        gx = RM.gate_of(G[e], X["ticker"].to_numpy(), X["date"].to_numpy())
        gt = RM.gate_of(G[e], tr["ticker"].to_numpy(), sig) if len(tr) else np.array([], bool)
        out[e] = {"signals": int(len(X)), "b1_trades": int(len(tr)), "PDL": {"signals_blocked": int(gx.sum()), "trades_blocked": int(gt.sum())}}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop4_r07_delay.py", "scripts/loop3_r10_resmom.py",
                                 "scripts/candle_portfolio.py", "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/research_loop4.py", "scripts/research_loop3.py", "scripts/research_loop2.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def runs(W: dict, e: str, G: dict) -> dict:
    return {"PDL": {"em_tick": RM.em_tick_of(G[e], W["ctx"][e]["days"])}}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    G = inputs(W)
    print(f"分数算完（{time.time() - t0:.0f}s）", flush=True)
    reg = R4.load_state().get("baseline") or {}
    base, cand, trades, b1_trades = {}, {k: {} for k in IDS}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        trades[e] = {"B1": rb["n"]}
        for k, over in runs(W, e, G).items():
            rc = L2.run(W, e, **over)
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
            trades[e][k] = rc["n"]
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W, G)
    s1 = {k: R4.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"loop": 4, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades,
           "ticks": {e: len(runs(W, e, G)["PDL"]["em_tick"]) for e in L2.ERAS}, "scale": scale(W, G, b1_trades), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1, o = res["stage1"]["PDL"], res["other_stocks"]["PDL"]
    L = [f"# 第四个研究循环（选股）第 7 轮：价格延迟最小的三分之一不买 PDL（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop4_r07_delay.py 开头）", "",
         f"- **PDL（对大盘消息反应最快的三分之一 → 下个月不开新仓）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R4.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
         f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
         f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | PDL（Calmar 差） | 个股笔数 B1 → PDL |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['PDL'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {t['B1']} → {t['PDL']} |")
    L += ["", "规模与被挡的（不参与判定）："]
    for e in L2.ERAS:
        x = res["scale"][e]
        L.append(f"- {e}：B1 会买的信号 {x['signals']} 个、B1 的日本个股 {x['b1_trades']} 笔；em_tick {res['ticks'][e]} 对；PDL 挡信号 {x['PDL']['signals_blocked']} 个、"
                 f"B1 实际成交 {x['PDL']['trades_blocked']} 笔")
    for s in ("W", "Jx"):
        z = o[s]
        L.append(f"- PDL {s}：B1 会买的信号 {z['n']} 个，挡掉 {z['gone_n']} 个（胜率 {_f(z['gone_win'], '{:.1f}')}%、每笔 {_f(z['gone_mean'], '{:+.2f}')}%）；"
                 f"保留 {z['kept']} 个 → 胜率差 {_f(z['dwin'], '{:+.2f}')} pp、每笔差 {_f(z['dmean'], '{:+.2f}')} pp")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["PDL"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- PDL {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R4.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L2.load()
    G = inputs(W)
    b1 = {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
    print(json.dumps({"scale": scale(W, G, b1), "ticks": {e: len(runs(W, e, G)["PDL"]["em_tick"]) for e in L2.ERAS},
                      "blocked_cells": {k: int(v.to_numpy().sum()) for k, v in G.items()}}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 挡的集合为空 → 账户与 B1 逐项相同；② em_tick 对数 > 0（不看收益）。"""
    W = L2.load()
    G = inputs(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    same = all(rb.get(x) == L2.run(W, "J", em_tick={}).get(x) for x in keys)
    n = len(runs(W, "J", G)["PDL"]["em_tick"])
    print(json.dumps({"empty_same_as_b1": same, "count_J": n}, ensure_ascii=False))
    return 0 if same and n > 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第四个研究循环第 7 轮：PDL（选股：价格延迟最小的三分之一不买）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
