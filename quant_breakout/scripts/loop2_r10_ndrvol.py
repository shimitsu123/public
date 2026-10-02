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


# ───────────────────────── 接法（tests/test_loop2_r10.py） ─────────────────────────
def nvu_over(W: dict, ndx_bear: pd.Series, uni: pd.Series, x: pd.Series) -> dict:
    """NDRH 的接法（核心熊 = S&P 熊 且 不是早回来）+ VTU 的比例（两个核心键的 EXTRA_EXPO）；两边的键不重叠，直接合并。"""
    a, b = R8.ndrh_over(W, ndx_bear, uni), R9.vtu_over(x)
    assert not set(a) & set(b)
    return {**a, **b}


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第二个研究循环第 10 轮：NVU = NDRH ∪ VTU")
    ap.parse_args(argv)
    return stage_one()


if __name__ == "__main__":
    raise SystemExit(main())
