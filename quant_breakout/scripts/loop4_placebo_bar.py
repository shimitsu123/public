"""loop4_placebo_bar.py — 只描述的诊断（不是研究循环的做法、不占名额、不参与任何判定）：选股类第二关的门槛有多高
（2026-10-03；先提交脚本与读法、再只运行一次）。

为什么：第四个循环的选股做法要过第二关 =「Calmar 差合计严格大于 400 次同样强度随机挡里的最大值」。事后诊断（scripts/loop4_oracle_diag.py）
量过上限：事后完美挡掉跑输核心的突破合计 +0.594。这里量另一头：什么都不懂、随机挡掉同样比例的信号，400 次里最好的能有多少 → 一个真规则要
拿到上限的多少才可能过第二关。
做法：research_loop4.random_signal_block 原样（种子 numpy.random.default_rng([20261003, s])，s = 0〜399）：每个年代这个年代全部 W2 信号（A；
  B1 的候选是它的子集）各以概率 P = 0.15 随机挡（em_tick 0，接法与第 1〜3 轮相同）；三个年代用同一个 s；每个 s 记三个年代的 Calmar 差（− B1）与合计。
  P = 0.15 = 第 1〜3 轮各做法在 B1 会买的信号里实际挡掉的比例的大致中间（4〜20%）。
读法（写在运行之前）：
  - 「第二关门槛」= 400 次合计的最大值；另报 50 / 90 / 95 / 99 分位与 S1（合计 ≥ +0.03）在随机里有多常见。
  - 门槛 ÷ 上限（+0.594）= 一个挡 15% 信号的规则至少要拿到「完美选股」多大比例才能过第二关；> 50% → 这套检验下「挡」类选股几乎不可能被确认。
  - 只描述，不改任何做法的判定、不改循环规则。
运行：python scripts/loop4_placebo_bar.py → var/out/loop4_placebo_bar.md / .json。非投资建议。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import loop2_common as L2                                                    # noqa: E402
import research_loop4 as R4                                                  # noqa: E402

P = 0.15
N = 400
CEILING = 0.594                                                              # 事后诊断 O2 合计（e04b53a）
OUT = "loop4_placebo_bar"


def placebo_tick(A: pd.DataFrame, s: int, p: float = P) -> dict:
    """这个年代全部 W2 信号里按 random_signal_block(n, p, s) 挡掉的 → em_tick。"""
    g = R4.random_signal_block(len(A), p, s)
    return {(str(t), pd.Timestamp(d)): 0.0 for t, d, k in zip(A["ticker"], pd.to_datetime(A["date"]), g) if k}


def summarize(sums: list[float], ceiling: float = CEILING) -> dict:
    a = np.asarray(sums, float)
    q = {k: float(np.quantile(a, v)) for k, v in (("p50", 0.5), ("p90", 0.9), ("p95", 0.95), ("p99", 0.99))}
    mx = float(a.max())
    return {"n": int(len(a)), **q, "max": mx, "share_s1": float((a >= R4.SUM_MIN).mean()), "bar_over_ceiling": mx / ceiling}


def main() -> int:
    from qbreak import paths
    t0 = time.time()
    W = L2.load()
    base = {e: L2.run(W, e)["calmar"] for e in L2.ERAS}
    rows = []
    for s in range(N):
        d = {e: L2.run(W, e, em_tick=placebo_tick(W["A"][e], s))["calmar"] - base[e] for e in L2.ERAS}
        rows.append({"s": s, **{e: round(v, 4) for e, v in d.items()}, "sum": round(sum(d.values()), 4)})
        if s % 50 == 49:
            print(f"{s + 1} / {N}（{time.time() - t0:.0f}s）", flush=True)
    sm = summarize([r["sum"] for r in rows])
    per = {e: summarize([r[e] for r in rows], ceiling=np.nan) for e in L2.ERAS}
    L = ["# 只描述的诊断：选股类第二关的门槛（随机挡 15% 的 W2 信号 400 次；规则见 scripts/loop4_placebo_bar.py 开头）", "",
         f"- 合计（Calmar 差，− B1）：50 分位 {sm['p50']:+.3f}、90 分位 {sm['p90']:+.3f}、95 分位 {sm['p95']:+.3f}、99 分位 {sm['p99']:+.3f}、"
         f"**最大 {sm['max']:+.3f}（= 第二关门槛）**；随机里过 S1（≥ +0.03）的占 {sm['share_s1'] * 100:.1f}%",
         f"- 门槛 ÷ 完美选股上限（+{CEILING:.3f}）= **{sm['bar_over_ceiling'] * 100:.0f}%** → 按事先写的读法："
         + ("> 50% → 这套检验下「挡」类选股几乎不可能被确认" if sm["bar_over_ceiling"] > 0.5 else "≤ 50% → 真规则拿到上限的这个比例就可能过第二关"),
         "- 各年代（Calmar 差）：" + "；".join(f"{e} 中位 {per[e]['p50']:+.3f}、95 分位 {per[e]['p95']:+.3f}、最大 {per[e]['max']:+.3f}" for e in L2.ERAS),
         f"- B1 Calmar Z {base['Z']:.3f} / E {base['E']:.3f} / J {base['J']:.3f}；用时 {time.time() - t0:.0f} s。非投资建议。"]
    text = "\n".join(L)
    print(text)
    (paths.out_dir() / f"{OUT}.md").write_text(text + "\n", encoding="utf-8")
    (paths.out_dir() / f"{OUT}.json").write_text(json.dumps({"p": P, "n": N, "base": base, "summary": sm, "eras": per, "rows": rows},
                                                            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
