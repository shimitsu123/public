"""scripts/perf_attrib.py（只描述）：月 / 周的期末、当期变化与期初取值不偷看、个股仓位按成交记录重建、三等分与多因素 R²。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import perf_attrib as PA                                                     # noqa: E402


def test_period_ends_and_changes():
    idx = pd.bdate_range("2026-01-05", "2026-03-31")
    ends = PA.period_ends(idx, "M")
    assert [str(d.date()) for d in ends] == ["2026-01-30", "2026-02-27", "2026-03-31"]
    w = PA.period_ends(idx, "W")
    assert all(d.weekday() == 4 for d in w[:-1]) and w[-1] == idx[-1]         # 周五结束；最后一周到数据末尾
    x = pd.Series(np.arange(1, len(idx) + 1, dtype=float), index=idx)
    ch = PA.period_change(x, ends)
    assert np.isnan(ch.iloc[0]) and np.isclose(ch.iloc[1], (x[ends[1]] / x[ends[0]] - 1) * 100)
    pre = PA.at_prev_end(x, ends)
    assert np.isnan(pre.iloc[0]) and pre.iloc[2] == x[ends[1]]                # 期初 = 上一期末（不用本期的数据）


def test_stock_exposure_rebuilt_from_trades():
    idx = pd.bdate_range("2026-01-05", periods=10)
    closes = pd.DataFrame({"A.T": np.full(10, 100.0), "B.T": np.full(10, 50.0)}, index=idx)
    eq = pd.Series(100_000.0, index=idx)
    tr = pd.DataFrame({"ticker": ["A.T", "B.T"], "entry_date": [str(idx[1].date()), str(idx[3].date())],
                       "exit_date": [str(idx[5].date()), str(idx[4].date())], "shares": [100, 200]})
    e = PA.stock_exposure(tr, closes, eq)
    assert e.iloc[0] == 0 and e.iloc[1] == 10.0 and e.iloc[3] == 20.0 and e.iloc[4] == 10.0 and e.iloc[5] == 0.0


def test_tercile_and_ols():
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(0, 1, 300))
    y = 2 * x + rng.normal(0, 1, 300)
    t = PA.tercile_table(y, x)
    assert len(t) == 3 and t[0]["mean"] < t[1]["mean"] < t[2]["mean"] and sum(g["n"] for g in t) == 300
    r2, co = PA.ols_r2(y, pd.DataFrame({"x": x, "z": rng.normal(0, 1, 300)}))
    assert r2 > 0.7 and co["x"]["t"] > 10 and abs(co["z"]["t"]) < 3
    rho, n = PA.spearman(y, x)
    assert rho > 0.8 and n == 300
