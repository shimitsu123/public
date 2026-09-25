"""signal_filters.py — 日本个股「买点 / 卖点」的候选改动（scripts/signal_study.py；2026-09-26 事先登记，参数事先固定）。

全部是对 strategy.compute_indicators 结果的变换，交易引擎不用改：
  买点候选（E1〜E4）只把 entry 收紧（再 AND 一个条件）；卖点候选（X1）只改 dead_cross（离场事件）。
只用当天为止的收盘（E3 用前一天的带宽，避免信号当天的放量大阳线把带宽撑开）。
"""
from __future__ import annotations

import pandas as pd

TREND_MA, TREND_SLOPE = 200, 20            # E1：收在 200 日线上 且 200 日线比 20 个交易日前高（长期上升趋势）
HI_WIN, HI_RATIO = 252, 0.75               # E2：收盘 ≥ 52 周（252 日）最高收盘 × 0.75（离一年高点不超过 25%）
BB_N, BB_RANK_WIN, BB_RANK_MAX = 20, 250, 0.25   # E3：前一天的布林带宽（20 日 ±2σ）在过去 250 天里处于最低 25%
EXIT_MA = 20                               # X1：MACD 在信号线下 且 收在 20 日线下（两者同时成立的第一天）才离场


def trend_ok(df: pd.DataFrame) -> pd.Series:
    c = df["Close"]
    m = c.rolling(TREND_MA, min_periods=TREND_MA).mean()
    return (c > m) & (m > m.shift(TREND_SLOPE))


def near_high_ok(df: pd.DataFrame) -> pd.Series:
    c = df["Close"]
    return c >= c.rolling(HI_WIN, min_periods=HI_WIN).max() * HI_RATIO


def bb_width(c: pd.Series) -> pd.Series:
    mid = c.rolling(BB_N, min_periods=BB_N).mean()
    return 4 * c.rolling(BB_N, min_periods=BB_N).std() / mid


def squeeze_ok(df: pd.DataFrame) -> pd.Series:
    pct = bb_width(df["Close"]).rolling(BB_RANK_WIN, min_periods=BB_RANK_WIN).rank(pct=True)
    return pct.shift(1) <= BB_RANK_MAX


def breakout_ok(df: pd.DataFrame) -> pd.Series:
    """收盘 > 过去 range_n 日最高（不含当天）：compute_indicators 已算好的 breakout 列（原版的可选开关）。"""
    return df["breakout"].astype("boolean").fillna(False).astype(bool)


def confirmed_exit(df: pd.DataFrame) -> pd.Series:
    """MACD 在信号线下 且 收在 20 日线下，两者同时成立的第一天（事件）。"""
    c = df["Close"]
    cond = (df["macd"] < df["macd_sig"]) & (c < c.rolling(EXIT_MA, min_periods=EXIT_MA).mean())
    return cond & ~cond.shift(1, fill_value=False)


ENTRY_FILTERS = {"E1": trend_ok, "E2": near_high_ok, "E3": squeeze_ok, "E4": breakout_ok}
KEYS = ["BASE", "E1", "E2", "E3", "E4", "X1"]
LABELS = {"BASE": "现行", "E1": "长期趋势对齐（200 日线上且上升）", "E2": "接近 52 周高点（≥ 高点 ×0.75）",
          "E3": "波动收缩（前一天布林带宽处于一年最低 25%）", "E4": "真突破箱顶（收盘 > 过去 60 日最高）",
          "X1": "死叉离场要确认（MACD 在信号线下 且 跌破 20 日线）"}


def apply(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """返回改过的副本（BASE = 原样）。"""
    if key == "BASE":
        return df
    out = df.copy()
    if key in ENTRY_FILTERS:
        out["entry"] = out["entry"].astype(bool) & ENTRY_FILTERS[key](df).astype("boolean").fillna(False).astype(bool)
    elif key == "X1":
        out["dead_cross"] = confirmed_exit(df).astype("boolean").fillna(False).astype(bool)
    else:
        raise KeyError(key)
    return out


def entry_condition(df: pd.DataFrame, key: str) -> pd.Series | None:
    """候补队列「即将触发」也可以加同一个条件（E4 在触发前不可能成立 → None）。"""
    if key in ("E1", "E2", "E3"):
        return ENTRY_FILTERS[key](df).astype("boolean").fillna(False).astype(bool)
    return None
