"""loop6_r09_volcash.py — 第六个研究循环第三段（基准 B3 = 撤掉 FJE 之后的模拟盘 Q1B，修正口径）第 9 轮：
「高波动且纳指正在跌（收在 50 日线下）的牛市里，三分之一核心离开纳指 —— 股债负相关时换对冲版美债、不是负相关时留现金」VCT
（2026-10-03 登记；先提交后只运行一次；家族「核心·波动率仓位」这一段 3 / 3（最后一个）；kind = signal；事后 → S7 适用）。

用户（2026-10-03）：㊼ ①「重新检验，不过就撤」（只回答编号 = 同时同意：第六个循环按修正口径重算基准、计数接着 7 / 20、照现行规则选题）；
之前「…没有时间限制 一直找到比现在算法更好的」。循环的规则：scripts/research_loop6.py（第三段 = 开头「九」与末尾一节）；基准 B3：scripts/loop6_common.load3。
为什么做这个（照实写；看过第 7 轮 VBH、第 8 轮 VBT 的结果与 B3 的回撤分段之后设计 = 事后）：
  - VBH / VBT 都让 J 的最大回撤 −29.61% → −22.03%（2020-02〜03 那一段，股债负相关 → 美债涨），但只在负相关时动；
    B3 的回撤分段（本会话的描述，不跑候选）里有好几段负相关很少、美债帮不上：Z 最深的 2006-04〜07 −14.29%（0%）、J 2024-07〜08 −21.34%（0%）、
    J 2025-01〜04 −23.54%（17%）。这些时候 BCU 的逻辑（债券只在负相关时是避险）说该拿的是现金，不是美债。
  - 没看过的 1987〜2000：只有核心的最大回撤是 1987-10（−44.69%），那次大跌前股债是同涨同跌（正相关）→ VBH / VBT 在那里没动（S7 −0.020 / −0.004）。
  → 同一个信号（VBT 原样：高波动 ∧ 纳指在 50 日线下），三分之一离开纳指：负相关 → 1482（同 VBT）、不是负相关 → 现金。
做法 VCT（VT20 的状态与参数、50 日线、BCU 的相关条件、2 : 1 都同第 8 轮 VBT；没有新参数 → S6 不适用；不改个股 → S5 不适用）：
  - 信号 = loop6_r08_voltrend.signal（美元计纳指总收益：VT20 比例 < 1 且 收盘 < 50 日简单均线）；东证日的对齐同 B3 的「美股熊」。
  - 美股牛 ∧ 信号 ∧ 股债 63 天负相关 → 1545 : 1482 = 2 : 1（同 VBT）；美股牛 ∧ 信号 ∧ 不是负相关 → 1545 拿 2/3、1/3 现金；其余同 B3。
  - 接法 = VBT 的接法（1545 键 US、1482 键 US_BD、follow 2 : 1）+ 引擎的 core_expo["US"]（1545 的目标再乘：上面「留现金」的日子 = 2/3，其余 = 1）。
第一关：research_loop6.stage1（S1〜S4 + S7：1987〜2000 只有核心 VCT − B3 > 0；只有核心的口径 = 第 7 轮 old_core（同一套合成价、相关、前一天的状态、
  换仓扣 0.1% × 换的比例），持仓多一条「牛 ∧ 信号 ∧ 不是负相关 → 纳指 2/3、现金 1/3」）。
第二关（第一关全过才做；另行登记后只运行一次；代码写在本脚本 --stage2）：kind = signal —— 候选自己新加的信号「高波动 ∧ 正在跌」（东证日上的布尔序列）
  在 2000-01-04〜2026-09-30 的东证交易日上整体循环平移 k（research_loop6.shift_ks(n, 0)：种子 [20261006, 0, s]），窗外不动；
  美债与现金两部分都跟着平移后的信号重算；B3（美股熊、股债相关、价格）不动。候选的 Calmar 差合计要严格大于 400 次的最大值（有算不出的 = 不过）。
接线核对（登记前，不看候选的结果；--wiring）：① 信号永远不成立 → 三个年代与 B3 逐项相同；② 「留现金」那部分关掉（core_expo 全 1）→ 三个年代与
  第 8 轮 VBT 已公开的账户（var/out/loop6_r08_voltrend.json）逐项相同；③ old_core：信号 None = B3 的 old_core、「留现金」关掉 = VBT 的 old_core（两个都与
  第 7 轮的函数直接算的相同）；④ B3 的引擎参数里没有别的 core_expo（候选加的是唯一一个）。
只描述（不参与判定）：各年代美股牛日子里 信号且负相关（拿美债）/ 信号且不是负相关（留现金）的比例与段数；核心换仓笔数；每年收益差；
  1987〜2000 的同样数字；最新一天的状态。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop6_r09_volcash.py（第一关）；--scale（只数日子）；--wiring（登记前的接线核对）；--stage2 VCT [--workers N]（第二关）。
输出 var/out/loop6_r09_volcash.md / .json（第二关 loop6_r09_volcash_stage2_VCT.md / .json）。非投资建议。

第二关（2026-10-03 第一关全过之后另行登记；登记 = 加这一段的那次提交，之后不改、只运行一次，`--stage2 VCT --workers 3`；第一关与 --stage2 的代码不改）：
  形状 = 第一关登记时写定的那一个 —— 信号「高波动 ∧ 正在跌」（东证日上的布尔序列）在 2000-01-04〜2026-09-30 的 6,549 个东证交易日上整体循环平移 k
  （research_loop6.shift_ks(n, 0)：numpy.random.default_rng([20261006, 0, s])，s = 0〜399），窗外不动；拿美债（负相关）与留现金（不是负相关）
  两部分都跟着平移后的信号重算（vct_over）；B3（美股熊、股债相关、价格）不动；每次三个年代都跑，统计量 = Calmar 差合计（对同一次运行的 B3）；
  VCT 要严格大于 400 次的最大值（research_loop6.stage2；有算不出的 = 不过）。
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
import loop2_r02_bondrefuge as T2                                            # noqa: E402
import loop6_common as L6                                                    # noqa: E402
import loop6_r01_bondcorr as T                                               # noqa: E402
import loop6_r07_volbond as V                                                # noqa: E402
import loop6_r08_voltrend as X                                               # noqa: E402
import research_loop6 as R6                                                  # noqa: E402

ROUND = 9
IDS = ("VCT",)
FAMILY = {"VCT": "核心·波动率仓位"}
KIND = {"VCT": "signal"}
POSTHOC = True
KEEP = V.W_CORE / (V.W_CORE + V.W_BOND)                                      # 留现金的日子 1545 拿 2/3（与拿美债时 1545 的份额相同）
OLD = V.OLD
OUT = "loop6_r09_volcash"
REF8 = "loop6_r08_voltrend.json"                                             # 接线核对 ②：第 8 轮 VBT 已公开的账户
on_idx = V.on_idx
KEYS = X.KEYS


# ───────────────────────── 规则（纯函数，tests/test_loop6_r09.py） ─────────────────────────
def cash_days(bear_t: pd.Series, sig_t: pd.Series, on_b: pd.Series) -> pd.Series:
    """东证日：留现金的日子 = 美股牛 ∧ 信号 ∧ 不是负相关。"""
    idx = on_b.index
    b, s, o = on_idx(bear_t, idx).to_numpy(bool), on_idx(sig_t, idx).to_numpy(bool), on_b.astype(bool).to_numpy()
    return pd.Series(~b & s & ~o, index=idx)


def expo_us(bear_t: pd.Series, sig_t: pd.Series, on_b: pd.Series, enabled: bool = True) -> pd.Series:
    """1545（键 US）目标再乘的比例：留现金的日子 = KEEP（2/3），其余 = 1；enabled = False → 全 1（接线核对用）。"""
    c = cash_days(bear_t, sig_t, on_b)
    return pd.Series(np.where(c.to_numpy(bool) & enabled, KEEP, 1.0), index=c.index)


def vct_over(W: dict, M: dict, sig_t: pd.Series, cash: bool = True) -> dict:
    """VBT 的接法（vbh_over：1545 键 US、1482 键 US_BD = ¬负相关 ∨（牛 ∧ ¬信号）、2 : 1）+ core_expo["US"]（留现金的日子 2/3）。"""
    ov = X.vbt_over(W, M, sig_t)
    return {**ov, "core_expo": {"US": expo_us(M["bear_t"], sig_t, M["on_b"], enabled=cash)}}


def core_weights(bear: pd.Series, sig: pd.Series, on: pd.Series, cash: bool = True) -> pd.DataFrame:
    """只有核心（1987〜2000）的持仓：牛 ∧ 信号 ∧ 负相关 → 纳指 2/3、美债 1/3；牛 ∧ 信号 ∧ 不是负相关 → 纳指 2/3（cash = False → 纳指 1）；
    牛的其余 → 纳指 1；熊 ∧ 负相关 → 美债 1；其余现金。"""
    b, s, o = bear.astype(bool), sig.astype(bool), on.astype(bool)
    w = V.core_weights(b, s, o)
    if cash:
        cut = ~b & s & ~o
        w.loc[cut, "u"] = KEEP
    return w


def shifted_signal(sig_t: pd.Series, k: int | None) -> pd.Series:
    return X.shifted_signal(sig_t, k)


def placebo_ks(n: int) -> list[int]:
    return R6.shift_ks(n, 0)


# ───────────────────────── 1987〜2000 只有核心（S7） ─────────────────────────
def old_core(W: dict, sig_us: pd.Series | None, cash: bool = True) -> dict:
    """第 7 轮 old_core 同一个口径（日元计纳指不对冲、对冲版美债、S&P 与美债 63 天相关（前一天）、前一天的状态决定当天、换仓扣 0.1% × 换的比例），
    持仓换成本轮的 core_weights；sig_us = None → B3。"""
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
    s = (ff(sig_us).fillna(0.0) > 0.5) if sig_us is not None else pd.Series(False, index=idx)
    ou = ff(on_u).fillna(0.0) > 0.5
    w = core_weights(b, s, ou, cash=cash).shift(1).fillna(0.0)
    ret = w["u"] * unh.pct_change().fillna(0.0) + w["b"] * b_px.pct_change().fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["bond_mix_pct"] = round(float(((w["u"] > 0) & (w["b"] > 0)).mean() * 100), 1)
    out["cash_cut_pct"] = round(float(((w["u"] > 0) & (w["u"] < 1 - 1e-9) & (w["b"] <= 0)).mean() * 100), 1)
    out["sig_bull_pct"] = round(float((s & ~b).sum() / max(1, int((~b).sum())) * 100), 1)
    return out


# ───────────────────────── 规模 ─────────────────────────
def state_share(bear_t, sig_t, on_b, days) -> dict:
    """这段日子里：美股牛的天数、其中 信号且负相关（拿美债）/ 信号且不是负相关（留现金）的比例与段数（只数日子）。"""
    days = pd.DatetimeIndex(days)
    b, s, o = on_idx(bear_t, days), on_idx(sig_t, days), on_idx(on_b, days)
    bull = ~b
    bond, cash = bull & s & o, bull & s & ~o
    nb = int(bull.sum())
    pct = lambda x: round(float(x) / nb * 100, 1) if nb else None                  # noqa: E731
    return {"bull_days": nb, "bond_pct": pct(int(bond.sum())), "bond_segments": V.segments(bond),
            "cash_pct": pct(int(cash.sum())), "cash_segments": V.segments(cash)}


def scale(W: dict, M: dict) -> dict:
    out = {e: state_share(M["bear_t"], M["sig_t"], M["on_b"], V.era_days(W, e)) for e in L6.ERAS}
    w = R6.shift_window(M["sig_t"])
    out["window"] = state_share(M["bear_t"], M["sig_t"], M["on_b"], w.index)
    out["sig_share_2000_2026"] = round(float(w.mean() * 100), 1)
    out["shift_n"] = len(w)
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "us_bear": bool(M["bear_t"].iloc[-1]), "signal": bool(M["sig_t"].iloc[-1]),
                     "corr_neg": bool(M["on_b"].iloc[-1])}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def stage_one() -> int:
    import loop2_r05_ddbrake as R5
    from qbreak import paths
    t0 = time.time()
    code, dirty = V.git_head()
    W = L6.load3()
    M = X.inputs(W)
    ov = vct_over(W, M, M["sig_t"])
    reg = R6.segment(R6.load_state()).get("baseline") or {}
    base, cand, trades = {}, {"VCT": {}}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand["VCT"][e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B3": nb, "VCT": nc}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B3": old_core(W, None), "VCT": old_core(W, M["sig_us"])}
    unseen = None if old["B3"]["calmar"] is None or old["VCT"]["calmar"] is None else old["VCT"]["calmar"] - old["B3"]["calmar"]
    s1 = {"VCT": R6.stage1(cand["VCT"], base, posthoc=unseen)}
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
    f = V._f
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s = res["stage1"]["VCT"]
    pv = s["posthoc"]
    L = [f"# 第六个研究循环第三段第 9 轮：高波动且纳指在 50 日线下的牛市里三分之一核心离开纳指（负相关 → 美债、否则现金）VCT（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop6_r09_volcash.py 开头；基准 B3 = Q1B，修正口径）", "",
         f"- **VCT：{'第一关全过 → 另行登记第二关（信号循环平移）' if s['ok'] else R6.FAIL1}**"
         f"（S1 合计 {f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
         f"S4（{f(s['h1'], '{:+.3f}')} / {f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）",
         "", "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | VCT（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{f(x['cagr'], '{:+.2f}')}% / {f(x['dd'], '{:.2f}')}% / {f(x['calmar'])}（{f(x['h1'])} / {f(x['h2'])}）"   # noqa: E731
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['VCT'][e])}（{f(s['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定；规模只数日子）："]
    sc = res["scale"]
    for e in L6.ERAS:
        x = sc[e]
        L.append(f"- {e}：美股牛 {x['bull_days']} 天里 信号且负相关（拿美债）{f(x['bond_pct'], '{:.1f}')}%（{x['bond_segments']} 段）、"
                 f"信号且不是负相关（留现金）{f(x['cash_pct'], '{:.1f}')}%（{x['cash_segments']} 段）；"
                 f"核心换仓 B3 {res['core_trades'][e]['B3']} → VCT {res['core_trades'][e]['VCT']} 笔")
    lt = sc["latest"]
    L.append(f"- 信号在 2000〜2026 全部东证日里的比例 {sc['sig_share_2000_2026']}%；最新一天 {lt['date']}：美股{'熊' if lt['us_bear'] else '牛'}、"
             f"信号 {'是' if lt['signal'] else '否'}、股债负相关 {'是' if lt['corr_neg'] else '否'}")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {f(o[k]['calmar'])}（年化 {f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {f(o[k].get('dd'), '{:.2f}')}%、"
        f"纳指 + 美债 {f(o[k].get('bond_mix_pct'), '{:.1f}')}% / 纳指 2/3 + 现金 {f(o[k].get('cash_cut_pct'), '{:.1f}')}% 的日子）" for k in ("B3", "VCT"))
        + f"；美股牛的日子里信号 {f(o['VCT'].get('sig_bull_pct'), '{:.1f}')}%")
    for e in L6.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["VCT"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（VCT − B3，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B3 与第三段登记值的 Calmar 差：" + "、".join(f"{e} {f(dr[e], '{:+.4f}')}" for e in L6.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R6.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B3）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L6.load3()
    M = X.inputs(W)
    print(json.dumps({"scale": scale(W, M)}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用：① 信号永远不成立 → B3；② 留现金关掉 → 第 8 轮 VBT 已公开的账户；③ old_core 的两个特例；④ B3 的引擎参数里没有别的 core_expo。"""
    from qbreak import paths
    W = L6.load3()
    M = X.inputs(W)
    no_other = {e: "core_expo" not in (W["kw"][e] or {}) and "core_expo" not in (W.get("b1") or {}) for e in L6.ERAS}
    never = pd.Series(False, index=M["sig_t"].index)
    ov0 = vct_over(W, M, never)
    same_b3 = {}
    for e in L6.ERAS:
        rb, r0 = L6.run(W, e), L6.run(W, e, **ov0)
        same_b3[e] = bool(all(rb.get(x) == r0.get(x) for x in KEYS))
    ref = json.loads((paths.out_dir() / REF8).read_text(encoding="utf-8"))["cand"]["VBT"]
    ovn = vct_over(W, M, M["sig_t"], cash=False)
    same_vbt = {}
    for e in L6.ERAS:
        r = L6.run(W, e, **ovn)
        same_vbt[e] = bool(all(r.get(x) == ref[e].get(x) for x in ("cagr", "dd", "calmar", "h1", "h2", "n")))
    o_b3, o_b3v = old_core(W, None), V.old_core(W, None)
    o_vbt, o_vbtv = old_core(W, M["sig_us"], cash=False), V.old_core(W, M["sig_us"])
    out = {"no_other_core_expo": no_other, "never_same_as_b3": same_b3, "no_cash_same_as_vbt": same_vbt,
           "old_core_b3_same": bool(o_b3["calmar"] == o_b3v["calmar"] and o_b3["cagr"] == o_b3v["cagr"]),
           "old_core_no_cash_same_as_vbt": bool(o_vbt["calmar"] == o_vbtv["calmar"] and o_vbt["cagr"] == o_vbtv["cagr"])}
    print(json.dumps(out, ensure_ascii=False))
    ok = (all(no_other.values()) and all(same_b3.values()) and all(same_vbt.values()) and out["old_core_b3_same"]
          and out["old_core_no_cash_same_as_vbt"])
    return 0 if ok else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次；signal = 信号循环平移） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        kw = vct_over(W, M, shifted_signal(M["sig_t"], ks[int(seed)]))
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
    code, dirty = V.git_head()
    W = L6.load3()
    M = X.inputs(W)
    base = {e: L6.run(W, e)["calmar"] for e in L6.ERAS}
    ov = vct_over(W, M, M["sig_t"])
    cand = {e: L6.run(W, e, **ov)["calmar"] for e in L6.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L6.ERAS), 6)
    n = len(R6.shift_window(M["sig_t"]))
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
    f = V._f
    res = {"loop": 6, "segment": 3, "round": ROUND, "id": k, "kind": KIND[k], "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat,
           "stage1_stat": s1["sum"], "n": n, "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第六个研究循环第三段第 9 轮 第二关：{k} vs 400 次信号循环平移（{KIND[k]}；B3 不动）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {f(res['q'].get(95), '{:+.4f}')}、99 分位 {f(res['q'].get(99), '{:+.4f}')}；随机里比 B3 好的 {f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第六个研究循环第三段第 9 轮：VCT")
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
