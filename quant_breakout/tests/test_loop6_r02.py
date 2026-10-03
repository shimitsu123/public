"""第六个研究循环第二段第 2 轮 BCS / BCM / BCF（scripts/loop6_r02_bondgate.py，2026-10-03 登记）：登记值与第六个循环第二段的规则、
63 天涨跌条件（不到 63 天不拿、不看未来）、与 BCU 条件的「且」、只数日子的统计、接法（B2 同一个 tbh_over）、第二关的平移与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop6_r02_bondgate as G  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_loop6_segment2_rules():
    assert (G.ROUND, G.IDS, G.POSTHOC, G.WIN) == (2, ("BCS", "BCM", "BCF"), True, 63)
    assert G.KIND == {"BCS": "signal", "BCM": "signal", "BCF": "combo"} and set(G.KIND.values()) <= set(R6.KINDS)
    assert G.FAMILY == {k: "核心·熊市避险资产" for k in G.IDS} and G.USE == {"BCS": (True, False), "BCM": (False, True), "BCF": (True, True)}
    st = R6.load_state(ROOT / "var")
    if not R6.segment(st):
        pytest.skip("第二段还没有登记")
    assert not set(G.IDS) & (R6.previous_ids(ROOT / "var") | R6.earlier_ids(st))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == G.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(G.IDS)
    else:
        R6.check_new_approaches(st, [{"id": k, "family": G.FAMILY[k], "posthoc": G.POSTHOC, "kind": G.KIND[k]} for k in G.IDS],
                                R6.previous_ids(ROOT / "var"))


def _walk(seed, n=300, start="2020-01-01"):
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, n)), index=pd.bdate_range(start, periods=n))


def test_falling_rising_sign_warmup_and_no_future():
    s = _walk(1)
    f, r = G.falling(s), G.rising(s)
    assert not f.iloc[:63].any() and not r.iloc[:63].any()                                   # 不到 63 天 → 不拿
    ret = (s / s.shift(63) - 1).iloc[63:]
    assert f.iloc[63:].tolist() == (ret < 0).tolist() and r.iloc[63:].tolist() == (ret > 0).tolist()
    assert G.falling(s.iloc[:200]).equals(f.iloc[:200]) and G.rising(s.iloc[:200]).equals(r.iloc[:200])   # 后来的数据不改变以前的判断


def test_gated_is_and_of_bcu_condition_and_gates():
    d = pd.bdate_range("2024-01-01", periods=6)
    on_b = pd.Series([True, True, True, False, True, True], index=d)
    g = {"spx_down": pd.Series([True, False, True, True, True, False], index=d),
         "bond_up": pd.Series([True, True, False, True, False, False], index=d)}
    assert G.gated(on_b, g, G.USE["BCS"]).tolist() == [True, False, True, False, True, False]
    assert G.gated(on_b, g, G.USE["BCM"]).tolist() == [True, True, False, False, False, False]
    assert G.gated(on_b, g, G.USE["BCF"]).tolist() == [True, False, False, False, False, False]
    assert G.on_idx(pd.Series([True], index=d[2:3]), d).tolist() == [False, False, True, True, True, True]   # 向后填、之前 = 不拿


def test_keep_stats_counts_days_only():
    d = pd.bdate_range("2021-12-27", periods=20)
    bear = pd.Series([False] * 4 + [True] * 16, index=d)
    on_b = pd.Series([True] * 20, index=d)
    cand = pd.Series([True] * 10 + [False] * 10, index=d)
    s = G.keep_stats(bear, on_b, cand, d)
    assert (s["b2_days"], s["cand_days"], s["keep_pct"], s["segments"], s["b2_segments"]) == (16, 6, 37.5, 1, 1)
    assert sum(s["dropped_by_year"].values()) == 10


def test_wiring_and_shifts_and_cli():
    o = inspect.getsource(G.overs)
    assert "T2.tbh_over(bear_us, gated(on_b, g, USE[k]), fb)" in o
    assert 'M = dict(W["bcu"])' in inspect.getsource(G.inputs) and "L6.load()" in inspect.getsource(G.stage_one)
    s1 = inspect.getsource(G.stage_one)
    assert "R6.stage1(cand[k], base, posthoc=unseen)" in s1 and 'old["B2"]' in s1 and "old_core(W, uni, None)" in s1
    oc = inspect.getsource(G.old_core)
    assert "T.corr_on(ffull(spx), ffull(bnd))" in oc and "cond.shift(1, fill_value=False)" in oc and ".shift(1).fillna(0.0)" in oc
    w = inspect.getsource(G.wiring)
    assert "always_same_as_b2" in w and "never_same_as_b1" in w and "T.OUT" in w
    d = pd.bdate_range("2000-01-04", periods=800)
    g = {"spx_down": pd.Series(np.arange(800) % 7 == 0, index=d), "bond_up": pd.Series(np.arange(800) % 5 == 0, index=d)}
    sh = G.shifted_gates(g, (3, None))
    assert sh["bond_up"].equals(g["bond_up"]) and sh["spx_down"].tolist() == np.roll(g["spx_down"].to_numpy(), 3).tolist()
    assert G.placebo_ks("BCS", 800)[:3] == [(k, None) for k in R6.shift_ks(800, 0, seeds=range(3))]
    assert G.placebo_ks("BCM", 800)[:3] == [(None, k) for k in R6.shift_ks(800, 0, seeds=range(3))]
    assert G.placebo_ks("BCF", 800)[:3] == [tuple(x) for x in R6.combo_ks(800, 2, seeds=range(3))]
    s2 = inspect.getsource(G.stage_two)
    assert "placebo_ks(k, n)" in s2 and "R6.stage2(stat, vals)" in s2
    with pytest.raises(SystemExit):
        G.main(["--nope"])
