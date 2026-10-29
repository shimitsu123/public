"""webpush.py — 网页 App（主屏幕上的操作面板）的推送通知：Web Push（RFC 8030）+ 加密（RFC 8291 aes128gcm）+ VAPID（RFC 8292）。

只用 cryptography（已在依赖里）与标准库，不加新依赖。都在 Mac 的数据目录（~/.qbreak/home，不入库）：
  webpush_vapid.json   这台 Mac 的 VAPID 密钥对（0600；只用来证明推送是这台 Mac 发的，不是券商密钥）
  webpush_subs.json    订阅（手机的推送地址 + 加密公钥；0600）：{设备 id: {"endpoint", "keys": {"p256dh", "auth"}, "at", "name"}}
推送服务（Apple 的 web.push.apple.com 等）只看到加密后的内容。通知正文不放金额以外的敏感信息（与邮件通知同一段文字）。
iPhone 要 iOS 16.4 以上、面板要从「添加到主屏幕」的图标打开，并在页面上点「打开推送」允许通知。
"""
from __future__ import annotations

import base64
import contextlib
import fcntl
import json
import os
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import paths
from .utils import read_json, setup_logging

log = setup_logging("webpush")

VAPID_FILE, SUBS_FILE = "webpush_vapid.json", "webpush_subs.json"
SUBS_LOCK = "webpush_subs.lock"
_TLOCK = threading.Lock()
MAX_SUBS = 5
TTL_S = 24 * 3600


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def unb64u(s: str) -> bytes:
    s = str(s or "")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _write_private(name: str, obj) -> None:
    p = paths.home() / name
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def _vapid() -> tuple:
    """(私钥对象, 公钥的 base64url（未压缩 65 字节）)。没有就生成并存（0600）。"""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    d = read_json(paths.home() / VAPID_FILE, {}) or {}
    if d.get("private_pem"):
        key = serialization.load_pem_private_key(d["private_pem"].encode("ascii"), password=None)
    else:
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        _write_private(VAPID_FILE, {"private_pem": pem.decode("ascii"), "created": int(time.time())})
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return key, b64u(pub)


def public_key() -> str:
    """页面 pushManager.subscribe 的 applicationServerKey。"""
    return _vapid()[1]


@contextlib.contextmanager
def _subs_locked():
    """改订阅文件（读 → 改 → 写）时拿的锁：同一进程的线程（threading）+ 别的进程（flock；面板 / 执行器 / 自检都会发推送）。
    2026-10-24 复核：以前 send() 先读、发完（每台最多 15 秒）再整个写回 → 这期间新打开的推送被覆盖掉。"""
    with _TLOCK:
        p = paths.home() / SUBS_LOCK
        fd = os.open(p, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


def subs() -> dict:
    d = read_json(paths.home() / SUBS_FILE, {}) or {}
    return d if isinstance(d, dict) else {}


def _valid_endpoint(ep: str) -> bool:
    u = urllib.parse.urlparse(str(ep or ""))
    return u.scheme == "https" and bool(u.netloc) and len(ep) < 2000


def sub_id(endpoint: str) -> str:
    """订阅的 id = 推送地址的摘要（每个浏览器 / 主屏幕 App 一个；同一个 Tailscale 账户的几台设备不互相覆盖）。"""
    import hashlib
    return hashlib.sha256(str(endpoint).encode("utf-8")).hexdigest()[:16]


def subscribe(device: str | None, sub: dict, name: str = "") -> tuple[bool, str]:
    """存一个订阅（同一个推送地址覆盖）。校验 endpoint 是 https、p256dh 是 65 字节的 P-256 公钥、auth 16 字节。最多 MAX_SUBS 个。
    device：只用来记是哪台设备（名字），id 按推送地址。"""
    try:
        ep = str(sub.get("endpoint") or "")
        keys = sub.get("keys") or {}
        p256, auth = unb64u(keys.get("p256dh")), unb64u(keys.get("auth"))
    except Exception:                                      # noqa: BLE001
        return False, "订阅的格式不对"
    if not _valid_endpoint(ep) or len(p256) != 65 or p256[0] != 4 or len(auth) != 16:
        return False, "订阅的格式不对"
    with _subs_locked():
        d = subs()
        d[sub_id(ep)] = {"endpoint": ep, "keys": {"p256dh": b64u(p256), "auth": b64u(auth)}, "at": int(time.time()),
                          "name": str(name or "")[:40]}
        if len(d) > MAX_SUBS:
            for k in sorted(d, key=lambda k: d[k].get("at", 0))[:len(d) - MAX_SUBS]:
                d.pop(k, None)
        _write_private(SUBS_FILE, d)
    return True, "这台设备的推送已打开"


def unsubscribe(endpoint: str) -> bool:
    with _subs_locked():
        d = subs()
        if d.pop(sub_id(endpoint), None) is None:
            return False
        _write_private(SUBS_FILE, d)
    return True


def _hkdf(salt: bytes, ikm: bytes, info: bytes, n: int) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=hashes.SHA256(), length=n, salt=salt, info=info).derive(ikm)


def encrypt(payload: bytes, p256dh: bytes, auth: bytes, salt: bytes | None = None, as_key=None) -> bytes:
    """RFC 8291（aes128gcm，单个 record）→ 发给推送服务的正文。salt / as_key 只给测试用（固定向量）。"""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    as_key = as_key or ec.generate_private_key(ec.SECP256R1())
    as_pub = as_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    ua_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), p256dh)
    ecdh = as_key.exchange(ec.ECDH(), ua_pub)
    ikm = _hkdf(auth, ecdh, b"WebPush: info\x00" + p256dh + as_pub, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack("!I", 4096) + bytes([len(as_pub)]) + as_pub + body


def _jwt(aud: str, sub: str, key) -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    h = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    c = b64u(json.dumps({"aud": aud, "exp": int(time.time()) + 12 * 3600, "sub": sub}, separators=(",", ":")).encode())
    r, s = decode_dss_signature(key.sign(f"{h}.{c}".encode("ascii"), ec.ECDSA(hashes.SHA256())))
    return f"{h}.{c}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def _sub_claim() -> str:
    from .panel_phone import phone_url
    return (phone_url() or "https://qbreak.invalid/").rstrip("/")


def send_one(sub: dict, title: str, body: str, url: str = "/", opener=None) -> int:
    """发一条 → HTTP 状态码（201 / 200 成功；404 / 410 = 订阅已失效）。网络错误 → 0。"""
    key, pub = _vapid()
    ep = sub["endpoint"]
    u = urllib.parse.urlparse(ep)
    data = encrypt(json.dumps({"title": title[:120], "body": body[:600], "url": url}, ensure_ascii=False).encode("utf-8"),
                   unb64u(sub["keys"]["p256dh"]), unb64u(sub["keys"]["auth"]))
    req = urllib.request.Request(ep, data=data, method="POST", headers={
        "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": str(TTL_S), "Urgency": "high",
        "Authorization": f"vapid t={_jwt(f'{u.scheme}://{u.netloc}', _sub_claim(), key)}, k={pub}"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=15) as r:
            return int(getattr(r, "status", 201))
    except urllib.error.HTTPError as e:
        return int(e.code)
    except (OSError, ValueError):
        return 0


def send(title: str, body: str, url: str = "/", opener=None) -> bool | None:
    """发给全部订阅 → True 至少一个成功 / False 都失败 / None 没有订阅。失效的订阅（404 / 410）删掉。绝不抛。"""
    d = subs()
    if not d:
        return None
    ok, gone = False, []
    for dev, sub in list(d.items()):
        try:
            code = send_one(sub, title, body, url, opener)
        except Exception as e:                            # noqa: BLE001
            log.warning("推送失败：%s", type(e).__name__)
            continue
        if code in (200, 201, 202):
            ok = True
        elif code in (404, 410):
            gone.append((dev, sub.get("endpoint")))
        else:
            log.warning("推送失败：HTTP %s", code)
    if gone:                                               # 只删失效的那几个：拿锁、重新读（发的途中新打开 / 重新打开的不丢；2026-10-24 复核）
        try:
            with _subs_locked():
                cur = subs()
                hit = [dev for dev, ep in gone if dev in cur and cur[dev].get("endpoint") == ep]
                for dev in hit:
                    cur.pop(dev, None)
                if hit:
                    _write_private(SUBS_FILE, cur)
        except OSError as e:
            log.warning("删失效的推送订阅没成：%s", type(e).__name__)
    return ok
