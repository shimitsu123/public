"""scripts/allstock_study.py、allstock_data.py 与 candle_portfolio.MixEngine.PRIORITY：训练用的股票 = 月末上市一览里一般市场的内国普通股（用严格早于那天的快照）、
特征只用当天为止（含市场的两个）、按年滚动训练只用卖出日在那年之前的交易、模型按信号日的年份选、预测 → 过滤（> 0 保留、没有预测 = 保留）、
同一天的新仓候选按分数高的先。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import allstock_data as AD                                                   # noqa: E402
import allstock_study as S                                                   # noqa: E402
import candle_portfolio as CP                                                # noqa: E402

from qbreak.calendar_jp import is_trading_day                               # noqa: E402
from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402


def _tse_days(start: str, end: str) -> pd.DatetimeIndex:
    d = pd.bdate_range(start, end)
    return pd.DatetimeIndex([x for x in d if is_trading_day(x.date())])


def _ohlcv(days: pd.DatetimeIndex, seed: int = 5) -> pd.DataFrame:
    r = np.random.default_rng(seed)
    n = len(days)
    c = 1000 * np.exp(np.cumsum(r.normal(0, 0.015, n)))
    o = c * (1 + r.normal(0, 0.004, n))
    h = np.maximum(o, c) * (1 + np.abs(r.normal(0, 0.006, n)))
    l = np.minimum(o, c) * (1 - np.abs(r.normal(0, 0.006, n)))
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": r.lognormal(13, 0.5, n)}, index=days)


def test_features_use_only_data_up_to_the_day():
    days = _tse_days("2023-01-04", "2024-12-27")
    df = _ohlcv(days)
    n225 = _ohlcv(_tse_days("2022-01-04", "2024-12-27"), seed=9)["Close"]
    full = S.stock_features(df, S.market_frame(n225))
    assert list(full.columns) == S.FEATS
    assert full.iloc[300:].notna().all().all()                               # 预热之后 18 个都有值
    for d in (days[260], days[301], days[355], days[-2]):                    # 截到那天（个股与日経225 都截）→ 那天的特征不变
        part = S.stock_features(df.loc[:d], S.market_frame(n225.loc[:d]))
        a, b = part.iloc[-1].to_numpy(float), full.loc[d].to_numpy(float)
        assert np.allclose(a, b, equal_nan=True), (d, dict(zip(S.FEATS, a - b)))


def test_features_match_w2_definition():
    days = _tse_days("2023-01-04", "2024-12-27")
    df = _ohlcv(days, seed=7)
    from qbreak import mtf
    f = S.stock_features(df, S.market_frame(df["Close"]))
    w = mtf.weekly_volume_ratio(df, mtf.live_calendar(df.index))
    assert np.allclose(f["w5v"].to_numpy(), w.to_numpy(), equal_nan=True)


def _train_table() -> pd.DataFrame:
    r = np.random.default_rng(1)
    n = 3000
    sig = pd.to_datetime("2016-10-03") + pd.to_timedelta(r.integers(0, 365 * 5, n), unit="D")
    ex = sig + pd.to_timedelta(r.integers(5, 120, n), unit="D")
    X = r.normal(0, 1, (n, len(S.FEATS)))
    t = pd.DataFrame(X, columns=S.FEATS)
    t["ticker"], t["sig_date"], t["exit_date"], t["net"] = "A", sig, ex, r.normal(0, 5, n)
    return t


def test_walk_forward_trains_only_on_trades_closed_before_the_year(monkeypatch):
    tr = _train_table()
    seen = {}

    def rec(X, y):
        seen[len(seen)] = (X.copy(), y.copy())
        return "m"
    monkeypatch.setattr(S, "fit_gbm", rec)
    ms = S.walk_forward(tr, [2019, 2020], "gbm")
    assert set(ms) == {2019, 2020}
    for k, y in enumerate([2019, 2020]):
        want = tr[tr["exit_date"] < pd.Timestamp(y, 1, 1)]
        X, lab = seen[k]
        assert len(lab) == len(want) and np.allclose(lab, want["net"].to_numpy())
        assert np.allclose(X, want[S.FEATS].to_numpy())
    straddle = tr[(tr["sig_date"] < "2019-01-01") & (tr["exit_date"] >= "2019-01-01")]
    assert len(straddle) and len(seen[0][1]) < (tr["sig_date"] < "2019-01-01").sum()   # 跨年的交易（信号在前、卖出在后）不进 2019 的训练


def test_models_fit_and_ridge_handles_missing():
    tr = _train_table()
    tr.loc[::7, "w5v"] = np.nan
    X, y = tr[S.FEATS].to_numpy(float), tr["net"].to_numpy(float)
    for m in (S.fit_gbm(X, y), S.RidgeModel().fit(X, y)):
        p = m.predict(X)
        assert p.shape == (len(tr),) and np.isfinite(p).all() and np.abs(p).max() <= S.CLIP + 1e-9


class _Const:
    def __init__(self, v):
        self.v = v

    def predict(self, X):
        return np.full(len(X), self.v)


def test_predict_frames_picks_model_by_signal_year_and_keep_rule():
    d = pd.DatetimeIndex(["2018-12-27", "2019-03-01", "2020-06-01", "2021-02-01"])
    feats = {"1111.T": pd.DataFrame(0.0, index=d, columns=S.FEATS)}
    models = {2019: _Const(1.5), 2020: _Const(-0.5)}
    pred = S.predict_frames(feats, lambda y: models.get(y))
    assert pred == {("1111.T", d[1]): 1.5, ("1111.T", d[2]): -0.5}            # 2018、2021 没有模型 → 不预测
    fr = {"1111.T": pd.DataFrame({"entry": True}, index=d)}
    keep = S.keep_by_pred(fr, pred)["1111.T"]
    assert keep.tolist() == [True, True, False, True]                          # 没有预测 = 保留；> 0 保留；≤ 0 去掉


def test_training_table_joins_signal_day_features():
    d = pd.bdate_range("2020-01-06", periods=5)
    f = pd.DataFrame(np.arange(5 * len(S.FEATS), dtype=float).reshape(5, -1), index=d, columns=S.FEATS)
    T = pd.DataFrame({"ticker": ["1111.T", "1111.T", "9999.T"], "sig_date": [d[1], d[3], d[2]],
                      "exit_date": [d[2], d[4], d[4]], "net": [1.0, -2.0, 3.0]})
    tt = S.training_table(T, {"1111.T": f})
    assert len(tt) == 2 and tt["net"].tolist() == [1.0, -2.0]                   # 没有特征的票不进
    assert np.allclose(tt[S.FEATS].to_numpy(), f.loc[[d[1], d[3]]].to_numpy())


D16 = pd.bdate_range("2026-01-05", periods=16)
EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0, stop_loss_pct=50.0)


def _bars(entry_on=()):
    px = np.full(16, 1000.0)
    df = pd.DataFrame({"Open": px, "High": px * 1.01, "Low": px * 0.99, "Close": px, "Volume": 1e6}, index=D16)
    df["entry"] = df.index.isin(pd.DatetimeIndex(entry_on))
    df["dead_cross"], df["climax"], df["atr"] = False, False, px * 0.02
    return df


def test_priority_hook_orders_same_day_candidates():
    ind = {"1111.T": _bars([D16[1]]), "2222.T": _bars([D16[1]])}
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=1, stock_markets=("JP",), core={}, core_index={})

    def bought(pr):
        old = CP.MixEngine.PRIORITY
        CP.MixEngine.PRIORITY = pr
        try:
            ue = CP.MixEngine(ind, cfg, {"JP": P, "US": P}, EX, {})
            ue.run()
        finally:
            CP.MixEngine.PRIORITY = old
        return {t["ticker"] for t in ue.st.trades} | set(ue.st.pos)
    assert bought({}) == {"1111.T"}                                            # 没给分数：按代码
    assert bought({("2222.T", D16[1]): 0.9, ("1111.T", D16[1]): 0.1}) == {"2222.T"}
    assert bought({("2222.T", D16[1]): 0.9, ("1111.T", D16[2]): 5.0}) == {"2222.T"}   # 分数按信号日取（别的日子的分数不算）
    assert CP.MixEngine.PRIORITY == {}


def test_training_universe_uses_strictly_earlier_month_end_list():
    m1 = pd.DataFrame({"Code": ["11110", "22220", "33330", "44440", "55550"], "Mkt": ["0111", "0105", "0113", "0109", "0112"],
                       "ProdCat": ["011", "011", "011", "011", "014"]})
    assert AD.eligible(m1) == {"11110", "33330"}                              # TOKYO PRO MARKET、その他、非内国普通股（ETF 等）不算
    m2 = pd.DataFrame({"Code": ["33330", "66660"], "Mkt": ["0112", "0101"], "ProdCat": ["011", "011"]})
    days = pd.DatetimeIndex(pd.bdate_range("2020-01-27", "2020-03-06"))
    s1, s2 = pd.Timestamp("2020-01-31"), pd.Timestamp("2020-02-28")
    names = ["1111.T", "3333.T", "6666.T", "2222.T"]
    L = AD.listed_mask(days, names, {s1: m1, s2: m2})
    on = lambda t, d: bool(L[days.get_loc(pd.Timestamp(d)), names.index(t)])   # noqa: E731
    assert not on("1111.T", "2020-01-31") and on("1111.T", "2020-02-03")      # 月末当天还用之前的（没有 → 否），第二天起用新一览
    assert on("1111.T", "2020-02-28") and not on("1111.T", "2020-03-02")      # 下一个一览里没有了 → 之后不算
    assert on("3333.T", "2020-02-03") and on("3333.T", "2020-03-06")          # 两个一览都有；最后一个一览用到数据末尾
    assert not on("6666.T", "2020-02-28") and on("6666.T", "2020-03-02")
    assert not L[:, names.index("2222.T")].any()
