"""买点质量分（qbreak/signal_score.py）：因子不用未来数据、行业因子不含自己、百分位变换、配比方式、滚动前推只用已平仓的交易、
就绪度向量化版与 scan.py 一致。"""
import numpy as np
import pandas as pd
import pytest

from qbreak import signal_score as S
from qbreak.config import StrategyParams
from qbreak.scan import scan
from qbreak.strategy import compute_indicators

P = StrategyParams(range_x_pct=40.0, vol_mult=1.0)               # 放宽条件，多出一些信号
SECTOR = {"A1.T": "a", "A2.T": "a", "A3.T": "a", "B1.T": "b", "B2.T": "b", "C1.T": "c"}


def _raw(n=700, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2016-01-01", periods=n)
    out = {}
    for k, t in enumerate(SECTOR):
        c = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
        o = c * (1 + rng.normal(0, 0.004, n))
        out[t] = pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.01, "Low": np.minimum(o, c) * 0.99, "Close": c,
                               "Volume": rng.integers(50_000, 400_000, n).astype(float)}, index=days)
    idx = pd.Series(30000 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n))), index=days)
    return out, idx


def _panel(raw, idx):
    ind = {t: compute_indicators(df, P) for t, df in raw.items()}
    return ind, S.feature_panel(ind, idx, SECTOR)


def test_features_do_not_use_future_prices():
    raw, idx = _raw()
    ind, pa = _panel(raw, idx)
    t = 600
    raw2 = {k: v.copy() for k, v in raw.items()}
    for v in raw2.values():
        v.iloc[t + 1:, :4] *= 1.7
        v.iloc[t + 1:, 4] *= 3
    idx2 = idx.copy()
    idx2.iloc[t + 1:] *= 0.6
    _, pb = _panel(raw2, idx2)
    for k in S.ALL:
        a, b = pa[k].iloc[:t + 1], pb[k].iloc[:t + 1]
        assert np.allclose(a.to_numpy(float), b.to_numpy(float), equal_nan=True), k
        assert a.iloc[300:].notna().to_numpy().any(), k                     # 预热之后有值


def test_industry_factors_exclude_the_stock_itself_and_need_two_others():
    days = pd.bdate_range("2020-01-01", periods=130)
    base = np.linspace(100, 110, 130)
    closes = pd.DataFrame({t: base for t in SECTOR}, index=days)
    closes["A1.T"] = np.linspace(100, 200, 130)                            # 只有 A1 大涨
    ent = pd.DataFrame(False, index=days, columns=closes.columns)
    ent.loc[days[-3], "A2.T"] = True
    f = S.industry_panel(closes, ent, SECTOR)
    last = days[-1]
    r60 = closes.iloc[-1] / closes.iloc[-61] - 1
    univ = r60.mean()
    assert f["ind_mom60"].loc[last, "A1.T"] == pytest.approx(r60["A2.T"] - univ)          # A1 的行业 = A2、A3（不含自己）
    assert f["ind_mom60"].loc[last, "A2.T"] == pytest.approx((r60["A1.T"] + r60["A3.T"]) / 2 - univ)
    assert f["rel_ind60"].loc[last, "A1.T"] == pytest.approx(r60["A1.T"] - r60["A2.T"])
    assert np.isnan(f["ind_mom60"].loc[last, "B1.T"]) and np.isnan(f["ind_mom60"].loc[last, "C1.T"])   # 其他成员 < 2
    assert f["ind_cobreak"].loc[last, "A1.T"] == pytest.approx(0.5)        # A2 在 10 日内出过信号（A2、A3 里 1 个）
    assert f["ind_cobreak"].loc[last, "A2.T"] == pytest.approx(0.0)        # 自己的信号不算
    assert f["ind_breadth"].loc[last, "A3.T"] == pytest.approx(1.0)


def test_pct_x_ties_and_missing():
    ref = np.array([1.0, 2.0, 2.0, 3.0, np.nan])
    x = S.pct_x(np.array([0.0, 2.0, 5.0, np.nan]), ref)
    assert x.tolist() == [-0.5, 0.0, 0.5, 0.0]
    assert S.pct_x(np.array([1.0]), np.array([np.nan])).tolist() == [0.0]


def _train(n=240, seed=3):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, len(S.ALL))), columns=S.ALL)
    z = 1.5 * X["vol"] - 1.5 * X["tight"]
    X["win"] = (z + rng.normal(0, 1, n) > 0).astype(float)
    X["net"] = z + rng.normal(0, 1, n)
    X["pos"] = np.arange(n) * 5
    return X


def test_fit_kinds():
    tr = _train()
    ew = S.fit("ew", S.ALL, tr)
    assert np.allclose(ew.w, [S.SIGN[c] / len(S.ALL) for c in S.ALL])
    assert np.mean(ew.score(tr) < ew.thr) == pytest.approx(1 / 3, abs=0.01)
    lr = S.fit("lr", S.ALL, tr)
    j, k = S.ALL.index("vol"), S.ALL.index("tight")
    assert lr.w[j] > 0 > lr.w[k] and np.isfinite(lr.w).all() and "lam" in lr.info
    ic = S.fit("ic", S.ALL, tr)
    assert ic.w[j] > 0.3 and ic.w[k] < -0.3
    sub = S.fit("ew", S.INDUSTRY, tr)
    assert sub.X(tr).shape == (len(tr), len(S.INDUSTRY))


def test_walk_forward_trains_only_on_trades_closed_before_the_year():
    tr = _train(300)
    dates = pd.bdate_range("2010-01-01", periods=300, freq="5B")
    tr["sig_date"], tr["exit_date"] = dates, dates + pd.Timedelta(days=40)
    rows = tr[S.ALL].assign(date=dates, ticker="X.T")
    out, models = S.walk_forward(rows, tr, "ew", S.ALL, [2012, 2013])
    for y, m in models.items():
        cut = pd.Timestamp(f"{y}-01-01")
        assert len(m.refs["vol"]) == int(((tr.sig_date < cut) & (tr.exit_date < cut)).sum())
    assert out.loc[out.date < pd.Timestamp("2012-01-01"), "score"].isna().all()
    assert out.loc[out.date.dt.year == 2013, "score"].notna().all()


def test_readiness_components_match_scan():
    raw, idx = _raw(seed=7)
    ind = {t: compute_indicators(df, P) for t, df in raw.items()}
    sc = scan(ind, P, "JP", budget=1e12, top=100).set_index("ticker")
    for t, df in ind.items():
        v = float(S.readiness_score(S.readiness_components(df, P)).iloc[-1])
        assert round(v, 1) == pytest.approx(sc.loc[t, "score"]), t
