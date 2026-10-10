"""〔77〕C：特定口座的年内已实现损益与预计代扣（qbreak/tax_ytd.py；只展示与提醒）。"""
from types import SimpleNamespace

import pytest

from qbreak import tax_ytd as TY


def _st():
    return {
        "trades": [
            {"ticker": "7203.T", "market": "JP", "exit_date": "2026-10-05", "shares": 100, "exit_px": 3100, "pnl_jpy": 9000},
            {"ticker": "6758.T", "market": "JP", "exit_date": "2026-10-07", "shares": 100, "exit_px": 2000, "pnl_jpy": -4000},
            {"ticker": "AAPL", "market": "US", "exit_date": "2026-10-07", "shares": 1, "exit_px": 1, "pnl_jpy": 99999},
            {"ticker": "9984.T", "market": "JP", "exit_date": "2025-12-30", "shares": 100, "exit_px": 1, "pnl_jpy": 50000},
        ],
        "core_trades": [
            ["2026-10-01", "1545.T", "BUY", 1000, 240.0, 100.0],
            ["2026-10-06", "1545.T", "SELL", 500, 250.0, 50.0],       # 成本 = (240000 + 100) / 2 = 120050 → 损益 125000 − 50 − 120050 = 4900
        ],
    }


def test_realized_stock_and_core_moving_average():
    rows = TY.realized(_st())
    assert [(r["date"], r["kind"], r["ticker"]) for r in rows] == [
        ("2025-12-30", "stock", "9984.T"), ("2026-10-05", "stock", "7203.T"),
        ("2026-10-06", "core", "1545.T"), ("2026-10-07", "stock", "6758.T")]
    assert rows[2]["pnl"] == pytest.approx(4900)
    obj = SimpleNamespace(trades=_st()["trades"], core_trades=_st()["core_trades"])   # 引擎的状态对象也能读
    assert len(TY.realized(obj)) == 4


def test_ytd_nets_within_the_year_only():
    y = TY.ytd(_st(), 2026)
    assert y["gain"] == 9900 and y["n"] == 3 and y["stock_gain"] == 5000 and y["core_gain"] == 4900
    assert y["withheld"] == round(9900 * 0.20315)
    assert TY.ytd(_st(), 2026, upto="2026-10-05")["gain"] == 9000
    assert TY.ytd(_st(), 2025)["gain"] == 50000


def test_withheld_change_and_sale_effect_with_refund():
    # 10-06〜10-07：累计 9000 → 9900，多扣 900 × 20.315%
    assert TY.withheld_change(_st(), "2026-10-06", "2026-10-07") == pytest.approx(900 * 0.20315)
    # 再卖一笔亏 20000：累计 9900 → −10100 → 之前扣的全部退还
    assert TY.sale_effect(_st(), -20000, "2026-10-08") == pytest.approx(-9900 * 0.20315)
    assert TY.sale_effect(_st(), 1000, "2026-10-08") == pytest.approx(1000 * 0.20315)
    assert TY.withheld(-5) == 0


def test_bad_core_records_are_skipped_not_guessed():
    st = {"core_trades": [["2026-10-01", "1545.T", "SELL", 10, 250.0, 0.0]]}
    assert TY.realized(st) == []


def test_jq_live_cache_prune_keeps_recent_days():
    import datetime as dt
    from qbreak import jq_live
    d = jq_live.live_dir()
    for name in ("2025-01-01_fins.csv.gz", "2026-09-01_fins.csv.gz", "notes.csv.gz"):
        (d / name).write_bytes(b"x")
    assert jq_live.prune(dt.date(2026, 10, 10)) == 1
    assert sorted(p.name for p in d.glob("*.csv.gz")) == ["2026-09-01_fins.csv.gz", "notes.csv.gz"]


def test_ytd_flags_incomplete_core_records():
    st = {"core_trades": [["2026-10-01", "1545.T", "SELL", 10, 250.0, 0.0]]}
    assert TY.ytd(st, 2026)["incomplete"] == ["1545.T"]
    assert TY.ytd(_st(), 2026)["incomplete"] == []
