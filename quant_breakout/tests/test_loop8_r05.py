"""第八个研究循环第 5 轮 SSR（scripts/loop8_r05_shortratio.py，2026-10-04 登记）：登记的常数与判定的接线、全市场空売り比率（33 业种合计、不含 9999）、
去趋势（最近 21 天 − 再之前 250 天，只用决定日以前）、月度「被挡」只在月末之后变且 2017 年以前不挡。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop8_r05_shortratio as V  # noqa: E402
import research_loop8 as L8  # noqa: E402


def test_registered_constants_and_judgment():
    assert (V.ROUND, V.IDS, V.FAMILY, V.POSTHOC, V.N_RECENT, V.N_BASE) == (5, ("SSR",), "卖空·空売り比率", False, 21, 250)
    assert V.FAMILY in L8.SOURCES and len(V.S33) == 33 and "9999" not in V.S33 and len(set(V.S33)) == 33
    assert (V.GATE_FROM, V.SEED_INFO, V.SEED_S2, V.PLACEBO_N, V.SHIFT_GAP) == ("2017-01-01", 20261017, 20261018, 400, 250)
    ra, ic, s1, s2 = (inspect.getsource(f) for f in (V.run_all, V.info_check, V.stage_one, V.stage_two))
    assert "RL8.info_judge({\"JP\": ic}, {\"JP\": ic}, boot, sign=-1, halves=h)" in ic and "seed=SEED_INFO" in ic
    assert "if not A[\"judge\"][\"ok\"]:" in ra and "RL8.FAIL_INFO" in ra and "R7.FOUND if b[\"stage2\"][\"ok\"] else R7.FAIL2" in ra
    assert "R6.stage1(cand, base, trade=os_, posthoc=None)" in s1 and "RL.stage2(stat, vals)" in s2 and "shift_ks(n)" in s2


def test_daily_ratio_sums_sectors():
    df = pd.DataFrame({"Date": ["2024-01-04"] * 3 + ["2024-01-05"],
                       "S33": ["0050", "1050", "1050", "0050"],
                       "SellExShortVa": [60.0, 30.0, 30.0, 50.0], "ShrtWithResVa": [30.0, 5.0, 5.0, 25.0], "ShrtNoResVa": [10.0, 5.0, 5.0, 25.0]})
    sr = V.daily_ratio(df)
    assert sr.loc["2024-01-04"] == pytest.approx(50.0 / 140.0)                 # 重复的 1050 只算一次
    assert sr.loc["2024-01-05"] == pytest.approx(0.5)


def test_detrended_uses_only_past():
    idx = pd.bdate_range("2017-01-02", periods=300)
    sr = pd.Series(np.r_[np.full(279, 0.40), np.full(21, 0.45)], index=idx)
    t = pd.DatetimeIndex([idx[-1], idx[-2], idx[200]])
    x = V.detrended(sr, t)
    assert x.iloc[0] == pytest.approx(0.05)                                     # 最近 21 天 0.45 − 再之前 250 天 0.40
    assert x.iloc[1] == pytest.approx((20 * 0.45 + 0.40) / 21 - 0.40)
    assert np.isnan(x.iloc[2])                                                  # 不够 271 天
    lv = V.level(sr, pd.DatetimeIndex([idx[-1]]))
    assert lv.iloc[0] == pytest.approx(0.45)


def test_gate_flags_monthly_from_2017():
    idx = pd.bdate_range("2016-11-01", "2017-04-10")
    c = pd.Series(100.0, index=idx)
    me = L8.month_ends_done(c)
    x = pd.Series([0.01, 0.02, -0.01, np.nan, 0.03], index=me[:5])
    g = V.gate_flags(c, x)
    assert not g[g.index < pd.Timestamp("2017-01-01")].any()
    assert g[(g.index >= "2017-01-01") & (g.index < me[2])].all()
    assert not g[(g.index >= me[2]) & (g.index < me[4])].any() and g.loc[me[4]]


def test_shift_ks_seed():
    ks = V.shift_ks(2400)
    assert len(ks) == 400 and min(ks) >= 250 and max(ks) <= 2150 and ks == V.shift_ks(2400)
    assert ks != __import__("loop8_r04_foreign").shift_ks(2400)                # 与第 4 轮不同的种子
    with pytest.raises(ValueError):
        V.shift_ks(500)
