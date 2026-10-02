"""loop3_r02_fjeust.py — 第三个研究循环第 2 轮：「日元走强状态（FJE 对冲中）里一半拿对冲版美债」FHU（资产置换类）
（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 4 / 20）。

循环的规则：scripts/research_loop3.py（第二关按类别；本轮 kind = "asset"）；基准 B1：scripts/loop2_common.py。
为什么做这个（照实写）：
  - B1 的闲置资金在「美股牛且 FJE 对冲中」（USD/JPY 急升多数决 FXE 或「日経熊且日元牛」JBH）时全部拿对冲版纳指 2845。
    规模核对（登记前，只看 B1 的状态、不含候选）：这个状态占日子 Z 11.6%（7 段）、E 20.3%（14 段）、J 16.8%（17 段）。
  - 这个状态本身是「日本 / 汇率的避险」（日元急升、日経熊）：日元急升多半伴随美日利差收窄（美国利率下降）→ 美国国债上涨；
    对冲版 → 不受日元升值影响。所以假设：在这个状态里，对冲版美国 7〜10 年国债（1482）比对冲版纳指更合适（至少拿一半）。
    两只都是对冲版、对冲成本相同 → 置换只比「纳指 vs 美国 7〜10 年国债」。日本国债 2561 不另做（省做法数；与日元急升的关联比美债弱）。
  - 本循环第 1 轮（美股熊市拿国债）的拖累是 2022 年股债一起跌（通胀熊市、日元大跌）；那时 FJE 多半不在「对冲中」→ 这一轮与第 1 轮的时段大多不重叠。
    看过第二个循环 TBH / TBJ / TBU 与本循环第 1 轮之后设计 → 事后，S7 适用（没看过的 1987〜2000 只有核心）。
  - 家族「核心·日元走强状态资产」（新家族 1 / 3）。不是「汇率对冲」家族：那个家族 = 什么时候对冲纳指（第二个循环 scripts/loop2_r02_bondrefuge.py 的定义）；
    FHU 不改对冲的时点（FJE 的状态原样），只改「对冲中」时拿什么资产。ID 是新的（第一 / 第二个循环没用过）。
  - 为什么是一半、不是原来设想的「2845 八成 + 两只国债各一成」（登记前改的，那时没有任何候选的结果）：核心的调仓带 band_pct = 10%（var/sim.json）——
    一只核心 ETF 的目标与现有的差额要 > 总资产的 10% 才买卖 → 份额 s 的 ETF 从 0 买进要「闲置资金 × s > 总资产 10%」；s = 10% 时永远买不进（闲置资金 ≤ 总资产），
    s = 50% 时闲置资金 > 总资产 20% 就买得进（B1 自己的 2845 是 > 10%）。照实写：闲置资金在总资产 10〜20% 之间时 B1 买 2845、FHU 两只都不买（留现金）——
    这是模拟盘同一个调仓带的真实结果，不另外处理；接线核对与运行里报 1482 的买卖笔数。
做法（没有学出来的参数 → S6 不适用；不改个股买卖 → S5 不适用；kind = "asset"）：
  - FHU：B1 的核心 1545 / 2845 不动，再加第三只核心 1482（对冲版美国 7〜10 年国债），它的「熊」= 2845 的「熊」（美股熊 或 不是 FJE 对冲中）
    → follow 模式下「美股牛且对冲中」时 2845 与 1482 各一半（三只权重都是 1.0）；美股牛且不是对冲中 → 1545 全部（同 B1）；美股熊 → 现金（同 B1）。
  - 1482 的合成价、费用、接法沿用第二个循环第 2 轮（scripts/loop2_r02_bondrefuge.py：DGS7 / DGS10 平均 → 8.5 年平价债、hedged_index 同一口径、
    扣 信託報酬 0.154% + 跟踪差 0.6%、2026-08-31 定水平；qbreak/fees.py 已有 1482.T）。
第一关：research_loop3.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 FHU − B1 的 Calmar 差；口径同第二个循环第 4 轮 old_core：
  前一天收盘的状态决定当天，美股牛且对冲中 → 对冲版纳指 / 对冲版美债合成价各一半，换掉的比例 × 0.1%）。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "asset" —— 1482 合成收盘的日收益序列（东证交易日 2000-01-04〜2026-09-30）
  整体循环平移 k 个交易日（research_loop3.shift_ks / asset_shift，参考日 2026-08-31 的价格水平不变），B1 的状态与 2845 不动；候选要严格大于 400 次的最大值。
接线核对（登记前，不看候选的收益）：① 1482 的「熊」全程 = True（从不拿）→ J 的账户与 B1 逐项相同；② 候选在 J 里 1482 的买卖笔数 > 0（只数笔数）。
只描述（不参与判定）：各年代「美股牛且对冲中」的日子比例与段数、那些日子（前一天定、当天拿）里 1482 与 2845 合成价的连乘收益、核心换仓笔数、每年收益差；
  1987〜2000 只有核心的两个数。
事前预期（照实写）：对冲中的日子里纳指多半在回调（日元急升 = 避险），美债多半上涨 → 回撤略浅；但美股牛时纳指长期涨得多，换掉一半会少赚；
  2013〜2015、2023〜2024 美国利率上升期的对冲中，美债可能下跌。第一关约 30%；第二关（这个资产偏偏在这个状态里特别好）约 15%。
运行：python scripts/loop3_r02_fjeust.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop3_r02_fjeust.md / .json。非投资建议。
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
import research_loop3 as R3                                                  # noqa: E402

ROUND = 2
IDS = ("FHU",)
FAMILY = "核心·日元走强状态资产"
POSTHOC = True
KIND = "asset"
SHARE = 0.5                                                                  # 对冲中：2845 与 1482 各一半（follow 模式、权重都是 1.0）
OLD = T2.OLD
OUT = "loop3_r02_fjeust"


# ───────────────────────── 接法（纯函数，tests/test_loop3_r02.py） ─────────────────────────
def fhu_over(bear_us: pd.Series, uni: pd.Series, frame: pd.DataFrame) -> dict:
    """在 B1 上加第三只核心 1482：它的「熊」= 2845 的「熊」（美股熊 或 不是对冲中）；1545 / 2845 不动（loop2_common 按键合并，core 要给全）。"""
    import loop_r04_yensurge as Y
    return {"cfg_over": {"core": {"1545.T": 1.0, Y.HEDGE_T: 1.0, T2.BOND_T: 1.0},
                         "core_index": {"1545.T": Y.UH_KEY, Y.HEDGE_T: Y.HG_KEY, T2.BOND_T: T2.BD_KEY}, "core_mode": "follow"},
            "extra_core": {T2.BOND_T: frame},
            "extra_bear": {T2.BD_KEY: Y.or_series(bear_us, ~uni.astype(bool))}}


def min_idle_to_buy(share: float, band_pct: float) -> float:
    """份额 share 的核心 ETF 从 0 买进所需的闲置资金（占总资产的比例）：闲置资金 × share > 总资产 × band_pct %。"""
    return band_pct / 100 / share


def held(bear_us: pd.Series, uni: pd.Series, idx) -> pd.Series:
    """idx 上「美股牛且对冲中」（各自向后填；没有值 = 不是）。"""
    idx = pd.DatetimeIndex(idx)
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx).fillna(0.0) > 0.5       # noqa: E731
    return ~ff(bear_us) & ff(uni)


def fhu_weights(bear: pd.Series, hedge: pd.Series, use_bond: bool, share: float = SHARE) -> pd.DataFrame:
    """只有核心（1987〜2000）的持仓：美股牛且不是对冲中 → u（日元计纳指）；美股牛且对冲中 → h（对冲版纳指）与 b（对冲版美债）各 share；美股熊 → 现金。"""
    b, h = bear.astype(bool), hedge.astype(bool)
    on = (~b & h).astype(float)
    f = share if use_bond else 0.0
    return pd.DataFrame({"u": (~b & ~h).astype(float), "h": on * (1 - f), "b": on * f}, index=bear.index)


def old_core(W: dict, uni: pd.Series, use_bond: bool) -> dict:
    """只描述 + S7：1987〜2000 只有核心（第二个循环第 4 轮 / 本循环第 1 轮 old_core 同一个口径）。"""
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
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    unh, hed, b_px = unh.reindex(idx), ff(hed), ff(bnd)
    bear = ff(W["bear"]["US"]).fillna(0.0) > 0.5
    hdg = ff(uni).fillna(0.0) > 0.5
    w = fhu_weights(bear, hdg, use_bond).shift(1).fillna(0.0)
    ret = w["u"] * unh.pct_change().fillna(0.0) + w["h"] * hed.pct_change().fillna(0.0) + w["b"] * b_px.pct_change().fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["hedge_days_pct"] = round(float((w["h"] > 0).mean() * 100), 1)
    return out


def describe(W: dict, e: str, uni: pd.Series, bc: pd.Series, hc: pd.Series) -> dict:
    """「美股牛且对冲中」的日子比例与段数；那些日子（前一天定、当天拿）里 1482 与 2845 合成价的连乘收益。"""
    a, b = W["ctx"][e]["windows"][e]
    end = pd.Timestamp(b) if b else pd.Timestamp(L2.J_END) + pd.Timedelta(days=1)
    days = bc.index[(bc.index >= pd.Timestamp(a)) & (bc.index < end)]
    on = held(W["bear"]["US"], uni, days)
    hl = on.shift(1, fill_value=False)
    out = {"on_pct": round(float(on.mean() * 100), 1), "segments": T2.segments(on)}
    for k, c in (("ust", bc), ("ndx_h", hc)):
        r = c.reindex(days).ffill().pct_change().fillna(0.0)
        out[f"{k}_on_ret_pct"] = round(float((np.prod(1 + r[hl].to_numpy()) - 1) * 100), 2) if hl.any() else 0.0
    return out


def bond_trades(e: str, W: dict) -> dict:
    """核心换仓笔数（按 ETF），1482 的买卖笔数用来核对接法生效。"""
    return T2.core_trades(e, W)


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop3_r02_fjeust.py", "scripts/loop2_r02_bondrefuge.py",
                                 "scripts/loop2_common.py", "scripts/loop_r04_yensurge.py", "scripts/loop_r15_fxeunion.py",
                                 "scripts/research_loop3.py", "scripts/candle_portfolio.py", "qbreak/fees.py", "qbreak/unified.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def inputs(W: dict):
    """1482 的合成收盘与引擎用的 K 线、2845 的合成收盘（B1 的那一份）。"""
    import equity_idle_study as EI
    import loop_r04_yensurge as Y
    bc = T2.bond_close(W["inp"])
    return bc, EI.frame_close(bc), W["b1"]["extra_core"][Y.HEDGE_T]["Close"]


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    bc, fb, hc = inputs(W)
    ov = fhu_over(W["bear"]["US"], uni, fb)
    reg = R3.load_state().get("baseline") or {}
    base, cand, ctr, desc = {}, {k: {} for k in IDS}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        ctr[e] = {"B1": bond_trades(e, W)}
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        ctr[e]["FHU"] = bond_trades(e, W)
        cand["FHU"][e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = describe(W, e, uni, bc, hc)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": old_core(W, uni, False), "FHU": old_core(W, uni, True)}
    unseen = None if old["B1"]["calmar"] is None or old["FHU"]["calmar"] is None else old["FHU"]["calmar"] - old["B1"]["calmar"]
    s1 = {"FHU": R3.stage1(cand["FHU"], base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty, "base": base,
           "cand": cand, "stage1": s1, "drift": drift, "core_trades": ctr, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 第三个研究循环第 2 轮：日元走强状态（FJE 对冲中）里一半拿对冲版美债 FHU（资产置换类）（{pd.Timestamp.today().date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop3_r02_fjeust.py 开头）", ""]
    s = res["stage1"]["FHU"]
    pv = s["posthoc"]
    L.append(f"- **FHU：{'第一关全过 → 另行登记第二关（1482 收益循环平移）' if s['ok'] else R3.FAIL1}**"
             f"（S1 合计 {_f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
             f"S4（{_f(s['h1'], '{:+.3f}')} / {_f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
             f"S7（1987〜2000 只有核心 {_f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | FHU（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['FHU'][e])}（{_f(s['d'][e], '{:+.3f}')}） |")
    ct = res["core_trades"]
    L += ["", "接线核对（不参与判定）：核心买卖笔数 " + "；".join(
        f"{e} B1 2845 {ct[e]['B1'].get('2845.T', 0)}、FHU 2845 {ct[e]['FHU'].get('2845.T', 0)} / 1482 {ct[e]['FHU'].get(T2.BOND_T, 0)}"
        for e in L2.ERAS), "", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        L.append(f"- {e}：美股牛且对冲中 {_f(d['on_pct'], '{:.1f}')}% 的日子（{d['segments']} 段）；那些日子里的连乘收益 1482 {_f(d['ust_on_ret_pct'], '{:+.2f}')}%、"
                 f"2845 {_f(d['ndx_h_on_ret_pct'], '{:+.2f}')}%")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {_f(o[k]['calmar'])}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%）" for k in ("B1", "FHU"))
        + f"；对冲中的日子 {_f(o['FHU'].get('hedge_days_pct'), '{:.1f}')}%")
    for e in L2.ERAS:
        yb = res["base"][e].get("years") or {}
        yc = res["cand"]["FHU"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（FHU − B1，pp）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R3.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def wiring() -> int:
    """登记前用（J）：① 1482 从不拿 → 账户与 B1 逐项相同；② 候选 1482 的买卖笔数 > 0（只数笔数，不看候选的收益）。"""
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    _, fb, _ = inputs(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    never = fhu_over(W["bear"]["US"], pd.Series(False, index=uni.index), fb)
    rn = L2.run(W, "J", **never)
    same = all(rb.get(x) == rn.get(x) for x in keys)
    L2.run(W, "J", **fhu_over(W["bear"]["US"], uni, fb))
    n_bond = bond_trades("J", W).get(T2.BOND_T, 0)
    print(json.dumps({"never_same_as_b1": same, "fhu_1482_trades_J": n_bond}, ensure_ascii=False))
    return 0 if same and n_bond > 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环第 2 轮：FHU（日元走强状态里一半拿对冲版美债）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的收益）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
