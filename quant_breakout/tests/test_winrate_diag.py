"""scripts/winrate_diag.py 的纯函数（只描述的诊断）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import winrate_diag as WD  # noqa: E402


def _tr(**k):
    base = dict(ticker="7203.T", market="JP", entry_date="2020-01-06", exit_date="2020-01-20", entry_px=100.0, exit_px=110.0,
                shares=100, pnl=990.0, pnl_jpy=990.0, ret_pct=10.0, hold_days=10, reason="chandelier")
    base.update(k)
    return base


def test_stock_trades_filters_core_end_and_window():
    trades = [_tr(), _tr(ticker="1545.T"), _tr(reason="end"), _tr(entry_date="2019-12-30"),
              _tr(ticker="6758.T", pnl=-210.0, ret_pct=-2.0, exit_px=98.0)]
    tr = WD.stock_trades(trades, "2020-01-01", "2021-01-01")
    assert list(tr["ticker"]) == ["7203.T", "6758.T"]
    assert np.allclose(tr["net"], [9.9, -2.1])
    assert np.allclose(tr["fee_pp"], [0.1, 0.1])
    assert list(tr["win"]) == [True, False]
    assert WD.stock_trades([], "2020-01-01", "2021-01-01").empty


def test_payoff_breakeven_and_ratio():
    p = WD.payoff([10, 10, -5, -5, -5])
    assert p["n"] == 5 and p["wins"] == 2 and p["win"] == 40.0
    assert p["avg_win"] == 10.0 and p["avg_loss"] == 5.0 and p["ratio"] == 2.0
    assert p["breakeven"] == round(5 / 15 * 100, 1)                         # 盈亏比 2 → 保本胜率 33.3%
    assert p["mean"] == 1.0
    assert WD.payoff([])["n"] == 0
    lo, hi = p["ci"]
    assert lo < 40.0 < hi


def test_wilson_bounds():
    assert WD.wilson(0, 0) is None
    lo, hi = WD.wilson(50, 100)
    assert 39 < lo < 41 and 59 < hi < 61


def test_path_extremes_uses_entry_to_day_before_exit():
    idx = pd.bdate_range("2020-01-06", periods=6)
    df = pd.DataFrame({"High": [101, 104, 103, 120, 99, 98], "Low": [99, 97, 100, 101, 90, 95]}, index=idx)
    mfe, mae = WD.path_extremes(df, idx[0], idx[3], 100.0)                  # 卖出日（第 4 天）的 120 不算
    assert round(mfe, 9) == 4.0 and round(mae, 9) == -3.0
    assert all(np.isnan(WD.path_extremes(None, idx[0], idx[3], 100.0)))


def test_loser_types_buckets():
    tr = pd.DataFrame({"win": [False, False, False, False, True], "mfe": [1.0, 3.0, 8.0, np.nan, 12.0],
                       "gross": [-3.0, 0.05, -1.0, -2.0, 10.0], "net": [-3.1, -0.05, -1.1, -2.1, 9.9], "hold_days": [3, 6, 20, 4, 30]})
    x = WD.loser_types(tr)
    assert (x["n"], x["L1"], x["L2"], x["L3"], x["unknown"]) == (4, 1, 1, 1, 1)
    assert x["fee_eaten"] == 1                                               # 价格涨 0.05% 但扣费用后亏
    assert x["within5_pct"] == 50.0 and x["within10_pct"] == 75.0


def test_ret_between_close_to_close():
    s = pd.Series([100.0, 110.0, 99.0], index=pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-09"]))
    assert round(WD.ret_between(s, "2020-01-06", "2020-01-08"), 6) == 10.0      # 1/8 没有 → 用之前最后一天
    assert np.isnan(WD.ret_between(s, "2019-12-31", "2020-01-07"))
