"""整组撤单（2026-10-16 用户：「如果一起下的买单和卖单的话要可以一起进行撤单 而不是一个个撤单」）。
同一组 = 当前决策里一起下的单：早上照固定口数排的凑钱卖单 + 买单、盘中的固定口数 / 手动买入 + 为它凑钱卖的、「平摊凑 / 全部换成」同一次写的个股卖出、
拆成两笔（-2）的单。撤的顺序：先撤买单，确认没成交再撤卖单；买单已经成交 / 撤不掉 / 立花 10 分钟还没确认 → 卖单不撤（撤了买的钱不够）。"""
import datetime as dt
import json
import re
from types import SimpleNamespace

import pytest

from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST
from qbreak.live_unified import CANCEL_ASKED, ExecOrder

from test_core_etf_restore import _paper2
from test_fund_src import _CancelOK, _NoBroker, _dict_book, _fixed_case
from test_manual_now import _at
from test_panel import AT15, _book1015, _card

D = "2026-10-14"
SELL, BUY = f"U{D}-SELL-1545.T", f"U{D}-BUY-1482.T"
T0 = dt.datetime(2026, 10, 15, 8, 30, tzinfo=JST)
T9 = dt.datetime(2026, 10, 15, 9, 30, tzinfo=JST)
BOOK_T = "live_unified_tachibana.json"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(LO, "_sleep", lambda s: None)


def _gbook(sell="SENT", buy="DEFERRED", **kw):
    """2026-10-15 的那一对（卖 1545 4,110 口寄付 + 买 1482 678 口等开盘后），带上来源（src）：同一组。"""
    b = _dict_book(sell, buy, **kw)
    b["orders"][0]["src"] = "fix_fund"
    b["orders"][1]["src"] = "core_fix"
    return b


def _at_exch(b, cid, bid, status="SENT"):
    o = next(x for x in b["orders"] if x["cid"] == cid)
    o.update(status=status, broker_id=bid, order_date="20261015", sent_qty=int(o["qty"]))
    return o


def _xo(b):
    return [ExecOrder.from_dict(o) for o in b["orders"]]


def _ord(cid, t, side, kind="core", qty=100, status="SENT", **kw):
    o = {"cid": cid, "ticker": t, "side": side, "kind": kind, "qty": qty, "decided_on": D, "ref_px": 1000.0, "phase": "now",
         "status": status, "sent_qty": qty if status in ("SENT", "PARTIAL", "FILLED") else 0, "filled_qty": 0, "note": ""}
    if status in ("SENT", "PARTIAL", "FILLED"):
        o.update(broker_id="X" + cid[-6:], order_date="20261015")
    o.update(kw)
    return o


class _Rec(_CancelOK):
    """立花：撤单都受理、马上取消完了；记下撤单的顺序。"""
    def __init__(self):
        self.calls = []

    def cancel_order(self, bid, day):
        self.calls.append(bid)
        return True


class _Pending(_Rec):
    """立花：撤单受理了，前 k 次查状态都还是「取消中」，之后取消完了。"""
    def __init__(self, k):
        super().__init__()
        self.k, self.n = k, 0

    def order_status(self, bid, day):
        self.n += 1
        if self.n <= self.k:
            return {"final": "", "status": "取消中", "filled_qty": 0}
        return {"final": "CANCELLED", "filled_qty": 0, "status": "取消完了"}


class _PartFill(_Rec):
    """立花：撤单受理了，撤的时候已经成交了 100 股 / 口。"""
    def order_status(self, bid, day):
        return {"final": "CANCELLED", "filled_qty": 100, "avg_px": 1500.0, "status": "取消完了"}


class _PaperQ:
    """模拟券商：排队的寄付单能撤（cancel_pending），记下撤的时候那笔买单已经是什么状态。"""
    def __init__(self, orders):
        self.orders, self.calls = orders, []

    def cancel_pending(self, cid):
        buy = next(o for o in self.orders if o.cid == BUY)
        self.calls.append((cid, buy.status))
        return True

    def cash(self):
        return 191.678


# ══════════════════════════ 同一组的定义 ══════════════════════════
def test_groups_morning_pair_and_split_buy_first():
    b = _gbook()
    b["orders"].append({**b["orders"][1], "cid": BUY + "-2", "qty": 1, "status": "PLANNED"})     # 拆成两笔的买单
    b["orders"].append({**b["orders"][0], "cid": f"U{D}-SELL-2845.T", "ticker": "2845.T", "src": "rule", "broker_id": "S9"})
    G = LO.groups(b["orders"], b)
    assert G[SELL] == [BUY, BUY + "-2", SELL] and G[BUY] == G[SELL] == G[BUY + "-2"]
    assert f"U{D}-SELL-2845.T" not in G                                     # 规则的核心卖单不在组里
    assert LO.groups(_dict_book()["orders"], _dict_book()) == {}             # 旧账本（没有 src）：没有组
    assert [x["cid"] for x in LO.group_of(b["orders"][2], b["orders"], b)] == [BUY, BUY + "-2", SELL]


def test_groups_intraday_fixed_units_use_fix_fund_cids_not_the_filled_morning_buy():
    b = _gbook(sell="FILLED", buy="FILLED")
    b["orders"][1].update(filled_qty=678, broker_id="B1", order_date="20261015", sent_qty=678)
    ib = _ord(f"U{D}-BUY-1482.T-N1", "1482.T", "BUY", qty=10, reason="core_fix", src="core_fix", fund_src=[f"U{D}-SELL-1545.T-N1"])
    s1 = _ord(f"U{D}-SELL-1545.T-N1", "1545.T", "SELL", qty=50, reason="fix_fund", src="fix_fund")
    s2 = _ord(f"U{D}-SELL-2845.T-N1", "2845.T", "SELL", qty=3, reason="fix_fund", src="fix_fund")
    b["orders"] += [ib, s1, s2]
    b["core_rule"]["fix_fund"] = {"1482.T": {"units": 688, "cids": [s2["cid"]]}}
    G = LO.groups(b["orders"], b)
    assert G[ib["cid"]] == [ib["cid"], s1["cid"], s2["cid"]]
    assert BUY not in G[ib["cid"]] and G[BUY] == [BUY, SELL]                # 早上已经成交的那一对是另一组


def test_groups_intraday_manual_buy_takes_only_its_manual_fund_sells():
    b = _gbook()
    mb = _ord(f"U{D}-BUY-7203.T-N1", "7203.T", "BUY", kind="stock", qty=100, reason="manual_buy",
              fund_src=[f"U{D}-SELL-1545.T-N1", f"U{D}-SELL-2845.T"])
    mf = _ord(f"U{D}-SELL-1545.T-N1", "1545.T", "SELL", qty=500, reason="manual_fund")
    rs = _ord(f"U{D}-SELL-2845.T", "2845.T", "SELL", qty=5, phase="morning", src="rule")
    b["orders"] += [mb, mf, rs]
    G = LO.groups(b["orders"], b)
    assert G[mb["cid"]] == [mb["cid"], mf["cid"]] and rs["cid"] not in G


@pytest.mark.parametrize("fund", ["split", "all"])
def test_groups_split_or_allin_companion_sells_but_not_a_separate_manual_sell(fund):
    b = _gbook()
    at = "2026-10-14T20:00:00+09:00"
    b["manual"]["items"] = {
        "M-buy": {"id": "M-buy", "kind": "buy", "ticker": "7203.T", "fund": fund, "at": at, "status": "placed"},
        "M-s1": {"id": "M-s1", "kind": "sell", "ticker": "6758.T", "fund_for": "7203.T", "at": at, "status": "placed"},
        "M-s2": {"id": "M-s2", "kind": "sell", "ticker": "9984.T", "at": "2026-10-14T19:00:00+09:00", "status": "placed"}}
    b["manual"]["buys"] = {"7203.T": {"id": "M-buy"}}
    mb = _ord(f"U{D}-BUY-7203.T", "7203.T", "BUY", kind="stock", phase="morning", status="PLANNED", reason="manual_buy")
    s1 = _ord(f"U{D}-SELL-6758.T", "6758.T", "SELL", kind="stock", phase="morning", reason="manual")
    s2 = _ord(f"U{D}-SELL-9984.T", "9984.T", "SELL", kind="stock", phase="morning", reason="manual")
    b["orders"] += [mb, s1, s2]
    G = LO.groups(b["orders"], b)
    assert G[mb["cid"]] == [mb["cid"], s1["cid"]] and s2["cid"] not in G


# ══════════════════════════ 指令记录 ══════════════════════════
def test_normalize_grp_and_describe():
    r = MO.normalize({"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY, BUY, SELL]})
    assert r["grp"] == [BUY]                                                 # 去重、去掉主单
    assert "grp" not in MO.normalize({"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": []})
    bad = [{"grp": [BUY]},                                                   # 没有 deps=cancel
           {"deps": "keep", "grp": [BUY]},
           {"deps": "cancel", "grp": ["U2026-10-13-BUY-1482.T"]},           # 不是同一天的决策
           {"deps": "cancel", "grp": ["U2026-10-14-BUY-xyz"]},              # 单号写错
           {"deps": "cancel", "grp": [f"U{D}-BUY-{1000 + i}.T" for i in range(MO.GROUP_MAX)]},   # 超过 11 笔
           {"deps": "cancel", "grp": BUY}]                                   # 不是列表
    for x in bad:
        with pytest.raises(ValueError):
            MO.normalize({"kind": "cancel_order", "cid": SELL, **x})
    assert MO.describe(MO.normalize({"kind": "cancel_order", "cid": SELL})) == f"撤单 1545 纳斯达克 100（{SELL}）"
    assert MO.describe(r) == f"撤单 1545 纳斯达克 100（{SELL}） + 同一组 1 笔（买 1482 对冲版美国 7〜10 年国债）"


def test_cancel_cids_and_asked_cids_cover_unread_and_pending_but_not_voided():
    assert MO.cancel_cids({"cid": SELL, "grp": [BUY, SELL, ""]}) == [SELL, BUY]
    b = _gbook()
    b["manual"]["items"] = {"M1": {"id": "M1", "kind": "cancel_order", "cid": "U2026-10-14-SELL-2845.T",
                                   "grp": ["U2026-10-14-BUY-2846.T"], "status": "pending"},
                            "M2": {"id": "M2", "kind": "cancel_order", "cid": "U2026-10-14-SELL-7203.T",
                                   "grp": ["U2026-10-14-BUY-6758.T"], "status": "done"}}
    waiting = [{"id": "W1", "kind": "cancel_order", "cid": SELL, "grp": [BUY]},
               {"id": "W2", "kind": "cancel_order", "cid": "U2026-10-14-SELL-9984.T", "grp": ["U2026-10-14-BUY-9983.T"]},
               {"id": "W3", "kind": "uncancel", "target": "W2"}]
    assert LO.asked_cids(b, waiting) == {SELL, BUY, "U2026-10-14-SELL-2845.T", "U2026-10-14-BUY-2846.T"}
    MO.append("paper", {"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY]}, clock=lambda: T0)
    b = _gbook()
    MO.Manual(b, "paper", lambda: T0).ingest(only=("cancel_order",))
    it = next(iter(b["manual"]["items"].values()))
    assert it["grp"] == [BUY] and it["msg"] == "等执行器整组撤单（2 笔）"


def test_check_and_group_prune():
    b = _gbook()
    rec = MO.normalize({"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY]})
    assert MO.check(rec, b, "paper", now=AT15) is None
    b["orders"].append({**b["orders"][0], "cid": f"U{D}-SELL-2845.T", "ticker": "2845.T", "src": "rule", "broker_id": "S9"})
    r2 = MO.normalize({"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [f"U{D}-SELL-2845.T"]})
    assert "不在 1545 纳斯达克 100 这一组里" in MO.check(r2, b, "paper", now=AT15)
    r3 = MO.normalize({"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [f"U{D}-BUY-7203.T"]})
    assert "账本里没有" in MO.check(r3, b, "paper", now=AT15) and "7203 トヨタ自動車" in MO.check(r3, b, "paper", now=AT15)
    b["manual"]["items"] = {"M9": {"id": "M9", "kind": "cancel_order", "cid": BUY, "status": "pending"}}
    assert "已经在撤（等执行器）" in MO.check(rec, b, "paper", now=AT15)
    b = _gbook()                                                             # 页面过期：同一组里一笔已经成交了
    b["orders"].append({**b["orders"][1], "cid": BUY + "-2", "qty": 1, "status": "FILLED", "sent_qty": 1, "filled_qty": 1})
    r4 = MO.normalize({"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY, BUY + "-2"]})
    out, notes = MO.group_prune(r4, b, AT15, True)
    assert out["grp"] == [BUY] and len(notes) == 1 and "现在撤不了" in notes[0] and "1482 对冲版美国 7〜10 年国债" in notes[0]
    b["orders"][1]["status"] = "FILLED"
    with pytest.raises(ValueError, match="同一组的其他单现在都撤不了"):
        MO.group_prune(r4, b, AT15, True)


# ══════════════════════════ 撤单引擎 ══════════════════════════
def test_paper_0830_buy_cancelled_locally_before_the_queued_sell():
    b = _gbook()
    orders = _xo(b)
    pq = _PaperQ(orders)
    res = LO.cancel_core(orders, b, lambda: pq, [SELL], paper=True, now=T0, source="test", groups={SELL: [BUY]}, tag="paper")
    assert [x["cid"] for x in res["done"]] == [BUY, SELL]
    assert pq.calls == [(SELL, "CANCELLED")]                                 # 撤卖单的时候买单已经撤了
    assert all(o.status == "CANCELLED" for o in orders) and res["grp"][SELL]["state"] == "all"
    assert LO.cancel_text(res)[0] == "整组撤单（2 笔：卖 1545 纳斯达克 100 这一组）：都撤了"


def test_filled_buy_keeps_the_sell():
    b = _gbook(sell="SENT", buy="FILLED")
    b["orders"][1].update(broker_id="B1", order_date="20261015", sent_qty=678, filled_qty=678)
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _Rec(), [SELL], paper=False, now=T9, source="test", groups={SELL: [BUY]})
    assert orders[0].status == "SENT" and res["by_cid"][SELL][0] == "skipped" and "卖单不撤" in res["by_cid"][SELL][1]
    g = res["grp"][SELL]
    assert g["state"] == "part" and g["line"].startswith("★ ") and "买 1482 对冲版美国 7〜10 年国债 已经成交 678 口" in g["line"]
    assert any(lv == "warn" and m == g["line"] for lv, m in res["events"])


def test_tachibana_partial_fill_on_cancel_keeps_the_sell():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    br = _PartFill()
    res = LO.cancel_core(orders, b, lambda: br, [SELL], paper=False, now=T9, source="test", groups={SELL: [BUY]})
    assert orders[1].status == "CANCELLED" and orders[1].filled_qty == 100 and orders[0].status == "SENT"
    assert br.calls == ["B1"] and res["grp"][SELL]["state"] == "part"


def _tbook(b):
    p = paths.state_dir() / BOOK_T
    p.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return p


def _items(p):
    return list(json.loads(p.read_text(encoding="utf-8"))["manual"]["items"].values())


def test_tachibana_wait_then_recheck_without_resending():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY]}, clock=lambda: T9)
    br = _Pending(LO.GROUP_POLLS)
    res = LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: T9, source="面板的撤单指令")
    assert res["grp"][SELL]["state"] == "wait" and br.calls == ["B1"] and [x["cid"] for x in res["pending"]] == [BUY]
    it = _items(p)[0]
    assert it["status"] == "pending" and it["grp_wait"] == [BUY] and it["recheck_at"] == "2026-10-15T09:31:00+09:00"
    assert "约 1 分钟后再查" in it["msg"]
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert not MO.cancel_due("tachibana", saved, T9 + dt.timedelta(seconds=30))
    assert MO.cancel_due("tachibana", saved, T9 + dt.timedelta(seconds=61))
    t2 = T9 + dt.timedelta(seconds=61)
    res = LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: t2, source="面板的撤单指令")
    assert br.calls == ["B1", "S1"]                                          # 买单的撤单不再发
    st = {o["cid"]: o["status"] for o in json.loads(p.read_text(encoding="utf-8"))["orders"]}
    assert st == {SELL: "CANCELLED", BUY: "CANCELLED"} and res["grp"][SELL]["state"] == "all"
    it = _items(p)[0]
    assert it["status"] == "done" and "grp_wait" not in it and "recheck_at" not in it


def test_tachibana_gives_up_after_ten_minutes_and_keeps_the_sell():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY]}, clock=lambda: T9)
    br = _Pending(10 ** 6)
    LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: T9)
    t2 = T9 + dt.timedelta(seconds=MO.GROUP_WAIT_MAX_S)
    res = LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: t2)
    assert res["grp"][SELL]["state"] == "gaveup" and br.calls == ["B1"]
    st = {o["cid"]: o["status"] for o in json.loads(p.read_text(encoding="utf-8"))["orders"]}
    assert st[SELL] == "SENT"
    it = _items(p)[0]
    assert it["status"] == "done" and "kabuka.e-shiten.jp/mfds_smp.php" in it["msg"] and "grp_wait" not in it


def test_a_buy_that_appeared_after_you_confirmed_is_not_cancelled_and_keeps_the_sell():
    b = _gbook()
    b["orders"].append({**b["orders"][1], "cid": BUY + "-2", "qty": 1})      # 你点的时候还没有的拆单（DEFERRED）
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _Rec(), [SELL], paper=False, now=T0, source="test", groups={SELL: [BUY]})
    by = {o.cid: o.status for o in orders}
    assert by == {SELL: "SENT", BUY: "CANCELLED", BUY + "-2": "DEFERRED"}
    assert res["grp"][SELL]["state"] == "part" and "你确认之后才出现" in res["grp"][SELL]["line"]


def test_paper_0910_buy_cancelled_but_the_sell_is_already_at_the_open():
    b = _gbook()
    orders = _xo(b)
    t = dt.datetime(2026, 10, 15, 9, 10, tzinfo=JST)
    res = LO.cancel_core(orders, b, lambda: _NoBroker(), [SELL], paper=True, now=t, source="test", groups={SELL: [BUY]})
    assert orders[1].status == "CANCELLED" and orders[0].status == "SENT"
    g = res["grp"][SELL]
    assert g["state"] == "part" and "寄付单已经在 09:00 开盘" in g["line"]


def test_blocked_member_that_would_retry_is_cancelled_locally_then_the_sell():
    b = _gbook()
    b["orders"][1].update(status="BLOCKED", note="登录失败，没发单")
    orders = _xo(b)
    br = _Rec()
    res = LO.cancel_core(orders, b, lambda: br, [SELL], paper=False, now=T0, source="test", groups={SELL: [BUY]})
    assert orders[1].status == "CANCELLED" and "被挡" in orders[1].note
    assert orders[0].status == "CANCELLED" and br.calls == ["S1"] and res["grp"][SELL]["state"] == "all"


def test_recheck_goes_on_when_the_main_order_is_already_cancelled_and_dup_cids_run_once():
    b = _gbook()
    b["orders"][1]["status"] = "CANCELLED"                                   # 主单（买）第一次就在本地撤了
    b["orders"].append(_ord(BUY + "-2", "1482.T", "BUY", qty=1, phase="open", src="core_fix", broker_id="B2"))
    orders = _xo(b)
    br = _Rec()
    w = {BUY: {"wait": [BUY + "-2"], "since": T9.isoformat(), "all": [BUY, BUY + "-2", SELL]}}
    res = LO.cancel_core(orders, b, lambda: br, [BUY], paper=False, now=T9, source="test", groups={BUY: [SELL, BUY + "-2"]}, waits=w)
    assert br.calls == ["S1"] and all(o.status == "CANCELLED" for o in orders) and res["grp"][BUY]["state"] == "all"
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    br = _Rec()
    res = LO.cancel_core(orders, b, lambda: br, [SELL, BUY, SELL], paper=False, now=T9, source="test",
                         groups={SELL: [BUY], BUY: [SELL]})
    assert br.calls == ["B1", "S1"] and all(o.status == "CANCELLED" for o in orders)


def test_halt_cancel_takes_buys_first_without_the_gate():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    br = _Rec()
    LO.cancel_core(orders, b, lambda: br, None, paper=False, now=T9, source="test")
    assert br.calls == ["B1", "S1"]
    b = _gbook(buy="FILLED")                                                  # 买单已经成交：停并撤单照样撤卖单（不设闸门）
    b["orders"][1].update(broker_id="B1", order_date="20261015", sent_qty=678, filled_qty=678)
    orders = _xo(b)
    br = _Rec()
    LO.cancel_core(orders, b, lambda: br, None, paper=False, now=T9, source="test")
    assert br.calls == ["S1"] and orders[0].status == "CANCELLED"


def test_executor_does_not_send_a_deferred_buy_you_asked_to_cancel():
    from test_paper_open_settle import _feed
    r = _paper2()
    sell, buy = _fixed_case(r)
    r.ux.save(force=True)
    MO.append(r.tag, {"kind": "cancel_order", "cid": sell.cid, "deps": "cancel", "grp": [buy.cid]}, clock=lambda: _at(r, 9, 20))
    r.now["t"] = _at(r, 9, 25)
    r.ux.open_phase(feed=_feed(r))
    assert buy.status == "DEFERRED" and buy.note == CANCEL_ASKED and "执行器不发" in buy.note
    assert any("不发：" + CANCEL_ASKED in e["msg"] for e in r.ux.book["events"])


def test_cancelling_the_intraday_fixed_pair_does_not_requeue_the_fixed_units_today():
    b = _gbook(sell="FILLED", buy="FILLED")
    ib = _ord(f"U{D}-BUY-1482.T-N1", "1482.T", "BUY", qty=10, reason="core_fix", src="core_fix", fund_src=[f"U{D}-SELL-1545.T-N1"])
    s1 = _ord(f"U{D}-SELL-1545.T-N1", "1545.T", "SELL", qty=50, reason="fix_fund", src="fix_fund")
    b["orders"] += [ib, s1]
    b["manual"]["core_fix"] = {"1482.T": 688}
    b["core_rule"].update(fix_applied={"1482.T": 688}, fix_fund={"1482.T": {"units": 688, "cids": [s1["cid"]]}})
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _Rec(), [ib["cid"]], paper=False, now=T9, source="test", groups={ib["cid"]: [s1["cid"]]})
    assert res["grp"][ib["cid"]]["state"] == "all"
    b["orders"] = [o.__dict__ for o in orders]
    assert MO.corefix_pending(b, "tachibana", T9) == {}
    assert b["manual"]["core_fix"] == {"1482.T": 688}                        # 固定口数不自动取消


# ══════════════════════════ 面板 ══════════════════════════
def _pbook(tag="paper"):
    b = _book1015(tag, sell="SENT")
    b["orders"][0]["src"] = "fix_fund"
    b["orders"][1].update(src="core_fix", fund_src=[SELL])
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


def _btn(card, cid):
    i = card.index(f"data-cid='{cid}'")
    return card[i:card.index(">撤单</button>", i)]


@pytest.mark.parametrize("mode", ["local", "remote"])
def test_panel_group_buttons(mode):
    _pbook()
    kw = {"mode": "remote", "device": {"name": "x", "kind": "ts", "id": "ts"}} if mode == "remote" else {}
    card = _card(panel.render("paper", "t" * 40, AT15, **kw), "today")
    sb = _btn(card, SELL)
    assert f"data-grp='{BUY}'" in sb and "data-solo='" in sb and sb.endswith("data-name='纳斯达克 100'")
    gl = re.search(r"data-glist='([^']*)'", sb).group(1)
    assert "先撤买单" in gl and "买 1482 对冲版美国 7〜10 年国债" in gl
    bb = _btn(card, BUY)
    assert f"data-grp='{SELL}'" in bb and "data-solo='只撤这笔买单（卖 1545 纳斯达克 100 照常卖，钱留现金）'" in bb
    assert card.count(f"data-g='{BUY}'") == 2 and card.count("同一组（一起下的）还有：") == 2
    assert "同一组 2 笔" in card


def test_panel_submit_group_cancel_marks_both_rows_and_calls_the_runner():
    _pbook()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY]}, AT15)
    assert ok and "执行器马上撤" in msg and "同一组" in msg and rec["grp"] == [BUY]
    card = _card(panel.render("paper", "t" * 40, AT15), "today")
    assert card.count("<span class='chip'>撤单中</span>") == 2
    ok2, msg2, _ = panel.submit({"book": "paper", "kind": "cancel_order", "cid": BUY, "deps": "cancel", "grp": [SELL]}, AT15)
    assert not ok2 and "已经在撤" in msg2
    calls = []
    trg = panel.Trigger(run=lambda tag, mode="retry": calls.append((tag, mode)) or SimpleNamespace(poll=lambda: 0),
                        clock=lambda: AT15, mono=lambda: 1000.0)
    trg.check()
    assert ("paper", "cancel") in calls


# ══════════════════════════ 命令行 ══════════════════════════
def _cli(monkeypatch, b, now=T9):
    import run
    from test_live_ops import _unified_home
    _unified_home()
    p = _tbook(b)
    monkeypatch.setattr(LO, "now_jst", lambda: now)
    monkeypatch.setattr(MO, "now_jst", lambda: now)
    monkeypatch.setattr("qbreak.calendar_jp.now_jst", lambda: now)
    return run, p


def test_cli_preview_is_read_only(monkeypatch, capsys):
    b = _gbook()
    _at_exch(b, BUY, "B1")
    run, p = _cli(monkeypatch, b)
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: (_ for _ in ()).throw(AssertionError("预览不该连券商")))
    before = p.read_bytes()
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group", "--preview"]) == 0
    out = capsys.readouterr().out
    assert "整组撤单预览（不连券商、不改账本）：卖 1545 纳斯达克 100（" + SELL + "）所在的一组 2 笔" in out
    assert "· 撤：买 1482 对冲版美国 7〜10 年国债：678 口" in out and "· 撤：卖 1545 纳斯达克 100：4,110 口" in out
    assert p.read_bytes() == before
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", f"U{D}-BUY-7203.T", "--group", "--preview"]) == 1


def test_cli_group_flags_and_cancel(monkeypatch, capsys):
    b = _gbook()
    _at_exch(b, BUY, "B1")
    run, p = _cli(monkeypatch, b)
    br = _Rec()
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: br)
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", "--group"]) == 2
    assert "--group 要和一笔单的 cid 一起用" in capsys.readouterr().out
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group", "--preview", "--halt-first"]) == 2
    assert "预览不建 HALT" in capsys.readouterr().out and not paths.halt_file().exists()
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--preview"]) == 2
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group"]) == 0
    out = capsys.readouterr().out
    assert "整组撤单（2 笔：卖 1545 纳斯达克 100 这一组）：都撤了" in out and br.calls == ["B1", "S1"]
    st = {o["cid"]: o["status"] for o in json.loads(p.read_text(encoding="utf-8"))["orders"]}
    assert st == {SELL: "CANCELLED", BUY: "CANCELLED"}


def test_cli_push_titles(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr("qbreak.notify.send", lambda title, body, level="info": sent.append((title, level)) or True)
    b = _gbook()
    _at_exch(b, BUY, "B1")
    run, p = _cli(monkeypatch, b)
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: _Rec())
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group", "--notify"]) == 0
    assert sent[-1][0] == "qbreak 立花实盘 整组撤单"
    b = _gbook()
    _at_exch(b, BUY, "B1")
    run, p = _cli(monkeypatch, b)
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: _PartFill())
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group", "--notify"]) == 0
    assert sent[-1][0].startswith("★ 交易：qbreak 立花实盘 整组撤单") and sent[-1][1] == "warn"
    b = _gbook()                                                             # 面板的撤单指令：第一次（买单取消中）推一条，还在等的复查不推
    _at_exch(b, BUY, "B1")
    run, p = _cli(monkeypatch, b)
    br = _Pending(10 ** 6)
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: br)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY]}, clock=lambda: T9)
    n0 = len(sent)
    assert run.main(["live-u", "--broker", "tachibana", "--phase", "cancel", "--notify"]) == 0
    assert len(sent) == n0 + 1 and sent[-1][0] == "qbreak 立花实盘 整组撤单"
    t2 = T9 + dt.timedelta(seconds=61)
    monkeypatch.setattr(LO, "now_jst", lambda: t2)
    monkeypatch.setattr(MO, "now_jst", lambda: t2)
    assert run.main(["live-u", "--broker", "tachibana", "--phase", "cancel", "--notify"]) == 0
    assert len(sent) == n0 + 1
    assert _items(p)[0]["status"] == "pending"


def test_liveu_cancel_plan_passes_group_preview(tmp_path):
    import shutil
    from test_shell_scripts import _bash, _calls, _run_env
    if not shutil.which("bash"):
        pytest.skip("需要 bash")
    from pathlib import Path
    txt = (Path(__file__).resolve().parent.parent / "scripts" / "liveu.sh").read_text(encoding="utf-8")
    i = txt.index('if [ "${1:-}" = "cancel-plan" ]')
    assert "--group --preview" in txt[i:txt.index("\nfi\n", i)]
    env, log = _run_env(tmp_path, 0)
    _bash(env, "scripts/liveu.sh", "cancel-plan", SELL, "--broker", "tachibana")
    assert f"run.py live-u --broker tachibana --cancel {SELL} --group --preview" in _calls(log)
    env, log = _run_env(tmp_path, 0)
    _bash(env, "scripts/liveu.sh", "cancel", SELL, "--group", "--broker", "tachibana")
    assert f"run.py live-u --group --broker tachibana --cancel {SELL}" in _calls(log)
