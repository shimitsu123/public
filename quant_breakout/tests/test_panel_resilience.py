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
