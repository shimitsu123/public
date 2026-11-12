"""研究循环第 12 轮 ERG（scripts/loop_r12_trendgate.py，2026-10-01 登记）：登记值、效率比、只用过去的门槛、倍数的时点、循环平移。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_common as LCM  # noqa: E402
import loop_r12_trendgate as G  # noqa: E402


def test_registered_constants():
    assert (G.ROUND, G.IDS, G.ER_N, G.Q_WIN, G.Q) == (12, ("ERG",), 60, 1250, 1 / 3)
    assert (G.SHIFT_FROM, G.SHIFT_GAP, G.SEED0) == ("2000-01-04", 250, 20261012)


def test_efficiency_ratio_line_is_one_and_zigzag_is_low():
    idx = pd.bdate_range("2020-01-01", periods=10)
    line = pd.Series(np.arange(10, dtype=float) + 100, index=idx)
    er = G.efficiency_ratio(line, 3)
    assert er.iloc[:3].isna().all() and np.allclose(er.iloc[3:], 1.0)
    zig = pd.Series([100.0, 101] * 5, index=idx)
    ez = G.efficiency_ratio(zig, 4)
    assert np.allclose(ez.iloc[4:], 0.0)                                                   # 来回 → 0
    flat = pd.Series(100.0, index=idx)
    assert G.efficiency_ratio(flat, 3).isna().all()                                        # 分母 0 → NaN


def test_chop_state_uses_only_past_and_needs_full_window():
    idx = pd.bdate_range("2010-01-01", periods=400)
    rng = np.random.default_rng(5)
    c = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))), index=idx)
    a = G.chop_state(c, n=10, win=50)
    assert not a.iloc[:59].any()                                                           # 10 天 ER + 50 天分位之前都不算
    c2 = c.copy()
    c2.iloc[300:] = c2.iloc[300:] * 1.3 + 7                                                # 改将来
    b = G.chop_state(c2, n=10, win=50)
    assert a.iloc[:300].equals(b.iloc[:300])                                               # 过去不变（不偷看）
    er = G.efficiency_ratio(c, 10)
    thr = er.rolling(50, min_periods=50).quantile(1 / 3)
    m = thr.notna()
    assert a[m].tolist() == (er[m] < thr[m]).tolist()


def test_gate_factor_blocks_next_trading_day():
    days = pd.bdate_range("2020-01-06", periods=5)
    chop = pd.Series([False, True, False], index=pd.to_datetime(["2020-01-03", "2020-01-07", "2020-01-09"]))
    g = G.gate_factor(chop, days)
    assert g.tolist() == [1.0, 0.0, 0.0, 1.0, 1.0]                                         # 01-08 向后填还是震荡
    m = LCM.fill_scale(g, days)
    assert m.tolist() == [1.0, 1.0, 0.0, 0.0, 1.0]                                         # 信号日 d → d+1 成交
    assert G.chop_at(chop, ["2020-01-08", "2020-01-08", "2020-01-10"]).tolist() == [True, True, False]


def test_shift_placebo_keeps_days_and_is_reproducible():
    idx = pd.bdate_range("1999-06-01", "2026-10-30")
    s = pd.Series((np.arange(len(idx)) % 75) < 25, index=idx)
    a, b = G.shifted(s, 6), G.shifted(s, 6)
    assert a.equals(b) and int(a.sum()) == int(G.shift_domain(s).sum())
    w = G.shift_domain(s)
    ks = [G.shift_k(x, len(w)) for x in range(400)]
    assert min(ks) >= 250 and max(ks) <= len(w) - 250 and len(set(ks)) > 300
