"""第六个研究循环第三段第 12 轮 VPS（scripts/loop6_r12_crashspx.py，2026-10-03 登记）：登记值与第三段的规则、换 S&P500 的日子 = 牛 ∧ 信号 ∧ 不是负相关、
三个键任何一天最多一只可拿、1482 的键 = B3 原样、只有核心的持仓、第二关只平移信号、接线核对的三项。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop2_r02_bondrefuge as T2  # noqa: E402
import loop6_r08_voltrend as X  # noqa: E402
import loop6_r12_crashspx as P  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_segment3_rules():
    assert (P.ROUND, P.IDS, P.POSTHOC, P.KIND, P.FAMILY) == (12, ("VPS",), True, {"VPS": "signal"}, {"VPS": "核心·指数选择"})
    assert (P.SPX_T, P.NQ_KEY, P.SP_KEY) == ("1655.T", "US_VN", "US_VS")
    st = R6.load_state(ROOT / "var")
    if int((R6.segment(st) or {}).get("seg", 2)) < 3:
        pytest.skip("第三段还没有登记")
    assert not set(P.IDS) & (R6.previous_ids(ROOT / "var") | R6.ids_before(st, P.ROUND))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == P.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(P.IDS)
    else:
        R6.check_new_approaches(st, [{"id": k, "family": P.FAMILY[k], "posthoc": P.POSTHOC, "kind": P.KIND[k]} for k in P.IDS],
                                R6.previous_ids(ROOT / "var"))


def _states():
    idx = pd.bdate_range("2024-01-01", periods=6)
    bear = pd.Series([False, False, False, True, True, False], index=idx)
    sig = pd.Series([True, True, False, True, False, True], index=idx)
    on = pd.Series([True, False, False, True, False, False], index=idx)
    return idx, bear, sig, on


def test_swap_days_and_keys_at_most_one_open():
    idx, bear, sig, on = _states()
    assert P.swap_days(bear, sig, on).tolist() == [False, True, False, False, False, True]
    W = {"kw": {"Z": {"extra_core": {"1545.T": "F1545"}}}, "assets": {"1655.T": "F1655"}}
    M = {"fb": "F1482", "bear_t": bear, "on_b": on}
    ov = P.vps_over(W, M, sig)
    assert ov["cfg_over"]["core_index"] == {"1545.T": "US_VN", "1655.T": "US_VS", T2.BOND_T: T2.BD_KEY} and ov["cfg_over"]["core_mode"] == "follow"
    assert ov["extra_core"] == {"1545.T": "F1545", T2.BOND_T: "F1482", "1655.T": "F1655"} and W["kw"]["Z"]["extra_core"] == {"1545.T": "F1545"}
    eb = ov["extra_bear"]
    open_ = (~eb["US_VN"]).astype(int) + (~eb["US_VS"]).astype(int) + (~eb[T2.BD_KEY]).astype(int)
    assert open_.max() <= 1                                                                      # 任何一天最多一只可拿
    assert (~eb["US_VS"]).tolist() == [False, True, False, False, False, True]
    assert (~eb["US_VN"]).tolist() == [True, False, True, False, False, False]
    assert eb[T2.BD_KEY].tolist() == (~(bear & on)).tolist()                                    # 1482 的键 = B3 原样
    never = P.vps_over(W, M, pd.Series(False, index=idx))["extra_bear"]
    assert never["US_VN"].tolist() == bear.tolist() and never["US_VS"].all()                    # 信号永远不成立 → 1545 键 = 美股熊、1655 永远不拿


def test_core_weights_old_period():
    idx, bear, sig, on = _states()
    w = P.core_weights(bear, sig, on)
    assert w["u"].tolist() == [1, 0, 1, 0, 0, 0] and w["sp"].tolist() == [0, 1, 0, 0, 0, 1] and w["b"].tolist() == [0, 0, 0, 1, 0, 0]
    assert (w.sum(axis=1) <= 1).all()
    src = inspect.getsource(P.old_core)
    assert "T.corr_on(ffull(spx), ffull(bnd)).shift(1, fill_value=False)" in src and "EI.FEE[SPX_T]" in src


def test_shift_and_cli():
    idx = pd.bdate_range("1999-12-20", "2026-10-02")
    s = pd.Series(np.arange(len(idx)) % 19 == 0, index=idx)
    assert P.shifted_signal(s, 444).equals(X.shifted_signal(s, 444)) and P.placebo_ks(6549) == R6.shift_ks(6549, 0)
    src = inspect.getsource(P.wiring)
    for k in ("never_same_as_b3", "spx_frame_same", "old_core_b3_same"):
        assert k in src, k
    assert "vps_over(W, M, shifted_signal(M[\"sig_t\"], ks[int(seed)]))" in inspect.getsource(P._placebo_one)
    for flag in ("--scale", "--wiring", "--stage2", "--workers"):
        assert flag in inspect.getsource(P.main)
