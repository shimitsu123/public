"""行业联动（qbreak/sector_leadlag.py）：行业相对收益、可交易的目标对齐、美国日期对齐、Newey–West、
领先分的训练期不含标签未结束的日子、领先分不用未来数据、埋进去的领先关系能被发现并复现。"""
import numpy as np
import pandas as pd
import pytest

from qbreak import sector_leadlag as SL


def _ohlc(days, closes, opens=None):
    return pd.DataFrame({"Open": opens if opens is not None else closes, "Close": closes}, index=days)


def test_industry_returns_relative_to_all_and_min_members():
    days = pd.bdate_range("2020-01-01", periods=3)
    c = {"A1": [100, 110, 121], "A2": [100, 100, 100], "A3": [100, 100, 100], "B1": [100, 90, 90], "B2": [100, 100, 100],
         "B3": [100, 100, 100], "C1": [100, 200, 200]}
    s33 = {"A1": "a", "A2": "a", "A3": "a", "B1": "b", "B2": "b", "B3": "b", "C1": "c"}
    CC, OC = SL.industry_returns({t: _ohlc(days, np.array(v, float)) for t, v in c.items()}, s33)
    assert list(CC.columns) == ["a", "b"]                                             # c 只有 1 只 → 不要
    r = {t: np.log(v[1] / v[0]) * 100 for t, v in c.items()}
    univ = np.mean(list(r.values()))
    assert CC["a"].iloc[1] == pytest.approx((r["A1"] + r["A2"] + r["A3"]) / 3 - univ)
    assert OC["a"].abs().max() == pytest.approx(0)                                  # 开盘 = 收盘 → 日内收益 0


def test_target_is_tradable_from_next_open():
    idx = pd.bdate_range("2020-01-01", periods=30)
    CC = pd.DataFrame({"x": np.arange(30, dtype=float)}, index=idx)
    OC = pd.DataFrame({"x": np.arange(30, dtype=float) * 100}, index=idx)
    assert SL.target(CC, OC, (1, 1))["x"].iloc[3] == 400                              # 只拿到 D+1 的开盘→收盘
    assert SL.target(CC, OC, (1, 5))["x"].iloc[3] == 400 + 5 + 6 + 7 + 8
    assert SL.target(CC, OC, (6, 20))["x"].iloc[3] == sum(range(9, 24))
    assert np.isnan(SL.target(CC, OC, (6, 20))["x"].iloc[20])


def test_us_relative_uses_us_dates_up_to_jp_day():
    us = pd.DatetimeIndex(["2020-01-06", "2020-01-07", "2020-01-08"])
    etf = pd.Series([100.0, 110.0, 110.0], index=us)
    spy = pd.Series([100.0, 100.0, 100.0], index=us)
    jp = pd.DatetimeIndex(["2020-01-06", "2020-01-07", "2020-01-08"])
    R = SL.us_relative({"XLK": etf}, spy, jp, 1)
    assert np.isnan(R.loc["2020-01-06", "XLK"])
    assert R.loc["2020-01-07", "XLK"] == pytest.approx(np.log(1.1) * 100)            # 美国 1/7 收盘 → 日本 1/7 的「之后」可用
    assert R.loc["2020-01-08", "XLK"] == pytest.approx(0.0)


def test_nw_t_matches_ols_for_iid_and_is_wider_for_overlap():
    rng = np.random.default_rng(0)
    x, y = rng.normal(size=3000), rng.normal(size=3000)
    b0, t0, _ = SL.nw_t(x, 0.1 * x + y, 0)
    assert t0 == pytest.approx(0.1 * np.sqrt(3000), rel=0.2)
    xo = pd.Series(x).rolling(20).sum().to_numpy()
    yo = pd.Series(y).rolling(20).sum().shift(-20).to_numpy()
    assert abs(SL.nw_t(xo, yo, 39)[1]) < abs(SL.nw_t(xo, yo, 0)[1]) * 1.01 or abs(SL.nw_t(xo, yo, 0)[1]) < 2


def _planted(n=3000, seed=1, after=None, beta=0.35):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2007-01-01", periods=n)
    CC = pd.DataFrame(rng.normal(0, 1, (n, 3)), index=idx, columns=["A", "B", "C"])
    OC = pd.DataFrame(rng.normal(0, 1, (n, 3)), index=idx, columns=["A", "B", "C"])
    eff = beta * CC["A"].shift(1).fillna(0)                                          # A 今天涨 → B 明天日内跟着涨
    if after is not None:
        eff[idx < after] = 0
    OC["B"] += eff
    return CC, OC


def test_scan_finds_planted_lead_and_replicates():
    CC, OC = _planted()
    T = {"1": SL.target(CC, OC, (1, 1))}
    P = {1: SL.past(CC, 1)}
    d = CC.index
    H = {"H1": (d[0], d[1499]), "H2": (d[1500], d[-1])}
    D = SL.discoveries(SL.scan("JP→JP", P, T, H, "exclude"), 0.10)
    rep = D[D["replicated"]]
    assert ((rep["lead"] == "A") & (rep["target"] == "B")).any()
    assert len(rep) <= 2
    x = D[(D["lead"] == "A") & (D["target"] == "B")].iloc[0]
    assert x["hit_H1"] > 0.55


def test_lead_fit_respects_training_cut_and_score_is_causal():
    CC, OC = _planted(beta=0.6)
    Y = SL.target(CC, OC, SL.B_TARGET)
    P = {w: SL.past(CC, w) for w in SL.WINDOWS}
    m = SL.lead_fit(P, Y, len(Y), "jp")
    assert any(l == "A" for l, *_ in m.get("B", []))
    cut = 2000
    CC2, OC2 = _planted(beta=0.6, after=CC.index[cut - 5])                            # 关系只在切点前 5 天之后才有
    m2 = SL.lead_fit({w: SL.past(CC2, w) for w in SL.WINDOWS}, SL.target(CC2, OC2, SL.B_TARGET), cut, "jp")
    assert not any(l == "A" for l, *_ in m2.get("B", []))
    own = SL.lead_fit(P, Y, len(Y), "own")
    assert all(l == t for t, v in own.items() for l, *_ in v)
    a = SL.lead_score(m, P, list(Y.columns))
    P2 = {w: p.copy() for w, p in P.items()}
    for p in P2.values():
        p.iloc[2500:] *= 3
    b = SL.lead_score(m, P2, list(Y.columns))
    assert np.allclose(a.iloc[:2500], b.iloc[:2500])
    F, info = SL.lead_walk_forward(P, Y, [2012, 2013], "jp")
    assert F.loc[:"2011"].isna().all().all() and F.loc["2012"].notna().all().all() and set(info) == {2012, 2013}
