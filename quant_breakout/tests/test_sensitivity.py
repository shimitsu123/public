"""个股宏观敏感度与顺风度（qbreak/sensitivity.py）：能找回已知系数、只用截止日为止的数据、说明文字方向正确。"""
import numpy as np
import pandas as pd

from qbreak import sensitivity as SN


def _levels(n=900, seed=2):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2020-01-06", periods=n)
    lv = pd.DataFrame({"rate_jp": np.cumsum(rng.normal(0, 0.01, n)), "rate_us": np.cumsum(rng.normal(0, 0.02, n)),
                       "oil": np.log(70) + np.cumsum(rng.normal(0, 0.02, n)), "fx": np.log(140) + np.cumsum(rng.normal(0, 0.005, n)),
                       "credit": 2 + np.cumsum(rng.normal(0, 0.01, n)), "mkt": np.log(30000) + np.cumsum(rng.normal(0, 0.01, n))},
                      index=days)
    return lv, rng


def test_factor_levels_use_previous_us_close():
    jp = pd.DatetimeIndex(["2026-09-24", "2026-09-25", "2026-09-28"])
    us = pd.Series([4.0, 4.1, 4.2], index=pd.DatetimeIndex(["2026-09-23", "2026-09-24", "2026-09-25"]))
    one = pd.Series(1.0, index=us.index)
    lv = SN.factor_levels(jp, pd.Series(100.0, index=jp), pd.Series([1.0, 1.1, 1.2], index=jp), us, one * 60, one * 150, us)
    assert list(lv["rate_us"]) == [4.0, 4.1, 4.2] and list(lv["rate_jp"]) == [1.0, 1.1, 1.2]


def test_betas_recover_known_exposures_and_ignore_future():
    lv, rng = _levels()
    W = SN.weekly_changes(lv)
    X = W[SN.FACTORS + ["mkt"]]
    y = 1.2 * X["mkt"] + 2.0 * X["oil"] - 3.0 * X["rate_jp"] + pd.Series(rng.normal(0, 0.3, len(X)), index=X.index)
    end = X.index[150]
    b = SN.betas(y, X, end)
    assert abs(b["oil"] - 2.0) < 0.2 and abs(b["rate_jp"] + 3.0) < 1.0 and abs(b["mkt"] - 1.2) < 0.2
    y2 = y.where(y.index <= end, 99.0)
    assert SN.betas(y2, X, end).equals(b)                                   # 截止日之后的数据不影响
    assert SN.betas(y, X, X.index[20]) is None                              # 不足 60 周


def test_trend_and_fit_text():
    days = pd.bdate_range("2026-01-05", periods=61)
    lv = pd.DataFrame({"rate_jp": np.linspace(1.0, 1.24, 61), "rate_us": 4.0, "oil": np.log(np.linspace(60, 66, 61)),
                       "fx": np.log(150.0), "credit": 2.0, "mkt": 10.0}, index=days)
    tr = SN.trend(lv, days[-1])
    assert abs(tr["rate_jp"] - 0.24 / 12) < 1e-12 and abs(tr["oil"] - np.log(1.1) * 100 / 12) < 1e-9
    b = pd.Series({"rate_jp": 5.0, "rate_us": 0.0, "oil": -0.5, "fx": 0.0, "credit": 0.0, "mkt": 1.0})
    s, why = SN.fit_score(b, tr)
    assert abs(s - (5 * 0.02 - 0.5 * tr["oil"])) < 1e-9
    assert why.startswith("油价↑ 受损") and "日本利率↑ 受益" in why
