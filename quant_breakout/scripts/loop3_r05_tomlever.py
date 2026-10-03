"""loop3_r05_tomlever.py — 第三个研究循环第 5 轮：「美股牛市里的月末月初（turn of month）把一半核心换成 2 倍纳指」TOML
（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 7 / 20）。

循环的规则：scripts/research_loop3.py（第二关按类别；本轮 kind = "signal"）；基准 B1：scripts/loop2_common.py；
2 倍纳指的接法：第一个循环第 3 轮 scripts/loop_r03_calmlever.py（LV25）的 2869 合成价与费用（equity_idle_study 的 lev：每日重置
2 × (纳指总收益 − 美国 3 个月国库券) + 日本拆借 − 0.825%、不乘汇率；qbreak/fees.py 已有 2869.T：0.05%、1 口）。
为什么做这个（照实写）：
  - 月末月初效应（最后 1 个 + 下月前 3 个美国交易日；Ariel 1987、Lakonishok & Smidt 1988、McConnell & Xu 2008：1926〜2005 美国与 35 个国家里
    股票的超额收益几乎都集中在这 4 天）是有据可查、跨年代 / 跨国家最稳的日历效应之一；文献也报告 2000 年以后变弱。
  - 本项目试过：第二个循环 TOMB（美股熊市里只在月末月初拿核心 → 第一关不过、2002 / 2008 熊市里的窗口大跌）、FMB（熊市里只在 FOMC 那天拿）、
    第一个循环 LV25（平静的牛市里 25% 2 倍纳指 → 第一关不过，Z −0.062）。本轮是没试过的组合：**牛市里**（B1 本来就满仓纳指）只在这 4 天
    把一半核心换成 2 倍纳指（有效 1.5 倍）。看过 TOMB / FMB / LV25 的结果之后设计 → 事后，S7 适用。
  - 选题来自本会话另一个只读检查（它估约 3%；风险：费用约每年 1〜1.6% 的换仓、2025-04-03 纳指 −5.4% 正好在窗口里，J 回撤可能深约 1.8 pp）。
    同一个检查提的 ENS（美股分界改成 9 组参数多数决）登记前的规模核对：多数决与 B1 的分界在 Z / J / 1987〜2000 完全相同、E 只差 7 天 →
    账户必然≈ B1 → 不拿它占做法（没登记、不算做法）。
  - 家族「核心·日历杠杆」1 / 3（新家族）。ID 是新的（第一 / 第二个循环没用过）。
做法 TOML（月末月初的定义是固定的日历规则、不学参数 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 月末月初日 = 美国交易日（纳指总收益序列的日期）里每月最后一个 + 下月前 3 个。拿 2869 的决定 = 美国 d 日收盘时「下一个美国交易日是月末月初日」
    → 日本 d+1 开盘成交（同 B1 的时点）→ 拿着的期间正好吃到那 4 个美国交易日的收益（日历事先知道，不算偷看）。
  - 核心（引擎 core_mode = "follow"，三只权重都是 1.0）：2869 的「熊」= 美股熊 或 不在拿的日子；1545 / 2845 的「熊」同 B1（FJE）→
    美股牛且在拿的日子：B1 那只（1545 或 2845）与 2869 各一半；其余同 B1（美股熊 → 现金）。
第一关：research_loop3.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 TOML − B1 的 Calmar 差；口径 = 第二个循环第 8 轮
  loop2_r08_ndrhedged.old_core（日元计纳指 / 对冲版、前一天收盘的状态决定当天、换掉的比例 × 0.1%），在拿的日子 B1 那只与 2869 合成价（同上）各一半）。
第二关（第一关全过的才做；另行登记后只运行一次）：kind = "signal"，形状预定 =「在拿的日子」标记在 2000-01-03〜2026-09-30 里 B1 分界是牛的
  美国交易日串上整体循环平移 k（k ∈ [250, N − 250]，research_loop3.shift_ks 同一组种子；天数与每段长短不变），细节在那时写定。
接线核对（登记前，不看 TOML 的收益）：① 「在拿的日子」全程 = False → J 的账户与 B1 逐项相同；② TOML 在 J 里 2869 的买卖笔数 > 0（只数笔数）。
规模核对（登记前，只看日历与 B1 的状态）：见 sim_changes 的登记一节（--scale）。
只描述（不参与判定）：各年代在拿的日子数与占牛市的比例、核心换仓笔数、每年收益差；1987〜2000 的两个数。
事前预期（照实写）：月末月初效应 2000 年以后变弱、换仓费用每年约 1%；1.5 倍时窗口里的急跌（2000-04-03、2025-04-03 等）会让回撤更深
  → 第一关约 15%（S3 / S7 是难点）；第二关约 20%（平移后的窗口落在别的日子，效应没了；但也会有几次碰上大涨日）。
运行：python scripts/loop3_r05_tomlever.py（第一关）；--scale；--wiring。输出 var/out/loop3_r05_tomlever.md / .json。非投资建议。
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
import loop2_r08_ndrhedged as R8                                             # noqa: E402
import loop_r08_ndxreentry as N8                                             # noqa: E402
import research_loop3 as R3                                                  # noqa: E402

ROUND = 5
IDS = ("TOML",)
FAMILY = "核心·日历杠杆"
POSTHOC = True
KIND = "signal"
LEV_T, LV_KEY = "2869.T", "US_LV"
TOM_LAST, TOM_FIRST = 1, 3                                                   # 每月最后 1 个 + 下月前 3 个美国交易日
OLD = R8.OLD
OUT = "loop3_r05_tomlever"


# ───────────────────────── 日历与接法（纯函数，tests/test_loop3_r05.py） ─────────────────────────
def tom_days(us_days) -> pd.DatetimeIndex:
    """月末月初日：每个月最后 TOM_LAST 个 + 每个月前 TOM_FIRST 个美国交易日（只用日历）。"""
    d = pd.DatetimeIndex(us_days).sort_values().unique()
    s = pd.Series(np.arange(len(d)), index=d)
    g = s.groupby(d.to_period("M"))
    first = g.head(TOM_FIRST).index
    last = g.tail(TOM_LAST).index
    return pd.DatetimeIndex(first.union(last))


def hold_state(us_days) -> pd.Series:
    """美国 d 日收盘时的决定：下一个美国交易日是月末月初日 → True（日本 d+1 开盘拿进 2869，吃到那天的美国收益）。最后一天没有下一天 → False。"""
    d = pd.DatetimeIndex(us_days).sort_values().unique()
    t = d.isin(tom_days(d))
    nxt = np.zeros(len(d), bool)
    nxt[:-1] = t[1:]
    return pd.Series(nxt, index=d)


def toml_over(W: dict, bear_us: pd.Series, hold: pd.Series) -> dict:
    """B1 的接法（fxh_over）加第三只核心 2869：它的「熊」= 美股熊 或 不在拿的日子；follow 模式下与 B1 那只各一半。"""
    import loop_r04_yensurge as Y
    xc = {**W["b1"]["extra_core"], LEV_T: W["assets"][LEV_T]}
    return {"cfg_over": {"core": {"1545.T": 1.0, Y.HEDGE_T: 1.0, LEV_T: 1.0},
                         "core_index": {"1545.T": Y.UH_KEY, Y.HEDGE_T: Y.HG_KEY, LEV_T: LV_KEY}, "core_mode": "follow"},
            "extra_core": xc, "extra_bear": {LV_KEY: Y.or_series(bear_us, ~hold.astype(bool))}}


def lev_index(inp: dict) -> pd.Series:
    """2869 的合成价（美国日期；equity_idle_study 的 lev 原样，不乘汇率）。"""
    import equity_idle_study as EI
    return EI.lev(EI.ndx_tr(inp), 2.0, inp["dtb3"], inp["cjp"], EI.FEE[LEV_T])


def old_core(W: dict, uni: pd.Series, bear: pd.Series, hold: pd.Series | None) -> dict:
    """只描述 + S7：1987〜2000 只有核心（第二个循环第 8 轮 old_core 同一个口径）；hold = None → B1；在拿的日子 B1 那只与 2869 各一半。"""
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
    lv = lev_index(inp)
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    ru = unh.reindex(idx).pct_change().fillna(0.0).to_numpy()
    rh = ff(hed).pct_change().fillna(0.0).to_numpy()
    rl = ff(lv).pct_change().fillna(0.0).to_numpy()
    b = (ff(bear).fillna(0.0) > 0.5).to_numpy()
    hdg = (ff(uni).fillna(0.0) > 0.5).to_numpy()
    hl = np.zeros(len(idx), bool) if hold is None else (ff(hold).fillna(0.0) > 0.5).to_numpy()
    n = len(idx)
    eq = np.ones(n)
    w0 = np.zeros(3)
    for t in range(1, n):
        w = np.zeros(3)
        if not b[t - 1]:
            w[1 if hdg[t - 1] else 0] = 1.0
            if hl[t - 1]:
                w[:2] *= 0.5
                w[2] = 0.5
        turn = float(np.abs(w - w0).sum())
        eq[t] = eq[t - 1] * (1 + w[0] * ru[t] + w[1] * rh[t] + w[2] * rl[t] - turn * HW.SWITCH_COST / 100)
        w0 = w
    return EI.curve_stats(pd.Series(eq, index=idx))


# ───────────────────────── 只描述 ─────────────────────────
def held_days(W: dict, e: str, bear: pd.Series, hold: pd.Series) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    m = (hold.index >= pd.Timestamp(a)) & ((hold.index < pd.Timestamp(b)) if b else (hold.index <= pd.Timestamp(L2.J_END)))
    h = hold[m].astype(bool)
    bb = bear.astype(float).reindex(h.index.union(bear.index)).ffill().reindex(h.index).fillna(0.0) > 0.5
    on = h & ~bb
    nb = int((~bb).sum())
    return {"hold_days": int(on.sum()), "bull_days": nb, "pct_of_bull": round(float(on.sum()) / nb * 100, 1) if nb else None}


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop3_r05_tomlever.py", "scripts/loop2_r08_ndrhedged.py",
                                 "scripts/loop2_common.py", "scripts/loop_r04_yensurge.py", "scripts/equity_idle_study.py",
                                 "scripts/research_loop3.py", "scripts/candle_portfolio.py", "qbreak/fees.py",
                                 "scripts/loop2_r02_bondrefuge.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def inputs(W: dict):
    import equity_idle_study as EI
    _, _, uni = L2.fje_states(W)
    hold = hold_state(EI.ndx_tr(W["inp"]).dropna().index)
    return uni, hold


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    uni, hold = inputs(W)
    ov = toml_over(W, W["bear"]["US"], hold)
    reg = R3.load_state().get("baseline") or {}
    base, cand, ctr, desc = {}, {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        ctr[e] = {"B1": T2.core_trades(e, W)}
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        ctr[e]["TOML"] = T2.core_trades(e, W)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = held_days(W, e, W["bear"]["US"], hold)
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": old_core(W, uni, W["bear"]["US"], None), "TOML": old_core(W, uni, W["bear"]["US"], hold)}
    unseen = None if old["B1"]["calmar"] is None or old["TOML"]["calmar"] is None else old["TOML"]["calmar"] - old["B1"]["calmar"]
    s1 = {"TOML": R3.stage1(cand, base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "kind": KIND, "code": code, "dirty": dirty, "base": base,
           "cand": {"TOML": cand}, "stage1": s1, "drift": drift, "core_trades": ctr, "describe": desc, "old": old,
           "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["TOML"]
    ph = s1["posthoc"]
    L = [f"# 第三个研究循环第 5 轮：美股牛市里的月末月初把一半核心换成 2 倍纳指 TOML（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop3_r05_tomlever.py 开头）", "",
         f"- **TOML：{'第一关全过 → 另行登记第二关（在拿的日子标记在牛市的日子上循环平移）' if s1['ok'] else R3.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | TOML（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['TOML'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    ct = res["core_trades"]
    L += ["", "接线核对（不参与判定）：2869 买卖笔数 " + "、".join(f"{e} {ct[e]['TOML'].get(LEV_T, 0)}" for e in L2.ERAS)
          + "；核心换仓合计 " + "、".join(f"{e} {sum(ct[e]['B1'].values())} → {sum(ct[e]['TOML'].values())}" for e in L2.ERAS), "", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        L.append(f"- {e}：在拿 2869 的决定日 {d['hold_days']} 天（牛市日子的 {_f(d['pct_of_bull'], '{:.1f}')}%）")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["TOML"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（TOML − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心 + FJE）：B1 {oc(o['B1'])}；TOML {oc(o['TOML'])}")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R3.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    """登记前用：只数日历与 B1 的状态（在拿的决定日数与占牛市的比例；不跑 TOML、不看收益）。"""
    W = L2.load()
    _, hold = inputs(W)
    out = {e: held_days(W, e, W["bear"]["US"], hold) for e in L2.ERAS}
    m = (hold.index >= pd.Timestamp(OLD[0])) & (hold.index <= pd.Timestamp(OLD[1]))
    out["1987-2000"] = {"hold_days": int(hold[m].sum())}
    print(json.dumps(out, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用（J）：① 在拿的日子全程 = False → 账户与 B1 逐项相同；② TOML 的 2869 买卖笔数 > 0（只数笔数，不看收益）。"""
    W = L2.load()
    _, hold = inputs(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    rb = L2.run(W, "J")
    rn = L2.run(W, "J", **toml_over(W, W["bear"]["US"], pd.Series(False, index=hold.index)))
    same = all(rb.get(x) == rn.get(x) for x in keys)
    L2.run(W, "J", **toml_over(W, W["bear"]["US"], hold))
    n_lev = int(T2.core_trades("J", W).get(LEV_T, 0))
    print(json.dumps({"never_same_as_b1": same, "toml_2869_trades_J": n_lev}, ensure_ascii=False))
    return 0 if same and n_lev > 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第三个研究循环第 5 轮：TOML（牛市里的月末月初一半核心换成 2 倍纳指）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日历与 B1 的状态（不跑 TOML）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看 TOML 的收益）")
    a = ap.parse_args(argv)
    return scale_only() if a.scale else wiring() if a.wiring else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
