"""通知到手机 + 「Mac 没跑」的提醒（2026-10-09 立花实盘缺口 A1：条目 LU-04 / OPS-01 / UX-03 / LU-05 / OPS-02）：
① qbreak/notify.py：环境变量优先、没有时读钥匙串（注入的 run；只查有没有时不加 -w）；Discord / Slack 发 JSON、ntfy 发纯文本；
   失败只记 warning（不含地址）、绝不抛；外部心跳成功 / 失败的地址；
② run.py notify（--test / --subject）不打印任何值；
③ qbreak/watchdog.py（09:30 自检）：没装 / 还早 / 休市 / 跑完 / 没跑完 / 执行器停下 / 状态不明 / DEFERRED / HALT（同一天只提醒一次）；
④ 上线检查「准备」的 ⑧ 三项（手机通知通道、外部心跳、09:30 自检任务）。全部只用假的 run / urlopen / 临时目录，不联网、不调真的 security。"""
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


# ────────── ② run.py notify ──────────
def test_notify_command_never_prints_values(monkeypatch, posts, capsys):
    import run
    assert run.main(["notify", "--test"]) == 3
    out = capsys.readouterr().out
    assert "webhook：没设置" in out and "security add-generic-password -s qbreak-webhook -a qbreak -w" in out
    monkeypatch.setenv("QBREAK_WEBHOOK", SECRET)
    monkeypatch.setenv("QBREAK_HEARTBEAT", BEAT)
    assert run.main(["notify", "--test"]) == 0
    out = capsys.readouterr().out
    assert "webhook：已发" in out and "邮件：没设置" in out and "外部心跳：已设置（测试不 ping" in out
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
        self.sent, self.beats, self.macs = [], [], []

    def send(self, title, text, level="info"):
        self.sent.append((title, text, level))
        return {"webhook": True, "email": None}

    def beat(self, ok, msg=""):
        self.beats.append((ok, msg))
        return True

    def mac(self, title, text):
        self.macs.append((title, text))
        return True


def _run(tmp_path, now=TUE, kind="tachibana"):
    r = _Rec()
    lines = []
    rc = watchdog.run(_agents(tmp_path, kind), now, send=r.send, beat=r.beat, mac=r.mac, out=lines.append)
    return rc, r, "\n".join(lines)


def _wd(tag="tachibana"):
    return json.loads(watchdog.path(tag).read_text(encoding="utf-8"))


def test_watchdog_not_installed_or_too_early_sends_nothing(tmp_path):
    rc, r, out = _run(tmp_path, kind=None)
    assert rc == 0 and not r.sent and not r.beats and "只打印" in out
    _book(last="2026-10-02")
    rc, r, out = _run(tmp_path, now=TUE.replace(hour=8, minute=10))
    assert rc == 0 and not r.sent and not r.beats and "之前不判定" in out and not watchdog.path("tachibana").exists()


def test_watchdog_holiday_and_done_ping_success_without_notifying(tmp_path):
    _book(last="2026-10-02")                                                      # 周六：休市（账本怎样都不算）
    rc, r, out = _run(tmp_path, now=dt.datetime(2026, 10, 10, 9, 30, tzinfo=JST))
    assert rc == 0 and not r.sent and r.beats == [(True, "qbreak 立花实盘：2026-10-10 休市")] and _wd()["ok"] is True
    rc, r, out = _run(tmp_path, now=dt.datetime(2026, 10, 12, 9, 30, tzinfo=JST))  # スポーツの日
    assert rc == 0 and r.beats[0][0] is True and "休市" in r.beats[0][1]
    _book(orders=[_o("a", "SENT"), _o("b", "FILLED", side="SELL")])
    rc, r, out = _run(tmp_path)
    assert rc == 0 and not r.sent and not r.macs and r.beats[0][0] is True and "自检通过" in out
    assert _wd() == {"at": "2026-10-06T09:30:00+09:00", "ok": True, "reasons": [], "halt": None, "note": ""}


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
    assert rc == 1 and r.sent[0][1] == "- 今天的单没下：持仓与券商不一致：7203.T"   # 跑完了：不说「没有跑完」；原因说过的单不再逐笔列
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
    assert "- 决策 2026-10-05 处理了，但有 2 笔没下：7203.T 买 100 股 被挡：未 ARM；1655.T 卖 100 口 被拒：余力不足" in r.sent[0][1]


def test_watchdog_paper_before_the_sim_start_is_not_a_failure(tmp_path):
    """模拟账户在模拟期开始日之前故意不推进（run.py live-u）：不算失败，心跳成功、不通知。"""
    _book(tag="paper", last="2026-09-18")
    (paths.home() / "sim.json").write_text(json.dumps({"mode": "unified", "start": "2026-10-13"}), encoding="utf-8")
    rc, r, out = _run(tmp_path, kind="paper")
    assert rc == 0 and not r.sent and r.beats == [(True, "qbreak 模拟操盘：模拟期开始日 2026-10-13 之前（模拟账户还不推进）")]
    assert _wd("paper")["ok"] is True
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
    assert rc == 0 and naps == [15, 15] and not r.sent and r.beats[0][0] is True
    assert "等它结束再判定" in lines[0] and _wd()["at"] == "2026-10-06T09:30:30+09:00"
    lock = RunLock(paths.state_dir() / "live_unified_tachibana.lock").acquire()  # 一直不结束：不判定、不发
    try:
        r = _Rec()
        lines = []
        rc = watchdog.run(_agents(tmp_path), TUE, send=r.send, beat=r.beat, mac=r.mac, out=lines.append, sleep=lambda s: None)
    finally:
        lock.release()
    assert rc == 0 and not r.sent and not r.beats and not r.macs and "这次不判定" in lines[-1]


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
    agents = _agents(tmp_path, "paper")
    assert run.main(["live-watchdog", "--agents", str(agents)]) == 2
    assert calls == [] and "不能放进仓库的 var/" in capsys.readouterr().out and list(repo.rglob("*")) == []


def test_watchdog_unknown_orders_and_deferred_buys(tmp_path):
    _book(orders=[_o("a", "ERROR", d="2026-10-02", side="SELL"), _o("b", "DEFERRED")])
    rc, r, out = _run(tmp_path, now=TUE.replace(minute=20))                       # 09:20：开盘后的补单可能还在跑 → 不算 DEFERRED
    assert rc == 1 and "有状态不明的单 1 笔（7203.T 卖 100）" in r.sent[0][1] and "kabuka.e-shiten.jp" in r.sent[0][1]
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
    assert rc == 0 and r.beats[0][0] is True and len(r.sent) == 1 and r.sent[0][2] == "info"
    assert r.sent[0][0] == "qbreak 立花实盘：HALT 生效中" and "HALT 2026-10-05 用户说停" in r.sent[0][1]
    assert "另外：今天早上的执行器没有跑完" in r.sent[0][1]
    assert _wd()["ok"] is True and _wd()["halt"].startswith("HALT 2026-10-05")
    rc, r, out = _run(tmp_path, now=TUE.replace(minute=45))                        # 同一天再跑：不再提醒，心跳照发
    assert rc == 0 and not r.sent and not r.macs and r.beats[0][0] is True and "今天已经提醒过" in out
    rc, r, out = _run(tmp_path, now=TUE + dt.timedelta(days=1))                    # 第二天：再提醒一次
    assert len(r.sent) == 1


def test_watchdog_command_uses_agents_dir(tmp_path, monkeypatch, capsys):
    import run
    monkeypatch.setenv("QBREAK_LAUNCH_AGENTS", str(tmp_path / "none"))
    assert run.main(["live-watchdog"]) == 0 and "只打印" in capsys.readouterr().out
    assert run.main(["live-watchdog", "--agents", str(tmp_path / "none2")]) == 0


# ────────── ④ 上线检查 ⑧ ──────────
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
    names = ("⑧ 手机通知通道（webhook / 邮件）", "⑧ 外部心跳（Mac 没跑的提醒）", "⑧ 09:30 自检任务（com.qbreak.watchdog）")
    monkeypatch.setenv("QBREAK_WEBHOOK", SECRET)                                   # 环境变量有、钥匙串没有 → 定时任务读不到
    run_, calls = fake({})
    items = {it["name"]: it for it in G.check(agents=agents, run=run_)}
    assert [items[n]["ok"] for n in names] == [False, False, False]
    assert "定时任务读不到" in items[names[0]]["text"] and "healthchecks.io" in items[names[1]]["text"]
    assert "没装" in items[names[2]]["text"]
    assert all("-w" not in c for c in calls if c[0] == "security")                # 只查有没有
    (agents / "com.qbreak.watchdog.plist").write_text("x", encoding="utf-8")
    run_, calls = fake({"qbreak-smtp": "x", "qbreak-heartbeat": BEAT})
    items = {it["name"]: it for it in G.check(agents=agents, run=run_)}
    assert [items[n]["ok"] for n in names] == [True, True, False] and "没加载" in items[names[2]]["text"]
    assert "qbreak-smtp" in items[names[0]]["text"] and BEAT not in json.dumps(items, ensure_ascii=False)
    run_, calls = fake({"qbreak-webhook": "x"}, listing="-\t0\tcom.qbreak.watchdog\n")
    items = {it["name"]: it for it in G.check(agents=agents, run=run_)}
    assert [items[n]["ok"] for n in names] == [True, False, True]
    text, _ = G.report(list(items.values()))
    assert "[★ 未完成] ⑧ 外部心跳" in text and SECRET not in text

    def none(args, **kw):
        raise FileNotFoundError(args[0])                                          # 不是 macOS：前两项跳过，自检任务只看文件
    items = {it["name"]: it for it in G.check(agents=agents, run=none)}
    assert [items[n]["ok"] for n in names] == [None, None, True]
