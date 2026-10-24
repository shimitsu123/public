"""loop13_s2_idx.py — 第十三个研究循环 第二关：IDX（10 月第 1 个交易日前 15 个交易日不买；第一关路线 B 全过）vs 400 次同比例随机挡。
（2026-10-12 登记 = 本提交；之后不改、只运行一次。）

照 scripts/research_loop13.py（= 第十二个循环的第二关）：只过了路线 B → 400 次；统计量 = 三个年代合起来的胜率差（pp，research_loop10.pooled_trades）。
随机挡：每个年代在「TBF 没挡的信号」里随机挡掉和 IDX 一样多的比例（IDX 多挡的个数 ÷ TBF 没挡的信号数；种子 numpy.random.default_rng([20261012, 13, s])，
s = 0〜399）→ B4 + 随机挡 → 合起来胜率差。IDX 的统计量要严格大于 400 次的最大值（有算不出的 = 不过）。两关都过 = 「更好候选」→ 停下汇报、等用户决定。
运行：python scripts/loop13_s2_idx.py → var/out/loop13_s2_idx.md / .json。非投资建议。
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
import loop12_common as LC                                                   # noqa: E402
import loop13_ra_cal as RA                                                   # noqa: E402
import research_loop10 as R10                                                # noqa: E402
import research_loop13 as R13                                                # noqa: E402

N = 400


def pooled_dwin(cand: dict, base: dict) -> float | None:
    c, b = R10.pooled_trades(cand), R10.pooled_trades(base)
    return None if c["win"] is None or b["win"] is None else float(c["win"] - b["win"])


def main() -> int:
    from qbreak import paths
    t0 = time.time()
    W = LC.load()
    G = RA.build(W)["IDX"]["era"]
    base = {e: LC.run_b4(W, e) for e in LC.ERAS}
    cand = {e: LC.run_b4(W, e, G[e]) for e in LC.ERAS}
    stat = pooled_dwin(cand, base)
    free = {e: ~np.asarray(W["tbf"][e], bool) for e in LC.ERAS}
    rate = {e: float((np.asarray(G[e], bool) & free[e]).sum() / max(1, free[e].sum())) for e in LC.ERAS}
    vals = []
    for s in range(N):
        cc = {}
        for e in LC.ERAS:
            r = np.zeros(len(free[e]), bool)
            idx = np.flatnonzero(free[e])
            r[idx] = R13.random_block(len(idx), rate[e], s)
            cc[e] = LC.run_b4(W, e, r)
        vals.append(pooled_dwin(cc, base))
        if (s + 1) % 50 == 0:
            print(f"随机挡 {s + 1} / {N}（{time.time() - t0:.0f}s）", flush=True)
    s2 = R13.stage2({"B": stat}, [{"B": v} for v in vals], ["B"])
    v = np.array([x for x in vals if x is not None], float)
    res = {"id": "IDX", "stat": stat, "rate": rate, "stage2": s2, "verdict": "更好候选" if s2["pass"] else R13.R12.FAIL2,
           "q": {q: round(float(np.percentile(v, q)), 3) for q in (50, 95, 99)} if len(v) else {}, "placebo": vals, "seconds": round(time.time() - t0)}
    r = s2["routes"]["B"]
    text = (f"# 第十三个研究循环 第二关：IDX vs 400 次同比例随机挡（JST {pd.Timestamp.now(tz='Asia/Tokyo').date()}）\n\n"
            f"**{res['verdict']}**：IDX 的合起来胜率差 {stat:+.2f} pp；400 次随机挡里最大 {r['max']:+.2f} pp（中位 {res['q'].get(50)}、95 分位 {res['q'].get(95)}、"
            f"99 分位 {res['q'].get(99)}；IDX 高于随机的 {r.get('pct', 0):.1f}%）；挡的比例 " + "、".join(f"{e} {rate[e] * 100:.1f}%" for e in LC.ERAS)
            + f"。用时 {res['seconds']} s。非投资建议。\n")
    print(text)
    (paths.out_dir() / "loop13_s2_idx.md").write_text(text, encoding="utf-8")
    (paths.out_dir() / "loop13_s2_idx.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
