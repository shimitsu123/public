"""leap2_s6c_grid.py — 「选股本身的质的飞跃」第 S6 轮探索续 2：C2 的阈值网格（只描述、不登记；E / J，Z 不看）。

S6b（scripts/leap2_s6b_portfolio.py）：C2「突破日量比 ≥ 2.184 ∧ 对日経 β ≤ 0.7803」放进组合 —— J 过了 S1〜S5（39 笔 59% / +2.32%）；
E 胜率 55% / 每笔 +2.27% / 随机对照都过，只差笔数（20 < 现行 68 × 30% = 20.4）与 Calmar（0.276 < 0.278）。
用户要求「调整阈值进行研究」→ 在 E / J 上看附近的阈值：突破日量比 ∈ {1.8, 2.0, 2.184, 2.5} × 对日経 β ∈ {0.70, 0.78, 0.85, 0.90, 1.00}（20 格），
每格 E / J 的组合结果；E、J 都到 S1〜S4 的格子再做 S5 随机对照（30 次）。挑出来的（≤ 5 个）下一步提交登记，再在 Z 上确认一次。
输出：var/out/leap2_s6c_grid.md / .json（只有统计）
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leap2_common as L2                                                    # noqa: E402
import leap_confirm as LF                                                    # noqa: E402
from leap2_s6b_portfolio import daily_from_weekly, weekly_betas              # noqa: E402
from leap_r11_explore import vr1                                             # noqa: E402
from qbreak import paths                                                     # noqa: E402

VR = (1.8, 2.0, 2.184, 2.5)
BN = (0.70, 0.78, 0.85, 0.90, 1.00)
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def main() -> int:
    from qbreak import score_forward as SF
    from qbreak.config import universe
    from qbreak.trader import load_params
    t0 = time.time()
    B = weekly_betas(list(universe("JP", "broad")))
    say(f"# 「选股本身的质的飞跃」第 S6 轮探索续 2：C2 的阈值网格（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s6c_grid.py 开头。格子 = 笔数 / 胜率 / 每笔 / Calmar；✓ = 这个年代到 S1〜S4（S5 另列）。")
    out, keep_all, ctxs = {}, {}, {}
    for era in ("E", "J"):
        p = load_params(market="JP")
        ctx = LF.context(era)
        fw = LF.frames(ctx, p)
        base = LF.run(ctx, LF.runner(ctx, fw), fw, p)[era]
        fa = LF.frames(ctx, SF.no_w2_params(p))
        run_fn = LF.runner(ctx, fa)
        V = {t: np.nan_to_num(vr1(df), nan=0.0) for t, df in fa.items()}
        BNd = {t: np.nan_to_num(daily_from_weekly(B["b_n225"], t, df.index), nan=np.inf) for t, df in fa.items()}
        cells = {}
        for v in VR:
            for bn in BN:
                keep = {t: (V[t] >= v) & (BNd[t] <= bn) for t in fa}
                r = LF.run(ctx, run_fn, LF.with_mask(fa, keep), p)[era]
                f = [x for x in L2.s_fails({era: r}, {era: base}, {era: {"win": -1e9, "mean": -1e9}}) if x.split(" ")[1] == era]
                cells[(v, bn)] = {**{k: r.get(k) for k in ("n", "win", "mean", "calmar", "dd")}, "ok14": not f, "frac": LF.keep_frac(fa, keep)}
                keep_all[(era, v, bn)] = keep
        out[era] = {"base": {k: base.get(k) for k in ("n", "win", "mean", "calmar", "dd")}, "cells": {f"{v}/{bn}": c for (v, bn), c in cells.items()}}
        ctxs[era] = (ctx, run_fn, fa, p)
        say(f"\n## {era}（现行 {base['n']} 笔 {base['win']:.0f}% / {base['mean']:+.2f}% / Calmar {base['calmar']:.3f}；{time.time() - t0:.0f}s）")
        say("| 突破日量比 ≥ \\ 对日経 β ≤ | " + " | ".join(f"{bn:.2f}" for bn in BN) + " |")
        say("|---|" + "---|" * len(BN))
        for v in VR:
            say(f"| {v} | " + " | ".join(f"{c['n']} / {c['win']:.0f}% / {c['mean']:+.2f}% / {c['calmar']:.3f}{' ✓' if c['ok14'] else ''}"
                                         for c in (cells[(v, bn)] for bn in BN)) + " |")
    both = [(v, bn) for v in VR for bn in BN if out["E"]["cells"][f"{v}/{bn}"]["ok14"] and out["J"]["cells"][f"{v}/{bn}"]["ok14"]]
    say(f"\n## E、J 都到 S1〜S4 的格子：{len(both)} 个 → 随机对照（S5，30 次）")
    say("| 突破日量比 ≥ / 对日経 β ≤ | E 胜率 / 每笔 vs 随机 95% 分位 | J 胜率 / 每笔 vs 随机 95% 分位 | S5 |")
    say("|---|---|---|---|")
    out["s5"] = {}
    for v, bn in both:
        row, okall = {}, True
        for era in ("E", "J"):
            ctx, run_fn, fa, p = ctxs[era]
            c = out[era]["cells"][f"{v}/{bn}"]
            q = LF.placebo_trades(ctx, run_fn, fa, p, c["frac"], seeds=L2.PLACEBO_SEEDS, q=L2.PLACEBO_Q)
            ok = c["win"] > q["win"] and c["mean"] > q["mean"]
            okall &= ok
            row[era] = {"win_q95": round(q["win"], 1), "mean_q95": round(q["mean"], 3), "ok": ok}
        out["s5"][f"{v}/{bn}"] = row
        fm = lambda era: (f"{out[era]['cells'][f'{v}/{bn}']['win']:.0f}% / {out[era]['cells'][f'{v}/{bn}']['mean']:+.2f}% vs "      # noqa: E731
                          f"{row[era]['win_q95']:.1f}% / {row[era]['mean_q95']:+.2f}%")
        say(f"| {v} / {bn:.2f} | {fm('E')} | {fm('J')} | {'✓' if okall else '✗'} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s6c_grid"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
