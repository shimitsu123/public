"""threat.py — 「大事件威胁指数」：把历史上大跌之前常见的因素做成 0–100 的综合分（只用当时已公布的数据）。

每个因素换成「扩张窗口百分位」（在它自己过去全部历史里排第几；至少 3 年历史才开始用），等权平均 → 0–100。
不拟合任何系数（避免过度拟合）。因素（方向：越高越危险）：
  vix      VIX 水平                           vix_d20  VIX 20 日变化
  credit   Baa−10Y 利差 60 日变化（走阔）       curve    −(10Y−3M)（越倒挂越高）
  rates    美 10Y 利率 60 日变化（急升）         oil      WTI 60 日涨幅（油价冲击）
  jobs     失业率 3 个月均值 − 过去 12 个月最低（Sahm 型；按公布时滞）
  rvol     指数 20 日实现波动（年化）
  （日経另加）yen  −(USD/JPY 20 日变化，%)（日元急升）   jgb  日本 10Y 60 日变化
时滞：VIX / 指数 / 汇率当天收盘可用；Baa、美债、WTI 滞后 1 个营业日；失业率次月 10 日起可用；日本 10Y 当天（財務省）。
研究与是否用于交易见 scripts/threat_index_study.py；日报展示当前值与历史同档位后的大跌频率。
"""
from __future__ import annotations

import bisect

import numpy as np
import pandas as pd

from .timing import monthly_available

US_COLS = ["vix", "vix_d20", "credit", "curve", "rates", "oil", "jobs", "rvol"]
JP_COLS = US_COLS + ["yen", "jgb"]
LABELS = {"vix": "VIX 水平", "vix_d20": "VIX 20 日变化", "credit": "信用利差走阔", "curve": "利率曲线倒挂",
          "rates": "美债利率急升", "oil": "油价冲击", "jobs": "失业率上升", "rvol": "指数波动", "yen": "日元急升",
          "jgb": "日债利率急升"}
MIN_N = 750


def _daily(s: pd.Series, days: pd.DatetimeIndex, lag: int = 0) -> pd.Series:
    s = s.dropna()
    return s.reindex(days.union(s.index)).ffill().reindex(days).shift(lag)


def raw_features(days: pd.DatetimeIndex, close: pd.Series, vix: pd.Series, baa: pd.Series, dgs10: pd.Series,
                 dgs3m: pd.Series, wti: pd.Series, unrate: pd.Series, usdjpy: pd.Series | None = None,
                 jgb10: pd.Series | None = None) -> pd.DataFrame:
    """days：该市场的交易日；close：该市场指数收盘（与 days 对齐）。美国因素对日本交易日用「前一个美国收盘」的值
    （调用方把 days 传成日本交易日时，先把美国序列错开一天：见 us_asof_for_jp）。"""
    f = pd.DataFrame(index=days)
    v = _daily(vix, days)
    f["vix"] = v
    f["vix_d20"] = v - v.shift(20)
    b = _daily(baa, days, 1)
    f["credit"] = b - b.shift(60)
    f["curve"] = -(_daily(dgs10, days, 1) - _daily(dgs3m, days, 1))
    r10 = _daily(dgs10, days, 1)
    f["rates"] = r10 - r10.shift(60)
    w = _daily(wti.where(wti > 0), days, 1)
    f["oil"] = w / w.shift(60) - 1
    un = unrate.dropna()
    sahm = un.rolling(3).mean() - un.rolling(3).mean().rolling(12).min()
    f["jobs"] = monthly_available(sahm, days)
    c = close.reindex(days)
    f["rvol"] = np.log(c).diff().rolling(20).std() * np.sqrt(252)
    if usdjpy is not None:
        fx = _daily(usdjpy, days)
        f["yen"] = -(fx / fx.shift(20) - 1) * 100
    if jgb10 is not None:
        j = _daily(jgb10, days)
        f["jgb"] = j - j.shift(60)
    return f


def expanding_pct(x: pd.Series, min_n: int = MIN_N) -> pd.Series:
    """x_t 在 x_0..x_t（有效值）里的百分位（0–1，含自己；平局取中位）。历史不足 min_n 个有效值时为 NaN。"""
    out = np.full(len(x), np.nan)
    hist: list[float] = []
    for i, v in enumerate(x.to_numpy(float)):
        if not np.isfinite(v):
            continue
        bisect.insort(hist, v)
        n = len(hist)
        if n >= min_n:
            lo, hi = bisect.bisect_left(hist, v), bisect.bisect_right(hist, v)
            out[i] = (lo + hi) / 2 / n
    return pd.Series(out, index=x.index)


def threat_index(raw: pd.DataFrame, cols: list[str], min_n: int = MIN_N) -> tuple[pd.Series, pd.DataFrame]:
    """等权平均各因素的扩张百分位 → 0–100；至少一半因素可用才给值。返回 (指数, 各因素百分位)。"""
    pct = pd.DataFrame({c: expanding_pct(raw[c], min_n) for c in cols if c in raw})
    ok = pct.notna().sum(axis=1) >= max(1, len(cols) // 2)
    idx = (pct.mean(axis=1) * 100).where(ok)
    return idx, pct


def us_asof_for_jp(s: pd.Series, jp_days: pd.DatetimeIndex) -> pd.Series:
    """美国的日序列 → 日本交易日 D 早上已知的值（D 之前最后一个美国收盘）。"""
    s = s.dropna()
    prev = jp_days - pd.Timedelta(days=1)
    v = s.reindex(s.index.union(prev)).ffill().reindex(prev)
    return pd.Series(v.to_numpy(float), index=jp_days)


def forward_drawdown(close: pd.Series, n: int = 60) -> pd.Series:
    """今天收盘之后 n 个交易日内的最低收盘相对今天的跌幅（负数；最后 n 天为 NaN）。"""
    c = close.to_numpy(float)
    out = np.full(len(c), np.nan)
    for i in range(len(c) - n):
        out[i] = c[i + 1:i + 1 + n].min() / c[i] - 1
    return pd.Series(out, index=close.index)


def auc(score: pd.Series, event: pd.Series) -> float | None:
    """ROC AUC（Mann–Whitney），只用两者都有值的日子。"""
    d = pd.DataFrame({"s": score, "e": event}).dropna()
    pos, neg = d[d["e"] > 0.5]["s"], d[d["e"] <= 0.5]["s"]
    if len(pos) == 0 or len(neg) == 0:
        return None
    r = d["s"].rank()
    return float((r[d["e"] > 0.5].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))
