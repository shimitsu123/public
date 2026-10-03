"""第六个研究循环第二段第 3 轮 NDB（scripts/loop6_r03_earlyreturn.py，2026-10-03 登记）：登记值与第二段的规则、早回来与核心用的熊（NDR 原样）、
东证日的对齐（d 之前含 d 的最近一个值）、接法（B2 同一对函数，三个核心键都换成核心用的熊）、只数日子的统计、第二关的平移与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop6_r03_earlyreturn as N  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_loop6_segment2_rules():
    assert (N.ROUND, N.IDS, N.POSTHOC) == (3, ("NDB",), True)
    assert N.KIND == {"NDB": "signal"} and set(N.KIND.values()) <= set(R6.KINDS)
    assert N.FAMILY == {"NDB": "核心·择时（早回来）"} and N.FAMILY["NDB"].startswith(R6.FAMILY_PREFIX)
    st = R6.load_state(ROOT / "var")
    if not R6.segment(st):
        pytest.skip("第二段还没有登记")
    assert not set(N.IDS) & (R6.previous_ids(ROOT / "var") | R6.earlier_ids(st))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == N.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(N.IDS)
    else:
        R6.check_new_approaches(st, [{"id": k, "family": N.FAMILY[k], "posthoc": N.POSTHOC, "kind": N.KIND[k]} for k in N.IDS],
                                R6.previous_ids(ROOT / "var"))


def test_early_return_and_core_bear_follow_ndr():
    d = pd.bdate_range("2024-01-01", periods=12)
    spx = pd.Series([0, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0], index=d).astype(bool)
    ndx = pd.Series([0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0], index=d).astype(bool)
    e = N.early(spx, ndx)
    # 第一段 S&P 熊（1〜7）：纳指 2〜3 熊、4 起牛 → 4、5 早回来；6 再熊 → 不是；7 牛（这一段里熊过）→ 早回来；第二段（9〜10）纳指没熊过 → 不是
    assert e.tolist() == [False, False, False, False, True, True, False, True, False, False, False, False]
    cb = N.core_bear(spx, ndx)
    assert cb.tolist() == (spx & ~e).tolist()
    assert N.core_bear(spx, pd.Series(True, index=d)).tolist() == spx.tolist()                 # 纳指永远是熊 → 永远没有早回来
    assert N.core_bear(spx, pd.Series(False, index=d)).tolist() == spx.tolist()                # 纳指从来不熊 → 也没有早回来


def test_on_idx_is_asof_including_same_date():
    us = pd.Series([True, False, True], index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-05"]))
    tse = pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-04", "2024-01-08"])
    assert N.on_idx(us, tse).tolist() == [False, False, False, True]                           # 之前没有值 = False；同一天用同一天的值


def test_over_uses_core_bear_for_all_three_core_keys():
    import loop2_r02_bondrefuge as T2
    import loop_r04_yensurge as Y
    d = pd.bdate_range("2024-01-01", periods=4)
    W = {"kw": {"Z": {"extra_core": {}}}}
    cb = pd.Series([True, False, True, False], index=d)            # 熊、早回来 / 牛、熊、牛
    uni = pd.Series([False, True, False, False], index=d)
    on_b = pd.Series([True, True, False, False], index=d)
    fr = pd.DataFrame({"Close": 1.0}, index=d)
    o = N.over(W, cb, uni, fr, on_b, fr)
    assert set(o["cfg_over"]["core"]) == {"1545.T", Y.HEDGE_T, T2.BOND_T} and o["cfg_over"]["core_mode"] == "follow"
    eb = o["extra_bear"]
    assert eb[T2.BD_KEY].tolist() == [False, True, True, True]                                  # 只在 核心用的熊 ∧ 负相关 拿 1482
    assert eb[Y.UH_KEY].tolist() == [True, True, True, False] and eb[Y.HG_KEY].tolist() == [True, False, True, True]
    assert set(o["extra_core"]) == {Y.HEDGE_T, T2.BOND_T}


def test_split_days_counts_days_only():
    d = pd.bdate_range("2020-03-02", periods=10)
    re = pd.Series([False] * 3 + [True] * 5 + [False] * 2, index=d)
    spx = pd.Series([True] * 9 + [False], index=d)
    on_b = pd.Series([True] * 5 + [False] * 5, index=d)
    uni = pd.Series([True] * 4 + [False] * 6, index=d)
    s = N.split_days(re, spx, on_b, uni, d)
    assert (s["early_days"], s["b2_bond_days"], s["b2_cash_days"], s["hedged_pct"]) == (5, 2, 3, 20.0)
    assert s["segments"] == [["2020-03-05", "2020-03-11", 5]]


def test_shift_window_only_and_placebo_seeds():
    d = pd.bdate_range("1999-06-01", periods=7000)
    s = pd.Series(np.arange(7000) % 9 == 0, index=d)
    assert N.shifted_ndx(s, None).equals(s)
    sh = N.shifted_ndx(s, 5)
    w = R6.shift_window(s)
    assert sh[~s.index.isin(w.index)].equals(s[~s.index.isin(w.index)])                       # 窗外不动
    assert sh.loc[w.index].tolist() == np.roll(w.to_numpy(), 5).tolist()
    assert N.placebo_ks(len(w))[:3] == R6.shift_ks(len(w), 0, seeds=range(3))


def test_wiring_sources_and_cli():
    o = inspect.getsource(N.over)
    assert "Y.fxh_over(W, cb, uni, hf)" in o and "T2.tbh_over(cb, on_b, fb)" in o and "L6.merge_over(" in o
    s1 = inspect.getsource(N.stage_one)
    assert "L6.load()" in s1 and 'R6.stage1(cand["NDB"], base, posthoc=unseen)' in s1
    assert 'old_core(W, M["uni"], W["bear"]["US"])' in s1 and 'N8.nr_key(W["bear"]["US"], M["ndx_us"])' in s1
    w = inspect.getsource(N.wiring)
    assert "never_early_same_as_b2" in w and "no_bond_same_as_ndrh_J" in w and "old_core_b2_same" in w
    s2 = inspect.getsource(N.stage_two)
    assert "placebo_ks(n)" in s2 and "R6.stage2(stat, vals)" in s2 and 'R6.shift_window(M["ndx_t"])' in s2
    p = inspect.getsource(N._placebo_one)
    assert 'core_bear(M["spx_t"], shifted_ndx(M["ndx_t"], ks[int(seed)]))' in p
    with pytest.raises(SystemExit):
        N.main(["--nope"])


def test_reference_shape_matches_ndrh_and_only_moves_inside_spx_bear():
    import loop2_r08_ndrhedged as R8
    assert N.ref_ks(1500)[:5] == [R8.shift_k(s, 1500) for s in range(5)]                      # NDRH 同一组平移量
    d = pd.bdate_range("1999-06-01", periods=9000)
    rng = np.random.default_rng(7)
    spx = pd.Series(np.repeat(rng.random(9000 // 60 + 1) < 0.35, 60)[:9000], index=d)
    ndx = pd.Series(np.repeat(rng.random(9000 // 25 + 1) < 0.4, 25)[:9000], index=d)
    assert N.ref_core_bear(spx, ndx, 0).equals(N.core_bear(spx, ndx))                          # k = 0 → 候选本身
    m = N.ref_mask(spx)
    re = N.early(spx, ndx).to_numpy(bool)
    k = N.ref_core_bear(spx, ndx, 37)
    moved = spx.to_numpy() & ~k.to_numpy()                                                     # 平移后的早回来
    assert not (moved & ~spx.to_numpy()).any()                                                 # 只落在 S&P 熊的日子里
    assert int(moved[m].sum()) == int(re[m].sum())                                             # 窗口里早回来的天数不变
    assert (moved[~m] == re[~m]).all()                                                         # 窗外照真实的


def test_stage2ref_is_describe_only_and_cli():
    s = inspect.getsource(N.stage_two_ref)
    assert '"describe_only": True' in s and "ref_ks(n)" in s and "_stage2ref_" in s and "R6.verdict" not in s
    p = inspect.getsource(N._placebo_ref_one)
    assert 'ref_core_bear(M["spx_t"], M["ndx_t"], ks[int(seed)])' in p
    with pytest.raises(SystemExit):
        N.main(["--stage2ref", "XXX"])
