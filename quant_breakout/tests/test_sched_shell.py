"""立花实盘缺口 B 组「SCHED」的 shell 部分（2026-10-09）：前一晚预检的 LaunchAgent、冒烟测试挡住不下单、日志轮换、磁盘不足提醒、
登录时 Python 环境坏了的提醒、requirements.lock 的安装（装不上退回 requirements.txt）、新子命令的转发。
假 Python / 假 osascript / 假 caffeinate（tests/test_shell_scripts.py 的 _run_env），不调真的 launchctl / security / osascript。"""
import os
import shutil
import sys
from pathlib import Path

import pytest

from test_shell_scripts import ROOT, _bash, _calls, _run_env

pytestmark = pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")


def _stub(tmp_path, name: str, body: str) -> Path:
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    p = b / name
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return p


# ────────── 前一晚预检的 LaunchAgent ──────────
def test_precheck_agent_installs_with_the_live_mode_and_goes_with_it(tmp_path):
    env, _ = _run_env(tmp_path, 0, QBREAK_SKIP_VENV="1")
    agents = tmp_path / "agents"
    _stub(tmp_path, "launchctl", "#!/bin/sh\nexit 0\n")
    _stub(tmp_path, "git", '#!/bin/sh\ncase "$*" in *rev-parse*) echo origin/x; exit 0 ;; esac\nexit 1\n')   # 有上游（不碰真仓库）
    out, err = _bash(env, "scripts/install_launchd_live_u.sh", "tachibana")
    pre = agents / "com.qbreak.precheck.plist"
    assert "已注册 com.qbreak.precheck：周日〜周四 20:00" in out and pre.exists(), (out, err)
    txt = pre.read_text(encoding="utf-8")
    assert "<string>precheck</string>" in txt and txt.count("<key>Weekday</key>") == 5
    assert "<integer>0</integer><key>Hour</key><integer>20</integer>" in txt          # 周日（0）20:00 = 周一交易的前一晚
    assert "<integer>5</integer><key>Hour</key><integer>20</integer>" not in txt      # 周五晚不做（周六休市）
    out, _ = _bash(env, "scripts/install_launchd_live_u.sh", "paper")                 # 切回模拟：预检一起卸
    assert not pre.exists() and "已卸载 com.qbreak.precheck" in out
    _bash(env, "scripts/install_launchd_live_u.sh", "tachibana")
    assert pre.exists()
    out, _ = _bash(env, "scripts/install_launchd_live_u.sh", "uninstall")
    assert not pre.exists() and "已卸载 com.qbreak.precheck" in out


def test_wakehold_agent_installs_with_both_modes_and_goes_with_uninstall(tmp_path):
    """06:40 唤醒之后一直醒到 07:40 的执行器（com.qbreak.wakehold：caffeinate -i -t 4200），不靠桌面版的 Keep computer awake（R-4）。"""
    env, _ = _run_env(tmp_path, 0, QBREAK_SKIP_VENV="1")
    agents = tmp_path / "agents"
    _stub(tmp_path, "launchctl", "#!/bin/sh\nexit 0\n")
    _stub(tmp_path, "git", '#!/bin/sh\ncase "$*" in *rev-parse*) echo origin/x; exit 0 ;; esac\nexit 1\n')
    wh = agents / "com.qbreak.wakehold.plist"
    for mode in ("paper", "tachibana"):
        out, err = _bash(env, "scripts/install_launchd_live_u.sh", mode)
        assert wh.exists() and "已注册 com.qbreak.wakehold" in out, (out, err)
        txt = wh.read_text(encoding="utf-8")
        assert "<string>/usr/bin/caffeinate</string>" in txt and "<string>4200</string>" in txt and txt.count("<key>Weekday</key>") == 5
        assert "<integer>1</integer><key>Hour</key><integer>6</integer><key>Minute</key><integer>40</integer>" in txt
        assert "<integer>0</integer><key>Hour</key>" not in txt and "<integer>6</integer><key>Hour</key>" not in txt   # 只周一至五
    out, _ = _bash(env, "scripts/install_launchd_live_u.sh", "uninstall")
    assert not wh.exists() and "已卸载 com.qbreak.wakehold" in out
    (agents / "com.qbreak.liveu.paper.plist").write_text("x", encoding="utf-8")         # 以前装的模拟操盘：mac_setup 补上
    (tmp_path / "m").mkdir()
    env2, _ = _run_env(tmp_path / "m", 0, QBREAK_SKIP_VENV="1", QBREAK_DEV=str(tmp_path / "nodev"), QBREAK_LAUNCH_AGENTS=str(agents))
    _stub(tmp_path / "m", "launchctl", "#!/bin/sh\nexit 0\n")
    _stub(tmp_path / "m", "git", "#!/bin/sh\nexit 1\n")
    out, err = _bash(env2, "scripts/mac_setup.sh")
    assert "缺「唤醒后保持清醒」" in out and wh.exists(), (out, err)


def test_mac_setup_adds_the_missing_precheck_to_an_existing_live_install(tmp_path):
    env, _ = _run_env(tmp_path, 0, QBREAK_SKIP_VENV="1", QBREAK_DEV=str(tmp_path / "nodev"))
    _stub(tmp_path, "launchctl", "#!/bin/sh\nexit 0\n")
    _stub(tmp_path, "git", "#!/bin/sh\nexit 1\n")                                   # 研究用的克隆建不了：其他步骤照常
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    for lb in ("morning", "retry", "open", "open2"):
        (agents / f"com.qbreak.liveu.{lb}.plist").write_text("x", encoding="utf-8")
    out, err = _bash(env, "scripts/mac_setup.sh")
    assert "立花本番缺前一晚预检" in out and (agents / "com.qbreak.precheck.plist").exists(), (out, err)


# ────────── 冒烟测试（立花本番、新代码）──────────
def test_new_code_runs_the_smoke_test_and_blocks_orders_when_it_fails(tmp_path):
    env, log = _run_env(tmp_path, 0, QBREAK_SMOKE_CMD="echo boom; exit 1")
    out, err = _bash(env, "scripts/liveu.sh", "run", "--broker", "tachibana", "--retry")
    c = _calls(log)
    assert "新代码的冒烟测试没过" in out and "--block-reason 新代码的冒烟测试没过" in c, (out, err)
    assert "osascript" in c and "notify --subject qbreak 立花实盘 ★ 新代码的冒烟测试没过" in c
    assert "boom" in (tmp_path / "lh" / "logs" / "smoke_test.log").read_text(encoding="utf-8")
    assert not (tmp_path / "lh" / ".smoke_ok").exists()


def test_smoke_test_passes_once_per_commit_and_skips_paper_demo_and_cancel(tmp_path):
    env, log = _run_env(tmp_path, 0, QBREAK_SMOKE_CMD="exit 0")
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "tachibana", "--retry")
    ok = (tmp_path / "lh" / ".smoke_ok").read_text(encoding="utf-8").strip()
    assert "冒烟测试通过" in out and ok and "--block-reason" not in _calls(log)
    env, log = _run_env(tmp_path, 0, QBREAK_SMOKE_CMD="exit 1")                      # 同一个提交：不再跑（假命令会失败，但没被叫）
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "tachibana", "--retry")
    assert "冒烟测试" not in out and "--block-reason" not in _calls(log)
    (tmp_path / "lh" / ".smoke_ok").unlink()
    for args in (["--broker", "paper", "--retry"], ["--broker", "tachibana", "--demo", "--retry"],
                 ["--broker", "tachibana", "--dry-run", "--retry"], ["--broker", "tachibana", "--phase", "cancel"]):
        env, log = _run_env(tmp_path, 0, QBREAK_SMOKE_CMD="exit 1")
        out, _ = _bash(env, "scripts/liveu.sh", "run", *args)
        assert "冒烟测试" not in out and "--block-reason" not in _calls(log), args


def test_smoke_ok_is_keyed_on_the_code_only_identity(tmp_path):
    """.smoke_ok 记的是只看代码的标识（qbreak/versions.py code_tree() 同一个算法）：云端每天推的 var/ 提交不算新代码。"""
    from qbreak import versions as V
    env, log = _run_env(tmp_path, 0, QBREAK_SMOKE_CMD="exit 0")
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "tachibana", "--retry")
    ok = (tmp_path / "lh" / ".smoke_ok").read_text(encoding="utf-8").strip()
    assert ok == V.code_tree() and len(ok) == 12, out


def test_smoke_test_timeout_blocks_too(tmp_path):
    env, log = _run_env(tmp_path, 0, QBREAK_SMOKE_CMD="sleep 30", QBREAK_SMOKE_TIMEOUT="2")
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "tachibana", "--retry")
    assert "冒烟测试没跑完" in out and "--block-reason 新代码的冒烟测试没跑完" in _calls(log)


# ────────── 日志轮换 / 磁盘 ──────────
def test_big_logs_rotate_and_keep_three(tmp_path):
    env, log = _run_env(tmp_path, 0, QBREAK_LOG_MAX_BYTES="100")
    logs = tmp_path / "lh" / "logs"
    logs.mkdir(parents=True)
    (logs / "com.qbreak.news.out").write_text("x" * 500, encoding="utf-8")
    (logs / "com.qbreak.news.out.1").write_text("old1", encoding="utf-8")
    (logs / "com.qbreak.news.out.2").write_text("old2", encoding="utf-8")
    (logs / "com.qbreak.news.out.3").write_text("old3", encoding="utf-8")
    (logs / "com.qbreak.panel.err").write_text("small", encoding="utf-8")
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "paper", "--retry")
    assert "日志轮换：com.qbreak.news.out" in out
    assert (logs / "com.qbreak.news.out.1").read_text(encoding="utf-8") == "x" * 500
    assert (logs / "com.qbreak.news.out.2").read_text(encoding="utf-8") == "old1"
    assert (logs / "com.qbreak.news.out.3").read_text(encoding="utf-8") == "old2"   # 最旧的那份丢掉：只留 3 份
    assert not (logs / "com.qbreak.news.out.4").exists()
    f = logs / "com.qbreak.news.out"
    assert not f.exists() or f.stat().st_size == 0
    assert (logs / "com.qbreak.panel.err").read_text(encoding="utf-8") == "small"


def test_low_disk_notifies_once_a_day(tmp_path):
    env, log = _run_env(tmp_path, 0, QBREAK_DISK_MIN_KB="999999999999")
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "paper", "--retry")
    c = _calls(log)
    assert "Mac 的磁盘只剩" in out and "notify --subject qbreak ★ Mac 的磁盘快满了" in c and "osascript" in c
    env, log = _run_env(tmp_path, 0, QBREAK_DISK_MIN_KB="999999999999")
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "paper", "--retry")
    assert "Mac 的磁盘只剩" in out and "磁盘快满了" not in _calls(log)                 # 同一天：只打印，不再通知


def test_rotation_covers_dot_log_files_but_not_qbreak_log(tmp_path):
    """2026-10-24 复核：面板追加写的 *.log（盘中观测 / 重试记录 / demotest）以前不轮换；qbreak.log 由 Python 自己轮换，不动。"""
    env, log = _run_env(tmp_path, 0, QBREAK_LOG_MAX_BYTES="100")
    logs = tmp_path / "lh" / "logs"
    logs.mkdir(parents=True)
    for n in ("com.qbreak.panel.intraday.log", "com.qbreak.panel.retry.log", "demotest.log", "qbreak.log"):
        (logs / n).write_text("y" * 500, encoding="utf-8")
    (logs / "com.qbreak.panel.intraday.log.1").write_text("old1", encoding="utf-8")
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "paper", "--retry")
    for n in ("com.qbreak.panel.intraday.log", "com.qbreak.panel.retry.log", "demotest.log"):
        assert f"日志轮换：{n}" in out and (logs / f"{n}.1").read_text(encoding="utf-8") == "y" * 500, (n, out)
    assert (logs / "com.qbreak.panel.intraday.log.2").read_text(encoding="utf-8") == "old1"
    assert (logs / "qbreak.log").read_text(encoding="utf-8") == "y" * 500 and not (logs / "qbreak.log.1").exists()
    assert "日志轮换：qbreak.log" not in out


def test_news_job_rotates_once_a_day_and_warns_low_disk_once_a_day(tmp_path):
    """2026-10-24 复核：每 15 分钟的 news 也轮换日志（同一天一次）、看磁盘（< 10 GB；同一天一次推送，和执行器共用 .disk_warned）。"""
    env, log = _run_env(tmp_path, 0, QBREAK_LOG_MAX_BYTES="100", QBREAK_DISK_MIN_KB="999999999999")
    logs = tmp_path / "lh" / "logs"
    logs.mkdir(parents=True)
    (logs / "com.qbreak.news.out").write_text("x" * 500, encoding="utf-8")
    out, err = _bash(env, "scripts/liveu.sh", "news")
    c = _calls(log)
    assert (logs / "com.qbreak.news.out.1").read_text(encoding="utf-8") == "x" * 500, (out, err)
    assert c.count("notify --subject qbreak ★ Mac 的磁盘快满了") == 1 and "osascript" in c
    assert "Mac 的磁盘只剩" not in out                                              # 每 15 分钟：不往日志里写
    assert "run.py news --page --notify" in c                                     # 仪表盘照常
    (logs / "com.qbreak.news.out").write_text("z" * 500, encoding="utf-8")
    env, log = _run_env(tmp_path, 0, QBREAK_LOG_MAX_BYTES="100", QBREAK_DISK_MIN_KB="999999999999")
    out, _ = _bash(env, "scripts/liveu.sh", "news")                                # 同一天第二次：不再轮换、不再推送
    assert (logs / "com.qbreak.news.out.1").read_text(encoding="utf-8") == "x" * 500
    assert "磁盘快满了" not in _calls(log) and "osascript" not in _calls(log)
    env, log = _run_env(tmp_path, 0, QBREAK_LOG_MAX_BYTES="100", QBREAK_DISK_MIN_KB="999999999999")
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "paper", "--retry")  # 执行器照旧每次轮换、只打印（今天已推过）
    assert (logs / "com.qbreak.news.out.1").read_text(encoding="utf-8") == "z" * 500
    assert "Mac 的磁盘只剩" in out and "磁盘快满了" not in _calls(log)


def test_disk_warning_threshold_is_10_gb():
    sh = (ROOT / "scripts" / "liveu.sh").read_text(encoding="utf-8")
    assert '"${QBREAK_DISK_MIN_KB:-10485760}"' in sh and "QBREAK_DISK_MIN_KB:-1048576}" not in sh


# ────────── 登录时：Python 环境坏了 ──────────
def test_login_warns_when_the_venv_python_is_broken(tmp_path):
    env, log = _run_env(tmp_path, 0, QBREAK_LOGIN_DELAY="0")
    bad = _stub(tmp_path, "badpy", '#!/bin/sh\necho "badpy $*" >> "$CALLS"\nexit 1\n')
    sys_py = _stub(tmp_path, "python3", '#!/bin/sh\necho "syspy $*" >> "$CALLS"\nexit 0\n')
    out, _ = _bash({**env, "QBREAK_PYTHON": str(bad)}, "scripts/liveu.sh", "login")
    c = _calls(log)
    assert "Python 环境坏了" in out and "osascript" in c
    assert "badpy run.py notify --subject qbreak ★ Mac 的 Python 环境坏了" in c       # 先用虚拟环境试
    assert "syspy run.py notify --subject qbreak ★ Mac 的 Python 环境坏了" in c       # 不行再用系统的 python3
    assert sys_py.exists()
    env, log = _run_env(tmp_path, 0, QBREAK_LOGIN_DELAY="0")                          # 好的 Python：不提醒
    out, _ = _bash(env, "scripts/liveu.sh", "login")
    assert "Python 环境坏了" not in out


# ────────── 依赖：requirements.lock ──────────
def test_install_deps_prefers_the_lock_and_falls_back(tmp_path):
    calls = tmp_path / "pip.log"
    py = _stub(tmp_path, "vpy", '#!/bin/sh\necho "$*" >> "$PIPLOG"\n'
                                'case "$*" in *requirements.lock*) exit "${LOCK_RC:-0}" ;; esac\n'
                                'case "$*" in *version_info*) echo 3.10 ;; esac\nexit 0\n')
    env = {**os.environ, "PIPLOG": str(calls), "LC_ALL": "C.UTF-8"}
    r = __import__("subprocess").run(["bash", "scripts/install_deps.sh", str(py)], cwd=ROOT, env=env,
                                     capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "按 requirements.lock 装好" in r.stdout
    assert "requirements.txt" not in calls.read_text(encoding="utf-8")
    calls.unlink()
    r = __import__("subprocess").run(["bash", "scripts/install_deps.sh", str(py)], cwd=ROOT, env={**env, "LOCK_RC": "1"},
                                     capture_output=True, text=True, timeout=60)
    log = calls.read_text(encoding="utf-8")
    assert r.returncode == 0 and "Python 3.10" in r.stdout and "退回 requirements.txt" in r.stdout
    assert "requirements.lock" in log and "requirements.txt" in log
    for f in ("install_launchd_live_u.sh", "mac_setup.sh"):
        assert "install_deps.sh" in (ROOT / "scripts" / f).read_text(encoding="utf-8"), f


# ────────── 新子命令的转发 ──────────
@pytest.mark.parametrize("args,expect", [
    (["precheck", "--force"], "py run.py live-precheck --force"),
    (["adopt-host"], "py run.py live-u --broker tachibana --adopt-host"),
    (["closed", "list"], "py run.py extra-closed list"),
])
def test_new_subcommands_pass_through(tmp_path, args, expect):
    env, log = _run_env(tmp_path, 0)
    _bash(env, "scripts/liveu.sh", *args)
    assert expect in _calls(log)


def test_dev_check_reports_the_lock(tmp_path):
    """dev.sh check：虚拟环境的版本和 requirements.lock 比（不一致只提醒，不算 ★）。"""
    env, _ = _run_env(tmp_path, 0, QBREAK_PYTHON=sys.executable, QBREAK_DEV=str(tmp_path / "none"),
                      QBREAK_SRC=str(tmp_path / "none"))
    out, _ = _bash(env, "scripts/dev.sh", "check")
    assert ("[OK] 虚拟环境的依赖版本与 requirements.lock 一致" in out
            or "[提醒] 虚拟环境有" in out), out


# ────────── 立花 + 模拟同时跑（install_launchd_live_u.sh both，2026-10-17 用户「现在装、模拟同时跑」）──────────
TACHI = ("morning", "retry", "open", "open2", "fills1", "fills2")


def test_both_mode_installs_paper_and_tachibana_and_switching_removes_the_other(tmp_path):
    env, _ = _run_env(tmp_path, 0, QBREAK_SKIP_VENV="1")
    agents = tmp_path / "agents"
    _stub(tmp_path, "launchctl", "#!/bin/sh\nexit 0\n")
    _stub(tmp_path, "git", '#!/bin/sh\ncase "$*" in *rev-parse*) echo origin/x; exit 0 ;; esac\nexit 1\n')
    paper = agents / "com.qbreak.liveu.paper.plist"
    out, err = _bash(env, "scripts/install_launchd_live_u.sh", "both")
    assert paper.exists(), (out, err)
    assert "<string>paper</string>" in paper.read_text(encoding="utf-8")
    for k in TACHI:
        assert (agents / f"com.qbreak.liveu.{k}.plist").exists(), (k, out, err)
        assert "<string>tachibana</string>" in (agents / f"com.qbreak.liveu.{k}.plist").read_text(encoding="utf-8")
    assert (agents / "com.qbreak.precheck.plist").exists() and (agents / "com.qbreak.wakehold.plist").exists()
    from qbreak import watchdog
    assert watchdog.installed_all(agents) == ["tachibana", "paper"] and watchdog.installed(agents) == "tachibana"
    _bash(env, "scripts/install_launchd_live_u.sh", "tachibana")                      # 只立花：模拟卸掉
    assert not paper.exists() and (agents / "com.qbreak.liveu.morning.plist").exists()
    assert watchdog.installed_all(agents) == ["tachibana"]
    _bash(env, "scripts/install_launchd_live_u.sh", "paper")                          # 只模拟：立花全卸
    assert paper.exists() and not any((agents / f"com.qbreak.liveu.{k}.plist").exists() for k in TACHI)
    assert watchdog.installed_all(agents) == ["paper"]


def test_mac_setup_reinstall_keeps_paper_when_both_were_installed(tmp_path):
    """mac_setup 补装立花缺的重试时：模拟也装着 → 用 both 重装（不把模拟卸掉）。"""
    agents = tmp_path / "agents"
    agents.mkdir()
    for k in ("paper", "morning"):                                                    # 旧的立花安装缺 retry / open2
        (agents / f"com.qbreak.liveu.{k}.plist").write_text("x", encoding="utf-8")
    (tmp_path / "m").mkdir()
    env, _ = _run_env(tmp_path / "m", 0, QBREAK_SKIP_VENV="1", QBREAK_DEV=str(tmp_path / "nodev"), QBREAK_LAUNCH_AGENTS=str(agents))
    _stub(tmp_path / "m", "launchctl", "#!/bin/sh\nexit 0\n")
    _stub(tmp_path / "m", "git", '#!/bin/sh\ncase "$*" in *rev-parse*) echo origin/x; exit 0 ;; esac\nexit 1\n')
    out, err = _bash(env, "scripts/mac_setup.sh")
    assert "重装（both" in out, (out, err)
    assert (agents / "com.qbreak.liveu.paper.plist").exists() and (agents / "com.qbreak.liveu.retry.plist").exists()
    assert (agents / "com.qbreak.liveu.open2.plist").exists()
