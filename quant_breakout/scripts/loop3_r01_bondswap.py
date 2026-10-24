"""loop3_r01_bondswap.py — 第三个研究循环第 1 轮：「美股熊市的闲置资金无条件拿高信用国债」BAJ / BAU / BAB（资产置换类）
（2026-10-02 登记；先提交后只运行一次；用掉 3 个做法 → 3 / 20）。

循环的规则：scripts/research_loop3.py（第二关按类别；本轮 kind = "asset"）；基准 B1：scripts/loop2_common.py。
为什么做这个（照实写）：
  - 第二个循环第 2〜4 轮（TBH / TBJ / TBU）加了「债券自己是牛才拿」的过滤，第一关过（TBJ / TBU）、时点平移的第二关不过 ——
    但随机时点 95〜98% 也比 B1 好 → 效果在「美股熊市里拿国债而不是现金」这个资产本身，不在债券自己的牛熊过滤。
    第三个循环登记时写定：先做「资产置换类」—— 不加任何新的择时信号，只在 B1 已有的状态（美股熊市：B1 的闲置资金是现金）里换成国债，
    第二关检验「国债偏偏在美股熊市里特别好（避险）」而不是时点。
  - 资产与合成价、费用、接法全部沿用第二个循环（已核对、已登记）：1482 = scripts/loop2_r02_bondrefuge.py（对冲版美国 7〜10 年国债合成价，
    扣 信託報酬 0.154% + 跟踪差 0.6%）、2561 = scripts/loop2_r03_jgbrefuge.py（財務省 5 / 10 / 20 年阶梯合成价，扣 0.066%）；费用表 qbreak/fees.py 已有两只。
  - 看过 TBH / TBJ / TBU 的结果之后设计 → 事后，S7 适用（没看过的 1987〜2000 只有核心）。家族「核心·熊市避险资产」（与第二个循环同一个家族名；本循环 3 / 3）。
    ID 是新的（第一 / 第二个循环没用过）。
做法（没有参数 → S6 不适用；不改个股买卖 → S5 不适用；kind = "asset"）：
  - BAJ：B1 的美股牛熊分界是「熊」→ 闲置资金拿 2561（日本国债），否则同 B1（美股牛：FJE 对冲中 → 2845、否则 1545）。
  - BAU：美股熊 → 1482（对冲版美国 7〜10 年国债）。
  - BAB：美股熊 → 1482 与 2561 各一半（follow 模式下两只「不是熊」的核心平分）。
  - 接法 = 第二个循环 TBH / TBJ / TBU 的 *_over 原样，债券的「牛」全程 = True（= 不加过滤）；美股牛熊分界、FJE、个股层全部同 B1。
第一关：research_loop3.stage1（= research_loop2.stage1；trade = None、lenses = None、posthoc = 1987〜2000 只有核心 候选 − B1 的 Calmar 差；
  口径同第二个循环第 2〜4 轮的 old_core，只是债券不加牛熊过滤：前一天收盘的美股熊 → 当天拿债券）。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "asset" —— 换进来的资产的日收益序列（东证交易日的合成收盘，2000-01-04〜2026-09-30）
  整体循环平移 k 个交易日（research_loop3.shift_ks / asset_shift；BAB 的两只用同一个 k 一起平移），B1 的状态不动；候选要严格大于 400 次的最大值。
接线核对（登记前，不看候选的结果）：两只债券的「熊」全程 = True（从不拿）→ J 的账户与 B1 逐项相同。同一次运行里另报债券的买卖笔数（应 > 0）。
只描述（不参与判定）：各年代美股熊的日子比例、熊市里拿着的债券合成价的连乘收益、核心换仓笔数、每年收益差；1987〜2000 只有核心的三个数。
事前预期（照实写）：第二个循环的 TBJ / TBU 加过滤时合计 +0.25〜+0.28；不加过滤会多拿 2022、2025 的国债下跌（股债一起跌）→ J 变差、Z / E 差不多
  → 第一关 BAJ 约 40%、BAU 约 30%、BAB 约 40%；第二关（资产与状态的对齐要胜过 400 次随机对齐的最好一次）各约 15%。
运行：python scripts/loop3_r01_bondswap.py（第一关）；--wiring（登记前的接线核对）。输出 var/out/loop3_r01_bondswap.md / .json。非投资建议。
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
import loop2_r04_bondunion as T4                                             # noqa: E402
import research_loop3 as R3                                                  # noqa: E402

ROUND = 1
IDS = ("BAJ", "BAU", "BAB")
FAMILY = T2.FAMILY
POSTHOC = True
KIND = "asset"
OLD = T2.OLD
OUT = "loop3_r01_bondswap"


# ───────────────────────── 接法（纯函数，tests/test_loop3_r01.py） ─────────────────────────
def always(idx) -> pd.Series:
    """债券的「牛」全程 = True（不加过滤）。"""
    return pd.Series(True, index=pd.DatetimeIndex(idx))


def overs(bear_us: pd.Series, fb: pd.DataFrame, fj: pd.DataFrame, on_b: pd.Series, on_j: pd.Series) -> dict:
    """三个做法的覆盖（第二个循环 TBH / TBJ / TBU 的接法原样）。"""
    return {"BAJ": T3.tbj_over(bear_us, on_j, fj), "BAU": T2.tbh_over(bear_us, on_b, fb),
            "BAB": T4.tbu_over(bear_us, on_b, fb, on_j, fj)}


def old_core(W: dict, uni: pd.Series, use_ust: bool, use_jgb: bool) -> dict:
    """只描述 + S7：1987〜2000 只有核心（第二个循环第 4 轮 old_core 同一个口径），债券不加牛熊过滤（美股熊 → 拿；两只都用 → 各一半）。"""
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
    on, off = pd.Series(True, index=idx), pd.Series(False, index=idx)
    w = T4.union_weights(bear, hdg, on if use_ust else off, on if use_jgb else off).shift(1).fillna(0.0)
    ret = (w["u"] * unh.pct_change().fillna(0.0) + w["h"] * hed.pct_change().fillna(0.0)
           + w["b"] * b_px.pct_change().fillna(0.0) + w["j"] * j_px.pct_change().fillna(0.0))
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["bond_days_pct"] = round(float((w["b"] + w["j"] > 0).mean() * 100), 1)
    return out


def describe(W: dict, e: str, bc: pd.Series, jc: pd.Series) -> dict:
    """美股熊的日子比例、熊市里（前一天定、当天拿）两只债券合成价的连乘收益。"""
    a, b = W["ctx"][e]["windows"][e]
    days = bc.index[(bc.index >= pd.Timestamp(a)) & ((bc.index < pd.Timestamp(b)) if b else True)]
    bus = W["bear"]["US"].astype(float).reindex(days.union(W["bear"]["US"].index)).ffill().reindex(days).fillna(0.0) > 0.5
    hl = bus.shift(1, fill_value=False)
    out = {"bear_pct": round(float(bus.mean() * 100), 1), "segments": T2.segments(bus)}
    for k, c in (("ust", bc), ("jgb", jc)):
        r = c.reindex(days).pct_change().fillna(0.0)
        out[f"{k}_bear_ret_pct"] = round(float((np.prod(1 + r[hl].to_numpy()) - 1) * 100), 2) if hl.any() else 0.0
    return out


def bond_trades(e: str, W: dict) -> dict:
    """核心换仓笔数（按 ETF），债券的买卖笔数用来核对接法生效。"""
    return T2.core_trades(e, W)


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop3_r01_bondswap.py", "scripts/loop2_r02_bondrefuge.py",
                                 "scripts/loop2_r03_jgbrefuge.py", "scripts/loop2_r04_bondunion.py", "scripts/loop2_common.py",
                                 "scripts/research_loop3.py", "scripts/candle_portfolio.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def inputs(W: dict):
    import equity_idle_study as EI
    bc, jc = T2.bond_close(W["inp"]), T3.jgb_close(W["inp"])
    return bc, jc, EI.frame_close(bc), EI.frame_close(jc)


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    bc, jc, fb, fj = inputs(W)
    ov = overs(W["bear"]["US"], fb, fj, always(bc.index), always(jc.index))
    reg = R3.load_state().get("baseline") or {}
    base, cand, ctr, desc = {}, {k: {} for k in IDS}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        ctr[e] = {"B1": bond_trades(e, W)}
        base[e] = {**_acct(rb), "years": rb.get("years")}
        for k in IDS:
            rc = L2.run(W, e, **ov[k])
            ctr[e][k] = bond_trades(e, W)
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = describe(W, e, bc, jc)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": old_core(W, uni, False, False), "BAJ": old_core(W, uni, False, True), "BAU": old_core(W, uni, True, False),
           "BAB": old_core(W, uni, True, True)}
    s1 = {}
    for k in IDS:
        unseen = None if old["B1"]["calmar"] is None or old[k]["calmar"] is None else old[k]["calmar"] - old["B1"]["calmar"]
        s1[k] = R3.stage1(cand[k], base, posthoc=unseen)
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
    L = [f"# 第三个研究循环第 1 轮：美股熊市的闲置资金无条件拿高信用国债 BAJ / BAU / BAB（资产置换类）（{pd.Timestamp.today().date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop3_r01_bondswap.py 开头）", ""]
    for k in IDS:
        s = res["stage1"][k]
        pv = s["posthoc"]
        L.append(f"- **{k}：{'第一关全过 → 另行登记第二关（资产收益循环平移）' if s['ok'] else R3.FAIL1}**"
                 f"（S1 合计 {_f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
                 f"S4（{_f(s['h1'], '{:+.3f}')} / {_f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
                 f"S7（1987〜2000 只有核心 {_f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | BAJ（Calmar 差） | BAU | BAB |", "|---|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS) + " |")
    ct = res["core_trades"]
    L += ["", "接线核对（不参与判定）：债券买卖笔数 " + "；".join(
        f"{e} " + "、".join(f"{k} 1482 {ct[e][k].get(T2.BOND_T, 0)} / 2561 {ct[e][k].get(T3.JGB_T, 0)}" for k in IDS) for e in L2.ERAS),
        "", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        L.append(f"- {e}：美股熊 {_f(d['bear_pct'], '{:.1f}')}% 的日子（{d['segments']} 段）；熊市里拿着的连乘收益 1482 {_f(d['ust_bear_ret_pct'], '{:+.2f}')}%、"
                 f"2561 {_f(d['jgb_bear_ret_pct'], '{:+.2f}')}%")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：B1 " + "、".join(
        f"{k} {_f(o[k]['calmar'])}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%）" for k in ("B1",) + IDS))
    for e in L2.ERAS:
        yb = res["base"][e].get("years") or {}
        parts = []
        for k in IDS:
            yc = res["cand"][k][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            parts.append(f"{k} " + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
        L.append(f"- {e} 每年收益差（候选 − B1，pp）：" + "；".join(parts))
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R3.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def wiring() -> int:
    """登记前用：J 年代 两只债券的「熊」全程 = True（从不拿）→ 账户与 B1 逐项相同（不跑候选）。"""
    W = L2.load()
    bc, jc, fb, fj = inputs(W)
    never_b, never_j = pd.Series(False, index=bc.index), pd.Series(False, index=jc.index)
    ov = overs(W["bear"]["US"], fb, fj, never_b, never_j)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    out = {k: all(rb.get(x) == L2.run(W, "J", **ov[k]).get(x) for x in keys) for k in IDS}
    print(json.dumps({"never_same_as_b1": out}, ensure_ascii=False))
    return 0 if all(out.values()) else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环第 1 轮：BAJ / BAU / BAB（美股熊市的闲置资金无条件拿国债）")
    ap.add_argument("--wiring", action="store_true", help="登记前的接线核对（不跑候选）")
    a = ap.parse_args(argv)
    return wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
