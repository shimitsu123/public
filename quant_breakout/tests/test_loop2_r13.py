"""第二个研究循环第 13 轮 RXC（scripts/loop2_r13_rateshock.py，2026-10-02 登记）：登记值、利率急升 = threat 的 rates + 扩展分位、纳指落后、换指数、接法。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r13_rateshock as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.OLD) == (13, ("RXC",), "核心·指数选择", True, ("1987-01-01", "2000-12-31"))
    assert (T.CHG_N, T.PCT_TH, T.REL_N) == (60, 0.80, 63)


def test_rate_change_is_threat_rates_feature():
    from qbreak import threat as TH
    rng = np.random.default_rng(13)
    days = pd.bdate_range("1990-01-01", periods=400)
    dgs = pd.Series(5 + np.cumsum(rng.normal(0, 0.05, 400)), index=days)
    z = pd.Series(1.0, index=days)
    raw = TH.raw_features(days, z * 100, z * 20, z * 2, dgs, z * 3, z * 50, pd.Series(dtype=float))
    got = T.rate_change(dgs, days)
    assert np.allclose(got.dropna().to_numpy(), raw["rates"].dropna().to_numpy())
    assert got.index.equals(raw.index)


def test_rate_shock_uses_expanding_percentile():
    from qbreak import threat as TH
    days = pd.bdate_range("1960-01-01", periods=1200)
    dgs = pd.Series(np.r_[np.linspace(4, 5, 1000), np.linspace(5, 7, 200)], index=days)   # 最后一段急升
    sh = T.rate_shock(dgs, days)
    p = TH.expanding_pct(T.rate_change(dgs, days))
    assert sh.tolist() == ((p >= 0.8) & p.notna()).tolist()
    assert not sh.iloc[:800].any() and sh.iloc[-50:].all()                    # 不足 750 个值 → False；急升段 → True


def test_ndx_lag_compares_63_day_total_returns():
    days = pd.bdate_range("2020-01-01", periods=100)
    ndx = pd.Series(np.r_[np.full(64, 100.0), np.linspace(100, 90, 36)], index=days)
    spx = pd.Series(100.0, index=days)
    lag = T.ndx_lag(ndx, spx, days)
    assert not lag.iloc[:64].any()                                             # 不足 63 天 / 不落后
    assert lag.iloc[65:].all()


def test_switch_state_needs_shock_lag_and_spx_bull():
    idx = pd.bdate_range("2020-01-01", periods=5)
    bear = pd.Series([False, False, True, False, False], index=idx)
    shock = pd.Series([True, True, True, False, True], index=idx)
    lag = pd.Series([True, False, True, True, True], index=idx)
    assert T.switch_state(bear, shock, lag).tolist() == [True, False, False, False, True]


def test_wiring_is_round12_over():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=4)
    fr = pd.DataFrame({"Close": [1.0] * 4}, index=idx)
    W = {"b1": {"extra_core": {"1545.T": fr, Y.HEDGE_T: fr}}, "assets": {"1655.T": fr}, "bear": {"US": pd.Series(False, index=idx)}}
    sw = pd.Series([False, True, True, False], index=idx)
    o = T.rxc_over(W, sw, pd.Series(False, index=idx), fr)
    r = T.R12.nsx_over(W, sw, pd.Series(False, index=idx), fr)
    assert o["cfg_over"] == r["cfg_over"] and set(o["extra_core"]) == set(r["extra_core"])
    assert all(o["extra_bear"][k].tolist() == r["extra_bear"][k].tolist() for k in r["extra_bear"])


def test_cli_takes_no_options():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "RXC"])
