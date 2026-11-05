"""资金依赖 fund_src + 撤单级联（D2）与「今天已有执行器的单」只算还活着的单（D4）；2026-10-15。
事故（模拟账户，真实状态）：07:40 照「固定 1482 678 口」排了「卖 1545 4,110 口（寄付）→ 买 1482 678 口（现金不够 → 等开盘后）」，
08:05 撤了卖单 → 买单成了孤儿（撤不了、仍写「开盘后再下」、第二天早上被拒、不推送），1482 / 1545 当天也写不了新的指令。
现在：买单记 fund_src（凑钱的卖单）；卖单到了没成交的终态 → 按实际现金重算（照常 / 减股 / 不下 + ★ 交易 提醒）；
执行器还没发出的单也能撤；撤卖单的确认框给「一起撤买单 / 只撤卖单 / 撤单并恢复按规则」；立花 09:05 凑钱的卖单还没约定 → 09:20 再看，
没了 → 不拿别的钱部分买；出金预留不拿来买；撤了 / 不下 / 被拒 / 孤儿的单不算「今天已经有执行器的单」。"""
import datetime as dt
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.brokers.tachibana import TachibanaBroker
from qbreak.brokers.tachibana_sim import SimExchange
from qbreak.calendar_jp import JST, next_trading_day
from qbreak.live_unified import ACCEPTED, FUND_WAIT, ExecOrder, UnifiedExecutor
from qbreak.unified import UnifiedEngine

from test_core_etf_restore import CC, CFG2, _morning, _paper2, _w
from test_live_unified import EX, P, _frame
from test_manual_now import _at, _quote
from test_panel import AT15, _book1015, _card

FIX_NOTE = "凑钱的卖单 卖 1545 纳斯达克 100：970 口 已撤（08:05）"


def _cur(r) -> list:
    d = r.ux.book["state"]["last_date"]
    return [o for o in r.ux.orders if o.decided_on == d]


def _one(r, side: str, t: str, suffix: str = "") -> ExecOrder:
    return next(o for o in _cur(r) if o.side == side and o.ticker == t and o.cid.endswith(t + suffix))


def _low_cash(r, cash: float = 191.68) -> None:
    """现金只剩 191.68 円（与 2026-10-15 早上的模拟账户一样少：买 1 口 1482 都不够）。"""
    r.b.state["cash"] = cash
    r.eng.st.cash_jpy = cash


def _fixed_case(r, units: int = 678):
    """1545 照规则拿满 → 固定 1482 units 口 → 决策：卖 1545（寄付）+ 买 1482（现金不够 → 等开盘后，fund_src = 那笔卖单）。"""
    _morning(r, 8)
    _low_cash(r)
    _w(r.tag, "M-fix-1482", kind="corefix", ticker="1482.T", units=units)
    _morning(r)
    return _one(r, "SELL", "1545.T"), _one(r, "BUY", "1482.T")


# ══════════════════════════ 模拟账户：重放 2026-10-15 ══════════════════════════
def test_paper_replay_cancel_funding_sell_skips_buy_pushes_and_next_morning_has_no_rejection():
    r = _paper2()
    sell, buy = _fixed_case(r)
    assert sell.status == "SENT" and buy.status == "DEFERRED" and buy.fund_src == [sell.cid]
    saved = json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8"))
    assert [o["fund_src"] for o in saved["orders"] if o["cid"] == buy.cid] == [[sell.cid]]   # 账本里存着
    assert MO.busy_today(r.ux.book, "1482.T", _at(r, 10, 0))                  # 钱还会来：算「今天已经有执行器的单」
    r.now["t"] = _at(r, 8, 5)
    res = r.ux.cancel_orders([sell.cid], source="面板的撤单指令")
    assert [x["cid"] for x in res["done"]] == [sell.cid] and sell.status == "CANCELLED"
    assert buy.status == "SKIPPED" and buy.fund_src == [] and buy.note.startswith(FIX_NOTE)
    assert "→ 不会下（现在能用的钱约 ¥192，按参考价买 1 口要约 ¥1,005）" in buy.note
    assert res["fund"] == [{"cid": buy.cid, "ticker": "1482.T", "kind": "core", "act": "skip", "qty": 0, "was": 678,
                            "note": buy.note}]
    assert r.ux.trade_warns == [f"★ 交易：买 1482 对冲版美国 7〜10 年国债：678 口：{buy.note}"]
    assert any(lv == "warn" and m.startswith("★ 交易：买 1482 对冲版美国") for lv, m in res["events"])
    txt = LO.cancel_text(res)
    assert any(x.startswith("★ 买 1482 对冲版美国 7〜10 年国债：678 口：凑钱的卖单") for x in txt)
    hint = res["done"][0]["hint"]                                             # 按单的来源（M5）：固定口数排的换仓，不是个股版
    assert "为手动固定（1482 对冲版美国 7〜10 年国债 678 口）凑钱" in hint and "规则明天还要卖" not in hint
    # D4：撤了 / 不下的单不算 → 两只当天都还能写新的指令马上下
    assert not MO.busy_today(r.ux.book, "1482.T", _at(r, 10, 0)) and not MO.busy_today(r.ux.book, "1545.T", _at(r, 10, 0))
    assert MO.when_for(_at(r, 10, 0), r.ux.book, "1545.T") == "马上（盘中）"
    _w(r.tag, "M-fix-1482b", kind="corefix", ticker="1482.T", units=679)    # 还没读的固定口数 679 口
    seen = list(r.ux.orders)
    _morning(r)                                                               # 第二天早上：撮合 + 对账 + 新的决策
    seen += list(r.ux.orders)
    assert not [o for o in seen if o.status == "REJECTED"]                   # 以前：孤儿买单第二天早上被拒
    sell2, buy2 = _one(r, "SELL", "1545.T"), _one(r, "BUY", "1482.T")
    assert buy2.qty == 679 and buy2.status == "DEFERRED" and buy2.fund_src == [sell2.cid]
    _morning(r)
    assert int(r.eng.st.core_units["1482.T"]) > 0 and not r.ux.blocked


def test_paper_cancel_book_with_deps_cancel_withdraws_the_buy_too():
    """面板的撤单指令（cancel_book，不建引擎）选了「一起撤买单」（deps = cancel）：买单 CANCELLED（执行器不再发），不用重算。"""
    r = _paper2()
    sell, buy = _fixed_case(r)
    r.ux.save(force=True)
    MO.append(r.tag, MO.normalize({"kind": "cancel_order", "cid": sell.cid, "deps": "cancel", "source": "panel"}))
    now = _at(r, 8, 5)
    res = LO.cancel_book(paths.state_dir() / "live_unified_paper.json", lambda: r.b, None, paper=True, tag=r.tag,
                         requests=True, clock=lambda: now, source="面板的撤单指令")
    book = json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8"))
    st = {o["cid"]: o for o in book["orders"]}
    assert st[sell.cid]["status"] == "CANCELLED" and st[buy.cid]["status"] == "CANCELLED"
    assert "和凑钱的卖单 1545 纳斯达克 100 一起撤，执行器不再发" in st[buy.cid]["note"] and st[buy.cid]["fund_src"] == []
    assert {x["cid"] for x in res["done"]} == {sell.cid, buy.cid} and res["fund"] == []
    assert res["items"] and res["items"][0][1] == "done"


def test_paper_cancel_with_enough_cash_keeps_or_reduces_the_buy():
    """现金够 → 照常（info，不推送）；够一部分 → 减到放得下的整单元（★ 交易）。"""
    r = _paper2()
    sell, buy = _fixed_case(r)
    _low_cash(r, 800_000.0)
    r.now["t"] = _at(r, 8, 5)
    r.ux.cancel_orders([sell.cid])
    assert buy.status == "DEFERRED" and buy.qty == 678 and "现在能用的钱够" in buy.note and not r.ux.trade_warns
    r = _paper2("p2")
    sell, buy = _fixed_case(r)
    _low_cash(r, 5_360.0)
    r.now["t"] = _at(r, 8, 5)
    res = r.ux.cancel_orders([sell.cid])
    assert buy.status == "DEFERRED" and buy.qty == 5 and "减到 5 口（原计划 678 口；开盘后下）" in buy.note
    assert res["fund"][0]["act"] == "reduce" and r.ux.trade_warns


def test_paper_orphan_deferred_is_not_busy_and_does_not_hold_cash_in_now_phase():
    """凑钱的卖单在执行器之外没了（撤单没经过执行器），买单还是 DEFERRED（孤儿）：盘中 cash_now 不再为它留钱，也不算「今天已经有单」。"""
    r = _paper2()
    sell, buy = _fixed_case(r)
    r.b.cancel_pending(sell.cid)
    sell.status = "CANCELLED"                                                 # 不经过撤单级联（例：旧版本撤的）
    _low_cash(r, 300_000.0)
    now = _at(r, 10, 0)
    assert LO.orphan(buy, r.ux.orders, now, r.ux.fill_day()) and not LO.busy(buy, r.ux.orders, now, r.ux.fill_day())
    _w(r.tag, "M-buy-A", kind="buy", ticker="A.T", unit="shares", value=200)
    r.now["t"] = now
    res = r.ux.now_phase(_quote({"A.T": 1000.0, "B.T": 1500.0, "1545.T": 700.0, "1482.T": 1000.0}))
    assert res["placed"] == 1
    assert not [o for o in r.ux.orders if o.reason == "manual_fund"]          # 以前：孤儿占着 69 万 → 先卖核心 ETF 凑钱
    a = next(o for o in r.ux.orders if o.ticker == "A.T" and o.phase == "now")
    assert a.status == "FILLED" and a.qty == 200 and a.fund_src == []


def test_old_book_without_fund_src_still_loads_and_runs():
    """旧账本（没有 fund_src 字段）：读成 []，照旧（不推测依赖；面板照旧用 unfunded_buys 写说明）。"""
    o = ExecOrder.from_dict({"cid": "U2026-10-14-BUY-1482.T", "ticker": "1482.T", "side": "BUY", "kind": "core", "qty": 678,
                             "decided_on": "2026-10-14", "status": "DEFERRED", "phase": "open"})
    assert o.fund_src == []
    old = [{"cid": "S", "ticker": "1545.T", "side": "SELL", "kind": "core", "qty": 10, "status": "CANCELLED"},
           {"cid": "B", "ticker": "1482.T", "side": "BUY", "kind": "core", "qty": 5, "status": "DEFERRED", "ref_px": 1000.0}]
    now = dt.datetime(2026, 10, 15, 8, 30, tzinfo=JST)
    assert not LO.orphan(old[1], old, now) and LO.busy(old[1], old, now) and LO.deps_of(old[0], old) == []
    assert LO.fund_cascade(old, cash=0.0, now=now) == []
    r = _paper2()
    sell, buy = _fixed_case(r)
    r.ux.save(force=True)
    p = paths.state_dir() / "live_unified_paper.json"
    b = json.loads(p.read_text(encoding="utf-8"))
    for x in b["orders"]:
        x.pop("fund_src", None)
    p.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    ux = UnifiedExecutor(r.eng, r.b, p, paper=True, check_clock=False, clock=lambda: r.now["t"], manual_tag=r.tag)
    assert all(o.fund_src == [] for o in ux.orders)
    r.ux = ux
    _morning(r)
    assert not r.ux.blocked


# ══════════════════════════ 立花（模拟交易所）══════════════════════════
def _t(d: dt.date, hh: int, mm: int = 0) -> dt.datetime:
    return dt.datetime.combine(d, dt.time(hh, mm), tzinfo=JST)


def _tachi2(n: int = 30):
    """两只核心 ETF（1545 / 1482）的立花适配器 + 模拟交易所执行器。"""
    a, b = _frame([1000.0] * n, entry=()), _frame([1500.0] * n)
    c1, c2 = _frame([700.0] * n), _frame([1000.0] * n)
    c1["entry"] = c2["entry"] = False
    idx = c1.index
    bear = {"US": pd.Series(False, index=idx), "BR:BD": pd.Series(True, index=idx)}
    eng = UnifiedEngine({"A.T": a, "B.T": b, "1545.T": c1, "1482.T": c2}, CFG2, {"JP": P, "US": P}, EX, CC, bear=bear)
    exch = SimExchange(eng, cash=eng.st.cash_jpy)
    br = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=False, confirm_timeout_s=0.0,
                         max_order_value=10_000_000)
    lo = int(eng.gidx.searchsorted(idx[5]))
    now = {"t": _t(eng.gidx[lo].date(), 7, 40)}
    ux = UnifiedExecutor(eng, br, paths.state_dir() / "live_unified_tachibana.json", paper=False, check_clock=False,
                         clock=lambda: now["t"], manual_tag="tachibana")
    r = SimpleNamespace(eng=eng, exch=exch, b=br, ux=ux, now=now, k=lo, tag="tachibana")
    eng.prime(lo)
    return r


def _tday(r) -> None:
    """第 r.k 天：开盘撮合 → 开盘后补单 → 收盘 → 下一交易日 07:40 的早上运行。"""
    k = r.k
    r.exch.open(k)
    r.ux.open_phase()
    r.exch.close_day()
    r.exch.set_day(k + 1)
    r.now["t"] = _t(next_trading_day(r.eng.gidx[k].date()), 7, 40)
    r.ux.morning([k])
    r.k += 1


def _tfixed(r):
    """立花：1545 拿满 → 固定 1482 678 口 → 卖 1545（寄付）+ 买 1482 5 口（寄付）+ 余下 673 口开盘后（cid-2，fund_src = 卖单）。"""
    for _ in range(9):
        _tday(r)
    _w(r.tag, "M-fix-1482", kind="corefix", ticker="1482.T", units=678)
    _tday(r)
    return _one(r, "SELL", "1545.T"), _one(r, "BUY", "1482.T", "-2")


def _opening(r) -> None:
    """成交日开盘了、但还没撮合（特別気配 / 还没约定）：交易所进入开盘、价格是当天的始値。"""
    r.exch.k = r.exch.day_k = r.k
    r.exch.phase = "open"


def test_tachibana_cid2_split_records_the_funding_sell_and_cancel_cascades():
    r = _tachi2()
    sell, rest = _tfixed(r)
    first = _one(r, "BUY", "1482.T")
    assert sell.status == "SENT" and first.status == "SENT" and rest.status == "DEFERRED" and rest.fund_src == [sell.cid]
    f = r.ux.fill_day()
    r.now["t"] = _t(f, 8, 5)
    res = r.ux.cancel_orders([sell.cid])                                      # 同一组的买 1482 还挂在交易所：单笔撤卖单默认不撤（复核 2026-10-16）
    assert sell.status == "SENT" and res["held"] == [sell.cid] and "命令行加 --solo" in res["by_cid"][sell.cid][1]
    res = r.ux.cancel_orders([sell.cid], deps="keep")                         # 你明确说只撤这笔卖单（--solo / 「只撤这笔卖单」）
    assert sell.status == "CANCELLED" and rest.status == "SKIPPED" and "凑钱的卖单 卖 1545 纳斯达克 100：970 口 已撤（08:05）" in rest.note
    assert res["fund"][0]["act"] == "skip" and r.ux.trade_warns
    r.exch.open(r.k)
    r.now["t"] = _t(f, 9, 5)
    r.ux.open_phase(final=False)
    assert rest.status == "SKIPPED" and not rest.broker_id                  # 09:05 不发


def test_tachibana_0905_waits_for_the_funding_sell_then_0920_sends():
    r = _tachi2()
    sell, rest = _tfixed(r)
    f = r.ux.fill_day()
    _opening(r)
    r.now["t"] = _t(f, 9, 5)
    r.ux.open_phase(final=False)
    assert rest.status == "DEFERRED" and rest.note.startswith(FUND_WAIT) and "09:20 再看" in rest.note
    assert any(FUND_WAIT in e["msg"] for e in r.ux.book["events"][-5:])
    r.exch.open(r.k)                                                          # 09:10 寄り付いた：卖单约定
    r.now["t"] = _t(f, 9, 20)
    r.ux.open_phase(final=True)
    assert rest.status in ACCEPTED and rest.sent_qty == 673 and rest.fund_src == []


def test_tachibana_0905_expired_funding_sell_skips_without_a_partial_buy():
    r = _tachi2()
    sell, rest = _tfixed(r)
    f = r.ux.fill_day()
    _opening(r)
    r.exch.orders[sell.broker_id]["status"] = "12"                          # 卖单在交易所失效（没约定）
    r.now["t"] = _t(f, 9, 5)
    r.ux.open_phase(final=False)
    assert rest.status == "SKIPPED" and "不拿别的钱部分买" in rest.note and not rest.broker_id
    assert any(w.startswith("★ 交易：买 1482 对冲版美国 7〜10 年国债（开盘后）放弃：凑钱的卖单") for w in r.ux.trade_warns)


def test_tachibana_0905_buying_power_leaves_the_withdrawal_reserve():
    """M15：开盘后补单的余力 = max(0, 余力 − 出金预留)（与盘中、决策同口径）。"""
    r = _tachi2()
    sell, rest = _tfixed(r)
    f = r.ux.fill_day()
    r.exch.open(r.k)
    r.ux.book["flows"] = [{"date": str(f), "jpy": -600_000.0, "reserve": True, "note": "test"}]
    r.now["t"] = _t(f, 9, 5)
    bp = float(r.b.cash())
    r.ux.open_phase(final=False)
    assert rest.status in ACCEPTED and 0 < rest.sent_qty < 673                # 按 余力 − 预留 减股
    assert rest.sent_qty * 1000.0 <= bp - 600_000.0 < (rest.sent_qty + 2) * 1000.0


def test_reject_of_a_funding_sell_cascades_at_once():
    """_send 的结果是被拒 / 失效（例：09:05 补发的卖单）→ _on_source_final：靠它的钱的买单马上重算。"""
    r = _tachi2()
    sell, rest = _tfixed(r)
    r.now["t"] = _t(r.ux.fill_day(), 8, 10)
    sell.status = "REJECTED"
    res = r.ux._on_source_final(sell)
    assert res and res[0]["act"] == "skip" and rest.status == "SKIPPED" and "被拒" in rest.note


def test_expire_of_a_funding_sell_cascades_at_once():
    r = _tachi2()
    sell, rest = _tfixed(r)
    r.now["t"] = _t(r.ux.fill_day(), 9, 10)
    sell.status = "EXPIRED"
    r.ux._on_source_final(sell)
    assert rest.status == "SKIPPED" and "已失效" in rest.note and r.ux.trade_warns


# ── 复核 R1（2026-10-16）：立花 09:05 的开盘后补单在确认窗口里成交了 → 单上要记成交数，盘中的固定口数不再买一遍 ──
PXQ = {"A.T": 1000.0, "B.T": 1500.0, "1545.T": 700.0, "1482.T": 1000.0}


def _confirming(r, monkeypatch) -> None:
    """立花适配器的确认窗口 > 0（本番是 20 秒；测试里其它地方都是 0 → 从来不在发单当场回 FILLED）。"""
    from qbreak.brokers import tachibana as TB
    monkeypatch.setattr(TB, "_sleep", lambda s: None)
    r.b.confirm_timeout_s = 5.0


def test_tachibana_open_phase_fill_in_the_confirm_window_is_on_the_order_and_corefix_does_not_rebuy(monkeypatch):
    r = _tachi2()
    sell, rest = _tfixed(r)
    _confirming(r, monkeypatch)
    f = r.ux.fill_day()
    r.exch.open(r.k)
    r.now["t"] = _t(f, 9, 5)
    r.ux.open_phase(final=False)
    assert rest.status == "FILLED" and rest.filled_qty == 673 and rest.filled_px > 0   # 以前 filled_qty = 0
    assert LO.busy(rest, _cur(r), r.now["t"], f)
    r.exch.cash += 2_000_000                                                  # 钱够：不是被现金挡住的
    _w(r.tag, "M-fix-679", kind="corefix", ticker="1482.T", units=679)        # 09:40 写固定 679 口
    r.now["t"] = _t(f, 9, 40)
    r.ux.now_phase(_quote(PXQ))
    assert r.exch.pos.get("1482.T") == 679                                    # 以前：再买 674 口 → 1,352 口
    new = [o for o in _cur(r) if o.ticker == "1482.T" and o.phase == "now"]
    assert [(o.side, o.sent_qty) for o in new] == [("BUY", 1)]


def test_tachibana_corefix_before_open_waits_then_counts_the_open_phase_fill(monkeypatch):
    """D1 的自然流程：08:48 写固定 679 口 → 09:01 等寄付的 1482 5 口 → 09:05 开盘后补 673 口当场成交 → 09:11 只补 1 口。"""
    r = _tachi2()
    sell, rest = _tfixed(r)
    _confirming(r, monkeypatch)
    f = r.ux.fill_day()
    _w(r.tag, "M-fix-679", kind="corefix", ticker="1482.T", units=679)
    _opening(r)
    r.now["t"] = _t(f, 9, 1)
    r.ux.now_phase(_quote(PXQ))
    assert rest.status == "DEFERRED"                                          # 先等今天还挂着的单（不取代开盘后的 673 口）
    r.exch.open(r.k)
    r.now["t"] = _t(f, 9, 5)
    r.ux.open_phase(final=False)
    assert rest.status == "FILLED" and rest.filled_qty == 673
    r.exch.cash += 1_000_000
    r.now["t"] = _t(f, 9, 11)
    r.ux.now_phase(_quote(PXQ))
    assert r.exch.pos.get("1482.T") == 679


@pytest.mark.parametrize("case", ["filled_no_qty", "cancelled_partly"])
def test_corefix_counts_old_filled_rows_and_partly_filled_cancelled_orders(case):
    """这次修之前记的 FILLED（单上没有成交数）按发出的口数算；立花撤掉 / 失效的单查券商的成交（成交过一部分照算）。"""
    r = _tachi2()
    sell, rest = _tfixed(r)
    first = _one(r, "BUY", "1482.T")
    f = r.ux.fill_day()
    r.exch.open(r.k)
    r.now["t"] = _t(f, 9, 5)
    r.ux.open_phase(final=False)
    assert rest.status in ("SENT", "FILLED") and rest.broker_id
    if case == "filled_no_qty":
        rest.status, rest.filled_qty, want = "FILLED", 0, 1                  # 旧版本记的样子：5（寄付）+ 673 → 679：只补 1 口
    else:
        r.exch.orders[rest.broker_id].update(filled=300, px=1000.0)          # 成交 300 口之后你撤了单
        rest.status, rest.filled_qty, want = "CANCELLED", 0, 679 - 5 - 300
    _w(r.tag, "M-fix-679", kind="corefix", ticker="1482.T", units=679)
    r.exch.cash += 2_000_000
    r.now["t"] = _t(f, 9, 40)
    r.ux.now_phase(_quote(PXQ))
    new = [o for o in _cur(r) if o.ticker == "1482.T" and o.phase == "now" and o.side == "BUY"]
    assert sum(int(o.sent_qty or 0) for o in new) == want


# ══════════════════════════ 只撤执行器还没发出的单 / 手动凑钱的卖单（live_ops）══════════════════════════
def _dict_book(sell_status="SENT", buy_status="DEFERRED", fund=True, fill="2026-10-15"):
    d = "2026-10-14"
    orders = [{"cid": f"U{d}-SELL-1545.T", "ticker": "1545.T", "side": "SELL", "kind": "core", "qty": 4110, "decided_on": d,
               "ref_px": 243.7, "phase": "morning", "status": sell_status, "sent_qty": 4110, "filled_qty": 0, "broker_id": "S1",
               "order_date": "20261015", "note": ""},
              {"cid": f"U{d}-BUY-1482.T", "ticker": "1482.T", "side": "BUY", "kind": "core", "qty": 678, "decided_on": d,
               "limit": 1503.0, "ref_px": 1474.0, "phase": "open", "status": buy_status, "sent_qty": 0, "filled_qty": 0,
               "fund_src": [f"U{d}-SELL-1545.T"] if fund else [], "note": "开盘后按始値检查、减股再下"}]
    return {"state": {"last_date": d, "cash_jpy": 191.678, "pos": {}, "core_units": {"1545.T": 4110}},
            "orders": orders, "core_rule": {"lot": {"1482.T": 1, "1545.T": 10}},
            "manual": {"items": {}, "core_fix": {"1482.T": 678}, "core_pct": 100.0}}


class _NoBroker:
    def __getattr__(self, k):
        raise AssertionError(f"不该连券商（{k}）")


def test_unsent_deferred_or_planned_can_be_cancelled_without_the_broker():
    book = _dict_book()
    orders = [ExecOrder.from_dict(o) for o in book["orders"]]
    now = dt.datetime(2026, 10, 15, 8, 30, tzinfo=JST)
    assert LO.cancel_why(orders[1], book, now, paper=False) is None
    res = LO.cancel_core(orders, book, lambda: _NoBroker(), [orders[1].cid], paper=False, now=now, source="test")
    assert orders[1].status == "CANCELLED" and "还没发到交易所，执行器不再发" in orders[1].note
    assert res["done"][0]["hint"].startswith("还没发到交易所：撤了执行器就不再发")
    assert "1482 对冲版美国 7〜10 年国债 手动固定 678 口仍有效 → 10/16 07:40 的决策还会再排同样的单" in res["done"][0]["hint"]
    orders[1].status = "PLANNED"
    assert LO.cancel_why(orders[1], book, now, paper=True) is None
    assert "已经收盘" in LO.cancel_why(orders[1], book, now.replace(hour=15, minute=40), paper=False)
    for s in ("SKIPPED", "REJECTED", "FILLED"):
        orders[1].status = s
        assert "只撤还挂着的单" in LO.cancel_why(orders[1], book, now, paper=False)


class _CancelOK:
    def cancel_order(self, bid, day):
        return True

    def order_status(self, bid, day):
        return {"final": "CANCELLED", "filled_qty": 0, "status": "取消完了"}

    def cash(self):
        return 191.678


def test_pure_replay_of_the_real_book_cancel_skips_the_orphan_and_counts_nothing():
    """2026-10-15 的真实形状（立花口径：现金 191.678 円、1545 参考价 243.7、一手 10 口；1482 限价 1,503、参考价 1,474、一手 1 口）。"""
    book = _dict_book()
    orders = [ExecOrder.from_dict(o) for o in book["orders"]]
    now = dt.datetime(2026, 10, 15, 8, 5, tzinfo=JST)
    res = LO.cancel_core(orders, book, lambda: _CancelOK(), [orders[0].cid], paper=False, now=now, source="test")
    assert orders[0].status == "CANCELLED" and orders[1].status == "SKIPPED"
    assert orders[1].note.startswith("凑钱的卖单 卖 1545 纳斯达克 100：4,110 口 已撤（08:05） → 不会下（现在能用的钱约 ¥192")
    assert [lv for lv, m in res["events"] if m.startswith("★ 交易")] == ["warn"]
    book["orders"] = [o.__dict__ for o in orders]
    assert not MO.busy_today(book, "1482.T", now) and not MO.busy_today(book, "1545.T", now)
    assert MO.orders_today(book, now) == []
    lv = panel._trade_live(book, [], AT15, "paper", halt=False)              # 「交易」：不下了的买单结束了；固定口数还在 → 提醒
    assert "U2026-10-14-BUY-1482.T" not in lv["orders"] and "手动固定 678 口仍然有效" in lv["fix"]["U2026-10-14-BUY-1482.T"]


@pytest.mark.parametrize("buy_status", ["SENT", "FILLED"])
def test_deps_cancel_also_cancels_a_dependent_buy_that_already_reached_the_exchange(buy_status):
    """R3：「一起撤买单」点下去时，靠这笔卖出的钱的买单已经在 09:05 / 09:20 发到交易所（页面是旧的）→ 也去撤；
    已经成交撤不了 → 写明「已经发到交易所，没一起撤」并推 ★ 交易（以前只撤还没发出的，发出的那笔留在交易所、推送也不提）。
    2026-10-16 有意的改动（整组撤单，用户「一起下的买单和卖单要可以一起撤」）：先撤买单；买单已经成交 → 卖单不撤（撤了，买的钱不够）。
    以前卖单照撤（FILLED 那一例以前断言卖单 CANCELLED）。
    复核 4（2026-10-16，有意的改动）：已经成交的那笔不再另推「已经发到交易所，没一起撤」★（卖单那条 ★ 已经写了「靠它的钱的买 1482 已经成交」：
    确认框把它列为卖单不撤的理由，推送不再说成「没一起撤」）；那一行改写「已经成交 678 口，撤不了」（info）。"""
    book = _dict_book()
    book["orders"][1].update(status=buy_status, sent_qty=678, broker_id="B1", order_date="20261015",
                             filled_qty=678 if buy_status == "FILLED" else 0)
    orders = [ExecOrder.from_dict(o) for o in book["orders"]]
    now = dt.datetime(2026, 10, 15, 9, 30, tzinfo=JST)
    res = LO.cancel_core(orders, book, lambda: _CancelOK(), [orders[0].cid], paper=False, now=now, source="test", deps="cancel")
    if buy_status == "SENT":
        assert orders[0].status == "CANCELLED"
        assert orders[1].status == "CANCELLED" and orders[1].cid in [x["cid"] for x in res["done"]]
        assert any("和凑钱的卖单 1545 纳斯达克 100 一起撤" in m for _lv, m in res["events"])
    else:
        assert orders[0].status == "SENT" and res["by_cid"][orders[0].cid][0] == "skipped"   # 买单已经成交：卖单不撤
        assert orders[1].status == "FILLED" and [x["cid"] for x in res["skipped"]] == [orders[1].cid, orders[0].cid]
        assert res["skipped"][0]["why"] == "已经成交 678 口，撤不了（不用撤）"
        assert not any("没一起撤" in m for _lv, m in res["events"])
        assert [m for lv, m in res["events"] if lv == "warn" and m.startswith("★ 交易")] == [
            f"★ 交易：卖 1545 纳斯达克 100：4,110 口（{orders[0].cid}）没撤 —— 靠它的钱的买 1482 对冲版美国 7〜10 年国债 已经成交 678 口："
            "卖单不撤（撤了买的钱不够）"]
        assert "卖单不撤" in res["skipped"][1]["why"] and "买 1482 对冲版美国 7〜10 年国债 已经成交 678 口" in res["skipped"][1]["why"]
        assert any("卖单不撤" in x for x in LO.cancel_text(res)) and res["held"] == [orders[0].cid]


def test_manual_fund_sell_cancel_withdraws_the_buy_by_default_or_keeps_it():
    """盘中为手动买入凑钱的核心卖单（fund_wait）被撤（M16）：默认那条买入也撤回；deps = keep → 留着、按现金重新算。"""
    for deps, want in ((None, "cancelled"), ("keep", "pending")):
        book = _dict_book()
        o = book["orders"][0]
        o.update(reason="manual_fund", phase="now")
        book["manual"]["items"] = {"M1-buy": {"id": "M1-buy", "kind": "buy", "ticker": "7203.T", "status": "pending",
                                              "fund_wait": [o["cid"]], "at": "2026-10-15T10:00:00+09:00"}}
        orders = [ExecOrder.from_dict(x) for x in book["orders"]]
        now = dt.datetime(2026, 10, 15, 10, 5, tzinfo=JST)
        LO.cancel_core(orders, book, lambda: _CancelOK(), [orders[0].cid], paper=False, now=now, deps=deps)
        it = book["manual"]["items"]["M1-buy"]
        assert it["status"] == want and "fund_wait" not in it
        assert ("这条买入也撤回" if deps is None else "按现在的现金重新算") in it["msg"]
    assert "那条买入默认一起撤回" in LO.cancel_hint(orders[0], book, now)


def test_cancel_hint_depends_on_the_order_source():
    """M5：撤之后会怎样按单的来源写（以前一律个股版「撤掉的卖单如果规则明天还要卖会再下」）。"""
    book = _dict_book()
    now = dt.datetime(2026, 10, 15, 8, 5, tzinfo=JST)
    sell, buy = book["orders"]
    assert "为手动固定（1482 对冲版美国 7〜10 年国债 678 口）凑钱" in LO.cancel_hint(sell, book, now)
    assert "手动固定 678 口仍有效 → 10/16 07:40 的决策还会再排同样的单" in LO.cancel_hint(buy, book, now)
    book["manual"]["core_fix"] = {}
    assert "照规则 / 闲置资金比例重新算目标" in LO.cancel_hint(sell, book, now)
    st = {"cid": "U-SELL-7203.T", "ticker": "7203.T", "side": "SELL", "kind": "stock", "status": "SENT"}
    assert "规则明天还要卖就会再下" in LO.cancel_hint(st, book, now)
    assert "那条指令也撤回" in LO.cancel_hint({**st, "reason": "manual"}, book, now)
    assert "撤掉的个股买单不再买" in LO.cancel_hint({**st, "side": "BUY"}, book, now)


# ══════════════════════════ D4：busy 真值表 ══════════════════════════
def _o(status, **kw):
    return {"cid": kw.pop("cid", "X"), "ticker": "7203.T", "side": kw.pop("side", "BUY"), "kind": "stock", "qty": 100,
            "status": status, "phase": kw.pop("phase", "morning"), **kw}


T0800 = dt.datetime(2026, 10, 15, 8, 0, tzinfo=JST)
T0910 = dt.datetime(2026, 10, 15, 9, 10, tzinfo=JST)
T0940 = dt.datetime(2026, 10, 15, 9, 40, tzinfo=JST)
F = dt.date(2026, 10, 15)
LATE = "寄付注文来不及（08:55 之后）"


@pytest.mark.parametrize("o, now, want", [
    (_o("SENDING"), T0910, True), (_o("SENT"), T0910, True), (_o("PARTIAL"), T0910, True), (_o("FILLED"), T0910, True),
    (_o("ERROR"), T0910, True),                                               # 状态不明（UNKNOWN）
    (_o("CANCELLED"), T0910, False), (_o("CANCELLED", filled_qty=100), T0910, True),   # 成交过的照算（同一只当天只下一笔）
    (_o("SKIPPED"), T0910, False), (_o("REJECTED"), T0910, False), (_o("EXPIRED"), T0910, False),
    (_o("EXPIRED", filled_qty=30), T0910, True), (_o("UNFILLED"), T0910, False),
    (_o("DEFERRED"), T0910, True),                                            # 没有 fund_src（旧账本 / 不靠卖单）：算
    (_o("PLANNED"), T0800, True), (_o("PLANNED"), T0910, False), (_o("PLANNED", phase="now"), T0800, False),
    (_o("BLOCKED"), T0800, True), (_o("BLOCKED"), T0940, False),
    (_o("BLOCKED", side="SELL", note=LATE), T0910, True), (_o("BLOCKED", side="SELL", note=LATE), T0940, False),
])
def test_busy_truth_table(o, now, want, monkeypatch):
    monkeypatch.setattr("qbreak.live_unified.CUTOFF_TEXT", "寄付注文来不及")
    assert LO.busy(o, [o], now, F) is want


@pytest.mark.parametrize("src, want", [("SENT", True), ("FILLED", True), ("SENDING", True), ("CANCELLED", False),
                                       ("REJECTED", False), ("EXPIRED", False), ("SKIPPED", False)])
def test_busy_of_funded_deferred_follows_its_funding_sell(src, want):
    s = _o(src, cid="S", side="SELL")
    b = _o("DEFERRED", cid="B", fund_src=["S"])
    assert LO.busy(b, [s, b], T0910, F) is want and LO.orphan(b, [s, b], T0910, F) is (not want)
    p = _o("PLANNED", cid="B", fund_src=["S"])                                 # 计划中、今天还会再发：钱没了也不算
    assert LO.busy(p, [s, p], T0800, F) is want


def test_busy_today_and_when_for_use_the_same_judgement():
    book = _dict_book(sell_status="SENT", buy_status="DEFERRED")
    now = dt.datetime(2026, 10, 15, 10, 0, tzinfo=JST)
    assert MO.busy_today(book, "1545.T", now) and MO.busy_today(book, "1482.T", now)
    assert MO.when_for(now, book, "1545.T").startswith("10/16 开盘（1545 纳斯达克 100 今天已经有执行器的单")
    assert MO.when_for(now, book) == "马上（盘中）"
    book["orders"][0]["status"] = "CANCELLED"
    assert not MO.busy_today(book, "1545.T", now) and not MO.busy_today(book, "1482.T", now)   # 孤儿也不算
    assert MO.when_for(now, book, "1545.T") == "马上（盘中）"


def test_normalize_cancel_order_deps():
    r = MO.normalize({"kind": "cancel_order", "cid": "U2026-10-14-SELL-1545.T", "deps": "keep"})
    assert r["deps"] == "keep" and "deps" not in MO.normalize({"kind": "cancel_order", "cid": "U2026-10-14-SELL-1545.T"})
    with pytest.raises(ValueError):
        MO.normalize({"kind": "cancel_order", "cid": "U2026-10-14-SELL-1545.T", "deps": "all"})


# ══════════════════════════ 面板：撤单按钮 / 确认框 ══════════════════════════
def test_panel_cancel_button_offers_the_dependent_choices():
    b = _book1015(sell="SENT")
    b["orders"][1]["fund_src"] = ["U2026-10-14-SELL-1545.T"]
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    card = _card(panel.render("paper", "t" * 40, AT15), "today")
    i = card.index("data-cid='U2026-10-14-SELL-1545.T'")
    btn = card[i:card.index(">撤单</button>", i)]
    assert "data-depn='1'" in btn and "data-keep='只撤卖单（买 1482 对冲版美国 7〜10 年国债 不会下）'" in btn
    assert "data-fix='1482.T'" in btn and "为手动固定（1482 对冲版美国 7〜10 年国债 678 口）凑钱" in btn
    assert "data-deps='靠这笔卖出的钱、执行器还没发出的买单：买 1482 对冲版美国 7〜10 年国债：678 口（只撤卖单 → 不会下）" in btn
    assert btn.endswith("data-name='纳斯达克 100'")                            # 名字放最后（确认框标题）
    j = card.index("data-cid='U2026-10-14-BUY-1482.T'")                       # 还没发出的买单也能撤
    assert "data-unsent='1'" in card[j:card.index(">撤单</button>", j)]
    assert "执行器还没发出的单（计划 / 等开盘后 / 被挡、今天还会再发的）也能撤" in card
    J = (panel.STATIC_DIR / "trade.js").read_text(encoding="utf-8")
    assert "alt.push({text:d.keep||'只撤卖单', v:'keep'})" in J and "body.deps = q.alt==='keep' ? 'keep' : 'cancel'" in J
    assert "kind:'corefix', ticker:d.fix, clear:true" in J and "if(a==='ask-alt')" in J
    assert "+(d.deps ? '\\n★ '+d.deps : '')" in J and "const hint=d.hint ||" in J
    html = panel.render("paper", "t" * 40, AT15)
    assert "id='ask-alt' data-act='ask-alt'" in html and "id='ask-alt2' data-act='ask-alt'" in html


def _cancel_block(J: str) -> str:
    """trade.js 点「撤单」那一段（if(a==='cancel-order'){…}；按大括号配对，这段的字符串里没有大括号）。"""
    i = J.index("if(a==='cancel-order'){")
    j = J.index("{", i)
    depth = 0
    for k in range(j, len(J)):
        depth += {"{": 1, "}": -1}.get(J[k], 0)
        if depth == 0:
            return J[i:k + 1]
    raise ValueError("cancel-order")


@pytest.mark.parametrize("alt,first_ok,want", [
    ("keep", True, [{"deps": "keep"}]),                           # 只撤卖单
    (None, True, [{"deps": "cancel"}]),                           # 主按钮「一起撤买单」
    ("fix", True, [{"deps": "cancel"}, {"kind": "corefix", "ticker": "1482.T", "clear": True}]),   # 撤单并恢复按规则：先撤、再恢复
    ("fix", False, [{"deps": "cancel"}]),                         # 撤单没写成 → 不再发恢复按规则
])
def test_panel_cancel_flow_requests_in_node(alt, first_ok, want):
    """撤凑钱的卖单的三个选择在 node 里实际跑（审查 tests F5，2026-10-16：以前只查源码子串）：发出的请求、顺序、deps 的名字与值；
    每个撤单请求都能过服务器的 MO.normalize（参数名 / 值一致）。没有 node 就跳过。"""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    J = (panel.STATIC_DIR / "trade.js").read_text(encoding="utf-8")
    blk = _cancel_block(J)
    js = ("let SENT=[], DONE=[], ASKED=[];const CFG={book:'paper', paper:true};"
          f"const ALT={json.dumps(alt)}, OK1={json.dumps(first_ok)};"
          "const fmt=x=>String(x), tlab=(t,n)=>t+' '+(n||''), tqty=(t,q,n)=>t+' '+q;"
          "const post=async b=>{SENT.push(b); return SENT.length===1 ? (OK1 ? {ok:true, msg:'已写撤单'} : null) : {ok:true, msg:'已写恢复按规则'};};"
          "const ask=async (t,b,ok,o)=>{ASKED.push([t, ok, (o.alt||[]).map(x=>x.v)]); return {ok:true, alt:ALT||undefined};};"
          "const done=j=>DONE.push(j);"
          "async function H(a,d){ " + blk + " }\n"
          "const d={cid:'U2026-10-14-SELL-1545.T', side:'SELL', t:'1545.T', qty:'4110', core:'1', name:'纳斯达克 100', depn:'1',"
          " keep:'只撤卖单（买 1482 不会下）', fix:'1482.T', fixname:'对冲版美国 7〜10 年国债', deps:'靠这笔卖出的钱…'};"
          "H('cancel-order', d).then(()=>console.log(JSON.stringify({SENT, DONE, ASKED})));")
    out = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True, timeout=60).stdout.splitlines()[-1])
    assert out["ASKED"] == [["撤单 卖 1545.T 4110 口", "一起撤买单", ["keep", "fix"]]]
    assert len(out["SENT"]) == len(want)
    first = out["SENT"][0]
    assert first == {"book": "paper", "kind": "cancel_order", "cid": "U2026-10-14-SELL-1545.T", **want[0]}
    for b in out["SENT"][1:]:
        assert b == {"book": "paper", **want[1]}
    for b in out["SENT"]:                                         # 服务器认得这些参数（deps 只能是 cancel / keep）
        MO.normalize({k: v for k, v in b.items() if k != "book"})
    assert len(out["DONE"]) == 1


def _node_cancel(d: dict, alt, first_ok: bool = True) -> dict:
    """trade.js 点「撤单」那一段在 node 里跑（ask 回答 ALT；第一次 post 成不成 = first_ok）→ {SENT, DONE, ASKED}；没有 node → skip。"""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    blk = _cancel_block((panel.STATIC_DIR / "trade.js").read_text(encoding="utf-8"))
    js = ("let SENT=[], DONE=[], ASKED=[];const CFG={book:'paper', paper:true};"
          f"const ALT={json.dumps(alt)}, OK1={json.dumps(first_ok)};"
          "const fmt=x=>String(x), tlab=(t,n)=>t+' '+(n||''), tqty=(t,q,n)=>t+' '+q;"
          "const post=async b=>{SENT.push(b); return SENT.length===1 ? (OK1 ? {ok:true, msg:'已写撤单'} : null) : {ok:true, msg:'已写恢复按规则'};};"
          "const ask=async (t,b,ok,o)=>{ASKED.push([t, ok, (o.alt||[]).map(x=>x.v)]); return {ok:true, alt:ALT||undefined};};"
          "const done=j=>DONE.push(j);"
          "async function H(a,d){ " + blk + " }\n"
          f"const d={json.dumps(d, ensure_ascii=False)};"
          "H('cancel-order', d).then(()=>console.log(JSON.stringify({SENT, DONE, ASKED})));")
    return json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True, timeout=60).stdout.splitlines()[-1])


GRP_D = {"cid": "U2026-10-14-SELL-1545.T", "side": "SELL", "t": "1545.T", "qty": "4110", "core": "1", "name": "纳斯达克 100",
         "depn": "1", "keep": "只撤卖单（买 1482 不会下）", "grp": "U2026-10-14-BUY-1482.T",
         "glist": "整组撤单：先撤买单，确认买单撤掉了（没成交）再撤卖单", "solo": "只撤卖单（买 1482 不会下）",
         "fix": "1482.T", "fixname": "对冲版美国 7〜10 年国债"}


@pytest.mark.parametrize("alt,first_ok,want", [
    (None, True, [{"deps": "cancel", "grp": ["U2026-10-14-BUY-1482.T"]}]),                        # 整组撤单（2 笔）
    ("one", True, [{"deps": "keep"}]),                                                           # 只撤这一笔（卖单）
    ("fix", True, [{"deps": "cancel", "grp": ["U2026-10-14-BUY-1482.T"]},
                   {"kind": "corefix", "ticker": "1482.T", "clear": True}]),                      # 整组撤单并恢复按规则
    ("fix", False, [{"deps": "cancel", "grp": ["U2026-10-14-BUY-1482.T"]}]),                      # 整组撤单没写成 → 不再发恢复按规则
])
def test_panel_group_cancel_flow_in_node(alt, first_ok, want):
    """整组撤单的确认框（2026-10-16）在 node 里实际跑：标题「· 同一组 2 笔」、主按钮「整组撤单（2 笔）」、两个选择；
    发出的请求都能过服务器的 MO.normalize。"""
    out = _node_cancel(GRP_D, alt, first_ok)
    assert out["ASKED"] == [["撤单 卖 1545.T 4110 口 · 同一组 2 笔", "整组撤单（2 笔）", ["one", "fix"]]]
    assert len(out["SENT"]) == len(want)
    assert out["SENT"][0] == {"book": "paper", "kind": "cancel_order", "cid": "U2026-10-14-SELL-1545.T", **want[0]}
    for b in out["SENT"][1:]:
        assert b == {"book": "paper", **want[1]}
    for b in out["SENT"]:
        MO.normalize({k: v for k, v in b.items() if k != "book"})
    assert len(out["DONE"]) == 1


def test_panel_group_cancel_buy_row_one_has_no_deps_in_node():
    """买单那一行选「只撤这笔买单」→ 只撤这一笔、不带 deps（买单没有靠它的钱的单）。"""
    d = {**GRP_D, "cid": "U2026-10-14-BUY-1482.T", "side": "BUY", "t": "1482.T", "qty": "678", "grp": "U2026-10-14-SELL-1545.T",
         "solo": "只撤这笔买单（卖 1545 纳斯达克 100 照常卖，钱留现金）"}
    d.pop("depn")
    d.pop("keep")
    out = _node_cancel(d, "one")
    assert out["SENT"] == [{"book": "paper", "kind": "cancel_order", "cid": "U2026-10-14-BUY-1482.T"}]
    MO.normalize({"kind": "cancel_order", "cid": "U2026-10-14-BUY-1482.T"})


def test_panel_cancel_without_dependents_offers_restore_rule_for_fixed_units_in_node():
    """没有组、没有靠它的钱的买单、但这笔是固定口数排的（data-fix）：选择只有「撤单并恢复按规则」，主按钮「撤单」；
    选它 → 先撤单（不带 deps），再恢复按规则。"""
    d = {"cid": "U2026-10-14-BUY-1482.T", "side": "BUY", "t": "1482.T", "qty": "678", "core": "1", "name": "对冲版美国 7〜10 年国债",
         "fix": "1482.T", "fixname": "对冲版美国 7〜10 年国债"}
    out = _node_cancel(d, "fix")
    assert out["ASKED"] == [["撤单 买 1482.T 678 口", "撤单", ["fix"]]]
    assert out["SENT"] == [{"book": "paper", "kind": "cancel_order", "cid": "U2026-10-14-BUY-1482.T"},
                           {"book": "paper", "kind": "corefix", "ticker": "1482.T", "clear": True}]


def test_trade_warn_push_is_a_warn_titled_trade(monkeypatch):
    import run
    sent = []
    monkeypatch.setattr("qbreak.notify.send", lambda title, body, level="info": sent.append((title, body, level)) or True)
    run._trade_warn_push(["★ 交易：买 1482.T：凑钱的卖单 卖 1545.T 已撤 → 不会下"], paper=True)
    assert sent and sent[0][0].startswith("★ 交易：qbreak 模拟操盘") and sent[0][2] == "warn"


def test_now_phase_buy_records_its_funding_sells():
    """盘中的手动买入：凑钱卖的核心 ETF（manual_fund）记在买单的 fund_src 上。"""
    from test_manual_now import PX, _paper, _req
    from test_manual_now import _morning as _m
    r = _paper("pf")
    _m(r, until=14)
    _req(r, kind="buy", ticker="B.T", unit="rule")
    r.now["t"] = _at(r, 10, 0)
    assert r.ux.now_phase(_quote(PX))["placed"] == 1
    fs = [o.cid for o in r.ux.orders if o.reason == "manual_fund"]
    b = next(o for o in r.ux.orders if o.reason == "manual_buy")
    assert fs and b.fund_src == fs
