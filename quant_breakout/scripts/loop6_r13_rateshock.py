"""loop6_r13_rateshock.py — 第六个研究循环第三段（基准 B3 = 撤掉 FJE 之后的模拟盘 Q1B，修正口径）第 13 轮：
「10 年美债收益率急升（20 个营业日上升 ≥ 0.40 pp）的牛市里，三分之一核心离开纳指、留现金」RSC（2026-10-03 登记；先提交后只运行一次；
家族「核心·利率冲击」新家族 1 / 3；kind = signal；事后 → S7 适用）。

用户（2026-10-03）：㊼ ①「重新检验，不过就撤」（只回答编号 = 同时同意：第六个循环按修正口径重算基准、计数接着 7 / 20、照现行规则选题）；
之前「…没有时间限制 一直找到比现在算法更好的」。循环的规则：scripts/research_loop6.py（第三段 = 开头「九」与末尾一节）；基准 B3：scripts/loop6_common.load3。
为什么做这个（照实写；看过第 7〜12 轮之后设计 = 事后）：
  - 第 9 / 12 轮里「股债不是负相关的急跌」多半是利率急升带动的（2021-02〜03、2022-01〜04、2023-08〜10、2004-04〜05、1994、1987-09〜10），
    纳指久期长、对利率最敏感；这种时候债券自己在跌 → 避险只能拿现金。第二个循环的 RXC / RXH（2 年利率急升 → 换 S&P500）Z 有用、E / J 不一致；
    这一轮换成「10 年利率急升 → 1/3 现金」，信号来源是利率（与 VCT 的价格信号、CSV 的信用利差不同）。
  - 选参数前只数了状态（本会话；没看收益）：FRED DGS10 晚一天、20 个营业日上升 ≥ 0.40 pp 开、< 0.20 pp 关，牛市日子里成立
    1987〜2000 14.9%（31 段，含 1987-09-03〜10-20、1994-02〜05）、Z 12.1%（5 段）、E 6.1%（8 段）、J 7.2%（10 段）。0.40 / 0.20 / 20 天是整数常用值，看过状态之后没有改。
做法 RSC（没有学出来的参数 → S6 不适用；不改个股 → S5 不适用）：
  - 利率 = FRED DGS10（营业日）；先用前一个 FRED 日的值（晚一天发布），20 个营业日的变化 ≥ 0.40 pp → 开，< 0.20 pp → 关（中间保持）；
    东证日的对齐同 B3 的「美股熊」。
  - 美股牛 ∧ 信号 → 1545 拿 2/3、1/3 现金（不管股债相关：利率急升时美债本身在跌）；其余同 B3。
  - 接法：B3 原样 + 引擎的 core_expo["US"]（1545 的目标再乘：信号成立的牛市日子 2/3，其余 1）。
第一关：research_loop6.stage1（S1〜S4 + S7：1987〜2000 只有核心 RSC − B3 > 0；口径 = 第 7 轮 old_core，持仓多一条：牛 ∧ 信号 → 纳指 2/3、现金 1/3）。
第二关（第一关全过才做；另行登记后只运行一次；代码写在本脚本 --stage2）：kind = signal —— 信号「10 年利率急升」（东证日上的布尔序列）在 2000-01-04〜2026-09-30
  的东证交易日上整体循环平移 k（research_loop6.shift_ks(n, 0)：种子 [20261006, 0, s]），窗外不动；B3 不动。候选的 Calmar 差合计要严格大于 400 次的最大值。
接线核对（登记前，不看候选的结果；--wiring）：① 信号永远不成立 → 三个年代与 B3 逐项相同；② old_core 信号 None = 第 7 轮函数的 B3；③ B3 没有别的 core_expo。
只描述（不参与判定）：各年代美股牛日子里信号的比例与段数；核心换仓笔数；每年收益差；1987〜2000；最新一天的状态。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop6_r13_rateshock.py（第一关）；--scale（只数日子）；--wiring（登记前的接线核对）；--stage2 RSC [--workers N]（第二关）。
输出 var/out/loop6_r13_rateshock.md / .json（第二关 loop6_r13_rateshock_stage2_RSC.md / .json）。非投资建议。
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
import loop6_r11_creditcut as S                                              # noqa: E402
import research_loop6 as R6                                                  # noqa: E402

ROUND = 13
IDS = ("RSC",)
FAMILY = {"RSC": "核心·利率冲击"}
KIND = {"RSC": "signal"}
POSTHOC = True
SERIES = "DGS10"
WIN = 20
ON, OFF = 0.40, 0.20                                                         # pp：≥ 0.40 开、< 0.20 关
KEEP = 2.0 / 3.0                                                             # 信号成立的牛市日子 1545 拿 2/3、1/3 现金
OLD = V.OLD
OUT = "loop6_r13_rateshock"
on_idx = V.on_idx
KEYS = X.KEYS


# ───────────────────────── 规则（纯函数，tests/test_loop6_r13.py） ─────────────────────────
def shock(yields: pd.Series) -> pd.Series:
    """FRED 日期上的信号：第 11 轮 widening 同一个函数（晚一天、20 个营业日变化、开 / 关的滞后），门槛换成 0.40 / 0.20 pp。"""
    return S.widening(yields, win=WIN, on=ON, off=OFF)


def expo_us(bear_t: pd.Series, sig_t: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """1545（键 US）的比例：美股牛 ∧ 信号 → 2/3，其余 1。"""
    days = pd.DatetimeIndex(days)
    b, s = on_idx(bear_t, days).to_numpy(bool), on_idx(sig_t, days).to_numpy(bool)
    return pd.Series(np.where(~b & s, KEEP, 1.0), index=days)


def rsc_over(W: dict, M: dict, sig_t: pd.Series) -> dict:
    """B3 原样 + core_expo["US"]（B3 的 1545 键就是 US）。"""
    return {"core_expo": {"US": expo_us(M["bear_t"], sig_t, M["on_b"].index)}}


def core_weights(bear: pd.Series, sig: pd.Series, on: pd.Series) -> pd.DataFrame:
    """只有核心（1987〜2000）：B3 的持仓（牛 → 纳指 1；熊 ∧ 负相关 → 美债 1；其余现金），牛 ∧ 信号 → 纳指 2/3。"""
    b, s, o = bear.astype(bool), sig.astype(bool), on.astype(bool)
    w = V.core_weights(b, pd.Series(False, index=b.index), o)
    w.loc[~b & s, "u"] = KEEP
    return w


def shifted_signal(sig_t: pd.Series, k: int | None) -> pd.Series:
    return X.shifted_signal(sig_t, k)


def placebo_ks(n: int) -> list[int]:
    return R6.shift_ks(n, 0)


# ───────────────────────── 1987〜2000 只有核心（S7） ─────────────────────────
def old_core(W: dict, sig_us: pd.Series | None) -> dict:
    """第 7 轮 old_core 同一个口径，持仓换成本轮的 core_weights；sig_us = None → B3。"""
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
    w = core_weights(b, s, ou).shift(1).fillna(0.0)
    ret = w["u"] * unh.pct_change().fillna(0.0) + w["b"] * b_px.pct_change().fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["cut_bull_pct"] = round(float((s & ~b).sum() / max(1, int((~b).sum())) * 100), 1)
    return out


# ───────────────────────── 输入 / 规模 ─────────────────────────
def inputs(W: dict) -> dict:
    from qbreak import factors as F
    M = X.inputs(W)
    rs = shock(F.fred(SERIES))
    M.update({"rs_us": rs, "rs_t": on_idx(rs, M["days"])})
    return M


def state_share(bear_t, sig_t, days) -> dict:
    days = pd.DatetimeIndex(days)
    b, s = on_idx(bear_t, days), on_idx(sig_t, days)
    cut = ~b & s
    nb = int((~b).sum())
    return {"bull_days": nb, "cut_pct": round(float(cut.sum()) / nb * 100, 1) if nb else None, "cut_segments": V.segments(cut)}


def scale(W: dict, M: dict) -> dict:
    out = {e: state_share(M["bear_t"], M["rs_t"], V.era_days(W, e)) for e in L6.ERAS}
    w = R6.shift_window(M["rs_t"])
    out["window"] = state_share(M["bear_t"], M["rs_t"], w.index)
    out["sig_share_2000_2026"] = round(float(w.mean() * 100), 1)
    out["shift_n"] = len(w)
    out["overlap_with_vct_pct"] = round(float((M["rs_t"] & M["sig_t"]).sum() / max(1, int(M["rs_t"].sum())) * 100), 1)
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "us_bear": bool(M["bear_t"].iloc[-1]), "signal": bool(M["rs_t"].iloc[-1])}
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
    M = inputs(W)
    ov = rsc_over(W, M, M["rs_t"])
    reg = R6.segment(R6.load_state()).get("baseline") or {}
    base, cand, trades = {}, {"RSC": {}}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand["RSC"][e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B3": nb, "RSC": nc}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B3": old_core(W, None), "RSC": old_core(W, M["rs_us"])}
    unseen = None if old["B3"]["calmar"] is None or old["RSC"]["calmar"] is None else old["RSC"]["calmar"] - old["B3"]["calmar"]
    s1 = {"RSC": R6.stage1(cand["RSC"], base, posthoc=unseen)}
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
    s = res["stage1"]["RSC"]
    pv = s["posthoc"]
    L = [f"# 第六个研究循环第三段第 13 轮：10 年美债收益率急升的牛市里 1/3 留现金 RSC（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop6_r13_rateshock.py 开头；基准 B3 = Q1B，修正口径）", "",
         f"- **RSC：{'第一关全过 → 另行登记第二关（信号循环平移）' if s['ok'] else R6.FAIL1}**"
         f"（S1 合计 {f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
         f"S4（{f(s['h1'], '{:+.3f}')} / {f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）",
         "", "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | RSC（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{f(x['cagr'], '{:+.2f}')}% / {f(x['dd'], '{:.2f}')}% / {f(x['calmar'])}（{f(x['h1'])} / {f(x['h2'])}）"   # noqa: E731
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['RSC'][e])}（{f(s['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定；规模只数日子）："]
    sc = res["scale"]
    for e in L6.ERAS:
        x = sc[e]
        L.append(f"- {e}：美股牛 {x['bull_days']} 天里信号 {f(x['cut_pct'], '{:.1f}')}%（{x['cut_segments']} 段）；"
                 f"核心换仓 B3 {res['core_trades'][e]['B3']} → RSC {res['core_trades'][e]['RSC']} 笔")
    lt = sc["latest"]
    L.append(f"- 信号在 2000〜2026 全部东证日里的比例 {sc['sig_share_2000_2026']}%（其中 {sc['overlap_with_vct_pct']}% 的日子 VCT 的信号也成立）；"
             f"最新一天 {lt['date']}：美股{'熊' if lt['us_bear'] else '牛'}、信号 {'是' if lt['signal'] else '否'}")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {f(o[k]['calmar'])}（年化 {f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {f(o[k].get('dd'), '{:.2f}')}%、美股牛的日子里留 1/3 现金 "
        f"{f(o[k].get('cut_bull_pct'), '{:.1f}')}%）" for k in ("B3", "RSC")))
    for e in L6.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["RSC"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（RSC − B3，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B3 与第三段登记值的 Calmar 差：" + "、".join(f"{e} {f(dr[e], '{:+.4f}')}" for e in L6.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R6.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B3）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L6.load3()
    M = inputs(W)
    print(json.dumps({"scale": scale(W, M)}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用：① 信号永远不成立 → B3；② old_core 信号 None = 第 7 轮函数的 B3；③ B3 没有别的 core_expo。"""
    W = L6.load3()
    M = inputs(W)
    no_other = {e: "core_expo" not in (W["kw"][e] or {}) and "core_expo" not in (W.get("b1") or {}) for e in L6.ERAS}
    never = pd.Series(False, index=M["rs_t"].index)
    ov0 = rsc_over(W, M, never)
    same_b3 = {}
    for e in L6.ERAS:
        rb, r0 = L6.run(W, e), L6.run(W, e, **ov0)
        same_b3[e] = bool(all(rb.get(x) == r0.get(x) for x in KEYS))
    o1, o2 = old_core(W, None), V.old_core(W, None)
    out = {"no_other_core_expo": no_other, "never_same_as_b3": same_b3,
           "old_core_b3_same": bool(o1["calmar"] == o2["calmar"] and o1["cagr"] == o2["cagr"])}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if all(no_other.values()) and all(same_b3.values()) and out["old_core_b3_same"] else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次；signal = 信号循环平移） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        kw = rsc_over(W, M, shifted_signal(M["rs_t"], ks[int(seed)]))
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
    M = inputs(W)
    base = {e: L6.run(W, e)["calmar"] for e in L6.ERAS}
    ov = rsc_over(W, M, M["rs_t"])
    cand = {e: L6.run(W, e, **ov)["calmar"] for e in L6.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L6.ERAS), 6)
    n = len(R6.shift_window(M["rs_t"]))
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
    L = [f"# 第六个研究循环第三段第 13 轮 第二关：{k} vs 400 次信号循环平移（{KIND[k]}；B3 不动）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
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
    ap = argparse.ArgumentParser(description="第六个研究循环第三段第 13 轮：RSC")
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
