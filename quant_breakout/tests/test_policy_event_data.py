"""scripts/policy_event_data.py：反应日规则、窗口收益、等权业种、打乱日期对照、汇总。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import policy_event_data as PE  # noqa: E402

DAYS = pd.bdate_range("2024-10-01", "2025-03-31")


def test_reaction_days_rules():
    E = pd.DataFrame({"date": pd.to_datetime(["2024-10-31", "2024-10-31", "2024-11-06", "2024-11-06", "2024-11-09", "2024-12-19"]),
                      "time_jst": ["12:30", "15:10", "15:10", "15:35", "", ""]})
    r = PE.reaction_days(E, DAYS)
    assert list(r.strftime("%Y-%m-%d")) == ["2024-10-31", "2024-11-01", "2024-11-06", "2024-11-07", "2024-11-11", "2024-12-20"]
    # 15:10：2024-11-05 前 = 盘后 → 次日；之后 = 盘中 → 当天；周六 → 下周一；缺时刻 → 当盘后


def test_window_returns_and_reactions():
    idx = DAYS[:10]
    c = pd.Series([100, 100, 110, 121, 121, 121, 121, 121, 121, 121], index=idx, dtype=float)
    inc, post = PE.window_returns(c, idx[2], 1)
    assert np.isclose(inc, 21.0) and np.isclose(post, 10.0)                    # r−1 → r+1：100 → 121；r → r+1：110 → 121
    assert np.isnan(PE.window_returns(c, idx[0], 1)[0]) and np.isnan(PE.window_returns(c, idx[9], 1)[0])
    S = pd.DataFrame({"a": c, "b": c * 0 + 100})
    R = PE.reactions(pd.DataFrame({"x": [1]}), pd.DatetimeIndex([idx[2]]), S, c, horizons=(1,))
    assert len(R) == 2 and np.isclose(R.loc[R["series"] == "a", "ex_post"].iloc[0], 0.0) and np.isclose(R.loc[R["series"] == "b", "ex_post"].iloc[0], -10.0)
    summ = PE.summarize(R)
    assert set(summ["series"]) == {"a", "b"} and summ.loc[summ["series"] == "b", "hit"].iloc[0] == 0.0


def test_equal_weight_returns_and_mask():
    idx = DAYS[:3]
    rets = pd.DataFrame({"1.T": [1.0, 2.0, np.nan], "2.T": [3.0, 4.0, 5.0], "3.T": [5.0, 6.0, 7.0], "4.T": [9.0, 9.0, 9.0]}, index=idx)
    groups = {"1.T": "A", "2.T": "A", "3.T": "A", "4.T": "B"}
    ew = PE.equal_weight_returns(rets, groups, min_n=2)
    assert np.isclose(ew.loc[idx[0], "A"], 3.0) and np.isclose(ew.loc[idx[2], "A"], 6.0) and ew["B"].isna().all()   # B 只有 1 只 → 不够
    mask = pd.DataFrame(True, index=idx, columns=rets.columns); mask.loc[idx[0], "3.T"] = False
    ew2 = PE.equal_weight_returns(rets, groups, mask, min_n=2)
    assert np.isclose(ew2.loc[idx[0], "A"], 2.0)


def test_shuffle_dates_same_year_and_gap():
    r = pd.DatetimeIndex(["2024-10-15", "2025-02-03", pd.NaT])
    s = PE.shuffle_dates(r, DAYS, 0)
    assert s[0].year == 2024 and s[1].year == 2025 and pd.isna(s[2])
    assert abs(DAYS.get_loc(s[0]) - DAYS.get_loc(r[0])) >= 5
    assert list(PE.shuffle_dates(r, DAYS, 0)) == list(s)                       # 种子可复现
    cum = PE.cum_from_returns(pd.DataFrame({"a": [1.0, np.nan, -1.0]}, index=DAYS[:3]))
    assert np.isclose(cum["a"].iloc[-1], 100 * 1.01 * 0.99)


def test_sector33_all_pit_uses_strictly_earlier_snapshot():
    idx = DAYS[:6]
    n = len(idx)
    C = np.ones((n, 2)); C[:, 0] = np.cumprod([1, 1.01, 1.01, 1.01, 1.01, 1.01]); C[:, 1] = np.cumprod([1, 1.03, 1.03, 1.03, 1.03, 1.03])
    A = {"days": idx, "names": ["1000.T", "2000.T"], "C": C, "listed": np.ones((n, 2), bool)}
    snaps = {pd.Timestamp(idx[0]): pd.DataFrame({"Code": ["10000", "20000"], "S33Nm": ["A", "A"]}),
             pd.Timestamp(idx[3]): pd.DataFrame({"Code": ["10000", "20000"], "S33Nm": ["A", "B"]})}
    ew = PE.sector33_all_pit(A, snaps, min_n=1)
    assert np.isclose(ew.loc[idx[2], "A"], 2.0) and np.isnan(ew.loc[idx[2]].get("B", np.nan))    # 第二份快照之前：两只都在 A（等权 (1+3)/2）
    assert np.isclose(ew.loc[idx[4], "A"], 1.0) and np.isclose(ew.loc[idx[4], "B"], 3.0)          # 严格早于那天的快照 → 2.T 归 B
    assert np.isnan(ew.loc[idx[3]].get("B", np.nan))                                             # 快照当天还用旧分类
