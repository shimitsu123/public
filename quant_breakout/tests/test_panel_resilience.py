"""面板的再发防止（2026-10-12：手机上点「买入 1482」→ 固定口数这种指令没有说明文字 → 拼接崩溃 → 连接断开 → Tailscale 回 HTTP 502、
页面写「没写成」，其实已经写进去了，用户又点了一次）：每种指令都有说明；处理中出异常 → 回能读的 JSON（可能已写 → 先确认）。"""
import json

import pytest

from qbreak import manual_orders as MO
from qbreak import panel

from test_panel import AT, _book, _req, _sm, server  # noqa: F401（pytest 夹具）

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
    ok, msg, rec = panel.submit({"book": "paper", "kind": kind.split("_")[0], **body}, AT)
    assert isinstance(msg, str) and msg, (kind, msg)
    if ok:
        assert msg.startswith("已写") and rec["id"] in msg


def test_all_kinds_covered():
    assert set(MO.KINDS) - {"cancel", "cancel_order"} <= {k.split("_")[0] for k in BODIES}


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
    ok, _m, rec = panel.submit({"book": "paper", "kind": "corefix", "ticker": "1482", "units": 300}, AT)
    assert ok
    html = panel.render("paper", "t" * 40, AT)
    i = html.index(f"data-id='{rec['id']}'")
    btn = html[html.rindex("<button", 0, i):html.index("</button>", i)]
    assert "data-act='cancel'" in btn and ">撤单" in btn and "data-desc='" in btn and "1482.T" in btn
    assert "ask('确认撤单？'" in panel._JS and "'确认撤单', {danger:true}" in panel._JS             # 一定先确认
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
    _sm()
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
