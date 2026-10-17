"""loop2_r04_bondunion.py — 第二个研究循环第 4 轮：「美股熊市里拿对冲版美债 或 日本国债」TBU = TBH ∪ TBJ（2026-10-02 登记；先提交后只运行一次；
用掉 1 个做法 → 4 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；第 2 轮 TBH：scripts/loop2_r02_bondrefuge.py；第 3 轮 TBJ：scripts/loop2_r03_jgbrefuge.py。
为什么做这个（照实写）：
  - TBH（对冲版美债 1482）合计 +0.248、只差 S4（Z 后一半的路径差）；TBJ（日本国债 2561）合计 +0.247、第一关全过、第二关约第 99.5 百分位
    （400 次随机平移最大 +0.254；随机的 97.8% 比 B1 好、中位 +0.168）→ 同一个假设「美股熊市里拿高信用国债」用两种资产都成立，效果主要来自资产本身。
  - 两只的「牛」不完全重叠（例：2022 美债是熊、日本国债在收益率曲线控制下还是牛；2016 两只都是牛）→ 合起来拿：两只都是牛就各一半（分散），
    只有一只是牛就拿那一只，都不是就现金。这与第一个循环 FJH / FJE（两个对冲信号合并）是同一种做法。
  → 看过 TBH / TBJ 的结果之后的组合 = 事后组合，S7 适用。家族「核心·熊市避险资产」3 / 3（这个家族到此用完）。
做法（参数事先写定、没调 → S6 不适用；不改个股买卖 → S5 不适用）：
  TBU：B1 的美股牛熊分界是「熊」时，1482（第 2 轮同一个合成价与「自己的牛熊」）是牛就拿、2561（第 3 轮同一个）是牛就拿，
    两只都是牛 → 闲置资金各一半（引擎的 follow 模式：牛的核心平分）；都不是 → 现金；美股牛 → 同 B1（FJE：2845 或 1545）。
  接线：两只都从不是牛 = B1；只有 1482 = TBH；只有 2561 = TBJ（登记前跑过三个年代的数字一致检查）。
第一关：research_loop2.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 TBU − B1 的 Calmar 差；
  口径同第 2 / 3 轮：两只都牛 → 各一半，两只债券的牛熊都再晚一天用）。另报（不参与判定）：同一次运行里 TBH、TBJ 的数字。
第二关（第一关全过才做）：另行登记（提交）后只运行一次，「同样多、同样形状的随机改动」在那时写定。
事前预期（照实写）：合计约 +0.20〜+0.30（两只的平均附近，分散后回撤可能更浅）；第二关仍要赢过「随机时点也有资产效果」的 400 次最大值 →
  第一关约 55%，「更好候选」约 12%。不论结果，这个家族到此用完。
运行：python scripts/loop2_r04_bondunion.py（第一关）。输出 var/out/loop2_r04_bondunion.md / .json。非投资建议。

第二关（2026-10-02 第一关全过之后另行登记；登记 = 加这一段的那次提交，之后不改、只运行一次，`--stage2 TBU`）：
  第 3 轮 TBJ 同一个口径 —— 把候选自己新加的两条信号「对冲版美债自己的牛熊」「日本国债自己的牛熊」（都是东证交易日，2000-01-04〜2026-09-30）
  用同一个 k 一起整体循环平移（k ∈ [250, N − 250]，种子 s = 0〜399：numpy.random.default_rng([20262004, s])；两条之间的关系不变），
  美股牛熊分界与 B1 的其余部分都不动 → 同样多、同样形状的随机改动；统计量 = 三个年代 Calmar 差合计（同一次运行里 TBU 与 B1 重算），
  要严格大于 400 次的最大值（research_loop2.stage2；有算不出的、次数不够 → 不过）。
  事前预期（照实写）：TBJ 的随机平移 97.8% 比 B1 好、最大 +0.254 → 这次随机的也会多半赚；候选 +0.277 要赢过 400 次里最好的那一次，约 30%。
  输出 var/out/loop2_r04_bondunion_stage2_TBU.md / .json。
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
import loop2_r03_jgbrefuge as T3                                             # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 4
IDS = ("TBU",)
FAMILY = T2.FAMILY
POSTHOC = True
OLD = T2.OLD
OUT = "loop2_r04_bondunion"
SHIFT_FROM, SHIFT_GAP, SEED0 = "2000-01-04", 250, 20262004          # 第二关（另行登记）


# ───────────────────────── 规则（纯函数，tests/test_loop2_r04.py） ─────────────────────────
def tbu_over(bear_us: pd.Series, ust_on: pd.Series, ust_frame: pd.DataFrame, jgb_on: pd.Series, jgb_frame: pd.DataFrame) -> dict:
    """在 B1 上加两只核心：1482（美股熊且美债牛）、2561（美股熊且日本国债牛）；follow 模式下牛的核心平分 → 两只都牛各一半。"""
    import loop_r04_yensurge as Y
    a, b = T2.tbh_over(bear_us, ust_on, ust_frame), T3.tbj_over(bear_us, jgb_on, jgb_frame)
    return {"cfg_over": {"core": {**a["cfg_over"]["core"], **b["cfg_over"]["core"]},
                         "core_index": {**a["cfg_over"]["core_index"], **b["cfg_over"]["core_index"]}, "core_mode": "follow"},
            "extra_core": {**a["extra_core"], **b["extra_core"]},
            "extra_bear": {**a["extra_bear"], **b["extra_bear"]}}


def union_weights(bear: pd.Series, hedge: pd.Series, ust: pd.Series, jgb: pd.Series) -> pd.DataFrame:
    """只有核心（1987〜2000）的持仓：美股牛 → 纳指（对冲中 → h、否则 u）；美股熊 → 牛的债券平分（b 美债、j 日本国债）；都不是 → 现金。"""
    b, h, o1, o2 = bear.astype(bool), hedge.astype(bool), ust.astype(bool), jgb.astype(bool)
    n = (b & o1).astype(float) + (b & o2).astype(float)
    share = 1.0 / n.where(n > 0, 1.0)
    return pd.DataFrame({"u": (~b & ~h).astype(float), "h": (~b & h).astype(float),
                         "b": (b & o1).astype(float) * share, "j": (b & o2).astype(float) * share}, index=bear.index)


def shift_domain(s: pd.Series, a: str = SHIFT_FROM, b: str = L2.J_END) -> pd.Series:
    return s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]


def shift_k(seed: int, n: int, gap: int = SHIFT_GAP) -> int:
    rng = np.random.default_rng([SEED0, int(seed)])
    return int(rng.integers(gap, n - gap + 1))


def shifted_pair(a: pd.Series, b: pd.Series, seed: int) -> tuple[pd.Series, pd.Series]:
    """第二关：两条债券牛熊序列放到同一组日子上（SHIFT_FROM〜J_END），用同一个 k 一起整体循环平移（两条之间的关系不变）。"""
    wa, wb = shift_domain(a), shift_domain(b)
    idx = wa.index.intersection(wb.index)
    k = shift_k(seed, len(idx))
    va, vb = wa.reindex(idx).fillna(False).to_numpy(bool), wb.reindex(idx).fillna(False).to_numpy(bool)
    return pd.Series(np.roll(va, k), index=idx), pd.Series(np.roll(vb, k), index=idx)


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def old_core(W: dict, uni: pd.Series, use_ust: bool, use_jgb: bool) -> dict:
    """只描述 + S7：1987〜2000 只有核心（第 2 / 3 轮 old_core 同一个口径）；两只债券的牛熊都在各自的日期上算、晚一天用。"""
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
    bnd = T2.bond_hedged(T2.bond_usd())
    bnd = bnd[bnd.index >= pd.Timestamp(T2.BOND_START)]
    jtr = T3.jgb_tr()
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    unh, hed, b_px, j_px = unh.reindex(idx), ff(hed), ff(bnd), ff(jtr)
    bear = ff(W["bear"]["US"]).fillna(0.0) > 0.5
    hdg = ff(uni).fillna(0.0) > 0.5
    off = pd.Series(False, index=idx)
    on_b = (ff(T2.trend_on(bnd).shift(1, fill_value=False)).fillna(0.0) > 0.5) if use_ust else off
    on_j = (ff(T2.trend_on(jtr).shift(1, fill_value=False)).fillna(0.0) > 0.5) if use_jgb else off
    w = union_weights(bear, hdg, on_b, on_j).shift(1).fillna(0.0)
    ret = (w["u"] * unh.pct_change().fillna(0.0) + w["h"] * hed.pct_change().fillna(0.0)
           + w["b"] * b_px.pct_change().fillna(0.0) + w["j"] * j_px.pct_change().fillna(0.0))
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["bond_days_pct"] = round(float((w["b"] + w["j"] > 0).mean() * 100), 1)
    return out


def describe(W: dict, e: str, ust_on: pd.Series, jgb_on: pd.Series, idx: pd.DatetimeIndex) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    days = idx[(idx >= pd.Timestamp(a)) & ((idx < pd.Timestamp(b)) if b else True)]
    bus = W["bear"]["US"].astype(float).reindex(days.union(W["bear"]["US"].index)).ffill().reindex(days).fillna(0.0) > 0.5
    hb, hj = T2.held(W["bear"]["US"], ust_on, days), T2.held(W["bear"]["US"], jgb_on, days)
    nb = int(bus.sum())
    pct = lambda m: round(float(m[bus].mean() * 100), 1) if nb else None          # noqa: E731
    return {"bear_pct": round(float(bus.mean() * 100), 1), "both_pct_of_bear": pct(hb & hj), "ust_only_pct_of_bear": pct(hb & ~hj),
            "jgb_only_pct_of_bear": pct(~hb & hj), "cash_pct_of_bear": pct(~hb & ~hj)}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r04_bondunion.py", "scripts/loop2_r03_jgbrefuge.py",
                                 "scripts/loop2_r02_bondrefuge.py", "scripts/loop2_common.py", "scripts/research_loop2.py",
                                 "scripts/candle_portfolio.py", "qbreak/fees.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    import equity_idle_study as EI
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    bc, jc = T2.bond_close(W["inp"]), T3.jgb_close(W["inp"])
    on_b, on_j = T2.trend_on(bc), T2.trend_on(jc)
    fb, fj = EI.frame_close(bc), EI.frame_close(jc)
    bear = W["bear"]["US"]
    ov = tbu_over(bear, on_b, fb, on_j, fj)
    ov_h, ov_j = T2.tbh_over(bear, on_b, fb), T3.tbj_over(bear, on_j, fj)
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {"TBU": {}, "TBH": {}, "TBJ": {}}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        cand["TBU"][e] = {**_acct(rc), "years": rc.get("years")}
        cand["TBH"][e] = _acct(L2.run(W, e, **ov_h))
        cand["TBJ"][e] = _acct(L2.run(W, e, **ov_j))
        desc[e] = describe(W, e, on_b, on_j, bc.index.union(jc.index))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": old_core(W, uni, False, False), "TBU": old_core(W, uni, True, True)}
    unseen = None if old["B1"]["calmar"] is None or old["TBU"]["calmar"] is None else old["TBU"]["calmar"] - old["B1"]["calmar"]
    s1 = {"TBU": R2.stage1(cand["TBU"], base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base, "cand": cand,
           "stage1": s1, "drift": drift, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["TBU"]
    ph = s1["posthoc"]
    L = [f"# 第二个研究循环第 4 轮：美股熊市里拿对冲版美债 或 日本国债 TBU（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r04_bondunion.py 开头）", "",
         f"- **TBU（= TBH ∪ TBJ，两只都牛各一半）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | TBU（Calmar 差） | 另报：TBH / TBJ 的 Calmar |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['TBU'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | "
                 f"{_f(res['cand']['TBH'][e]['calmar'])} / {_f(res['cand']['TBJ'][e]['calmar'])} |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        L.append(f"- {e}：美股熊的日子 {_f(d['bear_pct'], '{:.1f}')}%；其中两只都拿 {_f(d['both_pct_of_bear'], '{:.1f}')}%、只拿美债 {_f(d['ust_only_pct_of_bear'], '{:.1f}')}%、"
                 f"只拿日本国债 {_f(d['jgb_only_pct_of_bear'], '{:.1f}')}%、现金 {_f(d['cash_pct_of_bear'], '{:.1f}')}%")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["TBU"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（TBU − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心）：B1 {oc(o['B1'])}；TBU {oc(o['TBU'])}（拿债券的日子 {o['TBU']['bond_days_pct']}%）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


_G: dict = {}


def _placebo_one(seed: int) -> float | None:
    W, on_b, on_j, fb, fj, base = _G["W"], _G["on_b"], _G["on_j"], _G["fb"], _G["fj"], _G["base"]
    try:
        sb, sj = shifted_pair(on_b, on_j, seed)
        ov = tbu_over(W["bear"]["US"], sb, fb, sj, fj)
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
    bc, jc = T2.bond_close(W["inp"]), T3.jgb_close(W["inp"])
    on_b, on_j = T2.trend_on(bc), T2.trend_on(jc)
    fb, fj = EI.frame_close(bc), EI.frame_close(jc)
    base = {e: L2.run(W, e)["calmar"] for e in L2.ERAS}
    cand = {e: L2.run(W, e, **tbu_over(W["bear"]["US"], on_b, fb, on_j, fj))["calmar"] for e in L2.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L2.ERAS), 6)
    _G.update({"W": W, "on_b": on_b, "on_j": on_j, "fb": fb, "fj": fj, "base": base})
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
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第二个研究循环第 4 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B1 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 4 轮：TBU")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
