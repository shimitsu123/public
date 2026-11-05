"""core_points_study.py — 核心 ETF（闲置资金）的买卖点：两个以前没试过的做法（2026-10-11 登记；先提交后只运行一次）。

用户（2026-10-11）：「研究核心 ETF 的买卖点等等，横展开，让利益最大化」。
现行（基准 B3 = 模拟盘的闲置资金 Q1B，修正口径；scripts/loop6_common.load3）：美股牛（S&P500 牛熊分界：250 日线 ±3%、连续 5 天）→ 纳指 1545；
美股熊且股债 63 天负相关 → 对冲版美债 1482；其余现金。
以前试过、都没通过的（不再重复）：牛熊分界的参数、快速离场（ZBX）、双速离场（TB7）、分批切换（TR3）、纳指先转牛早拿回（NDB）、
纳指转熊换 S&P（NSX）、波动率仓位（VT20 / VTU / VTD / VBH / VBT / VCT）、杠杆（LV25 / TOML）、季节 / 月末（H1 / H2 / TOMB）、汇率对冲（FJE 等）、
避险资产（R10 / TBH / TBJ / TBU / BAJ…）、熊市里拿回一部分（BPR）、利率 / 信用急变（RSC / CSV / RXC）、按局面选模型（S1〜S4 / M1〜M3）。
这次两个做法（家族「核心·买卖点」；kind = signal；看过以前的结果之后设计 → 按事后处理，S7 适用；没有学参数 → S6 不适用；不改个股 → S5 不适用）：
  OXT「过热时先卖三分之一」：美股牛里，纳指总收益（美元）比自己的 200 日简单均线高 ≥ 20% 时进入「过热」、回到 ≤ 10% 才解除（滞回）；
       过热的日子 1545 只拿目标的 2/3，1/3 留现金。参数（200 日、+20% / +10%、1/3）事先定、不调。
  NXC「纳指自己转熊先离场」：美股（S&P500）还是牛、但纳指自己按同一个牛熊检测器（250 日线 ±3%、连续 5 天，equity_idle_study.t0_bear）已经转熊 →
       1545 拿 0（现金）；纳指转回牛（或 S&P 转熊、照 B3）为止。与 NSX 不同：NSX 换成 S&P500，这里留现金。
接法：引擎的 core_expo["US"]（1545 的目标再乘：OXT 过热的牛市日子 = 2/3、NXC 纳指熊的牛市日子 = 0，其余 = 1）；东证日的对齐同 B3 的「美股熊」
  （loop6_r07_volbond.on_idx：东证 d 日用前一个美国收盘的状态）。
第一关：research_loop6.stage1（S1 三个年代 Calmar 差合计 ≥ +0.03、S2 每个 ≥ −0.02、S3 最大回撤不深于 2 pp、S4 前后两半各 ≥ 0、
  S7 1987〜2000 只有核心（日元计纳指、同 VCT 的 old_core 口径）候选 − B3 > 0）。
第二关（第一关全过才做；事先写定，本脚本 --stage2，只运行一次）：候选自己的信号（东证日布尔序列）在 2000-01-04〜J 的最后一天上整体循环平移 k
  （research_loop6.shift_ks(n, 0)，400 次），B3 不动；候选的 Calmar 差合计要严格大于 400 次的最大值。
两关都过 = 「更好候选」→ 只提议（改模拟盘要用户决定）。
事前预期（看结果之前写）：以前 60 多个核心择时都没通过、第二关单一序列的择时 0 / 8 → 这两个大概率也不通过；OXT 可能减少回撤但少赚涨势后段，
  NXC 在 2000〜2002、2022 年可能有利、但纳指 / S&P 分歧的假信号会拖后腿。
运行：python scripts/core_points_study.py（第一关）；--stage2 OXT|NXC [--workers N]。输出 var/out/core_points_study.md / .json。非投资建议。
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
import loop6_r07_volbond as V                                                # noqa: E402
import research_loop6 as R6                                                  # noqa: E402

IDS = ("OXT", "NXC")
FAMILY = {"OXT": "核心·买卖点", "NXC": "核心·买卖点"}
KIND = {"OXT": "signal", "NXC": "signal"}
POSTHOC = True
MA_N, HOT_IN, HOT_OUT = 200, 20.0, 10.0                                      # OXT：200 日线、≥ +20% 进入过热、≤ +10% 解除
KEEP = {"OXT": 2.0 / 3.0, "NXC": 0.0}                                        # 信号成立的美股牛日子里 1545 拿目标的几成
OUT = "core_points_study"
on_idx = V.on_idx


# ───────────────────────── 规则（纯函数，tests/test_core_points_study.py） ─────────────────────────
def overheat(tr: pd.Series, n: int = MA_N, hot_in: float = HOT_IN, hot_out: float = HOT_OUT) -> pd.Series:
    """美国日：比 n 日简单均线高 ≥ hot_in % 进入过热，≤ hot_out % 解除（滞回）；均线算不出的日子 = 不过热。"""
    c = tr.astype(float).dropna()
    gap = (c / c.rolling(n).mean() - 1) * 100
    out, st = np.zeros(len(c), bool), False
    for i, g in enumerate(gap.to_numpy()):
        if not np.isfinite(g):
            st = False
        elif not st and g >= hot_in:
            st = True
        elif st and g <= hot_out:
            st = False
        out[i] = st
    return pd.Series(out, index=c.index)


def expo(bear_t: pd.Series, sig_t: pd.Series, keep: float) -> pd.Series:
    """东证日：1545 目标再乘的比例 = 美股牛 ∧ 信号 → keep，其余 1。"""
    idx = sig_t.index
    b = on_idx(bear_t, idx).to_numpy(bool)
    s = sig_t.astype(bool).to_numpy()
    return pd.Series(np.where(~b & s, keep, 1.0), index=idx)


def cand_over(M: dict, k: str, sig_t: pd.Series) -> dict:
    return {"core_expo": {"US": expo(M["bear_t"], sig_t, KEEP[k])}}


def signals_us(W: dict) -> dict[str, pd.Series]:
    import equity_idle_study as EI
    return {"OXT": overheat(EI.ndx_tr(W["inp"])), "NXC": EI.t0_bear(W["inp"]["ndx"]).astype(bool)}


def inputs(W: dict) -> dict:
    M = V.inputs(W)
    sus = signals_us(W)
    M["sig_us"] = sus
    M["sig_t"] = {k: on_idx(s, M["days"]) for k, s in sus.items()}
    return M


# ───────────────────────── 1987〜2000 只有核心（S7） ─────────────────────────
def old_core(W: dict, sig_us: pd.Series | None, keep: float) -> dict:
    """同 VCT 的 old_core 口径（日元计纳指不对冲、对冲版美债、S&P 与美债 63 天相关（前一天）、前一天的状态决定当天、换仓扣 0.1% × 换的比例）；
    持仓 = B3（牛 → 纳指 1；熊 ∧ 负相关 → 美债 1；其余现金），牛 ∧ 信号 → 纳指 × keep。sig_us = None → B3。"""
    import equity_idle_study as EI
    import halloween_study as HW
    import loop2_r02_bondrefuge as T2
    import loop6_r01_bondcorr as T
    inp = W["inp"]
    dex = inp["dexjp"].dropna()
    unh = EI.grow(EI.ndx_tr(inp), -EI.FEE["1545.T"])
    unh = (unh * dex.reindex(unh.index.union(dex.index)).ffill().reindex(unh.index)).dropna()
    bnd = T2.bond_hedged(T2.bond_usd())
    bnd = bnd[bnd.index >= pd.Timestamp(T2.BOND_START)]
    spx = inp["spx"]["Close"].astype(float)
    full = unh.index[unh.index >= pd.Timestamp(T2.BOND_START)]
    ffull = lambda s: s.astype(float).reindex(full.union(s.index)).ffill().reindex(full)      # noqa: E731
    on_u = T.corr_on(ffull(spx), ffull(bnd)).shift(1, fill_value=False)
    idx = unh.index[(unh.index >= pd.Timestamp(V.OLD[0])) & (unh.index <= pd.Timestamp(V.OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    unh, b_px = unh.reindex(idx), ff(bnd)
    b = ff(W["bear"]["US"]).fillna(0.0) > 0.5
    s = (ff(sig_us).fillna(0.0) > 0.5) if sig_us is not None else pd.Series(False, index=idx)
    ou = ff(on_u).fillna(0.0) > 0.5
    w = pd.DataFrame({"u": np.where(~b, 1.0, 0.0), "b": np.where(b & ou, 1.0, 0.0)}, index=idx)
    w.loc[~b & s, "u"] = keep
    w = w.shift(1).fillna(0.0)
    ret = w["u"] * unh.pct_change().fillna(0.0) + w["b"] * b_px.pct_change().fillna(0.0)
    turn = w.diff().abs().sum(axis=1).fillna(w.iloc[0].abs().sum())
    eq = pd.Series(np.cumprod(1 + ret.to_numpy() - turn.to_numpy() * HW.SWITCH_COST / 100), index=idx)
    out = EI.curve_stats(eq)
    out["sig_bull_pct"] = round(float((s & ~b).sum() / max(1, int((~b).sum())) * 100), 1)
    return out


# ───────────────────────── 运行 ─────────────────────────
def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win", "years")}


def share(M: dict, k: str, days) -> dict:
    days = pd.DatetimeIndex(days)
    b, s = on_idx(M["bear_t"], days), on_idx(M["sig_t"][k], days)
    bull = ~b
    on = bull & s
    nb = int(bull.sum())
    return {"bull_days": nb, "sig_pct": round(float(on.sum()) / nb * 100, 1) if nb else None, "segments": V.segments(on)}


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = V.git_head()
    W = L6.load3()
    M = inputs(W)
    base = {e: _acct(L6.run(W, e)) for e in L6.ERAS}
    cand, s1, old, sc = {}, {}, {"B3": old_core(W, None, 1.0)}, {}
    for k in IDS:
        ov = cand_over(M, k, M["sig_t"][k])
        cand[k] = {e: _acct(L6.run(W, e, **ov)) for e in L6.ERAS}
        old[k] = old_core(W, M["sig_us"][k], KEEP[k])
        uns = None if old["B3"]["calmar"] is None or old[k]["calmar"] is None else old[k]["calmar"] - old["B3"]["calmar"]
        s1[k] = R6.stage1(cand[k], base, posthoc=uns)
        sc[k] = {e: share(M, k, V.era_days(W, e)) for e in L6.ERAS}
        sc[k]["latest"] = {"date": str(M["days"][-1].date()), "signal": bool(M["sig_t"][k].iloc[-1]), "us_bear": bool(M["bear_t"].iloc[-1])}
        print(f"{k} 完成（{time.time() - t0:.0f}s）", flush=True)
    res = {"study": OUT, "ids": list(IDS), "family": FAMILY, "kind": KIND, "posthoc": POSTHOC, "code": code, "dirty": dirty,
           "base": base, "cand": cand, "stage1": s1, "old": old, "scale": sc, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def write(res: dict) -> None:
    from qbreak import paths
    f = V._f
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    name = {"OXT": "过热时先卖三分之一", "NXC": "纳指自己转熊先离场（现金）"}
    L = [f"# 核心 ETF 的买卖点：OXT / NXC（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；"
         "规则见 scripts/core_points_study.py 开头；基准 B3 = 现行闲置资金 Q1B，修正口径）", ""]
    cell = lambda x: f"{f(x['cagr'], '{:+.2f}')}% / {f(x['dd'], '{:.2f}')}% / {f(x['calmar'])}"   # noqa: E731
    for k in IDS:
        s = res["stage1"][k]
        pv = s["posthoc"]
        L.append(f"- **{k}（{name[k]}）：{'第一关全过 → 第二关（信号循环平移）' if s['ok'] else R6.FAIL1}**"
                 f"（S1 合计 {f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
                 f"S4（{f(s['h1'], '{:+.3f}')} / {f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；S7（1987〜2000 只有核心 {f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}）")
    L += ["", "| 年代 | B3 年化 / 最大回撤 / Calmar | OXT（Calmar 差） | NXC（Calmar 差） |", "|---|---|---|---|"]
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | " + " | ".join(
            f"{cell(res['cand'][k][e])}（{f(res['stage1'][k]['d'][e], '{:+.3f}')}）" for k in IDS) + " |")
    L += ["", "只描述（不参与判定）："]
    for k in IDS:
        sc = res["scale"][k]
        L.append(f"- {k}：美股牛的日子里信号成立 " + "、".join(f"{e} {f(sc[e]['sig_pct'], '{:.1f}')}%（{sc[e]['segments']} 段）" for e in L6.ERAS)
                 + f"；最新一天 {sc['latest']['date']} 信号 {'是' if sc['latest']['signal'] else '否'}")
        for e in L6.ERAS:
            yb, yc = res["base"][e].get("years") or {}, res["cand"][k][e].get("years") or {}
            diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
            L.append(f"  - {e} 每年收益差（{k} − B3，pp）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7）：" + "、".join(f"{k} Calmar {f(o[k]['calmar'])}（年化 {f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {f(o[k].get('dd'), '{:.2f}')}%）"
                                                  for k in ("B3",) + IDS))
    L += ["", f"用时 {res['seconds']} s。只研究，不改模拟盘 / 执行器。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


# ───────────────────────── 第二关（第一关全过才做；只运行一次） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, base, ks, k = _G["W"], _G["M"], _G["base"], _G["ks"], _G["k"]
    try:
        kw = cand_over(M, k, V.shifted_high(M["sig_t"][k], ks[int(seed)]))
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
    W = L6.load3()
    M = inputs(W)
    base = {e: L6.run(W, e)["calmar"] for e in L6.ERAS}
    ov = cand_over(M, k, M["sig_t"][k])
    stat = round(sum(L6.run(W, e, **ov)["calmar"] - base[e] for e in L6.ERAS), 6)
    ks = R6.shift_ks(len(R6.shift_window(M["sig_t"][k])), 0)
    _G.update({"W": W, "M": M, "base": base, "ks": ks, "k": k})
    seeds = list(range(R6.PLACEBO_N))
    if workers > 1:
        with mp.get_context("fork").Pool(workers) as pool:
            vals = list(pool.imap(_placebo_one, seeds))
    else:
        vals = [_placebo_one(i) for i in seeds]
    s2 = R6.stage2(stat, vals)
    vd = R6.verdict(s1, s2)
    text = (f"# 核心 ETF 的买卖点 第二关：{k} vs 400 次信号循环平移（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}）\n\n"
            f"**{vd}**：候选 {stat:+.4f}；400 次里最大 {V._f(s2['max'], '{:+.4f}')}、≥ 候选 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']}；"
            f"用时 {round(time.time() - t0)} s。非投资建议。\n")
    print(text)
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps({"id": k, "stat": stat, "stage2": s2, "verdict": vd, "placebo": vals},
                                                                       ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="核心 ETF 的买卖点：OXT / NXC")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
