"""scripts/core_points_study.py 的规则（纯函数）：过热的滞回、1545 的再乘比例。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import core_points_study as CP  # noqa: E402


def test_overheat_hysteresis():
    idx = pd.bdate_range("2020-01-01", periods=7)
    tr = pd.Series([100, 100, 100, 140, 150, 150, 150], index=idx, dtype=float)
    # 3 日线：140 → +23.5%（进入）；150 → +15.4%（> 10% 还在）；150 → +2.3%（解除）
    assert CP.overheat(tr, n=3, hot_in=20, hot_out=10).tolist() == [False, False, False, True, True, False, False]


def test_expo_only_in_us_bull():
    idx = pd.bdate_range("2020-01-01", periods=4)
    bear = pd.Series([False, False, True, True], index=idx)
    sig = pd.Series([True, False, True, False], index=idx)
    e = CP.expo(bear, sig, 2 / 3)
    assert np.allclose(e.to_numpy(), [2 / 3, 1, 1, 1])
    assert CP.KEEP["NXC"] == 0.0 and CP.IDS == ("OXT", "NXC")
