"""第九个研究循环第 7 轮（scripts/loop9_r07_sentliq.py）的纯函数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop9_r07_sentliq as R  # noqa: E402


def _df(opens, closes, vols, start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Open": np.asarray(opens, float), "Close": np.asarray(closes, float), "Volume": np.asarray(vols, float)}, index=idx)


def test_overnight_returns_drop_bad_ratios():
    df = _df([10, 11, 30, 10.5], [10, 10, 10, 10], [1, 1, 1, 1])
    r = R.overnight_returns({"A": df})["A"]
    assert np.isnan(r.iloc[0]) and abs(r.iloc[1] - 0.1) < 1e-12               # 第 2 天 11 ÷ 10 − 1
    assert np.isnan(r.iloc[2])                                                  # 30 ÷ 10 = 3.0 > 1.7 → 坏数据
    assert abs(r.iloc[3] - 0.05) < 1e-12


def test_monthly_mean_needs_min_days():
    idx = pd.bdate_range("2020-01-01", "2020-02-28")
    R_ = pd.DataFrame({"A": np.ones(len(idx)) * 0.01}, index=idx)
    R_.loc["2020-02-01":, "A"] = np.nan
    R_.loc["2020-02-03":"2020-02-07", "A"] = 0.02                              # 2 月只有 5 天
    M = R.monthly_mean(R_, min_n=15)
    assert abs(M.loc[pd.Period("2020-01", "M"), "A"] - 0.01) < 1e-12 and np.isnan(M.loc[pd.Period("2020-02", "M"), "A"])


def test_cv_months_matches_direct_formula():
    idx = pd.bdate_range("2020-01-01", "2020-06-30")
    rng = np.random.default_rng(0)
    TV = pd.DataFrame({"A": rng.uniform(1, 3, len(idx))}, index=idx)
    cv = R.cv_months(TV, months=6, min_n=50)
    x = TV["A"].to_numpy()
    assert abs(cv.loc[pd.Period("2020-06", "M"), "A"] - x.std(ddof=1) / x.mean()) < 1e-9
    assert np.isnan(cv.loc[pd.Period("2020-05", "M"), "A"])                    # 不满 6 个月 → NaN


def test_prev_month_gate_uses_previous_month_only():
    P = pd.DataFrame({"A": [0.95, 0.10], "B": [0.50, 0.99]}, index=pd.PeriodIndex(["2020-01", "2020-02"], freq="M"))
    d = pd.to_datetime(["2020-02-10", "2020-02-10", "2020-03-02", "2020-03-02", "2020-01-15"])
    g = R.prev_month_gate(["A", "B", "A", "B", "A"], d, P, top=0.9)
    assert list(g) == [True, False, False, True, False]                        # 2 月的信号看 1 月；3 月的看 2 月；1 月的没有上个月 → 不挡


def test_round_constants():
    assert R.IDS == ("ONS", "LVV") and set(R.KINDS.values()) == {"stock"} and R.POSTHOC is False
    assert all(v.startswith("选股") for v in R.FAMILY.values())
