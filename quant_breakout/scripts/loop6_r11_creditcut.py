"""loop6_r11_creditcut.py — 第六个研究循环第三段（基准 B3 = 撤掉 FJE 之后的模拟盘 Q1B，修正口径）第 11 轮：
「信用利差急速走阔（Moody's Baa − 10 年美债，20 个营业日上升 ≥ 0.20 pp）的牛市里，三分之一核心离开纳指（负相关 → 对冲版美债、否则现金）」CSV
（2026-10-03 登记；先提交后只运行一次；家族「核心·信用利差」新家族 1 / 3；kind = signal；事后 → S7 适用）。

用户（2026-10-03）：㊼ ①「重新检验，不过就撤」（只回答编号 = 同时同意：第六个循环按修正口径重算基准、计数接着 7 / 20、照现行规则选题）；
之前「…没有时间限制 一直找到比现在算法更好的」。循环的规则：scripts/research_loop6.py（第三段 = 开头「九」与末尾一节）；基准 B3：scripts/loop6_common.load3。
为什么做这个（照实写；看过第 7〜10 轮的结果之后设计 = 事后）：
  - 第 9 轮 VCT（牛市里「高波动 ∧ 纳指在 50 日线下」时 1/3 离开纳指）第一关全过、第二关约第 97 百分位 —— 「急跌时少拿一部分纳指」的接法有用，
    但信号只用了价格本身。这一轮换一个独立的信息来源：信用市场。信用利差急速走阔 = 债券市场在给违约风险加价（2007-07〜08、2007-11、2010-05、
    2018-11〜12、2020-02〜03、2022-02〜03、2025-03〜04、1998-08、2000-03〜04）。
  - 选参数前只数了状态（本会话；没看收益）：20 个营业日上升 ≥ 0.20 pp 开、< 0.10 pp 关，牛市日子里成立 1987〜2000 8.0%（24 段）、Z 3.1%（2 段）、
    E 10.1%（12 段）、J 5.7%（9 段）。0.20 / 0.10 / 20 天是整数的常用值，看过状态之后没有改。
  - 家族按信号来源分（同第 7〜9 轮按波动率归「核心·波动率仓位」）→「核心·信用利差」新家族；接法与 VCT 相同（只换信号）。
做法 CSV（没有学出来的参数 → S6 不适用；不改个股 → S5 不适用）：
  - 信用利差 = FRED BAA10Y（营业日）；FRED 晚一个营业日发布 → 美国 d 日只用 d 之前一个 FRED 日的值；20 个 FRED 营业日的变化 ≥ 0.20 pp → 开，
    < 0.10 pp → 关（中间保持）；东证日的对齐同 B3 的「美股熊」（d 之前含 d 的最近一个美国日的状态）。
  - 美股牛 ∧ 信号 ∧ 股债 63 天负相关 → 1545 : 1482 = 2 : 1；美股牛 ∧ 信号 ∧ 不是负相关 → 1545 拿 2/3、1/3 现金；其余同 B3
    （接法 = loop6_r09_volcash.vct_over，信号换成这个）。
第一关：research_loop6.stage1（S1〜S4 + S7：1987〜2000 只有核心 CSV − B3 > 0；口径 = 第 9 轮 old_core，信号换成这个）。
第二关（第一关全过才做；另行登记后只运行一次；代码写在本脚本 --stage2）：kind = signal —— 候选自己新加的信号「信用利差急速走阔」（东证日上的布尔序列）
  在 2000-01-04〜2026-09-30 的东证交易日上整体循环平移 k（research_loop6.shift_ks(n, 0)：种子 [20261006, 0, s]），窗外不动；美债与现金两部分都跟着
  平移后的信号重算；B3 不动。候选的 Calmar 差合计要严格大于 400 次的最大值（有算不出的 = 不过）。
接线核对（登记前，不看候选的结果；--wiring）：① 信号永远不成立 → 三个年代与 B3 逐项相同；② 信号换成第 9 轮 VCT 的信号 → 三个年代与 VCT 已公开的账户
  （var/out/loop6_r09_volcash.json）逐项相同（同一条代码路径）；③ old_core 信号 None = 第 7 轮函数算的 B3。
只描述（不参与判定）：各年代美股牛日子里信号且负相关（拿美债）/ 信号且不是负相关（留现金）的比例与段数；核心换仓笔数；每年收益差；1987〜2000；最新一天的状态。
事前预期：写在登记（var/sim_changes.md）里、看结果之前。
运行：python scripts/loop6_r11_creditcut.py（第一关）；--scale（只数日子）；--wiring（登记前的接线核对）；--stage2 CSV [--workers N]（第二关）。
输出 var/out/loop6_r11_creditcut.md / .json（第二关 loop6_r11_creditcut_stage2_CSV.md / .json）。非投资建议。
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
import loop6_r08_voltrend as X                                               # noqa: E402
import loop6_r09_volcash as C                                                # noqa: E402
import research_loop6 as R6                                                  # noqa: E402

ROUND = 11
IDS = ("CSV",)
FAMILY = {"CSV": "核心·信用利差"}
KIND = {"CSV": "signal"}
POSTHOC = True
SERIES = "BAA10Y"
WIN = 20                                                                     # 20 个 FRED 营业日的变化
ON, OFF = 0.20, 0.10                                                         # pp：≥ 0.20 开、< 0.10 关
OLD = V.OLD
OUT = "loop6_r11_creditcut"
REF9 = "loop6_r09_volcash.json"                                              # 接线核对 ②：第 9 轮 VCT 已公开的账户
on_idx = V.on_idx
KEYS = X.KEYS


# ───────────────────────── 规则（纯函数，tests/test_loop6_r11.py） ─────────────────────────
def widening(spread: pd.Series, win: int = WIN, on: float = ON, off: float = OFF) -> pd.Series:
    """FRED 日期上的信号：先用前一个 FRED 日的值（晚一天发布），win 个营业日的变化 ≥ on 开、< off 关、中间保持；变化算不出 = 关。"""
    s = spread.dropna().sort_index().astype(float).shift(1)
    chg = (s - s.shift(win)).to_numpy()
    out = np.zeros(len(chg), bool)
    st = False
    for i, v in enumerate(chg):
        if not np.isfinite(v):
            st = False
        elif not st and v >= on - 1e-12:
            st = True
        elif st and v < off - 1e-12:
            st = False
        out[i] = st
    return pd.Series(out, index=s.index)


def csv_over(W: dict, M: dict, sig_t: pd.Series) -> dict:
    """第 9 轮 vct_over 原样（牛 ∧ 信号：负相关 → 1545 : 1482 = 2 : 1、否则 1545 2/3 + 现金），信号换成信用利差急速走阔。"""
    return C.vct_over(W, M, sig_t)


def shifted_signal(sig_t: pd.Series, k: int | None) -> pd.Series:
    return X.shifted_signal(sig_t, k)


def placebo_ks(n: int) -> list[int]:
    return R6.shift_ks(n, 0)


def old_core(W: dict, sig_us: pd.Series | None) -> dict:
    return C.old_core(W, sig_us)


# ───────────────────────── 输入 / 规模 ─────────────────────────
def inputs(W: dict) -> dict:
    """第 8 轮的输入（W["bcu"]、美股熊、VCT 的信号等）+ 信用利差信号（FRED 日期 → 东证日）。"""
    from qbreak import factors as F
    M = X.inputs(W)
    cs = widening(F.fred(SERIES))
    M.update({"csv_us": cs, "csv_t": on_idx(cs, M["days"])})
    return M


def scale(W: dict, M: dict) -> dict:
    out = {e: C.state_share(M["bear_t"], M["csv_t"], M["on_b"], V.era_days(W, e)) for e in L6.ERAS}
    w = R6.shift_window(M["csv_t"])
    out["window"] = C.state_share(M["bear_t"], M["csv_t"], M["on_b"], w.index)
    out["sig_share_2000_2026"] = round(float(w.mean() * 100), 1)
    out["shift_n"] = len(w)
    out["overlap_with_vct_pct"] = round(float((M["csv_t"] & M["sig_t"]).sum() / max(1, int(M["csv_t"].sum())) * 100), 1)
    last = M["days"][-1]
    out["latest"] = {"date": str(last.date()), "us_bear": bool(M["bear_t"].iloc[-1]), "signal": bool(M["csv_t"].iloc[-1]),
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
    M = inputs(W)
    ov = csv_over(W, M, M["csv_t"])
    reg = R6.segment(R6.load_state()).get("baseline") or {}
    base, cand, trades = {}, {"CSV": {}}, {}
    for e in L6.ERAS:
        rb = L6.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L6.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand["CSV"][e] = {**_acct(rc), "years": rc.get("years")}
        trades[e] = {"B3": nb, "CSV": nc}
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B3": old_core(W, None), "CSV": old_core(W, M["csv_us"])}
    unseen = None if old["B3"]["calmar"] is None or old["CSV"]["calmar"] is None else old["CSV"]["calmar"] - old["B3"]["calmar"]
    s1 = {"CSV": R6.stage1(cand["CSV"], base, posthoc=unseen)}
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
    s = res["stage1"]["CSV"]
    pv = s["posthoc"]
    L = [f"# 第六个研究循环第三段第 11 轮：信用利差急速走阔的牛市里三分之一核心离开纳指（负相关 → 美债、否则现金）CSV（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
         f"代码 {res['code']}{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop6_r11_creditcut.py 开头；基准 B3 = Q1B，修正口径）", "",
         f"- **CSV：{'第一关全过 → 另行登记第二关（信号循环平移）' if s['ok'] else R6.FAIL1}**"
         f"（S1 合计 {f(s['sum'], '{:+.3f}')}：{yn(s['S1'])}；S2：{yn(s['S2'])}；S3：{yn(s['S3'])}；"
         f"S4（{f(s['h1'], '{:+.3f}')} / {f(s['h2'], '{:+.3f}')}）：{yn(s['S4'])}；"
         f"S7（1987〜2000 只有核心 {f(pv['unseen'], '{:+.3f}')}）：{yn(s['S7'])}；S5 / S6 不适用）",
         "", "| 年代 | B3 年化 / 最大回撤 / Calmar（前半 / 后半） | CSV（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{f(x['cagr'], '{:+.2f}')}% / {f(x['dd'], '{:.2f}')}% / {f(x['calmar'])}（{f(x['h1'])} / {f(x['h2'])}）"   # noqa: E731
    for e in L6.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['CSV'][e])}（{f(s['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定；规模只数日子）："]
    sc = res["scale"]
    for e in L6.ERAS:
        x = sc[e]
        L.append(f"- {e}：美股牛 {x['bull_days']} 天里 信号且负相关（拿美债）{f(x['bond_pct'], '{:.1f}')}%（{x['bond_segments']} 段）、"
                 f"信号且不是负相关（留现金）{f(x['cash_pct'], '{:.1f}')}%（{x['cash_segments']} 段）；"
                 f"核心换仓 B3 {res['core_trades'][e]['B3']} → CSV {res['core_trades'][e]['CSV']} 笔")
    lt = sc["latest"]
    L.append(f"- 信号在 2000〜2026 全部东证日里的比例 {sc['sig_share_2000_2026']}%（其中 {sc['overlap_with_vct_pct']}% 的日子 VCT 的信号也成立）；"
             f"最新一天 {lt['date']}：美股{'熊' if lt['us_bear'] else '牛'}、信号 {'是' if lt['signal'] else '否'}、股债负相关 {'是' if lt['corr_neg'] else '否'}")
    o = res["old"]
    L.append("- 1987〜2000 只有核心（S7 用）：" + "、".join(
        f"{k} {f(o[k]['calmar'])}（年化 {f(o[k].get('cagr'), '{:+.2f}')}%、回撤 {f(o[k].get('dd'), '{:.2f}')}%、"
        f"纳指 + 美债 {f(o[k].get('bond_mix_pct'), '{:.1f}')}% / 纳指 2/3 + 现金 {f(o[k].get('cash_cut_pct'), '{:.1f}')}% 的日子）" for k in ("B3", "CSV"))
        + f"；美股牛的日子里信号 {f(o['CSV'].get('sig_bull_pct'), '{:.1f}')}%")
    for e in L6.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["CSV"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（CSV − B3，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
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
    """登记前用：① 信号永远不成立 → B3；② 信号换成 VCT 的 → 与第 9 轮 VCT 已公开的账户相同；③ old_core 信号 None = 第 7 轮函数的 B3。"""
    from qbreak import paths
    W = L6.load3()
    M = inputs(W)
    never = pd.Series(False, index=M["csv_t"].index)
    ov0 = csv_over(W, M, never)
    same_b3 = {}
    for e in L6.ERAS:
        rb, r0 = L6.run(W, e), L6.run(W, e, **ov0)
        same_b3[e] = bool(all(rb.get(x) == r0.get(x) for x in KEYS))
    ref = json.loads((paths.out_dir() / REF9).read_text(encoding="utf-8"))["cand"]["VCT"]
    ovv = csv_over(W, M, M["sig_t"])
    same_vct = {}
    for e in L6.ERAS:
        r = L6.run(W, e, **ovv)
        same_vct[e] = bool(all(r.get(x) == ref[e].get(x) for x in ("cagr", "dd", "calmar", "h1", "h2", "n")))
    o1, o2 = old_core(W, None), V.old_core(W, None)
    out = {"never_same_as_b3": same_b3, "vct_signal_same_as_vct": same_vct,
           "old_core_b3_same": bool(o1["calmar"] == o2["calmar"] and o1["cagr"] == o2["cagr"])}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if all(same_b3.values()) and all(same_vct.values()) and out["old_core_b3_same"] else 1


# ───────────────────────── 第二关（第一关全过才做；另行登记后只运行一次；signal = 信号循环平移） ─────────────────────────
_G: dict = {}


def _placebo_one(seed: int):
    W, M, base, ks = _G["W"], _G["M"], _G["base"], _G["ks"]
    try:
        kw = csv_over(W, M, shifted_signal(M["csv_t"], ks[int(seed)]))
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
    ov = csv_over(W, M, M["csv_t"])
    cand = {e: L6.run(W, e, **ov)["calmar"] for e in L6.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L6.ERAS), 6)
    n = len(R6.shift_window(M["csv_t"]))
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
    L = [f"# 第六个研究循环第三段第 11 轮 第二关：{k} vs 400 次信号循环平移（{KIND[k]}；B3 不动）（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}；"
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
    ap = argparse.ArgumentParser(description="第六个研究循环第三段第 11 轮：CSV")
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
