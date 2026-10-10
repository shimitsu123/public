"""loop6_r04_fastexit.py — 第六个研究循环第二段（基准 B2 = 采用后的模拟盘 B1 + BCU）第 4 轮：「核心的快速离场」ZBX
（2026-10-03 登记；先提交后只运行一次；家族「核心·择时（早离场）」第二段 1 / 3（新家族）；kind = signal；事后 → S7 适用）。

用户（2026-10-03）：「采用\\n\\n并且继续第六个研究循环」。循环的规则：scripts/research_loop6.py（第二段 = 开头七与末尾一节）；基准 B2：scripts/loop6_common.py。
为什么做这个（照实写）：
  - 只看 B2 的诊断（2026-10-03，本会话；不跑任何候选）：三个年代最深的几次回撤几乎全部来自核心，而且都在美股牛熊分界（250 日线 ±3%、连续 5 天）
    翻熊之前 —— J 2020-02-21〜03-13 −26.96%（全部是核心）、J 2025-01-24〜04-09 −23.75%、J 2022-01-04〜03-09 −19.34%（全部是核心）、
    E 2007-11〜2008-06 −15.88%（全部是核心）、Z 2004 / 2005 的纳指回调（全部是核心）。分界为了少误报，要等跌到线下 3%、连续 5 天才翻熊。
  - 选题时用过一个只读的子任务（独立扫描；只算状态序列与已存的第二关随机分布，没有算任何候选的账户），它推荐「警戒区提前换 1482」（ZBC：
    相关 ≥ 0 时换 S&P500）为第一，另列「相关 ≥ 0 时拿现金」的变体（ZBX）、说两个只做一个。这里选 ZBX：它就是「核心对熊市用更快的那条线」，
    熊市里拿什么完全照 B2（负相关 → 1482、否则现金），不另加换指数；1987〜2000 股债多为正相关，拿现金比拿 S&P500 更像 B2 的熊市做法。
  - 机制：时间序列动量（Moskowitz, Ooi & Pedersen 2012；Hurst, Ooi & Pedersen 2017）与均线择时（Faber 2007：跌破长期均线就离场，主要好处是避开大跌）；
    离场后的去处照 BCU（股债负相关时国债起避险作用：Campbell, Sunderam & Viceira 2017），来回的代价比拿现金小一点。
  - 以前相近的（照实写）：第三个循环 ZSP（同一条 250 日线、b = 0、k = 5 的警戒区里换 S&P500）第一关 +0.141（几乎全在 Z）、第二关第 96.8 百分位；
    时点研究 T7（跌破 250 日线且距高点 −10%、连续 2 天）把 S0C2 的 20 年回撤从 −35.10% 浅到 −27.85%、年化几乎不变，但没过那次研究的多市场门槛；
    第一个循环 CPX（10 天内跌 10% 熔断）第一关不过。这里和它们不同的是：只动核心（日本个股层的分界不动）、离场去处照 BCU。
  → 看过 B2 的回撤诊断、ZSP、T7、CPX 之后设计 → 按事后处理，S7 适用（没看过的 1987〜2000 只有核心，候选 − B2 > 0）。家族「核心·择时（早离场）」是新家族。
做法 ZBX（参数：L = 250 与现行分界相同；b = 0、k = 1 = 不加带宽、不等确认的「收盘在 250 日线下」—— 看过 2020 年跌得多快之后选的最简单形式，照实写；
  S6 不适用（没有从数据学出来的参数）；不改个股 → S5 不适用）：
  - 快线 = qbreak.bullbear.ma_band(L = 250, b = 0, k = 1) 用在 S&P500 收盘（美国日期）上：收盘 < 250 日均线 → 熊、> 均线 → 牛（相等 = 维持前一天）。
  - 东证交易日 d 上（引擎读 B2「美股熊」同一个对齐：d 之前（含 d 的日期）最近一个美国收盘）：核心用的熊 = B2 的分界是熊 或 快线是熊。
    即：B2 是牛、但 S&P500 已收在 250 日线下（警戒区）→ 核心先照 B2 熊市的做法（股债 63 天负相关 → 1482，否则现金）；
    收回线上、且 B2 的分界不是熊 → 回到核心（FJE 照旧决定 1545 / 2845）；B2 的分界已翻熊 → 照 B2（回来照 B2 的规则）。
  - 接法 = 第 3 轮 NDB 同一个函数（loop6_r03_earlyreturn.over：fxh_over + tbh_over，三个核心键都换成核心用的熊）。个股层、判断层、费用全部同 B2。
第一关：research_loop6.stage1（trade = None、lenses = None、posthoc = 1987〜2000 只有核心 ZBX − B2 的 Calmar 差；只有核心的口径 = 第 3 轮 old_core（第 2 轮 B2 同一个），
  只把核心用的熊换成美国日期上的「分界是熊 或 快线是熊」）。
第二关（第一关全过才做；另行登记后只运行一次；代码写在本脚本 --stage2）：kind = signal —— 候选自己新加的信号 = 警戒区标记（东证日上：快线是熊 且 B2 的分界不是熊；
  = ZBX 与 B2 不一样的日子）在 2000-01-04〜2026-09-30 的东证交易日上整体循环平移 k（research_loop6.shift_ks(n, 0)：种子 [20261006, 0, s]），窗外不动；
  核心用的熊 = B2 的分界 或 平移后的警戒区（落在熊市里的不起作用）；B2（分界、FJE、BCU 的相关条件、1482 价格）不动。候选的 Calmar 差合计要严格大于 400 次的最大值。
  照实写为什么平移警戒区而不是快线本身：快线与 B2 的分界用的是同一条 S&P500、熊市段大多重叠；平移快线会把熊市的整段「在线下」搬进牛市（随机地长期离场），
  对照会太差、太容易过；平移警戒区只检验新加的那部分信息（同第 3 轮参照用的「只平移不一样的日子」）。
  另加只描述（不参与判定）：ZSP 的第二关形状 —— 警戒区标记只在 B2 是牛的东证日串上整体循环平移（research_loop3.shift_ks：种子 [20261003, s]），
  每次都有同样多的、起作用的警戒区日子；报候选在 400 次里的百分位。
接线核对（登记前，不看候选的结果）：① 警戒区全为 False → 三个年代与 B2 逐项相同；② 本脚本的 old_core 用 B2 自己的熊 = 第 2 轮记录的 B2 只有核心 Calmar。
只描述（不参与判定）：各年代警戒区的天数 / 段 / 占牛市日子的比例、其中拿 1482（负相关）与现金的天数、对冲中的比例；核心换仓笔数；1987〜2000 的警戒区段；
  每年收益差；最新一天的状态。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop6_r04_fastexit.py（第一关）；--scale（只数日子）；--wiring（登记前的接线核对）；--stage2 ZBX [--workers N]（第二关）；
  --stage2ref ZBX [--workers N]（只描述的 ZSP 形状）。输出 var/out/loop6_r04_fastexit.md / .json（第二关 _stage2_ZBX、参照 _stage2ref_ZBX）。非投资建议。
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
import loop6_common as L6                                                    # noqa: E402
import loop6_r03_earlyreturn as N3                                           # noqa: E402
import loop_r08_ndxreentry as N8                                             # noqa: E402
import research_loop3 as R3                                                  # noqa: E402
import research_loop6 as R6                                                  # noqa: E402

ROUND = 4
IDS = ("ZBX",)
FAMILY = {"ZBX": "核心·择时（早离场）"}
KIND = {"ZBX": "signal"}
POSTHOC = True
FAST = {"L": 250, "b": 0.0, "k": 1}                                          # 收盘在 250 日线下（不加带宽、不等确认）
OLD = N3.OLD
REF2 = N3.REF2                                                               # 接线核对 ②：第 2 轮记录的 B2 只有核心
OUT = "loop6_r04_fastexit"
on_idx = N3.on_idx
over = N3.over


# ───────────────────────── 规则（纯函数，tests/test_loop6_r04.py） ─────────────────────────
def fast_bear(close: pd.Series, params: dict | None = None) -> pd.Series:
    """快线：现行检测器 qbreak.bullbear.ma_band 用 L = 250、b = 0、k = 1（美国日期；True = 收在 250 日线下）。"""
    from qbreak.bullbear import BEAR, Detector
    c = close.dropna().astype(float)
    return pd.Series(np.asarray(Detector("ma_band", dict(params or FAST)).states(c)) == BEAR, index=c.index)


def zone(slow_t: pd.Series, fast_t: pd.Series) -> pd.Series:
    """警戒区（同一个日期轴上）= 快线是熊 且 B2 的分界不是熊（= ZBX 与 B2 不一样的日子）。"""
    return pd.Series(fast_t.astype(bool).to_numpy() & ~slow_t.astype(bool).to_numpy(), index=slow_t.index)


def core_bear(slow_t: pd.Series, zone_t: pd.Series) -> pd.Series:
    """核心用的熊 = B2 的分界是熊 或 在警戒区里。"""
    return pd.Series(slow_t.astype(bool).to_numpy() | zone_t.astype(bool).to_numpy(), index=slow_t.index)


def shifted_zone(zone_t: pd.Series, k: int | None) -> pd.Series:
    """第二关：警戒区标记在 2000-01-04〜J 的最后一天上整体循环平移 k（None = 不平移），窗外不动。"""
    s = zone_t.astype(bool).copy()
    if k is not None:
        w = R6.shift_window(s)
        s.loc[w.index] = R6.shift_signal(w, k).to_numpy(bool)
    return s


def placebo_ks(n: int) -> list[int]:
    """每个种子的平移量（signal：shift_ks(n, 0)）。"""
    return R6.shift_ks(n, 0)


def ref_mask(slow_t: pd.Series) -> np.ndarray:
    """只描述用：2000-01-04〜J 的最后一天里 B2 是牛的东证日。"""
    idx = slow_t.index
    return ~slow_t.astype(bool).to_numpy() & np.asarray((idx >= pd.Timestamp(R6.SHIFT_FROM)) & (idx <= pd.Timestamp(L6.J_END)))


def ref_zone(slow_t: pd.Series, zone_t: pd.Series, k: int) -> pd.Series:
    """只描述用（ZSP 的第二关形状）：警戒区标记只在 B2 是牛的东证日串上整体循环平移 k；窗外照真实的。"""
    z = zone_t.astype(bool).to_numpy().copy()
    pos = np.flatnonzero(ref_mask(slow_t))
    z[pos] = np.roll(z[pos], int(k))
    return pd.Series(z, index=zone_t.index)


def ref_ks(n: int) -> list[int]:
    """ZSP 同一组平移量（research_loop3.shift_ks：numpy.random.default_rng([20261003, s])，k ∈ [250, n − 250]）。"""
    return R3.shift_ks(n)


def zone_days(zone_t: pd.Series, slow_t: pd.Series, on_b: pd.Series, uni: pd.Series, days: pd.DatetimeIndex) -> dict:
    """这段日子里：警戒区天数 / 段、占牛市日子的比例、其中拿 1482（负相关）/ 现金的天数、对冲中的比例（只数日子）。"""
    days = pd.DatetimeIndex(days)
    z = on_idx(zone_t, days)
    bull = ~on_idx(slow_t, days)
    ob = on_idx(on_b, days)
    h = on_idx(uni, days)
    seg = N8.segments(z, str(days[0].date()), str(days[-1].date())) if len(days) else []
    return {"zone_days": int(z.sum()), "bull_days": int(bull.sum()), "pct_of_bull": round(float(z.sum() / bull.sum() * 100), 1) if bull.any() else None,
            "bond_days": int((z & ob).sum()), "cash_days": int((z & ~ob).sum()),
            "hedged_pct": round(float(h[z].mean() * 100), 1) if z.any() else None,
            "segments": len(seg), "longest": max((x[2] for x in seg), default=0), "seg_list": [list(x) for x in seg]}


# ───────────────────────── 输入 / 规模 ─────────────────────────
def inputs(W: dict) -> dict:
    """B2 的输入（W["bcu"]）+ FJE 的「对冲中」+ 东证日上的 B2 分界 / 快线 / 警戒区 / 核心用的熊；美国日期上的快线（S7 用）。"""
    import loop2_common as L2
    import loop_r04_yensurge as Y
    M = dict(W["bcu"])
    days = M["on_b"].index
    _, _, uni = L2.fje_states(W)
    fast_us = fast_bear(W["inp"]["spx"]["Close"])
    M.update({"days": days, "uni": uni, "hf": Y.hedged_frame(W["inp"]), "fast_us": fast_us,
              "slow_t": on_idx(W["bear"]["US"], days), "fast_t": on_idx(fast_us, days)})
    M["zone"] = zone(M["slow_t"], M["fast_t"])
    M["cb"] = core_bear(M["slow_t"], M["zone"])
    return M


def old_bear(W: dict, M: dict) -> pd.Series:
    """S7 用：美国日期上的核心用的熊 = 分界是熊 或 快线是熊（各自向后填）。"""
    import loop_r04_yensurge as Y
    return Y.or_series(W["bear"]["US"].astype(bool), M["fast_us"].astype(bool))


def scale(W: dict, M: dict) -> dict:
    out = {e: zone_days(M["zone"], M["slow_t"], M["on_b"], M["uni"], N3.era_days(W, e)) for e in L6.ERAS}
    w = R6.shift_window(M["zone"])
    out["zone_share_2000_2026"] = round(float(w.mean() * 100), 2)
    out["shift_n"] = len(w)
    out["ref_n"] = int(ref_mask(M["slow_t"]).sum())
    zo = pd.Series(M["fast_us"].astype(bool).to_numpy(), index=M["fast_us"].index)
    sl = on_idx(W["bear"]["US"], zo.index)
    zus = zo & ~sl
    out["old_segments"] = [list(x) for x in N8.segments(zus, *OLD)]
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "slow_bear": bool(M["slow_t"].iloc[-1]), "fast_bear": bool(M["fast_t"].iloc[-1]),
                     "zone": bool(M["zone"].iloc[-1])}
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


_f = N3._f
git_head = N3.git_head


def stage_one() -> int:
    import loop2_r05_ddbrake as R5
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L6.load()
    M = inputs(W)
    ov = over(W, M["cb"], M["uni"], M["hf"], M["on_b"], M["fb"])
    reg = R6.segment(R6.load_state()).get("baseline") or {}
    base, cand, trades = {}, {"ZBX": {}}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand["ZBX"][e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B2": nb, "ZBX": nc}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B2": N3.old_core(W, M["uni"], W["bear"]["US"]), "ZBX": N3.old_core(W, M["uni"], old_bear(W, M))}
    unseen = None if old["B2"]["calmar"] is None or old["ZBX"]["calmar"] is None else old["ZBX"]["calmar"] - old["B2"]["calmar"]
    s1 = {"ZBX": R6.stage1(cand["ZBX"], base, posthoc=unseen)}
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
    s = res["stage1"]["ZBX"]
    pv = s["posthoc"]
    L = [f"# 第六个研究循环第二段第 4 轮：核心的快速离场 ZBX（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop6_r04_fastexit.py 开头；基准 B2 = B1 + BCU）", "",
         f"- **ZBX：{'第一关全过 → 另行登记第二关（警戒区循环平移）' if s['ok'] else R6.FAIL1}**"
         f"（S1 合计 {_f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
         f"S4（{_f(s['h1'], '{:+.3f}')} / {_f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {_f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）",
         "", "| 年代 | B2 年化 / 最大回撤 / Calmar（前半 / 后半） | ZBX（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['ZBX'][e])}（{_f(s['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定；规模只数日子）："]
    sc = res["scale"]
    for e in L6.ERAS:
        x = sc[e]
        L.append(f"- {e}：警戒区 {x['zone_days']} 天（牛市日子的 {_f(x['pct_of_bull'], '{:.1f}')}%，{x['segments']} 段、最长 {x['longest']} 天；"
                 f"拿 1482 {x['bond_days']} 天、现金 {x['cash_days']} 天；对冲中 {_f(x['hedged_pct'], '{:.1f}')}%）；"
                 f"核心换仓 B2 {res['core_trades'][e]['B2']} → ZBX {res['core_trades'][e]['ZBX']} 笔")
    L.append(f"- 警戒区占 2000〜2026 全部东证日的 {sc['zone_share_2000_2026']}%；最新一天 {sc['latest']['date']}：分界 {'熊' if sc['latest']['slow_bear'] else '牛'}、"
             f"快线 {'熊' if sc['latest']['fast_bear'] else '牛'}、警戒区 {'是' if sc['latest']['zone'] else '否'}")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {_f(o[k]['calmar'])}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%、"
        f"拿核心 {_f(o[k].get('core_days_pct'), '{:.1f}')}%、拿债券 {_f(o[k].get('bond_days_pct'), '{:.1f}')}% 的日子）" for k in ("B2", "ZBX"))
        + f"；警戒区 {len(sc['old_segments'])} 段")
    for e in L6.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["ZBX"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（ZBX − B2，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
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
    sc = scale(W, M)
    for e in L6.ERAS:
        sc[e] = {k: v for k, v in sc[e].items() if k != "seg_list"} | {"seg_list": sc[e]["seg_list"]}
    print(json.dumps({"scale": sc}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用：① 警戒区全为 False → 三个年代与 B2 逐项相同；② old_core(B2 自己的熊) = 第 2 轮记录的 B2 只有核心 Calmar。"""
    from qbreak import paths
    W = L6.load()
    M = inputs(W)
    keys = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")
    none = core_bear(M["slow_t"], pd.Series(False, index=M["days"]))
    ov0 = over(W, none, M["uni"], M["hf"], M["on_b"], M["fb"])
    same_b2 = {}
    for e in L6.ERAS:
        rb, r0 = L6.run(W, e), L6.run(W, e, **ov0)
        same_b2[e] = bool(all(rb.get(x) == r0.get(x) for x in keys))
    oc = N3.old_core(W, M["uni"], W["bear"]["US"])["calmar"]
    ref2 = json.loads((paths.out_dir() / REF2).read_text(encoding="utf-8"))["old"]["B2"]["calmar"]
    out = {"no_zone_same_as_b2": same_b2, "old_core_b2_same": bool(oc == ref2)}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if all(same_b2.values()) and out["old_core_b2_same"] else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次；signal = 警戒区循环平移）与只描述的参照 ─────────────────────────
_G: dict = {}


def _run_sum(W: dict, M: dict, cb: pd.Series, base: dict):
    kw = over(W, cb, M["uni"], M["hf"], M["on_b"], M["fb"])
    tot = 0.0
    for e in L6.ERAS:
        c = L6.run(W, e, **kw)["calmar"]
        if c is None or base[e] is None:
            return None
        tot += c - base[e]
    return round(float(tot), 6)


def _placebo_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        return _run_sum(W, M, core_bear(M["slow_t"], shifted_zone(M["zone"], ks[int(seed)])), base)
    except Exception:                                                         # noqa: BLE001
        return None


def _placebo_ref_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        return _run_sum(W, M, core_bear(M["slow_t"], ref_zone(M["slow_t"], M["zone"], ks[int(seed)])), base)
    except Exception:                                                         # noqa: BLE001
        return None


def _pool(fn, seeds: list[int], workers: int, t0: float, tag: str) -> list:
    import multiprocessing as mp
    vals = []
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            for i, v in enumerate(pool.imap(fn, seeds)):
                vals.append(v)
                if (i + 1) % 40 == 0:
                    print(f"{tag} {i + 1} / {len(seeds)}（{time.time() - t0:.0f}s）", flush=True)
    else:
        for i in seeds:
            vals.append(fn(i))
    return vals


def _prepare(k: str):
    from qbreak import paths
    s1 = json.loads((paths.out_dir() / f"{OUT}.json").read_text(encoding="utf-8"))["stage1"][k]
    if not s1["ok"]:
        return None
    W = L6.load()
    M = inputs(W)
    base = {e: L6.run(W, e)["calmar"] for e in L6.ERAS}
    ov = over(W, M["cb"], M["uni"], M["hf"], M["on_b"], M["fb"])
    cand = {e: L6.run(W, e, **ov)["calmar"] for e in L6.ERAS}
    return s1, W, M, base, cand, round(sum(cand[e] - base[e] for e in L6.ERAS), 6)


def stage_two(k: str, workers: int) -> int:
    from qbreak import paths
    t0 = time.time()
    p = _prepare(k)
    if p is None:
        print(f"{k} 第一关没过 → 不做第二关")
        return 1
    s1, W, M, base, cand, stat = p
    code, dirty = git_head()
    n = len(R6.shift_window(M["zone"]))
    ks = placebo_ks(n)
    _G.update({"W": W, "M": M, "base": base, "ks": ks})
    vals = _pool(_placebo_one, list(range(R6.PLACEBO_N)), workers, t0, "随机改动")
    s2 = R6.stage2(stat, vals)
    vd = R6.verdict(s1, s2)
    v = np.array([x for x in vals if x is not None], float)
    res = {"loop": 6, "segment": 2, "round": ROUND, "id": k, "kind": KIND[k], "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat,
           "stage1_stat": s1["sum"], "n": n, "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第六个研究循环第二段第 4 轮 第二关：{k} vs 400 次警戒区循环平移（{KIND[k]}；B2 不动）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
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


def stage_two_ref(k: str, workers: int) -> int:
    """只描述（不参与判定）：ZSP 形状（警戒区只在 B2 是牛的日子串上平移）的 400 次随机对照，报候选的百分位。"""
    from qbreak import paths
    t0 = time.time()
    p = _prepare(k)
    if p is None:
        print(f"{k} 第一关没过 → 不做")
        return 1
    s1, W, M, base, cand, stat = p
    code, dirty = git_head()
    n = int(ref_mask(M["slow_t"]).sum())
    ks = ref_ks(n)
    _G.update({"W": W, "M": M, "base": base, "ks": ks})
    vals = _pool(_placebo_ref_one, list(range(R6.PLACEBO_N)), workers, t0, "随机改动（ZSP 形状）")
    s2 = R6.stage2(stat, vals)
    v = np.array([x for x in vals if x is not None], float)
    pct = round(float((v < stat).mean() * 100), 2) if len(v) else None
    res = {"loop": 6, "segment": 2, "round": ROUND, "id": k, "shape": "ZSP（警戒区标记在 B2 是牛的东证日串上循环平移）", "describe_only": True,
           "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "n": n, "placebo": vals, "max": s2["max"],
           "ge_stat": s2["ge_stat"], "valid": s2["valid"], "pct_below": pct,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第六个研究循环第二段第 4 轮 只描述（不参与判定）：{k} vs ZSP 形状的 400 次随机对照（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"候选的 Calmar 差合计 {stat:+.4f}；随机（警戒区标记在 B2 是牛的 {n} 个东证日串上循环平移）比候选低的 {_f(pct, '{:.2f}')}%、"
         f"最大 {_f(s2['max'], '{:+.4f}')}、≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B2 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。只描述，判定只看 --stage2。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}_stage2ref_{k}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2ref_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第六个研究循环第二段第 4 轮：ZBX（核心的快速离场）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scale", action="store_true", help="只数日子（不算收益）")
    g.add_argument("--wiring", action="store_true", help="登记前的接线核对（不看候选的结果）")
    g.add_argument("--stage2", choices=IDS, help="第二关（第一关全过才做）")
    g.add_argument("--stage2ref", choices=IDS, help="只描述：ZSP 形状的随机对照（不参与判定）")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    if a.scale:
        return scale_only()
    if a.wiring:
        return wiring()
    if a.stage2:
        return stage_two(a.stage2, a.workers)
    if a.stage2ref:
        return stage_two_ref(a.stage2ref, a.workers)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
