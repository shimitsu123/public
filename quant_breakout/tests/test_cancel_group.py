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
    assert g["state"] == "none" and g["line"].startswith("★ ") and "买 1482 对冲版美国 7〜10 年国债 已经成交 678 口" in g["line"]
    assert "一笔都没撤成" in g["line"]                                          # 复核 2：一笔都没撤 → 不说「只撤了一部分」
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


# ══════════════════════════ 复核（2026-10-16）══════════════════════════
class _SellPending(_Rec):
    """立花：买单的撤单马上取消完了；卖单的撤单受理了、一直是「取消中」。"""
    def order_status(self, bid, day):
        if bid == "S1":
            return {"final": "", "status": "取消中", "filled_qty": 0}
        return {"final": "CANCELLED", "filled_qty": 0, "status": "取消完了"}


class _AlreadyCancelling(_Rec):
    """立花：不受理这次撤单（单已经在取消中：之前撤过 / 在立花网站撤的）。"""
    def cancel_order(self, bid, day):
        self.calls.append(bid)
        return False

    def order_status(self, bid, day):
        return {"final": "", "status": "取消中", "filled_qty": 0}


def test_review_check_refuses_a_single_cancel_inside_a_pending_or_unread_group():
    b = _gbook()
    b["manual"]["items"] = {"M1": {"id": "M1", "kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY], "status": "pending"}}
    one = MO.normalize({"kind": "cancel_order", "cid": BUY})                # 只撤这一笔（买）：整组撤单里已经有它
    assert "1482 对冲版美国 7〜10 年国债 的单 " + BUY + " 已经在撤（等执行器）" == MO.check(one, b, "paper", now=AT15)
    b = _gbook()
    MO.append("paper", {"kind": "cancel_order", "cid": BUY, "deps": "cancel", "grp": [SELL]}, clock=lambda: T0)   # 还没读的整组撤单
    keep = MO.normalize({"kind": "cancel_order", "cid": SELL, "deps": "keep"})
    assert "已经在撤（等执行器）" in MO.check(keep, b, "paper", now=AT15)
    rec = MO.normalize({"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY]})
    assert MO.group_prune(rec, b, AT15, True, MO.unseen("paper", b)) == (rec, [])   # 点的这一笔自己在撤：交给 check 说「已经在撤」
    assert "已经在撤" in MO.check(rec, b, "paper", now=AT15)


def test_review_single_sell_target_is_folded_into_the_group_job_buy_first():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    br = _Rec()                                                              # 命令行 cancel <卖> <买>，只有买单写了 --group（或两条指令同一次运行）
    res = LO.cancel_core(orders, b, lambda: br, [SELL, BUY], paper=False, now=T9, source="test", groups={BUY: [SELL]})
    assert br.calls == ["B1", "S1"] and all(o.status == "CANCELLED" for o in orders)   # 以前：卖单的撤单先发
    assert list(res["grp"]) == [BUY] and res["grp"][BUY]["state"] == "all"
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    br = _Pending(10 ** 6)
    res = LO.cancel_core(orders, b, lambda: br, [SELL, BUY], paper=False, now=T9, source="test", groups={BUY: [SELL]})
    assert br.calls == ["B1"] and orders[0].status == "SENT" and res["grp"][BUY]["state"] == "wait"
    assert res["by_cid"][SELL] == ("skipped", "同一组正在整组撤单：这一笔交给整组撤单（先撤买单、确认没成交再撤卖单）")


def test_review_two_group_cids_merge_into_one_summary():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    br = _Rec()
    res = LO.cancel_core(orders, b, lambda: br, [SELL, BUY], paper=False, now=T9, source="test", groups={SELL: None, BUY: None})
    assert list(res["grp"]) == [SELL] and res["alias"] == {BUY: SELL} and br.calls == ["B1", "S1"]
    assert [ln for ln in LO.cancel_text(res) if ln.startswith("整组撤单")] == ["整组撤单（2 笔：卖 1545 纳斯达克 100 这一组）：都撤了"]


def test_review_requests_alias_items_both_finish():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY]}, clock=lambda: T9)
    b2 = json.loads(p.read_text(encoding="utf-8"))
    MO.Manual(b2, "tachibana", lambda: T9).ingest(only=("cancel_order",))
    b2["manual"]["items"]["X2"] = {"id": "X2", "kind": "cancel_order", "cid": BUY, "deps": "cancel", "grp": [SELL], "status": "pending",
                                   "at": T9.isoformat()}                     # 另一台设备几乎同时点的（check 之前已经写进来了）
    p.write_text(json.dumps(b2, ensure_ascii=False), encoding="utf-8")
    br = _Rec()
    res = LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: T9)
    assert br.calls == ["B1", "S1"] and len(res["grp"]) == 1
    assert {i["status"] for i in _items(p)} == {"done"} and all("都撤了" in i["msg"] for i in _items(p))


def test_review_sell_cancel_accepted_but_still_cancelling_counts_as_all():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _SellPending(), [SELL], paper=False, now=T9, source="test", groups={SELL: [BUY]})
    g = res["grp"][SELL]
    assert g["state"] == "all" and "卖单的撤单已受理、立花还在处理" in g["line"] and not g["line"].startswith("★")
    assert not any(lv == "warn" for lv, _m in res["events"]) and [x["cid"] for x in res["pending"]] == [SELL]


def test_review_recancel_of_an_order_already_cancelling_is_pending_not_failed():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _AlreadyCancelling(), [BUY], paper=False, now=T9, source="test")
    assert not res["failed"] and res["by_cid"][BUY][0] == "pending" and "之前已经撤过" in res["by_cid"][BUY][1]
    assert LO.ACCEPTED in orders[1].note and orders[1].status == "SENT"
    br = _Rec()                                                              # 之后整组撤单：买单照样再发撤单（复核 2：之前的撤单可能没成功），
    res = LO.cancel_core(orders, b, lambda: br, [SELL], paper=False, now=T9, source="test", groups={SELL: [BUY]})   # 取消完了 → 撤卖单
    assert br.calls == ["B1", "S1"] and res["grp"][SELL]["state"] == "all"


def test_review_late_wait_gives_up_before_the_close_and_stale_waits_close_quietly():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    p = _tbook(b)
    t1 = dt.datetime(2026, 10, 15, 15, 20, tzinfo=JST)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY]}, clock=lambda: t1)
    br = _Pending(10 ** 6)
    res = LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: t1)
    assert res["grp"][SELL]["state"] == "wait"
    t2 = dt.datetime(2026, 10, 15, 15, 27, tzinfo=JST)                     # 收盘前 3 分钟：不再等（15:30 之后面板不再叫撤单的运行）
    res = LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: t2)
    g = res["grp"][SELL]
    assert g["state"] == "gaveup" and "快收盘了（15:30）不再等" in g["line"] and "kabuka.e-shiten.jp" in g["line"]
    assert br.calls == ["B1"] and _items(p)[0]["status"] == "done"


def test_review_a_wait_left_past_the_close_ends_quietly_next_morning():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    p = _tbook(b)
    t1 = dt.datetime(2026, 10, 15, 15, 20, tzinfo=JST)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY]}, clock=lambda: t1)
    res = LO.cancel_book(p, lambda: _Pending(10 ** 6), paper=False, tag="tachibana", requests=True, clock=lambda: t1)
    assert res["grp"][SELL]["state"] == "wait"
    it = _items(p)[0]
    t3 = dt.datetime(2026, 10, 16, 8, 0, tzinfo=JST)                       # 等到收盘之后（第二天早上才轮到）：不吵地结束
    assert MO.grp_wait_stale(it, t3) and MO.grp_wait_stale(it, t1.replace(hour=15, minute=31)) and not MO.grp_wait_stale(it, t1)
    assert MO.cancel_due("tachibana", json.loads(p.read_text(encoding="utf-8")), t3)
    res = LO.cancel_book(p, lambda: _NoBroker(), paper=False, tag="tachibana", requests=True, clock=lambda: t3)
    assert not (res["done"] or res["pending"] or res["failed"] or res["skipped"] or res["events"])   # 不推送
    it = _items(p)[0]
    assert it["status"] == "done" and it["msg"].startswith("已收盘（15:30）：整组撤单停在等立花确认买单的撤单（10/15 15:20 起）")
    assert "grp_wait" not in it and "recheck_at" not in it


def test_review_legacy_deps_cancel_waits_like_the_group_cancel():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel"}, clock=lambda: T9)   # 以前的「一起撤买单」
    br = _Pending(LO.GROUP_POLLS)
    res = LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: T9)
    g = res["grp"][SELL]
    assert g["state"] == "wait" and g["legacy"] and "和靠它的钱的买单一起撤：买单已发撤单" in g["line"]
    assert br.calls == ["B1"] and SELL not in res["by_cid"]
    it = _items(p)[0]
    assert it["status"] == "pending" and it["grp_legacy"] and it["grp_wait"] == [BUY]
    t2 = T9 + dt.timedelta(seconds=61)
    res = LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: t2)
    assert br.calls == ["B1", "S1"] and res["by_cid"][SELL][0] == "done"
    it = _items(p)[0]
    assert it["status"] == "done" and "grp_legacy" not in it


def test_review_single_sell_is_held_while_a_group_buy_can_still_spend_unless_keep():
    b = _gbook(buy="FILLED")
    b["orders"][1].update(broker_id="B1", order_date="20261015", sent_qty=678, filled_qty=678)
    orders = _xo(b)
    br = _Rec()
    res = LO.cancel_core(orders, b, lambda: br, [SELL], paper=False, now=T9, source="test")
    assert br.calls == [] and orders[0].status == "SENT" and res["held"] == [SELL]
    assert "买 1482 对冲版美国 7〜10 年国债 已经成交 678 口" in res["by_cid"][SELL][1] and "只撤这笔卖单" in res["by_cid"][SELL][1]
    assert any(lv == "warn" and m.startswith("★ 交易：") for lv, m in res["events"])
    res = LO.cancel_core(orders, b, lambda: br, [SELL], paper=False, now=T9, source="test", deps={SELL: "keep"})
    assert br.calls == ["S1"] and orders[0].status == "CANCELLED"
    b = _gbook()                                                             # 买单还没发出（等开盘后）：发的时候按那时的钱重算 → 不挡
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _Rec(), [SELL], paper=False, now=T0, source="test")
    assert orders[0].status == "CANCELLED" and not res["held"]


def test_review_busy_group_members_are_not_cancelled_alone():
    b = _gbook()
    _at_exch(b, BUY, "B1", status="SENT")
    b["orders"][1]["note"] = "你撤了单（09:30）：撤单已受理，立花还在处理（取消中）"
    b["manual"]["items"] = {"M1": {"id": "M1", "kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [BUY], "status": "pending",
                                   "grp_wait": [BUY], "grp_wait0": T9.isoformat(), "grp_all": [BUY, SELL],
                                   "recheck_at": (T9 + dt.timedelta(seconds=60)).isoformat(), "at": T9.isoformat()}}
    p = _tbook(b)
    t = T9 + dt.timedelta(seconds=20)
    res = LO.cancel_book(p, lambda: _NoBroker(), [SELL], paper=False, tag="tachibana", clock=lambda: t, deps="keep")   # 命令行 --solo
    assert res["by_cid"][SELL][0] == "skipped" and "同一组正在整组撤单" in res["by_cid"][SELL][1]
    assert json.loads(p.read_text(encoding="utf-8"))["orders"][0]["status"] == "SENT"


def test_review_panel_solo_dialog_text_and_solok():
    b = _book1015("paper", sell="SENT", buy="FILLED")
    b["orders"][0]["src"] = "fix_fund"
    b["orders"][1].update(src="core_fix", fund_src=[SELL], sent_qty=678, filled_qty=678, filled_px=1474.0)
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    card = _card(panel.render("paper", "t" * 40, AT15), "today")
    sb = _btn(card, SELL)
    assert "data-grp=" not in sb and "data-solok='1'" in sb and sb.endswith("data-name='纳斯达克 100'")
    gl = re.search(r"data-glist='([^']*)'", sb).group(1)
    assert gl.startswith("只撤这一笔：") and "整组撤单：" not in gl and "卖单因此不撤" not in gl
    assert "· 已成交：买 1482 对冲版美国 7〜10 年国债：678 口 —— 不能撤" in gl and "· 撤（这一笔）：卖 1545 纳斯达克 100" in gl
    assert "★ 同一组的买 1482 对冲版美国 7〜10 年国债 已经成交 678 口：只撤这笔卖单" in gl


def test_review_panel_data_fix_prefers_the_clicked_fixed_etf():
    b = _book1015("paper", sell="SENT", fix={"1482.T": 678, "2845.T": 10})
    b["orders"][0]["src"] = "fix_fund"
    b["orders"][1]["src"] = "core_fix"
    b["orders"].append({**b["orders"][1], "cid": f"U{D}-BUY-2845.T", "ticker": "2845.T", "qty": 10})
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    card = _card(panel.render("paper", "t" * 40, AT15), "today")
    xb = _btn(card, f"U{D}-BUY-2845.T")
    assert "data-fix='2845.T'" in xb and "data-fix='1482.T'" not in xb
    gl = re.search(r"data-glist='([^']*)'", xb).group(1)
    assert "固定口数 2845 纳斯达克 100 对冲版 10 口还有效" in gl and "不要再排 → 「整组撤单并恢复按规则」" in gl
    assert "→ 「持仓」里 1482 对冲版美国 7〜10 年国债 下面点「恢复按规则」" in gl
    assert "data-fix='1482.T'" in _btn(card, BUY)


def test_review_group_row_css_beats_the_list_padding():
    css = (panel.STATIC_DIR / "panel.css").read_text(encoding="utf-8")
    assert ".list .li.og{border-left:3px solid var(--accent);padding-left:6px}" in css
    assert css.index(".list .li{") < css.index(".list .li.og{")


def test_review_panel_solo_sell_sends_keep_in_node():
    from test_fund_src import _node_cancel
    d = {"cid": SELL, "side": "SELL", "t": "1545.T", "qty": "4110", "core": "1", "name": "纳斯达克 100", "solok": "1",
         "glist": "只撤这一笔：…"}
    out = _node_cancel(d, None)
    assert out["ASKED"] == [["撤单 卖 1545.T 4110 口", "只撤这笔卖单", []]]
    assert out["SENT"] == [{"book": "paper", "kind": "cancel_order", "cid": SELL, "deps": "keep"}]
    MO.normalize({k: v for k, v in out["SENT"][0].items() if k != "book"})
    d.pop("solok")
    assert _node_cancel(d, None)["SENT"] == [{"book": "paper", "kind": "cancel_order", "cid": SELL}]


def test_review_cli_solo_flag(monkeypatch, capsys):
    b = _gbook(buy="FILLED")
    b["orders"][1].update(broker_id="B1", order_date="20261015", sent_qty=678, filled_qty=678)
    run, p = _cli(monkeypatch, b)
    br = _Rec()
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: br)
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--solo", "--group"]) == 2
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", "--solo"]) == 2
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group", "--preview", "--solo"]) == 2
    capsys.readouterr()
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL]) == 0
    assert "命令行加 --solo" in capsys.readouterr().out and br.calls == []
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--solo"]) == 0
    assert br.calls == ["S1"] and json.loads(p.read_text(encoding="utf-8"))["orders"][0]["status"] == "CANCELLED"


def test_review_liveu_cancel_plan_needs_the_broker(tmp_path):
    import shutil
    from test_shell_scripts import _bash, _calls, _run_env
    if not shutil.which("bash"):
        pytest.skip("需要 bash")
    env, log = _run_env(tmp_path, 0)
    out, _err = _bash(env, "scripts/liveu.sh", "cancel-plan", SELL)
    assert "用法：bash scripts/liveu.sh cancel-plan <cid> --broker tachibana|paper" in out and "--preview" not in _calls(log)
    env, log = _run_env(tmp_path, 0)
    _bash(env, "scripts/liveu.sh", "cancel-plan", SELL, "--broker=paper")
    assert f"run.py live-u --broker=paper --cancel {SELL} --group --preview" in _calls(log)


# ══════════════════════════ 复核 2（2026-10-16）══════════════════════════
S2 = f"U{D}-SELL-2845.T"
R7 = f"U{D}-BUY-7203.T"


class _BPend(_Rec):
    """立花：买单 B1 前 k 次查状态是「取消中」，之后取消完了；别的单的撤单马上取消完了。"""
    def __init__(self, k):
        super().__init__()
        self.k, self.n = k, 0

    def order_status(self, bid, day):
        if bid == "B1":
            self.n += 1
            if self.n <= self.k:
                return {"final": "", "status": "取消中", "filled_qty": 0}
        return {"final": "CANCELLED", "filled_qty": 0, "status": "取消完了"}


class _CancelFailed(_Rec):
    """立花：不受理这次撤单，单的状态是「取消失敗」（撤单没成功、单还挂着）。"""
    def cancel_order(self, bid, day):
        self.calls.append(bid)
        return False

    def order_status(self, bid, day):
        return {"final": "", "status": "取消失敗", "status_code": "8", "filled_qty": 0}


class _AcceptThenFail(_Rec):
    """立花：买单的撤单先受理（取消中），之后交易所那边撤单没成功（取消失敗、单还挂着）；卖单的撤单马上取消完了。"""
    def __init__(self):
        super().__init__()
        self.phase = 0

    def order_status(self, bid, day):
        if bid == "B1":
            return {"final": "", "status": "取消中" if self.phase == 0 else "取消失敗", "filled_qty": 0}
        return {"final": "CANCELLED", "filled_qty": 0, "status": "取消完了"}


def _three(s2="SENT", qty=5):
    """买 1482 + 卖 1545 + 卖 2845（都是凑钱卖的 fix_fund：同一组 3 笔）；买单挂在交易所。"""
    b = _gbook()
    _at_exch(b, BUY, "B1")
    b["orders"].append({**b["orders"][0], "cid": S2, "ticker": "2845.T", "qty": qty, "src": "fix_fund", "broker_id": "S2X",
                        "order_date": "20261015", "sent_qty": qty, "status": s2, "filled_qty": qty if s2 == "FILLED" else 0})
    assert sorted(LO.groups(b["orders"], b)[BUY]) == sorted([BUY, SELL, S2])
    return b


def _attrs(btn):
    import html
    return {k: html.unescape(v) for k, v in re.findall(r"data-([a-z]+)='([^']*)'", btn)}


def _tcard(b, now=T9):
    _tbook(b)
    return _card(panel.render("tachibana", "t" * 40, now), "today")


def _node_ask(d: dict, alt=None) -> dict:
    """trade.js 点「撤单」那一段在 node 里跑，记下确认框的标题、正文、主按钮、其他按钮 → {SENT, ASKED}；没有 node → skip。"""
    import shutil
    import subprocess
    from test_fund_src import _cancel_block
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    blk = _cancel_block((panel.STATIC_DIR / "trade.js").read_text(encoding="utf-8"))
    js = ("let SENT=[], ASKED=[];const CFG={book:'tachibana', paper:false};"
          f"const ALT={json.dumps(alt)};"
          "const fmt=x=>String(x), tlab=(t,n)=>t+' '+(n||''), tqty=(t,q,n)=>t+' '+q;"
          "const post=async b=>{SENT.push(b); return {ok:true, msg:'已写撤单'};};"
          "const ask=async (t,b,ok,o)=>{ASKED.push({title:t, body:b, ok:ok, alt:(o.alt||[]).map(x=>x.text)}); return {ok:true, alt:ALT||undefined};};"
          "const done=j=>0;"
          "async function H(a,d){ " + blk + " }\n"
          f"const d={json.dumps(d, ensure_ascii=False)};"
          "H('cancel-order', d).then(()=>console.log(JSON.stringify({SENT, ASKED})));")
    return json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True, timeout=60).stdout.splitlines()[-1])


# 1. 单笔撤单不交给不撤它的整组撤单；「都撤了」只说这次范围里的，范围外还开着的卖单写出来
@pytest.mark.parametrize("k", [0, LO.GROUP_POLLS])
def test_r2_single_cancel_outside_the_group_scope_is_not_dropped(k):
    b = _three()
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": S2, "deps": "keep"}, clock=lambda: T9)       # 只撤这一笔（卖 2845）
    MO.append("tachibana", {"kind": "cancel_order", "cid": BUY, "deps": "cancel", "grp": [SELL]}, clock=lambda: T9)   # 整组撤单（买 + 卖 1545）
    br = _BPend(k)
    res = LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: T9)
    assert res["by_cid"][S2][0] == "done" and "S2X" in br.calls          # 以前：交给整组撤单，而整组撤单不撤它（不在范围里）→ 一直不撤
    assert {i["cid"]: i["status"] for i in _items(p)}[S2] == "done"
    if k:
        assert res["grp"][BUY]["state"] == "wait"
        res = LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: T9 + dt.timedelta(seconds=61))
    assert res["grp"][BUY]["line"] == "整组撤单（同一组 3 笔里的 2 笔：买 1482 对冲版美国 7〜10 年国债 这一组）：都撤了"
    st = {o["cid"]: o["status"] for o in json.loads(p.read_text(encoding="utf-8"))["orders"]}
    assert st == {SELL: "CANCELLED", BUY: "CANCELLED", S2: "CANCELLED"}
    assert {i["status"] for i in _items(p)} == {"done"}


def test_r2_group_summary_names_open_sells_outside_the_scope():
    b = _three()
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _Rec(), [BUY], paper=False, now=T9, source="test", groups={BUY: [SELL]})
    assert {o.cid: o.status for o in orders} == {SELL: "CANCELLED", BUY: "CANCELLED", S2: "SENT"}
    assert res["grp"][BUY]["line"] == ("整组撤单（同一组 3 笔里的 2 笔：买 1482 对冲版美国 7〜10 年国债 这一组）：都撤了；"
                                       "同一组另有 卖 2845 纳斯达克 100 对冲版：5 口（已下单（等成交）） 不在这次整组撤单里")


def test_r2_cli_single_cancel_of_a_member_the_waiting_group_does_not_cover_runs_now():
    b = _three()
    b["orders"][1]["note"] = "你撤了单（09:30）：撤单已受理，立花还在处理（取消中）"
    b["manual"]["items"] = {"M1": {"id": "M1", "kind": "cancel_order", "cid": BUY, "deps": "cancel", "grp": [SELL], "status": "pending",
                                   "grp_wait": [BUY], "grp_wait0": T9.isoformat(), "grp_all": [BUY, SELL, S2],
                                   "recheck_at": (T9 + dt.timedelta(seconds=60)).isoformat(), "at": T9.isoformat()}}
    p = _tbook(b)
    br = _BPend(0)
    res = LO.cancel_book(p, lambda: br, [S2], paper=False, tag="tachibana", clock=lambda: T9 + dt.timedelta(seconds=20), deps="keep")
    assert res["by_cid"][S2][0] == "done" and br.calls == ["S2X"]       # 以前：「交给整组撤单」，整组撤单不撤它
    res = LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: T9 + dt.timedelta(seconds=61))
    assert res["grp"][BUY]["state"] == "all" and br.calls == ["S2X", "S1"]
    st = {o["cid"]: o["status"] for o in json.loads(p.read_text(encoding="utf-8"))["orders"]}
    assert st == {SELL: "CANCELLED", BUY: "CANCELLED", S2: "CANCELLED"}


# 2. 「取消失敗」不是已受理；整组撤单对范围里的买单照样再发撤单
def test_r2_cancel_failed_status_is_failed_not_accepted():
    assert LO._cancelling({"status_code": "6"}) and LO._cancelling({"status": "取消中"})
    assert not LO._cancelling({"status": "取消失敗", "status_code": "8"}) and not LO._cancelling(None)
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _CancelFailed(), [BUY], paper=False, now=T9, source="test")
    kind, why = res["by_cid"][BUY]
    assert kind == "failed" and why.startswith("撤单没成功（立花：取消失敗）：单还挂着") and "kabuka.e-shiten.jp/mfds_smp.php" in why
    assert LO.ACCEPTED not in (orders[1].note or "") and orders[1].status == "SENT"
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    br = _CancelFailed()
    res = LO.cancel_core(orders, b, lambda: br, [SELL], paper=False, now=T9, source="test", groups={SELL: [BUY]})
    g = res["grp"][SELL]
    assert br.calls == ["B1"] and orders[0].status == "SENT" and g["state"] == "none" and g["line"].startswith("★ ")


def test_r2_group_resends_the_buy_cancel_after_an_earlier_cancel_failed():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    br = _AcceptThenFail()
    res = LO.cancel_core(orders, b, lambda: br, [BUY], paper=False, now=T9, source="test")   # 只撤这笔买单 → 取消中
    assert res["by_cid"][BUY][0] == "pending" and LO.ACCEPTED in orders[1].note
    br.phase = 1                                                             # 交易所那边撤单没成功：单还挂着
    br.calls.clear()
    res = LO.cancel_core(orders, b, lambda: br, [SELL], paper=False, now=T9 + dt.timedelta(minutes=2), source="test",
                         groups={SELL: [BUY]})
    assert br.calls == ["B1"]                                                # 以前：备注里有「撤单已受理」→ 不再发撤单、卖单一直等
    assert res["by_cid"][BUY][0] == "failed" and orders[0].status == "SENT"
    g = res["grp"][SELL]
    assert g["state"] == "none" and "一笔都没撤成" in g["line"] and "卖单不撤" in g["line"]


# 3. __all__ 里的名字都在
@pytest.mark.parametrize("mod", [LO, MO], ids=["live_ops", "manual_orders"])
def test_r2_every_name_in_all_exists(mod):
    assert [n for n in mod.__all__ if not hasattr(mod, n)] == []
    assert len(set(mod.__all__)) == len(mod.__all__)
    if mod is LO:                                                            # 以前少一个逗号：两个名字连成一个不存在的名字
        assert {"group_lines", "group_view", "solo_holds", "DEPK"} <= set(LO.__all__)


# 4. 部分成交的单：写「撤剩下的（已成交 x/y 口）」、在整组撤单的范围里
def test_r2_partial_sell_is_cancel_the_rest_and_in_the_group():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    b["orders"][0].update(status="PARTIAL", filled_qty=1000)
    a = _attrs(_btn(_tcard(b), SELL))
    assert a["grp"] == BUY and "gn" not in a
    assert "· 撤剩下的：卖 1545 纳斯达克 100：4,110 口（部分成交，已成交 1,000/4,110 口）" in a["glist"]
    assert "· 已成交：卖 1545" not in a["glist"]
    orders = _xo(b)
    br = _Rec()
    res = LO.cancel_core(orders, b, lambda: br, [SELL], paper=False, now=T9, source="test", groups={SELL: [BUY]})
    assert br.calls == ["B1", "S1"] and res["grp"][SELL]["state"] == "all"


def test_r2_partial_buy_is_not_shown_as_filled_and_blocks_the_group():
    b = _gbook()
    _at_exch(b, BUY, "B1", status="PARTIAL")
    b["orders"][1]["filled_qty"] = 100
    card = _tcard(b)
    sa, ba = _attrs(_btn(card, SELL)), _attrs(_btn(card, BUY))
    assert "grp" not in sa and sa["solok"] == "1" and "grp" not in ba
    assert sa["glist"].startswith("只撤这一笔：买 1482 对冲版美国 7〜10 年国债 已经成交 100 口 → 这一组不能整组撤")
    assert "· 不跟着撤：买 1482 对冲版美国 7〜10 年国债：678 口（部分成交，已成交 100/678 口）" in sa["glist"]
    assert "· 撤剩下的（这一笔）：买 1482 对冲版美国 7〜10 年国债：678 口（部分成交，已成交 100/678 口）" in ba["glist"]
    assert "· 已成交：买 1482" not in sa["glist"] + ba["glist"]


# 5. 卖单有靠它的钱、还没发出的买单时（不能整组撤）：确认框把两个按钮各会怎样写清楚
def _deps_book(buy="CANCELLED"):
    b = _gbook()
    if buy == "CANCELLED":
        b["orders"][1].update(status="CANCELLED", note="你撤了单（08:04，面板的撤单指令）：还没发到交易所，执行器不再发", fund_src=[])
    else:
        b["orders"][1].update(status="FILLED", broker_id="B1", order_date="20261015", sent_qty=678, filled_qty=678)
    b["orders"].append(_ord(R7, "7203.T", "BUY", kind="stock", qty=100, status="DEFERRED", phase="open", src="rule", reason="",
                            fund_src=[SELL]))
    return b


def test_r2_deps_dialog_explains_both_buttons_and_the_main_one_cancels_the_buys():
    b = _deps_book()
    a = _attrs(_btn(_tcard(b, T0), SELL))
    assert "grp" not in a and a["depn"] == "1" and "depk" not in a and "solok" not in a
    gl = a["glist"]
    assert gl.startswith("这笔卖单：同一组（一起下的）其他单现在不能一起撤") and "（两个按钮不一样）" in gl and "只撤这一笔" not in gl
    assert ("· 靠这笔卖出的钱：买 7203 トヨタ自動車：100 股（等开盘后）—— 「一起撤买单」→ 一起撤（执行器不再发）；「只撤卖单」→ 不会下"
            in gl)
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel"}, clock=lambda: T0)   # 主按钮「一起撤买单」
    br = _Rec()
    LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: T0)
    st = {o["cid"]: o["status"] for o in json.loads(p.read_text(encoding="utf-8"))["orders"]}
    assert st[R7] == "CANCELLED" and st[SELL] == "CANCELLED" and br.calls == ["S1"]
    out = _node_ask({"cid": SELL, "side": "SELL", "t": "1545.T", "qty": "4110", "core": "1", "name": "纳斯达克 100",
                     "depn": "1", "keep": a["keep"], "deps": a.get("deps", ""), "glist": gl})
    q = out["ASKED"][0]
    assert q["ok"] == "一起撤买单" and "「一起撤买单」= 这几笔买单也撤（执行器不再发）" in q["body"]


def test_r2_deps_with_a_filled_group_buy_main_button_cancels_only_the_buys():
    b = _deps_book(buy="FILLED")
    a = _attrs(_btn(_tcard(b), SELL))
    assert a["solok"] == "1" and a["depk"] == LO.DEPK == "撤买单（卖单不撤）" and a["depn"] == "1"
    gl = a["glist"]
    assert "—— 「撤买单（卖单不撤）」→ 一起撤（执行器不再发）；「只撤卖单」→" in gl
    assert ("★ 「撤买单（卖单不撤）」：靠它的钱的买单撤掉，这笔卖单不撤（同一组的买 1482 对冲版美国 7〜10 年国债 已经成交 678 口："
            "撤了买的钱不够）；要撤这笔卖单 → 「只撤卖单」") in gl
    assert "★ 同一组的买 1482 对冲版美国 7〜10 年国债 已经成交 678 口：只撤卖单 = 这笔卖出的钱不来了" in gl
    out = _node_ask({"cid": SELL, "side": "SELL", "t": "1545.T", "qty": "4110", "core": "1", "name": "纳斯达克 100",
                     "depn": "1", "keep": a["keep"], "depk": a["depk"], "solok": "1", "glist": gl})
    q = out["ASKED"][0]
    assert q["ok"] == "撤买单（卖单不撤）" and "「撤买单（卖单不撤）」= 这几笔买单撤掉（执行器不再发），这笔卖单不撤（见下面 ★）" in q["body"]
    assert out["SENT"] == [{"book": "tachibana", "kind": "cancel_order", "cid": SELL, "deps": "cancel"}]
    p = _tbook(b)                                                            # 引擎：确实只撤买单、卖单不撤（与按钮一致）
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel"}, clock=lambda: T9)
    br = _Rec()
    res = LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: T9)
    st = {o["cid"]: o["status"] for o in json.loads(p.read_text(encoding="utf-8"))["orders"]}
    assert st[R7] == "CANCELLED" and st[SELL] == "SENT" and br.calls == []
    assert res["by_cid"][SELL][0] == "skipped" and "卖单不撤" in res["by_cid"][SELL][1]


# 6. 整组撤单的按钮只在引擎真的会撤时给；笔数与引擎一致；一笔都没撤 → none
def test_r2_no_group_button_when_a_filled_buy_keeps_every_sell():
    b = _gbook(buy="FILLED")
    _at_exch(b, BUY, "B1", status="FILLED")
    b["orders"][1]["filled_qty"] = 678
    b["orders"].append({**b["orders"][0], "cid": S2, "ticker": "2845.T", "broker_id": "S2X", "qty": 30, "sent_qty": 30})
    card = _tcard(b)
    for c in (SELL, S2):
        a = _attrs(_btn(card, c))
        assert "grp" not in a and a["solok"] == "1"                           # 以前：给「整组撤单（2 笔）」，引擎却一笔都不撤
        assert a["glist"].startswith("只撤这一笔：买 1482 对冲版美国 7〜10 年国债 已经成交 678 口 → 这一组不能整组撤")
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _Rec(), [SELL], paper=False, now=T9, source="test", groups={SELL: [S2]})
    g = res["grp"][SELL]
    assert g["state"] == "none" and "一笔都没撤成" in g["line"] and all(o.status != "CANCELLED" for o in orders)


def test_r2_group_button_counts_what_can_be_cancelled():
    b = _three(s2="FILLED", qty=30)
    a = _attrs(_btn(_tcard(b), SELL))
    assert a["grp"] == BUY and a["gn"] == "3"
    assert "· 已成交：卖 2845 纳斯达克 100 对冲版：30 口" in a["glist"]
    out = _node_ask({"cid": SELL, "side": "SELL", "t": "1545.T", "qty": "4110", "core": "1", "name": "纳斯达克 100",
                     "grp": a["grp"], "gn": a["gn"], "solo": a["solo"], "glist": a["glist"]})
    q = out["ASKED"][0]
    assert q["title"] == "撤单 卖 1545.T 4110 口 · 同一组 3 笔" and q["ok"] == "整组撤单（能撤的 2 笔）"
    assert "「整组撤单（能撤的 2 笔）」= 这一组能撤的一起撤" in q["body"]
    orders = _xo(b)
    br = _Rec()
    res = LO.cancel_core(orders, b, lambda: br, [SELL], paper=False, now=T9, source="test", groups={SELL: [BUY]})
    assert br.calls == ["B1", "S1"]
    assert res["grp"][SELL]["line"] == "整组撤单（同一组 3 笔里的 2 笔：卖 1545 纳斯达克 100 这一组）：都撤了"
    d = {"cid": SELL, "side": "SELL", "t": "1545.T", "qty": "4110", "core": "1", "name": "纳斯达克 100", "grp": BUY, "glist": "x"}
    assert _node_ask(d)["ASKED"][0]["ok"] == "整组撤单（2 笔）"                 # 都能撤：照旧


# 7. 卖单被挡下时的提示：--group 只在有用时给、写实际的 cid 与 --broker
@pytest.mark.parametrize("tag,paper,barg", [("tachibana", False, "tachibana"), ("tachibana_demo", False, "tachibana --demo"),
                                            ("paper", True, "paper")])
def test_r2_held_sell_hint_offers_group_only_when_it_helps(tag, paper, barg):
    t = T0 if paper else T9                                                  # 模拟账户的寄付单：开盘前还能撤
    b = _gbook(buy="FILLED")
    b["orders"][1].update(broker_id="B1", order_date="20261015", sent_qty=678, filled_qty=678)
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _NoBroker(), [SELL], paper=paper, now=t, source="test", tag=tag)
    why = res["by_cid"][SELL][1]
    assert f"bash scripts/liveu.sh cancel {SELL} --solo --broker {barg}）" in why and "--group" not in why
    b = _gbook()
    _at_exch(b, BUY, "B1")
    if paper:
        b["orders"][1]["phase"] = "morning"                                  # 模拟账户：排队的寄付买单（开盘前能撤）
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _NoBroker(), [SELL], paper=paper, now=t, source="test", tag=tag)
    why = res["by_cid"][SELL][1]
    assert f"bash scripts/liveu.sh cancel {SELL} --solo --broker {barg}）" in why
    assert f"或整组撤（bash scripts/liveu.sh cancel {SELL} --group --broker {barg}：先撤买单、确认没成交再撤卖单）" in why
    assert "<cid>" not in why and orders[0].status == "SENT"
    if paper:                                                                # 买单撤不了（模拟账户开盘后的单当场成交）→ 整组撤也没用：不提
        b["orders"][1]["phase"] = "open"
        res = LO.cancel_core(_xo(b), b, lambda: _NoBroker(), [SELL], paper=True, now=t, source="test", tag=tag)
        assert "--solo --broker paper" in res["by_cid"][SELL][1] and "--group" not in res["by_cid"][SELL][1]


# 8. 状态不明的买单不说成「你确认之后才出现的」
def test_r2_unknown_status_buy_is_not_called_new():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    b["orders"].append({**b["orders"][1], "cid": BUY + "-2", "qty": 1, "status": "SENDING", "sent_qty": 0, "broker_id": ""})
    orders = _xo(b)
    x = next(o for o in orders if o.cid == BUY + "-2")
    assert LO._spends(x, {SELL, BUY}, set(), T9, None)[0] == "unknown"
    res = LO.cancel_core(orders, b, lambda: _Rec(), [SELL], paper=False, now=T9, source="test", groups={SELL: [BUY]})
    g = res["grp"][SELL]
    assert "买 1482 对冲版美国 7〜10 年国债 状态不明（发送中 / 结果不明）" in g["line"] and "你确认之后才出现" not in g["line"]
    assert orders[0].status == "SENT" and g["state"] == "part"


# 9. 只撤这笔卖单的 ★：按买单的情况写（已成交不叫你等；撤单中 / 取消中不说「还挂着」）
def test_r2_solo_star_wording_follows_the_buy_state():
    def star(b, asked=()):
        ls = LO.group_lines(b["orders"][0], b["orders"], b, T9, False, "tachibana", asked=asked, solo=True)
        return [ln for ln in ls if ln.startswith("★ ")]
    b = _gbook(buy="FILLED")
    b["orders"][1].update(broker_id="B1", order_date="20261015", sent_qty=678, filled_qty=678)
    s = star(b)
    assert s == ["★ 同一组的买 1482 对冲版美国 7〜10 年国债 已经成交 678 口：只撤这笔卖单 = 这笔卖出的钱不来了，现金比计划少"
                 "（买单是按发出时的钱成交的，不会透支）"]
    b = _gbook()
    _at_exch(b, BUY, "B1")
    s = star(b, asked={BUY})
    assert len(s) == 1 and s[0].startswith("★ 同一组的买 1482 对冲版美国 7〜10 年国债 撤单中（等执行器）：只撤这笔卖单 = ")
    assert "还挂在交易所" not in s[0] and "先撤买" not in s[0]
    b["orders"][1]["note"] = "你撤了单（09:20）：撤单已受理，立花还在处理（取消中）"
    s = star(b)
    assert len(s) == 1 and "的撤单立花还没确认（取消中）" in s[0] and "稳妥做法：等买单撤掉（取消完了）之后再撤卖单" in s[0]
    assert "还挂在交易所" not in s[0]
    b["orders"][1]["note"] = ""
    s = star(b)
    assert len(s) == 1 and "还挂在交易所（没撤）" in s[0] and "稳妥做法：先撤买 1482 对冲版美国 7〜10 年国债（它那一行的「撤单」）" in s[0]


# 10. 命令行的提示 / 帮助写 --broker
def test_r2_cli_hints_name_the_broker(monkeypatch, capsys):
    from pathlib import Path
    run, _p = _cli(monkeypatch, _gbook())
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", "--group"]) == 2
    assert "bash scripts/liveu.sh cancel <cid> --group --broker tachibana" in capsys.readouterr().out
    assert run.main(["live-u", "--broker", "tachibana", "--demo", "--cancel", "--solo"]) == 2
    assert "bash scripts/liveu.sh cancel <cid> --solo --broker tachibana --demo" in capsys.readouterr().out
    assert run.main(["live-u", "--broker", "paper", "--cancel", "--preview"]) == 2
    assert "bash scripts/liveu.sh cancel-plan <cid> --broker paper" in capsys.readouterr().out
    assert "bash scripts/liveu.sh cancel-plan <cid> --broker tachibana|paper" in run._cancel_preview.__doc__
    src = (Path(run.__file__)).read_text(encoding="utf-8")
    assert src.count("cancel-plan <cid> --broker tachibana|paper") >= 2 and "cancel-plan <cid>）" not in src
    assert "cancel <cid> --group --broker tachibana|paper" in src and "cancel <cid> --solo --broker tachibana|paper" in src


# ══════════════════════════ 复核 3（2026-10-16）：确认框 / 按钮 / 命令行预览 / 执行器 / 推送说同一件事 ══════════════════════════
def _bst(p):
    return {o["cid"]: o["status"] for o in json.loads(p.read_text(encoding="utf-8"))["orders"]}


def _sell_dlg(a, alt=None):
    """面板卖 1545 那一行的 data-* → trade.js 的确认框（node）。"""
    d = {"cid": SELL, "side": "SELL", "t": "1545.T", "qty": "4110", "core": "1", "name": "纳斯达克 100"}
    d.update({k: a[k] for k in ("depn", "keep", "deps", "depk", "depw", "depx", "solok", "glist", "grp", "gn", "solo", "fix", "fixname")
              if k in a})
    return _node_ask(d, alt=alt)


def _run_req(p, br, t=T9):
    return LO.cancel_book(p, lambda: br, paper=False, tag="tachibana", requests=True, clock=lambda: t)


def _dep7203(b):
    b["orders"].append(_ord(R7, "7203.T", "BUY", kind="stock", qty=100, status="DEFERRED", phase="open", src="rule", reason="",
                            fund_src=[SELL]))
    return b


# F1 / F7：命令行预览（cancel-plan = cancel <cid> --group --preview）照 --group 实际做的写
def test_r3_cli_preview_matches_the_group_run_when_a_filled_buy_keeps_the_sell(monkeypatch, capsys):
    b = _dep7203(_gbook(buy="FILLED"))
    b["orders"][1].update(broker_id="B1", order_date="20261015", sent_qty=678, filled_qty=678)
    run, p = _cli(monkeypatch, b)
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group", "--preview"]) == 0
    pv = capsys.readouterr().out
    assert "· 不撤（买 1482 对冲版美国 7〜10 年国债 已经成交 678 口）：卖 1545 纳斯达克 100：4,110 口（已下单（等成交））" in pv
    assert "整组撤单：买 1482 对冲版美国 7〜10 年国债 已经成交 678 口 → 这一组的卖单都不撤" in pv
    for bad in ("撤（这一笔）", "两个按钮", "一起撤买单", "只撤卖单", "只撤这一笔", "「撤单并恢复按规则」", "「整组撤单并恢复按规则」"):
        assert bad not in pv                                                  # 以前：按面板的「只撤这一笔」写，--group 却一笔都不撤
    assert "→ 「持仓」里 1482 对冲版美国 7〜10 年国债 下面点「恢复按规则」" in pv
    br = _Rec()
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: br)
    run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group"])
    capsys.readouterr()
    assert br.calls == [] and _bst(p)[SELL] == "SENT"                       # 执行器：与预览一样，卖单不撤


def test_r3_cli_preview_includes_what_the_group_run_cancels_even_if_asked(monkeypatch, capsys):
    b = _gbook()
    _at_exch(b, SELL, "S1")
    run, p = _cli(monkeypatch, b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": BUY}, clock=lambda: T9)   # 买单那一行的「撤单」还没被读
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group", "--preview"]) == 0
    pv = capsys.readouterr().out
    assert "· 撤：买 1482 对冲版美国 7〜10 年国债：678 口（等开盘后）" in pv and "· 撤：卖 1545 纳斯达克 100：4,110 口" in pv
    assert "撤单中" not in pv and "不跟着撤" not in pv
    orders = _xo(b)
    br = _Rec()
    LO.cancel_core(orders, b, lambda: br, [SELL], paper=False, now=T9, source="test", groups={SELL: None})
    assert {o.cid: o.status for o in orders} == {SELL: "CANCELLED", BUY: "CANCELLED"} and br.calls == ["S1"]


def test_r3_cli_preview_says_nothing_is_cancelled_while_a_panel_group_cancel_covers_it(monkeypatch, capsys):
    b = _gbook()
    _at_exch(b, BUY, "B1")
    run, p = _cli(monkeypatch, b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": BUY, "deps": "cancel", "grp": [SELL]}, clock=lambda: T9)
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", SELL, "--group", "--preview"]) == 0
    pv = capsys.readouterr().out
    assert f"★ cancel {SELL} --group 这次什么都不撤：同一组已经写了整组撤单（等执行器）" in pv and "· 撤" not in pv
    br = _Rec()
    res = LO.cancel_book(p, lambda: br, [SELL], paper=False, tag="tachibana", clock=lambda: T9, groups={SELL: None})
    assert br.calls == [] and res["by_cid"][SELL][0] == "skipped" and _bst(p)[SELL] == "SENT"


# F2：撤单先受理（取消中）、之后取消失敗 → 不再当「已受理」等；整组撤单马上结束、写立花网站
def test_r3_accepted_then_cancel_failed_ends_the_waiting_group_with_the_site_link():
    b = _three()
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": BUY}, clock=lambda: T9)                       # 先单笔撤买单
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel", "grp": [S2]}, clock=lambda: T9)
    br = _AcceptThenFail()
    res = _run_req(p, br)
    assert res["by_cid"][BUY][0] == "pending" and res["grp"][SELL]["state"] == "wait" and br.calls == ["B1"]
    br.phase = 1                                                              # 交易所那边撤单没成功：买单还挂着
    res = _run_req(p, br, T9 + dt.timedelta(seconds=61))
    g = res["grp"][SELL]
    assert res["by_cid"][BUY][0] == "failed" and g["state"] == "none" and g["line"].startswith("★ ")
    assert "买 1482 对冲版美国 7〜10 年国债 的撤单没成功（立花：取消失敗，还挂着）：卖单不撤" in g["line"]
    assert "kabuka.e-shiten.jp/mfds_smp.php" in g["line"] and "还没确认" not in g["line"]
    o = next(x for x in json.loads(p.read_text(encoding="utf-8"))["orders"] if x["cid"] == BUY)
    assert o["status"] == "SENT" and LO.ACCEPTED not in o["note"] and o["note"].startswith(LO.FAILED)   # 以前：备注留着「撤单已受理」
    assert "撤单没成功（取消失敗）" in LO._st_txt(o) and "撤单已受理" not in LO._st_txt(o)
    assert _bst(p) == {SELL: "SENT", BUY: "SENT", S2: "SENT"}
    assert {i["cid"]: i["status"] for i in _items(p)}[SELL] == "rejected"
    n = len(br.calls)
    res = _run_req(p, br, T9 + dt.timedelta(seconds=122))                     # 以前：照旧当「取消中」等到 10 分钟
    assert res["grp"] == {} and len(br.calls) == n and _bst(p)[SELL] == "SENT"
    x = _xo(json.loads(p.read_text(encoding="utf-8")))[1]
    assert LO._spends(x, {SELL, BUY}, set(), T9, None)[0] == "live"           # 单笔撤卖单的闸门也当它还挂着


# F3：立花只给状态码 8（没有状态名称）也是取消失敗；只给 6 是取消中
class _Code(_Rec):
    def __init__(self, code):
        super().__init__()
        self.code = code

    def order_status(self, bid, day):
        return {"final": "", "status": "", "status_code": self.code, "filled_qty": 0}


def test_r3_status_code_8_without_a_name_is_failed_not_pending():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _Code("8"), [BUY], paper=False, now=T9, source="test")
    kind, why = res["by_cid"][BUY]
    assert kind == "failed" and why.startswith("撤单没成功（立花：取消失敗）：单还挂着")    # 以前：pending（「撤单已受理」）
    assert orders[1].status == "SENT" and orders[1].note.startswith(LO.FAILED) and LO.ACCEPTED not in orders[1].note
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _Code("8"), [SELL], paper=False, now=T9, source="test", groups={SELL: [BUY]})
    g = res["grp"][SELL]
    assert g["state"] == "none" and not g.get("wait") and orders[0].status == "SENT"     # 以前：wait（等 10 分钟）
    assert "撤单没成功（立花：取消失敗，还挂着）" in g["line"] and "kabuka.e-shiten.jp/mfds_smp.php" in g["line"]
    b = _gbook()
    _at_exch(b, BUY, "B1")
    orders = _xo(b)
    res = LO.cancel_core(orders, b, lambda: _Code("6"), [BUY], paper=False, now=T9, source="test")
    assert res["by_cid"][BUY][0] == "pending" and "取消中" in res["by_cid"][BUY][1] and LO.ACCEPTED in orders[1].note


# F4：「一起撤买单」也撤靠这笔卖出的钱、在交易所的买单（拆单的余数）→ 确认框照实写，不写「不跟着撤」
def _split_book(first="FILLED", rest="SENT"):
    b = _gbook()
    b["orders"][1].update(status=first, broker_id="B1", order_date="20261015", sent_qty=600, qty=600,
                          filled_qty=600 if first == "FILLED" else 100)
    r = {**b["orders"][1], "cid": BUY + "-2", "qty": 78, "filled_qty": 0, "status": rest, "fund_src": [SELL]}
    r.update(sent_qty=78, broker_id="B2") if rest == "SENT" else r.update(sent_qty=0, broker_id="", phase="open")
    b["orders"].append(r)
    return b


def test_r3_deps_dialog_lists_an_exchange_buy_it_cancels_and_the_engine_matches():
    b = _dep7203(_split_book())
    a = _attrs(_btn(_tcard(b), SELL))
    assert a["depk"] == LO.DEPK and a["depx"] == "1" and "depw" not in a
    gl = a["glist"]
    assert ("· 靠这笔卖出的钱、在交易所：买 1482 对冲版美国 7〜10 年国债：78 口（已下单（等成交））—— 「撤买单（卖单不撤）」→ 一起撤（发撤单）；"
            "「只撤卖单」→ 不撤") in gl
    assert "不跟着撤：买 1482 对冲版美国 7〜10 年国债：78 口" not in gl                 # 以前：写「不跟着撤」，执行器却撤了它
    star = next(ln for ln in gl.split("\n") if ln.startswith("★ 「撤买单（卖单不撤）」"))
    assert "已经成交 600 口" in star and "78" not in star
    assert ("· 这一笔：卖 1545 纳斯达克 100：4,110 口（已下单（等成交））—— 「撤买单（卖单不撤）」→ 不撤；「只撤卖单」→ 撤") in gl
    q = _sell_dlg(a)["ASKED"][0]
    assert q["ok"] == LO.DEPK and "这几笔买单撤掉（还没发出的执行器不再发，在交易所的发撤单），这笔卖单不撤" in q["body"]
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel"}, clock=lambda: T9)
    br = _Rec()
    res = _run_req(p, br)
    st = _bst(p)
    assert br.calls == ["B2"] and st[BUY + "-2"] == "CANCELLED" and st[R7] == "CANCELLED" and st[SELL] == "SENT"
    assert res["by_cid"][SELL][0] == "skipped" and "卖单不撤" in res["by_cid"][SELL][1]


def test_r3_a_member_that_is_also_an_unsent_dep_is_listed_once():
    b = _split_book(first="PARTIAL", rest="DEFERRED")
    a = _attrs(_btn(_tcard(b), SELL))
    gl = a["glist"]
    rows = [ln for ln in gl.split("\n") if ln.startswith("· ") and "78 口" in ln]
    assert rows == ["· 靠这笔卖出的钱：买 1482 对冲版美国 7〜10 年国债：78 口（等开盘后）—— 「撤买单（卖单不撤）」→ 一起撤（执行器不再发）；"
                    "「只撤卖单」→ 不会下"]                                         # 以前：成员一行「不跟着撤」+ 这一行「一起撤」
    assert ("· 靠这笔卖出的钱、在交易所：买 1482 对冲版美国 7〜10 年国债：600 口（部分成交，已成交 100/600 口）—— 「撤买单（卖单不撤）」→ "
            "撤剩下的（发撤单）；「只撤卖单」→ 不撤") in gl
    assert a["depk"] == LO.DEPK and a["depx"] == "1"
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel"}, clock=lambda: T9)
    br = _PartFill()                                                          # 立花：撤剩下的，已成交 100 口照旧
    _run_req(p, br)
    st = _bst(p)
    assert br.calls == ["B1"] and st[BUY] == "CANCELLED" and st[BUY + "-2"] == "CANCELLED" and st[SELL] == "SENT"


# F5：挡卖单的买单自己正在撤 / 在交易所、「一起撤买单」会先撤它 → 不写「卖单不撤」，写「买单撤掉了（没成交）才撤卖单」
def test_r3_deps_while_the_blocking_buy_is_being_cancelled_says_conditional_not_kept():
    b = _dep7203(_gbook())
    _at_exch(b, BUY, "B1")
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": BUY}, clock=lambda: T9)       # 买单那一行的「撤单」还没处理
    a = _attrs(_btn(_tcard(json.loads(p.read_text(encoding="utf-8"))), SELL))
    assert "depk" not in a and a["depw"] == "1" and "depx" not in a                    # 以前：data-depk（「撤买单（卖单不撤）」）
    gl = a["glist"]
    assert ("★ 「一起撤买单」：先撤买单（买 1482 对冲版美国 7〜10 年国债：678 口（撤单中）），确认买单撤掉了（没成交）才撤这笔卖单；"
            "买单成交了 / 撤不掉 / 立花 10 分钟还没确认 → 这笔卖单不撤（会推送 ★）") in gl
    assert "卖单不撤）」" not in gl and "—— 「一起撤买单」→ 买单撤掉了（没成交）才撤；「只撤卖单」→ 撤" in gl
    out = _sell_dlg(a)
    q = out["ASKED"][0]
    assert q["ok"] == "一起撤买单" and "这几笔买单也撤（执行器不再发），买单撤掉了（没成交）才撤这笔卖单（见下面 ★）" in q["body"]
    assert out["SENT"] == [{"book": "tachibana", "kind": "cancel_order", "cid": SELL, "deps": "cancel"}]
    MO.append("tachibana", out["SENT"][0], clock=lambda: T9)
    br = _Rec()
    _run_req(p, br)
    assert br.calls == ["B1", "S1"] and set(_bst(p).values()) == {"CANCELLED"}      # 与确认框一样：买单撤掉了才撤卖单


def test_r3_deps_outside_a_group_with_an_exchange_buy_is_conditional_and_buy_first():
    b = _dep7203(_gbook())
    for o in b["orders"]:
        o["src"] = "rule"                                                     # 不是同一组：只有「一起撤买单」
    _at_exch(b, BUY, "B1")
    assert LO.groups(b["orders"], b).get(SELL) is None
    a = _attrs(_btn(_tcard(b), SELL))
    assert "grp" not in a and "depk" not in a and a["depw"] == "1" and a["depx"] == "1"
    gl = a["glist"]
    assert gl.startswith("这笔卖单：靠这笔卖出的钱的买单看下面（两个按钮不一样）")
    assert ("· 靠这笔卖出的钱、在交易所：买 1482 对冲版美国 7〜10 年国债：678 口（已下单（等成交））—— 「一起撤买单」→ 一起撤（发撤单）；"
            "「只撤卖单」→ 不撤") in gl
    assert "★ 「一起撤买单」：先撤买单（买 1482 对冲版美国 7〜10 年国债：678 口），确认买单撤掉了（没成交）才撤这笔卖单" in gl
    q = _sell_dlg(a)["ASKED"][0]
    assert q["ok"] == "一起撤买单" and "（还没发出的执行器不再发，在交易所的发撤单），买单撤掉了（没成交）才撤这笔卖单" in q["body"]
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": SELL, "deps": "cancel"}, clock=lambda: T9)
    br = _Rec()
    _run_req(p, br)
    assert br.calls == ["B1", "S1"] and set(_bst(p).values()) == {"CANCELLED"}


# F6：「撤买单（卖单不撤）」时「撤单并恢复按规则」改叫「撤买单并恢复按规则」、写卖单不撤
def test_r3_fix_button_follows_depk_and_the_engine_keeps_the_sell():
    b = _deps_book(buy="FILLED")
    a = _attrs(_btn(_tcard(b), SELL))
    assert a["depk"] == LO.DEPK and a["fix"] == "1482.T"
    assert "不要再排 → 「撤买单并恢复按规则」" in a["glist"]
    out = _sell_dlg(a, alt="fix")
    q = out["ASKED"][0]
    assert q["alt"][1] == "撤买单并恢复按规则（1482.T 对冲版美国 7〜10 年国债；卖单不撤）"            # 以前：「撤单并恢复按规则」
    assert "「撤买单并恢复按规则」= 靠它的钱的买单撤掉、这笔卖单不撤，再取消固定口数" in q["body"] and "一起撤，再取消" not in q["body"]
    assert out["SENT"] == [{"book": "tachibana", "kind": "cancel_order", "cid": SELL, "deps": "cancel"},
                           {"book": "tachibana", "kind": "corefix", "ticker": "1482.T", "clear": True}]
    p = _tbook(b)
    MO.append("tachibana", out["SENT"][0], clock=lambda: T9)
    br = _Rec()
    _run_req(p, br)
    assert br.calls == [] and _bst(p)[SELL] == "SENT" and _bst(p)[R7] == "CANCELLED"


def test_r3_fix_button_with_a_conditional_deps_cancel_says_so():
    b = _dep7203(_gbook())
    _at_exch(b, BUY, "B1")
    p = _tbook(b)
    MO.append("tachibana", {"kind": "cancel_order", "cid": BUY}, clock=lambda: T9)
    a = _attrs(_btn(_tcard(json.loads(p.read_text(encoding="utf-8"))), SELL))
    assert "不要再排 → 「撤单并恢复按规则」" in a["glist"]
    q = _sell_dlg(a, alt="fix")["ASKED"][0]
    assert q["alt"][1] == "撤单并恢复按规则（1482.T 对冲版美国 7〜10 年国债）"
    assert "「撤单并恢复按规则」= 和「一起撤买单」一样（买单撤掉了才撤这笔卖单），再取消固定口数" in q["body"]


# F8：这次范围里的都撤了 → 「都撤了」（不推「只撤了一部分」）；范围里没有卖单时不写「卖单因此不撤」
def test_r3_all_in_scope_cancelled_is_all_not_part_and_no_kept_sell_wording():
    b = _gbook()
    _at_exch(b, BUY, "B1")
    b["orders"][0].update(status="FILLED", filled_qty=4110)                  # 卖 1545 已成交（不在范围里）
    b2, b3 = f"U{D}-BUY-2845.T", f"U{D}-BUY-2846.T"
    b["orders"].append({**b["orders"][1], "cid": b2, "ticker": "2845.T", "qty": 30, "broker_id": "B2", "src": "core_fix",
                        "status": "SENT", "sent_qty": 30})
    b["orders"].append({**b["orders"][1], "cid": b3, "ticker": "2846.T", "qty": 20, "broker_id": "B3", "src": "core_fix",
                        "status": "FILLED", "sent_qty": 20, "filled_qty": 20})
    a = _attrs(_btn(_tcard(b), BUY))
    assert sorted(a["grp"].split(",")) == [b2] and a["gn"] == "4"
    assert "卖单因此不撤" not in a["glist"]                                    # 范围里没有卖单
    q = _node_ask({"cid": BUY, "side": "BUY", "t": "1482.T", "qty": "678", "core": "1", "name": "x", "grp": a["grp"], "gn": a["gn"],
                   "solo": a.get("solo", ""), "glist": a["glist"]})["ASKED"][0]
    assert q["ok"].startswith("整组撤单（能撤的 2 笔）")
    orders = _xo(b)
    br = _Rec()
    res = LO.cancel_core(orders, b, lambda: br, [BUY], paper=False, now=T9, source="test", groups={BUY: a["grp"].split(",")})
    st = {o.cid: o.status for o in orders}
    assert st[BUY] == "CANCELLED" and st[b2] == "CANCELLED" and sorted(br.calls) == ["B1", "B2"]
    g = res["grp"][BUY]
    assert g["state"] == "all" and g["line"].endswith("：都撤了") and "只撤了一部分" not in g["line"]   # 以前：part「★ 只撤了一部分」
    assert not any("只撤了一部分" in ln for ln in LO.cancel_text(res))
