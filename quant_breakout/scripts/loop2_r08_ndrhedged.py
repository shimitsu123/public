"""loop2_r08_ndrhedged.py — 第二个研究循环第 8 轮：「纳指先转牛就早一点拿回核心」接到 B1 上 NDRH（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 8 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；NDR：第一个循环第 8 轮 scripts/loop_r08_ndxreentry.py（规则一字不改）。
为什么做这个（照实写）：
  - 第一个循环第 8 轮 NDR（B0 上：S&P 熊市里纳指自己翻过熊、又先回到牛 →「早回来」拿回 1545）合计 +0.055（Z +0.019、E −0.041、J +0.077），
    S4 过，只输在 S2（E −0.041）与 S3（E 回撤 −23.09% → −26.11%）。当时的事后描述：E 的回撤加深来自 2009-06-11 提前买回之后的一个月 ——
    「纳指约 −7%、**日元约 +6%**」。B0 没有汇率对冲；B1 有 FJE（日元走强时闲置资金换对冲版纳指 2845），那一段的日元那一半在 B1 上会被对冲掉。
  - 所以把 NDR 原样接到 B1 上：早回来时照 B1 的做法拿核心（FJE 照旧决定 2845 还是 1545）。规则、参数都不改。
  → 看过 NDR 的结果之后、与已采用的 FJE 拼起来 = 事后组合（同第一个循环 FJH = FXH ∪ JBH 的处理），S7 适用。家族「核心·择时（早回来）」1 / 3。
做法 NDRH（参数照 NDR 原样 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 纳指熊 = 现行牛熊检测器用在 ^NDX（美元）上（loop_r08_ndxreentry.ndx_bear）；一段 S&P 熊市里纳指出现过熊、当天是牛 →「早回来」（reentry）。
  - 核心用的「熊」= S&P 熊 且 不是早回来（loop_r08_ndxreentry.nr_key）；B1 的两个核心键 US_UH / US_HG 用它代替「美股熊」
    （loop_r04_yensurge.fxh_over 同一个接法：对冲中 → 2845，否则 1545）。美国 d 日收盘 → 日本 d+1 开盘。个股层、判断层、费用全部同 B1。
  - 接线检查（登记前跑过，见 sim_changes 登记一节）：永远没有早回来 = B1（三个年代与 1987〜2000 只有核心）。
第一关：research_loop2.stage1（posthoc = 1987〜2000 只有核心 NDRH − B1 的 Calmar 差；第 5 轮 old_core 同一个合成价与口径：日元计纳指 / 对冲版，
  前一天收盘的状态决定当天、换仓扣 0.1% × 换的比例）。只描述：各年代早回来的天数与段、核心换仓、每年收益差。
第二关（第一关全过才做）：另行登记（提交）后只运行一次（形状照 NDR 登记时写的：早回来标记在 S&P 熊的日子串上整体循环平移）。
事前预期（照实写）：NDR 在 B0 上 Z / J 都是正的；E 的回撤加深有一半来自日元，B1 会对冲掉一部分 → 第一关约 40%（E 的 S2 / S3 仍是关键）、
  第二关约 30%（NDR 登记时的估计），「更好候选」约 12%。
运行：python scripts/loop2_r08_ndrhedged.py（第一关）。输出 var/out/loop2_r08_ndrhedged.md / .json。非投资建议。

第二关（2026-10-02 第一关全过之后另行登记；登记 = 加这一段的那次提交，之后不改、只运行一次，`--stage2 NDRH --workers 3`）：
  NDR 登记时写定的形状（第一个循环第 8 轮，loop_r08_ndxreentry.placebo_key 同一个做法）—— 把 2000-01-03〜2026-09-30 里 S&P 熊的美国交易日
  按顺序接成一串，「早回来」标记在这一串上整体循环平移 k 天（k ∈ [250, N − 250]，N = 那一串的天数；种子 s = 0〜399：
  numpy.random.default_rng([20262008, s])）→ 早回来的天数与每段长短不变、只落在 S&P 熊的日子里；窗口外照真实的；FJE 与 B1 的其余部分都不动。
  每次三个年代都跑，统计量 = Calmar 差合计（对同一次运行的 B1）；NDRH 要严格大于 400 次的最大值（research_loop2.stage2；有算不出的 = 不过）。
  事前预期（照实写）：早回来只有几段（2003-04〜05、2009-06〜07、2020-04〜06、2023-03〜04 等），平移到熊市里别的日子多半是在下跌里拿核心
  → 随机的多半比 B1 差；但也会有几次碰到别的反弹。NDR 登记时估第二关约 30%，这里同样约 30〜35%。
  输出 var/out/loop2_r08_ndrhedged_stage2_NDRH.md / .json。
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
import loop2_r05_ddbrake as R5                                               # noqa: E402
import loop_r08_ndxreentry as N8                                             # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 8
IDS = ("NDRH",)
FAMILY = "核心·择时（早回来）"
POSTHOC = True
OLD = R5.OLD
OUT = "loop2_r08_ndrhedged"
SHIFT_FROM, SHIFT_GAP, SEED0 = N8.SHIFT_FROM, N8.SHIFT_GAP, 20262008  # 第二关（另行登记）：NDR 同一个形状，种子换成本轮的


# ───────────────────────── 接法（tests/test_loop2_r08.py） ─────────────────────────
def core_bear(spx_bear: pd.Series, ndx_bear: pd.Series) -> pd.Series:
    """核心用的「熊」= S&P 熊 且 不是早回来（NDR 原样）。"""
    return N8.nr_key(spx_bear, ndx_bear)


def ndrh_over(W: dict, ndx_bear: pd.Series, uni: pd.Series) -> dict:
    """B1 的接法（fxh_over：对冲中 → 2845，否则 1545）里把「美股熊」换成 core_bear。"""
    import loop_r04_yensurge as Y
    return Y.fxh_over(W, core_bear(W["bear"]["US"], ndx_bear), uni, Y.hedged_frame(W["inp"]))


def shift_k(seed: int, n: int, gap: int = SHIFT_GAP) -> int:
    rng = np.random.default_rng([SEED0, int(seed)])
    return int(rng.integers(gap, n - gap + 1))


def placebo_bear(spx_bear: pd.Series, ndx_bear: pd.Series, seed: int, a: str = SHIFT_FROM, b: str = L2.J_END) -> pd.Series:
    """第二关的随机改动（NDR 登记时的形状）：窗口里 S&P 熊的日子接成一串，「早回来」标记在这一串上循环平移 → 核心用的熊；窗口外照真实的。"""
    s, _, idx = N8.on_union(spx_bear, ndx_bear)
    re = N8.reentry(spx_bear, ndx_bear).to_numpy(bool)
    key = s & ~re
    inw = (idx >= pd.Timestamp(a)) & (idx <= pd.Timestamp(b))
    pos = np.flatnonzero(s & inw)
    rolled = np.roll(re[pos], shift_k(seed, len(pos)))
    key = key.copy()
    key[pos] = ~rolled
    return pd.Series(key, index=idx)


def old_core(W: dict, uni: pd.Series, bear: pd.Series) -> dict:
    """只描述 + S7：1987〜2000 只有核心（第 5 轮 old_core 同一个合成价与口径）；bear = 核心用的熊（B1 = 美股熊；NDRH = core_bear）。"""
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
    idx = unh.index[(unh.index >= pd.Timestamp(OLD[0])) & (unh.index <= pd.Timestamp(OLD[1]))]
    ff = lambda s: s.astype(float).reindex(idx.union(s.index)).ffill().reindex(idx)            # noqa: E731
    ru = unh.reindex(idx).pct_change().fillna(0.0).to_numpy()
    rh = ff(hed).pct_change().fillna(0.0).to_numpy()
    b = (ff(bear).fillna(0.0) > 0.5).to_numpy()
    hdg = (ff(uni).fillna(0.0) > 0.5).to_numpy()
    n = len(idx)
    eq = np.ones(n)
    pu0 = ph0 = 0.0
    for t in range(1, n):
        x = 0.0 if b[t - 1] else 1.0
        pu, ph = (0.0, x) if hdg[t - 1] else (x, 0.0)
        turn = abs(pu - pu0) + abs(ph - ph0)
        eq[t] = eq[t - 1] * (1 + pu * ru[t] + ph * rh[t] - turn * HW.SWITCH_COST / 100)
        pu0, ph0 = pu, ph
    return EI.curve_stats(pd.Series(eq, index=idx))


def describe(W: dict, e: str, re: pd.Series, uni: pd.Series, n_core: tuple[int, int]) -> dict:
    a, b = W["ctx"][e]["windows"][e]
    seg = N8.segments(re, a, b or L2.J_END)
    m = (re.index >= pd.Timestamp(a)) & ((re.index < pd.Timestamp(b)) if b else True)
    r = re[m].astype(bool)
    h = uni.astype(float).reindex(r.index.union(uni.index)).ffill().reindex(r.index).fillna(0.0) > 0.5
    return {"early_days": int(r.sum()), "early_hedged_pct": round(float(h[r].mean() * 100), 1) if r.any() else None,
            "segments": seg, "core_trades": {"B1": n_core[0], "NDRH": n_core[1]}}


def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r08_ndrhedged.py", "scripts/loop_r08_ndxreentry.py",
                                 "scripts/loop2_r05_ddbrake.py", "scripts/loop2_common.py", "scripts/research_loop2.py",
                                 "scripts/candle_portfolio.py", "qbreak/fees.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    nb_ = N8.ndx_bear(W["inp"])
    re = N8.reentry(W["bear"]["US"], nb_)
    ov = ndrh_over(W, nb_, uni)
    reg = R2.load_state().get("baseline") or {}
    base, cand, desc = {}, {}, {}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        nb = R5.core_trades(e, W)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        nc = R5.core_trades(e, W)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        desc[e] = describe(W, e, re, uni, (nb, nc))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    old = {"B1": old_core(W, uni, W["bear"]["US"]), "NDRH": old_core(W, uni, core_bear(W["bear"]["US"], nb_)),
           "segments": N8.segments(re, *OLD)}
    unseen = None if old["B1"]["calmar"] is None or old["NDRH"]["calmar"] is None else old["NDRH"]["calmar"] - old["B1"]["calmar"]
    s1 = {"NDRH": R2.stage1(cand, base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"NDRH": cand}, "stage1": s1, "drift": drift, "describe": desc, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["NDRH"]
    ph = s1["posthoc"]
    L = [f"# 第二个研究循环第 8 轮：纳指先转牛就早一点拿回核心（B1 + FJE）NDRH（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r08_ndrhedged.py 开头）", "",
         f"- **NDRH（NDR 原样 + FJE）：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | NDRH（Calmar 差） |", "|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['NDRH'][e])}（{_f(s1['d'][e], '{:+.3f}')}） |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        d = res["describe"][e]
        sg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in d["segments"]) or "无"
        L.append(f"- {e}：早回来 {d['early_days']} 天（其中对冲中 {_f(d['early_hedged_pct'], '{:.1f}')}%；{sg}）；"
                 f"核心换仓 B1 {d['core_trades']['B1']} → NDRH {d['core_trades']['NDRH']} 笔")
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["NDRH"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（NDRH − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    sg = "、".join(f"{a}〜{b}（{n} 天）" for a, b, n in o["segments"]) or "无"
    L.append(f"- 没看过的年代 1987〜2000（只有核心 + FJE）：B1 {oc(o['B1'])}；NDRH {oc(o['NDRH'])}（早回来 {sg}）")
    dr = res["drift"]
    L += ["", "B1 与登记值的 Calmar 差：" + "、".join(f"{e} {_f(dr[e], '{:+.4f}')}" for e in L2.ERAS)
          + ("（都 ≤ 0.005）" if all(v is not None and abs(v) <= R2.REPRO_TOL for v in dr.values()) else "（★ 有超过 0.005 的：数据更新，判定仍用同一次运行的 B1）"),
          f"用时 {res['seconds']} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")


_G: dict = {}


def _placebo_one(seed: int) -> float | None:
    import loop_r04_yensurge as Y
    W, nb_, uni, hf, base = _G["W"], _G["nb"], _G["uni"], _G["hf"], _G["base"]
    try:
        ov = Y.fxh_over(W, placebo_bear(W["bear"]["US"], nb_, seed), uni, hf)
        tot = 0.0
        for e in L2.ERAS:
            c = L2.run(W, e, **ov)["calmar"]
            if c is None or base[e] is None:
                return None
            tot += c - base[e]
        return round(float(tot), 6)
    except Exception:                                                         # noqa: BLE001
        return None


def stage_two(k: str, workers: int) -> int:
    import multiprocessing as mp
    import loop_r04_yensurge as Y
    from qbreak import paths
    t0 = time.time()
    s1 = json.loads((paths.out_dir() / f"{OUT}.json").read_text(encoding="utf-8"))["stage1"][k]
    if not s1["ok"]:
        print(f"{k} 第一关没过 → 不做第二关")
        return 1
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    nb_ = N8.ndx_bear(W["inp"])
    base = {e: L2.run(W, e)["calmar"] for e in L2.ERAS}
    cand = {e: L2.run(W, e, **ndrh_over(W, nb_, uni))["calmar"] for e in L2.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L2.ERAS), 6)
    _G.update({"W": W, "nb": nb_, "uni": uni, "hf": Y.hedged_frame(W["inp"]), "base": base})
    seeds = list(range(R2.PLACEBO_N))
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
    s2 = R2.stage2(stat, vals)
    vd = R2.verdict(s1, s2)
    v = np.array([x for x in vals if x is not None], float)
    res = {"round": ROUND, "id": k, "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "stage1_stat": s1["sum"],
           "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第二个研究循环第 8 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B1 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 8 轮：NDRH（NDR 原样 + FJE）")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
