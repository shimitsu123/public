"""leap_r1b_portfolio.py — 第 1 轮探索的组合层面（只描述、不登记；只用 E 2006〜2016 与 J 2017〜2026）。

第 1 轮逐笔探索（var/out/leap_r1_explore.md）：两个年代、各个子样本方向都一致的新特征只有股息率（秩相关 +0.05〜+0.12）。
这里看它放进 S0C2 组合之后怎样：
  F1 W2 ∧ 股息率 ≥ 当天股票池的中位数；F2 W2 ∧ 股息率 ≥ 前 1/3；P1 W2，同一天多个信号时股息率高的先买；P2 = F1 + P1
  股票池：日経225（= 现行的股票池）；更宽的立花可买股票池（E：日経225 + 扩大池；J：时点 TOPIX 500，无幸存者偏差）。
  股息率缺值（没有 1 年以上的分红历史、或 yfinance 没有这只票 = 多半已退市）→ 不算「高股息」；另报缺值的比例。
输出：var/out/leap_r1b_portfolio.md / .json（只有统计）
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
import leap_data as LD                                                       # noqa: E402
from qbreak import paths                                                     # noqa: E402

LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def dy_pct(ctx: dict, fr: dict, member: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """每只票每天：股息率在当天股票池（member = True 的票）里的百分位（0〜1）；缺值 → NaN。"""
    days = ctx["days"]
    Y = pd.DataFrame({t: LD.div_yield(LD.actions(t), days).to_numpy() for t in fr}, index=days)
    M = pd.DataFrame({t: pd.Series(member[t], index=fr[t].index).reindex(days).fillna(False).to_numpy(bool) for t in fr}, index=days)
    R = Y.where(M).rank(axis=1, pct=True)
    return {t: R[t].reindex(fr[t].index).to_numpy(float) for t in fr}


def cell(w: dict) -> str:
    f = lambda v, s="{:.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else s.format(v)   # noqa: E731
    return (f"{f(w.get('cagr'))}% / {f(w.get('dd'))}% / {f(w.get('calmar'), '{:.3f}')} · {w.get('n')} 笔 "
            f"{f(w.get('mean'), '{:+.2f}')}% / {f(w.get('win'), '{:.0f}')}%")


def setting(era: str, uni: str) -> dict:
    from qbreak import wide_universe as WU
    from qbreak.config import universe
    from qbreak.trader import load_params
    t0 = time.time()
    n225 = list(universe("JP", "broad"))
    if era == "E":
        names = n225 if uni == "n225" else n225 + [t for t in WU.tickers(WU.load()) if t not in set(n225)]
        ctx = LF.context("E", names)
    else:
        ctx = LF.context("J", jmem="U0" if uni == "n225" else "U1")
    p = load_params(market="JP")
    fr = LF.frames(ctx, p)
    mem = LF.member_mask(ctx, fr)
    fr = LF.with_mask(fr, mem)
    run_fn = LF.runner(ctx, fr)
    pct = dy_pct(ctx, fr, mem)
    ent = {t: df["entry"].to_numpy(bool) for t, df in fr.items()}
    miss = sum(int((ent[t] & ~np.isfinite(pct[t])).sum()) for t in fr) / max(1, sum(int(ent[t].sum()) for t in fr))
    k1 = {t: np.nan_to_num(pct[t], nan=-1.0) >= 0.5 for t in fr}
    k2 = {t: np.nan_to_num(pct[t], nan=-1.0) >= 2 / 3 for t in fr}
    prio = {(t, d): float(v) for t, df in fr.items() for d, v, e in zip(df.index, pct[t], ent[t]) if e and np.isfinite(v)}
    res = {"现行（W2）": LF.run(ctx, run_fn, fr, p), "只有核心": LF.run(ctx, run_fn, LF.no_entries(fr), p),
           "F1 W2 ∧ 股息率 ≥ 中位数": LF.run(ctx, run_fn, LF.with_mask(fr, k1), p),
           "F2 W2 ∧ 股息率前 1/3": LF.run(ctx, run_fn, LF.with_mask(fr, k2), p),
           "P1 W2，股息率高的先买": LF.run(ctx, run_fn, fr, p, priority=prio),
           "P2 F1 + 股息率高的先买": LF.run(ctx, run_fn, LF.with_mask(fr, k1), p, priority=prio)}
    return {"res": res, "miss": miss, "keep1": LF.keep_frac(fr, k1), "keep2": LF.keep_frac(fr, k2), "n_names": len(fr),
            "secs": round(time.time() - t0)}


def main() -> int:
    t0 = time.time()
    say(f"# 第 1 轮探索（组合层面）：股息率放进 S0C2（只描述，{pd.Timestamp.today().date()}）")
    say("规则见 scripts/leap_r1b_portfolio.py 开头。各格 = 年化 / 最大回撤 / Calmar · 个股笔数 每笔净收益 / 胜率（组合里的交易）。")
    out = {}
    for era, uni, lab in (("E", "n225", "E 2006-10〜2016-09 · 日経225"), ("E", "wide", "E · 日経225 + 扩大池"),
                          ("J", "n225", "J 2017-01〜2026-09 · 今天的日経225"), ("J", "wide", "J · 时点 TOPIX 500（无幸存者偏差）")):
        s = setting(era, uni)
        out[f"{era}/{uni}"] = {k: {w: v for w, v in r.items() if not w.startswith("_")} for k, r in s["res"].items()}
        say(f"\n## {lab}（{s['n_names']} 只；股息率缺值的信号 {s['miss'] * 100:.0f}%；F1 保留 {s['keep1'] * 100:.0f}%、F2 {s['keep2'] * 100:.0f}%；{s['secs']}s）")
        say(f"| 方案 | {era} 全期 | {era} 前半 | {era} 后半 |")
        say("|---|---|---|---|")
        for k, r in s["res"].items():
            say(f"| {k} | {cell(r[era])} | {cell(r[era + '1'])} | {cell(r[era + '2'])} |")
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "leap_r1b_portfolio"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
