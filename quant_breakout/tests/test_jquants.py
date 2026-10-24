"""J-Quants V2 客户端：认证头、分页、限速、429 退避、接入检查（离线假 HTTP）。"""
import datetime as dt

import pytest

from qbreak.jquants import API, JQuants, JQuantsError, check, summarize


class FakeHTTP:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, params, headers):
        self.calls.append((url, dict(params), dict(headers)))
        path = url[len(API):]
        fn = self.routes.get(path)
        if fn is None:
            return 403, {"message": "This API is not available on your subscription"}
        return fn(params)


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("JQUANTS_API_KEY", raising=False)
    with pytest.raises(JQuantsError, match="JQUANTS_API_KEY"):
        JQuants()


def test_header_pagination_and_rate_limit():
    pages = {None: {"data": [{"Code": "72030"}], "pagination_key": "p2"},
             "p2": {"data": [{"Code": "67580"}]}}
    http = FakeHTTP({"/equities/master": lambda p: (200, pages[p.get("pagination_key")])})
    slept, t = [], [0.0]
    c = JQuants(api_key="k", plan="free", http=http, sleep=lambda s: slept.append(s), clock=lambda: t[0])
    rows = c.get("/equities/master", date="2025-01-06")
    assert [r["Code"] for r in rows] == ["72030", "67580"]
    assert all(h["x-api-key"] == "k" for _, _, h in http.calls)
    assert http.calls[1][1]["pagination_key"] == "p2" and http.calls[1][1]["date"] == "2025-01-06"
    assert slept and slept[0] == pytest.approx(60 / 5 * 1.05)    # Free：5 次/分，第二次请求前要等


def test_429_backoff_then_success():
    state = {"n": 0}

    def route(p):
        state["n"] += 1
        return (429, {"message": "Too Many Requests"}) if state["n"] == 1 else (200, {"data": [{"x": 1}]})
    slept = []
    c = JQuants(api_key="k", plan="premium", http=FakeHTTP({"/markets/calendar": route}),
                sleep=lambda s: slept.append(s), clock=lambda: 1e9)
    assert c.get("/markets/calendar") == [{"x": 1}] and 60 in slept


def test_check_reports_point_in_time_universe_and_delisted_history():
    today = dt.date(2026, 9, 24)

    def master(p):
        if p.get("date"):
            return 200, {"data": [{"Code": "72030"}, {"Code": "65020"}]}      # 当时还在上市的东芝
        return 200, {"data": [{"Code": "72030"}]}

    def daily(p):
        if p.get("code") == "65020":
            return 200, {"data": [{"Date": "2006-10-02", "Code": "65020", "C": 800.0}]}
        return 200, {"data": [{"Date": "2026-09-22", "Code": "72030", "C": 3000.0}]}
    http = FakeHTTP({"/equities/master": master, "/equities/bars/daily": daily,
                     "/indices/bars/daily/topix": lambda p: (200, {"data": [{"C": 3000}]})})
    c = JQuants(api_key="k", plan="premium", http=http, sleep=lambda s: None, clock=lambda: 1e9)
    r = check(c, today)
    assert r["key_ok"] and r["recent_daily_ok"] and r["delisted_since_probe"] == 1
    assert r["delisted_sample"] == "65020" and r["delisted_in_daily"] is True
    assert r["endpoints"]["/indices/bars/daily/topix"]["ok"] and not r["endpoints"]["/fins/dividend"]["ok"]
    txt = summarize(r)
    assert "无幸存者偏差" in txt and "k" not in txt.split("✓")[0]                # 不打印 API キー
    assert r["calls"] <= 9
