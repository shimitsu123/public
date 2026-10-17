"""引擎层测试：成交时点、止损/止盈/跟踪、跳空、单元股、资金约束。

这些断言就是"回测规则"的可执行说明书 —— 改了引擎而没改这里，说明规则变了。
"""
import numpy as np
import pytest

from conftest import make_indicator_frame
from qbreak.config import BacktestConfig, StrategyParams
from qbreak.engine import run_backtest


def _bt(cash=1_000_000, **kw):
    bt = BacktestConfig.for_market("JP")
    bt.sizing.initial_cash = cash
    bt.exec_cfg.slippage_pct = 0.0
    bt.exec_cfg.commission_pct = 0.0
    for k, v in kw.items():
        if hasattr(bt.exec_cfg, k):
            setattr(bt.exec_cfg, k, v)
        else:
            setattr(bt.sizing, k, v)
    return bt


FLAT = (100.0, 101.0, 99.0, 100.0, 1e6)


def test_entry_executes_next_open_not_signal_close():
    rows = [FLAT] * 5 + [(100, 101, 99, 100, 1e6), (110, 112, 109, 111, 1e6)] + [FLAT] * 5
    ind = {"A.T": make_indicator_frame(rows, entries={5})}
    p = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=False)
    res = run_backtest(ind, p, _bt(max_entry_gap_pct=0))
    assert len(res.trades) == 1
    assert res.trades.iloc[0]["entry_px"] == 110.0          # T+1 开盘，不是 T 日收盘 100
    assert str(res.trades.iloc[0]["entry_date"].date()) == str(ind["A.T"].index[6].date())


def test_gap_filter_skips_runaway_open():
    rows = [FLAT] * 5 + [(100, 101, 99, 100, 1e6), (120, 125, 119, 124, 1e6)] + [FLAT] * 5
    ind = {"A.T": make_indicator_frame(rows, entries={5})}
    bt = _bt()
    bt.exec_cfg.max_entry_gap_pct = 3.0
    res = run_backtest(ind, StrategyParams(), bt)
    assert res.trades.empty and res.skipped["gap"] == 1


def test_fixed_stop_triggers_at_stop_price():
    rows = [FLAT] * 5 + [FLAT, (100, 101, 99, 100, 1e6), (100, 100, 80, 85, 1e6)] + [FLAT] * 3
    ind = {"A.T": make_indicator_frame(rows, entries={5})}
    p = StrategyParams(stop_loss_pct=7, take_profit_pct=0, trailing_stop_pct=0,
                       exit_on_macd_dead_cross=False)
    res = run_backtest(ind, p, _bt(stop_fill_mode="intraday"))
    t = res.trades.iloc[0]
    assert t["reason"] == "stop"
    assert t["exit_px"] == pytest.approx(100 * 0.93)         # 按止损价，不是按收盘 85


def test_gap_down_exits_at_open_not_stop_price():
    rows = [FLAT] * 5 + [FLAT, (100, 101, 99, 100, 1e6), (80, 82, 78, 79, 1e6)] + [FLAT] * 3
    ind = {"A.T": make_indicator_frame(rows, entries={5})}
    p = StrategyParams(stop_loss_pct=7, take_profit_pct=0, trailing_stop_pct=0,
                       exit_on_macd_dead_cross=False)
    res = run_backtest(ind, p, _bt(stop_fill_mode="intraday"))
    t = res.trades.iloc[0]
    assert t["reason"] == "gap_stop" and t["exit_px"] == 80.0


def test_take_profit_and_stop_priority_is_pessimistic():
    """同一根 K 线里既打到止损又打到止盈时，必须假设先打止损（最保守）。"""
    rows = [FLAT] * 5 + [FLAT, (100, 101, 99, 100, 1e6), (100, 140, 80, 130, 1e6)] + [FLAT] * 3
    ind = {"A.T": make_indicator_frame(rows, entries={5})}
    p = StrategyParams(stop_loss_pct=7, take_profit_pct=25, trailing_stop_pct=0,
                       exit_on_macd_dead_cross=False)
    res = run_backtest(ind, p, _bt(stop_fill_mode="intraday"))
    assert res.trades.iloc[0]["reason"] == "stop"


def test_trailing_stop_uses_running_peak():
    """intraday 模式：峰值取前一根为止的最高价。"""
    rows = ([FLAT] * 5 + [FLAT, (100, 101, 99, 100, 1e6)]
            + [(100, 150, 100, 150, 1e6), (150, 152, 125, 126, 1e6)] + [FLAT] * 3)
    ind = {"A.T": make_indicator_frame(rows, entries={5})}
    p = StrategyParams(stop_loss_pct=50, take_profit_pct=0, trailing_stop_pct=12,
                       exit_on_macd_dead_cross=False)
    res = run_backtest(ind, p, _bt(stop_fill_mode="intraday"))
    t = res.trades.iloc[0]
    assert t["reason"] == "trail"
    # 峰值取**前一根为止**的最高价（150），当根盘中新高 152 不算 —— 日线无法知道
    # 152 和 125 谁先出现，取更保守的一边
    assert t["exit_px"] == pytest.approx(150 * 0.88, rel=1e-6)


def test_dead_cross_exits_next_open():
    rows = [FLAT] * 5 + [FLAT, (100, 101, 99, 100, 1e6), (100, 101, 99, 100, 1e6),
                         (95, 96, 94, 95, 1e6)] + [FLAT] * 3
    ind = {"A.T": make_indicator_frame(rows, entries={5}, deads={7})}
    p = StrategyParams(stop_loss_pct=50, take_profit_pct=0, trailing_stop_pct=0)
    res = run_backtest(ind, p, _bt())
    t = res.trades.iloc[0]
    assert t["reason"] == "dead_cross" and t["exit_px"] == 95.0


def test_max_hold_and_time_stop():
    rows = [FLAT] * 30
    ind = {"A.T": make_indicator_frame(rows, entries={5})}
    p = StrategyParams(stop_loss_pct=50, take_profit_pct=0, trailing_stop_pct=0,
                       exit_on_macd_dead_cross=False, max_hold_days=5)
    res = run_backtest(ind, p, _bt())
    assert res.trades.iloc[0]["reason"] == "max_hold"
    assert res.trades.iloc[0]["hold_days"] == 5

    p2 = StrategyParams(stop_loss_pct=50, take_profit_pct=0, trailing_stop_pct=0,
                        exit_on_macd_dead_cross=False, max_hold_days=0,
                        time_stop_days=3, time_stop_min_ret_pct=5.0)
    res2 = run_backtest(ind, p2, _bt())
    assert res2.trades.iloc[0]["reason"] == "time_stop"


def test_lot_rounding_and_cash_never_negative():
    rows = [FLAT] * 5 + [FLAT, (333, 340, 330, 335, 1e6)] + [FLAT] * 20
    ind = {"A.T": make_indicator_frame(rows, entries={5})}
    bt = _bt(cash=100_000, position_pct=1.0, max_position_pct=1.0)
    bt.exec_cfg.max_entry_gap_pct = 0
    res = run_backtest(ind, StrategyParams(stop_loss_pct=90, take_profit_pct=0,
                                           trailing_stop_pct=0,
                                           exit_on_macd_dead_cross=False), bt)
    assert res.trades.iloc[0]["shares"] % 100 == 0          # 単元株 100 股
    assert (res.equity > 0).all()


def test_position_sizing_uses_previous_equity_not_today_close():
    """当日买入的金额只能依据『昨日收盘权益』——用当日收盘价算就是前视偏差。"""
    rows = [FLAT] * 5 + [FLAT, (100, 300, 100, 300, 1e6)] + [FLAT] * 10
    ind = {"A.T": make_indicator_frame(rows, entries={5})}
    bt = _bt(cash=1_000_000, position_pct=0.5, max_position_pct=1.0)
    bt.exec_cfg.max_entry_gap_pct = 0
    res = run_backtest(ind, StrategyParams(stop_loss_pct=90, take_profit_pct=0,
                                           trailing_stop_pct=0,
                                           exit_on_macd_dead_cross=False), bt)
    shares = res.trades.iloc[0]["shares"]
    assert shares == 5000        # 1,000,000×50% / 100 = 5000 股；若用当日收盘 300 会得到别的数


def test_max_positions_respected():
    rows = [FLAT] * 40
    ind = {f"{i}.T": make_indicator_frame(rows, entries={5}) for i in range(8)}
    bt = _bt(max_positions=3, position_pct=0.2)
    bt.exec_cfg.max_entry_gap_pct = 0
    res = run_backtest(ind, StrategyParams(stop_loss_pct=90, take_profit_pct=0,
                                           trailing_stop_pct=0,
                                           exit_on_macd_dead_cross=False), bt)
    assert len(res.trades) == 3 and res.skipped["full"] >= 1


def test_atr_stop_overrides_fixed_pct():
    rows = [FLAT] * 5 + [FLAT, (100, 101, 99, 100, 1e6), (100, 100, 94, 95, 1e6)] + [FLAT] * 3
    ind = {"A.T": make_indicator_frame(rows, entries={5}, atr=2.0)}
    p = StrategyParams(stop_loss_pct=50, atr_stop_mult=2.0, take_profit_pct=0,
                       trailing_stop_pct=0, exit_on_macd_dead_cross=False)
    res = run_backtest(ind, p, _bt(stop_fill_mode="intraday"))
    assert res.trades.iloc[0]["exit_px"] == pytest.approx(96.0)   # 100 − 2×2


def test_halted_ticker_does_not_lose_pending_exit():
    """标的停牌那天不能被当成"已卖出"；恢复交易后仍要卖。"""
    df = make_indicator_frame([FLAT] * 12, entries={5}, deads={7})
    df = df.drop(df.index[8])                     # 第 8 根 K 线缺失 = 停牌
    res = run_backtest({"A.T": df}, StrategyParams(stop_loss_pct=90, take_profit_pct=0,
                                                   trailing_stop_pct=0), _bt())
    assert res.trades.iloc[0]["reason"] == "dead_cross"


def test_equity_curve_consistent_with_cash_and_positions():
    rows = [FLAT] * 5 + [FLAT, (100, 101, 99, 100, 1e6)] + [FLAT] * 20
    ind = {"A.T": make_indicator_frame(rows, entries={5})}
    res = run_backtest(ind, StrategyParams(stop_loss_pct=90, take_profit_pct=0,
                                           trailing_stop_pct=0,
                                           exit_on_macd_dead_cross=False), _bt())
    assert np.isfinite(res.equity).all() and (res.equity > 0).all()
    assert res.metrics["trades"] == len(res.trades)


# ────────────── next_open 模式（默认）：程序每天只跑一次时真正能做到的 ──────────────
def test_next_open_mode_exits_at_following_open_not_stop_price():
    """默认模式下，收盘跌破止损 → 次日开盘成交。若当晚利空跳空，成交价远低于止损价 ——
    这才是"没挂逆指値"时的真实结果。原版按 intraday 记账，等于白送了这部分亏损。"""
    rows = ([FLAT] * 5 + [FLAT, (100, 101, 99, 100, 1e6), (100, 100, 90, 91, 1e6),
                          (85, 86, 84, 85, 1e6)] + [FLAT] * 3)
    ind = {"A.T": make_indicator_frame(rows, entries={5})}
    p = StrategyParams(stop_loss_pct=7, take_profit_pct=0, trailing_stop_pct=0,
                       exit_on_macd_dead_cross=False)
    res = run_backtest(ind, p, _bt())                       # 默认 next_open
    t = res.trades.iloc[0]
    assert t["reason"] == "stop" and t["exit_px"] == 85.0    # 不是 93


def test_intraday_mode_is_more_optimistic_than_next_open():
    rows = ([FLAT] * 5 + [FLAT, (100, 101, 99, 100, 1e6), (100, 100, 90, 91, 1e6),
                          (85, 86, 84, 85, 1e6)] + [FLAT] * 3)
    ind = {"A.T": make_indicator_frame(rows, entries={5})}
    p = StrategyParams(stop_loss_pct=7, take_profit_pct=0, trailing_stop_pct=0,
                       exit_on_macd_dead_cross=False)
    a = run_backtest(ind, p, _bt()).trades.iloc[0]["pnl"]
    b = run_backtest(ind, p, _bt(stop_fill_mode="intraday")).trades.iloc[0]["pnl"]
    assert b > a, "intraday 假设必然更乐观；两者之差就是『没挂逆指値』的代价"


def test_stop_takes_priority_over_dead_cross_in_next_open_mode():
    rows = ([FLAT] * 5 + [FLAT, (100, 101, 99, 100, 1e6), (100, 100, 90, 91, 1e6)]
            + [FLAT] * 4)
    ind = {"A.T": make_indicator_frame(rows, entries={5}, deads={7})}
    p = StrategyParams(stop_loss_pct=7, take_profit_pct=0, trailing_stop_pct=0)
    assert run_backtest(ind, p, _bt()).trades.iloc[0]["reason"] == "stop"
