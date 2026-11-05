"""scripts/household_spend_study.py 的纯函数：信号的时点（调查月 + 2 个月才用）、相对整体消费、IC。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import household_spend_study as S  # noqa: E402


def test_signal_uses_month_minus_two_and_relative_growth():
    months = pd.period_range("2020-01", "2021-12", freq="M").strftime("%Y-%m")
    w = pd.DataFrame({"消費支出": 100.0, "ビール": [100.0] * 12 + [110.0] * 12, "米": 100.0}, index=months)
    T = pd.DatetimeIndex([pd.Timestamp("2021-05-31")])
    s = S.signals(w, T)
    # 2021-05 月末能用的是 2021-03 调查月：3 个月平均 110 vs 一年前 100 → +10%，整体 0%
    assert np.isclose(s.loc[T[0], "ビール"], 0.10) and np.isclose(s.loc[T[0], "米"], 0.0) and "消費支出" not in s.columns


def test_ic_and_verdict():
    T = pd.date_range("2005-01-31", periods=200, freq="ME")
    items = [f"i{k}" for k in range(12)]
    sig = pd.DataFrame(np.tile(np.arange(12, dtype=float), (200, 1)), index=T, columns=items)
    ret = sig * 0.01
    ic = S.ic_series(sig, ret)
    assert np.allclose(ic.to_numpy(), 1.0)
    noisy = ic * 0 + 0.1 + 0.05 * np.sin(np.arange(len(ic)))
    v = S.verdict(noisy)
    assert v["info"] and v["ic_h1"] > 0 and v["ic_h2"] > 0
