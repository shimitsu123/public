"""loop6_r08_voltrend.py — 第六个研究循环第三段（基准 B3 = 撤掉 FJE 之后的模拟盘 Q1B，修正口径）第 8 轮：
「高波动且纳指正在跌（收在 50 日线下）的牛市里，股债负相关时把三分之一核心换成对冲版美债」VBT（2026-10-03 登记；先提交后只运行一次；
家族「核心·波动率仓位」这一段 2 / 3；kind = signal；事后 → S7 适用）。

用户（2026-10-03）：㊼ ①「重新检验，不过就撤」（只回答编号 = 同时同意：第六个循环按修正口径重算基准、计数接着 7 / 20、照现行规则选题）；
之前「…没有时间限制 一直找到比现在算法更好的」。循环的规则：scripts/research_loop6.py（第三段 = 开头「九」与末尾一节）；基准 B3：scripts/loop6_common.load3。
为什么做这个（照实写；看过第 7 轮 VBH 的结果与 B3 的回撤分段之后设计 = 事后）：
  - 第 7 轮 VBH（高波动 ∧ 负相关的牛市日子 1545 : 1482 = 2 : 1）第一关不过（+0.179）：J +0.194、E +0.092 —— 最大回撤 J −29.61% → −22.03%、
    E −23.19% → −19.93%；但 Z −0.107（2003 年熊市后的反弹里波动仍高 → 1/3 美债少赚 9.3 pp）、E 2014〜2016 −12.9 pp、J 2018〜2021 −10.7 pp。
    VT20 的高波动在下跌之后还要持续很久（σ20 回到中位数以下才算结束）→ 一大半拿美债的日子落在反弹里。
  - 只看 B3 的回撤分段（本会话，不跑候选）：E / J 最深的几段多半在美股分界还是「牛」、股债负相关的时候开始 ——
    J 2020-02-20〜03-13 −29.61%、2022-01-04〜03-09 −19.22%、2018-10-04〜11-21 −15.74%；E 2011-02〜10 −23.19%、2010-04〜07 −17.10%、2007-07〜08 −15.22%
    （这几段负相关的日子 96〜100%）；J 2024-07〜08 −21.34%、2025-01〜04 −23.54% 与 Z 2006-04〜07 −14.29% 负相关很少（0〜17%）→ 债券帮不上。
  → 只在「正在跌」的时候拿美债：高波动 且 纳指总收益（美元）收在自己的 50 日均线下；回到线上（或波动回落）就全拿 1545。
做法 VBT（VT20 的波动率状态与参数原样、BCU 的相关条件原样、2 : 1 同第 7 轮；50 日线是常用的固定值、不是学出来的 → S6 不适用；不改个股 → S5 不适用）：
  - 高波动 = 第 7 轮 VBH 原样（loop6_r07_volbond.vt_ratio / high_vol：美元计纳指总收益 σ20、VT20 的比例 < 1）。
  - 正在跌 = 同一条美元计纳指总收益（equity_idle_study.ndx_tr）的收盘 < 它自己的 50 日简单均线（至少 50 个值；美国交易日）。
  - 信号 = 高波动 ∧ 正在跌（美国交易日）；东证交易日 d = d 之前（含 d 的日期）最近一个美国收盘的状态（与 B3 的「美股熊」同一个对齐）。
  - 美股牛 ∧ 信号 ∧ 股债 63 天负相关 → 核心 1545 : 1482 = 2 : 1；其余同 B3（接法 = 第 7 轮 vbh_over，把「高波动」换成这个信号）。
第一关：research_loop6.stage1（S1〜S4 + S7：1987〜2000 只有核心 VBT − B3 > 0；只有核心的口径 = 第 7 轮 old_core，把高波动换成这个信号）。
第二关（第一关全过才做；另行登记后只运行一次；代码写在本脚本 --stage2）：kind = signal —— 候选自己新加的信号 =「高波动 ∧ 正在跌」（东证日上的布尔序列）
  在 2000-01-04〜2026-09-30 的东证交易日上整体循环平移 k（research_loop6.shift_ks(n, 0)：种子 [20261006, 0, s]），窗外不动；
  B3（美股熊、股债相关、价格）不动。候选的 Calmar 差合计要严格大于 400 次的最大值（有算不出的 = 不过）。
接线核对（登记前，不看候选的结果；--wiring）：① 信号永远不成立 → 三个年代与 B3 逐项相同；② 信号 = 高波动（正在跌永远成立）→ 三个年代与第 7 轮 VBH
  已公开的账户（var/out/loop6_r07_volbond.json）逐项相同（同一条代码路径）；③ old_core 的 B3 两种写法相同。
只描述（不参与判定）：各年代美股牛日子里信号 / 信号且负相关（= 与 B3 不同的日子）的比例与段数、其中 VBH 也拿美债的比例；核心换仓笔数；每年收益差；
  1987〜2000 的同样数字；最新一天的状态。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop6_r08_voltrend.py（第一关）；--scale（只数日子）；--wiring（登记前的接线核对）；--stage2 VBT [--workers N]（第二关）。
输出 var/out/loop6_r08_voltrend.md / .json（第二关 loop6_r08_voltrend_stage2_VBT.md / .json）。非投资建议。
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
import loop6_r07_volbond as V                                                # noqa: E402
import research_loop6 as R6                                                  # noqa: E402

ROUND = 8
IDS = ("VBT",)
FAMILY = {"VBT": "核心·波动率仓位"}
KIND = {"VBT": "signal"}
POSTHOC = True
TREND_N = 50                                                                 # 纳指总收益（美元）的 50 日简单均线
OLD = V.OLD
OUT = "loop6_r08_voltrend"
REF7 = "loop6_r07_volbond.json"                                              # 接线核对 ②：第 7 轮 VBH 已公开的账户
on_idx = V.on_idx
KEYS = ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2")


# ───────────────────────── 规则（纯函数，tests/test_loop6_r08.py） ─────────────────────────
def trend_down(ndx_tr: pd.Series, n: int = TREND_N) -> pd.Series:
    """正在跌 = 收盘 < 自己的 n 日简单均线（至少 n 个值；不够 → False）。"""
    s = ndx_tr.dropna().sort_index().astype(float)
    ma = s.rolling(n, min_periods=n).mean()
    return pd.Series((s < ma).to_numpy(bool), index=s.index)


def signal(ratio: pd.Series, down: pd.Series) -> pd.Series:
    """信号（美国交易日）= 高波动（VT20 比例 < 1）∧ 正在跌；两边日期取交集。"""
    idx = ratio.index.intersection(down.index)
    h = V.high_vol(ratio.reindex(idx))
    return pd.Series(h.to_numpy(bool) & down.reindex(idx).astype(bool).to_numpy(), index=idx)


def vbt_over(W: dict, M: dict, sig_t: pd.Series) -> dict:
    """第 7 轮 vbh_over 原样，「高波动」换成这个信号（东证日）。"""
    return V.vbh_over(W, M, sig_t)


def shifted_signal(sig_t: pd.Series, k: int | None) -> pd.Series:
    """第二关：信号在 2000-01-04〜J 的最后一天上整体循环平移 k（None = 不平移），窗外不动（同第 7 轮 shifted_high）。"""
    return V.shifted_high(sig_t, k)


def placebo_ks(n: int) -> list[int]:
    return R6.shift_ks(n, 0)


def old_core(W: dict, sig_us: pd.Series | None) -> dict:
    """1987〜2000 只有核心：第 7 轮 old_core 原样，高波动换成这个信号（None → B3）。"""
    return V.old_core(W, sig_us)


# ───────────────────────── 输入 / 规模 ─────────────────────────
def inputs(W: dict) -> dict:
    """第 7 轮的输入（W["bcu"] + VT20 比例 / 高波动）+ 正在跌 / 信号（美国日）+ 东证日上的信号。"""
    import equity_idle_study as EI
    M = V.inputs(W)
    tr = EI.ndx_tr(W["inp"])
    down = trend_down(tr)
    sig = signal(M["ratio_us"], down)
    M.update({"down_us": down, "sig_us": sig, "sig_t": on_idx(sig, M["days"])})
    return M


def state_share(bear_t, sig_t, high_t, on_b, days) -> dict:
    """这段日子里：美股牛的天数、其中信号 / 信号且负相关（= 与 B3 不同的日子）的比例与段数、信号且负相关的日子里 VBH 也拿美债的比例（只数日子）。"""
    days = pd.DatetimeIndex(days)
    b, s, h, o = on_idx(bear_t, days), on_idx(sig_t, days), on_idx(high_t, days), on_idx(on_b, days)
    bull = ~b
    mix = bull & s & o
    vbh_mix = bull & h & o
    nb = int(bull.sum())
    pct = lambda x: round(float(x) / nb * 100, 1) if nb else None                  # noqa: E731
    return {"bull_days": nb, "sig_pct": pct(int((bull & s).sum())), "mix_pct": pct(int(mix.sum())), "mix_segments": V.segments(mix),
            "vbh_mix_pct": pct(int(vbh_mix.sum())), "vbh_mix_segments": V.segments(vbh_mix),
            "kept_of_vbh_pct": round(float((mix & vbh_mix).sum()) / max(1, int(vbh_mix.sum())) * 100, 1)}


def scale(W: dict, M: dict) -> dict:
    out = {e: state_share(M["bear_t"], M["sig_t"], M["high_t"], M["on_b"], V.era_days(W, e)) for e in L6.ERAS}
    w = R6.shift_window(M["sig_t"])
    out["window"] = state_share(M["bear_t"], M["sig_t"], M["high_t"], M["on_b"], w.index)
    out["sig_share_2000_2026"] = round(float(w.mean() * 100), 1)
    out["shift_n"] = len(w)
    bu = W["bear"]["US"]
    old = M["sig_us"][(M["sig_us"].index >= pd.Timestamp(OLD[0])) & (M["sig_us"].index <= pd.Timestamp(OLD[1]))]
    bo = on_idx(bu, old.index)
    out["old_sig_bull_pct"] = round(float((old & ~bo).sum() / max(1, int((~bo).sum())) * 100), 1)
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "us_bear": bool(M["bear_t"].iloc[-1]), "high_vol": bool(M["high_t"].iloc[-1]),
                     "down": bool(on_idx(M["down_us"], M["days"]).iloc[-1]), "corr_neg": bool(M["on_b"].iloc[-1]),
                     "vt_ratio": round(float(M["ratio_us"].dropna().iloc[-1]), 3)}
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
    ov = vbt_over(W, M, M["sig_t"])
    reg = R6.segment(R6.load_state()).get("baseline") or {}
    base, cand, trades = {}, {"VBT": {}}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand["VBT"][e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B3": nb, "VBT": nc}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B3": old_core(W, None), "VBT": old_core(W, M["sig_us"])}
    unseen = None if old["B3"]["calmar"] is None or old["VBT"]["calmar"] is None else old["VBT"]["calmar"] - old["B3"]["calmar"]
    s1 = {"VBT": R6.stage1(cand["VBT"], base, posthoc=unseen)}
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
    s = res["stage1"]["VBT"]
    pv = s["posthoc"]
    L = [f"# 第六个研究循环第三段第 8 轮：高波动且纳指在 50 日线下的牛市里、股债负相关时三分之一核心换对冲版美债 VBT（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop6_r08_voltrend.py 开头；基准 B3 = Q1B，修正口径）", "",
         f"- **VBT：{'第一关全过 → 另行登记第二关（信号循环平移）' if s['ok'] else R6.FAIL1}**"
         f"（S1 合计 {f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
         f"S4（{f(s['h1'], '{:+.3f}')} / {f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）",
         "", "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | VBT（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{f(x['cagr'], '{:+.2f}')}% / {f(x['dd'], '{:.2f}')}% / {f(x['calmar'])}（{f(x['h1'])} / {f(x['h2'])}）"   # noqa: E731
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['VBT'][e])}（{f(s['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定；规模只数日子）："]
    sc = res["scale"]
    for e in L6.ERAS:
        x = sc[e]
        L.append(f"- {e}：美股牛 {x['bull_days']} 天里信号 {f(x['sig_pct'], '{:.1f}')}%、信号且负相关（与 B3 不同的日子）{f(x['mix_pct'], '{:.1f}')}%"
                 f"（{x['mix_segments']} 段；第 7 轮 VBH {f(x['vbh_mix_pct'], '{:.1f}')}%、{x['vbh_mix_segments']} 段，VBH 的日子留下 {f(x['kept_of_vbh_pct'], '{:.1f}')}%）；"
                 f"核心换仓 B3 {res['core_trades'][e]['B3']} → VBT {res['core_trades'][e]['VBT']} 笔")
    lt = sc["latest"]
    L.append(f"- 信号在 2000〜2026 全部东证日里的比例 {sc['sig_share_2000_2026']}%；最新一天 {lt['date']}：美股{'熊' if lt['us_bear'] else '牛'}、"
             f"高波动 {'是' if lt['high_vol'] else '否'}（VT20 比例 {lt['vt_ratio']}）、纳指在 50 日线下 {'是' if lt['down'] else '否'}、"
             f"股债负相关 {'是' if lt['corr_neg'] else '否'}")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {f(o[k]['calmar'])}（年化 {f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {f(o[k].get('dd'), '{:.2f}')}%、"
        f"纳指 + 美债一起拿 {f(o[k].get('mix_days_pct'), '{:.1f}')}% 的日子）" for k in ("B3", "VBT"))
        + f"；美股牛的日子里信号 {f(o['VBT'].get('high_bull_pct'), '{:.1f}')}%")
    for e in L6.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["VBT"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（VBT − B3，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
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
    """登记前用：① 信号永远不成立 → 三个年代与 B3 逐项相同；② 信号 = 高波动 → 与第 7 轮 VBH 已公开的账户逐项相同；③ old_core 的 B3 两种写法相同。"""
    from qbreak import paths
    W = L6.load3()
    M = inputs(W)
    never = pd.Series(False, index=M["sig_t"].index)
    ov0 = vbt_over(W, M, never)
    same_b3 = {}
    for e in L6.ERAS:
        rb, r0 = L6.run(W, e), L6.run(W, e, **ov0)
        same_b3[e] = bool(all(rb.get(x) == r0.get(x) for x in KEYS))
    ref = json.loads((paths.out_dir() / REF7).read_text(encoding="utf-8"))["cand"]["VBH"]
    ovh = vbt_over(W, M, M["high_t"])
    same_vbh = {}
    for e in L6.ERAS:
        r = L6.run(W, e, **ovh)
        same_vbh[e] = bool(all(r.get(x) == ref[e].get(x) for x in ("cagr", "dd", "calmar", "h1", "h2", "n")))
    o1, o2 = old_core(W, None), old_core(W, pd.Series(False, index=M["sig_us"].index))
    out = {"never_same_as_b3": same_b3, "high_only_same_as_vbh": same_vbh,
           "old_core_same": bool(o1["calmar"] == o2["calmar"] and o1["cagr"] == o2["cagr"])}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if all(same_b3.values()) and all(same_vbh.values()) and out["old_core_same"] else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次；signal = 信号循环平移） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        kw = vbt_over(W, M, shifted_signal(M["sig_t"], ks[int(seed)]))
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
    ov = vbt_over(W, M, M["sig_t"])
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
    L = [f"# 第六个研究循环第三段第 8 轮 第二关：{k} vs 400 次信号循环平移（{KIND[k]}；B3 不动）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
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
    ap = argparse.ArgumentParser(description="第六个研究循环第三段第 8 轮：VBT")
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
