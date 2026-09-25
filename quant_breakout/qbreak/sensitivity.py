"""sensitivity.py — 个股对宏观因素的敏感度与「宏观顺风度」（只用当时已知的数据）。

因素（日本交易日；美国的量取「前一个美国收盘」之后的变化 —— 美国夜里的变化在日本第二天反映）：
  rate_jp  日本 10Y 利率变化（pt）            rate_us  美国 10Y 利率变化（pt）
  oil      WTI 涨跌（%）                      fx       美元日元涨跌（%，正 = 日元贬值）
  credit   Baa−10Y 利差变化（pt）             mkt      日経225 涨跌（控制大盘）
敏感度：每只票近 104 周（约 2 年）的周收益对以上因素的多元回归系数（周五到周五；至少 60 周）。
宏观顺风度：Σ 敏感度 × 该因素近 60 个交易日的平均周变化（不含大盘项）= 「近期宏观趋势若延续，每周多赚 / 少赚多少」（%/周）。
说明文字：贡献最大的两个因素，例「利率↑ 受益」「油价↑ 受损」。
研究见 scripts/regime_fit_study.py；候补队列按顺风度作第二排序键（只作参考），是否用于交易排序看研究结论。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FACTORS = ["rate_jp", "rate_us", "oil", "fx", "credit"]
LABEL = {"rate_jp": "日本利率", "rate_us": "美国利率", "oil": "油价", "fx": "日元贬值", "credit": "信用利差"}
WEEKS, MIN_WEEKS, TREND_DAYS = 104, 60, 60


def _asof(s: pd.Series, when: pd.DatetimeIndex) -> np.ndarray:
    s = s.dropna()
    return s.reindex(s.index.union(when)).ffill().reindex(when).to_numpy(float)


def factor_levels(jp_days: pd.DatetimeIndex, n225: pd.Series, jgb10: pd.Series, dgs10: pd.Series, wti: pd.Series,
                  usdjpy: pd.Series, baa: pd.Series) -> pd.DataFrame:
    """日本交易日 D 收盘时已知的各因素水平（美国量 = D 之前最后一个美国收盘；日本 10Y = D 当天）。"""
    prev = jp_days - pd.Timedelta(days=1)
    lv = pd.DataFrame(index=jp_days)
    lv["rate_jp"] = _asof(jgb10, jp_days)
    lv["rate_us"] = _asof(dgs10, prev)
    lv["oil"] = np.log(np.clip(_asof(wti.where(wti > 0), prev), 1e-6, None))
    lv["fx"] = np.log(_asof(usdjpy, prev))
    lv["credit"] = _asof(baa, prev)
    lv["mkt"] = np.log(_asof(n225, jp_days))
    return lv


def weekly_changes(lv: pd.DataFrame) -> pd.DataFrame:
    """周五（该周最后一个交易日）水平 → 周变化；对数量乘 100 变成 %。"""
    wk = lv.groupby(lv.index.to_period("W-FRI")).tail(1)
    ch = wk.diff()
    for c in ("oil", "fx", "mkt"):
        ch[c] *= 100
    return ch.iloc[1:]


def stock_weekly(close: pd.Series, weeks_index: pd.DatetimeIndex) -> pd.Series:
    """个股周收益（%，对数），按因素周表的日期对齐（该周最后一个交易日）。"""
    c = close.dropna()
    wk = np.log(c.groupby(c.index.to_period("W-FRI")).tail(1))
    r = wk.diff() * 100
    r.index = r.index.to_period("W-FRI")
    out = pd.Series(np.nan, index=weeks_index)
    per = weeks_index.to_period("W-FRI")
    m = per.isin(r.index)
    out[m] = r.reindex(per[m]).to_numpy(float)
    return out


def betas(y: pd.Series, X: pd.DataFrame, end: pd.Timestamp) -> pd.Series | None:
    """截至 end（含）最近 WEEKS 周的 OLS 系数（含大盘项）；样本不足返回 None。"""
    d = pd.concat([y.rename("y"), X], axis=1).loc[:end].dropna().tail(WEEKS)
    if len(d) < MIN_WEEKS:
        return None
    A = np.c_[np.ones(len(d)), d[X.columns].to_numpy(float)]
    coef, *_ = np.linalg.lstsq(A, d["y"].to_numpy(float), rcond=None)
    return pd.Series(coef[1:], index=X.columns)


def trend(lv: pd.DataFrame, at: pd.Timestamp, days: int = TREND_DAYS) -> pd.Series:
    """近 days 个交易日各因素的平均周变化（与回归同单位）。"""
    x = lv.loc[:at].tail(days + 1)
    if len(x) < days + 1:
        return pd.Series(np.nan, index=FACTORS)
    ch = x.iloc[-1] - x.iloc[0]
    for c in ("oil", "fx"):
        ch[c] *= 100
    return ch[FACTORS] / (days / 5)


def fit_score(b: pd.Series | None, tr: pd.Series) -> tuple[float | None, str]:
    """顺风度（%/周）与说明文字（贡献最大的两项）。"""
    if b is None or tr.isna().any():
        return None, ""
    contrib = b[FACTORS] * tr[FACTORS]
    score = float(contrib.sum())
    top = contrib.abs().sort_values(ascending=False).head(2).index
    parts = [f"{LABEL[f]}{'↑' if tr[f] > 0 else '↓'} {'受益' if contrib[f] > 0 else '受损'}" for f in top if abs(contrib[f]) > 1e-9]
    return score, "；".join(parts)
