"""呼値取整与数据层质量检查。"""
import pandas as pd
import pytest

from conftest import make_frame
from qbreak.config import DataConfig
from qbreak.data import DataError, load_universe, synthetic, validate_ohlcv
from qbreak.tick import round_to_tick, tick_size


@pytest.mark.parametrize("price,unit", [
    (999, 1), (3000, 1), (3001, 5), (5000, 5), (5001, 10), (30000, 10),
    (30001, 50), (50000, 50), (50001, 100), (300000, 100), (300001, 500),
])
def test_tick_size_bands(price, unit):
    assert tick_size(price) == unit


@pytest.mark.parametrize("raw", [1234.4, 2999.9, 3001.9, 4999.1, 30010.0, 123.456])
def test_rounded_price_is_always_legal(raw):
    for side in ("BUY", "SELL"):
        px = round_to_tick(raw, "7203.T", side)
        assert abs(px / tick_size(px) - round(px / tick_size(px))) < 1e-9


def test_buy_rounds_down_sell_rounds_up():
    assert round_to_tick(3002.0, "7203.T", "BUY") == 3000.0
    assert round_to_tick(3002.0, "7203.T", "SELL") == 3005.0


def test_round_to_tick_rejects_nonpositive():
    with pytest.raises(ValueError):
        round_to_tick(0, "7203.T", "BUY")


# ────────── 数据质量 ──────────
def _cfg(**kw):
    return DataConfig(provider="csv", min_bars=10, **kw)


def test_validate_drops_duplicates_and_sorts():
    df = make_frame([(1, 2, 0.5, 1, 100)] * 20)
    df = pd.concat([df, df.iloc[[-1]]]).iloc[::-1]
    out = validate_ohlcv("X", df, _cfg())
    assert out.index.is_monotonic_increasing and not out.index.has_duplicates


def test_validate_rejects_too_short():
    with pytest.raises(DataError):
        validate_ohlcv("X", make_frame([(1, 2, 0.5, 1, 100)] * 5), _cfg())


def test_validate_drops_nonpositive_prices():
    rows = [(1, 2, 0.5, 1, 100)] * 20 + [(0, 0, 0, 0, 0)]
    out = validate_ohlcv("X", make_frame(rows), _cfg())
    assert len(out) == 20 and (out[["Open", "High", "Low", "Close"]] > 0).all().all()


def test_validate_drops_inverted_high_low_rows():
    rows = [(10, 11, 9, 10, 100)] * 20 + [(10, 9, 11, 10, 100)] * 2   # 后两根 High<Low
    out = validate_ohlcv("X", make_frame(rows), _cfg())
    assert len(out) == 20 and (out["High"] >= out["Low"]).all()


def test_validate_enforces_high_low_contain_open_close():
    rows = [(10, 10.2, 9.8, 10, 100)] * 19 + [(12, 10.2, 9.8, 11, 100)]
    out = validate_ohlcv("X", make_frame(rows), _cfg())
    assert out["High"].iloc[-1] >= out["Open"].iloc[-1]
    assert out["Low"].iloc[-1] <= out["Close"].iloc[-1]


def test_synthetic_is_deterministic():
    """原版用内置 hash()，受 PYTHONHASHSEED 影响每次运行都不同，结果无法复现。"""
    a = synthetic("7203.T", 2)
    b = synthetic("7203.T", 2)
    assert a["Close"].round(6).equals(b["Close"].round(6))
    assert not a["Close"].round(6).equals(synthetic("6758.T", 2)["Close"].round(6))


def test_synthetic_is_opt_in_only():
    """默认必须拒绝造假数据：宁可报错，也不要"看起来正常的假结果"。"""
    with pytest.raises(DataError):
        load_universe(["NOPE.T"], DataConfig(provider="csv", allow_synthetic=False))
    got = load_universe(["NOPE.T"], DataConfig(provider="csv", allow_synthetic=True, years=2))
    assert "NOPE.T" in got
