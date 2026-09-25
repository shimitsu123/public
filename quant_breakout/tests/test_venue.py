"""成交市场（venue）与账户标签分开：美股指数仓位放在东证（日元账户）时，风控 / 流水按账户记，日报按日元显示。"""
import argparse
import datetime as dt
import json

import pandas as pd

from qbreak import paths
from qbreak.brokers import PaperBroker
from qbreak.config import DataConfig, ExecConfig, RiskConfig, SizingConfig, StrategyParams
from qbreak.report import build_data
from qbreak.trader import run_once
from qbreak.utils import read_json, write_json

T = "1655.T"
P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=False)


def _csv(bars, last):
    idx = pd.bdate_range(end=pd.Timestamp(last), periods=len(bars))
    df = pd.DataFrame(bars, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)
    df.index.name = "Date"
    (paths.sub("csv") / f"{T}.csv").write_text(df.to_csv(), encoding="utf-8")


def test_run_once_books_under_account_label_not_venue():
    ex = ExecConfig.for_market("JP", "tachibana")
    b = PaperBroker(initial_cash=1_000_000, exec_cfg=ex, market="JP",
                    state_file=paths.state_dir() / "paper_state_US.json")
    _csv([(8800.0, 8820.0, 8780.0, 8800.0, 1e6)] * 300, dt.date(2026, 9, 24))
    core = {"ticker": T, "bear": False, "buffer_pct": 0.0, "band_pct": 10.0,
            "buy_fee_tiers": [[1_000_000, 341.0]], "sell_fee_tiers": [[1_000_000, 341.0]], "slip_pct": 0.02, "lot": 10}
    res = run_once([], b, P, RiskConfig(require_arm=False, max_order_value=1e9), SizingConfig(position_pct=0.01),
                   DataConfig(provider="csv", years=2, min_bars=100), market="JP", account="US",
                   today=dt.date(2026, 9, 25), exec_cfg=ex, core=core)
    assert [o["ticker"] for o in res.orders] == [T] and res.orders[0]["qty"] % 10 == 0   # 1655 以 10 口为单位
    j = pd.read_csv(paths.out_dir() / "journal.csv", encoding="utf-8-sig")
    assert list(j["market"]) == ["US"]
    assert (paths.state_dir() / "risk_state_US.json").exists()
    assert not (paths.state_dir() / "risk_state_JP.json").exists()
    assert (paths.state_dir() / "paper_state_US.json").exists()


def test_report_shows_jpy_account_for_us_sleeve_on_tse():
    write_json(paths.home() / "sim.json", {"start": "2026-09-25", "end": "2026-12-24", "capital_jpy": 1_000_000,
               "markets": ["US"], "us": {"initial_cash": 1_000_000, "venue": "JP", "broker": "tachibana"}})
    pd.DataFrame([{"date": "2026-09-26", "market": "US", "bar_date": "2026-09-25", "equity": 1_010_000,
                   "cash": 10_000, "positions": "1655.T:110", "orders": 0, "signals": "", "risk": ""}]
                 ).to_csv(paths.out_dir() / "journal.csv", index=False, encoding="utf-8-sig")
    (paths.out_dir() / "fx.csv").write_text("date,fx_date,usdjpy\n2026-09-26,2026-09-25,150.0\n", encoding="utf-8")
    d = build_data(["US"])["markets"]["US"]
    assert d["currency"] == "JPY" and d["days"][0]["fx"] is None          # 不再按美元折日元
    fx = d["fx"]
    assert fx["jpy_account"] and fx["exposure_jpy"] == 1_000_000
    up = next(s for s in fx["scenarios"] if s["shock_pct"] == 5.0)
    assert up["equity_jpy"] == 10_000 + 1_000_000 * 1.05 and up["usdjpy"] == 157.5


def test_sim_tier_venue_change_requires_reset_and_archives_old_sleeve():
    import run
    write_json(paths.home() / "sim.json", {"start": "2026-09-24", "end": "2026-12-24", "capital_jpy": 1_000_000,
               "markets": ["JP", "US"], "jp": {"initial_cash": 1_000_000, "position_pct": 0.25, "max_positions": 4},
               "us": {"initial_cash": 6336.37, "fx_start": 157.8, "position_pct": 0.2, "max_positions": 5,
                      "breakout": False, "core": {"enabled": True, "ticker": "SPYM"}}})
    write_json(paths.state_dir() / "paper_state_US.json", {"cash": 19.4, "positions": {"SPYM": {"qty": 70}}})
    write_json(paths.state_dir() / "position_book.json", {"SPYM": {"peak": 90.5}, "7203.T": {"peak": 3000}})
    pd.DataFrame([{"date": "2026-09-24", "market": m, "bar_date": "2026-09-23", "equity": 1, "cash": 1}
                  for m in ("JP", "US")]).to_csv(paths.out_dir() / "journal.csv", index=False, encoding="utf-8-sig")
    ns = argparse.Namespace(tier="aggressive", markets="US", reset=False)
    assert run.cmd_sim_tier(ns) == 2                                          # 不加 --reset 拒绝
    assert read_json(paths.home() / "sim.json")["us"]["core"]["ticker"] == "SPYM"
    ns.reset = True
    assert run.cmd_sim_tier(ns) == 0
    cfg = read_json(paths.home() / "sim.json")
    assert (cfg["us"]["venue"], cfg["us"]["core"]["ticker"], cfg["us"]["initial_cash"]) == ("JP", "1655.T", 1_000_000)
    assert "fx_start" not in cfg["us"]
    arch = next((paths.home() / "archive").iterdir())
    assert (arch / "paper_state_US.json").exists() and not (paths.state_dir() / "paper_state_US.json").exists()
    assert list(pd.read_csv(paths.out_dir() / "journal.csv", encoding="utf-8-sig")["market"]) == ["JP"]
    assert list(pd.read_csv(arch / "journal.csv", encoding="utf-8-sig")["market"]) == ["US"]
    assert set(read_json(paths.state_dir() / "position_book.json")) == {"7203.T"}


def test_sim_unify_archives_sleeves_and_writes_one_account_config():
    import run
    write_json(paths.home() / "sim.json", {"start": "2026-09-24", "end": "2026-12-24", "capital_jpy": 1_000_000,
               "markets": ["JP", "US"], "jp": {"initial_cash": 1_000_000, "broker": "tachibana"},
               "us": {"initial_cash": 1_000_000, "broker": "tachibana", "venue": "JP"}})
    write_json(paths.state_dir() / "paper_state_JP.json", {"cash": 1_000_000, "positions": {}, "pending": [{"ticker": "1329.T"}]})
    pd.DataFrame([{"date": "2026-09-24", "market": "JP", "bar_date": "2026-09-24", "equity": 1, "cash": 1}]
                 ).to_csv(paths.out_dir() / "journal.csv", index=False, encoding="utf-8-sig")
    ns = argparse.Namespace(capital=None, stock_markets="JP,US", core="1329.T:0.5,1655.T:0.5", core_mode="split",
                            position_pct=0.25, max_positions=4, start="2026-09-28", force=False)
    assert run.cmd_sim_unify(ns) == 0
    cfg = read_json(paths.home() / "sim.json")
    u = cfg["unified"]
    assert cfg["mode"] == "unified" and cfg["capital_jpy"] == 1_000_000 and cfg["start"] == "2026-09-28"
    assert u["core"] == {"1329.T": 0.5, "1655.T": 0.5} and u["core_index"] == {"1329.T": "JP", "1655.T": "US"}
    assert u["stock_markets"] == ["JP", "US"] and u["broker"] == "rakuten"
    assert cfg["jp"]["broker"] == cfg["us"]["broker"] == "rakuten"
    assert not (paths.state_dir() / "paper_state_JP.json").exists()
    assert run.cmd_sim_unify(ns) == 2                                    # 已是一个账户模式：不加 --force 不重开
    c = run._unified_cfg(cfg)
    assert c.fx_before_jp_open and c.fx_spread_yen == 0.03 and c.max_positions == 4


def test_per_market_live_signal_daemon_refuse_in_unified_mode(capsys):
    import run
    write_json(paths.home() / "sim.json", {"mode": "unified", "start": "2026-09-28", "end": "2026-12-24",
               "capital_jpy": 1_000_000, "jp": {"initial_cash": 1_000_000, "position_pct": 0.25, "max_positions": 4}})
    ns = argparse.Namespace(market="JP", no_sim_config=False)
    assert run.cmd_signal(ns) == 2 and run.cmd_daemon(ns) == 2 and run._live_common(ns, live=True) == 2
    assert "一个账户" in capsys.readouterr().out
    ns.no_sim_config = True                                             # 显式按命令行参数：不拦
    assert run._refuse_unified(ns) is False
