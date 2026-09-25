"""一个账户（楽天）日报：只做日本个股时不显示换汇 / 美股栏；核心 ETF 用到的指数显示牛熊分界；候补队列；模拟期结束只重出报表。"""
import argparse

from qbreak import paths
from qbreak.report_unified import write_unified_report
from qbreak.unified import UnifiedConfig
from qbreak.utils import read_json, write_json


def _write(stock_markets, cash_usd=0.0, todo=None):
    cfg = UnifiedConfig(stock_markets=tuple(stock_markets), core={"1329.T": 0.5, "1655.T": 0.5},
                        core_index={"1329.T": "JP", "1655.T": "US"})
    write_json(paths.home() / "sim.json", {"mode": "unified", "start": "2026-09-28", "end": "2026-12-24",
                                           "capital_jpy": 1_000_000})
    write_json(paths.state_dir() / "unified_state.json",
               {"cash_jpy": 1_000_000, "cash_usd": cash_usd, "last_date": "2026-09-25",
                "history": [["2026-09-25", 1_000_000, 1_000_000, cash_usd, 150.0]],
                "core_units": {"1329.T": 0, "1655.T": 0}, "core_last": {"1329.T": 6800, "1655.T": 876}})
    bb = {"state": "bull", "since": "2025-05-19", "level": 6891.63, "distance_pct": 11.8}
    extras = {"JP": {"regime": {"label": "neutral", "final_mult": 0.5, "bullbear": dict(bb, level=55673.49)},
                     "macro": {"fired": []},
                     "watchlist": [{"ticker": "8801.T", "sector": "不动产", "status": "imminent", "score": 98.0,
                                    "close": 1501, "affordable": True, "tilt": 1.0}]}}
    if "US" not in stock_markets:
        extras["US"] = {"regime": {"bullbear": bb}, "core_only": ["1655.T"]}
    write_json(paths.out_dir() / "unified_today.json",
               {"todo": todo or {"JP": [{"side": "BUY", "ticker": "1655.T", "qty": 570, "type": "寄付成行"}],
                                 "FX": [], "US": []},
                "extras": extras, "config": cfg.to_dict(), "positions": {}})


def test_jp_only_hides_fx_and_us_and_shows_core_index_and_watchlist():
    _write(["JP"])
    html = write_unified_report().read_text(encoding="utf-8")
    assert "日间 换汇" not in html and "美股开盘" not in html
    assert "只用于核心 ETF 1655.T 的择时" in html and "6891.63" in html
    assert "8801.T" in html and "即将" in html
    assert "只做日本个股" in html and "JST" in html
    rd = read_json(paths.out_dir() / "report_data.json")
    assert rd["mode"] == "unified" and rd["markets"]["US"]["regime"]["bullbear"]["level"] == 6891.63   # 例行任务的旧路径
    assert rd["markets"]["JP"]["watchlist"][0]["ticker"] == "8801.T" and "markets.JP.watchlist" in rd["hint"]


def test_fx_section_uses_configured_spread_when_us_stocks_on_or_usd_left():
    _write(["JP", "US"])
    html = write_unified_report().read_text(encoding="utf-8")
    assert "价差按片道 3 銭估" in html and "美股开盘" in html and "一起排名" in html
    _write(["JP"], cash_usd=250.0)                         # 只做日本个股，但手上还有美元 → 仍显示换汇栏
    assert "日间 换汇" in write_unified_report().read_text(encoding="utf-8")


def test_sim_day_after_end_only_rebuilds_report():
    import run
    _write(["JP"])
    cfg = read_json(paths.home() / "sim.json")
    cfg["end"] = "2026-01-01"
    write_json(paths.home() / "sim.json", cfg)
    (paths.out_dir() / "report.html").unlink(missing_ok=True)
    assert run.cmd_sim_day(argparse.Namespace()) == 0          # 不取行情、不推进状态
    assert (paths.out_dir() / "report.html").exists()
    assert read_json(paths.state_dir() / "unified_state.json")["last_date"] == "2026-09-25"


def test_report_before_first_run_says_when_it_starts():
    write_json(paths.home() / "sim.json", {"mode": "unified", "start": "2026-09-28", "end": "2026-12-24",
                                           "capital_jpy": 1_000_000,
                                           "unified": {"stock_markets": ["JP"], "core": {"1655.T": 1.0},
                                                       "core_index": {"1655.T": "US"}, "core_mode": "split"}})
    html = write_unified_report().read_text(encoding="utf-8")
    assert "还没有运行过" in html and "2026-09-28" in html and "¥1,000,000" in html
    assert "个股 4×25%（只做日本个股" in html and "1655.T 1" in html and "None" not in html   # 规则取自 sim.json
