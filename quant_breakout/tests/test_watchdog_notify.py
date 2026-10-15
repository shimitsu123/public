"""通知到手机 + 「Mac 没跑」的提醒（2026-10-09 立花实盘缺口 A1：条目 LU-04 / OPS-01 / UX-03 / LU-05 / OPS-02）：
① qbreak/notify.py：环境变量优先、没有时读钥匙串（注入的 run；只查有没有时不加 -w）；Discord / Slack 发 JSON、ntfy 发纯文本；
   失败只记 warning（不含地址）、绝不抛；外部心跳成功 / 失败的地址；
② run.py notify（--test / --subject）不打印任何值；
③ qbreak/watchdog.py（09:30 自检）：没装 / 还早 / 休市 / 跑完 / 没跑完 / 执行器停下 / 状态不明 / DEFERRED / HALT（同一天只提醒一次）；
   每个工作日推一条（2026-10-14 起代替外部心跳：通过 / 平日休市 / 模拟期开始前同一天只一次、执行器一直在跑也推、推送结果记进结果文件）；
④ 上线检查「准备」的 ⑧ 三项（手机通知通道、每天的自检推送、09:30 自检任务）。全部只用假的 run / urlopen / 临时目录，不联网、不调真的 security。"""
import datetime as dt
import json
import logging
import subprocess
import urllib.error

import pytest

from qbreak import notify, paths, watchdog
from qbreak import run_status as RS
from qbreak.calendar_jp import JST

SECRET = "https://discord.example/api/webhooks/123/SECRET-TOKEN"
NTFY = "https://ntfy.sh/qbreak-private-topic-xyz"
BEAT = "https://hc-ping.example/uuid-SECRET"


def _kc(values: dict[str, str] | None = None, rc_missing: int = 44, calls: list | None = None):
    """假的 security：values = {服务名: 值}；没有 → 退出码 44（找不到）。记下每次的参数。"""
    values = values or {}

    def run_(args, **kw):
        if calls is not None:
            calls.append(list(args))
        svc = args[args.index("-s") + 1]
        if svc not in values:
            return subprocess.CompletedProcess(args, rc_missing, "", "")
        return subprocess.CompletedProcess(args, 0, values[svc] + "\n" if "-w" in args else "attributes only", "")
    return run_


class _Resp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b"ok"


@pytest.fixture
def posts(monkeypatch):
    """截下所有 urlopen（不联网）：[(url, headers, body)]。"""
    got = []

    def fake(req, timeout=None):
        got.append((req.full_url, {k.lower(): v for k, v in req.header_items()}, req.data))
        return _Resp()
    monkeypatch.setattr(notify.urllib.request, "urlopen", fake)
    return got


# ────────── ① 设置从哪里来 ──────────
def test_env_first_then_keychain_and_never_cached_when_missing(monkeypatch):
    calls = []
    run_ = _kc({"qbreak-webhook": SECRET}, calls=calls)
    assert notify.get("webhook", run_) == SECRET and calls[-1][-1] == "-w"         # 读值才加 -w（只给进程内用）
    calls.clear()
    assert notify.get("webhook", run_) == SECRET and not calls                       # 进程内缓存
    assert notify.get("heartbeat", run_) is None and notify.get("heartbeat", run_) is None and len(calls) == 2   # 没有的不缓存
    monkeypatch.setenv("QBREAK_HEARTBEAT", BEAT)
    assert notify.get("heartbeat", run_) == BEAT and len(calls) == 2                # 环境变量优先，不查钥匙串
    notify.reset()

    def boom(args, **kw):
        raise FileNotFoundError("security")                                          # 不是 macOS
    assert notify.get("webhook", boom) is None

    def slow(args, **kw):
        raise subprocess.TimeoutExpired(args, kw.get("timeout"))
    assert notify.get("webhook", slow) is None
    assert notify.get("email") is None                                               # 测试里不指定 run：绝不碰真的钥匙串


def test_configured_and_channels_only_check_presence(monkeypatch):
    calls = []
    run_ = _kc({"qbreak-webhook": SECRET, "qbreak-heartbeat": BEAT}, calls=calls)
    assert notify.channels(run_) == {"webhook": True, "email": False, "heartbeat": True}
    assert calls and all("-w" not in c for c in calls)                                # 只查有没有，绝不取出值
    monkeypatch.setenv("QBREAK_SMTP", "smtp.example:587:u:p:to")
    assert notify.channels(run_)["email"] is True
    assert notify.configured("email", run_, env=False) is False                      # 上线检查只看钥匙串（定时任务读不到环境变量）

    def boom(args, **kw):
        raise FileNotFoundError("security")
    assert notify.configured("webhook", boom) is None and notify.channels(boom)["webhook"] is False
    assert notify.configured("webhook") is None                                      # 测试里（QBREAK_NO_KEYCHAIN）：不查钥匙串


# ────────── ① 发送 ──────────
def test_send_discord_json_and_ntfy_plain_text(monkeypatch, posts):
    monkeypatch.setenv("QBREAK_WEBHOOK", SECRET)
    res = notify.send("标题", "正文" * 2000, "warn")
    assert res == {"webhook": True, "email": None}
    url, h, body = posts[-1]
    d = json.loads(body)
    assert url == SECRET and h["content-type"] == "application/json"
    assert d["content"] == d["text"] and d["content"].startswith("[WARN] 标题\n正文") and len(d["content"]) == 1900
    monkeypatch.setenv("QBREAK_WEBHOOK", NTFY)
    assert notify.send("qbreak ★ 执行器停下", "原因：行情落后", "warn")["webhook"] is True
    url, h, body = posts[-1]
    assert url == NTFY and h["content-type"].startswith("text/plain") and h.get("priority") == "high"
    assert body.decode("utf-8") == "qbreak ★ 执行器停下\n原因：行情落后"                # 第一行标题 + 正文
    notify.send("日报", "x" * 10000, "info")
    url, h, body = posts[-1]
    assert "priority" not in h and len(body) <= notify.MAX_NTFY_BYTES
    assert notify.is_ntfy("https://ntfy.example.org/t") and not notify.is_ntfy(SECRET)


def test_send_failures_only_warn_without_the_address(monkeypatch, caplog):
    monkeypatch.setenv("QBREAK_WEBHOOK", SECRET)
    monkeypatch.setenv("QBREAK_SMTP", "smtp.example:notaport:user:pw-SECRET:to@example")

    def fail(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found " + req.full_url, {}, None)
    monkeypatch.setattr(notify.urllib.request, "urlopen", fail)
    lg = logging.getLogger("qbreak")                                                  # qbreak 的日志不往根传：直接挂上 caplog
    lg.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="qbreak"):
            res = notify.send("t", "x", "error")
    finally:
        lg.removeHandler(caplog.handler)
    assert res == {"webhook": False, "email": False}
    log_text = caplog.text
    assert "HTTP 404" in log_text and "SECRET" not in log_text and "discord.example" not in log_text
    assert "pw-" not in log_text and "格式应为 host:port:user:password:to" in log_text
    assert notify.send("t", "x") == {"webhook": False, "email": False}               # 绝不抛
    monkeypatch.delenv("QBREAK_WEBHOOK")
    monkeypatch.delenv("QBREAK_SMTP")
    assert notify.send("t", "x") == {"webhook": None, "email": None}                 # 没设置：什么都不发


def test_heartbeat_success_and_fail_urls(monkeypatch, posts):
    assert notify.heartbeat(True, "x") is None and not posts                         # 没设置
    monkeypatch.setenv("QBREAK_HEARTBEAT", BEAT + "/")
    assert notify.heartbeat(True, "自检通过") is True
    assert posts[-1][0] == BEAT and posts[-1][2].decode("utf-8") == "自检通过"
    assert notify.heartbeat(False, "y" * 5000) is True
    assert posts[-1][0] == BEAT + "/fail" and len(posts[-1][2]) == 1000

    def fail(req, timeout=None):
        raise urllib.error.URLError(OSError("down"))
    monkeypatch.setattr(notify.urllib.request, "urlopen", fail)
    assert notify.heartbeat(True) is False                                           # 绝不抛
    assert notify.heartbeat_detail(True) == (False, "连不上（OSError）")


def test_heartbeat_bad_address_gives_a_safe_reason_and_never_logs_it(monkeypatch, posts, caplog):
    """钥匙串里的心跳地址格式不对（2026-10-14 G12：urllib 的 ValueError 以前只记「ValueError」）：不发；原因只说是哪种问题、
    不含地址；前后的空白去掉照发。"""
    lg = logging.getLogger("qbreak")
    lg.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="qbreak"):
            for bad, why in (("hc-ping.example/uuid-SECRET", "地址不是 http(s):// 开头"),
                             ("https://hc-ping.example/uuid- SECRET", "地址里有空白或换行"),
                             ("https://hc-ping.example/uuid-\nSECRET", "地址里有空白或换行"),
                             ("https://hc-ping.example/uuid-\u3000SECRET", "地址里有空白或换行"),
                             ("https:///uuid-SECRET", "地址格式不对")):
                notify.reset()
                run_ = _kc({"qbreak-heartbeat": bad})
                assert notify.heartbeat_detail(True, "x", run_) == (False, why)
                assert notify.heartbeat(False, "x", run_) is False
                assert notify.beat_addr_why(bad) == why
            assert not posts
            monkeypatch.setenv("QBREAK_HEARTBEAT", "  " + BEAT + " \n")
            assert notify.heartbeat_detail(True, "ok") == (True, "") and posts[-1][0] == BEAT   # 前后的空白去掉

            def bad_url(req, timeout=None):
                raise ValueError("unknown url type: " + req.full_url)                # urllib 的文字里带着地址
            monkeypatch.setattr(notify.urllib.request, "urlopen", bad_url)
            assert notify.heartbeat_detail(True, "x") == (False, "地址格式不对")
    finally:
        lg.removeHandler(caplog.handler)
        notify.reset()
    log_text = caplog.text
    assert "地址不是 http(s):// 开头" in log_text and "地址里有空白或换行" in log_text and "地址格式不对" in log_text
    assert "SECRET" not in log_text and "hc-ping.example" not in log_text


# ────────── ② run.py notify ──────────
def test_notify_command_never_prints_values(monkeypatch, posts, capsys):
    import run
    assert run.main(["notify", "--test"]) == 3
    out = capsys.readouterr().out
    assert "webhook：没设置" in out and "在这台设备打开推送" in out and "通知记录：已记一条" in out
    assert "心跳" not in out and "09:30 自检每个工作日推一条到这里" in out                  # 外部心跳没设：不提（2026-10-14 起不用）
    monkeypatch.setenv("QBREAK_WEBHOOK", SECRET)
    monkeypatch.setenv("QBREAK_HEARTBEAT", BEAT)
    assert run.main(["notify", "--test"]) == 0
    out = capsys.readouterr().out
    assert "webhook：已发" in out and "邮件：没设置" in out and "外部心跳（可选）：已设置（测试不 ping" in out
    assert "SECRET" not in out and "discord" not in out and "hc-ping" not in out
    assert [p[0] for p in posts] == [SECRET]                                         # 测试不 ping 心跳
    assert run.main(["notify", "--subject", "qbreak ★ 运行没有完成", "--text=10/09 07:41 的运行没有完成（退出码 1）",
                     "--level", "warn", "--once", "tachibana"]) == 0
    assert len(posts) == 2 and json.loads(posts[-1][2])["content"].startswith("[WARN] qbreak ★ 运行没有完成")
    assert run.main(["notify", "--subject", "qbreak ★ 运行没有完成", "--text=10/09 07:52 的运行没有完成（退出码 1）",
                     "--level", "warn", "--once", "tachibana"]) == 0
    assert len(posts) == 2 and "今天已经通知过" in capsys.readouterr().out          # 同一天同一段文字（时刻不算）只发一次
    assert "SECRET" not in capsys.readouterr().out
    assert run.main(["notify"]) == 2


# ────────── ③ 09:30 自检 ──────────
TUE = dt.datetime(2026, 10, 6, 9, 30, tzinfo=JST)          # 交易日；早上应该处理到 2026-10-05（周一）
DONE = "2026-10-05"


def _agents(tmp_path, kind="tachibana"):
    a = tmp_path / f"agents_{kind}"                                               # 每种装法一个目录
    a.mkdir(exist_ok=True)
    if kind:
        (a / f"{watchdog.LIVE_PLIST if kind == 'tachibana' else watchdog.PAPER_PLIST}.plist").write_text("x", encoding="utf-8")
    return a


def _book(tag="tachibana", last=DONE, orders=()):
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps(
        {"state": {"last_date": last}, "orders": list(orders)}), encoding="utf-8")


def _o(cid, status, d=DONE, side="BUY", ticker="7203.T", qty=100):
    return {"cid": cid, "ticker": ticker, "side": side, "qty": qty, "decided_on": d, "status": status}


class _Rec:
    def __init__(self):
        self.sent, self.beats, self.macs, self.resends = [], [], [], []

    def send(self, title, text, level="info", resend=False):
        self.sent.append((title, text, level))
        self.resends.append(resend)
        return {"webhook": True, "email": None}

    def beat(self, ok, msg=""):
        self.beats.append((ok, msg))
        return True

    def mac(self, title, text):
        self.macs.append((title, text))
        return True


def _run(tmp_path, now=TUE, kind="tachibana", r=None, naps=None):
    r = r or _Rec()
    lines = []
    naps = [] if naps is None else naps
    rc = watchdog.run(_agents(tmp_path, kind), now, send=r.send, beat=r.beat, mac=r.mac, out=lines.append, sleep=naps.append)
    return rc, r, "\n".join(lines)


def _wd(tag="tachibana"):
    return json.loads(watchdog.path(tag).read_text(encoding="utf-8"))


def test_watchdog_not_installed_or_too_early_sends_nothing(tmp_path):
    rc, r, out = _run(tmp_path, kind=None)
    assert rc == 0 and not r.sent and not r.beats and "只打印" in out
    _book(last="2026-10-02")
    rc, r, out = _run(tmp_path, now=TUE.replace(hour=8, minute=10))
    assert rc == 0 and not r.sent and not r.beats and "之前不判定" in out and not watchdog.path("tachibana").exists()


DAILY = watchdog.DAILY_LINE


def test_watchdog_holiday_and_done_push_once_a_day(tmp_path):
    """每个工作日推一条（2026-10-14 用户「不用做 healthchecks.io 心跳 check，改为每天用 qbreak 进行推送就可以」）：
    平日休市 → 「今天休市（系统正常）」；通过 → 「✓ HH:MM 自检通过」（决策日、今天的单几笔）；同一天再自检 / 补跑不再推；周末不推。"""
    _book(last="2026-10-02")                                                      # 周六：休市、周末不推
    rc, r, out = _run(tmp_path, now=dt.datetime(2026, 10, 10, 9, 30, tzinfo=JST))
    assert rc == 0 and not r.sent and r.beats == [(True, "qbreak 立花实盘：2026-10-10 休市")] and _wd()["ok"] is True
    assert "push" not in _wd() and "周末不推送" in out
    rc, r, out = _run(tmp_path, now=dt.datetime(2026, 10, 12, 9, 30, tzinfo=JST))  # スポーツの日（周一）：照推
    assert rc == 0 and r.beats[0][0] is True and "休市" in r.beats[0][1]
    assert r.sent == [("qbreak 立花实盘：今天休市（系统正常）", f"10/12 休市：执行器今天不下单；09:30 自检照常运行。\n{DAILY}", "info")]
    assert not r.macs and _wd()["push"] == {"at": "2026-10-12T09:30:00+09:00", "state": "sent", "why": "webhook 已发"}
    _book(orders=[_o("a", "SENT"), _o("b", "FILLED", side="SELL"), _o("c", "SKIPPED")])
    rc, r, out = _run(tmp_path)
    assert rc == 0 and not r.macs and r.beats[0][0] is True and "自检通过" in out and "推送 已推送" in out
    assert r.sent == [("qbreak 立花实盘 ✓ 09:30 自检通过",
                       f"决策 2026-10-05 处理完；今天的单 2 笔：成交 1、挂着 1。\n{DAILY}", "info")]
    assert _wd() == {"at": "2026-10-06T09:30:00+09:00", "ok": True, "reasons": [], "halt": None, "note": "",
                     "push": {"at": "2026-10-06T09:30:00+09:00", "state": "sent", "why": "webhook 已发"},
                     "heartbeat": {"at": "2026-10-06T09:30:00+09:00", "state": "sent", "why": ""}}
    rc, r, out = _run(tmp_path, now=TUE.replace(hour=10, minute=5))               # 「再自检一次」：同一天不再推
    assert rc == 0 and not r.sent and "今天已经推过" in out
    assert _wd()["at"] == "2026-10-06T10:05:00+09:00" and _wd()["push"]["at"] == "2026-10-06T09:30:00+09:00"   # 沿用那次的结果
    _book(last="2026-10-06", orders=[])
    rc, r, out = _run(tmp_path, now=dt.datetime(2026, 10, 7, 10, 15, tzinfo=JST))   # 第二天 Mac 10:15 才醒：按真的时刻写
    assert [x[0] for x in r.sent] == ["qbreak 立花实盘 ✓ 10:15 自检通过"] and "今天没有单" in r.sent[0][1]


def test_orders_brief_counts_cancelled_orders_by_name():
    """通过那条推送里的单数摘要：撤掉的单（CANCELLED，面板 / liveu.sh cancel）算「已撤」，不算「其他」（2026-10-14 复核）。"""
    os_ = [{"decided_on": DONE, "status": "FILLED"}, {"decided_on": DONE, "status": "CANCELLED"},
           {"decided_on": DONE, "status": "SKIPPED"}, {"decided_on": "2026-10-02", "status": "CANCELLED"}]
    assert watchdog.orders_brief({"orders": os_}, DONE) == "今天的单 2 笔：成交 1、已撤 1"
    assert watchdog.orders_brief({"orders": [{"decided_on": DONE, "status": "WEIRD"}]}, DONE) == "今天的单 1 笔：其他 1"
    assert watchdog.orders_brief({}, DONE) == "今天没有单"


def test_watchdog_fail_after_ok_still_pushes_and_ok_after_fail_says_so(tmp_path):
    """同一天：通过（推了）→ 没通过（照推 warn）→ 又通过（再推一次，说早些时候没通过）→ 再通过（不再推）。"""
    _book(orders=[_o("a", "SENT")])
    rc, r, out = _run(tmp_path)
    assert rc == 0 and [x[2] for x in r.sent] == ["info"]
    _book(orders=[_o("a", "ERROR")])
    rc, r, out = _run(tmp_path, now=TUE.replace(minute=50))
    assert rc == 1 and len(r.sent) == 1 and r.sent[0][2] == "warn" and r.sent[0][0] == "qbreak 立花实盘 ★ 09:50 自检没通过"   # 真的运行时刻
    assert r.macs[0][0] == "qbreak 立花实盘 ★ 09:50 自检没通过"
    assert _wd()["push"] == {"at": "2026-10-06T09:50:00+09:00", "state": "sent", "why": "webhook 已发"}
    _book(orders=[{**_o("a", "FILLED")}])
    rc, r, out = _run(tmp_path, now=TUE.replace(hour=10, minute=20))
    assert rc == 0 and [x[0] for x in r.sent] == ["qbreak 立花实盘 ✓ 10:20 自检通过"]
    assert r.sent[0][1].startswith("现在通过了（09:50 没通过）。\n决策 2026-10-05 处理完；今天的单 1 笔：成交 1。")
    rc, r, out = _run(tmp_path, now=TUE.replace(hour=10, minute=30))
    assert rc == 0 and not r.sent


def test_watchdog_records_the_push_result_and_retries_when_it_did_not_reach_the_phone(tmp_path):
    """推送的结果记进结果文件（push）：推送没发成 / 没有设备打开推送 → 面板顶部、菜单栏 ★ 并说怎么做；同一天再自检会再推一次。"""
    from qbreak import mac_status, panel
    _book(orders=[_o("a", "SENT")])

    class _Push(_Rec):
        def __init__(self, res):
            super().__init__()
            self.res = res

        def send(self, title, text, level="info", resend=False):
            self.sent.append((title, text, level))
            self.resends.append(resend)
            return self.res
    naps = []
    rc, r, out = _run(tmp_path, r=_Push({"webhook": None, "email": None, "push": False}), naps=naps)
    assert rc == 0 and len(r.sent) == 2 and r.resends == [False, True] and naps == [watchdog.RETRY_S]   # 60 秒后重推一次（只一次）
    assert "60 秒后再推一次" in out and "★ 推送没发成（推送（网页 App） 失败；60 秒后重推也没成）" in out
    assert _wd()["push"] == {"at": "2026-10-06T09:30:00+09:00", "state": "failed", "why": "推送（网页 App） 失败；60 秒后重推也没成"}
    book = json.loads((paths.state_dir() / "live_unified_tachibana.json").read_text(encoding="utf-8"))
    top = "\n".join(h for _, h in panel._run_lines("tachibana", book, TUE.replace(minute=40), None))
    assert "★ 10/06 09:30 自检的推送没发成（推送（网页 App） 失败；60 秒后重推也没成）：今天不会自动再推" in top
    assert "「再自检一次」" in top and "下一次会再推" not in top and "在这台设备打开推送" not in top   # 失败 ≠ 没有通道：不叫你重新打开推送
    it = mac_status._watchdog_item("tachibana", TUE.replace(minute=40))
    assert it["level"] == "warn" and it["text"].startswith("通过；★ 推送没发成") and "「再自检一次」" in it["text"]
    rc, r, out = _run(tmp_path, now=TUE.replace(minute=45), r=_Push({"webhook": None, "email": None}), naps=naps)   # 没推到 → 再推（没有通道）
    assert len(r.sent) == 1 and _wd()["push"]["state"] == "none" and "没有设备打开 qbreak 推送" in _wd()["push"]["why"]
    assert "★ 没推到手机" in out and naps == [watchdog.RETRY_S]                    # 没有通道：不重推（等也没用）
    it = mac_status._watchdog_item("tachibana", TUE.replace(minute=46))
    assert "在这台设备打开推送" in it["text"]                                     # 没有通道：教你打开推送
    rc, r, out = _run(tmp_path, now=TUE.replace(minute=50), r=_Push({"webhook": None, "email": None, "push": True}))
    assert len(r.sent) == 1 and _wd()["push"]["state"] == "sent"
    top = "\n".join(h for _, h in panel._run_lines("tachibana", book, TUE.replace(minute=55), None))
    assert "自检（09:50）：通过；已推送到手机" in top and "★" not in top
    it = mac_status._watchdog_item("tachibana", TUE.replace(minute=55))
    assert it == {"name": "09:30 自检", "level": "ok", "text": "通过；已推送"}
    rc, r, out = _run(tmp_path, now=TUE.replace(hour=10), r=_Push({"push": True}))   # 推到了：同一天不再推
    assert not r.sent


def test_watchdog_without_a_heartbeat_address_says_nothing_about_it(tmp_path):
    """外部心跳没设（2026-10-14 起不用）：正常 —— 终端、结果文件、面板、菜单栏、推送里都不提心跳。"""
    from qbreak import mac_status, panel
    _book(orders=[_o("a", "SENT")])
    r, lines = _Rec(), []
    rc = watchdog.run(_agents(tmp_path), TUE, send=r.send, mac=r.mac, out=lines.append)   # 真的 heartbeat_detail：没设 → (None, "")
    out = "\n".join(lines)
    assert rc == 0 and len(r.sent) == 1 and "心跳" not in out and "heartbeat" not in _wd() and _wd()["push"]["state"] == "sent"
    book = json.loads((paths.state_dir() / "live_unified_tachibana.json").read_text(encoding="utf-8"))
    top = "\n".join(h for _, h in panel._run_lines("tachibana", book, TUE.replace(minute=40), None))
    assert "心跳" not in top and mac_status._beat_item("tachibana") is None
    assert all("心跳" not in t + x for t, x, _ in r.sent)
    _book(orders=[_o("a", "ERROR")])
    lines.clear()
    assert watchdog.run(_agents(tmp_path), TUE.replace(minute=40), send=r.send, mac=r.mac, out=lines.append) == 1
    assert "心跳" not in "\n".join(lines) and "heartbeat" not in _wd()


def test_watchdog_morning_not_done_notifies_and_fails_the_heartbeat(tmp_path):
    _book(last="2026-10-02")
    RS.write("tachibana", RS.build({}, phase="retry", ok=False, rc=3, error="另一个执行器还在运行（pid 1）",
                                   now=TUE.replace(hour=8, minute=35)))
    rc, r, out = _run(tmp_path)
    assert rc == 1 and len(r.sent) == 1 and r.sent[0][2] == "warn" and r.beats[0][0] is False
    title, text, _ = r.sent[0]
    assert title == "qbreak 立花实盘 ★ 09:30 自检没通过"
    assert "- 今天早上的执行器没有跑完（上次决策 2026-10-02）" in text
    assert "- 执行器停下（08:35）：另一个执行器还在运行（pid 1）" in text
    assert r.macs[0][1].startswith("今天早上的执行器没有跑完") and text in r.beats[0][1]
    wd = _wd()
    assert wd["ok"] is False and wd["reasons"][0] == "今天早上的执行器没有跑完（上次决策 2026-10-02）"
    _book(last=DONE, orders=[{**_o("a", "BLOCKED"), "note": "持仓与券商不一致：7203.T"}])   # 处理到了，但整次被挡（没下）
    RS.write("tachibana", RS.build({}, phase="morning", ok=True, rc=0, blocked="持仓与券商不一致：7203.T",
                                   now=TUE.replace(hour=7, minute=41)))
    rc, r, out = _run(tmp_path)
    assert rc == 1 and r.sent[0][1] == "- 今天的单没下：持仓与券商不一致：7203 トヨタ自動車"   # 跑完了：不说「没有跑完」；原因说过的单不再逐笔列（代码 + 名字，2026-10-15）
    assert "执行器停下" not in r.sent[0][1] and "没有跑完" not in r.sent[0][1]
    RS.write("tachibana", RS.build({}, phase="morning", ok=False, rc=1, error="昨天的",
                                   now=TUE - dt.timedelta(days=1)))
    _book(last="2026-10-02")
    rc, r, out = _run(tmp_path)
    assert "昨天的" not in r.sent[0][1]                                            # 运行状态只看今天的


def test_watchdog_names_orders_that_were_not_placed_after_a_finished_run(tmp_path):
    """决策处理了、运行也正常结束，但有单被适配器挡下 / 被拒 / 还没发：说清是哪几笔、为什么（不说「没有跑完」）。"""
    _book(last=DONE, orders=[{**_o("a", "BLOCKED"), "note": "未 ARM"}, _o("b", "SENT", ticker="6758.T"),
                             {**_o("c", "REJECTED", side="SELL", ticker="1655.T"), "kind": "core", "note": "余力不足"}])
    RS.write("tachibana", RS.build({}, phase="morning", ok=True, rc=0, now=TUE.replace(hour=7, minute=41)))
    rc, r, out = _run(tmp_path)
    assert rc == 1 and "没有跑完" not in r.sent[0][1]
    assert "- 决策 2026-10-05 处理了，但有 2 笔没下：7203 トヨタ自動車 买 100 股 被挡：未 ARM；1655 S&P500 卖 100 口 被拒：余力不足" in r.sent[0][1]


def test_watchdog_paper_before_the_sim_start_is_not_a_failure(tmp_path):
    """模拟账户在模拟期开始日之前故意不推进（run.py live-u）：不算失败，推一条说明（每个工作日那条）。"""
    _book(tag="paper", last="2026-09-18")
    (paths.home() / "sim.json").write_text(json.dumps({"mode": "unified", "start": "2026-10-13"}), encoding="utf-8")
    rc, r, out = _run(tmp_path, kind="paper")
    assert rc == 0 and r.beats == [(True, "qbreak 模拟操盘：模拟期开始日 2026-10-13 之前（模拟账户还不推进）")]
    assert r.sent == [("qbreak 模拟操盘 ✓ 09:30 自检：模拟期开始前", f"模拟期开始日 2026-10-13 之前（模拟账户还不推进）。\n{DAILY}", "info")]
    assert _wd("paper")["ok"] is True and not r.macs
    (paths.home() / "sim.json").write_text(json.dumps({"mode": "unified", "start": "2026-10-01"}), encoding="utf-8")
    rc, r, out = _run(tmp_path, kind="paper")                                      # 开始之后：照常判定
    assert rc == 1 and "没有跑完（上次决策 2026-09-18）" in r.sent[0][1]
    _book(last="2026-09-18")
    (paths.home() / "sim.json").write_text(json.dumps({"mode": "unified", "start": "2026-10-13"}), encoding="utf-8")
    rc, r, out = _run(tmp_path)                                                    # 立花本番不看模拟期
    assert rc == 1


def test_watchdog_waits_while_the_executor_holds_the_run_lock(tmp_path):
    """Mac 睡着错过 07:40、醒来时自检和执行器一起被拉起：执行器拿着运行锁 → 等它结束再判定（不判定跑到一半的账本）。"""
    from qbreak.live_unified import RunLock
    _book(last="2026-10-02")
    lock = RunLock(paths.state_dir() / "live_unified_tachibana.lock").acquire()
    naps = []

    def sleep(sec):                                                                # 执行器在等的时候跑完、放开锁
        naps.append(sec)
        if len(naps) == 2:
            _book(orders=[_o("a", "SENT")])
            lock.release()
    r = _Rec()
    lines = []
    rc = watchdog.run(_agents(tmp_path), TUE, send=r.send, beat=r.beat, mac=r.mac, out=lines.append, sleep=sleep)
    assert rc == 0 and naps == [15, 15] and [x[0] for x in r.sent] == ["qbreak 立花实盘 ✓ 09:30 自检通过"] and r.beats[0][0] is True
    assert "等它结束再判定" in lines[0] and _wd()["at"] == "2026-10-06T09:30:30+09:00"


def test_watchdog_pushes_once_a_day_when_the_executor_never_finishes(tmp_path):
    """执行器跑了 10 分钟以上还没结束：这次不判定 → 推一条 warn「自检判定不了」（同一天只一次；2026-10-14 起，以前一声不响）。
    今天还没有结果 → 写一份 ok = None（面板顶部 / 菜单栏显示）；今天已经判定过 → 不盖掉。"""
    from qbreak import mac_status, panel
    from qbreak.live_unified import RunLock
    _book(last="2026-10-02")
    lp = paths.state_dir() / "live_unified_tachibana.lock"
    lock = RunLock(lp).acquire()
    lp.write_text("pid 1 从 2026-10-06 09:12:00 JST\n", encoding="utf-8")         # 执行器 09:12 开始（锁文件里写的）
    try:
        r = _Rec()
        lines = []
        rc = watchdog.run(_agents(tmp_path), TUE, send=r.send, beat=r.beat, mac=r.mac, out=lines.append, sleep=lambda s: None)
        assert rc == 0 and not r.beats and len(r.sent) == 1 and len(r.macs) == 1 and "这次不判定" in "\n".join(lines)
        title, text, level = r.sent[0]
        assert title == "qbreak 立花实盘 ★ 09:40 自检判定不了" and level == "warn"
        assert text.startswith("执行器从 09:12 起已经跑了 28 分钟还没结束：这次不判定（今天早上的单下没下还不知道）。")
        assert "bash scripts/liveu.sh watchdog --dry" in text and "pid" not in text
        wd = _wd()
        assert wd["ok"] is None and wd["at"] == "2026-10-06T09:40:00+09:00" and wd["push"]["state"] == "sent"
        book = json.loads((paths.state_dir() / "live_unified_tachibana.json").read_text(encoding="utf-8"))
        top = "\n".join(h for _, h in panel._run_lines("tachibana", book, TUE.replace(minute=45), None))
        assert "★ 自检（09:40）判定不了：执行器从 09:12 起已经跑了 28 分钟还没结束" in top
        assert mac_status._watchdog_item("tachibana", TUE.replace(minute=45))["level"] == "warn"
        r = _Rec()
        lines = []
        rc = watchdog.run(_agents(tmp_path), TUE.replace(hour=10), send=r.send, beat=r.beat, mac=r.mac, out=lines.append,
                          sleep=lambda s: None)
        assert rc == 0 and not r.sent and not r.macs and "今天已经推过「判定不了」" in lines[-1]
        lp.write_text("x\n", encoding="utf-8")                                    # 锁文件读不出时刻：按等了多久说
        rc = watchdog.run(_agents(tmp_path), TUE + dt.timedelta(days=1), send=r.send, beat=r.beat, mac=r.mac, out=lines.append,
                          sleep=lambda s: None)
        assert r.sent[0][1].startswith("执行器已经跑了 10 分钟以上还没结束")
    finally:
        lock.release()
    _book(last="2026-10-07", orders=[_o("a", "SENT", d="2026-10-07")])            # 今天已经判定过（通过、推了）
    rc, r, out = _run(tmp_path, now=TUE + dt.timedelta(days=2))
    assert rc == 0 and [x[0] for x in r.sent] == ["qbreak 立花实盘 ✓ 09:30 自检通过"]
    lock = RunLock(lp).acquire()
    lp.write_text("pid 1 从 2026-10-08 11:50:00 JST\n", encoding="utf-8")         # 12:00 再自检、等了 10 分钟还在跑
    try:
        r2, lines = _Rec(), []
        rc = watchdog.run(_agents(tmp_path), TUE + dt.timedelta(days=2, hours=2, minutes=30), send=r2.send, beat=r2.beat, mac=r2.mac,
                          out=lines.append, sleep=lambda s: None)
    finally:
        lock.release()
    # 「再自检一次」时执行器在跑（例：面板叫的）：早上已经确认过 → 不推「判定不了…早上的单下没下还不知道」、不盖掉（2026-10-14 复核）
    assert rc == 0 and not r2.sent and not r2.macs and _wd()["ok"] is True and _wd()["at"] == "2026-10-08T09:30:00+09:00"
    assert "今天 09:30 已经判定过（通过）；这次执行器还在跑（从 11:50 起已经跑了 20 分钟），不再判定、不推送" in lines[-1]


def test_watchdog_keeps_local_paths_out_of_what_it_sends(tmp_path, monkeypatch):
    """liveu.sh「运行没有完成」的文字带数据目录的路径（含 Mac 的用户名）：手机通知 / 心跳里换成「数据目录」/「~」。"""
    home = tmp_path / "Users" / "someone"
    monkeypatch.setenv("HOME", str(home))
    _book(last="2026-10-02")
    RS.write("tachibana", {"at": "2026-10-06T07:41:00+09:00", "phase": "morning", "ok": False, "rc": 1,
                           "error": f"运行没有完成：看 {paths.home()}/logs/ 里的 .err；仓库 {home}/qbreak-src"})
    rc, r, out = _run(tmp_path)
    sent = r.sent[0][1] + r.beats[0][1] + r.macs[0][1] + json.dumps(_wd(), ensure_ascii=False)
    assert rc == 1 and str(paths.home()) not in sent and "someone" not in sent
    assert "看 数据目录/logs/ 里的 .err；仓库 ~/qbreak-src" in r.sent[0][1]
    assert RS.scrub(f"{paths.home()}/HALT") == "数据目录/HALT"


class _Beat(_Rec):
    """心跳返回 (状态, 原因)（notify.heartbeat_detail 的形状）；None → 没设置。"""
    def __init__(self, res):
        super().__init__()
        self.res = res

    def beat(self, ok, msg=""):
        self.beats.append((ok, msg))
        return self.res


def test_watchdog_records_the_heartbeat_and_warns_once_a_day_when_it_fails(tmp_path, monkeypatch, posts):
    """外部心跳（可选，2026-10-14 起不用）设了却没发成（2026-10-14 G12：以前只在日志里记「ValueError」，没人知道）：结果文件记 heartbeat
    （原因不含地址）、手机 + Mac 通知同一天只一次（教你在「终端」重新存钥匙串或删掉）；面板顶部（Mac 与手机）/ 菜单栏的状态显示；
    发成了就消失；没设 → 不记、不显示。"""
    from qbreak import mac_status, panel
    _book(orders=[_o("a", "SENT")])
    monkeypatch.setenv("QBREAK_HEARTBEAT", "hc-ping.example/uuid-SECRET")          # 真的 heartbeat_detail（不注入 beat）
    r, lines = _Rec(), []
    rc = watchdog.run(_agents(tmp_path), TUE, send=r.send, mac=r.mac, out=lines.append)
    out = "\n".join(lines)
    assert rc == 0 and not posts and _wd()["ok"] is True                           # 自检本身通过
    assert _wd()["heartbeat"] == {"at": "2026-10-06T09:30:00+09:00", "state": "failed", "why": "地址不是 http(s):// 开头"}
    assert "外部心跳 ★ 没发成（地址不是 http(s):// 开头）" in out
    assert [x[0] for x in r.sent] == ["qbreak 立花实盘 ✓ 09:30 自检通过", "qbreak 立花实盘：外部心跳没发成"] and r.sent[1][2] == "warn"
    assert "地址不是 http(s):// 开头" in r.sent[1][1] and "security add-generic-password -U -s qbreak-heartbeat -a qbreak -w" in r.sent[1][1]
    assert "security delete-generic-password -s qbreak-heartbeat -a qbreak" in r.sent[1][1]   # 不用了就删掉
    assert len(r.macs) == 1
    seen_all = out + json.dumps(_wd(), ensure_ascii=False) + r.sent[1][1] + r.macs[0][1]
    assert "SECRET" not in seen_all and "hc-ping.example" not in seen_all
    book = json.loads((paths.state_dir() / "live_unified_tachibana.json").read_text(encoding="utf-8"))
    top = "\n".join(h for _, h in panel._run_lines("tachibana", book, TUE.replace(minute=40), None))
    assert "★ 10/06 09:30 外部心跳没发成（地址不是 http(s):// 开头）" in top and "SECRET" not in top
    it = mac_status._beat_item("tachibana")
    assert it["level"] == "bad" and "地址不是 http(s):// 开头" in it["text"] and it["name"] == "外部心跳"
    rc, r, out = _run(tmp_path, now=TUE.replace(minute=45), r=_Beat((False, "HTTP 404")))   # 同一天：不再通知，结果照记
    assert not r.sent and not r.macs and "今天已经提醒过外部心跳没发成" in out and _wd()["heartbeat"]["why"] == "HTTP 404"
    _book(last="2026-10-06", orders=[_o("a", "SENT", d="2026-10-06")])
    rc, r, out = _run(tmp_path, now=TUE + dt.timedelta(days=1), r=_Beat((False, "连不上（OSError）")))   # 第二天：再提醒一次
    assert rc == 0 and len(r.sent) == 2 and "多半是网络问题" in r.sent[1][1]
    rc, r, out = _run(tmp_path, now=TUE + dt.timedelta(days=1, minutes=5), r=_Beat((True, "")))       # 发成了：面板上消失
    book = json.loads((paths.state_dir() / "live_unified_tachibana.json").read_text(encoding="utf-8"))
    top = "\n".join(h for _, h in panel._run_lines("tachibana", book, TUE + dt.timedelta(days=1, minutes=10), None))
    assert _wd()["heartbeat"]["state"] == "sent" and "外部心跳" not in top and not r.sent
    assert mac_status._beat_item("tachibana") is None                               # 发成了：不显示（只在没发成时说）
    rc, r, out = _run(tmp_path, now=TUE + dt.timedelta(days=1, minutes=6), r=_Beat((None, "")))      # 没设置：不记、不显示
    assert "heartbeat" not in _wd() and mac_status._beat_item("tachibana") is None and not r.sent and "心跳" not in out


def test_watchdog_dry_only_prints(tmp_path):
    """liveu.sh watchdog --dry（Mac 对话里问「今天的自检过了吗」）：只判定、打印；不写结果文件、不发通知 / 心跳。"""
    _book(last="2026-10-02")
    r = _Rec()
    lines = []
    rc = watchdog.run(_agents(tmp_path), TUE, send=r.send, beat=r.beat, mac=r.mac, out=lines.append, dry=True)
    assert rc == 1 and not r.sent and not r.beats and not r.macs and not watchdog.path("tachibana").exists()
    assert "只看不发" in lines[-1] and "- 今天早上的执行器没有跑完（上次决策 2026-10-02）" in lines[-1]
    _book(orders=[_o("a", "SENT")])
    lines.clear()
    assert watchdog.run(_agents(tmp_path), TUE, send=r.send, beat=r.beat, mac=r.mac, out=lines.append, dry=True) == 0
    assert "自检通过" in lines[-1] and not r.beats


def test_watchdog_command_refuses_a_data_dir_inside_the_repo(tmp_path, monkeypatch, capsys):
    """数据目录在仓库里（没设 QBREAK_HOME）：判定的是别的账本，还会发真的通知 / 心跳 → 拒绝，什么都不发。"""
    import run
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", repo)
    monkeypatch.delenv("QBREAK_HOME", raising=False)
    calls = []
    monkeypatch.setattr(notify, "send", lambda *a, **k: calls.append("send"))
    monkeypatch.setattr(notify, "heartbeat", lambda *a, **k: calls.append("beat"))
    monkeypatch.setattr(notify, "heartbeat_detail", lambda *a, **k: calls.append("beat"))
    agents = _agents(tmp_path, "paper")
    assert run.main(["live-watchdog", "--agents", str(agents)]) == 2
    assert calls == [] and "不能放进仓库的 var/" in capsys.readouterr().out and list(repo.rglob("*")) == []


def test_watchdog_unknown_orders_and_deferred_buys(tmp_path):
    _book(orders=[_o("a", "ERROR", d="2026-10-02", side="SELL"), _o("b", "DEFERRED")])
    rc, r, out = _run(tmp_path, now=TUE.replace(minute=20))                       # 09:20：开盘后的补单可能还在跑 → 不算 DEFERRED
    assert rc == 1 and "有状态不明的单 1 笔（7203 トヨタ自動車 卖 100 股）" in r.sent[0][1] and "kabuka.e-shiten.jp" in r.sent[0][1]
    assert "开盘后的买单" not in r.sent[0][1]
    rc, r, out = _run(tmp_path)
    assert "开盘后的买单还没下（1 笔：09:05 / 09:20 的补单没跑成）" in r.sent[0][1]
    _book(tag="paper", orders=[_o("b", "DEFERRED"), _o("c", "SENDING")])
    rc, r, out = _run(tmp_path, kind="paper")                                      # 模拟账户：没有开盘后补单这一说
    assert rc == 1 and r.sent[0][0] == "qbreak 模拟操盘 ★ 09:30 自检没通过"
    assert "开盘后的买单" not in r.sent[0][1] and "在 Mac 对话里看一下" in r.sent[0][1]


def test_watchdog_halt_is_not_a_failure_and_reminds_once_a_day(tmp_path):
    _book(last="2026-10-02")
    paths.halt_file().write_text("HALT 2026-10-05 用户说停\n", encoding="utf-8")
    rc, r, out = _run(tmp_path)
    assert rc == 0 and r.beats[0][0] is True and len(r.sent) == 1 and r.sent[0][2] == "info"   # 这一条就是今天的推送（不另推「通过」）
    assert r.sent[0][0] == "qbreak 立花实盘：HALT 生效中" and "HALT 2026-10-05 用户说停" in r.sent[0][1]
    assert "另外：今天早上的执行器没有跑完" in r.sent[0][1]
    assert _wd()["ok"] is True and _wd()["halt"].startswith("HALT 2026-10-05") and _wd()["push"]["state"] == "sent"
    _book(orders=[_o("a", "SENT")])                                               # 早上跑完了、HALT 还在：仍然只有 HALT 那一条
    rc, r, out = _run(tmp_path, now=TUE.replace(minute=45))                        # 同一天再跑：不再提醒，心跳照发
    assert rc == 0 and not r.sent and not r.macs and r.beats[0][0] is True and "今天已经推过 HALT" in out
    assert _wd()["push"]["at"] == "2026-10-06T09:30:00+09:00"
    rc, r, out = _run(tmp_path, now=TUE + dt.timedelta(days=1))                    # 第二天：再提醒一次
    assert len(r.sent) == 1


def test_watchdog_halt_push_that_did_not_reach_the_phone_is_pushed_again(tmp_path):
    """HALT 当天那条没推到手机（2026-10-14 复核：以前同一天再自检不再推，和面板「再自检一次会再推」不一致）→ 再自检时再推；
    推到了之后不再推；Mac 通知只在第一次。"""
    paths.halt_file().write_text("HALT 2026-10-05 用户说停\n", encoding="utf-8")
    _book(orders=[_o("a", "SENT")])

    class _Push(_Rec):
        def __init__(self, res):
            super().__init__()
            self.res = res

        def send(self, title, text, level="info", resend=False):
            self.sent.append((title, text, level))
            return self.res
    rc, r, out = _run(tmp_path, r=_Push({"webhook": None, "email": None, "push": False}))
    assert rc == 0 and [x[0] for x in r.sent] == ["qbreak 立花实盘：HALT 生效中"] * 2 and len(r.macs) == 1   # 60 秒后重推了一次
    assert _wd()["push"]["state"] == "failed"
    rc, r, out = _run(tmp_path, now=TUE.replace(minute=50), r=_Push({"webhook": None, "email": None, "push": True}))
    assert [x[0] for x in r.sent] == ["qbreak 立花实盘：HALT 生效中"] and not r.macs and _wd()["push"]["state"] == "sent"
    assert _wd()["push"]["at"] == "2026-10-06T09:50:00+09:00"
    rc, r, out = _run(tmp_path, now=TUE.replace(hour=10), r=_Push({"push": True}))
    assert not r.sent and "今天已经推过 HALT" in out and _wd()["push"]["at"] == "2026-10-06T09:50:00+09:00"


def test_watchdog_push_retries_once_after_a_transient_failure(tmp_path, monkeypatch):
    """设置了的通道都没发成（网络抖动）→ 60 秒后重推一次（只一次）：成了 → sent（说明第一次没成）；重推不再记进通知记录
    （notify.send(resend=True)）。没通过的 warn 也一样。"""
    _book(orders=[_o("a", "SENT")])

    class _Flaky(_Rec):
        def __init__(self, results):
            super().__init__()
            self.results = list(results)

        def send(self, title, text, level="info", resend=False):
            self.sent.append((title, text, level))
            self.resends.append(resend)
            return self.results.pop(0)
    naps = []
    rc, r, out = _run(tmp_path, r=_Flaky([{"webhook": False, "email": None}, {"webhook": True, "email": None}]), naps=naps)
    assert rc == 0 and naps == [60] and r.resends == [False, True] and r.sent[0] == r.sent[1]
    assert _wd()["push"] == {"at": "2026-10-06T09:30:00+09:00", "state": "sent", "why": "webhook 已发（第一次没发成，60 秒后重推）"}
    assert watchdog.push_text(_wd()["push"]) is None
    _book(orders=[_o("a", "ERROR")])
    naps.clear()
    rc, r, out = _run(tmp_path, now=TUE.replace(minute=40), r=_Flaky([{"push": False}, {"push": False}]), naps=naps)
    assert rc == 1 and [x[2] for x in r.sent] == ["warn", "warn"] and naps == [60] and _wd()["push"]["state"] == "failed"
    # notify.send(resend=True)：同一条再发，不再记进通知记录
    monkeypatch.setenv("QBREAK_WEBHOOK", SECRET)
    monkeypatch.setattr(notify.urllib.request, "urlopen", lambda req, timeout=None: _Resp())
    n0 = len(notify.history(500))
    assert notify.send("t", "x", "warn")["webhook"] is True and len(notify.history(500)) == n0 + 1
    assert notify.send("t", "x", "warn", resend=True)["webhook"] is True and len(notify.history(500)) == n0 + 1


def test_watchdog_pushes_once_a_day_when_the_check_itself_crashes(tmp_path, monkeypatch):
    """自检程序自己出错（2026-10-14 复核：以前只写日志、退出 1，当天一条推送都没有，看起来和 Mac 关机一样）→ 推一条 warn
    「★ HH:MM 自检出错」（只写异常的类型名，不带路径 / 值）+ Mac 通知，同一天只一次；今天还没有判定结果 → 写 ok = None（面板 ★）；
    已经判定过 → 不盖掉；--dry 照常抛（只给对话看）。"""
    from qbreak import mac_status, panel
    _book(orders=[_o("a", "SENT")])
    real = watchdog.evaluate

    def boom(tag, now=None):
        raise TypeError(f"bad value at {paths.home()}/state/x.json SECRET")
    monkeypatch.setattr(watchdog, "evaluate", boom)
    rc, r, out = _run(tmp_path)
    assert rc == 1 and len(r.sent) == 1 and len(r.macs) == 1
    title, text, level = r.sent[0]
    assert title == "qbreak 立花实盘 ★ 09:30 自检出错" and level == "warn"
    assert text == "TypeError：这次没判定（今天早上的单下没下还不知道）。\n在 Mac 对话里说「看一下自检日志」"
    wd = _wd()
    assert wd["ok"] is None and wd["note"].startswith("自检程序出错（TypeError）") and wd["push"]["state"] == "sent"
    leaked = text + r.macs[0][1] + out + json.dumps(wd, ensure_ascii=False)
    assert "SECRET" not in leaked and str(paths.home()) not in leaked
    book = json.loads((paths.state_dir() / "live_unified_tachibana.json").read_text(encoding="utf-8"))
    top = "\n".join(h for _, h in panel._run_lines("tachibana", book, TUE.replace(minute=40), None))
    assert "★ 自检（09:30）判定不了：自检程序出错（TypeError）" in top
    assert mac_status._watchdog_item("tachibana", TUE.replace(minute=40))["level"] == "warn"
    rc, r, out = _run(tmp_path, now=TUE.replace(minute=45))                       # 同一天再出错：不再推
    assert rc == 1 and not r.sent and not r.macs and "今天已经推过「自检出错」" in out
    with pytest.raises(TypeError):                                                 # --dry：照常抛（run.main 记日志、退出 1）
        watchdog.run(_agents(tmp_path), TUE, send=r.send, beat=r.beat, mac=r.mac, out=lambda *a: None, dry=True)
    assert not r.sent
    monkeypatch.setattr(watchdog, "evaluate", real)                                # 第二天：先通过（推了），之后再出错 → 推一次、不盖掉通过
    _book(last="2026-10-06", orders=[])
    rc, r, out = _run(tmp_path, now=TUE + dt.timedelta(days=1))
    assert rc == 0 and _wd()["ok"] is True
    monkeypatch.setattr(watchdog, "evaluate", boom)
    rc, r, out = _run(tmp_path, now=TUE + dt.timedelta(days=1, hours=1))
    assert rc == 1 and [x[0] for x in r.sent] == ["qbreak 立花实盘 ★ 10:30 自检出错"]
    assert _wd()["ok"] is True and _wd()["at"] == "2026-10-07T09:30:00+09:00"


def test_watchdog_command_pushes_when_the_check_crashes(tmp_path, monkeypatch, capsys):
    """run.py live-watchdog（LaunchAgent 走的路）：自检出错 → 退出 1，但推了一条、写了结果文件（以前 run.main 只记日志）。"""
    import run
    _book(orders=[_o("a", "SENT")])
    sent = []
    monkeypatch.setattr(notify, "send", lambda t, x, lv="info", **k: sent.append((t, lv)) or {"push": True})
    monkeypatch.setattr(watchdog, "evaluate", lambda tag, now=None: (_ for _ in ()).throw(TypeError("x")))
    assert run.main(["live-watchdog", "--agents", str(_agents(tmp_path))]) == 1
    assert len(sent) == 1 and sent[0][0].endswith("自检出错") and sent[0][1] == "warn"
    assert _wd()["ok"] is None and "TypeError" in _wd()["note"]


def test_watchdog_command_uses_agents_dir(tmp_path, monkeypatch, capsys):
    import run
    monkeypatch.setenv("QBREAK_LAUNCH_AGENTS", str(tmp_path / "none"))
    assert run.main(["live-watchdog"]) == 0 and "只打印" in capsys.readouterr().out
    assert run.main(["live-watchdog", "--agents", str(tmp_path / "none2")]) == 0


# ────────── ④ 上线检查 ⑧ ──────────
def _sub_push():
    from qbreak import webpush as WP
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    pub = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,
                                                                             serialization.PublicFormat.UncompressedPoint)
    assert WP.subscribe("iPhone", {"endpoint": "https://web.push.apple.com/x-ENDPOINT",
                                   "keys": {"p256dh": WP.b64u(pub), "auth": WP.b64u(b"0" * 16)}})[0]


def test_gate_alert_items(tmp_path, monkeypatch):
    from qbreak import live_gate as G
    agents = tmp_path / "agents"
    agents.mkdir()

    def fake(kc, listing=""):
        calls = []
        base = _kc(kc, calls=calls)

        def run_(args, **kw):
            if args[0] == "security":
                return base(args, **kw)
            calls.append(list(args))
            return subprocess.CompletedProcess(args, 0, listing if args[0] == "launchctl" else "", "")
        return run_, calls
    names = ("⑧ 手机通知通道（qbreak 推送）", "⑧ 每天的自检推送（Mac 没跑的提醒）", "⑧ 09:30 自检任务（com.qbreak.watchdog）")
    monkeypatch.setenv("QBREAK_WEBHOOK", SECRET)                                   # 环境变量有、钥匙串没有 → 定时任务读不到
    run_, calls = fake({})
    items = {it["name"]: it for it in G.check(agents=agents, run=run_)}
    assert [items[n]["ok"] for n in names] == [False, False, False]
    assert "还没有设备打开 qbreak 推送" in items[names[0]]["text"] and "email-setup" not in items[names[0]]["text"]
    assert "推不到手机" in items[names[1]]["text"] and "每个工作日 09:30 自检推一条到手机（2026-10-14 起代替外部心跳）" in items[names[1]]["text"]
    assert "没装" in items[names[2]]["text"]
    assert all("-w" not in c for c in calls if c[0] == "security")                # 只查有没有
    assert not any(c[0] == "security" and "qbreak-heartbeat" in c for c in calls)  # 外部心跳不再查
    (agents / "com.qbreak.watchdog.plist").write_text("x", encoding="utf-8")
    run_, calls = fake({"qbreak-smtp": "x"})
    items = {it["name"]: it for it in G.check(agents=agents, run=run_)}
    assert [items[n]["ok"] for n in names] == [True, True, False] and "没加载" in items[names[2]]["text"]
    assert "qbreak-smtp" in items[names[0]]["text"] and "下一次 09:30 自检确认" in items[names[1]]["text"]
    run_, calls = fake({"qbreak-webhook": "x"}, listing="-\t0\tcom.qbreak.watchdog\n")
    items = {it["name"]: it for it in G.check(agents=agents, run=run_)}
    assert [items[n]["ok"] for n in names] == [True, True, True]
    text, _ = G.report(list(items.values()))
    assert "心跳" not in text.replace("代替外部心跳", "") and "healthchecks" not in text and SECRET not in text

    def none(args, **kw):
        raise FileNotFoundError(args[0])                                          # 不是 macOS：前两项跳过，自检任务只看文件
    items = {it["name"]: it for it in G.check(agents=agents, run=none)}
    assert [items[n]["ok"] for n in names] == [None, None, True]


def test_gate_daily_push_passes_with_a_push_subscription_and_no_heartbeat(tmp_path):
    """⑧ 有设备打开 qbreak 推送 → 不用外部心跳、不用 webhook / 邮件也满足（2026-10-14）；最近一次自检的推送没发成 → ★，发成了 → 满足。
    推送的订阅只数台数（地址不出现在结果里）。"""
    from qbreak import live_gate as G
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "com.qbreak.watchdog.plist").write_text("x", encoding="utf-8")

    def run_(args, **kw):
        if args[0] == "security":
            return subprocess.CompletedProcess(args, 44, "", "")                  # 钥匙串里什么都没有（也没有 qbreak-heartbeat）
        return subprocess.CompletedProcess(args, 0, "-\t0\tcom.qbreak.watchdog\n" if args[0] == "launchctl" else "", "")
    _sub_push()
    names = ("⑧ 手机通知通道（qbreak 推送）", "⑧ 每天的自检推送（Mac 没跑的提醒）", "⑧ 09:30 自检任务（com.qbreak.watchdog）")
    items = {it["name"]: it for it in G.check(agents=agents, run=run_)}
    assert [items[n]["ok"] for n in names] == [True, True, True]
    assert "推送已打开的设备 1 台" in items[names[0]]["text"] and "ENDPOINT" not in json.dumps(items, ensure_ascii=False)
    (paths.out_dir() / "watchdog_paper.json").write_text(json.dumps(
        {"at": "2026-10-06T09:30:00+09:00", "ok": True, "push": {"at": "2026-10-06T09:30:00+09:00", "state": "failed",
                                                                   "why": "推送（网页 App） 失败"}}), encoding="utf-8")
    it = {x["name"]: x for x in G.check(agents=agents, run=run_)}[names[1]]
    assert it["ok"] is False and "★ 最近一次（2026-10-06 09:30）自检的推送没发成（推送（网页 App） 失败" in it["text"]
    (paths.out_dir() / "watchdog_tachibana.json").write_text(json.dumps(
        {"at": "2026-10-07T09:30:00+09:00", "ok": True, "push": {"at": "2026-10-07T09:30:00+09:00", "state": "sent",
                                                                   "why": "推送（网页 App） 已发"}}), encoding="utf-8")
    it = {x["name"]: x for x in G.check(agents=agents, run=run_)}[names[1]]
    assert it["ok"] is True and "最近一次 2026-10-07 09:30 已推送" in it["text"]
    (paths.out_dir() / "watchdog_tachibana.json").write_text(json.dumps(
        {"at": "2026-10-08T09:30:00+09:00", "ok": True, "push": {"at": "2026-10-08T09:30:00+09:00", "state": "none",
                                                                   "why": "没有设备"}}), encoding="utf-8")
    it = {x["name"]: x for x in G.check(agents=agents, run=run_)}[names[1]]
    assert it["ok"] is True                                                       # 那次还没有通道、之后打开了推送：等下一次确认
