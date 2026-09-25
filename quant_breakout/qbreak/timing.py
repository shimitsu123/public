"""timing.py — 核心 ETF 的顶底（牛熊）择时候选：现行价格均线带之外，加入汇率 / 失业率 / 信用利差 / 波动率 / 利率曲线 / 动量。

全部返回「熊市」布尔序列（美国交易日索引；当天收盘后、日本次日开盘前已知）。参数事先固定，
比较与选择见 scripts/timing_study.py。发布时滞：VIX 当天收盘可用；Baa 利差、美债利率滞后 1 个营业日
（FRED 次日才更新）；失业率（月度）在次月 10 日起可用（就业统计通常在次月第一个周五公布）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .bullbear import BEAR, ma_band

L, B, K = 250, 0.03, 5            # 现行分界（var/bullbear.json）
VIX_HIGH, VIX_PANIC = 22.0, 30.0  # 现行宏观层阈值 vix_high / vix_panic
BAA_JUMP = 0.30                   # 多因子研究的单因子规则：Baa 利差 20 日走阔 ≥ 0.3pt


def monthly_available(s: pd.Series, days: pd.DatetimeIndex, lag_day: int = 10) -> pd.Series:
    """月度序列（索引 = 月初）→ 每个交易日「已经公布」的最新值：M 月的值在 M+1 月 lag_day 日起可用。"""
    s = s.dropna()
    avail = pd.DatetimeIndex([d + pd.offsets.MonthBegin(1) + pd.Timedelta(days=lag_day - 1) for d in s.index])
    a = pd.Series(s.values, index=avail)
    a = a[~a.index.duplicated(keep="last")].sort_index()
    return a.reindex(days.union(a.index)).ffill().reindex(days)


def factor_frame(days: pd.DatetimeIndex, fx: pd.Series, vix: pd.Series, baa: pd.Series, dgs10: pd.Series,
                 dgs3m: pd.Series, unrate: pd.Series) -> pd.DataFrame:
    """各因子对齐到美国交易日（只用当时已公布的数据）。"""
    def daily(s, lag):
        return s.dropna().reindex(days.union(s.dropna().index)).ffill().reindex(days).shift(lag)
    f = pd.DataFrame(index=days)
    f["fx"] = daily(fx, 0)
    f["vix"] = daily(vix, 0)
    f["baa"] = daily(baa, 1)
    f["curve"] = daily(dgs10, 1) - daily(dgs3m, 1)
    un = unrate.dropna()
    f["un"] = monthly_available(un, days)
    f["un_ma12"] = monthly_available(un.rolling(12).mean(), days)
    f["baa_ma250"] = f["baa"].rolling(250, min_periods=200).mean()
    f["baa_d20"] = f["baa"] - f["baa"].shift(20)
    return f


def _trend(close: pd.Series) -> pd.Series:
    return pd.Series(ma_band(close, L, B, K) == BEAR, index=close.index)


def _persist(raw: pd.Series, k: int = K) -> pd.Series:
    """原始判断连续 k 天一致才切换（与均线带的 k 相同）。"""
    out, state, run, last = [], None, 0, None
    for v in raw.to_numpy(bool):
        run = run + 1 if v == last else 1
        last = v
        if state is None:
            state = bool(v)
        elif v != state and run >= k:
            state = bool(v)
        out.append(state)
    return pd.Series(out, index=raw.index)


def t0_trend(close: pd.Series, f: pd.DataFrame | None = None) -> pd.Series:
    """T0 现行：收盘连续 5 天 < 250 日线 ×0.97 → 熊；连续 5 天 > ×1.03 → 牛。"""
    return _trend(close)


def t1_fx_trend(close: pd.Series, f: pd.DataFrame) -> pd.Series:
    """T1 汇率：同一规则用在日元计价的指数（指数 × USD/JPY）上。"""
    j = (close * f["fx"]).dropna()
    return _trend(j).reindex(close.index).fillna(False).astype(bool)


def t2_growth_trend(close: pd.Series, f: pd.DataFrame) -> pd.Series:
    """T2 增长 + 趋势：趋势熊 且 失业率 > 其 12 个月均值（衰退风险）才熊。"""
    return _trend(close) & (f["un"] > f["un_ma12"]).fillna(False)


def t3_credit_confirm(close: pd.Series, f: pd.DataFrame) -> pd.Series:
    """T3 信用确认：趋势熊 且 Baa−10Y 利差 > 其 250 日均值 才熊。"""
    return _trend(close) & (f["baa"] > f["baa_ma250"]).fillna(False)


def stress_state(f: pd.DataFrame) -> pd.Series:
    """压力态：VIX ≥ 30 且 Baa 利差 20 日走阔 ≥ 0.3pt 时进入，VIX < 22 时解除。"""
    out, on = [], False
    for v, d in zip(f["vix"].to_numpy(float), f["baa_d20"].to_numpy(float)):
        if not on and v >= VIX_PANIC and d >= BAA_JUMP:
            on = True
        elif on and v < VIX_HIGH:
            on = False
        out.append(on)
    return pd.Series(out, index=f.index)


def t4_stress_exit(close: pd.Series, f: pd.DataFrame) -> pd.Series:
    """T4 压力提前离场：趋势熊 或 压力态。"""
    return _trend(close) | stress_state(f)


def t5_momentum(close: pd.Series, f: pd.DataFrame | None = None) -> pd.Series:
    """T5 12 个月绝对动量：每月最后一个交易日 252 日涨幅 ≤ 0 → 熊，持有到下个月末再判断。"""
    mom = close / close.shift(252) - 1
    me = close.index.to_series().groupby(close.index.to_period("M")).max()
    last = close.index[-1]
    if last < last + pd.offsets.BMonthEnd(0):                     # 最后一个月还没到月末：不算月末（与每日实盘一致）
        me = me[me < last.to_period("M").start_time]
    sig = pd.Series(np.nan, index=close.index)
    sig.loc[me.values] = (mom.loc[me.values] <= 0).astype(float)
    return sig.ffill().fillna(0.0).astype(bool)


def t6_majority(close: pd.Series, f: pd.DataFrame) -> pd.Series:
    """T6 多数表决：趋势熊、Baa 利差 > 250 日均值、VIX ≥ 22、失业率 > 12 个月均值、10Y−3M < 0，
    5 项里 ≥3 项为熊的状态连续 5 天才切换。"""
    flags = pd.DataFrame({"trend": _trend(close), "credit": (f["baa"] > f["baa_ma250"]).fillna(False),
                          "vix": (f["vix"] >= VIX_HIGH).fillna(False), "jobs": (f["un"] > f["un_ma12"]).fillna(False),
                          "curve": (f["curve"] < 0).fillna(False)})
    return _persist(flags.sum(axis=1) >= 3)


CANDIDATES = {"T0": t0_trend, "T1": t1_fx_trend, "T2": t2_growth_trend, "T3": t3_credit_confirm,
              "T4": t4_stress_exit, "T5": t5_momentum, "T6": t6_majority}
LABELS = {"T0": "现行 250 日线 ±3%、连续 5 天", "T1": "同规则用在日元计价指数（汇率）",
          "T2": "趋势熊 且 失业率上升（增长+趋势）", "T3": "趋势熊 且 信用利差高于均值",
          "T4": "趋势熊 或 压力态（VIX≥30 且利差急扩）", "T5": "12 个月绝对动量（月度）",
          "T6": "5 因子多数表决（趋势/信用/VIX/失业率/曲线）"}
