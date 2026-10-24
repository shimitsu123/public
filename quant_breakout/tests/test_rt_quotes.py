"""模拟账户用立花本番的实时价（qbreak/rt_quotes.py；2026-10-17 用户「能用到立花实时数据的地方用实时数据」）：
盘中手动指令（--phase now）的现价、成交日开盘撮合（--phase open）的开盘价先用立花（只读登录一次、取完登出），
取不到 → 照旧 Yahoo，成交说明写用的是哪个。测试里绝不登录真的立花（conftest 设 QBREAK_PAPER_RT=0；这里用假的券商）。"""
import os

import pytest

from qbreak import rt_quotes as RT

from test_manual_now import PX, _at, _item, _morning, _paper, _req
from test_paper_open_settle import _feed
from test_core_etf_restore import _paper2
from test_fund_src import _fixed_case


class _FakeB:
    def __init__(self, rows=None, fail=None, log=None):
        self.rows, self.fail, self.log = rows or {}, fail, log if log is not None else []
        self.dry_run, self.require_arm = True, True

    def login(self):
        from qbreak.brokers import tachibana as T
        w = getattr(T.WAIT_TLS, "wait_s", None)
        self.log.append(("login", None if w is None else str(w)))
        assert "QBREAK_TACHIBANA_SESSION_WAIT_S" not in os.environ       # 不改环境变量（同时起的子进程不继承；2026-10-24 复核）
        if self.fail:
            raise RuntimeError(self.fail)

    def quote_detail(self, ts):
        self.log.append(("quote", sorted(ts)))
        return {t: v for t, v in self.rows.items() if t in ts}

    def logout(self):
        self.log.append(("logout", None))

    def buy(self, *a, **k):                                   # 绝不发单
        raise AssertionError("rt_quotes 不该下单")

    sell = buy


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(RT.ENV, "1")
    monkeypatch.delenv("QBREAK_TACHIBANA_SESSION_WAIT_S", raising=False)


def test_tests_never_log_in_to_the_real_tachibana():
    assert os.environ.get(RT.ENV) == "0" and not RT.enabled()
    calls = []
    d, why = RT.tachibana_detail(["1482.T"], make=lambda: _FakeB(log=calls))
    assert d == {} and "没开" in why and calls == []                           # 关着：连券商对象都不建


def test_now_quote_uses_tachibana_then_logs_out_and_restores_the_wait(on):
    log, yh = [], []
    q = RT.NowQuote(lambda ts: yh.append(ts) or {}, make=lambda: _FakeB({"A.T": {"price": 101.0}, "B.T": {"price": 55.5}}, log=log))
    assert q(["B.T", "A.T"]) == {"A.T": 101.0, "B.T": 55.5}
    assert q.src == RT.SRC_RT and q.why is None and yh == []
    assert log == [("login", str(RT.WAIT_S)), ("quote", ["A.T", "B.T"]), ("logout", None)]   # 会话锁只等 20 秒、取完马上登出
    assert "QBREAK_TACHIBANA_SESSION_WAIT_S" not in os.environ                  # 环境变量没动（执行器自己的 300 秒不受影响）
    from qbreak.brokers import tachibana as T
    assert getattr(T.WAIT_TLS, "wait_s", None) is None                         # 取完还原


def test_short_wait_is_only_for_the_quote_thread(on):
    """面板取实时价时，别的线程（撤单 / 下单的子进程是从别的线程起的）照旧等默认的 300 秒（2026-10-24 复核）。"""
    import threading
    from qbreak.brokers import tachibana as T
    seen, gate, go = {}, threading.Event(), threading.Event()

    class _Slow(_FakeB):
        def login(self):
            super().login()
            gate.set()
            go.wait(5)

    th = threading.Thread(target=lambda: RT.NowQuote(lambda ts: {}, make=lambda: _Slow({"A.T": {"price": 1.0}}))(["A.T"]))
    th.start()
    assert gate.wait(5)
    seen["other"] = getattr(T.WAIT_TLS, "wait_s", None)
    seen["env"] = os.environ.get("QBREAK_TACHIBANA_SESSION_WAIT_S")
    go.set()
    th.join(5)
    assert seen == {"other": None, "env": None}


def test_now_quote_fills_missing_tickers_from_yahoo_and_says_so(on):
    q = RT.NowQuote(lambda ts: {t: 9.0 for t in ts}, make=lambda: _FakeB({"A.T": {"price": 101.0}}))
    assert q(["A.T", "B.T"]) == {"A.T": 101.0, "B.T": 9.0}
    assert q.src == f"{RT.SRC_RT} + {RT.SRC_YH}"


def test_login_failure_or_busy_session_falls_back_to_yahoo(on):
    log = []
    q = RT.NowQuote(lambda ts: {t: 9.0 for t in ts}, make=lambda: _FakeB(fail="另一个进程正在用立花本番的会话", log=log))
    assert q(["A.T"]) == {"A.T": 9.0} and q.src == RT.SRC_YH and "另一个进程" in q.why
    assert log[-1] == ("logout", None)                                          # 失败也放锁
    q2 = RT.NowQuote(lambda ts: {}, make=lambda: (_ for _ in ()).throw(RuntimeError("找不到私钥")))
    assert q2(["A.T"]) == {} and q2.src == RT.SRC_YH and "找不到私钥" in q2.why


def test_open_feed_uses_tachibana_open_and_waits_for_unopened_tickers(on):
    yh = []
    f = RT.OpenFeed(lambda ts, now=None: yh.append(ts) or {},
                    make=lambda: _FakeB({"A.T": {"price": 101.0, "open": 100.0, "high": 102.0, "low": 99.0},
                                         "B.T": {"price": 50.0, "prev_close": 49.0},        # B 还没寄付（没有始値）
                                         "C.T": {"open": 70.0, "prev_close": 69.0}}))       # C 只有始値、没有现在值：不算今天寄付了
    out = f(["A.T", "B.T", "C.T"], "now")
    assert out == {"A.T": {"open": 100.0, "high": 102.0, "low": 99.0, "first": "09:00"}}
    assert f.src == RT.SRC_RT and yh == []                                      # 立花在应答：不拿 Yahoo 补（同一批口径一样）


def test_open_feed_falls_back_to_yahoo_as_a_whole_batch(on):
    seen = []
    f = RT.OpenFeed(lambda ts, now=None: seen.append((ts, now)) or {t: {"open": 1.0} for t in ts},
                    make=lambda: _FakeB(fail="交付書面未読"))
    assert f(["A.T", "B.T"], "NOW") == {"A.T": {"open": 1.0}, "B.T": {"open": 1.0}}
    assert f.src == RT.SRC_YH and seen == [(["A.T", "B.T"], "NOW")]


# ────────── 接到执行器：成交说明写来源 ──────────
def test_paper_now_fill_says_tachibana_realtime(on):
    r = _paper("rtn")
    _morning(r, until=14)
    trim = _req(r, kind="trim", ticker="A.T", pct=12.0)
    r.now["t"] = _at(r, 10, 0)
    q = RT.NowQuote(lambda ts: {}, make=lambda: _FakeB({t: {"price": p} for t, p in PX.items()}))
    res = r.ux.now_phase(q)
    assert res["placed"] >= 1 and q.src == RT.SRC_RT
    assert "（模拟：立花实时）" in _item(r, trim["id"])["msg"]


def test_paper_now_fill_with_yahoo_keeps_the_old_wording(on):
    r = _paper("rty")
    _morning(r, until=14)
    trim = _req(r, kind="trim", ticker="A.T", pct=12.0)
    r.now["t"] = _at(r, 10, 0)
    q = RT.NowQuote(lambda ts: {t: PX[t] for t in ts if t in PX}, make=lambda: _FakeB(fail="会话被占"))
    r.ux.now_phase(q)
    assert "（模拟：约 20 分钟前的价）" in _item(r, trim["id"])["msg"]


def test_paper_open_settle_with_tachibana_open_notes_the_source(on):
    r = _paper2("rto")
    sell, buy = _fixed_case(r)
    yahoo = _feed(r)
    rows = {t: {"price": v["open"], "open": v["open"], "high": v["high"], "low": v["low"]} for t, v in yahoo([sell.ticker, buy.ticker], None).items()}
    r.now["t"] = _at(r, 9, 25)
    res = r.ux.open_phase(feed=RT.OpenFeed(yahoo, make=lambda: _FakeB(rows)))
    assert res["done"]
    assert "立花始値" in sell.note and "1 分钟线" not in sell.note
    assert r.ux.book["paper_open"]["src"] == "rt"
