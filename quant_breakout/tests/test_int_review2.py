"""整合复核 2（2026-10-16，事后）：
- 写了撤单、撤单的运行没处理到的被挡（BLOCKED、没有注文番号）的单：对账记为已撤，手动买入 / 卖出不留到下一次决策重新下；
- 撤单时立花回「已经全部成交」的单：交易页 / 撤单按钮 / 持仓 / 手动指令的检查都按已成交（以前只认快照）；
- 「今天还能买 / 卖几次」的总数按含今天已成交的持仓数；没拿着的核心 ETF 写「买入…」（与「持仓」的按钮同名）；
- 文档几句（MACOS.md 上线头几天、盘中自动下单暂停；CLAUDE.md 的 today_why）。"""
import datetime as dt
import json
import re
from pathlib import Path

import pytest

from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import panel
from qbreak.brokers.base import Order
from qbreak.calendar_jp import JST

from test_cancel_group import BUY, SELL, D, T9, _Rec, _at_exch, _gbook, _ord, _run_req, _tbook  # noqa: F401
from test_trade_room import _bk, _o, _room
from test_trade_today import _parts

ROOT = Path(__file__).resolve().parents[1]
_CID_T = re.compile(r"^U(\d{4}-\d{2}-\d{2})-(BUY|SELL)-([0-9A-Z]{1,4}\.T)(-[0-9A-Za-z]{1,20})?$")


# ───────────── 撤单时立花回已经全部成交 ─────────────
class _FullFill(_Rec):
    """立花：撤单没受理，查状态 = 全部約定。"""
    def __init__(self, q):
        super().__init__()
        self.q = q

    def cancel_order(self, bid, day):
        self.calls.append(bid)
        return False

    def order_status(self, bid, day):
        if bid == "B1":
            return {"final": "FILLED", "filled_qty": self.q, "avg_px": 1490.0, "status": "全部約定"}
        return {"final": "CANCELLED", "filled_qty": 0, "status": "取消完了"}


def test_full_fill_found_on_cancel_is_done_everywhere():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    _at_exch(b, SELL, "S1")
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": BUY}, clock=lambda: T9)
    _run_req(p, _FullFill(678))
    b = json.loads(p.read_text(encoding="utf-8"))
    o = next(x for x in b["orders"] if x["cid"] == BUY)
    assert o["status"] == "SENT" and LO.note_full(o)                         # 账本不动（明早对账照常查立花）
    t1 = T9 + dt.timedelta(minutes=2)
    pj = LO.held_now(b, "tachibana", now=t1)
    assert BUY not in [x["cid"] for x in pj["pending"]]                      # 以前「还在等成交」
    f = next(x for x in pj["fills"] if x["cid"] == BUY)
    assert f["qty"] == 678 and f["src"] == "cancel_check" and f["approx"]
    ol = LO.outlook(b, MO.unseen("tachibana", b), t1, tag="tachibana", halt=False)
    assert ol["orders"][BUY]["state"] == "done" and ol["orders"][BUY]["chip"] == LO.NOTE_DONE
    assert LO.cancel_why(o, b, t1, False) == f"{LO.NOTE_DONE}，不用撤"       # 以前 None（给「撤单」）
    tl = panel._trade_live(b, MO.unseen("tachibana", b), t1, "tachibana")
    assert tl["split"]["orders"][BUY] == "ended" and tl["n"] == 1             # 以前 2
    top, _later, ended = _parts(panel.render("tachibana", "t" * 40, t1))
    assert f"data-cid='{BUY}'" not in top and LO.NOTE_DONE in ended


def test_manual_buy_full_fill_found_on_cancel_ends_the_instruction(monkeypatch):
    monkeypatch.setattr(MO, "_CID", _CID_T)
    mb = f"U{D}-BUY-7203.T-N100500"

    class _F(_Rec):
        def cancel_order(self, bid, day):
            return False

        def order_status(self, bid, day):
            return {"final": "FILLED", "filled_qty": 100, "avg_px": 2500.0, "status": "全部約定"}
    b = _gbook(sell="FILLED", buy="FILLED")
    b["orders"] += [_ord(mb, "7203.T", "BUY", kind="stock", qty=100, reason="manual_buy", broker_id="B1", limit=2600.0)]
    b["state"]["cash_jpy"] = 1_000_000
    b["manual"]["items"]["M1"] = {"id": "M1", "kind": "buy", "ticker": "7203.T", "status": "placed", "now": True,
                                  "at": "2026-10-15T09:20:00+09:00"}
    b["manual"]["buys"] = {"7203.T": {"id": "M1"}}
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": mb}, clock=lambda: T9)
    _run_req(p, _F())
    b = json.loads(p.read_text(encoding="utf-8"))
    t1 = T9 + dt.timedelta(minutes=2)
    pj = LO.held_now(b, "tachibana", now=t1)
    assert "7203.T" in pj["new"] and not pj["pending"]
    tl = panel._trade_live(b, MO.unseen("tachibana", b), t1, "tachibana")
    assert tl["split"]["orders"][mb] == "ended" and tl["split"]["items"]["M1"] == "ended" and tl["n"] == 0
    t16 = dt.datetime(2026, 10, 15, 16, 0, tzinfo=JST)
    assert MO.check({"kind": "sell", "ticker": "7203.T"}, b, "tachibana", now=t16) is None   # 以前「账本里没有这只持仓」
    why = MO.check({"kind": "buy", "ticker": "7203.T"}, b, "tachibana", now=t1)
    assert "没处理完的手动指令" not in str(why) and "已经买进 100 股" in str(why)


def test_full_fill_note_survives_a_long_note_and_is_not_repeated():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    _at_exch(b, SELL, "S1")
    next(x for x in b["orders"] if x["cid"] == BUY)["note"] = "长" * 295
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": BUY}, clock=lambda: T9)
    _run_req(p, _FullFill(678))
    o = next(x for x in json.loads(p.read_text(encoding="utf-8"))["orders"] if x["cid"] == BUY)
    assert LO.CANCEL_FULL in o["note"] and len(o["note"]) <= 300             # 以前 [:300] 把标记截掉
    assert o["note"].count(LO.CANCEL_FULL) == 1


# ───────────── 写了撤单的被挡（BLOCKED）单：对账记为已撤 ─────────────
def _blocking(r, ts):
    real = r.b._place

    def place(ticker, side, qty, limit, *a, **kw):
        if ticker in ts:
            return Order(ticker, side, qty, limit, None, "BLOCKED", client_id=kw.get("client_id"),
                         note="登录失败，没发单（ConnectionError）：测试")
        return real(ticker, side, qty, limit, *a, **kw)
    r.b._place = place


def _hist(r, cid):
    return [o for h in r.ux.book.get("history") or [] for o in h["orders"] if o["cid"] == cid]


@pytest.mark.parametrize("hh", [9, 15])
def test_blocked_manual_buy_with_an_unprocessed_cancel_is_not_bought_again(monkeypatch, hh):
    from qbreak.live_unified import ASKED_UNSENT
    from test_manual_buy import _buy
    from test_manual_orders import TAG, _Run
    monkeypatch.setattr(MO, "_CID", _CID_T)
    r = _Run([1000.0] * 30)
    r.until(14)
    _buy(r, id="M-b")
    r.day()                                                                   # 决策：B.T 等开盘后
    d0 = r.eng.st.last_date
    bo = next(o for o in r.ux.orders if o.ticker == "B.T")
    k = r.k
    _blocking(r, ("B.T",))
    r.exch.open(k)
    r.now["t"] = dt.datetime.combine(r.eng.gidx[k].date(), dt.time(9, 5), tzinfo=JST)
    r.ux.open_phase()                                                         # 09:05：登录失败 → BLOCKED（没有注文番号）
    assert bo.status == "BLOCKED" and not bo.broker_id
    tc = dt.datetime.combine(r.eng.gidx[k].date(), dt.time(hh, 10), tzinfo=JST)
    MO.append(TAG, {"kind": "cancel_order", "cid": bo.cid}, clock=lambda: tc)   # 写了撤单；撤单的运行没来
    r.exch.close_day()
    r.exch.set_day(k + 1)
    r.now["t"] = r.at(k)
    r.ux.morning([k])                                                         # 下一个 07:40：对账
    r.k += 1
    h = _hist(r, bo.cid)
    assert h and h[0]["status"] == "CANCELLED" and h[0]["note"] == ASKED_UNSENT
    assert r.item("M-b")["status"] == "cancelled"                             # 以前：系统原因 → 留到这次决策、又买
    assert not any(o.ticker == "B.T" and o.side == "BUY" for o in r.ux.orders if o.decided_on != d0)


def test_blocked_manual_sell_with_an_unprocessed_cancel_is_not_sold_again(monkeypatch):
    from test_manual_buy import _buy
    from test_manual_orders import TAG, _Run, _sell_req
    monkeypatch.setattr(MO, "_CID", _CID_T)
    r = _Run([1000.0] * 40, entry=(10,))
    r.until(14)
    _sell_req(r, id="M-s")
    _buy(r, id="M-b")                                                         # 靠这笔卖单的钱的买入（等开盘后）
    _blocking(r, ("A.T", "B.T"))
    r.day()
    d0 = r.eng.st.last_date
    so = next(o for o in r.ux.orders if o.ticker == "A.T" and o.side == "SELL")
    bo = next(o for o in r.ux.orders if o.ticker == "B.T")
    assert so.status == "BLOCKED" and not so.broker_id and bo.status == "DEFERRED"
    t902 = dt.datetime.combine(r.eng.gidx[r.k].date(), dt.time(9, 2), tzinfo=JST)
    MO.append(TAG, {"kind": "cancel_order", "cid": so.cid}, clock=lambda: t902)
    r.day()
    assert _hist(r, so.cid)[0]["status"] == "CANCELLED" and r.item("M-s")["status"] == "cancelled"   # 以前：没发出 → 留到下一次决策再卖
    assert r.item("M-b")["status"] != "placed"
    assert not [o for o in r.ux.orders if o.decided_on != d0 and o.ticker in ("A.T", "B.T")]


def test_asked_unsent_covers_blocked_orders_without_a_broker_id():
    from qbreak.live_unified import CANCEL_ASKED, asked_unsent, requeue_next, system_miss
    o = {"cid": "c1", "status": "BLOCKED", "side": "BUY", "phase": "open", "note": "登录失败，没发单（X）：y", "filled_qty": 0}
    assert system_miss(o) and requeue_next(o, [o], None) is True               # 没写撤单：系统原因 → 照旧留到下一次决策
    assert asked_unsent(o, {"c1"}) and requeue_next(o, [o], None, asked={"c1"}) is False
    o2 = {**o, "note": CANCEL_ASKED}                                         # 整合复核 3：说明本身不算撤单（撤单已经结束 → 照常）
    assert asked_unsent(o2, {"c1"}) and not asked_unsent(o2) and system_miss(o2) is not None
    assert not asked_unsent({**o, "broker_id": "B9"}, {"c1"})                 # 发到交易所了：照旧由撤单的运行撤


# ───────────── 今天还能买 / 卖几次：按含今天已成交的持仓数 ─────────────
def _swap_book():
    b = _bk(pos={}, cores={"1545.T": 100}, orders=[_o("1545.T", "SELL", qty=100, px=2400.0, kind="core", at="09:10"),
                                                   _o("1482.T", "BUY", qty=50, px=1490.0, kind="core", at="09:40")])
    b["core_rule"]["lot"]["1482.T"] = 1
    b["core_rule"]["px"]["1482.T"] = 1490.0
    return b


def test_headline_counts_follow_holdings_including_todays_fills():
    R = _room(_swap_book())
    pt = R["per_ticker"]
    assert pt["1482.T"]["sell"]["n"] == 1
    assert R["overall"]["sell_left"]["n"] == 1                                 # 以前 0（1482 那一行却是卖 ✓）
    assert "里今天还能卖 1 只" in R["overall"]["sell_left"]["why"]
    assert R["overall"]["buy_left"]["adds"] == 1                               # 1482（今天买进）；以前数的是今天已卖光的 1545
    assert R["overall"]["trades_left"]["n"] == R["overall"]["buy_left"]["n"] + 1 - 1


def test_unheld_core_says_buy_button_like_the_holdings_page():
    pt = _room(_swap_book())["per_ticker"]
    assert pt["1545.T"]["buy"]["via"] == "「买入…」（= 固定口数）"            # 现在 0 口、没固定：「持仓」的按钮叫「买入…」
    assert pt["1482.T"]["buy"]["via"] == "「固定口数…」"


# ───────────── 文档 ─────────────
def test_docs_follow_the_behaviour():
    mac = (ROOT / "MACOS.md").read_text(encoding="utf-8")
    assert "（成交了的在下面「已结束 / 不是今天的」）对得上" not in mac
    assert "寄付单成交了，面板也先写「已下单（等成交）」" in mac
    assert "「等下个交易日 07:40 的运行」" not in mac and "「等 MM/DD（周X）07:40 的运行」" in mac
    assert "暂停发生在 09:30 之前时 09:30 自检也会没通过" in mac
    md = ROOT.parent / "CLAUDE.md"
    if md.exists():
        assert "MO.today_why" in md.read_text(encoding="utf-8")
    sc = (ROOT / "var" / "sim_changes.md").read_text(encoding="utf-8")
    assert "整合复核 2" in sc and "已知限制（事后）" in sc
