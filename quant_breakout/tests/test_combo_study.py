"""各层怎么搭配（scripts/combo_study.py；2026-09-26 事先登记）：离翻转价位的距离、状态 → 下一交易日成交的系数不看未来、
量比优先的分数、分组统计、判定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import combo_study as CB                                                      # noqa: E402


def test_flip_distance_bull_and_bear():
    idx = pd.bdate_range("2020-01-01", periods=300)
    c = pd.Series(100.0, index=idx)
    c.iloc[-1] = 110.0
    bear = pd.Series(False, index=idx)
    d = CB.flip_distance(c, bear)
    ma = c.rolling(250).mean().iloc[-1]
    assert d.iloc[-1] == pytest.approx((110 / (ma * 0.97) - 1) * 100) and np.isnan(d.iloc[100])
    bear.iloc[-1] = True
    assert CB.flip_distance(c, bear).iloc[-1] == pytest.approx((110 / (ma * 1.03) - 1) * 100)


def test_fill_scale_uses_previous_signal_day_only():
    g = pd.bdate_range("2024-01-01", periods=6)
    f = pd.Series([1.0, 0.5, 1.0, 1.0, 0.5, 1.0], index=g)
    s = CB.fill_scale(f, g)
    assert s.tolist() == [1.0, 1.0, 0.5, 1.0, 1.0, 0.5]                      # 第 i 天成交用第 i−1 天收盘时的状态
    us = pd.Series([0.5], index=[g[2] + pd.Timedelta(hours=0)])              # 只有一天有值 → 之后向前填
    assert CB.fill_scale(us, g).tolist() == [1.0, 1.0, 1.0, 0.5, 0.5, 0.5]


def test_vol_prio_only_signal_days():
    idx = pd.bdate_range("2024-01-01", periods=4)
    df = pd.DataFrame({"entry": [False, True, False, True], "vol_ratio": [9.0, 2.5, 9.0, np.nan]}, index=idx)
    assert CB.vol_prio({"7203.T": df}) == {("7203.T", idx[1]): 2.5}


def test_bucket_table_and_decide():
    T = pd.DataFrame({"sig_date": pd.to_datetime(["2010-01-05", "2012-01-05", "2018-01-05", "2019-01-05"]),
                      "x": [1.0, 7.0, 1.0, 12.0], "win": [1.0, 0.0, 1.0, 1.0], "net": [2.0, -1.0, 3.0, 1.0]})
    rows = CB.bucket_table(T, "x", [-1e9, 5, 1e9], ["低", "高"])
    assert rows[0] == {"group": "低", "n1": 1, "win1": 100.0, "exp1": 2.0, "n2": 1, "win2": 100.0, "exp2": 3.0}
    assert rows[1]["n1"] == 1 and rows[1]["win1"] == 0.0 and rows[1]["n2"] == 1

    def r(a, h1, h2, w5, dd):
        return {"all": {"calmar": a, "dd": dd}, "h1": {"calmar": h1}, "h2": {"calmar": h2}, "w5": {"calmar": w5}}
    base = r(0.36, 0.30, 0.50, 1.0, -35.0)
    R = {"C1": r(0.42, 0.31, 0.52, 1.1, -34.0), "C2": r(0.44, 0.29, 0.60, 1.2, -30.0), "C3": r(0.40, 0.35, 0.55, 1.0, -36.0),
         "C4": r(0.45, 0.35, 0.55, 0.9, -35.0), "C5": r(0.50, 0.40, 0.60, 1.2, -38.0)}
    V = CB.decide(R, base)
    assert V["best"] == "C1" and not V["per"]["C1"]
    assert V["per"]["C2"] and V["per"]["C3"] and V["per"]["C4"] and V["per"]["C5"]   # 前半低 / 只 +0.04 / 近 5 年低 / 回撤深 3 pp


def test_asof_values_handles_repeated_dates():
    s = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-05"]))
    d = pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-05", "2023-12-31"])
    v = CB.asof_values(s, d)
    assert v[:3].tolist() == [1.0, 1.0, 3.0] and np.isnan(v[3])                # 同一天多笔、之前没有值 → 缺值
