"""实盘 / 半自动 / 守护进程默认跟模拟盘同一档：资金、风控、股票池、个股开关、核心 ETF 都取自 var/sim.json。"""
import argparse
import json

import pandas as pd


def _args(**kw):
    d = dict(cash=None, max_order_value=None, position_pct=None, no_sim_config=False, core=False,
             core_ticker=None, no_macro=False)
    d.update(kw)
    return argparse.Namespace(**d)


def _write_sim(home, **us):
    cfg = {"start": "2026-09-24", "end": "2026-12-24", "markets": ["JP", "US"], "use_market_regime": True,
           "jp": {"initial_cash": 1_000_000, "universe": "default", "position_pct": 0.25, "max_positions": 4,
                  "breakout": True, "use_macro": False, "use_sector_tilt": False, "use_event_window": False,
                  "core": {"enabled": True, "ticker": "1329.T", "timing": True, "band_pct": 10.0},
                  "halt_dd_pct": 45.0, "tier": "aggressive"},
           "us": {"initial_cash": 6336.37, "universe": "default", "position_pct": 0.2, "max_positions": 5,
                  "breakout": False, "use_macro": False, "use_sector_tilt": False, "use_event_window": False,
                  "use_fx_scale": False,
                  "core": {"enabled": True, "ticker": "SPYM", "timing": True, "band_pct": 10.0},
                  "halt_dd_pct": 45.0, "tier": "aggressive", **us}}
    (home / "sim.json").write_text(json.dumps(cfg), encoding="utf-8")
    return cfg


def test_live_setup_follows_sim_tier(isolated_home):
    import run
    _write_sim(isolated_home)
    a = _args()
    cfg, mc, sizing, risk = run._live_setup(a, "JP", require_arm=True)
    assert mc["tier"] == "aggressive"
    assert (sizing.position_pct, sizing.max_positions, sizing.initial_cash) == (0.25, 4, 1_000_000)
    assert (risk.max_positions, risk.max_drawdown_pct, risk.require_arm) == (4, 45.0, True)
    assert a.max_order_value == risk.max_order_value == 1_100_000        # 核心 ETF 一笔可到权益 100%，不被上限挡住
    a2 = _args(max_order_value=500_000)
    run._live_setup(a2, "JP", require_arm=True)
    assert a2.max_order_value == 500_000                                  # 显式指定的上限不被覆盖
    _, _, sz3, _ = run._live_setup(_args(position_pct=0.05), "JP", require_arm=True)
    assert (sz3.position_pct, sz3.max_positions) == (0.05, 4)            # 实盘头两周可临时调小仓位


def test_live_setup_legacy_cli_mode(isolated_home):
    import run
    _write_sim(isolated_home)
    a = _args(no_sim_config=True)
    cfg, mc, sizing, risk = run._live_setup(a, "JP", require_arm=False)
    assert mc is None and cfg == {}
    assert (sizing.position_pct, sizing.max_positions, a.max_order_value) == (0.2, 5, 300_000)


def test_plan_inputs_respect_breakout_switch_and_core(isolated_home, monkeypatch):
    """_plan_inputs：模拟盘与实盘共用。US 段 breakout=false → 不做个股新仓，只按核心 ETF（SPYM）调仓。"""
    import run
    from qbreak.regime import Regime
    cfg = _write_sim(isolated_home)
    idx = pd.Series([100.0, 101.0], index=pd.to_datetime(["2026-09-22", "2026-09-23"]))
    monkeypatch.setattr(run, "_market_regime", lambda m, d: (Regime(market=m), idx))
    monkeypatch.setattr(run, "_bullbear", lambda m, d=None: {"state": "bear", "since": "2026-09-01"})
    monkeypatch.setattr(run, "_index_mult", lambda m, uni, today, base=None: base or {})
    p = run._params(_args(params=None), "US")
    P = run._plan_inputs("US", cfg["us"], cfg, None, pd.Timestamp("2026-09-24").date(), p)
    assert P.trade_uni == [] and len(P.uni) > 0
    assert P.core["ticker"] == "SPYM" and P.core["bear"] is True        # 熊市 → 指数仓位目标 0
    P2 = run._plan_inputs("JP", cfg["jp"], cfg, None, pd.Timestamp("2026-09-24").date(), p)
    assert P2.trade_uni == P2.uni and P2.core["ticker"] == "1329.T"
