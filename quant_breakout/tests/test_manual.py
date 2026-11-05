"""半自动模式：ManualBroker 永不发单 + 操作清单可读可照抄。"""
import datetime as dt

import pandas as pd

from qbreak import paths
from qbreak.brokers.manual import ManualBroker
from qbreak.brokers.base import Position
from qbreak.config import DataConfig, ExecConfig, RiskConfig, SizingConfig, StrategyParams
from qbreak.trader import DayResult, PositionBook, operation_sheet, run_once

TICKER = "9999.T"


def test_manual_broker_never_fills():
    b = ManualBroker(initial_cash=1_000_000)
    b.set_prices({TICKER: 1000.0})
    o = b.buy(TICKER, 100, client_id="c1")
    assert o.status == "PROPOSED" and not b.positions() and b.cash() == 1_000_000


def test_manual_register_and_remove_persist():
    b = ManualBroker(initial_cash=1_000_000)
    b.add(TICKER, 100, 1000.0, "2026-09-22")
    b.add(TICKER, 100, 1100.0)
    p = ManualBroker().positions()[TICKER]
    assert p.qty == 200 and p.avg_px == 1050.0 and p.entry_date == "2026-09-22"
    ManualBroker().remove(TICKER, 50)
    assert ManualBroker().positions()[TICKER].qty == 150
    ManualBroker().remove(TICKER)
    assert not ManualBroker().positions()


def test_operation_sheet_lists_buy_with_limit_and_stop():
    res = DayResult(date="2026-09-24", orders=[
        {"side": "BUY", "ticker": "7203.T", "qty": 100, "price": 2987.0,
         "status": "DRY_RUN", "note": "entry(range=8.1% vol×2.3)", "stop_px": 2777.9}])
    p = StrategyParams()
    txt = operation_sheet(res, p, {}, limit_buffer_pct=0.5)
    assert "买入" in txt and "7203.T" in txt
    assert "3,000" in txt                     # 2987×1.005=3001.9 → 合法呼値 3000
    assert "2,778" in txt                     # 逆指値


def test_operation_sheet_holdings_show_trailing_stop_level():
    pos = {"8035.T": Position("8035.T", 100, 20000.0, peak=28000.0, stop_px=18600.0)}
    txt = operation_sheet(DayResult(date="2026-09-24"), StrategyParams(), pos)
    assert "跟踪止损" in txt and "24,640" in txt         # 28000×0.88


def test_signal_flow_end_to_end_with_csv(tmp_path):
    """信号 → 操作清单，全程不发单（和 test_trader 用同样的造数方式）。"""
    idx = pd.bdate_range(end=pd.Timestamp("2026-01-05"), periods=301)
    bars = [(1000.0, 1002.0, 998.0, 1000.0, 1e6)] * 300 + [(1000.0, 1031.0, 999.0, 1030.0, 6e6)]
    df = pd.DataFrame(bars, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)
    df.index.name = "Date"
    (paths.sub("csv") / f"{TICKER}.csv").write_text(df.to_csv(), encoding="utf-8")
    p = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=False)
    b = ManualBroker(initial_cash=1_000_000)
    res = run_once([TICKER], b, p, RiskConfig(require_arm=False, max_order_value=1e7),
                   SizingConfig(position_pct=0.5, max_position_pct=1.0),
                   DataConfig(provider="csv", years=2, min_bars=100),
                   today=dt.date(2026, 1, 5), dry_run=True,
                   exec_cfg=ExecConfig(market="JP", commission_pct=0, slippage_pct=0))
    assert res.signals == [TICKER]
    txt = operation_sheet(res, p, PositionBook().merge(b.positions()))
    assert "买入" in txt and TICKER in txt and "逆指値" in txt
    assert not b.positions()                 # 什么都没成交
