"""loop6_r12_crashspx.py — 第六个研究循环第三段（基准 B3 = 撤掉 FJE 之后的模拟盘 Q1B，修正口径）第 12 轮：
「急跌信号成立、而股债不是负相关的牛市日子里，核心的纳指（1545）整个换成 S&P500（1655，不对冲）」VPS（2026-10-03 登记；先提交后只运行一次；
家族「核心·指数选择」这一段 1 / 3；kind = signal；事后 → S7 适用）。

用户（2026-10-03）：㊼ ①「重新检验，不过就撤」（只回答编号 = 同时同意：第六个循环按修正口径重算基准、计数接着 7 / 20、照现行规则选题）；
之前「…没有时间限制 一直找到比现在算法更好的」。循环的规则：scripts/research_loop6.py（第三段 = 开头「九」与末尾一节）；基准 B3：scripts/loop6_common.load3。
为什么做这个（照实写；看过第 7〜11 轮的结果之后设计 = 事后）：
  - 第 9 轮 VCT（急跌信号 =「高波动 ∧ 纳指在 50 日线下」时 1/3 离开纳指：负相关 → 美债、否则现金）第一关全过、第二关约第 97 百分位。
    它的「留现金」那部分（股债不是负相关的急跌）在 Z 有用（2006 那段回撤浅了约 1.6 pp），但在 J 多半是成本（2021 −5.5、2026 −4.1 pp：现金错过反弹）。
  - 股债不是负相关的急跌，多半是利率 / 通胀或科技股自己的回调（2006-05〜06、2021-02〜03、2022-01〜03、2024-07〜08、2025-02〜04），
    那时纳指（久期长、β 高）通常比 S&P500 跌得多；换成同样是美股的 S&P500 = 不离开股市、只把 β 降下来，反弹里仍在。
    负相关的急跌（2020-02〜03 等）S&P500 不一定跌得少（2020 年 S&P500 比纳指跌得多）→ 这些日子不动（同 B3）。
  - 家族「核心·指数选择」（这一段 0 用过）；照实写：信号沿用 VCT 的（同第 10 轮 BPR 沿用 VCT 的信号、归「早回来」的做法）。
做法 VPS（信号 = 第 8 / 9 轮原样；BCU 的相关条件原样；1655 的合成价 = equity_idle_study.asset_closes 原样（S&P500 总收益 − 0.066% × 汇率 fx_on）；
  没有新参数 → S6 不适用；不改个股 → S5 不适用）：
  - 美股牛 ∧ 信号 ∧ 股债不是负相关 → 核心拿 1655（不拿 1545）；其余同 B3（美股牛的其余日子 1545、美股熊 ∧ 负相关 1482、其余现金）。
  - 接法：1545 换到键 US_VN（熊 = 美股熊 ∨（信号 ∧ 不是负相关））、1655 键 US_VS（熊 = 美股熊 ∨ ¬（信号 ∧ 不是负相关））、1482 的键 = B3 原样；
    follow 权重都是 1（任何一天最多一只可拿）。东证日的对齐同 B3 的「美股熊」。
第一关：research_loop6.stage1（S1〜S4 + S7：1987〜2000 只有核心 VPS − B3 > 0；口径 = 第 7 轮 old_core（日元计纳指 / 对冲版美债 / S&P 与美债 63 天相关、
  前一天的状态、换仓扣 0.1% × 换的比例），持仓多一条：牛 ∧ 信号 ∧ 不是负相关 → S&P500 总收益 − 0.066%（日元计、不对冲，DEXJPUS）代替纳指）。
第二关（第一关全过才做；另行登记后只运行一次；代码写在本脚本 --stage2）：kind = signal —— 信号「高波动 ∧ 正在跌」（东证日上的布尔序列）在 2000-01-04〜2026-09-30
  的东证交易日上整体循环平移 k（research_loop6.shift_ks(n, 0)：种子 [20261006, 0, s]），窗外不动；三个键跟着平移后的信号重算；B3 不动。
  候选的 Calmar 差合计要严格大于 400 次的最大值（有算不出的 = 不过）。
接线核对（登记前，不看候选的结果；--wiring）：① 信号永远不成立 → 三个年代与 B3 逐项相同；② 引擎拿到的 1655 价格 = equity_idle_study.assets 的合成 1655；
  ③ old_core 信号 None = 第 7 轮函数的 B3。
只描述（不参与判定）：各年代美股牛日子里换成 S&P500 的比例与段数；核心换仓笔数；每年收益差；1987〜2000；最新一天的状态。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop6_r12_crashspx.py（第一关）；--scale（只数日子）；--wiring（登记前的接线核对）；--stage2 VPS [--workers N]（第二关）。
输出 var/out/loop6_r12_crashspx.md / .json（第二关 loop6_r12_crashspx_stage2_VPS.md / .json）。非投资建议。
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
import research_loop6 as R6                                                  # noqa: E402

ROUND = 12
IDS = ("VPS",)
FAMILY = {"VPS": "核心·指数选择"}
KIND = {"VPS": "signal"}
POSTHOC = True
SPX_T = "1655.T"
NQ_KEY, SP_KEY = "US_VN", "US_VS"
OLD = V.OLD
OUT = "loop6_r12_crashspx"
on_idx = V.on_idx
KEYS = X.KEYS


# ───────────────────────── 规则（纯函数，tests/test_loop6_r12.py） ─────────────────────────
def swap_days(bear_t: pd.Series, sig_t: pd.Series, on_b: pd.Series) -> pd.Series:
    """东证日：换成 S&P500 的日子 = 美股牛 ∧ 信号 ∧ 不是负相关。"""
    idx = on_b.index
    b, s, o = on_idx(bear_t, idx).to_numpy(bool), on_idx(sig_t, idx).to_numpy(bool), on_b.astype(bool).to_numpy()
    return pd.Series(~b & s & ~o, index=idx)


def vps_over(W: dict, M: dict, sig_t: pd.Series) -> dict:
    """B3 的接法 + 1545 / 1655 两个键（任何一天最多一只可拿）；1482 的键 = B3 原样。"""
    days = M["on_b"].index
    b = on_idx(M["bear_t"], days).to_numpy(bool)
    sw = swap_days(M["bear_t"], sig_t, M["on_b"]).to_numpy(bool)
    xc = dict(W["kw"]["Z"]["extra_core"])
    xc[T2.BOND_T] = M["fb"]
    xc[SPX_T] = W["assets"][SPX_T]
    bd = pd.Series(~(b & M["on_b"].astype(bool).to_numpy()), index=days)                   # B3 的 1482 键原样
    return {"cfg_over": {"core": {"1545.T": 1.0, SPX_T: 1.0, T2.BOND_T: 1.0},
                         "core_index": {"1545.T": NQ_KEY, SPX_T: SP_KEY, T2.BOND_T: T2.BD_KEY}, "core_mode": "follow"},
            "extra_core": xc,
            "extra_bear": {NQ_KEY: pd.Series(b | sw, index=days), SP_KEY: pd.Series(b | ~sw, index=days), T2.BD_KEY: bd}}


def core_weights(bear: pd.Series, sig: pd.Series, on: pd.Series) -> pd.DataFrame:
    """只有核心（1987〜2000）的持仓：牛 ∧ 信号 ∧ 不是负相关 → S&P500 1；牛的其余 → 纳指 1；熊 ∧ 负相关 → 美债 1；其余现金。"""
    b, s, o = bear.astype(bool), sig.astype(bool), on.astype(bool)
    sw = ~b & s & ~o
    return pd.DataFrame({"u": (~b & ~sw).astype(float), "sp": sw.astype(float), "b": (b & o).astype(float)}, index=bear.index)


def shifted_signal(sig_t: pd.Series, k: int | None) -> pd.Series:
    return X.shifted_signal(sig_t, k)


def placebo_ks(n: int) -> list[int]:
    return R6.shift_ks(n, 0)


# ───────────────────────── 1987〜2000 只有核心（S7） ─────────────────────────
def old_core(W: dict, sig_us: pd.Series | None) -> dict:
    """第 7 轮 old_core 同一个口径；多一只 S&P500（总收益 − 0.066%，日元计、不对冲，DEXJPUS）；sig_us = None → B3。"""
    import equity_idle_study as EI
    import halloween_study as HW
    inp = W["inp"]
    dex = inp["dexjp"].dropna()
    to_jpy = lambda s: (s * dex.reindex(s.index.union(dex.index)).ffill().reindex(s.index)).dropna()   # noqa: E731
    unh = to_jpy(EI.grow(EI.ndx_tr(inp), -EI.FEE["1545.T"]))
    spj = to_jpy(EI.grow(inp["sptr"].dropna(), -EI.FEE[SPX_T]))
    bnd = T2.bond_hedged(T2.bond_usd())
    bnd = bnd[bnd.index >= pd.Timestamp(T2.BOND_START)]
    spx = inp["spx"]["Close"].astype(float)
    full = unh.index[unh.index >= pd.Timestamp(T2.BOND_START)]
    ffull = lambda s: s.astype(float).reindex(full.union(s.index)).ffill().reindex(full)      # noqa: E731
    on_u = T.corr_on(ffull(spx), ffull(bnd)).shift(1, fill_value=False)
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    unh, b_px, sp_px = unh.reindex(idx), ff(bnd), ff(spj)
    b = ff(W["bear"]["US"]).fillna(0.0) > 0.5
    s = (ff(sig_us).fillna(0.0) > 0.5) if sig_us is not None else pd.Series(False, index=idx)
    ou = ff(on_u).fillna(0.0) > 0.5
    w = core_weights(b, s, ou).shift(1).fillna(0.0)
    ret = (w["u"] * unh.pct_change().fillna(0.0) + w["sp"] * sp_px.pct_change().fillna(0.0)
           + w["b"] * b_px.pct_change().fillna(0.0))
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["spx_days_pct"] = round(float((w["sp"] > 0).mean() * 100), 1)
    return out


# ───────────────────────── 规模 ─────────────────────────
def state_share(bear_t, sig_t, on_b, days) -> dict:
    days = pd.DatetimeIndex(days)
    b, s, o = on_idx(bear_t, days), on_idx(sig_t, days), on_idx(on_b, days)
    bull = ~b
    sw = bull & s & ~o
    nb = int(bull.sum())
    return {"bull_days": nb, "swap_pct": round(float(sw.sum()) / nb * 100, 1) if nb else None, "swap_segments": V.segments(sw)}


def scale(W: dict, M: dict) -> dict:
    out = {e: state_share(M["bear_t"], M["sig_t"], M["on_b"], V.era_days(W, e)) for e in L6.ERAS}
    w = R6.shift_window(M["sig_t"])
    out["window"] = state_share(M["bear_t"], M["sig_t"], M["on_b"], w.index)
    out["shift_n"] = len(w)
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "us_bear": bool(M["bear_t"].iloc[-1]), "signal": bool(M["sig_t"].iloc[-1]),
                     "corr_neg": bool(M["on_b"].iloc[-1])}
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
    M = X.inputs(W)
    ov = vps_over(W, M, M["sig_t"])
    reg = R6.segment(R6.load_state()).get("baseline") or {}
    base, cand, trades = {}, {"VPS": {}}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand["VPS"][e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B3": nb, "VPS": nc}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B3": old_core(W, None), "VPS": old_core(W, M["sig_us"])}
    unseen = None if old["B3"]["calmar"] is None or old["VPS"]["calmar"] is None else old["VPS"]["calmar"] - old["B3"]["calmar"]
    s1 = {"VPS": R6.stage1(cand["VPS"], base, posthoc=unseen)}
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
    s = res["stage1"]["VPS"]
    pv = s["posthoc"]
    L = [f"# 第六个研究循环第三段第 12 轮：急跌且股债不是负相关的牛市里纳指换 S&P500 VPS（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop6_r12_crashspx.py 开头；基准 B3 = Q1B，修正口径）", "",
         f"- **VPS：{'第一关全过 → 另行登记第二关（信号循环平移）' if s['ok'] else R6.FAIL1}**"
         f"（S1 合计 {f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
         f"S4（{f(s['h1'], '{:+.3f}')} / {f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）",
         "", "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | VPS（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{f(x['cagr'], '{:+.2f}')}% / {f(x['dd'], '{:.2f}')}% / {f(x['calmar'])}（{f(x['h1'])} / {f(x['h2'])}）"   # noqa: E731
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['VPS'][e])}（{f(s['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定；规模只数日子）："]
    sc = res["scale"]
    for e in L6.ERAS:
        x = sc[e]
        L.append(f"- {e}：美股牛 {x['bull_days']} 天里换成 S&P500 {f(x['swap_pct'], '{:.1f}')}%（{x['swap_segments']} 段）；"
                 f"核心换仓 B3 {res['core_trades'][e]['B3']} → VPS {res['core_trades'][e]['VPS']} 笔")
    lt = sc["latest"]
    L.append(f"- 最新一天 {lt['date']}：美股{'熊' if lt['us_bear'] else '牛'}、信号 {'是' if lt['signal'] else '否'}、股债负相关 {'是' if lt['corr_neg'] else '否'}")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {f(o[k]['calmar'])}（年化 {f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {f(o[k].get('dd'), '{:.2f}')}%、拿 S&P500 {f(o[k].get('spx_days_pct'), '{:.1f}')}% 的日子）"
        for k in ("B3", "VPS")))
    for e in L6.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["VPS"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（VPS − B3，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    dr = res["drift"]
    L += ["", "B3 与第三段登记值的 Calmar 差：" + "、".join(f"{e} {f(dr[e], '{:+.4f}')}" for e in L6.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R6.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B3）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


def scale_only() -> int:
    W = L6.load3()
    M = X.inputs(W)
    print(json.dumps({"scale": scale(W, M)}, ensure_ascii=False))
    return 0


def wiring() -> int:
    """登记前用：① 信号永远不成立 → B3；② 引擎拿到的 1655 = equity_idle_study.assets 的合成 1655；③ old_core 信号 None = 第 7 轮函数的 B3。"""
    import equity_idle_study as EI
    W = L6.load3()
    M = X.inputs(W)
    never = pd.Series(False, index=M["sig_t"].index)
    ov0 = vps_over(W, M, never)
    same_b3 = {}
    for e in L6.ERAS:
        rb, r0 = L6.run(W, e), L6.run(W, e, **ov0)
        same_b3[e] = bool(all(rb.get(x) == r0.get(x) for x in KEYS))
    fr, _ = EI.assets(W["inp"])
    same_px = bool(fr[SPX_T]["Close"].equals(W["assets"][SPX_T]["Close"]))
    o1, o2 = old_core(W, None), V.old_core(W, None)
    out = {"never_same_as_b3": same_b3, "spx_frame_same": same_px,
           "old_core_b3_same": bool(o1["calmar"] == o2["calmar"] and o1["cagr"] == o2["cagr"])}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if all(same_b3.values()) and same_px and out["old_core_b3_same"] else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次；signal = 信号循环平移） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        kw = vps_over(W, M, shifted_signal(M["sig_t"], ks[int(seed)]))
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
    M = X.inputs(W)
    base = {e: L6.run(W, e)["calmar"] for e in L6.ERAS}
    ov = vps_over(W, M, M["sig_t"])
    cand = {e: L6.run(W, e, **ov)["calmar"] for e in L6.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L6.ERAS), 6)
    n = len(R6.shift_window(M["sig_t"]))
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
    L = [f"# 第六个研究循环第三段第 12 轮 第二关：{k} vs 400 次信号循环平移（{KIND[k]}；B3 不动）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
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
    ap = argparse.ArgumentParser(description="第六个研究循环第三段第 12 轮：VPS")
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
