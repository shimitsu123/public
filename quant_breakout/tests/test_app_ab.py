"""〔App 化〕A + B 与手机连不上的再发防止：Web Push（RFC 8291 / 8292）、service worker、通知卡片、mac_status、菜单栏安装。"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from qbreak import mac_status as MS
from qbreak import panel, paths
from qbreak import panel_phone as PP
from qbreak import webpush as WP

ROOT = Path(__file__).resolve().parent.parent


def test_rfc8291_vector():
    from cryptography.hazmat.primitives.asymmetric import ec
    asp = ec.derive_private_key(int.from_bytes(WP.unb64u("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"), ec.SECP256R1())
    out = WP.encrypt(b"When I grow up, I want to be a watermelon",
                     WP.unb64u("BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"),
                     WP.unb64u("BTBZMqHH6r4Tts7J_aSIgg"), salt=WP.unb64u("DGv6ra1nlYgDCS1FRnbzlw"), as_key=asp)
    assert WP.b64u(out) == ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8w"
                            "EqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


def _ua():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1())
    pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"endpoint": "https://web.push.apple.com/abc", "keys": {"p256dh": WP.b64u(pub), "auth": WP.b64u(os.urandom(16))}}


def test_vapid_keys_are_private_and_jwt_verifies():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
    k1 = WP.public_key()
    assert k1 == WP.public_key() and len(WP.unb64u(k1)) == 65
    assert oct(os.stat(paths.home() / WP.VAPID_FILE).st_mode & 0o777) == "0o600"
    key, pub = WP._vapid()
    tok = WP._jwt("https://web.push.apple.com", "https://x.ts.net", key)
    h, c, s = tok.split(".")
    raw = WP.unb64u(s)
    pk = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), WP.unb64u(pub))
    pk.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
              f"{h}.{c}".encode(), ec.ECDSA(hashes.SHA256()))
    assert json.loads(WP.unb64u(c))["aud"] == "https://web.push.apple.com"


def test_subscribe_validates_and_send_drops_gone_subscriptions():
    assert not WP.subscribe("x", {"endpoint": "http://insecure", "keys": {}})[0]
    good = _ua()
    assert WP.subscribe("LIiphone", good, "LIiphone")[0]
    assert oct(os.stat(paths.home() / WP.SUBS_FILE).st_mode & 0o777) == "0o600"
    sent = []

    class R:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def ok_opener(req, timeout=15):
        sent.append(req)
        return R()
    assert WP.send("t", "b", opener=ok_opener) is True
    h = dict(sent[0].header_items())
    assert h["Content-encoding"] == "aes128gcm" and h["Authorization"].startswith("vapid t=") and h["Ttl"] == str(WP.TTL_S)
    import urllib.error

    def gone(req, timeout=15):
        raise urllib.error.HTTPError(req.full_url, 410, "Gone", {}, None)
    assert WP.send("t", "b", opener=gone) is False and WP.subs() == {}
    assert WP.send("t", "b") is None                                         # 没有订阅


def test_sw_csp_key_and_subscribe_endpoints_on_local_port():
    import http.client
    import threading
    from http.server import ThreadingHTTPServer
    assert "worker-src 'self'" in panel.CSP and "addEventListener('push'" in panel.SW_JS
    tok = panel.token()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), panel.make_handler(1, tok))
    port = srv.server_address[1]
    srv.RequestHandlerClass = panel.make_handler(port, tok)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        def req(method, path, body=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            h = {"Host": f"127.0.0.1:{port}", "X-Qbreak-Token": tok, "Content-Type": "application/json"}
            c.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=h)
            r = c.getresponse()
            return r.status, r.read().decode("utf-8"), dict(r.getheaders())
        st, body, hd = req("GET", "/sw.js")
        assert st == 200 and hd.get("Service-Worker-Allowed") == "/" and "showNotification" in body
        st, body, _ = req("GET", "/api/push/key")
        assert st == 200 and json.loads(body)["key"] == WP.public_key()
        sub = _ua()
        st, body, _ = req("POST", "/api/push/subscribe", {"sub": sub})
        assert st == 200 and len(WP.subs()) == 1
        st, body, _ = req("POST", "/api/push/unsubscribe", {"endpoint": sub["endpoint"]})
        assert st == 200 and WP.subs() == {}
    finally:
        srv.shutdown()
        srv.server_close()


def test_remote_page_has_notify_card_tabbar_and_stale_banner():
    from test_panel import AT, _book
    _book()
    h = panel.render("paper", "t" * 40, AT, mode="remote", device={"name": "x", "kind": "ts", "id": "ts"})
    assert "id='notify'" in h and "class='tabbar'" in h and "id='stale'" in h and '"gen":' in h
    assert "127.0.0.1 的地址（那是手机自己" in h
    hl = panel.render("paper", "t" * 40, AT, phone={"port": 8766, "url": None, "devices": []})
    assert "id='notify'" not in hl and "class='tabbar'" in hl


def test_phone_health_and_ensure(monkeypatch):
    assert PP.health()["enabled"] is False                                   # 没打开过手机访问 → 不查
    calls = []
    monkeypatch.setattr(PP, "health", lambda port=8766: {"enabled": True, "ok": False, "url": "https://m.ts.net/",
                                                          "problems": ["Tailscale Serve 的设置不在了"], "repairable": False})
    PP.ensure(notify=lambda s, t: calls.append((s, t)), today="2026-10-11")
    PP.ensure(notify=lambda s, t: calls.append((s, t)), today="2026-10-11")  # 同一天同一个问题只通知一次
    assert len(calls) == 1 and "https://m.ts.net/" in calls[0][1] and "127.0.0.1" in calls[0][1]


def test_mac_status_flags_unloaded_agents(tmp_path, monkeypatch):
    ag = Path(os.environ["QBREAK_LAUNCH_AGENTS"])
    ag.mkdir(parents=True, exist_ok=True)
    for lb in ("com.qbreak.login", "com.qbreak.news"):
        (ag / f"{lb}.plist").write_text("x", encoding="utf-8")

    def run(args, **k):
        return subprocess.CompletedProcess(args, 0, "PID\tStatus\tLabel\n-\t0\tcom.qbreak.news\n", "")
    it = MS._agents_item(run)
    assert it["level"] == "bad" and "login" in it["text"]
    s = MS.build(run=run)
    assert s["level"] == "bad" and s["title"] == "qbreak ✕"
    MS.main(["--write"])
    assert json.loads(MS.path().read_text(encoding="utf-8"))["items"]


def test_menubar_installer_with_stub_compiler(tmp_path):
    b = tmp_path / "bin"
    b.mkdir()
    (b / "launchctl").write_text("#!/bin/sh\nexit 0\n")
    (b / "swiftc").write_text('#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = "-o" ] && { shift; echo bin > "$1"; }; shift; done\n')
    for f in ("launchctl", "swiftc"):
        (b / f).chmod(0o755)
    env = {**os.environ, "PATH": f"{b}:/usr/bin:/bin", "QBREAK_LAUNCH_AGENTS": str(tmp_path / "la"),
           "QBREAK_LIVEU_HOME": str(tmp_path / "h"), "QBREAK_APP_DIR": str(tmp_path / "app")}
    r = subprocess.run(["bash", str(ROOT / "scripts" / "install_launchd_menubar.sh")], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    p = (tmp_path / "la" / "com.qbreak.menubar.plist").read_text(encoding="utf-8")
    assert "QbreakBar.app/Contents/MacOS/QbreakBar" in p and "<key>RunAtLoad</key><true/>" in p
    assert "<key>LSUIElement</key><true/>" in (tmp_path / "app" / "QbreakBar.app" / "Contents" / "Info.plist").read_text()


@pytest.mark.skipif(not shutil.which("swiftc"), reason="没有 swiftc（不是装了 Xcode CLT 的 Mac）")
def test_menubar_swift_typechecks():
    r = subprocess.run(["swiftc", "-typecheck", str(ROOT / "scripts" / "menubar" / "QbreakBar.swift")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-800:]


def test_tabs_group_sections_and_news_deeplink(monkeypatch):
    """面板分成 总览 / 持仓 / 交易 / 选股 / 消息 / 更多（_panes）；消息卡片显示发布 / 提醒时间、每条有 id（推送点开 ?tab=news&n=<id>）。"""
    from qbreak import news as NW
    from qbreak.utils import write_json
    from test_panel import AT, _book
    _book()
    write_json(NW.cache_dir() / "news.json", {"generated": "2026-10-06 07:45 JST", "events": [
        {"id": "abc123", "title": "Oil spikes", "link": "https://example.com/x", "time": "2026-10-06T06:30+09:00", "publisher": "X",
         "n_sources": 3, "event_labels": ["原油供给冲击"], "severity": 2, "cred": 80, "cred_label": "高", "why": ["3 个来源"],
         "alert": True, "threat": 1.5, "chain": {"shock_txt": "原油 +5%", "down": [["运输", -1.2]], "tickers_down": ["9020.T"]}}]})
    write_json(NW.cache_dir() / "alerted.json", {"abc123": "2026-10-06T06:45"})
    h = panel.render("paper", "t" * 40, AT, mode="remote", device={"name": "x", "kind": "ts", "id": "ts"})
    for k in ("home", "hold", "trade", "pick", "news", "more"):
        assert f"class='pane' data-tab='{k}'" in h and f"data-tabgo='{k}'" in h, k
    assert "id='n-abc123'" in h and "10/06 06:30" in h and "提醒：10/06 06:45" in h and "原油 +5%" in h
    assert h.count("<div class='pane'") == h.count("<div class='pane' data-tab=")
    assert "<i class='badge'>1</i>" in h                                    # 消息 24 小时内的提醒数 / 持仓只数


def test_notify_send_passes_url_to_push(monkeypatch):
    from qbreak import notify
    got = {}
    monkeypatch.setattr(WP, "send", lambda title, body, url="/", opener=None: got.update(url=url) or True)
    assert notify.send("经济威胁提醒", "x", "warn", url="/?tab=news&n=abc")["push"] is True
    assert got["url"] == "/?tab=news&n=abc"


def test_notifications_are_recorded_and_shown_with_jst_and_deeplink(monkeypatch):
    """2026-10-11 用户「不用 Gmail，直接在 qbreak 里通知并记录」：每条 notify.send 记进通知记录（0600），面板「消息 → 通知记录」显示，
    推送的默认点开地址 = 通知记录里的这一条。"""
    from qbreak import notify
    got = {}
    monkeypatch.setattr(WP, "send", lambda title, body, url="/", opener=None: got.update(url=url) or True)
    notify.send("qbreak ★ 自检没通过", "原因：今天早上的运行没跑", "warn")
    hs = notify.history()
    assert hs[0]["subject"] == "qbreak ★ 自检没通过" and hs[0]["level"] == "warn"
    assert got["url"] == f"/?tab=news&seg=log&l={hs[0]['id']}"
    assert oct(os.stat(paths.out_dir() / notify.LOG_FILE).st_mode & 0o777) == "0o600"
    for i in range(notify.LOG_KEEP + 5):
        notify.record(f"s{i}", "t")
    assert len((paths.out_dir() / notify.LOG_FILE).read_text(encoding="utf-8").splitlines()) == notify.LOG_KEEP
    h = panel._notify_log_card()
    assert "JST" in h and "id='l-" in h and "通知记录" in h
