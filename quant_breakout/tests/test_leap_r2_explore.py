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
