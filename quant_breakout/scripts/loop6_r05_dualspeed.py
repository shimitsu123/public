"""loop6_r05_dualspeed.py — 第六个研究循环第二段（基准 B2 = 采用后的模拟盘 B1 + BCU）第 5 轮：「核心的双速离场」TB7
（2026-10-03 登记；先提交后只运行一次；家族「核心·择时（早离场）」第二段 2 / 3；kind = signal；事后 → S7 适用）。

用户（2026-10-03）：「采用\\n\\n并且继续第六个研究循环」。循环的规则：scripts/research_loop6.py（第二段 = 开头七与末尾一节）；基准 B2：scripts/loop6_common.py。
为什么做这个（照实写）：
  - 第 4 轮 ZBX（S&P500 一收在 250 日线下就照熊市处理、收回就回来）第一关不过（−0.555）：跌破又收回的段来回卖低买高，Z 的回撤反而加深 5 pp，
    2022 / 2025 各少赚 10〜12 pp。看过这个结果之后，改用时点研究第二轮已经登记、参数固定的 T7（qbreak/timing.s7_dual_speed：
    「收在 250 日线下 且 距 250 日最高收盘回落 ≥ 10%」连续 2 天才快速离场；回来与现行分界同一个规则：连续 5 天收在 250 日线 × 1.03 之上）
    —— 只在真正的回调里早走、不会跌破一下就走、收回一下就回来。
  - T7 在时点研究里（1655 核心的旧组合 S0C2）20 年回撤 −35.10% → −27.85%、年化几乎不变（12.84% vs 12.82%），但美国前半段与日本两段没过那次研究的门槛
    → 没进观察名单。这里只把它用在 B2 的闲置资金上（日本个股层的分界不动），熊市里拿什么照 B2（负相关 → 1482、否则现金）。
  → 看过 ZBX、T7 的结果之后设计 → 按事后处理，S7 适用。参数全部是 T7 登记时的（250 日、−10%、连续 2 天；回来照 T0）→ S6 不适用；不改个股 → S5 不适用。
做法 TB7：T7 用在 S&P500 收盘（美国日期）上 → 快线 = T7 是熊；东证日 d（d 之前含 d 的最近一个美国收盘）核心用的熊 = B2 的分界是熊 或 T7 是熊
  （T7 的熊包含 T0 的熊：T0 翻熊的那天 T7 也满足连续 5 天的条件；回来的规则相同）。接法 = 第 3 / 4 轮同一个函数（loop6_r03_earlyreturn.over）。
第一关：research_loop6.stage1（posthoc = 1987〜2000 只有核心 TB7 − B2；口径 = 第 3 轮 old_core，核心用的熊换成美国日期上的「分界熊 或 T7 熊」）。
第二关（第一关全过才做；另行登记后只运行一次；代码写在本脚本 --stage2）：kind = signal —— 候选自己新加的信号 =「T7 是熊、B2 的分界还不是熊」的标记
  （= TB7 与 B2 不一样的日子）在 2000-01-04〜2026-09-30 的东证交易日上整体循环平移 k（shift_ks(n, 0)：种子 [20261006, 0, s]），窗外不动；
  B2 不动；候选的 Calmar 差合计要严格大于 400 次的最大值。理由同第 4 轮（平移 T7 本身会把整段熊市搬进牛市，对照太差）。
  另加只描述（不参与判定）：ZSP 的形状（标记只在 B2 是牛的东证日串上平移，research_loop3.shift_ks 种子 [20261003, s]），报候选的百分位。
接线核对（登记前，不看候选的结果）：① 标记全为 False → 三个年代与 B2 逐项相同；② T7 的熊包含 B2 的熊（1986〜2026 每个美国交易日）；
  ③ 本脚本的 old_core 用 B2 自己的熊 = 第 2 轮记录的 B2 只有核心 Calmar。
只描述（不参与判定）：各年代 T7 早走的天数 / 段 / 占牛市比例 / 其中拿 1482 与现金的天数、核心换仓笔数、1987〜2000 的段、每年收益差。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop6_r05_dualspeed.py（第一关）；--scale；--wiring；--stage2 TB7 [--workers N]；--stage2ref TB7 [--workers N]。
输出 var/out/loop6_r05_dualspeed.md / .json（第二关 _stage2_TB7、参照 _stage2ref_TB7）。非投资建议。
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
import loop6_common as L6                                                    # noqa: E402
import loop6_r03_earlyreturn as N3                                           # noqa: E402
import loop6_r04_fastexit as Z4                                              # noqa: E402
import research_loop6 as R6                                                  # noqa: E402

ROUND = 5
IDS = ("TB7",)
FAMILY = {"TB7": "核心·择时（早离场）"}
KIND = {"TB7": "signal"}
POSTHOC = True
OLD = N3.OLD
OUT = "loop6_r05_dualspeed"
on_idx, over = N3.on_idx, N3.over
zone, core_bear, shifted_zone, placebo_ks = Z4.zone, Z4.core_bear, Z4.shifted_zone, Z4.placebo_ks
ref_mask, ref_zone, ref_ks, zone_days = Z4.ref_mask, Z4.ref_zone, Z4.ref_ks, Z4.zone_days
_f, git_head = N3._f, N3.git_head


# ───────────────────────── 规则（纯函数，tests/test_loop6_r05.py） ─────────────────────────
def t7_bear(close: pd.Series) -> pd.Series:
    """T7（qbreak.timing.s7_dual_speed，时点研究第二轮登记的参数）用在 S&P500 收盘上：True = 熊（250 日线还没有的开头 = False）。"""
    from qbreak.bullbear import BEAR
    from qbreak.timing import s7_dual_speed
    c = close.dropna().astype(float)
    return pd.Series(np.asarray(s7_dual_speed(c)) == BEAR, index=c.index)


def t0_bear(close: pd.Series) -> pd.Series:
    """T0（qbreak.timing.s0_states = 现行分界）：只给接线核对 ② 用。"""
    from qbreak.bullbear import BEAR
    from qbreak.timing import s0_states
    c = close.dropna().astype(float)
    return pd.Series(np.asarray(s0_states(c)) == BEAR, index=c.index)


# ───────────────────────── 输入 / 规模 ─────────────────────────
def inputs(W: dict) -> dict:
    """第 4 轮同一个结构，只把快线换成 T7。"""
    import loop2_common as L2
    import loop_r04_yensurge as Y
    M = dict(W["bcu"])
    days = M["on_b"].index
    _, _, uni = L2.fje_states(W)
    fast_us = t7_bear(W["inp"]["spx"]["Close"])
    M.update({"days": days, "uni": uni, "hf": Y.hedged_frame(W["inp"]), "fast_us": fast_us,
              "slow_t": on_idx(W["bear"]["US"], days), "fast_t": on_idx(fast_us, days)})
    M["zone"] = zone(M["slow_t"], M["fast_t"])
    M["cb"] = core_bear(M["slow_t"], M["zone"])
    return M


old_bear = Z4.old_bear
scale = Z4.scale


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def stage_one() -> int:
    import loop2_r05_ddbrake as R5
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L6.load()
    M = inputs(W)
    ov = over(W, M["cb"], M["uni"], M["hf"], M["on_b"], M["fb"])
    reg = R6.segment(R6.load_state()).get("baseline") or {}
    base, cand, trades = {}, {"TB7": {}}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand["TB7"][e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B2": nb, "TB7": nc}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B2": N3.old_core(W, M["uni"], W["bear"]["US"]), "TB7": N3.old_core(W, M["uni"], old_bear(W, M))}
    unseen = None if old["B2"]["calmar"] is None or old["TB7"]["calmar"] is None else old["TB7"]["calmar"] - old["B2"]["calmar"]
    s1 = {"TB7": R6.stage1(cand["TB7"], base, posthoc=unseen)}
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
    s = res["stage1"]["TB7"]
    pv = s["posthoc"]
    L = [f"# 第六个研究循环第二段第 5 轮：核心的双速离场 TB7（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop6_r05_dualspeed.py 开头；基准 B2 = B1 + BCU）", "",
         f"- **TB7：{'第一关全过 → 另行登记第二关（早走标记循环平移）' if s['ok'] else R6.FAIL1}**"
         f"（S1 合计 {_f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
         f"S4（{_f(s['h1'], '{:+.3f}')} / {_f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {_f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）",
         "", "| 年代 | B2 年化 / 最大回撤 / Calmar（前半 / 后半） | TB7（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['TB7'][e])}（{_f(s['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定；规模只数日子）："]
    sc = res["scale"]
    for e in L6.ERAS:
        x = sc[e]
        L.append(f"- {e}：T7 早走 {x['zone_days']} 天（牛市日子的 {_f(x['pct_of_bull'], '{:.1f}')}%，{x['segments']} 段、最长 {x['longest']} 天；"
                 f"拿 1482 {x['bond_days']} 天、现金 {x['cash_days']} 天）；核心换仓 B2 {res['core_trades'][e]['B2']} → TB7 {res['core_trades'][e]['TB7']} 笔")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {_f(o[k]['calmar'])}（年化 {_f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {_f(o[k].get('dd'), '{:.2f}')}%）" for k in ("B2", "TB7"))
        + f"；早走 {len(sc['old_segments'])} 段")
    for e in L6.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["TB7"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（TB7 − B2，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
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
    """登记前用：① 标记全为 False → 三个年代与 B2 逐项相同；② T7 的熊包含 T0 的熊（= B2 的分界）；③ old_core(B2 的熊) = 第 2 轮记录值。"""
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
    spx = W["inp"]["spx"]["Close"]
    t0b, t7b = t0_bear(spx), M["fast_us"]
    slow = W["bear"]["US"].astype(bool).reindex(t0b.index).fillna(False)
    contains = bool((~t0b | t7b.reindex(t0b.index).fillna(False)).all())
    t0_is_slow = bool((t0b == slow).all())
    oc = N3.old_core(W, M["uni"], W["bear"]["US"])["calmar"]
    ref2 = json.loads((paths.out_dir() / N3.REF2).read_text(encoding="utf-8"))["old"]["B2"]["calmar"]
    out = {"no_zone_same_as_b2": same_b2, "t7_contains_t0": contains, "t0_equals_b2_slow": t0_is_slow, "old_core_b2_same": bool(oc == ref2)}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if all(same_b2.values()) and contains and t0_is_slow and out["old_core_b2_same"] else 1


# ───────────────────────── 第二关与只描述的参照（与第 4 轮同一套代码，输入换成 T7） ─────────────────────────
_G: dict = {}


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


def _placebo_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        return Z4._run_sum(W, M, core_bear(M["slow_t"], shifted_zone(M["zone"], ks[int(seed)])), base)
    except Exception:                                                         # noqa: BLE001
        return None


def _placebo_ref_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        return Z4._run_sum(W, M, core_bear(M["slow_t"], ref_zone(M["slow_t"], M["zone"], ks[int(seed)])), base)
    except Exception:                                                         # noqa: BLE001
        return None


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
    vals = Z4._pool(_placebo_one, list(range(R6.PLACEBO_N)), workers, t0, "随机改动")
    s2 = R6.stage2(stat, vals)
    vd = R6.verdict(s1, s2)
    v = np.array([x for x in vals if x is not None], float)
    res = {"loop": 6, "segment": 2, "round": ROUND, "id": k, "kind": KIND[k], "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat,
           "stage1_stat": s1["sum"], "n": n, "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第六个研究循环第二段第 5 轮 第二关：{k} vs 400 次早走标记循环平移（{KIND[k]}；B2 不动）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
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
    """只描述（不参与判定）：ZSP 形状的 400 次随机对照，报候选的百分位。"""
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
    vals = Z4._pool(_placebo_ref_one, list(range(R6.PLACEBO_N)), workers, t0, "随机改动（ZSP 形状）")
    s2 = R6.stage2(stat, vals)
    v = np.array([x for x in vals if x is not None], float)
    pct = round(float((v < stat).mean() * 100), 2) if len(v) else None
    res = {"loop": 6, "segment": 2, "round": ROUND, "id": k, "shape": "ZSP（早走标记在 B2 是牛的东证日串上循环平移）", "describe_only": True,
           "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "n": n, "placebo": vals, "max": s2["max"],
           "ge_stat": s2["ge_stat"], "valid": s2["valid"], "pct_below": pct,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第六个研究循环第二段第 5 轮 只描述（不参与判定）：{k} vs ZSP 形状的 400 次随机对照（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"候选的 Calmar 差合计 {stat:+.4f}；随机（早走标记在 B2 是牛的 {n} 个东证日串上循环平移）比候选低的 {_f(pct, '{:.2f}')}%、"
         f"最大 {_f(s2['max'], '{:+.4f}')}、≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B2 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。只描述，判定只看 --stage2。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}_stage2ref_{k}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2ref_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第六个研究循环第二段第 5 轮：TB7（核心的双速离场）")
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
