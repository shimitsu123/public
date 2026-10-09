"""notify.py — 通知到手机（webhook / 邮件）+ 外部心跳（死人开关）。默认关闭：没有配置就什么都不发。

原版 README 的检查清单里写了「熔断时发通知，不要静默」，但代码里没有实现。这里给三样（值都是密钥：绝不打印、不记录、不提交，只说「有 / 没有」）：
  QBREAK_WEBHOOK   = https://...                     Discord / Slack（发 JSON）；主机名含 ntfy 的（ntfy.sh 或自建）发纯文本
  QBREAK_SMTP      = host:port:user:password:to      邮件（Gmail 需用应用专用密码；端口 465 = SMTP_SSL，其他端口 = STARTTLS；
                                                     密码里的空格去掉；to 可以逗号分隔多个，空 = 发给自己）
  QBREAK_HEARTBEAT = https://hc-ping.com/<uuid>      外部心跳（healthchecks.io 之类）：成功 POST 到这个地址、失败 POST 到「地址/fail」
来源：环境变量优先；没有时在 macOS 上从钥匙串读（服务名 qbreak-webhook / qbreak-smtp / qbreak-heartbeat，账户 qbreak）——
  定时任务（launchd）读不到 ~/.zshrc 的环境变量，所以 Mac 上放钥匙串。存法（你自己在终端，回车后输入，不要贴进聊天）：
    security add-generic-password -s qbreak-webhook -a qbreak -w
  邮件（Gmail）用 bash scripts/liveu.sh email-setup（setup_email：问发件地址 / 应用专用密码（不回显）/ 收件地址 → 存进钥匙串 → 发一封测试邮件）。
钥匙串的值只给这个进程用（进程内缓存），绝不打印。只用标准库，不增加依赖。通知 / 心跳失败绝不影响交易主流程（只记 warning，不含地址 / 密码）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import smtplib
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

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
SMTP_TIMEOUT = 20           # 邮件服务器的连接 / 应答超时（秒）
ABS_SETUP = "bash ~/qbreak-src/quant_breakout/scripts/liveu.sh email-setup"   # 你在新开的「终端」里运行（新窗口在 ~，不在仓库里）
EHLO_NAME = "localhost"                                       # SMTP 的 EHLO 名字（不用本机主机名）
GMAIL = ("smtp.gmail.com", 587)                               # email-setup 的默认发件服务器（STARTTLS）
APP_PW_URL = "https://myaccount.google.com/apppasswords"      # Gmail 应用专用密码（要先开两步验证）
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


class SmtpFormatError(ValueError):
    """qbreak-smtp / QBREAK_SMTP 的值格式不对（文字里不含密码 / 地址）。"""


def _why(e: BaseException) -> str:
    """失败的原因（只有类型 / HTTP 状态码 / SMTP 应答码：异常文字里可能带地址或账户，不记）。"""
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    if isinstance(e, urllib.error.URLError):
        return f"连不上（{type(e.reason).__name__}）"
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return (f"SMTP 认证失败（{e.smtp_code}）：发件地址或应用专用密码不对（Gmail 要先开两步验证、用应用专用密码；"
                "改过 Google 密码后旧的应用专用密码会失效）")
    if isinstance(e, smtplib.SMTPResponseException):
        return f"{type(e).__name__}（SMTP {e.smtp_code}）"
    if isinstance(e, ssl.SSLCertVerificationError):
        return "TLS 证书验证失败（SSLCertVerificationError）"
    if isinstance(e, socket.gaierror):
        return "找不到邮件服务器（DNS：gaierror）"
    if isinstance(e, (socket.timeout, TimeoutError)):
        return f"超时（{type(e).__name__}）"
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


_SEP = re.compile(r"[,;，；、\s]+")                              # 收件人之间：逗号 / 分号（半角、全角）/ 顿号 / 空白


def split_addrs(to: str) -> list[str]:
    """收件人字符串 → [地址…]（逗号 / 分号 / 顿号 / 空白分隔，去掉空的）。"""
    return [t for t in _SEP.split(to or "") if t]


def parse_smtp(conf: str) -> tuple[str, int, str, str, list[str]]:
    """「host:port:user:password:to」→ (host, port, user, password, [收件人…])。
    password 里不会有冒号（Gmail 应用专用密码是 16 位字母），所以按冒号切成 5 段；password 里的空格全部去掉
    （Google 把它显示成 4 组 4 位）；to 可以逗号分隔多个，空 = 发给自己（user）。格式不对 → SmtpFormatError（文字不含密码 / 地址）。"""
    parts = (conf or "").strip().split(":", 4)
    if len(parts) != 5:
        raise SmtpFormatError("不是 5 段")
    host, port_s, user, pw, to = parts
    host, user, pw = host.strip(), user.strip(), "".join(pw.split())
    try:
        port = int(port_s.strip())
    except ValueError:
        raise SmtpFormatError("端口不是数字") from None
    tos = split_addrs(to) or [user]
    if not host or not user or not pw or not 0 < port < 65536 or any("@" not in t or ":" in t for t in tos):
        raise SmtpFormatError("缺项或收件地址不对")
    return host, port, user, pw, tos


def _tls() -> ssl.SSLContext:
    """验证服务器证书的 TLS（smtplib 不给 context 时不验证证书 → 密码可能被中间人拿走）。
    python.org 版的 Python 没运行「Install Certificates」时系统根证书是空的 → 再加上 certifi 的根证书（装了 requests 就有）。"""
    ctx = ssl.create_default_context()
    try:
        import certifi                                        # 可选：没有就只用系统的根证书
        ctx.load_verify_locations(certifi.where())
    except Exception:                                         # noqa: BLE001
        pass
    return ctx


def _email(conf: str, subject: str, text: str) -> int:
    """发一封邮件 → 收件人个数。端口 465 = SMTP_SSL（隐式 TLS），其他端口 = STARTTLS；From 用 user；主题 / 正文 UTF-8；超时 20 秒。
    失败直接抛（send 只记 _why：不含密码 / 地址）。"""
    host, port, user, pw, tos = parse_smtp(conf)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(tos)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=user.rpartition("@")[2] if "@" in user else "localhost")   # 不用本机主机名
    msg.set_content(text, charset="utf-8", cte="base64")            # 7 位安全（smtplib 不声明 8BITMIME）
    # EHLO 的名字固定成 localhost：不给的话 smtplib 用 socket.getfqdn()（Mac 的主机名，会写进收件方的 Received: 头；
    # 而且 macOS 上反查主机名不受 20 秒超时管，可能每封卡几秒）
    if port == 465:
        with smtplib.SMTP_SSL(host, port, local_hostname=EHLO_NAME, timeout=SMTP_TIMEOUT, context=_tls()) as s:
            s.login(user, pw)
            s.send_message(msg, from_addr=user, to_addrs=tos)
    else:
        with smtplib.SMTP(host, port, local_hostname=EHLO_NAME, timeout=SMTP_TIMEOUT) as s:
            s.starttls(context=_tls())
            s.login(user, pw)
            s.send_message(msg, from_addr=user, to_addrs=tos)
    return len(tos)


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
            extra = "（格式应为 host:port:user:password:to）" if isinstance(e, SmtpFormatError) else ""
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


def mask_addr(addr: str) -> str:
    """邮件地址打码（ab***@example.com）：终端里也不整串显示。"""
    local, at, dom = (addr or "").partition("@")
    return (local[:2] if len(local) > 2 else local[:1]) + "***" + at + dom


def setup_email(host: str | None = None, port: int | None = None, *, run=None, ask=None, ask_secret=None,
                which=None, isatty=None, out=print) -> int:
    """bash scripts/liveu.sh email-setup（= run.py notify --setup-email）：只在你自己的终端里运行（不是 Claude 运行的命令）。
    问「发件地址」（回显）、「应用专用密码」（不回显）、「收件地址」（回车 = 同发件；多个用逗号）→
    拼成 host:port:user:password:to → 先用这个值发一封测试邮件 → 发成了才存进钥匙串 qbreak-smtp（-U 覆盖旧值），打印「已发 / 失败（原因）」。
    服务器拒绝（认证失败 = 密码不对 / 收件地址被拒 / 格式不对）→ 不存（钥匙串里原来的值不变；免得上线门槛 ⑧ 看到「有」就当通了）；
    只是网络问题（连不上 / 超时）→ 问你还要不要存。
    默认 Gmail（smtp.gmail.com:587，STARTTLS）；别的邮箱 --host / --port（465 = SMTP_SSL）。不打印密码、不写任何文件。
    run / ask / ask_secret / which / isatty：测试注入（代替 subprocess.run / input / getpass / shutil.which / stdin.isatty）。
    → 0 测试邮件已发且存好；1 测试邮件失败（存没存见输出）/ 存进钥匙串失败；2 不是 macOS、不是终端、输入不对或取消（什么都没存）。"""
    import getpass
    svc = KEYS["email"][1]
    if not (which or shutil.which)("security"):
        out("这台机器没有 security 命令（不是 macOS）：email-setup 只在 Mac 上用。"
            "别的机器上可以设环境变量 QBREAK_SMTP=host:port:user:password:to（不要提交、不要贴进聊天）")
        return 2
    try:
        tty = (isatty or sys.stdin.isatty)()
    except (AttributeError, ValueError, OSError):
        tty = False
    if not tty:
        out("要在你自己的终端里运行（会问应用专用密码，输入时不显示）：打开「终端」App，运行 " + ABS_SETUP + "。"
            "密码不要贴进 Claude 的对话")
        return 2
    gmail = host is None or host.strip().lower() == GMAIL[0]
    host = (host or GMAIL[0]).strip()
    port = int(port or GMAIL[1])
    if not host or ":" in host or not 0 < port < 65536:
        out("发件服务器 / 端口不对：例 --host smtp.example.com --port 465")
        return 2
    out(f"── 邮件通知设置：发件服务器 {host}:{port}（{'SMTP_SSL' if port == 465 else 'STARTTLS'}）；"
        f"存进钥匙串 {svc}，不写文件、不打印密码 ──")
    if gmail:
        out(f"Gmail：先开两步验证，再在 {APP_PW_URL} 建一个应用专用密码（16 位字母）；改 Google 密码会让应用专用密码失效（失效后再运行这条）")
    ask = ask or input
    ask_secret = ask_secret or getpass.getpass
    try:
        user = (ask("发件 Gmail 地址：" if gmail else "发件邮箱地址：") or "").strip()
        if "@" not in user or any(c in ":,;" or c.isspace() for c in user):
            out("发件地址不对（要像 ……@gmail.com）：什么都没存")
            return 2
        pw = "".join((ask_secret("应用专用密码（16 位，输入时不显示）：" if gmail else "SMTP 密码（输入时不显示）：") or "").split())
        if not pw:
            out("没有输入密码：什么都没存")
            return 2
        if ":" in pw:
            out("密码里有冒号：这个格式存不了（Gmail 的应用专用密码是 16 位字母）：什么都没存")
            return 2
        if gmail and not (len(pw) == 16 and pw.isascii() and pw.isalpha()):
            out(f"Gmail 的应用专用密码是 16 位字母（显示成 4 组 4 位，空格会自动去掉）；你输入的不是（是不是输了 Google 账户的密码？）"
                f"：什么都没存。在 {APP_PW_URL} 建一个再运行")
            return 2
        tos = split_addrs(ask("收件地址（多个用逗号隔开；回车 = 同发件）：") or "") or [user]
    except (EOFError, KeyboardInterrupt):
        out("\n已取消：什么都没存")
        return 2
    if any("@" not in t or ":" in t for t in tos):
        out("收件地址不对（要像 name@example.com，多个用逗号隔开）：什么都没存")
        return 2
    value = f"{host}:{port}:{user}:{pw}:{','.join(tos)}"
    from .calendar_jp import now_jst
    body = (f"这是 qbreak 的测试邮件（{now_jst():%Y-%m-%d %H:%M} JST）：收到了就说明邮件通知通了。\n"
            "之后执行器停下、09:30 自检没通过、有状态不明的单等会发到这个地址。\n"
            "建议在 Gmail 建一个过滤器：主题含 qbreak → 不要送进垃圾邮件、标星。")
    out("先用这个设置发一封测试邮件（发成了才存进钥匙串）……")
    n, store = 0, True
    try:
        n = _email(value, "qbreak 测试邮件", body)
    except Exception as e:                                    # noqa: BLE001
        net = isinstance(e, OSError) and not isinstance(e, (smtplib.SMTPException, ssl.SSLError))   # 连不上 / 超时 / DNS
        if not net:
            out(f"★ 测试邮件：失败（{_why(e)}）：什么都没存（钥匙串里原来的值不变）。改好后再运行 {ABS_SETUP}")
            return 1
        try:
            yes = (ask(f"测试邮件没发出去（网络：{_why(e)}）：设置本身可能是对的。仍然存进钥匙串吗？[y/N] ") or "").strip().lower()
        except (EOFError, KeyboardInterrupt):
            yes = ""
        if yes not in ("y", "yes"):
            out(f"什么都没存（钥匙串里原来的值不变）：网络好了再运行 {ABS_SETUP}")
            return 1
        store = False                                     # 存，但测试没发成 → 退出 1
    # 值经 argv 交给 security：运行的一瞬间同一台 Mac 的进程列表里看得到（macOS 上 security 的通常用法，可以接受）；
    # 只写 -w 不带值让 security 自己问的话，要你再输一遍整串 host:port:user:password:to，不友好
    try:
        r = (run or subprocess.run)(["security", "add-generic-password", "-U", "-s", svc, "-a", ACCOUNT, "-w", value],
                                    capture_output=True, text=True, timeout=120)
        rc = r.returncode
    except (OSError, subprocess.SubprocessError) as e:
        rc, why = None, type(e).__name__
    else:
        why = f"security 退出码 {rc}"
    if rc != 0:
        out((f"测试邮件：已发（{n} 个收件地址），但" if store else "")
            + f"★ 存进钥匙串失败（{why}）：钥匙串锁着的话先解锁（或重新登录 Mac）再运行 {ABS_SETUP}")
        return 1
    _CACHE.pop("email", None)
    out(f"已存进钥匙串 {svc}：发件 {mask_addr(user)} → 收件 {len(tos)} 个（{'、'.join(mask_addr(t) for t in tos)}）")
    if (os.environ.get(KEYS["email"][0]) or "").strip():
        out("（提醒：环境变量 QBREAK_SMTP 也有设置——在终端里它优先；定时任务读不到 ~/.zshrc，用钥匙串里刚存的）")
    if not store:
        out("★ 测试邮件没发成（网络）：网络好了用 bash scripts/liveu.sh notify-test 再试")
        return 1
    out(f"测试邮件：已发（{n} 个收件地址）。几分钟内没收到 → 看垃圾邮件；之后可以用 bash scripts/liveu.sh notify-test 再试")
    return 0


__all__ = ["send", "heartbeat", "channels", "configured", "get", "reset", "is_ntfy", "KEYS",
           "parse_smtp", "split_addrs", "setup_email", "mask_addr", "SmtpFormatError"]
