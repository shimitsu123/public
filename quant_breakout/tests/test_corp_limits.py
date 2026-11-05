"""配当落ち / 株式分割 / 値幅制限。"""
import datetime as dt

import numpy as np
import pandas as pd

from conftest import make_indicator_frame
from qbreak import paths
from qbreak.brokers import PaperBroker
from qbreak.config import BacktestConfig, DataConfig, ExecConfig, RiskConfig, SizingConfig, StrategyParams
from qbreak.corpactions import FakeActions, infer_split
from qbreak.engine import run_backtest
from qbreak.tick import limit_lock, price_limit_jp
from qbreak.trader import PositionBook, run_once

T = "9999.T"
EX = ExecConfig(market="JP", commission_pct=0, slippage_pct=0)
P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=False, stop_loss_pct=7)


def _write(bars, last):
    idx = pd.bdate_range(end=pd.Timestamp(last), periods=len(bars))
    df = pd.DataFrame(bars, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)
    df.index.name = "Date"
    (paths.sub("csv") / f"{T}.csv").write_text(df.to_csv(), encoding="utf-8")
    return idx


def _run(b, day, acts=None):
    return run_once([T], b, P, RiskConfig(require_arm=False, max_order_value=1e9),
                    SizingConfig(position_pct=0.5, max_position_pct=1.0),
                    DataConfig(provider="csv", years=2, min_bars=100),
                    market="JP", today=day, exec_cfg=EX, corp_actions=acts)


FLAT = [(1000.0, 1002.0, 998.0, 1000.0, 1e6)] * 300
SIG = (1000.0, 1031.0, 999.0, 1030.0, 6e6)


def _enter(b):
    """信号 → 次日开盘 1040 买入 → 返回 (idx, 持仓日)。"""
    _write(FLAT + [SIG], "2026-02-02"); _run(b, dt.date(2026, 2, 2))
    idx = _write(FLAT + [SIG, (1040.0, 1045.0, 1035.0, 1042.0, 2e6)], "2026-02-03")
    _run(b, dt.date(2026, 2, 3))
    assert T in b.positions()
    return idx


def test_price_limit_table_and_lock_detection():
    assert price_limit_jp(99) == 30 and price_limit_jp(1000) == 300 and price_limit_jp(2999) == 500
    assert limit_lock(1000, 700, 700, 700, "JP") == "down"
    assert limit_lock(1000, 1300, 1300, 1300, "JP") == "up"
    assert limit_lock(1000, 760, 700, 700, "JP") is None           # 盘中有成交区间 → 寄付能卖
    assert limit_lock(1000, 700, 700, 700, "US") is None


def test_infer_split_ratios():
    assert infer_split(1000, 500) == 2 and infer_split(900, 300.5) == 3 and infer_split(1000, 985) is None


def test_dividend_credits_cash_lowers_stop_and_counts_in_pnl():
    b = PaperBroker(initial_cash=1_000_000, exec_cfg=EX, market="JP")
    _enter(b)
    qty = b.positions()[T].qty
    book = PositionBook()
    stop0 = float(book.book[T]["stop_px"])
    cash0 = b.cash()
    acts = FakeActions({T: [{"date": "2026-02-04", "dividend": 20.0, "split": 0.0}]})
    # 2/4 除息：真实价格下跌 20，复权数据里之前的 K 线都被下调
    _write(FLAT + [SIG, (1040.0, 1045.0, 1035.0, 1042.0, 2e6), (1022.0, 1026.0, 1018.0, 1021.0, 1e6)], "2026-02-04")
    r = _run(b, dt.date(2026, 2, 4), acts)
    net = round(20.0 * qty * (1 - 0.20315), 2)
    assert abs(b.cash() - (cash0 + net)) < 0.01
    assert abs(float(PositionBook().book[T]["stop_px"]) - (stop0 - 20.0)) < 1e-6
    assert any("配当落ち" in n for n in r.notes)
    _run(b, dt.date(2026, 2, 4), acts)                              # 重复运行不重复入账
    assert abs(b.cash() - (cash0 + net)) < 0.01


def test_split_scales_qty_and_does_not_trigger_stop():
    b = PaperBroker(initial_cash=1_000_000, exec_cfg=EX, market="JP")
    _enter(b)
    qty0, avg0 = b.positions()[T].qty, b.positions()[T].avg_px
    acts = FakeActions({T: [{"date": "2026-02-04", "dividend": 0.0, "split": 2.0}]})
    # 1→2 拆股：真实价格 ~521（复权数据把之前的 K 线都除以 2）
    half = [(o / 2, h / 2, l / 2, c / 2, v * 2) for o, h, l, c, v in FLAT + [SIG, (1040.0, 1045.0, 1035.0, 1042.0, 2e6)]]
    _write(half + [(521.0, 524.0, 519.0, 522.0, 4e6)], "2026-02-04")
    r = _run(b, dt.date(2026, 2, 4), acts)
    pos = b.positions()[T]
    assert pos.qty == qty0 * 2 and abs(pos.avg_px - avg0 / 2) < 1e-9
    assert not [o for o in r.orders if o["side"] == "SELL"]          # 没有被误判为 −50% 止损
    assert abs(float(PositionBook().book[T]["stop_px"]) - avg0 * 0.93 / 2) < 1e-6


def test_split_fallback_when_provider_fails():
    class Broken:
        def actions(self, t):
            raise RuntimeError("network down")
    b = PaperBroker(initial_cash=1_000_000, exec_cfg=EX, market="JP")
    _enter(b)
    qty0 = b.positions()[T].qty
    half = [(o / 2, h / 2, l / 2, c / 2, v * 2) for o, h, l, c, v in FLAT + [SIG, (1040.0, 1045.0, 1035.0, 1042.0, 2e6)]]
    _write(half + [(521.0, 524.0, 519.0, 522.0, 4e6)], "2026-02-04")
    r = _run(b, dt.date(2026, 2, 4), Broken())
    assert b.positions()[T].qty == qty0 * 2 and not [o for o in r.orders if o["side"] == "SELL"]


def test_paper_sell_carried_over_on_limit_down_lock():
    b = PaperBroker(initial_cash=1_000_000, exec_cfg=EX, market="JP")
    _enter(b)
    # 2/4 收盘跌破止损 → 排队卖出；2/5 一整天张贴ストップ安 → 卖不掉顺延；2/6 寄付成交
    bars = FLAT + [SIG, (1040.0, 1045.0, 1035.0, 1042.0, 2e6), (960.0, 962.0, 950.0, 955.0, 3e6)]
    _write(bars, "2026-02-04"); _run(b, dt.date(2026, 2, 4))
    assert any(o["side"] == "SELL" for o in b.pending())
    _write(bars + [(655.0, 655.0, 655.0, 655.0, 1e5)], "2026-02-05")
    r = _run(b, dt.date(2026, 2, 5))
    assert T in b.positions() and any(o["side"] == "SELL" for o in b.pending())
    assert not [o for o in r.orders if o["side"] == "SELL" and o["status"] == "FILLED"]
    _write(bars + [(655.0, 655.0, 655.0, 655.0, 1e5), (600.0, 640.0, 590.0, 630.0, 5e6)], "2026-02-06")
    r = _run(b, dt.date(2026, 2, 6))
    assert T not in b.positions()
    assert [o for o in r.orders if o["side"] == "SELL" and o["status"] == "FILLED"][0]["filled_px"] == 600.0


def test_engine_limit_down_defers_exit_and_limit_up_blocks_entry():
    rows = [(1000.0, 1002.0, 998.0, 1000.0, 1e6)] * 30
    rows += [(1000.0, 1031.0, 999.0, 1030.0, 6e6)]                 # 30: 信号
    rows += [(1040.0, 1045.0, 1035.0, 1042.0, 2e6)]                # 31: 买入
    rows += [(960.0, 962.0, 950.0, 955.0, 3e6)]                    # 32: 收盘破止损 → 排队
    rows += [(655.0, 655.0, 655.0, 655.0, 1e5)]                    # 33: ストップ安張り付き
    rows += [(600.0, 640.0, 590.0, 630.0, 5e6)] * 5                # 34: 寄付で約定
    ind = {"A.T": make_indicator_frame(rows, entries=[30])}
    bt = BacktestConfig.for_market("JP")
    bt.exec_cfg.slippage_pct = 0
    res = run_backtest(ind, P, bt)
    tr = res.trades.iloc[0]
    assert tr["exit_px"] == 600.0 and res.skipped["limit_down_hold"] == 1
    up = [(1000.0, 1002.0, 998.0, 1000.0, 1e6)] * 30 + [(1000.0, 1031.0, 999.0, 1030.0, 6e6)] \
        + [(1330.0, 1330.0, 1330.0, 1330.0, 1e5)] + [(1330.0, 1340.0, 1320.0, 1330.0, 1e6)] * 5
    bt.exec_cfg.max_entry_gap_pct = 0                              # 关掉跳空过滤，单测値幅制限
    res2 = run_backtest({"B.T": make_indicator_frame(up, entries=[30])}, P, bt)
    assert res2.trades.empty and res2.skipped["limit_up"] == 1
