"""研究循环第 3 轮 LV25（scripts/loop_r03_calmlever.py，2026-10-01 登记）：登记值、平静的定义、2869 的开关、循环平移、引擎参数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_r03_calmlever as LV  # noqa: E402


def test_registered_constants():
    assert (LV.ROUND, LV.ID, LV.W_BASE, LV.W_LEV, LV.LEV_T, LV.LEV_KEY) == (3, "LV25", 0.75, 0.25, "2869.T", "US_LV")
    assert (LV.SHIFT_FROM, LV.SHIFT_GAP, LV.SEED0) == ("2000-01-03", 250, 20261003)


def test_volatile_is_sigma_at_or_above_target_and_missing_counts_as_volatile():
    idx = pd.bdate_range("2001-01-01", periods=5)
    sig = pd.Series([0.1, 0.2, 0.3, np.nan, 0.15], index=idx)
    tgt = pd.Series([0.2, 0.2, 0.2, 0.2, np.nan], index=idx)
    assert LV.volatile(sig, tgt).tolist() == [False, True, True, True, True]


def test_lever_off_is_bear_or_volatile():
    b = pd.Series([False, True, False], index=pd.to_datetime(["2020-01-06", "2020-01-08", "2020-01-10"]))
    v = pd.Series([False, False, True, False], index=pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-09", "2020-01-10"]))
    o = LV.lever_off(b, v)
    assert o.tolist() == [False, False, True, True, False]                                 # 01-08 熊；01-09 熊（向后填）且不平静；01-10 都不是


def test_shift_keeps_volatile_days():
    idx = pd.bdate_range("1999-06-01", "2026-10-30")
    s = pd.Series((np.arange(len(idx)) % 200) < 70, index=idx)
    a = LV.shifted(s, 7)
    assert a.equals(LV.shifted(s, 7)) and int(a.sum()) == int(LV.shift_domain(s).sum())
    ks = [LV.shift_k(x, len(LV.shift_domain(s))) for x in range(400)]
    assert min(ks) >= 250 and len(set(ks)) > 300


def test_lever_over_uses_follow_mode_with_two_cores():
    fr = pd.DataFrame({"Close": [1.0]}, index=[pd.Timestamp("2020-01-06")])
    W = {"kw": {"Z": {"extra_core": {"1545.T": fr}}}, "assets": {"2869.T": fr}}
    off = pd.Series([True], index=[pd.Timestamp("2020-01-06")])
    o = LV.lever_over(W, off)
    assert o["cfg_over"]["core"] == {"1545.T": 0.75, "2869.T": 0.25} and o["cfg_over"]["core_mode"] == "follow"
    assert o["cfg_over"]["core_index"] == {"1545.T": "US", "2869.T": "US_LV"} and o["extra_bear"]["US_LV"] is off
    assert set(o["extra_core"]) == {"1545.T", "2869.T"} and set(W["kw"]["Z"]["extra_core"]) == {"1545.T"}   # 原来的不改
