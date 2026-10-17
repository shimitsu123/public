"""loop6_r01_bondcorr.py — 第六个研究循环（核心层）第 1 轮：美股熊市里、只在「股债负相关」（国债起避险作用）时拿高信用国债 BCU / BCJ / BCB
（2026-10-03 登记；先提交后只运行一次；家族「核心·熊市避险资产」3 / 3；kind = asset；三个都是事后 → S7 适用）。

用户（2026-10-03 约 11:50 JST）：「继续第五个循环 并找到接下来研究成功率最大的方向 没有时间限制 一直找到比现在算法更好的」。
循环的规则：scripts/research_loop6.py；基准 B1：scripts/loop2_common.py。
为什么先做这个（照实写）：
  - 研究成功率统计里「核心·熊市避险资产」6 个做法第一关全过 2 个（TBJ、TBU）、只差一条 4 个（TBH、BAJ、BAU、BAB）—— 是第一关通过率最高的家族之一。
  - 第三个循环第 1 轮「美股熊市无条件拿国债」（资产置换类）：BAU 合计 +0.241（Z +0.194、E +0.059、J −0.012）只差 S4、BAJ +0.248 只差 S2（J −0.024）、
    BAB +0.252 只差 S4；差的那一条都来自 J 的 2022（BAU −6.4 pp、BAJ −3.8 pp：通胀熊市里股债一起跌）与 E 的 2009（BAU −11.2 pp）。
    第二个循环加了「债券自己是牛才拿」的过滤（TBJ / TBU）第一关过、但时点平移的第二关不过（随机时点 95〜98% 也比 B1 好 = 效果在资产本身）。
  - 机制（文献）：股债相关的正负由宏观冲击决定 —— 增长冲击为主时国债是避险（负相关，2000〜2020 年的常态），通胀冲击为主时股债一起跌
    （正相关，1970〜90 年代、2022 年）（Campbell, Sunderam & Viceira 2017；Campbell, Pflueger & Viceira 2020；Ilmanen 2003）。
    → 只在最近一个季度股债日收益负相关时，才把熊市的闲置资金放进国债；正相关时照 B1 拿现金。条件只由国债自己的价格与美股指数算出。
  - 照实写：看过 BAU / BAJ / BAB（以及 TBH / TBJ / TBU）的结果、知道失败来自 2022 之后设计 → 三个都按事后处理，S7 适用（没看过的 1987〜2000 只有核心，
    候选 − B1 > 0）。参数一次写定、没有调：窗口 63 个交易日（一个季度）、门槛 0（相关的正负）→ S6 不适用。不改个股买卖 → S5 不适用。
做法（只改美股熊市里闲置资金拿什么；美股牛熊分界、FJE、个股层全部同 B1；接法 = 第二 / 三个循环 TBH / TBJ / TBU 的 *_over 原样，
  「债券可拿」的序列换成相关条件）：
  - 相关条件 corr_on：东证交易日上（S&P500 = 前一个美国收盘、1482 合成价 = 前一个美国收盘、2561 合成价 = 前一天的值，都是 d 日开盘前已知），
    最近 63 天两者日收益的相关 < 0 → 可拿；不到 63 天 / 算不出 → 不拿。
  - BCU：美股熊 且 S&P500 与 1482（对冲版美国 7〜10 年国债）负相关 → 闲置资金拿 1482；否则同 B1（美股熊 → 现金）。
  - BCJ：美股熊 且 S&P500 与 2561（日本国债阶梯）负相关 → 拿 2561。
  - BCB：两只各自按自己的条件；都可拿 → 各一半（follow 模式平分）；只有一只可拿 → 那一只。
第一关：research_loop6.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 候选 − B1 的 Calmar 差；口径同第三个循环第 1 轮 old_core，
  美国日期上算同样的 63 天相关、因为 FRED 的收益率第二天才公布 → 相关条件再晚一天用）。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = asset —— 换进来的债券的东证收盘（2000-01-04〜2026-09-30）日收益整体循环平移 k
  （research_loop6.shift_ks(n, 1)、research_loop3.asset_shift；BCB 的两只用同一个 k 一起平移），相关条件用平移后的价格重算；
  B1 的状态与 S&P500 不动；候选的 Calmar 差合计要严格大于 400 次的最大值。代码写在本脚本（--stage2），第二关登记时只加登记、不改代码。
接线核对（登记前，不看候选的结果）：J 年代 ① 条件全为 False（从不拿）→ 与 B1 逐项相同；② 条件全为 True → 与第三个循环 BAJ / BAU / BAB 已公开的
  J 账户（Calmar / 年化 / 回撤）相同（同一条代码路径）。
只描述（不参与判定）：各年代美股熊的日子比例、其中条件成立（可拿）的比例与段数、条件不成立的熊市年份；1987〜2000 只有核心的三个数；每年收益差。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop6_r01_bondcorr.py（第一关）；--scale（只数日子）；--wiring（登记前的接线核对）；--stage2 BCU|BCJ|BCB [--workers N]（第二关）。
输出 var/out/loop6_r01_bondcorr.md / .json（第二关 loop6_r01_bondcorr_stage2_<ID>.md / .json）。非投资建议。
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
import research_loop6 as R6                                                  # noqa: E402

ROUND = 1
IDS = ("BCU", "BCJ", "BCB")
FAMILY = {k: "核心·熊市避险资产" for k in IDS}
KIND = {k: "asset" for k in IDS}
POSTHOC = True
WIN = 63                                                                     # 相关的窗口（交易日）
USE = {"BCU": (True, False), "BCJ": (False, True), "BCB": (True, True)}      # (拿 1482, 拿 2561)
OLD = T2.OLD
REF3 = "loop3_r01_bondswap.json"                                             # 接线核对 ②：第三个循环 BAJ / BAU / BAB 已公开的账户
SAME3 = {"BCU": "BAU", "BCJ": "BAJ", "BCB": "BAB"}
OUT = "loop6_r01_bondcorr"


# ───────────────────────── 规则（纯函数，tests/test_loop6_r01.py） ─────────────────────────
def corr_on(stock: pd.Series, asset: pd.Series, win: int = WIN) -> pd.Series:
    """asset 的日期上：最近 win 天两者日收益的相关 < 0 → True（国债起避险作用）；不到 win 天 / 算不出 → False。"""
    a = asset.dropna().astype(float)
    s = stock.astype(float).reindex(a.index.union(stock.index)).ffill().reindex(a.index)
    c = s.pct_change().rolling(win, min_periods=win).corr(a.pct_change())
    return pd.Series(np.where(c.to_numpy(float) < 0, True, False), index=a.index)


def spx_tse(W: dict, days: pd.DatetimeIndex) -> pd.Series:
    """东证交易日 d 的 S&P500 = 前一个美国收盘（与 1482 合成价同一个对齐）。"""
    import equity_idle_study as EI
    return EI.on_jp(W["inp"]["spx"]["Close"].astype(float), None, pd.DatetimeIndex(days))


def masks(spx: pd.Series, bc: pd.Series, jc: pd.Series) -> tuple[pd.Series, pd.Series]:
    return corr_on(spx, bc), corr_on(spx, jc)


def overs(bear_us: pd.Series, fb: pd.DataFrame, fj: pd.DataFrame, on_b: pd.Series, on_j: pd.Series) -> dict:
    """三个做法的覆盖（第二个循环 TBH / TBJ / TBU 的接法原样，「可拿」换成相关条件）。"""
    return {"BCU": T2.tbh_over(bear_us, on_b, fb), "BCJ": T3.tbj_over(bear_us, on_j, fj), "BCB": T4.tbu_over(bear_us, on_b, fb, on_j, fj)}


def bear_on_stats(bear: pd.Series, on: pd.Series, days: pd.DatetimeIndex) -> dict:
    """这段日子里：美股熊的日子比例、其中条件成立的比例与段数、有熊但条件一天都不成立的年份（只数日子，不看收益）。"""
    days = pd.DatetimeIndex(days)
    b = bear.astype(float).reindex(days.union(bear.index)).ffill().reindex(days).fillna(0.0) > 0.5
    o = on.astype(float).reindex(days.union(on.index)).ffill().reindex(days).fillna(0.0) > 0.5
    both = b & o
    yrs_b = b.groupby(days.year).sum()
    yrs_o = both.groupby(days.year).sum()
    off_years = [int(y) for y in yrs_b.index if yrs_b[y] > 0 and yrs_o.get(y, 0) == 0]
    return {"bear_pct": round(float(b.mean() * 100), 1), "on_in_bear_pct": round(float(both.sum() / b.sum() * 100), 1) if b.any() else None,
            "segments": T2.segments(both), "bear_days_by_year": {str(y): int(v) for y, v in yrs_b.items() if v > 0},
            "on_days_by_year": {str(y): int(yrs_o.get(y, 0)) for y, v in yrs_b.items() if v > 0}, "off_years": off_years}


# ───────────────────────── 1987〜2000 只有核心（S7） ─────────────────────────
def old_core(W: dict, uni: pd.Series, use_ust: bool, use_jgb: bool, cond: bool = True) -> dict:
    """第三个循环第 1 轮 old_core 同一个口径；cond = True → 债券只在 63 天相关 < 0 时可拿（美国日期上算、再晚一天用：FRED 第二天才公布）。"""
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
    spx = inp["spx"]["Close"].astype(float)
    full = unh.index[unh.index >= pd.Timestamp(T2.BOND_START)]
    ffull = lambda s: s.astype(float).reindex(full.union(s.index)).ffill().reindex(full)      # noqa: E731
    on_u = corr_on(ffull(spx), ffull(bnd)).shift(1, fill_value=False) if cond else pd.Series(True, index=full)
    on_j = corr_on(ffull(spx), ffull(jtr)).shift(1, fill_value=False) if cond else pd.Series(True, index=full)
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    unh, hed, b_px, j_px = unh.reindex(idx), ff(hed), ff(bnd), ff(jtr)
    bear = ff(W["bear"]["US"]).fillna(0.0) > 0.5
    hdg = ff(uni).fillna(0.0) > 0.5
    off = pd.Series(False, index=idx)
    ou, oj = ff(on_u).fillna(0.0) > 0.5, ff(on_j).fillna(0.0) > 0.5
    w = T4.union_weights(bear, hdg, ou if use_ust else off, oj if use_jgb else off).shift(1).fillna(0.0)
    ret = (w["u"] * unh.pct_change().fillna(0.0) + w["h"] * hed.pct_change().fillna(0.0)
           + w["b"] * b_px.pct_change().fillna(0.0) + w["j"] * j_px.pct_change().fillna(0.0))
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["bond_days_pct"] = round(float((w["b"] + w["j"] > 0).mean() * 100), 1)
    return out


# ───────────────────────── 输入 ─────────────────────────
def inputs(W: dict) -> dict:
    import equity_idle_study as EI
    bc, jc = T2.bond_close(W["inp"]), T3.jgb_close(W["inp"])
    spx = spx_tse(W, bc.index.union(jc.index))
    on_b, on_j = masks(spx, bc, jc)
    return {"bc": bc, "jc": jc, "fb": EI.frame_close(bc), "fj": EI.frame_close(jc), "spx": spx, "on_b": on_b, "on_j": on_j}


def scale(W: dict, M: dict) -> dict:
    out = {}
    for e in L2.ERAS:
        a, b = W["ctx"][e]["windows"][e]
        days = pd.DatetimeIndex(W["ctx"][e]["days"])
        days = days[(days >= pd.Timestamp(a)) & ((days < pd.Timestamp(b)) if b else True)]
        out[e] = {"ust": bear_on_stats(W["bear"]["US"], M["on_b"], days), "jgb": bear_on_stats(W["bear"]["US"], M["on_j"], days)}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop6_r01_bondcorr.py", "scripts/loop2_r02_bondrefuge.py",
                                 "scripts/loop2_r03_jgbrefuge.py", "scripts/loop2_r04_bondunion.py", "scripts/loop2_common.py",
                                 "scripts/research_loop6.py", "scripts/candle_portfolio.py", "qbreak/fees.py"],
                                capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    M = inputs(W)
    ov = overs(W["bear"]["US"], M["fb"], M["fj"], M["on_b"], M["on_j"])
    reg = R6.load_state().get("baseline") or {}
    base, cand = {}, {k: {} for k in IDS}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        for k in IDS:
            rc = L2.run(W, e, **ov[k])
            cand[k][e] = {**_acct(rc), "years": rc.get("years")}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": old_core(W, uni, False, False), **{k: old_core(W, uni, *USE[k]) for k in IDS}}
    s1 = {}
    for k in IDS:
        unseen = None if old["B1"]["calmar"] is None or old[k]["calmar"] is None else old[k]["calmar"] - old["B1"]["calmar"]
        s1[k] = R6.stage1(cand[k], base, posthoc=unseen)
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"loop": 6, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "scale": scale(W, M), "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    L = [f"# 第六个研究循环（核心层）第 1 轮：美股熊市里、股债负相关时才拿国债 BCU / BCJ / BCB（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop6_r01_bondcorr.py 开头）", ""]
    for k in IDS:
        s = res["stage1"][k]
        pv = s["posthoc"]
        L.append(f"- **{k}：{'第一关全过 → 另行登记第二关（债券收益循环平移、相关条件重算）' if s['ok'] else R6.FAIL1}**"
                 f"（S1 合计 {_f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
                 f"S4（{_f(s['h1'], '{:+.3f}')} / {_f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
                 f"S7（1987〜2000 只有核心 {_f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）")
    L += ["", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | " + " | ".join(f"{k}（Calmar 差）" for k in IDS) + " |", "|---|---|" + "---|" * len(IDS)]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{_f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS) + " |")
    L += ["", "规模（不参与判定；只数日子）："]
    for e in L2.ERAS:
        x = res["scale"][e]
        L.append(f"- {e}：美股熊 {_f(x['ust']['bear_pct'], '{:.1f}')}% 的日子；其中 1482 条件成立 {_f(x['ust']['on_in_bear_pct'], '{:.1f}')}%（{x['ust']['segments']} 段，"
                 f"整年不成立 {x['ust']['off_years'] or '—'}）、2561 条件成立 {_f(x['jgb']['on_in_bear_pct'], '{:.1f}')}%（{x['jgb']['segments']} 段，"
                 f"整年不成立 {x['jgb']['off_years'] or '—'}）")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {_f(o[k]['calmar'])}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%、拿债券 {_f(o[k].get('bond_days_pct'), '{:.1f}')}% 的日子）"
        for k in ("B1",) + IDS))
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
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R6.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L2.load()
    M = inputs(W)
    print(json.dumps({"scale": scale(W, M)}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 条件全为 False → 与 B1 逐项相同；② 条件全为 True → 与第三个循环 BAJ / BAU / BAB 已公开的 J 账户相同（同一条代码路径）。"""
    from qbreak import paths
    W = L2.load()
    M = inputs(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    never_b, never_j = pd.Series(False, index=M["bc"].index), pd.Series(False, index=M["jc"].index)
    always_b, always_j = pd.Series(True, index=M["bc"].index), pd.Series(True, index=M["jc"].index)
    rb = L2.run(W, "J")
    ov0 = overs(W["bear"]["US"], M["fb"], M["fj"], never_b, never_j)
    ov1 = overs(W["bear"]["US"], M["fb"], M["fj"], always_b, always_j)
    same0 = {k: all(rb.get(x) == L2.run(W, "J", **ov0[k]).get(x) for x in keys) for k in IDS}
    ref = json.loads((paths.out_dir() / REF3).read_text(encoding="utf-8"))["cand"]
    same1 = {}
    for k in IDS:
        r1 = L2.run(W, "J", **ov1[k])
        rr = ref[SAME3[k]]["J"]
        same1[k] = all(r1.get(x) is not None and rr.get(x) is not None and abs(r1[x] - rr[x]) <= 1e-9 for x in ("calmar", "cagr", "dd"))
    print(json.dumps({"never_same_as_b1": same0, "always_same_as_loop3": same1}, ensure_ascii=False))
    return 0 if all(same0.values()) and all(same1.values()) else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次；kind = asset） ─────────────────────────
_G: dict = {}


def shifted_inputs(M: dict, k: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """两只债券的东证收盘在 2000-01-04〜J 的最后一天上用同一个 k 平移日收益（参考日 = 最后一天的水平不变），相关条件用平移后的价格重算。"""
    import equity_idle_study as EI
    idx = R6.shift_window(M["bc"]).index.intersection(R6.shift_window(M["jc"]).index)
    bc, jc = R6.asset_shift(M["bc"].reindex(idx), k), R6.asset_shift(M["jc"].reindex(idx), k)
    on_b, on_j = masks(M["spx"], bc, jc)
    return EI.frame_close(bc), EI.frame_close(jc), on_b, on_j


def _placebo_one(seed: int):
    W, M, k, base, ks = _G["W"], _G["M"], _G["k"], _G["base"], _G["ks"]
    try:
        fb, fj, on_b, on_j = shifted_inputs(M, ks[int(seed)])
        kw = overs(W["bear"]["US"], fb, fj, on_b, on_j)[k]
        tot = 0.0
        for e in L2.ERAS:
            c = L2.run(W, e, **kw)["calmar"]
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
    W = L2.load()
    M = inputs(W)
    base = {e: L2.run(W, e)["calmar"] for e in L2.ERAS}
    ov = overs(W["bear"]["US"], M["fb"], M["fj"], M["on_b"], M["on_j"])[k]
    cand = {e: L2.run(W, e, **ov)["calmar"] for e in L2.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L2.ERAS), 6)
    n = len(R6.shift_window(M["bc"]).index.intersection(R6.shift_window(M["jc"]).index))
    ks = R6.shift_ks(n, 1)
    _G.update({"W": W, "M": M, "k": k, "base": base, "ks": ks})
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
    res = {"loop": 6, "round": ROUND, "id": k, "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "stage1_stat": s1["sum"],
           "n": n, "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第六个研究循环第 1 轮 第二关：{k} vs 400 次债券收益循环平移（相关条件重算）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B1 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第六个研究循环第 1 轮：BCU / BCJ / BCB（美股熊市里股债负相关时才拿国债）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的结果）")
    g.add_argument("--stage2", choices=IDS, help="第二关（第一关全过才做）")
    ap.add_argument("--workers", type=int, default=4)
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
