"""notify.py — 通知（通知 / notification）。默认关闭，靠环境变量开启。

原版 README 的检查清单里写了「熔断时发通知，不要静默」，但代码里没有实现。
这里给两条最省事的通道：
  QBREAK_WEBHOOK  = https://...   （Discord / Slack / LINE Notify 兼容的 POST）
  QBREAK_SMTP     = host:port:user:password:to   （Gmail 需用应用专用密码）
两者都只用标准库，不增加依赖。通知失败绝不影响交易主流程。
"""
from __future__ import annotations

import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage

from .utils import setup_logging

log = setup_logging("notify")


def _webhook(text: str) -> None:
    url = os.environ.get("QBREAK_WEBHOOK")
    if not url:
        return
    # Discord/Slack 都接受 {"content"/"text": ...}；LINE Notify 用 form 的 message 字段
    body = json.dumps({"content": text, "text": text}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:   # noqa: S310
        r.read()


def _email(subject: str, text: str) -> None:
    conf = os.environ.get("QBREAK_SMTP")
    if not conf:
        return
    host, port, user, pw, to = conf.split(":", 4)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(text)
    with smtplib.SMTP(host, int(port), timeout=20) as s:
        s.starttls()
        s.login(user, pw)
        s.send_message(msg)


def send(subject: str, text: str, level: str = "info") -> None:
    body = f"[{level.upper()}] {subject}\n{text}"
    for fn, name in ((lambda: _webhook(body), "webhook"),
                     (lambda: _email(subject, text), "email")):
        try:
            fn()
        except Exception as e:                    # noqa: BLE001
            log.warning("%s 通知失败: %s", name, e)
