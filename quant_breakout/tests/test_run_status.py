"""执行器这次跑成没有（2026-10-09 立花实盘缺口 A4：条目 UX-01 / UX-02 + 「适配器层被挡 / 被拒的单不算没下单」）：
① 运行状态文件 out/live_unified_<账本>_run.json：正常结束 / 执行器停下 / 拿不到运行锁 / 程序出错 / liveu.sh「运行没有完成」都写，
   没事可做的重试不写；② 面板（Mac 与手机同一个）顶部显示运行状态、没下成的单、早上没跑完、09:30 自检没通过（文字都转义）；
③ 通知：当前决策里有被挡 / 被拒 / 状态不明的单、或这次运行有 error 事件 → warn，一行摘要标「★ 没下 N 笔」；没有时与原来完全相同。"""
import datetime as dt
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from qbreak import panel, paths
from qbreak import run_status as RS
from qbreak.brokers.tachibana_sim import SimExchange
from qbreak.calendar_jp import JST, now_jst
from qbreak.live_unified import ExecOrder, ExecutorError, RunLock, UnifiedExecutor, daily_text
from qbreak.unified import UState

from test_live_ops import _done_book, _unified_home
from test_live_unified import NEW, _scenario
from test_panel import AT, _book


def _o(cid, status, d="2026-10-08", side="BUY", ticker="7203.T", qty=100, note="", kind="stock", phase="morning"):
    return {"cid": cid, "ticker": ticker, "side": side, "kind": kind, "qty": qty, "sent_qty": 0, "decided_on": d,
            "status": status, "note": note, "phase": phase, "limit": 3090.0 if side == "BUY" else None}


# ────────── ① 运行状态（单元）──────────
def test_build_takes_bad_orders_of_the_current_decision_and_this_runs_errors():
    t0 = dt.datetime(2026, 10, 9, 7, 40, tzinfo=JST)
    book = {"state": {"last_date": "2026-10-08"},
            "orders": [_o("a", "REJECTED", note="余力不足"), _o("b", "SENT"), _o("c", "SENDING", side="SELL", ticker="6758.T"),
                       _o("old", "ERROR", d="2026-10-07"), _o("e", "BLOCKED", kind="core", ticker="1655.T", qty=0)],
            "events": [{"at": "2026-10-08T07:41:00+09:00", "level": "error", "msg": "昨天的"},
                       {"at": "2026-10-09T07:41:00+09:00", "level": "warn", "msg": "warn 不算"},
                       {"at": "2026-10-09T07:42:00+09:00", "level": "error", "msg": "今天的 1"}]}
    rec = RS.build(book, phase="morning", ok=True, rc=0, since=t0.isoformat(),
                   events=[{"at": "2026-10-09T07:43:00+09:00", "level": "error", "msg": "还没存的"}], now=t0)
    assert rec["decided_on"] == "2026-10-08" and rec["ok"] is True and rec["rc"] == 0 and rec["error"] is None
    assert [o["cid"] for o in rec["bad_orders"]] == ["a", "c", "e"]                     # 前一个决策的不算
    assert rec["bad_orders"][0] == {"cid": "a", "side": "BUY", "ticker": "7203.T", "qty": 100, "status": "REJECTED",
                                    "note": "余力不足", "kind": "stock"}
    assert rec["errors"] == ["今天的 1", "还没存的"]                                     # 这次运行开始之后的 error 事件
    assert RS.bad_text(rec["bad_orders"]) == "被挡 1、被拒 1、状态不明 1"
    assert RS.build({}, phase="now", ok=False, rc=3, error="连不上 https://example.invalid/e_api/x?s=1")["error"] == "连不上 （网址已省略）"
    assert RS.run_errors(book["events"], None) == []
    assert RS.uncovered([_o("x", "BLOCKED", note="行情落后"), _o("y", "BLOCKED", note="未 ARM")], "行情落后")[0]["cid"] == "y"


def test_write_keeps_a_recent_specific_failure_and_read_ignores_broken_files():
    t = dt.datetime(2026, 10, 9, 8, 35, tzinfo=JST)
    lock = RS.build({}, phase="retry", ok=False, rc=3, error="另一个执行器还在运行（pid 1）", now=t)
    assert RS.write("paper", lock)
    alert = RS.build({}, phase="retry", ok=False, rc=3, error="运行没有完成", now=t + dt.timedelta(minutes=1))
    assert not RS.write("paper", alert, keep_recent_fail=True)                          # 15 分钟内更具体的原因不盖掉
    assert RS.read("paper")["error"].startswith("另一个执行器")
    assert RS.write("paper", RS.build({}, phase="morning", ok=False, rc=1, error="别的阶段", now=t), keep_recent_fail=True)
    late = RS.build({}, phase="morning", ok=False, rc=1, error="晚了", now=t + dt.timedelta(minutes=20))
    assert RS.write("paper", late, keep_recent_fail=True) and RS.read("paper")["error"] == "晚了"
    RS.path("paper").write_text("{坏", encoding="utf-8")
    assert RS.read("paper") is None and RS.path("paper").exists()                       # 读坏不改名、不报错


# ────────── ① 运行状态（命令行的各条路）──────────
def test_lock_failure_and_the_liveu_alert_write_the_run_status(capsys):
    import run
    _unified_home()
    lock = RunLock(paths.state_dir() / "live_unified_tachibana.lock").acquire()
    try:
        assert run.main(["live-u", "--broker", "tachibana", "--retry", "--lock-wait", "0"]) == 3
    finally:
        lock.release()
    rec = RS.read("tachibana")
    assert rec["ok"] is False and rec["rc"] == 3 and rec["phase"] == "retry" and "另一个执行器还在运行" in rec["error"]
    msg = "10/09 08:35 的运行没有完成（退出码 3）：看 logs/ 里的 .err / .out，或把它发给 Claude"
    assert run.main(["live-u", "--broker", "tachibana", "--retry", "--status", "--alert", msg]) == 0
    assert "另一个执行器还在运行" in RS.read("tachibana")["error"]                        # 紧跟着的「运行没有完成」不盖掉具体原因
    RS.path("tachibana").unlink()
    assert run.main(["live-u", "--broker", "tachibana", "--phase", "open", "--status", "--alert", msg]) == 0
    rec = RS.read("tachibana")
    assert rec["ok"] is False and rec["rc"] == 3 and rec["phase"] == "open" and rec["error"] == msg
    RS.path("tachibana").unlink()
    assert run.main(["live-u", "--broker", "tachibana", "--status"]) == 0                # 只读的 --status 不写
    assert RS.read("tachibana") is None


def test_retry_with_nothing_to_do_does_not_overwrite_the_last_status():
    import run
    _unified_home()
    _done_book()
    RS.write("tachibana", {"at": "2026-10-09T07:41:00+09:00", "phase": "morning", "ok": True, "rc": 0})
    assert run.main(["live-u", "--broker", "tachibana", "--retry"]) == 0
    assert RS.read("tachibana")["phase"] == "morning"


def test_crash_writes_the_run_status_without_urls(monkeypatch):
    import run

    def boom(a):
        raise RuntimeError("连不上 https://example.invalid/e_api_v4r10/abc?session=1")
    monkeypatch.setattr(run, "_live_unified_body", boom)
    assert run.main(["live-u", "--broker", "paper"]) == 1
    rec = RS.read("paper")
    assert rec["ok"] is False and rec["rc"] == 1 and "RuntimeError" in rec["error"] and "example.invalid" not in rec["error"]
    RS.path("paper").unlink()
    assert run.main(["live-u", "--broker", "paper", "--resolve", "c1"]) == 1             # 登记成交出错：不是执行器的运行，不写
    assert RS.read("paper") is None


class _UX:
    """假的执行器（只给 run.py 的流程用）：账本、单、事件由测试给。"""
    book0: dict = {}
    raise_on: str | None = None
    now_new: list = []

    def __init__(self, eng, broker, path=None, **kw):
        self.eng, self.b, self.path = eng, broker, path
        self.book = json.loads(json.dumps(self.book0))
        self.orders = [ExecOrder.from_dict(o) for o in self.book.get("orders") or []]
        self.events, self.blocked, self.manual = [], None, None

    def _maybe_raise(self):
        if self.raise_on:
            self.events.append({"at": now_jst().isoformat(timespec="seconds"), "level": "error", "msg": "还没存的错误"})
            raise ExecutorError(self.raise_on)

    def morning(self, idxs, corp=None):
        self._maybe_raise()

    def now_phase(self, quote):
        for o in self.now_new:
            self.orders.append(ExecOrder.from_dict(o))
            self.book["orders"].append(o)
        return {"placed": 0, "items": [{"id": "M1", "ticker": "7203.T", "status": "没执行", "msg": "立花没受理"}]}

    def save(self, force=False):
        pass

    def summary(self):
        d = (self.book.get("state") or {}).get("last_date")
        return {"broker": "PaperBroker", "decided_on": d, "fill_day": "2026-10-09", "equity_jpy": 1_000_000, "cash_jpy": 1_000_000,
                "positions": {}, "core_units": {}, "pending_exit": {}, "reconciled": [], "blocked": self.blocked, "stats": {},
                "orders": [o for o in self.book.get("orders") or [] if o.get("decided_on") == d], "manual": None,
                "events": list(self.book.get("events") or [])}


def _fake_run(monkeypatch, book, raise_on=None, now_new=()):
    import qbreak.live_unified as LU
    import run
    _unified_home()
    st = UState(cash_jpy=1e6, last_date="2026-10-08",
                history=[["2026-10-07", 1e6, 1e6, 0, 150], ["2026-10-08", 1e6, 1e6, 0, 150]])
    eng = SimpleNamespace(gidx=pd.DatetimeIndex(["2026-10-07", "2026-10-08"]), st=st, gate_log=[],
                          cfg=SimpleNamespace(core={"1655.T": 1.0}))
    gate = SimpleNamespace(pre_send=None, panel=lambda **k: {}, held_alerts=lambda *a: [])
    ctx = SimpleNamespace(ex={"JP": None}, gate=gate, delist={}, extras={}, xmode="DC", ic_status={}, cc=None, bar_date=None,
                          cc_on=False, tbf=None, tbf_on=False)
    monkeypatch.setattr(run, "_netcheck", lambda: [])
    monkeypatch.setattr("qbreak.trader.expected_last_bar", lambda today, market: dt.date(2026, 10, 8))   # 假引擎的行情到 10-08
    monkeypatch.setattr(run, "_unified_engine", lambda a, cfg, state, provider: (eng, ctx))
    monkeypatch.setattr(run, "_paper_broker_for_executor", lambda ucfg, ex: SimpleNamespace())
    monkeypatch.setattr(run, "_new_bar_idxs", lambda e, s: ([], "2026-10-08"))
    monkeypatch.setattr(run, "_corp_actions_provider", lambda: None)
    monkeypatch.setattr(run, "_now_work", lambda tag, b: True)
    for f in ("_new_pos_brief", "_fj_brief", "_holding_view", "_suggest", "_kline"):
        monkeypatch.setattr(run, f, lambda *a, **k: {})
    monkeypatch.setattr("qbreak.combo_c.brief", lambda *a, **k: {})
    monkeypatch.setattr("qbreak.tbf.brief", lambda *a, **k: {})
    ux = type("UX", (_UX,), {"book0": book, "raise_on": raise_on, "now_new": list(now_new)})
    monkeypatch.setattr(LU, "UnifiedExecutor", ux)
    sent = []
    monkeypatch.setattr(LU, "mac_notify", lambda t, s: sent.append(("mac", t, s)) or True)
    monkeypatch.setattr("qbreak.notify.send", lambda t, b, level="info": sent.append(("send", t, b, level)))
    return sent


def _book_dict(orders, events=()):
    return {"state": {"last_date": "2026-10-08", "cash_jpy": 1e6}, "orders": orders, "events": list(events)}


def test_normal_end_writes_status_and_unplaced_orders_make_the_notice_warn(monkeypatch):
    import run
    old = {"at": "2026-01-05T07:40:00+09:00", "level": "error", "msg": "很久以前的错误"}
    sent = _fake_run(monkeypatch, _book_dict([_o("U-B", "REJECTED", note="立花：余力不足"), _o("U-S", "SENT", side="SELL")], [old]))
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify"]) == 0
    rec = RS.read("paper")
    assert rec["ok"] is True and rec["rc"] == 0 and rec["phase"] == "morning" and rec["blocked"] is None
    assert rec["decided_on"] == "2026-10-08" and [o["cid"] for o in rec["bad_orders"]] == ["U-B"] and rec["errors"] == []
    mac = [x for x in sent if x[0] == "mac"][0]
    send = [x for x in sent if x[0] == "send"][0]
    assert "｜★ 没下 1 笔（被拒 1）" in mac[2] and send[3] == "warn"


def test_normal_end_without_problems_keeps_the_info_level(monkeypatch):
    import run
    old = {"at": "2026-01-05T07:40:00+09:00", "level": "error", "msg": "很久以前的错误"}      # 以前的 error 事件不算这次的
    sent = _fake_run(monkeypatch, _book_dict([_o("U-B", "SENT"), _o("U-X", "SKIPPED")], [old]))
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify"]) == 0
    mac = [x for x in sent if x[0] == "mac"][0]
    assert "★" not in mac[2] and [x for x in sent if x[0] == "send"][0][3] == "info"
    assert RS.read("paper")["bad_orders"] == [] and RS.read("paper")["ok"] is True


def test_executor_error_writes_the_status_with_unsaved_events(monkeypatch):
    import run
    _fake_run(monkeypatch, _book_dict([_o("U-B", "SENDING")]), raise_on="有状态不明的单（发送中断）：U-B BUY 7203.T ×100")
    assert run.main(["live-u", "--broker", "paper", "--force"]) == 3
    rec = RS.read("paper")
    assert rec["ok"] is False and rec["rc"] == 3 and rec["error"].startswith("执行器停下（状态没有改动）：有状态不明的单")
    assert rec["bad_orders"][0]["status"] == "SENDING" and rec["errors"] == ["还没存的错误"]


def test_now_phase_warns_only_for_orders_sent_in_this_run(monkeypatch):
    import run
    morning_blocked = _o("U-A", "BLOCKED", ticker="6758.T", note="未 ARM")
    rej = _o("N1-BUY-7203.T", "REJECTED", note="立花：余力不足", phase="now")
    sent = _fake_run(monkeypatch, _book_dict([morning_blocked]), now_new=[rej])
    assert run.main(["live-u", "--broker", "paper", "--phase", "now", "--force", "--notify"]) == 0
    mac = [x for x in sent if x[0] == "mac"][0]
    assert mac[2].startswith("★ 没下 1 笔（被拒 1）｜下单 0 笔") and [x for x in sent if x[0] == "send"][0][3] == "warn"
    rec = RS.read("paper")
    assert rec["phase"] == "now" and rec["ok"] is True and {o["cid"] for o in rec["bad_orders"]} == {"U-A", "N1-BUY-7203.T"}
    sent2 = _fake_run(monkeypatch, _book_dict([morning_blocked]), now_new=[{**rej, "status": "SENT"}])
    assert run.main(["live-u", "--broker", "paper", "--phase", "now", "--force", "--notify"]) == 0
    assert [x for x in sent2 if x[0] == "send"][0][3] == "info"                       # 早上被挡的那笔不让盘中的通知变 warn
    assert [x for x in sent2 if x[0] == "mac"][0][2] == "下单 0 笔：7203.T 没执行"           # 没有问题时与原来完全相同


def test_halt_blocked_orders_are_not_failures_in_the_notice(monkeypatch):
    """HALT 生效中：执行器把单都标成 BLOCKED（note「存在 HALT 文件…」）但不经过 ux.block → 不标 ★、级别不升到 warn
    （HALT 不是失败；面板也不逐笔列）；HALT 之外被挡的照样算。"""
    import run
    halt = f"存在 HALT 文件（{paths.halt_file()}）"
    st = UState(cash_jpy=1e6, last_date="2026-10-08")
    sm = {"decided_on": "2026-10-08", "blocked": None, "events": [],
          "orders": [_o("a", "BLOCKED", note=halt), _o("b", "BLOCKED", side="SELL", ticker="6758.T", note=halt)]}
    _, short, _ = daily_text(sm, st, None, False, 1_000_000)
    assert "★" not in short and "下一开盘的单 2 笔" in short
    assert RS.actionable(RS.bad_orders(sm["orders"])) == []
    _, short2, _ = daily_text({**sm, "orders": sm["orders"] + [_o("c", "REJECTED", note="余力不足")]}, st, None, False, 1_000_000)
    assert "｜★ 没下 1 笔（被拒 1）" in short2
    sent = _fake_run(monkeypatch, _book_dict([_o("U-A", "BLOCKED", note=halt), _o("U-S", "SENT", side="SELL")]))
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify"]) == 0
    assert "★" not in [x for x in sent if x[0] == "mac"][0][2] and [x for x in sent if x[0] == "send"][0][3] == "info"
    sent2 = _fake_run(monkeypatch, _book_dict([]), now_new=[_o("N1", "BLOCKED", note=halt, phase="now")])
    assert run.main(["live-u", "--broker", "paper", "--phase", "now", "--force", "--notify"]) == 0
    assert [x for x in sent2 if x[0] == "send"][0][3] == "info" and "★" not in [x for x in sent2 if x[0] == "mac"][0][2]


# ────────── ③ 通知的一行摘要 ──────────
def test_daily_text_flags_orders_blocked_by_the_adapter_but_not_twice():
    """立花适配器挡下（例如没有 ARM）不经过 ux.block：以前一行摘要什么都不说，通知是 info。"""
    from qbreak.brokers.tachibana import TachibanaBroker
    make, start = _scenario([1000.0] * 30, entry=(10,), bear_all=True)
    eng = make()
    exch = SimExchange(eng, cash=eng.st.cash_jpy)
    b = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=True, confirm_timeout_s=0.0)
    ux = UnifiedExecutor(eng, b, paths.state_dir() / "book.json", paper=False, check_clock=False)
    lo = int(eng.gidx.searchsorted(start))
    eng.prime(lo)
    for k in range(lo, 11):
        exch.open(k)
        ux.open_phase()
        exch.close_day()
        exch.set_day(k + 1)
        ux.run_bar(k)
    sm = ux.summary()
    assert ux.blocked is None and any(o["status"] == "BLOCKED" and "未 ARM" in o["note"] for o in sm["orders"])
    assert exch.calls.get(NEW, 0) == 0
    n = len(RS.bad_orders(sm["orders"]))
    _, short, _ = daily_text(sm, eng.st, None, False, 1_000_000)
    assert f"｜★ 没下 {n} 笔（被挡 {n}）" in short and "★ 没下单" not in short
    st = UState(cash_jpy=1e6, last_date="2026-10-08")
    blocked = {"decided_on": "2026-10-08", "blocked": "行情落后", "events": [],
               "orders": [_o("a", "BLOCKED", note="行情落后"), _o("b", "ERROR", note="状态不明（URLError）")]}
    _, short2, _ = daily_text(blocked, st, None, False, 1_000_000)
    assert "｜★ 没下单｜★ 没下 1 笔（状态不明 1）" in short2                              # 整次被挡的不再重复算
    _, short3, _ = daily_text({**blocked, "blocked": None, "orders": [_o("c", "SENT")]}, st, None, False, 1_000_000)
    assert "★" not in short3


# ────────── ② 面板 ──────────
def _write_rec(tag="paper", **kw):
    rec = {"at": "2026-10-06T07:41:00+09:00", "phase": "morning", "ok": True, "rc": 0, "error": None, "blocked": None,
           "decided_on": "2026-10-05", "bad_orders": [], "errors": []}
    rec.update(kw)
    RS.write(tag, rec)


def test_panel_shows_a_quiet_line_when_the_run_went_fine():
    _book(orders=[_o("U1", "SENT", d="2026-10-05")])
    _write_rec()
    html = panel.render("paper", "t" * 40, AT)
    assert "执行器：10/06 07:41 跑完 ✓（早上的运行）" in html and "停下" not in html and "被挡 / 被拒" not in html
    assert "今天早上的运行还没完成" not in html


def test_panel_shows_a_stopped_executor_and_unplaced_orders_escaped():
    _book(tag="tachibana", orders=[_o("U1", "ERROR", d="2026-10-05", note="状态不明（<script>x</script>）"),
                                   _o("U2", "REJECTED", d="2026-10-05", side="SELL", ticker="6758.T", note="余力不足"),
                                   _o("U0", "ERROR", d="2026-10-02")])
    _write_rec("tachibana", ok=False, rc=3, error="执行器停下：<b>有状态不明的单</b>", phase="retry", at="2026-10-06T08:35:10+09:00")
    html = panel.render("tachibana", "t" * 40, AT)
    assert "★ 执行器 10/06 08:35 停下：执行器停下：&lt;b&gt;有状态不明的单&lt;/b&gt;" in html and "<b>有状态" not in html
    assert "★ 有 2 笔被挡 / 被拒 / 状态不明（被拒 1、状态不明 1）" in html
    assert "・7203.T 买 100 股 状态不明：状态不明（&lt;script&gt;x&lt;/script&gt;）" in html and "<script>x" not in html
    assert "・6758.T 卖 100 股 被拒：余力不足" in html
    assert f"href='{panel.ESHITEN_SP}'" in html and "再在 Mac 对话里登记" in html
    assert "<section class='card warn'>" in html


def test_panel_blocked_run_is_said_once_and_paper_gets_no_tachibana_hint():
    _book(orders=[_o("U1", "BLOCKED", d="2026-10-05", note="行情落后：^N225"),
                  _o("U2", "ERROR", d="2026-10-05", ticker="1655.T", kind="core", qty=300)])
    _write_rec(blocked="行情落后：^N225", decided_on="2026-10-05")
    html = panel.render("paper", "t" * 40, AT)
    assert "★ 今天的单没下：行情落后：^N225" in html and "★ 有 1 笔被挡 / 被拒 / 状态不明（状态不明 1）" in html
    assert "・1655.T 买 300 口 状态不明" in html and panel.ESHITEN_SP not in html
    _write_rec(blocked="行情落后：^N225", decided_on="2026-10-05", at="2026-10-05T07:41:00+09:00")
    assert "★ 10/05 的单没下" in panel.render("paper", "t" * 40, AT)


def test_panel_halt_blocked_orders_are_covered_by_the_halt_banner():
    _book(orders=[_o("U1", "BLOCKED", d="2026-10-05", note=f"存在 HALT 文件（{paths.halt_file()}）")])
    paths.halt_file().write_text("用户说停", encoding="utf-8")
    html = panel.render("paper", "t" * 40, AT)
    assert "HALT 生效中" in html and "被挡 / 被拒" not in html and "今天早上的运行还没完成" not in html


def test_panel_flags_a_morning_run_that_has_not_finished():
    _book(last="2026-10-02")                                                       # 10-06（火）08:00：应处理到 10-05（月）
    assert "★ 今天早上的运行还没完成（上次决策 2026-10-02）" in panel.render("paper", "t" * 40, AT)
    assert "今天早上的运行还没完成" not in panel.render("paper", "t" * 40, AT.replace(hour=7, minute=59))
    assert "今天早上的运行还没完成" not in panel.render("paper", "t" * 40, dt.datetime(2026, 10, 10, 9, 0, tzinfo=JST))   # 周六
    _book(orders=[_o("U1", "BLOCKED", d="2026-10-05", note="行情落后")])               # 处理到了，但单被挡 → 还没完成
    assert "★ 今天早上的运行还没完成（上次决策 2026-10-05）" in panel.render("paper", "t" * 40, AT)
    _book(orders=[_o("U1", "SENT", d="2026-10-05")])
    assert "今天早上的运行还没完成" not in panel.render("paper", "t" * 40, AT)
    _book(last="2026-09-18")                                                       # 停用了的模拟账户：不吵
    assert "今天早上的运行还没完成" not in panel.render("paper", "t" * 40, AT)
    _book(tag="tachibana", last="2026-09-18")                                      # 立花本番：几天没跑更要提醒
    assert "★ 今天早上的运行还没完成（上次决策 2026-09-18）" in panel.render("tachibana", "t" * 40, AT)


def test_panel_keeps_flagging_a_scheduled_paper_book_that_missed_several_mornings(monkeypatch, tmp_path):
    """模拟账户装着 07:40 的定时任务：连着两天没跑也照样提醒（以前只在第一天提醒）；没装 → 停用了的账本不吵。"""
    _book(last="2026-10-01")                                                       # 10-06（火）：应处理到 10-05，已经落后 2 个交易日
    assert "今天早上的运行还没完成" not in panel.render("paper", "t" * 40, AT)
    agents = Path(os.environ["QBREAK_LAUNCH_AGENTS"])
    agents.mkdir(parents=True, exist_ok=True)
    (agents / "com.qbreak.liveu.paper.plist").write_text("x", encoding="utf-8")
    assert "★ 今天早上的运行还没完成（上次决策 2026-10-01）" in panel.render("paper", "t" * 40, AT)


def test_panel_sending_order_while_the_executor_runs_is_not_unknown():
    """执行器发单前先把 SENDING 存进账本：它还拿着运行锁时，SENDING 是「发送中」，不叫人去注文一覧核对 / 登记。"""
    _book(tag="tachibana", orders=[_o("U1", "SENDING", d="2026-10-05")])
    lock = RunLock(paths.state_dir() / "live_unified_tachibana.lock").acquire()
    try:
        html = panel.render("tachibana", "t" * 40, AT)
    finally:
        lock.release()
    assert "发送中（执行器正在运行）：7203.T 买 100 股" in html
    assert "状态不明" not in html and panel.ESHITEN_SP not in html
    html = panel.render("tachibana", "t" * 40, AT)                                 # 运行结束了还是 SENDING → 状态不明
    assert "★ 有 1 笔被挡 / 被拒 / 状态不明（状态不明 1）" in html and panel.ESHITEN_SP in html
    _book(tag="tachibana", orders=[_o("U1", "ERROR", d="2026-10-05")])             # ERROR 不管运行锁，一直是状态不明
    lock = RunLock(paths.state_dir() / "live_unified_tachibana.lock").acquire()
    try:
        assert "状态不明 1" in panel.render("tachibana", "t" * 40, AT)
    finally:
        lock.release()


def test_panel_shows_todays_failed_watchdog_only():
    _book(orders=[_o("U1", "SENT", d="2026-10-05")])
    wd = paths.out_dir() / "watchdog_paper.json"
    wd.write_text(json.dumps({"at": "2026-10-06T09:30:05+09:00", "ok": False,
                              "reasons": ["今天早上的执行器没有跑完（上次决策 2026-10-02）", "<i>x</i>"]}), encoding="utf-8")
    at = AT.replace(hour=9, minute=40)
    html = panel.render("paper", "t" * 40, at)
    assert "★ 自检（09:30）：今天早上的执行器没有跑完（上次决策 2026-10-02）；&lt;i&gt;x&lt;/i&gt;" in html
    wd.write_text(json.dumps({"at": "2026-10-05T09:30:05+09:00", "ok": False, "reasons": ["昨天的"]}), encoding="utf-8")
    assert "自检" not in panel.render("paper", "t" * 40, at)
    wd.write_text(json.dumps({"at": "2026-10-06T09:30:05+09:00", "ok": True, "reasons": []}), encoding="utf-8")
    assert "自检" not in panel.render("paper", "t" * 40, at)
    wd.write_text("{坏", encoding="utf-8")
    RS.path("paper").write_text("[1, 2", encoding="utf-8")
    html = panel.render("paper", "t" * 40, at)                                     # 读坏 → 不显示、不报错
    assert "自检" not in html and "执行器：" not in html and wd.exists()
