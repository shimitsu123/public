"""loop_common.py — 研究循环（2026-10-01 登记，规则 scripts/research_loop.py）的共用部分：基准 B0 与账户回测接口。

B0 = 今天（2026-10-01）模拟盘的规则（var/sim.json）里能在 Z / E / J 历史上重现的部分：
  个股层 S0C2：日経225 突破、4 个名额 × 权益 25%、单只 ≤ 34%、按名额买不到一手就跳过、新仓倍数 = 量化状态层 × 宏观层 × 板块倾斜、
    立花个別コース费用、当时真实的一手（J）；W2（周线量比 ≥ 1.0）；
  C 关联搭配：留一年代版 —— 每个年代用另外两个年代的 W2 信号学（scripts/combo_all_common.fit_c / apply_c，= combo_all_study 7f2ca59、
    combo2_study 的「现行（W2 + C）」）；模拟盘冻结的那一份（qbreak/combo_c.RULE）是三个年代一起学的，放在历史上是样本内，不用；
  离场 X6（吊灯止损：收盘 < 持有以来最高价 − 3 × ATR14）；
  闲置资金 Q1：纳指 1545（合成价）+ 美股牛熊分界（熊 → 现金）—— scripts/equity_idle_study 同一做法（spec_a("Q1")）；
  前向记录判断层的市场层：scripts/fwd_judgment_check 的 MA（n = 0 / 1 / ≥2 → 日本个股新仓 ×1 / ×0.75 / ×0.5，按成交日；
    回测里与原有倍数相乘，实时是取小 → 略保守；A5 K4 2026-10-01 起不计分，这里同样不计）。
  不在里面（没有历史）：判断层的个股层 B1〜B7、回撤 45% HALT（以前各研究同样）。
窗口：Z 2001-01〜2006-09、E 2006-10〜2016-09、J 2017-01〜2026-09-30（J 的终点固定，循环中途新的 K 线不改基准）；
前后两半 = scripts/leap_common.HALVES（J 的后一半同样到 2026-09-30）。
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("QB_DROP_ZERO_VOL", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ERAS = ("Z", "E", "J")
J_END = "2026-09-30"
KEYS = ("cagr", "dd", "calmar", "n", "mean", "win")


def fix_j_end(ctx: dict) -> dict:
    """J 的回测终点与窗口（含两半）固定到 J_END（seg_stats 的终点是「之前」→ 用下一天）。"""
    if ctx.get("era") != "J":
        return ctx
    nxt = str((pd.Timestamp(J_END) + pd.Timedelta(days=1)).date())
    w = {k: (a, nxt if (b is None or pd.Timestamp(b) > pd.Timestamp(J_END)) else b) for k, (a, b) in ctx["windows"].items()}
    return {**ctx, "end": J_END, "windows": w}


def c_masks(SM: dict, D: dict, A: dict) -> dict[str, dict[str, np.ndarray]]:
    """C 留一年代：每个年代用另外两个年代的 W2 信号学 → 这个年代 C 跳过的（票, 信号日）在 W2 掩码上再关掉。"""
    import combo_all_common as CA
    out = {}
    for e in ERAS:
        rules = CA.fit_c([D[x] for x in ERAS if x != e])
        keep = CA.apply_c(rules, A[e])
        fa = SM[e]["fa"]
        m = {t: np.asarray(SM[e]["keep"][t], bool).copy() for t in fa}
        tk = A[e]["ticker"].to_numpy()[~keep]
        dd = pd.to_datetime(A[e]["date"]).to_numpy()[~keep]
        for t, d in zip(tk, dd):
            if t in m:
                m[t][fa[t].index.get_loc(pd.Timestamp(d))] = False
        out[e] = m
    return out


def q1_spec() -> tuple[dict, dict, dict, dict]:
    """闲置资金 Q1（equity_idle_study 同一段代码）→ (回测参数, 原始输入, 合成 K 线, 牛熊)。"""
    import equity_idle_study as EI
    inp = EI.load_inputs()
    fr, _ = EI.assets(inp)
    bear = EI.bears(inp)
    return EI.spec_a("Q1", fr, bear), inp, fr, bear


def ma_factor() -> pd.DataFrame:
    """判断层市场层每个日本交易日（信号日收盘）的倍数（fwd_judgment_check.daily_mults；A5 不计分 → K4 不取）。"""
    import fwd_judgment_check as FC
    from qbreak import fwd_judgment as FJ
    H = FJ.market_history()
    return FC.daily_mults(H, pd.Series(False, index=H.index))


def fill_scale(factor: pd.Series, days) -> pd.Series:
    import fwd_judgment_check as FC
    return FC.fill_scale(factor, pd.DatetimeIndex(days))


def load(smoke_names: list[str] | None = None) -> dict:
    """B0 的全部输入：{p0, px, SM, D, A, CM, q1, inp, assets, bear, MA, ctx, run_fn, fr, kw}（每个年代一套）。"""
    import combo_all_posthoc as PH
    import combo_all_study as CS
    import leap_confirm as LF
    from qbreak import exit_rules as EXR
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    p = load_params(market="JP")
    p0 = SF.no_w2_params(p)
    px = EXR.apply(p, "X6")
    SM = CS.load_samples(p0, smoke_names)
    D, A, _ = PH.build_panel()
    CM = c_masks(SM, D, A)
    q1, inp, fra, bear = q1_spec()
    M = ma_factor()
    W = {"p": p, "p0": p0, "px": px, "SM": SM, "D": D, "A": A, "CM": CM, "q1": q1, "inp": inp, "assets": fra, "bear": bear, "MA": M,
         "ctx": {}, "run_fn": {}, "fr": {}, "fr_w2": {}, "kw": {}}
    for e in ERAS:
        ctx = fix_j_end(SM[e]["ctx"])
        fa = SM[e]["fa"]
        fr_w2 = LF.with_mask(fa, SM[e]["keep"])
        W["ctx"][e] = ctx
        W["run_fn"][e] = LF.runner(ctx, fr_w2)
        W["fr_w2"][e] = fr_w2
        W["fr"][e] = LF.with_mask(fa, CM[e])
        W["kw"][e] = {**q1, "em_scale": fill_scale(M["MA"], ctx["days"])}
    return W


def mul_scale(a: pd.Series | None, b: pd.Series | None) -> pd.Series | None:
    """两个按成交日的新仓倍数相乘（b 对齐到 a 的日子，缺 = 1）。"""
    if a is None:
        return b
    if b is None:
        return a
    return a * b.reindex(a.index.union(b.index)).ffill().reindex(a.index).fillna(1.0)


def run(W: dict, e: str, fr: dict | None = None, em_mult: pd.Series | None = None, **over) -> dict:
    """B0（或在它上面改一处）在年代 e 的账户：{cagr, dd, calmar, n, mean, win, h1, h2, years}。
    fr = 换掉买点掩码；em_mult = 再乘的新仓倍数（按成交日）；over = 覆盖 / 追加 candle_portfolio.run 的参数（例：core_expo）。"""
    import leap_confirm as LF
    import pit_retrain_study as PRS
    ctx = W["ctx"][e]
    PRS.PitEngine.DELIST = ctx["delist"]                                     # runner 是缓存的 → 每次重设
    kw = dict(W["kw"][e])
    if em_mult is not None:
        kw["em_scale"] = mul_scale(kw.get("em_scale"), em_mult)
    kw.update(over)
    r = LF.run(ctx, W["run_fn"][e], fr if fr is not None else W["fr"][e], W["px"], **kw)
    out = {k: r[e][k] for k in KEYS}
    out["h1"], out["h2"] = r[f"{e}1"]["calmar"], r[f"{e}2"]["calmar"]
    out["years"] = r.get("_years") or {}
    return out


def baseline(W: dict) -> dict[str, dict]:
    return {e: run(W, e) for e in ERAS}


def repro_c(W: dict) -> dict[str, dict]:
    """先决条件用：只有 W2 + C、闲置资金 1655（回测框架缺省）、不加判断层（J 同样到 J_END）
    → 应与 combo_all_study（7f2ca59）/ combo2_study 的「现行（W2 + C）」账户一致。"""
    import leap_confirm as LF
    import pit_retrain_study as PRS
    out = {}
    for e in ERAS:
        ctx = W["ctx"][e]
        PRS.PitEngine.DELIST = ctx["delist"]
        r = LF.run(ctx, W["run_fn"][e], W["fr"][e], W["px"])
        out[e] = {k: r[e][k] for k in KEYS}
    return out
