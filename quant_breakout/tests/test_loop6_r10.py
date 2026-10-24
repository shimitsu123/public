"""第六个研究循环第三段第 10 轮 BPR（scripts/loop6_r10_bearpartial.py，2026-10-03 登记）：登记值与第三段的规则、1545 的键 = 美股熊 ∧ 信号、
1/3 的比例只在「熊 ∧ 不是信号 ∧ 不是负相关」、1 : 2 的权重、1482 的键 = B3 原样、只有核心的持仓、第二关只平移信号、接线核对的三项。"""
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
import loop6_r10_bearpartial as P  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_segment3_rules():
    assert (P.ROUND, P.IDS, P.POSTHOC, P.KIND, P.FAMILY) == (10, ("BPR",), True, {"BPR": "signal"}, {"BPR": "核心·择时（早回来）"})
    assert P.PART == pytest.approx(1 / 3) and (P.W_EQ, P.W_BD) == (1.0, 2.0) and P.PR_KEY == "US_PR"
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
    bear = pd.Series([False, False, True, True, True, True], index=idx)
    sig = pd.Series([True, False, True, True, False, False], index=idx)
    on = pd.Series([True, False, True, False, True, False], index=idx)
    return idx, bear, sig, on


def test_equity_key_and_expo():
    idx, bear, sig, on = _states()
    assert P.eq_closed(bear, sig, idx).tolist() == [False, False, True, True, False, False]    # 只有「熊 ∧ 信号」不拿 1545
    assert P.eq_closed(bear, pd.Series(True, index=idx), idx).tolist() == bear.tolist()         # 信号永远成立 → = 美股熊（B3）
    assert np.allclose(P.eq_expo(bear, sig, on).to_numpy(), [1, 1, 1, 1, 1, 1 / 3])            # 熊 ∧ 不是信号 ∧ 不是负相关 → 1/3


def test_over_wiring():
    idx, bear, sig, on = _states()
    W = {"kw": {"Z": {"extra_core": {"1545.T": "F1545"}}}}
    M = {"fb": "F1482", "bear_t": bear, "on_b": on}
    ov = P.bpr_over(W, M, sig)
    assert ov["cfg_over"] == {"core": {"1545.T": 1.0, T2.BOND_T: 2.0}, "core_index": {"1545.T": "US_PR", T2.BOND_T: T2.BD_KEY}, "core_mode": "follow"}
    assert ov["extra_core"] == {"1545.T": "F1545", T2.BOND_T: "F1482"} and W["kw"]["Z"]["extra_core"] == {"1545.T": "F1545"}
    assert ov["extra_bear"][T2.BD_KEY].tolist() == (~(bear & on)).tolist()                     # 1482 的键 = B3 原样
    assert ov["extra_bear"]["US_PR"].tolist() == (bear & sig).tolist()
    assert list(ov["extra_expo"]) == ["US_PR"]


def test_core_weights_old_period():
    idx, bear, sig, on = _states()
    w = P.core_weights(bear, sig, on)
    assert np.allclose(w["u"], [1, 1, 0, 0, 1 / 3, 1 / 3])
    assert np.allclose(w["b"], [0, 0, 1, 0, 2 / 3, 0])
    always = P.core_weights(bear, pd.Series(True, index=idx), on)                               # 信号永远成立 → B3：牛 1、熊 ∧ 负相关 美债
    assert np.allclose(always["u"], (~bear).astype(float)) and np.allclose(always["b"], (bear & on).astype(float))
    src = inspect.getsource(P.old_core)
    assert "pd.Series(True, index=idx)" in src and "T.corr_on(ffull(spx), ffull(bnd)).shift(1, fill_value=False)" in src


def test_shift_and_cli():
    idx = pd.bdate_range("1999-12-20", "2026-10-02")
    s = pd.Series(np.arange(len(idx)) % 9 == 0, index=idx)
    assert P.shifted_signal(s, 321).equals(X.shifted_signal(s, 321)) and P.placebo_ks(6549) == R6.shift_ks(6549, 0)
    src = inspect.getsource(P.wiring)
    for k in ("no_other_expo", "always_signal_same_as_b3", "old_core_always_same_as_b3"):
        assert k in src, k
    assert "bpr_over(W, M, shifted_signal(M[\"sig_t\"], ks[int(seed)]))" in inspect.getsource(P._placebo_one)
    for flag in ("--scale", "--wiring", "--stage2", "--workers"):
        assert flag in inspect.getsource(P.main)
