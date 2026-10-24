"""盘中执行器失败时不再每分钟重叫（2026-10-09 立花实盘缺口 A7：条目 UX-04 / C-01）：
① 面板的 Trigger 记下上一次叫的进程的退出码：盘中失败后等待加倍（60 → 120 → 240 秒）、同一天连续失败 3 次暂停（开盘前的重试也算）、
   新的手动指令 / 第二天恢复、成功一次清零；面板顶部显示暂停（文字转义）；
② 通知去重：「执行器停下」「拿不到运行锁」同一个账本、同一天、同一段文字只发一次 Mac / 手机通知（out/notify_seen_<账本>.json）。"""
import datetime as dt
import json

import pytest

import qbreak.calendar_jp as CJ
from qbreak import manual_orders as MO
from qbreak import notify_seen as NS
from qbreak import panel, paths
from qbreak import run_status as RS
from qbreak.calendar_jp import JST
from qbreak.live_unified import RunLock

from test_live_ops import _unified_home
from test_panel import _book
from test_run_status import _book_dict, _fake_run, _o


class _Proc:
    """假的子进程：poll() 返回退出码（None = 还在跑）。"""

    def __init__(self, rc):
        self.rc = rc

    def poll(self):
        return self.rc


@pytest.fixture()
def rig(monkeypatch):
    """假时钟（JST 时刻 + 单调秒数）+ 假的叫执行器（按顺序给退出码）。"""
    now = {"t": dt.datetime(2026, 10, 6, 9, 30, tzinfo=JST), "m": 1000.0}
    monkeypatch.setattr(CJ, "now_jst", lambda: now["t"])            # expected_last_bar 看的时钟
    calls, rcs = [], []

    def run(tag, mode="retry"):
        calls.append((tag, mode))
        return _Proc(rcs.pop(0) if rcs else 0)
    trg = panel.Trigger(run=run, clock=lambda: now["t"], mono=lambda: now["m"])

    def at(sec=None, t=None):                                         # 前进 sec 秒（单调时钟与 JST 时刻一起）
        if sec is not None:
            now["m"] += sec
            now["t"] += dt.timedelta(seconds=sec)
        if t is not None:
            now["t"] = t
        return trg.check()
    return trg, calls, rcs, at, now


def _fail_status(err, when):
    RS.write("paper", RS.build({}, phase="now", ok=False, rc=3, error=err, now=when))


def test_session_failures_back_off_then_pause_until_a_new_request(rig):
    trg, calls, rcs, at, now = rig
    _book(last="2026-10-05")
    MO.append("paper", {"kind": "sell", "ticker": "7203"})
    rcs.extend([3, 3, 3, 0])
    assert at() == ["paper"] and calls == [("paper", "now")]          # 第 1 次（失败）
    assert at(1) == []                                                 # 看到失败（退避从这时算起）
    assert trg.fails["paper"] == ("2026-10-06", 1)
    assert at(119) == []                                               # 失败 1 次 → 至少等 120 秒
    assert at(1) == ["paper"]                                          # 120 秒：第 2 次（失败）
    assert at(1) == [] and trg.fails["paper"][1] == 2
    assert at(239) == []                                               # 失败 2 次 → 至少等 240 秒
    assert at(1) == ["paper"] and len(calls) == 3                      # 240 秒：第 3 次（失败）
    _fail_status("执行器停下（状态没有改动）：有状态不明的单 <U1>", now["t"])
    assert at(30) == [] and trg.paused["paper"][0] == "2026-10-06"    # 连续 3 次 → 今天暂停
    assert at(5000) == [] and len(calls) == 3                          # 再久也不叫
    cls, txt = trg.status("paper")
    assert cls == "neg" and txt.startswith("★ 盘中自动下单暂停：执行器连续失败 3 次（执行器停下") and "修好后写新的指令或明天自动恢复" in txt
    html = panel.render("paper", "t" * 40, now["t"], trigger=trg)
    assert "★ 盘中自动下单暂停" in html and "&lt;U1&gt;" in html and "<U1>" not in html
    assert "盘中自动下单暂停" not in panel.render("paper", "t" * 40, now["t"])            # 不给 trigger（以前的调用）：不显示
    MO.append("paper", {"kind": "core", "pct": 50})                   # 修好后写了新的指令 → 恢复
    assert at(1) == ["paper"] and len(calls) == 4 and "paper" not in trg.paused and trg.status("paper") is None
    assert at(30) == [] and "paper" not in trg.fails                   # 成功一次 → 清零：回到 1 分钟一次
    assert at(31) == ["paper"]


def test_success_resets_the_count_and_the_next_day_resumes(rig):
    trg, calls, rcs, at, now = rig
    _book(last="2026-10-05")
    MO.append("paper", {"kind": "sell", "ticker": "7203"})
    rcs.extend([3, 3, 0, 3, 3])
    assert at() == ["paper"]
    assert at(1) == [] and at(120) == ["paper"]                        # 看到失败后 120 秒
    assert at(1) == [] and at(240) == ["paper"]                        # 第 3 次成功
    assert at(60) == ["paper"] and "paper" not in trg.fails            # 成功清零：60 秒就能再叫；第 4 次失败
    assert at(1) == [] and at(120) == ["paper"] and len(calls) == 5    # 失败 2 次（中间隔着一次成功）→ 不暂停
    assert at(60) == [] and "paper" not in trg.paused
    assert trg.status("paper")[0] == "muted" and "连续失败 2 次" in trg.status("paper")[1]
    rcs.extend([3])
    assert at(239) == []                                               # 失败 2 次：从看到失败（上面 at(60) 那一刻）起等 240 秒
    assert at(1) == ["paper"]
    assert at(60) == [] and trg.paused["paper"][0] == "2026-10-06"
    _book(last="2026-10-06")                                           # 第二天早上的运行完成（没读的指令不变）
    assert at(60, t=dt.datetime(2026, 10, 7, 9, 30, tzinfo=JST)) == ["paper"] and "paper" not in trg.paused
    assert trg.status("paper") is None


def test_morning_retry_counts_failures_without_doubling_and_pause_covers_the_session(rig):
    trg, calls, rcs, at, now = rig
    now["t"] = dt.datetime(2026, 10, 6, 7, 50, tzinfo=JST)
    _book(last="2026-10-05")
    MO.append("paper", {"kind": "sell", "ticker": "7203"})
    rcs.extend([1, 1, 1])
    assert at() == ["paper"] and calls[-1] == ("paper", "retry")
    assert at(1) == [] and at(179) == []
    assert at(1) == ["paper"]                                          # 开盘前照旧 3 分钟一次（不加倍；从看到失败算起）
    assert at(1) == [] and at(180) == ["paper"] and len(calls) == 3
    assert at(180) == [] and trg.paused["paper"][1].startswith("退出码 1")   # 没有这次的运行状态 → 退出码
    assert at(t=dt.datetime(2026, 10, 6, 9, 30, tzinfo=JST)) == [] and len(calls) == 3   # 盘中也不叫（同一天）


def test_running_process_is_not_counted_and_old_run_status_is_not_used(rig):
    trg, calls, rcs, at, now = rig
    _book(last="2026-10-05")
    MO.append("paper", {"kind": "sell", "ticker": "7203"})
    _fail_status("昨天的错误", now["t"] - dt.timedelta(days=1))
    p = _Proc(None)
    trg.run = lambda tag, mode="retry": calls.append((tag, mode)) or p
    assert at() == ["paper"]
    assert at(600) == [] and "paper" not in trg.fails                 # 还在跑：不叫、不算
    p.rc = 2                                                           # 跑了 10 分钟才失败：等待从看到失败算起（不是从叫的时候）
    assert at(1) == [] and trg.fails["paper"][1] == 1 and trg.errs["paper"].startswith("退出码 2")   # 旧的运行状态不当成这次的原因
    assert at(119) == []
    assert at(1) == ["paper"]


def test_a_run_that_ends_between_two_polls_is_counted(rig):
    """每个账本每次只 poll 一次：先看到「还在跑」、紧接着又「结束了（失败）」时，失败照样记下，不会马上再叫。"""
    trg, calls, rcs, at, now = rig
    _book(last="2026-10-05")
    MO.append("paper", {"kind": "sell", "ticker": "7203"})

    class _Flip:                                                       # 第 1 次 poll：还在跑；之后：退出码 3
        n = 0

        def poll(self):
            self.n += 1
            return None if self.n == 1 else 3
    trg.run = lambda tag, mode="retry": calls.append((tag, mode)) or _Flip()
    assert at() == ["paper"]
    assert at(200) == [] and len(calls) == 1                          # 第 1 次 poll：还在跑
    assert at(1) == [] and trg.fails["paper"][1] == 1 and len(calls) == 1   # 第 2 次 poll：失败记下，从这时起等 120 秒
    assert at(119) == [] and at(1) == ["paper"]


def _read_into_book(ids):
    """像执行器读过这些指令（账本的 manual.items 里有、已经处理完）。"""
    _book(last="2026-10-05", manual={"items": {i: {"id": i, "kind": "sell", "ticker": "7203.T", "status": "done"} for i in ids}})


def test_status_is_quiet_when_nothing_is_due_any_more(rig):
    """失败过，但指令已经被读掉、处理完（面板不会再叫）→ 不显示「最早几点再叫」。"""
    trg, calls, rcs, at, now = rig
    _book(last="2026-10-05")
    r = MO.append("paper", {"kind": "sell", "ticker": "7203"})
    rcs.extend([3])
    assert at() == ["paper"] and at(1) == []
    cls, txt = trg.status("paper")
    assert cls == "muted" and "连续失败 1 次：最早 09:32 再自动叫" in txt
    _read_into_book([r["id"]])
    assert trg.status("paper") is None and trg.status("paper", book=panel._load("paper")[0]) is None
    assert at(3000) == [] and len(calls) == 1


def test_new_request_during_the_third_failing_run_avoids_the_pause(rig):
    """连续失败 2 次后你写了新的指令，第 3 次（正在跑）又失败：你刚写的指令算「修好后写新的指令」→ 不暂停、重新计数。"""
    trg, calls, rcs, at, now = rig
    _book(last="2026-10-05")
    MO.append("paper", {"kind": "sell", "ticker": "7203"})
    rcs.extend([3, 3])
    assert at() == ["paper"] and at(1) == [] and at(120) == ["paper"] and at(1) == []
    p = _Proc(None)
    trg.run = lambda tag, mode="retry": calls.append((tag, mode)) or p
    assert at(240) == ["paper"] and len(calls) == 3                    # 第 3 次（正在跑）
    MO.append("paper", {"kind": "core", "pct": 50})                   # 跑着的时候写了新的指令（面板这时不会叫）
    assert at(1) == []
    p.rc = 3
    assert at(1) == [] and "paper" not in trg.paused and "paper" not in trg.fails
    assert at(60) == ["paper"]                                         # 重新计数：1 分钟一次


def test_pause_is_not_lifted_when_the_scheduled_run_reads_the_requests(rig):
    """暂停中，指令被别的运行读掉（没读的变少）不算新的指令；出现新的 id 才恢复。"""
    trg, calls, rcs, at, now = rig
    _book(last="2026-10-05")
    r1 = MO.append("paper", {"kind": "sell", "ticker": "7203"})
    MO.append("paper", {"kind": "sell", "ticker": "6758"})
    rcs.extend([3, 3, 3])
    assert at() == ["paper"] and at(1) == [] and at(120) == ["paper"] and at(1) == [] and at(240) == ["paper"]
    assert at(1) == [] and trg.paused["paper"][0] == "2026-10-06" and len(calls) == 3
    _read_into_book([r1["id"]])                                        # 有一条被读掉了（没读的变少）
    assert at(60) == [] and "paper" in trg.paused and len(calls) == 3
    MO.append("paper", {"kind": "core", "pct": 50})                   # 新的指令 → 恢复
    assert at(1) == ["paper"] and "paper" not in trg.paused and len(calls) == 4


# ────────── ② 通知去重 ──────────
def test_first_dedupes_per_book_day_and_text():
    d1 = dt.datetime(2026, 10, 9, 9, 30, tzinfo=JST)
    a = "另一个执行器还在运行（pid 12 从 2026-10-09 09:20:01 JST），等了 0 分钟仍没结束 → 这次不运行"
    b = "另一个执行器还在运行（pid 99 从 2026-10-09 09:31:40 JST），等了 0 分钟仍没结束 → 这次不运行"
    assert NS.first("paper", a, d1) and not NS.first("paper", a, d1)
    assert not NS.first("paper", b, d1)                               # 只差进程号 / 时刻：同一个原因
    assert NS.first("paper", "执行器停下：别的原因", d1)                 # 换文字
    assert NS.first("tachibana", a, d1)                               # 换账本
    assert NS.first("paper", a, d1 + dt.timedelta(days=1))            # 换天
    raw = json.loads(NS.path("paper").read_text(encoding="utf-8"))
    assert set(raw) == {"2026-10-09", "2026-10-10"} and all(len(k) == 12 for v in raw.values() for k in v)
    assert "执行器" not in NS.path("paper").read_text(encoding="utf-8")    # 只记摘要，不记原文
    NS.first("paper", "x", d1 + dt.timedelta(days=9))
    assert set(json.loads(NS.path("paper").read_text(encoding="utf-8"))) == {"2026-10-18"}   # 只留最近 7 天
    NS.path("paper").write_text("{坏", encoding="utf-8")
    assert NS.first("paper", "x", d1)                                 # 读坏 → 当作没发过（宁可多发一次）
    assert NS.first("../x", "y", d1)                                  # 账本名不对：不写文件，照常发


def test_executor_stop_notifies_once_per_day_and_text(monkeypatch):
    import run
    day = {"t": dt.datetime(2026, 10, 9, 9, 30, tzinfo=JST)}
    monkeypatch.setattr(NS, "now_jst", lambda: day["t"])
    err = "有状态不明的单（发送中断）：U-B BUY 7203.T ×100"
    sent = _fake_run(monkeypatch, _book_dict([_o("U-B", "SENDING")]), raise_on=err)
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify"]) == 3
    assert [x[0] for x in sent] == ["mac", "send"] and sent[1][3] == "warn"
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify"]) == 3
    assert len(sent) == 2                                              # 同一天同样的原因：不再发
    assert RS.read("paper")["ok"] is False                             # 运行状态照写（面板看得到）
    sent2 = _fake_run(monkeypatch, _book_dict([_o("U-B", "SENDING")]), raise_on="另一个原因")
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify"]) == 3 and len(sent2) == 2   # 换文字：发
    sent3 = _fake_run(monkeypatch, _book_dict([_o("U-B", "SENDING")]), raise_on=err)
    day["t"] += dt.timedelta(days=1)
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify"]) == 3 and len(sent3) == 2   # 换天：发
    sent4 = _fake_run(monkeypatch, _book_dict([_o("U-B", "SENDING")]), raise_on="没有 --notify")
    assert run.main(["live-u", "--broker", "paper", "--force"]) == 3 and sent4 == []
    assert NS.first("paper", "执行器停下（状态没有改动）：没有 --notify")      # 没发通知的不记


def test_lock_failure_notifies_once(monkeypatch, capsys):
    import qbreak.live_unified as LU
    import run
    _unified_home()
    sent = []
    monkeypatch.setattr(LU, "mac_notify", lambda t, s: sent.append(("mac", t, s)) or True)
    monkeypatch.setattr("qbreak.notify.send", lambda t, b, level="info": sent.append(("send", t, b, level)))
    lock = RunLock(paths.state_dir() / "live_unified_paper.lock").acquire()
    try:
        for _ in range(3):
            assert run.main(["live-u", "--broker", "paper", "--lock-wait", "0", "--notify"]) == 3
    finally:
        lock.release()
    out = capsys.readouterr().out
    assert [x[0] for x in sent] == ["mac", "send"] and "执行器没运行" in sent[0][1] and sent[1][3] == "warn"
    assert out.count("今天已经通知过") == 2
