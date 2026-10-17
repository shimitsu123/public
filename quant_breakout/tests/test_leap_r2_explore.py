"""第 2 轮探索（scripts/leap_r2_explore.py）：月末选股只用当月末为止的分数、拿到下个月末。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leap_r2_explore as X  # noqa: E402


def test_month_end_rows_and_pick_top():
    days = pd.bdate_range("2020-01-01", "2020-03-31")
    rows = X.month_end_rows(days)
    assert [days[r].strftime("%m-%d") for r in rows] == ["01-31", "02-28", "03-31"]
    assert X.pick_top(np.array([1.0, np.nan, 3.0, 2.0]), 2, np.array([True, True, True, False])).tolist() == [2, 0]


def test_sleeve_uses_score_at_month_end_and_next_month_return():
    C = np.array([[100.0, 100.0], [110.0, 90.0], [121.0, 99.0]])
    S = np.array([[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]])
    R = X.sleeve_returns(C, np.array([0, 1, 2]), {"s": S}, 1, np.ones_like(C, bool))
    assert np.allclose(R["s"], [10.0 - X.COST, 10.0 - X.COST]) and np.allclose(R["EW"], [0.0, 10.0])


def test_sleeve_frames_rank_at_month_end_and_drop_losers():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import leap_r2c_sleeve as SL
    idx = pd.bdate_range("2021-01-25", "2021-03-05")
    fr = {t: pd.DataFrame({"entry": False, "dead_cross": False}, index=idx) for t in ("A.T", "B.T", "C.T")}
    sc = {"A.T": np.full(len(idx), 3.0), "B.T": np.full(len(idx), 2.0), "C.T": np.full(len(idx), 1.0)}
    sc["A.T"][idx >= pd.Timestamp("2021-02-01")] = 0.0                               # A 在 2 月跌到最后
    mem = {t: np.ones(len(idx), bool) for t in fr}
    out, prio = SL.sleeve_frames(fr, sc, mem, top=2)
    jan, feb = pd.Timestamp("2021-01-29"), pd.Timestamp("2021-02-26")
    assert out["A.T"].loc[jan, "entry"] and out["B.T"].loc[jan, "entry"] and not out["C.T"].loc[jan, "entry"]
    assert out["A.T"].loc[feb, "dead_cross"] and out["C.T"].loc[feb, "entry"] and not out["B.T"].loc[feb, "dead_cross"]
    assert out["A.T"]["entry"].sum() == 1 and not out["A.T"].loc["2021-02-01":"2021-02-25", "dead_cross"].any()
    assert prio[("B.T", jan)] == 2.0


def test_weekly_ratio_uses_only_finished_weeks():
    import leap_r6_explore as R6
    days = pd.bdate_range("2021-01-04", periods=80)                                  # 周一开始
    V = np.ones((80, 1))
    C = np.ones((80, 1)) * 100.0
    V[60:65] = 5.0                                                                  # 第 13 周放量（周一〜周五）
    C[64] = 110.0
    R, W = R6.weekly_ratio(V, C, days)
    wed = 62                                                                        # 那一周的周三：那一周还没结束 → 仍是上一周的量比
    assert np.isclose(R[wed, 0], 1.0) and np.isclose(R[64, 0], 5.0) and W[64, 0] > 0
    V2 = V.copy()
    V2[70:] = 50.0                                                                  # 之后的放量不改变之前的值
    R2_, _ = R6.weekly_ratio(V2, C, days)
    assert np.allclose(R2_[:70], R[:70], equal_nan=True)


def test_month_picks_rank_members_at_month_end():
    import leap_r6b_sleeve as S6
    idx = pd.bdate_range("2021-01-25", "2021-02-26")
    fr = {t: pd.DataFrame({"entry": False}, index=idx) for t in ("A.T", "B.T", "C.T")}
    sc = {"A.T": np.full(len(idx), 3.0), "B.T": np.full(len(idx), 2.0), "C.T": np.full(len(idx), 5.0)}
    mem = {"A.T": np.ones(len(idx), bool), "B.T": np.ones(len(idx), bool), "C.T": np.zeros(len(idx), bool)}   # C 不是成员
    pk = S6.month_picks(fr, sc, mem, top=1)
    assert pk["A.T"][idx.get_loc(pd.Timestamp("2021-01-29"))] and not pk["C.T"].any() and pk["A.T"].sum() == 2


def test_synth_jpy_uses_previous_us_close_and_morning_fx():
    import leap_r9_explore as R9
    us = pd.DataFrame({"Close": [100.0, 110.0, 121.0]}, index=pd.to_datetime(["2021-01-04", "2021-01-05", "2021-01-06"]))
    fx = pd.Series([100.0, 100.0, 200.0], index=us.index)
    jp = pd.to_datetime(["2021-01-05", "2021-01-06", "2021-01-07"])
    df = R9.synth_jpy(us, fx, pd.DatetimeIndex(jp), base=1000.0)
    # 1/5：前一个美国收盘 100 × 前一日汇率 100；1/6：110 × 100；1/7：121 × 200（当天早上知道的是前一天收盘的汇率）
    assert np.allclose(df["Close"].to_numpy(), [1000.0, 1100.0, 2420.0]) and (df["Volume"] == 1e6).all()


def test_trend_frame_monthly_decision_without_lookahead():
    import leap_r10_explore as R10
    idx = pd.bdate_range("2019-01-01", "2020-12-31")
    c = pd.Series(np.linspace(100, 200, len(idx)), index=idx)
    c[idx >= pd.Timestamp("2020-06-01")] = 50.0                                     # 6 月暴跌
    df = pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 1e6})
    fr = R10.trend_frame(df, months=3)
    assert not fr.loc["2019-02-28", "entry"] and fr.loc["2019-03-29", "entry"] and fr.loc["2019-04-01", "entry"]   # 第 3 个月末起才有 3 个月均线
    assert fr.loc["2020-06-10", "entry"]                                            # 月中暴跌：月末之前不改判定（只在月末看）
    assert fr.loc["2020-06-30", "dead_cross"] and not fr.loc["2020-07-01", "entry"]
    df2 = df.copy()
    df2.loc["2020-09-01":, "Close"] = 1e6                                           # 之后的数据不改变之前的判定
    fr2 = R10.trend_frame(df2, months=3)
    assert (fr2.loc[:"2020-08-31", "entry"] == fr.loc[:"2020-08-31", "entry"]).all()


def test_r10_placebo_keeps_monthly_structure_and_fraction():
    import leap_r10_study as ST
    idx = pd.bdate_range("2010-01-01", "2019-12-31")
    tf = pd.DataFrame({"Close": 1.0, "entry": False, "dead_cross": False}, index=idx)
    out = ST.placebo_frame(tf, 0.3, np.random.default_rng(0))
    me = idx[ST.month_end_flags(idx)]
    held = out["entry"].reindex(me).to_numpy(bool)
    assert 0.15 < held.mean() < 0.45                                               # 大约 30% 的月份拿着
    # 同一个月里（两个月末之间）拿不拿不变；不拿的那个月末有卖出标记
    per_month = out["entry"].groupby(idx.to_period("M")).nunique()
    assert (per_month <= 2).all()
    assert (out["dead_cross"].to_numpy(bool) <= ~out["entry"].to_numpy(bool)).all()
    me2, frac = ST.hold_months(out, "2012-01-01", "2013-12-31")
    assert len(me2) == 24 and 0.0 <= frac <= 1.0
