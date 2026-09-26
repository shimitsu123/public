"""顶部/出货过滤、相对强度、决算回避、climax 离场、汇率倍数。"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from conftest import make_frame, make_indicator_frame
from qbreak.brokers import PaperBroker
from qbreak.config import BacktestConfig, DataConfig, ExecConfig, RiskConfig, SizingConfig, StrategyParams
from qbreak.engine import run_backtest
from qbreak.events import FakeEarnings, trading_days_until
from qbreak.strategy import compute_indicators, rsi
from qbreak.trader import Position, exit_reason
from qbreak import paths

FLAT = (100.0, 101.0, 99.0, 100.0, 1e6)


def _signal_frame(n=300, px=1000.0, last=None):
    rows = [(px, px * 1.002, px * 0.998, px, 1e6)] * n + [last or (px, px * 1.031, px * 0.999, px * 1.03, 6e6)]
    return make_frame(rows)


def test_rsi_bounds_and_direction():
    up = pd.Series(np.linspace(100, 200, 60)); dn = pd.Series(np.linspace(200, 100, 60))
    assert rsi(up, 14).iloc[-1] > 90 and rsi(dn, 14).iloc[-1] < 10


def test_base_signal_still_fires_with_filters_off():
    ind = compute_indicators(_signal_frame(), StrategyParams())
    assert bool(ind["entry"].iloc[-1])


def test_upper_shadow_filter_blocks_blowoff_bar():
    # 信号日冲高回落：高 1100、收 1030（上影 70 / 实体 30 > 2）
    blow = (1000.0, 1100.0, 999.0, 1030.0, 6e6)
    p_off = StrategyParams(); p_on = StrategyParams(max_upper_shadow_ratio=2.0)
    assert bool(compute_indicators(_signal_frame(last=blow), p_off)["entry"].iloc[-1])
    assert not bool(compute_indicators(_signal_frame(last=blow), p_on)["entry"].iloc[-1])


def test_extension_and_rsi_filters_block_overextended():
    # 先横盘 300 天，再连拉 8 天（RSI 与伸展度都很高），最后一根仍满足四条件时应被顶部过滤拦下
    rows = [(1000.0, 1002.0, 998.0, 1000.0, 1e6)] * 300
    px = 1000.0
    for _ in range(8):
        px *= 1.02; rows.append((px / 1.02, px * 1.002, px / 1.02 * 0.999, px, 2e6))
    df = make_frame(rows)
    ind = compute_indicators(df, StrategyParams(max_ext_ma20_pct=8.0, max_rsi=70.0))
    assert float(ind["ext_ma20_pct"].iloc[-1]) > 8 and float(ind["rsi"].iloc[-1]) > 70
    assert not bool(ind["entry"].iloc[-1])


def test_distribution_days_counted_and_block():
    rows = [(1000.0, 1002.0, 998.0, 1000.0, 1e6)] * 280
    # 5 个出货日：收跌 0.5% 且放量
    for i in range(5):
        rows.append((1000.0, 1001.0, 990.0, 995.0, 1e6 * (1.5 + i)))
        rows.append((995.0, 1005.0, 994.0, 1000.0, 1e6))
    rows.append((1000.0, 1031.0, 999.0, 1030.0, 6e6))
    df = make_frame(rows)
    ind = compute_indicators(df, StrategyParams(max_distribution_days=4))
    assert int(ind["dist_days"].iloc[-1]) >= 4
    assert not bool(ind["entry"].iloc[-1])


def test_relative_strength_requires_index():
    df = _signal_frame()
    idx_strong = pd.Series(np.linspace(1000, 1500, len(df)), index=df.index)   # 指数大涨，个股横盘 → 跑输
    p = StrategyParams(min_rs_pct=0.0)
    assert not bool(compute_indicators(df, p, idx_strong)["entry"].iloc[-1])
    assert bool(compute_indicators(df, p, None)["entry"].iloc[-1])              # 无指数 → 跳过过滤


def test_climax_exit_in_engine():
    rows = [FLAT] * 5 + [FLAT, (100, 101, 99, 100, 1e6), (100, 112, 100, 111, 1e6),
                         (111, 115, 108, 109, 4e6)] + [(109, 110, 108, 109, 1e6)] * 3   # 第 8 根：高位放量陰線
    df = make_indicator_frame(rows, entries={5})
    df["climax"] = False; df.loc[df.index[8], "climax"] = True
    bt = BacktestConfig.for_market("JP"); bt.exec_cfg.slippage_pct = 0; bt.exec_cfg.commission_pct = 0
    bt.exec_cfg.max_entry_gap_pct = 0
    p = StrategyParams(stop_loss_pct=50, take_profit_pct=0, trailing_stop_pct=0,
                       exit_on_macd_dead_cross=False, exit_on_climax=True, climax_min_gain_pct=5.0)
    res = run_backtest({"A.T": df}, p, bt)
    assert res.trades.iloc[0]["reason"] == "climax"
    p2 = StrategyParams(**{**p.to_dict(), "exit_on_climax": False})
    assert run_backtest({"A.T": df}, p2, bt).trades.iloc[0]["reason"] == "end"


def test_exit_reason_orders_climax_and_pre_earnings():
    p = StrategyParams(exit_on_climax=True, climax_min_gain_pct=5, exit_before_earnings=True,
                       exit_on_macd_dead_cross=False)
    pos = Position("A.T", 100, 1000.0, peak=1100.0, stop_px=930.0)
    assert exit_reason(p, pos, 1080.0, False, 930, -1e9, 1e9, climax=True).startswith("climax")
    assert exit_reason(p, pos, 1020.0, False, 930, -1e9, 1e9, climax=True) is None   # 浮盈不足 5%
    assert exit_reason(p, pos, 1020.0, False, 930, -1e9, 1e9, earnings_in_days=1).startswith("pre_earnings")
    assert exit_reason(p, pos, 1020.0, False, 930, -1e9, 1e9, earnings_in_days=5) is None


def test_trading_days_until_skips_weekends():
    assert trading_days_until(dt.date(2026, 9, 28), dt.date(2026, 9, 24)) == 2   # 木→月：金、月


def test_earnings_blackout_blocks_entry(tmp_path):
    from qbreak.trader import run_once
    T = "9999.T"
    idx = pd.bdate_range(end=pd.Timestamp("2026-01-05"), periods=301)
    df = _signal_frame(300); df.index = idx; df.index.name = "Date"
    (paths.sub("csv") / f"{T}.csv").write_text(df.to_csv(), encoding="utf-8")
    p = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=False,
                       earnings_blackout_days=3)
    ex = ExecConfig(market="JP", commission_pct=0, slippage_pct=0)
    b = PaperBroker(initial_cash=1_000_000, exec_cfg=ex)
    fake = FakeEarnings({T: dt.date(2026, 1, 7)})          # 2 个交易日后决算
    r = run_once([T], b, p, RiskConfig(require_arm=False, max_order_value=1e9),
                 SizingConfig(position_pct=0.5, max_position_pct=1.0),
                 DataConfig(provider="csv", years=2, min_bars=100), market="JP",
                 today=dt.date(2026, 1, 5), exec_cfg=ex, earnings=fake)
    assert r.signals == [T] and not b.pending()
    assert any("决算前" in x for x in r.blocked) and fake.calls == [T]
    # 决算很远 → 正常排队
    b2 = PaperBroker(initial_cash=1_000_000, exec_cfg=ex, state_file=tmp_path / "s2.json")
    run_once([T], b2, p, RiskConfig(require_arm=False, max_order_value=1e9),
             SizingConfig(position_pct=0.5, max_position_pct=1.0),
             DataConfig(provider="csv", years=2, min_bars=100), market="JP",
             today=dt.date(2026, 1, 5), exec_cfg=ex, earnings=FakeEarnings({T: dt.date(2026, 2, 20)}))
    assert b2.pending()


def test_fx_spread_in_us_exec_config():
    ex = ExecConfig.for_market("US")
    assert ex.fx_spread_pct > 0 and ex.tax_pct == pytest.approx(20.315)
