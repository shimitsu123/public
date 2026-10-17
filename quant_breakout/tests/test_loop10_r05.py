"""第十个研究循环第 5 轮（scripts/loop10_r05_anchor.py）：CGO 的算法、门槛、常量。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop10_r02_diagfeat as R2  # noqa: E402
import loop10_r05_anchor as R  # noqa: E402


def _df(close, vol):
    idx = pd.bdate_range("2020-01-06", periods=len(close))
    return pd.DataFrame({"Close": close, "Volume": vol}, index=idx)


def test_cgo_series_is_volume_weighted_and_causal():
    df = _df([100.0, 110.0, 90.0, 120.0], [1.0, 3.0, 0.0, 1.0])
    s = R.cgo_series(df, n=3, min_n=2)
    assert np.isnan(s.iloc[0])                                                 # 不到 min_n 天 → 缺值
    assert abs(s.iloc[1] - (110 / ((100 + 330) / 4) - 1)) < 1e-12              # 只用当天为止
    assert abs(s.iloc[3] - (120 / ((330 + 0 + 120) / 4) - 1)) < 1e-12          # 最近 3 天：成交量 0 的那天不算价格
    df2 = df.copy(); df2.iloc[3, 0] = 1e6                                      # 改将来的价格不影响以前的值
    assert np.allclose(R.cgo_series(df2, n=3, min_n=2).iloc[:3].to_numpy(), s.iloc[:3].to_numpy(), equal_nan=True)


def test_cgo_series_zero_volume_window_is_missing():
    df = _df([100.0, 101.0, 102.0], [0.0, 0.0, 0.0])
    assert R.cgo_series(df, n=2, min_n=2).isna().all()


def test_cgo_feature_lookup_and_missing():
    fa = {"A.T": _df([100.0, 110.0, 90.0], [1.0, 1.0, 1.0])}
    d = fa["A.T"].index
    x = R.cgo_feature(["A.T", "A.T", "B.T", "A.T"], [d[2], d[1], d[2], pd.Timestamp("2030-01-01")], fa, n=2, min_n=2)
    assert abs(x[0] - (90 / 100 - 1)) < 1e-12 and abs(x[1] - (110 / 105 - 1)) < 1e-12
    assert np.isnan(x[2]) and np.isnan(x[3])                                   # 没有这只票 / 没有那一天 → 缺值（不挡）


def test_rules_and_constants():
    X = pd.DataFrame({"cgo": [-0.01, 0.0, np.nan], "hi52": [0.84, 0.85, np.nan], "rng": [0.131, 0.13, np.nan]})
    assert list(R.feature_gate(X, R.RULES["CGO"])) == [True, False, False]
    assert list(R.feature_gate(X, R.RULES["H52"])) == [True, False, False]
    assert list(R.feature_gate(X, R.RULES["RNG"])) == [True, False, False]
    assert R.ROUND == 5 and R.IDS == ("CGO", "H52", "RNG") and R.feature_gate is R2.feature_gate
    assert set(R.KINDS.values()) == {"stock"} and R.POSTHOC == {"CGO": False, "H52": True, "RNG": True}
    assert all(v.startswith("选股") for v in R.FAMILY.values())
