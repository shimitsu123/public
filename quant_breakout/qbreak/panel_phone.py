"""panel_phone.py — 手机上操作（2026-10-06 用户：「做一个可以在手机上操作的页面」）。

怎么连到 Mac：操作面板（qbreak/panel.py）除了本机的 127.0.0.1:8765，另开一个只给手机用的本机端口 127.0.0.1:8766；
  Tailscale Serve（tailscale serve --bg --https=443 http://127.0.0.1:8766/<路径密钥>）把它放到 https://<Mac 的机器名>.<tailnet>.ts.net/：
  只有你自己 tailnet 里的设备（iPhone 装 Tailscale App）能打开，证书由 Tailscale 自动发（HTTPS）。
  绝不用 Tailscale Funnel（那会把页面公开到互联网）：run.py panel-phone 发现 Funnel 开着就拒绝；Funnel 来的请求面板一律 403。
  路径密钥（2026-10-07 起）：panel-phone on 生成的 32 位十六进制随机串（128 位），只记在数据目录的 panel_phone.json（0600）与 Tailscale 的 Serve 设置里；
  经 Serve 来的请求路径都是「/<路径密钥>/原来的路径」（手机的浏览器看不到它），面板先去掉它再按原来的路径处理。终端 / 页面 / 日志里不显示。
「你本人」= 按 Tailscale 账户登录（下面）或已配对的设备；都不是 → 只看到输入配对码的页面，什么数据都看不到。
配对（备用；别的账户 / 带 tag 的设备 / 关掉了按账户登录时用）：
  ① Mac 的本机面板 http://127.0.0.1:8765/ 的「手机」点「生成配对码」→ 8 位（不含 I O 0 1）、10 分钟内有效、只能用一次、
     输错 5 次作废。配对码只显示在 Mac 屏幕上（不打印到终端、日志、对话；文件里只存 HMAC 摘要）
  ② 手机打开 https://…ts.net/（或扫 Mac 屏幕上的二维码）→ 输入配对码 → 发这台设备的 cookie
     （qbd=<设备 id>.<令牌>；HttpOnly; Secure; SameSite=Strict; 180 天；文件里只存令牌的 SHA-256）
  ③ 手机上的每个写操作还要带这台设备的 CSRF 令牌（页面里 = HMAC(secret, 设备 id)；别的网站读不到）
  最多 5 台；Mac 的面板上可以取消任何一台，手机上可以「退出这台设备」；run.py panel-phone forget = 全部取消。
按 Tailscale 账户登录（2026-10-07 用户：「手机以后不用配对也能连：改成按 Tailscale 身份认证」；配对码保留为备用）：
  Tailscale Serve 把请求转给面板时，会先删掉请求里自带的 Tailscale-User-Login 等头，再按发请求的设备填上它的登录账户
  （带 tag 的设备、Funnel 来的请求不填；Funnel 来的另加 Tailscale-Funnel-Request）。手机端口只在下面全部成立时把请求当成「你本人」：
  ① 连过来的是本机回环地址（127.0.0.1 = Serve 转过来的；面板只监听 127.0.0.1）② 路径带着正确的路径密钥（= 经 Serve 来的）
  ③ 没有 Tailscale-Funnel-Request（有 → 整个请求拒绝）④ Host = panel-phone on 记下的手机地址
  ⑤ Tailscale-User-Login 头正好一个、与 panel-phone on 时这台 Mac 登录的 Tailscale 账户完全相同（ASCII 原样比；非 ASCII 只认 Serve 的
  RFC 2047 写法 =?utf-8?q?…?=）⑥ 明确打开着（panel_phone.json 里 identity = true；文件没了 / 坏了 = 关；panel-phone identity off / forget 关掉）。
  不成立 → 照旧要配对。写操作照旧要 CSRF 令牌（页面里 = HMAC(secret, 账户)），另外 Origin / Sec-Fetch-Site 必须是这个页面自己。
  照实写（剩下的风险）：Mac 上的程序都能连 127.0.0.1:8766，冒充还要知道路径密钥 —— 它只在 panel_phone.json（0600）与 Tailscale 的 Serve 设置里：
  同一个 Mac 用户的程序本来就能读面板令牌；这台 Mac 上有别人的 macOS 用户账户时，按 Tailscale 的装法他们可能读得到 Serve 设置
  → 第一次 panel-phone on 默认只用配对、status 会提醒（bash scripts/liveu.sh phone identity off = 只用配对）。
  另外：用你的账户登录 Tailscale 的每一台设备（不只是手机）都算你本人；手机丢了 → 先在 Tailscale 管理页把它删掉（Remove），再打开按账户登录。
  账户在这台 Mac 上换了 / 带上 tag：记下的账户只在 panel-phone on 时更新（mac_setup.sh 每次更新都会跑），status 会提醒不一样。
  账户名只存在数据目录的 panel_phone.json（0600），终端 / 页面 / 日志 / HALT 里只出现打码后的（例 ab***@e***.com），不入库。
手机能做的 = 本机面板能做的（只写手动指令；下单永远是执行器）＋「停止下单（HALT）」：只能建、不能解除
  （解除只在 Mac 上，用户明确说「恢复下单，删除 HALT」）。配对、取消别的设备只在 Mac 上。
数据目录里的文件（不入库；仓库的 var/panel_* 已 gitignore）：panel_devices.json（0600：secret、设备、配对码摘要、
  按账户登录关没关的选择 identity_off —— phone off 之后再 on 也记得）、
  panel_phone.json（0600：手机地址、路径密钥、这台 Mac 的 Tailscale 账户、按账户登录开没开 identity；panel-phone on 写、off 删）。
"""
from __future__ import annotations

import base64
import contextlib
import datetime as dt
import fcntl
import functools
import hashlib
import hmac
import ipaddress
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
from urllib.parse import urlparse

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
TS_LOGIN_H = "Tailscale-User-Login"                     # Serve 按发请求的设备填（先删掉请求里自带的）
TS_FUNNEL_H = "Tailscale-Funnel-Request"                # Funnel（公开到互联网）来的请求才有 → 一律拒绝
IDENT_PREFIX = "ts-"                                    # 按账户登录的「设备 id」（配对的设备 id 是 12 位十六进制，不会重）
_LOGIN = re.compile(r"[^\s@<>\"'`\\\x00-\x1f\x7f]{1,100}@[^\s@<>\"'`\\\x00-\x1f\x7f]{1,100}")
_QWORD = re.compile(r"=\?utf-8\?q\?([!->@-~]*)\?=")                        # Serve（Go 的 mime.QEncoding）对非 ASCII 账户的写法（只认这一种）
GATE_RE = re.compile(r"[0-9a-f]{32}")                                   # 路径密钥（Serve 的目标 http://127.0.0.1:8766/<路径密钥>）
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
    """全部取消（设备 + 在等的配对码），换掉 secret（旧的 CSRF 令牌全部失效），按 Tailscale 账户登录也关掉
    （「全部取消」= 手机都要重新配对；手机丢了 → 先在 Tailscale 管理页删掉那台手机，再 panel-phone identity on）。"""
    with _locked():
        d = _read()
        n = len(d["devices"])
        _write({"devices": {}, "secret": secrets.token_hex(32), "identity_off": True})
        _update_phone({"identity": False})
    log.info("手机配对：全部取消（%d 台）", n)
    return n


def cookie_set(value: str) -> str:
    return f"{COOKIE}={value}; Path=/; Max-Age={COOKIE_MAX_AGE}; HttpOnly; Secure; SameSite=Strict"


def cookie_clear() -> str:
    return f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict"


# ───────────────────────── 按 Tailscale 账户登录（不用配对；配对码留作备用） ─────────────────────────
def _valid_login(v) -> str | None:
    """像 Tailscale 的登录名（alice@example.com / alice@github / alice@passkey）→ 原样；带 tag 的设备（tagged-devices）/ 别的 → None。"""
    t = str(v or "").strip()
    return t if t and _LOGIN.fullmatch(t) else None


def _q_bytes(s: str) -> bytes:
    """RFC 2047 Q 编码的内容 → 字节（=XX 两位十六进制、_ = 空格、别的可见 ASCII 原样；别的写法 → ValueError）。"""
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == "=":
            h = s[i + 1:i + 3]
            if not re.fullmatch(r"[0-9A-Fa-f]{2}", h):
                raise ValueError("bad =XX")
            out.append(int(h, 16))
            i += 3
        elif c == "_":
            out.append(0x20)
            i += 1
        elif "!" <= c <= "~":
            out.append(ord(c))
            i += 1
        else:
            raise ValueError("bad char")
    return bytes(out)


def decode_login(raw: str | None) -> str | None:
    """Tailscale-User-Login 头的值 → 登录名；只认 Serve 的两种写法（别的 → None）：
    全是可见 ASCII → 原样（Serve 对 ASCII 不编码）；有非 ASCII → Go 的 mime.QEncoding「=?utf-8?q?…?=」（长的分成几段、段间一个空格），
    解出来必须是合法 UTF-8、而且真的含非 ASCII（Serve 不会把纯 ASCII 编码）。"""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or len(s) > 512:
        return None
    if s.startswith("=?"):
        try:
            words = [_QWORD.fullmatch(w) for w in s.split(" ")]
            if not all(words):
                return None
            t = b"".join(_q_bytes(m.group(1)) for m in words).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
        return _valid_login(t) if not t.isascii() else None
    if not all(" " <= c <= "~" for c in s) or "=?" in s:
        return None
    return _valid_login(s)


def mask_login(v) -> str:
    """登录名打码（终端 / 页面 / 日志 / HALT 里只用这个）：alice@example.com → al***@e***.com、bob@github → b***@g***。"""
    user, _, dom = str(v or "").partition("@")
    if not user or not dom:
        return "—"
    head, dot, tld = dom.rpartition(".")
    d = f"{head[:1]}***.{tld}" if dot and head and tld else f"{dom[:1]}***"
    return f"{user[:2] if len(user) > 3 else user[:1]}***@{d}"


def trusted_peer(addr) -> bool:
    """只信任本机回环地址连过来的请求（Tailscale Serve 转给 127.0.0.1:8766；面板也只监听 127.0.0.1）。"""
    try:
        return ipaddress.ip_address(str(addr or "").split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def hostport(v: str | None) -> str:
    """Host / Origin 的 host[:port]（小写；:443 去掉）。"""
    h = str(v or "").strip().lower()
    return h[:-4] if h.endswith(":443") else h


def _netloc(url: str | None) -> str:
    return hostport(urlparse(url).netloc) if url else ""


def gate() -> str | None:
    """路径密钥（panel-phone on 生成；Serve 的目标 = http://127.0.0.1:8766/<路径密钥>）；没有 / 不对 → None。不显示、不打印。"""
    g = str(_saved().get("gate") or "")
    return g if GATE_RE.fullmatch(g) else None


def split_gate(raw_path: str | None) -> tuple[bool, str]:
    """请求行里的路径 → (带着正确的路径密钥?, 去掉路径密钥之后的路径)。经 Serve 来的是「/<路径密钥>/原来的路径」；
    不带的原样返回（配对的设备照旧能用，但按账户登录不算）。"""
    p = str(raw_path or "")
    g = gate()
    if g and p.startswith("/"):
        head = "/" + g
        rest = p[len(head):]
        if hmac.compare_digest(p[:len(head)].encode("utf-8"), head.encode("utf-8")) and (rest == "" or rest[0] in "/?"):
            return True, rest if rest.startswith("/") else "/" + rest
    return False, p


def identity_off() -> bool:
    """用户选了只用配对（panel-phone identity off / forget；放在 panel_devices.json，phone off 之后再 on 也记得）。"""
    d = read_json(_path(), {}) or {}
    return isinstance(d, dict) and d.get("identity_off") is True


def _identity_choice(saved: dict) -> tuple[bool, str | None]:
    """panel-phone on 时按账户登录开不开 →（开?, 默认关的原因）：以前的选择（panel_phone.json → panel_devices.json）优先；
    第一次：开（用户 2026-10-07 要的），这台 Mac 上有别人的 macOS 用户账户 → 关（要开：phone identity on）。"""
    v = saved.get("identity")
    if isinstance(v, bool):
        return v, None
    d = read_json(_path(), {}) or {}
    if isinstance(d, dict) and isinstance(d.get("identity_off"), bool):
        return not d["identity_off"], None
    n = other_local_users()
    if n:
        return False, f"这台 Mac 上还有 {n} 个别的 macOS 用户账户 → 默认只用配对"
    return True, None


def set_identity(on: bool) -> None:
    """打开 / 关掉按 Tailscale 账户登录（只在 Mac 上：run.py panel-phone identity on|off）。两个文件都写：
    panel_phone.json 的 identity（请求时看它；文件没了 / 坏了 = 关）+ panel_devices.json 的 identity_off（phone off 之后也记得）。"""
    with _locked():
        d = _read()
        d["identity_off"] = not on
        _write(d)
        _update_phone({"identity": bool(on)})
    log.info("手机：按 Tailscale 账户登录 %s", "打开" if on else "关掉（只用配对）")


def identity_state() -> dict:
    """按 Tailscale 账户登录现在能不能用（给 status / 页面；账户只给打码后的）。"""
    saved = _saved()
    owner = _valid_login(saved.get("owner"))
    off = identity_off() or saved.get("identity") is False
    if off:
        why = "只用配对；要按账户登录：bash scripts/liveu.sh phone identity on"
    elif not phone_url():
        why = "手机访问没打开"
    elif not owner:
        why = str(saved.get("owner_why") or "还没记下这台 Mac 登录的 Tailscale 账户（bash scripts/liveu.sh phone on 之后才有）")
    elif saved.get("identity") is not True or not gate():
        why = "手机访问的设置是旧的（没有路径密钥）：bash scripts/liveu.sh phone on 更新一次"
    else:
        why = None
    return {"on": why is None, "off": off, "owner": mask_login(owner) if owner else None, "why": why}


def identity_for(headers, peer, path: str | None = None) -> dict | None:
    """手机端口的请求 → 按 Tailscale 账户登录的「设备」{"id","name","kind": "ts","login"}；不成立 → None（照旧要配对）。
    全部成立才算（见文件开头）：本机回环地址连过来；路径带着正确的路径密钥（path = 请求行里原样的路径）；不是 Funnel；
    Host = 记下的手机地址；Tailscale-User-Login 正好一个、与 panel-phone on 时这台 Mac 登录的账户完全相同；明确打开着。"""
    if headers is None or not trusted_peer(peer) or headers.get(TS_FUNNEL_H) is not None or not split_gate(path)[0]:
        return None
    vals = headers.get_all(TS_LOGIN_H) or []
    if len(vals) != 1:
        return None
    saved = _saved()
    url = phone_url()
    owner = _valid_login(saved.get("owner"))
    if (not url or not owner or saved.get("identity") is not True or identity_off()
            or hostport(headers.get("Host")) != _netloc(url)):
        return None
    who = decode_login(vals[0])
    if who is None or not hmac.compare_digest(who.encode("utf-8"), owner.encode("utf-8")):
        return None
    m = mask_login(owner)
    return {"id": IDENT_PREFIX + hashlib.sha256(owner.encode("utf-8")).hexdigest()[:10], "name": f"Tailscale 账户 {m}",
            "kind": "ts", "login": m, "created": None, "seen": None}


def other_local_users() -> int | None:
    """这台 Mac 上别人的 macOS 用户账户数（UID ≥ 501、不含自己；打开了「客人用户」也算 1 个）；不是 Mac / 查不到 → None。
    只数个数，不打印名字。"""
    if sys.platform != "darwin":
        return None
    try:
        r = subprocess.run(["dscl", ".", "-list", "/Users", "UniqueID"], capture_output=True, text=True, timeout=10)
        g = subprocess.run(["defaults", "read", "/Library/Preferences/com.apple.loginwindow", "GuestEnabled"],
                           capture_output=True, text=True, timeout=10)
    except Exception:                                        # noqa: BLE001
        return None
    if r.returncode != 0:
        return None
    me, n = os.getuid(), 0
    for ln in r.stdout.splitlines():
        parts = ln.split()
        if len(parts) >= 2 and re.fullmatch(r"-?\d+", parts[-1]) and int(parts[-1]) >= 501 and int(parts[-1]) != me:
            n += 1
    return n + (1 if g.returncode == 0 and g.stdout.strip() == "1" else 0)


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
    """tailscale status --json 里要用的几项（这台 Mac 的 DNS 名、MagicDNS、HTTPS 证书、这台 Mac 登录的账户 owner / 带不带 tag）。
    别的设备 / 账户信息不留不打印；owner 只记进数据目录的 panel_phone.json（0600），显示时只用 mask_login。"""
    rc, out, err = _ts(cli, "status", "--json")
    try:
        j = json.loads(out) if out.strip() else {}
    except ValueError:
        j = {}
    if not isinstance(j, dict) or not j:
        return {"ok": False, "err": (err or out or f"退出码 {rc}").strip()[:300]}
    me = j.get("Self") if isinstance(j.get("Self"), dict) else {}
    dns = str(me.get("DNSName") or "").rstrip(".").lower()
    tagged = bool(me.get("Tags"))
    users = j.get("User") if isinstance(j.get("User"), dict) else {}
    prof = users.get(str(me.get("UserID"))) if me.get("UserID") is not None else None
    owner = None if tagged else _valid_login((prof or {}).get("LoginName") if isinstance(prof, dict) else None)
    return {"ok": True, "state": str(j.get("BackendState") or ""), "dns": dns,
            "magicdns": bool((j.get("CurrentTailnet") or {}).get("MagicDNSEnabled")), "https": bool(j.get("CertDomains")),
            "version": str(j.get("Version") or ""), "owner": owner, "tagged": tagged}


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


def _write_phone(d: dict) -> None:
    p = paths.home() / PHONE_FILE
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def _save_phone(url: str, port: int, https_port: int, owner: str | None = None, why: str | None = None,
                gate: str | None = None, identity: bool = False) -> None:
    """记下手机地址、路径密钥、这台 Mac 登录的 Tailscale 账户、按账户登录开没开（数据目录 panel_phone.json，0600；不入库）。"""
    with _locked():
        _write_phone({"url": url, "port": int(port), "https_port": int(https_port), "owner": _valid_login(owner), "owner_why": why,
                      "gate": gate if GATE_RE.fullmatch(str(gate or "")) else None, "identity": identity is True,
                      "at": now_jst().isoformat(timespec="seconds")})


def _update_phone(kv: dict) -> None:
    """改 panel_phone.json 的几项（文件不在 / 坏了 → 不动：手机访问没打开）。调用的人要先拿着 _locked()。"""
    d = read_json(paths.home() / PHONE_FILE, None)
    if isinstance(d, dict):
        d.update(kv)
        _write_phone(d)


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


ADMIN_DNS = "https://login.tailscale.com/admin/dns"
ADMIN_MACHINES = "https://login.tailscale.com/admin/machines"
LOST_PHONE = (f"手机丢了的话：先在 Tailscale 管理页 {ADMIN_MACHINES} 把那台手机删掉（Remove）或让它退出登录，再打开按账户登录 —— "
              "那台手机只要还在你的 tailnet、还登录着你的账户，打开按账户登录之后它就又能用")


def _users_warning() -> list[str]:
    n = other_local_users()
    if not n:
        return []
    return [f"★ 这台 Mac 上还有 {n} 个别的 macOS 用户账户：按 Tailscale 的装法，他们的程序可能读得到 Serve 的设置（含路径密钥）、"
            "冒充你的账户 → 建议只用配对：bash scripts/liveu.sh phone identity off"]


def _identity_lines() -> list[str]:
    st = identity_state()
    if st["on"]:
        return [f"按 Tailscale 账户登录：开 —— 只认这台 Mac 登录的 Tailscale 账户（{st['owner']}）：用这个账户登录 Tailscale 的手机"
                "打开手机地址就能用、不用配对；别的账户 / 带 tag 的设备照旧要配对（配对码留作备用）。"
                "只关这一项：bash scripts/liveu.sh phone identity off"] + _users_warning()
    return [f"按 Tailscale 账户登录：{'关' if st['off'] else '现在不可用'}（{st['why']}）→ 手机要配对才能用"]


def _ours_old(proxy: str | None, port: int) -> bool:
    """qbreak 以前设的 Serve 目标：没有路径密钥的 http://127.0.0.1:8766（2026-10-06 版）或别的路径密钥（panel_phone.json 没了）。"""
    return bool(re.fullmatch(rf"http://127\.0\.0\.1:{int(port)}(?:/[0-9a-f]{{32}})?", _norm(proxy)))


def _owner_drift(info: dict, saved: dict) -> str | None:
    """这台 Mac 现在的 Tailscale 账户和 panel-phone on 时记下的不一样 → 提醒（只读；记下的只在 phone on 时更新）。"""
    rec = _valid_login(saved.get("owner"))
    if not info.get("ok") or not rec:
        return None
    if info.get("tagged"):
        now = "带 tag（没有用户账户）"
    elif info.get("owner") and info["owner"] != rec:
        now = f"登录的是 {mask_login(info['owner'])}"
    else:
        return None
    return (f"★ 这台 Mac 在 Tailscale 里现在{now}，和记下的账户（{mask_login(rec)}）不一样：按账户登录还认记下的那个 → "
            "bash scripts/liveu.sh phone on 更新一次")


def _open(url: str, open_panel: bool) -> None:
    """Mac 上用浏览器打开（NO_OPEN 存在 / 不是 Mac / 不要打开时不动）。"""
    if open_panel and sys.platform == "darwin" and not (paths.home() / "NO_OPEN").exists():
        try:
            subprocess.run(["open", url], timeout=20, capture_output=True, check=False)
        except Exception:                                    # noqa: BLE001
            pass


def cli(action: str = "status", port: int = PHONE_PORT, https_port: int = 443, yes: bool = False, out=print,
        open_panel: bool = True, confirm_name: str | None = None, wait_s: float = 20.0, value: str | None = None) -> int:
    """run.py panel-phone：on（打开手机访问）/ off（关闭）/ status（只读）/ forget（取消全部配对，按账户登录也关）/
    identity on|off（按 Tailscale 账户登录：打开 / 关掉，只用配对；不带值 = 只看）。
    从不打印配对码、路径密钥、完整的账户名（只打码后的）；只动 Tailscale Serve 的这一个 HTTPS 端口；Funnel 开着就拒绝。
    confirm_name：用户确认过可以公开的机器名（scripts/mac_setup.sh --phone <机器名>）—— 只有这台 Mac 的机器名正好是它才算确认。
    退出码：0 打开了 / 1 tailscale serve 失败 / 2 前提不满足（没装、没登录、Funnel、端口被占）/ 3 要确认机器名 / 4 要先打开 HTTPS。"""
    base = f"http://127.0.0.1:{int(port)}"
    out("── 手机操作（Tailscale Serve：只有你自己 Tailscale 里的设备能连；绝不用 Funnel）──")
    if value is not None and action != "identity":
        out(f"只有 identity 后面带 on / off（{action} 不带）")
        return 2
    if action == "forget":
        n = revoke_all()
        out(f"已取消全部 {n} 台设备的配对，按 Tailscale 账户登录也关了（手机上要重新配对：Mac 的操作面板「手机」→ 生成配对码）。"
            f"{LOST_PHONE}（bash scripts/liveu.sh phone identity on）")
        return 0
    if action == "identity":
        v = str(value or "").strip().lower()
        if v not in ("", "on", "off"):
            out(f"不认识的值 {value!r}（identity on / identity off）")
            return 2
        if v:
            set_identity(v == "on")
            out(f"已打开按 Tailscale 账户登录（{LOST_PHONE}）" if v == "on"
                else "已关掉按 Tailscale 账户登录：手机要配对才能用（已配对的设备照旧能用）")
        for ln in _identity_lines():
            out(ln)
        return 0
    saved = _saved()
    hp = int(saved.get("https_port") or https_port) if action in ("off", "status") else int(https_port)
    ts = find_cli()
    if ts is None:
        out("★ 没找到 tailscale 命令：Mac 上装 Tailscale（App Store 或 tailscale.com/download），登录；"
            "iPhone 上装 Tailscale App、用同一个账户登录")
        if action == "status":
            out(f"操作面板的手机端口 127.0.0.1:{port}：{'在监听' if listening(port) else '没在监听'}")
            for ln in _devices_lines() + _identity_lines():
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
    g = gate() or (secrets.token_hex(16) if action == "on" else None)      # 路径密钥：已有的照用；第一次 on 时生成
    target = f"{base}/{g}" if g else None
    ours = bool(target) and _norm(si["proxy"]) == _norm(target)
    old = not ours and _ours_old(si["proxy"], port)                       # qbreak 以前的设置（没有路径密钥 / 别的路径密钥）
    hide = (lambda t: t.replace(g, "<路径密钥>")) if g else (lambda t: t)  # tailscale 的报错里可能带目标：不显示路径密钥
    if action == "status":
        out(f"Tailscale：{info.get('state') or '—'}；这台 Mac：{host or '—'}；MagicDNS {'开' if info.get('magicdns') else '关'}；"
            f"HTTPS 证书 {'开' if info.get('https') else '关'}")
        addr = (url if ours else f"{url}（★ Serve 的设置是旧的（没有路径密钥）：bash scripts/liveu.sh phone on 更新一次；更新前按账户登录不能用）"
                if old else "没打开（bash scripts/liveu.sh phone on）")
        out(f"手机地址：{addr}"
            + ("；★ Funnel 开着（公开到互联网）：tailscale funnel --https=" + str(hp) + " off" if si["funnel"] else ""))
        out(f"操作面板的手机端口 127.0.0.1:{port}：{'在监听' if listening(port) else '没在监听（bash scripts/install_launchd_panel.sh 重启面板）'}")
        drift = _owner_drift(info, saved)
        for ln in _devices_lines() + _identity_lines() + ([drift] if drift else []):
            out(ln)
        return 0
    if action == "off":
        if ours or old:
            rc, o, e = _ts(ts, "serve", f"--https={hp}", "off")
            if rc != 0:
                out(f"★ 关闭失败（退出码 {rc}）：{hide((e or o).strip()[:300])}")
                return 1
            out(f"已关闭 Tailscale Serve 的 {hp} 端口：手机打不开了")
        else:
            out(f"Tailscale Serve 的 {hp} 端口不是 qbreak 的（或已经关了）：不动它")
        (paths.home() / PHONE_FILE).unlink(missing_ok=True)
        out("已配对的设备保留（重新打开：bash scripts/liveu.sh phone on；全部取消配对：bash scripts/liveu.sh phone forget）")
        return 0
    if action != "on":
        out(f"不认识的操作 {action!r}（on / off / status / forget / identity）")
        return 2
    # ── on ──
    if not info.get("magicdns") or not info.get("https"):
        out(f"★ 还要在 Tailscale 管理页 {ADMIN_DNS} 打开 MagicDNS 与 HTTPS Certificates（Enable HTTPS；只要点一次），再运行一次"
            + ("（已经在 Mac 的浏览器里打开了这一页）" if open_panel and sys.platform == "darwin" else ""))
        _open(ADMIN_DNS, open_panel)
        return 4
    if si["funnel"]:
        out(f"★ {host}:{hp} 开着 Funnel（公开到互联网）：先关掉 tailscale funnel --https={hp} off；qbreak 只用 Serve（只在你的 tailnet 里）")
        return 2
    if (si["proxy"] and not ours and not old) or si.get("other_root"):
        out(f"★ Tailscale Serve 的 {hp} 端口已经被别的服务用（{si['proxy'] or '文件 / 文本'}）：不覆盖。换一个端口："
            "bash scripts/liveu.sh phone on --https-port 8443")
        return 2
    name, _, tailnet = host.partition(".")
    named = str(confirm_name or "").strip().lower()
    if not ours and not old and not yes and _norm(saved.get("url")) != _norm(url) and named != name:
        if named:
            out(f"★ 这台 Mac 在 Tailscale 里的机器名是「{name}」，不是确认过的「{named}」：没有打开（机器名改过、或不是这台 Mac）")
        out(f"★ 第一次打开：HTTPS 证书会把机器名「{name}」与 tailnet 名「{tailnet}」写进公开的证书透明度日志"
            "（Certificate Transparency），任何人都能查到（查到也连不上：只有你 Tailscale 里的设备能连）。")
        out("  名字里有姓名等个人信息 → 先在 Tailscale 管理页 Machines → 这台 Mac → Edit machine name 改成不含个人信息的名字"
            "（例 qbreak-mac），再运行一次")
        out(f"  名字没问题 → bash scripts/mac_setup.sh --phone {name}（或 bash scripts/liveu.sh phone on --confirm-name {name}）")
        return 3
    deadline = time.monotonic() + max(0.0, float(wait_s))
    while not listening(port) and time.monotonic() < deadline:   # 刚重启的面板要几秒才起来
        time.sleep(1.0)
    if not listening(port):
        out(f"★ 操作面板没在监听手机端口 127.0.0.1:{port}（没运行、或还是旧版本）：bash scripts/install_launchd_panel.sh 重启面板。"
            "Serve 照样打开，面板起来之后手机就能连")
    if not ours:
        rc, o, e = _ts(ts, "serve", "--bg", f"--https={hp}", target, timeout=90)
        if rc != 0 and old:                                    # 不肯覆盖的老版本 tailscale：只关掉根路径，再设一次
            _ts(ts, "serve", f"--https={hp}", "--set-path=/", "off")
            rc, o, e = _ts(ts, "serve", "--bg", f"--https={hp}", target, timeout=90)
        if rc != 0:
            out(f"★ tailscale serve 失败（退出码 {rc}）：{hide((e or o).strip()[:400])}")
            return 1
        si = serve_info(ts, host, hp)
        if _norm(si["proxy"]) != _norm(target) or si["funnel"]:
            out("★ tailscale serve 之后的设置不对（没有指向面板，或 Funnel 开着）：bash scripts/liveu.sh phone status 看一下")
            return 1
    owner = info.get("owner")
    why = None if owner else ("这台 Mac 在 Tailscale 里带 tag（tagged device）：没有用户账户可以对照 → 只能配对" if info.get("tagged")
                              else "tailscale status 里没有这台 Mac 登录的账户 → 只能配对")
    choice, why_off = _identity_choice(saved)
    _save_phone(url, port, hp, owner, why, gate=g, identity=choice)
    out(f"手机访问已打开：{url}（Serve → 127.0.0.1:{port}，带路径密钥、不显示；只在你的 tailnet 里，不公开到互联网）"
        + ("。已把以前的 Serve 设置换成带路径密钥的" if old else ""))
    if why_off:
        out(f"按 Tailscale 账户登录默认没打开：{why_off}（确认没问题再打开：bash scripts/liveu.sh phone identity on）")
    if identity_state()["on"]:
        out("下一步：① iPhone 装 Tailscale App、用和这台 Mac 同一个账户登录、打开连接 ② Safari 打开上面的地址就能用"
            "（按 Tailscale 账户登录，不用配对码）③ Safari 的「共享 → 添加到主屏幕」可以像 App 一样打开。"
            "别的账户 / 带 tag 的设备：在 Mac 的操作面板 http://127.0.0.1:8765/ 的「手机」点「生成配对码」配对（备用）")
    else:
        out("下一步：① iPhone 装 Tailscale App、用同一个账户登录、打开连接 ② Safari 打开上面的地址 "
            "③ 在这台 Mac 的操作面板 http://127.0.0.1:8765/ 的「手机」点「生成配对码」，把 Mac 屏幕上的配对码输进手机（或扫二维码）"
            "④ Safari 的「共享 → 添加到主屏幕」可以像 App 一样打开（主屏幕上要求重新配对的话，再生成一次配对码）")
    for ln in _devices_lines() + _identity_lines():
        out(ln)
    _open("http://127.0.0.1:8765/#phone", open_panel)
    return 0


__all__ = ["new_code", "pair", "device_for", "csrf", "csrf_ok", "devices", "revoke", "revoke_all", "create_halt",
           "phone_url", "qr_data_uri", "touch_icon_png", "cli", "MANIFEST", "TS_HOST", "PHONE_PORT", "fmt_code",
           "identity_for", "identity_state", "set_identity", "identity_off", "decode_login", "mask_login", "trusted_peer",
           "hostport", "split_gate", "gate", "other_local_users", "TS_LOGIN_H", "TS_FUNNEL_H"]
