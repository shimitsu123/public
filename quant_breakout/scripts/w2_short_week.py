"""w2_short_week.py — 连休让一周只有 2〜4 个交易日时，下一周 W2（周线量比 ≥ 1.0）让多少票通过（只描述，不改规则；HANDOFF ㊲ 的背景，日均版对照见 scripts/w2d_study.py）。

W2 = 最近完成的一周成交量合计 ÷ 前 10 周平均（qbreak/mtf.weekly_volume_ratio，与模拟盘同一个函数、同一个日历口径）。
对每一周：完成之后的下一个交易日，股票池里 w5v ≥ 1.0 的比例与中位数；按那一周的交易日数分组。
股票池 = 今天的日経225（幸存者口径，只作描述）。输出 var/out/w2_short_week.md。
  python scripts/w2_short_week.py [--years 10] [--end 2026-09-29]
非投资建议。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def table(W: pd.DataFrame) -> pd.DataFrame:
    """W：日期 × 股票的 w5v → 每一周（按东证日历里这只票们实际有 K 线的日子）一行：起止、交易日数、之后一周过 W2 的比例、中位数。"""
    idx = W.index
    iso = idx.isocalendar()
    wk = pd.Series(idx, index=idx).groupby([iso.year.to_numpy(), iso.week.to_numpy()]).agg(["min", "max", "count"])
    rows = []
    for _, r in wk.iterrows():
        nxt = idx[idx > r["max"]]
        if not len(nxt):
            continue
        x = W.loc[nxt[0]].dropna()
        if not len(x):
            continue
        rows.append({"start": r["min"].date(), "end": r["max"].date(), "days": int(r["count"]),
                     "share": float((x >= 1.0).mean()), "median": float(x.median()), "n": int(len(x))})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--end", default=None)
    a = ap.parse_args()
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    from qbreak.mtf import live_calendar, weekly_volume_ratio
    jp = universe("JP", "broad")
    data = load_universe(jp, DataConfig(provider="yfinance", years=a.years, allow_synthetic=False, min_bars=100).validate())
    W = {}
    for t, df in data.items():
        df = df.loc[:a.end] if a.end else df
        W[t] = weekly_volume_ratio(df, live_calendar(df.index))
    W = pd.DataFrame(W).sort_index()
    T = table(W)
    T = T[T["start"] >= (W.index[0] + pd.Timedelta(days=120)).date()]      # 前 10 周平均要有历史：去掉最开头
    g = T.groupby("days").agg(weeks=("share", "size"), share=("share", "mean"), median=("median", "mean")).reset_index()
    lines = [f"# W2 × 一周的交易日数（{T['start'].min()}〜{T['end'].max()}，今天的日経225 {W.shape[1]} 只；只描述，不改规则）", "",
             "| 那一周的交易日数 | 周数 | 之后一周过 W2（w5v ≥ 1.0）的比例（平均） | w5v 中位数（平均） |", "|---|---|---|---|"]
    for r in g.itertuples(index=False):
        lines.append(f"| {r.days} 天 | {r.weeks} | {r.share * 100:.1f}% | {r.median:.2f} |")
    short = T[T["days"] <= 3].sort_values("start")
    lines += ["", "只有 2〜3 个交易日的周：", ""] + [f"- {r.start}〜{r.end}（{r.days} 天）：过 W2 {r.share * 100:.1f}%、中位 {r.median:.2f}"
                                                   for r in short.itertuples(index=False)]
    lines += ["", "读法：W2 用一周的**合计**成交量，连休那一周天数少、合计自然偏低 → 下一周几乎所有突破都被挡；研究里的 W2 回测也是同一个定义，"
              "这个效果已经算在历史结果里。按日均量算的对照研究（㊲，登记 e24f9b3）没通过 → 维持 W2（var/out/w2d_study.md）。非投资建议。", ""]
    fp = Path(__file__).resolve().parents[1] / "var" / "out" / "w2_short_week.md"
    fp.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
