"""风控测试。重点是原版那个"永远不会触发的熔断"。"""
import datetime as dt

from qbreak import paths
from qbreak.config import RiskConfig
from qbreak.risk import RiskManager


def test_circuit_breaker_uses_previous_session_equity():
    """原版拿"今天第一次运行时的权益"当基准，而程序每天只跑一次 → 亏损恒为 0，
    熔断永远不触发。正确做法是用上一交易日收盘权益。"""
    rm = RiskManager(RiskConfig(daily_max_loss_pct=2.0))
    d1, d2 = dt.date(2026, 1, 5), dt.date(2026, 1, 6)
    rm.begin(1_000_000, d1)
    rm.end(1_000_000, d1)                       # 昨日收盘权益 = 100 万

    rm2 = RiskManager(RiskConfig(daily_max_loss_pct=2.0))
    dec = rm2.begin(975_000, d2)                # 今天 -2.5%
    assert dec.daily_loss_pct < -2.0
    assert dec.allow_open is False and dec.halted is False   # 只平不开，不是 HALT


def test_small_loss_does_not_trip():
    rm = RiskManager(RiskConfig(daily_max_loss_pct=2.0))
    rm.begin(1_000_000, dt.date(2026, 1, 5))
    rm.end(1_000_000, dt.date(2026, 1, 5))
    dec = RiskManager(RiskConfig(daily_max_loss_pct=2.0)).begin(990_000, dt.date(2026, 1, 6))
    assert dec.allow_open is True


def test_max_drawdown_writes_halt_file():
    cfg = RiskConfig(max_drawdown_pct=20.0, daily_max_loss_pct=99.0)
    rm = RiskManager(cfg)
    rm.begin(1_000_000, dt.date(2026, 1, 5))
    rm.end(1_000_000, dt.date(2026, 1, 5))
    dec = RiskManager(cfg).begin(750_000, dt.date(2026, 6, 1))
    assert dec.halted and paths.halt_file().exists()
    # HALT 必须人工解除，重启程序不会自动放行
    assert RiskManager(cfg).begin(760_000, dt.date(2026, 6, 2)).halted


def test_halt_can_be_reset_manually():
    cfg = RiskConfig(max_drawdown_pct=20.0, daily_max_loss_pct=99.0)
    rm = RiskManager(cfg)
    rm.begin(1_000_000, dt.date(2026, 1, 5)); rm.end(1_000_000, dt.date(2026, 1, 5))
    RiskManager(cfg).begin(700_000, dt.date(2026, 6, 1))
    rm2 = RiskManager(cfg)
    rm2.reset_halt()
    assert not paths.halt_file().exists()
    assert not rm2.st.halted_reason


def test_consecutive_losses_trip_halt():
    cfg = RiskConfig(max_consecutive_losses=3, daily_max_loss_pct=99.0, max_drawdown_pct=99.0)
    rm = RiskManager(cfg)
    rm.begin(1_000_000, dt.date(2026, 1, 5))
    for _ in range(3):
        rm.on_trade_closed(-1000)
    assert RiskManager(cfg).begin(1_000_000, dt.date(2026, 1, 6)).halted
    # 一笔盈利就清零
    rm3 = RiskManager(cfg)
    rm3.reset_halt()
    rm3.on_trade_closed(-1); rm3.on_trade_closed(+1)
    assert rm3.st.consecutive_losses == 0


def test_order_limits():
    cfg = RiskConfig(max_order_value=300_000, max_positions=3, max_new_positions_per_day=2)
    rm = RiskManager(cfg)
    rm.begin(1_000_000, dt.date(2026, 1, 5))
    assert rm.check_order(400_000, 0)[0] is False
    assert rm.check_order(100_000, 3)[0] is False
    rm.on_open(); rm.on_open()
    assert rm.check_order(100_000, 0)[0] is False    # 当日开仓数已满


def test_halt_file_alone_blocks():
    paths.halt_file().write_text("manual", encoding="utf-8")
    dec = RiskManager(RiskConfig()).begin(1_000_000, dt.date(2026, 1, 5))
    assert dec.halted and not dec.allow_open


def test_risk_state_is_per_market():
    """¥100 万的日本株账户和 $6,000 的美股账户共用峰值会把美股误判成 -99% 回撤。"""
    jp = RiskManager(RiskConfig(), market="JP")
    jp.begin(1_000_000, dt.date(2026, 1, 5)); jp.end(1_000_000, dt.date(2026, 1, 5))
    us = RiskManager(RiskConfig(), market="US")
    dec = us.begin(6_336, dt.date(2026, 1, 5))
    assert not dec.halted and dec.allow_open
    assert jp.path != us.path and jp.halt_file() != us.halt_file()


def test_auto_halt_is_per_market_but_global_halt_blocks_all():
    cfg = RiskConfig(max_drawdown_pct=20.0, daily_max_loss_pct=99.0)
    us = RiskManager(cfg, market="US")
    us.begin(10_000, dt.date(2026, 1, 5)); us.end(10_000, dt.date(2026, 1, 5))
    assert RiskManager(cfg, market="US").begin(7_000, dt.date(2026, 2, 1)).halted
    assert (paths.home() / "HALT_US").exists() and not paths.halt_file().exists()
    assert not RiskManager(cfg, market="JP").begin(1_000_000, dt.date(2026, 2, 1)).halted
    paths.halt_file().write_text("manual", encoding="utf-8")
    assert RiskManager(cfg, market="JP").begin(1_000_000, dt.date(2026, 2, 2)).halted
