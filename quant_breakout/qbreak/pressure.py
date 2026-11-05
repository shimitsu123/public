"""pressure.py — 综合压力 P_g 与「威胁高 + 压力已释放」C_rel 的每日读数（日报 / 前向记录 / 模拟盘判断层共用）。

算法与登记的研究完全相同（tests/test_pressure_module.py 逐项对照）：
  - 分项与分位：scripts/pressure_study.py（登记 38b648e）的 price_parts / month_lag1 / month_ends / rolling_pct；
  - P_g：scripts/threat_pressure_global.py（登记 f01ea80）= 综合压力去掉宽度，6 个分项（涨幅 log(收盘 ÷ 500 日最低)、
    长期乖离 log(收盘 ÷ 250 日线)、平静 −60 日年化波动、利率上升 GS10 12 个月变化、曲线变平 −(GS10 − TB3MS)、
    信用利差收窄 −(BAA − GS10)；美国宏观用上个月的月均），每个分项取「过去 120 个月末（含当月）里的分位」（≥ 60 个月），
    ≥ 4 个有值才平均；
  - 当天的读数 = 今天的原始分项在「过去 119 个已结束的月末 + 今天」里的分位（pressure_study.now_reading 同一算法）；
  - C_rel = (A0 + 100 − P_g) ÷ 2（全球确认成立，2026-09-29；用户 ㉞ 同意进前向记录）。
只用当时已知的数据；FRED 月度序列有缓存（qbreak/factors.fred）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RUNUP_D, MA_D, VOL_D = 500, 250, 60
WIN_M, MIN_M, MIN_COMP = 120, 60, 4
PCOMP = ["runup", "ma", "calm", "rate", "curve", "credit"]


def price_parts(c: pd.Series) -> pd.DataFrame:
    c = c.dropna().astype(float)
    lr = np.log(c).diff()
    return pd.DataFrame({"runup": np.log(c / c.rolling(RUNUP_D, min_periods=RUNUP_D).min()),
                         "ma": np.log(c / c.rolling(MA_D, min_periods=MA_D).mean()),
                         "calm": -lr.rolling(VOL_D, min_periods=VOL_D).std() * np.sqrt(252) * 100}, index=c.index)


def month_lag1(s: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """月度序列（FRED 的日期 = 那个月 1 日）→ 每个日期用「上个月」的值。"""
    s = s.dropna().copy()
    s.index = pd.DatetimeIndex(s.index).to_period("M")
    prev = pd.DatetimeIndex(dates).to_period("M") - 1
    return pd.Series(s.reindex(prev).to_numpy(float), index=dates)


def month_ends(c: pd.Series) -> pd.DatetimeIndex:
    c = c.dropna()
    return pd.DatetimeIndex(c.groupby(c.index.to_period("M")).tail(1).index)


def rolling_pct(x: pd.Series, win: int = WIN_M, min_n: int = MIN_M) -> pd.Series:
    """月末序列 → 本月的值在过去 win 个月末（含本月）里的分位（≤ 它的比例 × 100）；有值的 < min_n → 空。"""
    v = x.to_numpy(float)
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        if not np.isfinite(v[i]):
            continue
        w = v[max(0, i - win + 1):i + 1]
        w = w[np.isfinite(w)]
        if len(w) >= min_n:
            out[i] = float((w <= v[i]).mean() * 100)
    return pd.Series(out, index=x.index)


def macro_from(y10: pd.Series, y3: pd.Series, baa: pd.Series, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """美国利率 / 曲线 / 信用（上个月的月均；方向 = 景气时往哪边走 = 加压）。"""
    y10l = month_lag1(y10, dates)
    return pd.DataFrame({"rate": y10l - month_lag1(y10.shift(12), dates), "curve": -(y10l - month_lag1(y3, dates)),
                         "credit": -(month_lag1(baa, dates) - y10l)}, index=dates)


def macro_parts(dates: pd.DatetimeIndex) -> pd.DataFrame:
    from . import factors as F
    return macro_from(F.fred("GS10"), F.fred("TB3MS"), F.fred("BAA"), dates)


def pressure_raw(close: pd.Series, dates: pd.DatetimeIndex, macro: pd.DataFrame) -> pd.DataFrame:
    pp = price_parts(close).reindex(dates)
    return pd.concat([pp[["runup", "ma", "calm"]], macro.reindex(dates)], axis=1)[PCOMP]


def p_scores(raw: pd.DataFrame) -> pd.DataFrame:
    """月末原始分项 → P_g（≥ 4 个分项的分位平均）、P_price（涨幅 + 乖离两个都有）。"""
    pct = pd.DataFrame({k: rolling_pct(raw[k]) for k in PCOMP}, index=raw.index)
    n = pct.notna().sum(axis=1)
    return pd.DataFrame({"P_g": pct.mean(axis=1).where(n >= MIN_COMP), "P_price": pct[["runup", "ma"]].mean(axis=1, skipna=False)},
                        index=raw.index)


def month_frame(close: pd.Series, macro_fn=macro_parts) -> tuple[pd.DatetimeIndex, pd.DataFrame, pd.DataFrame]:
    """已结束的月末（当月还没结束的不用）→ (月末日期, 原始分项, P_g / P_price)。"""
    close = close.dropna()
    dates = month_ends(close)[:-1]
    raw = pressure_raw(close, dates, macro_fn(dates))
    return dates, raw, p_scores(raw)


def pct_now(hist: pd.DataFrame, cur: pd.Series) -> dict[str, float | None]:
    """今天的原始分项在「过去 119 个月末 + 今天」里的分位（0〜100）。"""
    out: dict[str, float | None] = {}
    for k in PCOMP:
        v = cur.get(k)
        h = hist[k].dropna().iloc[-(WIN_M - 1):]
        if v is None or not np.isfinite(v) or len(h) + 1 < MIN_M:
            out[k] = None
            continue
        w = np.append(h.to_numpy(float), v)
        out[k] = float((w <= v).mean() * 100)
    return out


def now_reading(close: pd.Series, macro_fn=macro_parts) -> dict:
    """最新一天的 P_g（与 scripts/threat_pressure_global.now_reading 相同）与各分项分位。"""
    close = close.dropna()
    _, raw, S = month_frame(close, macro_fn)
    last = pd.DatetimeIndex([close.index[-1]])
    cur = pressure_raw(close, last, macro_fn(last)).iloc[0]
    pct = pct_now(raw, cur)
    have = [v for v in pct.values() if v is not None]
    p = float(np.mean(have)) if len(have) >= MIN_COMP else None
    return {"date": str(close.index[-1].date()), "P_g": None if p is None else round(p, 1),
            "pct": {k: (None if v is None else round(v, 1)) for k, v in pct.items()}, "S": S}


def c_rel(a0: float | None, p_g: float | None) -> float | None:
    if a0 is None or p_g is None or not np.isfinite(a0) or not np.isfinite(p_g):
        return None
    return (float(a0) + 100.0 - float(p_g)) / 2.0


def daily_pg(close: pd.Series, macro_fn=macro_parts, start: str | None = None) -> pd.Series:
    """每个交易日「当天读数」的 P_g 历史（回测 / 自身历史分位用）：第 d 天 = d 的原始分项在「d 所在月之前的 119 个
    已结束月末 + d」里的分位（与 now_reading 在那一天会给的值相同）。"""
    close = close.dropna()
    dates = month_ends(close)
    raw_m = pressure_raw(close, dates, macro_fn(dates))
    days = close.index if start is None else close.index[close.index >= pd.Timestamp(start)]
    raw_d = pressure_raw(close, days, macro_fn(days))
    per = raw_m.index.to_period("M")
    out = np.full(len(days), np.nan)
    arr = {k: raw_m[k].to_numpy(float) for k in PCOMP}
    dper = days.to_period("M")
    pos = per.searchsorted(dper, side="left")                  # 当月之前的月末个数
    for i in range(len(days)):
        k0 = int(pos[i])
        vals = []
        for k in PCOMP:
            v = raw_d[k].iat[i]
            if not np.isfinite(v):
                continue
            h = arr[k][:k0]
            h = h[np.isfinite(h)][-(WIN_M - 1):]
            if len(h) + 1 < MIN_M:
                continue
            vals.append(float((np.append(h, v) <= v).mean() * 100))
        if len(vals) >= MIN_COMP:
            out[i] = float(np.mean(vals))
    return pd.Series(out, index=days)
