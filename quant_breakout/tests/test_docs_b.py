"""test_docs_b.py — 立花实盘缺口 B 组的文档与几处小改（B14 第 3 点、B15、「文档 / 记录」）：
① 上线门槛 ①：最近一次与云端的比较要在 10 个交易日以内（过期 ★；门槛数字 10 不变；模拟操盘停了就不再拿以前的连续一致算数）；
② doctor 的「launchd」几行只看现行一个账户方案的 LaunchAgents（OPS-16：以前没装旧守护进程就提示装它，会误导）；
③ 文档：代码里提到的章节在 MACOS.md 里有；新命令写进了 HANDOFF「在 Mac 对话里怎么问」与 CLAUDE.md「实盘相关」；
   过时说法（「立花网站 / App 上撤」「盘中的单发出后撤不了」「股票池 + 1655」、没标旧方案的「逆指値是永远在岗的保险」）不再出现；
   文档里写到的 `liveu.sh <子命令>` 在 scripts/liveu.sh 里都有。只读文件、不联网、不调系统命令。
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from qbreak import paths

ROOT = Path(__file__).resolve().parent.parent
CLAUDE = ROOT.parent / "CLAUDE.md"


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _no_cmd(args, **kw):
    raise FileNotFoundError(args[0])                     # 不是 macOS：security / launchctl / pmset / sntp 都没有


# ────────── ① 门槛 ①：最近一次比较要在 10 个交易日以内 ──────────
def test_tdays_since_counts_tse_trading_days():
    from qbreak.live_gate import tdays_since
    assert tdays_since("2026-10-09", dt.date(2026, 10, 9)) == 0
    assert tdays_since("2026-10-09", dt.date(2026, 10, 13)) == 1          # 10-10 / 10-11 周末、10-12 スポーツの日
    assert tdays_since("2026-10-09", dt.date(2026, 10, 26)) == 10
    assert tdays_since("2026-10-09", dt.date(2026, 10, 27)) == 11
    assert tdays_since("2026-10-20", dt.date(2026, 10, 9)) == 0           # 比较日在今天之后（测试数据）→ 0
    assert tdays_since("", dt.date(2026, 10, 9)) is None and tdays_since("x", dt.date(2026, 10, 9)) is None


def _paper(days: list[str], same: bool = True) -> None:
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(
        {"compare_history": [{"date": d, "comparable": True, "same": same} for d in days]}), encoding="utf-8")


def _gate1(tmp_path, today: dt.date) -> dict:
    from qbreak import live_gate as G
    return {it["name"]: it for it in G.check(agents=tmp_path / "agents", run=_no_cmd, today=today)}[
        f"① Mac 模拟操盘与云端连续 ≥ {G.STREAK_NEED} 个交易日一致"]


def test_gate_streak_is_ok_only_while_recent(tmp_path):
    from qbreak.calendar_jp import is_trading_day
    days, d = [], dt.date(2026, 10, 9)
    while len(days) < 12:                                 # 到 2026-10-09 为止连续 12 个交易日一致
        if is_trading_day(d):
            days.insert(0, d.isoformat())
        d -= dt.timedelta(days=1)
    assert days[-1] == "2026-10-09"
    _paper(days)
    it = _gate1(tmp_path, dt.date(2026, 10, 13))
    assert it["ok"] is True and "最近连续一致 12 个决策日" in it["text"] and "最近一次比较 2026-10-09（1 个交易日前）" in it["text"]
    it = _gate1(tmp_path, dt.date(2026, 10, 26))           # 第 10 个交易日：还算
    assert it["ok"] is True and "★" not in it["text"]
    it = _gate1(tmp_path, dt.date(2026, 10, 27))           # 第 11 个交易日：过期（模拟操盘停了 / 上线后模拟账户被卸掉）
    assert it["ok"] is False and it["text"].startswith("★ 最近一次比较是 2026-10-09，已经 11 个交易日没和云端比了")
    from qbreak import live_gate as G
    text, ok = G.report([it])
    assert not ok and "[★ 未完成]" in text and "★ ★" not in text           # report 去掉开头的 ★（不重复）


def test_gate_streak_freezes_when_paper_was_uninstalled_for_live(tmp_path):
    """装了立花本番（install_launchd_live_u.sh tachibana 卸掉了模拟操盘）：① 的新鲜度只量到模拟操盘最后一次运行的那天 ——
    不在卸掉 10 个交易日之后自己变 ★（上线顺序 install → pmset → gate → ARM 不受时间限制），前一晚预检也不当作新出现的 ★ 通知。"""
    from qbreak import live_gate as G
    from qbreak import precheck as PC
    from qbreak.calendar_jp import is_trading_day
    days, d = [], dt.date(2026, 10, 9)
    while len(days) < 12:
        if is_trading_day(d):
            days.insert(0, d.isoformat())
        d -= dt.timedelta(days=1)
    _paper(days)
    ag = tmp_path / "agents"
    ag.mkdir()
    for lb in G.LIVE_LABELS:
        (ag / f"{lb}.plist").write_text("x", encoding="utf-8")
    (paths.out_dir() / "live_unified_paper_run.json").write_text(
        json.dumps({"at": "2026-10-09T07:52:00+09:00", "ok": True}), encoding="utf-8")
    assert paths.live_installed(ag)
    it = _gate1(tmp_path, dt.date(2026, 10, 27))            # 11 个交易日之后
    assert it["ok"] is True and not it["text"].startswith("★") and "模拟操盘的定时任务已卸掉" in it["text"]
    s1 = PC.gate_stars(G.check(agents=ag, run=_no_cmd, today=dt.date(2026, 10, 13)))
    s2 = PC.gate_stars(G.check(agents=ag, run=_no_cmd, today=dt.date(2026, 11, 20)))
    assert not [x for x in s2 if x not in s1] and not any("①" in x for x in s2)
    # 卸掉之前就已经很久没比较了（模拟操盘照跑、云端没比上）→ 照样 ★
    (paths.out_dir() / "live_unified_paper_run.json").write_text(
        json.dumps({"at": "2026-11-20T07:52:00+09:00", "ok": True}), encoding="utf-8")
    it = _gate1(tmp_path, dt.date(2026, 11, 24))
    assert it["ok"] is False and it["text"].startswith("★ 最近一次比较是 2026-10-09，到模拟操盘最后一次运行（2026-11-20）")
    # 模拟操盘还装着（没上线）：照常量到今天
    (ag / "com.qbreak.liveu.paper.plist").write_text("x", encoding="utf-8")
    for lb in G.LIVE_LABELS:
        (ag / f"{lb}.plist").unlink()
    it = _gate1(tmp_path, dt.date(2026, 10, 27))
    assert it["ok"] is False and it["text"].startswith("★ 最近一次比较是 2026-10-09，已经 11 个交易日没和云端比了")


def test_exit_live_doc_matches_the_panel_default_after_uninstall_only(tmp_path):
    """「退出实盘」第 4 步：只卸不装（uninstall）之后立花的账本还在、模拟操盘也没装 → 面板 / 手机仍默认立花的账本（文档照实写）。"""
    ag = tmp_path / "agents"
    ag.mkdir()
    (paths.state_dir() / "live_unified_tachibana.json").write_text("{}", encoding="utf-8")
    assert paths.default_book(ag) == "tachibana"
    (ag / "com.qbreak.liveu.paper.plist").write_text("x", encoding="utf-8")   # install_launchd_live_u.sh paper
    assert paths.default_book(ag) == "paper"
    md = (ROOT / "MACOS.md").read_text(encoding="utf-8")
    assert "仍默认打开立花的账本" in md and "uninstall`。之后面板 / 手机默认回到模拟账户" not in md
    assert "§1.7「与云端不一致时」" not in md and "**与云端「不一致」时**" in md


def test_gate_streak_short_or_broken_is_not_marked_stale(tmp_path):
    _paper(["2026-10-07", "2026-10-08", "2026-10-09"])
    it = _gate1(tmp_path, dt.date(2026, 10, 13))
    assert it["ok"] is False and not it["text"].startswith("★") and "最近连续一致 3 个决策日" in it["text"]
    (paths.state_dir() / "live_unified_paper.json").unlink()
    it = _gate1(tmp_path, dt.date(2026, 10, 13))           # 一次都没比过：照旧（不报「过期」）
    assert it["ok"] is False and "一共比过 0 天" in it["text"] and "最近一次比较" not in it["text"]


# ────────── ② doctor 的定时任务行（OPS-16）──────────
def test_doctor_launchd_lines_show_current_agents_not_the_old_daemon(tmp_path):
    import run
    ag = tmp_path / "LA"
    ag.mkdir()
    lines = run._doctor_launchd(ag)
    assert lines == ["launchd     : 现行的定时任务一个都没装（bash scripts/mac_setup.sh）"]
    assert not any("install_launchd.sh" in ln for ln in lines)                # 不再把人引去装旧的分市场守护进程
    for lb in ("com.qbreak.liveu.morning", "com.qbreak.precheck", "com.qbreak.watchdog"):
        (ag / f"{lb}.plist").write_text("x", encoding="utf-8")
    lines = run._doctor_launchd(ag)
    assert len(lines) == 1 and "com.qbreak.liveu.morning（立花本番）" in lines[0] and "com.qbreak.precheck（立花前一晚预检）" in lines[0]
    (ag / "com.qbreak.daemon.plist").write_text("x", encoding="utf-8")
    lines = run._doctor_launchd(ag)
    assert len(lines) == 2 and lines[1].startswith("  ★ 旧的分市场守护进程 com.qbreak.daemon 还装着")
    assert str(tmp_path) not in "\n".join(lines)                                # 不打印本机路径


# ────────── ③ 文档 ──────────
def test_sections_referenced_by_code_exist_in_macos():
    from qbreak.live_unified import check_host
    m = _read("MACOS.md")
    why = check_host({"host": "aaaaaaaa"}, hid="bbbbbbbb")                     # 两台 Mac：停下的原因指向 MACOS.md「换 Mac」
    assert why and "MACOS.md「换 Mac」" in why and "adopt-host --broker tachibana" in why
    assert re.search(r"^## 1\.14 换 Mac", m, re.M)
    for h in ("### 上线头 5 个交易日的值守清单", "### 退出实盘 / 回到模拟", "### 最后停止手段：在立花网页把 API 关掉"):
        assert h in m, h
    last = m.split("### 最后停止手段", 1)[1].split("\n## ", 1)[0]
    for k in ("ｅ支店・API 利用設定", "「無効化」", "https://kabuka.e-shiten.jp/mfds_smp.php", "パスキー", "https://www.e-shiten.jp/QA/answer14.html",
              "2026-10-09 检索"):
        assert k in last, k
    switch = m.split("## 1.14 换 Mac", 1)[1].split("\n## ", 1)[0]
    for k in ("install_launchd_live_u.sh uninstall", "~/.qbreak/home", "~/.qbreak/e_api_private_key.pem", "chmod 600",
              "换 Mac，账本归这台", "bash scripts/liveu.sh adopt-host --broker tachibana", "reconcile --broker tachibana", "liveu.sh gate"):
        assert k in switch, k
    watch = m.split("### 上线头 5 个交易日的值守清单", 1)[1].split("\n### ", 1)[0]
    for k in ("前一晚 20:00", "07:40", "09:30", "第二天 07:40", "马上停", "撤单"):
        assert k in watch, k
    leave = m.split("### 退出实盘 / 回到模拟", 1)[1].split("\n## ", 1)[0]
    for k in ("HALT", "manual sell", "install_launchd_live_u.sh paper", "rm ~/.qbreak/home/ARM", "live_unified_paper.json", "利用しない"):
        assert k in leave, k


def test_outdated_statements_are_gone_or_marked_old():
    docs = {n: _read(n) for n in ("MACOS.md", "HANDOFF.md", "CHECK_TIMELINE.md", "README.md")}
    if CLAUDE.exists():
        docs["CLAUDE.md"] = CLAUDE.read_text(encoding="utf-8")
    for n, t in docs.items():
        assert "立花网站 / App" not in t and "App 上撤" not in t, n                 # 立花没有原生 App（C-17）
        assert "股票池 + 1655" not in t, n                                         # 核心 ETF 是 1545 / 1482（T2 补出的）
        assert "盘中的单发出后撤不了" not in t, n                                 # 2026-10-09 起可以撤（B1）
    for ln in docs["MACOS.md"].splitlines():                                      # LU-16：旧守护进程的说法都标明是旧方案
        if "永远在岗的保险" in ln or "--protective-stop" in ln:
            assert "旧" in ln, ln
    m = docs["MACOS.md"]
    assert "https://www.e-shiten.jp/QA/answer12.html" in m and "指値・無条件・当日中" in m           # T8：NISA 的下单限制带来源
    assert "每次登录会收到一封「ログインメール」" not in m and "待开户后" in m                     # C-17 ③
    assert "标准 Web 首次登录（电话认证一次）" not in m                                             # C-17 ②
    assert "MTWRF 08:40:00" not in m.split("## 5.", 1)[0]                                            # 旧方案的唤醒时刻只留在 §5（且标明）


def test_new_commands_are_in_the_how_to_ask_table_and_claude_rules():
    h = _read("HANDOFF.md")
    ask = h.split("## 在 Mac 对话里怎么问", 1)[1].split("\n## ", 1)[0]
    for k in ("liveu.sh cancel", "halt-cancel", "liveu.sh unknown --broker tachibana", "liveu.sh reconcile --broker tachibana",
              "liveu.sh adopt --broker tachibana", "restore --broker tachibana --list", "restore --broker tachibana <备份文件名>",
              "liveu.sh precheck", "email-setup", "adopt-host --broker tachibana", "closed add", "MACOS.md §1.14",
              "最后停止手段", "上线头 5 个交易日的值守清单"):
        assert k in ask, k
    if not CLAUDE.exists():
        return
    c = CLAUDE.read_text(encoding="utf-8")
    live = c.split("- 实盘相关（立花）", 1)[1].split("\n- 手机上操作", 1)[0]
    for k in ("liveu.sh cancel", "halt-cancel", "liveu.sh adopt", "liveu.sh restore --broker tachibana <备份文件名>", "adopt-host",
              "closed add|rm", "用户这次明确说才运行", "無効化", "可以撤", "email-setup"):
        assert k in live or k in c, k
    assert "盘中的单发出后可以撤" in live


def test_documented_liveu_subcommands_exist():
    sh = _read("scripts/liveu.sh")
    subs = set(re.findall(r'"\$\{1:-\}" = "([\w-]+)"', sh))
    assert {"cancel", "halt-cancel", "unknown", "reconcile", "adopt", "restore", "precheck", "adopt-host", "closed", "email-setup"} <= subs
    docs = [_read(n) for n in ("MACOS.md", "HANDOFF.md", "CHECK_TIMELINE.md", "README.md")]
    if CLAUDE.exists():
        docs.append(CLAUDE.read_text(encoding="utf-8"))
    used = set()
    for t in docs:
        used |= set(re.findall(r"liveu\.sh\s+([A-Za-z][\w-]*)", t))
    assert used - subs == set(), sorted(used - subs)
