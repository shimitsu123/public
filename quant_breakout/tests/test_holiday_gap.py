"""东证休市期间的日経225先物参考（qbreak/holiday_gap.py，只展示）与日报「09:00 日本开盘」写明成交日：
休市平日、只用成交日之前结束的 CME 交易日（不偷看）、分档、提示文字；休市日的日报写「今天东证休市 → 某日开盘成交」。"""
import datetime as dt
import json

import pandas as pd

from qbreak import holiday_gap as HG

HIST = {"normal": {"buckets": [{"lo": -1.0, "hi": -0.02, "label": "≤ −2%", "n": 158, "med": -1.88, "up3": 0.5, "dn3": 26.9},
                               {"lo": -0.02, "hi": 0.02, "label": "−2%〜+2%", "n": 4367, "med": 0.08, "up3": 1.7, "dn3": 1.2},
                               {"lo": 0.02, "hi": 1.0, "label": "≥ +2%", "n": 102, "med": 1.84, "up3": 27.4, "dn3": 0.8}]},
        "holiday": {"buckets": [{"lo": 0.02, "hi": 1.0, "label": "≥ +2%", "n": 22, "med": 1.70, "up3": 28.6, "dn3": 0.7}]}}


def _fetch(n225: dict, niy: dict):
    ser = {HG.IDX: pd.Series(n225), HG.FUT: pd.Series(niy)}
    for s in ser.values():
        s.index = pd.DatetimeIndex(s.index)
    return lambda t: ser[t]


def test_closed_weekdays_are_exchange_holidays_only():
    assert HG.closed_weekdays(dt.date(2026, 9, 18), dt.date(2026, 9, 24)) == [dt.date(2026, 9, 21), dt.date(2026, 9, 22), dt.date(2026, 9, 23)]
    assert HG.closed_weekdays(dt.date(2026, 9, 25), dt.date(2026, 9, 28)) == []                  # 普通周末
    assert HG.closed_weekdays(dt.date(2026, 12, 30), dt.date(2027, 1, 4)) == [dt.date(2026, 12, 31), dt.date(2027, 1, 1)]


def test_panel_uses_only_cme_sessions_before_the_fill_day():
    f = _fetch({"2026-09-17": 64000.0, "2026-09-18": 65000.0},
               {"2026-09-18": 65100.0, "2026-09-22": 66000.0, "2026-09-23": 67000.0, "2026-09-24": 90000.0})   # 9/24 那一段在开盘之后
    p = HG.panel("2026-09-18", dt.date(2026, 9, 24), fetch=f, hist=HIST)
    assert p["fill"] == "2026-09-24" and p["niy_date"] == "2026-09-23" and abs(p["pct"] - (67000 / 65000 - 1) * 100) < 0.01
    assert p["holiday"] and p["closed"] == ["2026-09-21", "2026-09-22", "2026-09-23"] and p["hist"]["label"] == "≥ +2%"
    h = HG.html(p)
    assert "★ 其间东证休市 09/21（月）、09/22（火）、09/23（水）" in h and "+3.08%" in h and "≥ 3%：个股买单" in h
    assert "高开 3% 以上的票平均 28.6%" in h and "只展示，交易规则不变" in h


def test_panel_normal_day_and_missing_data():
    f = _fetch({"2026-09-28": 65877.62}, {"2026-09-28": 65900.0})
    p = HG.panel("2026-09-28", dt.date(2026, 9, 29), fetch=f, hist=HIST)
    assert not p["holiday"] and p["hist"]["label"] == "−2%〜+2%" and "★" not in HG.html(p) and "≥ 3%" not in HG.html(p)
    assert HG.panel("2026-09-25", dt.date(2026, 9, 29), fetch=f, hist=HIST) is None             # ^N225 没有 bar_date 那天
    assert HG.panel(None, dt.date(2026, 9, 29), fetch=f) is None and HG.html(None) == ""

    def boom(t):
        raise RuntimeError("net")
    assert HG.panel("2026-09-28", dt.date(2026, 9, 29), fetch=boom) is None


def test_report_names_the_fill_day_and_holiday(isolated_home, monkeypatch):
    from qbreak import report_unified as RU
    d = {"generated": "x", "sim": {}, "capital_jpy": 1e6, "equity_jpy": 1e6, "ret_pct": 0, "max_dd_pct": 0, "history": [[1, 1e6]],
         "config": {"stock_markets": ["JP"]}, "bar_date": "2026-10-09",
         "todo": {"JP": [{"side": "BUY", "ticker": "8035.T", "qty": 100, "type": "寄付指値", "limit": 1030.0}]},
         "jp_futures": {"bar_date": "2026-10-09", "fill": "2026-10-13", "closed": ["2026-10-12"], "n225": 65000.0, "niy": 63000.0,
                        "niy_date": "2026-10-12", "pct": -3.08, "holiday": True, "hist": None}}
    monkeypatch.setattr(RU, "now_jst", lambda: dt.datetime(2026, 10, 12, 7, 0))
    html = RU.render_unified_html(d)
    assert "10/13（火）09:00 日本开盘（寄付）" in html
    assert "今天 10/12（月）东证休市：上面的单在 10/13（火）开盘成交" in html
    assert "★ 其间东证休市 10/12（月）" in html and "≤ −3%" in html
    monkeypatch.setattr(RU, "now_jst", lambda: dt.datetime(2026, 10, 13, 7, 0))
    html = RU.render_unified_html(d)
    assert "10/13（火）09:00 日本开盘（寄付）" in html and "东证休市：上面的单" not in html
    json.dumps(d, ensure_ascii=False)
