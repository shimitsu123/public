"""错峰（qbreak/lag_factors.py）：错开的因子不用未来数据、之后第 L 天与窗口的对齐、BH、错开天数只在训练样本里选、
延迟顺风分的训练期不含标签未结束的日子、顺风分不用未来数据。"""
import numpy as np
import pandas as pd
import pytest

from qbreak import lag_factors as LF
from qbreak import signal_score as S
from qbreak.config import StrategyParams
from qbreak.strategy import compute_indicators

P = StrategyParams(range_x_pct=40.0, vol_mult=1.0)
TICK = ["4004.T", "4005.T", "4021.T", "8306.T", "8316.T", "8411.T"]


def _ind(n=700, seed=4):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2016-01-01", periods=n)
    out = {}
    for t in TICK:
        c = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
        o = c * (1 + rng.normal(0, 0.004, n))
        out[t] = compute_indicators(pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.01, "Low": np.minimum(o, c) * 0.99,
                                                  "Close": c, "Volume": rng.integers(50_000, 400_000, n).astype(float)},
                                                 index=days), P)
    idx = pd.Series(30000 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n))), index=days)
    return out, idx


def test_lagged_rows_take_values_from_l_days_before():
    ind, idx = _ind()
    panel = S.feature_panel(ind, idx)
    R = LF.lagged_rows(panel, ind)
    assert len(R) > 0
    x = R.iloc[len(R) // 2]
    i = panel["vol"].index.get_loc(x["date"])
    for L in LF.LAGS:
        v = panel["vol"].iloc[i - L][x["ticker"]] if i - L >= 0 else np.nan
        assert (np.isnan(v) and np.isnan(x[f"vol@{L}"])) or x[f"vol@{L}"] == pytest.approx(v)
    assert np.allclose(R["vol@0"], R["vol"], equal_nan=True)


def test_ahead_alignment():
    y = pd.DataFrame({"a": np.arange(10, dtype=float)})
    assert LF.ahead(y, 2)["a"].iloc[3] == 5
    assert LF.ahead(y, (1, 3))["a"].iloc[2] == 3 + 4 + 5
    assert np.isnan(LF.ahead(y, (1, 3))["a"].iloc[7])


def test_bh():
    p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, np.nan])
    assert LF.bh(p, 0.05).tolist() == [True, True, False, False, False, False, False, False, False]
    assert LF.bh(np.array([0.5, 0.9]), 0.1).tolist() == [False, False]


def test_leadlag_scan_finds_a_planted_two_day_delay():
    rng = np.random.default_rng(1)
    days = pd.bdate_range("2008-01-01", periods=2400)
    X = pd.DataFrame({"agri": rng.normal(0, 1, len(days)), "gold": rng.normal(0, 1, len(days))}, index=days)
    Y = pd.DataFrame(rng.normal(0, 1, (len(days), 3)), index=days, columns=["food", "bank", "auto"])
    Y["food"] += 0.3 * X["agri"].shift(2).fillna(0)                        # 粮食涨 → 两天后食品跑赢
    scan = LF.leadlag_scan(X, Y, "2008-01-01")
    D = LF.discoveries(scan, 0.10)
    rep = D[D["replicated"]]
    assert ((rep["factor"] == "agri") & (rep["sector"] == "food") & (rep["lag"] == "2")).any()
    assert len(rep[(rep["factor"] == "gold")]) <= 1                         # 没有关系的因子几乎不出现


def test_choose_lags_uses_training_rows_only():
    rng = np.random.default_rng(0)
    n = 400
    tr = pd.DataFrame({"win": (rng.random(n) < 0.45).astype(float)})
    for k in S.ALL:
        for L in LF.LAGS:
            tr[f"{k}@{L}"] = rng.normal(size=n)
    tr["vol@3"] = tr["win"] * 2 + rng.normal(size=n)                         # 量比：3 天前的值最有用
    tr["tight@5"] = -tr["win"] * 2 + rng.normal(size=n)                      # 箱体幅度（方向 −）：5 天前
    assert LF.choose_lags(tr, S.ALL, "ew")["vol"] == 3 and LF.choose_lags(tr, S.ALL, "ew")["tight"] == 5
    assert LF.choose_lags(tr, S.ALL, "lr")["tight"] == 5
    f = LF.lagged_frame(tr, {"vol": 3})
    assert np.allclose(f["vol"], tr["vol@3"]) and "vol@3" not in f.columns


def test_walk_forward_lagged_trains_only_on_closed_trades():
    rng = np.random.default_rng(3)
    n = 300
    dates = pd.bdate_range("2010-01-01", periods=n, freq="5B")
    T = pd.DataFrame({"sig_date": dates, "exit_date": dates + pd.Timedelta(days=40), "win": (rng.random(n) < 0.45).astype(float),
                      "net": rng.normal(size=n), "pos": np.arange(n) * 5})
    for k in S.ALL:
        T[k] = rng.normal(size=n)
        for L in LF.LAGS:
            T[f"{k}@{L}"] = rng.normal(size=n)
    rows = T.drop(columns=["win", "net", "pos", "exit_date", "sig_date"]).assign(date=dates, ticker="X.T")
    out, models, ch = LF.walk_forward_lagged(rows, T, "ew", S.INDUSTRY, [2012, 2013])
    for y, m in models.items():
        cut = pd.Timestamp(f"{y}-01-01")
        assert len(m.refs[S.INDUSTRY[0]]) == int(((T.sig_date < cut) & (T.exit_date < cut)).sum())
        assert set(ch[y]) == set(S.INDUSTRY)
    assert out.loc[out.date.dt.year == 2013, "score"].notna().all()


def _xy(n=1600, seed=7, delay=12, beta=0.5, after=None):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2006-01-02", periods=n)
    X = pd.DataFrame({"oil": rng.normal(0, 1, n), "gold": rng.normal(0, 1, n)}, index=days)
    Y = pd.DataFrame(rng.normal(0, 1, (n, 2)), index=days, columns=["energy", "bank"])
    eff = beta * X["oil"].shift(delay).fillna(0)
    if after is not None:
        eff[days < after] = 0
    Y["energy"] += eff
    return X, Y


def test_tailwind_fit_picks_a_delayed_lag_and_ignores_unfinished_labels():
    X, Y = _xy()
    m = LF.tailwind_fit(X, Y, len(X))
    assert m["oil"]["L"] in (2, 3, 5) and "energy" in m["oil"]["keep"] and m["oil"]["keep"]["energy"] > 0
    cut = 1200
    X2, Y2 = _xy(after=X.index[cut - 5])                                     # 关系只在切点前 5 天之后才出现
    m2 = LF.tailwind_fit(X2, Y2, cut)
    assert "energy" not in m2["oil"]["keep"]                                 # 训练期（切点 − 20 天之前）看不到
    assert LF.tailwind_fit(X, Y, len(X), fixed_lag=0)["oil"]["L"] == 0


def test_tailwind_score_uses_only_past_factor_values():
    X, Y = _xy()
    m = LF.tailwind_fit(X, Y, 1000)
    a = LF.tailwind_score(m, X, list(Y.columns))
    X2 = X.copy()
    X2.iloc[1300:] *= 5
    b = LF.tailwind_score(m, X2, list(Y.columns))
    assert np.allclose(a.iloc[:1300], b.iloc[:1300])
    fr, info = LF.tailwind_walk_forward(X, Y, [2010, 2011])
    assert fr.loc["2010"].notna().all().all() and fr.loc[:"2009"].isna().all().all() and set(info) == {2010, 2011}
    v = LF.lookup(fr, pd.Series(pd.to_datetime(["2010-06-01", "2010-06-01"])), pd.Series(["X.T", "Y.T"]),
                  {"X.T": "energy", "Y.T": "bank"})
    assert v[0] == pytest.approx(fr.loc["2010-06-01", "energy"]) and v[1] == pytest.approx(fr.loc["2010-06-01", "bank"])
