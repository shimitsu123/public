"""多周期（日 / 周 / 月线）：把日线聚合成周线 / 月线（只用已经完成的 K 线，不偷看），算周 / 月线的趋势、动量、见顶特征，
再按「那根 K 线完成的那一天收盘时已知」放回日线的日期上。scripts/mtf_study.py 用（2026-09-27 事先登记）。

完成的定义：周 = ISO 周（周一〜周日），月 = 日历月；一根周 / 月线在市场日历（全部股票交易日的并集）里这一周 / 这个月
最后一个交易日收盘时完成（节假日事先知道）。数据里最后一段周期后面没有交易日 → 不知道是否已完成 → 不用。
状态类特征（例：周线在 30 周均线上）从完成日起一直有效到下一根完成；事件类特征（例：周线跌破 10 周均线）只在完成日那一天为真。
取值：1.0 = 是、0.0 = 否、NaN = 历史不够（不判断）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .strategy import macd, rsi

W_STATE = {"W1": "周线 Stage 2（收盘 > 30 周均线且均线比 4 周前高）", "W2": "周线 MACD 柱 > 0", "W3": "周线 RSI(14) ≥ 50",
           "W4v": "周线 26 周箱体振幅（最高 / 最低 − 1）", "W5v": "周线量比（这周 / 前 10 周平均）",
           "W6v": "离 52 周高点（收盘 / 52 周最高）"}
W_EVENT = {"X1": "周线收盘 < 10 周均线", "X2": "周线 MACD 死叉", "X3": "周线高潮（放量 2 倍 + 收在周振幅下 1/3 + 52 周新高）",
           "X5": "周线收盘跌破上一周最低", "X6": "连涨 ≥ 5 周后第一根下跌周", "B26": "周线突破（收盘 > 前 26 周最高且周量比 ≥ 1.5）"}
M_STATE = {"M1": "月线收盘 > 10 个月均线", "M2v": "12-1 个月动量（上月收盘 / 12 个月前 − 1）", "M3": "月线 MACD 柱 > 0",
           "M4v": "离 36 个月高点（收盘 / 36 个月最高）", "M5v": "离 10 个月均线（收盘 / 均线 − 1）"}
M_EVENT = {"X4": "月线 RSI(14) ≥ 80"}


def period_key(days: pd.DatetimeIndex, freq: str) -> np.ndarray:
    """日期 → 周期编号（W：ISO 年 × 100 + ISO 周；M：年 × 100 + 月）。"""
    days = pd.DatetimeIndex(days)
    if freq == "W":
        iso = days.isocalendar()
        return (iso["year"].to_numpy(int) * 100 + iso["week"].to_numpy(int)).astype(int)
    if freq == "M":
        return (days.year.to_numpy(int) * 100 + days.month.to_numpy(int)).astype(int)
    raise ValueError(f"freq 只能是 W / M：{freq}")


def completion_days(days: pd.DatetimeIndex, freq: str) -> pd.Series:
    """市场日历 → 每个已完成周期的完成日（这一周期最后一个交易日）；最后一个周期后面没有交易日 → 不算完成。"""
    days = pd.DatetimeIndex(sorted(pd.DatetimeIndex(days).unique()))
    if not len(days):
        return pd.Series(dtype="datetime64[ns]")
    last = pd.Series(days, index=period_key(days, freq)).groupby(level=0).max().sort_values()
    return last.iloc[:-1]


def bars(df: pd.DataFrame, days: pd.DatetimeIndex, freq: str) -> pd.DataFrame:
    """一只票的日线 → 周 / 月线（O 第一个开盘、H 最高、L 最低、C 最后收盘、V 合计）；index = 该周期在市场日历里的完成日。
    没完成的周期、这只票在那个周期没有 K 线 → 不出现。"""
    comp = completion_days(days, freq)
    d = df[["Open", "High", "Low", "Close", "Volume"]]
    d = d[d["Close"].notna()]
    if not len(d) or not len(comp):
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"], index=pd.DatetimeIndex([]))
    g = d.groupby(period_key(d.index, freq))
    out = pd.DataFrame({"Open": g["Open"].first(), "High": g["High"].max(), "Low": g["Low"].min(),
                        "Close": g["Close"].last(), "Volume": g["Volume"].sum()})
    out = out[out.index.isin(comp.index)]
    out.index = pd.DatetimeIndex(comp.reindex(out.index).to_numpy())
    return out.sort_index()


def _b(cond: pd.Series, *need: pd.Series) -> pd.Series:
    """布尔 → 1.0 / 0.0；任何一个依赖是 NaN → NaN。"""
    out = cond.astype(float)
    for s in need:
        out = out.where(s.notna())
    return out


def weekly_features(wb: pd.DataFrame) -> pd.DataFrame:
    """周线 → 状态（W1〜W3、W4v〜W6v）与事件（X1〜X3、X5、X6、B26）；index 同 wb（完成日）。"""
    c, h, l, v = wb["Close"], wb["High"], wb["Low"], wb["Volume"]
    n = np.arange(len(c))
    sma10, sma30 = c.rolling(10).mean(), c.rolling(30).mean()
    m, s, hist = macd(c, 12, 26, 9)
    ok = pd.Series(n >= 25, index=c.index)
    hist = hist.where(ok)
    r = rsi(c, 14)
    vma10 = v.shift(1).rolling(10).mean()
    hh52 = h.shift(1).rolling(52, min_periods=40).max()
    f = pd.DataFrame(index=wb.index)
    f["W1"] = _b((c > sma30) & (sma30 > sma30.shift(4)), sma30, sma30.shift(4))
    f["W2"] = _b(hist > 0, hist)
    f["W3"] = _b(r >= 50, r)
    f["W4v"] = h.rolling(26).max() / l.rolling(26).min() - 1
    f["W5v"] = v / vma10.where(vma10 > 0)
    f["W6v"] = c / h.rolling(52, min_periods=40).max()
    f["X1"] = _b(c < sma10, sma10)
    f["X2"] = _b((m < s) & (m.shift(1) >= s.shift(1)) & ok & ok.shift(1, fill_value=False), hist)
    f["X3"] = _b((f["W5v"] >= 2.0) & (c <= l + (h - l) / 3) & (h >= hh52), f["W5v"], hh52)
    f["X5"] = _b(c < l.shift(1), l.shift(1))
    up = c > c.shift(1)
    run5 = up.shift(1, fill_value=False)
    for k in range(2, 6):
        run5 &= up.shift(k, fill_value=False)
    f["X6"] = _b((c < c.shift(1)) & run5, c.shift(6))
    brk = h.shift(1).rolling(26).max()
    f["B26"] = _b((c > brk) & (f["W5v"] >= 1.5), brk, f["W5v"])
    return f


def monthly_features(mb: pd.DataFrame) -> pd.DataFrame:
    """月线 → 状态（M1、M2v、M3、M4v、M5v）与事件（X4）；index 同 mb（完成日）。"""
    c, h = mb["Close"], mb["High"]
    n = np.arange(len(c))
    sma10 = c.rolling(10).mean()
    _, _, hist = macd(c, 12, 26, 9)
    hist = hist.where(pd.Series(n >= 25, index=c.index))
    r = rsi(c, 14)
    f = pd.DataFrame(index=mb.index)
    f["M1"] = _b(c > sma10, sma10)
    f["M2v"] = c.shift(1) / c.shift(12) - 1
    f["M3"] = _b(hist > 0, hist)
    f["M4v"] = c / h.rolling(36, min_periods=24).max()
    f["M5v"] = c / sma10 - 1
    f["X4"] = _b(r >= 80, r)
    return f


def state_on(feat: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.DataFrame:
    """状态类特征放到日线日期上：每一天取「完成日 ≤ 这一天」的最后一根（含 NaN，原样）；之前没有完成的 → NaN。"""
    idx = pd.DatetimeIndex(idx)
    pos = feat.index.searchsorted(idx, side="right") - 1
    vals = feat.to_numpy(dtype=float)
    out = np.full((len(idx), feat.shape[1]), np.nan)
    ok = pos >= 0
    out[ok] = vals[pos[ok]]
    return pd.DataFrame(out, index=idx, columns=feat.columns)


def event_on(flag: pd.Series, idx: pd.DatetimeIndex) -> pd.Series:
    """事件类特征放到日线日期上：完成日那天为真；这只票那天没有 K 线（停牌等）→ 放到之后第一根 K 线（决定只会更晚，不会更早）。"""
    idx = pd.DatetimeIndex(idx)
    out = np.zeros(len(idx), bool)
    d = flag.index[flag.to_numpy(dtype=float) == 1.0]
    if len(d):
        j = idx.searchsorted(d, side="left")
        j = j[j < len(idx)]
        out[j] = True
    return pd.Series(out, index=idx)


def daily_frame(df: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    """一只票：日线 → 周 / 月线特征 → 放回这只票的日线日期（状态列 + 事件列 E_*）。"""
    wf = weekly_features(bars(df, days, "W"))
    mf = monthly_features(bars(df, days, "M"))
    idx = df.index
    out = pd.concat([state_on(wf[list(W_STATE)], idx), state_on(mf[list(M_STATE)], idx)], axis=1)
    for k in W_EVENT:
        out[f"E_{k}"] = event_on(wf[k], idx)
    for k in M_EVENT:
        out[f"E_{k}"] = event_on(mf[k], idx)
    return out
