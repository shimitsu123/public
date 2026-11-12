"""第二个研究循环第 6 轮 VXB（scripts/loop2_r06_vixbrake.py，2026-10-02 登记）：登记值、开 / 关的滞后带、接到 B1 的两个核心键。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r06_vixbrake as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC) == (6, ("VXB",), "风险层·恐慌指数刹车", True)
    assert (T.ON, T.OFF, T.MULT, T.VIX_START, T.OLD) == (30.0, 25.0, 0.5, "1990-01-01", ("1987-01-01", "2000-12-31"))


def test_brake_state_hysteresis():
    idx = pd.bdate_range("2020-01-01", periods=9)
    vix = pd.Series([20, 29.9, 30, 27, 25, 24.9, 26, 31, 12], index=idx, dtype=float)
    assert T.brake_state(vix).tolist() == [False, False, True, True, True, False, False, True, False]   # ≥ 30 开、< 25 关、之间保持
    assert T.multiplier(T.brake_state(vix)).tolist() == [1, 1, 0.5, 0.5, 0.5, 1, 1, 0.5, 1]


def test_wiring_to_b1_core_keys():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=3)
    o = T.vxb_over(pd.Series([False, True, False], index=idx))
    assert set(o) == {"extra_expo"} and set(o["extra_expo"]) == {Y.UH_KEY, Y.HG_KEY}
    assert o["extra_expo"][Y.UH_KEY].tolist() == [1.0, 0.5, 1.0] and o["extra_expo"][Y.HG_KEY].tolist() == [1.0, 0.5, 1.0]
    never = T.vxb_over(pd.Series(False, index=idx))
    assert all(v.eq(1.0).all() for v in never["extra_expo"].values())                       # 永远不开 = B1


def test_cli_takes_no_options():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "VXB"])
