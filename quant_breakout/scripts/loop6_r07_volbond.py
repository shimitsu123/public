"""loop6_r07_volbond.py — 第六个研究循环第三段（基准 B3 = 撤掉 FJE 之后的模拟盘 Q1B，修正口径）第 7 轮：
「高波动的牛市里，股债负相关时把三分之一核心换成对冲版美债」VBH（2026-10-03 登记；先提交后只运行一次；家族「核心·波动率仓位」这一段 1 / 3
（第二段没用过）；kind = signal；事后 → S7 适用）。

用户（2026-10-03）：㊼ ①「重新检验，不过就撤」（只回答编号 = 同时同意：第六个循环按修正口径重算基准、计数接着 7 / 20、剩下的汇率对冲名额不用、
照现行规则选题）。循环的规则：scripts/research_loop6.py（第三段 = 开头「九」与末尾一节）；基准 B3：scripts/loop6_common.load3。
为什么做这个（照实写）：
  - 研究成功率（var/out/research_success_map.md）：核心层第一关全过的 14 个里 FXH / FXE / FJH / FJE / CRW 都是汇率择时，修正口径后不算数；
    剩下的是熊市避险资产（TBJ / TBU / BCU / BCB；这一段家族用量已满 3）、早回来（NDRH / NVU / NDB；第二关都在第 89〜98 百分位）、
    指数选择（ZSP 96.8）、波动率仓位（VTU 88.0）。
  - 波动率仓位：第一个循环 VT20（日元计纳指 σ20 高于自己的中位数时核心按 中位数 / σ20 减仓、余下现金）合计 +0.203（J +0.275），只输在 E −0.053
    （高波动之后的反弹少赚）；第二个循环 VTU（σ20 改按美元计）第一关全过 +0.184（Z +0.006、E +0.034、J +0.144），第二关第 88 百分位。
  - BCU（2026-10-03 采用、两关都过）：美股熊且股债 63 天负相关 → 1482 比现金好。高波动的牛市日子（例：2010-05、2011-08、2015-08〜2016-02、
    2018-02 / 10〜12、2020-02〜03）多半也是股债负相关、美债上涨的时候 → 减下来的那部分拿 1482 而不是现金，减仓的代价（反弹少赚）由美债补一部分。
  → 看过 VT20 / VTU / BCU 的结果之后设计 = 事后（S7 适用）。
做法 VBH（VT20 的波动率状态与参数原样、BCU 的相关条件原样 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 高波动：纳指总收益（美元，equity_idle_study.ndx_tr）的 σ20（20 日对数收益标准差 × √252）、目标 = σ20 自 1986-01-01 起的扩展中位数（至少 250 个值）、
    VT20 的比例（min(1, 目标 / σ20)，差 ≥ 0.10 才换，σ20 ≤ 目标就直接回到 1）< 1 的美国交易日（loop_r01_voltarget.sigma / target / exposure 原样）；
    东证交易日 d = d 之前（含 d 的日期）最近一个美国收盘的状态（与 B3 的「美股熊」同一个对齐：美国 d 日收盘 → 东证 d+1 开盘成交）。
  - 美股牛 且 高波动 且 股债 63 天负相关（BCU 的条件：loop6_r01_bondcorr.inputs 的 on_b，东证日上）→ 核心 1545 : 1482 = 2 : 1（follow 模式的固定权重）；
    美股牛的其余日子 → 只拿 1545（同 B3）；美股熊 → 同 B3（负相关 → 1482、其余现金）。
  - 接法：B3 的 follow 模式（1545 键 US、1482 键 US_BD）只改两处 —— 1482 的键（不可拿）=「¬负相关 ∨（美股牛 ∧ ¬高波动）」、权重 1545 : 1482 = 2 : 1。
    2 : 1 的来由（照实写，只看状态、没看收益）：登记前的 --scale 报 2000〜2026 高波动的牛市日子里 VT20 比例的平均（见 sim_changes 登记一节），
    取最接近的简单比例。
第一关：research_loop6.stage1（S1〜S4 + S7：1987〜2000 只有核心 VBH − B3 > 0；只有核心的口径 = 第 3 轮 old_core（日元计纳指不对冲、对冲版美债、
  S&P 与美债 63 天相关、前一天的状态决定当天、换仓扣 0.1% × 换的比例），没有 FJE；VBH 只多一条：美股牛 ∧ 高波动 ∧ 负相关 → 纳指 2/3、美债 1/3）。
第二关（第一关全过才做；另行登记后只运行一次；代码写在本脚本 --stage2）：kind = signal —— 候选自己新加的信号 =「高波动」（东证日上的布尔序列）在
  2000-01-04〜2026-09-30 的东证交易日上整体循环平移 k（research_loop6.shift_ks(n, 0)：种子 [20261006, 0, s]），窗外不动；
  B3（美股熊、股债相关、价格）不动。候选的 Calmar 差合计要严格大于 400 次的最大值（有算不出的 = 不过）。
接线核对（登记前，不看候选的结果；--wiring）：① 高波动永远不成立 → 三个年代与 B3 逐项相同；② old_core 的 B3（高波动永远不成立）
  = 同一函数直接按 B3 的规则算（weights 的两种写法相同）。
只描述（不参与判定）：各年代美股牛日子里高波动的比例、其中负相关的比例、段数；高波动牛市日子里 VT20 比例的平均；核心换仓笔数；每年收益差；
  1987〜2000 的同样数字；最新一天的状态。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop6_r07_volbond.py（第一关）；--scale（只数日子）；--wiring（登记前的接线核对）；--stage2 VBH [--workers N]（第二关）。
输出 var/out/loop6_r07_volbond.md / .json（第二关 loop6_r07_volbond_stage2_VBH.md / .json）。非投资建议。
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
import loop2_r02_bondrefuge as T2                                            # noqa: E402
import loop6_common as L6                                                    # noqa: E402
import loop6_r01_bondcorr as T                                               # noqa: E402
import loop6_r03_earlyreturn as N3                                           # noqa: E402
import loop_r01_voltarget as VT                                              # noqa: E402
import research_loop6 as R6                                                  # noqa: E402

ROUND = 7
IDS = ("VBH",)
FAMILY = {"VBH": "核心·波动率仓位"}
KIND = {"VBH": "signal"}
POSTHOC = True
W_CORE, W_BOND = 2.0, 1.0                                                    # 高波动 ∧ 负相关的牛市日子：1545 : 1482
OLD = T.OLD
OUT = "loop6_r07_volbond"
on_idx = N3.on_idx


# ───────────────────────── 规则（纯函数，tests/test_loop6_r07.py） ─────────────────────────
def vt_ratio(ndx_tr: pd.Series) -> pd.Series:
    """VT20 的比例（美元计纳指总收益；loop_r01_voltarget 原样，同第二个循环 VTU）。"""
    sg = VT.sigma(ndx_tr.dropna().sort_index())
    return VT.exposure(sg, VT.target(sg))


def high_vol(ratio: pd.Series) -> pd.Series:
    """高波动 = VT20 的比例 < 1（美国交易日）。"""
    return pd.Series(ratio.to_numpy(float) < 1.0 - 1e-12, index=ratio.index)


def bond_closed(bear_t: pd.Series, high_t: pd.Series, on_b: pd.Series) -> pd.Series:
    """东证日上 1482 的「熊」键（True = 目标 0）：¬负相关 ∨（美股牛 ∧ ¬高波动）。高波动永远不成立 → = B3 的键（¬负相关 ∨ 美股牛）。"""
    idx = on_b.index
    b, h, o = (on_idx(bear_t, idx).to_numpy(bool), on_idx(high_t, idx).to_numpy(bool), on_b.astype(bool).to_numpy())
    return pd.Series(~o | (~b & ~h), index=idx)


def vbh_over(W: dict, M: dict, high_t: pd.Series) -> dict:
    """B3 的接法（1545 键 US、1482 键 US_BD、follow），只把 1482 的键换成 bond_closed、权重 1545 : 1482 = 2 : 1。"""
    xc = dict(W["kw"]["Z"]["extra_core"])
    xc[T2.BOND_T] = M["fb"]
    return {"cfg_over": {"core": {"1545.T": W_CORE, T2.BOND_T: W_BOND}, "core_index": {"1545.T": "US", T2.BOND_T: T2.BD_KEY},
                         "core_mode": "follow"},
            "extra_core": xc, "extra_bear": {T2.BD_KEY: bond_closed(M["bear_t"], high_t, M["on_b"])}}


def shifted_high(high_t: pd.Series, k: int | None) -> pd.Series:
    """第二关：高波动在 2000-01-04〜J 的最后一天上整体循环平移 k（None = 不平移），窗外不动。"""
    s = high_t.astype(bool).copy()
    if k is not None:
        w = R6.shift_window(s)
        s.loc[w.index] = R6.shift_signal(w, k).to_numpy(bool)
    return s


def placebo_ks(n: int) -> list[int]:
    """每个种子的平移量（signal：shift_ks(n, 0)）。"""
    return R6.shift_ks(n, 0)


def core_weights(bear: pd.Series, high: pd.Series, on: pd.Series) -> pd.DataFrame:
    """只有核心（1987〜2000）的持仓：美股牛 → 纳指（高波动 ∧ 负相关 → 纳指 2/3、美债 1/3）；美股熊 ∧ 负相关 → 美债；其余现金。"""
    b, h, o = bear.astype(bool), high.astype(bool), on.astype(bool)
    mix = ~b & h & o
    u = (~b & ~mix).astype(float) + mix.astype(float) * W_CORE / (W_CORE + W_BOND)
    bd = (b & o).astype(float) + mix.astype(float) * W_BOND / (W_CORE + W_BOND)
    return pd.DataFrame({"u": u, "b": bd}, index=bear.index)


# ───────────────────────── 1987〜2000 只有核心（S7） ─────────────────────────
def old_core(W: dict, high_us: pd.Series | None) -> dict:
    """第 3 轮 old_core 同一个口径（没有 FJE）：日元计纳指不对冲、对冲版美债、S&P 与美债 63 天相关（前一天）；high_us = None → B3。"""
    import equity_idle_study as EI
    import halloween_study as HW
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
    h = (ff(high_us).fillna(0.0) > 0.5) if high_us is not None else pd.Series(False, index=idx)
    ou = ff(on_u).fillna(0.0) > 0.5
    w = core_weights(b, h, ou).shift(1).fillna(0.0)
    ret = w["u"] * unh.pct_change().fillna(0.0) + w["b"] * b_px.pct_change().fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["mix_days_pct"] = round(float(((w["u"] > 0) & (w["b"] > 0)).mean() * 100), 1)
    out["bond_days_pct"] = round(float((w["b"] > 0).mean() * 100), 1)
    out["high_bull_pct"] = round(float((h & ~b).sum() / max(1, int((~b).sum())) * 100), 1)
    return out


# ───────────────────────── 输入 / 规模 ─────────────────────────
def inputs(W: dict) -> dict:
    """B3 的输入（W["bcu"]：1482 合成价、相关条件，东证日）+ 东证日上的美股熊 / 高波动 + 美国日的 VT20 比例 / 高波动。"""
    import equity_idle_study as EI
    M = dict(W["bcu"])
    days = M["on_b"].index
    ratio = vt_ratio(EI.ndx_tr(W["inp"]))
    hus = high_vol(ratio)
    M.update({"days": days, "ratio_us": ratio, "high_us": hus, "bear_t": on_idx(W["bear"]["US"], days), "high_t": on_idx(hus, days)})
    return M


def era_days(W: dict, e: str) -> pd.DatetimeIndex:
    return N3.era_days(W, e)


def segments(flag: pd.Series) -> int:
    v = flag.astype(bool).to_numpy()
    return int((v[1:] & ~v[:-1]).sum() + (1 if len(v) and v[0] else 0))


def state_share(bear_t: pd.Series, high_t: pd.Series, on_b: pd.Series, ratio_t: pd.Series, days: pd.DatetimeIndex) -> dict:
    """这段日子里：美股牛的天数、其中高波动 / 高波动且负相关（= 候选与 B3 不同的日子）的比例与段数、高波动牛市日子里 VT20 比例的平均（只数日子）。"""
    days = pd.DatetimeIndex(days)
    b, h, o = on_idx(bear_t, days), on_idx(high_t, days), on_idx(on_b, days)
    r = ratio_t.astype(float).reindex(days.union(ratio_t.index)).ffill().reindex(days)
    bull = ~b
    mix = bull & h & o
    nb = int(bull.sum())
    pct = lambda x: round(float(x) / nb * 100, 1) if nb else None                  # noqa: E731
    return {"bull_days": nb, "high_pct": pct(int((bull & h).sum())), "mix_pct": pct(int(mix.sum())), "mix_segments": segments(mix),
            "ratio_mean_high": round(float(r[bull & h].mean()), 3) if (bull & h).any() else None,
            "ratio_mean_mix": round(float(r[mix].mean()), 3) if mix.any() else None}


def scale(W: dict, M: dict) -> dict:
    out = {e: state_share(M["bear_t"], M["high_t"], M["on_b"], M["ratio_us"], era_days(W, e)) for e in L6.ERAS}
    w = R6.shift_window(M["high_t"])
    out["window"] = state_share(M["bear_t"], M["high_t"], M["on_b"], M["ratio_us"], w.index)
    out["high_share_2000_2026"] = round(float(w.mean() * 100), 1)
    out["shift_n"] = len(w)
    bu = W["bear"]["US"]
    old = M["high_us"][(M["high_us"].index >= pd.Timestamp(OLD[0])) & (M["high_us"].index <= pd.Timestamp(OLD[1]))]
    bo = on_idx(bu, old.index)
    out["old_high_bull_pct"] = round(float((old & ~bo).sum() / max(1, int((~bo).sum())) * 100), 1)
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "us_bear": bool(M["bear_t"].iloc[-1]), "high_vol": bool(M["high_t"].iloc[-1]),
                     "corr_neg": bool(M["on_b"].iloc[-1]), "vt_ratio": round(float(M["ratio_us"].dropna().iloc[-1]), 3)}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None else f.format(v)


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[2]
    try:
        h = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "quant_breakout/scripts", "quant_breakout/qbreak"],
                                    capture_output=True, text=True).stdout.strip())
        return h, dirty
    except Exception:                                                         # noqa: BLE001
        return "?", True


def stage_one() -> int:
    import loop2_r05_ddbrake as R5
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L6.load3()
    M = inputs(W)
    ov = vbh_over(W, M, M["high_t"])
    reg = R6.segment(R6.load_state()).get("baseline") or {}
    base, cand, trades = {}, {"VBH": {}}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand["VBH"][e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B3": nb, "VBH": nc}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B3": old_core(W, None), "VBH": old_core(W, M["high_us"])}
    unseen = None if old["B3"]["calmar"] is None or old["VBH"]["calmar"] is None else old["VBH"]["calmar"] - old["B3"]["calmar"]
    s1 = {"VBH": R6.stage1(cand["VBH"], base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L6.ERAS}
    res = {"loop": 6, "segment": 3, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "scale": scale(W, M), "core_trades": trades, "old": old,
           "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s = res["stage1"]["VBH"]
    pv = s["posthoc"]
    L = [f"# 第六个研究循环第三段第 7 轮：高波动的牛市里、股债负相关时三分之一核心换对冲版美债 VBH（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop6_r07_volbond.py 开头；基准 B3 = Q1B，修正口径）", "",
         f"- **VBH：{'第一关全过 → 另行登记第二关（高波动循环平移）' if s['ok'] else R6.FAIL1}**"
         f"（S1 合计 {_f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
         f"S4（{_f(s['h1'], '{:+.3f}')} / {_f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {_f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）",
         "", "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | VBH（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['VBH'][e])}（{_f(s['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定；规模只数日子）："]
    sc = res["scale"]
    for e in L6.ERAS:
        x = sc[e]
        L.append(f"- {e}：美股牛 {x['bull_days']} 天里高波动 {_f(x['high_pct'], '{:.1f}')}%、高波动且负相关（与 B3 不同的日子）{_f(x['mix_pct'], '{:.1f}')}%"
                 f"（{x['mix_segments']} 段；VT20 比例平均 {_f(x['ratio_mean_mix'])}）；核心换仓 B3 {res['core_trades'][e]['B3']} → VBH {res['core_trades'][e]['VBH']} 笔")
    lt = sc["latest"]
    L.append(f"- 高波动在 2000〜2026 全部东证日里的比例 {sc['high_share_2000_2026']}%；最新一天 {lt['date']}：美股{'熊' if lt['us_bear'] else '牛'}、"
             f"高波动 {'是' if lt['high_vol'] else '否'}（VT20 比例 {lt['vt_ratio']}）、股债负相关 {'是' if lt['corr_neg'] else '否'}")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {_f(o[k]['calmar'])}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%、"
        f"纳指 + 美债一起拿 {_f(o[k].get('mix_days_pct'), '{:.1f}')}% 的日子）" for k in ("B3", "VBH"))
        + f"；美股牛的日子里高波动 {_f(o['VBH'].get('high_bull_pct'), '{:.1f}')}%")
    for e in L6.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["VBH"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（VBH − B3，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B3 与第三段登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L6.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R6.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B3）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L6.load3()
    M = inputs(W)
    print(json.dumps({"scale": scale(W, M)}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用：① 高波动永远不成立 → 三个年代与 B3 逐项相同；② old_core(B3) 的两种写法相同（high_us = None 与 全 False）。"""
    W = L6.load3()
    M = inputs(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    never = pd.Series(False, index=M["high_t"].index)
    ov0 = vbh_over(W, M, never)
    ov0 = {**ov0, "cfg_over": {**ov0["cfg_over"], "core": {"1545.T": 1.0, T2.BOND_T: 1.0}}}       # 权重不影响：两只不会同时开着
    same_b3 = {}
    for e in L6.ERAS:
        rb, r0 = L6.run(W, e), L6.run(W, e, **ov0)
        same_b3[e] = bool(all(rb.get(x) == r0.get(x) for x in keys))
    ovw = vbh_over(W, M, never)                                                                 # 同上但权重 2 : 1（高波动不成立时两只不会同时开着 → 也必须相同）
    same_w = {e: bool(all(L6.run(W, e).get(x) == L6.run(W, e, **ovw).get(x) for x in keys)) for e in L6.ERAS}
    o1, o2 = old_core(W, None), old_core(W, pd.Series(False, index=M["high_us"].index))
    out = {"never_high_same_as_b3": same_b3, "never_high_weights_21_same": same_w,
           "old_core_same": bool(o1["calmar"] == o2["calmar"] and o1["cagr"] == o2["cagr"])}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if all(same_b3.values()) and all(same_w.values()) and out["old_core_same"] else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次；signal = 高波动循环平移） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        kw = vbh_over(W, M, shifted_high(M["high_t"], ks[int(seed)]))
        tot = 0.0
        for e in L6.ERAS:
            c = L6.run(W, e, **kw)["calmar"]
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
    W = L6.load3()
    M = inputs(W)
    base = {e: L6.run(W, e)["calmar"] for e in L6.ERAS}
    ov = vbh_over(W, M, M["high_t"])
    cand = {e: L6.run(W, e, **ov)["calmar"] for e in L6.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L6.ERAS), 6)
    n = len(R6.shift_window(M["high_t"]))
    ks = placebo_ks(n)
    _G.update({"W": W, "M": M, "base": base, "ks": ks})
    seeds = list(range(R6.PLACEBO_N))
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
    s2 = R6.stage2(stat, vals)
    vd = R6.verdict(s1, s2)
    v = np.array([x for x in vals if x is not None], float)
    res = {"loop": 6, "segment": 3, "round": ROUND, "id": k, "kind": KIND[k], "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat,
           "stage1_stat": s1["sum"], "n": n, "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第六个研究循环第三段第 7 轮 第二关：{k} vs 400 次高波动循环平移（{KIND[k]}；B3 不动）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B3 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第六个研究循环第三段第 7 轮：VBH")
    ap.add_argument("--scale", action="store_true")
    ap.add_argument("--wiring", action="store_true")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
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
