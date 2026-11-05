"""第六个研究循环第三段第 8 轮 VBT（scripts/loop6_r08_voltrend.py，2026-10-03 登记）：登记值与第三段的规则、正在跌 = 收在 50 日均线下、
信号 = 高波动 ∧ 正在跌、信号永远不成立 → 与 B3 相同的键、接法 = 第 7 轮 vbh_over、第二关只平移信号（窗外不动）、只有核心用第 7 轮的 old_core。"""
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
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_segment3_rules():
    assert (X.ROUND, X.IDS, X.POSTHOC, X.KIND, X.FAMILY) == (8, ("VBT",), True, {"VBT": "signal"}, {"VBT": "核心·波动率仓位"})
    assert (X.TREND_N, V.W_CORE, V.W_BOND) == (50, 2.0, 1.0)
    st = R6.load_state(ROOT / "var")
    if int((R6.segment(st) or {}).get("seg", 2)) < 3:
        pytest.skip("第三段还没有登记")
    assert not set(X.IDS) & (R6.previous_ids(ROOT / "var") | R6.ids_before(st, X.ROUND))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == X.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(X.IDS)
    else:
        R6.check_new_approaches(st, [{"id": k, "family": X.FAMILY[k], "posthoc": X.POSTHOC, "kind": X.KIND[k]} for k in X.IDS],
                                R6.previous_ids(ROOT / "var"))


def test_trend_down_is_close_below_own_sma():
    idx = pd.bdate_range("2024-01-01", periods=6)
    s = pd.Series([10.0, 11.0, 12.0, 9.0, 13.0, 8.0], index=idx)
    out = X.trend_down(s, n=3)
    # 均线（3 日）：— / — / 11 / 10.67 / 11.33 / 10 → 只有 9 < 10.67、8 < 10 是「正在跌」；不够 3 个值的日子 = False
    assert out.tolist() == [False, False, False, True, False, True]
    assert X.trend_down(s.iloc[::-1].sort_index(), n=3).equals(out)


def test_signal_is_high_vol_and_down_on_common_dates():
    idx = pd.bdate_range("2024-01-01", periods=5)
    ratio = pd.Series([1.0, 0.8, 0.8, 0.7, 1.0], index=idx)
    down = pd.Series([True, True, False, True, True], index=idx)
    assert X.signal(ratio, down).tolist() == [False, True, False, True, False]
    short = X.signal(ratio, down.iloc[1:])
    assert list(short.index) == list(idx[1:])


def test_never_signal_keeps_b3_bond_key_and_wiring_is_round7():
    idx = pd.bdate_range("2024-01-01", periods=4)
    bear = pd.Series([False, False, True, True], index=idx)
    on = pd.Series([True, False, True, False], index=idx)
    never = V.bond_closed(bear, pd.Series(False, index=idx), on)
    assert never.tolist() == (~on | ~bear).tolist()
    W = {"kw": {"Z": {"extra_core": {"1545.T": "F1545"}}}}
    M = {"fb": "F1482", "bear_t": bear, "on_b": on}
    sig = pd.Series([True, False, False, False], index=idx)
    a, b = X.vbt_over(W, M, sig), V.vbh_over(W, M, sig)
    assert a["cfg_over"] == b["cfg_over"] and a["extra_core"] == b["extra_core"]
    assert a["extra_bear"][T2.BD_KEY].equals(b["extra_bear"][T2.BD_KEY])
    assert a["extra_bear"][T2.BD_KEY].tolist() == [False, True, False, True]          # 牛 ∧ 信号 ∧ 负相关 → 1482 可拿；熊 ∧ 负相关 → 可拿


def test_shifted_signal_only_inside_window_and_old_core_delegates():
    idx = pd.bdate_range("1999-12-20", "2026-10-02")
    s = pd.Series(np.arange(len(idx)) % 11 == 0, index=idx)
    out = X.shifted_signal(s, 500)
    w = R6.shift_window(s)
    assert out[~out.index.isin(w.index)].equals(s[~s.index.isin(w.index)])
    assert out.loc[w.index].tolist() == np.roll(w.to_numpy(bool), 500).tolist()
    assert X.shifted_signal(s, None).equals(s) and X.placebo_ks(len(w)) == R6.shift_ks(len(w), 0)
    assert "V.old_core(W, sig_us)" in inspect.getsource(X.old_core)
    assert "V.vbh_over(W, M, sig_t)" in inspect.getsource(X.vbt_over)


def test_cli_and_wiring_checks_present():
    src = inspect.getsource(X.wiring)
    assert "never_same_as_b3" in src and "high_only_same_as_vbh" in src and "old_core_same" in src and X.REF7 == "loop6_r07_volbond.json"
    assert X.main.__code__.co_varnames[:1] == ("argv",)
    for flag in ("--scale", "--wiring", "--stage2", "--workers"):
        assert flag in inspect.getsource(X.main)
