"""第九个研究循环第 1 轮（scripts/loop9_r01_market.py）的纯函数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop9_r01_market as R  # noqa: E402


def test_adr_series_counts_advances_over_declines():
    idx = pd.bdate_range("2020-01-06", periods=4)
    closes = pd.DataFrame({"A": [10, 11, 12, 11], "B": [10, 9, 9, 10], "C": [5, 6, np.nan, 7]}, index=idx)
    adr = R.adr_series(closes, n=3)
    # 第 2〜4 天：A ↑↑↓、B ↓ 平 ↑、C ↑（NaN 不算）→ 上涨 1+1+1 / 1+0+... 逐日：d2 adv 2 dec 1；d3 adv 1 dec 0；d4 adv 1 dec 1
    assert np.isnan(adr.iloc[2])                                              # 第一天没有涨跌 → 前 3 天不够
    assert round(adr.iloc[3], 6) == round((2 + 1 + 1) / (1 + 0 + 1) * 100, 6)


def test_hot_days_threshold():
    s = pd.Series([119.9, 120.0, np.nan, 150.0])
    assert list(R.hot_days(s)) == [False, True, False, True]


def test_below_ma_days_needs_full_window():
    c = pd.Series([10, 10, 10, 9, 12], index=pd.bdate_range("2020-01-06", periods=5), dtype=float)
    b = R.below_ma_days(c, n=3)
    assert list(b) == [False, False, False, True, False]


def test_on_days_aligns_and_forward_fills():
    s = pd.Series([True, False], index=pd.to_datetime(["2020-01-06", "2020-01-08"]))
    days = pd.bdate_range("2020-01-03", periods=5)                           # 1/3（之前没有值）、1/6、1/7、1/8、1/9
    assert list(R.on_days(s, days)) == [False, True, True, False, False]
