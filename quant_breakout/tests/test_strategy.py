"""信号层测试：指标正确性 + 无前视偏差（先読みバイアス）。"""
import numpy as np
import pandas as pd
import pytest

from conftest import make_frame
from qbreak.config import StrategyParams
from qbreak.strategy import atr, compute_indicators, ema, macd


def _series(n=400, seed=7):
    rng = np.random.default_rng(seed)
    c = 1000 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    rows = [(c[i] * 0.999, c[i] * 1.012, c[i] * 0.988, c[i], float(rng.lognormal(13, 0.4)))
            for i in range(n)]
    return make_frame(rows)


def test_ema_matches_manual():
    s = pd.Series([1.0, 2, 3, 4, 5])
    got = ema(s, 3).tolist()
    a = 2 / 4
    want, prev = [], None
    for x in s:
        prev = x if prev is None else a * x + (1 - a) * prev
        want.append(prev)
    assert got == pytest.approx(want)


def test_macd_line_is_fast_minus_slow():
    df = _series(200)
    line, sig, hist = macd(df["Close"], 12, 26, 9)
    assert line.iloc[-1] == pytest.approx(
        ema(df["Close"], 12).iloc[-1] - ema(df["Close"], 26).iloc[-1])
    assert hist.iloc[-1] == pytest.approx(line.iloc[-1] - sig.iloc[-1])


def test_atr_is_positive_and_bounded():
    df = _series(300)
    a = atr(df, 14).dropna()
    assert (a > 0).all()
    assert a.max() < df["Close"].max()


def test_no_lookahead_property():
    """核心不变量：把数据截断到第 k 根，重新计算，第 k 根的信号必须和用完整数据算出来的一致。
    任何用到未来数据的写法都会让这个断言挂掉。"""
    df = _series(400)
    p = StrategyParams(range_n=30, vol_ma_n=10)
    full = compute_indicators(df, p)
    for k in (150, 233, 310, 399):
        part = compute_indicators(df.iloc[:k + 1], p)
        for col in ("entry", "dead_cross", "is_range", "golden_cross", "near_zero", "vol_surge"):
            assert bool(part[col].iloc[-1]) == bool(full[col].iloc[k]), f"{col} @ {k}"
        assert part["macd"].iloc[-1] == pytest.approx(full["macd"].iloc[k])


def test_range_uses_yesterday_value():
    """横盘判定必须用『昨日为止』的振幅：今天的大阳线不能把箱体自己撑大。"""
    rows = [(100, 101, 99, 100, 1e6)] * 80 + [(100, 200, 99, 200, 5e6)]
    df = make_frame(rows)
    ind = compute_indicators(df, StrategyParams(range_n=60))
    assert ind["is_range"].iloc[-1] is np.True_ or bool(ind["is_range"].iloc[-1])  # 昨日振幅≈2% → 横盘
    assert ind["range_pct"].iloc[-1] > 100        # 今日振幅已被大阳线撑到 100%+
    assert not bool(ind["range_pct"].iloc[-1] < 15)  # 若误用当日值则判定会翻转


def test_warmup_blocks_early_signals():
    df = _series(400)
    p = StrategyParams(range_n=90)
    ind = compute_indicators(df, p)
    assert not ind["entry"].iloc[:p.warmup_bars].any()


def test_require_breakout_filter_is_stricter():
    df = _series(600, seed=3)
    base = StrategyParams(range_n=30, range_x_pct=40.0, vol_mult=1.0, macd_zero_band_pct=5.0)
    a = compute_indicators(df, base)["entry"].sum()
    b = compute_indicators(df, StrategyParams(**{**base.to_dict(),
                                                "require_breakout": True}))["entry"].sum()
    assert b <= a


def test_rejects_unsorted_or_duplicated_index():
    df = _series(300)
    with pytest.raises(ValueError):
        compute_indicators(df.iloc[::-1], StrategyParams())
    with pytest.raises(ValueError):
        compute_indicators(pd.concat([df, df.iloc[[-1]]]), StrategyParams())
