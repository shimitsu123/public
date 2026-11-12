"""第六个研究循环第三段第 9 轮 VCT（scripts/loop6_r09_volcash.py，2026-10-03 登记）：登记值与第三段的规则、留现金的日子 = 牛 ∧ 信号 ∧ 不是负相关、
1545 的 core_expo（2/3）、接法 = 第 8 轮 VBT + core_expo、只有核心的持仓、第二关只平移信号、接线核对的四项。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop2_r02_bondrefuge as T2  # noqa: E402
import loop6_r07_volbond as V  # noqa: E402
import loop6_r08_voltrend as X  # noqa: E402
import loop6_r09_volcash as C  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_segment3_rules():
    assert (C.ROUND, C.IDS, C.POSTHOC, C.KIND, C.FAMILY) == (9, ("VCT",), True, {"VCT": "signal"}, {"VCT": "核心·波动率仓位"})
    assert C.KEEP == pytest.approx(2 / 3) and (V.W_CORE, V.W_BOND, X.TREND_N) == (2.0, 1.0, 50)
    st = R6.load_state(ROOT / "var")
    if int((R6.segment(st) or {}).get("seg", 2)) < 3:
        pytest.skip("第三段还没有登记")
    assert not set(C.IDS) & (R6.previous_ids(ROOT / "var") | R6.ids_before(st, C.ROUND))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == C.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(C.IDS)
    else:
        R6.check_new_approaches(st, [{"id": k, "family": C.FAMILY[k], "posthoc": C.POSTHOC, "kind": C.KIND[k]} for k in C.IDS],
                                R6.previous_ids(ROOT / "var"))


def _states():
    idx = pd.bdate_range("2024-01-01", periods=6)
    bear = pd.Series([False, False, False, True, True, False], index=idx)
    sig = pd.Series([True, True, False, True, False, True], index=idx)
    on = pd.Series([True, False, False, True, False, False], index=idx)
    return idx, bear, sig, on


def test_cash_days_and_expo():
    idx, bear, sig, on = _states()
    assert C.cash_days(bear, sig, on).tolist() == [False, True, False, False, False, True]      # 牛 ∧ 信号 ∧ 不是负相关
    ex = C.expo_us(bear, sig, on)
    assert np.allclose(ex.to_numpy(), [1.0, 2 / 3, 1.0, 1.0, 1.0, 2 / 3])
    assert (C.expo_us(bear, sig, on, enabled=False) == 1.0).all()
    assert (C.expo_us(bear, pd.Series(False, index=idx), on) == 1.0).all()                      # 信号永远不成立 → 全 1


def test_over_is_vbt_plus_core_expo():
    idx, bear, sig, on = _states()
    W = {"kw": {"Z": {"extra_core": {"1545.T": "F1545"}}}}
    M = {"fb": "F1482", "bear_t": bear, "on_b": on}
    a, b = C.vct_over(W, M, sig), X.vbt_over(W, M, sig)
    assert a["cfg_over"] == b["cfg_over"] and a["extra_core"] == b["extra_core"]
    assert a["extra_bear"][T2.BD_KEY].equals(b["extra_bear"][T2.BD_KEY])
    assert set(a) == set(b) | {"core_expo"} and list(a["core_expo"]) == ["US"]
    assert a["cfg_over"]["core_index"]["1545.T"] == "US"
    assert np.allclose(C.vct_over(W, M, sig, cash=False)["core_expo"]["US"].to_numpy(), 1.0)


def test_core_weights_old_period():
    idx, bear, sig, on = _states()
    w = C.core_weights(bear, sig, on)
    assert np.allclose(w["u"], [2 / 3, 2 / 3, 1.0, 0.0, 0.0, 2 / 3])
    assert np.allclose(w["b"], [1 / 3, 0.0, 0.0, 1.0, 0.0, 0.0])
    w0 = C.core_weights(bear, sig, on, cash=False)
    v0 = V.core_weights(bear, sig, on)
    assert np.allclose(w0["u"], v0["u"]) and np.allclose(w0["b"], v0["b"])
    src = inspect.getsource(C.old_core)
    for s in ("T.corr_on(ffull(spx), ffull(bnd)).shift(1, fill_value=False)", "core_weights(b, s, ou, cash=cash).shift(1)", "HW.SWITCH_COST / 100"):
        assert s in src, s
    assert inspect.getsource(V.old_core).count("T.corr_on(ffull(spx), ffull(bnd)).shift(1, fill_value=False)") == 1


def test_shift_and_cli():
    idx = pd.bdate_range("1999-12-20", "2026-10-02")
    s = pd.Series(np.arange(len(idx)) % 13 == 0, index=idx)
    assert C.shifted_signal(s, 777).equals(X.shifted_signal(s, 777)) and C.placebo_ks(6549) == R6.shift_ks(6549, 0)
    src = inspect.getsource(C.wiring)
    for k in ("no_other_core_expo", "never_same_as_b3", "no_cash_same_as_vbt", "old_core_b3_same", "old_core_no_cash_same_as_vbt"):
        assert k in src, k
    assert C.REF8 == "loop6_r08_voltrend.json"
    assert "vct_over(W, M, shifted_signal(M[\"sig_t\"], ks[int(seed)]))" in inspect.getsource(C._placebo_one)
    for flag in ("--scale", "--wiring", "--stage2", "--workers"):
        assert flag in inspect.getsource(C.main)
