"""日报：从 journal + 模拟盘状态构建数据，渲染成可点击的 HTML。"""
import datetime as dt
import json

import pandas as pd

from qbreak import paths
from qbreak.brokers import PaperBroker
from qbreak.config import DataConfig, ExecConfig, RiskConfig, SizingConfig, StrategyParams
from qbreak.report import build_data, render_html, write_report
from qbreak.trader import run_once
from qbreak.utils import write_json

T = "9999.T"
P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=False)
EX = ExecConfig(market="JP", commission_pct=0, slippage_pct=0)


def _csv(bars, last):
    idx = pd.bdate_range(end=pd.Timestamp(last), periods=len(bars))
    df = pd.DataFrame(bars, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)
    df.index.name = "Date"
    (paths.sub("csv") / f"{T}.csv").write_text(df.to_csv(), encoding="utf-8")


def _run(b, day):
    return run_once([T], b, P, RiskConfig(require_arm=False, max_order_value=1e9),
                    SizingConfig(position_pct=0.5, max_position_pct=1.0),
                    DataConfig(provider="csv", years=2, min_bars=100),
                    market="JP", today=day, exec_cfg=EX)


def test_report_pipeline_three_days():
    write_json(paths.home() / "sim.json", {"start": "2026-01-05", "end": "2026-04-05",
               "markets": ["JP"], "jp": {"initial_cash": 1_000_000}})
    flat = [(1000.0, 1002.0, 998.0, 1000.0, 1e6)] * 300
    sig = (1000.0, 1031.0, 999.0, 1030.0, 6e6)
    b = PaperBroker(initial_cash=1_000_000, exec_cfg=EX, market="JP")
    _csv(flat + [sig], dt.date(2026, 1, 5)); _run(b, dt.date(2026, 1, 5))            # 信号
    _csv(flat + [sig, (1040.0, 1045.0, 1035.0, 1042.0, 2e6)], dt.date(2026, 1, 6))
    _run(b, dt.date(2026, 1, 6))                                                    # 09:00 成交
    _csv(flat + [sig, (1040.0, 1045.0, 1035.0, 1042.0, 2e6), (1050.0, 1060.0, 1045.0, 1058.0, 2e6)],
         dt.date(2026, 1, 7))
    _run(b, dt.date(2026, 1, 7))                                                    # 浮盈

    data = build_data(["JP"])
    m = data["markets"]["JP"]
    assert [d["date"] for d in m["days"]] == ["2026-01-05", "2026-01-06", "2026-01-07"]
    d2 = m["days"][1]
    assert d2["trades"] and d2["trades"][0]["time"] == "09:00 JST"                  # 几点几分
    assert d2["trades"][0]["side"] == "BUY" and d2["trades"][0]["px"] == 1040.0
    assert m["days"][2]["pnl"] > 0 and m["summary"]["equity"] > 1_000_000
    assert m["days"][0]["signals"] == [T]

    html = render_html(data)
    assert "<title>突破策略模拟盘</title>" in html
    assert "09:00 JST" in html and "2026-01-06" in html
    assert "prefers-color-scheme" in html and "color-scheme:dark" in html
    hp, jp = write_report(["JP"])
    assert hp.exists() and json.loads(jp.read_text(encoding="utf-8"))["markets"]["JP"]["days"]


def test_report_empty_state_renders():
    write_json(paths.home() / "sim.json", {"start": "2026-01-05", "end": "2026-04-05",
               "markets": ["JP", "US"], "jp": {"initial_cash": 1_000_000}, "us": {}})
    data = build_data()
    assert data["markets"]["JP"]["days"] == [] and data["markets"]["US"]["summary"]["days"] == 0
    html = render_html(data)
    assert "尚无交易日数据" in html or "__DATA__" not in html


def test_report_escapes_script_terminator():
    write_json(paths.home() / "sim.json", {"markets": ["JP"], "jp": {"initial_cash": 1}})
    data = build_data(["JP"]); data["sim"]["note"] = "</script><b>x</b>"
    assert "</script><b>" not in render_html(data).split("const DATA")[1].split(";")[0]
