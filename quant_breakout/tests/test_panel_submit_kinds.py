"""面板提交（panel.submit）每一种指令都不崩溃、都回一句有意义的话（2026-10-16 复核 C）。
起因：2026-10-12 手机上点「固定口数…」→ submit 里 msg（说明）是 None → `msg + "（指令 …）"` TypeError → 手机 502
（当天 38517c2 补了 corefix 的说明与兜底）。复核时按每一种指令走一遍：说明为 None 只有 corefix 一种（已修）；另外发现 body 里
fund 写成字符串 "all"（页面不会这样写，旧页面 / 手写请求会）→ 先写进一条没有同批卖出的「全部换成」买入，再拼说明时
AttributeError 崩溃。现在：页面带来的内部字段不收（panel.CLIENT_DROP）；写进去之后说明拼不成也照实回「已写：…（指令 id）」。"""
import datetime as dt
import json

import pytest

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST

from test_fund_all import _book4
from test_panel import _book, _sm

TIMES = {"pre": dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST), "session": dt.datetime(2026, 10, 6, 10, 0, tzinfo=JST),
         "after": dt.datetime(2026, 10, 6, 16, 0, tzinfo=JST), "sat": dt.datetime(2026, 10, 10, 11, 0, tzinfo=JST)}
BUY_CID = "U2026-10-05-BUY-6501.T"


def _setup(fix=None):
    """4 只个股 + 1545（100 口）；6758 在「不自动买回」里（解除用）；当前决策（10/05）有一笔执行器还没发出的 6501 买单（撤单用）。"""
    b = _book4(core_fix=fix or {}, blocks={"6758.T": {"until": "2026-11-01", "since": "2026-10-01", "id": "M20261001-080000-sell-6758"}})
    b["orders"] = [{"cid": BUY_CID, "ticker": "6501.T", "side": "BUY", "kind": "stock", "qty": 100, "decided_on": "2026-10-05",
                    "limit": 3600.0, "phase": "open", "status": "DEFERRED", "sent_qty": 0, "filled_qty": 0, "reason": "entry"}]
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm()
    p = MO.requests_path("paper")
    if p.exists():
        p.unlink()


def _go(body, now):
    ok, msg, rec = panel.submit({"book": "paper", **body}, now, fetch=lambda ts: {})
    if not ok and (rec or {}).get("need_confirm"):                       # 固定口数：点了「确认下单」
        ok, msg, rec = panel.submit({"book": "paper", **body, "confirm": rec["confirm"]["token"]}, now, fetch=lambda ts: {})
    return ok, msg, rec


def _cancel_target(now):
    return MO.append("paper", {"kind": "sell", "ticker": "8306.T"}, clock=lambda: now - dt.timedelta(minutes=5))["id"]


def _uncancel_target(now):
    sid = _cancel_target(now)
    return MO.append("paper", {"kind": "cancel", "target": sid}, clock=lambda: now - dt.timedelta(minutes=4))["id"]


BODIES = [   # (种类, body 或「先写好它要指的那条、再给 body」的函数)
    ("sell", {"kind": "sell", "ticker": "8306"}),
    ("trim", {"kind": "trim", "ticker": "8306", "pct": 5}),
    ("adjust", {"kind": "adjust", "ticker": "9432", "unit": "shares", "value": 300}),
    ("adjust", {"kind": "adjust", "ticker": "9432", "unit": "shares", "value": 0}),
    ("buy", {"kind": "buy", "ticker": "6501", "unit": "shares", "value": 100, "fund": {"mode": "all"}}),
    ("core", {"kind": "core", "pct": 50}),
    ("core", {"kind": "sell", "ticker": "1545"}),                         # 核心 ETF 的卖出全部 → 比例指令（固定口数的 → corefix）
    ("core", {"kind": "adjust", "ticker": "1545", "unit": "shares", "value": 50}),
    ("corefix", {"kind": "corefix", "ticker": "1545", "units": 200}),
    ("corefix", {"kind": "corefix", "ticker": "1545", "clear": True}),
    ("corefix", {"kind": "corefix", "ticker": "1482", "units": 10}),
    ("unblock", {"kind": "unblock", "ticker": "6758"}),
    ("unblock", {"kind": "unblock", "tickers": ["6758:M20261001-080000-sell-6758"]}),
    ("cancel_order", {"kind": "cancel_order", "cid": BUY_CID}),
    ("flow", {"kind": "flow", "jpy": 1000}),
    ("cancel", lambda now: {"kind": "cancel", "target": _cancel_target(now)}),
    ("uncancel", lambda now: {"kind": "uncancel", "target": _uncancel_target(now)}),
]


@pytest.mark.parametrize("halt", [False, True])
@pytest.mark.parametrize("when", sorted(TIMES))
def test_every_kind_returns_a_message_and_never_raises(monkeypatch, when, halt):
    monkeypatch.setattr(panel.MO, "paper_refuse", lambda tag, agents=None: None)   # 模拟账户的执行器在测试里没装：照样走到底
    now = TIMES[when]
    if halt:
        paths.halt_file().write_text("test")
    wrote = set()
    for fix in ({}, {"1545.T": 100}):
        for kind, body in BODIES:
            _setup(fix)                                                  # 每一条都从同一个账本开始（不被前一条挡住）
            body = body(now) if callable(body) else body
            ok, msg, rec = _go(body, now)
            assert isinstance(msg, str) and msg.strip(), (kind, body, msg)
            if ok:
                assert msg.startswith("已写") and rec["id"] in msg, (kind, msg)
                assert "None" not in msg, msg
                wrote.add(kind)
    assert {k for k, _b in BODIES} == set(MO.KINDS) | {"flow"}             # 每一种都在表里（新加的种类要加进 BODIES）
    if when == "session":
        assert wrote == set(MO.KINDS), wrote                              # 盘中：每一种都真的写进去了（不是都在检查那里就返回）


def test_written_never_concatenates_none():
    """2026-10-12 的崩溃本身：说明是 None（以前 corefix 没有说明）→ 照实写写了什么 + 指令 id。"""
    rec = {"id": "M20261012-145300-corefix-1482", "kind": "corefix", "ticker": "1482.T", "units": 655}
    out = panel._written(None, rec)
    assert out.startswith("已写：固定 1482 ") and "655 口" in out and out.endswith("（指令 M20261012-145300-corefix-1482）")
    assert panel._written("已写：x", rec) == "已写：x（指令 M20261012-145300-corefix-1482）"


def test_message_failure_after_write_still_answers(monkeypatch):
    """写进去之后拼说明出错（例：账本里读不了的数）→ 不崩溃（以前 → 面板 500 / 手机 502「可能已经写进去了」），照实说已写 + 指令 id。"""
    monkeypatch.setattr(panel.MO, "paper_refuse", lambda tag, agents=None: None)
    _setup()

    def boom(*a, **k):
        raise TypeError("unsupported operand type(s) for +: 'NoneType' and 'str'")
    monkeypatch.setattr(panel.MO, "when_for", boom)
    ok, msg, rec = _go({"kind": "sell", "ticker": "7203"}, TIMES["after"])
    assert ok and rec["kind"] == "sell"
    assert msg == f"已写：卖出全部 7203 トヨタ自動車（说明没生成：到「交易」里看这条指令的状态）（指令 {rec['id']}）"


def test_client_cannot_send_internal_fields(monkeypatch):
    """页面提交里带了只由面板 / 执行器自己算的字段 → 不收。以前 fund:"all"（字符串）→ 写进一条没有同批卖出的「全部换成」买入，
    然后拼说明 AttributeError（指令已经写了、页面收到 500）。"""
    monkeypatch.setattr(panel.MO, "paper_refuse", lambda tag, agents=None: None)
    now = TIMES["after"]
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"]})   # 拿着 1 只：名额还有
    _sm()
    ok, msg, rec = _go({"kind": "buy", "ticker": "6501", "unit": "shares", "value": 100, "fund": "all"}, now)
    assert ok and msg.startswith("已写：买入 6501 日立製作所（100 股）→ 10/07 开盘买入")   # 当成普通买入（以前：写了一条「全部换成」再崩溃）
    assert [(r["kind"], r.get("fund")) for r in MO.read_all("paper")] == [("buy", None)]
    _setup()
    ok, msg, rec = _go({"kind": "core", "pct": 10, "fund_for": "6501.T", "batch": "all", "prev_pct": 5, "dir": 1}, now)
    assert ok and msg.startswith("已写：闲置资金比例 10%")
    assert not {"fund_for", "batch", "prev_pct", "dir"} & set(MO.read_all("paper")[0])
