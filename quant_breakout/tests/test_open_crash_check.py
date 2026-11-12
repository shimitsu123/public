"""scripts/open_crash_check.py（2026-10-04 登记，只描述）：登记的常数与读法、跳空 / 开盘→收盘 / 次日只用连续交易日、盘中止损的卖价、
个股按天平均、按年重抽的区间、R1 / R2 的判法。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import open_crash_check as V  # noqa: E402


def test_registered_constants():
    assert (V.ETF, V.START, V.MID, V.END) == ("1321.T", "2009-02-06", "2017-01-01", "2026-09-30")
    assert (V.GAPS, V.STOPS, V.MAIN_GAP, V.MAIN_STOP, V.SEED, V.REPS) == ((-0.01, -0.02, -0.03), (0.01, 0.02, 0.03), -0.02, 0.02, 20261019, 2000)
    assert V.TRADES_PER_YEAR == pytest.approx(62 / 9.75) and (V.SLOT, V.CAPITAL) == (0.25, 1_000_000)
    src = inspect.getsource(V.run_all)
    assert "judge(r[\"etf_oc\"], r[\"etf_on\"], r[\"stk_oc\"], r[\"stk_on\"]) if thr == MAIN_GAP" in src
    assert "judge(r[\"etf_x0\"], r[\"etf_x1\"], r[\"stk_x0\"], r[\"stk_x1\"]) if s == MAIN_STOP" in src


def _bars(rows, dates):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=pd.DatetimeIndex(dates))


def test_day_table_uses_only_consecutive_trading_days():
    dates = ["2026-09-24", "2026-09-25", "2026-09-28", "2026-09-30", "2026-10-01"]     # 09-29 缺行
    e = _bars([[100, 101, 99, 100], [97, 99, 96, 98], [99, 100, 95, 96], [90, 92, 89, 91], [92, 93, 91, 92]], dates)
    D = V.day_table(e)
    assert np.isnan(D["g"].iloc[0]) and D["g"].iloc[1] == pytest.approx(-0.03) and D["g"].iloc[2] == pytest.approx(99 / 98 - 1)
    assert np.isnan(D["g"].iloc[3])                                              # 前一行是 09-28，不是前一个交易日 09-29 → 不算跳空
    assert D["oc"].iloc[1] == pytest.approx(98 / 97 - 1) and D["on"].iloc[1] == pytest.approx(96 / 97 - 1)
    assert np.isnan(D["on"].iloc[2]) and np.isnan(D["on"].iloc[4])               # 次日缺行 / 没有次日 → 空
    assert D["lo"].iloc[2] == pytest.approx(95 / 99 - 1)


def test_stop_table_sells_at_open_times_one_minus_s():
    dates = ["2026-09-24", "2026-09-25", "2026-09-28"]
    e = _bars([[100, 101, 97.9, 99], [100, 100, 99, 99.5], [100, 101, 96, 97]], dates)
    T = V.stop_table(e, 0.02)
    assert list(T.index) == [pd.Timestamp("2026-09-24"), pd.Timestamp("2026-09-28")]  # 最低 ≤ 98 的日子
    assert T["x0"].iloc[0] == pytest.approx(99 / 98 - 1) and T["x1"].iloc[0] == pytest.approx(99.5 / 98 - 1)
    assert T["x0"].iloc[1] == pytest.approx(97 / 98 - 1) and np.isnan(T["x1"].iloc[1])


def test_stock_means_by_day():
    dates = pd.DatetimeIndex(["2026-09-24", "2026-09-25", "2026-09-28"])
    a = _bars([[100, 100, 100, 100], [90, 95, 80, 99], [100, 100, 91, 95]], dates)
    b = _bars([[50, 50, 50, 50], [50, 51, 40, 45], [44, 46, 43, 46]], dates)
    P = V.panel({"A": a, "B": b.drop(dates[2])})                                 # B 在 09-28 没有行情
    m = V.stock_gap_means(P, pd.DatetimeIndex([dates[1]]))
    assert m["oc"].iloc[0] == pytest.approx(((99 / 90 - 1) + (45 / 50 - 1)) / 2)
    assert m["on"].iloc[0] == pytest.approx(95 / 90 - 1)                         # B 没有次日 → 只平均 A
    s = V.stock_stop_means(P, 0.10)
    assert list(s.index) == [dates[1]] and s["x0"].iloc[0] == pytest.approx(((99 / 81 - 1) + (45 / 45 - 1)) / 2)


def test_summarize_and_year_block_ci():
    idx = pd.to_datetime([f"{y}-03-02" for y in range(2010, 2020)] + [f"{y}-06-01" for y in range(2010, 2020)])
    x = pd.Series(np.r_[np.full(10, -0.01), np.full(10, -0.03)], index=idx).sort_index()
    s = V.summarize(x, 1)
    assert s["n"] == 20 and s["mean"] == pytest.approx(-0.02) and s["pos"] == 0
    assert s["ci"][1] < 0 and s["ci"][0] == pytest.approx(-0.02) and s["h1"] == pytest.approx(-0.02) and s["n2"] == 6
    assert V.summarize(x, 1) == s and V.summarize(pd.Series(dtype=float), 1) == {"n": 0}


def _st(mean, lo, hi, h1, h2, n=30):
    return {"n": n, "mean": mean, "ci": [lo, hi], "h1": h1, "h2": h2}


def test_judge_reading_rule():
    neg, neg2 = _st(-0.01, -0.02, -0.002, -0.01, -0.01), _st(-0.012, -0.02, -0.001, -0.02, -0.005)
    pos, pos2 = _st(0.01, 0.002, 0.02, 0.01, 0.01), _st(0.008, 0.001, 0.02, -0.001, 0.02)
    assert V.judge(neg, neg2, _st(-0.004, -1, 1, 0, 0), _st(-0.001, -1, 1, 0, 0)) == "有用"
    assert V.judge(neg, neg2, _st(0.004, -1, 1, 0, 0), _st(-0.001, -1, 1, 0, 0)) == "分不出"     # 个股与 1321 不同号
    assert V.judge(pos, pos2, _st(0.003, -1, 1, 0, 0), _st(0.002, -1, 1, 0, 0)) == "有害"         # 有害只看区间下限，不看两半
    assert V.judge(neg, _st(-0.01, -0.02, 0.001, -0.01, -0.01)) == "分不出"                      # 区间上限没 < 0
    assert V.judge(neg, _st(-0.01, -0.02, -0.001, 0.001, -0.02)) == "分不出"                     # 前一半 > 0
    assert V.judge({"n": 0}, neg) == "分不出"
