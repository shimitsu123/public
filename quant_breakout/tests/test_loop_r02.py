"""研究循环第 2 轮（scripts/loop_r02_bearstate.py，2026-10-01 登记）：登记值、熊序列合并、挡新仓的倍数、信号日对齐、循环平移。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_r02_bearstate as B  # noqa: E402


def test_registered_constants():
    assert (B.ROUND, B.IDS, B.OR_KEY) == (2, ("HBOR", "UBG"), "US_OR")
    assert (B.SHIFT_FROM, B.SHIFT_GAP, B.SEED0) == ("2000-01-03", 250, 20261002)


def test_union_bear_forward_fills_each_side():
    a = pd.Series([False, True, False], index=pd.to_datetime(["2020-01-06", "2020-01-08", "2020-01-10"]))
    b = pd.Series([False, True], index=pd.to_datetime(["2020-01-07", "2020-01-09"]))
    u = B.union_bear(a, b)
    assert u.index.tolist() == pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09", "2020-01-10"]).tolist()
    assert u.tolist() == [False, False, True, True, True]                                  # 01-10：a 回牛，b 还是熊


def test_gate_factor_and_bear_at_use_same_day_value():
    bear = pd.Series([False, True, False], index=pd.to_datetime(["2020-01-03", "2020-01-07", "2020-01-09"]))
    days = pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09", "2020-01-10"])
    f = B.gate_factor(bear, days)
    assert f.tolist() == [1.0, 0.0, 0.0, 1.0, 1.0]                                         # 当天（向后填）的熊 → 0
    assert B.bear_at(bear, days).tolist() == [False, True, True, False, False]
    assert B.gate_factor(bear.iloc[0:0].astype(bool), days).tolist() == [1.0] * 5          # 没有值 = 不是熊


def test_shift_placebo_keeps_bear_days_and_is_reproducible():
    idx = pd.bdate_range("1999-06-01", "2026-10-30")
    s = pd.Series((np.arange(len(idx)) % 300) < 60, index=idx)
    a, b = B.shifted(s, 5), B.shifted(s, 5)
    assert a.equals(b) and int(a.sum()) == int(B.shift_domain(s).sum())                   # 熊的天数不变
    w = B.shift_domain(s)
    ks = [B.shift_k(x, len(w)) for x in range(400)]
    assert min(ks) >= 250 and max(ks) <= len(w) - 250 and len(set(ks)) > 300


def test_hb_over_points_core_to_extra_key():
    s = pd.Series([True], index=[pd.Timestamp("2020-01-06")])
    o = B.hb_over(s)
    assert o["cfg_over"]["core_index"] == {"1545.T": "US_OR"} and o["extra_bear"]["US_OR"] is s
    assert o["cfg_over"]["core"] == {"1545.T": 1.0} and o["cfg_over"]["core_mode"] == "split"
