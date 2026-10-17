"""scripts/ml_study.py：每周样本日、卖出价（退市按最后收盘）、走动训练的划分不偷看、空头合计快速版 = 原算法、
予想利润只用开示日之前的、滚动 β、截面排名只在成员里、每周前 k 名、门槛、出场模型在下一交易日开盘卖。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ml_study as MS                                                        # noqa: E402
from qbreak import jq_data as JD                                             # noqa: E402


def test_week_ends_last_trading_day_of_each_iso_week():
    days = pd.bdate_range("2021-12-27", "2022-01-14").delete(4)              # 12-31（周五）休市
    wk = MS.week_ends(days, "2021-12-27")
    assert list(wk) == [pd.Timestamp("2021-12-30"), pd.Timestamp("2022-01-07"), pd.Timestamp("2022-01-14")]


def test_fwd_exit_price_uses_last_close_when_no_bar():
    o = np.array([100.0, np.nan])
    cf = np.array([99.0, 95.0])
    assert MS.fwd_exit_price(o, cf).tolist() == [100.0, 95.0]


def test_fold_split_purges_and_windows():
    days = pd.bdate_range("2018-01-01", "2020-12-31")
    t_idx = np.arange(len(days))
    end = t_idx + 21
    dates = days[t_idx]
    rf, nx = pd.Timestamp("2019-12-31"), pd.Timestamp("2020-12-31")
    tr, fi, vi, te = MS.fold_split(t_idx, end, dates, rf, nx, days)
    r = int(days.searchsorted(rf, side="right")) - 1
    assert (end[tr] <= r).all() and not tr[(end > r)].any()                     # 训练 = 结果完全揭晓
    assert (dates[te] > rf).all() and (dates[te] <= nx).all() and te.sum() == ((dates > rf) & (dates <= nx)).sum()
    assert not (te & tr).any() and (dates[vi] > rf - pd.Timedelta(days=365)).all() and (vi <= tr).all()
    assert (end[fi] <= int(days.searchsorted(rf - pd.Timedelta(days=365), side="right")) - 1).all()


def test_short_sum_fast_equals_original():
    rng = np.random.default_rng(1)
    base = pd.Timestamp("2020-01-01")
    R = pd.DataFrame({"DiscDate": [(base + pd.Timedelta(days=int(x))).strftime("%Y-%m-%d") for x in rng.integers(0, 700, 60)],
                      "SSName": rng.choice(["A", "B", "C", "D"], 60),
                      "ShrtPosToSO": np.round(rng.uniform(0.003, 0.02, 60), 4).astype(str)})
    dates = pd.date_range("2020-01-10", "2022-03-01", freq="7D")
    ref = JD.short_features(R, dates)["s1"].to_numpy()
    assert np.allclose(MS.short_sum_fast(R, dates), ref)
    assert (MS.short_sum_fast(pd.DataFrame(columns=["DiscDate", "SSName", "ShrtPosToSO"]), dates) == 0).all()


def test_latest_forecast_only_before_the_day_and_not_stale():
    ev = pd.DataFrame({"date": pd.to_datetime(["2020-02-10", "2020-05-10", "2020-08-10"]), "fy": "x",
                       "fc": [100.0, np.nan, 120.0], "rev": np.nan, "yoy": np.nan})
    d = pd.to_datetime(["2020-02-10", "2020-02-11", "2020-06-01", "2020-08-11", "2021-06-01"])
    out = MS.latest_forecast(ev, d)
    assert np.isnan(out[0]) and out[1] == 100.0 and out[2] == 100.0 and out[3] == 120.0 and np.isnan(out[4])   # 当天开示的不用；超过 200 天 → 缺值


def test_rolling_beta_recovers_slope():
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2020-01-01", periods=400)
    f = pd.Series(rng.normal(0, 0.01, 400), index=idx)
    R = pd.DataFrame({"a": 2.0 * f + rng.normal(0, 0.001, 400), "b": -0.5 * f + rng.normal(0, 0.001, 400)}, index=idx)
    R.iloc[:50, 1] = np.nan
    b = MS.rolling_beta(R, f, win=250, min_n=200)
    assert b["a"].iloc[:199].isna().all() and abs(b["a"].iloc[-1] - 2.0) < 0.05 and abs(b["b"].iloc[-1] + 0.5) < 0.05
    assert b["b"].iloc[:249].isna().all()                                    # b 前 50 天缺 → 满 200 个有效日才有值


def test_cs_rank_only_members():
    idx = pd.bdate_range("2020-01-01", periods=2)
    W = pd.DataFrame({"a": [1.0, 3.0], "b": [2.0, 2.0], "c": [3.0, 1.0]}, index=idx)
    mem = pd.DataFrame({"a": [True, True], "b": [True, False], "c": [True, True]}, index=idx)
    r = MS.cs_rank(W, mem)
    assert np.allclose(r.iloc[0].to_numpy(), [-1 / 3, 0.0, 1 / 3]) and np.isnan(r.iloc[1]["b"])
    assert np.allclose(r.iloc[1][["a", "c"]].to_numpy(), [0.25, -0.25])


def test_top_k_entries():
    S = pd.DataFrame({"a": [3.0, np.nan], "b": [2.0, 1.0], "c": [1.0, 2.0]})
    E = MS.top_k_entries(S, 2)
    assert E.to_numpy().tolist() == [[True, True, False], [False, True, True]]


def _st(va=None, ho=None, h1=None, h2=None, dd=-20.0):
    f = lambda c: {"cagr": 10.0, "dd": dd, "calmar": c}                   # noqa: E731
    return {"all": f(0.5), "va": f(va), "ho": f(ho), "h1": f(h1), "h2": f(h2)}


def test_gates_and_choice():
    cur = _st(va=0.40, ho=0.50, h1=0.40, h2=0.60)
    good = _st(va=0.41, ho=0.56, h1=0.46, h2=0.66)
    assert MS.v_fails(good, cur) == [] and MS.h_fails(good, cur) == []
    assert MS.v_fails(_st(va=0.40), cur) and any("前半" in x for x in MS.h_fails(_st(va=0.5, ho=0.6, h1=0.44, h2=0.7), cur))
    assert any("回撤" in x for x in MS.h_fails({**good, "ho": {"cagr": 9, "dd": -20.1, "calmar": 0.9}}, cur))
    assert MS.choose({"K4": _st(va=0.6), "K2": _st(va=0.6), "K1": _st(va=0.5)}) == "K2"
    assert MS.VAL[1] == MS.HOLD[0] == MS.H1[0] and MS.H1[1] == MS.H2[0]


def _bars(dates, px, entry_on=()):
    idx = pd.DatetimeIndex(dates)
    df = pd.DataFrame({"Open": px, "High": np.array(px) * 1.01, "Low": np.array(px) * 0.99, "Close": px, "Volume": 1e6}, index=idx)
    df["entry"] = df.index.isin(pd.DatetimeIndex(entry_on))
    df["dead_cross"], df["climax"] = False, False
    df["atr"] = np.array(px) * 0.02
    return df


def test_ml_engine_exit_overlay_sells_next_open():
    from qbreak.config import ExecConfig, StrategyParams
    from qbreak.unified import UnifiedConfig
    P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0, stop_loss_pct=50.0)
    EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
    D = pd.bdate_range("2026-01-05", periods=8)
    FX = pd.DataFrame({"Open": 150.0, "Close": 150.0}, index=D)
    ind = {"1111.T": _bars(D, [1000.0] * 8, entry_on=[D[1]])}                # D2 买入
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), core={}, core_index={})
    old = MS.MLEngine.EXIT
    MS.MLEngine.EXIT = {"1111.T": {D[4]}}                                    # D4 收盘出场模型触发 → D5 开盘卖
    try:
        ue = MS.MLEngine(ind, cfg, {"JP": P, "US": P}, EX, {}, fx=FX)
        ue.run()
    finally:
        MS.MLEngine.EXIT = old
    tr = {t["ticker"]: t for t in ue.st.trades}
    assert tr["1111.T"]["entry_date"] == str(D[2].date()) and tr["1111.T"]["exit_date"] == str(D[5].date())
    assert tr["1111.T"]["reason"] == "ml_exit"
