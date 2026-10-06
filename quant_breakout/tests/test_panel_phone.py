"""手机上操作（qbreak/panel_phone.py + panel.py 的手机端口）：没配对什么都看不到、配对码只在本机生成、cookie + CSRF、
取消配对、HALT 只能建、Tailscale 只用 Serve（假的 tailscale 命令）、手机版面。"""
import datetime as dt
import http.client
import json
import os
import re
import stat
import sys
import threading
from http.server import ThreadingHTTPServer

import pytest

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak import panel_phone as PP
from qbreak.calendar_jp import JST

TS_HOST = "qbreak-mac.tail1234.ts.net"
AT = dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST)


def _book(tag="paper"):
    st = {"last_date": "2026-10-05", "cash_jpy": 500_000.0, "history": [["2026-10-05", 1_000_000.0, 0, 0, 150]],
          "pos": {"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0}},
          "pending_exit": {}, "core_units": {"1545.T": 100}}
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps({"state": st, "orders": []}), encoding="utf-8")


@pytest.fixture()
def servers():
    tok = panel.token()
    lsrv = ThreadingHTTPServer(("127.0.0.1", 0), panel.make_handler(1, tok))
    psrv = ThreadingHTTPServer(("127.0.0.1", 0), panel.make_phone_handler(1))
    lp, pp = lsrv.server_address[1], psrv.server_address[1]
    lsrv.RequestHandlerClass = panel.make_handler(lp, tok, clock=lambda: AT, phone_port=pp)
    psrv.RequestHandlerClass = panel.make_phone_handler(pp, clock=lambda: AT)
    for s in (lsrv, psrv):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    yield lp, pp, tok
    for s in (lsrv, psrv):
        s.shutdown()
        s.server_close()


def _req(port, method, path, body=None, headers=None, host=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": host or f"127.0.0.1:{port}"}
    h.update(headers or {})
    data = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    raw = r.read()
    out = r.status, raw, dict(r.getheaders())
    c.close()
    return out


def _phone(port, method, path, body=None, cookie=None, csrf=None, origin=f"https://{TS_HOST}", host=TS_HOST):
    h = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)"}
    if origin:
        h["Origin"] = origin
    if cookie:
        h["Cookie"] = f"other=1; qbd={cookie}"
    if csrf:
        h["X-Qbreak-Csrf"] = csrf
    code, raw, hd = _req(port, method, path, body, h, host=host)
    return code, raw.decode("utf-8", "replace"), hd


def _local_post(lp, tok, path, body):
    h = {"X-Qbreak-Token": tok, "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{lp}"}
    code, raw, _ = _req(lp, "POST", path, body, h)
    return code, json.loads(raw.decode("utf-8"))


def test_pairing_code_rules():
    code, exp = PP.new_code(now=1000.0)
    assert len(code) == 8 and set(code) <= set(PP.CODE_ALPHABET) and exp == 1000.0 + 600
    raw = (paths.home() / PP.DEVICES_FILE).read_text(encoding="utf-8")
    assert code not in raw and oct(os.stat(paths.home() / PP.DEVICES_FILE).st_mode & 0o777) == "0o600"   # 只存摘要
    for i in range(4):
        ok, msg, ck = PP.pair("AAAA-AAAA", now=1001.0)
        assert not ok and ck is None and f"还能试 {4 - i} 次" in msg
    ok, msg, _ = PP.pair("BBBB-BBBB", now=1001.0)
    assert not ok and "作废" in msg
    assert not PP.pair(code, now=1002.0)[0]                    # 输错 5 次：对的也不行了
    code, _ = PP.new_code(now=2000.0)
    assert not PP.pair(code, now=2000.0 + 601)[0]              # 过期
    code, _ = PP.new_code(now=3000.0)
    ok, msg, ck = PP.pair(code.lower()[:4] + " - " + code.lower()[4:], "我的 <b>iPhone</b>", now=3001.0)
    assert ok and re.fullmatch(r"[0-9a-f]{12}\.[A-Za-z0-9_\-]{40,}", ck)
    assert not PP.pair(code, now=3002.0)[0]                    # 只能用一次
    assert PP.devices()[0]["name"] == "我的 biPhone/b"                          # 尖括号等去掉
    for _ in range(PP.MAX_DEVICES - 1):
        c, _ = PP.new_code(now=4000.0)
        assert PP.pair(c, now=4000.0)[0]
    c, _ = PP.new_code(now=5000.0)
    ok, msg, _ = PP.pair(c, now=5000.0)
    assert not ok and "已经配对了 5 台" in msg and PP.pending(now=5000.0) is not None    # 配对码没被用掉


def test_device_cookie_csrf_and_revoke():
    code, _ = PP.new_code()
    ok, _, ck = PP.pair(code, "", "Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X)")
    did = ck.split(".")[0]
    dev = PP.device_for(f"a=b; qbd={ck}; c=d")
    assert dev["id"] == did and dev["name"] == "iPad"
    for bad in (None, "", "qbd=", f"qbd={did}.wrong-token-wrong-token-xx", f"qbd={ck}x", "qbd=../../etc.passwd", f"xqbd={ck}"):
        assert PP.device_for(bad) is None
    t = PP.csrf(did)
    assert len(t) == 40 and PP.csrf_ok(did, t) and not PP.csrf_ok(did, "") and not PP.csrf_ok(did, t[:-1] + "0")
    assert PP.csrf("000000000000") != t
    assert PP.revoke(did) and PP.device_for(f"qbd={ck}") is None and not PP.revoke(did)
    code, _ = PP.new_code()
    _, _, ck2 = PP.pair(code)
    t2 = PP.csrf(ck2.split(".")[0])
    assert PP.revoke_all() == 1 and PP.device_for(f"qbd={ck2}") is None and PP.pending() is None
    assert PP.csrf(ck2.split(".")[0]) != t2                    # secret 换了：旧的 CSRF 令牌全部失效
    assert "HttpOnly" in PP.cookie_set("x") and "Secure" in PP.cookie_set("x") and "SameSite=Strict" in PP.cookie_set("x")
    assert "Max-Age=0" in PP.cookie_clear()


def test_halt_is_create_only_and_takes_over_a_drill():
    ok, msg = PP.create_halt("出差", "手机 iPhone", AT)
    h = paths.halt_file()
    assert ok and h.exists() and "已建 HALT" in msg and "立花网站" in msg and "恢复只在 Mac 上" in msg
    first = h.read_text(encoding="utf-8")
    assert first.startswith("停止下单（手机 iPhone）2026-10-06 08:00 JST：出差")
    ok, msg = PP.create_halt("again", "x", AT)
    assert ok and "已经生效" in msg and h.read_text(encoding="utf-8") == first     # 不覆盖
    h.write_text("HALT 演练 2026-10-06 09:30 JST（run.py live-u --halt-drill 建的，演练结束自动删除）\n", encoding="utf-8")
    ok, msg = PP.create_halt("", "Mac 操作面板", AT)
    assert ok and not h.read_text(encoding="utf-8").startswith("HALT 演练")         # 演练结束时不会被删
    assert PP.halt_text().startswith("停止下单（Mac 操作面板）")
    src = (paths.PROJECT_ROOT / "qbreak" / "panel_phone.py").read_text(encoding="utf-8")
    src += (paths.PROJECT_ROOT / "qbreak" / "panel.py").read_text(encoding="utf-8")
    assert "unlink" not in src.split("def create_halt")[1].split("def halt_text")[0]
    assert "halt_file().unlink" not in src and "os.remove" not in src             # 没有删除 HALT 的路


def test_phone_port_needs_pairing_and_csrf(servers):
    lp, pp, tok = servers
    _book()
    code, html, hd = _phone(pp, "GET", "/")
    assert code == 200 and "qbreak 手机配对" in html and "7203" not in html and "¥" not in html and tok not in html
    assert "frame-ancestors 'none'" in hd.get("Content-Security-Policy", "")
    assert _phone(pp, "GET", "/", host="evil.example")[0] == 421                     # DNS rebinding
    assert _phone(pp, "GET", "/", host=f"127.0.0.1:{pp}")[0] == 200
    body = {"book": "paper", "kind": "sell", "ticker": "7203", "block_days": 20}
    assert _phone(pp, "POST", "/api/request", body)[0] == 401
    assert _phone(pp, "POST", "/api/halt", {"reason": "x"})[0] == 401 and not paths.halt_file().exists()
    for p_ in ("/api/pair/new", "/api/device/revoke"):                                # 只在本机
        assert _phone(pp, "POST", p_, {})[0] == 404
    assert not MO.read_all("paper")
    # 本机生成配对码（手机地址已打开 → 有二维码与地址）
    (paths.home() / PP.PHONE_FILE).write_text(json.dumps({"url": f"https://{TS_HOST}/"}), encoding="utf-8")
    c, j = _local_post(lp, tok, "/api/pair/new", {})
    assert c == 200 and re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", j["code"]) and j["url"] == f"https://{TS_HOST}/"
    if j.get("qr"):
        assert j["qr"].startswith("data:image/svg+xml;base64,")
    assert _req(lp, "POST", "/api/pair/new", {}, {"Content-Type": "application/json"})[0] == 403    # 没有面板令牌
    code, txt, _ = _phone(pp, "GET", "/pair?c=" + j["code"].replace("-", "").lower())
    assert code == 200 and j["code"] in txt                                         # 扫码打开：配对码已经填好
    code, txt, _ = _phone(pp, "POST", "/api/pair", {"code": "ZZZZ-ZZZZ"})
    assert code == 400 and "还能试 4 次" in txt
    code, txt, _ = _phone(pp, "POST", "/api/pair", {"code": j["code"]}, origin="https://evil.example")
    assert code == 403
    code, txt, hd = _phone(pp, "POST", "/api/pair", {"code": j["code"], "name": "iPhone 16"})
    sc = hd.get("Set-Cookie", "")
    assert code == 200 and "HttpOnly" in sc and "Secure" in sc and "SameSite=Strict" in sc and "Max-Age=15552000" in sc
    ck = re.match(r"qbd=([^;]+)", sc).group(1)
    did = ck.split(".")[0]
    # 配对之后：看得到账本、带的是这台设备的 CSRF 令牌（不是本机的面板令牌）
    code, html, _ = _phone(pp, "GET", "/?book=paper", cookie=ck)
    csrf = re.search(r'"h": "X-Qbreak-Csrf", "v": "([0-9a-f]{40})"', html).group(1)
    assert "7203.T" in html and "卖出全部" in html and csrf == PP.csrf(did) and tok not in html
    assert "退出这台设备" in html and "data-act='pair-new'" not in html and "id='phone'" not in html and "iPhone 16" in html
    assert _phone(pp, "GET", "/pair?c=AAAA", cookie=ck)[0] == 303
    assert _phone(pp, "POST", "/api/request", body, cookie=ck)[0] == 403                     # 没有 CSRF
    assert _phone(pp, "POST", "/api/request", body, cookie=ck, csrf="0" * 40)[0] == 403
    assert _phone(pp, "POST", "/api/request", body, cookie=ck, csrf=csrf, origin="https://evil.example")[0] == 403
    assert _phone(pp, "POST", "/api/request", body, cookie=ck, csrf=csrf, host="evil.example")[0] == 421
    assert not MO.read_all("paper")
    code, txt, _ = _phone(pp, "POST", "/api/request", body, cookie=ck, csrf=csrf)
    assert code == 200 and "10/06（今天）开盘" in json.loads(txt)["msg"]
    r = MO.read_all("paper")
    assert len(r) == 1 and r[0]["source"] == "phone" and r[0]["ticker"] == "7203.T"
    code, txt, _ = _phone(pp, "POST", "/api/halt", {"reason": "在外面"}, cookie=ck, csrf=csrf)
    assert code == 200 and paths.halt_file().read_text(encoding="utf-8").startswith("停止下单（手机 iPhone 16）")
    # Mac 上能看到这台设备、能取消；取消之后手机又只能看到配对页
    code, raw, _ = _req(lp, "GET", "/?book=paper")
    page = raw.decode("utf-8")
    assert "iPhone 16" in page and "data-act='pair-new'" in page and f"https://{TS_HOST}/" in page
    assert "HALT 生效中" in page and "停止下单（HALT）</button>" not in page
    c, j2 = _local_post(lp, tok, "/api/device/revoke", {"id": did})
    assert c == 200 and j2["ok"]
    assert "qbreak 手机配对" in _phone(pp, "GET", "/", cookie=ck)[1]
    assert _phone(pp, "POST", "/api/request", body, cookie=ck, csrf=csrf)[0] == 401


def test_unpair_static_files_and_local_halt(servers):
    lp, pp, tok = servers
    _book()
    code, _ = PP.new_code()
    ok, _, ck = PP.pair(code, "iPhone")
    csrf = PP.csrf(ck.split(".")[0])
    code, txt, hd = _phone(pp, "POST", "/api/unpair", {}, cookie=ck, csrf=csrf)
    assert code == 200 and "Max-Age=0" in hd.get("Set-Cookie", "") and not PP.devices()
    for port, host in ((pp, TS_HOST), (lp, None)):
        c, raw, hd = _req(port, "GET", "/apple-touch-icon.png", host=host)
        assert c == 200 and hd["Content-Type"] == "image/png" and raw[:8] == b"\x89PNG\r\n\x1a\n" and raw[16:24] == bytes.fromhex("000000b4000000b4")
        c, raw, hd = _req(port, "GET", "/manifest.webmanifest", host=host)
        assert c == 200 and json.loads(raw)["display"] == "standalone"
    c, j = _local_post(lp, tok, "/api/halt", {"reason": "测试"})
    assert c == 200 and paths.halt_file().read_text(encoding="utf-8").startswith("停止下单（Mac 操作面板）")


def test_render_mobile_layout_local_vs_remote():
    _book()
    html = panel.render("paper", "t" * 40, AT, phone={"port": 8766, "url": None, "devices": []})
    assert "viewport-fit=cover" in html and "rel='manifest'" in html and "apple-touch-icon" in html
    assert "<dialog id='dlg-sell'>" in html and "<dialog id='dlg-trim'>" in html and "data-act='sell'" in html
    assert "data-px='2600'" in html and "data-shares='200'" in html and "停止下单（HALT）</button>" in html
    assert "id='phone'" in html and "打开手机操作" in html and "data-act='unpair'" not in html
    assert '"X-Qbreak-Token", "v": "' + "t" * 40 in html
    remote = panel.render("paper", "c" * 40, AT, mode="remote", device={"name": "iPhone", "created": "2026-10-06T08:00:00+09:00"})
    assert "id='phone'" not in remote and "data-act='unpair'" in remote and '"X-Qbreak-Csrf", "v": "' + "c" * 40 in remote
    assert str(paths.home()) not in html and str(paths.home()) not in remote                  # 不在页面上露出本机路径
    paths.halt_file().write_text("停止下单（手机 iPhone）2026-10-06 08:00 JST：x\n", encoding="utf-8")
    remote = panel.render("paper", "c" * 40, AT, mode="remote", device={"name": "iPhone"})
    assert "HALT 生效中" in remote and "停止下单（HALT）</button>" not in remote and "恢复只在 Mac 上" in remote
    pg = panel.pair_page("<script>abcd2345")
    assert "<script>abcd" not in pg and "value='SCRI'" not in pg and "7203" not in pg
    assert "value='ABCD-2345'" in panel.pair_page("abcd2345")


def _fake_ts(tmp_path, monkeypatch, status, serve=None):
    st = tmp_path / "ts_state.json"
    st.write_text(json.dumps({"status": status, "serve": serve or {}}), encoding="utf-8")
    logf = tmp_path / "ts_calls.log"
    logf.write_text("", encoding="utf-8")
    exe = tmp_path / "tailscale"
    exe.write_text(f"#!{sys.executable}\n" + r'''
import json, os, sys
p = os.environ["FAKE_TS_STATE"]
st = json.load(open(p))
a = sys.argv[1:]
open(os.environ["FAKE_TS_LOG"], "a").write(" ".join(a) + "\n")
if a[:2] == ["status", "--json"]:
    print(json.dumps(st["status"])); sys.exit(0)
if a[:3] == ["serve", "status", "--json"]:
    print(json.dumps(st.get("serve") or {})); sys.exit(0)
port = next((x.split("=", 1)[1] for x in a if x.startswith("--https=")), "443")
host = st["status"]["Self"]["DNSName"].rstrip(".")
if a and a[0] == "serve" and a[-1] == "off":
    st.get("serve", {}).get("Web", {}).pop(host + ":" + port, None)
    json.dump(st, open(p, "w")); print("ok"); sys.exit(0)
if a and a[0] == "serve" and "--bg" in a:
    st.setdefault("serve", {}).setdefault("Web", {})[host + ":" + port] = {"Handlers": {"/": {"Proxy": a[-1]}}}
    json.dump(st, open(p, "w")); print("Available within your tailnet: https://" + host + "/"); sys.exit(0)
sys.exit(1)
''', encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("QBREAK_TAILSCALE", str(exe))
    monkeypatch.setenv("FAKE_TS_STATE", str(st))
    monkeypatch.setenv("FAKE_TS_LOG", str(logf))
    return st, logf


def _status(magic=True, https=True, state="Running"):
    return {"BackendState": state, "Version": "1.90.0", "Self": {"DNSName": TS_HOST + "."},
            "CurrentTailnet": {"MagicDNSEnabled": magic}, "CertDomains": [TS_HOST] if https else None}


def _cli(action, **kw):
    lines = []
    rc = PP.cli(action, out=lines.append, open_panel=False, **kw)
    return rc, "\n".join(lines)


def test_panel_phone_cli_uses_serve_only(tmp_path, monkeypatch, capsys):
    import run
    monkeypatch.setenv("QBREAK_TAILSCALE", str(tmp_path / "nope"))
    assert _cli("on")[0] == 2 and "没找到 tailscale" in _cli("on")[1]
    assert _cli("status")[0] == 0
    st, logf = _fake_ts(tmp_path, monkeypatch, _status(magic=False))
    rc, out = _cli("on")
    assert rc == 2 and "MagicDNS" in out and "Enable HTTPS" in out
    st, logf = _fake_ts(tmp_path, monkeypatch, _status())
    code, _ = PP.new_code()                                   # 有一个配对码在等：命令的输出里绝不出现
    rc, out = _cli("on")
    assert rc == 3 and "证书透明度日志" in out and "qbreak-mac" in out and "--yes" in out
    assert "serve --bg" not in logf.read_text(encoding="utf-8")                      # 没确认之前不打开
    rc, out = _cli("on", yes=True)
    calls = logf.read_text(encoding="utf-8")
    assert rc == 0 and "serve --bg --https=443 http://127.0.0.1:8766" in calls and "funnel" not in calls
    assert f"https://{TS_HOST}/" in out and PP.phone_url() == f"https://{TS_HOST}/"
    assert code not in out and PP.fmt_code(code) not in out and "有一个配对码在等" in out
    n = calls.count("serve --bg")
    assert _cli("on")[0] == 0 and logf.read_text(encoding="utf-8").count("serve --bg") == n    # 已经打开：不重复
    assert run.main(["panel-phone", "status"]) == 0
    out = capsys.readouterr().out
    assert f"手机地址：https://{TS_HOST}/" in out and code not in out
    assert run.main(["panel-phone", "off"]) == 0
    assert "serve --https=443 off" in logf.read_text(encoding="utf-8") and PP.phone_url() is None
    # Funnel 开着 / 443 被别的服务占着 → 拒绝、不覆盖
    st, logf = _fake_ts(tmp_path, monkeypatch, _status(), {"AllowFunnel": {f"{TS_HOST}:443": True}})
    rc, out = _cli("on", yes=True)
    assert rc == 2 and "Funnel" in out and "serve --bg" not in logf.read_text(encoding="utf-8")
    other = {"Web": {f"{TS_HOST}:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:3000"}}}}}
    st, logf = _fake_ts(tmp_path, monkeypatch, _status(), other)
    rc, out = _cli("on", yes=True)
    assert rc == 2 and "--https-port 8443" in out and "serve --bg" not in logf.read_text(encoding="utf-8")
    rc, out = _cli("on", yes=True, https_port=8443)
    assert rc == 0 and PP.phone_url() == f"https://{TS_HOST}:8443/"
    assert _cli("off", https_port=443)[0] == 0                                   # 记下的是 8443：关的也是 8443
    assert "serve --https=8443 off" in logf.read_text(encoding="utf-8")
    assert json.loads(st.read_text(encoding="utf-8"))["serve"]["Web"][f"{TS_HOST}:443"]["Handlers"]["/"]["Proxy"] == "http://127.0.0.1:3000"
    ok, _, _ = PP.pair(PP.new_code()[0])
    assert ok and run.main(["panel-phone", "forget"]) == 0 and not PP.devices()


def test_code_watcher_exits_on_update(monkeypatch):
    seq = iter([{"panel.py": 1.0}, {"panel.py": 1.0}, {"panel.py": 2.0}])
    monkeypatch.setattr(panel, "_mtimes", lambda: next(seq))
    calls = []

    class Srv:
        def shutdown(self):
            calls.append(1)
    stop = threading.Event()
    panel._watch_code(stop, Srv(), every=0.01)
    assert calls == [1]
