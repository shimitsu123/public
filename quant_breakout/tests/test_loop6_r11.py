"""第六个研究循环第三段第 11 轮 CSV（scripts/loop6_r11_creditcut.py，2026-10-03 登记）：登记值与第三段的规则、信用利差信号（晚一天、20 天变化、
≥ 0.20 开 / < 0.10 关）、接法 = 第 9 轮 vct_over、只有核心 = 第 9 轮 old_core、第二关只平移信号、接线核对的三项。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop6_r08_voltrend as X  # noqa: E402
import loop6_r09_volcash as C  # noqa: E402
import loop6_r11_creditcut as S  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_segment3_rules():
    assert (S.ROUND, S.IDS, S.POSTHOC, S.KIND, S.FAMILY) == (11, ("CSV",), True, {"CSV": "signal"}, {"CSV": "核心·信用利差"})
    assert (S.SERIES, S.WIN, S.ON, S.OFF) == ("BAA10Y", 20, 0.20, 0.10)
    st = R6.load_state(ROOT / "var")
    if int((R6.segment(st) or {}).get("seg", 2)) < 3:
        pytest.skip("第三段还没有登记")
    assert not set(S.IDS) & (R6.previous_ids(ROOT / "var") | R6.ids_before(st, S.ROUND))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == S.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(S.IDS)
    else:
        R6.check_new_approaches(st, [{"id": k, "family": S.FAMILY[k], "posthoc": S.POSTHOC, "kind": S.KIND[k]} for k in S.IDS],
                                R6.previous_ids(ROOT / "var"))


def test_widening_lag_change_and_hysteresis():
    idx = pd.bdate_range("2024-01-01", periods=8)
    sp = pd.Series([2.0, 2.0, 2.1, 2.3, 2.3, 2.2, 2.05, 2.0], index=idx)
    out = S.widening(sp, win=2, on=0.20, off=0.10)
    # 先晚一天：[—, 2.0, 2.0, 2.1, 2.3, 2.3, 2.2, 2.05]；2 天变化：[—, —, —, 0.1, 0.3, 0.2, −0.1, −0.25]
    assert out.tolist() == [False, False, False, False, True, True, False, False]
    sp2 = pd.Series([2.0, 2.0, 2.0, 2.25, 2.4, 2.4, 2.4, 2.4], index=idx)
    # 晚一天：[—, 2.0, 2.0, 2.0, 2.25, 2.4, 2.4, 2.4]；变化：[—, —, —, 0.0, 0.25, 0.4, 0.15, 0.0] → 第 5 天开，0.15 仍 ≥ 0.10 保持，0.0 关
    assert S.widening(sp2, win=2).tolist() == [False, False, False, False, True, True, True, False]


def test_reuses_vct_machinery():
    assert "C.vct_over(W, M, sig_t)" in inspect.getsource(S.csv_over)
    assert "C.old_core(W, sig_us)" in inspect.getsource(S.old_core)
    idx = pd.bdate_range("1999-12-20", "2026-10-02")
    s = pd.Series(np.arange(len(idx)) % 17 == 0, index=idx)
    assert S.shifted_signal(s, 555).equals(X.shifted_signal(s, 555)) and S.placebo_ks(6549) == R6.shift_ks(6549, 0)
    assert "csv_over(W, M, shifted_signal(M[\"csv_t\"], ks[int(seed)]))" in inspect.getsource(S._placebo_one)


def test_cli_and_wiring_checks_present():
    src = inspect.getsource(S.wiring)
    for k in ("never_same_as_b3", "vct_signal_same_as_vct", "old_core_b3_same"):
        assert k in src, k
    assert S.REF9 == "loop6_r09_volcash.json" and C.OUT == "loop6_r09_volcash"
    for flag in ("--scale", "--wiring", "--stage2", "--workers"):
        assert flag in inspect.getsource(S.main)
