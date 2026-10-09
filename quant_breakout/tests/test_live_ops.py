"""实盘的运行保障（2026-10-04，用户「什么都不改，把没有考虑的点自动补齐」；只补工程，不改交易规则）：
① 运行锁：同一份账本同一时间只有一个执行器进程（Mac 醒来时 launchd 会同时补跑错过的几个定时任务）
② 入出金：登记 → 早上的现金差对上 → 收益计算里扣掉（入金不算赚、出金不算亏）；没登记的大额现金变化 → 提醒
③ 立花实盘与云端模拟盘的比较只看「拿的是不是同样的票」（本金、税、成交价都不同，金额一定对不上）
④ 远程停止：云端对话里说「停」→ var/HALT_REMOTE → Mac 建本地 HALT（同一个 id 只生效一次）
⑤ 08:35 / 09:20 的重试只在前一次没跑完时才跑；HALT 演练；上线门槛的只读检查；立花通知（API 新版本）"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from qbreak import paths
from qbreak.calendar_jp import now_jst
from qbreak.live_unified import (ExecutorError, RunLock, apply_remote_halt, compare_with_sim, daily_text, flows_in_change,
                                 invested_jpy, morning_done, open_pending, parse_remote_halt, record_compare,
                                 register_flow, rehearse)
from qbreak.trader import expected_last_bar
from qbreak.unified import UPos, UState

from test_live_unified import _synth

ROOT = Path(__file__).resolve().parents[1]


# ────────── ① 运行锁 ──────────
def test_run_lock_second_process_waits_then_gives_up(tmp_path):
    p = tmp_path / "live_unified_tachibana.lock"
    first = RunLock(p).acquire()
    t = {"now": 0.0}

    def sleep(s):
        t["now"] += s
    with pytest.raises(ExecutorError, match="另一个执行器还在运行（pid "):
        RunLock(p, wait_s=60, poll_s=5, sleep=sleep, mono=lambda: t["now"]).acquire()
    assert t["now"] >= 60                                    # 等满了才放弃（这次不运行，状态不动）
    first.release()
    with RunLock(p, wait_s=0):                               # 前一个结束（崩溃时进程退出，系统也会自动释放）→ 马上拿到
        assert p.read_text(encoding="utf-8").startswith("pid ")


def test_cli_does_not_run_while_another_executor_holds_the_book(capsys):
    import run
    _unified_home()
    lock = RunLock(paths.state_dir() / "live_unified_tachibana.lock").acquire()
    try:
        assert run.main(["live-u", "--broker", "tachibana", "--lock-wait", "0"]) == 3
        assert "另一个执行器还在运行" in capsys.readouterr().out
        assert run.main(["live-u", "--broker", "tachibana", "--status"]) == 0      # 只读的 --status 不用锁
    finally:
        lock.release()


# ────────── ② 入出金 ──────────
def test_register_flow_and_invested_capital(tmp_path):
    book = tmp_path / "b.json"
    r1 = register_flow(book, 300_000, "工资", "2026-10-05")
    register_flow(book, -50_000, day="2026-10-07")
    assert register_flow(tmp_path / "c.json", 1000)["date"] == now_jst().date().isoformat()     # 默认今天
    with pytest.raises(ValueError):
        register_flow(book, 0)
    with pytest.raises(ValueError):
        register_flow(book, 1000, day="2026-13-01")                           # 日期写错不存进账本
    b = json.loads(book.read_text(encoding="utf-8"))
    assert [f["jpy"] for f in b["flows"]] == [300_000, -50_000] and "seen_after" not in r1
    assert any("登记入金 +300,000 円（2026-10-05）工资" in e["msg"] for e in b["events"])
    assert invested_jpy(1_000_000, b) == 1_250_000                            # 全部
    assert invested_jpy(1_000_000, b, "2026-10-04") == 1_000_000              # 还没对上现金差的按登记日期算
    assert invested_jpy(1_000_000, b, "2026-10-05") == 1_300_000
    b["flows"][0]["seen_after"] = "2026-10-05"                                # 10-05 之后的早上现金差对上了
    assert invested_jpy(1_000_000, b, "2026-10-05") == 1_000_000              # 10-05 的权益里还没有这笔入金
    assert invested_jpy(1_000_000, b, "2026-10-06") == 1_300_000
    assert flows_in_change(b, "2026-10-05", "2026-10-06") == 300_000
    assert flows_in_change(b, "2026-10-06", "2026-10-08") == -50_000
    assert flows_in_change(b, "2026-10-08", "2026-10-09") == 0


def test_flow_registered_after_it_arrived_matches_the_recent_cash_drift(tmp_path):
    book = tmp_path / "b.json"
    book.write_text(json.dumps({"cash_drift": [["2026-10-01", -812.0], ["2026-10-05", 299_200.0]]}), encoding="utf-8")
    r = register_flow(book, 300_000)
    assert r["seen_after"] == "2026-10-05"                    # 先到账、后登记：记为在那次现金同步里到账
    r2 = register_flow(book, 300_000)
    assert "seen_after" not in r2                             # 同一次现金差不会被算两次


def _deposit_run(make, start, amount, register):
    """第 120 根 K 线的早上券商那边多了 amount（入金）；register=True 时在那之前登记。"""
    seen = {}

    def dep(k, ux, exch):
        if not seen and k > 120:
            if register:
                ux.book.setdefault("flows", []).append({"date": "x", "jpy": amount, "note": "", "at": "x"})
            exch.cash += amount
            seen["k"] = k
    return rehearse(make, start, kind="tachibana-sim", before_bar=dep), seen


def test_deposit_is_matched_and_excluded_from_the_daily_change():
    make, start = _synth(7)
    base = rehearse(make, start, kind="tachibana-sim")
    r, seen = _deposit_run(make, start, 300_000, register=True)
    ux = r["ux"]
    f = ux.book["flows"][0]
    h0, h = base["ux"].eng.st.history, ux.eng.st.history
    i = next(j for j, x in enumerate(h) if x[0] > f["seen_after"])            # 入金第一次含在权益里的那一天
    assert h[i - 1][0] == f["seen_after"]                                      # 到账时记的是「之前那个决策日」
    assert any("登记过的入出金 +300,000 円已到账" in e["msg"] for e in ux.book["events"])
    assert h[i][1] - h[i - 1][1] - flows_in_change(ux.book, h[i - 1][0], h[i][0]) == pytest.approx(h0[i][1] - h0[i - 1][1], abs=1e-6)
    assert invested_jpy(1_000_000, ux.book, h[i - 1][0]) == 1_000_000 and invested_jpy(1_000_000, ux.book, h[i][0]) == 1_300_000


def test_unregistered_large_cash_change_is_flagged_with_the_command():
    make, start = _synth(7)
    r, _ = _deposit_run(make, start, 500_000, register=False)
    msgs = [e["msg"] for e in r["ux"].book["events"]]
    assert any("现金突然变化 +500,000 円" in m and "bash scripts/liveu.sh flow +500000 --broker tachibana" in m for m in msgs)


def test_daily_text_uses_invested_capital_and_strips_flows_from_the_day():
    st = UState(cash_jpy=5000.0, last_date="2026-10-06",
                history=[["2026-10-05", 1_000_000.0, 0, 0, 150], ["2026-10-06", 1_303_000.0, 0, 0, 150]])
    sm = {"decided_on": "2026-10-06", "fill_day": "2026-10-07", "orders": [], "events": [], "blocked": None}
    _, short, body = daily_text(sm, st, None, False, 1_000_000, invested=1_300_000, flows_day=300_000)
    assert "当日 +3,000 円，累计 +0.23%" in short                  # 入金不算赚
    assert "投入本金 ¥1,300,000（起始 ¥1,000,000，登记的入出金 +300,000 円）；当日损益已扣掉入出金 +300,000 円" in body


# ────────── ③ 立花实盘 vs 云端模拟盘：只比拿的票 ──────────
def test_live_compare_checks_the_same_holdings_not_amounts():
    def st(shares, cash, eq, core=1100):
        s = UState(cash_jpy=cash, last_date="2026-10-06", core_units={"1655.T": core},
                   history=[["2026-10-06", eq, cash, 0, 150]])
        s.pos["7203.T"] = UPos("7203.T", "JP", shares, 3000.0, "2026-10-06", 2800.0, 3000.0, 3000.0)
        return s
    r = compare_with_sim(st(300, 12_345.0, 3_100_000.0, core=3300), st(100, 5_000.0, 1_003_000.0), live=True)
    assert r["comparable"] and r["same"] and r["mode"] == "holdings" and "同样的票" in r["text"]
    assert compare_with_sim(st(300, 1.0, 3.0), st(100, 5.0, 1.0))["same"] is False          # 模拟账户照旧逐项比
    other = st(100, 5_000.0, 1_003_000.0)
    other.pos["6758.T"] = other.pos.pop("7203.T")
    r = compare_with_sim(st(300, 12_345.0, 3_100_000.0), other, live=True)
    assert r["same"] is False and "个股 7203.T vs 模拟盘 6758.T" in r["text"]
    _, short, _ = daily_text({"decided_on": "2026-10-06", "orders": []}, st(300, 1.0, 3.0), r, False, 1_000_000)
    assert "★ 与云端不一致" in short


def test_compare_history_keeps_the_last_result_per_day():
    book = {}
    record_compare(book, {"exec_date": "2026-10-06", "comparable": True, "same": False})
    record_compare(book, {"exec_date": "2026-10-06", "comparable": True, "same": True, "mode": "holdings"})
    record_compare(book, {"exec_date": "2026-10-05", "comparable": False, "same": None})
    record_compare(book, None)
    assert book["compare_history"] == [{"date": "2026-10-05", "comparable": False, "same": None, "mode": "exact"},
                                       {"date": "2026-10-06", "comparable": True, "same": True, "mode": "holdings"}]


# ────────── ④ 远程停止 ──────────
def test_remote_halt_applies_once_per_id(tmp_path):
    assert parse_remote_halt("") is None and parse_remote_halt("  \n") is None
    assert parse_remote_halt("停一下")["id"] == parse_remote_halt("停一下")["id"]          # 没写 id：内容的稳定摘要
    text = "id: 20261006-081500\nreason: 新闻说要暴跌\nat: 2026-10-06 08:15 JST\n"
    msg = apply_remote_halt(text, tmp_path)
    assert "新闻说要暴跌" in msg and "20261006-081500" in msg and (tmp_path / "HALT").exists()
    (tmp_path / "HALT").unlink()                              # 你在 Mac 上明确说「恢复下单，删除 HALT」
    assert apply_remote_halt(text, tmp_path) is None and not (tmp_path / "HALT").exists()   # 同一条远程停止不会再停住
    (tmp_path / "HALT").write_text("我自己建的", encoding="utf-8")
    assert apply_remote_halt(text.replace("081500", "120000"), tmp_path)
    assert (tmp_path / "HALT").read_text(encoding="utf-8") == "我自己建的"                  # 已有的 HALT 不覆盖


def test_cloud_remote_halt_command_writes_a_new_id(tmp_path, monkeypatch, capsys):
    import run
    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    assert run.main(["remote-halt", "--reason", "今天不要下单\n（手机上说的）"]) == 0
    t = (tmp_path / "var" / "HALT_REMOTE").read_text(encoding="utf-8")
    assert t.startswith("id: ") and "reason: 今天不要下单 （手机上说的）" in t and "提交并推送之后" in capsys.readouterr().out
    assert parse_remote_halt(t)["reason"] == "今天不要下单 （手机上说的）"


# ────────── ⑤ 重试 / HALT 演练 ──────────
def _unified_home():
    shutil.copy(ROOT / "var" / "sim.json", paths.home() / "sim.json")          # liveu.sh 的 sync_inputs 做的事


def _done_book(tag="tachibana", status="SENT"):
    exp = expected_last_bar(now_jst().date(), "JP").isoformat()
    b = {"state": {"last_date": exp, "cash_jpy": 1.0},
         "orders": [{"cid": f"U{exp}-BUY-7203.T", "decided_on": exp, "status": status, "ticker": "7203.T"}]}
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps(b), encoding="utf-8")
    return exp, b


def test_morning_done_and_open_pending():
    exp, b = _done_book()
    assert morning_done(b, exp) and not morning_done(b, "1999-01-04")
    b["orders"][0]["status"] = "BLOCKED"                     # 07:40 被挡（行情没更新 / HALT）→ 重试要再跑
    assert not morning_done(b, exp) and not open_pending(b)
    b["orders"][0]["status"] = "DEFERRED"
    assert open_pending(b)


def test_retry_does_nothing_when_the_morning_is_done(capsys):
    import run
    _unified_home()
    _done_book()
    assert run.main(["live-u", "--broker", "tachibana", "--retry"]) == 0
    assert "今天早上的运行已经完成：重试不用做" in capsys.readouterr().out
    assert run.main(["live-u", "--broker", "tachibana", "--phase", "open", "--retry"]) == 0
    assert "开盘后没有要补的买单" in capsys.readouterr().out


def test_remote_halt_reaches_the_retry_and_stops_it(tmp_path, capsys):
    import run
    _unified_home()
    _done_book(status="DEFERRED")
    rh = tmp_path / "HALT_REMOTE"
    rh.write_text("id: 20261006-083000\nreason: 用户说停\n", encoding="utf-8")
    assert run.main(["live-u", "--broker", "tachibana", "--phase", "open", "--retry", "--remote-halt", str(rh)]) == 0
    out = capsys.readouterr().out
    assert "远程停止（云端对话）" in out and "HALT 生效中" in out and paths.halt_file().exists()


def test_halt_drill_only_after_the_morning_and_never_touches_a_real_halt(monkeypatch, capsys):
    import run
    _unified_home()
    seen = {}

    def body(a):                                              # 代替真正的执行器：HALT 存在 → 记下 halt_seen（_gate 做的事）
        seen["halt"] = paths.halt_file().read_text(encoding="utf-8")
        p_ = paths.state_dir() / "live_unified_paper.json"
        b_ = json.loads(p_.read_text(encoding="utf-8"))
        b_["halt_seen"] = [now_jst().date().isoformat()]
        p_.write_text(json.dumps(b_), encoding="utf-8")
        return 0
    monkeypatch.setattr(run, "_live_unified_body", body)
    _done_book("paper", status="BLOCKED")
    assert run.main(["live-u", "--broker", "paper", "--halt-drill"]) == 2                # 早上还没跑完 → 不演练
    assert "现在不能演练" in capsys.readouterr().out and not seen
    _done_book("paper")
    assert run.main(["live-u", "--broker", "paper", "--halt-drill"]) == 0
    assert "HALT 演练通过" in capsys.readouterr().out and "HALT 演练" in seen["halt"] and not paths.halt_file().exists()
    paths.halt_file().write_text("真的停", encoding="utf-8")
    assert run.main(["live-u", "--broker", "paper", "--halt-drill"]) == 0
    assert "HALT 已经存在" in capsys.readouterr().out and paths.halt_file().read_text(encoding="utf-8") == "真的停"


def test_flow_cli_registers_in_the_tachibana_book(capsys):
    import run
    assert run.main(["live-u", "--broker", "tachibana", "--flow", "300000", "--flow-note", "入金"]) == 0
    assert "已登记入金 +300,000 円" in capsys.readouterr().out
    b = json.loads((paths.state_dir() / "live_unified_tachibana.json").read_text(encoding="utf-8"))
    assert b["flows"][0]["jpy"] == 300_000
    assert run.main(["live-u", "--broker", "tachibana", "--flow", "1000", "--flow-date", "2026-13-01"]) == 2
    assert "★ 没登记" in capsys.readouterr().out
    assert len(json.loads((paths.state_dir() / "live_unified_tachibana.json").read_text(encoding="utf-8"))["flows"]) == 1


# ────────── 上线门槛（只读）──────────
def _fake_run(security=0, launchctl="", pmset="Repeating power events:\n  wakepoweron at 7:30AM weekdays only\n"):
    calls = []

    def run_(args, **kw):
        calls.append(list(args))
        rc, out = {"security": (security, "keychain: secret-free attributes"), "launchctl": (0, launchctl),
                   "pmset": (0, pmset)}[args[0]]
        return subprocess.CompletedProcess(args, rc, out, "")
    return run_, calls


def test_compare_days_reads_old_journal_and_new_history():
    from qbreak.live_gate import compare_days, streak
    j = ("# 执行器日志\n\n## 2026-09-29 07:45 JST　qbreak 模拟操盘 2026-09-26\n- 与云端模拟盘一致（个股、核心 ETF、现金、权益）\n"
         "\n## 2026-09-30 07:45 JST　qbreak 模拟操盘 2026-09-29\n- ★ 与云端模拟盘不一致：现金差 +5 円\n"
         "\n## 2026-10-01 07:45 JST　qbreak 模拟操盘 2026-09-30\n- 模拟盘停在 2026-09-29、执行器在 2026-09-30：不是同一天，这次不比\n")
    book = {"compare_history": [{"date": "2026-09-30", "comparable": True, "same": True},
                                {"date": "2026-10-01", "comparable": True, "same": True}]}
    d = compare_days(book, j)
    assert d == {"2026-09-26": True, "2026-09-29": False, "2026-09-30": True, "2026-10-01": True}
    assert streak(d) == (2, "2026-09-29") and streak({}) == (0, None)


def test_live_gate_reports_each_item_without_reading_secrets(tmp_path, monkeypatch):
    from qbreak import live_gate as G
    monkeypatch.setenv("HOME", str(tmp_path))
    agents = tmp_path / "agents"
    agents.mkdir()
    run_, calls = _fake_run(security=44)
    items = {it["name"]: it for it in G.check(agents=agents, run=run_)}
    assert items["① Mac 模拟操盘与云端连续 ≥ 10 个交易日一致"]["ok"] is False
    assert items["② 没有状态不明的单"]["ok"] is True and items["③ HALT 演练过一次"]["ok"] is False
    assert "probe --demo --order-test" in items["④ デモ发单检查（约定字段、余力变化、按注文番号撤单）"]["text"]
    assert items["⑥ 认证 ID 在钥匙串"]["ok"] is False and "-w（回车后输入，不要贴进聊天）" in items["⑥ 认证 ID 在钥匙串"]["text"]
    assert all("-w" not in c for c in calls if c[0] == "security")                     # 只查有没有，绝不取出值
    assert items["⑦ Mac 工作日早上自动唤醒"]["ok"] is True
    text, ok = G.report(list(items.values()))
    assert not ok and "【上线门槛】" in text and "★ 未完成" in text

    # 全部满足的样子
    days = [f"2026-10-{d:02d}" for d in range(1, 13)]
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(
        {"compare_history": [{"date": d, "comparable": True, "same": True} for d in days], "halt_seen": ["2026-10-06"]}),
        encoding="utf-8")
    from qbreak.brokers.tachibana import TachibanaSpec, api_version
    (paths.out_dir() / "tachibana_probe_demo.json").write_text(json.dumps(
        {"at": "2026-10-07 10:00 JST", "ok": True, "api": api_version(TachibanaSpec().base_demo),
         "order_test": {"ok": True, "fields_missing": [], "cash_or_pos_changed": True, "cancel": True,
                        "opening_limit_buy": "SENT", "opening_cancel": True}}), encoding="utf-8")
    (paths.out_dir() / "tachibana_probe_live.json").write_text(json.dumps(
        {"at": "2026-10-08 08:00 JST", "ok": True, "tax": "1", "steps": {"登录": True},
         "api": api_version(TachibanaSpec().base_live)}), encoding="utf-8")
    key = tmp_path / ".qbreak" / "e_api_private_key.pem"
    key.parent.mkdir()
    key.write_text("x", encoding="utf-8")
    key.chmod(0o644)
    for lb in G.LIVE_LABELS + ("com.qbreak.watchdog",):                              # ⑧ 09:30 自检任务（2026-10-09 加）
        (agents / f"{lb}.plist").write_text("x", encoding="utf-8")
    run_, _ = _fake_run(security=0, launchctl="\n".join(f"-\t0\t{lb}" for lb in G.LIVE_LABELS + ("com.qbreak.watchdog",)))
    items = {it["name"]: it for it in G.check(agents=agents, run=run_)}
    assert items["⑥ 私钥文件"]["ok"] is False and "chmod 600" in items["⑥ 私钥文件"]["text"]       # 权限太宽
    key.chmod(0o600)
    items = G.check(agents=agents, run=run_)
    text, ok = G.report(items)
    bad = [it["name"] for it in items if it["group"] != "参考" and it["ok"] is False]
    assert bad == ([] if G.importlib.util.find_spec("cryptography") else ["⑥ cryptography（解密虚拟 URL）"])
    assert ok is (not bad) and "特定口座" in text and "未解锁" in text


def test_live_gate_unknown_orders_hint_uses_liveu(tmp_path, monkeypatch):
    """② 状态不明的单：登记的命令经 liveu.sh、按账本给 --broker（直接 run.py 默认是模拟账户、仓库的 var/）。"""
    from qbreak import live_gate as G
    monkeypatch.setenv("HOME", str(tmp_path))
    (paths.state_dir() / "live_unified_tachibana.json").write_text(json.dumps(
        {"orders": [{"cid": "U1", "side": "BUY", "ticker": "7203.T", "status": "ERROR"}]}), encoding="utf-8")
    run_, _ = _fake_run(security=44)
    it = {x["name"]: x for x in G.check(agents=tmp_path, run=run_)}["② 没有状态不明的单"]
    assert it["ok"] is False and "立花 U1 BUY 7203.T" in it["text"]
    assert "bash scripts/liveu.sh --broker tachibana --resolve <cid> --filled <股数> --px <均价>；没成交填 0" in it["text"]
    assert "--broker paper" not in it["text"] and "run.py live-u" not in it["text"]


def test_wake_schedule_parsing():
    from qbreak.live_gate import _wake
    assert _wake("Repeating power events:\n  wakepoweron at 7:30AM weekdays only\n")[0] is True
    assert _wake("Repeating power events:\n  wake at 8:00AM every day\n")[0] is False
    assert _wake("Scheduled power events:\n [0] wake at 10/05/2026 07:30:00\n")[0] is False      # 只有一次性的，不算
    assert _wake("Repeating power events:\n  wakepoweron at 7:30AM weekends only\n")[0] is None


def test_demo_order_test_records_the_three_gate_points():
    """tachibana-probe --demo --order-test：上线门槛的三点（约定字段、余力 / 持仓变化、按注文番号撤单）记进结果（没有金额）。"""
    import run
    from qbreak.brokers.tachibana import TachibanaBroker
    from qbreak.brokers.tachibana_sim import SimExchange
    from test_live_unified import _scenario
    make, _ = _scenario([1000.0] * 30)
    eng = make()
    exch = SimExchange(eng, cash=1_000_000)
    b = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), dry_run=True, require_arm=True,
                        confirm_timeout_s=0.0)
    exch.set_day(10)
    exch.open(10)
    rec = {}
    assert run._tachibana_order_test(b, exch.spec, rec) is True
    ot = rec["order_test"]
    assert ot["ok"] and ot["fields_missing"] == [] and ot["cash_or_pos_changed"] and ot["cancel"] and ot["buy"] in ("SENT", "FILLED", "PARTIAL")
    assert ot["opening_limit_buy"] == "SENT" and ot["opening_cancel"] is True                # 寄付指値买受理 → 按注文番号撤掉
    assert not any(isinstance(v, float) for v in ot.values())               # 不记金额
