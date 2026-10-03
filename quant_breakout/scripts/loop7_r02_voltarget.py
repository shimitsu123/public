"""loop7_r02_voltarget.py — 第七个研究循环（独立市场验证）第 2 轮：牛市里按自己指数的波动率连续调节仓位 VTX
（2026-10-04 登记；先提交后只运行一次；家族「核心·波动率」2 / 3；kind = cross；事后（看过第一个循环 VT20、第二个循环 VTU 的账户结果之后）→ S7 适用）。

用户（2026-10-04，待办 ㊽）：「把 VCT 加进前向记录 / 然后换别的方向继续研究」。循环的规则：scripts/research_loop7.py 开头。
为什么做这个（照实写）：
  - 第 1 轮 VCX（急跌时减 1/3）17 个市场不成立：真实信号只比随机中位好 +0.007（随机最大比中位高 +0.016）。
  - 「按已实现波动率调仓位」（volatility targeting / volatility-managed portfolio）是核心择时里文献证据最多、跨市场检验最多的一种
    （Moreira & Muir 2017；Harvey et al. 2018「The Impact of Volatility Targeting」：股票类资产上回撤与左尾变小）；这个项目里：
    第一个循环第 1 轮 VT20（B0、日元计）只输在 S2（E −0.053）、J 回撤浅 8 pp；第二个循环第 9 轮 VTU（B1、美元计）第一关全过 +0.184、
    第二关（单一序列 400 次平移）约第 88 百分位、S7 只有 +0.002。单一序列的第二关检验力太低 → 放到 17 个独立市场上检验。
  - 与 VCX 的不同：不要「正在跌」的条件、按波动的大小连续减（比例 = 中位数 / σ20），减得更多、也在高波动的上涨里减。
做法 VTX（VT20 的机制与参数原样：20 日、扩展中位数至少 250 个值、滞后带 0.10、σ20 ≤ 中位数直接回到 1；没有新参数 → S6 不适用；不改个股 → S5 不适用）：
  - 账户（第一关，在 B3 上，本脚本运行一次）：比例 = 美元计纳指总收益的 VT20 比例（loop6_r07_volbond.vt_ratio = 第二个循环 VTU 原样：
    1986-01-01 起的扩展中位数）；东证日的对齐 = 美国日期 ≤ 东证日的最近一个值（同 B3 的「美股熊」、VCT 的信号）；
    引擎的 core_expo["US"]（1545 的目标再乘这个比例；美股熊时 1545 本来就是 0）；减下来的部分留现金（1482 的条件不变 = B3）。
    S7（1987〜2000 只有核心）：第 7 轮 old_core 同一个口径，持仓多一条「美股牛 → 纳指 × 比例（前一天的状态）、其余现金」。
  - 每个市场的通用版（第二关）：自己指数（本币价格指数）的 VT20 比例（qbreak/vct_forward 的 sigma / target / exposure 原样，
    中位数的起点换成这个市场的数据第一天 = 第 1 轮 VCX 同一个算法）；自己的牛熊分界是牛 → 指数 × 比例、其余现金。
  - 第二关 = research_loop7 三（17 个市场、窗口 1998-01-01〜2026-09-30、C1〜C3）；随机对照 = 比例序列（数值）在窗口内、每个市场自己的
    交易日上整体循环平移同一个 k（research_loop7.shift_ks：k 与第 1 轮相同的 400 个）；窗外不动；基准不动。
  - 判定 = 第一关（账户）全过 ∧ 第二关三条都过 → 更好候选；第一关不过 = 「第一关不过」（第二关照样算、只描述）。
接线核对（登记前，不看候选的结果；--wiring）：① 比例全 1 → 三个年代与 B3 逐项相同、17 个市场 Δ 全为 0；② old_core 比例 None = 第 7 轮函数的 B3；
  ③ B3 的引擎参数里没有别的 core_expo；④ 账户的比例 = loop6_r07_volbond.vt_ratio、市场的比例 = vct_forward 的函数（tests/test_loop7_r02.py）。
规模（登记前，只数日子；--scale）：三个年代美股牛的日子里比例 < 1 的比例、段数、平均比例；17 个市场牛的日子里同样的数字；N_min。
只描述（不参与判定）：每个市场的 Δ（全窗口 / 两半）、各市场自己的随机百分位、美国 S&P 500（规则来源）、账户每年收益差、核心换仓笔数。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop7_r02_voltarget.py（第一关 + 第二关，只运行一次）；--scale；--wiring。输出 var/out/loop7_r02_voltarget.md / .json。非投资建议。
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
import loop6_common as L6                                                    # noqa: E402
import loop6_r07_volbond as V                                                # noqa: E402
import loop6_r08_voltrend as X                                               # noqa: E402
import research_loop6 as R6                                                  # noqa: E402
import research_loop7 as R7                                                  # noqa: E402
from qbreak import vct_forward as VF                                         # noqa: E402

ROUND = 2
IDS = ("VTX",)
FAMILY = {"VTX": "核心·波动率"}
KIND = {"VTX": "cross"}
POSTHOC = True
OLD = V.OLD
OUT = "loop7_r02_voltarget"
KEYS = X.KEYS


# ───────────────────────── 规则（纯函数，tests/test_loop7_r02.py） ─────────────────────────
def as_of(x: pd.Series, idx: pd.DatetimeIndex, fill: float = 1.0) -> pd.Series:
    """数值序列 → idx 上（d 日 = 日期 ≤ d 的最近一个值；没有值 = fill）。布尔版是 loop6_r03_earlyreturn.on_idx。"""
    idx = pd.DatetimeIndex(idx)
    return x.astype(float).reindex(idx.union(x.index)).ffill().reindex(idx).fillna(fill)


def ratio_us(ndx_tr: pd.Series) -> pd.Series:
    """账户：美元计纳指总收益的 VT20 比例（第二个循环 VTU 原样 = loop6_r07_volbond.vt_ratio）。"""
    return V.vt_ratio(ndx_tr)


def vtx_over(ratio_t: pd.Series) -> dict:
    """B3 原样 + core_expo["US"]（B3 的 1545 键就是 US；引擎在美股熊时本来就不拿 1545）。"""
    return {"core_expo": {"US": ratio_t.astype(float).clip(0.0, 1.0)}}


def core_weights(bear: pd.Series, ratio: pd.Series, on: pd.Series) -> pd.DataFrame:
    """只有核心（1987〜2000）：B3 的持仓（牛 → 纳指 1；熊 ∧ 负相关 → 美债 1；其余现金），牛的日子纳指 × 比例、其余现金。"""
    b, o = bear.astype(bool), on.astype(bool)
    w = V.core_weights(b, pd.Series(False, index=b.index), o)
    x = ratio.reindex(b.index).astype(float).fillna(1.0).clip(0.0, 1.0)
    w.loc[~b, "u"] = x[~b]
    return w


def market_ratio(close: pd.Series) -> pd.Series:
    """一个市场：自己指数的 VT20 比例（vct_forward 的函数原样，中位数从这个市场的数据第一天起 = 第 1 轮 VCX 同一个算法）。"""
    c = close.dropna().sort_index().astype(float)
    sg = VF.sigma(c)
    return VF.exposure(sg, VF.target(sg, start=str(c.index[0].date())))


def expo(bull: pd.Series, ratio: pd.Series) -> pd.Series:
    """牛 → 比例；其余 0（现金）。"""
    b = bull.astype(bool)
    x = ratio.reindex(b.index).astype(float).fillna(1.0).clip(0.0, 1.0)
    return pd.Series(np.where(b.to_numpy(bool), x.to_numpy(float), 0.0), index=b.index)


def shifted_num(x: pd.Series, k: int | None, w=R7.WINDOW) -> pd.Series:
    """比例（数值）在窗口内（这个市场自己的交易日）整体循环平移 k；窗外不动；None = 不平移（research_loop7.shifted 的数值版）。"""
    s = x.astype(float).copy()
    if k is None:
        return s
    idx = s.index[(s.index >= pd.Timestamp(w[0])) & (s.index <= pd.Timestamp(w[1]))]
    s.loc[idx] = np.roll(s.loc[idx].to_numpy(float), int(k))
    return s


def deltas_num(closes: dict[str, pd.Series], ratios: dict[str, pd.Series], bulls: dict[str, pd.Series], k: int | None,
               spans: dict[str, list[tuple[str, str]]]) -> dict[str, list[float | None]]:
    """research_loop7.deltas 的数值版：每个市场各段 Calmar（候选 = 牛 × 平移后的比例）− 基准（牛 100%）。"""
    out = {}
    for m, c in closes.items():
        b = bulls[m]
        base = R7.nav(c, b.astype(float))
        cand = R7.nav(c, expo(b, shifted_num(ratios[m], k)))
        row = []
        for a, z in spans[m]:
            cb, cc = R7.calmar(base, a, z), R7.calmar(cand, a, z)
            row.append(None if cb is None or cc is None else cc - cb)
        out[m] = row
    return out


# ───────────────────────── 1987〜2000 只有核心（S7） ─────────────────────────
def old_core(W: dict, ratio: pd.Series | None) -> dict:
    """第 7 轮 old_core 同一个口径（日元计纳指不对冲、对冲版美债、S&P 与美债 63 天相关（前一天）、前一天的状态决定当天、换仓扣 0.1% × 换的比例），
    持仓换成本轮的 core_weights；ratio = None → B3。"""
    import equity_idle_study as EI
    import halloween_study as HW
    import loop2_r02_bondrefuge as T2
    import loop6_r01_bondcorr as T
    inp = W["inp"]
    dex = inp["dexjp"].dropna()
    ntr = EI.ndx_tr(inp)
    unh = EI.grow(ntr, -EI.FEE["1545.T"])
    unh = (unh * dex.reindex(unh.index.union(dex.index)).ffill().reindex(unh.index)).dropna()
    bnd = T2.bond_hedged(T2.bond_usd())
    bnd = bnd[bnd.index >= pd.Timestamp(T2.BOND_START)]
    spx = inp["spx"]["Close"].astype(float)
    full = unh.index[unh.index >= pd.Timestamp(T2.BOND_START)]
    ffull = lambda s: s.astype(float).reindex(full.union(s.index)).ffill().reindex(full)      # noqa: E731
    on_u = T.corr_on(ffull(spx), ffull(bnd)).shift(1, fill_value=False)
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    unh, b_px = unh.reindex(idx), ff(bnd)
    b = ff(W["bear"]["US"]).fillna(0.0) > 0.5
    x = ff(ratio).fillna(1.0) if ratio is not None else pd.Series(1.0, index=idx)
    ou = ff(on_u).fillna(0.0) > 0.5
    w = core_weights(b, x, ou).shift(1).fillna(0.0)
    ret = w["u"] * unh.pct_change().fillna(0.0) + w["b"] * b_px.pct_change().fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    cut = ~b & (x < 1.0 - 1e-12)
    out["cut_bull_pct"] = round(float(cut.sum() / max(1, int((~b).sum())) * 100), 1)
    out["ratio_mean_cut"] = round(float(x[cut].mean()), 3) if cut.any() else None
    return out


# ───────────────────────── 输入 / 规模 ─────────────────────────
def account_inputs(W: dict) -> dict:
    """B3 的输入（loop6_r07_volbond.inputs：东证日、美股熊、股债相关、美国日的 VT20 比例）+ 东证日上的比例。"""
    M = V.inputs(W)
    M["ratio_t"] = as_of(M["ratio_us"], M["days"])
    return M


def market_inputs(keys=None) -> dict:
    closes = R7.load_markets(keys)
    bad = [m for m, c in closes.items() if m in R7.MARKETS and not R7.eligible(c)]
    if bad:
        raise RuntimeError(f"数据不够（1996-06-30 之前没有 / 窗口里缺）：{bad}")
    return {"closes": closes, "ratios": {m: market_ratio(c) for m, c in closes.items()}, "bulls": {m: R7.bull(c) for m, c in closes.items()}}


def segments(flag: pd.Series) -> int:
    v = flag.astype(bool).to_numpy()
    return int((v[1:] & ~v[:-1]).sum() + (1 if len(v) and v[0] else 0))


def cut_share(bull: pd.Series, ratio: pd.Series) -> dict:
    """牛的日子里比例 < 1 的比例、段数、这些日子的平均比例、牛的日子全部的平均比例（只数日子）。"""
    b = bull.astype(bool)
    x = ratio.reindex(b.index).astype(float).fillna(1.0)
    cut = b & (x < 1.0 - 1e-12)
    nb = int(b.sum())
    return {"bull_days": nb, "cut_pct": round(float(cut.sum()) / nb * 100, 1) if nb else None, "segments": segments(cut),
            "ratio_mean_cut": round(float(x[cut].mean()), 3) if cut.any() else None,
            "expo_mean_bull": round(float(x[b].mean()), 3) if nb else None}


def account_scale(W: dict, M: dict) -> dict:
    out = {}
    for e in L6.ERAS:
        d = V.era_days(W, e)
        out[e] = cut_share(~V.on_idx(M["bear_t"], d), M["ratio_t"].reindex(d))
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "us_bear": bool(M["bear_t"].iloc[-1]), "ratio": round(float(M["ratio_t"].iloc[-1]), 3)}
    return out


def market_scale(I: dict) -> dict:
    out = {}
    for m, c in I["closes"].items():
        days = R7.window_days(c)
        b = I["bulls"][m].reindex(days).fillna(False).astype(bool)
        out[m] = {"start": str(c.index[0].date()), "days": int(len(days)), "bull_pct": round(float(b.mean() * 100), 1),
                  **cut_share(b, I["ratios"][m].reindex(days))}
    n_min = min(v["days"] for m, v in out.items() if m in R7.MARKETS)
    return {"markets": out, "n_min": int(n_min)}


# ───────────────────────── 运行 ─────────────────────────
def spans_of(c: pd.Series) -> list[tuple[str, str]]:
    days = R7.window_days(c)
    h1, h2 = R7.halves(days)
    return [(str(days[0].date()), str(days[-1].date())), h1, h2]


def run_k(I: dict, k: int | None, keys) -> dict[str, list[float | None]]:
    return deltas_num({m: I["closes"][m] for m in keys}, {m: I["ratios"][m] for m in keys}, {m: I["bulls"][m] for m in keys}, k,
                      {m: spans_of(I["closes"][m]) for m in keys})


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop7_r02_voltarget.py", "scripts/research_loop7.py",
                                 "qbreak/vct_forward.py", "qbreak/bullbear.py", "qbreak/unified.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def stage_one(W: dict, M: dict) -> dict:
    """第一关（账户，B3 上）：三个年代 B3 / VTX + 1987〜2000 只有核心（S7）。"""
    import loop2_r05_ddbrake as R5
    t0 = time.time()
    ov = vtx_over(M["ratio_t"])
    reg = R7.load_state().get("baseline") or {}
    base, cand, trades = {}, {}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B3": nb, "VTX": nc}
        print(f"账户 {e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B3": old_core(W, None), "VTX": old_core(W, M["ratio_us"])}
    unseen = None if old["B3"]["calmar"] is None or old["VTX"]["calmar"] is None else old["VTX"]["calmar"] - old["B3"]["calmar"]
    s1 = R6.stage1(cand, base, posthoc=unseen)
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L6.ERAS}
    return {"ok": bool(s1["ok"]), "stage1": s1, "base": base, "cand": cand, "core_trades": trades, "old": old, "drift": drift,
            "scale": account_scale(W, M), "seconds": round(time.time() - t0)}


def stage_two(I: dict) -> dict:
    """第二关（横展开）：17 个市场的真实 Δ + 400 次同一 k 平移 → research_loop7.judge。"""
    t0 = time.time()
    sc = market_scale(I)
    keys = list(R7.MARKETS)
    real = run_k(I, None, keys)
    ks = R7.shift_ks(sc["n_min"])
    plac, per = [], {m: [] for m in keys}
    for i, k in enumerate(ks):
        r = run_k(I, k, keys)
        full = [v[0] for v in r.values()]
        plac.append(None if any(x is None for x in full) else float(np.mean(full)))
        for m in keys:
            per[m].append(r[m][0])
        if (i + 1) % 100 == 0:
            print(f"随机 {i + 1} / {len(ks)}（{time.time() - t0:.0f}s）", flush=True)
    jd = R7.judge(real, plac)
    pct = {m: (round(float(np.mean([1.0 if (p is not None and p < real[m][0]) else 0.0 for p in per[m]]) * 100), 1)
               if real[m][0] is not None else None) for m in keys}
    us = run_k(I, None, list(R7.SOURCE))
    return {"scale": sc, "real": real, "own_pctile": pct, "us_source": us, "ks": ks, "placebo": plac, "judge": jd,
            "seconds": round(time.time() - t0)}


def run_all() -> int:
    t0 = time.time()
    code, dirty = git_head()
    W = L6.load3()
    M = account_inputs(W)
    a = stage_one(W, M)
    I = market_inputs(list(R7.MARKETS) + list(R7.SOURCE))
    b = stage_two(I)
    jd = b["judge"]
    verdict = R7.FOUND if (a["ok"] and jd["ok"]) else (R7.FAIL1 if not a["ok"] else R7.FAIL2)
    res = {"loop": 7, "round": ROUND, "ids": list(IDS), "family": FAMILY, "kind": KIND, "posthoc": POSTHOC, "code": code, "dirty": dirty,
           "account": a, "cross": b, "verdict": verdict, "seconds": round(time.time() - t0)}
    write(res)
    return 0


def _f(v, f="{:+.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    a, b = res["account"], res["cross"]
    s, jd, sc = a["stage1"], b["judge"], b["scale"]["markets"]
    pv = s["posthoc"]
    yn = lambda x: "过" if x else "不过"                                       # noqa: E731
    L = [f"# 第七个研究循环第 2 轮：牛市里按自己指数的波动率连续调节仓位 VTX（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop7_r02_voltarget.py 开头）", "",
         f"**{res['verdict']}**", "",
         f"## 第一关（账户，B3 上）：{'全过' if a['ok'] else '不过'}",
         f"S1 合计 {_f(s['sum'])}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；S4（{_f(s['h1'])} / {_f(s['h2'])}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {_f(pv['unseen'])}）：{yn(s['S7'])}；S5 / S6 不适用", "",
         "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | VTX（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: (f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'], '{:.3f}')}"     # noqa: E731
                      f"（{_f(x['h1'], '{:.3f}')} / {_f(x['h2'], '{:.3f}')}）")
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(a['base'][e])} | {cell(a['cand'][e])}（{_f(s['d'][e])}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L6.ERAS:
        x = a["scale"][e]
        L.append(f"- {e}：美股牛 {x['bull_days']} 天里比例 < 1 的 {_f(x['cut_pct'], '{:.1f}')}%（{x['segments']} 段、这些日子平均比例 "
                 f"{_f(x['ratio_mean_cut'], '{:.3f}')}；牛的日子平均 {_f(x['expo_mean_bull'], '{:.3f}')}）；核心换仓 B3 {a['core_trades'][e]['B3']} → "
                 f"VTX {a['core_trades'][e]['VTX']} 笔")
    o = a["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {_f(o[k]['calmar'], '{:.3f}')}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%、"
        f"美股牛的日子里比例 < 1 的 {_f(o[k].get('cut_bull_pct'), '{:.1f}')}%）" for k in ("B3", "VTX")))
    for e in L6.ERAS:
        yb, yc = a["base"][e].get("years") or {}, a["cand"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（VTX − B3，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    lt = a["scale"]["latest"]
    dr = a["drift"]
    L.append(f"- 最新一天 {lt['date']}：美股{'熊' if lt['us_bear'] else '牛'}、比例 {lt['ratio']}")
    L.append("- B3 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L6.ERAS)
             + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R6.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B3）"))
    L += ["", f"## 第二关（横展开，17 个市场）：{'三条都过' if jd.get('ok') else '不过'}",
          f"C1 {yn(jd.get('C1'))}（合并平均 {_f(jd.get('pooled'))}，400 次随机最大 {_f(jd.get('max'))}、≥ 候选 {jd.get('ge_stat')} 次、"
          f"中位 {_f((jd.get('q') or {}).get(50))}、95 分位 {_f((jd.get('q') or {}).get(95))}、99 分位 {_f((jd.get('q') or {}).get(99))}；"
          f"随机比基准好的 {_f(jd.get('pos_share'), '{:.1f}')}%）；C2 {yn(jd.get('C2'))}（Δ > 0 的市场 {jd.get('positive')} / {jd.get('n')}，"
          f"要 ≥ {jd.get('need')}）；C3 {yn(jd.get('C3'))}（前一半 {_f(jd.get('h1'))}、后一半 {_f(jd.get('h2'))}）", "",
          "| 市场 | 数据起点 | 窗口交易日 | 牛的比例 | 牛里比例 < 1 | 段数 | 那些日子平均比例 | Δ 全窗口 | Δ 前一半 | Δ 后一半 | 自己的随机百分位 |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for m, (sym, name) in {**R7.MARKETS, **R7.SOURCE}.items():
        x = sc[m]
        v = b["real"][m] if m in R7.MARKETS else b["us_source"][m]
        p = _f(b["own_pctile"][m], "{:.1f}") if m in R7.MARKETS else "—"
        L.append(f"| {name}（{sym}） | {x['start']} | {x['days']} | {x['bull_pct']}% | {_f(x['cut_pct'], '{:.1f}')}% | {x['segments']} | "
                 f"{_f(x['ratio_mean_cut'], '{:.3f}')} | {_f(v[0])} | {_f(v[1])} | {_f(v[2])} | {p} |")
    L += ["", f"N_min = {b['scale']['n_min']}；随机 = 17 个市场用同一个 k 循环平移比例序列（种子 [20261007, 0, s]，与第 1 轮相同的 400 个 k）；"
          "基准 = 自己的牛熊分界（牛 100%、其余现金）；收盘决定、下一个交易日生效；换仓扣 0.1% × 换的比例。",
          f"用时 {res['seconds']} s（账户 {a['seconds']} s、横展开 {b['seconds']} s）。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L6.load3()
    M = account_inputs(W)
    I = market_inputs(list(R7.MARKETS) + list(R7.SOURCE))
    print(json.dumps({"account": account_scale(W, M), "cross": market_scale(I)}, ensure_ascii=False, indent=1))
    return 0


def wiring() -> int:
    """登记前用（不看候选的结果）：① 比例全 1 → 三个年代与 B3 逐项相同、17 个市场 Δ 全为 0；② old_core 比例 None = 第 7 轮函数的 B3；
    ③ B3 没有别的 core_expo；④ 账户的比例 = vt_ratio。"""
    import equity_idle_study as EI
    W = L6.load3()
    M = account_inputs(W)
    no_other = {e: "core_expo" not in (W["kw"][e] or {}) and "core_expo" not in (W.get("b1") or {}) for e in L6.ERAS}
    ones = pd.Series(1.0, index=M["ratio_t"].index)
    ov1 = vtx_over(ones)
    same_b3 = {}
    for e in L6.ERAS:
        rb, r1 = L6.run(W, e), L6.run(W, e, **ov1)
        same_b3[e] = bool(all(rb.get(x) == r1.get(x) for x in KEYS))
    o1, o2 = old_core(W, None), V.old_core(W, None)
    o3 = old_core(W, pd.Series(1.0, index=M["ratio_us"].index))
    ratio_same = bool(M["ratio_us"].equals(V.vt_ratio(EI.ndx_tr(W["inp"]))))
    I = market_inputs(list(R7.MARKETS))
    one = {m: pd.Series(1.0, index=r.index) for m, r in I["ratios"].items()}
    z = deltas_num(I["closes"], one, I["bulls"], None, {m: spans_of(c) for m, c in I["closes"].items()})
    zero = all(all(x is not None and abs(x) < 1e-12 for x in v) for v in z.values())
    zs = deltas_num(I["closes"], one, I["bulls"], 1234, {m: spans_of(c) for m, c in I["closes"].items()})
    zero_shift = all(all(x is not None and abs(x) < 1e-12 for x in v) for v in zs.values())
    out = {"no_other_core_expo": no_other, "ones_same_as_b3": same_b3,
           "old_core_b3_same": bool(o1["calmar"] == o2["calmar"] and o1["cagr"] == o2["cagr"]),
           "old_core_ones_same": bool(o3["calmar"] == o2["calmar"] and o3["cagr"] == o2["cagr"]),
           "ratio_us_is_vt_ratio": ratio_same, "markets_ones_zero_delta": zero, "markets_ones_shift_zero_delta": zero_shift}
    print(json.dumps(out, ensure_ascii=False))
    ok = (all(no_other.values()) and all(same_b3.values()) and out["old_core_b3_same"] and out["old_core_ones_same"] and ratio_same
          and zero and zero_shift)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第七个研究循环第 2 轮：VTX（牛市里按自己指数的波动率连续调节仓位）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的结果）")
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    return run_all()


if __name__ == "__main__":
    raise SystemExit(main())
