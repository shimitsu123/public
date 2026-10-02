"""loop2_r10_ndrvol.py — 第二个研究循环第 10 轮：「早回来 + 按美元波动调仓位」NVU = NDRH ∪ VTU（2026-10-02 登记；先提交后只运行一次；用掉 1 个做法 → 10 / 20）。

循环的规则：scripts/research_loop2.py；基准 B1：scripts/loop2_common.py；NDRH：scripts/loop2_r08_ndrhedged.py；VTU：scripts/loop2_r09_voltusd.py（两条都原样）。
为什么做这个（照实写）：
  - 第 8 轮 NDRH（S&P 熊市里纳指先翻熊再回到牛 → 早一点拿回核心，FJE 照旧）第一关全过（+0.246）、第二关约第 91 百分位；
    第 9 轮 VTU（美股牛日的核心按美元计纳指 σ20 减仓）第一关全过（+0.184）、第二关约第 88 百分位。
  - 两条管的是不同的日子（NDRH 只在 S&P 熊市里、VTU 只在不是熊的日子），效果大致可以相加；第一个循环里 FJE = FXE ∪ JBH 就是把两个差一点的规则
    合起来之后第二关才过的。→ 看过两轮结果之后的组合 = 事后组合，S7 适用。
  - 家族：记在「核心·择时（早回来）」（2 / 3），同时用到「核心·波动率仓位」（这两个家族各算用了一次，之后各自最多还能再加 1 个）。
做法 NVU（参数照两条原样 → S6 不适用；不改个股买卖 → S5 不适用）：
  - 核心用的熊 = NDRH 的 core_bear（S&P 熊 且 不是早回来）；B1 的两个核心键 US_UH / US_HG 用它代替「美股熊」（FJE 照旧决定 2845 / 1545）。
  - 不是熊的日子（含早回来的日子）核心目标 × VTU 的比例（美元计纳指 σ20，VT20 的机制）。两条原样叠在一起，不另调。
  - 接线检查（登记前跑过）：早回来永远没有 且 比例全 1 = B1；只开早回来（比例全 1）= NDRH；只开比例（没有早回来）= VTU（三个年代逐项相同）。
第一关：research_loop2.stage1（posthoc = 1987〜2000 只有核心 NVU − B1 的 Calmar 差；同第 8 / 9 轮的口径：熊用 core_bear、比例只在不是熊的日子乘）。
只描述：每年收益差；另报同一次运行里 NDRH、VTU 各自的 Calmar。
第二关（第一关全过才做）：另行登记（提交）后只运行一次（预定形状：两条信号各自按自己登记时的形状平移，平移量由同一个种子的两次抽取得出 —— 那时写定）。
事前预期（照实写）：第一关大概率过（两条各自都过、管的日子不同；但早回来的日子 σ20 通常偏高 → 那几段会被比例打折，合起来可能比相加少）；
  第二关：两条的随机版也相加，右尾一起变长，粗算约第 97 百分位 → 约 10%；「更好候选」约 8%。
运行：python scripts/loop2_r10_ndrvol.py（第一关）。输出 var/out/loop2_r10_ndrvol.md / .json。非投资建议。

第二关（2026-10-02 第一关全过之后另行登记；登记 = 加这一段的那次提交，之后不改、只运行一次，`--stage2 NVU --workers 3`）：
  两条信号各自按自己登记时的形状平移，平移量由同一个种子的两次抽取得出（种子 s = 0〜399：rng = numpy.random.default_rng([20262010, s])，
  先抽 k1、再抽 k2）：
    ① 早回来（NDRH / NDR 的形状）：2000-01-03〜2026-09-30 里 S&P 熊的美国交易日接成一串，早回来标记在这一串上整体循环平移 k1（k1 ∈ [250, N1 − 250]）；
    ② 比例（VTU / VT20 的形状）：2000-01-03〜2026-09-30 的比例序列整体循环平移 k2（k2 ∈ [250, N2 − 250]），窗口外 = 1。
  两条的天数、每段长短、比例分布都不变，只是时点与真实的信号脱钩；FJE 与 B1 的其余部分都不动。
  统计量 = 三个年代 Calmar 差合计（对同一次运行的 B1）；NVU 要严格大于 400 次的最大值（research_loop2.stage2；有算不出的 = 不过）。
  事前预期（照实写）：两条各自的随机版中位数都 < 0（−0.380 / −0.138）、右尾都长（最大 +0.699 / +0.607）；相加之后候选 +0.430 粗算约第 97 百分位 → 约 10%。
  输出 var/out/loop2_r10_ndrvol_stage2_NVU.md / .json。
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
import loop2_r08_ndrhedged as R8                                             # noqa: E402
import loop2_r09_voltusd as R9                                               # noqa: E402
import loop_r08_ndxreentry as N8                                             # noqa: E402
import research_loop2 as R2                                                  # noqa: E402

ROUND = 10
IDS = ("NVU",)
FAMILY = R8.FAMILY
POSTHOC = True
OLD = R5.OLD
OUT = "loop2_r10_ndrvol"
SHIFT_FROM, SHIFT_GAP, SEED0 = "2000-01-03", 250, 20262010           # 第二关（另行登记）：两条各自的形状，同一个种子抽两次


# ───────────────────────── 接法（tests/test_loop2_r10.py） ─────────────────────────
def nvu_over(W: dict, ndx_bear: pd.Series, uni: pd.Series, x: pd.Series) -> dict:
    """NDRH 的接法（核心熊 = S&P 熊 且 不是早回来）+ VTU 的比例（两个核心键的 EXTRA_EXPO）；两边的键不重叠，直接合并。"""
    a, b = R8.ndrh_over(W, ndx_bear, uni), R9.vtu_over(x)
    assert not set(a) & set(b)
    return {**a, **b}


def shift_pair(seed: int, n1: int, n2: int, gap: int = SHIFT_GAP) -> tuple[int, int]:
    """同一个种子抽两次：k1（早回来那一串）、k2（比例序列）。"""
    rng = np.random.default_rng([SEED0, int(seed)])
    return int(rng.integers(gap, n1 - gap + 1)), int(rng.integers(gap, n2 - gap + 1))


def placebo_parts(spx_bear: pd.Series, ndx_bear: pd.Series, x: pd.Series, seed: int,
                  a: str = SHIFT_FROM, b: str = L2.J_END) -> tuple[pd.Series, pd.Series]:
    """第二关的随机改动 → (核心用的熊, 比例)。早回来：窗口里 S&P 熊的日子接成一串、标记循环平移 k1（窗口外照真实的）；比例：窗口里循环平移 k2。"""
    s, _, idx = N8.on_union(spx_bear, ndx_bear)
    re = N8.reentry(spx_bear, ndx_bear).to_numpy(bool)
    inw = (idx >= pd.Timestamp(a)) & (idx <= pd.Timestamp(b))
    pos = np.flatnonzero(s & inw)
    w = x[(x.index >= pd.Timestamp(a)) & (x.index <= pd.Timestamp(b))]
    k1, k2 = shift_pair(seed, len(pos), len(w))
    key = s & ~re
    key[pos] = ~np.roll(re[pos], k1)
    return pd.Series(key, index=idx), pd.Series(np.roll(w.to_numpy(float), k2), index=w.index)


def old_core(W: dict, uni: pd.Series, bear: pd.Series, x: pd.Series | None) -> dict:
    """只描述 + S7：1987〜2000 只有核心（第 5 轮 old_core 同一个合成价与口径）；bear = 核心用的熊，x = 不是熊时的比例（None = 1）。"""
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
    xx = ff(x).fillna(1.0).to_numpy() if x is not None else np.ones(len(idx))
    n = len(idx)
    eq = np.ones(n)
    pu0 = ph0 = 0.0
    for t in range(1, n):
        e = 0.0 if b[t - 1] else float(xx[t - 1])
        pu, ph = (0.0, e) if hdg[t - 1] else (e, 0.0)
        turn = abs(pu - pu0) + abs(ph - ph0)
        eq[t] = eq[t - 1] * (1 + pu * ru[t] + ph * rh[t] - turn * HW.SWITCH_COST / 100)
        pu0, ph0 = pu, ph
    return EI.curve_stats(pd.Series(eq, index=idx))


def _acct(r: dict) -> dict:
    return {k: r.get(k) for k in ("cagr", "dd", "calmar", "h1", "h2", "n", "mean", "win")}


def git_head() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[1]
    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=root).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "scripts/loop2_r10_ndrvol.py", "scripts/loop2_r08_ndrhedged.py",
                                 "scripts/loop2_r09_voltusd.py", "scripts/loop_r08_ndxreentry.py", "scripts/loop_r01_voltarget.py",
                                 "scripts/loop2_r05_ddbrake.py", "scripts/loop2_common.py", "scripts/research_loop2.py",
                                 "scripts/candle_portfolio.py", "qbreak/fees.py"], capture_output=True, text=True, cwd=root).stdout.strip())
    return code, dirty


def stage_one() -> int:
    import equity_idle_study as EI
    from qbreak import paths
    t0 = time.time()
    code, dirty = git_head()
    W = L2.load()
    _, _, uni = L2.fje_states(W)
    nb_ = N8.ndx_bear(W["inp"])
    x = R9.ratio_usd(EI.ndx_tr(W["inp"]))
    ov = nvu_over(W, nb_, uni, x)
    reg = R2.load_state().get("baseline") or {}
    base, cand, side = {}, {}, {"NDRH": {}, "VTU": {}}
    for e in L2.ERAS:
        rb = L2.run(W, e)
        base[e] = {**_acct(rb), "years": rb.get("years")}
        rc = L2.run(W, e, **ov)
        cand[e] = {**_acct(rc), "years": rc.get("years")}
        side["NDRH"][e] = _acct(L2.run(W, e, **R8.ndrh_over(W, nb_, uni)))
        side["VTU"][e] = _acct(L2.run(W, e, **R9.vtu_over(x)))
        print(f"{e} 完成（{time.time() - t0:.0f}s）", flush=True)
    cb = R8.core_bear(W["bear"]["US"], nb_)
    old = {"B1": old_core(W, uni, W["bear"]["US"], None), "NVU": old_core(W, uni, cb, x)}
    unseen = None if old["B1"]["calmar"] is None or old["NVU"]["calmar"] is None else old["NVU"]["calmar"] - old["B1"]["calmar"]
    s1 = {"NVU": R2.stage1(cand, base, posthoc=unseen)}
    drift = {e: (None if (reg.get(e) or {}).get("calmar") is None or base[e]["calmar"] is None
                 else round(base[e]["calmar"] - reg[e]["calmar"], 4)) for e in L2.ERAS}
    res = {"round": ROUND, "ids": list(IDS), "family": FAMILY, "posthoc": POSTHOC, "code": code, "dirty": dirty, "base": base,
           "cand": {"NVU": cand, **side}, "stage1": s1, "drift": drift, "old": old, "seconds": round(time.time() - t0)}
    write(res)
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def _f(v, f="{:.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def write(res: dict) -> None:
    from qbreak import paths
    yn = lambda b: "过" if b else "不过"                                       # noqa: E731
    s1 = res["stage1"]["NVU"]
    ph = s1["posthoc"]
    L = [f"# 第二个研究循环第 10 轮：早回来 + 按美元波动调仓位 NVU = NDRH ∪ VTU（{pd.Timestamp.today().date()}；代码 {res['code']}"
         f"{' + 未提交的改动' if res['dirty'] else ''}；规则见 scripts/loop2_r10_ndrvol.py 开头）", "",
         f"- **NVU：{'第一关全过 → 另行登记第二关' if s1['ok'] else R2.FAIL1}**"
         f"（S1 合计 {_f(s1['sum'], '{:+.3f}')}：{yn(s1['S1'])}；S2：{yn(s1['S2'])}；S3：{yn(s1['S3'])}；"
         f"S4（{_f(s1['h1'], '{:+.3f}')} / {_f(s1['h2'], '{:+.3f}')}）：{yn(s1['S4'])}；S5 / S6 不适用；"
         f"S7（1987〜2000 只有核心的差 {_f(ph['unseen'], '{:+.3f}')}）：{yn(s1['S7'])}）",
         "", "| 年代 | B1 年化 / 最大回撤 / Calmar（前半 / 后半） | NVU（Calmar 差） | 另报：NDRH / VTU 的 Calmar |", "|---|---|---|---|"]
    cell = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}（{_f(x['h1'])} / {_f(x['h2'])}）"   # noqa: E731
    for e in L2.ERAS:
        L.append(f"| {e} | {cell(res['base'][e])} | {cell(res['cand']['NVU'][e])}（{_f(s1['d'][e], '{:+.3f}')}） | "
                 f"{_f(res['cand']['NDRH'][e]['calmar'])} / {_f(res['cand']['VTU'][e]['calmar'])} |")
    L += ["", "只描述（不参与判定）："]
    for e in L2.ERAS:
        yb, yc = res["base"][e].get("years") or {}, res["cand"]["NVU"][e].get("years") or {}
        diff = {y: round(yc[y] - yb[y], 1) for y in yb if y in yc and abs(yc[y] - yb[y]) >= 0.05}
        L.append(f"- {e} 每年收益差（NVU − B1，pp，只列有差的年份）：" + ("、".join(f"{y} {v:+.1f}" for y, v in diff.items()) or "无"))
    o = res["old"]
    oc = lambda x: f"{_f(x['cagr'], '{:+.2f}')}% / {_f(x['dd'], '{:.2f}')}% / {_f(x['calmar'])}"   # noqa: E731
    L.append(f"- 没看过的年代 1987〜2000（只有核心 + FJE）：B1 {oc(o['B1'])}；NVU {oc(o['NVU'])}")
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
    W, nb_, uni, x, hf, base = _G["W"], _G["nb"], _G["uni"], _G["x"], _G["hf"], _G["base"]
    try:
        key, xs = placebo_parts(W["bear"]["US"], nb_, x, seed)
        ov = {**Y.fxh_over(W, key, uni, hf), **R9.vtu_over(xs)}
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
    import equity_idle_study as EI
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
    x = R9.ratio_usd(EI.ndx_tr(W["inp"]))
    base = {e: L2.run(W, e)["calmar"] for e in L2.ERAS}
    cand = {e: L2.run(W, e, **nvu_over(W, nb_, uni, x))["calmar"] for e in L2.ERAS}
    stat = round(sum(cand[e] - base[e] for e in L2.ERAS), 6)
    _G.update({"W": W, "nb": nb_, "uni": uni, "x": x, "hf": Y.hedged_frame(W["inp"]), "base": base})
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
    v = np.array([z for z in vals if z is not None], float)
    res = {"round": ROUND, "id": k, "code": code, "dirty": dirty, "base": base, "cand": cand, "stat": stat, "stage1_stat": s1["sum"],
           "placebo": vals, "stage2": s2, "verdict": vd,
           "q": {q: round(float(np.percentile(v, q)), 4) for q in (50, 95, 99)} if len(v) else {},
           "pos_share": round(float((v > 0).mean() * 100), 1) if len(v) else None, "seconds": round(time.time() - t0)}
    L = [f"# 第二个研究循环第 10 轮 第二关：{k} vs 400 次循环平移（{pd.Timestamp.today().date()}；代码 {code}{' + 未提交的改动' if dirty else ''}）", "",
         f"**{vd}**：候选的 Calmar 差合计 {stat:+.4f}（第一关运行 {s1['sum']:+.4f}）；400 次随机里最大 {_f(s2['max'], '{:+.4f}')}、"
         f"≥ 候选的 {s2['ge_stat']} 次、算出 {s2['valid']} / {s2['n']} 次；中位数 {_f(res['q'].get(50), '{:+.4f}')}、"
         f"95 分位 {_f(res['q'].get(95), '{:+.4f}')}、99 分位 {_f(res['q'].get(99), '{:+.4f}')}；随机里比 B1 好的 {_f(res['pos_share'], '{:.1f}')}%",
         "", f"用时 {res['seconds']} s。非投资建议。"]
    print("\n".join(L))
    (paths.out_dir() / f"{OUT}_stage2_{k}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}_stage2_{k}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 10 轮：NVU = NDRH ∪ VTU")
    ap.add_argument("--stage2", choices=IDS)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    return stage_two(a.stage2, a.workers) if a.stage2 else stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
