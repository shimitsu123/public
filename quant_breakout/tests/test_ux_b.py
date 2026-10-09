"""立花实盘缺口 B 组的 UX 部分（2026-10-09「做〔77〕B」；只改工程，不改交易规则）：
B10 数据依赖的提醒（判断层的输入几天没更新 / 行情有问题 + 修法 / 离场判断被跳过）、
B12 上线后的默认账本 / 真钱标识 / ARM 判定一致 / 登录时打开立花的页面并提醒、
LU-12 上线初期和云端比较不报不一致、LU-13 gate「准备」加 dry-run / 时区 / doctor、TA-15 ARM 的说明文字。
全部用临时数据目录与假的命令（不联网、不调真的 launchctl / security / osascript）。"""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from qbreak import paths
from qbreak.calendar_jp import JST
from qbreak.live_unified import (EARLY_TEXT, YF_FIX, compare_bad, compare_with_sim, daily_text, data_problem,
                                 lag_exit_lines, record_compare, stale_inputs, trading_days_behind)
from qbreak.unified import UPos, UState

ROOT = Path(__file__).resolve().parents[1]
MON_0800 = dt.datetime(2026, 9, 28, 8, 0, tzinfo=JST)                         # 周一（交易日）08:00


def _plist(name: str) -> None:
    ag = paths.launch_agents()
    ag.mkdir(parents=True, exist_ok=True)
    (ag / f"{name}.plist").write_text("x", encoding="utf-8")


def _book(tag: str, data: dict | None = None) -> Path:
    p = paths.state_dir() / f"live_unified_{tag}.json"
    p.write_text(json.dumps(data or {}), encoding="utf-8")
    return p


# ────────── UX-12 / TA-15：ARM 判定和适配器一致（内容是 ARMED 才算）──────────
def test_arm_state_follows_the_adapter_rule(monkeypatch):
    monkeypatch.delenv("QBREAK_ARM", raising=False)
    assert paths.arm_state() == "off" and not paths.armed()
    (paths.home() / "ARM").write_text("yes\n", encoding="utf-8")
    assert paths.arm_state() == "bad" and not paths.armed()                      # 文件在、内容不对 → 单会被挡
    (paths.home() / "ARM").write_text(" armed \n", encoding="utf-8")
    assert paths.arm_state() == "file" and paths.armed()
    (paths.home() / "ARM").unlink()
    monkeypatch.setenv("QBREAK_ARM", "ARMED")
    assert paths.arm_state() == "env" and paths.armed()


def test_adapter_block_text_no_longer_says_cleared_after_close(monkeypatch):
    from qbreak.brokers.tachibana import FakeTransport, TachibanaBroker
    monkeypatch.delenv("QBREAK_ARM", raising=False)
    b = TachibanaBroker(transport=FakeTransport({}))
    why = b._preflight("7203.T", 100, 1000.0)
    assert why.startswith("未 ARM：") and "收盘后清空" not in why
    assert "过了上线门槛、你在对话里明确说之后才建；要停用 = 删掉它或建 HALT" in why
    (paths.home() / "ARM").write_text("ARMD", encoding="utf-8")                  # 打错了
    assert "内容不是 ARMED" in b._preflight("7203.T", 100, 1000.0)
    demo = TachibanaBroker(transport=FakeTransport({}), demo=True)
    assert "デモ账本的执行器也看同一个 ARM" in demo._preflight("7203.T", 100, 1000.0)
    (paths.home() / "ARM").write_text("ARMED", encoding="utf-8")
    assert b._preflight("7203.T", 100, 1000.0) is None
    assert TachibanaBroker(transport=FakeTransport({}), require_arm=False)._armed()


def test_run_armed_and_manual_hint_use_the_same_rule(monkeypatch, capsys):
    import run
    monkeypatch.delenv("QBREAK_ARM", raising=False)
    (paths.home() / "ARM").write_text("nope", encoding="utf-8")
    assert run._armed() is False
    (paths.home() / "ARM").write_text("ARMED", encoding="utf-8")
    assert run._armed() is True


# ────────── B12：默认账本 ──────────
def test_default_book_follows_the_installed_mode():
    assert paths.default_book() == "paper"                                         # 什么都没装
    _book("tachibana")
    assert paths.default_book() == "tachibana"                                     # 立花账本在、模拟操盘的定时任务不在
    _plist(paths.PAPER_AGENT)
    assert paths.default_book() == "paper"                                         # 上线前（例如登记过入金）：还是模拟账户
    _plist(paths.LIVE_AGENT)
    assert paths.default_book() == "tachibana" and paths.live_installed()          # 装了立花本番


def test_panel_default_book_and_real_money_banner(monkeypatch):
    from qbreak import panel as P
    monkeypatch.delenv("QBREAK_ARM", raising=False)
    now = MON_0800.replace(hour=20)
    assert P._book_of("") == "paper" and P._book_of("book=bogus") == "paper" and P.books() == ["paper"]
    _plist(paths.LIVE_AGENT)                                                       # 装了立花本番（账本还没有也一样）
    assert P._book_of("") == "tachibana" and P._book_of("book=paper") == "paper"
    assert P.books() == ["paper", "tachibana"]
    html = P.render("tachibana", "t" * 40, now)
    assert "class='top real'" in html and "真钱（立花本番）" in html and '"real": true' in html
    assert "立花还没解锁（没有 ARM）" in html
    (paths.home() / "ARM").write_text("armed?", encoding="utf-8")
    html = P.render("tachibana", "t" * 40, now)
    assert "ARM 文件在，但内容不是 ARMED" in html and "立花还没解锁" not in html
    (paths.home() / "ARM").write_text("ARMED", encoding="utf-8")
    html = P.render("tachibana", "t" * 40, now)
    assert "ARM 文件在" not in html and "立花还没解锁" not in html
    pp = P.render("paper", "t" * 40, now)                                          # 模拟操盘的定时任务已卸载 → 标「已停」
    assert "真钱（立花本番）</span>" not in pp and "模拟账户已停" in pp and '"real": false' in pp
    _plist(paths.PAPER_AGENT)
    assert "模拟账户已停" not in P.render("paper", "t" * 40, now)


# ────────── B12：登录时（mac_login）──────────
def _login_home(tmp_path, live=True, book=None, pages=("page_paper.html", "page_tachibana.html", "dashboard.html")):
    from qbreak import mac_login as ML
    home, agents = tmp_path / "h", tmp_path / "ag"
    (home / "out").mkdir(parents=True)
    (home / "state").mkdir()
    agents.mkdir()
    for name in ((ML.LIVE, ML.NEWS) if live else (ML.PAPER, ML.NEWS)):
        (agents / f"{name}.plist").write_text("x", encoding="utf-8")
    for p in pages:
        (home / "out" / p).write_text("x", encoding="utf-8")
    if book is not None:
        (home / "state" / "live_unified_tachibana.json").write_text(json.dumps(book), encoding="utf-8")
    return home, agents


def test_login_opens_the_tachibana_page_and_alerts_when_the_morning_is_not_done(tmp_path):
    from qbreak import mac_login as ML
    home, agents = _login_home(tmp_path)
    p = ML.plan(MON_0800, home, agents, {ML.NEWS}, running=False)
    acts = dict(p["actions"])
    assert "RUN_PAPER" not in acts                                                 # 真钱永远不在登录时补跑
    assert [Path(a).name for k, a in p["actions"] if k == "OPEN"] == ["page_tachibana.html", "dashboard.html"]
    assert "08:35 的重试会再跑一次" in acts["MAC_ALERT"]
    late = ML.plan(MON_0800.replace(hour=9, minute=10), home, agents, {ML.NEWS}, running=False)
    assert "08:35 的重试也没跑成" in dict(late["actions"])["MAC_ALERT"]
    for now, running in ((MON_0800, True), (MON_0800.replace(hour=7, minute=30), False), (MON_0800.replace(hour=16), False),
                         (dt.datetime(2026, 9, 26, 9, 0, tzinfo=JST), False)):        # 正在跑 / 07:40 前 / 收盘后 / 周六
        assert "MAC_ALERT" not in dict(ML.plan(now, home, agents, {ML.NEWS}, running=running)["actions"])
    (home / "HALT").write_text("停", encoding="utf-8")
    assert "MAC_ALERT" not in dict(ML.plan(MON_0800, home, agents, {ML.NEWS}, running=False)["actions"])


def test_login_alert_uses_the_same_done_rule_as_the_executor(tmp_path):
    from qbreak import mac_login as ML
    from qbreak.live_unified import morning_done
    exp = "2026-09-25"                                                             # 周一的应有决策日 = 上周五
    for orders, done in (([{"decided_on": exp, "status": "SENT"}], True), ([{"decided_on": exp, "status": "BLOCKED"}], False),
                         ([{"decided_on": "2026-09-24", "status": "PLANNED"}], True), ([], True)):
        book = {"state": {"last_date": exp}, "orders": orders}
        assert ML._morning_done(book, exp) is done is morning_done(book, exp)
        home, agents = _login_home(tmp_path / f"{len(orders)}{done}{orders[0]['status'] if orders else ''}", book=book)
        assert ("MAC_ALERT" in dict(ML.plan(MON_0800, home, agents, {ML.NEWS}, running=False)["actions"])) is (not done)
    paper_home, paper_agents = _login_home(tmp_path / "paper", live=False)          # 模拟操盘：照旧打开模拟账户的页面、不提醒
    p = ML.plan(MON_0800, paper_home, paper_agents, {ML.NEWS}, running=False)
    assert "MAC_ALERT" not in dict(p["actions"]) and "RUN_PAPER" in dict(p["actions"])


def test_liveu_login_shell_shows_the_live_alert(tmp_path):
    from test_mac_login import _stub_env
    home, agents = tmp_path / "home", tmp_path / "agents"
    (home / "out").mkdir(parents=True)
    agents.mkdir()
    for name in ("com.qbreak.liveu.morning", "com.qbreak.news"):
        (agents / f"{name}.plist").write_text("x", encoding="utf-8")
    for p in ("page_paper.html", "page_tachibana.html", "dashboard.html"):
        (home / "out" / p).write_text("x", encoding="utf-8")
    env = _stub_env(tmp_path, "PID\tStatus\tLabel\n-\t0\tcom.qbreak.news\n")
    r = subprocess.run(["bash", "scripts/liveu.sh", "login"], cwd=ROOT, env=env, capture_output=True, timeout=120)
    out, err = r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0 and "unbound variable" not in err, err
    assert "★ 今天立花早上的运行还没完成" in out and "登录时不补跑真钱的单" in out
    calls = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert "page_tachibana.html" in calls and "page_paper.html" not in calls
    assert "osascript" in calls and "早上的运行还没完成" in calls                   # 假 osascript（测试不弹真的 Mac 通知）


# ────────── LU-12：上线初期和云端比较 ──────────
def _st(last, first=None, pos=(), core=None, entry=None):
    s = UState(cash_jpy=1.0, last_date=last, core_units=dict(core or {}),
               history=[[first or last, 1.0, 1.0, 0, 150]] + ([[last, 1.0, 1.0, 0, 150]] if first and first != last else []))
    for t in pos:
        s.pos[t] = UPos(t, "JP", 100, 3000.0, (entry or {}).get(t, "2026-10-01"), 2800.0, 3000.0, 3000.0)
    return s


def test_early_live_compare_is_expected_until_the_first_match():
    sim = _st("2026-11-02", pos=["7203.T"], core={"1545.T": 4000}, entry={"7203.T": "2026-10-20"})
    live = _st("2026-11-02")                                                        # 第一个决策日：实盘空仓
    book = {}
    r = compare_with_sim(live, sim, live=True, book=book)
    assert r["comparable"] and r["same"] is False and r["early"] is True and not compare_bad(r)
    assert r["text"].startswith(EARLY_TEXT) and "7203.T" in r["text"] and "1545.T 实盘第一笔明天开盘才成交" in r["text"]
    record_compare(book, r)
    assert book["compare_history"][-1]["early"] is True
    _, short, body = daily_text({"decided_on": "2026-11-02", "orders": []}, live, r, False, 300_000)
    assert "上线初期：持仓与云端不同（预期）" in short and "★ 与云端不一致" not in short and EARLY_TEXT in body
    # 第二天：核心 ETF 已成交，模拟盘还拿着上线前买的个股 → 仍是预期
    sim2, live2 = (_st("2026-11-04", pos=["7203.T"], core={"1545.T": 4000}, entry={"7203.T": "2026-10-20"}),
                   _st("2026-11-04", first="2026-11-02", core={"1545.T": 1200}))
    r2 = compare_with_sim(live2, sim2, live=True, book=book)
    assert r2.get("early") and "1545" not in r2["text"]
    # 核心 ETF 第二天还没有 → 照常算不一致（第一笔没成交？）
    assert not compare_with_sim(_st("2026-11-04", first="2026-11-02"), sim2, live=True, book=book).get("early")
    # 模拟盘在上线之后买的票、实盘没有 → 不是上线初期（实盘照同一决策本应也买）
    sim3 = _st("2026-11-04", pos=["7203.T", "6758.T"], core={"1545.T": 4000},
               entry={"7203.T": "2026-10-20", "6758.T": "2026-11-04"})
    r3 = compare_with_sim(live2, sim3, live=True, book=book)
    assert not r3.get("early") and compare_bad(r3) and r3["text"].startswith("★ 与云端模拟盘拿的票不同")
    # 实盘多出来的票 → 真的不同
    assert not compare_with_sim(_st("2026-11-04", first="2026-11-02", pos=["8035.T"], core={"1545.T": 1}), sim2,
                                live=True, book=book).get("early")
    # 第一次拿的票相同之后照常
    same = compare_with_sim(_st("2026-11-05", first="2026-11-02", pos=["7203.T"], core={"1545.T": 1}),
                            _st("2026-11-05", pos=["7203.T"], core={"1545.T": 9}), live=True, book=book)
    assert same["same"] is True
    record_compare(book, same)
    later = compare_with_sim(_st("2026-11-06", first="2026-11-02", core={"1545.T": 1}),
                             _st("2026-11-06", pos=["7203.T"], core={"1545.T": 9}, entry={"7203.T": "2026-10-20"}),
                             live=True, book=book)
    assert not later.get("early") and compare_bad(later)


def test_early_needs_a_live_book():
    sim, live = _st("2026-11-02", core={"1545.T": 1}), _st("2026-11-02")
    assert not compare_with_sim(live, sim, live=True).get("early")                 # 没给账本：照旧
    assert not compare_with_sim(live, sim, live=False, book={}).get("early")       # 模拟账户：照旧逐项比
    assert compare_bad({"comparable": True, "same": False}) and not compare_bad({"comparable": False})
    assert not compare_bad(None) and not compare_bad({"comparable": True, "same": True})


# ────────── B10：数据依赖 ──────────
def test_trading_days_behind_counts_trading_days():
    assert trading_days_behind("2026-10-08", "2026-10-08") == 0
    assert trading_days_behind("2026-10-09", "2026-10-08") == 0
    assert trading_days_behind("2026-10-09", "2026-10-13") == 1                    # 金 → 火（10/12 体育の日）
    assert trading_days_behind("2026-10-07", "2026-10-09") == 2
    assert trading_days_behind(None, "2026-10-09") is None and trading_days_behind("x", "2026-10-09") is None


def test_stale_inputs_when_the_cloud_files_are_old():
    sm = {"decided_on": "2026-10-09",
          "fwd_judgment": {"enabled": True, "applied": False, "as_of": "2026-10-07", "bar_date": "2026-10-09"},
          "combo_c": {"enabled": True, "applied": False, "bar_date": "2026-10-09"},                # 没有文件
          "tbf": {"enabled": True, "applied": True, "as_of": "2026-10-09"}}
    si = stale_inputs(sm, sim_last="2026-10-08")
    assert si["days"] == 2 and si["short"] == "判断层的输入 2 天没更新"
    assert "前向记录判断层（文件是 2026-10-07 的）" in si["text"] and "关联搭配 C（没有文件）" in si["text"]
    assert "云端模拟盘停在 2026-10-08" in si["text"] and "照旧按原规则下单" in si["text"]
    ok = {"decided_on": "2026-10-09", "fwd_judgment": {"enabled": True, "applied": True, "as_of": "2026-10-09"},
          "tbf": {"enabled": True, "applied": False, "as_of": "2026-10-09", "bar_date": "2026-10-09"},   # 当天的文件标着关闭：云端自己关的
          "combo_c": {"enabled": False}}
    assert stale_inputs(ok, sim_last="2026-10-09") is None and stale_inputs(ok) is None
    only_missing = stale_inputs({"decided_on": "2026-10-09", "combo_c": {"enabled": True, "applied": False}})
    assert only_missing["days"] is None and only_missing["short"] == "判断层的输入没更新"


def test_daily_text_raises_data_problems_with_the_fix():
    st = _st("2026-10-09", pos=["7203.T"])
    sm = {"decided_on": "2026-10-09", "orders": [],
          "stale_inputs": stale_inputs({"decided_on": "2026-10-09",
                                        "fwd_judgment": {"enabled": True, "applied": False, "as_of": "2026-10-08",
                                                         "bar_date": "2026-10-09"}}),
          "data_problem": data_problem(["连不上 Yahoo（query1.finance.yahoo.com）：这次用的是本机的行情缓存"]),
          "lag_exits": {"7203.T": "2026-10-08"}}
    _, short, body = daily_text(sm, st, None, False, 1_000_000)
    assert "｜★ 判断层的输入 1 天没更新" in short and "｜★ 行情有问题（看修法）" in short and "7203.T 的离场判断今天跳过" in short
    assert "- ★ 行情：连不上 Yahoo" in body and "升级 yfinance" in body and "pip install -U yfinance" in body
    assert "- ★ 7203.T 今天的离场判断被跳过（行情只到 2026-10-08）" in body
    assert data_problem([]) is None and data_problem(None) is None and lag_exit_lines({}) == []
    assert "mac_setup.sh --upgrade-yfinance" in YF_FIX


def test_panel_and_page_show_the_data_reminders():
    from qbreak import desktop_page as DP
    from qbreak import panel as P
    _book("paper", {"state": {"last_date": "2026-10-09", "cash_jpy": 1.0, "history": [["2026-10-09", 1.0]]}})
    sm = {"decided_on": "2026-10-09",
          "stale_inputs": {"days": 1, "short": "判断层的输入 1 天没更新", "text": "判断层的输入 1 天没更新：TBF（文件是 2026-10-08 的）"},
          "data_problem": data_problem(["日本行情只到 2026-10-08（应有 2026-10-09）"]),
          "lag_exits": {"7203.T": "2026-10-08"}}
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps(sm), encoding="utf-8")
    html = P.render("paper", "t" * 40, MON_0800.replace(hour=20))
    assert "★ 判断层的输入 1 天没更新：TBF" in html and "★ 行情：日本行情只到 2026-10-08" in html
    assert "升级 yfinance" in html and "7203.T 今天的离场判断被跳过" in html and "card warn" in html
    page = DP.render("paper", 1_000_000)
    assert "判断层的输入 1 天没更新" in page and "修法：" in page and "7203.T 今天的离场判断被跳过" in page
    sm["decided_on"] = "2026-10-08"                                                # 旧的汇总：不显示
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps(sm), encoding="utf-8")
    assert "判断层的输入 1 天没更新" not in P.render("paper", "t" * 40, MON_0800.replace(hour=20))


def test_desktop_page_titles_and_real_badge():
    from qbreak import desktop_page as DP
    assert "真钱（立花本番）" in DP.render("tachibana", 300_000) and "class='real'" in DP.render("tachibana", 300_000)
    demo = DP.render("tachibana_demo", 300_000)
    assert "デモ（不是真钱）" in demo and "真钱（立花本番）" not in demo
    assert "dry-run（只算不发单）" in DP.render("tachibana_dryrun", 300_000)
    assert "真钱（立花本番）" not in DP.render("paper", 1_000_000)
    _book("tachibana", {"state": {"last_date": "2026-11-02", "cash_jpy": 1.0, "history": [["2026-11-02", 1.0]]}})
    (paths.out_dir() / "live_unified_tachibana.json").write_text(json.dumps(
        {"decided_on": "2026-11-02", "compare": {"comparable": True, "same": False, "early": True, "mode": "holdings"}}),
        encoding="utf-8")
    page = DP.render("tachibana", 300_000)
    assert "上线初期：持仓不同是预期的" in page and "★ 与云端模拟盘不一致" not in page


def test_executor_stops_with_the_yfinance_fix_when_no_data_at_all(monkeypatch, capsys):
    import shutil

    import run
    from qbreak import run_status as RS
    from qbreak.data import DataError
    shutil.copy(ROOT / "var" / "sim.json", paths.home() / "sim.json")
    monkeypatch.setattr(run, "_netcheck", lambda: ["query1.finance.yahoo.com"])

    def boom(*a, **k):
        raise DataError("没有取到任何行情数据")
    monkeypatch.setattr(run, "_unified_engine", boom)
    assert run.main(["live-u", "--broker", "paper", "--force"]) == 3
    out = capsys.readouterr().out
    assert "★ 取不到行情，这次没运行" in out and "pip install -U yfinance" in out
    rec = RS.read("paper")
    assert rec["ok"] is False and "升级 yfinance" in rec["error"]
    assert "取不到行情" in (paths.out_dir() / "page_paper.html").read_text(encoding="utf-8")


# ────────── LU-13：gate「准备」──────────
def _gate_run(tz="+0900"):
    def run_(args, **kw):
        if args[0] == "date":
            if tz is None:
                raise FileNotFoundError("date")
            return subprocess.CompletedProcess(args, 0, tz + "\n", "")
        raise FileNotFoundError(args[0])                                          # 其他命令：不是 macOS
    return run_


def test_gate_dryrun_timezone_doctor_items(tmp_path):
    from qbreak import live_gate as G
    from qbreak import run_status as RS
    today = dt.date(2026, 10, 9)

    def items(**kw):
        return {it["name"]: it for it in G.check(agents=tmp_path / "ag", run=_gate_run(**kw), today=today)}
    dry, tz, doc = ("⑤ 本番 dry-run 跑通过（登录 / 对账 / 决策，只算不发单）", "⑦ Mac 的时区（定时任务按 Mac 的本地时间触发）",
                    "⑥ doctor（Python / 依赖 / 外网）")
    it = items()
    assert it[dry]["ok"] is False and G.DRYRUN_CMD in it[dry]["text"] and it[dry]["group"] == "准备"
    assert it[tz]["ok"] is True and it[doc]["ok"] is None and G.DOCTOR_CMD in it[doc]["text"]
    assert items(tz="-0700")[tz]["ok"] is False and "东京" in items(tz="-0700")[tz]["text"]
    assert items(tz=None)[tz]["ok"] is None and items(tz="")[tz]["ok"] is None
    RS.write("tachibana_dryrun", {"at": "2026-10-08T07:50:00+09:00", "ok": False, "error": "立花 API 出错"})
    assert items()[dry]["ok"] is False and "立花 API 出错" in items()[dry]["text"]
    _book("tachibana_dryrun", {"state": {"history": [["2026-10-07", 1.0]]}})
    assert items()[dry]["ok"] is True and "★ 上次" in items()[dry]["text"]      # 以前跑通过一次就算；这次停下的原因照样显示
    RS.write("tachibana_dryrun", {"at": "2026-10-08T07:50:00+09:00", "ok": True})
    assert items()[dry]["ok"] is True and "1 天前" in items()[dry]["text"]
    (paths.out_dir() / "doctor.json").write_text(json.dumps({"at": "2026-10-09T10:00:00+09:00", "ok": False,
                                                              "problems": ["连不上 pypi.org"]}), encoding="utf-8")
    assert items()[doc]["ok"] is False and "连不上 pypi.org" in items()[doc]["text"]
    (paths.out_dir() / "doctor.json").write_text(json.dumps({"at": "2026-10-09T10:00:00+09:00", "ok": True}), encoding="utf-8")
    assert items()[doc]["ok"] is True
    names = [x["name"] for x in G.check(agents=tmp_path / "ag", run=_gate_run(), today=today)]
    assert names.index(dry) == names.index("⑤ 本番只读检查（登录 / 取价 / 持仓 / 余力 / 立花能不能买）") + 1


def test_gate_timezone_reads_the_system_zone_not_the_pinned_tz(tmp_path, monkeypatch):
    """run.py 把这个进程的 TZ 钉成 Asia/Tokyo：gate 的 date 要不带 TZ 跑，否则 Mac 设成别的时区也永远显示 +0900（UX-R1）。"""
    from qbreak import live_gate as G
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    seen = []

    def run_(args, **kw):
        if args[0] == "date":
            env = kw.get("env")
            seen.append(env)
            z = "+0900" if (os.environ if env is None else env).get("TZ") == "Asia/Tokyo" else "-0700"   # 系统时区 = 洛杉矶
            return subprocess.CompletedProcess(args, 0, z + "\n", "")
        raise FileNotFoundError(args[0])
    it = {x["name"]: x for x in G.check(agents=tmp_path / "ag", run=run_, today=dt.date(2026, 10, 9))}
    tz = it["⑦ Mac 的时区（定时任务按 Mac 的本地时间触发）"]
    assert seen and seen[0] is not None and "TZ" not in seen[0]
    assert tz["ok"] is False and "-0700" in tz["text"]


def test_gate_arm_reference_has_three_states(tmp_path, monkeypatch):
    from qbreak import live_gate as G
    monkeypatch.delenv("QBREAK_ARM", raising=False)

    def arm_text():
        return {x["name"]: x for x in G.check(agents=tmp_path, run=_gate_run())}["ARM（解锁发单）"]["text"]
    assert arm_text().startswith("未解锁")
    (paths.home() / "ARM").write_text("armed-ish", encoding="utf-8")
    assert "内容不是 ARMED" in arm_text()
    (paths.home() / "ARM").write_text("ARMED\n", encoding="utf-8")
    assert arm_text().startswith("已解锁（ARM 文件")


def test_doctor_result_file_only_outside_the_repo(monkeypatch):
    import run
    run._doctor_result(False, ["连不上 pypi.org"])
    d = json.loads((paths.out_dir() / "doctor.json").read_text(encoding="utf-8"))
    assert d["ok"] is False and d["problems"] == ["连不上 pypi.org"] and "at" in d
    monkeypatch.delenv("QBREAK_HOME")                                              # 默认 = 仓库的 var/（公开仓库）：不写
    before = (ROOT / "var" / "out" / "doctor.json").exists()
    run._doctor_result(True, [])
    assert (ROOT / "var" / "out" / "doctor.json").exists() is before


def test_liveu_has_doctor_and_mac_setup_knows_upgrade_yfinance(tmp_path):
    txt = (ROOT / "scripts" / "liveu.sh").read_text(encoding="utf-8")
    assert '"${1:-}" = "doctor"' in txt and "run.py doctor" in txt and "MAC_ALERT)" in txt
    env = {**os.environ, "QBREAK_LAUNCH_AGENTS": str(tmp_path / "ag"), "QBREAK_LIVEU_HOME": str(tmp_path / "h")}
    r = subprocess.run(["bash", "scripts/mac_setup.sh", "--bogus"], cwd=ROOT, env=env, capture_output=True, timeout=60)
    assert r.returncode == 2 and "--upgrade-yfinance" in r.stdout.decode("utf-8")
    ms = (ROOT / "scripts" / "mac_setup.sh").read_text(encoding="utf-8")
    assert "--upgrade-yfinance) UPGRADE_YF=1" in ms and 'pip install -q -U yfinance' in ms


@pytest.mark.parametrize("tag,expect", [("paper", False), ("tachibana", True), ("tachibana_demo", False)])
def test_panel_confirm_note_names_real_money(tag, expect):
    from qbreak import panel as P
    html = P.render(tag, "t" * 40, MON_0800.replace(hour=20))
    assert ('"real": true' in html) is expect
    assert "CFG.real ? '\\n\\n★ 真钱（立花本番）：执行器会在立花真的下单。'" in html


# ────────── run.py 的接线（假的引擎 / 执行器：test_run_status 的那一套）──────────
def test_stale_inputs_and_yahoo_problems_raise_the_notice_to_warn(monkeypatch):
    import run
    from test_run_status import _book_dict, _fake_run
    sent = _fake_run(monkeypatch, _book_dict([]))
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify"]) == 0
    assert [x for x in sent if x[0] == "send"][0][3] == "info"                    # 没有问题：照旧 info
    sm = json.loads((paths.out_dir() / "live_unified_paper.json").read_text(encoding="utf-8"))
    assert sm["stale_inputs"] is None and sm["data_problem"] is None and sm["lag_exits"] == {}
    sent = _fake_run(monkeypatch, _book_dict([]))
    monkeypatch.setattr(run, "_fj_brief", lambda ctx: {"enabled": True, "applied": False, "as_of": "2026-10-06",
                                                        "bar_date": "2026-10-08", "why": "判断层文件是旧的"})
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify"]) == 0
    send = [x for x in sent if x[0] == "send"][0]
    assert send[3] == "warn" and "判断层的输入 2 天没更新" in send[2]
    assert "★ 判断层的输入 2 天没更新" in [x for x in sent if x[0] == "mac"][0][2]
    sent = _fake_run(monkeypatch, _book_dict([]))
    monkeypatch.setattr(run, "_netcheck", lambda: ["query1.finance.yahoo.com"])
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify"]) == 0
    send = [x for x in sent if x[0] == "send"][0]
    assert send[3] == "warn" and "连不上 Yahoo（query1.finance.yahoo.com）" in send[2] and "升级 yfinance" in send[2]


def test_paper_lagging_market_data_names_the_yfinance_fix(monkeypatch):
    """模拟账户：Yahoo 连得上、但 yfinance 逐只失败只好用旧缓存（行情没到应有的交易日）→ 不挡，但通知升 warn、写原因 + 修法（UX-R3）；
    收盘后（post）跑不算落后。"""
    import run
    from qbreak import calendar_jp
    from test_run_status import _book_dict, _fake_run
    sent = _fake_run(monkeypatch, _book_dict([]))
    monkeypatch.setattr("qbreak.trader.expected_last_bar", lambda today, market: dt.date(2026, 10, 9))
    monkeypatch.setattr(calendar_jp, "session_of", lambda ts=None: "pre")
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify"]) == 0
    send = [x for x in sent if x[0] == "send"][0]
    assert send[3] == "warn" and "日本行情只到 2026-10-08（应有 2026-10-09）" in send[2] and "升级 yfinance" in send[2]
    sent = _fake_run(monkeypatch, _book_dict([]))
    monkeypatch.setattr("qbreak.trader.expected_last_bar", lambda today, market: dt.date(2026, 10, 9))
    monkeypatch.setattr(calendar_jp, "session_of", lambda ts=None: "post")
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify"]) == 0
    assert [x for x in sent if x[0] == "send"][0][3] == "info"


def test_cloud_lag_from_the_compare_state(monkeypatch, tmp_path):
    import run
    from test_run_status import _book_dict, _fake_run
    sim = UState(cash_jpy=1e6, last_date="2026-10-07", history=[["2026-10-07", 1e6, 1e6, 0, 150]])
    fp = tmp_path / "unified_state.json"
    fp.write_text(json.dumps(sim.to_dict()), encoding="utf-8")
    sent = _fake_run(monkeypatch, _book_dict([]))
    assert run.main(["live-u", "--broker", "paper", "--force", "--notify", "--compare-sim", str(fp)]) == 0
    send = [x for x in sent if x[0] == "send"][0]
    assert send[3] == "warn" and "云端模拟盘停在 2026-10-07" in send[2] and "判断层的输入 1 天没更新" in send[2]
