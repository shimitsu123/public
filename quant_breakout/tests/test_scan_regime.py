"""候补队列、市场状态、数据源降级、entry_scale。"""
import datetime as dt

import numpy as np
import pandas as pd

from conftest import make_frame
from qbreak import paths
from qbreak.brokers import PaperBroker
from qbreak.config import DataConfig, ExecConfig, RiskConfig, SizingConfig, StrategyParams
from qbreak.data import csv_name, dump_csv, load_universe
from qbreak.regime import Regime, apply_overlay, quant_regime
from qbreak.scan import scan, tag_breakouts
from qbreak.strategy import compute_indicators
from qbreak.trader import run_once
from qbreak.utils import write_json


def _flat_then_signal(n=300, px=1000.0, jump=1.03, volx=6.0, hi=1.002):
    rows = [(px, px * hi, px * 0.998, px, 1e6)] * n + [(px, px * jump * 1.001, px * 0.999, px * jump, 1e6 * volx)]
    return make_frame(rows)


def _random(n=400, seed=1, drift=0.0):
    rng = np.random.default_rng(seed)
    c = 1000 * np.exp(np.cumsum(rng.normal(drift, 0.02, n)))
    return make_frame([(c[i], c[i] * 1.01, c[i] * 0.99, c[i], 1e6) for i in range(n)])


P = StrategyParams()


def test_scan_ranks_triggered_first_and_flags_affordability():
    ind = {"SIG.T": compute_indicators(_flat_then_signal(), P),
           "RND.T": compute_indicators(_random(), P),
           "EXP.T": compute_indicators(_flat_then_signal(px=50_000.0), P)}   # 1 単元 = 500 万
    df = scan(ind, P, "JP", budget=340_000)
    assert df.iloc[0]["ticker"] == "SIG.T" and df.iloc[0]["status"] == "triggered"
    exp = df[df["ticker"] == "EXP.T"].iloc[0]
    assert not exp["affordable"] and exp["lot_cost"] == 5_150_000     # 51,500 × 100 股
    assert df["score"].is_monotonic_decreasing or df["status"].iloc[0] == "triggered"


def test_scan_us_pref_flags_price_over_100():
    ind = {"BIG": compute_indicators(_flat_then_signal(px=250.0), P)}
    df = scan(ind, P, "US", budget=1300)
    assert not df.iloc[0]["pref_ok"] and "单价" in df.iloc[0]["pref_note"]


def test_scan_and_todo_mark_true_breakout_display_only():
    """「真突破」= 收盘 > 过去 60 日最高价（不含当天）；只加展示字段，状态与排序不变。"""
    ind = {"SIG.T": compute_indicators(_flat_then_signal(), P),                       # 收 1030 > 箱顶 1002
           "INB.T": compute_indicators(_flat_then_signal(jump=1.005, hi=1.01), P)}    # 收 1005 < 箱顶 1010
    df = scan(ind, P, "JP", budget=340_000).set_index("ticker")
    assert (df["status"] == "triggered").all()
    assert bool(df.loc["SIG.T", "breakout"]) and df.loc["SIG.T", "to_box_top_pct"] == -2.7
    assert not bool(df.loc["INB.T", "breakout"]) and df.loc["INB.T", "to_box_top_pct"] == 0.5
    d = str(ind["SIG.T"].index[-1].date())
    todo = {"JP": [{"side": "BUY", "ticker": "SIG.T", "qty": 100, "signal_date": d},
                   {"side": "BUY", "ticker": "INB.T", "qty": 100, "signal_date": d},
                   {"side": "SELL", "ticker": "SIG.T", "qty": 100},
                   {"side": "BUY", "ticker": "1655.T", "qty": 5, "reason": "核心 ETF 调整"},
                   {"side": "BUY", "ticker": "NOPE.T", "qty": 100, "signal_date": d}], "FX": [], "US": []}
    out = tag_breakouts(todo, ind)["JP"]
    assert out[0]["breakout"] is True and out[0]["to_box_top_pct"] == -2.7
    assert out[1]["breakout"] is False and out[1]["to_box_top_pct"] == 0.5
    assert all("breakout" not in o for o in out[2:])                                  # 卖单、核心 ETF、没有行情的票不动


# ────────── 市场状态 ──────────
def _index(trend: float, vol: float, n=300):
    rng = np.random.default_rng(5)
    c = 30000 * np.exp(np.cumsum(rng.normal(trend, vol, n)))
    return make_frame([(c[i], c[i] * 1.005, c[i] * 0.995, c[i], 1e8) for i in range(n)])


def test_quant_regime_risk_on_and_off():
    on = quant_regime(_index(0.0008, 0.006), "JP")
    assert on.quant_label == "risk_on" and on.mult == 1.0
    off = quant_regime(_index(-0.003, 0.02), "JP")
    assert off.quant_label == "risk_off" and off.mult == 0.0
    assert quant_regime(None, "JP").quant_label == "unknown"


def test_overlay_from_market_report_caps_multiplier_and_expires():
    write_json(paths.home() / "market_regime.json",
               {"as_of": dt.date.today().isoformat(),
                "JP": {"action": "减仓观察", "crash_prob": 12},
                "US": {"action": "避险", "crash_prob": 30}})
    jp = apply_overlay(Regime("JP", "risk_on", 1.0))
    assert jp.mult == 0.5 and jp.crash_prob == 12
    us = apply_overlay(Regime("US", "risk_on", 1.0))
    assert us.mult == 0.0
    write_json(paths.home() / "market_regime.json",
               {"as_of": (dt.date.today() - dt.timedelta(days=5)).isoformat(),
                "JP": {"action": "避险"}})
    assert apply_overlay(Regime("JP", "risk_on", 1.0)).mult == 1.0     # 过期即忽略


# ────────── entry_scale ──────────
T = "9999.T"


def _csv_signal(day):
    df = _flat_then_signal(px=1000.0)
    df.index = pd.bdate_range(end=pd.Timestamp(day), periods=len(df)); df.index.name = "Date"
    (paths.sub("csv") / f"{T}.csv").write_text(df.to_csv(), encoding="utf-8")


def _run(b, day, scale):
    return run_once([T], b, StrategyParams(take_profit_pct=0, trailing_stop_pct=0,
                                            exit_on_macd_dead_cross=False),
                    RiskConfig(require_arm=False, max_order_value=1e9),
                    SizingConfig(position_pct=0.5, max_position_pct=1.0),
                    DataConfig(provider="csv", years=2, min_bars=100), market="JP",
                    today=day, exec_cfg=ExecConfig(market="JP", commission_pct=0, slippage_pct=0),
                    entry_scale=scale)


def test_entry_scale_zero_blocks_new_entries():
    d = dt.date(2026, 1, 5); _csv_signal(d)
    b = PaperBroker(initial_cash=1_000_000, exec_cfg=ExecConfig(market="JP", commission_pct=0, slippage_pct=0))
    r = _run(b, d, 0.0)
    assert r.signals == [T] and not b.pending()
    assert any("不开新仓" in x for x in r.blocked)


def test_entry_scale_half_halves_budget():
    d = dt.date(2026, 1, 5); _csv_signal(d)
    b = PaperBroker(initial_cash=1_000_000, exec_cfg=ExecConfig(market="JP", commission_pct=0, slippage_pct=0))
    _run(b, d, 0.5)
    assert b.pending()[0]["qty"] == 200          # 100 万×50%×0.5 / 1030 → 2 単元


# ────────── CSV 兜底数据源 ──────────
def test_dump_csv_roundtrip_including_index_symbols():
    data = {"^N225": _random(300), "JPY=X": _random(300, seed=2)}
    assert dump_csv(data) == 2
    assert (paths.sub("csv") / f"{csv_name('^N225')}.csv").exists()
    got = load_universe(["^N225"], DataConfig(provider="csv", years=2, min_bars=100))
    assert len(got["^N225"]) == 300
