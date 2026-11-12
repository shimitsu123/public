"""core_sleeve_study.py — 核心 ETF 一侧：美股牛的时候核心不只拿纳指 1545，固定分一小部分给别的股票指数（地理 / 指数分散）（2026-10-23 登记 = 本提交；之后不改、只运行一次）。

用户（2026-10-23）：「改进方向选择在买点或核心 ETF 一侧进行研究」。
为什么选核心、选这个题（照实写）：
  - 诊断（scripts/b4_weakness_diag.py）：核心占权益 81〜93%，账户回撤段 ≥ 10% 的亏损 76〜100% 来自核心，大多是美股仍判为牛时的急跌；
    以前的研究统计：核心层第一关通过率约 27%、个股层（买点 / 选股）47 个做法 0 个过第一关 → 先做核心。
  - 核心层的「择时」（什么时候减 / 换）第二关几乎都输给随机时点；不择时的分散只做过债券（〔81〕SBS：牛市一直 1545 : 1482 = 4 : 1，等用户决定）。
    股票指数之间的分散在 B 系列基准上没做过：2026-09-27 N3 纳指 / S&P 各半（旧系统、1987〜2005，只差回撤一条）、2026-09-29 equity_idle A 段
    （Q4 日経225 单独当核心：收益不够）、2026-09-30 core_switch（A 一直 S&P500：Z 好、E / J 差）、第二个循环 NSX（纳指自己熊时换 S&P500）都不是
    「牛市里固定一小部分」。→ 本研究 = 同一族（「核心·牛市分散」）的第二个题：分散的对象换成股票指数。看过诊断与上面这些结果才定 → 事后（posthoc = True，S7 适用）。
〇 基准 B4 = B3 + TBF（同 core_bullmix_study / kshape_link_study；先决条件同那里：规则指纹 + 接线 + B4 重算 = B4_PREP）。
一 候选（比例事先写定，不从数据学 → S6 不适用；不改个股的买点 / 选股 / 仓位 / 离场 → S5 不适用）：
   - SJP：美股牛 ∧ 日本牛（日経225 用现行同一个牛熊检测器，= equity_idle Q4 的「日本牛熊分界」）→ 1545 : 1321 = 4 : 1；
          美股牛 ∧ 日本熊 → 只拿 1545（同 B4）；美股熊 → 同 B4（负相关 → 1482、其余现金；1321 不拿）。
   - SJH：同 SJP，比例 2 : 1。
   - SSP：美股牛 → 1545 : 1655 = 4 : 1（S&P500 与纳指同一个美股牛熊键）；美股熊 → 同 B4。
   接法：B3 的 follow 模式（core_bullmix_study.mix_over 同一结构）加第三只：1545 键 US、分散的那只键 SL:JP / SL:SP（True = 不拿）、1482 键 US_BD（B3 原样）。
     follow 在不是熊的几只之间按权重归一：美股熊 → 1545 与分散的那只都不拿 → 1482 归一成 100%（同 B3）；美股牛 → 1482 的键是熊 → 1545 与分散的按比例。
   合成价（不新做，用 W["assets"]，equity_idle_study 同一做法）：1321 = 日経225 + 年 1.6% 股息估计 − 0.0817%（东证当天）；
     1655 = S&P500 总收益 − 0.066% × USD/JPY（东证 d 日 = 前一个美国收盘）；费用表 qbreak/fees.py 已有（1321 滑点 0.08% / 1 口、1655 0.02% / 10 口）。
   4 : 1 / 2 : 1 的来由（照实写，没看收益）：与 SBS / SBH 同样的量（20% / 1/3），便于对照。
二 判定（同 core_bullmix_study：第一关 = research_loop2.stage1：S1 三个年代 Calmar 差合计 ≥ +0.03、S2 每个年代 ≥ −0.02、S3 最大回撤不深 2 pp 以上、
   S4 前后两半合计都 ≥ 0、S7 没看过的 1987〜2000 只有核心（第六个循环 VBH 的 old_core 同一口径 + 分散的那只：日経 = 日元的日経总收益（年 1.6% 股息估计）
   − 0.0817%、日本牛熊 = 同一检测器用在日経；S&P500 = ^SP500TR（1988 以前 ^GSPC + 年 3.5%）− 0.066% × USD/JPY）候选 − B3 > 0）；候选与同一次运行的 B4 比较。
   稳健（第一关全过的候选才看；同一次运行里算好）：同一结构、分散的那只占比 ± 10 pp 的两个邻居（SJP / SSP：10% / 30%；SJH：23.3% / 43.3%）S1〜S3 都要过。
   没有第二关的随机平移：SSP 没有新的择时；SJP / SJH 的日本牛熊是现行检测器、现行参数（不是新拟合的），但它确实是 B4 没有的开关 → 照实写：
   比研究循环的两关弱，第一关 + 稳健都过也只是「历史上的候选」，要不要加进前向记录 / 采用由用户决定；不改模拟盘、执行器、策略参数。
   多重检验：3 个候选 + 前面诊断 / SBS 看过的数据 → 事后。
三 接线核对（同一次运行里、判定之前；不过 → 停、不出判定）：① 本脚本的接法、分散的那只权重 0（1321 与 1655 各一次）→ 三个年代与 B4 逐项相同；
   ② 只有核心的写法在分散权重 0 时 = loop6_r07_volbond.old_core(W, None)（B3）。
四 只描述（不参与判定）：SJS =「SJP 但不看日本牛熊（美股牛就一直 4 : 1）」的账户与 1987〜2000（看日本牛熊这一个开关值多少）；
   各年代美股牛的日子里拿分散那只的比例、核心换仓笔数、每年收益差、诊断里 B4 最深的几段回撤在候选里的深度。
事前预期（写在看结果之前；按一般的市场历史估计，不是这个项目的结果）：
   - SJP：Z（2003〜2006 日本涨得比纳指日元计多）多半变好；E（2007〜2012 日本长期弱，但日本熊时不拿）小幅变差或持平；
     J（2017〜2026 纳指日元计每年比日経高很多）少赚约 1〜2 pp/年 → J 多半变差；2020-03、2024-08 两个指数一起跌、日経更急 → 回撤不浅。第一关约 15%。
   - SJH：方向同 SJP、幅度更大 → 第一关约 10%。
   - SSP：以前「一直 S&P500」Z 大幅好、E / J 差 → 4 : 1 大致是它的五分之一：Z +、E / J 各约 −0.03〜−0.06 → S2 多半不过；第一关约 10%。
运行：python scripts/core_sleeve_study.py --run（只运行一次；输出已存在就拒绝）。输出 var/out/core_sleeve_study.md / .json。非投资建议。
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
import core_bullmix_study as BM                                              # noqa: E402

ERAS = ("Z", "E", "J")
OUT = "core_sleeve_study"
POSTHOC = True
FAMILY = "核心·牛市分散"
JP_T, SP_T = "1321.T", "1655.T"
SKEY = {JP_T: "SL:JP", SP_T: "SL:SP"}
NAME = {JP_T: "1321 日経225", SP_T: "1655 S&P500"}
# id → (分散的那只, 1545 权重, 分散的权重, 看不看日本牛熊)
CANDS = {"SJP": (JP_T, 4.0, 1.0, True), "SJH": (JP_T, 2.0, 1.0, True), "SSP": (SP_T, 4.0, 1.0, False)}
DESCRIBE = {"SJS": (JP_T, 4.0, 1.0, False)}                                   # 只描述：不看日本牛熊
NEIGHBORS = {"SJP": ((9.0, 1.0), (7.0, 3.0)), "SSP": ((9.0, 1.0), (7.0, 3.0)), "SJH": ((23.0 / 3, 7.0 / 3), (17.0 / 3, 13.0 / 3))}

robust_ok, verdict, dd_in, git_info, _eq, _f = BM.robust_ok, BM.verdict, BM.dd_in, BM.git_info, BM._eq, BM._f
KEYS = BM.KEYS


# ───────────────────────── 规则（纯函数；tests/test_core_sleeve_study.py） ─────────────────────────
def sleeve_closed(bear_us: pd.Series, bear_jp: pd.Series | None, own: bool) -> pd.Series:
    """分散那只的键（True = 不拿）：own = True → 美股熊 ∨ 日本熊；False → 美股熊。"""
    b = bear_us.astype(bool).to_numpy()
    if own:
        b = b | bear_jp.reindex(bear_us.index).astype(bool).to_numpy()
    return pd.Series(b, index=bear_us.index)


def mix_over(W: dict, M: dict, sleeve: str, w_core: float, w_sl: float, closed: pd.Series) -> dict:
    """B3 的接法（1545 键 US、1482 键 US_BD 原样、follow）+ 第三只（分散的那只，键 SL:*）。"""
    import loop2_r02_bondrefuge as T2
    xc = dict(W["kw"]["Z"]["extra_core"])
    xc[T2.BOND_T] = M["fb"]
    xc[sleeve] = W["assets"][sleeve]
    return {"cfg_over": {"core": {"1545.T": w_core, sleeve: w_sl, T2.BOND_T: 1.0},
                         "core_index": {"1545.T": "US", sleeve: SKEY[sleeve], T2.BOND_T: T2.BD_KEY}, "core_mode": "follow"},
            "extra_core": xc, "extra_bear": {SKEY[sleeve]: closed}}


def core_weights(bear: pd.Series, bear_jp: pd.Series | None, on: pd.Series, w_core: float, w_sl: float, own: bool) -> pd.DataFrame:
    """只有核心（1987〜2000）的持仓：u = 纳指、s = 分散的那只、b = 美债。w_sl = 0 → B3（牛 → 纳指；熊 ∧ 负相关 → 美债；其余现金）。"""
    b, o = bear.astype(bool), on.astype(bool)
    s_on = ~b if not own else (~b & ~bear_jp.reindex(b.index).astype(bool))
    s_on = s_on & (w_sl > 0)
    sc, ss = w_core / (w_core + w_sl), w_sl / (w_core + w_sl)
    u = (~b & ~s_on).astype(float) + s_on.astype(float) * sc
    s = s_on.astype(float) * ss
    bd = (b & o).astype(float)
    return pd.DataFrame({"u": u, "s": s, "b": bd}, index=b.index)


def held_share(closed: pd.Series, bull: pd.Series, m) -> float:
    """美股牛的日子里分散那只拿着（键不是熊）的比例 %。"""
    held, bl = ~closed.astype(bool).to_numpy()[m], bull.astype(bool).to_numpy()[m]
    return round(float((held & bl).sum() / max(1, int(bl.sum())) * 100), 1)


# ───────────────────────── 1987〜2000 只有核心（S7） ─────────────────────────
def old_core(W: dict, sleeve: str, w_core: float, w_sl: float, own: bool) -> dict:
    """core_bullmix_study.old_core 同一口径（loop6_r07_volbond.old_core），加分散的那只。"""
    import equity_idle_study as EI
    import halloween_study as HW
    import loop2_r02_bondrefuge as T2
    import loop6_r01_bondcorr as T
    inp = W["inp"]
    dex = inp["dexjp"].dropna()
    on_dex = lambda s: (s * dex.reindex(s.index.union(dex.index)).ffill().reindex(s.index)).dropna()      # noqa: E731
    unh = on_dex(EI.grow(EI.ndx_tr(inp), -EI.FEE["1545.T"]))
    if sleeve == JP_T:
        sl = EI.jp_product(inp["n225"], 1.0, None, None, EI.FEE[JP_T])["Close"]
    else:
        sl = on_dex(EI.grow(EI.spx_tr(inp), -EI.FEE[SP_T]))
    bnd = T2.bond_hedged(T2.bond_usd())
    bnd = bnd[bnd.index >= pd.Timestamp(T2.BOND_START)]
    spx = inp["spx"]["Close"].astype(float)
    full = unh.index[unh.index >= pd.Timestamp(T2.BOND_START)]
    ffull = lambda s: s.astype(float).reindex(full.union(s.index)).ffill().reindex(full)      # noqa: E731
    on_u = T.corr_on(ffull(spx), ffull(bnd)).shift(1, fill_value=False)
    idx = unh.index[(unh.index >= pd.Timestamp(T.OLD[0])) & (unh.index <= pd.Timestamp(T.OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    unh, b_px, s_px = unh.reindex(idx), ff(bnd), ff(sl)
    b = ff(W["bear"]["US"]).fillna(0.0) > 0.5
    bj = ff(W["bear"]["JP"]).fillna(0.0) > 0.5
    ou = ff(on_u).fillna(0.0) > 0.5
    w = core_weights(b, bj, ou, w_core, w_sl, own).shift(1).fillna(0.0)
    ret = (w["u"] * unh.pct_change().fillna(0.0) + w["b"] * b_px.pct_change().fillna(0.0)
           + w["s"] * s_px.pct_change().fillna(0.0))
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["sleeve_days_pct"] = round(float((w["s"] > 0).mean() * 100), 1)
    return out


# ───────────────────────── 运行 ─────────────────────────
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
    bear_j = N3.on_idx(W["bear"]["JP"], days)                                   # 引擎读「熊」的键同一个对齐
    ticks = {e: C9.tick_of(C9.signals(W, e)["ticker"], C9.signals(W, e)["date"], tbf[e]) for e in ERAS}

    def acct(e: str, ov: dict | None) -> tuple[dict, pd.Series, int]:
        r = L6.run(W, e, em_tick=ticks[e], **(ov or {})) if ticks[e] else L6.run(W, e, **(ov or {}))
        eng = JS.RealLotEngine.LAST[-1]
        return {**{k: r.get(k) for k in KEYS}, "years": r.get("years")}, _eq(eng), R5.core_trades(e, W)

    def closed_of(sleeve: str, own: bool) -> pd.Series:
        return sleeve_closed(bear_t, bear_j if own else None, own)

    # 三 接线核对
    base, beq, btr, wire = {}, {}, {}, {}
    for e in ERAS:
        base[e], beq[e], btr[e] = acct(e, None)
        for sl in (JP_T, SP_T):
            w0, _, _ = acct(e, mix_over(W, M, sl, 1.0, 0.0, closed_of(sl, sl == JP_T)))
            wire[f"{e}:{sl}"] = bool(all(base[e].get(k) == w0.get(k) for k in KEYS))
        say(f"{e} 基准与接线（{time.time() - t0:.0f}s）")
    o_vb = VB.old_core(W, None)
    for sl in (JP_T, SP_T):
        o0 = old_core(W, sl, 1.0, 0.0, sl == JP_T)
        wire[f"old_core:{sl}"] = bool(o0["calmar"] == o_vb["calmar"] and o0["cagr"] == o_vb["cagr"])
    same = {e: KS.same_prep(base[e], KS.B4_PREP[e]) for e in ERAS}
    if not all(wire.values()) or not all(same.values()):
        raise SystemExit(f"接线核对 / B4 重算不过 → 停：{wire} {same}")

    res: dict = {"study": OUT, "git": git_info(), "posthoc": POSTHOC, "family": FAMILY, "prereq": {k: v for k, v in pre.items() if k != "base"},
                 "wiring": wire, "b4_same": same, "base": base, "base_core_trades": btr, "old": {"B3": o_vb}, "cands": {}, "describe": {}}
    from qbreak import paths
    diag = json.loads((paths.out_dir() / "b4_weakness_diag.json").read_text(encoding="utf-8"))
    bull = ~bear_t.astype(bool)

    def one(cid: str, spec: tuple, judge: bool) -> dict:
        sl, wc, ws, own = spec
        closed = closed_of(sl, own)
        cand, ceq, ctr = {}, {}, {}
        for e in ERAS:
            cand[e], ceq[e], ctr[e] = acct(e, mix_over(W, M, sl, wc, ws, closed))
        o = old_core(W, sl, wc, ws, own)
        unseen = None if o["calmar"] is None or o_vb["calmar"] is None else o["calmar"] - o_vb["calmar"]
        s1 = R2.stage1(cand, base, posthoc=unseen)
        neigh = []
        if judge and s1["ok"]:
            for nc, ns_ in NEIGHBORS[cid]:
                na = {e: acct(e, mix_over(W, M, sl, nc, ns_, closed))[0] for e in ERAS}
                ns = R2.stage1(na, base)
                neigh.append({"w": [nc, ns_], "sleeve_pct": round(ns_ / (nc + ns_) * 100, 1), "d": ns["d"], "sum": ns["sum"],
                              "S1": ns["S1"], "S2": ns["S2"], "S3": ns["S3"]})
        hold = {}
        for e in ERAS:
            a, b = TS._win(*W["ctx"][e]["windows"][e])
            hold[e] = held_share(closed, bull, (days >= a) & (days < b))
        eps = {e: [{"from": str(x["peak"]), "to": str(x["trough"]), "b4": x["depth"], "cand": dd_in(ceq[e], x["peak"], x["trough"])}
                   for x in diag["eras"][e]["episodes"]] for e in ERAS}
        say(f"{cid} 完成（{time.time() - t0:.0f}s）")
        return {"sleeve": sl, "w": [wc, ws], "own_jp": own, "acct": cand, "core_trades": ctr, "old": o, "stage1": s1, "neighbors": neigh,
                "verdict": verdict(s1, neigh) if judge else "只描述", "hold_in_bull_pct": hold, "episodes": eps}
    for cid, spec in CANDS.items():
        res["cands"][cid] = one(cid, spec, True)
    for cid, spec in DESCRIBE.items():
        res["describe"][cid] = one(cid, spec, False)
    res["elapsed_s"] = round(time.time() - t0)
    return res


def _desc(cid: str, c: dict) -> str:
    rule = "美股牛 ∧ 日本牛时" if c["own_jp"] else "美股牛时一直"
    return f"{cid}（{rule} 1545 : {NAME[c['sleeve']]} = {c['w'][0]:g} : {c['w'][1]:g}）"


def report(res: dict) -> str:
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    B = res["base"]
    L = [f"# 核心 ETF 一侧：美股牛时核心分一小部分给别的股票指数（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；规则见 scripts/core_sleeve_study.py 开头）", "",
         f"代码 {res['git']['rev']}（未提交的改动：{res['git']['dirty']}）；先决条件 {res['prereq'].get('ok')}；接线 {all(res['wiring'].values())}；"
         f"B4 = 登记值 {all(res['b4_same'].values())}；事后（S7 适用）；用时 {res['elapsed_s']} s。", ""]
    for cid, c in res["cands"].items():
        s = c["stage1"]
        pv = s["posthoc"]
        L.append(f"- **{_desc(cid, c)}：{c['verdict']}**"
                 f"（S1 合计 {_f(s['sum'])}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；S4（{_f(s['h1'])} / {_f(s['h2'])}）：{yn(s['S4'])}；"
                 f"S7（1987〜2000 只有核心 {_f(pv['unseen'])}）：{yn(s['S7'])}；S5 / S6 不适用）")
        for n in c["neighbors"]:
            L.append(f"  - 稳健：分散占 {n['sleeve_pct']}% → 合计 {_f(n['sum'])}（" + " / ".join(f"{e} {_f(n['d'][e])}" for e in ERAS)
                     + f"）S1 {yn(n['S1'])}、S2 {yn(n['S2'])}、S3 {yn(n['S3'])}")
    allc = {**res["cands"], **res["describe"]}
    L += ["", "| 年代 | B4 年化 / 最大回撤 / Calmar（前半 / 后半） | " + " | ".join(f"{k}（Calmar 差）" for k in allc) + " |",
          "|---|---|" + "---|" * len(allc)]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'], '{:.3f}')}（{_f(x['h1'], '{:.3f}')} / {_f(x['h2'], '{:.3f}')}）"   # noqa: E731
    for e in ERAS:
        L.append(f"| {e} | {cell(B[e])} | " + " | ".join(f"{cell(c['acct'][e])}（{_f(c['stage1']['d'][e])}）" for c in allc.values()) + " |")
    L += ["", "只描述（不参与判定；SJS = SJP 但不看日本牛熊）："]
    for cid, c in allc.items():
        L.append(f"- {_desc(cid, c)}：美股牛的日子里拿分散那只 " + " / ".join(f"{e} {c['hold_in_bull_pct'][e]}%" for e in ERAS)
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
    ap = argparse.ArgumentParser(description="核心 ETF 一侧：美股牛时核心分一小部分给别的股票指数")
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
