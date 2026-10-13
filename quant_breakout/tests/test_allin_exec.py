"""「全部换成 X」/ 平摊凑钱 / 调仓在执行时的回归（2026-10-13 审计）：
① 执行时拿着的 X 以外的个股全部卖出（写指令之后才拿的补同批卖出；规则已在卖的设不自动买回；已经不在持仓的也设）；
② 闸门过了 → 比例 0%、取消全部固定口数（同批里没有比例 / 固定口数指令也一样）；
③ 平摊凑钱：买入先过闸门，被挡 → 凑钱的卖出也不做；补单 / 盘中先卖后买一起；
④ 调仓方向在执行时反了 → 不执行；凑钱的卖出绝不变成买入；⑤ 晚做的说明、08:55 之后整批等下一次决策；
⑥ LU-15 在卖出之前查；异常熔断 → 整批退回；卖单已发出、X 没买 → 提醒；⑦ HALT 挡住开盘后补单 → 原因记在单上；
⑧ 整个运行不下单 → 买入 / 调仓往上留到下一次能下单的决策；⑨ 面板 / 命令行写入的 dir、HALT 回复的提醒。"""
import datetime as dt
import json

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.live_unified import ALLIN_SENT_TAG, HALT_WAIT

from test_manual_buy import _write
from test_manual_orders import _NoSellOnce, _Run
from test_panel import AT, _book, _sm, _sm_nowarn


def _allin(r, at: str, core: bool = True, **buy) -> None:
    """写一笔「全部换成 B.T」：个股不写同批卖出（执行时由执行器补），核心 ETF 比例 0%（core=True）。"""
    if core:
        _write({"kind": "core", "pct": 0, "fund_for": "B.T", "batch": "all", "source": "test", "id": "M-all-core", "at": at, "prev_pct": 100})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100_000, "fund": "all", "source": "test", "id": "M-all-buy", "at": at, **buy})


def _ev(r) -> list[dict]:
    """存进账本的事件 + 还没存的。"""
    return (r.ux.book.get("events") or []) + r.ux.events


def _orders(r, t: str, side: str) -> list:
    return [o for o in r.ux.orders if o.ticker == t and o.side == side]


# ────────── ① 执行时拿着的都卖 ──────────
def test_holding_bought_after_the_instruction_is_sold_with_the_batch():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    assert "A.T" in r.eng.st.pos
    _allin(r, r.at(r.k - 1, 6).isoformat())                                    # 写的时候还没有 A.T 的同批卖出（例：之后规则买进的）
    r.day()
    a = r.item("M-all-buy-auto-A")
    assert a["status"] == "placed" and a.get("auto") and a["fund_for"] == "B.T" and a["batch"] == "all"
    assert r.eng.st.pending_exit.get("A.T") == "manual" and r.ux.manual.m["blocks"]["A.T"]["id"] == a["id"]
    assert r.item("M-all-buy")["status"] == "placed"
    r.day()
    assert set(r.eng.st.pos) == {"B.T"} and r.eng.st.core_units.get("1655.T", 0) == 0


def test_rule_exiting_member_gets_no_rebuy_block():
    """规则已在卖（卖单开盘没成交 → 仍是待卖）：同批卖出照样设不自动买回（以前跳过 → 规则 20 天内可能买回）。"""
    r = _Run([1000.0] * 30, entry=(10,), dead=(15,), exchange_cls=_NoSellOnce)
    r.until(15)
    assert r.eng.st.pending_exit.get("A.T") and r.eng.st.pending_exit["A.T"] != "manual"
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "sell", "ticker": "A.T", "block_days": 20, "fund_for": "B.T", "batch": "all", "source": "test", "id": "M-all-a", "at": at})
    _allin(r, at)
    r.day()
    a = r.item("M-all-a")
    assert a["status"] == "superseded" and "规则已在卖出" in a["msg"] and "不自动买回" in a["msg"]
    assert r.ux.manual.m["blocks"]["A.T"]["id"] == "M-all-a" and r.item("M-all-buy")["status"] == "placed"


def test_member_already_sold_by_the_rule_still_gets_the_block():
    r = _Run([1000.0] * 30, entry=(10,), dead=(13,))
    r.until(13)
    at = r.at(r.k - 1, 6).isoformat()
    r.day()                                                                   # 规则的卖单这时成交（指令写在成交之前）
    assert "A.T" not in r.eng.st.pos
    _write({"kind": "sell", "ticker": "A.T", "block_days": 20, "fund_for": "B.T", "batch": "all", "source": "test", "id": "M-all-a", "at": at})
    _allin(r, at)
    r.day()
    a = r.item("M-all-a")
    assert a["status"] == "superseded" and "已经不在持仓（规则已先卖出）→ 设不自动买回" == a["msg"]
    assert r.ux.manual.m["blocks"]["A.T"]["id"] == "M-all-a" and r.ux.manual.m["blocks"]["A.T"]["fund_for"] == "B.T"


# ────────── ② 比例 0% / 取消全部固定口数 ──────────
def test_gate_pass_always_pauses_core_and_clears_every_corefix():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(13)
    u = int(r.eng.st.core_units["1655.T"])
    want = (u // 2 // 10) * 10
    r.ask(kind="corefix", ticker="1655", units=want)                          # 写「全部换成」之后才固定的口数
    r.day()
    assert r.eng.core_fix == {"1655.T": want}
    _allin(r, r.at(r.k - 1, 6).isoformat(), core=False)                      # 同批里没有比例 / 固定口数的指令
    r.day()
    m = r.ux.manual.m
    assert r.ux.manual.core_pct == 0.0 and m["core_fix"] == {} and r.eng.core_fix == {} and r.eng.core_scale == 0.0
    assert m["core_pause"]["prev_fix"] == {"1655.T": want} and m["core_pause"]["allin"] == "B.T"
    assert m["core_pause"]["prev_pct"] == 100.0
    assert r.eng.st.core_plan["1655.T"][0] == "SELL"
    r.day()
    assert r.eng.st.core_units.get("1655.T", 0) == 0


# ────────── ③ 平摊凑钱 ──────────
def _split(r, at: str, keep: int) -> None:
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": keep, "fund_for": "B.T", "source": "test", "id": "M-sp-a",
            "at": at, "dir": -1})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100, "fund": "split", "source": "test", "id": "M-sp-buy", "at": at})


def test_split_buy_blocked_at_decision_means_nothing_is_sold():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    sh = int(r.eng.st.pos["A.T"].shares)
    base = r.eng.entry_block_fn
    r.eng.entry_block_fn = lambda t, i, _b=base: "决算前 2 天" if t == "B.T" else (_b(t, i) if _b else None)
    _split(r, r.at(r.k - 1, 6).isoformat(), sh // 2 // 100 * 100)
    r.day()
    assert r.item("M-sp-buy")["status"] == "rejected" and "决算前 2 天" in r.item("M-sp-buy")["msg"]
    assert r.item("M-sp-a")["status"] == "rejected" and "凑钱的卖出也不做" in r.item("M-sp-a")["msg"]
    assert "A.T" not in r.ux.manual.m["trims"] and not _orders(r, "A.T", "SELL")
    r.day()
    assert int(r.eng.st.pos["A.T"].shares) == sh


def test_split_written_after_the_decision_waits_with_its_buy():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    sh = int(r.eng.st.pos["A.T"].shares)
    _split(r, r.at(r.k - 1, 8).isoformat(), sh // 2 // 100 * 100)
    r.now["t"] = r.at(r.k - 1, 8, 0)
    r.ux.morning([])                                                          # 同一决策的补单：买入要等开盘后 → 凑钱的卖出也等
    c = r.item("M-sp-a")
    assert c["status"] == "pending" and c.get("wait") and "一起：开盘后盘中先卖后买" in c["msg"]
    assert "A.T" not in r.ux.manual.m["trims"] and not _orders(r, "A.T", "SELL")


def test_split_buy_blocked_intraday_sends_no_funding_sell():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    sh = int(r.eng.st.pos["A.T"].shares)
    base = r.eng.entry_block_fn
    r.eng.entry_block_fn = lambda t, i, _b=base: "决算前 2 天" if t == "B.T" else (_b(t, i) if _b else None)
    _split(r, r.at(r.k, 10, 0).isoformat(), sh // 2 // 100 * 100)
    r.session(10, 0)
    assert r.item("M-sp-buy")["status"] == "rejected" and r.item("M-sp-a")["status"] == "rejected"
    assert not _orders(r, "A.T", "SELL") and int(r.eng.st.pos["A.T"].shares) == sh


# ────────── ④ 调仓的方向 ──────────
def test_adjust_flip_why_unit():
    assert MO.adjust_flip_why({"dir": 1}, 300, 100).startswith("价格变了：按 ¥ / % 换算后变成卖出")
    assert MO.adjust_flip_why({"dir": -1}, 100, 300).startswith("价格变了：按 ¥ / % 换算后变成买入")
    assert MO.adjust_flip_why({"dir": 1}, 100, 300) is None and MO.adjust_flip_why({}, 300, 100) is None
    assert MO.adjust_flip_why({"fund_for": "X.T", "dir": -1}, 100, 100) == "凑钱卖出：现在 100 股已经不高于目标 100 股 → 不卖（不会改成买入）"
    assert MO.adjust_flip_why({"fund_for": "X.T"}, 100, 300).startswith("凑钱卖出")


def test_adjust_direction_flipped_at_execution_is_rejected():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    sh = int(r.eng.st.pos["A.T"].shares)
    assert sh > 100
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "adjust", "ticker": "A.T", "unit": "yen", "value": 100_000, "source": "test", "id": "M-adj", "at": at, "dir": 1, "cur0": 0})
    r.day()
    it = r.item("M-adj")
    assert it["status"] == "rejected" and it["msg"].startswith("价格变了：按 ¥ / % 换算后变成卖出")
    assert "A.T" not in r.ux.manual.m["trims"] and "A.T" not in r.eng.st.pending_exit


def test_funding_adjust_never_turns_into_a_buy():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    sh = int(r.eng.st.pos["A.T"].shares)
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": sh + 100, "fund_for": "B.T", "source": "test", "id": "M-f",
            "at": at})
    r.day()
    it = r.item("M-f")
    assert it["status"] == "rejected" and it["msg"].startswith("凑钱卖出：现在") and "不会改成买入" in it["msg"]
    assert "A.T" not in r.ux.manual.m["adds"] and not _orders(r, "A.T", "BUY")


def test_adjust_direction_flip_checked_intraday_too():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _write({"kind": "adjust", "ticker": "A.T", "unit": "yen", "value": 100_000, "source": "test", "id": "M-adj",
            "at": r.at(r.k, 10, 0).isoformat(), "dir": 1, "cur0": 0})
    r.session(10, 0)
    it = r.item("M-adj")
    assert it["status"] == "rejected" and it["msg"].startswith("价格变了") and not _orders(r, "A.T", "SELL")


# ────────── ⑤ 晚做 / 08:55 之后 ──────────
def test_late_all_in_says_it_was_planned_earlier_and_how_x_moved():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _allin(r, r.at(r.k - 1, 6).isoformat(), allin_fill="2026-01-05", x_close=1400.0)
    r.day()
    msg = r.item("M-all-buy")["msg"]
    assert r.item("M-all-buy")["status"] == "placed" and "原定 01/05 没做（HALT / 晚跑 / 运行被挡）" in msg
    assert "¥1,400 → ¥1,500" in msg
    assert any("原定 01/05" in e["msg"] for e in _ev(r))


def test_after_cutoff_the_batch_waits_for_the_next_decision():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _allin(r, r.at(r.k - 1, 6).isoformat())
    r.now["t"] = r.at(r.k - 1, 9, 0)
    r.ux.morning([])
    assert any("全部换成整批：等下一次决策" in e["msg"] for e in _ev(r))
    assert not any("开盘后马上下" in e["msg"] for e in _ev(r))


# ────────── ⑥ 卖出之前的检查 / 整批退回 / 卖单已发出 ──────────
def test_prev_close_mismatch_aborts_the_batch_before_any_sell():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _allin(r, r.at(r.k - 1, 6).isoformat())
    r.ux._prev_closes = lambda ts: {"B.T": 2000.0}
    r.day()
    it = r.item("M-all-buy")
    assert it["status"] == "rejected" and "立花前日終値" in it["msg"] and "整批不做" in it["msg"]
    assert "A.T" not in r.eng.st.pending_exit and r.ux.manual.core_pct == 100.0 and r.item("M-all-core")["status"] == "rejected"
    assert not _orders(r, "A.T", "SELL") and "M-all-buy-auto-A" not in r.ux.manual.m["items"]


def test_breaker_after_the_gate_rolls_the_whole_batch_back():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    u = int(r.eng.st.core_units["1655.T"])
    _allin(r, r.at(r.k - 1, 6).isoformat())
    r.ux._breaker = lambda k, todo: "异常熔断：测试"
    r.day()
    it, m = r.item("M-all-buy"), r.ux.manual.m
    assert it["status"] == "pending" and it.get("hold") and "整批退回" in it["msg"]
    assert r.item("M-all-core")["status"] == "pending" and "M-all-buy-auto-A" not in m["items"]
    assert "A.T" not in r.eng.st.pending_exit and "A.T" not in m["blocks"] and "B.T" not in r.eng.st.plan
    assert r.ux.manual.core_pct == 100.0 and "core_pause" not in m and r.eng.core_scale == 1.0
    assert any("★ 「全部换成 B.T」这次没下成" in e["msg"] for e in _ev(r))
    assert all(o.status == "SKIPPED" for o in r.ux.orders if o.decided_on == r.eng.st.last_date)
    del r.ux._breaker
    r.ux.blocked = None
    r.day()                                                                   # 熔断那天什么都没动；下一次决策重新过闸门
    assert "A.T" in r.eng.st.pos and int(r.eng.st.core_units["1655.T"]) == u
    assert r.item("M-all-buy")["status"] == "placed" and r.eng.st.pending_exit.get("A.T") == "manual"
    r.day()
    assert set(r.eng.st.pos) == {"B.T"}


def test_sells_sent_but_x_not_bought_is_reported_not_silently_voided():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _allin(r, r.at(r.k - 1, 6).isoformat())
    r.ux._gate_buy = lambda o: "测试：不下" if o.ticker == "B.T" else None
    r.day()
    it = r.item("M-all-buy")
    assert it["status"] == "rejected" and it["msg"].startswith("卖单已发出，B.T 没买（测试：不下）：钱留现金")
    assert any(e["level"] == "warn" and e["msg"].startswith("★ 「全部换成 B.T」的卖单已发出") for e in _ev(r))
    assert r.eng.st.pending_exit.get("A.T") == "manual" and "B.T" not in r.eng.st.plan


def test_sells_sent_but_x_blocked_by_prev_close_keeps_trying_and_warns():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _allin(r, r.at(r.k - 1, 6).isoformat())
    calls = {"n": 0}

    def pcs(ts):                                                             # 卖出之前查的时候还对得上；下单那一刻对不上
        calls["n"] += 1
        return {} if calls["n"] == 1 else {"B.T": 2000.0}
    r.ux._prev_closes = pcs
    r.day()
    xo = next(o for o in _orders(r, "B.T", "BUY") if o.decided_on == r.eng.st.last_date)
    assert xo.status == "BLOCKED" and ALLIN_SENT_TAG in xo.note
    it = r.item("M-all-buy")
    assert it["status"] == "placed" and it["msg"].startswith("卖单已发出；B.T 的买单被挡")
    n = sum(1 for e in _ev(r) if e["msg"].startswith("★ 「全部换成 B.T」的卖单已发出"))
    assert n == 1


# ────────── ⑦ HALT 挡住开盘后补单 ──────────
def test_halt_between_morning_and_open_note_on_deferred_buy_and_reply_warns():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _allin(r, r.at(r.k - 1, 6).isoformat())
    r.day()
    xo = next(o for o in _orders(r, "B.T", "BUY") if o.decided_on == r.eng.st.last_date)
    assert xo.status == "DEFERRED"
    book = json.loads((paths.state_dir() / "book.json").read_text(encoding="utf-8"))
    note = MO.allin_halt_note(book)
    assert note and "「全部换成 B.T」的卖单已在交易所会成交，B.T 不会买（钱留现金）" in note
    paths.halt_file().write_text("测试", encoding="utf-8")
    try:
        r.day()
    finally:
        paths.halt_file().unlink()
    assert xo.status in ("DEFERRED", "MISSED") and xo.note.startswith(HALT_WAIT)
    if xo.status == "DEFERRED":
        r.day()
    assert xo.status == "MISSED" and xo.note.startswith(HALT_WAIT) and "没买" in xo.note


def test_halt_note_none_without_live_batch():
    assert MO.allin_halt_note({}) is None
    assert MO.allin_halt_note({"state": {"last_date": "2026-10-05"}, "orders": [], "manual": {"items": {}}}) is None


def test_panel_halt_reply_mentions_live_batch():
    d = "2026-10-05"
    items = {"M-b": {"id": "M-b", "kind": "buy", "ticker": "6501.T", "fund": "all", "status": "placed", "decided_on": d, "at": "a"},
             "M-s": {"id": "M-s", "kind": "sell", "ticker": "7203.T", "fund_for": "6501.T", "batch": "all", "status": "placed", "at": "a"}}
    orders = [{"cid": "x1", "ticker": "6501.T", "side": "BUY", "kind": "stock", "status": "DEFERRED", "decided_on": d},
              {"cid": "x2", "ticker": "7203.T", "side": "SELL", "kind": "stock", "status": "SENT", "decided_on": d, "reason": "manual"}]
    _book(last=d, orders=orders, manual={"items": items, "blocks": {}})
    msg = panel._halt_allin("已停止")
    assert msg.startswith("已停止；") and "「全部换成 6501.T」的卖单已在交易所会成交，6501.T 不会买（钱留现金）" in msg
    _book(last=d, orders=[dict(orders[0], status="SENT"), orders[1]], manual={"items": items, "blocks": {}})
    assert panel._halt_allin("已停止") == "已停止"


# ────────── ⑧ 整个运行不下单 ──────────
def test_blocked_run_holds_plain_buys_and_adjust_ups():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    sh = int(r.eng.st.pos["A.T"].shares)
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100, "source": "test", "id": "M-b", "at": at})
    _write({"kind": "adjust", "ticker": "A.T", "unit": "shares", "value": sh + 100, "source": "test", "id": "M-up", "at": at, "dir": 1})
    r.ux.block("测试：行情落后")
    r.day()
    for rid in ("M-b", "M-up"):
        it = r.item(rid)
        assert it["status"] == "pending" and it.get("hold") and it["msg"] == "这次运行不下单 → 等下一次能下单的决策"
    assert "B.T" not in r.eng.st.plan and "A.T" not in r.ux.manual.m["adds"]
    r.ux.blocked = None
    r.day()
    assert r.item("M-b")["status"] == "placed" and r.item("M-up")["status"] == "placed"
    r.day()
    assert "B.T" in r.eng.st.pos and int(r.eng.st.pos["A.T"].shares) == sh + 100


# ────────── ⑨ 面板 / 命令行 ──────────
def test_panel_split_refused_for_buy_the_executor_would_block():
    b = _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"]})
    b["state"]["core_last"] = {"1545.T": 250.0}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm()                                                                     # 9984：新仓倍数 0
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "9984", "unit": "shares", "value": 300,
                               "fund": {"mode": "split", "cost": 645_000}}, AT)
    assert not ok and msg.startswith("没写（从持仓凑钱买）") and not MO.read_all("paper")


def test_panel_split_writes_dir_and_one_shared_time_and_warns_about_gaps():
    b = _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"]})
    b["state"]["core_last"] = {"1545.T": 250.0}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm_nowarn()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "buy", "ticker": "9984", "unit": "shares", "value": 300,
                                 "fund": {"mode": "split", "cost": 645_000}}, AT)
    assert ok and "开盘跳空 / 价格更高没买到时，凑钱的卖出照样会卖" in msg and "被挡则凑钱的卖出也不做" in msg
    reqs = MO.read_all("paper")
    assert len({r["at"] for r in reqs}) == 1
    assert reqs[0]["kind"] == "adjust" and reqs[0]["dir"] == -1 and reqs[0]["cur0"] == 200


def test_panel_and_cli_adjust_store_direction(monkeypatch):
    import run
    from qbreak import calendar_jp as CJ
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    _sm()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "adjust", "ticker": "7203", "unit": "shares", "value": 300}, AT)
    assert ok and rec["dir"] == 1 and rec["cur0"] == 200
    MO.requests_path("paper").unlink()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "adjust", "ticker": "7203", "unit": "shares", "value": 100}, AT)
    assert ok and rec["dir"] == -1 and rec["cur0"] == 200
    monkeypatch.setattr(CJ, "now_jst", lambda: AT)
    MO.requests_path("paper").unlink()
    assert run.main(["manual", "adjust", "7203", "--shares", "300", "--broker", "paper"]) == 0
    rec = MO.read_all("paper")[0]
    assert rec["dir"] == 1 and rec["cur0"] == 200


def test_panel_all_in_records_expected_fill_day_and_close():
    from test_fund_all import _book4
    _book4()
    _sm()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501", "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok and rec["allin_fill"] and rec["x_close"] == 3500.0
    assert dt.date.fromisoformat(rec["allin_fill"]) >= AT.date()
    assert "执行时拿着的 6501.T 以外的个股和 ETF 全部卖出（包括写指令之后规则 / 别的指令买进的）" in msg
