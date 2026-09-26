"""qbreak/dashboard.py：偏向刻度（离翻转价位）、仓位构成、最上面一句的总结、日报（公开）只放消息汇总、Mac 页面放完整链路；
日报顶部出现「一眼看懂」、威胁明细折叠；run.py news 的整条路（不连网）。"""
import json

import pytest

from qbreak import dashboard as DB
from qbreak import news as NW


def _d(state="bull", dist=18.84, mult=0.5, phase="牛·稳固"):
    return {"equity_jpy": 1_000_000, "cash_jpy": 300_000, "cash_usd": 0, "usdjpy": 150, "core_units": {"1655.T": 100},
            "core_last": {"1655.T": 2000}, "positions": {"8306.T": {}},
            "extras": {"JP": {"regime": {"bullbear": {"state": state, "distance_pct": dist, "days": 300, "phase_label": phase},
                                         "final_mult": mult, "quant_label": "neutral", "quant_mult": 0.75},
                              "macro": {"fired": ["美 10Y 5.16% ≥ 5.0 → ×0.75"]}},
                       "US": {"regime": {"bullbear": {"state": "bull", "distance_pct": 11.8}}}}}


def test_lean_positions_and_text():
    pos, head, txt = DB.lean({"state": "bull", "distance_pct": 18.84, "days": 300})
    assert pos == 1.0 and head == "牛市" and "还要跌 15.9% 才翻转" in txt and "300 个交易日" in txt
    pos, _, txt = DB.lean({"state": "bear", "distance_pct": -6.0})
    assert pos == pytest.approx(-0.4) and "还要涨 6.4%" in txt
    assert DB.lean({})[0] is None


def test_exposure_parts():
    parts = {k: v for k, v, _ in DB.exposure(_d())}
    assert parts == {"个股": 500_000, "核心 ETF（1655）": 200_000, "现金": 300_000}
    assert DB.exposure({"equity_jpy": 0}) == []


def test_headline_summarises_direction_health_alerts():
    macro = {"health": {"score": 90, "tiles": [{"label": "美国 10 年期利率", "status": "warn"}, {"label": "VIX", "status": "good"}]}}
    h = DB.headline(_d(), macro, {"summary": {"n_alerts": 2}})
    assert h == "现在：日本偏多（牛市·牛·稳固），新仓只开 0.5 倍（防守）｜市场健康度 90 / 100（注意：美国 10 年期利率）｜经济威胁提醒 2 件"
    h2 = DB.headline(_d(phase=None, mult=1.0), {}, {})
    assert h2 == "现在：日本偏多（牛市），新仓全开（进攻）" and "，；" not in h2
    assert DB.headline(_d(state="bear", mult=0.0), {}, {"events": [{"alert": True}]}).endswith("暂停新仓（防守）｜经济威胁提醒 1 件")


def _events():
    it = [{"title": "米国、日本車に追加関税を発動", "link": "https://example.com/a?b=1&c=<x>", "time": "2026-09-26T11:00+09:00",
           "source": "ロイター", "publisher": "ロイター", "kind": "aggregator"}]
    import datetime as dt
    from qbreak.calendar_jp import JST
    return NW.analyze(it, {}, {"7203.T": "汽车·运输机"}, now=dt.datetime(2026, 9, 26, 12, 0, tzinfo=JST))


def test_public_render_has_no_headlines_but_mac_page_does():
    ev = _events()
    pub = DB.render(_d(), {}, {"summary": NW.summary(ev), "generated": "2026-09-26 12:00 JST"})
    assert "一眼看懂" in pub and "关税 / 贸易摩擦 / 制裁：1 件（提醒 1 件" in pub
    assert "追加関税" not in pub and "example.com" not in pub
    page = DB.page(_d(), {}, {"events": ev, "generated": "g", "sources": {"NHK 経済": 3, "FRB": "失败：TimeoutError"}}, "g")
    assert "追加関税を発動" in page and "https://example.com/a?b=1&amp;c=&lt;x&gt;" in page and 'http-equiv="refresh"' in page
    assert "提醒 1 件" in page and "受损方向的持仓 / 候补：7203.T" in page and "FRB ✗" in page


def test_report_puts_dashboard_on_top_and_folds_threat_details(isolated_home):
    from qbreak import report_unified as RU
    d = {"generated": "x", "sim": {}, "capital_jpy": 1e6, "equity_jpy": 1e6, "ret_pct": 0, "max_dd_pct": 0, "history": [[1, 1e6]],
         "config": {"stock_markets": ["JP"]}, "preview": True, "todo": {}, **{k: v for k, v in _d().items() if k == "extras"},
         "macro_now": {"health": {"score": 75, "counts": {"good": 3, "warn": 1}, "tiles": []}, "releases": []},
         "news": {"summary": NW.summary(_events()), "generated": "g"}}
    html = RU.render_unified_html(d)
    assert html.index("一眼看懂") < html.index("今天要做的事") and "健康度 75 / 100" in html
    assert "<details><summary><h2 style=\"display:inline\">大事件威胁指数的明细" in html and "追加関税" not in html


def test_cmd_news_offline(isolated_home, monkeypatch, capsys):
    import run
    from qbreak import macro_now as MN
    ev_items = [{"title": "米国、日本車に追加関税を発動", "link": "https://example.com/a", "time": None, "source": "ロイター",
                 "publisher": "ロイター", "kind": "aggregator"}]
    from qbreak.calendar_jp import now_jst
    ev_items[0]["time"] = now_jst().isoformat(timespec="minutes")
    monkeypatch.setattr(NW, "fetch_all", lambda *a, **k: (ev_items, {"ロイター": 1}))
    monkeypatch.setattr(NW, "sector_betas", lambda *a, **k: {})
    calls = []
    monkeypatch.setattr(NW, "notify_mac", lambda t, x: calls.append((t, x)) or True)
    monkeypatch.setattr(MN, "collect", lambda **k: {"generated": "g", "health": {"score": 80, "tiles": [], "counts": {}}, "releases": [],
                                                    "events": []})
    assert run.main(["news", "--page", "--notify"]) == 0
    out = capsys.readouterr().out
    assert "达到提醒线 1 件（新的 1 件）" in out and len(calls) == 1 and "关税" in calls[0][0]
    page = (isolated_home / "out" / "dashboard.html").read_text(encoding="utf-8")
    assert "追加関税を発動" in page and json.loads((isolated_home / "out" / "macro_now.json").read_text(encoding="utf-8"))["health_at"]
    assert json.loads((isolated_home / "cache" / "news" / "news.json").read_text(encoding="utf-8"))["events"][0]["alert"]
    assert run.main(["news", "--notify"]) == 0 and len(calls) == 1                  # 同一件事不再提醒


def test_panel_errors_are_shown_and_listed_as_missing():
    from qbreak import report_unified as RU
    html = DB.render(_d(), {"error": "RuntimeError: FRED 取不到"}, {"error": "TimeoutError: x"})
    assert "暂不可用：RuntimeError: FRED 取不到" in html and "暂不可用：TimeoutError: x" in html
    d = {"sim": {}, "history": [[1, 1e6]], "macro_now": {"error": "E1"}, "news": {"error": "E2"}}
    miss = RU.missing_items(d)
    assert any("市场健康度 / 新公布的数据：E1" in m for m in miss) and any("经济威胁消息：E2" in m for m in miss)

