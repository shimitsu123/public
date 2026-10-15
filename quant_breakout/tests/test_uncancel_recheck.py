"""撤销撤回（2026-10-13 审计）：恢复之前按现在的账本重查。
①「全部换成 X」：X 已经持有 / 撤回之后又做过别的「全部换成」/ fund_all 被挡 / 买入本身过不了 → 拒绝（请重新提交）；能恢复时说明写整批卖出那时拿着的全部；
② 平摊凑钱的卖出：现在已经不拿 / 不高于目标 → 拒绝（绝不说「卖出」却什么都不卖）；③ 撤回之后同一只票又写过别的指令 → 拒绝；
④ 确认框与说明写恢复之后实际什么时候、按什么价处理（HALT 中写明）；⑤ 执行器记录写指令的说明（比例那条以前是「None」）、prev_pct 按现在的比例。"""
import datetime as dt
import json

from qbreak import manual_orders as MO
from qbreak import panel, paths

from test_fund_all import _book4, _reqs
from test_panel import AT, _book, _sm, _sm_nowarn, _submit_ok

BP = lambda: paths.state_dir() / "live_unified_paper.json"   # noqa: E731


def _save(b: dict) -> None:
    BP().write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")


def _load() -> dict:
    return json.loads(BP().read_text())


def _allin_then_cancel(ticker="6501", sm=_sm):
    _book4()
    sm()
    ok, msg, buy = panel.submit({"book": "paper", "kind": "buy", "ticker": ticker, "unit": "shares", "value": 300, "fund": {"mode": "all"}}, AT)
    assert ok, msg
    ok, msg, cx = panel.submit({"book": "paper", "kind": "cancel", "target": buy["id"]}, AT)
    assert ok, msg
    return buy, cx


def _un(cx, now=AT):
    return panel.submit({"book": "paper", "kind": "uncancel", "target": cx["id"]}, now)


def _card(html: str) -> str:
    i = html.index("<h2>手动指令</h2>")
    return html[i:html.index("</section>", i)]


# ────────── ①「全部换成 X」按现在的账本重查 ──────────
def test_allin_uncancel_refused_when_x_already_held():
    _buy, cx = _allin_then_cancel()
    b = _load()
    b["state"]["pos"]["6501.T"] = {"shares": 100, "entry_px": 3500.0, "entry_date": "2026-10-05", "stop_px": 3200.0, "last_close": 3500.0}
    _save(b)
    ok, msg, _ = _un(cx)
    assert not ok and "6501.T 现在已经持有" in msg and msg.endswith("请重新提交「全部换成」"), msg
    assert not _reqs("uncancel")
    assert f"data-act='uncancel' data-id='{cx['id']}'" not in _card(panel.render("paper", "t" * 40, AT))


def test_allin_uncancel_refused_when_a_later_allin_already_done():
    _buy, cx = _allin_then_cancel()
    b = _load()
    later = {"id": "M-later-all", "kind": "buy", "ticker": "9984.T", "unit": "shares", "value": 100, "fund": "all",
             "status": "done", "at": (AT + dt.timedelta(hours=1)).isoformat(), "source": "panel"}
    b["manual"]["items"]["M-later-all"] = later
    _save(b)
    ok, msg, _ = _un(cx)
    assert not ok and "撤回之后已经有过「全部换成 9984.T」（M-later-all）" in msg and "请重新提交「全部换成」" in msg, msg


def test_allin_uncancel_refused_when_unread_corefix_written_after_the_cancel():
    _buy, cx = _allin_then_cancel()
    ok, msg, _fx = _submit_ok({"book": "paper", "kind": "corefix", "ticker": "1545", "units": 50}, AT + dt.timedelta(minutes=1))
    assert ok, msg
    ok, msg, _ = _un(cx, AT + dt.timedelta(minutes=2))
    assert not ok and "按现在的账本重新检查没通过" in msg and "固定口数" in msg and "请重新提交「全部换成」" in msg, msg


def test_allin_uncancel_refused_when_a_new_holding_has_a_live_trim():
    """撤回之后规则买进的票上又写了减仓 → 整批卖出时会冲突（fund_all 被挡）→ 请重新提交。"""
    _buy, cx = _allin_then_cancel()
    b = _load()
    b["state"]["pos"]["4063.T"] = {"shares": 100, "entry_px": 5000.0, "entry_date": "2026-10-05", "stop_px": 4600.0, "last_close": 5000.0}
    _save(b)
    MO.append("paper", {"kind": "trim", "ticker": "4063.T", "pct": 5, "source": "test"}, clock=lambda: AT + dt.timedelta(minutes=1))
    ok, msg, _ = _un(cx, AT + dt.timedelta(minutes=2))
    assert not ok and "4063.T" in msg and "请重新提交「全部换成」" in msg, msg


def test_allin_uncancel_after_holdings_changed_says_what_will_be_sold_and_when():
    _buy, cx = _allin_then_cancel()
    b = _load()
    del b["state"]["pos"]["9432.T"]
    b["state"]["pos"]["4063.T"] = {"shares": 100, "entry_px": 5000.0, "entry_date": "2026-10-05", "stop_px": 4600.0, "last_close": 5000.0}
    _save(b)
    html = _card(panel.render("paper", "t" * 40, AT))
    i = html.index(f"data-act='uncancel' data-id='{cx['id']}'")
    btn = html[i:html.index(">撤销撤回<", i)]
    assert "data-when='10/07 开盘整批先卖后买（那次决策先过闸门）" in btn and "4063.T 100 股" in btn and "data-halt" not in btn
    ok, msg, _ = _un(cx)
    assert ok and "同批的 5 条卖出 / 闲置资金指令一起恢复" in msg, msg
    assert ("10/07 开盘整批先卖后买（那次决策先过闸门）：卖出那时拿着的 6501.T 以外的全部个股和 ETF（现在：4063.T 100 股、6758.T 100 股、"
            "7203.T 100 股、8306.T 100 股、1545.T 100 口）、闲置资金比例 0%、取消全部固定口数") in msg
    assert "★ HALT" not in msg


def test_allin_uncancel_then_execution_sells_holding_bought_while_cancelled():
    """撤回期间规则买进的票：撤销撤回不拦（执行时拿着的都卖），执行器决策时一起卖掉、买 X。"""
    from test_manual_buy import _write
    from test_manual_orders import TAG, _Run
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(9)
    assert "A.T" not in r.eng.st.pos
    at = r.at(r.k - 1, 6).isoformat()
    _write({"kind": "core", "pct": 0, "fund_for": "B.T", "batch": "all", "source": "test", "id": "M-all-core", "at": at, "prev_pct": 100})
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100_000, "fund": "all", "source": "test", "id": "M-all-buy", "at": at})
    _write({"kind": "cancel", "target": "M-all-buy", "source": "test", "id": "M-cx-buy", "at": at})
    _write({"kind": "cancel", "target": "M-all-core", "source": "test", "id": "M-cx-core", "at": at})
    r.until(14)                                                               # 撤回生效；规则买进 A.T
    assert "A.T" in r.eng.st.pos and r.item("M-all-buy")["status"] == "cancelled"
    r.ux.save()
    book = json.loads((paths.state_dir() / "book.json").read_text())
    ok, msg, _ = MO.uncancel_request(TAG, book, "M-cx-buy", now=r.at(r.k - 1, 6, 30), source="cli")
    assert ok and "A.T" in msg and "整批先卖后买" in msg, msg
    r.day()
    assert r.item("M-all-buy")["status"] == "placed" and any(o.ticker == "A.T" and o.side == "SELL" for o in r.ux.orders)
    r.day()
    assert set(r.eng.st.pos) == {"B.T"} and r.eng.st.core_units.get("1655.T", 0) == 0


# ────────── ② 平摊凑钱的卖出：现在已经不卖了 → 不恢复 ──────────
def _split_then_cancel(alone=False):
    b = _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"]})
    b["state"]["core_last"] = {"1545.T": 250.0}
    _save(b)
    _sm_nowarn()
    ok, msg, buy = panel.submit({"book": "paper", "kind": "buy", "ticker": "9984", "unit": "shares", "value": 300,
                                 "fund": {"mode": "split", "cost": 645_000}}, AT)
    assert ok, msg
    adj = _reqs("adjust")[0]
    ok, msg, cx = panel.submit({"book": "paper", "kind": "cancel", "target": adj["id"] if alone else buy["id"]}, AT)
    assert ok, msg
    return buy, adj, cx


def test_split_uncancel_success_says_how_much_is_sold():
    _buy, adj, cx = _split_then_cancel()
    a = MO.adjust_plan(adj, _load()["state"], MO.MANUAL_CAP_PCT)
    assert 0 <= a["want"] < a["cur"] == 200
    ok, msg, _ = _un(cx)
    assert ok and f"（凑钱的卖出一起恢复：7203.T 卖 {a['cur'] - a['want']:,} 股（200 → {a['want']:,} 股））" in msg, msg
    assert "马上（盘中）下单" not in msg and "（凑钱的卖出同一时间先卖）" in msg


def test_split_uncancel_refused_when_shares_already_at_or_below_target():
    for alone in (False, True):
        _buy, adj, cx = _split_then_cancel(alone)
        b = _load()
        want = MO.adjust_plan(adj, b["state"], MO.MANUAL_CAP_PCT)["want"]
        b["state"]["pos"]["7203.T"]["shares"] = want
        _save(b)
        ok, msg, _ = _un(cx)
        assert not ok and f"7203.T 现在 {want:,} 股，已经不高于凑钱卖出的目标 {want:,} 股：恢复了也不会卖" in msg and "卖 " not in msg.split("（")[0], msg
        BP().unlink()
        MO.requests_path("paper").unlink()


def test_split_uncancel_refused_when_stock_no_longer_held():
    for alone in (False, True):
        _buy, _adj, cx = _split_then_cancel(alone)
        b = _load()
        del b["state"]["pos"]["7203.T"]
        _save(b)
        ok, msg, _ = _un(cx)
        assert not ok and "7203.T 现在已经不持有：凑钱的卖出用不上" in msg, msg
        assert f"data-act='uncancel' data-id='{cx['id']}'" not in _card(panel.render("paper", "t" * 40, AT))
        BP().unlink()
        MO.requests_path("paper").unlink()


# ────────── ③ 撤回之后同一只票又写过别的指令 ──────────
def test_uncancel_refused_when_same_ticker_had_a_later_instruction():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    _sm()
    _o, _m, sell = panel.submit({"book": "paper", "kind": "sell", "ticker": "7203"}, AT)
    _o, _m, cxa = panel.submit({"book": "paper", "kind": "cancel", "target": sell["id"]}, AT)
    t1 = AT + dt.timedelta(minutes=1)
    ok, msg, trim = panel.submit({"book": "paper", "kind": "trim", "ticker": "7203", "pct": 5}, t1)
    assert ok, msg
    _o, _m, _cxb = panel.submit({"book": "paper", "kind": "cancel", "target": trim["id"]}, t1)   # 之后那条也撤回了（不在处理）：照样算
    t2 = AT + dt.timedelta(minutes=2)
    ok, msg, _ = _un(cxa, t2)
    assert not ok and f"撤回之后 7203.T 已经有过别的指令（{trim['id']}）：请重新下" in msg, msg
    assert f"data-act='uncancel' data-id='{cxa['id']}'" not in _card(panel.render("paper", "t" * 40, t2))
    assert MO.check({"kind": "uncancel", "target": _cxb["id"]}, _load(), "paper", now=t2) is None   # 之后那条自己的撤回能撤销


def test_uncancel_later_instruction_counted_even_after_executor_read_it():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    _sm()
    _o, _m, sell = panel.submit({"book": "paper", "kind": "sell", "ticker": "7203"}, AT)
    _o, _m, cxa = panel.submit({"book": "paper", "kind": "cancel", "target": sell["id"]}, AT)
    _o, _m, adj = panel.submit({"book": "paper", "kind": "adjust", "ticker": "7203", "unit": "shares", "value": 100}, AT + dt.timedelta(minutes=1))
    b = _load()
    man = MO.Manual(b, "paper")
    man.ingest()
    man.m["items"][adj["id"]]["status"] = "done"                              # 之后那条已经做完
    _save(b)
    ok, msg, _ = _un(cxa, AT + dt.timedelta(minutes=2))
    assert not ok and f"撤回之后 7203.T 已经有过别的指令（{adj['id']}）" in msg, msg


# ────────── ④ 确认框 / 说明写实际的时间与价格；HALT ──────────
def _btn(html: str, cid: str) -> str:
    i = html.index(f"data-act='uncancel' data-id='{cid}'")
    return html[i:html.index(">撤销撤回<", i)]


def test_uncancel_button_and_message_give_actual_timing():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    _sm()
    _o, _m, sell = panel.submit({"book": "paper", "kind": "sell", "ticker": "7203"}, AT)
    _o, _m, cx = panel.submit({"book": "paper", "kind": "cancel", "target": sell["id"]}, AT)
    btn = _btn(panel.render("paper", "t" * 40, AT), cx["id"])
    assert "data-when='今天 09:00 开盘按开盘价卖（寄付成行）'" in btn and "data-halt" not in btn
    t10 = AT.replace(hour=10)
    btn = _btn(panel.render("paper", "t" * 40, t10), cx["id"])
    assert "data-when='马上（盘中）下单：模拟账户按执行器下单那一刻的 Yahoo 现价成交" in btn
    ok, msg, _ = _un(cx, t10)
    assert ok and "马上（盘中）下单：模拟账户按执行器下单那一刻的 Yahoo 现价成交" in msg and "★ HALT" not in msg, msg
    assert "d.when" in panel._JS and "照原来的时间处理" not in panel._JS and "★ HALT 生效中（解除后才处理）" in panel._JS


def test_uncancel_under_halt_says_it_waits_for_release():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    _sm()
    _o, _m, sell = panel.submit({"book": "paper", "kind": "sell", "ticker": "7203"}, AT)
    _o, _m, cx = panel.submit({"book": "paper", "kind": "cancel", "target": sell["id"]}, AT)
    paths.halt_file().write_text("test", encoding="utf-8")
    try:
        assert "data-halt='1'" in _btn(panel.render("paper", "t" * 40, AT), cx["id"])
        ok, msg, _ = _un(cx)
        assert ok and msg.split("（指令")[0].endswith("；★ HALT 生效中（解除后才处理）"), msg
    finally:
        paths.halt_file().unlink()


def test_uncancel_when_texts_for_settings():
    b = _book()
    assert MO.uncancel_when({"kind": "core", "pct": 50}, AT, b, "paper").startswith("执行器读到就生效：核心 ETF 今天 09:00 开盘")
    assert MO.uncancel_when({"kind": "corefix", "ticker": "1545.T"}, AT, b, "paper") == "下一次决策（交易日 07:40）起照它调"
    assert MO.uncancel_when({"kind": "unblock", "ticker": "7203.T"}, AT, b, "paper") == MO.NEXT_DECISION
    up = MO.uncancel_when({"kind": "adjust", "ticker": "7203.T", "unit": "shares", "value": 400}, AT, b, "paper")
    assert up.startswith("今天 09:00 开盘买：寄付指値")                          # 调仓往上 = 买
    assert MO.uncancel_when({"kind": "adjust", "ticker": "7203.T", "unit": "shares", "value": 100}, AT, b, "paper") == "今天 09:00 开盘按开盘价卖（寄付成行）"


# ────────── ⑤ 执行器的记录 / prev_pct ──────────
def test_ingest_log_names_core_companion_and_refreshes_prev_pct():
    buy, cx = _allin_then_cancel()
    b = _load()
    MO.Manual(b, "paper").ingest()                                            # 执行器读到撤回：整批已撤回
    _save(b)
    core = _reqs("core")[0]
    assert b["manual"]["items"][core["id"]]["status"] == "cancelled" and core["prev_pct"] == 100.0
    t1 = AT + dt.timedelta(minutes=1)
    ok, msg, _ = panel.submit({"book": "paper", "kind": "core", "pct": 60}, t1)   # 撤回期间改了比例
    assert ok, msg
    b = _load()
    man = MO.Manual(b, "paper")
    man.ingest()
    assert man.core_pct == 60.0
    _save(b)
    ok, msg, _ = _un(cx, t1 + dt.timedelta(minutes=1))
    assert ok, msg
    b = _load()
    man = MO.Manual(b, "paper")
    log = man.ingest()
    it = man.m["items"]
    assert it[buy["id"]]["status"] == "pending" and it[core["id"]]["status"] == "pending"
    assert it[core["id"]]["prev_pct"] == 60.0                                  # 之后撤不了时提示「设回 60%」，不是写指令那时的 100%
    msgs = [it[r["id"]]["msg"] for r in _reqs("uncancel")]
    assert all("None" not in m for m in msgs) and any(m.startswith("撤销撤回：闲置资金比例") for m in msgs), msgs
    assert all("None" not in str(x) for x in log)


def test_allin_uncancel_refused_when_x_now_blocked_by_executor_gate():
    """撤回之后 X 进了「会被执行器挡」（决算前 / 新仓倍数 0）：撤销撤回与提交同一个检查 → 不给恢复（2026-10-14）。"""
    from test_panel import SG_ROWS
    _buy, cx = _allin_then_cancel()
    _sm([dict(r, buy={**r["buy"], "warn": ["规则现在不开这只的新仓（新仓倍数 0）：执行器会挡"]}) if r["ticker"] == "6501.T" else r
         for r in SG_ROWS])
    ok, msg, _ = _un(cx)
    assert not ok and msg.startswith("撤销不了：这只现在会被执行器挡下（") and "等它解除再重新提交" in msg, msg
    assert not _reqs("uncancel")
    assert f"data-act='uncancel' data-id='{cx['id']}'" not in _card(panel.render("paper", "t" * 40, AT))
