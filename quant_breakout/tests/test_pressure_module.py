"""qbreak/pressure.py：与登记的研究脚本（pressure_study 38b648e、threat_pressure_global f01ea80）逐项一致；当天读数只用已知数据；
每日历史 daily_pg 在每一天都等于那天的 now_reading；C_rel 公式。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qbreak import pressure as PR                                           # noqa: E402

import pressure_study as PS                                                  # noqa: E402
import threat_pressure_global as TPG                                         # noqa: E402


def _close(n=2600, seed=5):
    days = pd.bdate_range("1995-01-02", periods=n)
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n))), index=days)


def _macro(dates):
    """只由月份决定（与真实的「上个月月均」一样，同一个月的每一天取值相同）。"""
    d = pd.DatetimeIndex(dates)
    k = (d.year.to_numpy() * 12 + d.month.to_numpy()).astype(float)
    return pd.DataFrame({"rate": np.sin(k / 7.0), "curve": np.cos(k / 11.0), "credit": (k % 5).astype(float)}, index=d)


def test_constants_match_registered_studies():
    assert (PR.RUNUP_D, PR.MA_D, PR.VOL_D) == (PS.RUNUP_D, PS.MA_D, PS.VOL_D)
    assert (PR.WIN_M, PR.MIN_M) == (PS.WIN_M, PS.MIN_M) and PR.MIN_COMP == TPG.MIN_COMP == 4
    assert PR.PCOMP == TPG.PCOMP


def test_parts_and_scores_identical_to_scripts():
    c = _close()
    assert PR.price_parts(c).equals(PS.price_parts(c))
    x = pd.Series(np.random.default_rng(1).normal(size=300))
    assert np.allclose(PR.rolling_pct(x), PS.rolling_pct(x), equal_nan=True)
    dates = PR.month_ends(c)
    assert dates.equals(PS.month_ends(c))
    raw = PR.pressure_raw(c, dates, _macro(dates))
    assert raw.equals(TPG.pressure_raw(c, dates, _macro(dates)))
    assert PR.p_scores(raw).equals(TPG.p_scores(raw))
    m = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]))
    d = pd.DatetimeIndex(["2020-03-31"])
    assert PR.month_lag1(m, d).iloc[0] == PS.month_lag1(m, d).iloc[0] == 2.0


def test_macro_from_matches_study_formula():
    idx = pd.date_range("2000-01-01", periods=40, freq="MS")
    y10 = pd.Series(np.linspace(5, 3, 40), index=idx)
    y3 = pd.Series(np.linspace(4, 1, 40), index=idx)
    baa = pd.Series(np.linspace(7, 6, 40), index=idx)
    d = pd.DatetimeIndex(["2002-06-28"])
    m = PR.macro_from(y10, y3, baa, d).iloc[0]
    k = list(idx).index(pd.Timestamp("2002-05-01"))                         # 上个月
    assert np.isclose(m["rate"], y10.iloc[k] - y10.iloc[k - 12])
    assert np.isclose(m["curve"], -(y10.iloc[k] - y3.iloc[k])) and np.isclose(m["credit"], -(baa.iloc[k] - y10.iloc[k]))


def test_now_reading_matches_global_script_and_daily_history():
    c = _close()
    a0 = pd.Series(50.0, index=c.index)
    ref = TPG.now_reading(c, a0, macro_fn=_macro)
    got = PR.now_reading(c, macro_fn=_macro)
    assert got["P_g"] == ref["P_g"] and got["date"] == ref["date"]
    dp = PR.daily_pg(c, macro_fn=_macro, start="2003-01-01")
    assert np.isclose(round(dp.iloc[-1], 1), got["P_g"])
    for cut in (c.index[2100], c.index[2350], c.index[2550]):                # 历史上的每一天 = 那天只用当时数据的读数
        sub = c[c.index <= cut]
        assert np.isclose(round(dp.loc[cut], 1), PR.now_reading(sub, macro_fn=_macro)["P_g"])


def test_c_rel():
    assert PR.c_rel(60.0, 30.0) == 65.0 and PR.c_rel(None, 30.0) is None and PR.c_rel(50.0, float("nan")) is None
