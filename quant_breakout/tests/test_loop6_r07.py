"""第六个研究循环第三段第 7 轮 VBH（scripts/loop6_r07_volbond.py，2026-10-03 登记）：登记值与第三段的规则、高波动 = VT20 的比例 < 1、
1482 的键（高波动永远不成立 → 与 B3 相同）、2 : 1 的权重、只有核心的持仓、第二关只平移高波动（窗外不动）、接法 / 命令行。"""
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
import loop_r01_voltarget as VT  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_segment3_rules():
    assert (V.ROUND, V.IDS, V.POSTHOC, V.KIND, V.FAMILY) == (7, ("VBH",), True, {"VBH": "signal"}, {"VBH": "核心·波动率仓位"})
    assert (V.W_CORE, V.W_BOND) == (2.0, 1.0) and (VT.WIN_N, VT.BAND) == (20, 0.10)
    st = R6.load_state(ROOT / "var")
    if int((R6.segment(st) or {}).get("seg", 2)) < 3:
        pytest.skip("第三段还没有登记")
    assert not set(V.IDS) & (R6.previous_ids(ROOT / "var") | R6.earlier_ids(st))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == V.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(V.IDS)
    else:
        R6.check_new_approaches(st, [{"id": k, "family": V.FAMILY[k], "posthoc": V.POSTHOC, "kind": V.KIND[k]} for k in V.IDS],
                                R6.previous_ids(ROOT / "var"))


def test_high_vol_is_vt20_ratio_below_one():
    r = pd.Series([1.0, 0.85, 0.85, 1.0, 0.7], index=pd.bdate_range("2024-01-01", periods=5))
    assert V.high_vol(r).tolist() == [False, True, True, False, True]
    src = inspect.getsource(V.vt_ratio)
    assert "VT.sigma(" in src and "VT.exposure(sg, VT.target(sg))" in src


def test_bond_key_truth_table_and_never_high_equals_b3():
    idx = pd.bdate_range("2024-01-01", periods=8)
    bear = pd.Series([False, False, False, False, True, True, True, True], index=idx)
    high = pd.Series([False, True, False, True, False, True, False, True], index=idx)
    on = pd.Series([False, False, True, True, False, False, True, True], index=idx)
    k = V.bond_closed(bear, high, on)
    assert k.tolist() == [True, True, True, False, True, True, False, False]       # 只有「牛 ∧ 高波动 ∧ 负相关」与「熊 ∧ 负相关」开着
    never = V.bond_closed(bear, pd.Series(False, index=idx), on)
    assert never.tolist() == (~on | ~bear).tolist()                                  # = B3 的键（¬负相关 ∨ 美股牛）


def test_core_weights_and_old_core_b3_case():
    idx = pd.bdate_range("2024-01-01", periods=4)
    b = pd.Series([False, False, True, True], index=idx)
    h = pd.Series([True, True, True, False], index=idx)
    o = pd.Series([True, False, True, False], index=idx)
    w = V.core_weights(b, h, o)
    assert np.allclose(w["u"], [2 / 3, 1.0, 0.0, 0.0]) and np.allclose(w["b"], [1 / 3, 0.0, 1.0, 0.0])
    w0 = V.core_weights(b, pd.Series(False, index=idx), o)
    assert w0["u"].tolist() == (~b).astype(float).tolist() and w0["b"].tolist() == (b & o).astype(float).tolist()
    assert "high_us is not None else pd.Series(False" in inspect.getsource(V.old_core)


def test_shifted_high_only_inside_window():
    idx = pd.bdate_range("1999-12-20", "2026-10-02")
    s = pd.Series(np.arange(len(idx)) % 7 == 0, index=idx)
    out = V.shifted_high(s, 300)
    w = R6.shift_window(s)
    assert out[~out.index.isin(w.index)].equals(s[~s.index.isin(w.index)])
    assert out.loc[w.index].tolist() == np.roll(w.to_numpy(bool), 300).tolist()
    assert V.shifted_high(s, None).equals(s) and V.placebo_ks(len(w)) == R6.shift_ks(len(w), 0)


def test_over_wiring_matches_b3_structure():
    idx = pd.bdate_range("2024-01-01", periods=3)
    W = {"kw": {"Z": {"extra_core": {"1545.T": "F1545"}}}}
    M = {"fb": "F1482", "bear_t": pd.Series(False, index=idx), "on_b": pd.Series(True, index=idx)}
    ov = V.vbh_over(W, M, pd.Series([False, True, False], index=idx))
    assert ov["cfg_over"] == {"core": {"1545.T": 2.0, T2.BOND_T: 1.0}, "core_index": {"1545.T": "US", T2.BOND_T: T2.BD_KEY}, "core_mode": "follow"}
    assert ov["extra_core"] == {"1545.T": "F1545", T2.BOND_T: "F1482"} and W["kw"]["Z"]["extra_core"] == {"1545.T": "F1545"}
    assert ov["extra_bear"][T2.BD_KEY].tolist() == [True, False, True]
    assert V.main.__code__.co_varnames[:1] == ("argv",) and "--wiring" in inspect.getsource(V.main)
