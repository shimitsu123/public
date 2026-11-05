"""core_bullmix_study.py — 诊断 R1 的下一步：美股牛的时候核心也常配一部分对冲版美债 1482，能不能减轻「牛市里的急跌」（2026-10-23 登记 = 本提交；之后不改、只运行一次）。

用户（2026-10-23）：「现在算法中不足的地方 通过探索相关的变量 看看是否能逐步提高现在算法的精准度」。
先做的只描述诊断（scripts/b4_weakness_diag.py，登记 bd4282c）：账户回撤段 ≥ 10% 的 12 段里核心占亏损 76〜100%，大多发生在美股仍判为牛的时候
（2020-02〜03、2024-07〜08、2024-12〜2025-04、2022-01〜03、2010-04〜07 …，熊的天数 0〜14%）；读法 R1 成立 → 先做核心。
→ 本研究是看了诊断才定的 = 事后（posthoc = True，S7 适用）。
以前做过、这里不重复的（照实写）：牛市里按波动率减仓 VT20 / VTU / VTD / VTX、波动冲击减仓 VSX、高波动 ∧ 负相关时 1545 : 1482 = 2 : 1 VBH / VBT、
三分之一离开纳指 VCT、急跌卖出 CPX、常配黄金 G3 / B、按状态选模型 S1〜S4。都是「什么时候减」的择时；VCT 的随机对照里随机放的减仓 45.5% 也比 B3 好
→ 好处多半来自「少拿纳指本身」。这里试的是不择时的分散：牛市里一直（或只看 B3 已经在用的股债相关条件）拿一个固定比例的 1482。

〇 基准 B4 = B3 + TBF（loop9_common.run_block(W, e, TBF)，同 kshape_link_study / b4_weakness_diag 的基准；先决条件同那里：规则指纹 + 接线 + B4 重算 = B4_PREP）。
一 候选（权重事先写定，不从数据学 → S6 不适用；不改个股的买点 / 选股 / 仓位 / 离场 → S5 不适用；家族「核心·牛市分散」）：
   - SBS：美股牛 → 1545 : 1482 = 4 : 1（一直）；美股熊 → 同 B3（负相关 → 1482、其余现金）。
   - SBC：美股牛 ∧ 股债 63 天负相关（B3 的 on_b 原样）→ 1545 : 1482 = 4 : 1；美股牛 ∧ 不是负相关 → 只拿 1545（同 B3）；美股熊 → 同 B3。
   - SBH：同 SBC，比例 2 : 1。
   接法：B3 的 follow 模式（1545 键 US、1482 键 US_BD）只改两处 —— 权重、1482 的键（True = 不拿）：
     SBS =「美股熊 ∧ ¬负相关」；SBC / SBH =「¬负相关」（B3 =「美股牛 ∨ ¬负相关」）。美股熊时 1545 是熊 → follow 把 1482 归一成 100%（同 B3）。
   4 : 1 / 2 : 1 的来由（照实写，没看收益）：20% 是常见的「少量分散」，1/3 = VBH / VCT 用过的量。
二 判定（第一关 = research_loop2.stage1，同第六个研究循环的核心层：S1 三个年代 Calmar 差合计 ≥ +0.03、S2 每个年代 ≥ −0.02、S3 最大回撤不深 2 pp 以上、
   S4 前后两半合计都 ≥ 0、S7 没看过的 1987〜2000 只有核心（第六个循环 VBH 的 old_core 同一口径：日元计纳指不对冲、对冲版美债、S&P 与美债 63 天相关、
   前一天决定当天、换仓扣 0.1% × 换的比例）候选 − B3 > 0）；候选与同一次运行的 B4 比较。
   稳健（第一关全过的候选才看；同一次运行里算好）：同一结构、1482 占比 ± 10 pp 的两个邻居（SBS / SBC：10% / 30%；SBH：23.3% / 43.3%）S1〜S3 都要过。
   没有第二关的随机平移：这些候选没有新加的择时信号（SBC / SBH 的条件是 B3 已有的），平移检验不适用 → 照实写：比研究循环的两关弱，
   第一关 + 稳健都过也只是「历史上的候选」，要不要加进前向记录 / 采用由用户决定；不改模拟盘、执行器、策略参数。
   多重检验：3 个候选 + 前面诊断看过的数据 → 事后。
三 接线核对（同一次运行里、判定之前；不过 → 停、不出判定）：① 用本脚本的键写出 B3（美股牛 ∨ ¬负相关、权重 1 : 1）→ 三个年代与 B4 逐项相同；
   ② 只有核心的 B3 两种写法相同（本脚本 core_weights 的「不分散」= loop6_r07_volbond.old_core(W, None)）。
四 只描述（不参与判定）：各年代 1482 拿着的天数比例、核心换仓笔数、每年收益差、诊断里 B4 最深的几段回撤在候选里的深度。
事前预期（写在看结果之前）：SBS 多半不过（2022 年股债同跌、J 的 1482 对冲成本高，牛市年份少赚）；SBC / SBH 在 2020-03、2024-08 这种负相关的急跌里少亏，
   但在 2017〜2026 的纳指大牛市里每年少赚约 1〜3 pp → J 多半变差；整体预计第一关不过的可能大（约 70%）。
运行：python scripts/core_bullmix_study.py --run（只运行一次；输出已存在就拒绝）。输出 var/out/core_bullmix_study.md / .json。非投资建议。
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

ERAS = ("Z", "E", "J")
OUT = "core_bullmix_study"
POSTHOC = True
FAMILY = "核心·牛市分散"
# id → (1545 权重, 1482 权重, 只在负相关时分散)
CANDS = {"SBS": (4.0, 1.0, False), "SBC": (4.0, 1.0, True), "SBH": (2.0, 1.0, True)}
NEIGHBORS = {"SBS": ((9.0, 1.0), (7.0, 3.0)), "SBC": ((9.0, 1.0), (7.0, 3.0)), "SBH": ((23.0 / 3, 7.0 / 3), (17.0 / 3, 13.0 / 3))}
EPS = 1e-12


# ───────────────────────── 规则（纯函数；tests/test_core_bullmix_study.py） ─────────────────────────
def bond_closed(bear_t: pd.Series, on_b: pd.Series, cond: bool) -> pd.Series:
    """东证日上 1482 的「熊」键（True = 不拿）。cond = False（SBS）：美股熊 ∧ ¬负相关；cond = True（SBC / SBH）：¬负相关。"""
    b, o = bear_t.astype(bool).to_numpy(), on_b.astype(bool).to_numpy()
    return pd.Series((b & ~o) if not cond else ~o, index=on_b.index)


def b3_closed(bear_t: pd.Series, on_b: pd.Series) -> pd.Series:
    """B3 的键（接线核对用）：美股牛 ∨ ¬负相关。"""
    b, o = bear_t.astype(bool).to_numpy(), on_b.astype(bool).to_numpy()
    return pd.Series(~b | ~o, index=on_b.index)


def mix_over(W: dict, M: dict, w_core: float, w_bond: float, closed: pd.Series) -> dict:
    """B3 的接法（1545 键 US、1482 键 US_BD、follow），换权重与 1482 的键。"""
    import loop2_r02_bondrefuge as T2
    xc = dict(W["kw"]["Z"]["extra_core"])
    xc[T2.BOND_T] = M["fb"]
    return {"cfg_over": {"core": {"1545.T": w_core, T2.BOND_T: w_bond}, "core_index": {"1545.T": "US", T2.BOND_T: T2.BD_KEY},
                         "core_mode": "follow"},
            "extra_core": xc, "extra_bear": {T2.BD_KEY: closed}}


def core_weights(bear: pd.Series, on: pd.Series, w_core: float, w_bond: float, cond: bool | None) -> pd.DataFrame:
    """只有核心（1987〜2000）的持仓。cond = None → B3（牛 → 纳指；熊 ∧ 负相关 → 美债；其余现金）；
    False → 牛一直 纳指 : 美债 = w_core : w_bond；True → 牛 ∧ 负相关时才分散。"""
    b, o = bear.astype(bool), on.astype(bool)
    mix = pd.Series(False, index=b.index) if cond is None else (~b & o if cond else ~b)
    sc, sb = w_core / (w_core + w_bond), w_bond / (w_core + w_bond)
    u = (~b & ~mix).astype(float) + mix.astype(float) * sc
    bd = (b & o).astype(float) + mix.astype(float) * sb
    return pd.DataFrame({"u": u, "b": bd}, index=b.index)


def robust_ok(s1: dict) -> bool:
    """稳健：邻居的 S1〜S3 都过。"""
    return bool(s1.get("S1") and s1.get("S2") and s1.get("S3"))


def verdict(s1: dict, neigh: list[dict]) -> str:
    if not s1.get("ok"):
        return "第一关不过"
    return "第一关与稳健都过（历史上的候选，由用户决定）" if all(robust_ok(x) for x in neigh) else "第一关过、稳健不过"


def dd_in(eq: pd.Series, a, b) -> float | None:
    """eq 在 [a, b] 里从这段之前（含 a）的最高点算起的最深回撤（%）。"""
    s = eq[eq.index <= pd.Timestamp(b)]
    if s.empty:
        return None
    peak = s.cummax()
    dd = (s / peak - 1) * 100
    w = dd[dd.index >= pd.Timestamp(a)]
    return None if w.empty else round(float(w.min()), 2)


# ───────────────────────── 1987〜2000 只有核心（S7） ─────────────────────────
def old_core(W: dict, w_core: float, w_bond: float, cond: bool | None) -> dict:
    """第六个循环 VBH 的 old_core 同一口径（loop6_r07_volbond.old_core），持仓换成 core_weights。"""
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
    idx = unh.index[(unh.index >= pd.Timestamp(T.OLD[0])) & (unh.index <= pd.Timestamp(T.OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    unh, b_px = unh.reindex(idx), ff(bnd)
    b = ff(W["bear"]["US"]).fillna(0.0) > 0.5
    ou = ff(on_u).fillna(0.0) > 0.5
    w = core_weights(b, ou, w_core, w_bond, cond).shift(1).fillna(0.0)
    ret = w["u"] * unh.pct_change().fillna(0.0) + w["b"] * b_px.pct_change().fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["bond_days_pct"] = round(float((w["b"] > 0).mean() * 100), 1)
    return out


# ───────────────────────── 运行 ─────────────────────────
KEYS = ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")


def git_info() -> dict:
    root = Path(__file__).resolve().parents[2]
    try:
        rev = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "quant_breakout/scripts", "quant_breakout/qbreak"],
                                    capture_output=True, text=True).stdout.strip())
        return {"rev": rev, "dirty": dirty}
    except Exception:                                                        # noqa: BLE001
        return {"rev": "?", "dirty": None}


def _eq(eng) -> pd.Series:
    h = pd.DataFrame(eng.st.history)
    return pd.Series(h[1].astype(float).to_numpy(), index=pd.to_datetime(h[0]))


def run(say=print) -> dict:
    import jq_study as JS
    import kshape_link_study as KS
    import loop2_r05_ddbrake as R5
    import loop6_common as L6
    import loop6_r03_earlyreturn as N3
    import loop6_r07_volbond as VB
    import loop9_common as C9
    import loop10_common as C10
    import research_loop2 as R2
    import trendline_study as TS
    t0 = time.time()
    W = C10.load()
    say(f"载入：{time.time() - t0:.0f}s")
    tbf, _ = TS.tbf_gates(W, say)
    pre = KS.prereq(W, tbf, say)
    if not pre["ok"]:
        raise SystemExit("先决条件不满足 → 停")
    M = W["bcu"]
    days = M["on_b"].index
    bear_t = N3.on_idx(W["bear"]["US"], days)
    ticks = {e: C9.tick_of(C9.signals(W, e)["ticker"], C9.signals(W, e)["date"], tbf[e]) for e in ERAS}

    def acct(e: str, ov: dict | None) -> tuple[dict, pd.Series, int]:
        r = L6.run(W, e, em_tick=ticks[e], **(ov or {})) if ticks[e] else L6.run(W, e, **(ov or {}))
        eng = JS.RealLotEngine.LAST[-1]
        return {**{k: r.get(k) for k in KEYS}, "years": r.get("years")}, _eq(eng), R5.core_trades(e, W)

    # 三 接线核对
    wire_ov = mix_over(W, M, 1.0, 1.0, b3_closed(bear_t, M["on_b"]))
    base, beq, btr, wire = {}, {}, {}, {}
    for e in ERAS:
        base[e], beq[e], btr[e] = acct(e, None)
        w0, _, _ = acct(e, wire_ov)
        wire[e] = bool(all(base[e].get(k) == w0.get(k) for k in KEYS))
        say(f"{e} 基准与接线（{time.time() - t0:.0f}s）")
    o_b3, o_vb = old_core(W, 1.0, 1.0, None), VB.old_core(W, None)
    wire["old_core"] = bool(o_b3["calmar"] == o_vb["calmar"] and o_b3["cagr"] == o_vb["cagr"])
    same = {e: KS.same_prep(base[e], KS.B4_PREP[e]) for e in ERAS}
    if not all(wire.values()) or not all(same.values()):
        raise SystemExit(f"接线核对 / B4 重算不过 → 停：{wire} {same}")

    res: dict = {"study": OUT, "git": git_info(), "posthoc": POSTHOC, "family": FAMILY, "prereq": {k: v for k, v in pre.items() if k != "base"},
                 "wiring": wire, "b4_same": same, "base": base, "base_core_trades": btr, "old": {"B3": o_b3}, "cands": {}}
    from qbreak import paths
    diag = json.loads((paths.out_dir() / "b4_weakness_diag.json").read_text(encoding="utf-8"))
    for cid, (wc, wb, cond) in CANDS.items():
        closed = bond_closed(bear_t, M["on_b"], cond)
        cand, ceq, ctr = {}, {}, {}
        for e in ERAS:
            cand[e], ceq[e], ctr[e] = acct(e, mix_over(W, M, wc, wb, closed))
        o = old_core(W, wc, wb, cond)
        unseen = None if o["calmar"] is None or o_b3["calmar"] is None else o["calmar"] - o_b3["calmar"]
        s1 = R2.stage1(cand, base, posthoc=unseen)
        neigh = []
        if s1["ok"]:
            for nc, nb in NEIGHBORS[cid]:
                na = {e: acct(e, mix_over(W, M, nc, nb, closed))[0] for e in ERAS}
                ns = R2.stage1(na, base)
                neigh.append({"w": [nc, nb], "bond_pct": round(nb / (nc + nb) * 100, 1), "d": ns["d"], "sum": ns["sum"],
                              "S1": ns["S1"], "S2": ns["S2"], "S3": ns["S3"]})
        bull = ~bear_t.astype(bool)
        held = (~closed.astype(bool))
        hold = {}
        for e in ERAS:
            a, b = TS._win(*W["ctx"][e]["windows"][e])
            m = (days >= a) & (days < b)
            hold[e] = {"bond_in_bull_pct": round(float((held[m] & bull[m]).sum() / max(1, int(bull[m].sum())) * 100), 1)}
        eps = {e: [{"from": str(x["peak"]), "to": str(x["trough"]), "b4": x["depth"], "cand": dd_in(ceq[e], x["peak"], x["trough"])}
                   for x in diag["eras"][e]["episodes"]] for e in ERAS}
        res["cands"][cid] = {"w": [wc, wb], "cond": cond, "acct": cand, "core_trades": ctr, "old": o, "stage1": s1, "neighbors": neigh,
                             "verdict": verdict(s1, neigh), "hold": hold, "episodes": eps}
        say(f"{cid} 完成（{time.time() - t0:.0f}s）")
    res["elapsed_s"] = round(time.time() - t0)
    return res


def _f(v, f="{:+.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def report(res: dict) -> str:
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    B = res["base"]
    L = [f"# 诊断 R1 的下一步：牛市里核心也常配一部分对冲版美债 1482（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；规则见 scripts/core_bullmix_study.py 开头）", "",
         f"代码 {res['git']['rev']}（未提交的改动：{res['git']['dirty']}）；先决条件 {res['prereq'].get('ok')}；接线 {all(res['wiring'].values())}；"
         f"B4 = 登记值 {all(res['b4_same'].values())}；事后（S7 适用）；用时 {res['elapsed_s']} s。", ""]
    for cid, c in res["cands"].items():
        s = c["stage1"]
        pv = s["posthoc"]
        L.append(f"- **{cid}（1545 : 1482 = {c['w'][0]:g} : {c['w'][1]:g}，{'只在股债负相关时' if c['cond'] else '美股牛时一直'}）：{c['verdict']}**"
                 f"（S1 合计 {_f(s['sum'])}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；S4（{_f(s['h1'])} / {_f(s['h2'])}）：{yn(s['S4'])}；"
                 f"S7（1987〜2000 只有核心 {_f(pv['unseen'])}）：{yn(s['S7'])}；S5 / S6 不适用）")
        for n in c["neighbors"]:
            L.append(f"  - 稳健：1482 占 {n['bond_pct']}% → 合计 {_f(n['sum'])}（" + " / ".join(f"{e} {_f(n['d'][e])}" for e in ERAS)
                     + f"）S1 {yn(n['S1'])}、S2 {yn(n['S2'])}、S3 {yn(n['S3'])}")
    L += ["", "| 年代 | B4 年化 / 最大回撤 / Calmar（前半 / 后半） | " + " | ".join(f"{k}（Calmar 差）" for k in res["cands"]) + " |",
          "|---|---|" + "---|" * len(res["cands"])]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'], '{:.3f}')}（{_f(x['h1'], '{:.3f}')} / {_f(x['h2'], '{:.3f}')}）"   # noqa: E731
    for e in ERAS:
        L.append(f"| {e} | {cell(B[e])} | " + " | ".join(f"{cell(c['acct'][e])}（{_f(c['stage1']['d'][e])}）" for c in res["cands"].values()) + " |")
    L += ["", "只描述（不参与判定）："]
    for cid, c in res["cands"].items():
        L.append(f"- {cid}：美股牛的日子里拿 1482 " + " / ".join(f"{e} {c['hold'][e]['bond_in_bull_pct']}%" for e in ERAS)
                 + "；核心换仓 B4 → 候选 " + " / ".join(f"{e} {res['base_core_trades'][e]} → {c['core_trades'][e]}" for e in ERAS)
                 + f"；1987〜2000 只有核心 B3 {_f(res['old']['B3']['calmar'], '{:.3f}')} → {_f(c['old']['calmar'], '{:.3f}')}"
                 f"（年化 {_f(c['old'].get('cagr'), '{:+.2f}')}%、回撤 {_f(c['old'].get('dd'), '{:.2f}')}%）")
        for e in ERAS:
            yb, yc = B[e].get("years") or {}, c["acct"][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            L.append(f"  - {e} 每年收益差（pp）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
        L.append("  - 诊断里 B4 的回撤段在候选里的深度（%）：" + "；".join(
            f"{e} " + "、".join(f"{x['from'][:7]}→{x['to'][:7]} {x['b4']:.1f} → {_f(x['cand'], '{:.1f}')}" for x in c["episodes"][e]) for e in ERAS))
    L += ["", "不改模拟盘 / 执行器 / 策略参数；要不要加进前向记录或采用由用户决定。非投资建议。"]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    from qbreak import paths
    ap = argparse.ArgumentParser(description="诊断 R1 的下一步：牛市里常配一部分 1482")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    if not a.run:
        ap.print_help()
        return 0
    out = paths.out_dir()
    if (out / f"{OUT}.json").exists():
        print(f"{OUT}.json 已存在 → 只运行一次，不再运行")
        return 1
    res = run()
    text = report(res)
    print(text)
    (out / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (out / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
