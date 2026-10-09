"""notify.py — 通知到手机（webhook / 邮件）+ 外部心跳（死人开关）。默认关闭：没有配置就什么都不发。

原版 README 的检查清单里写了「熔断时发通知，不要静默」，但代码里没有实现。这里给三样（值都是密钥：绝不打印、不记录、不提交，只说「有 / 没有」）：
  QBREAK_WEBHOOK   = https://...                     Discord / Slack（发 JSON）；主机名含 ntfy 的（ntfy.sh 或自建）发纯文本
  QBREAK_SMTP      = host:port:user:password:to      邮件（Gmail 需用应用专用密码）
  QBREAK_HEARTBEAT = https://hc-ping.com/<uuid>      外部心跳（healthchecks.io 之类）：成功 POST 到这个地址、失败 POST 到「地址/fail」
来源：环境变量优先；没有时在 macOS 上从钥匙串读（服务名 qbreak-webhook / qbreak-smtp / qbreak-heartbeat，账户 qbreak）——
  定时任务（launchd）读不到 ~/.zshrc 的环境变量，所以 Mac 上放钥匙串。存法（你自己在终端，回车后输入，不要贴进聊天）：
    security add-generic-password -s qbreak-webhook -a qbreak -w
钥匙串的值只给这个进程用（进程内缓存），绝不打印。只用标准库，不增加依赖。通知 / 心跳失败绝不影响交易主流程（只记 warning，不含地址 / 密码）。
"""
from __future__ import annotations

import json
import os
import smtplib
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

from .utils import setup_logging

log = setup_logging("notify")

ACCOUNT = "qbreak"
KEYS = {"webhook": ("QBREAK_WEBHOOK", "qbreak-webhook"),       # 通道名 → (环境变量, 钥匙串服务名)
        "email": ("QBREAK_SMTP", "qbreak-smtp"),
        "heartbeat": ("QBREAK_HEARTBEAT", "qbreak-heartbeat")}
LABEL = {"webhook": "webhook", "email": "邮件", "heartbeat": "外部心跳"}
MAX_CHARS = 1900            # Discord 一条最多 2,000 字
MAX_NTFY_BYTES = 3900       # ntfy 一条超过 4,096 字节会变成附件
MAX_BEAT = 1000             # 心跳附带的说明
KEYCHAIN = True             # 不指定 run 时在 macOS 上读钥匙串；环境变量 QBREAK_NO_KEYCHAIN=1 也关掉
                            # （tests/conftest.py 设：在 Mac 上跑测试，连子进程在内都绝不发真的通知 / 心跳）
_CACHE: dict[str, str] = {}


def _keychain(service: str, run=None) -> str | None:
    """钥匙串里的值（只给进程内用，绝不打印 / 记录）。没有 security 命令 / 没存 / 失败 / 超时（5 秒）→ None。"""
    try:
        r = (run or subprocess.run)(["security", "find-generic-password", "-s", service, "-a", ACCOUNT, "-w"],
                                    capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return (r.stdout or "").strip() or None


def _use_keychain(run) -> bool:
    return run is not None or (KEYCHAIN and sys.platform == "darwin" and os.environ.get("QBREAK_NO_KEYCHAIN") != "1")


def get(name: str, run=None) -> str | None:
    """通道 name（webhook / email / heartbeat）的设置值：环境变量 → 钥匙串（macOS；找到的值进程内缓存）→ None。
    run：测试注入（代替 subprocess.run）。返回的值是密钥：只拿来发送，绝不打印。"""
    env, svc = KEYS[name]
    v = (os.environ.get(env) or "").strip()
    if v:
        return v
    if name in _CACHE:
        return _CACHE[name]
    if not _use_keychain(run):
        return None
    v = _keychain(svc, run)
    if v:                                                     # 没找到不缓存：常驻的面板进程里，之后存进钥匙串也能用上
        _CACHE[name] = v
    return v


def reset() -> None:
    """清掉进程内缓存（测试用）。"""
    _CACHE.clear()


def configured(name: str, run=None, env: bool = True) -> bool | None:
    """有没有设置（只查有没有，绝不取出值：security 不加 -w）。env=False：只看钥匙串（上线检查用：定时任务读不到 ~/.zshrc 的环境变量）。
    → True / False；没有钥匙串可查（不是 macOS / 没有 security 命令）且环境变量也没有 → None。"""
    var, svc = KEYS[name]
    if env and (os.environ.get(var) or "").strip():
        return True
    if env and name in _CACHE:
        return True
    if not _use_keychain(run):
        return None
    try:
        r = (run or subprocess.run)(["security", "find-generic-password", "-s", svc, "-a", ACCOUNT],
                                    capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.returncode == 0


def channels(run=None, env: bool = True) -> dict[str, bool]:
    """{webhook / email / heartbeat: 有没有设置}（只查有没有，不取出值、不打印值）。"""
    return {n: bool(configured(n, run, env)) for n in KEYS}


def _why(e: BaseException) -> str:
    """失败的原因（只有类型 / HTTP 状态码：异常文字里可能带地址或账户，不记）。"""
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    if isinstance(e, urllib.error.URLError):
        return f"连不上（{type(e.reason).__name__}）"
    return type(e).__name__


def _clip_bytes(s: str, n: int) -> str:
    b = s.encode("utf-8")
    return s if len(b) <= n else b[:n].decode("utf-8", "ignore")


def is_ntfy(url: str) -> bool:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return False
    return "ntfy" in host.lower()


def _post(url: str, data: bytes, headers: dict, timeout: float = 10) -> None:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        r.read()


def _webhook(url: str, subject: str, text: str, level: str) -> None:
    if is_ntfy(url):                                          # ntfy：纯文本（第一行标题 + 正文）；warn / error 用高优先级
        body = _clip_bytes(f"{subject}\n{text}", MAX_NTFY_BYTES)
        h = {"Content-Type": "text/plain; charset=utf-8"}
        if level in ("warn", "error"):
            h["Priority"] = "high"
        _post(url, body.encode("utf-8"), h)
        return
    body = f"[{level.upper()}] {subject}\n{text}"[:MAX_CHARS]  # Discord 读 content、Slack 读 text
    _post(url, json.dumps({"content": body, "text": body}).encode(),
          {"Content-Type": "application/json"})


def _email(conf: str, subject: str, text: str) -> None:
    host, port, user, pw, to = conf.split(":", 4)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(text)
    with smtplib.SMTP(host, int(port), timeout=20) as s:
        s.starttls()
        s.login(user, pw)
        s.send_message(msg)


def send(subject: str, text: str, level: str = "info", run=None) -> dict[str, bool | None]:
    """按设置了的通道发一条通知 → {webhook / email: True 发了 / False 失败 / None 没设置}。绝不抛（失败只记 warning）。"""
    out: dict[str, bool | None] = {}
    for name in ("webhook", "email"):
        try:
            conf = get(name, run)
        except Exception:                                     # noqa: BLE001
            conf = None
        if not conf:
            out[name] = None
            continue
        try:
            if name == "webhook":
                _webhook(conf, subject, text, level)
            else:
                _email(conf, subject, text)
            out[name] = True
        except Exception as e:                                # noqa: BLE001
            extra = "（格式应为 host:port:user:password:to）" if name == "email" and isinstance(e, ValueError) else ""
            log.warning("%s 通知失败：%s%s", LABEL[name], _why(e), extra)
            out[name] = False
    return out


def heartbeat(ok: bool, msg: str = "", run=None) -> bool | None:
    """外部心跳（healthchecks.io 之类）：设置了 → 成功 POST 到地址、失败 POST 到「地址/fail」（正文 msg，≤ 1,000 字）。
    → True 发了 / False 没发成 / None 没设置。绝不抛。"""
    try:
        url = get("heartbeat", run)
    except Exception:                                         # noqa: BLE001
        url = None
    if not url:
        return None
    try:
        _post(url.rstrip("/") + ("" if ok else "/fail"), str(msg or "")[:MAX_BEAT].encode("utf-8"),
              {"Content-Type": "text/plain; charset=utf-8"})
        return True
    except Exception as e:                                    # noqa: BLE001
        log.warning("外部心跳没发成：%s", _why(e))
        return False


__all__ = ["send", "heartbeat", "channels", "configured", "get", "reset", "is_ntfy", "KEYS"]
