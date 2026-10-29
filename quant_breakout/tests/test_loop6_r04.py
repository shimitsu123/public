"""第六个研究循环第二段第 4 轮 ZBX（scripts/loop6_r04_fastexit.py，2026-10-03 登记）：登记值与第二段的规则、快线（250 日线、b = 0、k = 1）、
警戒区与核心用的熊、只数日子的统计、第二关只平移警戒区（窗外不动）、只描述的 ZSP 形状（只落在 B2 是牛的日子、天数不变）、接法 / 命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop6_r03_earlyreturn as N3  # noqa: E402
import loop6_r04_fastexit as Z  # noqa: E402
import research_loop3 as R3  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_loop6_segment2_rules():
    assert (Z.ROUND, Z.IDS, Z.POSTHOC) == (4, ("ZBX",), True)
    assert Z.KIND == {"ZBX": "signal"} and set(Z.KIND.values()) <= set(R6.KINDS)
    assert Z.FAMILY == {"ZBX": "核心·择时（早离场）"} and Z.FAMILY["ZBX"].startswith(R6.FAMILY_PREFIX)
    assert Z.FAST == {"L": 250, "b": 0.0, "k": 1} and Z.over is N3.over and Z.on_idx is N3.on_idx
    st = R6.load_state(ROOT / "var")
    if not R6.segment(st):
        pytest.skip("第二段还没有登记")
    assert not set(Z.IDS) & (R6.previous_ids(ROOT / "var") | R6.ids_before(st, Z.ROUND))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == Z.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(Z.IDS)
    else:
        R6.check_new_approaches(st, [{"id": k, "family": Z.FAMILY[k], "posthoc": Z.POSTHOC, "kind": Z.KIND[k]} for k in Z.IDS],
                                R6.previous_ids(ROOT / "var"))


def test_fast_bear_is_close_below_250_day_line():
    rng = np.random.default_rng(3)
    d = pd.bdate_range("2010-01-01", periods=900)
    c = pd.Series(100 * np.cumprod(1 + rng.normal(0.0003, 0.012, 900)), index=d)
    fb = Z.fast_bear(c)
    ma = c.rolling(250).mean()
    m = ma.notna() & (c != ma)
    assert fb[m].tolist() == (c[m] < ma[m]).tolist()                                           # 收在线下 = 熊、线上 = 牛
    assert Z.fast_bear(c.iloc[:600]).equals(fb.iloc[:600])                                     # 后来的数据不改变以前的判断


def test_zone_and_core_bear():
    d = pd.bdate_range("2024-01-01", periods=6)
    slow = pd.Series([False, False, True, True, False, False], index=d)
    fast = pd.Series([False, True, True, False, True, False], index=d)
    z = Z.zone(slow, fast)
    assert z.tolist() == [False, True, False, False, True, False]                              # 警戒区 = 快线熊 且 分界不是熊
    assert Z.core_bear(slow, z).tolist() == (slow | fast).tolist()
    assert Z.core_bear(slow, pd.Series(False, index=d)).tolist() == slow.tolist()               # 没有警戒区 = B2


def test_zone_days_counts_days_only():
    d = pd.bdate_range("2020-02-03", periods=10)
    slow = pd.Series([False] * 6 + [True] * 4, index=d)
    z = pd.Series([False, True, True, False, True, False, False, False, False, False], index=d)
    on_b = pd.Series([True, True, False, True, False, True, True, True, True, True], index=d)
    uni = pd.Series([False, True, True, True, True, True, False, False, False, False], index=d)
    s = Z.zone_days(z, slow, on_b, uni, d)
    assert (s["zone_days"], s["bull_days"], s["bond_days"], s["cash_days"], s["hedged_pct"], s["segments"], s["longest"]) == (3, 6, 1, 2, 100.0, 2, 2)
    assert s["pct_of_bull"] == 50.0


def test_stage2_shift_window_only_and_seeds():
    d = pd.bdate_range("1999-06-01", periods=7000)
    z = pd.Series(np.arange(7000) % 11 == 0, index=d)
    assert Z.shifted_zone(z, None).equals(z)
    sh = Z.shifted_zone(z, 7)
    w = R6.shift_window(z)
    assert sh[~z.index.isin(w.index)].equals(z[~z.index.isin(w.index)])                       # 窗外不动
    assert sh.loc[w.index].tolist() == np.roll(w.to_numpy(), 7).tolist()
    assert Z.placebo_ks(len(w))[:3] == R6.shift_ks(len(w), 0, seeds=range(3))


def test_reference_shape_moves_only_inside_b2_bull_days():
    assert Z.ref_ks(2000)[:3] == [int(np.random.default_rng([20261003, s]).integers(250, 2000 - 250 + 1)) for s in range(3)]
    assert R3.ASSET_SEED == 20261003
    d = pd.bdate_range("1999-06-01", periods=7000)
    rng = np.random.default_rng(5)
    slow = pd.Series(np.repeat(rng.random(7000 // 80 + 1) < 0.3, 80)[:7000], index=d)
    fast = pd.Series(np.repeat(rng.random(7000 // 9 + 1) < 0.2, 9)[:7000], index=d) | slow
    z = Z.zone(slow, fast)
    assert Z.ref_zone(slow, z, 0).equals(z)                                                    # k = 0 → 候选本身
    m = Z.ref_mask(slow)
    r = Z.ref_zone(slow, z, 123).to_numpy()
    assert int(r[m].sum()) == int(z.to_numpy()[m].sum())                                       # 窗口里的天数不变
    assert not (r & slow.to_numpy()).any()                                                     # 只落在 B2 是牛的日子
    assert (r[~m] == z.to_numpy()[~m]).all()                                                   # 窗外 / 熊市照真实的


def test_sources_and_cli():
    s1 = inspect.getsource(Z.stage_one)
    assert "L6.load()" in s1 and 'R6.stage1(cand["ZBX"], base, posthoc=unseen)' in s1
    assert 'N3.old_core(W, M["uni"], W["bear"]["US"])' in s1 and 'N3.old_core(W, M["uni"], old_bear(W, M))' in s1
    assert "Y.or_series(W[\"bear\"][\"US\"].astype(bool), M[\"fast_us\"].astype(bool))" in inspect.getsource(Z.old_bear)
    w = inspect.getsource(Z.wiring)
    assert "no_zone_same_as_b2" in w and "old_core_b2_same" in w
    s2 = inspect.getsource(Z.stage_two)
    assert "placebo_ks(n)" in s2 and "R6.stage2(stat, vals)" in s2 and 'R6.shift_window(M["zone"])' in s2
    assert 'core_bear(M["slow_t"], shifted_zone(M["zone"], ks[int(seed)]))' in inspect.getsource(Z._placebo_one)
    r = inspect.getsource(Z.stage_two_ref)
    assert '"describe_only": True' in r and "ref_ks(n)" in r and "R6.verdict" not in r
    with pytest.raises(SystemExit):
        Z.main(["--nope"])
