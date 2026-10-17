"""leap_r11_explore.py — 「质的飞跃」第 11 轮探索：按信号质量决定买多少（只描述、不登记；E / J）。

以前的研究：逐笔两个年代都成立的只有「量」（W2、突破日 3 倍量 V3：胜率 50〜51%、每笔 +1.3〜1.6% vs 其他 +0.2〜0.4%）与股息率（秩相关 +0.05〜+0.12）；
但「只买好的」会把交易砍到 15%（V3），账户几乎不变。这里不砍交易，只改仓位：好的信号买满（×1），其他的买一半（×0.5），省下的留在核心。
  Q1 突破日量比 ≥ 3 → ×1，否则 ×0.5；Q2 股息率在当天日経225 里前一半 → ×1，否则 ×0.5；Q3 两个条件任一 → ×1，否则 ×0.5；
  Q4 突破日量比 ≥ 2 → ×1，否则 ×0.5；Q5 两个条件都不满足 → ×0.25（更激进）。
输出：var/out/leap_r11_explore.md / .json（只有统计）
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
import leap_confirm as LF                                                    # noqa: E402

from leap_r1b_portfolio import cell, dy_pct                                  # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def vr1(df: pd.DataFrame) -> np.ndarray:
    """突破日量比：当天成交量 ÷ 之前 20 天平均（只用当天为止）。"""
    v = df["Volume"].astype(float)
    return (v / v.shift(1).rolling(20, min_periods=15).mean()).to_numpy(float)


def setting(era: str) -> dict:
    from qbreak.trader import load_params
    t0 = time.time()
    ctx = LF.context(era)
    p = load_params(market="JP")
    fr = LF.frames(ctx, p)
    run_fn = LF.runner(ctx, fr)
    mem = LF.member_mask(ctx, fr)
    dp = dy_pct(ctx, fr, mem)
    ent = {t: df["entry"].to_numpy(bool) for t, df in fr.items()}
    v1 = {t: vr1(df) for t, df in fr.items()}
    sig = [(t, d, v1[t][i], dp[t][i]) for t, df in fr.items() for i, d in enumerate(df.index) if ent[t][i]]
    rule = {"Q1 突破日量比 ≥ 3": lambda v, y: 1.0 if v >= 3 else 0.5, "Q2 股息率前一半": lambda v, y: 1.0 if y >= 0.5 else 0.5,
            "Q3 两者任一": lambda v, y: 1.0 if (v >= 3 or y >= 0.5) else 0.5, "Q4 突破日量比 ≥ 2": lambda v, y: 1.0 if v >= 2 else 0.5,
            "Q5 两者都不满足 ×0.25": lambda v, y: 1.0 if (v >= 3 or y >= 0.5) else 0.25}
    res = {"现行（W2，全部买满）": LF.run(ctx, run_fn, fr, p), "只有核心": LF.run(ctx, run_fn, LF.no_entries(fr), p)}
    share = {}
    for k, f in rule.items():
        tick = {(t, d): f(np.nan_to_num(v, nan=0.0), np.nan_to_num(y, nan=0.0)) for t, d, v, y in sig}
        share[k] = float(np.mean([x == 1.0 for x in tick.values()])) if tick else 0.0
        res[k] = LF.run(ctx, run_fn, fr, p, em_tick=tick)
    return {"res": res, "share": share, "secs": round(time.time() - t0)}


def main() -> int:
    t0 = time.time()
    say(f"# 「质的飞跃」第 11 轮探索：按信号质量决定买多少（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r11_explore.py 开头。各格 = 年化 / 最大回撤 / Calmar · 个股笔数 每笔净收益 / 胜率（每笔按收益率，不按金额）。")
    out = {}
    for era in ("E", "J"):
        s = setting(era)
        out[era] = {k: {w: v for w, v in r.items() if not w.startswith("_")} for k, r in s["res"].items()}
        say(f"\n## {era}（{s['secs']}s；买满的信号比例：" + "；".join(f"{k.split(' ')[0]} {v * 100:.0f}%" for k, v in s["share"].items()) + "）")
        say(f"| 方案 | {era} 全期 | {era} 前半 | {era} 后半 |")
        say("|---|---|---|---|")
        for k, r in s["res"].items():
            say(f"| {k} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r11_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
