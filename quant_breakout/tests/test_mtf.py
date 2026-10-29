"""qbreak/mtf.py（日线 → 周 / 月线，只用已完成的 K 线）：完成日（节假日、最后一段不算）、聚合、停牌时的完成日、
状态从完成日起有效、事件只在完成日、截断数据不改变截断日之前的任何值（不偷看）、几个手算得出的特征。"""
import numpy as np
import pandas as pd

from qbreak import mtf


def _ohlcv(idx, close, vol=1000.0):
    c = np.asarray(close, float)
    return pd.DataFrame({"Open": c * 0.995, "High": c * 1.01, "Low": c * 0.985, "Close": c, "Volume": vol}, index=pd.DatetimeIndex(idx))


def test_completion_days_holiday_friday_and_last_period_dropped():
    days = pd.bdate_range("2026-04-27", "2026-05-15").delete([4])             # 5/1（周五）休市
    comp = mtf.completion_days(days, "W")
    assert list(comp) == [pd.Timestamp("2026-04-30"), pd.Timestamp("2026-05-08")]   # 最后一周（5/11〜5/15）后面没有交易日 → 不算
    cm = mtf.completion_days(pd.bdate_range("2026-01-05", "2026-03-10"), "M")
    assert list(cm) == [pd.Timestamp("2026-01-30"), pd.Timestamp("2026-02-27")]


def test_bars_aggregate_and_index_on_market_completion_day():
    days = pd.bdate_range("2026-03-02", "2026-03-20")
    px = np.arange(1.0, len(days) + 1) * 100
    df = _ohlcv(days, px, vol=np.arange(1, len(days) + 1) * 10.0).drop(pd.Timestamp("2026-03-13"))   # 这只票 3/13（周五）停牌
    wb = mtf.bars(df, days, "W")
    assert list(wb.index) == [pd.Timestamp("2026-03-06"), pd.Timestamp("2026-03-13")]              # 第三周是最后一段 → 不出现
    w1 = wb.iloc[0]
    assert w1["Open"] == df["Open"].iloc[0] and w1["Close"] == df["Close"].iloc[4]
    assert w1["High"] == df["High"].iloc[:5].max() and w1["Low"] == df["Low"].iloc[:5].min() and w1["Volume"] == df["Volume"].iloc[:5].sum()
    assert wb.iloc[1]["Close"] == df.loc["2026-03-12", "Close"]                                        # 停牌那天 → 周线收盘 = 周四


def test_state_valid_from_completion_day_and_events_only_that_day():
    feat = pd.DataFrame({"A": [1.0, np.nan, 0.0]}, index=pd.to_datetime(["2026-03-06", "2026-03-13", "2026-03-20"]))
    idx = pd.bdate_range("2026-03-02", "2026-03-24")
    st = mtf.state_on(feat, idx)["A"]
    assert st.loc[:"2026-03-05"].isna().all() and (st.loc["2026-03-06":"2026-03-12"] == 1.0).all()
    assert st.loc["2026-03-13":"2026-03-19"].isna().all() and (st.loc["2026-03-20":] == 0.0).all()
    flag = pd.Series([1.0, 0.0, 1.0], index=feat.index)
    ev = mtf.event_on(flag, idx.delete(idx.get_loc(pd.Timestamp("2026-03-20"))))                     # 3/20 这只票没有 K 线
    assert list(ev[ev].index) == [pd.Timestamp("2026-03-06"), pd.Timestamp("2026-03-23")]            # → 放到之后第一根


def test_truncation_never_changes_earlier_values():
    rng = np.random.default_rng(3)
    days = pd.bdate_range("2019-01-01", "2023-12-29")
    px = 1000 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, len(days))))
    df = _ohlcv(days, px, vol=rng.uniform(5e5, 2e6, len(days)))
    full = mtf.daily_frame(df, days)
    for cut in ("2021-06-16", "2022-03-31", "2023-07-07"):                    # 周三、月末（周四）、周五
        part = mtf.daily_frame(df.loc[:cut], days)                              # 市场日历事先知道；行情只到 cut
        a, b = full.loc[:cut], part.loc[:cut]
        num = [c for c in a.columns if not c.startswith("E_")]
        assert np.allclose(a[num].to_numpy(float), b[num].to_numpy(float), equal_nan=True)
        assert (a[[c for c in a.columns if c.startswith("E_")]] == b[[c for c in b.columns if c.startswith("E_")]]).all().all()
    assert full["W1"].notna().sum() > 800 and full["M1"].notna().sum() > 800 and full["E_X1"].sum() > 10


def test_weekly_features_hand_checked():
    idx = pd.date_range("2020-01-03", periods=60, freq="W-FRI")
    c = np.r_[np.linspace(100, 160, 40), [158, 159, 161, 163, 165, 167, 150, 149], np.linspace(150, 155, 12)]
    wb = _ohlcv(idx, c)
    f = mtf.weekly_features(wb)
    assert np.isnan(f["W1"].iloc[32]) and f["W1"].iloc[33] == 1.0                                    # 30 周均线 + 4 周前 → 第 34 根起
    assert list(np.flatnonzero(f["X6"].eq(1.0))) == [40, 46]                                          # 连涨 ≥ 5 周后第一根下跌周（两次）
    assert f["X1"].iloc[46] == 1.0 and f["X1"].iloc[39] == 0.0                                        # 跌破 10 周均线
    assert f["X5"].iloc[46] == 1.0                                                                    # 收盘 150 < 上一周最低 167×0.985
    wv = wb.assign(Volume=np.r_[np.full(59, 1000.0), 3000.0])
    assert mtf.weekly_features(wv)["W5v"].iloc[-1] == 3.0


def test_monthly_momentum_and_trend():
    idx = pd.date_range("2018-01-31", periods=30, freq="ME")
    c = np.r_[np.linspace(100, 200, 20), np.linspace(190, 150, 10)]
    f = mtf.monthly_features(_ohlcv(idx, c))
    k = 25
    assert np.isclose(f["M2v"].iloc[k], c[k - 1] / c[k - 12] - 1)
    assert f["M1"].iloc[15] == 1.0 and f["M1"].iloc[29] == 0.0 and np.isnan(f["M1"].iloc[8])
    assert np.isnan(f["M3"].iloc[24]) and not np.isnan(f["M3"].iloc[25])
