"""每日流程端到端测试：用 CSV provider 喂确定数据，不碰网络。

覆盖：信号 → 次日开盘成交 → 止损离场；数据过期拒绝交易；幂等；熔断；HALT。
"""
import datetime as dt

import pandas as pd
import pytest

from qbreak import paths
from qbreak.brokers import PaperBroker
from qbreak.config import DataConfig, ExecConfig, RiskConfig, SizingConfig, StrategyParams
from qbreak.risk import RiskManager
from qbreak.trader import run_once

TICKER = "9999.T"


def _write_csv(bars, last_date: dt.date):
    """bars: [(o,h,l,c,v)]；最后一根的日期 = last_date。"""
    idx = pd.bdate_range(end=pd.Timestamp(last_date), periods=len(bars))
    df = pd.DataFrame(bars, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)
    df.index.name = "Date"
    (paths.sub("csv") / f"{TICKER}.csv").write_text(df.to_csv(), encoding="utf-8")


def _flat(n=300, px=1000.0, vol=1e6):
    return [(px, px * 1.002, px * 0.998, px, vol)] * n


def _signal_bar(px=1030.0, vol=6e6):
    """相对 1000 的横盘抬高 3% + 6 倍量 → 满足 横盘/金叉/0轴附近/放量。"""
    return (1000.0, px * 1.001, 999.0, px, vol)


P = StrategyParams(range_n=60, range_x_pct=15.0, take_profit_pct=0.0,
                   trailing_stop_pct=0.0, exit_on_macd_dead_cross=False,
                   stop_loss_pct=7.0)
RISK = RiskConfig(max_order_value=10_000_000, require_arm=False, stale_data_max_days=1)
SIZING = SizingConfig(initial_cash=1_000_000, position_pct=0.5, max_position_pct=1.0)
DATA = DataConfig(provider="csv", years=2, min_bars=100, allow_synthetic=False)
EX = ExecConfig(market="JP", commission_pct=0.0, slippage_pct=0.0, max_entry_gap_pct=3.0)


def _broker():
    return PaperBroker(initial_cash=1_000_000, exec_cfg=EX, market="JP")


def _run(broker, today, **kw):
    return run_once([TICKER], broker, P, RISK, SIZING, DATA, market="JP",
                    today=today, exec_cfg=EX, **kw)


def test_signal_queues_order_then_fills_at_next_open():
    d1 = dt.date(2026, 1, 5)
    _write_csv(_flat(300) + [_signal_bar()], d1)
    b = _broker()
    r1 = _run(b, d1)
    assert r1.signals == [TICKER], r1.summary()
    assert b.pending() and not b.positions()          # T 日只排队，不成交

    d2 = dt.date(2026, 1, 6)
    _write_csv(_flat(300) + [_signal_bar(), (1040.0, 1045.0, 1035.0, 1042.0, 2e6)], d2)
    r2 = _run(b, d2)
    assert any(o["status"] == "FILLED" for o in r2.orders), r2.summary()
    pos = b.positions()[TICKER]
    assert pos.qty == 400 and pos.avg_px == pytest.approx(1040.0)   # T+1 开盘价成交
    assert pos.stop_px == pytest.approx(1040.0 * 0.93, rel=1e-6)


def test_stop_loss_exits_position():
    d1, d2, d3 = dt.date(2026, 1, 5), dt.date(2026, 1, 6), dt.date(2026, 1, 7)
    base = _flat(300) + [_signal_bar()]
    _write_csv(base, d1)
    b = _broker(); _run(b, d1)
    base2 = base + [(1040.0, 1045.0, 1035.0, 1042.0, 2e6)]
    _write_csv(base2, d2); _run(b, d2)
    assert b.positions()

    # 第三天收盘跌破止损 → 排队 → 第四天开盘卖出
    base3 = base2 + [(1000.0, 1005.0, 940.0, 950.0, 3e6)]
    _write_csv(base3, d3)
    r3 = _run(b, d3)
    assert any("stop" in str(o.get("note", "")) for o in r3.orders), r3.summary()
    d4 = dt.date(2026, 1, 8)
    _write_csv(base3 + [(945.0, 950.0, 940.0, 945.0, 2e6)], d4)
    _run(b, d4)
    assert not b.positions()
    assert b.state["closed_trades"][-1]["exit_px"] == pytest.approx(945.0)


def test_stale_data_blocks_trading():
    old = dt.date(2026, 1, 5)
    _write_csv(_flat(300) + [_signal_bar()], old)
    b = _broker()
    r = _run(b, dt.date(2026, 2, 20))            # 数据是一个多月前的
    assert not r.orders and "过期" in " ".join(r.notes)
    assert not b.pending()


def test_idempotent_across_repeated_runs():
    d1 = dt.date(2026, 1, 5)
    _write_csv(_flat(300) + [_signal_bar()], d1)
    b = _broker()
    _run(b, d1)
    n1 = len(b.pending())
    r2 = _run(b, d1)              # 同一根 K 线再跑一次，不应再产生订单
    assert len(b.pending()) == n1
    assert any("幂等" in x for x in r2.blocked), r2.summary()


def test_circuit_breaker_blocks_new_entries():
    d1 = dt.date(2026, 1, 5)
    _write_csv(_flat(300) + [_signal_bar()], d1)
    rm = RiskManager(RISK)
    rm.begin(1_030_000, dt.date(2026, 1, 2))
    rm.end(1_030_000, dt.date(2026, 1, 2))        # 昨日 103 万 → 今天 100 万 = -2.9%，越过 2% 熔断线
    b = _broker()
    r = _run(b, d1)
    assert not b.pending()
    assert any("熔断" in x for x in r.blocked), r.summary()


def test_halt_file_stops_everything():
    d1 = dt.date(2026, 1, 5)
    _write_csv(_flat(300) + [_signal_bar()], d1)
    paths.halt_file().write_text("manual", encoding="utf-8")
    b = _broker()
    r = _run(b, d1)
    assert not b.pending() and "HALT" in r.risk


def test_dry_run_places_nothing():
    d1 = dt.date(2026, 1, 5)
    _write_csv(_flat(300) + [_signal_bar()], d1)
    b = _broker()
    r = _run(b, d1, dry_run=True)
    assert not b.pending()
    assert r.orders and r.orders[0]["status"] == "DRY_RUN"


def test_journal_is_written():
    d1 = dt.date(2026, 1, 5)
    _write_csv(_flat(300) + [_signal_bar()], d1)
    _run(_broker(), d1)
    fp = paths.out_dir() / "journal.csv"
    assert fp.exists() and "equity" in fp.read_text(encoding="utf-8-sig")


def test_partial_bar_is_dropped_during_session():
    """盘中跑（比如 10:30 JST）时 yfinance 会返回半根当日 K 线，必须丢掉。"""
    from zoneinfo import ZoneInfo
    from qbreak.trader import drop_partial_bar
    idx = pd.bdate_range(end=pd.Timestamp("2026-09-24"), periods=5)
    df = pd.DataFrame({"Open": 1, "High": 1, "Low": 1, "Close": 1, "Volume": 1}, index=idx)
    jst = ZoneInfo("Asia/Tokyo")
    mid = dt.datetime(2026, 9, 24, 10, 30, tzinfo=jst)            # 前場中
    assert len(drop_partial_bar(df, "JP", mid)) == 4
    post = dt.datetime(2026, 9, 24, 16, 0, tzinfo=jst)            # 收盘后
    assert len(drop_partial_bar(df, "JP", post)) == 5
    nxt = dt.datetime(2026, 9, 25, 7, 0, tzinfo=jst)              # 次日早上
    assert len(drop_partial_bar(df, "JP", nxt)) == 5
    # 美股：9/24 22:30 JST = 9/24 09:30 ET 开盘中 → 丢；9/25 07:00 JST = 9/24 18:00 ET 已收盘 → 留
    assert len(drop_partial_bar(df, "US", dt.datetime(2026, 9, 24, 22, 30, tzinfo=jst))) == 4
    assert len(drop_partial_bar(df, "US", dt.datetime(2026, 9, 25, 7, 0, tzinfo=jst))) == 5
