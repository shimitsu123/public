"""整合复核 3（2026-10-16，事后）：执行器还没发出的单上「你写了撤单（等撤单的运行处理）」（CANCEL_ASKED）的说明不再单独算「你撤了」。
对账（_reconcile）只在对账那一刻还写着撤单（还没读的 / pending 的）、或撤单的运行在成交日当天没处理到、第二天才被拒时记为已撤；
撤单当天结束时留下了这笔（整组撤单「卖单不撤」）/ 被拒（同一组正在撤单）/ 撤回 → 照常：被挡的手动卖出下一次决策再卖、
等开盘后的手动买入按系统原因留到下一次决策（以前：对账记 CANCELLED、手动卖出 / 买入跟着撤回，你的卖出不见了）。"""
import datetime as dt

import pytest

from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak.calendar_jp import JST, next_trading_day

from test_int_review2 import _CID_T, _blocking, _hist


def _fill_day(o) -> dt.date:
    return next_trading_day(dt.date.fromisoformat(o.decided_on))


def _blocked_sell(monkeypatch):
    """立花（模拟交易所）：手动卖出 A.T 被挡（登录失败，BLOCKED、没有注文番号），单上写着 CANCEL_ASKED（等撤单时没发）。"""
    from test_manual_orders import _Run, _sell_req
    from qbreak.live_unified import CANCEL_ASKED
    monkeypatch.setattr(MO, "_CID", _CID_T)
    r = _Run([1000.0] * 40, entry=(10,))
    r.until(14)
    _sell_req(r, id="M-s")
    _blocking(r, ("A.T",))
    r.day()
    so = next(o for o in r.ux.orders if o.ticker == "A.T" and o.side == "SELL")
    assert so.status == "BLOCKED" and not so.broker_id
    so.note = CANCEL_ASKED
    return r, so


def _rec(so, status: str, done_on: dt.date | None, **kw) -> dict:
    rec = {"kind": "cancel_order", "id": "M-c", "cid": so.cid, "grp": ["U2026-01-01-BUY-B.T"], "deps": "cancel",
           "at": dt.datetime.combine(_fill_day(so), dt.time(9, 2), tzinfo=JST).isoformat(), "status": status, **kw}
    if done_on is not None:
        rec["done_on"] = done_on.isoformat()
    return rec


ENDED = {   # 撤单当天就结束、没撤这笔：整组撤单留下卖单 / 同一组正在撤单被拒 / 撤回
    "kept": ("done", 0, "买 B 已经成交 → 这一组的卖单都不撤"),
    "refused": ("rejected", 0, "10/15 09:03 没做：同一组正在撤单（…）：等它结束再撤"),
    "withdrawn": ("cancelled", None, "已撤回（M-w）"),
}


@pytest.mark.parametrize("how", sorted(ENDED))
def test_blocked_manual_sell_is_sold_again_when_the_cancel_ended_without_it(monkeypatch, how):
    r, so = _blocked_sell(monkeypatch)
    d0 = r.eng.st.last_date
    status, dd, msg = ENDED[how]
    r.ux.book["manual"]["items"]["M-c"] = _rec(so, status, None if dd is None else _fill_day(so) + dt.timedelta(days=dd), msg=msg)
    r.day()                                                                   # 下一个 07:40：对账
    h = _hist(r, so.cid)
    assert h and h[0]["status"] == "BLOCKED", h                               # 以前：CANCELLED「记为已撤」
    assert r.item("M-s")["status"] == "placed" and not r.item("M-s").get("cancel_req")   # 以前：手动卖出跟着撤回
    assert any(o.ticker == "A.T" and o.side == "SELL" for o in r.ux.orders if o.decided_on != d0)   # 这次决策再卖


@pytest.mark.parametrize("how", ["pending", "late"])
def test_blocked_manual_sell_is_cancelled_when_the_cancel_is_still_open(monkeypatch, how):
    from qbreak.live_unified import ASKED_UNSENT
    r, so = _blocked_sell(monkeypatch)
    d0 = r.eng.st.last_date
    if how == "pending":                                                      # 撤单还在等（面板暂停 / 失败）
        rec = _rec(so, "pending", None)
    else:                                                                     # 成交日没处理到，第二天早上才被拒（不是今天的单）
        rec = _rec(so, "rejected", next_trading_day(_fill_day(so)), msg="不是今天的单")
    r.ux.book["manual"]["items"]["M-c"] = rec
    r.day()
    h = _hist(r, so.cid)
    assert h and h[0]["status"] == "CANCELLED" and h[0]["note"] == ASKED_UNSENT
    assert r.item("M-s")["status"] == "cancelled"
    assert not any(o.ticker == "A.T" and o.side == "SELL" for o in r.ux.orders if o.decided_on != d0)


def test_deferred_manual_buy_is_requeued_after_the_cancel_is_withdrawn(monkeypatch):
    """等开盘后的手动买入：09:02 写了撤单 → 09:05 不发（CANCEL_ASKED）→ 10:00 撤回了那条撤单 → 下一个 07:40 对账：照常（系统原因，
    这次决策重新处理）；以前：记为已撤、手动买入撤回。"""
    from test_manual_buy import _buy, _write
    from test_manual_orders import TAG, _Run
    from qbreak.live_unified import CANCEL_ASKED, CANCEL_LAPSED
    monkeypatch.setattr(MO, "_CID", _CID_T)
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _buy(r, id="M-x")
    r.day()
    buy = next(o for o in r.ux.orders if o.ticker == "B.T")
    assert buy.status == "DEFERRED"
    k = r.k
    day = r.eng.gidx[k].date()
    rid = MO.append(TAG, {"kind": "cancel_order", "cid": buy.cid},
                    clock=lambda: dt.datetime.combine(day, dt.time(9, 2), tzinfo=JST))["id"]
    r.exch.open(k)
    r.now["t"] = dt.datetime.combine(day, dt.time(9, 5), tzinfo=JST)
    r.ux.open_phase()
    assert buy.status == "DEFERRED" and buy.note == CANCEL_ASKED
    t10 = dt.datetime.combine(day, dt.time(10, 0), tzinfo=JST)               # 撤回那条撤单（直接写一行：normalize 的 id 格式不收 cancel_order 的 id）
    _write({"kind": "cancel", "target": rid, "id": f"M{t10:%Y%m%d-%H%M%S}-cancel-B", "at": t10.isoformat(), "source": "test"}, TAG)
    r.exch.close_day()
    r.exch.set_day(k + 1)
    r.now["t"] = r.at(k)
    r.ux.morning([k])                                                         # 07:40：先读到撤回（撤单指令 → 已撤回），再对账
    r.k += 1
    assert r.item(rid)["status"] == "cancelled"
    h = _hist(r, buy.cid)
    assert h and h[0]["status"] == "MISSED" and h[0]["note"].startswith(CANCEL_LAPSED), h   # 以前：CANCELLED「记为已撤」
    assert r.item("M-x")["status"] != "cancelled"
    assert any(o.ticker == "B.T" and o.side == "BUY" for o in r.ux.orders if o.decided_on == r.eng.st.last_date)   # 这次决策重新买


def test_stale_note_alone_is_not_a_cancel():
    from qbreak.live_unified import CANCEL_ASKED, CANCEL_LAPSED, asked_unsent, requeue_next, system_miss
    o = {"cid": "U2026-10-15-SELL-7203.T", "side": "SELL", "kind": "stock", "status": "BLOCKED", "broker_id": "",
         "filled_qty": 0, "phase": "late", "reason": "manual", "note": CANCEL_ASKED}
    assert not asked_unsent(o, set())                                         # 以前 True（说明还在就当成你撤了）
    assert asked_unsent(o, {o["cid"]})
    b = {**o, "side": "BUY", "phase": "open", "reason": "manual_buy"}
    assert system_miss(b) == CANCEL_LAPSED and requeue_next(b, [b], None) is True   # 以前 None：说明挡住了真正的系统原因
    assert requeue_next(b, [b], None, asked={b["cid"]}) is False


def test_late_cids_only_counts_rejections_after_the_fill_day():
    o = {"cid": "U2026-10-15-BUY-7203.T", "side": "BUY", "status": "DEFERRED", "broker_id": "", "decided_on": "2026-10-15"}
    f = next_trading_day(dt.date(2026, 10, 15)).isoformat()
    nxt = next_trading_day(dt.date.fromisoformat(f)).isoformat()

    def book(**rec):
        return {"orders": [o], "manual": {"items": {"M": {"kind": "cancel_order", "id": "M", "cid": o["cid"], **rec}}}}
    assert LO.asked_cids(book(status="rejected", done_on=nxt)) == {o["cid"]}
    assert LO.asked_cids(book(status="rejected", done_on=f)) == set()        # 当天被拒（同一组正在撤单…）
    assert LO.asked_cids(book(status="done", done_on=nxt)) == set()          # 整组撤单收盘后结束（卖单没撤）
    assert LO.asked_cids(book(status="cancelled")) == set()                  # 撤回
    assert LO.asked_cids({**book(status="rejected", done_on=nxt), "orders": [{**o, "broker_id": "B1", "status": "SENT"}]}) == set()
    assert LO.asked_cids({"orders": [o], "manual": {"items": {}}}) == set()
