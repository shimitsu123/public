"""leap2_s7_feasible.py — 「选股本身的质的飞跃」门槛 S5（随机对照 95% 分位）到底要求多高（只描述；只用 E / J，Z 不看）。

S6 登记检验里 K2 在 Z、J 没过 S5：保留 18〜19% 的信号 → 组合里只有 20〜40 笔，随机保留同比例 30 次的胜率 95% 分位到 59〜68%。
这里在 E / J 上按保留比例 25 / 35 / 50 / 70% 各做一次随机对照（同一个 leap_confirm.placebo_trades，30 个种子）：
给出胜率 / 每笔的中位数与 95% 分位，和 S1 / S2 要求的（现行 + 8 pp / + 1.0 pp）放在一起 → 候选要保留多少、要多准才可能同时过 S1 / S2 / S5。
输出：var/out/leap2_s7_feasible.md / .json（只有统计）
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
from qbreak import paths                                                     # noqa: E402

FRACS = (0.25, 0.35, 0.5, 0.7)
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def main() -> int:
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    t0 = time.time()
    say(f"# 门槛 S5（随机对照 95% 分位）要求多高（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s7_feasible.py 开头。随机对照 = 日経225 的全部突破（不加 W2）按「股票 × 周」随机保留，30 个种子。")
    out = {}
    for era in ("E", "J"):
        p = load_params(market="JP")
        ctx = LF.context(era)
        fa = LF.frames(ctx, SF.no_w2_params(p))
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        base = LF.run(ctx, run_fn, fw, p)[era]
        allb = LF.run(ctx, run_fn, fa, p)[era]
        say(f"\n## {era}：现行（W2）{base['n']} 笔 {base['win']:.1f}% / {base['mean']:+.2f}% → S1 要 ≥ {base['win'] + L2.WIN_UP_PP:.1f}%、"
            f"S2 要 ≥ {base['mean'] + L2.MEAN_UP_PP:+.2f}%；全部突破 {allb['n']} 笔 {allb['win']:.1f}% / {allb['mean']:+.2f}%")
        say("| 保留比例 | 组合里的笔数（中位数） | 胜率：中位数 / 95% 分位 | 每笔：中位数 / 95% 分位 | Calmar：中位数 / 95% 分位 |")
        say("|---|---|---|---|---|")
        out[era] = {"base": base, "all": allb, "fracs": {}}
        for f in FRACS:
            q = LF.placebo_trades(ctx, run_fn, fa, p, f, seeds=L2.PLACEBO_SEEDS, q=L2.PLACEBO_Q)
            w = np.array([x for x in q["vals"]["win"] if x is not None], float)
            m = np.array([x for x in q["vals"]["mean"] if x is not None], float)
            c = np.array([x for x in q["vals"]["calmar"] if x is not None], float)
            ns = [LF.run(ctx, run_fn, __import__("wvol_placebo").week_lottery(fa, f, s), p)[era]["n"] for s in range(3)]
            out[era]["fracs"][f] = {"n_med": float(np.median(ns)), "win_med": float(np.median(w)), "win_q95": q["win"],
                                    "mean_med": float(np.median(m)), "mean_q95": q["mean"], "calmar_med": float(np.median(c)), "calmar_q95": q["calmar"]}
            o = out[era]["fracs"][f]
            say(f"| {f * 100:.0f}% | {o['n_med']:.0f} | {o['win_med']:.1f}% / {o['win_q95']:.1f}% | {o['mean_med']:+.2f}% / {o['mean_q95']:+.2f}% | "
                f"{o['calmar_med']:.3f} / {o['calmar_q95']:.3f} |")
            print(f"  {era} {f}: {time.time() - t0:.0f}s", flush=True)
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s7_feasible"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
