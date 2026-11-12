"""holiday_gap_study.py — 周末 / 祝日 / 年末年始对行情的影响（只描述，不改规则；2026-09-29 用户：「周末和年休还有红日子现在考没考虑进去…
休息的时候没有交易的话要参照日经225指数主连指数 拉低个股的周线和月线的话有什么问题么」）。

一、休市之后第一个开盘：日経225 225 只的个股跳空（开盘 ÷ 前收 − 1）按「中间有没有东证休市的平日」分组，
    与休市期间 CME 日経225先物（Yahoo NIY=F，2004〜）的涨跌（最后一个 CME 收盘 ÷ 东证前收 − 1，含期现基差）的关系；
    按 CME 变化分三档（≤ −2% / −2〜+2% / ≥ +2%）→ var/holiday_gaps.json（日报「09:00 日本开盘」下面那一行读它，qbreak/holiday_gap.py）。
二、周线 / 月线的成交量：按那一周 / 那个月的交易日数分组，合计版（现行 W2 的算法）与日均版「≥ 前 10 期平均」的比例
    —— 价格线（开高低收、均线、MACD）只用真实交易日，不会被拉低；被拉低的只是「合计」类的成交量。
行情：今天的日経225（幸存者口径，只作描述）21 年缓存；东证日历 qbreak/calendar_jp.py（历年祝日，已对 J-Quants 官方日历核对）。
输出 var/out/holiday_gaps.md、var/holiday_gaps.json。  python scripts/holiday_gap_study.py
非投资建议。
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BUCKETS = [(-1.0, -0.02, "≤ −2%"), (-0.02, 0.02, "−2%〜+2%"), (0.02, 1.0, "≥ +2%")]


def yf_close(t: str, start: str = "2004-01-01") -> pd.DataFrame:
    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    h = yf.Ticker(t).history(start=start, auto_adjust=False)
    h.index = pd.DatetimeIndex(h.index.tz_localize(None) if h.index.tz is not None else h.index).normalize()
    return h[h["Close"] > 0]


def reopen_rows(n225: pd.DataFrame, fut: pd.DataFrame) -> pd.DataFrame:
    """东证每个交易日 R 与前一个交易日 L：中间休市的平日数、CME 最后收盘（日期 < R）÷ 东证 L 收盘 − 1。"""
    from qbreak.calendar_jp import is_trading_day
    idx = pd.DatetimeIndex([d for d in n225.index if is_trading_day(d.date())])
    rows = []
    for i in range(1, len(idx)):
        R, L = idx[i], idx[i - 1]
        fb = fut.loc[:R - pd.Timedelta(days=1), "Close"]
        if not len(fb) or fb.index[-1] < L:
            continue
        closed = int(np.busday_count(L.date(), R.date()) - 1)
        rows.append({"R": R, "L": L, "closed": closed, "cme": float(fb.iloc[-1] / n225.loc[L, "Close"] - 1)})
    return pd.DataFrame(rows)


def stock_gaps(D: pd.DataFrame, data: dict) -> pd.DataFrame:
    """每个重开日：个股跳空的中位数、高开 > 3% / 低开 < −3% 的比例（成交量 > 0 的票）。"""
    O = pd.DataFrame({t: df["Open"] for t, df in data.items()}).sort_index()
    C = pd.DataFrame({t: df["Close"] for t, df in data.items()}).sort_index()
    V = pd.DataFrame({t: df["Volume"] for t, df in data.items()}).sort_index()
    G = (O / C.shift(1) - 1).where(V > 0)
    out = []
    for r in D.itertuples(index=False):
        if r.R not in G.index:
            continue
        g = G.loc[r.R].dropna()
        if len(g) < 50:
            continue
        out.append({**r._asdict(), "med": float(g.median()), "up3": float((g > 0.03).mean()), "dn3": float((g < -0.03).mean()), "n": len(g)})
    return pd.DataFrame(out)


def buckets(X: pd.DataFrame) -> list[dict]:
    out = []
    for lo, hi, lab in BUCKETS:
        y = X[(X["cme"] > lo) & (X["cme"] <= hi)]
        if len(y):
            out.append({"lo": lo, "hi": hi, "label": lab, "n": int(len(y)), "med": round(float(y["med"].mean()) * 100, 2),
                        "up3": round(float(y["up3"].mean()) * 100, 1), "dn3": round(float(y["dn3"].mean()) * 100, 1)})
    return out


def period_volume(data: dict, freq: str) -> pd.DataFrame:
    """每只票每个完成的周 / 月：交易日数、合计 ÷ 前 10 期合计平均、日均 ÷ 前 10 期日均平均 → 按交易日数分组的「≥ 1.0」比例。"""
    from qbreak import mtf
    rows = []
    for t, df in data.items():
        d = df[df["Close"].notna()]
        if len(d) < 300:
            continue
        g = d.groupby(mtf.period_key(d.index, freq))["Volume"]
        s, k = g.sum().astype(float), g.size().astype(float)
        s, k = s.iloc[:-1], k.iloc[:-1]                                   # 最后一期可能还没完成
        per = s / k
        r_sum = s / s.shift(1).rolling(10).mean()
        r_day = per / per.shift(1).rolling(10).mean()
        rows.append(pd.DataFrame({"days": k, "sum": r_sum, "day": r_day}).dropna())
    A = pd.concat(rows)
    A = A[np.isfinite(A["sum"]) & np.isfinite(A["day"])]
    return A.groupby("days").agg(n=("sum", "size"), sum_ge1=("sum", lambda x: float((x >= 1).mean())),
                                  day_ge1=("day", lambda x: float((x >= 1).mean())),
                                  sum_med=("sum", "median"), day_med=("day", "median")).reset_index()


def main() -> int:
    from qbreak import paths
    from qbreak.config import DataConfig, universe
    from qbreak.data import load_universe
    logging.disable(logging.WARNING)
    jp = universe("JP", "broad")
    data = load_universe(jp, DataConfig(provider="yfinance", years=21, allow_synthetic=False, min_bars=100).validate())
    n225, fut = yf_close("^N225"), yf_close("NIY=F")
    n225 = n225[n225["Volume"] > 0] if "Volume" in n225 else n225
    D = reopen_rows(n225, fut)
    D = D[D["R"] >= "2006-01-01"]
    X = stock_gaps(D, data)
    groups = {"normal": X[X["closed"] == 0], "holiday": X[X["closed"] >= 1], "long": X[X["closed"] >= 2]}
    summ = {k: {"days": int(len(v)), "abs_med": round(float(v["med"].abs().mean()) * 100, 2),
                "up3": round(float(v["up3"].mean()) * 100, 1), "dn3": round(float(v["dn3"].mean()) * 100, 1),
                "corr": round(float(v["med"].corr(v["cme"])), 2), "buckets": buckets(v)} for k, v in groups.items()}
    W, M = period_volume(data, "W"), period_volume(data, "M")
    out = {"made": dt.date.today().isoformat(), "stocks": len(data), "span": [str(X["R"].min().date()), str(X["R"].max().date())], **summ,
           "week": W.round(4).to_dict("records"), "month": M.round(4).to_dict("records")}
    (paths.PROJECT_ROOT / "var" / "holiday_gaps.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    lab = {"normal": "中间没有休市平日（隔夜 / 周末）", "holiday": "中间有东证休市的平日（祝日 / 年末年始）", "long": "其中休市平日 ≥ 2 天（连休）"}
    L = [f"# 周末 / 祝日 / 年末年始对行情的影响（只描述，不改规则；{out['span'][0]}〜{out['span'][1]}，今天的日経225 {len(data)} 只）", "",
         "## 一、休市之后第一个开盘（个股跳空 = 开盘 ÷ 前收 − 1）", "",
         "| 分组 | 天数 | 个股跳空中位的绝对值（平均） | 高开 > 3% 的票（平均） | 低开 < −3% 的票（平均） | 与 CME 先物变化的相关 |", "|---|---|---|---|---|---|"]
    for k in ("normal", "holiday", "long"):
        s = summ[k]
        L.append(f"| {lab[k]} | {s['days']} | {s['abs_med']:.2f}% | {s['up3']:.1f}% | {s['dn3']:.1f}% | {s['corr']:.2f} |")
    L += ["", "按休市期间 CME 日経225先物（NIY=F）的变化分档（最后一个 CME 收盘 ÷ 东证前收 − 1，含期现基差）：", "",
          "| 分组 | CME 变化 | 天数 | 个股跳空中位（平均） | 高开 > 3% 的票 | 低开 < −3% 的票 |", "|---|---|---|---|---|---|"]
    for k in ("normal", "holiday"):
        for b in summ[k]["buckets"]:
            L.append(f"| {lab[k]} | {b['label']} | {b['n']} | {b['med']:+.2f}% | {b['up3']:.1f}% | {b['dn3']:.1f}% |")
    L += ["", "读法：个股买单的限价 = 信号收盘 ×1.03（跳空 > 3% 不买，回测同一条规则）→ 休市期间先物大涨时，重开那天高开 3% 以上的票多，",
          "买单多半成交不了；大跌时低开的票多（卖单照常寄付）。先物只用来提示开盘的跳空，不拿来补个股的休市日（那天个股没有成交）。", "",
          "## 二、周线 / 月线的成交量：交易日数少的周 / 月，「合计」被拉低，「日均」不会", "",
          "| 周线：那一周的交易日数 | 周数（票 × 周） | 合计 ≥ 前 10 周平均（现行 W2 的算法） | 日均 ≥ 前 10 周日均平均 | 合计比的中位 | 日均比的中位 |", "|---|---|---|---|---|---|"]
    for r in W.itertuples(index=False):
        L.append(f"| {int(r.days)} 天 | {int(r.n):,} | {r.sum_ge1 * 100:.1f}% | {r.day_ge1 * 100:.1f}% | {r.sum_med:.2f} | {r.day_med:.2f} |")
    L += ["", "| 月线：那个月的交易日数 | 月数（票 × 月） | 合计 ≥ 前 10 个月平均 | 日均 ≥ 前 10 个月日均平均 | 合计比的中位 | 日均比的中位 |", "|---|---|---|---|---|---|"]
    for r in M.itertuples(index=False):
        L.append(f"| {int(r.days)} 天 | {int(r.n):,} | {r.sum_ge1 * 100:.1f}% | {r.day_ge1 * 100:.1f}% | {r.sum_med:.2f} | {r.day_med:.2f} |")
    L += ["", "读法：价格线（开高低收、均线、MACD）只用真实交易日，休市不会把它们拉低；被拉低的只有「合计」类的成交量。",
          "在用的规则里只有 W2（周线量比，合计版）受影响；日均版 W2d（登记 e24f9b3，没通过）与相对市场版（2026-09-27 探索，不比 W2 准）都没有更好 → 维持 W2。",
          "月线的成交量没有用在任何在用的规则里。非投资建议。", ""]
    fp = paths.out_dir() / "holiday_gaps.md"
    fp.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
