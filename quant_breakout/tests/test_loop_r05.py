"""研究循环第 5 轮 RDH / SEX（scripts/loop_r05_ratediff.py，2026-10-01 登记）：登记值、利差的时点、收窄状态机、清仓列、循环平移。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_r05_ratediff as R  # noqa: E402


def test_registered_constants():
    assert (R.ROUND, R.IDS, R.DIFF_N, R.ON_THR, R.OFF_THR) == (5, ("RDH", "SEX"), 63, -0.50, -0.25)
    assert (R.SHIFT_FROM, R.SHIFT_GAP, R.SEED0) == ("2000-01-03", 250, 20261005)


def test_spread_uses_previous_values_on_both_sides():
    us = pd.Series([5.0, 4.0, 3.0, 2.0], index=pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09"]))
    jp = pd.Series([0.1, 0.2, 0.3], index=pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-09"]))
    s = R.spread_us_days(us, jp)
    # 01-07：美国用 01-06 的 5.0；日本用「01-07 之前最后一个值的前一个」= 01-06 的 0.1（日本序列先整体 shift 一格）
    assert abs(s.loc["2020-01-07"] - (5.0 - 0.1)) < 1e-12
    assert abs(s.loc["2020-01-08"] - (4.0 - 0.1)) < 1e-12                                  # 日本 01-07 的 0.2 要到下一个日本值才可用
    assert abs(s.loc["2020-01-09"] - (3.0 - 0.2)) < 1e-12


def test_narrowing_state_hysteresis():
    s = pd.Series(np.r_[np.full(70, 3.0), np.linspace(3.0, 2.3, 10), np.full(80, 2.3), np.linspace(2.3, 3.0, 60)],
                  index=pd.bdate_range("2010-01-01", periods=220))
    st = R.narrowing_state(s)
    d = (s - s.shift(63)).to_numpy()
    first = int(np.argmax(st.to_numpy()))
    assert d[first] <= -0.50 and not (d[:first][np.isfinite(d[:first])] <= -0.50).any()
    end = first + int(np.argmax(~st.to_numpy()[first:]))
    assert d[end] >= -0.25 and (d[first:end] < -0.25).all()                                 # 回到 ≥ −0.25 pp 才结束
    assert R.episodes(st) == 1


def test_climax_frames_marks_bear_days_only():
    idx = pd.bdate_range("2020-01-06", periods=4)
    df = pd.DataFrame({"Close": [1.0, 1, 1, 1], "climax": [False, False, True, False]}, index=idx)
    bear = pd.Series([False, True, False], index=pd.to_datetime(["2020-01-03", "2020-01-07", "2020-01-08"]))
    out = R.climax_frames({"1234.T": df}, bear)["1234.T"]
    assert out["climax"].tolist() == [False, True, True, False] and df["climax"].tolist() == [False, False, True, False]


def test_shift_keeps_state_days():
    idx = pd.bdate_range("1999-06-01", "2026-10-30")
    s = pd.Series((np.arange(len(idx)) % 500) < 90, index=idx)
    a = R.shifted(s, 11)
    assert a.equals(R.shifted(s, 11)) and int(a.sum()) == int(R.shift_domain(s).sum())
