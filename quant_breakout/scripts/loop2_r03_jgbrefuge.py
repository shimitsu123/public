"""loop2_r03_jgbrefuge.py — 第二个研究循环第 3 轮：「美股熊市里拿日本国债」TBJ（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 3 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；第 2 轮 TBH：scripts/loop2_r02_bondrefuge.py（登记 119aa46）。
为什么做这个（照实写）：第 2 轮 TBH（美股熊且对冲版美债自己是牛 → 1482）合计 +0.248，S1 / S2 / S3 / S7 都过、只差 S4（Z 后一半没拿债券、
  权益路径不同 −0.023）。要验证的假设是「美股熊市里高信用的国债是日元投资者的避险」；TBH 用的是外国国债 + 汇率对冲（对冲成本在美国利率高的年代很大）。
  这一轮换一个独立的资产复现同一个假设：日本国债（日元资产，没有汇率、没有对冲成本）。先试过「债券牛熊用相邻 9 组参数多数决」的稳健性检查，
  它与 TBH 的债券牛熊 98.4% 的日子相同（只看状态，没跑账户）→ 几乎是重复，没有登记、不算做法。
  → 看过 TBH 的结果之后设计 → 按事后处理，S7 适用。家族「核心·熊市避险资产」2 / 3。
做法（参数事先写定、没调 → S6 不适用；不改个股买卖 → S5 不适用）：
  TBJ：B1 的美股牛熊分界是「熊」且「日本国债自己的牛熊」是「牛」→ 闲置资金拿 2561（iシェアーズ・コア 日本国債 ETF），否则同 B1。
    日本国债的牛熊 = 模拟盘同一个检测器、同一组参数（250 日线 ±3%、连续 5 天），套在 2561 的合成价上（与 TBH 同一个做法）。
  2561 合成价（全程同一做法）：財務省 国债金利情报的 5 / 10 / 20 年收益率各当作同期限的平价债，日收益三等分平均（20 年 1986-12 起）
    → 扣 信託報酬 税込 0.066%；东证 d 日 = 前一天的值（d 日收盘后才公布 → 保守晚一天）；价格水平按 2026-08-31 真实收盘 ¥1,979。
    登记前的数据核对（全部年份，不分牛熊）：与真实 2561（2021〜2026）逐年平均差 +0.05 pp、平均绝对差 0.88 pp；只用 10 年的话平均绝对差 1.68 pp
    （2561 跟踪的是全部期限的 FTSE 日本国债指数）→ 用阶梯。
  费用表：qbreak/fees.py 加 2561.T（一手 1 口、滑点 0.10%；BlackRock 官网 2026-10-02 查：信託報酬 税込 0.066%、売買単位 1 口、
    純資産 約 601 億円（2026-10-01）、实效久期 9.33 年（2026-09-30）；Yahoo 到 2026-09-30：收盘 ¥1,967、近 60 个交易日日均成交额约 0.47 亿円）。
  接线：日本国债从不是牛（= 从不拿 2561）时必须与 B1 完全相同（登记前跑过三个年代的数字一致检查）。
第一关：research_loop2.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 TBJ − B1 的 Calmar 差；口径同第 2 轮，
  日本国债的牛熊在日本日期上算、晚一天用，向后填到美国日期）。另报（不参与判定）：同一次运行里 TBH 的数字。
第二关（第一关全过才做）：另行登记（提交）后只运行一次，「同样多、同样形状的随机改动」在那时写定。
只描述：各年代美股熊的日子比例、其中拿 2561 的比例与段数、拿着时 2561 合成价的连乘收益、每年收益差。
事前预期（照实写，按一般的市场历史估计）：2001〜2003、2008 下半年、2010、2015〜16（负利率）日本国债上涨；2022〜2025 日本利率上升 → 债券自己是熊 → 现金；
  幅度比 TBH 小（久期约 10 年但日本利率波动小）—— Z +0.05〜+0.15、E +0.03〜+0.10、J ±0.02；第一关约 30%，「更好候选」约 8%。
运行：python scripts/loop2_r03_jgbrefuge.py（第一关）。输出 var/out/loop2_r03_jgbrefuge.md / .json。非投资建议。

第二关（2026-10-02 第一关全过之后另行登记；登记 = 加这一段的那次提交，之后不改、只运行一次，`--stage2 TBJ`）：
  第一个循环第 4 / 11 / 14 / 15 轮同一个口径 —— 把候选自己新加的那条信号「日本国债自己的牛熊」（东证交易日，2000-01-04〜2026-09-30）
  整体循环平移 k 天（k ∈ [250, N − 250]，种子 s = 0〜399：numpy.random.default_rng([20262003, s])），美股牛熊分界与 B1 的其余部分都不动
  → 「美股熊且（平移后的）日本国债牛 → 拿 2561」= 同样多、同样形状的随机改动；统计量 = 三个年代 Calmar 差合计（同一次运行里 TBJ 与 B1 重算），
  要严格大于 400 次的最大值（research_loop2.stage2；有算不出的、次数不够 → 不过）。
  事前预期（照实写）：美股熊市里日本国债平均是涨的 → 随机的日子也会多半赚一点；候选要赢过 400 次里最好的那一次，约 25%。
  输出 var/out/loop2_r03_jgbrefuge_stage2_TBJ.md / .json。
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
import loop2_r02_bondrefuge as T2                                            # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 3
IDS = ("TBJ",)
FAMILY = T2.FAMILY
POSTHOC = True
JGB_T, JG_KEY = "2561.T", "US_JG"
LADDER = (5, 10, 20)                                                        # 年：財務省 5 / 10 / 20 年收益率，各当作同期限的平价债，等权
TRUST_FEE = 0.066                                                           # 年 %（税込）
REF_DATE, REF_PX = "2026-08-31", 1979.0                                     # 2561 的真实收盘（Yahoo）
OLD = T2.OLD
OUT = "loop2_r03_jgbrefuge"
SHIFT_FROM, SHIFT_GAP, SEED0 = "2000-01-04", 250, 20262003          # 第二关（另行登记）


# ───────────────────────── 规则（纯函数，tests/test_loop2_r03.py） ─────────────────────────
def ladder_tr(curve: pd.DataFrame, tenors=LADDER) -> pd.Series:
    """几只固定期限平价债的日收益等权平均 → 总收益指数（从 1 起；所有期限都有值的日子才算）。"""
    r = pd.concat([T2.par_bond_tr(curve[f"{t}Y"], float(t)).pct_change() for t in tenors], axis=1).dropna()
    return (1 + r.mean(axis=1)).cumprod()


def jgb_tr() -> pd.Series:
    """2561 的日元总收益（日本日期）：財務省 5 / 10 / 20 年阶梯 → 扣信託報酬。"""
    import equity_idle_study as EI
    from qbreak import factors
    return EI.grow(ladder_tr(factors.jgb_curve()), -TRUST_FEE)


def jgb_close(inp: dict, tr: pd.Series | None = None) -> pd.Series:
    """东证交易日的 2561 合成收盘：d 日 = 前一天的值（財務省当天收盘后才公布 → 保守晚一天），按 REF_DATE 定水平。"""
    import equity_idle_study as EI
    s = jgb_tr() if tr is None else tr
    days = inp["n225"].index[inp["n225"].index >= pd.Timestamp(T2.BOND_START)]
    c = EI.prev_on(days, s).dropna()
    return c * (REF_PX / float(c.asof(pd.Timestamp(REF_DATE))))


def tbj_over(bear_us: pd.Series, jgb_on: pd.Series, frame: pd.DataFrame) -> dict:
    """在 B1 上加第三只核心 2561：它的「熊」= 美股牛 或 日本国债不是牛（两个都 True 才拿）；B1 的 1545 / 2845 不动。"""
    import loop_r04_yensurge as Y
    return {"cfg_over": {"core": {"1545.T": 1.0, Y.HEDGE_T: 1.0, JGB_T: 1.0},
                         "core_index": {"1545.T": Y.UH_KEY, Y.HEDGE_T: Y.HG_KEY, JGB_T: JG_KEY}, "core_mode": "follow"},
            "extra_core": {JGB_T: frame},
            "extra_bear": {JG_KEY: Y.or_series(~bear_us.astype(bool), ~jgb_on.astype(bool))}}


def shift_domain(s: pd.Series, a: str = SHIFT_FROM, b: str = L2.J_END) -> pd.Series:
    return s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]


def shift_k(seed: int, n: int, gap: int = SHIFT_GAP) -> int:
    rng = np.random.default_rng([SEED0, int(seed)])
    return int(rng.integers(gap, n - gap + 1))


def shifted(s: pd.Series, seed: int) -> pd.Series:
    """第二关：日本国债的牛熊序列在 SHIFT_FROM〜J_END 里整体循环平移（同样多、同样形状）。"""
    w = shift_domain(s)
    return pd.Series(np.roll(w.to_numpy(bool), shift_k(seed, len(w))), index=w.index)


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def core_trades(e: str, W: dict) -> dict:
    return T2.core_trades(e, W)


def old_core(W: dict, uni: pd.Series, use_jgb: bool) -> dict:
    """只描述 + S7：1987〜2000 只有核心（第 2 轮 old_core 同一个口径）；日本国债 = 阶梯合成（日本日期 → 向后填到美国日期），
    牛熊在日本日期上算、晚一天用；持仓由前一天收盘的状态决定，换掉的比例 × 0.1%。"""
    import equity_idle_study as EI
    import fxhedge_study as FX
    import halloween_study as HW
    from qbreak import factors
    inp = W["inp"]
    dex = inp["dexjp"].dropna()
    ntr = EI.ndx_tr(inp)
    unh = EI.grow(ntr, -EI.FEE["1545.T"])
    unh = (unh * dex.reindex(unh.index.union(dex.index)).ffill().reindex(unh.index)).dropna()
    hed = FX.hedged_index(EI.grow(ntr, -0.22), factors.fred("DFF", max_age_h=1e9), factors.fred("IRSTCI01JPM156N", max_age_h=1e9))
    jtr = jgb_tr()
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    unh, hed, jg = unh.reindex(idx), ff(hed), ff(jtr)
    bear = ff(W["bear"]["US"]).fillna(0.0) > 0.5
    hdg = ff(uni).fillna(0.0) > 0.5
    on = (ff(T2.trend_on(jtr).shift(1, fill_value=False)).fillna(0.0) > 0.5) if use_jgb else pd.Series(False, index=idx)
    w = T2.core_weights(bear, hdg, on).shift(1).fillna(0.0)
    ret = w["u"] * unh.pct_change().fillna(0.0) + w["h"] * hed.pct_change().fillna(0.0) + w["b"] * jg.pct_change().fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["bond_days_pct"] = round(float(w["b"].mean() * 100), 1)
    return out


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r03_jgbrefuge.py", "scripts/loop2_r02_bondrefuge.py",
                                 "scripts/loop2_common.py", "scripts/research_loop2.py", "scripts/candle_portfolio.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    import equity_idle_study as EI
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    jc = jgb_close(W["inp"])
    on_j = T2.trend_on(jc)
    ov = tbj_over(W["bear"]["US"], on_j, EI.frame_close(jc))
    bc = T2.bond_close(W["inp"])
    ov_h = T2.tbh_over(W["bear"]["US"], T2.trend_on(bc), EI.frame_close(bc))
    reg = R2.load_state().get("baseline") or {}
    base, cand, ctr, desc = {}, {"TBJ": {}, "TBH": {}}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        ctr[e] = {"B1": core_trades(e, W)}
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        ctr[e]["TBJ"] = core_trades(e, W)
        cand["TBJ"][e] = {**_acct(rc), "years": rc.get("years")}
        cand["TBH"][e] = _acct(L2.run(W, e, **ov_h))
        desc[e] = T2.describe(W, e, on_j, jc)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": old_core(W, uni, False), "TBJ": old_core(W, uni, True)}
    unseen = None if old["B1"]["calmar"] is None or old["TBJ"]["calmar"] is None else old["TBJ"]["calmar"] - old["B1"]["calmar"]
    s1 = {"TBJ": R2.stage1(cand["TBJ"], base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base, "cand": cand,
           "stage1": s1, "drift": drift, "core_trades": ctr, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["TBJ"]
    ph = s1["posthoc"]
    L = [f"# 第二个研究循环第 3 轮：美股熊市里拿日本国债 TBJ（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r03_jgbrefuge.py 开头）", "",
         f"- **TBJ（美股熊且日本国债自己是牛 → 闲置资金拿 2561，否则同 B1）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | TBJ（Calmar 差） | 另报：同一次运行的 TBH |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['TBJ'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | {cell(res['cand']['TBH'][e])} |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d, c = res["describe"][e], res["core_trades"][e]
        L.append(f"- {e}：美股熊的日子 {_f(d['bear_pct'], '{:.1f}')}%，其中拿 2561 {_f(d['held_pct_of_bear'], '{:.1f}')}%（{d['segments']} 段，"
                 f"拿着时 2561 合成价连乘 {_f(d['held_ret_pct'], '{:+.2f}')}%）；核心换仓 B1 {sum(c['B1'].values())} → TBJ {sum(c['TBJ'].values())} 笔"
                 f"（2561 {c['TBJ'].get(JGB_T, 0)} 笔）")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["TBJ"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（TBJ − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心）：B1 {oc(o['B1'])}；TBJ {oc(o['TBJ'])}（拿日本国债的日子 {o['TBJ']['bond_days_pct']}%）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


_G: dict = {}


def _placebo_one(seed: int) -> float | None:
    W, on, frame, base = _G["W"], _G["on"], _G["frame"], _G["base"]
    try:
        ov = tbj_over(W["bear"]["US"], shifted(on, seed), frame)
        tot = 0.0
        for e in L2.ERAS:
            c = L2.run(W, e, **ov)["calmar"]
            if c is None or base[e] is None:
                return None
            tot += c - base[e]
        return round(float(tot), 6)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two(k: str, workers: int) -> int:
    import multiprocessing as mp
    import equity_idle_study as EI
    from qbreak import paths
    t0 = time.time()
    s1 = json.loads((paths.out_dir() / f"{OUT}.json").read_text(encoding="utf-8"))["stage1"][k]
    if not s1["ok"]:
        print(f"{k} 第一关没过 → 不做第二关")
        return 1
    code, dirty = git_head()
    W = L2.load()
    jc = jgb_close(W["inp"])
    on = T2.trend_on(jc)
    frame = EI.frame_close(jc)
    base = {e: L2.run(W, e)["calmar"] for e in L2.ERAS}
    cand = {e: L2.run(W, e, **tbj_over(W["bear"]["US"], on, frame))["calmar"] for e in L2.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L2.ERAS), 6)
    _G.update({"W": W, "on": on, "frame": frame, "base": base})
    seeds = list(range(R2.PLACEBO_N))
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
    s2 = R2.stage2(stat, vals)
    vd = R2.verdict(s1, s2)
    v = np.array([x for x in vals if x is not None], float)
    res = {"round": ROUND, "id": k, "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "stage1_stat": s1["sum"],
           "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {}, "seconds": round(time.time() - t0)}
    L = [f"# 第二个研究循环第 3 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}", "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 3 轮：TBJ")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
