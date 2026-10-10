"""leap2_s1_explore.py — 「选股本身的质的飞跃」第 S1 轮探索（只描述、不登记；只用 E / J，Z 不看；门槛见 scripts/leap2_common.py）。

用户选「E1 + E2」：门槛按选股本身（组合里个股交易的胜率 +8 pp、每笔 +1 pp，笔数 ≥ 30%，组合不变差，过随机对照），股票池可以扩大到 TOPIX 500 级（UW）。
这一轮看三类改法（都在同一套 S0C2 组合里，逐笔 = 组合里的个股交易）：
  ① 股票池：现行 W2 从日経225 换成 UW（E = 今天的日経225 + T500x；J = 時点 TOPIX 500）→ 信号多了、名额有限，能不能挑得更好
  ② 挑选：突破日量比（vr1 ≥ 2 / ≥ 3；两个年代逐笔都成立的只有「量」）、股息率在当天股票池里的前一半（第 1 轮两个年代同方向）
  ③ 买法：第二天挂指値 = 信号日收盘 − k × ATR（k = 0.5 / 1.0；碰到才成交，成交价 = min(开盘, 指値)，碰不到这笔不买）
     → 只买回踩的突破：买价更低，但会错过直接冲上去的（研究引擎 MixEngine 的押し目指値，出场与现行完全相同）
输出：var/out/leap2_s1_explore.md / .json（只有统计）
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
import leap_common as LC                                                     # noqa: E402
import leap_confirm as LF                                                    # noqa: E402
from leap_r1b_portfolio import cell, dy_pct                                  # noqa: E402
from leap_r11_explore import vr1                                             # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def limit_kw(fr: dict, k: float) -> dict:
    """「第二天挂指値 = 信号日收盘 − k × ATR」的 run 参数：全部信号当押し目登记（出场照现行：不限天数、看日线死叉、受新仓倍数限制）。"""
    pb = {t: set(df.index[df["entry"].to_numpy(bool)]) for t, df in fr.items() if df["entry"].any()}
    return {"pb": pb, "hold_pb": 10 ** 6, "pb_use_dead": True, "pb_free": False, "limit_k": k}


def targets(base: dict, era: str) -> str:
    b = base[era]
    return (f"门槛：胜率 ≥ {b['win'] + L2.WIN_UP_PP:.1f}%、每笔 ≥ {b['mean'] + L2.MEAN_UP_PP:+.2f}%、笔数 ≥ {L2.MIN_N_FRAC * b['n']:.0f}、"
            f"Calmar ≥ {b['calmar'] - L2.CALMAR_TOL:.3f}")


def setting(era: str) -> dict:
    from qbreak.trader import load_params
    t0 = time.time()
    p = load_params(market="JP")
    c0 = LF.context(era)
    f0 = LF.frames(c0, p)
    base = LF.run(c0, LF.runner(c0, f0), f0, p)
    del f0
    ctx = LF.context("E", L2.uw_names()) if era == "E" else LF.context("J", jmem=L2.J_UW)
    fr = LF.frames(ctx, p)
    mem = LF.member_mask(ctx, fr)
    fr = LF.with_mask(fr, mem)
    run_fn = LF.runner(ctx, fr)
    ent = {t: df["entry"].to_numpy(bool) for t, df in fr.items()}
    LC.assert_explore_dates([d for t, df in fr.items() for d in df.index[ent[t]] if d >= pd.Timestamp(ctx["windows"][era][0])])
    v = {t: vr1(df) for t, df in fr.items()}
    dp = dy_pct(ctx, fr, mem)
    k_v2 = {t: np.nan_to_num(v[t], nan=0.0) >= 2 for t in fr}
    k_v3 = {t: np.nan_to_num(v[t], nan=0.0) >= 3 for t in fr}
    k_dy = {t: np.nan_to_num(dp[t], nan=-1.0) >= 0.5 for t in fr}
    k_v2dy = {t: k_v2[t] & k_dy[t] for t in fr}
    res = {"现行（W2 · 日経225）": base, "U W2 · 扩大池": LF.run(ctx, run_fn, fr, p)}
    frac = {}
    for key, keep in (("F1 扩大池 · 突破日量比 ≥ 2", k_v2), ("F2 扩大池 · 突破日量比 ≥ 3", k_v3), ("F3 扩大池 · 股息率前一半", k_dy),
                      ("F4 扩大池 · 量比 ≥ 2 ∧ 股息率前一半", k_v2dy)):
        frac[key] = LF.keep_frac(fr, keep)
        res[key] = LF.run(ctx, run_fn, LF.with_mask(fr, keep), p)
    for key, f, k in (("B1 扩大池 · 回踩 0.5 ATR 才买", fr, 0.5), ("B2 扩大池 · 回踩 1.0 ATR 才买", fr, 1.0),
                      ("B3 扩大池 · 量比 ≥ 2 ∧ 回踩 0.5 ATR", LF.with_mask(fr, k_v2), 0.5)):
        res[key] = LF.run(ctx, run_fn, f, p, **limit_kw(f, k))
    return {"res": res, "frac": frac, "n": len(fr), "secs": round(time.time() - t0)}


def main() -> int:
    t0 = time.time()
    say(f"# 「选股本身的质的飞跃」第 S1 轮探索：扩大池 × 挑选 × 回踩买（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap2_s1_explore.py 开头；门槛 scripts/leap2_common.py。各格 = 年化 / 最大回撤 / Calmar · 组合里的个股笔数 每笔净收益 / 胜率。")
    out = {}
    for era in ("E", "J"):
        s = setting(era)
        base = {era: s["res"]["现行（W2 · 日経225）"][era]}
        out[era] = {k: {w: x for w, x in r.items() if not w.startswith("_")} for k, r in s["res"].items()}
        out[era]["_frac"] = s["frac"]
        say(f"\n## {era}（扩大池 {s['n']} 只；{s['secs']}s）— {targets(base, era)}")
        say(f"| 方案 | {era} 全期 | {era} 前半 | {era} 后半 | 保留的信号 |")
        say("|---|---|---|---|---|")
        for k, r in s["res"].items():
            fk = f"{s['frac'][k] * 100:.0f}%" if k in s["frac"] else "—"
            hit = "（到门槛 S1〜S4）" if not [x for x in L2.s_fails({era: r[era]}, base, {era: {"win": -1e9, "mean": -1e9}})
                                          if x.split(" ")[1] == era] else ""
            say(f"| {k}{hit} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} | {fk} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap2_s1_explore"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
