"""qbreak/mac_login.py + scripts/liveu.sh login（Mac 登录 / 开机时的自动启动）：什么时候补跑模拟操盘、仪表盘没加载就加载、
打开页面遵守 NO_OPEN、立花本番永远不补跑；shell 部分用假的 launchctl / open / pgrep 真跑一遍（不碰真的定时任务、不下单）。"""
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

from qbreak import mac_login as ML
from qbreak.calendar_jp import JST

ROOT = Path(__file__).resolve().parent.parent
MON_0800 = dt.datetime(2026, 9, 28, 8, 0, tzinfo=JST)                         # 周一（交易日）08:00


def _setup(tmp_path, paper=True, live=False, news=True, summary_at=None, no_open=False):
    home, agents = tmp_path / "home", tmp_path / "agents"
    (home / "out").mkdir(parents=True)
    agents.mkdir()
    for ok, name in ((paper, ML.PAPER), (live, ML.LIVE), (news, ML.NEWS)):
        if ok:
            (agents / f"{name}.plist").write_text("x", encoding="utf-8")
    for p in ("page_paper.html", "dashboard.html"):
        (home / "out" / p).write_text("x", encoding="utf-8")
    if summary_at is not None:
        fp = home / "out" / "live_unified_paper.json"
        fp.write_text("{}", encoding="utf-8")
        ts = summary_at.timestamp()
        os.utime(fp, (ts, ts))
    if no_open:
        (home / "NO_OPEN").write_text("", encoding="utf-8")
    return home, agents


def _acts(p):
    return [a for a, _ in p["actions"]]


def test_catch_up_when_trading_day_after_0740_and_not_run(tmp_path):
    home, agents = _setup(tmp_path, summary_at=MON_0800 - dt.timedelta(days=3))    # 上次是上周五
    p = ML.plan(MON_0800, home, agents, {ML.NEWS, ML.PAPER}, running=False)
    assert _acts(p) == ["RUN_PAPER", "OPEN"] and p["actions"][1][1].endswith("dashboard.html")   # 补跑自己会打开账本页面
    assert any("补跑" in n for n in p["notes"])


def test_no_catch_up_cases(tmp_path):
    home, agents = _setup(tmp_path, summary_at=MON_0800 - dt.timedelta(hours=1))   # 今天 07:00 已经跑过
    p = ML.plan(MON_0800, home, agents, {ML.NEWS}, running=False)
    assert "RUN_PAPER" not in _acts(p) and "今天已经跑过" in " ".join(p["notes"])
    assert [x[1].split("/")[-1] for x in p["actions"]] == ["page_paper.html", "dashboard.html"]
    early = ML.plan(MON_0800.replace(hour=7, minute=30), *_setup(tmp_path / "b"), {ML.NEWS}, running=False)
    assert "RUN_PAPER" not in _acts(early) and "还没到 07:40" in " ".join(early["notes"])
    sat = ML.plan(dt.datetime(2026, 9, 26, 10, 0, tzinfo=JST), *_setup(tmp_path / "c"), {ML.NEWS}, running=False)
    assert "RUN_PAPER" not in _acts(sat) and "不是交易日" in " ".join(sat["notes"])
    busy = ML.plan(MON_0800, *_setup(tmp_path / "d"), {ML.NEWS}, running=True)
    assert "RUN_PAPER" not in _acts(busy) and "执行器正在跑" in " ".join(busy["notes"])


def test_never_catch_up_with_live_broker_or_without_paper_agent(tmp_path):
    live = ML.plan(MON_0800, *_setup(tmp_path / "a", live=True), {ML.NEWS}, running=False)
    assert "RUN_PAPER" not in _acts(live) and "立花本番" in " ".join(live["notes"])
    none = ML.plan(MON_0800, *_setup(tmp_path / "b", paper=False), {ML.NEWS}, running=False)
    assert "RUN_PAPER" not in _acts(none)


def test_news_agent_load_or_install_and_no_open(tmp_path):
    home, agents = _setup(tmp_path / "a", summary_at=MON_0800, no_open=True)
    p = ML.plan(MON_0800, home, agents, set(), running=False)
    assert _acts(p) == ["LOAD_NEWS"] and "NO_OPEN" in " ".join(p["notes"])
    home, agents = _setup(tmp_path / "b", news=False, summary_at=MON_0800)
    assert _acts(ML.plan(MON_0800, home, agents, set(), running=False))[0] == "INSTALL_NEWS"


def _stub_env(tmp_path, launchctl_list: str) -> dict:
    b = tmp_path / "bin"
    b.mkdir()
    log = tmp_path / "calls.log"
    stubs = {"launchctl": f'#!/bin/sh\necho "launchctl $*" >> "{log}"\n[ "$1" = list ] && printf "%s" "{launchctl_list}"\nexit 0\n',
             "fakeopen": f'#!/bin/sh\necho "open $*" >> "{log}"\n', "pgrep": "#!/bin/sh\nexit 1\n"}
    for n, body in stubs.items():
        (b / n).write_text(body, encoding="utf-8")
        (b / n).chmod(0o755)
    return {**os.environ, "PATH": f"{b}{os.pathsep}{os.environ['PATH']}", "QBREAK_PYTHON": sys.executable,
            "QBREAK_LIVEU_HOME": str(tmp_path / "home"), "QBREAK_LAUNCH_AGENTS": str(tmp_path / "agents"),
            "QBREAK_LOGIN_DELAY": "0", "QBREAK_LOGIN_DRY": "1", "QBREAK_OPEN_CMD": str(b / "fakeopen"),
            "QBREAK_NOW": "2026-09-28T08:00:00", "PYTHONIOENCODING": "utf-8"}


def test_liveu_login_shell_end_to_end(tmp_path):
    _setup(tmp_path, summary_at=MON_0800 - dt.timedelta(days=3))
    env = _stub_env(tmp_path, "PID\tStatus\tLabel\n-\t0\tcom.qbreak.liveu.paper\n")   # 仪表盘没加载
    r = subprocess.run(["bash", "scripts/liveu.sh", "login"], cwd=ROOT, env=env, capture_output=True, timeout=120)
    out, err = r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0 and "unbound variable" not in err, err
    assert "登录时的检查" in out and "市场仪表盘没有在运行 → 加载" in out and "已加载 com.qbreak.news" in out
    assert "（演练：这里会补跑 liveu.sh run --broker paper）" in out and "已打开 " in out
    calls = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert "launchctl load -w" in calls and "com.qbreak.news.plist" in calls and "dashboard.html" in calls
    assert "page_paper.html" not in calls                                     # 补跑会自己打开账本页面，这里不重复
    (tmp_path / "home" / "NO_OPEN").write_text("", encoding="utf-8")
    r = subprocess.run(["bash", "scripts/liveu.sh", "login"], cwd=ROOT, env={**env, "QBREAK_NOW": "2026-09-28T07:00:00"},
                       capture_output=True, timeout=120)
    out = r.stdout.decode("utf-8", "replace")
    assert "还没到 07:40" in out and "有 NO_OPEN：不打开页面" in out and "已打开" not in out


def test_install_launchd_login_plist(tmp_path):
    env = {**os.environ, "QBREAK_SKIP_VENV": "1", "QBREAK_PYTHON": sys.executable, "QBREAK_LAUNCH_AGENTS": str(tmp_path / "agents"),
           "QBREAK_LIVEU_HOME": str(tmp_path / "home"), "PATH": "/usr/bin:/bin"}
    r = subprocess.run(["bash", "scripts/install_launchd_login.sh"], cwd=ROOT, env=env, capture_output=True, timeout=60)
    out = r.stdout.decode("utf-8", "replace")
    plist = (tmp_path / "agents" / "com.qbreak.login.plist").read_text(encoding="utf-8")
    assert r.returncode == 0 and "已注册 com.qbreak.login" in out
    assert "<key>RunAtLoad</key><true/>" in plist and "<string>login</string>" in plist and "StartInterval" not in plist
    r = subprocess.run(["bash", "scripts/install_launchd_login.sh", "uninstall"], cwd=ROOT, env=env, capture_output=True, timeout=60)
    assert "已卸载 com.qbreak.login" in r.stdout.decode("utf-8") and not (tmp_path / "agents" / "com.qbreak.login.plist").exists()
