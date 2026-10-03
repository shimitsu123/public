"""loop6_r03_earlyreturn.py — 第六个研究循环第二段（基准 B2 = 采用后的模拟盘 B1 + BCU）第 3 轮：「纳指先转牛就早一点拿回核心」接到 B2 上 NDB
（2026-10-03 登记；先提交后只运行一次；家族「核心·择时（早回来）」第二段 1 / 3；kind = signal；事后 → S7 适用）。

用户（2026-10-03）：「采用\\n\\n并且继续第六个研究循环」。循环的规则：scripts/research_loop6.py（第二段 = 开头七与末尾一节）；基准 B2：scripts/loop6_common.py。
为什么做这个（照实写）：
  - 研究成功率统计（var/out/research_success_map.md）：「核心·择时（早回来）」3 个做法里第一关全过 2 个（NDRH、NVU）；第二段「熊市避险资产」家族已用完 3 / 3。
  - 第二个循环第 8 轮 NDRH（第一个循环 NDR 原样 + FJE，接在 B1 上）第一关全过 +0.246（Z +0.078、E +0.076、J +0.092；三个年代都正；S7 +0.026），
    第二关（「早回来」标记在 S&P 熊的日子串里循环平移）约第 91 百分位、不过。
  - B2 = B1 + BCU：S&P 熊的日子里 B2 不再全是现金 —— 股债 63 天负相关时拿 1482。早回来的那几段（2003-04、2009-06〜07、2012-01、2019-03、2020-04〜06、
    2023-03〜04、2025-05）里 B2 有一部分拿着 1482 → 早回来换掉的是「1482 或现金」，不再只是现金；所以 NDRH 的结论不能直接搬到 B2 上，要重新比。
  → 看过 NDR / NDRH 的结果之后、接到采用后的 B2 上 = 事后组合（S7 适用：没看过的 1987〜2000 只有核心，候选 − B2 > 0）。
做法 NDB（NDR 的规则与参数一字不改 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 纳指熊 = 现行牛熊检测器用在 ^NDX（美元）上（loop_r08_ndxreentry.ndx_bear，与美股牛熊分界同一个检测器与参数）。
  - 东证交易日 d 上：S&P 熊 / 纳指熊 = d 之前（含 d 的日期）最近一个美国收盘的状态（引擎读 B2 的「美股熊」同一个对齐：美国 d 日收盘 → 东证 d+1 开盘成交）。
    一段 S&P 熊市（东证日上连续是熊）里纳指出现过熊、当天是牛 →「早回来」（loop_r08_ndxreentry.reentry 原样）。
    登记前核对过：这样在东证日上算的早回来，与在美国交易日上算（NDRH）再映射到东证日，1986-01〜2026-10 的 10,006 个东证交易日逐日相同。
  - 核心用的「熊」= S&P 熊 且 不是早回来。B2 的三个核心键都用它代替「美股熊」：US_UH / US_HG（FJE 照旧决定 1545 / 2845）与 1482 的键
    （1482 只在「核心用的熊 ∧ 股债 63 天负相关」时拿 → 早回来的日子不拿 1482、拿核心）。接法 = B2 同一对函数
    （loop_r04_yensurge.fxh_over + loop2_r02_bondrefuge.tbh_over，按键合并）。个股层、判断层、费用全部同 B2。
第一关：research_loop6.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 NDB − B2 的 Calmar 差；只有核心的口径同第 2 轮 old_core
  （use = None：B2 本身），只把「核心用的熊」换成美国日期上的 S&P 熊 且 不是早回来；前一天的状态决定当天、换仓扣 0.1% × 换的比例）。
第二关（第一关全过才做；另行登记后只运行一次；代码写在本脚本 --stage2）：kind = signal —— 候选自己新加的信号 =「纳指熊」（东证日上的布尔序列）在
  2000-01-04〜2026-09-30 的东证交易日上整体循环平移 k（research_loop6.shift_ks(n, 0)：种子 [20261006, 0, s]），窗外不动；早回来与核心用的熊用平移后的
  纳指熊重算；B2（S&P 熊、FJE、BCU 的相关条件、1482 价格）不动。候选的 Calmar 差合计要严格大于 400 次的最大值（有算不出的 = 不过）。
接线核对（登记前，不看候选的结果）：① 纳指永远是熊（永远没有早回来）→ 三个年代与 B2 逐项相同；② 1482 永远不可拿 → J 与第二个循环第 8 轮 NDRH
  已公开的 J 账户（Calmar / 年化 / 回撤）相同（= B1 + 早回来，同一条代码路径）；③ 本脚本的 old_core 用 B2 自己的熊 = 第 2 轮记录的 B2 只有核心 Calmar。
只描述（不参与判定）：各年代早回来的天数与段、其中 B2 原本拿 1482 / 现金的天数、对冲中的比例；核心换仓笔数；1987〜2000 早回来的段；每年收益差；
  纳指熊在 2000〜2026 全部东证日里的比例；最新一天的状态。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop6_r03_earlyreturn.py（第一关）；--scale（只数日子）；--wiring（登记前的接线核对）；--stage2 NDB [--workers N]（第二关）。
输出 var/out/loop6_r03_earlyreturn.md / .json（第二关 loop6_r03_earlyreturn_stage2_NDB.md / .json）。非投资建议。
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
import loop2_r04_bondunion as T4                                             # noqa: E402
import loop6_common as L6                                                    # noqa: E402
import loop6_r01_bondcorr as T                                               # noqa: E402
import loop_r08_ndxreentry as N8                                             # noqa: E402
import research_loop6 as R6                                                  # noqa: E402

ROUND = 3
IDS = ("NDB",)
FAMILY = {"NDB": "核心·择时（早回来）"}
KIND = {"NDB": "signal"}
POSTHOC = True
OLD = T.OLD
REF8 = "loop2_r08_ndrhedged.json"                                            # 接线核对 ②：第二个循环第 8 轮 NDRH 已公开的账户
REF2 = "loop6_r02_bondgate.json"                                             # 接线核对 ③：第 2 轮记录的 B2 只有核心
OUT = "loop6_r03_earlyreturn"


# ───────────────────────── 规则（纯函数，tests/test_loop6_r03.py） ─────────────────────────
def on_idx(s: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    """布尔序列 → idx 上（d 日 = d 之前（含 d 的日期）最近一个值；没有值 = False）。引擎读「熊」的键同一个对齐。"""
    idx = pd.DatetimeIndex(idx)
    return s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx).fillna(0.0) > 0.5


def early(spx_t: pd.Series, ndx_t: pd.Series) -> pd.Series:
    """早回来（同一个日期轴上）：S&P 熊的这一段里（含当天）纳指出现过熊、当天纳指是牛（NDR 原样）。"""
    return N8.reentry(spx_t.astype(bool), ndx_t.astype(bool))


def core_bear(spx_t: pd.Series, ndx_t: pd.Series) -> pd.Series:
    """核心用的「熊」= S&P 熊 且 不是早回来。"""
    return pd.Series(spx_t.astype(bool).to_numpy() & ~early(spx_t, ndx_t).to_numpy(bool), index=spx_t.index)


def over(W: dict, cb: pd.Series, uni: pd.Series, hf: pd.DataFrame, on_b: pd.Series, fb: pd.DataFrame) -> dict:
    """B2 同一对接法，只把「美股熊」换成 cb：FJE（fxh_over：对冲中 → 2845，否则 1545）+ BCU（tbh_over：cb ∧ 负相关 → 1482）。"""
    import loop_r04_yensurge as Y
    return L6.merge_over(Y.fxh_over(W, cb, uni, hf), T2.tbh_over(cb, on_b, fb))


def shifted_ndx(ndx_t: pd.Series, k: int | None) -> pd.Series:
    """第二关：纳指熊在 2000-01-04〜J 的最后一天上整体循环平移 k（None = 不平移），窗外不动。"""
    s = ndx_t.astype(bool).copy()
    if k is not None:
        w = R6.shift_window(s)
        s.loc[w.index] = R6.shift_signal(w, k).to_numpy(bool)
    return s


def placebo_ks(n: int) -> list[int]:
    """每个种子的平移量（signal：shift_ks(n, 0)）。"""
    return R6.shift_ks(n, 0)


def split_days(re: pd.Series, spx_t: pd.Series, on_b: pd.Series, uni: pd.Series, days: pd.DatetimeIndex) -> dict:
    """这段日子里：早回来的天数、其中 B2 原本拿 1482（S&P 熊 ∧ 负相关）/ 现金的天数、对冲中的比例、段（只数日子）。"""
    days = pd.DatetimeIndex(days)
    r = on_idx(re, days)
    b2_bond = on_idx(spx_t, days) & on_idx(on_b, days)
    h = on_idx(uni, days)
    seg = N8.segments(r, str(days[0].date()), str(days[-1].date())) if len(days) else []
    return {"early_days": int(r.sum()), "b2_bond_days": int((r & b2_bond).sum()), "b2_cash_days": int((r & ~b2_bond).sum()),
            "hedged_pct": round(float(h[r].mean() * 100), 1) if r.any() else None, "segments": [list(x) for x in seg]}


# ───────────────────────── 1987〜2000 只有核心（S7） ─────────────────────────
def old_core(W: dict, uni: pd.Series, bear: pd.Series) -> dict:
    """第 2 轮 old_core（use = None：B2 本身）同一个口径；bear = 核心用的熊（B2 = 美股熊；NDB = 美国日期上的 S&P 熊 且 不是早回来）。"""
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
    spx = inp["spx"]["Close"].astype(float)
    full = unh.index[unh.index >= pd.Timestamp(T2.BOND_START)]
    ffull = lambda s: s.astype(float).reindex(full.union(s.index)).ffill().reindex(full)      # noqa: E731
    on_u = T.corr_on(ffull(spx), ffull(bnd)).shift(1, fill_value=False)
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    unh, hed, b_px = unh.reindex(idx), ff(hed), ff(bnd)
    b = ff(bear).fillna(0.0) > 0.5
    hdg = ff(uni).fillna(0.0) > 0.5
    off = pd.Series(False, index=idx)
    ou = ff(on_u).fillna(0.0) > 0.5
    w = T4.union_weights(b, hdg, ou, off).shift(1).fillna(0.0)
    ret = (w["u"] * unh.pct_change().fillna(0.0) + w["h"] * hed.pct_change().fillna(0.0) + w["b"] * b_px.pct_change().fillna(0.0))
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["bond_days_pct"] = round(float((w["b"] > 0).mean() * 100), 1)
    out["core_days_pct"] = round(float(((w["u"] + w["h"]) > 0).mean() * 100), 1)
    return out


# ───────────────────────── 输入 / 规模 ─────────────────────────
def inputs(W: dict) -> dict:
    """B2 的输入（W["bcu"]：1482 合成价、相关条件）+ FJE 的「对冲中」+ 东证日上的 S&P 熊 / 纳指熊 / 早回来 / 核心用的熊。"""
    import loop2_common as L2
    import loop_r04_yensurge as Y
    M = dict(W["bcu"])
    days = M["on_b"].index
    _, _, uni = L2.fje_states(W)
    ndx_us = N8.ndx_bear(W["inp"])
    M.update({"days": days, "uni": uni, "hf": Y.hedged_frame(W["inp"]), "ndx_us": ndx_us,
              "spx_t": on_idx(W["bear"]["US"], days), "ndx_t": on_idx(ndx_us, days)})
    M["early"] = early(M["spx_t"], M["ndx_t"])
    M["cb"] = core_bear(M["spx_t"], M["ndx_t"])
    return M


def era_days(W: dict, e: str) -> pd.DatetimeIndex:
    a, b = W["ctx"][e]["windows"][e]
    d = pd.DatetimeIndex(W["ctx"][e]["days"])
    return d[(d >= pd.Timestamp(a)) & ((d < pd.Timestamp(b)) if b else True)]


def scale(W: dict, M: dict) -> dict:
    out = {e: split_days(M["early"], M["spx_t"], M["on_b"], M["uni"], era_days(W, e)) for e in L6.ERAS}
    w = R6.shift_window(M["ndx_t"])
    out["ndx_bear_share_2000_2026"] = round(float(w.mean() * 100), 1)
    out["spx_bear_share_2000_2026"] = round(float(R6.shift_window(M["spx_t"]).mean() * 100), 1)
    out["shift_n"] = len(w)
    re_us = N8.reentry(W["bear"]["US"], M["ndx_us"])
    out["old_segments"] = [list(x) for x in N8.segments(re_us, *OLD)]
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "spx_bear": bool(M["spx_t"].iloc[-1]), "ndx_bear": bool(M["ndx_t"].iloc[-1]),
                     "early": bool(M["early"].iloc[-1])}
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
    W = L6.load()
    M = inputs(W)
    ov = over(W, M["cb"], M["uni"], M["hf"], M["on_b"], M["fb"])
    reg = R6.segment(R6.load_state()).get("baseline") or {}
    base, cand, trades = {}, {"NDB": {}}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand["NDB"][e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B2": nb, "NDB": nc}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B2": old_core(W, M["uni"], W["bear"]["US"]), "NDB": old_core(W, M["uni"], N8.nr_key(W["bear"]["US"], M["ndx_us"]))}
    unseen = None if old["B2"]["calmar"] is None or old["NDB"]["calmar"] is None else old["NDB"]["calmar"] - old["B2"]["calmar"]
    s1 = {"NDB": R6.stage1(cand["NDB"], base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L6.ERAS}
    res = {"loop": 6, "segment": 2, "round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "drift": drift, "scale": scale(W, M), "core_trades": trades, "old": old,
           "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s = res["stage1"]["NDB"]
    pv = s["posthoc"]
    L = [f"# 第六个研究循环第二段第 3 轮：纳指先转牛就早一点拿回核心（接到 B2 上）NDB（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop6_r03_earlyreturn.py 开头；基准 B2 = B1 + BCU）", "",
         f"- **NDB：{'第一关全过 → 另行登记第二关（纳指熊循环平移）' if s['ok'] else R6.FAIL1}**"
         f"（S1 合计 {_f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
         f"S4（{_f(s['h1'], '{:+.3f}')} / {_f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {_f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）",
         "", "| 年代 | B2 年化 / 最大回撤 / Calmar（前半 / 后半） | NDB（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['NDB'][e])}（{_f(s['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定；规模只数日子）："]
    sc = res["scale"]
    for e in L6.ERAS:
        x = sc[e]
        sg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in x["segments"]) or "无"
        L.append(f"- {e}：早回来 {x['early_days']} 天（B2 原本拿 1482 {x['b2_bond_days']} 天、现金 {x['b2_cash_days']} 天；"
                 f"对冲中 {_f(x['hedged_pct'], '{:.1f}')}%；{sg}）；核心换仓 B2 {res['core_trades'][e]['B2']} → NDB {res['core_trades'][e]['NDB']} 笔")
    L.append(f"- 纳指熊在 2000〜2026 全部东证日里的比例 {sc['ndx_bear_share_2000_2026']}%（S&P 熊 {sc['spx_bear_share_2000_2026']}%）；"
             f"最新一天 {sc['latest']['date']}：S&P {'熊' if sc['latest']['spx_bear'] else '牛'}、纳指 {'熊' if sc['latest']['ndx_bear'] else '牛'}、"
             f"早回来 {'是' if sc['latest']['early'] else '否'}")
    o = res["old"]
    osg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in sc["old_segments"]) or "无"
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {_f(o[k]['calmar'])}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%、"
        f"拿核心 {_f(o[k].get('core_days_pct'), '{:.1f}')}%、拿债券 {_f(o[k].get('bond_days_pct'), '{:.1f}')}% 的日子）" for k in ("B2", "NDB"))
        + f"；早回来 {osg}")
    for e in L6.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["NDB"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（NDB − B2，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B2 与第二段登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L6.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R6.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B2）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L6.load()
    M = inputs(W)
    print(json.dumps({"scale": scale(W, M)}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用：① 纳指永远是熊 → 三个年代与 B2 逐项相同；② 1482 永远不可拿 → J 与 NDRH 已公开的 J 账户相同；
    ③ old_core(B2 自己的熊) = 第 2 轮记录的 B2 只有核心 Calmar。"""
    from qbreak import paths
    W = L6.load()
    M = inputs(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    never = core_bear(M["spx_t"], pd.Series(True, index=M["days"]))
    ov1 = over(W, never, M["uni"], M["hf"], M["on_b"], M["fb"])
    same_b2 = {}
    for e in L6.ERAS:
        rb, r1 = L6.run(W, e), L6.run(W, e, **ov1)
        same_b2[e] = bool(all(rb.get(x) == r1.get(x) for x in keys))
    off = pd.Series(False, index=M["on_b"].index)
    r0 = L6.run(W, "J", **over(W, M["cb"], M["uni"], M["hf"], off, M["fb"]))
    ref = json.loads((paths.out_dir() / REF8).read_text(encoding="utf-8"))["cand"]["NDRH"]["J"]
    same_ndrh = all(r0.get(x) is not None and ref.get(x) is not None and abs(r0[x] - ref[x]) <= 1e-9 for x in ("calmar", "cagr", "dd"))
    oc = old_core(W, M["uni"], W["bear"]["US"])["calmar"]
    ref2 = json.loads((paths.out_dir() / REF2).read_text(encoding="utf-8"))["old"]["B2"]["calmar"]
    out = {"never_early_same_as_b2": same_b2, "no_bond_same_as_ndrh_J": bool(same_ndrh), "old_core_b2_same": bool(oc == ref2),
           "ndrh_J": {x: ref.get(x) for x in ("calmar", "cagr", "dd")}, "run_J": {x: r0.get(x) for x in ("calmar", "cagr", "dd")}}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if all(same_b2.values()) and same_ndrh and out["old_core_b2_same"] else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次；signal = 纳指熊循环平移） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        cb = core_bear(M["spx_t"], shifted_ndx(M["ndx_t"], ks[int(seed)]))
        kw = over(W, cb, M["uni"], M["hf"], M["on_b"], M["fb"])
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
    W = L6.load()
    M = inputs(W)
    base = {e: L6.run(W, e)["calmar"] for e in L6.ERAS}
    ov = over(W, M["cb"], M["uni"], M["hf"], M["on_b"], M["fb"])
    cand = {e: L6.run(W, e, **ov)["calmar"] for e in L6.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L6.ERAS), 6)
    n = len(R6.shift_window(M["ndx_t"]))
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
    res = {"loop": 6, "segment": 2, "round": ROUND, "id": k, "kind": KIND[k], "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat,
           "stage1_stat": s1["sum"], "n": n, "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第六个研究循环第二段第 3 轮 第二关：{k} vs 400 次纳指熊循环平移（{KIND[k]}；B2 不动）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B2 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第六个研究循环第二段第 3 轮：NDB（纳指先转牛就早一点拿回核心，接到 B2 上）")
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
