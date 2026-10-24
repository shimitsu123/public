"""leap_r13c_frontier.py — 「质的飞跃」第 13 轮（诊断续 2，只描述、不登记；只用 E / J，Z 不看）：要多少笔、多准，组合才够得着门槛。

第 13 轮 A / B：只在 W2 信号里挑，即使全挑对（胜率 100%），E 也到不了门槛 —— 笔数太少、个股层占用的资金太少。
这里只用最大的信号集合「全部突破 · 扩大池」（E = 日経225 + 扩大池 yfinance；J = 时点 TOPIX 500，J-Quants），
按「笔数 = 现行 W2 · 日経225 单独交易笔数的 1 / 2 / 4 / 8 倍」×「胜率 45 / 50 / 55 / 60%」随机抽事后赚钱 / 亏钱的信号（leap_r13b_required.mix_keep），
每格 3 个种子取中位数 → 组合 Calmar 与个股层占用资金。回答：要一个每年给出多少笔、胜率多少的选股模型，组合才到「现行 + 0.10」。
事后结果 = 单独交易（candle_posthoc.trades，现行卖出规则、扣成本）；组合 = 同一套 S0C2（scripts/leap_confirm.py）。
输出：var/out/leap_r13c_frontier.md / .json（只有统计）
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
import leap_common as LC                                                     # noqa: E402
import leap_confirm as LF                                                    # noqa: E402
from leap_r12_explore import utilization                                     # noqa: E402
from leap_r13b_required import mix_keep, signal_set                          # noqa: E402
from qbreak import paths                                                     # noqa: E402

MULTS = (1, 2, 4, 8)
WINS = (0.45, 0.50, 0.55, 0.60)
SEEDS = 3
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def main() -> int:
    import jq_study as JS
    t0 = time.time()
    say(f"# 「质的飞跃」第 13 轮（诊断续 2）：要多少笔、多准，组合才够得着门槛（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r13c_frontier.py 开头。格子 = 组合 Calmar 中位数（3 个种子）/ 个股层平均占用资金；粗体 = 到了门槛（现行 + 0.10）。")
    out = {}
    for era in ("E", "J"):
        te = time.time()
        B = signal_set(era, False, True)                                     # 现行 W2 · 日経225：笔数的基准与门槛
        cur = LF.run(B["ctx"], B["run_fn"], B["fr"], B["p"])
        n0, bar = B["n"], cur[era]["calmar"] + LC.CALMAR_UP[era]
        del B
        S = signal_set(era, True, False)                                     # 全部突破 · 扩大池
        ctx, p, fr, run_fn, label = S["ctx"], S["p"], S["fr"], S["run_fn"], S["label"]
        a, b = ctx["windows"][era]
        years = (pd.Timestamp(b or ctx["days"][-1]) - pd.Timestamp(a)).days / 365.25
        grid = {}
        for m in MULTS:
            for w in WINS:
                cs, us, kept = [], [], 0
                for s in range(SEEDS):
                    k = mix_keep(fr, label, n0 * m, w, s)
                    kept = int(sum(int(x.sum()) for x in k.values()))
                    r = LF.run(ctx, run_fn, LF.with_mask(fr, k), p)
                    eng = JS.RealLotEngine.LAST[-1]
                    cs.append(r[era]["calmar"])
                    us.append(utilization(pd.DataFrame(eng.st.trades), eng.st.history, a, b))
                grid[f"{m}x/{w:.2f}"] = {"calmar": round(float(np.median(cs)), 3), "util": round(float(np.median(us)) * 100, 1), "kept": kept,
                                         "per_year": round(kept / years, 1)}
            print(f"  {era} ×{m}：{time.time() - te:.0f}s", flush=True)
        out[era] = {"n0": n0, "bar": round(bar, 3), "pool": {"n": S["n"], "win": round(S["win"], 1)}, "grid": grid}
        say(f"\n## {era}（门槛 {bar:.3f}；基准笔数 = W2 · 日経225 单独交易 {n0} 笔 ≈ {n0 / years:.0f} 笔/年；"
            f"信号池 = 全部突破 · 扩大池 {S['n']} 笔、胜率 {S['win']:.1f}%；{time.time() - te:.0f}s）")
        say("| 笔数（每年） | " + " | ".join(f"胜率 {w * 100:.0f}%" for w in WINS) + " |")
        say("|---|" + "---|" * len(WINS))
        for m in MULTS:
            cells = []
            for w in WINS:
                g = grid[f"{m}x/{w:.2f}"]
                c = f"{g['calmar']:.3f}"
                cells.append((f"**{c}**" if g["calmar"] >= bar else c) + f" / {g['util']:.0f}%")
            say(f"| ×{m}（约 {grid[f'{m}x/{WINS[0]:.2f}']['per_year']:.0f} 笔/年） | " + " | ".join(cells) + " |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r13c_frontier"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
