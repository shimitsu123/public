"""〔77〕C：面板的损益 / 立花那边 / 上线准备 / 入出金登记 / 状态轮询 / dry-run 只读，交易记录导出（只展示与提醒；不改交易）。"""
import argparse
import csv
import datetime as dt
import json

from qbreak import broker_snapshot as BS
from qbreak import live_gate as LG
from qbreak import money_view as MV
from qbreak import panel, paths
from qbreak.brokers.base import Position
from qbreak.calendar_jp import JST

AT = dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST)


def _book(tag="tachibana"):
    st = {"last_date": "2026-10-05", "cash_jpy": 192.0,
          "history": [["2026-10-02", 1_000_000.0, 0, 0, 150], ["2026-10-05", 1_010_000.0, 0, 0, 150]],
          "pos": {}, "pending_exit": {}, "core_units": {"1545.T": 4110},
          "trades": [{"ticker": "7203.T", "market": "JP", "exit_date": "2026-10-03", "shares": 100, "exit_px": 3100, "pnl_jpy": 9000}],
          "core_trades": [["2026-09-30", "1545.T", "BUY", 4110, 241.87, 500.0]]}
    b = {"state": st, "orders": [], "capital_jpy": 1_000_000.0,
         "history": [{"fill_bar": "2026-09-30", "orders": [{"side": "BUY", "ticker": "1545.T", "kind": "core",
                                                            "filled_qty": 4110, "filled_px": 241.87}]}]}
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


def test_money_summary_pnl_ytd_and_fills():
    m = MV.summary("tachibana", _book(), today="2026-10-06")
    assert m["eq"] == 1_010_000 and m["day"] == 10_000 and m["tot"] == 10_000
    assert m["ytd"]["gain"] == 9000 and m["ytd"]["withheld"] == round(9000 * 0.20315)
    assert m["fills"][0]["ticker"] == "1545.T" and len(m["spark"]) == 2
    assert MV.sparkline(m["spark"]).startswith("<svg")
    assert MV.core_name("1545.T") == "纳斯达克 100（1545）"


def test_render_has_money_broker_gate_and_flow_cards():
    _book()
    BS.record_check("tachibana", {"1545.T": Position("1545.T", 4000, 241.0)}, 12345, json.loads(
        (paths.state_dir() / "live_unified_tachibana.json").read_text(encoding="utf-8")))
    LG.save([{"group": "门槛", "name": "① 连续一致", "ok": False, "text": "★ 6/10"}])
    h = panel.render("tachibana", "t" * 40, AT)
    for k in ("id='money'", "id='broker'", "id='gate'", "id='flow'", "2026 年已实现", "账本和立花不一致 1 只", "还没全部满足"):
        assert k in h, k
    _book("paper")
    hp = panel.render("paper", "t" * 40, AT)
    assert "id='money'" in hp and "id='broker'" not in hp and "id='flow'" not in hp      # 模拟账户：没有立花那边、不登记入出金


def test_flow_submit_registers_under_lock_and_paper_refuses():
    _book()
    ok, msg, _ = panel.submit({"book": "tachibana", "kind": "flow", "jpy": "300,000", "date": "2026-10-06", "note": "x"}, AT)
    assert ok and "已登记入金 +300,000 円" in msg
    b = json.loads((paths.state_dir() / "live_unified_tachibana.json").read_text(encoding="utf-8"))
    assert b["flows"][-1]["jpy"] == 300000 and b["flows"][-1]["date"] == "2026-10-06"
    assert not panel.submit({"book": "tachibana", "kind": "flow", "jpy": "abc"}, AT)[0]
    _book("paper")
    assert not panel.submit({"book": "paper", "kind": "flow", "jpy": 1000}, AT)[0]


def test_flow_refused_while_executor_holds_the_lock():
    from qbreak.live_unified import RunLock
    _book()
    lock = RunLock((paths.state_dir() / "live_unified_tachibana.json").with_suffix(".lock"), wait_s=0).acquire()
    try:
        ok, msg, _ = panel.submit({"book": "tachibana", "kind": "flow", "jpy": 1000}, AT)
    finally:
        lock.release()
    assert not ok and "执行器正在运行" in msg


def test_dryrun_book_is_read_only():
    _book("tachibana_dryrun")
    ok, msg, _ = panel.submit({"book": "tachibana_dryrun", "kind": "sell", "ticker": "7203.T"}, AT)
    assert not ok and "只能看" in msg
    assert "dry-run 的账本：只能看" in panel.render("tachibana_dryrun", "t" * 40, AT)


def test_status_signature_changes_with_manual_items():
    b = _book()
    s0 = panel.status_json("tachibana")[1]
    b["manual"] = {"items": {"m1": {"id": "m1", "status": "pending", "kind": "sell"}}}
    (paths.state_dir() / "live_unified_tachibana.json").write_text(json.dumps(b), encoding="utf-8")
    s1 = panel.status_json("tachibana")[1]
    assert s0["sig"] != s1["sig"] and s1["pending"] >= 1


def test_status_endpoint_on_local_port():
    import http.client
    import threading
    from http.server import ThreadingHTTPServer
    _book()
    tok = panel.token()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), panel.make_handler(1, tok))
    port = srv.server_address[1]
    srv.RequestHandlerClass = panel.make_handler(port, tok, clock=lambda: AT)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", "/api/status?book=tachibana", headers={"Host": f"127.0.0.1:{port}"})
        r = c.getresponse()
        j = json.loads(r.read().decode("utf-8"))
        assert r.status == 200 and j["ok"] and len(j["sig"]) == 16
    finally:
        srv.shutdown()
        srv.server_close()


def test_export_writes_bom_csv(capsys):
    import run
    _book()
    rc = run.cmd_live_export(argparse.Namespace(broker="tachibana", demo=False, dry_run=False, year=2026))
    assert rc == 0
    d = paths.out_dir() / "export"
    raw = (d / "tachibana_2026_realized.csv").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(raw.decode("utf-8-sig").splitlines()))
    assert rows[1][:2] == ["2026-10-03", "7203.T"] and rows[1][-1] == "9000"
    assert (d / "tachibana_2026_fills.csv").exists() and "预计已代扣" in capsys.readouterr().out


def test_gate_save_and_load():
    LG.save([{"group": "门槛", "name": "a", "ok": True, "text": "OK"}, {"group": "参考", "name": "b", "ok": None, "text": "x"}])
    g = LG.load_saved()
    assert g["ok"] is True and [i["name"] for i in g["items"]] == ["a", "b"]


def test_flow_over_http_with_trigger_answers_once():
    """〔77〕C 审查：面板（带 Trigger）登记入出金 → 回 200 JSON（以前 _after_submit 读 rec["kind"] 抛错、连接断开，用户重试就登记两次）。"""
    import http.client
    import threading
    from http.server import ThreadingHTTPServer
    _book()
    tok = panel.token()
    trig = panel.Trigger(run=lambda *a, **k: None)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), panel.make_handler(1, tok))
    port = srv.server_address[1]
    srv.RequestHandlerClass = panel.make_handler(port, tok, trigger=trig, clock=lambda: AT)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("POST", "/api/request", body=json.dumps({"book": "tachibana", "kind": "flow", "jpy": 5000}).encode("utf-8"),
                  headers={"Host": f"127.0.0.1:{port}", "X-Qbreak-Token": tok, "Content-Type": "application/json"})
        r = c.getresponse()
        j = json.loads(r.read().decode("utf-8"))
        assert r.status == 200 and j["ok"] and "已登记入金" in j["msg"]
    finally:
        srv.shutdown()
        srv.server_close()
    b = json.loads((paths.state_dir() / "live_unified_tachibana.json").read_text(encoding="utf-8"))
    assert [f["jpy"] for f in b["flows"]] == [5000]


def test_flow_reserve_from_panel_and_card():
    _book()
    ok, msg, _ = panel.submit({"book": "tachibana", "kind": "flow", "jpy": -200000, "reserve": True}, AT)
    assert ok and "并预留" in msg
    assert not panel.submit({"book": "tachibana", "kind": "flow", "jpy": 5000, "reserve": True}, AT)[0]   # 入金不能预留
    h = panel.render("tachibana", "t" * 40, AT)
    assert "出金预留中" in h and "id='flow-reserve'" in h
