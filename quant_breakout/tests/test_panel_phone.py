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
    wrong = t[:-1] + ("1" if t[-1] == "0" else "0")                                  # 一定和真的不一样（原来 1/16 的概率相同）
    assert len(t) == 40 and PP.csrf_ok(did, t) and not PP.csrf_ok(did, "") and not PP.csrf_ok(did, wrong)
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
    assert code == 200 and "今天 09:00 开盘卖出" in json.loads(txt)["msg"]
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


def test_phone_chart_endpoint_needs_a_paired_device(servers):
    lp, pp, tok = servers
    _book()
    (paths.out_dir() / "charts_paper.json").write_text(json.dumps({"asof": "2026-10-05", "tickers": {"7203.T": {"kind": "stock"}}}),
                                                       encoding="utf-8")
    code, txt, _ = _phone(pp, "GET", "/api/chart?book=paper&t=7203.T")
    assert code == 401 and "7203" not in txt                                       # 没配对：K 线也拿不到
    assert _phone(pp, "GET", "/api/chart?book=paper&t=7203.T", host="evil.example")[0] == 421
    _, j = _local_post(lp, tok, "/api/pair/new", {})
    _, _, hd = _phone(pp, "POST", "/api/pair", {"code": j["code"], "name": "iPhone"})
    ck = re.match(r"qbd=([^;]+)", hd.get("Set-Cookie", "")).group(1)
    code, txt, _ = _phone(pp, "GET", "/api/chart?book=paper&t=7203.T", cookie=ck)
    assert code == 200 and json.loads(txt)["data"] == {"kind": "stock"}
    assert _phone(pp, "GET", "/api/chart?book=paper&t=6758.T", cookie=ck)[0] == 404


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
    assert "<dialog id='dlg-sell'>" in html and "<dialog id='dlg-adj'>" in html and "data-act='sell'" in html
    assert "data-act='adj'" in html and "data-u='yen'" in html and "data-u='pct'" in html
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
web = st.setdefault("serve", {}).setdefault("Web", {})
if a and a[0] == "serve" and a[-1] == "off":
    if "--set-path=/" in a:
        web.get(host + ":" + port, {}).get("Handlers", {}).pop("/", None)
    else:
        web.pop(host + ":" + port, None)
    json.dump(st, open(p, "w")); print("ok"); sys.exit(0)
if a and a[0] == "serve" and "--bg" in a:
    if os.environ.get("FAKE_TS_NO_OVERWRITE") and (web.get(host + ":" + port) or {}).get("Handlers", {}).get("/"):
        print("error: mount point / is already in use: " + a[-1], file=sys.stderr); sys.exit(1)   # 老版本：不覆盖（报错里带目标）
    web.setdefault(host + ":" + port, {"Handlers": {}}).setdefault("Handlers", {})["/"] = {"Proxy": a[-1]}
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
    rc = PP.cli(action, out=lines.append, open_panel=False, **{"wait_s": 0, **kw})
    return rc, "\n".join(lines)


def test_panel_phone_cli_uses_serve_only(tmp_path, monkeypatch, capsys):
    import run
    monkeypatch.setenv("QBREAK_TAILSCALE", str(tmp_path / "nope"))
    assert _cli("on")[0] == 2 and "没找到 tailscale" in _cli("on")[1]
    assert _cli("status")[0] == 0
    st, logf = _fake_ts(tmp_path, monkeypatch, _status(magic=False))
    rc, out = _cli("on")
    assert rc == 4 and "MagicDNS" in out and "Enable HTTPS" in out and PP.ADMIN_DNS in out    # 要先打开 HTTPS（Mac 上会打开管理页）
    st, logf = _fake_ts(tmp_path, monkeypatch, _status())
    code, _ = PP.new_code()                                   # 有一个配对码在等：命令的输出里绝不出现
    rc, out = _cli("on")
    assert rc == 3 and "证书透明度日志" in out and "mac_setup.sh --phone qbreak-mac" in out
    assert "serve --bg" not in logf.read_text(encoding="utf-8")                      # 没确认之前不打开
    rc, out = _cli("on", confirm_name="node")                                       # 确认过的是别的名字 → 不打开
    assert rc == 3 and "不是确认过的「node」" in out and "serve --bg" not in logf.read_text(encoding="utf-8")
    rc, out = _cli("on", confirm_name="QBREAK-MAC")                                 # 机器名正好是确认过的那个（不分大小写）
    calls = logf.read_text(encoding="utf-8")
    g = PP.gate()                                                                   # 路径密钥：Serve 的目标带着它，终端里不显示
    assert rc == 0 and re.fullmatch(r"[0-9a-f]{32}", g) and f"serve --bg --https=443 http://127.0.0.1:8766/{g}" in calls
    assert "funnel" not in calls and g not in out
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


def test_phone_on_waits_for_the_restarted_panel(tmp_path, monkeypatch):
    """mac_setup.sh 刚重启面板：等手机端口起来再打开 Serve（等不到也照样打开、说明怎么重启面板）。"""
    import socket
    _fake_ts(tmp_path, monkeypatch, _status())
    with socket.socket() as s0:
        s0.bind(("127.0.0.1", 0))
        port = s0.getsockname()[1]
    srv = socket.socket()

    def late():
        srv.bind(("127.0.0.1", port))
        srv.listen(1)
    t = threading.Timer(1.2, late)
    t.start()
    try:
        rc, out = _cli("on", yes=True, port=port, wait_s=8)
    finally:
        t.join()
        srv.close()
    assert rc == 0 and "没在监听" not in out and f"Serve → 127.0.0.1:{port}，带路径密钥" in out and PP.gate() not in out
    PP.cli("off", out=lambda *_: None)
    rc, out = _cli("on", yes=True, port=port, wait_s=0)                            # 面板没起来：照样打开，告诉怎么重启
    assert rc == 0 and "没在监听手机端口" in out


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


# ───────────────────────── 按 Tailscale 账户登录（2026-10-07）＋ 15 秒超时 ─────────────────────────
OWNER = "owner@example.com"
GATE = "0123456789abcdef0123456789abcdef"                     # 测试用的路径密钥（真的由 panel-phone on 随机生成）


def _ident_setup(pp, owner=OWNER, https_port=443, gate=GATE, identity=True):
    """模拟 panel-phone on 之后：记下手机地址、路径密钥、这台 Mac 登录的账户、打开按账户登录（0600）。"""
    url = f"https://{TS_HOST}/" if https_port == 443 else f"https://{TS_HOST}:{https_port}/"
    PP._save_phone(url, pp, https_port, owner, gate=gate, identity=identity)


def _ts(pp, method, path, body=None, login=OWNER, csrf=None, host=TS_HOST, extra=None, origin=f"https://{TS_HOST}", gated=True):
    """Tailscale Serve 转过来的样子：路径前面加了路径密钥、Host = 手机地址、带 Tailscale-User-Login（Serve 填的）。
    gated=False = 不经 Serve、本机的程序直接连 127.0.0.1:8766（自己写 Host 和账户头）。"""
    h = {"Content-Type": "application/json", "X-Forwarded-Host": host, "X-Forwarded-Proto": "https", "X-Forwarded-For": "100.101.102.103"}
    if origin:
        h["Origin"] = origin
    if login is not None:
        h["Tailscale-User-Login"] = login
    if csrf:
        h["X-Qbreak-Csrf"] = csrf
    h.update(extra or {})
    code, raw, hd = _req(pp, method, (f"/{GATE}" + path) if gated else path, body, h, host=host)
    return code, raw.decode("utf-8", "replace"), hd


def _raw(port, lines: list[str]) -> tuple[int, str]:
    """重复的头（http.client 的 dict 写不出来）：自己拼请求。"""
    import socket
    with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
        s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("utf-8"))
        data = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
    head, _, body = data.partition(b"\r\n\r\n")
    return int(head.split()[1]), body.decode("utf-8", "replace")


def test_identity_helpers():
    assert PP.decode_login(OWNER) == OWNER and PP.decode_login(" owner@example.com ") == OWNER
    assert PP.decode_login("=?utf-8?q?=E5=BC=A0=E4=B8=89@example.com?=") == "张三@example.com"        # Serve 的 RFC 2047 Q 编码
    assert PP.decode_login("=?utf-8?q?=E5=BC=A0?= =?utf-8?q?=E4=B8=89@example.com?=") == "张三@example.com"   # 长的分段（段间一个空格）
    for bad in (None, "", "tagged-devices", "a b@c", "a@b@c", "<x>@y", "x" * 600, "=?utf-8?q?=FF=FE?=", "a\x01b@c",
                "=?utf-8?b?b3duZXJAZXhhbXBsZS5jb20=?=",            # B 编码：Serve 不用
                "=?utf-8?q?owner@example.com?=", "=?utf-8?q?owner=40example.com?=",   # 纯 ASCII 被编码：Serve 不会这样写
                "=?utf-8@?q?owner=40example.com?=", "=?UTF-8?Q?=E5=BC=A0=E4=B8=89@example.com?=",
                "x=?utf-8?q?=E5=BC=A0?=@example.com", "=?utf-8?q?=E5=BC=A0?=@example.com", "=?utf-8?q?a?b=E5=BC=A0@x?=",
                "ownér@example.com", "=?utf-8?q?=E5=BC=A0_x@example.com?="):
        assert PP.decode_login(bad) is None, bad
    assert PP.mask_login("alice@example.com") == "al***@e***.com" and PP.mask_login("bob@github") == "b***@g***"
    assert PP.mask_login("ab@x.co.jp") == "a***@x***.jp" and PP.mask_login("") == "—" and PP.mask_login("nouser") == "—"
    assert OWNER not in PP.mask_login(OWNER) and "owner" not in PP.mask_login(OWNER)
    for a, want in (("127.0.0.1", True), ("127.0.0.2", True), ("::1", True), ("100.64.0.5", False), ("192.168.1.2", False),
                    ("0.0.0.0", False), ("", False), (None, False), ("localhost", False)):
        assert PP.trusted_peer(a) is want, a
    assert PP.hostport("Mac.TS.net:443") == "mac.ts.net" and PP.hostport("mac.ts.net:8443") == "mac.ts.net:8443"
    # 路径密钥：Serve 转过来的是「/<路径密钥>/原来的路径」
    assert PP.gate() is None and PP.split_gate(f"/{GATE}/api/chart") == (False, f"/{GATE}/api/chart")   # 还没记下 → 不认
    _ident_setup(8766)
    assert PP.gate() == GATE
    assert PP.split_gate(f"/{GATE}/api/chart?t=7203.T") == (True, "/api/chart?t=7203.T")
    assert PP.split_gate(f"/{GATE}/") == (True, "/") and PP.split_gate(f"/{GATE}") == (True, "/")
    assert PP.split_gate(f"/{GATE}?book=paper") == (True, "/?book=paper")
    for p in ("/", "/api/chart", f"/{GATE}x/", f"/{GATE[:-1]}/", f"/{GATE.upper()}/", f"//{GATE}/", f"http://h/{GATE}/", "", None):
        assert PP.split_gate(p) == (False, str(p or "")), p


def test_identity_for_rules():
    """identity_for 的每一条：本机回环、路径密钥、不是 Funnel、Host 对、头正好一个、账户完全相同、明确打开着、记下了账户。"""
    import http.client

    def H(**kv):
        m = http.client.HTTPMessage()
        for k, v in kv.items():
            for x in (v if isinstance(v, list) else [v]):
                m[k.replace("_", "-")] = x
        return m

    def I(h, peer="127.0.0.1", path=f"/{GATE}/"):
        return PP.identity_for(h, peer, path)
    good = dict(Host=TS_HOST, Tailscale_User_Login=OWNER)
    assert I(H(**good)) is None                                                    # 还没 panel-phone on（没记下账户）
    _ident_setup(8766)
    dev = I(H(**good))
    assert dev and dev["kind"] == "ts" and dev["login"] == "ow***@e***.com" and OWNER not in json.dumps(dev, ensure_ascii=False)
    assert re.fullmatch(r"ts-[0-9a-f]{10}", dev["id"]) and PP.csrf_ok(dev["id"], PP.csrf(dev["id"]))
    assert I(H(**good), path=f"/{GATE}/api/chart?t=1") and I(H(**good), path=f"/{GATE}")
    for p in ("/", "/api/chart", f"/{GATE}x", "/" + "f" * 32 + "/", None):                       # 没经 Serve（没有 / 不对的路径密钥）
        assert I(H(**good), path=p) is None, p
    assert I(H(**good), "::1") is not None
    assert I(H(**good), "100.101.102.103") is None                                 # 不是本机连过来的
    assert I(H(**good, Tailscale_Funnel_Request="?1")) is None
    assert I(H(Host=TS_HOST, Tailscale_User_Login=[OWNER, OWNER])) is None         # 头不止一个
    assert I(H(Host=TS_HOST)) is None
    assert I(H(Host=TS_HOST, Tailscale_User_Login="other@example.com")) is None
    assert I(H(Host=TS_HOST, Tailscale_User_Login="OWNER@example.com")) is None    # 完全相同才算
    assert I(H(Host=TS_HOST, Tailscale_User_Login="=?utf-8?q?owner=40example.com?=")) is None   # Serve 不会这样写
    assert I(H(Host="evil.ts.net", Tailscale_User_Login=OWNER)) is None
    assert I(H(Host="127.0.0.1:8766", Tailscale_User_Login=OWNER, X_Forwarded_Host=TS_HOST)) is None
    assert I(H(Host=f"{TS_HOST}:443", Tailscale_User_Login=OWNER)) is not None
    PP.set_identity(False)
    assert I(H(**good)) is None and not PP.identity_state()["on"] and PP.identity_state()["off"]
    assert json.loads((paths.home() / PP.PHONE_FILE).read_text(encoding="utf-8"))["identity"] is False
    (paths.home() / PP.DEVICES_FILE).unlink()                                      # 配对的文件没了：关掉的照样关着（不会自己打开）
    assert I(H(**good)) is None and not PP.identity_state()["on"]
    PP.set_identity(True)
    assert I(H(**good)) is not None and PP.identity_state() == {"on": True, "off": False, "owner": "ow***@e***.com", "why": None}
    (paths.home() / PP.DEVICES_FILE).write_text("{坏了", encoding="utf-8")         # 配对的文件坏了：按 panel_phone.json（开着）
    assert I(H(**good)) is not None
    _ident_setup(8766, identity=False)                                             # 没明确打开 → 关
    assert I(H(**good)) is None
    d = json.loads((paths.home() / PP.PHONE_FILE).read_text(encoding="utf-8"))
    d.pop("identity")
    (paths.home() / PP.PHONE_FILE).write_text(json.dumps(d), encoding="utf-8")     # 旧文件（没有 identity）→ 关
    assert I(H(**good)) is None and "phone on" in PP.identity_state()["why"]
    _ident_setup(8766, gate=None)                                                  # 没有路径密钥（旧的设置）→ 关
    assert I(H(**good)) is None and "路径密钥" in PP.identity_state()["why"]
    _ident_setup(8766)
    (paths.home() / PP.PHONE_FILE).write_text("{坏了", encoding="utf-8")           # panel_phone.json 坏了 → 关（不会打开）
    assert I(H(**good)) is None and not PP.identity_state()["on"]
    _ident_setup(8766, https_port=8443)                                            # 8443：Host 要带端口
    assert I(H(**good)) is None
    assert I(H(Host=f"{TS_HOST}:8443", Tailscale_User_Login=OWNER)) is not None
    _ident_setup(8766, owner="张三@example.com")
    assert I(H(Host=TS_HOST, Tailscale_User_Login="=?utf-8?q?=E5=BC=A0=E4=B8=89@example.com?="))
    PP._save_phone(f"https://{TS_HOST}/", 8766, 443, None, "带 tag", gate=GATE, identity=True)   # 带 tag 的 Mac：没有账户 → 只能配对
    assert I(H(**good)) is None and PP.identity_state()["why"] == "带 tag"
    st = os.stat(paths.home() / PP.PHONE_FILE)
    assert stat.S_IMODE(st.st_mode) == 0o600                                       # 账户名、路径密钥只在 0600 的文件里
    _ident_setup(8766)
    assert I(H(**good)) is not None
    PP.revoke_all()                                                                # 全部取消 = 按账户登录也关（两个文件都关）
    assert I(H(**good)) is None and PP.identity_state()["off"]
    assert json.loads((paths.home() / PP.PHONE_FILE).read_text(encoding="utf-8"))["identity"] is False


def test_phone_identity_login_end_to_end(servers):
    lp, pp, tok = servers
    _book()
    _ident_setup(pp)
    code, html, hd = _ts(pp, "GET", "/?book=paper")
    assert code == 200 and "7203.T" in html and "已用 Tailscale 账户登录（ow***@e***.com；不用配对）" in html
    assert OWNER not in html and GATE not in html and "data-act='unpair'" not in html and "qbreak 手机配对" not in html and tok not in html
    csrf = re.search(r'"h": "X-Qbreak-Csrf", "v": "([0-9a-f]{40})"', html).group(1)
    assert '"remote": true' in html
    code, _, hd = _ts(pp, "GET", "/pair?c=AAAA")
    assert code == 303 and hd.get("Location") == "/"                               # 已经是你本人：不用配对页（跳转里没有路径密钥）
    (paths.out_dir() / "charts_paper.json").write_text(json.dumps({"asof": "2026-10-05", "tickers": {"7203.T": {"kind": "stock"}}}),
                                                       encoding="utf-8")
    code, txt, _ = _ts(pp, "GET", "/api/chart?book=paper&t=7203.T")
    assert code == 200 and json.loads(txt)["data"] == {"kind": "stock"}
    body = {"book": "paper", "kind": "sell", "ticker": "7203", "block_days": 20}
    # 本机的程序直接连 127.0.0.1:8766、自己写 Host 和账户头（不知道路径密钥）→ 不算你本人：拿不到数据和 CSRF 令牌、写不进去
    code, txt, _ = _ts(pp, "GET", "/?book=paper", gated=False)
    assert code == 200 and "qbreak 手机配对" in txt and "7203.T" not in txt and "X-Qbreak-Csrf" not in txt
    assert _ts(pp, "GET", "/api/chart?book=paper&t=7203.T", gated=False)[0] == 401
    assert _ts(pp, "POST", "/api/request", body, csrf=csrf, gated=False)[0] == 401
    assert _ts(pp, "POST", "/api/halt", {"reason": "x"}, csrf=csrf, gated=False)[0] == 401 and not paths.halt_file().exists()
    code, txt = _raw(pp, [f"GET /{'f' * 32}/?book=paper HTTP/1.1", f"Host: {TS_HOST}", f"Tailscale-User-Login: {OWNER}", "Connection: close"])
    assert "7203.T" not in txt                                                     # 猜的路径密钥 → 不算
    assert _ts(pp, "POST", "/api/request", body)[0] == 403                         # 写操作照旧要 CSRF
    assert _ts(pp, "POST", "/api/request", body, csrf="0" * 40)[0] == 403
    assert _ts(pp, "POST", "/api/request", body, csrf=csrf, origin="https://evil.example")[0] == 403
    assert _ts(pp, "POST", "/api/request", body, csrf=csrf, extra={"Sec-Fetch-Site": "cross-site"})[0] == 403
    assert _ts(pp, "POST", "/api/request", body, csrf=csrf, extra={"Sec-Fetch-Site": "same-site"})[0] == 403
    assert not MO.read_all("paper")
    code, txt, _ = _ts(pp, "POST", "/api/request", body, csrf=csrf, extra={"Sec-Fetch-Site": "same-origin"})
    assert code == 200 and json.loads(txt)["ok"]
    r = MO.read_all("paper")
    assert len(r) == 1 and r[0]["source"] == "phone" and r[0]["ticker"] == "7203.T"
    code, txt, _ = _ts(pp, "POST", "/api/unpair", {}, csrf=csrf)
    assert code == 400 and "phone identity off" in json.loads(txt)["msg"]
    code, txt, _ = _ts(pp, "POST", "/api/halt", {"reason": "在外面"}, csrf=csrf)
    halt = paths.halt_file().read_text(encoding="utf-8")
    assert code == 200 and halt.startswith("停止下单（手机 Tailscale 账户 ow***@e***.com）") and OWNER not in halt
    # 不是你本人 → 照旧只看到配对页 / 401
    for kw in ({"login": "other@example.com"}, {"login": None}, {"extra": {"Tailscale-Funnel-Request": "?1"}},
               {"host": "other-mac.tail1234.ts.net", "origin": "https://other-mac.tail1234.ts.net"}):
        code, txt, _ = _ts(pp, "GET", "/?book=paper", **kw)
        assert "7203.T" not in txt and (code == 403 if "extra" in kw else "qbreak 手机配对" in txt), kw
        assert _ts(pp, "GET", "/api/chart?book=paper&t=7203.T", **kw)[0] in (401, 403), kw
        assert _ts(pp, "POST", "/api/request", body, csrf=csrf, **kw)[0] in (401, 403), kw
    code, txt = _raw(pp, [f"GET /{GATE}/?book=paper HTTP/1.1", f"Host: {TS_HOST}", f"Tailscale-User-Login: {OWNER}",
                          f"Tailscale-User-Login: {OWNER}", "Connection: close"])
    assert code == 200 and "qbreak 手机配对" in txt and "7203.T" not in txt         # 头不止一个 → 不算
    code, txt, _ = _ts(pp, "GET", "/apple-touch-icon.png", extra={"Tailscale-Funnel-Request": "?1"})
    assert code == 403                                                             # Funnel 来的：什么都不给
    assert _ts(pp, "GET", "/apple-touch-icon.png")[0] == 200                       # 静态文件（带路径密钥）照常
    # 这台手机以前也配对过：按账户登录的页面上可以取消它的配对（cookie 一起清掉）
    c, j = _local_post(lp, tok, "/api/pair/new", {})
    _, _, hd = _phone(pp, "POST", "/api/pair", {"code": j["code"], "name": "iPhone"})
    ck = re.match(r"qbd=([^;]+)", hd.get("Set-Cookie", "")).group(1)
    code, html, _ = _ts(pp, "GET", "/?book=paper", extra={"Cookie": f"qbd={ck}"})
    assert code == 200 and "以前也配对过（iPhone）" in html and "data-act='unpair'" in html
    code, txt, hd = _ts(pp, "POST", "/api/unpair", {}, csrf=csrf, extra={"Cookie": f"qbd={ck}"})
    assert code == 200 and json.loads(txt)["ok"] and "Max-Age=0" in hd.get("Set-Cookie", "") and not PP.devices()
    # Mac 上关掉 → 只用配对；配对的设备照旧能用
    PP.set_identity(False)
    assert "qbreak 手机配对" in _ts(pp, "GET", "/")[1]
    assert _ts(pp, "POST", "/api/request", body, csrf=csrf)[0] == 401
    c, j = _local_post(lp, tok, "/api/pair/new", {})
    _, _, hd = _phone(pp, "POST", "/api/pair", {"code": j["code"], "name": "iPhone"})
    ck = re.match(r"qbd=([^;]+)", hd.get("Set-Cookie", "")).group(1)
    assert "7203.T" in _phone(pp, "GET", "/?book=paper", cookie=ck)[1]
    assert "7203.T" in _ts(pp, "GET", "/?book=paper", login=None, extra={"Cookie": f"qbd={ck}"})[1]   # 带路径密钥的配对设备也照常
    code, page, _ = _req(lp, "GET", "/?book=paper")
    page = page.decode("utf-8")
    assert "按 Tailscale 账户登录：关" in page and OWNER not in page and GATE not in page
    PP.set_identity(True)
    page = _req(lp, "GET", "/?book=paper")[1].decode("utf-8")
    assert "按 Tailscale 账户登录：<b>开</b>" in page and "ow***@e***.com" in page and OWNER not in page


def _status_user(login=OWNER, tags=None):
    st = _status()
    st["Self"]["UserID"] = 123
    if tags:
        st["Self"]["Tags"] = tags
    st["User"] = {"123": {"ID": 123, "LoginName": login, "DisplayName": "Owner"},
                  "456": {"ID": 456, "LoginName": "someone-else@example.com", "DisplayName": "X"}}
    return st


def test_panel_phone_cli_identity(tmp_path, monkeypatch, capsys):
    import run
    _fake_ts(tmp_path, monkeypatch, _status_user())
    rc, out = _cli("on", yes=True)
    saved = json.loads((paths.home() / PP.PHONE_FILE).read_text(encoding="utf-8"))
    assert rc == 0 and saved["owner"] == OWNER and saved["identity"] is True and re.fullmatch(r"[0-9a-f]{32}", saved["gate"])
    assert stat.S_IMODE(os.stat(paths.home() / PP.PHONE_FILE).st_mode) == 0o600
    assert "按 Tailscale 账户登录：开" in out and "ow***@e***.com" in out and "不用配对码" in out
    assert OWNER not in out and "someone-else" not in out and saved["gate"] not in out   # 不打印完整的账户名、别的账户、路径密钥
    rc, out = _cli("identity", value="off")
    assert rc == 0 and "已关掉" in out and "按 Tailscale 账户登录：关" in out and PP.identity_off()
    assert run.main(["panel-phone", "identity", "on"]) == 0 and not PP.identity_off()
    out = capsys.readouterr().out
    assert "按 Tailscale 账户登录：开" in out and "Remove" in out and PP.ADMIN_MACHINES in out      # 手机丢了：先在管理页删掉
    assert run.main(["panel-phone", "identity"]) == 0                              # 不带值 = 只看
    assert run.main(["panel-phone", "status"]) == 0
    out = capsys.readouterr().out
    assert "按 Tailscale 账户登录：开" in out and OWNER not in out and saved["gate"] not in out
    assert _cli("on", value="off")[0] == 2 and _cli("identity", value="maybe")[0] == 2
    with pytest.raises(SystemExit):
        run.main(["panel-phone", "identity", "maybe"])
    rc, out = _cli("forget")
    assert rc == 0 and "按 Tailscale 账户登录也关了" in out and "Remove" in out and PP.identity_off()
    rc, out = _cli("on", yes=True)                                                 # 再 on：记得「关」（不会自己打开）
    assert rc == 0 and "按 Tailscale 账户登录：关" in out and not PP.identity_state()["on"]
    assert PP.cli("off", out=lambda *_: None) == 0 and not (paths.home() / PP.PHONE_FILE).exists()
    rc, out = _cli("on", yes=True)                                                 # off 之后再 on：照样记得「关」
    assert rc == 0 and not PP.identity_state()["on"] and PP.identity_off()
    PP.set_identity(True)
    assert PP.identity_state()["on"]
    # 这台 Mac 的账户换了 → status 提醒（只打码）；带 tag 的 Mac：没有用户账户 → 只能配对
    _fake_ts(tmp_path, monkeypatch, _status_user(login="new-owner@example.com"))
    json.loads((tmp_path / "ts_state.json").read_text(encoding="utf-8"))
    st = json.loads((tmp_path / "ts_state.json").read_text(encoding="utf-8"))
    st["serve"] = {"Web": {f"{TS_HOST}:443": {"Handlers": {"/": {"Proxy": f"http://127.0.0.1:8766/{PP.gate()}"}}}}}
    (tmp_path / "ts_state.json").write_text(json.dumps(st), encoding="utf-8")
    rc, out = _cli("status")
    assert rc == 0 and "和记下的账户（ow***@e***.com）不一样" in out and "ne***@e***.com" in out and "new-owner@" not in out
    _fake_ts(tmp_path, monkeypatch, _status_user(tags=["tag:server"]))
    rc, out = _cli("on", yes=True)
    assert rc == 0 and "现在不可用" in out and "带 tag" in out and "生成配对码" in out
    assert json.loads((paths.home() / PP.PHONE_FILE).read_text(encoding="utf-8"))["owner"] is None
    _fake_ts(tmp_path, monkeypatch, _status_user(login="tagged-devices"))
    assert _cli("on", yes=True)[0] == 0 and json.loads((paths.home() / PP.PHONE_FILE).read_text(encoding="utf-8"))["owner"] is None


def test_phone_on_with_other_mac_users_defaults_to_pairing(tmp_path, monkeypatch):
    """这台 Mac 上有别人的 macOS 用户账户：第一次 on 默认只用配对；明确打开后 status 也提醒。"""
    monkeypatch.setattr(PP, "other_local_users", lambda: 2)
    _fake_ts(tmp_path, monkeypatch, _status_user())
    rc, out = _cli("on", yes=True)
    assert rc == 0 and "还有 2 个别的 macOS 用户账户" in out and "默认只用配对" in out and not PP.identity_state()["on"]
    rc, out = _cli("identity", value="on")
    assert rc == 0 and PP.identity_state()["on"] and "还有 2 个别的 macOS 用户账户" in out and "identity off" in out
    monkeypatch.setattr(PP, "other_local_users", lambda: 0)
    assert "别的 macOS 用户账户" not in _cli("status")[1]


def test_phone_on_upgrades_the_old_serve_target(tmp_path, monkeypatch):
    """2026-10-06 版的 Serve 目标没有路径密钥：phone on 不用再确认机器名，换成带路径密钥的（不显示）；老版本 tailscale 不肯覆盖 → 先关根路径再设。"""
    old = {"Web": {f"{TS_HOST}:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8766"}}}}}
    st, logf = _fake_ts(tmp_path, monkeypatch, _status_user(), old)
    rc, out = _cli("status")
    assert rc == 0 and "Serve 的设置是旧的" in out
    rc, out = _cli("on")                                                           # 不带 --yes / --confirm-name：以前确认过
    g = PP.gate()
    web = json.loads(st.read_text(encoding="utf-8"))["serve"]["Web"][f"{TS_HOST}:443"]["Handlers"]["/"]["Proxy"]
    assert rc == 0 and web == f"http://127.0.0.1:8766/{g}" and "换成带路径密钥的" in out and g not in out and PP.identity_state()["on"]
    rc, out = _cli("status")
    assert rc == 0 and f"手机地址：https://{TS_HOST}/" in out and "旧的" not in out
    # 老版本 tailscale：同一个挂载点不肯覆盖 → serve --set-path=/ off 再设；报错里的目标不显示路径密钥
    st, logf = _fake_ts(tmp_path, monkeypatch, _status_user(), old)
    monkeypatch.setenv("FAKE_TS_NO_OVERWRITE", "1")
    rc, out = _cli("on")
    calls = logf.read_text(encoding="utf-8")
    assert rc == 0 and "serve --https=443 --set-path=/ off" in calls and PP.gate() not in out
    web = json.loads(st.read_text(encoding="utf-8"))["serve"]["Web"][f"{TS_HOST}:443"]["Handlers"]["/"]["Proxy"]
    assert web == f"http://127.0.0.1:8766/{PP.gate()}"
    # 别人的服务占着 443：照旧不覆盖
    st, logf = _fake_ts(tmp_path, monkeypatch, _status_user(), {"Web": {f"{TS_HOST}:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8766/x"}}}}})
    rc, out = _cli("on", yes=True)
    assert rc == 2 and "被别的服务用" in out


def test_render_identity_footer_and_timeout_script(tmp_path):
    _book()
    dev = {"id": "ts-0123456789", "name": "Tailscale 账户 ow***@e***.com", "kind": "ts", "login": "ow***@e***.com"}
    remote = panel.render("paper", "c" * 40, AT, mode="remote", device=dev)
    assert "已用 Tailscale 账户登录（ow***@e***.com；不用配对）" in remote and "data-act='unpair'" not in remote
    assert "TMO = 15000" in remote and "AbortController" in remote and "Mac 可能在睡眠：取不到" in remote
    assert "data-retry" in remote and "'timeout'" in remote and "HALT 可能没送到" in remote and "HALT_TIP" in remote
    assert "KP[t]" in remote and "'auth'" in remote and "box.onkeydown=" in remote and "addEventListener('keydown', ev=>" not in remote
    paired = panel.render("paper", "c" * 40, AT, mode="remote", device=dict(dev, paired="iPhone"))
    assert "以前也配对过（iPhone）" in paired and "data-act='unpair'" in paired
    local = panel.render("paper", "t" * 40, AT, phone={"port": 8766, "url": f"https://{TS_HOST}/", "devices": [],
                                                       "identity": {"on": True, "off": False, "owner": "ow***@e***.com", "why": None}})
    assert "按 Tailscale 账户登录：<b>开</b>" in local and '"remote": false' in local and "data-act='pair-new'" in local
    pg = panel.pair_page("")
    assert "TMO = 15000" in pg and "Mac 可能在睡眠" in pg and "同一个 Tailscale 账户" in pg and "在 Mac 上重新生成" in pg


def _node():
    import shutil
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    return node


def test_fetch_timeout_logic_in_node(tmp_path):
    """15 秒超时的实际行为（node 里把 15 秒换成 50 毫秒）：fetch 一直不回 → 抛 Timeout、并 abort 掉请求；内容读不出来 → j = null；正常的照常返回。"""
    import subprocess
    node = _node()
    js = panel._NET_JS.replace("const TMO = 15000;", "const TMO = 50;")
    assert js != panel._NET_JS
    harness = js + r"""
globalThis.window = globalThis;
let aborted = false;
globalThis.fetch = (url, opt) => new Promise((res, rej) => {
  if (url === '/ok') return res({ok: true, status: 200, json: async () => ({ok: true, v: 1})});
  if (url === '/slowbody') return res({ok: true, status: 200, json: () => new Promise(() => {})});
  if (url === '/badbody') return res({ok: true, status: 200, json: async () => { throw new TypeError('network error'); }});
  opt.signal.addEventListener('abort', () => { aborted = true; rej(Object.assign(new Error('aborted'), {name: 'AbortError'})); });
});
(async () => {
  const a = await req('/ok', {});
  if (!(a.r.status === 200 && a.j.v === 1)) throw new Error('ok path');
  const b = await req('/badbody', {});
  if (!(b.r.ok && b.j === null)) throw new Error('bad body path');
  let e1 = null; try { await req('/hang', {}); } catch (e) { e1 = e; }
  if (!e1 || e1.name !== 'Timeout' || !aborted) throw new Error('hang path ' + (e1 && e1.name) + ' ' + aborted);
  let e2 = null; try { await req('/slowbody', {}); } catch (e) { e2 = e; }
  if (!e2 || e2.name !== 'Timeout') throw new Error('slow body path');
  console.log('OK');
})().catch(e => { console.error(e.message); process.exit(1); });
"""
    f = tmp_path / "net.js"
    f.write_text(harness, encoding="utf-8")
    r = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "OK", r.stderr[-500:]
    dev = {"id": "ts-0123456789", "name": "Tailscale 账户 ow***@e***.com", "kind": "ts", "login": "ow***@e***.com", "paired": "iPhone"}
    pages = {"pair": panel.pair_page(""), "remote_ident": panel.render("paper", "c" * 40, AT, mode="remote", device=dev),
             "remote_paired": panel.render("paper", "c" * 40, AT, mode="remote", device={"id": "0123456789ab", "name": "iPhone"}),
             "local": panel.render("paper", "t" * 40, AT, phone={"port": 8766, "url": None, "devices": [], "identity": {}})}
    for name, html in pages.items():
        g = tmp_path / f"{name}.js"
        g.write_text(html.split("<script>")[-1].split("</script>")[0], encoding="utf-8")
        r = subprocess.run([node, "--check", str(g)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, (name, r.stderr[-500:])


def test_chart_and_api_failure_paths_in_node(tmp_path):
    """页面脚本的 loadK / api（从 _JS 原样取出来、在 node 里跑）：读不出内容 → 可以再点的「取不到」；401 → 刷新；
    同一只票同时只发一个请求；HALT 的每种失败都提示云端的「停」、不自动消失；超时的文字按接口分开。"""
    import subprocess
    node = _node()
    J = panel._JS
    loadk = J[J.index("function loadK(t){"):J.index("function legend(head, D, i, tf){")].replace("location.reload(), 1500", "location.reload(), 5")
    api = J[J.index("const HALT_TIP"):J.index("function done(j){")].replace("location.reload(),1500", "location.reload(),5")
    assert "KP[t]" in loadk and "'auth'" in loadk and "HALT_TIP" in api
    net = panel._NET_JS.replace("const TMO = 15000;", "const TMO = 60;")
    harness = net + r"""
globalThis.window = globalThis;
const CFG = {book: 'paper', remote: true, auth: {h: 'X-Qbreak-Csrf', v: 'c'}};
const KD = {}, KP = {};
let reloads = 0; globalThis.location = {reload: () => { reloads++; }};
const toasts = []; function toast(t, bad, sticky){ toasts.push({t, bad: !!bad, sticky: !!sticky}); }
function busy(){}
const calls = {};
let SCEN = '';                                                     // api() 的情形（路径照真的写）
globalThis.fetch = (url, opt) => new Promise((res, rej) => {
  const t = (url.match(/[?&]t=([^&]+)/) || [])[1] || url;
  calls[t] = (calls[t] || 0) + 1;
  const body = (o) => async () => o;
  const m = url.startsWith('/api/chart') ? t : url + ':' + SCEN;
  if (m === 'OK') return res({ok: true, status: 200, json: body({ok: true, data: {kind: 'stock'}})});
  if (m === 'NONE') return res({ok: false, status: 404, json: body({ok: false})});
  if (m === 'BAD' || m === '/api/request:bad') return res({ok: true, status: 200, json: async () => { throw new TypeError('net'); }});
  if (m === 'AUTH' || m === '/api/request:401') return res({ok: false, status: 401, json: body({ok: false, msg: '这台设备还没配对'})});
  if (m === 'ERR' || m === '/api/halt:502') return res({ok: false, status: 502, json: async () => { throw new SyntaxError('html'); }});
  if (m === 'SLOW') return setTimeout(() => res({ok: true, status: 200, json: body({ok: true, data: {kind: 'core'}})}), 20);
  if (m === '/api/halt:net') return rej(new TypeError('Failed to fetch'));
  opt.signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted'), {name: 'AbortError'})));   // HANG / *:hang
});
""" + loadk + api + r"""
const sleep = ms => new Promise(r => setTimeout(r, ms));
const eq = (a, b, m) => { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error(m + ': ' + JSON.stringify(a) + ' != ' + JSON.stringify(b)); };
(async () => {
  eq(await loadK('OK'), {kind: 'stock'}, 'ok');
  eq(await loadK('NONE'), 'none', 'none');
  eq(await loadK('BAD'), 'error', 'bad body → error (retryable)');
  eq(await loadK('ERR'), 'error', '502');
  eq(await loadK('HANG'), 'timeout', 'hang');
  eq(await loadK('AUTH'), 'auth', '401'); await sleep(30); eq(reloads, 1, '401 reloads');
  const p1 = loadK('SLOW'), p2 = loadK('SLOW');
  if (p1 !== p2) throw new Error('in-flight not shared');
  eq(await p1, {kind: 'core'}, 'slow'); eq(calls.SLOW, 1, 'one request'); eq('SLOW' in KP, false, 'KP cleared');
  await loadK('BAD'); eq(calls.BAD, 2, 'error retried');
  await loadK('OK'); eq(calls.OK, 1, 'cached');
  // api(): 路径照真的写，情形用 SCEN 选
  const T = async (pc) => { const [path, sc] = pc.split(':'); SCEN = sc; toasts.length = 0; const r = await api(path, {}); return {r, t: toasts[0]}; };
  let x = await T('/api/halt:hang');
  if (!(x.r === null && x.t.sticky && x.t.t.includes('HALT') && x.t.t.includes('云端对话'))) throw new Error('halt timeout ' + JSON.stringify(x));
  x = await T('/api/halt:net');
  if (!(x.t.sticky && x.t.t.includes('HALT 没送到') && x.t.t.includes('云端对话'))) throw new Error('halt net ' + JSON.stringify(x));
  x = await T('/api/halt:502');
  if (!(x.t.sticky && x.t.t.includes('HTTP 502') && x.t.t.includes('云端对话'))) throw new Error('halt 502 ' + JSON.stringify(x));
  x = await T('/api/request:hang');
  if (!(x.t.t.includes('手动指令') && !x.t.t.includes('云端对话'))) throw new Error('request timeout ' + JSON.stringify(x));
  x = await T('/api/pair/new:hang');
  if (!(x.t.t.includes('不确定有没有生效') && !x.t.t.includes('手动指令'))) throw new Error('pair-new timeout ' + JSON.stringify(x));
  x = await T('/api/request:bad');
  if (!(x.r === null && x.t.sticky && x.t.t.includes('回应读不出来'))) throw new Error('bad body ' + JSON.stringify(x));
  const before = reloads; x = await T('/api/request:401'); await sleep(30);
  if (!(x.r === null && reloads === before + 1)) throw new Error('401 reload');
  console.log('OK');
})().catch(e => { console.error(e.message); process.exit(1); });
"""
    f = tmp_path / "page.js"
    f.write_text(harness, encoding="utf-8")
    r = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "OK", (r.stdout[-300:], r.stderr[-800:])
