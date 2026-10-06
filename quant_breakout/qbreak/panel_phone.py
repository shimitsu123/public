"""panel_phone.py — 手机上操作（2026-10-06 用户：「做一个可以在手机上操作的页面」）。

怎么连到 Mac：操作面板（qbreak/panel.py）除了本机的 127.0.0.1:8765，另开一个只给手机用的本机端口 127.0.0.1:8766；
  Tailscale Serve（tailscale serve --bg --https=443 http://127.0.0.1:8766）把它放到 https://<Mac 的机器名>.<tailnet>.ts.net/：
  只有登录了你自己 Tailscale 账户的设备（iPhone 装 Tailscale App）能打开，证书由 Tailscale 自动发（HTTPS）。
  绝不用 Tailscale Funnel（那会把页面公开到互联网）：run.py panel-phone 发现 Funnel 开着就拒绝。
配对（8766 这一路永远要「已配对的设备」；没配对什么数据都看不到）：
  ① Mac 的本机面板 http://127.0.0.1:8765/ 的「手机」点「生成配对码」→ 8 位（不含 I O 0 1）、10 分钟内有效、只能用一次、
     输错 5 次作废。配对码只显示在 Mac 屏幕上（不打印到终端、日志、对话；文件里只存 HMAC 摘要）
  ② 手机打开 https://…ts.net/（或扫 Mac 屏幕上的二维码）→ 输入配对码 → 发这台设备的 cookie
     （qbd=<设备 id>.<令牌>；HttpOnly; Secure; SameSite=Strict; 180 天；文件里只存令牌的 SHA-256）
  ③ 手机上的每个写操作还要带这台设备的 CSRF 令牌（页面里 = HMAC(secret, 设备 id)；别的网站读不到）
  最多 5 台；Mac 的面板上可以取消任何一台，手机上可以「退出这台设备」；run.py panel-phone forget = 全部取消。
手机能做的 = 本机面板能做的（只写手动指令；下单永远是执行器）＋「停止下单（HALT）」：只能建、不能解除
  （解除只在 Mac 上，用户明确说「恢复下单，删除 HALT」）。配对、取消别的设备只在 Mac 上。
数据目录里的文件（不入库；仓库的 var/panel_* 已 gitignore）：panel_devices.json（0600：secret、设备、配对码摘要）、
  panel_phone.json（手机地址；panel-phone on 写、off 删）。
"""
from __future__ import annotations

import base64
import contextlib
import datetime as dt
import fcntl
import functools
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import zlib

from . import paths
from .calendar_jp import JST, now_jst
from .utils import atomic_write_text, read_json, setup_logging

log = setup_logging("panel")

DEVICES_FILE = "panel_devices.json"
PHONE_FILE = "panel_phone.json"
PHONE_PORT = 8766
COOKIE = "qbd"
COOKIE_MAX_AGE = 180 * 86400
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"        # 没有 I / O / 0 / 1（容易看错）
CODE_LEN = 8
CODE_TTL_S = 600
CODE_MAX_FAILS = 5
MAX_DEVICES = 5
SEEN_EVERY_S = 300
HALT_DRILL_PREFIX = "HALT 演练"                            # run.py live-u --halt-drill 建的 HALT（演练结束会被删）
TS_HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+ts\.net(?::\d{1,5})?$")
_URL = re.compile(r"^https://(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+ts\.net(?::\d{1,5})?/$")
TS_APP_CLI = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
TS_CANDIDATES = (TS_APP_CLI, "/opt/homebrew/bin/tailscale", "/usr/local/bin/tailscale")
_mu = threading.RLock()


# ───────────────────────── 设备与配对码（数据目录 panel_devices.json，0600） ─────────────────────────
def _path():
    return paths.home() / DEVICES_FILE


@contextlib.contextmanager
def _locked():
    """同一进程的线程（本机 / 手机两个服务）+ 别的进程（run.py panel-phone）都排队写。"""
    with _mu:
        fd = os.open(paths.home() / "panel_devices.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _read() -> dict:
    d = read_json(_path(), {}) or {}
    if not isinstance(d, dict):
        d = {}
    if not isinstance(d.get("devices"), dict):
        d["devices"] = {}
    if not re.fullmatch(r"[0-9a-f]{64}", str(d.get("secret") or "")):
        d["secret"] = secrets.token_hex(32)
    return d


def _write(d: dict) -> None:
    p = _path()
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def _mac(secret: str, s: str) -> str:
    return hmac.new(bytes.fromhex(secret), s.encode("utf-8"), hashlib.sha256).hexdigest()


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, JST).isoformat(timespec="seconds")


def fmt_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def new_code(now: float | None = None) -> tuple[str, float]:
    """生成配对码（旧的作废）→ (配对码, 失效的 epoch 秒)。只给 Mac 的本机页面用：调用的人负责只把它显示在 Mac 屏幕上。"""
    now = time.time() if now is None else float(now)
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
    with _locked():
        d = _read()
        d["pair"] = {"h": _mac(d["secret"], "pair:" + code), "exp": now + CODE_TTL_S, "fails": 0, "at": _iso(now)}
        _write(d)
    log.info("手机配对：生成了配对码（%d 分钟内有效；只显示在 Mac 屏幕上）", CODE_TTL_S // 60)
    return code, now + CODE_TTL_S


def pending(now: float | None = None) -> dict | None:
    """在等的配对码（不含配对码本身）：{"exp": epoch, "fails": n} 或 None。"""
    now = time.time() if now is None else float(now)
    p = (read_json(_path(), {}) or {}).get("pair") or None
    if not isinstance(p, dict) or now > float(p.get("exp") or 0):
        return None
    return {"exp": float(p["exp"]), "fails": int(p.get("fails") or 0)}


def device_name(name: str | None, ua: str | None = "") -> str:
    n = re.sub(r"[\x00-\x1f\x7f<>&\"'`\\]", "", " ".join(str(name or "").split()))[:20].strip()
    if n:
        return n
    ua = str(ua or "")
    for k, v in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Macintosh", "Mac")):
        if k in ua:
            return v
    return "手机"


def pair(code: str | None, name: str | None = "", ua: str | None = "", now: float | None = None) -> tuple[bool, str, str | None]:
    """手机输入的配对码 → (成功?, 说明, cookie 的值「设备 id.令牌」)。错 5 次 / 过期 / 用过 → 作废。"""
    now = time.time() if now is None else float(now)
    c = re.sub(r"[^A-Z0-9]", "", str(code or "").upper())
    with _locked():
        d = _read()
        p = d.get("pair")
        if not isinstance(p, dict) or now > float(p.get("exp") or 0):
            if p is not None:
                d.pop("pair", None)
                _write(d)
            return False, "没有有效的配对码（10 分钟内有效、只能用一次）：在 Mac 的操作面板「手机」里重新生成", None
        if len(c) != CODE_LEN or not hmac.compare_digest(_mac(d["secret"], "pair:" + c), str(p.get("h") or "")):
            p["fails"] = int(p.get("fails") or 0) + 1
            left = CODE_MAX_FAILS - p["fails"]
            if left <= 0:
                d.pop("pair", None)
                msg = f"配对码输错 {CODE_MAX_FAILS} 次，已作废：在 Mac 的操作面板上重新生成"
            else:
                d["pair"] = p
                msg = f"配对码不对（还能试 {left} 次）"
            _write(d)
            log.warning("手机配对：配对码不对（这个配对码第 %d 次）", p["fails"])
            return False, msg, None
        if len(d["devices"]) >= MAX_DEVICES:
            return False, f"已经配对了 {MAX_DEVICES} 台设备：先在 Mac 的操作面板「手机」里取消不用的", None
        d.pop("pair", None)
        did, tok = secrets.token_hex(6), secrets.token_urlsafe(32)
        nm = device_name(name, ua)
        d["devices"][did] = {"name": nm, "h": hashlib.sha256(tok.encode("utf-8")).hexdigest(), "created": _iso(now),
                             "seen": _iso(now), "seen_ts": now}
        _write(d)
    log.info("手机配对：新设备「%s」（%s…）", nm, did[:4])
    return True, f"配对成功：这台设备（{nm}）可以用了", f"{did}.{tok}"


def _cookie(header: str | None, name: str) -> str | None:
    for part in str(header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v.strip().strip('"')
    return None


def device_for(cookie_header: str | None, now: float | None = None) -> dict | None:
    """请求的 Cookie 头 → 已配对的设备 {"id","name","created","seen"}；不是 → None。"""
    val = _cookie(cookie_header, COOKIE)
    if not val or "." not in val:
        return None
    did, tok = val.split(".", 1)
    if not re.fullmatch(r"[0-9a-f]{12}", did) or not re.fullmatch(r"[A-Za-z0-9_\-]{20,100}", tok):
        return None
    dev = ((read_json(_path(), {}) or {}).get("devices") or {}).get(did)
    if not isinstance(dev, dict) or not hmac.compare_digest(hashlib.sha256(tok.encode("utf-8")).hexdigest(), str(dev.get("h") or "")):
        return None
    now = time.time() if now is None else float(now)
    if now - float(dev.get("seen_ts") or 0) > SEEN_EVERY_S:
        with _locked():
            d = _read()
            if did in d["devices"]:
                d["devices"][did].update(seen=_iso(now), seen_ts=now)
                _write(d)
    return {"id": did, "name": str(dev.get("name") or "手机"), "created": dev.get("created"), "seen": dev.get("seen")}


def _secret() -> str:
    s = str((read_json(_path(), {}) or {}).get("secret") or "")
    if re.fullmatch(r"[0-9a-f]{64}", s):
        return s
    with _locked():
        d = _read()
        _write(d)
        return d["secret"]


def csrf(did: str) -> str:
    """这台设备的 CSRF 令牌（嵌在给它的页面里；写操作要带 X-Qbreak-Csrf）。"""
    return _mac(_secret(), "csrf:" + str(did))[:40]


def csrf_ok(did: str, value: str | None) -> bool:
    return bool(value) and hmac.compare_digest(csrf(did), str(value))


def devices() -> list[dict]:
    """已配对的设备（不含令牌摘要），按最近使用排。"""
    d = (read_json(_path(), {}) or {}).get("devices") or {}
    out = [{"id": k, "name": str(v.get("name") or "手机"), "created": v.get("created"), "seen": v.get("seen")}
           for k, v in d.items() if isinstance(v, dict)]
    return sorted(out, key=lambda x: str(x.get("seen") or ""), reverse=True)


def revoke(did: str) -> bool:
    with _locked():
        d = _read()
        dev = d["devices"].pop(str(did), None)
        if dev is None:
            return False
        _write(d)
    log.info("手机配对：取消了设备「%s」（%s…）", dev.get("name"), str(did)[:4])
    return True


def revoke_all() -> int:
    """全部取消（设备 + 在等的配对码），并换掉 secret（旧的 CSRF 令牌全部失效）。"""
    with _locked():
        d = _read()
        n = len(d["devices"])
        _write({"devices": {}, "secret": secrets.token_hex(32)})
    log.info("手机配对：全部取消（%d 台）", n)
    return n


def cookie_set(value: str) -> str:
    return f"{COOKIE}={value}; Path=/; Max-Age={COOKIE_MAX_AGE}; HttpOnly; Secure; SameSite=Strict"


def cookie_clear() -> str:
    return f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict"


# ───────────────────────── HALT：只能建、不能解除 ─────────────────────────
def create_halt(reason: str | None, who: str, now: dt.datetime | None = None) -> tuple[bool, str]:
    """建 HALT 文件（数据目录 HALT：执行器的下一次运行起买卖都不下、持仓不动）。已经有了就不动；
    演练建的 HALT（演练结束会被删）→ 换成真的，免得被演练删掉。这里没有删除 HALT 的路。"""
    now = now or now_jst()
    p = paths.halt_file()
    why = " ".join(str(reason or "").split())[:200] or "用户点了停止下单"
    who = " ".join(str(who or "").split())[:40] or "面板"
    text = f"停止下单（{who}）{now:%Y-%m-%d %H:%M} JST：{why}\n恢复：在 Mac 对话里明确说「恢复下单，删除 HALT」\n"
    done = ("已建 HALT：执行器的下一次运行起不下任何单（模拟账户和立花都停；持仓不动）。已经发到交易所的单不会被撤："
            "要撤请在立花网站 / App 上撤。恢复只在 Mac 上（在 Mac 的 Claude 对话里明确说「恢复下单，删除 HALT」）")
    with _mu:
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            try:
                old = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                old = ""
            if old.startswith(HALT_DRILL_PREFIX):
                atomic_write_text(p, text)
                log.warning("HALT（把演练的 HALT 换成真的）：%s", text.splitlines()[0])
                return True, done
            first = (old.splitlines() or ["—"])[0][:120]
            return True, f"HALT 已经生效（{first}）：不用再点。恢复只在 Mac 上"
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
    log.warning("HALT：%s", text.splitlines()[0])
    return True, done


def halt_text() -> str | None:
    p = paths.halt_file()
    if not p.exists():
        return None
    try:
        return (p.read_text(encoding="utf-8", errors="replace").splitlines() or ["HALT"])[0][:160]
    except OSError:
        return "HALT"


# ───────────────────────── 手机地址、二维码、图标 ─────────────────────────
def phone_url() -> str | None:
    """panel-phone on 记下的手机地址（https://<机器名>.<tailnet>.ts.net/）；没打开 → None。"""
    u = str((read_json(paths.home() / PHONE_FILE, {}) or {}).get("url") or "")
    return u if _URL.match(u) else None


def qr_data_uri(text: str) -> str | None:
    """二维码（SVG 的 data URI）；没装 qrcode（可选依赖）→ None（页面只显示配对码与地址）。"""
    try:
        import qrcode
        import qrcode.image.svg
        svg = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2).to_string(encoding="unicode")
    except Exception as e:                                   # noqa: BLE001
        log.info("二维码不可用（%s）：只显示配对码与地址", type(e).__name__)
        return None
    if isinstance(svg, bytes):
        svg = svg.decode("utf-8")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _png(w: int, h: int, rows: list[bytes]) -> bytes:
    def chunk(t: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _seg(px: float, py: float, a: tuple, b: tuple) -> float:
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


@functools.lru_cache(maxsize=2)
def touch_icon_png(size: int = 180) -> bytes:
    """主屏幕图标（apple-touch-icon）：蓝底 + 白色「横盘之后向上突破」的折线。纯 Python 画（不依赖图像库）。"""
    bg, fg = (0x2F, 0x5B, 0xD3), (255, 255, 255)
    pts = [(x * size, y * size) for x, y in ((0.16, 0.66), (0.36, 0.60), (0.52, 0.66), (0.84, 0.27))]
    half = size * 0.045
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            d = min(_seg(x + 0.5, y + 0.5, a, b) for a, b in zip(pts, pts[1:]))
            cov = max(0.0, min(1.0, half + 0.5 - d))
            row += bytes(int(round(bg[k] + (fg[k] - bg[k]) * cov)) for k in range(3))
        rows.append(bytes(row))
    return _png(size, size, rows)


MANIFEST = {"name": "qbreak 操作面板", "short_name": "qbreak", "start_url": "/", "scope": "/", "display": "standalone",
            "background_color": "#f2f2f7", "theme_color": "#2f5bd3",
            "icons": [{"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"}]}


# ───────────────────────── Tailscale（只用 Serve；绝不用 Funnel） ─────────────────────────
def find_cli() -> str | None:
    """tailscale 命令：环境变量 QBREAK_TAILSCALE > PATH > Mac App 自带的（/Applications/Tailscale.app/…/Tailscale）> Homebrew。"""
    env = os.environ.get("QBREAK_TAILSCALE")
    if env:
        return env if os.access(env, os.X_OK) else None
    w = shutil.which("tailscale")
    if w:
        return w
    return next((c for c in TS_CANDIDATES if os.access(c, os.X_OK)), None)


def _ts(cli: str, *args: str, timeout: float = 30) -> tuple[int, str, str]:
    try:
        r = subprocess.run([cli, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"tailscale {' '.join(args)} 超过 {timeout:g} 秒没有结束"
    except OSError as e:
        return 127, "", str(e)


def ts_info(cli: str) -> dict:
    """tailscale status --json 里要用的几项（这台 Mac 的 DNS 名、MagicDNS、HTTPS 证书）。别的设备 / 账户信息不留不打印。"""
    rc, out, err = _ts(cli, "status", "--json")
    try:
        j = json.loads(out) if out.strip() else {}
    except ValueError:
        j = {}
    if not isinstance(j, dict) or not j:
        return {"ok": False, "err": (err or out or f"退出码 {rc}").strip()[:300]}
    dns = str((j.get("Self") or {}).get("DNSName") or "").rstrip(".").lower()
    return {"ok": True, "state": str(j.get("BackendState") or ""), "dns": dns,
            "magicdns": bool((j.get("CurrentTailnet") or {}).get("MagicDNSEnabled")), "https": bool(j.get("CertDomains")),
            "version": str(j.get("Version") or "")}


def serve_info(cli: str, host: str, https_port: int) -> dict:
    """tailscale serve status --json：这个 HTTPS 端口的根路径代理到哪里、Funnel（公开到互联网）开没开。"""
    rc, out, _ = _ts(cli, "serve", "status", "--json")
    try:
        j = json.loads(out) if rc == 0 and out.strip() else {}
    except ValueError:
        j = {}
    j = j if isinstance(j, dict) else {}
    web = j.get("Web") or {}
    key = f"{host}:{https_port}"
    handlers = (web.get(key) or {}).get("Handlers") or {}
    root = handlers.get("/") or {}
    return {"proxy": str(root.get("Proxy") or "") or None, "other_root": bool(root) and not root.get("Proxy"),
            "funnel": any(bool(v) for k, v in (j.get("AllowFunnel") or {}).items() if str(k).endswith(f":{https_port}")),
            "ok": rc == 0}


def _norm(u: str | None) -> str:
    return str(u or "").strip().rstrip("/").lower()


def listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=1.5):
            return True
    except OSError:
        return False


def _save_phone(url: str, port: int, https_port: int) -> None:
    atomic_write_text(paths.home() / PHONE_FILE, json.dumps(
        {"url": url, "port": int(port), "https_port": int(https_port), "at": now_jst().isoformat(timespec="seconds")},
        ensure_ascii=False, indent=1))


def _saved() -> dict:
    d = read_json(paths.home() / PHONE_FILE, {}) or {}
    return d if isinstance(d, dict) else {}


def _devices_lines() -> list[str]:
    ds = devices()
    out = [f"已配对的设备：{len(ds)} 台（最多 {MAX_DEVICES} 台）"]
    out += [f"  - {x['name']}（配对 {str(x.get('created') or '')[:16]}，最近 {str(x.get('seen') or '')[:16]}）" for x in ds]
    pc = pending()
    if pc:
        out.append(f"有一个配对码在等（{dt.datetime.fromtimestamp(pc['exp'], JST):%H:%M} JST 前有效；配对码只在 Mac 的操作面板上显示）")
    return out


def cli(action: str = "status", port: int = PHONE_PORT, https_port: int = 443, yes: bool = False, out=print,
        open_panel: bool = True) -> int:
    """run.py panel-phone：on（打开手机访问）/ off（关闭）/ status（只读）/ forget（取消全部配对）。
    从不打印配对码；只动 Tailscale Serve 的这一个 HTTPS 端口；Funnel 开着就拒绝。"""
    target = f"http://127.0.0.1:{int(port)}"
    out("── 手机操作（Tailscale Serve：只有你自己 Tailscale 里的设备能连；绝不用 Funnel）──")
    if action == "forget":
        n = revoke_all()
        out(f"已取消全部 {n} 台设备的配对（手机上要重新配对：Mac 的操作面板「手机」→ 生成配对码）")
        return 0
    saved = _saved()
    hp = int(saved.get("https_port") or https_port) if action in ("off", "status") else int(https_port)
    ts = find_cli()
    if ts is None:
        out("★ 没找到 tailscale 命令：Mac 上装 Tailscale（App Store 或 tailscale.com/download），登录；"
            "iPhone 上装 Tailscale App、用同一个账户登录")
        if action == "status":
            out(f"操作面板的手机端口 127.0.0.1:{port}：{'在监听' if listening(port) else '没在监听'}")
            for ln in _devices_lines():
                out(ln)
            return 0
        return 2
    info = ts_info(ts)
    if not info["ok"] or info.get("state") != "Running" or not info.get("dns"):
        out(f"★ Tailscale 没在运行或没登录（{info.get('state') or info.get('err') or '—'}）：打开 Tailscale App 登录、打开连接")
        if action != "status":
            return 2
    host = info.get("dns") or ""
    url = f"https://{host}/" if hp == 443 else f"https://{host}:{hp}/"
    si = serve_info(ts, host, hp) if host else {"proxy": None, "funnel": False, "other_root": False, "ok": False}
    ours = _norm(si["proxy"]) == _norm(target)
    if action == "status":
        out(f"Tailscale：{info.get('state') or '—'}；这台 Mac：{host or '—'}；MagicDNS {'开' if info.get('magicdns') else '关'}；"
            f"HTTPS 证书 {'开' if info.get('https') else '关'}")
        out(f"手机地址：{url if ours else '没打开（bash scripts/liveu.sh phone on）'}"
            + ("；★ Funnel 开着（公开到互联网）：tailscale funnel --https=" + str(hp) + " off" if si["funnel"] else ""))
        out(f"操作面板的手机端口 127.0.0.1:{port}：{'在监听' if listening(port) else '没在监听（bash scripts/install_launchd_panel.sh 重启面板）'}")
        for ln in _devices_lines():
            out(ln)
        return 0
    if action == "off":
        if ours:
            rc, o, e = _ts(ts, "serve", f"--https={hp}", "off")
            if rc != 0:
                out(f"★ 关闭失败（退出码 {rc}）：{(e or o).strip()[:300]}")
                return 1
            out(f"已关闭 Tailscale Serve 的 {hp} 端口：手机打不开了")
        else:
            out(f"Tailscale Serve 的 {hp} 端口不是 qbreak 的（或已经关了）：不动它")
        (paths.home() / PHONE_FILE).unlink(missing_ok=True)
        out("已配对的设备保留（重新打开：bash scripts/liveu.sh phone on；全部取消配对：bash scripts/liveu.sh phone forget）")
        return 0
    if action != "on":
        out(f"不认识的操作 {action!r}（on / off / status / forget）")
        return 2
    # ── on ──
    if not info.get("magicdns") or not info.get("https"):
        out("★ 先在 Tailscale 管理页（login.tailscale.com/admin/dns）打开 MagicDNS 与 HTTPS Certificates（Enable HTTPS），再运行一次")
        return 2
    if si["funnel"]:
        out(f"★ {host}:{hp} 开着 Funnel（公开到互联网）：先关掉 tailscale funnel --https={hp} off；qbreak 只用 Serve（只在你的 tailnet 里）")
        return 2
    if (si["proxy"] and not ours) or si.get("other_root"):
        out(f"★ Tailscale Serve 的 {hp} 端口已经被别的服务用（{si['proxy'] or '文件 / 文本'}）：不覆盖。换一个端口："
            "bash scripts/liveu.sh phone on --https-port 8443")
        return 2
    if not ours and not yes and _norm(saved.get("url")) != _norm(url):
        name, _, tailnet = host.partition(".")
        out(f"★ 第一次打开：HTTPS 证书会把机器名「{name}」与 tailnet 名「{tailnet}」写进公开的证书透明度日志"
            "（Certificate Transparency），任何人都能查到（查到也连不上：只有你 Tailscale 里的设备能连）。")
        out("  名字里有姓名等个人信息 → 先在 Tailscale 管理页 Machines → 这台 Mac → Edit machine name 改成不含个人信息的名字"
            "（例 qbreak-mac），再运行一次")
        out("  名字没问题 → bash scripts/liveu.sh phone on --yes")
        return 3
    if not listening(port):
        out(f"★ 操作面板没在监听手机端口 127.0.0.1:{port}（没运行、或还是旧版本）：bash scripts/install_launchd_panel.sh 重启面板。"
            "Serve 照样打开，面板起来之后手机就能连")
    if not ours:
        rc, o, e = _ts(ts, "serve", "--bg", f"--https={hp}", target, timeout=90)
        if rc != 0:
            out(f"★ tailscale serve 失败（退出码 {rc}）：{(e or o).strip()[:400]}")
            return 1
        si = serve_info(ts, host, hp)
        if _norm(si["proxy"]) != _norm(target) or si["funnel"]:
            out("★ tailscale serve 之后的设置不对（没有指向面板，或 Funnel 开着）：bash scripts/liveu.sh phone status 看一下")
            return 1
    _save_phone(url, port, hp)
    out(f"手机访问已打开：{url}（Serve → {target}；只在你的 tailnet 里，不公开到互联网）")
    out("下一步：① iPhone 装 Tailscale App、用同一个账户登录、打开连接 ② Safari 打开上面的地址 "
        "③ 在这台 Mac 的操作面板 http://127.0.0.1:8765/ 的「手机」点「生成配对码」，把 Mac 屏幕上的配对码输进手机（或扫二维码）"
        "④ Safari 的「共享 → 添加到主屏幕」可以像 App 一样打开（主屏幕上要求重新配对的话，再生成一次配对码）")
    for ln in _devices_lines():
        out(ln)
    if open_panel and sys.platform == "darwin" and not (paths.home() / "NO_OPEN").exists():
        try:
            subprocess.run(["open", "http://127.0.0.1:8765/#phone"], timeout=20, capture_output=True, check=False)
        except Exception:                                    # noqa: BLE001
            pass
    return 0


__all__ = ["new_code", "pair", "device_for", "csrf", "csrf_ok", "devices", "revoke", "revoke_all", "create_halt",
           "phone_url", "qr_data_uri", "touch_icon_png", "cli", "MANIFEST", "TS_HOST", "PHONE_PORT", "fmt_code"]
