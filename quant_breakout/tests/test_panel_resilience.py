"""面板的再发防止（2026-10-12：手机上点「买入 1482」→ 固定口数这种指令没有说明文字 → 拼接崩溃 → 连接断开 → Tailscale 回 HTTP 502、
页面写「没写成」，其实已经写进去了，用户又点了一次）：每种指令都有说明；处理中出异常 → 回能读的 JSON（可能已写 → 先确认）。"""
import json

import pytest

from qbreak import manual_orders as MO
from qbreak import panel

from test_panel import AT, _book, _pane, _req, _sm, _sm_nowarn, _submit_ok, server  # noqa: F401（pytest 夹具）

BODIES = {
    "sell": {"ticker": "7203"},
    "trim": {"ticker": "7203", "pct": 5},
    "adjust": {"ticker": "7203", "unit": "shares", "value": 100},
    "buy": {"ticker": "6501"},
    "core": {"pct": 50},
    "corefix": {"ticker": "1545", "units": 50},
    "unblock": {"ticker": "7203"},
}


@pytest.mark.parametrize("kind", list(BODIES) + ["corefix_clear"])
def test_every_kind_returns_a_message(kind):
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"], "blocked": {"7203.T": {"until": "2026-12-01"}}})
    _sm()
    body = {"ticker": "1545", "clear": True} if kind == "corefix_clear" else BODIES[kind]
    ok, msg, rec = panel.submit({"book": "paper", "kind": kind.split("_")[0], **body}, AT, fetch=lambda ts: {})   # 不联网取现价
    assert isinstance(msg, str) and msg, (kind, msg)
    if ok:
        assert msg.startswith("已写") and rec["id"] in msg


def test_all_kinds_covered():
    assert set(MO.KINDS) - {"cancel", "cancel_order", "uncancel"} <= {k.split("_")[0] for k in BODIES}


def test_internal_error_returns_json_not_dropped_connection(server, monkeypatch):  # noqa: F811
    port, tok = server
    _book()

    def boom(*a, **k):
        raise TypeError("测试用的异常")
    monkeypatch.setattr(panel, "submit", boom)
    code, body, _ = _req(port, "POST", "/api/request", {"book": "paper", "kind": "sell", "ticker": "7203"},
                         {"X-Qbreak-Token": tok, "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"})
    j = json.loads(body)
    assert code == 500 and j["ok"] is False and j["unsure"] is True and "不要直接再点" in j["msg"]


def test_waiting_corefix_can_be_cancelled_with_clear_confirm():
    """2026-10-12 用户：「等下单也可以选择撤单，点击撤单后要出来确认防止误撤销」：固定口数也给撤单按钮，确认框写明是哪一条。"""
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T", "1482.T"]})
    _sm()
    ok, _m, rec = _submit_ok({"book": "paper", "kind": "corefix", "ticker": "1482", "units": 300}, AT)
    assert ok
    html = panel.render("paper", "t" * 40, AT)
    i = html.index(f"data-id='{rec['id']}'")
    btn = html[html.rindex("<button", 0, i):html.index("</button>", i)]
    assert "data-act='cancel'" in btn and ">撤回" in btn and "data-desc='" in btn and "1482 对冲版" in btn   # 固定口数不是单：撤回（2026-10-17）
    assert "'确认撤回？' : '确认撤单？'" in panel._JS and "'确认撤回' : '确认撤单', {danger:true}" in panel._JS             # 一定先确认
    ok, msg, _ = panel.submit({"book": "paper", "kind": "cancel", "target": rec["id"]}, AT)
    assert ok and "撤回" in msg
    b = json.loads((panel.paths.state_dir() / "live_unified_paper.json").read_text())
    man = MO.Manual(b, "paper")
    man.ingest()
    assert man.m["items"][rec["id"]]["status"] == "cancelled" and "1482.T" not in (man.m.get("core_fix") or {})


def test_cancel_split_buy_also_cancels_its_fund_sells():
    b = _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"]})
    b["state"]["core_last"] = {"1545.T": 250.0}
    (panel.paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    _sm_nowarn()
    ok, _m, buy = panel.submit({"book": "paper", "kind": "buy", "ticker": "9984", "unit": "shares", "value": 300,
                                "fund": {"mode": "split", "cost": 645_000}}, AT)
    assert ok and buy["fund"] == "split"
    sells = [r for r in MO.read_all("paper") if r.get("fund_for") == "9984.T"]
    assert len(sells) == 1
    html = panel.render("paper", "t" * 40, AT)
    i = html.index(f"data-id='{buy['id']}'")
    assert "data-fund='1'" in html[i:html.index("</button>", i)]
    ok, msg, _ = panel.submit({"book": "paper", "kind": "cancel", "target": buy["id"]}, AT)
    assert ok and "为它凑钱的 1 条卖出也撤回" in msg
    targets = {r["target"] for r in MO.read_all("paper") if r["kind"] == "cancel"}
    assert targets == {buy["id"], sells[0]["id"]}


def test_auto_buy_card_lists_planned_and_near_with_days():
    """2026-10-12 用户：「选股最上面还要有将会按照规则自动进行购买的股票，大概几天后」。"""
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    sg = {"asof": "2026-10-09", "fill_day": "2026-10-13", "rows": [
        {"ticker": "6501.T", "code": "6501", "name": "日立", "status": "triggered", "rule": {"state": "planned", "text": "规则已安排：10/13 开盘买 100 股"}},
        {"ticker": "1925.T", "code": "1925", "name": "大和ハウス", "status": "imminent", "near": {"where": "below_up", "days": 3, "miss": []},
         "prob": {"p": 0.09}, "buy": {"px": 500.0, "em": 1.0, "lot": 100}},
        {"ticker": "2002.T", "code": "2002", "name": "日清製粉", "status": "watch", "near": {"where": "below_up", "days": 1, "miss": ["量"]},
         "prob": {"p": 0.03}, "buy": {"px": 5000.0, "em": 0.5, "lot": 100}},
        {"ticker": "9007.T", "code": "9007", "name": "小田急", "status": "watch", "near": {"where": "below_up", "days": 9}},
        {"ticker": "9008.T", "code": "9008", "name": "京王", "status": "watch", "near": {"where": "below_up", "days": 2}, "buy": {"block": "JPX 指定"}}]}
    book = json.loads((panel.paths.state_dir() / "live_unified_paper.json").read_text())
    h = panel._auto_buy_card(sg, book, "paper", 1_000_000)
    assert "<h2>规则接下来会自动买</h2>" in h and "已经出了买入信号" in h and "规则已安排：10/13 开盘买 100 股" in h
    assert h.index("2002") < h.index("1925")                                   # 近的在前
    assert "约 1 天" in h and "约 10/13 金叉" in h and "约 3 天" in h and "约 10/15 金叉" in h
    assert "约 400 股" in h and "买不起" in h and "其中 1 只出了信号也买不起" in h
    assert "9007" not in h and "9008" not in h                                 # 超过 5 天 / 闸门挡的不列
    assert panel._auto_buy_card({}, book, "paper", 1_000_000) == ""


def test_trade_tab_shows_only_last_two_days_except_unfinished():
    """2026-10-12 用户：「交易里面的股票只显示两天以内的，两天以上的不要」—— 没处理完的（等下单 / 已下单）一直显示。"""
    old, new = "2026-10-01T09:00:00+09:00", "2026-10-05T20:00:00+09:00"            # AT = 2026-10-06 08:00
    items = {"M-old-done": {"id": "M-old-done", "kind": "sell", "ticker": "6758.T", "status": "done", "at": old},
             "M-old-pend": {"id": "M-old-pend", "kind": "sell", "ticker": "7203.T", "status": "pending", "at": old},
             "M-new-done": {"id": "M-new-done", "kind": "unblock", "ticker": "9984.T", "status": "done", "at": new}}
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": items})
    html = panel.render("paper", "t" * 40, AT)
    card = _pane(html, "trade")                        # 2026-10-16：手动指令分在「今天要成交的单」/「另有…」/「已结束 / 不是今天的」里
    assert "M-old-pend" in card and "M-old-done" not in card and "10-05 20:00" in card
    assert "只显示最近 2 天的（没处理完的一直显示）；更早的 1 条不显示" in card


def _orders_card(html: str) -> str:
    """交易页里手动指令的那几行（2026-10-16 起分在「今天要成交的单」/「另有…」/「已结束 / 不是今天的」里 → 整个交易页）。"""
    return _pane(html, "trade")


def test_uncancel_before_executor_reads_restores_and_hides_the_cancel():
    """2026-10-12 用户：「撤回指令也可以进行撤回，撤回的话会退回到下单，然后去掉撤销记录；只写代码不知道哪只股票，要写上名字」。"""
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    _sm()
    ok, _m, sell = panel.submit({"book": "paper", "kind": "sell", "ticker": "7203"}, AT)
    ok2, _m, cxl = panel.submit({"book": "paper", "kind": "cancel", "target": sell["id"]}, AT)
    assert ok and ok2
    card = _orders_card(panel.render("paper", "t" * 40, AT))
    assert "卖出全部 7203 トヨタ自動車" in card and "撤回：卖出全部 7203 トヨタ自動車" in card       # 写名字
    assert f"data-act='uncancel' data-id='{cxl['id']}'" in card and "等下单（撤回中）" in card
    assert "ask('撤销这条撤回？'" in panel._JS
    ok, msg, _ = panel.submit({"book": "paper", "kind": "uncancel", "target": cxl["id"]}, AT)
    assert ok and "原来的指令恢复「等下单」" in msg
    card = _orders_card(panel.render("paper", "t" * 40, AT))
    assert "撤回：" not in card and "撤销撤回" not in card and "等下单（撤回中）" not in card    # 撤回记录不再显示
    assert f"data-act='cancel' data-id='{sell['id']}'" in card                                       # 原来的指令又能撤
    assert "已经撤销过" in panel.submit({"book": "paper", "kind": "uncancel", "target": cxl["id"]}, AT)[1]
    b = json.loads((panel.paths.state_dir() / "live_unified_paper.json").read_text())
    man = MO.Manual(b, "paper")
    man.ingest()
    it = man.m["items"]
    assert it[sell["id"]]["status"] == "pending" and it[cxl["id"]]["status"] == "voided"


def test_uncancel_after_executor_read_restores_pending_order():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    _sm()
    _o, _m, sell = panel.submit({"book": "paper", "kind": "sell", "ticker": "7203"}, AT)
    p = panel.paths.state_dir() / "live_unified_paper.json"
    b = json.loads(p.read_text())
    man = MO.Manual(b, "paper")
    man.ingest()                                                              # 执行器读了卖出
    p.write_text(json.dumps(b), encoding="utf-8")
    _o, _m, cxl = panel.submit({"book": "paper", "kind": "cancel", "target": sell["id"]}, AT)
    b = json.loads(p.read_text())
    man = MO.Manual(b, "paper")
    man.ingest()                                                              # 执行器读了撤回 → 卖出变成已撤回
    assert man.m["items"][sell["id"]]["status"] == "cancelled"
    p.write_text(json.dumps(b), encoding="utf-8")
    card = _orders_card(panel.render("paper", "t" * 40, AT))
    assert f"data-act='uncancel' data-id='{cxl['id']}'" in card
    ok, _m, _r = panel.submit({"book": "paper", "kind": "uncancel", "target": cxl["id"]}, AT)
    assert ok
    b = json.loads(p.read_text())
    man = MO.Manual(b, "paper")
    man.ingest()
    assert man.m["items"][sell["id"]]["status"] == "pending" and man.m["items"][cxl["id"]]["status"] == "voided"
    p.write_text(json.dumps(b), encoding="utf-8")
    card = _orders_card(panel.render("paper", "t" * 40, AT))
    assert "撤回：" not in card and "卖出全部 7203 トヨタ自動車" in card


def test_uncancel_refused_when_setting_already_decided():
    """固定口数这种读到就定了的：执行器读到之前撤回 → 读的时候已经不生效 → 之后撤销不了（给理由）。"""
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T", "1482.T"]})
    _sm()
    _o, _m, fx = _submit_ok({"book": "paper", "kind": "corefix", "ticker": "1482", "units": 300}, AT)
    _o, _m, cxl = panel.submit({"book": "paper", "kind": "cancel", "target": fx["id"]}, AT)
    card = _orders_card(panel.render("paper", "t" * 40, AT))
    assert "固定 1482 对冲版美国 7〜10 年国债" in card or "固定 1482" in card
    p = panel.paths.state_dir() / "live_unified_paper.json"
    b = json.loads(p.read_text())
    man = MO.Manual(b, "paper")
    man.ingest()
    p.write_text(json.dumps(b), encoding="utf-8")
    ok, msg, _ = panel.submit({"book": "paper", "kind": "uncancel", "target": cxl["id"]}, AT)
    assert not ok and "撤销不了" in msg


def test_notify_log_shows_only_last_24_hours():
    """2026-10-12 用户：「通知记录里面只显示 24 小时以内的记录」—— 卡片与「通知记录 N」按钮上的数字一致。"""
    from qbreak import notify
    p = panel.paths.out_dir() / notify.LOG_FILE
    fmt = lambda h: (AT - __import__("datetime").timedelta(hours=h)).strftime("%Y-%m-%d %H:%M:%S")   # noqa: E731
    recs = [{"id": "stale", "at": fmt(30), "level": "info", "subject": "旧的", "text": "x"},
            {"id": "dayold", "at": fmt(23), "level": "warn", "subject": "一天前", "text": "y"},
            {"id": "fresh", "at": fmt(1), "level": "info", "subject": "新的", "text": "z"}]
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n", encoding="utf-8")
    h = panel._notify_log_card(AT)
    assert "id='l-fresh'" in h and "id='l-dayold'" in h and "id='l-stale'" not in h
    assert "通知记录（最近 24 小时 2 条）" in h and "更早的 1 条不显示" in h
    assert "通知记录 2</button>" in panel._msg_seg(AT)
    _book()
    html = panel.render("paper", "t" * 40, AT)
    assert "id='l-stale'" not in html and "id='l-fresh'" in html
    p.write_text(json.dumps(recs[0], ensure_ascii=False) + "\n", encoding="utf-8")
    h = panel._notify_log_card(AT)
    assert "最近 24 小时没有通知（更早的 1 条不显示）" in h and "id='l-" not in h and "通知记录 0</button>" in panel._msg_seg(AT)
