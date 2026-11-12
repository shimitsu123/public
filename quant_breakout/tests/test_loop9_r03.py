"""第九个研究循环第 3 轮（scripts/loop9_r03_relative.py）的纯函数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop9_r03_relative as R  # noqa: E402


def test_rel_weak_days_compares_n_day_returns():
    idx = pd.bdate_range("2020-01-06", periods=4)
    jp = pd.Series([100.0, 101.0, 103.0, 100.0], index=idx)
    core = pd.Series([50.0, 50.0, 52.0, 51.0], index=idx)
    w = R.rel_weak_days(jp, core, n=2)
    # 第 3 天：日本 +3.0% vs 核心 +4.0% → 输；第 4 天：日本 −0.99% vs 核心 +2.0% → 输；前 2 天不够
    assert list(w) == [False, False, True, True]


def test_rel_weak_days_ffills_core_on_missing_days():
    jp = pd.Series([100.0, 110.0, 120.0], index=pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08"]))
    core = pd.Series([50.0, 60.0], index=pd.to_datetime(["2020-01-06", "2020-01-08"]))   # 1/7 没有 → 用 1/6
    w = R.rel_weak_days(jp, core, n=1)
    assert list(w) == [False, False, True]                                     # 1/8：日本 +9.1% vs 核心 +20% → 输


def test_open_gap_and_gate_band():
    idx = pd.bdate_range("2020-01-06", periods=4)
    df = pd.DataFrame({"Open": [100, 102.0, 104.0, 99.0], "Close": [100.0, 100.0, 100.0, 100.0]}, index=idx)
    assert round(R.open_gap(df, idx[0]), 6) == 0.02
    assert np.isnan(R.open_gap(df, idx[3]))                                   # 最后一天没有下一根
    assert np.isnan(R.open_gap(None, idx[0]))
    g = R.gap_gate(["A", "A", "A"], [idx[0], idx[1], idx[2]], {"A": df})
    assert list(g) == [True, False, False]                                    # +2% 挡；+4%（> 3% 本来就不成交）不挡；−1% 不挡
