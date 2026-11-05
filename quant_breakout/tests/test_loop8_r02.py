"""第八个研究循环第 2 轮 VRB（scripts/loop8_r02_vrphigh.py，2026-10-04 登记）：登记的常数与判定的接线、旗标只用之前的月末（滚动 60 个的 80 分位）、
旗标只在月末之后变、熊市里拿回 1/3、第二关只在「不是牛」的日子上平移（天数不变）、旗标全假 → Δ = 0。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop8_r02_vrphigh as V  # noqa: E402
import research_loop8 as L8  # noqa: E402


def test_registered_constants_and_judgment():
    assert (V.ROUND, V.IDS, V.FAMILY, V.POSTHOC, V.Q, V.HIST, V.SEED_B, V.PLACEBO_N, V.SHIFT_GAP) == (
        2, ("VRB",), "期权·波动风险溢价", True, 0.8, 60, 20261012, 400, 250)
    assert V.PART == pytest.approx(1 / 3) and V.FAMILY in L8.SOURCES
    assert V.CROSS == ("US", "EU", "AU", "IN") and V.WINDOW_B == ("2009-01-01", "2026-09-30") and V.DESC_X == ("BR", "NDX")
    s1, s2, ra = inspect.getsource(V.stage_one), inspect.getsource(V.stage_two), inspect.getsource(V.run_all)
    assert "R6.stage1(cand, base, posthoc=unseen)" in s1 and "BP.bpr_over(W, M, M[\"sig_t\"])" in s1 and "BP.old_core(W, M[\"sig_us\"])" in s1
    assert "R7.judge(real, plac)" in s2 and "shift_ks(n_min)" in s2 and "nonbull_days(" in s2
    assert "R7.FOUND if (a[\"ok\"] and b[\"judge\"][\"ok\"])" in ra


def test_flag_uses_only_previous_month_ends():
    idx = pd.bdate_range("2000-01-03", "2008-12-31")
    c = pd.Series(100.0, index=idx)
    me = L8.month_ends_done(c)
    v = pd.Series(np.nan, index=idx)
    vals = np.arange(len(me), dtype=float)                                      # 越来越大 → 每个月末都 ≥ 之前的 80 分位
    v.loc[me] = vals
    f = V.flag_me(c, v)
    assert list(f.index) == list(me)
    assert not f.iloc[:60].any() and f.iloc[60:].all()                         # 之前不够 60 个 → 假
    v2 = v.copy()
    v2.loc[me[70]] = -1.0                                                       # 这个月末低 → 假
    v2.loc[me[71]] = np.nan                                                     # 算不了 → 假、也不进以后的分位
    f2 = V.flag_me(c, v2)
    assert not f2.iloc[70] and not f2.iloc[71] and f2.iloc[72]
    past = (list(vals[:70]) + [-1.0])[-60:]                                     # 第 72 个月末之前有值的最近 60 个（第 71 个是空 → 不算）
    assert bool(f2.iloc[72]) == bool(vals[72] >= np.quantile(past, 0.8))
    v3 = v.copy()
    v3.loc[me[80]] = float(np.quantile(vals[20:80], 0.8)) - 1e-9                # 刚好低于之前 60 个的 80 分位 → 假
    assert not V.flag_me(c, v3).iloc[80] and V.flag_me(c, v3).iloc[79]


def test_flag_daily_changes_only_after_month_ends():
    idx = pd.bdate_range("2024-01-01", "2024-04-10")
    c = pd.Series(100.0, index=idx)
    me = L8.month_ends_done(c)
    fm = pd.Series([True, False], index=me[:2])
    d = V.flag_daily(c, fm)
    assert not d[d.index < me[0]].any() and d.loc[me[0]] and d[(d.index > me[0]) & (d.index < me[1])].all()
    assert not d[d.index >= me[1]].any() and d.index.equals(c.index)


def test_expo_and_shift_nonbull_keeps_count():
    idx = pd.bdate_range("2008-06-02", "2027-01-29")
    bull = pd.Series((np.arange(len(idx)) // 120) % 2 == 0, index=idx)
    flag = pd.Series((np.arange(len(idx)) // 21) % 5 == 0, index=idx)
    e = V.expo_vrb(bull, flag)
    assert (e[bull] == 1.0).all() and np.allclose(e[~bull & flag], 1 / 3) and (e[~bull & ~flag] == 0.0).all()
    w = (idx >= pd.Timestamp(V.WINDOW_B[0])) & (idx <= pd.Timestamp(V.WINDOW_B[1]))
    s = V.shift_nonbull(flag, bull, 77)
    nbw = w & ~bull.to_numpy()
    assert int(s[nbw].sum()) == int(flag[nbw].sum())                           # 不是牛的日子里有旗标的天数不变
    assert s[~nbw].equals(flag[~nbw]) and not s[nbw].equals(flag[nbw])         # 牛的日子与窗外不动
    assert V.shift_nonbull(flag, bull, None).equals(flag)
    assert V.nonbull_days(bull) == int(nbw.sum())


def test_cross_deltas_zero_with_no_flags_and_shift_ks():
    idx = pd.bdate_range("2006-01-02", "2026-09-30")
    g = np.random.default_rng(5)
    closes = {m: pd.Series(100 * np.exp(np.cumsum(g.normal(0.0003, 0.01, len(idx)))), index=idx) for m in ("A", "B")}
    bulls = {m: c > c.rolling(250, min_periods=250).mean() for m, c in closes.items()}   # 测试用的牛（检测器的配置在临时目录里没有）
    none = {m: pd.Series(False, index=idx) for m in closes}
    for k in (None, 333):
        d = V.deltas(closes, none, bulls, k)
        assert all(abs(x) < 1e-12 for v in d.values() for x in v)
    some = {m: pd.Series((np.arange(len(idx)) // 21) % 4 == 0, index=idx) for m in closes}
    assert V.deltas(closes, some, bulls, None) != V.deltas(closes, some, bulls, 300)
    ks = V.shift_ks(900)
    assert len(ks) == 400 and min(ks) >= 250 and max(ks) <= 650 and ks == V.shift_ks(900)
    with pytest.raises(ValueError):
        V.shift_ks(500)
