"""第六个研究循环第二段第 5 轮 TB7（scripts/loop6_r05_dualspeed.py，2026-10-03 登记）：登记值与第二段的规则（家族第 2 个）、T7 = 时点研究登记的
双速离场（T7 的熊包含 T0 的熊）、与第 4 轮同一套警戒区 / 第二关代码、接法 / 命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop6_r03_earlyreturn as N3  # noqa: E402
import loop6_r04_fastexit as Z4  # noqa: E402
import loop6_r05_dualspeed as T  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_loop6_segment2_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC) == (5, ("TB7",), True)
    assert T.KIND == {"TB7": "signal"} and T.FAMILY == {"TB7": "核心·择时（早离场）"}
    assert T.over is N3.over and T.zone is Z4.zone and T.shifted_zone is Z4.shifted_zone and T.ref_zone is Z4.ref_zone
    st = R6.load_state(ROOT / "var")
    if not R6.segment(st):
        pytest.skip("第二段还没有登记")
    assert not set(T.IDS) & (R6.previous_ids(ROOT / "var") | R6.earlier_ids(st))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R6.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND[k]} for k in T.IDS],
                                R6.previous_ids(ROOT / "var"))


def test_t7_is_registered_dual_speed_and_contains_t0():
    from qbreak.bullbear import BEAR
    from qbreak.timing import FAST_DD, FAST_K, L, s7_dual_speed
    assert (L, FAST_DD, FAST_K) == (250, 0.10, 2)
    rng = np.random.default_rng(11)
    d = pd.bdate_range("2000-01-03", periods=2500)
    c = pd.Series(100 * np.cumprod(1 + rng.normal(0.0002, 0.013, 2500)), index=d)
    b7 = T.t7_bear(c)
    assert b7.tolist() == (np.asarray(s7_dual_speed(c)) == BEAR).tolist()
    b0 = T.t0_bear(c)
    assert not (b0 & ~b7).any()                                                                # T7 的熊包含 T0 的熊
    assert T.t7_bear(c.iloc[:1800]).equals(b7.iloc[:1800])                                     # 不看未来


def test_sources_and_cli():
    i = inspect.getsource(T.inputs)
    assert 'fast_us = t7_bear(W["inp"]["spx"]["Close"])' in i and 'M["zone"] = zone(M["slow_t"], M["fast_t"])' in i
    s1 = inspect.getsource(T.stage_one)
    assert "L6.load()" in s1 and 'R6.stage1(cand["TB7"], base, posthoc=unseen)' in s1 and 'N3.old_core(W, M["uni"], old_bear(W, M))' in s1
    w = inspect.getsource(T.wiring)
    assert "no_zone_same_as_b2" in w and "t7_contains_t0" in w and "t0_equals_b2_slow" in w and "old_core_b2_same" in w
    s2 = inspect.getsource(T.stage_two)
    assert "placebo_ks(n)" in s2 and "R6.stage2(stat, vals)" in s2 and 'R6.shift_window(M["zone"])' in s2
    assert 'core_bear(M["slow_t"], shifted_zone(M["zone"], ks[int(seed)]))' in inspect.getsource(T._placebo_one)
    r = inspect.getsource(T.stage_two_ref)
    assert '"describe_only": True' in r and "ref_ks(n)" in r and "R6.verdict" not in r
    with pytest.raises(SystemExit):
        T.main(["--nope"])
