"""第六个研究循环第 1 轮 BCU / BCJ / BCB（scripts/loop6_r01_bondcorr.py，2026-10-03 登记）：登记值与第六个循环的规则、
63 天股债相关条件（负相关才拿、不到 63 天不拿、不看未来）、熊市日子的计数、接法（第二 / 三个循环的 *_over 原样）、第二关的平移与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop6_r01_bondcorr as T  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants_and_loop6_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.WIN, T.KIND) == (1, ("BCU", "BCJ", "BCB"), True, 63, {k: "asset" for k in ("BCU", "BCJ", "BCB")})
    assert T.FAMILY == {k: "核心·熊市避险资产" for k in T.IDS} and T.USE == {"BCU": (True, False), "BCJ": (False, True), "BCB": (True, True)}
    assert T.SAME3 == {"BCU": "BAU", "BCJ": "BAJ", "BCB": "BAB"} and not set(T.IDS) & R6.previous_ids(ROOT / "var")
    st = R6.load_state(ROOT / "var")
    if not st:
        pytest.skip("第六个研究循环还没有登记")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R6.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND[k]} for k in T.IDS], R6.previous_ids(ROOT / "var"))


def _walk(seed, n=300):
    rng = np.random.default_rng(seed)
    return rng.normal(0, 0.01, n)


def test_corr_on_sign_and_warmup():
    d = pd.bdate_range("2020-01-01", periods=300)
    r = _walk(1)
    stock = pd.Series(100 * np.cumprod(1 + r), index=d)
    neg = pd.Series(100 * np.cumprod(1 - 0.5 * r + _walk(2) * 0.1), index=d)           # 与股票负相关
    pos = pd.Series(100 * np.cumprod(1 + 0.5 * r + _walk(3) * 0.1), index=d)           # 正相关
    on_n, on_p = T.corr_on(stock, neg), T.corr_on(stock, pos)
    assert not on_n.iloc[:63].any() and not on_p.iloc[:63].any()                        # 不到 63 天（收益第一个是 NaN）→ 不拿
    assert on_n.iloc[64:].all() and not on_p.iloc[64:].any()
    assert on_n.index.equals(neg.index)


def test_corr_on_uses_no_future():
    d = pd.bdate_range("2020-01-01", periods=300)
    stock = pd.Series(100 * np.cumprod(1 + _walk(4)), index=d)
    bond = pd.Series(100 * np.cumprod(1 + _walk(5)), index=d)
    full = T.corr_on(stock, bond)
    cut = T.corr_on(stock.iloc[:200], bond.iloc[:200])
    assert full.iloc[:200].equals(cut)                                                  # 后来的数据不改变以前的判断


def test_bear_on_stats_counts_days_only():
    d = pd.bdate_range("2021-12-27", periods=20)
    bear = pd.Series([False] * 5 + [True] * 15, index=d)
    on = pd.Series([True] * 10 + [False] * 10, index=d)
    s = T.bear_on_stats(bear, on, d)
    assert s["bear_pct"] == 75.0 and s["on_in_bear_pct"] == round(5 / 15 * 100, 1) and s["segments"] == 1
    assert s["off_years"] == [] and sum(s["bear_days_by_year"].values()) == 15


def test_wiring_and_cli():
    o = inspect.getsource(T.overs)
    assert "T2.tbh_over(bear_us, on_b, fb)" in o and "T3.tbj_over(bear_us, on_j, fj)" in o and "T4.tbu_over(bear_us, on_b, fb, on_j, fj)" in o
    i = inspect.getsource(T.inputs)
    assert "T2.bond_close(W[\"inp\"]), T3.jgb_close(W[\"inp\"])" in i and "masks(spx, bc, jc)" in i
    assert "EI.on_jp(W[\"inp\"][\"spx\"][\"Close\"].astype(float), None, pd.DatetimeIndex(days))" in inspect.getsource(T.spx_tse)
    s1 = inspect.getsource(T.stage_one)
    assert "R6.stage1(cand[k], base, posthoc=unseen)" in s1 and "old_core(W, uni, *USE[k])" in s1
    oc = inspect.getsource(T.old_core)
    assert ".shift(1, fill_value=False)" in oc and "T4.union_weights(bear, hdg" in oc and ".shift(1).fillna(0.0)" in oc
    w = inspect.getsource(T.wiring)
    assert "never_same_as_b1" in w and "always_same_as_loop3" in w and "REF3" in w
    sh = inspect.getsource(T.shifted_inputs)
    assert "R6.asset_shift(M[\"bc\"].reindex(idx), k), R6.asset_shift(M[\"jc\"].reindex(idx), k)" in sh and "masks(M[\"spx\"], bc, jc)" in sh
    s2 = inspect.getsource(T.stage_two)
    assert "R6.shift_ks(n, 1)" in s2 and "R6.stage2(stat, vals)" in s2
    with pytest.raises(SystemExit):
        T.main(["--nope"])
