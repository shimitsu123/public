"""loop4_r05_weakvol.py — 第四个研究循环（选股）第 5 轮的候选（**规模核对后不登记、没有运行第一关、不占名额**）：日経在 200 日线下（弱市）时把量的门槛提高
—— W2T（周线量比 ≥ 1.5）/ VTZ（突破日量比 ≥ 2.0）（家族「选股·门槛随市况」）。
不登记的理由（2026-10-03 规模核对，只数个数）：B1 会买的信号里 W2T 挡 20 / 41 / 19 个、VTZ 14 / 28 / 11 个，但 **B1 实际的日本个股成交 35 / 43 / 63 笔里一笔都碰不到**
—— B1 的 141 笔日本个股全部在日経 200 日线上开仓（弱市新仓倍数为 0），弱市的选股对账户没有作用（与第二个循环的 EBG、第三个循环的 MXR / IVH 同样处理）。
下面是原来写好的规则（留作记录）。

用户（2026-10-02 23:40 JST）：「继续研究循环 6个小时之内不停 直到找到比现在好的选股算法」。
循环的规则：scripts/research_loop4.py（只限选股；判定同第三个循环；选股类第二关的随机挡事先写定）；基准 B1：scripts/loop2_common.py。
为什么这两个（照实写）：
  - 第 1〜4 轮的过滤都输在「挡掉 Z 2003〜2005 牛市里的大赢家」（个股层在 Z 的贡献最大：事后诊断里不做日本个股 Z −0.603）。这一轮只在日経弱的时候
    （信号日 日経225 收盘 < 200 日均线）收紧：牛市里一笔都不挡，Z 2003 年 5 月以后的主升浪原则上碰不到。
  - B1 在弱市里几乎没有选股：C 只在「日経在 200 日线上且 VIX < 20」的格子起作用（其余三格不动），弱市只剩 W2（周线量比 ≥ 1.0）一道门槛。
  - 文献：「放量」的突破 / 高成交量之后表现更好（Gervais, Kaniel & Mingelgrin 2001 的 high-volume return premium；Lee & Swaminathan 2000）；
    熊市里的反弹多是空头回补、量不足的更容易失败（经验，没有直接文献 → 先验中等偏弱）。
  - 门槛：W2T 周线量比 ≥ 1.5（W2 的 1.0 再高一半，整数、没调过）；VTZ 突破日量比 ≥ 2.0（= qbreak/idio_forward.K2_VR，已经登记过的前向记录门槛）。
  - 以前的选股盘点（2026-10-02 23:40 那一节）里没有「按大盘状况换量的门槛」；ERG（第一个循环）是弱市一律不开新仓（择时，不是选股），这里只挑量不够的。
做法：两个都是逐个信号判定（研究面板 A 的特征：n225_ma200 = 信号日 日経收盘 ÷ 200 日均线 − 1、w5v = 周线量比（W2 的连续值）、vr1 = 突破日量比 ÷ 之前 20 日均量）
  → em_tick 0（不开新仓，名额留给下一个候选、钱留在核心）；其余 —— W2 + C 的买点、X6 等离场、核心 FJE、判断层 —— 全部同 B1。
  - W2T：n225_ma200 < 0 且 w5v < 1.5 → 挡；VTZ：n225_ma200 < 0 且 vr1 < 2.0 → 挡；有缺值 → 不挡。
S5：W（扩大池 2006〜2016）与 Jx（时点 TOPIX 1000 里非日経225，2017〜）里 B1 会买的信号（W2 + C 那一折）按同样的定义挡，保留的 vs 全部，胜率差、每笔差都要 ≥ 0。
第一关：research_loop4.stage1（trade = S5，lenses = None，posthoc = None），两个各自判定。参数一次写定（S6 不适用）；不是事后组合（S7 不适用）。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "stock"，形状 = random_signal_block（每个候选信号以这个做法在那个年代实际挡掉的比例随机挡；
  种子 numpy.random.default_rng([20261003, s])）。
接线核对（登记前，不看候选的收益）：J 年代 ① 挡的集合为空 → 账户与 B1 逐项相同；② em_tick 对数 > 0。
只描述（不参与判定）：各年代被挡的信号与成交、个股笔数、每年收益差；W / Jx 被挡的信号的胜率 / 每笔。
事前预期（照实写，写在看结果之前）：只在弱市挡、Z 牛市不碰 → 账户差小；第一关各约 5%；第二关各约 10% → 「更好候选」约 1%。
运行：python scripts/loop4_r05_weakvol.py（第一关）；--scale（只数个数）；--wiring（登记前的接线核对）。输出 var/out/loop4_r05_weakvol.md / .json。非投资建议。
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
import loop3_r12_corediv as R12                                              # noqa: E402
import research_loop4 as R4                                                  # noqa: E402

ROUND = 5
DROPPED = True                                                                # 规模核对后不登记（B1 在弱市没有成交）
IDS = ("W2T", "VTZ")
FAMILY = {"W2T": "选股·门槛随市况", "VTZ": "选股·门槛随市况"}
POSTHOC = False
KIND = "stock"
W2T_MIN, VTZ_MIN = 1.5, 2.0                                                  # 弱市里周线量比 / 突破日量比的门槛
OUT = "loop4_r05_weakvol"


# ───────────────────────── 纯函数（tests/test_loop4_r05.py） ─────────────────────────
def weak(X: pd.DataFrame) -> np.ndarray:
    """信号日 日経225 收盘在 200 日均线之下（n225_ma200 < 0；缺值 → 不算弱）。"""
    m = X["n225_ma200"].to_numpy(float)
    with np.errstate(invalid="ignore"):
        return np.isfinite(m) & (m < 0)


def gate(X: pd.DataFrame, col: str, thr: float) -> np.ndarray:
    """弱市且 col < thr → 挡（col 缺值 → 不挡）。"""
    v = X[col].to_numpy(float)
    with np.errstate(invalid="ignore"):
        return weak(X) & np.isfinite(v) & (v < thr)


def gates(X: pd.DataFrame) -> dict:
    return {"W2T": gate(X, "w5v", W2T_MIN), "VTZ": gate(X, "vr1", VTZ_MIN)}


# ───────────────────────── 输入 ─────────────────────────
def ticks(W: dict) -> dict:
    """{年代: {W2T: em_tick, VTZ: em_tick}}：这个年代全部 W2 信号（A；B1 的候选是它的子集）里被挡的。"""
    out = {}
    for e in L2.ERAS:
        A = W["A"][e]
        g = gates(A)
        out[e] = {k: R12.tick_of(A["ticker"].to_numpy(), A["date"].to_numpy(), g[k]) for k in IDS}
    return out


# ───────────────────────── S5 ─────────────────────────
def other_stocks(W: dict) -> dict:
    import combo_all_common as CA
    D = W["D"]
    R1 = {e: CA.fit_c([D[x] for x in L2.ERAS if x != e]) for e in L2.ERAS}
    out = {k: {} for k in IDS}
    for s, fold in (("W", "E"), ("Jx", "J")):
        X = D[s][CA.apply_c(R1[fold], D[s])]
        net = X["net"].to_numpy(float)
        gs = gates(X)
        for k in IDS:
            g = gs[k]
            dl = CA.delta(net, ~g)
            gone = net[g]
            out[k][s] = {"n": int(dl["n"]), "kept": int(dl["kept"]), "dwin": dl["dwin"], "dmean": dl["dmean"], "gone_n": int(len(gone)),
                         "gone_win": float((gone > 0).mean() * 100) if len(gone) else None,
                         "gone_mean": float(gone.mean()) if len(gone) else None}
    return out


# ───────────────────────── 规模（只看 B1 的信号与成交） ─────────────────────────
def scale(W: dict, b1_trades: dict) -> dict:
    import combo_all_common as CA
    D, A = W["D"], W["A"]
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        X = A[e][CA.apply_c(CA.fit_c([D[x] for x in L2.ERAS if x != e]), A[e])]
        tr = X3.jp_stock_trades(b1_trades[e], a, b)
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        sig = np.asarray([days[max(0, int(days.searchsorted(pd.Timestamp(d))) - 1)] for d in pd.to_datetime(tr["entry_date"])]) if len(tr) else np.array([])
        gx = gates(X)
        key = {(str(t), pd.Timestamp(d).normalize()): i for i, (t, d) in enumerate(zip(A[e]["ticker"], pd.to_datetime(A[e]["date"])))}
        ga = gates(A[e])
        idx = [key.get((str(t), pd.Timestamp(d).normalize())) for t, d in zip(tr["ticker"], sig)] if len(tr) else []
        gt = {k: np.array([i is not None and bool(ga[k][i]) for i in idx], bool) for k in IDS}
        out[e] = {"signals": int(len(X)), "b1_trades": int(len(tr)),
                  **{k: {"signals_blocked": int(gx[k].sum()), "trades_blocked": int(gt[k].sum())} for k in IDS}}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop4_r05_weakvol.py", "scripts/loop3_r12_corediv.py",
                                 "scripts/candle_portfolio.py", "scripts/loop3_r03_yenexit.py", "scripts/loop2_common.py", "scripts/loop_common.py",
                                 "scripts/research_loop4.py", "scripts/research_loop3.py", "scripts/research_loop2.py", "qbreak/unified.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def runs(tk: dict, e: str) -> dict:
    return {k: {"em_tick": tk[e][k]} for k in IDS}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    tk = ticks(W)
    print(f"分数算完（{time.time() - t0:.0f}s）", flush=True)
    reg = R4.load_state().get("baseline") or {}
    base, cand, trades, b1_trades = {}, {k: {} for k in IDS}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        b1_trades[e] = X3.last_trades()
        base[e] = {**_acct(rb), "years": rb.get("years")}
        trades[e] = {"B1": rb["n"]}
        for k, over in runs(tk, e).items():
            rc = L2.run(W, e, **over)
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
            trades[e][k] = rc["n"]
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    os_ = other_stocks(W)
    s1 = {k: R4.stage1(cand[k], base, trade=os_[k], posthoc=None) for k in IDS}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"loop": 4, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "other_stocks": os_, "stock_trades": trades,
           "ticks": {e: {k: len(tk[e][k]) for k in IDS} for e in L2.ERAS}, "scale": scale(W, b1_trades), "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    desc = {"W2T": "日経在 200 日线下时周线量比 < 1.5 → 不开新仓", "VTZ": "日経在 200 日线下时突破日量比 < 2.0 → 不开新仓"}
    L = [f"# 第四个研究循环（选股）第 5 轮：弱市提高量的门槛 W2T / VTZ（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop4_r05_weakvol.py 开头）", ""]
    for k in IDS:
        s1, o = res["stage1"][k], res["other_stocks"][k]
        L.append(f"- **{k}（{desc[k]}）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R4.FAIL1}**"
                 f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
                 f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；"
                 f"S5（W 胜率 {_f(o['W']['dwin'], '{:+.2f}')} pp / 每笔 {_f(o['W']['dmean'], '{:+.2f}')} pp；"
                 f"Jx {_f(o['Jx']['dwin'], '{:+.2f}')} / {_f(o['Jx']['dmean'], '{:+.2f}')}）：{yn(s1['S5'])}；S6 / S7 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | W2T（Calmar 差） | VTZ（Calmar 差） | 个股笔数 B1 → W2T / VTZ |", "|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        t = res["stock_trades"][e]
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS) + f" | {t['B1']} → {t['W2T']} / {t['VTZ']} |")
    sc = res["scale"]
    L += ["", "规模与被挡的（不参与判定）："]
    for e in L2.ERAS:
        x = sc[e]
        L.append(f"- {e}：B1 会买的信号 {x['signals']} 个、B1 的日本个股 {x['b1_trades']} 笔；全部 W2 信号里挡 "
                 + "、".join(f"{k} {res['ticks'][e][k]} 个" for k in IDS) + "；"
                 + "；".join(f"{k} 挡信号 {x[k]['signals_blocked']} 个、B1 实际成交 {x[k]['trades_blocked']} 笔" for k in IDS))
    for k in IDS:
        for s in ("W", "Jx"):
            o = res["other_stocks"][k][s]
            L.append(f"- {k} {s}：B1 会买的信号 {o['n']} 个，挡掉 {o['gone_n']} 个（胜率 {_f(o['gone_win'], '{:.1f}')}%、每笔 {_f(o['gone_mean'], '{:+.2f}')}%）；"
                     f"保留 {o['kept']} 个 → 胜率差 {_f(o['dwin'], '{:+.2f}')} pp、每笔差 {_f(o['dmean'], '{:+.2f}')} pp")
    for k in IDS:
        for e in L2.ERAS:
            yb, yc = res["base"][e].get("years") or {}, res["cand"][k][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            L.append(f"- {k} {e} 每年收益差（− B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R4.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L2.load()
    b1 = {}
    for e in L2.ERAS:
        L2.run(W, e)
        b1[e] = X3.last_trades()
    tk = ticks(W)
    print(json.dumps({"scale": scale(W, b1), "ticks": {e: {k: len(tk[e][k]) for k in IDS} for e in L2.ERAS}}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 挡的集合为空 → 两个账户都与 B1 逐项相同；② em_tick 对数 > 0（不看收益）。"""
    W = L2.load()
    tk = ticks(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    empty = {"J": {k: {} for k in IDS}}
    same = {k: all(rb.get(x) == L2.run(W, "J", **over).get(x) for x in keys) for k, over in runs(empty, "J").items()}
    n = {k: len(v["em_tick"]) for k, v in runs(tk, "J").items()}
    print(json.dumps({"empty_same_as_b1": same, "counts_J": n}, ensure_ascii=False))
    return 0 if all(same.values()) and all(v > 0 for v in n.values()) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第四个研究循环第 5 轮：W2T / VTZ（选股：弱市提高量的门槛）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数个数（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
