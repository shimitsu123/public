"""面板 / 提醒的缺口（2026-10-14 G9 / G10 / G18 / G19 / G20 / G23 / G24）：
G9  早上的运行没完成时盘中点的买卖不再说「马上」；模拟账户面板自动补跑（立花不补跑）；
G10 同一只票等上一笔成交的指令不再每 3 分钟叫一次执行器、什么都没变的重试不再通知；
G18 盘中没下成、盘中已经结束的指令写「改到开盘」（不再写「10 分钟后再试」），收盘后提醒一次；
G20 07:45〜08:55（以前 08:50）、决策做了但有单被挡也补寄付单；重试说清「决策做了，有单没下」；
G23 面板自动下单暂停时通知一次、暂停记进状态目录（面板重启也接着停）、之后执行器跑成一次就恢复；
G24 09:30 自检报「该下了还没下的手动指令」；自检只等 liveu.sh 的运行标记（不等让 Mac 醒着的那段）；冒烟测试的 Mac 通知一天一次。"""
import datetime as dt
import json
import os
import shutil
import subprocess
import time

import pytest

import qbreak.calendar_jp as CJ
from qbreak import manual_orders as MO
from qbreak import notify_seen as NS
from qbreak import panel, paths
from qbreak import run_status as RS
from qbreak import watchdog as WD
from qbreak.calendar_jp import JST, next_trading_day

from test_manual_now import _at, _morning, _paper, _quote, _req
from test_manual_orders import TAG, _Run, _sell_req
from test_panel import _book
from test_run_status import _book_dict, _fake_run, _o
from test_shell_scripts import _bash, _calls, _run_env


class _Proc:
    def __init__(self, rc):
        self.rc = rc

    def poll(self):
        return self.rc


def _clock(monkeypatch, t: dt.datetime):
    """假时钟（JST 时刻 + 单调秒数）；expected_last_bar 也看它。"""
    now = {"t": t, "m": 1000.0}
    monkeypatch.setattr(CJ, "now_jst", lambda: now["t"])

    def step(sec: float) -> None:
        now["t"] += dt.timedelta(seconds=sec)
        now["m"] += sec
    return now, step


# ────────── G9：早上的运行没完成时的「什么时候下单」+ 模拟账户补跑 ──────────
def test_when_for_says_after_the_catch_up_when_the_morning_run_is_behind():
    behind, ok = {"state": {"last_date": "2026-10-02"}}, {"state": {"last_date": "2026-10-05"}}
    t = dt.datetime(2026, 10, 6, 10, 0, tzinfo=JST)                    # 火曜：应处理到 10-05
    s = MO.when_for(t, behind)
    assert s.startswith("补跑早上的运行之后") and "10/07 开盘" in s
    assert MO.when_for(t.replace(hour=12), behind).startswith("补跑早上的运行之后")     # 午休也一样
    assert MO.when_for(t, ok) == MO.when_for(t, {}) == "马上（盘中）"                 # 完成了 / 没有账本：照常
    assert MO.when_for(t.replace(hour=8), behind) == "今天 09:00 开盘"               # 开盘前：早上的运行自己会读到
    assert MO.when_for(t.replace(hour=15, minute=40), behind) == "10/07 开盘"
    assert MO.morning_behind(behind, t) and not MO.morning_behind(ok, t) and not MO.morning_behind({}, t)


def test_submit_and_render_say_after_the_catch_up(monkeypatch):
    t = dt.datetime(2026, 10, 6, 10, 0, tzinfo=JST)
    monkeypatch.setattr(CJ, "now_jst", lambda: t)
    _book(last="2026-10-02")
    ok, msg, _ = panel.submit({"book": "paper", "kind": "sell", "ticker": "7203"}, t)
    assert ok and "补跑早上的运行之后" in msg and "马上（盘中）" not in msg
    assert "补跑早上的运行之后" in panel.render("paper", "t" * 40, t)
    _book(last="2026-10-05")
    ok, msg, _ = panel.submit({"book": "paper", "kind": "core", "pct": 50}, t)        # 完成了：照常「马上」
    assert ok and "马上（盘中）照新比例调" in msg, msg


def test_runs_active_sees_only_live_fresh_markers(tmp_path):
    ld = paths.log_dir()
    me = ld / f".running.paper.{os.getpid()}"
    me.write_text("", encoding="utf-8")
    p = subprocess.Popen(["true"])
    p.wait()
    (ld / f".running.paper.{p.pid}").write_text("", encoding="utf-8")       # 进程已经没了
    (ld / ".running.paper.abc").write_text("", encoding="utf-8")            # 读不了
    (ld / f".running.tachibana.{os.getpid()}").write_text("", encoding="utf-8")
    assert RS.runs_active("paper") == [os.getpid()]
    assert RS.runs_active() == [os.getpid(), os.getpid()]
    old = time.time() - RS.RUN_MARK_MAX_S - 60
    os.utime(me, (old, old))                                                # 3 小时以前的：不算
    assert RS.runs_active("paper") == []


def _paper_agent():
    ag = paths.launch_agents()
    ag.mkdir(parents=True, exist_ok=True)
    (ag / f"{paths.PAPER_AGENT}.plist").write_text("x", encoding="utf-8")


def test_trigger_catches_up_a_missed_paper_morning_run_at_most_3_times(monkeypatch):
    now, step = _clock(monkeypatch, dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST))
    calls = []
    trg = panel.Trigger(run=lambda tag, mode="retry": calls.append((now["m"], tag, mode)) or _Proc(0),
                        clock=lambda: now["t"], mono=lambda: now["m"], notify=lambda *a: None)
    _book(last="2026-10-02")                                               # 07:40 没跑（Mac 睡着）
    assert trg.check() == []                                               # 没装 07:40 的定时任务：不补跑
    _paper_agent()
    assert trg.check() == [] and calls == []                               # 第一次看到：先等 2 分钟（launchd 自己会拉起错过的）
    step(90)
    assert trg.check() == []
    step(30)
    assert trg.check() == ["paper"] and calls == [(now["m"], "paper", "catchup")]
    for _ in range(int(3 * 3600 / 30)):                                    # 一直没完成：同一天最多 3 次、相隔至少 20 分钟
        step(30)
        trg.check()
    assert [c[2] for c in calls] == ["catchup"] * 3
    assert all(b[0] - a[0] >= panel.CATCHUP_GAP_S for a, b in zip(calls, calls[1:]))
    cls, txt = trg.status("paper", now["t"])
    assert cls == "neg" and "面板已经补跑了 3 次还是没完成" in txt
    _book(last="2026-10-05")                                               # 补上了：不再说
    assert trg.status("paper", now["t"]) is None


def test_trigger_does_not_catch_up_while_a_run_is_active_or_halted_or_live(monkeypatch):
    now, step = _clock(monkeypatch, dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST))
    calls = []
    mk = (lambda: panel.Trigger(run=lambda tag, mode="retry": calls.append(mode) or _Proc(0), clock=lambda: now["t"],
                                mono=lambda: now["m"], notify=lambda *a: None))
    _paper_agent()
    _book(last="2026-10-02")
    mark = paths.log_dir() / f".running.paper.{os.getpid()}"
    mark.write_text("", encoding="utf-8")                                  # liveu.sh run 还在跑（拉代码 / 等云端）
    trg = mk()
    for _ in range(10):
        trg.check()
        step(30)
    assert calls == []
    mark.unlink()
    paths.halt_file().write_text("x", encoding="utf-8")                    # HALT：不补跑
    for _ in range(10):
        trg.check()
        step(30)
    assert calls == []
    paths.halt_file().unlink()
    (paths.launch_agents() / f"{paths.LIVE_AGENT}.plist").write_text("x", encoding="utf-8")   # 装了立花本番：模拟账户不补跑
    trg = mk()
    for _ in range(10):
        trg.check()
        step(30)
    assert calls == []
    assert trg._catchup_due("tachibana", {"state": {"last_date": "2026-10-02"}}, now["t"]) is False   # 立花永远不补跑
    (paths.launch_agents() / f"{paths.LIVE_AGENT}.plist").unlink()
    now["t"] = dt.datetime(2026, 10, 6, 15, 30, tzinfo=JST)                # 15:30 之后不补跑
    trg = mk()
    for _ in range(10):
        trg.check()
        step(30)
    assert calls == []


# ────────── G10：等上一笔成交的指令不再每 3 分钟叫一次 ──────────
def test_sell_after_a_placed_trim_waits_for_the_fill_without_retrying_every_3_minutes(monkeypatch):
    r = _Run([1000.0] * 40, entry=(10,), bear_all=True)
    r.until(14)
    _sell_req(r, kind="trim", pct=15.0)
    r.day()                                                                # 07:40：减仓变成今天开盘的寄付单
    t0 = r.at(r.k - 1, 8, 0)
    with open(MO.requests_path(TAG), "a", encoding="utf-8") as f:          # 08:00 又写同一只票「卖出全部」
        f.write(json.dumps({"kind": "sell", "ticker": "A.T", "block_days": 20, "source": "test", "id": "M-sell",
                            "at": t0.isoformat()}) + "\n")
    monkeypatch.setattr(panel, "books", lambda: [TAG])
    monkeypatch.setattr(panel, "_load", lambda tag: (r.ux.book, {}))
    clk = {"t": t0, "m": 0.0}
    calls = []

    def run(tag, mode):
        calls.append(mode)
        r.now["t"] = clk["t"]
        r.ux.morning([])                                                   # 同一决策的补单（重试）
        return _Proc(0)
    trg = panel.Trigger(run=run, clock=lambda: clk["t"], mono=lambda: clk["m"], notify=lambda *a: None)
    while clk["t"].time() < dt.time(8, 55):
        trg.check()
        clk["t"] += dt.timedelta(seconds=30)
        clk["m"] += 30
    assert calls == ["retry"]                                              # 以前：08:00〜08:55 每 3 分钟一次（约 18 次）
    it = r.item("M-sell")
    assert it["status"] == "pending" and it.get("wait") == "prev" and it["msg"].startswith("等 A.T 的上一笔成交")
    assert MO.status_text(it) == "等上一笔成交" and not MO.due(TAG, r.ux.book, t0)
    r.day()                                                                # 第二天早上：上一笔记完 → 照常处理
    it = r.item("M-sell")
    assert "wait" not in it and it["status"] != "pending"


def test_retry_for_manual_instructions_does_not_notify_when_nothing_changed(monkeypatch, capsys):
    import run
    bk = _book_dict([_o("U-S", "SENT", side="SELL")])
    sent = _fake_run(monkeypatch, bk)
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(bk), encoding="utf-8")   # 重试先读账本文件
    monkeypatch.setattr(run, "_manual_due", lambda tag, b: True)
    assert run.main(["live-u", "--broker", "paper", "--retry", "--force", "--notify"]) == 0
    assert sent == [] and "不再发通知" in capsys.readouterr().out
    snaps = iter([{}, {"M1": ("placed", "x")}])                            # 运行前后指令的状态变了 → 照常通知
    monkeypatch.setattr(run, "_manual_snap", lambda b: next(snaps))
    assert run.main(["live-u", "--broker", "paper", "--retry", "--force", "--notify"]) == 0
    assert [x[0] for x in sent] == ["mac", "send"]


# ────────── G20：08:55 截止、决策做了但有单被挡 ──────────
def test_trigger_window_ends_at_the_open_cutoff_and_covers_a_decision_with_blocked_orders(monkeypatch):
    assert panel.TRIGGER_UNTIL == MO.CUTOFF == dt.time(8, 55)
    now, step = _clock(monkeypatch, dt.datetime(2026, 10, 6, 8, 52, tzinfo=JST))
    calls = []
    trg = panel.Trigger(run=lambda tag, mode="retry": calls.append(mode) or _Proc(0), clock=lambda: now["t"],
                        mono=lambda: now["m"], notify=lambda *a: None)
    blocked = {"cid": "U2026-10-05-BUY-6758.T", "ticker": "6758.T", "side": "BUY", "decided_on": "2026-10-05", "status": "BLOCKED",
               "qty": 100, "note": "行情没更新"}
    _book(last="2026-10-05", orders=[blocked])                             # 决策做了，有单被挡（以前 = 「没完成」→ 不叫）
    MO.append("paper", {"kind": "sell", "ticker": "7203"})
    assert trg.check() == ["paper"] and calls == ["retry"]                 # 08:52：还来得及加进寄付单
    trg.last.clear()
    now["t"] = dt.datetime(2026, 10, 6, 8, 55, tzinfo=JST)
    assert trg.check() == []


def test_retry_says_the_decision_was_made_but_orders_were_not_sent(monkeypatch, capsys):
    import run
    bk = _book_dict([_o("U-B", "BLOCKED"), _o("U-S", "SENT", side="SELL")])
    _fake_run(monkeypatch, bk)
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(bk), encoding="utf-8")
    assert run.main(["live-u", "--broker", "paper", "--retry", "--force"]) == 0
    out = capsys.readouterr().out
    assert "今天早上的决策做了（决策日 2026-10-08），但有 1 笔单没下（被挡 / 还没发）" in out and "运行没有完成" not in out


# ────────── G18：盘中没下成 → 改到开盘 ──────────
def test_instruction_tried_in_the_session_rolls_over_to_the_next_open(monkeypatch):
    r = _paper("ro")
    _morning(r, until=14)
    rq = _req(r, kind="sell", ticker="A.T")
    r.now["t"] = _at(r, 15, 0)
    res = r.ux.now_phase(_quote({}))                                       # 取不到现价：一会儿再试
    it = r.ux.book["manual"]["items"][rq["id"]]
    assert res["retry"] == 1 and it["status"] == "pending" and "分钟后再试" in it["msg"]
    assert MO.rolled_over(it, _at(r, 15, 0)) is None and MO.msg_text(it, _at(r, 15, 0)) == it["msg"]   # 盘中：照旧
    t1 = _at(r, 15, 30)
    nd = next_trading_day(t1.date())
    assert MO.rolled_over(it, t1) == nd
    assert MO.status_text(it, t1) == f"今天盘中没下成 → {nd:%m/%d} 开盘（寄付）"
    assert "分钟后再试" not in MO.msg_text(it, t1) and MO.msg_text(it, t1).startswith("取不到现价")
    assert MO.status_text(it, _at(r, 8, 0, days=1)) == f"{t1:%m/%d} 盘中没下成 → {nd:%m/%d} 开盘（寄付）"
    assert MO.rolled_over(it, _at(r, 8, 55, days=1)) is None              # 那天的寄付也过了：不再这么写
    assert any("今天盘中没下成" in ln for ln in MO.lines({"items": [it]}, today=t1.date().isoformat(), now=t1))
    sent = []
    monkeypatch.setattr(panel, "books", lambda: [r.tag])
    monkeypatch.setattr(panel, "_load", lambda tag: (r.ux.book, {}))
    mk = (lambda t: panel.Trigger(run=lambda *a: _Proc(0), clock=lambda: t, mono=lambda: 0.0,
                                  notify=lambda tag, title, text, level="warn": sent.append((title, text, level))))
    mk(_at(r, 15, 20)).check()                                             # 15:25 之前不汇总（盘中照常叫执行器再试）
    assert sent == []
    trg = mk(t1)
    trg.check()
    trg.check()
    assert len(sent) == 1 and sent[0][0].endswith("盘中没下成、改到开盘：1 条") and f"{nd:%m/%d} 开盘（寄付）" in sent[0][1]
    assert "分钟后再试" not in sent[0][1] and sent[0][2] == "info"
    mk(_at(r, 15, 40)).check()                                             # 面板重启：同一天同一段文字不再发
    assert len(sent) == 1


# ────────── G23：暂停通知一次、记进状态目录、跑成一次就恢复 ──────────
def test_pause_is_notified_once_persisted_and_lifted_by_a_successful_run(monkeypatch):
    now, step = _clock(monkeypatch, dt.datetime(2026, 10, 6, 9, 30, tzinfo=JST))
    sent, calls, rcs = [], [], [3, 3, 3]

    def mk():
        return panel.Trigger(run=lambda tag, mode="retry": calls.append(mode) or _Proc(rcs.pop(0) if rcs else 0),
                             clock=lambda: now["t"], mono=lambda: now["m"],
                             notify=lambda tag, title, text, level="warn": sent.append((tag, title, text)))
    trg = mk()
    _book(last="2026-10-05")
    MO.append("paper", {"kind": "sell", "ticker": "7203"})
    for _ in range(40):                                                    # 3 次失败（60 → 120 → 240 秒的退避）→ 暂停
        trg.check()
        step(30)
    assert len(calls) == 3 and trg.paused["paper"][0] == "2026-10-06"
    assert len(sent) == 1 and "面板自动下单今天暂停" in sent[0][1] and "再试一次" in sent[0][2]
    assert "再试一次" in trg.status("paper")[1]
    assert RS.trigger_paused("paper", "2026-10-06")["day"] == "2026-10-06"
    trg2 = mk()                                                            # 面板重启：接着停
    assert trg2.paused["paper"][0] == "2026-10-06"
    step(600)
    assert trg2.check() == [] and len(calls) == 3
    RS.write("paper", RS.build({}, phase="now", ok=True, rc=0, now=now["t"] + dt.timedelta(seconds=5)))   # 「再试一次」跑成了
    step(30)
    assert trg2.check() == ["paper"] and "paper" not in trg2.paused and RS.trigger_paused("paper") is None
    assert len(sent) == 1


def test_persisted_pause_expires_the_next_day(monkeypatch):
    now, step = _clock(monkeypatch, dt.datetime(2026, 10, 6, 9, 30, tzinfo=JST))
    (paths.state_dir() / RS.TRIGGER_FILE).write_text(json.dumps(
        {"paper": {"day": "2026-10-06", "why": "退出码 3", "ids": [], "at": "2026-10-06T09:20:00+09:00"}}), encoding="utf-8")
    assert "paper" in panel.Trigger(run=lambda *a: _Proc(0), clock=lambda: now["t"]).paused
    now["t"] = dt.datetime(2026, 10, 7, 9, 30, tzinfo=JST)
    assert panel.Trigger(run=lambda *a: _Proc(0), clock=lambda: now["t"]).paused == {}


# ────────── G24：自检报该下了还没下的手动指令 ──────────
def _pending(rid, at, **kw):
    return {"id": rid, "kind": "sell", "ticker": "7203.T", "status": "pending", "at": at, "source": "panel", "msg": "x", **kw}


def test_watchdog_reports_manual_instructions_that_should_have_been_placed():
    t = dt.datetime(2026, 10, 6, 9, 45, tzinfo=JST)
    items = {"M1": _pending("M1", "2026-10-06T08:20:00+09:00", msg="取不到现价，10 分钟后再试", tried="2026-10-06T09:05:00+09:00"),
             "M2": _pending("M2", "2026-10-06T08:21:00+09:00", hold="2026-10-06"),          # 明天开盘：不算
             "M3": _pending("M3", "2026-10-06T08:22:00+09:00", wait="prev"),                # 等上一笔成交：不算
             "M4": _pending("M4", "2026-10-06T08:23:00+09:00", tried="2026-10-06T09:40:00+09:00"),   # 刚试过：不算
             "M5": _pending("M5", "2026-10-06T09:40:00+09:00")}                             # 盘中刚写的（不到 10 分钟）：不算
    _book(last="2026-10-05", manual={"items": items})
    MO.append("paper", {"kind": "buy", "ticker": "6758"}, clock=lambda: dt.datetime(2026, 10, 6, 9, 20, tzinfo=JST))   # 面板没叫执行器
    rs = [x for x in WD.evaluate("paper", t)["reasons"] if "手动指令到现在还没下" in x]
    assert len(rs) == 1 and rs[0].startswith("有 2 条手动指令到现在还没下（面板没开")
    assert "M1（" in rs[0] and "执行器还没读到" in rs[0] and not any(f"M{i}（" in rs[0] for i in (2, 3, 4, 5))
    (paths.state_dir() / RS.TRIGGER_FILE).write_text(json.dumps(
        {"paper": {"day": "2026-10-06", "why": "退出码 3", "ids": [], "at": "2026-10-06T09:20:00+09:00"}}), encoding="utf-8")
    rs = [x for x in WD.evaluate("paper", t)["reasons"] if "手动指令到现在还没下" in x]
    assert "面板自动下单今天暂停了（退出码 3）" in rs[0]
    assert not [x for x in WD.evaluate("paper", t.replace(hour=9, minute=5))["reasons"] if "手动指令到现在还没下" in x]
    paths.halt_file().write_text("x", encoding="utf-8")                   # HALT：不下是预期的
    assert not [x for x in WD.evaluate("paper", t)["reasons"] if "手动指令到现在还没下" in x]


@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_watchdog_waits_only_for_live_run_markers(tmp_path):
    env, log = _run_env(tmp_path, 0, QBREAK_WATCHDOG_WAIT="2", QBREAK_WATCHDOG_POLL="0")
    logs = tmp_path / "lh" / "logs"
    logs.mkdir(parents=True)
    p = subprocess.Popen(["sleep", "30"])
    try:
        (logs / f".running.paper.{p.pid}").write_text("", encoding="utf-8")
        out, err = _bash(env, "scripts/liveu.sh", "watchdog")
        assert "执行器还在运行" in out and "py run.py live-watchdog" in _calls(log), err
    finally:
        p.kill()
        p.wait()
    env, log = _run_env(tmp_path, 0, QBREAK_WATCHDOG_WAIT="2", QBREAK_WATCHDOG_POLL="0")
    out, err = _bash(env, "scripts/liveu.sh", "watchdog")                 # 进程没了：不等，留下的标记删掉
    assert "执行器还在运行" not in out and not list(logs.glob(".running.*")) and "py run.py live-watchdog" in _calls(log)


@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_liveu_run_marks_itself_while_running_and_removes_the_marker(tmp_path):
    env, log = _run_env(tmp_path, 0)
    fp = tmp_path / "bin" / "fakepy"
    fp.write_text('#!/bin/sh\necho "py $*" >> "$CALLS"\n'
                  'case " $* " in *" -c "*) exit 0 ;; esac\n'
                  'case " $* " in *" live-u "*) ls -a "$QBREAK_HOME/logs" | grep "^\\.running\\." | sed "s/^/mark /" >> "$CALLS" ;; esac\n'
                  'case " $* " in *" live-u "*) exit "$FAKE_RC" ;; esac\nexit 0\n', encoding="utf-8")
    fp.chmod(0o755)
    _bash(env, "scripts/liveu.sh", "run", "--broker", "paper", "--retry")
    c = _calls(log)
    assert "mark .running.paper." in c                                     # 执行器运行时有标记
    assert not list((tmp_path / "lh" / "logs").glob(".running.*"))         # 跑完删掉


@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_smoke_failure_mac_alert_once_a_day(tmp_path):
    env, log = _run_env(tmp_path, 0, QBREAK_SMOKE_CMD="exit 1", QBREAK_NO_HOLD="1")
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "tachibana", "--retry")
    assert "冒烟测试没过" in out and _calls(log).count("osascript") == 1
    env, log = _run_env(tmp_path, 0, QBREAK_SMOKE_CMD="exit 1", QBREAK_NO_HOLD="1")
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "tachibana", "--retry")
    assert "冒烟测试没过" in out and "osascript" not in _calls(log)        # 同一天同一个原因：不再弹
    assert "--once tachibana" in _calls(log)                               # 手机通知照旧由 run.py notify --once 去重
