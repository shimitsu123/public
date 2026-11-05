"""第二个研究循环第 12 轮 NSX（scripts/loop2_r12_ndxtospx.py，2026-10-02 登记）：登记值、换指数的状态、四只核心的熊、接法、费用表。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r12_ndxtospx as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.OLD) == (12, ("NSX",), "核心·指数选择", True, ("1987-01-01", "2000-12-31"))
    assert (T.SPX_T, T.SPH_T, T.SU_FEE, T.SH_FEE, T.SH_BASIS, T.REF_DATE, T.SH_REF) == (
        "1655.T", "2563.T", 0.066, 0.077, 0.16, "2026-08-31", 406.3)


def test_switch_state_is_ndx_bear_while_spx_bull():
    idx = pd.bdate_range("2020-01-01", periods=6)
    spx = pd.Series([False, False, True, True, False, False], index=idx)
    ndx = pd.Series([False, True, True, False, True, True], index=idx[:6])
    sw = T.switch_state(spx, ndx)
    assert sw.tolist() == [False, True, False, False, True, True]


def test_keys_leave_exactly_one_core_unless_us_bear():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=8)
    bear = pd.Series([False, False, False, False, True, True, False, False], index=idx)
    uni = pd.Series([False, True, False, True, False, True, False, True], index=idx)
    sw = pd.Series([False, False, True, True, True, False, False, False], index=idx)
    k = T.nsx_keys(bear, uni, sw)
    M = np.column_stack([k[Y.UH_KEY].to_numpy(), k[Y.HG_KEY].to_numpy(), k[T.SU_KEY].to_numpy(), k[T.SH_KEY].to_numpy()])
    held = (~M).sum(axis=1)
    assert held.tolist() == [1, 1, 1, 1, 0, 0, 1, 1]                       # 美股熊 → 四只都熊（现金）；否则只有一只
    assert [int(np.flatnonzero(~r)[0]) for r in M[[0, 1, 2, 3, 6, 7]]] == [0, 1, 2, 3, 0, 1]   # 1545 / 2845 / 1655 / 2563
    # S 永远不成立 → 1545 / 2845 与 B1（fxh_over 的 or_series）完全相同、1655 / 2563 永远是熊
    k0 = T.nsx_keys(bear, uni, pd.Series(False, index=idx))
    assert k0[Y.UH_KEY].tolist() == Y.or_series(bear, uni).tolist()
    assert k0[Y.HG_KEY].tolist() == Y.or_series(bear, ~uni.astype(bool)).tolist()
    assert k0[T.SU_KEY].all() and k0[T.SH_KEY].all()


def test_keys_cover_dates_before_switch_series_starts():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=6)
    bear = pd.Series(False, index=idx)
    uni = pd.Series(False, index=idx)
    sw = pd.Series([True, False], index=idx[3:5])                            # 开始得晚：之前当作不换
    k = T.nsx_keys(bear, uni, sw)
    assert k[Y.UH_KEY].tolist() == [False, False, False, True, False, False]
    assert k[T.SU_KEY].tolist() == [True, True, True, False, True, True]


def test_wiring_adds_two_spx_cores_in_follow_mode():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=4)
    fr = pd.DataFrame({"Close": [1.0, 1.0, 1.0, 1.0]}, index=idx)
    W = {"b1": {"extra_core": {"1545.T": fr, Y.HEDGE_T: fr}}, "assets": {T.SPX_T: fr}, "bear": {"US": pd.Series(False, index=idx)}}
    o = T.nsx_over(W, pd.Series(False, index=idx), pd.Series(False, index=idx), fr)
    assert o["cfg_over"]["core_mode"] == "follow"
    assert o["cfg_over"]["core_index"] == {"1545.T": Y.UH_KEY, Y.HEDGE_T: Y.HG_KEY, T.SPX_T: T.SU_KEY, T.SPH_T: T.SH_KEY}
    assert set(o["extra_core"]) == {"1545.T", Y.HEDGE_T, T.SPX_T, T.SPH_T}
    assert set(o["extra_bear"]) == {Y.UH_KEY, Y.HG_KEY, T.SU_KEY, T.SH_KEY}


def test_fee_table_has_2563_for_research():
    from qbreak import fees
    c = fees.etf_cost("tachibana", "2563.T", "JP")
    assert (c["slip_pct"], c["lot"]) == (0.05, 10)


def test_cli_takes_no_options():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "NSX"])
