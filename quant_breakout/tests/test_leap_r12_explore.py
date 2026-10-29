"""第 12 轮探索（scripts/leap_r12_explore.py）：同月季节分只用过去年份的同一个月；个股层资金占用的算法。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leap_r12_explore as X  # noqa: E402


def test_month_end_close_and_excess():
    idx = pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-27", "2020-02-28", "2020-03-31"])
    c = pd.DataFrame({"A": [1.0, 2.0, 3.0, np.nan, 3.0], "B": [1.0, 1.0, 1.0, 1.1, 50.0]}, index=idx)
    me = X.month_end_close(c)
    assert me["A"].tolist() == [2.0, 3.0, 3.0] and me["B"].tolist() == [1.0, 1.1, 50.0]      # 月末没值 → 那个月最后一个有值的
    r, x = X.monthly_excess(me)
    assert np.isclose(r.iloc[1]["A"], 0.5) and np.isnan(r.iloc[2]["B"])                     # +4445% 当数据错误
    assert np.isclose(x.iloc[1].sum(), 0.0) and np.isclose(x.iloc[2]["A"], 0.0)


def test_seasonal_score_uses_only_same_month_of_past_years():
    per = pd.period_range("2000-01", "2004-12", freq="M")
    v = np.zeros(len(per))
    v[per.month == 3] = 1.0                                                       # 每年 3 月 +1
    v[per == pd.Period("2004-03")] = 100.0                                       # 目标月本身的值不能进分数
    Xd = pd.DataFrame({"A": v}, index=per)
    s = X.seasonal_score(Xd, k=10, min_n=3)
    assert np.isnan(s.loc[pd.Period("2002-03"), "A"])                            # 过去只有 2 年 < 3
    assert s.loc[pd.Period("2003-03"), "A"] == 1.0 and s.loc[pd.Period("2004-03"), "A"] == 1.0
    assert s.loc[pd.Period("2004-04"), "A"] == 0.0
    assert X.seasonal_score(Xd, k=1, min_n=1).loc[pd.Period("2001-03"), "A"] == 1.0
    v[per == pd.Period("2004-03")] = 1.0
    o = X.seasonal_score(pd.DataFrame({"A": v}, index=per), k=10, min_n=3, other=True)
    assert np.isclose(o.loc[pd.Period("2004-03"), "A"], 1.0)                     # 其他月里没有 3 月 → 平均 0
    assert np.isclose(o.loc[pd.Period("2004-04"), "A"], -5 / 47)                 # 4 月：同月 0 − 其他月（47 个月里 5 个 3 月，含上个月）


def test_rank_buckets_top_bottom():
    s = pd.Series(np.arange(20, dtype=float), index=[f"T{i}" for i in range(20)])
    x = pd.Series(np.arange(20, dtype=float) / 100, index=s.index)
    r = X.rank_buckets(s, x)
    assert np.isclose(r["top4"], np.mean([0.19, 0.18, 0.17, 0.16])) and np.isclose(r["bot10"], 0.045)
    assert np.isclose(r["q5"], np.mean([0.19, 0.18, 0.17, 0.16])) and np.isclose(r["ic"], 1.0)
    assert X.rank_buckets(s.iloc[:5], x.iloc[:5]) is None


def test_utilization_counts_stock_positions_only():
    hist = [["2020-01-06", 100.0], ["2020-01-07", 100.0], ["2020-01-08", 100.0], ["2020-01-09", 100.0]]
    tr = pd.DataFrame({"ticker": ["A.T", "1655.T"], "entry_date": ["2020-01-07", "2020-01-06"], "exit_date": ["2020-01-09", "2020-01-09"],
                       "shares": [1, 100], "entry_px": [50.0, 1.0]})
    assert np.isclose(X.utilization(tr, hist, "2020-01-06", None), 0.25)          # 4 天里有 2 天 50%
    assert np.isclose(X.utilization(tr, hist, "2020-01-08", "2020-01-09"), 0.5)
