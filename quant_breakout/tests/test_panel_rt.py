"""确认框的立花实时价（2026-10-17 用户：「想定时取得的话用yahoo，下单的时候在确认页面的时候用立花能看到实时价格 k线也可以更新到那时候」）：
/api/quotes?rt=票 → 盘中登录立花本番只读取一次（假的券商；测试里绝不登录真的立花），那一行 src="rt"、预计收益按它算、K 线今天这一根用它；
60 秒内同一只不再登录；没取成 60 秒内不再试；盘外不取；dry-run 账本不取；定时的现价（没有 rt）照旧 Yahoo。"""
import datetime as dt
import os

import pytest

from qbreak import panel
from qbreak import rt_quotes as RT
from qbreak.calendar_jp import JST

from test_manual_core import AT, _pbook
from test_panel_quotes import _fetch


class _B:
    def __init__(self, log, rows=None, fail=None):
        self.log, self.rows, self.fail = log, rows if rows is not None else {"7203.T": {"price": 2700.0, "open": 2610.0, "high": 2710.0, "low": 2600.0}}, fail

    def login(self):
        self.log.append(("login", self.purpose[0]))
        if self.fail:
            raise RuntimeError(self.fail)

    def quote_detail(self, ts):
        self.log.append(("quote", sorted(ts)))
        return {t: v for t, v in self.rows.items() if t in ts}

    def logout(self):
        self.log.append(("logout",))


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    panel._QUOTE_CACHE.clear()
    panel._RT.update(rows={}, fail=-1e9, why=None, flight=None)
    monkeypatch.setenv(RT.ENV, "1")
    yield
    panel._RT.update(rows={}, fail=-1e9, why=None, flight=None)
    panel._QUOTE_CACHE.clear()


def _make(monkeypatch, log, **kw):
    monkeypatch.setattr(panel, "_RT_MAKE", lambda: _B(log, **kw))


def test_rt_row_uses_tachibana_price_for_the_dialog_and_estimate(monkeypatch):
    _pbook()
    log = []
    _make(monkeypatch, log)
    js = panel.quotes_json("paper", now=AT, fetch=_fetch([]), rt=["7203.T"])[1]
    r = js["rows"]["7203.T"]
    assert r["src"] == "rt" and r["px"] == 2700.0 and r["est"]["px"] == 2700.0 and "delay" not in r
    assert js["rows"]["1655.T"].get("src") is None and js["rows"]["1655.T"]["px"] == 707.0      # 别的照旧 Yahoo
    assert js["rt"] == {"want": ["7203.T"], "got": ["7203.T"], "why": None, "pending": False}
    assert log == [("login", "面板确认框取实时价（只读）"), ("quote", ["7203.T"]), ("logout",)]   # 只读：登录 → 取价 → 登出
    assert r["bar"]["o"] == 2610.0 and r["bar"]["c"] == 2700.0
    lb = panel._live_bar("paper", "7203.T")                                   # K 线今天这一根：立花的（比 Yahoo 09:40 那根新）
    assert lb["src"] == "rt" and lb["bar"]["c"] == 2700.0 and lb["bar"]["h"] == 2710.0
    plain = panel.quotes_json("paper", now=AT, fetch=_fetch([]))[1]         # 定时的现价：照旧 Yahoo
    assert plain["rows"]["7203.T"]["px"] == 2650.0 and "rt" not in plain


def test_rt_caches_60s_and_backs_off_after_failure(monkeypatch):
    _pbook()
    clock = {"t": 5000.0}
    monkeypatch.setattr(panel.time, "monotonic", lambda: clock["t"])
    log = []
    _make(monkeypatch, log)
    panel.quotes_json("paper", now=AT, fetch=_fetch([]), rt=["7203.T"])
    clock["t"] += 59
    panel.quotes_json("paper", now=AT, fetch=_fetch([]), rt=["7203.T"])
    assert [x for x in log if x[0] == "login"] == [("login", "面板确认框取实时价（只读）")]   # 60 秒内同一只不再登录
    clock["t"] += 2
    panel.quotes_json("paper", now=AT, fetch=_fetch([]), rt=["7203.T"])
    assert len([x for x in log if x[0] == "login"]) == 2
    panel._RT.update(rows={}, fail=-1e9, why=None, flight=None)
    log2 = []
    _make(monkeypatch, log2, fail="另一个进程正在用立花本番的会话")
    js = panel.quotes_json("paper", now=AT, fetch=_fetch([]), rt=["7203.T"])[1]
    assert js["rows"]["7203.T"]["px"] == 2650.0 and "src" not in js["rows"]["7203.T"]   # 取不到：照旧 Yahoo
    assert "另一个进程" in js["rt"]["why"]
    clock["t"] += 30
    js = panel.quotes_json("paper", now=AT, fetch=_fetch([]), rt=["7203.T"])[1]
    assert len([x for x in log2 if x[0] == "login"]) == 1 and "另一个进程" in js["rt"]["why"]   # 60 秒内不再试


def test_rt_not_fetched_outside_session_or_for_other_tickers(monkeypatch):
    _pbook()
    log = []
    _make(monkeypatch, log)
    eve = dt.datetime(2026, 10, 6, 18, 0, tzinfo=JST)
    js = panel.quotes_json("paper", now=eve, fetch=_fetch([]), rt=["7203.T"])[1]
    assert "盘外" in js["rt"]["why"] and log == []
    js = panel.quotes_json("paper", now=AT, fetch=_fetch([]), rt=["9999.T"])[1]   # 不是这个账本的票：不登录
    assert js["rt"]["want"] == [] and log == []
    monkeypatch.setenv(RT.ENV, "0")
    js = panel.quotes_json("paper", now=AT, fetch=_fetch([]), rt=["7203.T"])[1]
    assert "没开" in js["rt"]["why"] and log == []


def test_corefix_confirm_price_label_says_tachibana():
    from qbreak import manual_orders as MO
    px, lab = MO._qpx("1655.T", 700.0, {"1655.T": {"px": 712.0, "at": "2026-10-06T10:00:05+09:00", "src": "rt"}}, AT, "2026-10-05")
    assert px == 712.0 and lab == "立花实时 10:00 的价"


def test_dialogs_have_the_rt_line_and_js_wires_it():
    html = panel._dialogs(True)
    for i in ("sell", "adj", "buy", "ask"):
        assert f"id='{i}-rt'" in html
    js = open(os.path.join(os.path.dirname(panel.__file__), "static", "trade.js"), encoding="utf-8").read()
    for k in ("'#sell-rt'", "'#adj-rt'", "'#buy-rt'", "'#ask-rt'"):
        assert k in js
