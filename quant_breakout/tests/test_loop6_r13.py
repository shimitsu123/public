"""第六个研究循环第三段第 13 轮 RSC（scripts/loop6_r13_rateshock.py，2026-10-03 登记）：登记值与第三段的规则、利率急升信号（第 11 轮同一个函数、
0.40 / 0.20 pp）、1545 的 core_expo（牛 ∧ 信号 → 2/3、不管股债相关）、只有核心的持仓、第二关只平移信号、接线核对的三项。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop6_r08_voltrend as X  # noqa: E402
import loop6_r11_creditcut as S  # noqa: E402
import loop6_r13_rateshock as Q  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_segment3_rules():
    assert (Q.ROUND, Q.IDS, Q.POSTHOC, Q.KIND, Q.FAMILY) == (13, ("RSC",), True, {"RSC": "signal"}, {"RSC": "核心·利率冲击"})
    assert (Q.SERIES, Q.WIN, Q.ON, Q.OFF) == ("DGS10", 20, 0.40, 0.20) and Q.KEEP == pytest.approx(2 / 3)
    st = R6.load_state(ROOT / "var")
    if int((R6.segment(st) or {}).get("seg", 2)) < 3:
        pytest.skip("第三段还没有登记")
    assert not set(Q.IDS) & (R6.previous_ids(ROOT / "var") | R6.ids_before(st, Q.ROUND))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == Q.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(Q.IDS)
    else:
        R6.check_new_approaches(st, [{"id": k, "family": Q.FAMILY[k], "posthoc": Q.POSTHOC, "kind": Q.KIND[k]} for k in Q.IDS],
                                R6.previous_ids(ROOT / "var"))


def test_shock_is_widening_with_rate_thresholds():
    idx = pd.bdate_range("2024-01-01", periods=8)
    y = pd.Series([4.0, 4.0, 4.0, 4.45, 4.6, 4.6, 4.55, 4.4], index=idx)
    assert Q.shock(y).equals(S.widening(y, win=20, on=0.40, off=0.20))
    assert "S.widening(yields, win=WIN, on=ON, off=OFF)" in inspect.getsource(Q.shock)


def test_expo_and_over():
    idx = pd.bdate_range("2024-01-01", periods=5)
    bear = pd.Series([False, False, True, True, False], index=idx)
    sig = pd.Series([True, False, True, False, True], index=idx)
    assert np.allclose(Q.expo_us(bear, sig, idx).to_numpy(), [2 / 3, 1, 1, 1, 2 / 3])
    M = {"bear_t": bear, "on_b": pd.Series(True, index=idx)}
    ov = Q.rsc_over({}, M, sig)
    assert list(ov) == ["core_expo"] and list(ov["core_expo"]) == ["US"]
    assert (Q.rsc_over({}, M, pd.Series(False, index=idx))["core_expo"]["US"] == 1.0).all()


def test_core_weights_old_period():
    idx = pd.bdate_range("2024-01-01", periods=5)
    bear = pd.Series([False, False, True, True, False], index=idx)
    sig = pd.Series([True, False, True, False, True], index=idx)
    on = pd.Series([True, True, True, False, False], index=idx)
    w = Q.core_weights(bear, sig, on)
    assert np.allclose(w["u"], [2 / 3, 1, 0, 0, 2 / 3]) and np.allclose(w["b"], [0, 0, 1, 0, 0])   # 牛 ∧ 信号：不管相关都留现金
    src = inspect.getsource(Q.old_core)
    assert "T.corr_on(ffull(spx), ffull(bnd)).shift(1, fill_value=False)" in src and "core_weights(b, s, ou).shift(1)" in src


def test_shift_and_cli():
    idx = pd.bdate_range("1999-12-20", "2026-10-02")
    s = pd.Series(np.arange(len(idx)) % 23 == 0, index=idx)
    assert Q.shifted_signal(s, 666).equals(X.shifted_signal(s, 666)) and Q.placebo_ks(6549) == R6.shift_ks(6549, 0)
    src = inspect.getsource(Q.wiring)
    for k in ("no_other_core_expo", "never_same_as_b3", "old_core_b3_same"):
        assert k in src, k
    assert "rsc_over(W, M, shifted_signal(M[\"rs_t\"], ks[int(seed)]))" in inspect.getsource(Q._placebo_one)
    for flag in ("--scale", "--wiring", "--stage2", "--workers"):
        assert flag in inspect.getsource(Q.main)
