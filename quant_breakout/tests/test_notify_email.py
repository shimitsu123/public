"""邮件通知（2026-10-09 用户选「手机通知用邮件」：spec E）：
① qbreak-smtp 的值「host:port:user:password:to」的解析：密码里的空格去掉、多个收件人、空 = 发给自己、格式不对；
② 发送：端口 465 = SMTP_SSL（隐式 TLS），其他端口 = STARTTLS；都验证证书；From = user；主题 / 正文 UTF-8；超时 20 秒；
   失败只记原因（不含密码 / 地址）、绝不抛；
③ email-setup（notify.setup_email / run.py notify --setup-email / liveu.sh email-setup）：不是 macOS、不是终端、输入不对 → 什么都不存；
   存进钥匙串（-U 覆盖）→ 发一封测试邮件；不打印密码与完整地址。
全部用假的 smtplib / security / 输入，不联网、不调真的 security。"""
import logging
import smtplib
import ssl
from email import message_from_bytes, policy

import pytest

from qbreak import notify

PW = "abcd efgh ijkl mnop"                 # Google 显示成 4 组 4 位
PW_RAW = "abcdefghijklmnop"


class _FakeSMTP:
    """假的 smtplib.SMTP / SMTP_SSL：记下连接参数、starttls 的 context、login、发出的邮件。"""
    made: list = []
    fail_login: Exception | None = None

    def __init__(self, host, port, timeout=None, context=None, local_hostname=None, **kw):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.local_hostname = local_hostname                                        # EHLO 的名字（不给 = 本机主机名）
        self.tls_ctx, self.logins, self.sent = None, [], []
        self.ssl = False
        _FakeSMTP.made.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.tls_ctx = context

    def login(self, user, pw):
        if _FakeSMTP.fail_login is not None:
            raise _FakeSMTP.fail_login
        self.logins.append((user, pw))

    def send_message(self, msg, from_addr=None, to_addrs=None):
        self.sent.append((msg, from_addr, list(to_addrs or [])))


class _FakeSSL(_FakeSMTP):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.ssl = True


@pytest.fixture
def smtp(monkeypatch):
    _FakeSMTP.made, _FakeSMTP.fail_login = [], None
    monkeypatch.setattr(notify.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", _FakeSSL)
    return _FakeSMTP


def _verified(ctx) -> bool:
    return isinstance(ctx, ssl.SSLContext) and ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname


# ────────── ① 解析 ──────────
def test_parse_strips_password_spaces_and_splits_recipients():
    assert notify.parse_smtp(f"smtp.gmail.com:587:me@example.com:{PW}:a@x.com, b@y.jp") == \
        ("smtp.gmail.com", 587, "me@example.com", PW_RAW, ["a@x.com", "b@y.jp"])
    assert notify.parse_smtp(f" smtp.gmail.com : 465 : me@example.com :{PW}: ")[1:] == (465, "me@example.com", PW_RAW, ["me@example.com"])
    assert notify.parse_smtp("h:25:u@d:p:a@x；b@y，c@z、d@w;e@v")[4] == ["a@x", "b@y", "c@z", "d@w", "e@v"]
    for bad in ("h:587:u@d:pw", "h:notaport:u@d:pw:to@x", "h:587:u@d::to@x", ":587:u@d:pw:to@x", "h:0:u@d:pw:to@x",
                "h:587:u@d:pw:not-an-address", "", "h:587:u@d:pw:a@x:extra"):
        with pytest.raises(notify.SmtpFormatError):
            notify.parse_smtp(bad)
    assert issubclass(notify.SmtpFormatError, ValueError)


# ────────── ② 发送 ──────────
def test_starttls_on_587_with_verified_tls_utf8_and_many_recipients(monkeypatch, smtp):
    monkeypatch.setenv("QBREAK_SMTP", f"smtp.gmail.com:587:me@example.com:{PW}:a@x.com,b@y.jp")
    assert notify.send("qbreak 立花实盘 ★ 执行器停下", "原因：行情落后（¥1,000,000）", "warn") == {"webhook": None, "email": True}
    (s,) = smtp.made
    assert (s.host, s.port, s.timeout, s.ssl) == ("smtp.gmail.com", 587, notify.SMTP_TIMEOUT, False) and s.timeout == 20
    assert s.local_hostname == "localhost"                                            # EHLO 不带 Mac 的主机名
    assert _verified(s.tls_ctx)                                                       # STARTTLS 也验证证书（smtplib 默认不验证）
    assert s.logins == [("me@example.com", PW_RAW)]                                     # 空格去掉
    msg, frm, tos = s.sent[0]
    assert frm == "me@example.com" and tos == ["a@x.com", "b@y.jp"]
    m = message_from_bytes(msg.as_bytes(), policy=policy.default)                    # 真的序列化一遍：中文主题 / 正文能还原
    assert m["Subject"] == "qbreak 立花实盘 ★ 执行器停下" and m["From"] == "me@example.com"
    assert m["To"] == "a@x.com, b@y.jp" and m["Date"] and m["Message-ID"].endswith("@example.com>")
    assert m.get_content_charset() == "utf-8" and m.get_content().strip() == "原因：行情落后（¥1,000,000）"
    assert msg.as_bytes().isascii()                                                    # 整封信 7 位（不依赖服务器的 8BITMIME）


def test_port_465_uses_smtp_ssl(monkeypatch, smtp):
    monkeypatch.setenv("QBREAK_SMTP", f"smtp.gmail.com:465:me@example.com:{PW}:")
    assert notify.send("t", "x")["email"] is True
    (s,) = smtp.made
    assert s.ssl and s.port == 465 and s.tls_ctx is None and _verified(s.context)    # 隐式 TLS：不再 STARTTLS
    assert s.local_hostname == "localhost"
    assert s.logins == [("me@example.com", PW_RAW)] and s.sent[0][2] == ["me@example.com"]   # 收件人空 = 发给自己


def _log(caplog, fn):
    lg = logging.getLogger("qbreak")                                                  # qbreak 的日志不往根传：直接挂上 caplog
    lg.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="qbreak"):
            return fn()
    finally:
        lg.removeHandler(caplog.handler)


def test_failures_only_log_the_reason_without_password_or_address(monkeypatch, smtp, caplog):
    monkeypatch.setenv("QBREAK_SMTP", f"smtp.gmail.com:587:me@example.com:{PW}:a@x.com")
    smtp.fail_login = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted me@example.com")
    assert _log(caplog, lambda: notify.send("t", "x")) == {"webhook": None, "email": False}
    text = caplog.text
    assert "SMTP 认证失败（535）" in text and "应用专用密码" in text and "格式应为" not in text
    assert "abcd" not in text and "me@example" not in text and "a@x.com" not in text
    caplog.clear()
    smtp.fail_login = ssl.SSLCertVerificationError("certificate verify failed: smtp.gmail.com")   # 也是 ValueError 的子类
    assert _log(caplog, lambda: notify.send("t", "x"))["email"] is False
    assert "TLS 证书验证失败" in caplog.text and "格式应为" not in caplog.text
    caplog.clear()
    monkeypatch.setenv("QBREAK_SMTP", "smtp.gmail.com:587:me@example.com")
    assert _log(caplog, lambda: notify.send("t", "x"))["email"] is False
    assert "格式应为 host:port:user:password:to" in caplog.text and "me@example" not in caplog.text


# ────────── ③ email-setup ──────────
class _Kc:
    """假的 security：记下参数；rc = 退出码。"""

    def __init__(self, rc=0):
        self.rc, self.calls = rc, []

    def __call__(self, args, **kw):
        import subprocess
        self.calls.append(list(args))
        return subprocess.CompletedProcess(args, self.rc, "", "")


def _setup(answers, secret=PW, kc=None, host=None, port=None, tty=True, which="/usr/bin/security"):
    lines, asked = [], []
    it = iter(answers)

    def ask(prompt):
        asked.append(prompt)
        v = next(it)
        if isinstance(v, BaseException):
            raise v
        return v

    def ask_secret(prompt):
        asked.append(prompt)
        return secret
    kc = kc if kc is not None else _Kc()
    rc = notify.setup_email(host, port, run=kc, ask=ask, ask_secret=ask_secret, which=lambda n: which,
                            isatty=lambda: tty, out=lines.append)
    return rc, kc, "\n".join(lines), asked


def test_setup_stores_in_keychain_and_sends_a_test_mail(monkeypatch, smtp):
    monkeypatch.setattr(notify, "_CACHE", {"email": "old-value"})
    rc, kc, out, asked = _setup(["me@example.com", "a@x.com, b@y.jp"])
    assert rc == 0
    assert kc.calls == [["security", "add-generic-password", "-U", "-s", "qbreak-smtp", "-a", "qbreak", "-w",
                         f"smtp.gmail.com:587:me@example.com:{PW_RAW}:a@x.com,b@y.jp"]]       # -U 覆盖旧值；空格去掉
    assert "email" not in notify._CACHE                                              # 进程内的旧值不再用
    assert any("不显示" in a for a in asked)
    (s,) = smtp.made
    assert (s.host, s.port, s.ssl) == ("smtp.gmail.com", 587, False) and _verified(s.tls_ctx)
    msg, frm, tos = s.sent[0]
    assert frm == "me@example.com" and tos == ["a@x.com", "b@y.jp"] and msg["Subject"] == "qbreak 测试邮件"
    assert "测试邮件：已发（2 个收件地址）" in out and "apppasswords" in out and "STARTTLS" in out
    assert "abcd" not in out and PW_RAW not in out                                   # 不打印密码
    assert "me@example.com" not in out and "a@x.com" not in out and "m***@example.com" in out    # 地址打码


def test_setup_blank_recipient_means_self_and_other_host_465(smtp):
    rc, kc, out, _ = _setup(["me@example.com", ""])
    assert rc == 0 and kc.calls[0][-1].endswith(":me@example.com") and smtp.made[-1].sent[0][2] == ["me@example.com"]
    rc, kc, out, asked = _setup(["me@example.com", "you@example.com"], secret="short pw", host="smtp.example.com", port=465)
    assert rc == 0 and kc.calls[0][-1] == "smtp.example.com:465:me@example.com:shortpw:you@example.com"
    assert smtp.made[-1].ssl and "SMTP_SSL" in out and "apppasswords" not in out and "发件邮箱地址：" in asked


@pytest.mark.parametrize("answers,secret,why", [
    (["not-an-address"], PW, "发件地址不对"),
    (["me@example.com"], "", "没有输入密码"),
    (["me@example.com"], "abcd:efgh", "冒号"),
    (["me@example.com"], "MyGooglePassword1", "16 位字母"),                          # Gmail：不像应用专用密码 → 不存
    (["me@example.com", "broken"], PW, "收件地址不对"),
    ([EOFError()], PW, "已取消"),
    (["me@example.com", KeyboardInterrupt()], PW, "已取消"),
])
def test_setup_bad_input_stores_nothing(smtp, answers, secret, why):
    rc, kc, out, _ = _setup(answers, secret=secret)
    assert rc == 2 and kc.calls == [] and not smtp.made and why in out and "什么都没存" in out


def test_setup_refuses_off_macos_or_off_terminal(smtp):
    rc, kc, out, asked = _setup([], which=None)
    assert rc == 2 and not kc.calls and not asked and "不是 macOS" in out and "QBREAK_SMTP" in out
    rc, kc, out, asked = _setup([], tty=False)
    assert rc == 2 and not kc.calls and not asked and "自己的终端" in out             # Claude 的工具里没有终端：不问密码
    rc, kc, out, asked = _setup([], host="smtp.example.com", port=70000)
    assert rc == 2 and not kc.calls and "端口不对" in out


def test_setup_keychain_or_test_mail_failure(smtp):
    rc, kc, out, _ = _setup(["me@example.com", ""], kc=_Kc(rc=45))
    assert rc == 1 and "存进钥匙串失败（security 退出码 45）" in out and smtp.made           # 先发测试邮件、再存
    smtp.fail_login = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    rc, kc, out, _ = _setup(["me@example.com", ""])
    assert rc == 1 and kc.calls == [] and "★ 测试邮件：失败（SMTP 认证失败（535）" in out   # 服务器拒了：不存（gate ⑧ 不会误显示 OK）
    assert "什么都没存" in out and notify.ABS_SETUP in out and PW_RAW not in out and "abcd" not in out


@pytest.mark.parametrize("answer,stored", [("n", False), ("", False), ("y", True)])
def test_setup_network_failure_asks_whether_to_store(smtp, answer, stored):
    smtp.fail_login = ConnectionRefusedError(61, "Connection refused")              # 只是网络：设置本身可能是对的 → 问
    rc, kc, out, asked = _setup(["me@example.com", "", answer])
    assert rc == 1 and bool(kc.calls) is stored and any("仍然存进钥匙串吗" in a for a in asked)
    assert ("没发成（网络）" in out) is stored and ("什么都没存" in out) is (not stored)


def test_run_py_routes_setup_email(monkeypatch, capsys):
    import run
    monkeypatch.setattr(notify.shutil, "which", lambda name: None)                  # 当作没有 security（在 Mac 上跑测试也一样）
    assert run.main(["notify", "--setup-email"]) == 2                               # 不是 macOS：说明后退出 2，什么都不问
    assert "不是 macOS" in capsys.readouterr().out
    got = []
    monkeypatch.setattr(notify, "setup_email", lambda host=None, port=None: got.append((host, port)) or 0)
    assert run.main(["notify", "--setup-email", "--host", "smtp.example.com", "--port", "465"]) == 0
    assert got == [("smtp.example.com", 465)]


def test_liveu_email_setup_never_asks_outside_a_terminal(tmp_path):
    """bash scripts/liveu.sh email-setup 经 run.py 走到 setup_email：stdin 不是终端（Claude 的工具里就是这样）→ 不问密码、什么都不存、退出 2
    （Linux 上先因为没有 security 退出 2）。"""
    import os
    import shutil
    import subprocess
    import sys
    from pathlib import Path
    if not shutil.which("bash"):
        pytest.skip("需要 bash")
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "QBREAK_PYTHON": sys.executable, "QBREAK_LIVEU_HOME": str(tmp_path / "lh"), "HOME": str(tmp_path),
           "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    r = subprocess.run(["bash", "scripts/liveu.sh", "email-setup"], cwd=root, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, timeout=120)
    out = r.stdout.decode("utf-8", "replace")
    assert r.returncode == 2 and ("不是 macOS" in out or "自己的终端" in out), (out, r.stderr.decode("utf-8", "replace"))
    assert "密码（" not in out                                                       # 没问密码
