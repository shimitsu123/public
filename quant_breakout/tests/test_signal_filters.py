"""个股买点 / 卖点候选（qbreak/signal_filters.py）：只收紧 entry / 只改离场事件；不用未来数据。"""
import numpy as np
import pandas as pd
import pytest

from qbreak import signal_filters as F
from qbreak.config import StrategyParams
from qbreak.strategy import compute_indicators


def _ind(n=900, seed=5):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2015-01-01", periods=n)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n)))
    o = c * (1 + rng.normal(0, 0.004, n))
    df = pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.01, "Low": np.minimum(o, c) * 0.99, "Close": c,
                       "Volume": rng.integers(50_000, 400_000, n).astype(float)}, index=days)
    return compute_indicators(df, StrategyParams(range_x_pct=40.0, vol_mult=1.0))       # 放宽条件，多出一些信号


@pytest.mark.parametrize("key", F.KEYS)
def test_candidates_only_tighten_entry_or_only_change_exit(key):
    df = _ind()
    out = F.apply(df, key)
    assert out["entry"].sum() > 0 or key != "BASE"
    if key in F.ENTRY_FILTERS:
        assert (out["entry"] <= df["entry"]).all() and out["entry"].sum() < df["entry"].sum()
        assert out["dead_cross"].equals(df["dead_cross"])
    elif key == "X1":
        assert out["entry"].equals(df["entry"]) and out["dead_cross"].sum() > 0
    else:
        assert out is df


@pytest.mark.parametrize("key", ["E1", "E2", "E3", "E4", "X1"])
def test_no_lookahead(key):
    """把第 t 天以后的价格改掉，第 t 天及以前的 entry / dead_cross 不变。"""
    df = _ind()
    t = 700
    raw = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    raw.iloc[t + 1:, :4] *= 1.8
    alt = compute_indicators(raw, StrategyParams(range_x_pct=40.0, vol_mult=1.0))
    a, b = F.apply(df, key), F.apply(alt, key)
    col = "dead_cross" if key == "X1" else "entry"
    assert a[col].iloc[:t + 1].equals(b[col].iloc[:t + 1])


def test_rules_match_their_definitions():
    df = _ind()
    c = df["Close"]
    m200 = c.rolling(200).mean()
    i = int(np.argmax((F.trend_ok(df)).to_numpy()))
    assert c.iloc[i] > m200.iloc[i] and m200.iloc[i] > m200.iloc[i - 20]
    j = int(np.argmax((~F.near_high_ok(df) & c.rolling(252).max().notna()).to_numpy()))
    assert c.iloc[j] < c.rolling(252).max().iloc[j] * 0.75
    ev = F.confirmed_exit(df)
    k = int(np.argmax(ev.to_numpy()))
    assert df["macd"].iloc[k] < df["macd_sig"].iloc[k] and c.iloc[k] < c.rolling(20).mean().iloc[k]
    assert not (ev & ev.shift(1, fill_value=False)).any()                 # 事件：连续成立只算第一天
