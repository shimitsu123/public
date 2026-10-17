"""核心指数仓位（引擎）与 2027-03 起的 STR 呼値表。"""
import datetime as dt

import numpy as np
import pandas as pd

from conftest import make_indicator_frame
from qbreak.config import BacktestConfig, StrategyParams
from qbreak.core import core_frame, core_orders
from qbreak.engine import run_backtest
from qbreak.tick import _STR_TICKS, round_to_tick, tick_size

P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=False, max_hold_days=0)


def _ind(n=60, core_path=None):
    rows = [(1000.0, 1002.0, 998.0, 1000.0, 1e6)] * 30 + [(1000.0, 1031.0, 999.0, 1030.0, 6e6)] \
        + [(1040.0, 1045.0, 1035.0, 1042.0, 2e6)] * (n - 31)
    cp = core_path if core_path is not None else np.linspace(100, 130, n)
    return {"A.T": make_indicator_frame(rows, entries=[30]),
            "CORE": make_indicator_frame([(x, x * 1.001, x * 0.999, x, 1e9) for x in cp])}


def _bt():
    bt = BacktestConfig.for_market("JP")
    bt.exec_cfg.slippage_pct = 0
    return bt


CS = {"ticker": "CORE", "buffer_pct": 0.0, "band_pct": 5.0, "buy_fee_pct": 0.0, "sell_fee_pct": 0.0, "slip_pct": 0.0, "lot": 1}


def test_core_invests_idle_cash_and_funds_stock_entries():
    ind = _ind()
    base = run_backtest(ind, P, _bt())
    r = run_backtest(ind, P, _bt(), core=CS)
    assert len(r.trades) == len(base.trades) == 1                     # 个股交易照常发生
    assert r.trades.iloc[0]["shares"] >= base.trades.iloc[0]["shares"]   # 权益含指数收益 → 按比例股数不少于无核心时
    assert r.equity.iloc[-1] > base.equity.iloc[-1] * 1.15              # 指数 +30% 的闲置资金收益
    assert r.extra["core"]["sold"] > 0                                 # 个股入场时卖出了核心仓位


def test_core_bear_timing_liquidates_and_fees_counted():
    n = 60
    path = np.r_[np.linspace(100, 120, 40), np.linspace(120, 80, 20)]
    ind = _ind(n, path)
    bear = np.zeros(n, bool); bear[42:] = True
    timed = run_backtest(ind, P, _bt(), core=CS, core_bear=bear)
    held = run_backtest(ind, P, _bt(), core=CS)
    assert timed.extra["core"]["units_end"] == 0 and timed.equity.iloc[-1] > held.equity.iloc[-1]
    costly = run_backtest(ind, P, _bt(), core={**CS, "sell_fee_pct": 0.495, "sell_fee_max": 22.0}, core_bear=bear)
    assert 0 < costly.extra["core"]["fees"] <= 22.0 * costly.extra["core"]["trades"]


def test_core_frame_and_target_units():
    idx = pd.bdate_range("2008-01-01", periods=6)
    ix = pd.DataFrame({"Open": [100, 101, 102, 103, 104, 105.0], "High": [101, 102, 103, 104, 105, 106.0],
                       "Low": [99, 100, 101, 102, 103, 104.0], "Close": [100, 101, 102, 103, 104, 105.0]}, index=idx)
    etf = pd.DataFrame({"Open": [51.0], "High": [52.0], "Low": [50.0], "Close": [52.0], "Volume": [1]}, index=idx[3:4])
    cf = core_frame(etf, ix)
    assert len(cf) == 4 and not cf["entry"].any() and abs(cf["Close"].iloc[-1] - 52.0) < 1e-9
    assert np.allclose(cf["Close"].pct_change().iloc[1:3].values, ix["Close"].pct_change().iloc[1:3].values)
    # 目标 = (100 万 − 个股 30 万) / 6800 = 102 口；已有 0 口 → 买 102
    assert core_orders(1_000_000, 300_000, 0, 700_000, 0, 6800, bear=False) == (0, 102)
    assert core_orders(1_000_000, 300_000, 0, 0, 102, 6800, bear=True) == (102, 0)       # 熊市清空
    assert core_orders(1_000_000, 300_000, 0, 0, 100, 6800, bear=False) == (0, 0)        # 偏离 < band 不动
    # 明天要买 34 万个股、现金只有 1 万 → 缺口 33 万 ×(1+3%) 由卖核心补足（多于目标差额）
    sell, buy = core_orders(1_000_000, 0, 340_000, 10_000, 147, 6800, bear=False)
    assert buy == 0 and sell * 6800 >= 330_000 * 1.03 and (sell - 1) * 6800 < 330_000 * 1.03


def test_str_tick_tables_switch_on_2027_03_01():
    before, after = dt.date(2027, 2, 26), dt.date(2027, 3, 1)
    assert tick_size(1500, "7203", before) == 1.0 and tick_size(1500, "7203", after) == 2.0   # 未登记 → C 表
    assert tick_size(1500, "1329", after, lot=1) == 1.0                                         # 交易单位 1 → O 表
    assert round_to_tick(1001.3, "X", "BUY", after) == 1000.0 and round_to_tick(1001.3, "X", "SELL", after) == 1002.0
    for a, b, c in zip(_STR_TICKS["A"], _STR_TICKS["B"], _STR_TICKS["C"]):   # C 表价格在 A/B 表也合法
        assert abs(c / a - round(c / a)) < 1e-9 and abs(c / b - round(c / b)) < 1e-9
