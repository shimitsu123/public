"""研究数据的分红调整（qbreak/pit_data.div_adjust；2026-10-12「修研究数据并重跑」）：与 yfinance auto_adjust 同一口径。"""
import numpy as np
import pandas as pd

from qbreak import pit_data as PD


def test_div_adjust_back_adjusts_before_ex_date_only():
    idx = pd.bdate_range("2024-09-24", periods=5)
    df = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": [100.0, 100.0, 100.0, 98.0, 98.0], "Volume": 1e5}, index=idx)
    div = pd.Series([2.0], index=[idx[3]])                                  # 除权日 = 第 4 天，前一天收盘 100 → 系数 0.98
    out = PD.div_adjust(df, div)
    assert np.allclose(out["Close"].iloc[:3], 98.0) and np.allclose(out["Close"].iloc[3:], 98.0)   # 除权那一下不再是下跌
    assert (out["Volume"] == df["Volume"]).all()
    assert PD.div_adjust(df, pd.Series(dtype=float)) is df                   # 没有分红 → 原样
