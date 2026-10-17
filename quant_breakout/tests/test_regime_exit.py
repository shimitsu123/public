"""scripts/regime_exit_explore.py：效率比的定义（单边 = 1、来回 = 0）与只用当天为止的数据；条件离场列。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import regime_exit_explore as R                                             # noqa: E402


def test_efficiency_ratio():
    up = pd.Series(np.arange(1.0, 31.0))
    assert abs(R.efficiency_ratio(up, 10).iloc[-1] - 1.0) < 1e-12
    zig = pd.Series([100.0, 101.0] * 15)
    assert R.efficiency_ratio(zig, 10).iloc[-1] < 0.11
    s = pd.Series(np.random.default_rng(0).normal(0, 1, 60).cumsum() + 100)
    s2 = s.copy()
    s2.iloc[40:] += 5
    assert np.allclose(R.efficiency_ratio(s, 10).iloc[:40].fillna(-1), R.efficiency_ratio(s2, 10).iloc[:40].fillna(-1))


def test_cond_exit_only_when_choppy():
    d = pd.bdate_range("2026-01-05", periods=12)
    px = [100.0] * 6 + [90.0] * 6                                              # 第 6 天起收盘 < 5 日线
    df = pd.DataFrame({"Close": px, "dead_cross": False}, index=d)
    er = pd.Series([0.9] * 8 + [0.1] * 4, index=d)
    out = R.cond_exit({"A.T": df}, er, 0.3)["A.T"]["dead_cross"].to_numpy()
    assert not out[:8].any() and out[8:10].all()
