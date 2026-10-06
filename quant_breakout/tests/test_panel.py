"""本机操作面板（qbreak/panel.py）：只接受本机、要令牌、只写手动指令；交易日 07:45〜08:50 早上的运行完成后叫执行器重试。"""
import datetime as dt
import http.client
import json
import os
import threading
from http.server import ThreadingHTTPServer

import pytest

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST


def _book(tag="paper", last="2026-10-05", pos=None, orders=None, manual=None):
    st = {"last_date": last, "cash_jpy": 500_000.0, "history": [[last, 1_000_000.0, 0, 0, 150]],
          "pos": pos if pos is not None else {"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01",
                                                         "stop_px": 2325.0, "last_close": 2600.0}},
          "pending_exit": {}, "core_units": {"1545.T": 100}}
    b = {"state": st, "orders": orders or []}
    if manual:
        b["manual"] = manual
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


AT = dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST)


@pytest.fixture()
def server():
    tok = panel.token()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), panel.make_handler(1, tok))
    port = srv.server_address[1]
    srv.RequestHandlerClass = panel.make_handler(port, tok, clock=lambda: AT)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield port, tok
    srv.shutdown()
    srv.server_close()


def _req(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": f"127.0.0.1:{port}"}
    h.update(headers or {})
    data = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    out = r.status, r.read().decode("utf-8"), dict(r.getheaders())
    c.close()
    return out


def test_token_is_private_and_stable():
    t = panel.token()
    p = paths.home() / panel.TOKEN_FILE
    assert len(t) >= 32 and oct(os.stat(p).st_mode & 0o777) == "0o600" and panel.token() == t


def test_page_needs_local_host_and_carries_no_broker_secrets(server):
    port, tok = server
    _book()
    code, html, hd = _req(port, "GET", "/?book=paper")
    assert code == 200 and "qbreak 操作面板" in html and tok in html and "卖出全部" in html and "减仓" in html
    assert hd.get("X-Frame-Options") == "DENY" and "frame-ancestors 'none'" in hd.get("Content-Security-Policy", "")
    assert _req(port, "GET", "/", headers={"Host": "evil.example:80"})[0] == 421          # DNS rebinding
    assert _req(port, "GET", "/etc/passwd")[0] == 404


def test_post_requires_token_origin_json_and_size(server):
    port, tok = server
    _book()
    ok_h = {"X-Qbreak-Token": tok, "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"}
    body = {"book": "paper", "kind": "sell", "ticker": "7203", "block_days": 20}
    assert _req(port, "POST", "/api/request", body, {**ok_h, "X-Qbreak-Token": "x" * 40})[0] == 403
    assert _req(port, "POST", "/api/request", body, {**ok_h, "Origin": "https://evil.example"})[0] == 403
    assert _req(port, "POST", "/api/request", body, {**ok_h, "Content-Type": "text/plain"})[0] == 415
    assert _req(port, "POST", "/api/request", b"x" * 5000, ok_h)[0] == 413
    assert _req(port, "POST", "/api/request", body, {**ok_h, "Host": "evil.example"})[0] == 421
    assert not MO.read_all("paper")                                                        # 上面这些都没写进去
    code, txt, _ = _req(port, "POST", "/api/request", body, ok_h)
    j = json.loads(txt)
    assert code == 200 and j["ok"] and "10/06（今天）开盘" in j["msg"]
    r = MO.read_all("paper")
    assert len(r) == 1 and r[0]["ticker"] == "7203.T" and r[0]["source"] == "panel"
    code, txt, _ = _req(port, "POST", "/api/request", body, ok_h)                           # 同一只票再点：挡住
    assert code == 400 and "没处理完" in json.loads(txt)["msg"]
    code, txt, _ = _req(port, "POST", "/api/request", {**body, "ticker": "6758"}, ok_h)
    assert code == 400 and "没有 6758.T" in json.loads(txt)["msg"]


def test_submit_messages_and_halt_note():
    _book()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "trim", "ticker": "7203", "pct": 10}, AT)
    assert ok and rec["pct"] == 10.0 and "减到约 10%" in msg
    ok, msg, _ = panel.submit({"book": "tachibana", "kind": "core", "pct": 40}, dt.datetime(2026, 10, 6, 9, 30, tzinfo=JST))
    assert ok and "下一次决策" in msg
    assert panel.submit({"book": "../etc", "kind": "core", "pct": 40})[0] is False
    paths.halt_file().write_text("x", encoding="utf-8")
    _book("tachibana")
    ok, msg, _ = panel.submit({"book": "tachibana", "kind": "sell", "ticker": "7203"}, dt.datetime(2026, 10, 6, 9, 30, tzinfo=JST))
    assert ok and "10/07（下一个交易日）开盘" in msg and "HALT" in msg


def test_trigger_runs_retry_only_when_morning_done_and_due(monkeypatch):
    calls = []
    now = {"t": dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST)}
    import qbreak.calendar_jp as CJ
    monkeypatch.setattr(CJ, "now_jst", lambda: now["t"])      # expected_last_bar 看真实时钟：真实日期 = 10-06 收盘后会算成 10-06 → 固定成假时钟
    trg = panel.Trigger(run=lambda tag: calls.append(tag), clock=lambda: now["t"])
    _book(last="2026-10-02")                                   # 早上的运行还没处理 10-05 → 不叫（它自己会读到指令）
    MO.append("paper", {"kind": "sell", "ticker": "7203"})
    assert trg.check() == [] and calls == []
    _book(last="2026-10-05")
    assert trg.check() == ["paper"] and calls == ["paper"]
    assert trg.check() == []                                    # 3 分钟之内不重复
    trg.last.clear()
    now["t"] = dt.datetime(2026, 10, 6, 8, 55, tzinfo=JST)      # 过了 08:50
    assert trg.check() == []
    now["t"] = dt.datetime(2026, 10, 10, 8, 0, tzinfo=JST)      # 周六
    assert trg.check() == []


def test_due_ignores_core_only_and_handled_requests():
    b = _book()
    MO.append("paper", {"kind": "core", "pct": 50})
    assert not MO.due("paper", b, AT)
    rec = MO.append("paper", {"kind": "sell", "ticker": "7203"})
    assert MO.due("paper", b, AT) and not MO.due("paper", b, dt.datetime(2026, 10, 6, 8, 55, tzinfo=JST))
    b["manual"] = {"items": {r["id"]: {**r, "status": "placed"} for r in MO.read_all("paper")}}
    assert not MO.due("paper", b, AT)
    b["manual"]["items"][rec["id"]]["cancel_req"] = "M20261006-081000-cancel"
    assert MO.due("paper", b, AT)


def test_render_shows_reasons_trend_and_hides_buttons_for_pending_exit():
    _book(pos={"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0},
               "6758.T": {"shares": 100, "entry_px": 3000.0, "entry_date": "2026-09-10", "stop_px": 2790.0, "last_close": 3100.0}},
          manual={"core_pct": 60.0, "blocks": {"9984.T": {"until": "2026-11-04"}}, "items": {}})
    b = json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8"))
    b["state"]["pending_exit"] = {"6758.T": "dead_cross"}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b), encoding="utf-8")
    hv = {"bar_date": "2026-10-05", "holdings": [
        {"ticker": "7203.T", "name": "トヨタ自動車", "shares": 200, "entry_date": "2026-09-01", "entry_px": 2500.0,
         "why": {"signal_date": "2026-08-29", "items": [{"key": "volume", "text": "放量：成交量是 20 日平均的 2.10 倍", "ok": True}],
                 "ok": True, "vol_ratio": 2.1, "golden_cross": True, "range_pct": 9.5, "range_n": 60},
         "trend": {"label": "up", "text": "收盘 ¥2,600：20 日线 …", "ret_pct": 4.0}},
        {"ticker": "6758.T", "shares": 100, "error": "x"}], "core": []}
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"holding_view": hv, "fill_day": "2026-10-06"}), encoding="utf-8")
    html = panel.render("paper", "t" * 40, AT)
    assert "トヨタ自動車" in html and "上升趋势" in html and "放量 2.10 倍" in html
    assert html.count("卖出全部</button>") == 1 and "已排定开盘卖（dead_cross）" in html
    assert "规则目标额的 <b>60%</b>" in html and "9984.T" in html and "解除" in html
    assert "模拟账户：手动操作后会和云端模拟盘不一致" in html and "10/06（今天）" in html


def test_submit_adjust_messages_and_due():
    _book(pos={"6758.T": {"shares": 200, "entry_px": 900.0, "entry_date": "2026-09-01", "stop_px": 850.0, "last_close": 1000.0},
               "7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0}})
    ok, msg, rec = panel.submit({"book": "paper", "kind": "adjust", "ticker": "6758", "unit": "yen", "value": 100_000}, AT)
    assert ok and rec["unit"] == "yen" and "估算卖 100 股" in msg and "10/06（今天）开盘前" in msg and "寄付成行" in msg
    MO.append("paper", {"kind": "cancel", "target": rec["id"]})
    b = json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8"))
    b["manual"] = {"items": {rec["id"]: {**rec, "status": "cancelled"}}}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b), encoding="utf-8")
    ok, msg, rec2 = panel.submit({"book": "paper", "kind": "adjust", "ticker": "6758", "unit": "pct", "value": 30}, AT)
    assert ok and "估算加 100 股 → 300 股" in msg and "10/07（下一个交易日）" in msg and "寄付指値" in msg   # 07:40 的决策已经做了
    ok, msg, _ = panel.submit({"book": "paper", "kind": "adjust", "ticker": "7203", "unit": "shares", "value": 400}, AT)
    assert not ok and "不能再加" in msg                         # 已经约占 52%，单只上限 34%
    b = json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8"))
    only_wait = {"state": b["state"], "manual": {"items": {rec2["id"]: {**rec2, "status": "pending", "wait": True}}}}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(only_wait), encoding="utf-8")
    MO.requests_path("paper").write_text(json.dumps(rec2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert not MO.due("paper", only_wait, AT)                   # 等下一次决策的加仓：不叫重试


def test_render_adjust_buttons_and_charts():
    _book(pos={"6758.T": {"shares": 200, "entry_px": 900.0, "entry_date": "2026-09-01", "stop_px": 850.0, "last_close": 1000.0}},
          manual={"cap_pct": 34.0, "items": {}})
    d = ["2026-10-01", "2026-10-02", "2026-10-05"]
    ser = {"d": d, "o": [990.0, 995.0, 1001.0], "h": [1001.0, 1004.0, 1010.0], "l": [985.0, 990.0, 995.0], "c": [995.0, 1000.0, 1000.0],
           "v": [100, 200, 300], "m20": [None, 990.0, 991.0], "m60": [None, None, None]}
    charts = {"6758.T": {**ser, "kind": "stock", "entry_px": 900.0, "entry_date": "2026-09-01", "stop_px": 850.0},
              "1545.T": {**ser, "kind": "core", "name": "纳斯达克 100（1545）"},
              "1482.T": {**ser, "kind": "core", "name": "对冲版美国国债</script><b>x"}}
    hv = {"bar_date": "2026-10-05", "holdings": [{"ticker": "6758.T", "shares": 200, "error": "x"}],
          "core": [{"ticker": "1545.T", "name": "纳斯达克 100（1545）", "units": 100, "why": "闲置资金规则"}]}
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"holding_view": hv, "charts": charts}), encoding="utf-8")
    html = panel.render("paper", "t" * 40, AT)
    assert "data-act='adj'" in html and "data-px='1000'" in html and "单只上限 34%" in html and "调整…</button>" in html
    assert "data-t='6758.T' data-kind='stock'" in html and "data-t='1545.T' data-kind='core'" in html
    assert "现在没拿" in html and "data-t='1482.T' data-kind='core'" in html and html.count("data-act='range'") == 4
    assert "</script><b>x" not in html                         # 名字里的标签被转义（JSON 里 </ → <\/；HTML 里 escape）
    raw = html.split("<script type='application/json' id='chart-data'>", 1)[1].split("</script>", 1)[0]
    assert json.loads(raw)["1482.T"]["name"].endswith("<b>x") and '"addWhen": "10/07（下一个交易日）"' in html
    assert "加仓 → <b>10/07（下一个交易日） 开盘</b>" in html
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"holding_view": hv}), encoding="utf-8")
    html = panel.render("paper", "t" * 40, AT)                  # 还没有走势数据：占位文字、没有期间切换
    assert "走势图在执行器下一次运行之后显示" in html and "data-act='range'" not in html


def test_page_script_is_valid_javascript(tmp_path):
    """页面里的脚本整段能被 JavaScript 解析（Python 字符串里的 \\n 转义写错会让整页的按钮和走势图都不工作）。没有 node 就跳过。"""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    _book()
    for mode in ("local", "remote"):
        html = panel.render("paper", "t" * 40, AT, mode=mode, device={"name": "x"}, phone={"port": 8766, "url": None, "devices": []})
        f = tmp_path / f"{mode}.js"
        f.write_text(html.split("<script>")[-1].split("</script>")[0], encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[-500:]
