"""qbreak/model_switch.py：局势特征、扩张标准化、结果已知的时点、KNN / 动量 / 映射、趋势 × 波动格、两态 HMM（滤波不偷看）、门槛与错开对照。"""
import math

import numpy as np
import pandas as pd

from qbreak import model_switch as MS


def _months(n, start="2000-01"):
    return pd.period_range(start, periods=n, freq="M")


def test_features():
    idx = pd.bdate_range("2020-01-01", periods=300)
    up = pd.Series(np.linspace(100, 200, 300), index=idx)
    assert np.isnan(MS.sma_gap(up).iloc[198]) and MS.sma_gap(up).iloc[-1] > 0
    assert np.isclose(MS.efficiency_ratio(up, 60).iloc[-1], 1.0)                      # 单边 → 1
    zig = pd.Series(np.tile([100.0, 101.0], 150), index=idx)
    assert MS.efficiency_ratio(zig, 60).iloc[-1] < 0.05                                # 来回 → ≈ 0
    rv = MS.realized_vol(pd.Series(100 * np.exp(np.cumsum(np.full(300, 0.01))), index=idx), 60)
    assert np.isclose(rv.iloc[-1], 0.0, atol=1e-6)                                     # 每天一样 → 波动 0
    d = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-03"]))
    me = MS.month_end(d, _months(3, "2020-01"))
    assert list(me.iloc[:2]) == [2.0, 3.0] and np.isnan(me.iloc[2])


def test_expanding_z_has_no_lookahead():
    rng = np.random.default_rng(0)
    X = pd.DataFrame(rng.normal(size=(60, 2)), index=_months(60), columns=["a", "b"])
    z1 = MS.expanding_z(X, 36)
    z2 = MS.expanding_z(pd.concat([X, pd.DataFrame(rng.normal(size=(10, 2)) * 100, index=_months(10, "2005-01"), columns=["a", "b"])]), 36)
    assert z1.iloc[:35].isna().all().all() and np.allclose(z1.iloc[35:].to_numpy(), z2.iloc[35:60].to_numpy())


def test_known_outcome_months_and_mom():
    P = pd.DataFrame({"a": [1.0, 2.0, np.nan, 0.0, 5.0], "b": [2.0, 1.0, np.nan, 3.0, 0.0]}, index=_months(5))
    t = P.index[4]
    assert MS.known_outcome_months(P, t, 0) == [P.index[i] for i in (0, 1, 3, 4)]          # 全 NaN 的月不算
    assert MS.known_outcome_months(P, t, 2) == [P.index[0], P.index[1]]
    assert MS.mom_pick(P, t, 0, 1) == "a" and MS.mom_pick(P, t, 0, 2) == "a"            # (0 + 5) / 2 vs (3 + 0) / 2
    assert MS.mom_pick(P, t, 2, 1) == "a" and MS.mom_pick(P, P.index[0], 3, 1) is None


def test_knn_pick_learns_state_and_respects_lag():
    n = 60
    idx = _months(n)
    s = np.where(np.arange(n) % 2 == 0, 1.0, -1.0)                                     # 偶数月状态 +1、奇数月 −1
    Z = pd.DataFrame({"x": s}, index=idx)
    P = pd.DataFrame({"up": np.where(np.roll(s, 1) > 0, 1.0, -1.0), "dn": np.where(np.roll(s, 1) > 0, -1.0, 1.0)}, index=idx)
    # P 的 u 月：上一个月（u − 1）的状态 +1 → up 好
    t = idx[50]
    assert MS.knn_pick(Z, P, t, 0, k=5, min_hist=10) == ("up" if s[50] > 0 else "dn")
    assert MS.knn_pick(Z, P, idx[5], 0, k=5, min_hist=10) is None                       # 历史不够
    Z2 = Z.copy()
    Z2.iloc[50] = np.nan
    assert MS.knn_pick(Z2, P, t, 0) is None
    assert MS.knn_pick(Z, P, t, 45, k=5, min_hist=10) is None                        # lag 45：已知结果只到 idx[5] → 候选不够
    P2 = P.copy()
    P2.iloc[46:] = P2.iloc[46:][["dn", "up"]].to_numpy()                              # 最近 5 个月反过来（还不知道的结果）
    assert MS.knn_pick(Z, P2, t, 5, k=5, min_hist=10) == MS.knn_pick(Z, P, t, 5, k=5, min_hist=10)


def test_map_pick_and_cells():
    idx = _months(30)
    lab = pd.Series(["x", "y"] * 15, index=idx)
    P = pd.DataFrame({"a": np.where(np.arange(30) % 2 == 1, 1.0, 0.0), "b": 0.5}, index=idx)   # x 月的下一个月（奇数）a 好
    assert MS.map_pick(lab, P, idx[28], 0, min_n=5) == "a"                                    # idx[28] 是 x
    assert MS.map_pick(lab, P, idx[29], 0, min_n=5) == "b"                                    # y 的下一个月 a = 0
    assert MS.map_pick(lab, P, idx[4], 0, min_n=5, default="b") == "b"
    gap = pd.Series([1.0, -1.0, -2.0, 3.0], index=_months(4))
    c = MS.trend_vol_cells(gap, pd.Series([1.0, 1.0, -1.0, np.nan], index=gap.index), pd.Series([10.0, 30.0, 5.0, 10.0], index=gap.index), 1)
    assert list(c.iloc[:3]) == ["up_hi", "mix_hi", "down_lo"] and pd.isna(c.iloc[3])


def _two_regime(n=300, seed=1):
    rng = np.random.default_rng(seed)
    st = np.zeros(n, int)
    for i in range(1, n):
        st[i] = st[i - 1] if rng.random() < 0.95 else 1 - st[i - 1]
    X = np.column_stack([np.where(st == 1, -1.0, 1.0) + rng.normal(0, 0.5, n), np.where(st == 1, 2.0, 0.0) + rng.normal(0, 0.3, n)])
    return X, st


def test_hmm_fit_recovers_regimes_and_filter_is_causal():
    X, st = _two_regime()
    prm = MS.hmm_fit(X, order_col=1)
    assert prm["mu"][0, 1] < prm["mu"][1, 1] and abs(prm["mu"][1, 1] - 2.0) < 0.3     # 状态 1 = 波动高
    f = MS.hmm_filter(X, prm)
    assert np.allclose(f.sum(axis=1), 1.0)
    acc = float(np.mean(np.argmax(f, axis=1) == st))
    assert acc > 0.9
    f2 = MS.hmm_filter(np.vstack([X, X[:50] * 10]), prm)
    assert np.allclose(f[:300], f2[:300])                                             # 后面的数据不影响前面的滤波概率


def test_hmm_labels_refit_rule():
    X, _ = _two_regime(120, seed=2)
    F = pd.DataFrame(X, index=_months(120, "1990-01"), columns=["r", "v"])
    lab = MS.hmm_labels(F, min_n=60, order_col=1)
    assert lab.iloc[:59].isna().all() and lab.iloc[59:].notna().all() and set(lab.dropna()) <= {"s0", "s1"}
    lab2 = MS.hmm_labels(pd.concat([F, F.iloc[:12].set_axis(_months(12, "2000-01"))]), min_n=60, order_col=1)
    assert (lab2.iloc[:120].fillna("na") == lab.fillna("na")).all()                   # 后来的数据不改以前的标签


def test_gains_placebo_gate():
    idx = _months(40)
    rng = np.random.default_rng(3)
    P = pd.DataFrame(rng.normal(size=(40, 3)), index=idx, columns=["a", "b", "c"])
    best = P.idxmax(axis=1)
    picks = pd.Series([best.get(t + 1) for t in idx], index=idx).dropna()           # 作弊：直接选下个月最好的
    G = MS.gains(picks, P, "a")
    u = idx[1]
    assert np.isclose(G.loc[idx[0], "g"], P.loc[u].max() - P.loc[u].mean()) and np.isclose(G.loc[idx[0], "h"], P.loc[u].max() - P.loc[u, "a"])
    pl = MS.shift_placebo(picks, P, "a", 12)
    assert len(pl) == len(picks) - 24 + 1 and G["g"].mean() > pl.max()
    assert np.isclose(MS.emp_p(float(G["g"].mean()), pl), 1 / (1 + len(pl)))
    eras = {"X": ("2000-02", "2001-08"), "Y": ("2001-09", "2003-04")}
    assert MS.era_of(idx[0], eras) == "X" and MS.era_of(idx[39], eras) is None
    gt = MS.gate(G, eras, pl, p_max=0.1)
    assert gt["pass"] and gt["c"] == [True] * 4
    assert not MS.gate(G, eras, pl, p_max=0.001)["c"][3]
    e = MS.gate(G.iloc[:0], eras, pl, 0.1)
    assert e["n"] == 0 and not e["pass"] and e["eras"] == {"X": None, "Y": None}
    assert MS.nw_t(np.ones(5)) is None and MS.nw_t(np.r_[np.ones(10), np.ones(10) * 3]) > 0
    assert math.isclose(MS.emp_p(0.0, np.array([1.0, -1.0])), 2 / 3)
