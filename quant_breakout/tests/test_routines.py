"""例行任务搬到 Mac（2026-10-09 用户「连云端例行任务也搬到 Mac」）：scripts/routines.sh、qbreak/routines.py、09:30 自检的「今天的日报没入库」、
mac_setup.sh 的 ~/qbreak-sim、说明书 routines/*.md 里的路径与命令。

全部在临时目录：一个 bare 仓库当远端，克隆 sim（= ~/qbreak-sim，本机例行任务）与 cloud（= 云端后备）；HOME 指向临时目录（不读你的 git
全局设置），假的 uname / security / pmset / 桌面版 Info.plist；不联网、不碰真的仓库、不调真的 security / pmset / launchctl。
"""
import datetime as dt
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from qbreak import paths, routines, watchdog
from qbreak.calendar_jp import JST

ROOT = Path(__file__).resolve().parent.parent
SH = ROOT / "scripts" / "routines.sh"
BRANCH = "claude/rakuten-auto-trading-review-ka7lf0"
DAILY = "quant_breakout/var/out/unified_today.json"
TOKEN = "ghp_abcdefghijklmnopqrstu"

_REAL_REMOTE_DAILY = watchdog._remote_daily_date      # 收集测试时（conftest 把它换成「读不了」之前）
need_git = pytest.mark.skipif(not shutil.which("git") or not shutil.which("bash"), reason="需要 git + bash")


# ────────── qbreak/routines.py（纯函数）──────────
def _ts(d: str, hm: str = "07:10") -> int:
    return int(dt.datetime.fromisoformat(f"{d}T{hm}:00").replace(tzinfo=JST).timestamp())


def test_who_and_find_each_kind():
    assert routines.who("sim(mac): 2026-10-08 日报") == "Mac" and routines.who("sim: 2026-10-08 日报") == "云端"
    assert routines.who("季度复核(mac)：顶底择时 2026-10-12") == "Mac" and routines.who("shadow(mac): 2026-10-09 判断") == "Mac"
    assert routines.who("修 sim(mac) 的说明") == "云端"                            # 标签只看开头
    e = routines.parse_log("\n".join([
        f"{_ts('2026-10-09', '07:11')}\tsim: 2026-10-08 日报（无下单）",
        f"{_ts('2026-10-09', '07:46')}\tshadow(mac): 2026-10-09 判断",
        f"{_ts('2026-10-12', '10:30')}\t季度复核加 2n 新的复核（用户确认）",          # 改例行任务的提交：不算复核
        "坏行", f"{_ts('2026-10-08', '06:55')}\tsim(mac): 2026-10-07 日报"]))
    d9, d8 = dt.date(2026, 10, 9), dt.date(2026, 10, 8)
    assert routines.find("sim", e, d9) == "云端" and routines.find("sim", e, d8) == "Mac"   # 日报看提交日（标题里是 K 线日期）
    assert routines.find("shadow", e, d9) == "Mac" and routines.find("shadow", e, d8) is None
    assert routines.find("quarterly", e, dt.date(2026, 10, 12)) is None
    e2 = routines.parse_log(f"{_ts('2026-10-12', '13:40')}\t季度复核：顶底择时 T0/T2/T3、… 2026-10-12")
    assert routines.find("quarterly", e2, dt.date(2026, 10, 12)) == "云端"


def test_table_lists_weekdays_and_marks_holidays():
    e = routines.parse_log(f"{_ts('2026-10-09', '06:58')}\tsim(mac): 2026-10-08 日报\n{_ts('2026-10-09', '07:50')}\tshadow: 2026-10-09 判断")
    rows = routines.table(e, dt.date(2026, 10, 13), 5)
    assert [r[:10] for r in rows] == ["2026-10-13", "2026-10-12", "2026-10-09", "2026-10-08", "2026-10-07"]
    assert rows[1] == "2026-10-12（周一，休市）：日报 —；影子账户 —（休市不做）"           # スポーツの日：日报照常做、影子不做
    assert rows[2] == "2026-10-09（周五）：日报 Mac；影子账户 云端"


def test_wake_and_app_version(tmp_path):
    ok, txt = routines.wake("Repeating power events:\n  wakepoweron at 6:40AM weekdays only\n")
    assert ok is True and "已设定" in txt
    ok, txt = routines.wake("Repeating power events:\n  wakepoweron at 7:30AM weekdays only\n")
    assert ok is False and "晚于 06:50" in txt and "MTWRF 06:40:00" in txt                 # 原来的 07:30：本机日报来不及
    assert routines.wake("Repeating power events:\n  wake at 6:30AM weekends only\n")[0] is None
    assert routines.wake("Scheduled power events:\n [0] wake at 10/05/2026 06:30:00\n")[0] is False
    p = tmp_path / "Info.plist"
    assert routines.app(str(p))[0] is False                                              # 没装
    p.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "1.1.5367"}))
    assert routines.app(str(p))[0] is False
    p.write_bytes(plistlib.dumps({"CFBundleShortVersionString": "1.2.0"}))
    ok, txt = routines.app(str(p))
    assert ok is True and "1.2.0" in txt
    p.write_bytes(b"not a plist")
    assert routines.app(str(p))[0] is None


def test_cli_day_and_usage(capsys):
    assert routines.main(["day", "2026-10-12"]) == 0 and capsys.readouterr().out.strip() == "1 0"
    assert routines.main(["day", "2026-10-10"]) == 0 and capsys.readouterr().out.strip() == "6 0"
    assert routines.main(["bogus"]) == 2


# ────────── scripts/routines.sh（临时 git 仓库）──────────
def _base_env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GIT_", "QBREAK_", "XDG_", "CLAUDE_")) and k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
    return {**env, "HOME": str(home), "XDG_CONFIG_HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1", "LANG": "C.UTF-8", "TZ": "UTC"}


def _git(cwd, *args, ident=True, env=None) -> str:
    pre = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"] if ident else []
    r = subprocess.run(["git", *pre, *args], cwd=cwd, capture_output=True, text=True, timeout=60, env=env or _base_env(Path(cwd)))
    assert r.returncode == 0, (args, r.stdout, r.stderr)
    return r.stdout


def _commit(clone: Path, files: dict, msg: str, date: str | None = None, ident: tuple = ("t", "t@example.invalid")):
    for rel, text in files.items():
        p = clone / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        _git(clone, "add", rel)
    env = _base_env(clone)
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    _git(clone, "-c", f"user.name={ident[0]}", "-c", f"user.email={ident[1]}", "commit", "-q", "-m", msg, ident=False, env=env)


def _daily(date: str) -> dict:
    return {DAILY: json.dumps({"date": date, "bar_date": "x"})}


@pytest.fixture
def repos(tmp_path):
    t = tmp_path
    _git(t, "init", "-q", "--bare", "remote.git", ident=False)
    seed = t / "seed"
    seed.mkdir()
    _git(seed, "init", "-q", "-b", BRANCH, ident=False)
    _commit(seed, {**_daily("2026-10-08"), "quant_breakout/app.txt": "v1\n"}, "init", date="2026-10-08T07:00:00+09:00")
    _git(seed, "push", "-q", str(t / "remote.git"), BRANCH, ident=False)
    for name in ("sim", "cloud"):
        _git(t, "clone", "-q", "-b", BRANCH, str(t / "remote.git"), name, ident=False)
    _git(t / "sim", "config", "user.name", "t", ident=False)
    _git(t / "sim", "config", "user.email", "t@example.invalid", ident=False)
    return t


def _bin(t: Path, uname: str = "Linux", security: int | None = None, pmset: str | None = None) -> Path:
    """假的 uname / security / pmset（只放这次要的）。security：find-generic-password 的退出码（None = 没有这个命令）。"""
    b = t / "bin"
    b.mkdir(exist_ok=True)
    stubs = {"uname": f"#!/bin/sh\necho {uname}\n"}
    if security is not None:
        stubs["security"] = f'#!/bin/sh\necho "$*" >> "{t}/security.log"\nexit {security}\n'
    if pmset is not None:
        (t / "sched.txt").write_text(pmset, encoding="utf-8")
        stubs["pmset"] = f'#!/bin/sh\ncat "{t}/sched.txt"\n'
    for n, body in stubs.items():
        (b / n).write_text(body, encoding="utf-8")
        (b / n).chmod(0o755)
    return b


def _run(t: Path, *args, today="2026-10-09", repo="sim", uname="Linux", path_extra: Path | None = None, **extra) -> tuple[int, str]:
    b = path_extra or _bin(t, uname)
    env = {**_base_env(t), "PATH": f"{b}{os.pathsep}{os.environ['PATH']}", "QBREAK_ROUTINES_REPO": str(t / repo),
           "QBREAK_SIM": str(t / "sim"), "QBREAK_SRC": str(t / "src"), "QBREAK_DEV": str(t / "dev"),
           "QBREAK_PYTHON": sys.executable, "QBREAK_ROUTINES_TODAY": today, "QBREAK_ROUTINES_SLEEP": "0", **extra}
    r = subprocess.run(["bash", str(SH), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    return r.returncode, r.stdout + r.stderr


def _push_cloud(t: Path, files: dict, msg: str, date: str):
    _commit(t / "cloud", files, msg, date=date)
    _git(t / "cloud", "push", "-q", "origin", BRANCH, ident=False)


@need_git
def test_done_today_sim_pulls_and_says_who(repos):
    t = repos
    rc, out = _run(t, "done-today", "sim")
    assert rc == 1 and "今天 2026-10-09 的模拟盘日报还没入库（最新 2026-10-08）：照常做" in out, out
    _push_cloud(t, _daily("2026-10-09"), "sim: 2026-10-08 日报（无下单）", "2026-10-09T07:11:00+09:00")
    rc, out = _run(t, "done-today", "sim")
    assert rc == 0 and "今天已经做过（云端）：2026-10-09 的模拟盘日报已入库" in out, out
    assert json.loads((t / "sim" / DAILY).read_text(encoding="utf-8"))["date"] == "2026-10-09"   # 先 git pull --ff-only
    _push_cloud(t, _daily("2026-10-13"), "sim(mac): 2026-10-09 日报", "2026-10-13T06:58:00+09:00")
    rc, out = _run(t, "done-today", "sim", today="2026-10-13")
    assert rc == 0 and "今天已经做过（Mac）" in out, out
    rc, out = _run(t, "done-today", "sim", today="2026-10-12")                            # 休市的工作日：照常做（和云端以前一样）
    assert rc == 1 and "今天 2026-10-12 休市：日报照常做" in out, out
    rc, out = _run(t, "done-today", "sim", today="2026-10-10")                            # 周六
    assert rc == 0 and "周末" in out


@need_git
def test_done_today_shadow_and_quarterly(repos):
    t = repos
    _push_cloud(t, {"quant_breakout/var/out/shadow_today.json": "{}"}, "shadow: 2026-10-08 判断", "2026-10-08T07:50:00+09:00")
    rc, out = _run(t, "done-today", "shadow")
    assert rc == 1 and "影子账户判断还没入库" in out
    _push_cloud(t, {"quant_breakout/var/out/shadow_today.json": "{1}"}, "shadow(mac): 2026-10-09 判断", "2026-10-09T07:52:00+09:00")
    rc, out = _run(t, "done-today", "shadow")
    assert rc == 0 and "今天已经做过（Mac）：2026-10-09 的影子账户判断已入库" in out, out
    _push_cloud(t, {"quant_breakout/routines/x.md": "x"}, "季度复核加 2n（用户确认）", "2026-10-12T10:00:00+09:00")
    rc, out = _run(t, "done-today", "quarterly", today="2026-10-12")
    assert rc == 1 and "季度复核还没入库" in out                                          # 改例行任务的提交不算
    _push_cloud(t, {"quant_breakout/var/out/data_audit.md": "x"}, "季度复核：顶底择时 T0/T2/T3、…数据体检与大事件日程 2026-10-12",
                "2026-10-12T13:40:00+09:00")
    rc, out = _run(t, "done-today", "quarterly", today="2026-10-12")
    assert rc == 0 and "今天已经做过（云端）：2026-10-12 的季度复核已入库" in out
    rc, out = _run(t, "done-today", "bogus")
    assert rc == 2 and "用法" in out


@need_git
def test_done_today_stops_when_the_routine_clone_cannot_pull(repos):
    t = repos
    _commit(t / "sim", {"quant_breakout/var/x.csv": "local\n"}, "手改的提交")               # 不是例行任务的结果：不自动处理
    _push_cloud(t, _daily("2026-10-09"), "sim: 2026-10-08 日报", "2026-10-09T07:11:00+09:00")
    rc, out = _run(t, "done-today", "sim")
    assert rc == 2 and "1 个没推上去的提交" in out and "拉不下来" in out, out
    _git(t / "sim", "reset", "-q", "--hard", "origin/" + BRANCH, ident=False)
    (t / "sim" / DAILY).write_text("改了\n", encoding="utf-8")                              # 被跟踪的文件被改、远端也改了它
    _push_cloud(t, _daily("2026-10-13"), "sim: 2026-10-09 日报", "2026-10-13T07:11:00+09:00")
    rc, out = _run(t, "done-today", "sim", today="2026-10-13")
    assert rc == 2 and "被跟踪的文件改了还没提交" in out and "不要丢弃" in out, out
    assert (t / "sim" / DAILY).read_text(encoding="utf-8") == "改了\n"                     # 不动本地改动


@need_git
def test_done_today_only_fetches_in_other_clones_and_needs_a_git_identity_on_the_mac(repos):
    t = repos
    _git(t, "clone", "-q", "-b", BRANCH, str(t / "remote.git"), "src", ident=False)       # ~/qbreak-src：只 fetch，不动工作区
    _push_cloud(t, _daily("2026-10-09"), "sim: 2026-10-08 日报", "2026-10-09T07:11:00+09:00")
    rc, out = _run(t, "done-today", "sim", repo="src")
    assert rc == 0 and "今天已经做过（云端）" in out, out
    assert json.loads((t / "src" / DAILY).read_text(encoding="utf-8"))["date"] == "2026-10-08"
    _git(t / "sim", "config", "--unset", "user.email", ident=False)
    rc, out = _run(t, "done-today", "sim", uname="Darwin")                                # Mac 的例行任务克隆：没设身份 → 停下
    assert rc == 2 and "git 的 user.name / user.email 没设" in out
    assert "t@example.invalid" not in out


@need_git
def test_push_rebases_and_pushes(repos):
    t = repos
    _push_cloud(t, {"quant_breakout/var/out/a.txt": "cloud"}, "routine", "2026-10-09T07:00:00+09:00")
    _commit(t / "sim", {"quant_breakout/var/out/b.txt": "mac"}, "sim(mac): 2026-10-08 日报")
    rc, out = _run(t, "push")
    assert rc == 0 and "[OK] 已推送 1 个提交" in out and "sim(mac): 2026-10-08 日报" in out, out
    log = _git(t / "remote.git", "log", "--format=%s", BRANCH, ident=False)
    assert log.splitlines()[:2] == ["sim(mac): 2026-10-08 日报", "routine"]
    rc, out = _run(t, "push")
    assert rc == 0 and "没有要推的提交" in out


@need_git
def test_push_refuses_dirty_tree_model_names_foreign_identity_and_wrong_clone(repos):
    t = repos
    (t / "sim" / "quant_breakout" / "app.txt").write_text("改了\n", encoding="utf-8")
    rc, out = _run(t, "push")
    assert rc == 1 and "还有被跟踪的文件改了没提交" in out and "app.txt" in out
    _git(t / "sim", "checkout", "--", "quant_breakout/app.txt", ident=False)
    _commit(t / "sim", {"quant_breakout/var/c.txt": "x"}, "sim(mac): x\n\nCo-Authored-By: Claude Foo 9.9 <noreply@anthropic.com>")
    rc, out = _run(t, "push")
    assert rc == 1 and "带模型名的署名行" in out
    _git(t / "sim", "reset", "-q", "--hard", "origin/" + BRANCH, ident=False)
    _commit(t / "sim", {"quant_breakout/var/c.txt": "y"}, "sim(mac): y", ident=("someone", "me@host.local"))
    rc, out = _run(t, "push")
    assert rc == 1 and "不是现在设的 git 身份" in out and "me@host.local" not in out
    before = _git(t / "remote.git", "rev-parse", BRANCH, ident=False)
    rc, out = _run(t, "push", uname="Darwin", QBREAK_SIM=str(t / "elsewhere"))           # Mac 上不是 ~/qbreak-sim：不推
    assert rc == 1 and "不是例行任务的克隆" in out
    assert _git(t / "remote.git", "rev-parse", BRANCH, ident=False) == before             # 什么都没推


@need_git
def test_push_retries_then_reports_without_leaking_the_token(repos):
    t = repos
    _commit(t / "sim", {"quant_breakout/var/d.txt": "x"}, "sim(mac): d")
    _git(t / "sim", "remote", "set-url", "origin", f"https://{TOKEN}@127.0.0.1:9/x.git", ident=False)
    rc, out = _run(t, "push")
    assert rc == 1 and "★ 推不上去（重试 4 次之后）" in out and out.count("后重试第") == 4, out
    assert TOKEN not in out


@need_git
def test_run_drops_qbreak_home_and_only_runs_in_the_routine_clone(tmp_path):
    code = "import os; print('HOME=' + str(os.environ.get('QBREAK_HOME')))"
    root = ROOT.parent if (ROOT.parent / ".git").exists() else ROOT
    rc, out = _run(tmp_path, "run", "-c", code, QBREAK_HOME="/somewhere")
    assert rc == 0 and "HOME=None" in out                                                 # 云端 / Linux：照跑，去掉 QBREAK_HOME
    rc, out = _run(tmp_path, "run", "-c", code, uname="Darwin")                           # Mac：这里不是 ~/qbreak-sim → 拒绝
    assert rc == 2 and "不是例行任务的克隆" in out and "HOME=" not in out
    rc, out = _run(tmp_path, "run", "-c", code, uname="Darwin", QBREAK_SIM=str(root), QBREAK_HOME="/x")
    assert rc == 0 and "HOME=None" in out
    rc, out = _run(tmp_path, "run")
    assert rc == 2 and "用法" in out


@need_git
def test_check_reports_everything_read_only_without_values(repos):
    t = repos
    _git(t / "sim", "remote", "set-url", "--push", "origin", f"https://{TOKEN}@127.0.0.1:9/x.git", ident=False)
    _push_cloud(t, _daily("2026-10-09"), "sim: 2026-10-08 日报", "2026-10-09T07:11:00+09:00")
    _git(t / "sim", "pull", "-q", "--ff-only", "origin", BRANCH, ident=False)
    app = t / "Claude.app"
    (app / "Contents").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": "1.1.5400"}))
    tasks = t / "cfg" / "scheduled-tasks"
    (tasks / "qbreak-sim-daily").mkdir(parents=True)
    (tasks / "qbreak-sim-daily" / "SKILL.md").write_text("读 ~/qbreak-sim/quant_breakout/routines/sim_daily.md 照做 SECRET-URL",
                                                         encoding="utf-8")
    b = _bin(t, "Darwin", security=0, pmset="Repeating power events:\n  wakepoweron at 7:30AM weekdays only\n")
    rc, out = _run(t, "check", path_extra=b, QBREAK_CLAUDE_APP=str(app), CLAUDE_CONFIG_DIR=str(t / "cfg"))
    assert rc == 1, out
    for s in ("[OK] 例行任务用的克隆：", "[OK] 当前分支：" + BRANCH, "没有本地改动", "[★] 推不上去（没有推送权限 / 没登录 GitHub）",
              "[OK] git 的 user.name / user.email：都设了", "[OK] Claude 桌面版 1.1.5400", "[OK] 本机任务「日报」：已建（qbreak-sim-daily",
              "[★] 本机任务「影子账户」还没建", "[★] 本机任务「季度复核」还没建", "[OK] 钥匙串里有 qbreak-jquants（只查了有没有）",
              "[★] 工作日自动唤醒：唤醒时间晚于 06:50", "2026-10-09（周五）：日报 云端；影子账户 —", "项要处理"):
        assert s in out, (s, out)
    assert TOKEN not in out and "SECRET-URL" not in out and "t@example.invalid" not in out
    assert all("-w" not in ln.split() for ln in (t / "security.log").read_text(encoding="utf-8").splitlines())   # 只查有没有，不读值
    assert _git(t / "sim", "status", "--porcelain", ident=False) == ""                    # 只读


@need_git
@pytest.mark.skipif(sys.platform == "darwin", reason="真的 macOS 上 PATH 里有 security / pmset，「不是 macOS 就跳过」这几行只在 Linux 上成立")
def test_check_without_the_clone_on_linux_skips_mac_only_items(tmp_path):
    rc, out = _run(tmp_path, "check", repo="none")
    assert rc == 1 and "[★] 没有例行任务用的克隆 " in out
    assert "[—] Claude 桌面版：不是 macOS，跳过" in out and "[—] 钥匙串：没有 security 命令" in out
    assert "[—] 工作日自动唤醒：没有 pmset" in out


# ────────── 本机任务按时跑了没有 / 有没有卡住的运行（桌面版的运行记录；2026-10-16）──────────
def _jst(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).replace(tzinfo=JST)


def _utc_iso(s: str) -> str:
    return _jst(s).astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _ms(s: str) -> int:
    return int(_jst(s).timestamp() * 1000)


DAILY_TASK = {"id": "qbreak-sim-daily", "cronExpression": "32 6 * * 1-5", "enabled": True}
WANT = {"qbreak-sim-daily": "日报", "qbreak-shadow": "影子账户", "qbreak-quarterly": "季度复核"}
SECRET_CMD = "git -C ~/qbreak-sim pull SECRET-CMD"


def _hm(fires) -> list[str]:
    return [x.astimezone(JST).strftime("%m-%d %H:%M") for x in fires]


def test_cron_parse_and_fires():
    mi, hr, dom, mon, dow, dom_star, dow_star = routines.parse_cron("*/15 9 * * 0,7")
    assert mi == {0, 15, 30, 45} and hr == {9} and dow == {0} and dom_star and not dow_star
    assert routines.parse_cron("5/20 * * * 1-5")[0] == {5, 25, 45}
    for bad in ("", "1 2 3 4", "61 * * * *", "* * * * 1-9", "*/0 * * * *"):
        with pytest.raises(ValueError):
            routines.parse_cron(bad)
    f = routines.fires_back("56 9 12 1,4,7,10 *", _jst("2026-10-16 10:00"), JST)
    assert _hm([next(f), next(f)]) == ["10-12 09:56", "07-12 09:56"]
    f = routines.fires_back("32 6 * * 1-5", _jst("2026-10-19 06:32"), JST)               # 到点那一分钟算；周末不算
    assert _hm([next(f), next(f)]) == ["10-19 06:32", "10-16 06:32"]


def test_missed_runs_follow_trading_days_and_the_grace():
    t = {**DAILY_TASK, "lastRunAt": _utc_iso("2026-10-16 06:32:30"), "lastScheduledFor": _utc_iso("2026-10-16 06:32")}   # 周五
    assert routines.missed_runs(t, _jst("2026-10-19 07:00"), JST) == []                  # 周一 07:00：06:32 + 30 分还没过
    assert _hm(routines.missed_runs(t, _jst("2026-10-20 07:00"), JST)) == ["10-19 06:32"]   # 周二 07:00：周一的没跑
    t = {**DAILY_TASK, "lastRunAt": _utc_iso("2026-10-09 06:45:56")}                       # 周五；10-12（周一）スポーツの日 休市
    assert routines.missed_runs(t, _jst("2026-10-13 07:00"), JST) == []                  # 休市日不算、周二的还没到
    assert _hm(routines.missed_runs(t, _jst("2026-10-13 07:05"), JST)) == ["10-13 06:32"]
    t = {**DAILY_TASK, "lastRunAt": _utc_iso("2026-10-12 06:45:56"), "lastScheduledFor": _utc_iso("2026-10-12 06:32")}
    assert _hm(routines.missed_runs(t, _jst("2026-10-16 10:46"), JST)) == ["10-13 06:32", "10-14 06:32", "10-15 06:32", "10-16 06:32"]
    q = {"id": "q", "cronExpression": "56 9 12 1,4,7,10 *", "lastRunAt": _utc_iso("2026-10-12 10:07:58")}
    assert routines.missed_runs(q, _jst("2026-10-16 10:46"), JST) == []
    q["lastRunAt"] = _utc_iso("2026-07-12 10:00")
    assert _hm(routines.missed_runs(q, _jst("2026-10-12 10:30"), JST)) == ["10-12 09:56"]   # 季度复核按 cron 原样（休市日也算）
    assert routines.missed_runs({**DAILY_TASK, "createdAt": _ms("2026-10-15 12:00")}, _jst("2026-10-16 07:00"), JST) == []   # 还没跑过：从建好起算
    assert len(routines.missed_runs({**DAILY_TASK, "createdAt": _ms("2026-10-14 12:00")}, _jst("2026-10-16 08:00"), JST)) == 2
    assert routines.missed_runs({"cronExpression": "bad", "lastRunAt": _utc_iso("2026-10-12 06:45")}, _jst("2026-10-16 10:46"), JST) is None
    assert routines.missed_runs(DAILY_TASK, _jst("2026-10-16 10:46"), JST) is None        # 没有任何时刻可比


def _turn(role: str, ts: str, tool: str | None = None) -> dict:
    content = [{"type": "tool_use", "name": tool, "input": {"command": SECRET_CMD}}] if tool else [{"type": "text", "text": "完了"}]
    if role == "user":
        content = "跑"
    return {"type": role, "message": {"role": role, "content": content}, "timestamp": _utc_iso(ts)}


def _desktop(t: Path, tasks: list, sessions: list = (), transcripts: dict | None = None, skips: dict | None = None) -> tuple[Path, Path]:
    """假的桌面版运行记录：<t>/sessions/<账户>/<组织>/scheduled-tasks.json + local_*.json；对话记录 <t>/cfg/projects/<编码>/<id>.jsonl。"""
    d = t / "sessions" / "acct" / "org"
    d.mkdir(parents=True)
    (d / "scheduled-tasks.json").write_text(json.dumps({"scheduledTasks": tasks, "recordedSkips": skips or {}}), encoding="utf-8")
    for i, s in enumerate(sessions):
        (d / f"local_{i:08d}-0000.json").write_text(json.dumps(s), encoding="utf-8")
    proj = t / "cfg" / "projects" / "-x-qbreak-sim"
    proj.mkdir(parents=True)
    for sid, entries in (transcripts or {}).items():
        (proj / f"{sid}.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n{坏行\n", encoding="utf-8")
    return t / "sessions", t / "cfg" / "projects"


def _session(task: str, created: str, last_s: int = 3, mode: str = "default", sid: str = "", **kw) -> dict:
    return {"scheduledTaskId": task, "createdAt": _ms(created), "lastActivityAt": _ms(created) + last_s * 1000, "isArchived": False,
            "permissionMode": mode, "cliSessionId": sid, "title": task, **kw}


def _stuck_desktop(t: Path) -> tuple[Path, Path]:
    """2026-10-16 的实况：10-12 日报那次停在 Bash 上（对话记录最后是没有结果的工具调用），桌面版之后每分钟记一条 per_task_limit 跳过。"""
    tasks = [{**DAILY_TASK, "lastRunAt": _utc_iso("2026-10-12 06:45:56"), "lastScheduledFor": _utc_iso("2026-10-12 06:32")},
             {"id": "qbreak-shadow", "cronExpression": "45 7 * * 1-5", "enabled": True, "lastRunAt": _utc_iso("2026-10-16 07:47:02")},
             {"id": "qbreak-quarterly", "cronExpression": "56 9 12 1,4,7,10 *", "enabled": True, "lastRunAt": _utc_iso("2026-10-12 10:07:58")}]
    sessions = [
        _session("qbreak-sim-daily", "2026-10-09 06:40:00", sid="old-daily-0000", isArchived=True),   # 归档了的：不看
        _session("qbreak-sim-daily", "2026-10-12 06:45:56", sid="aaaaaaaa-1111"),                    # 卡住（对话记录）
        _session("qbreak-shadow", "2026-10-16 07:47:02", mode="bypassPermissions", sid="bbbbbbbb-2222"),   # 记录像卡住、对话记录已结束
        _session("qbreak-quarterly", "2026-10-12 10:07:58", last_s=5, sid="cccccccc-3333"),          # 没有对话记录：几秒后就没动静
        _session("qbreak-quarterly", "2026-10-10 14:15:53", last_s=80, mode="bypassPermissions", completedTurns=1),
    ]
    tr = {"aaaaaaaa-1111": [_turn("user", "2026-10-12 06:45:57"), _turn("assistant", "2026-10-12 06:45:58", "Bash"),
                            _turn("assistant", "2026-10-12 06:45:59", "Read")],                # 同时发的两个调用各占一条
          "bbbbbbbb-2222": [_turn("user", "2026-10-16 07:47:03"), _turn("assistant", "2026-10-16 07:47:04", "Bash"),
                            _turn("assistant", "2026-10-16 07:58:00")]}
    skips = {"qbreak-sim-daily": [{"at": _ms(f"2026-10-{d} 06:32"), "reason": "per_task_limit"} for d in (13, 14, 15, 16)]
             + [{"at": _ms("2026-10-16 10:46"), "reason": "per_task_limit"}]}
    return _desktop(t, tasks, sessions, tr, skips)


def test_desktop_report_flags_the_stuck_run_missed_runs_and_prompting_mode(tmp_path):
    root, proj = _stuck_desktop(tmp_path)
    rows = routines.desktop_report(root, proj, WANT, _jst("2026-10-16 10:50"), JST)
    text = "\n".join(f"{m}\t{x}" for m, x in rows)
    assert ("NG", "本机任务「日报」最后一次运行 10/12 06:45；之后应该跑的 10/13〜10/16 没跑（4 次；"
                  "错过的没有云端后备：要补在 Mac 对话里说「补跑」）") in rows, text
    stuck = [x for m, x in rows if m == "NG" and "那次一直没动" in x]
    assert len(stuck) == 2, text
    assert stuck[0].startswith("本机任务「日报」10/12 06:45 那次一直没动（停在工具调用（Bash、Read）上、没有结果：多半在等权限确认、没人点允许）"
                               "；之后到点的运行桌面版都跳过了（上一次运行还没结束）"), stuck[0]
    assert "Code → Routines 打开那次运行、停止它" in stuck[0] and "routines/README.md" in stuck[0]
    assert stuck[1].startswith("本机任务「季度复核」10/12 10:07 那次一直没动（开始几秒之后就没有动静"), stuck[1]
    assert ("OK", "本机任务「影子账户」：最后一次运行 10/16 07:47（之后没有错过的）") in rows             # 对话记录已结束：不算卡住
    assert ("OK", "本机任务「季度复核」：最后一次运行 10/12 10:07（之后没有错过的）") in rows
    warn = [x for m, x in rows if m == "WARN"]
    assert len(warn) == 1 and "（日报 10/12 06:45、季度复核 10/12 10:07）" in warn[0] and "影子账户" not in warn[0], warn
    assert "SECRET-CMD" not in text and str(tmp_path) not in text                          # 不打印命令、路径
    # 还没到 2 小时：照常在跑，不算卡住；暂停的任务；只有跳过记录、找不到那次运行
    rows = routines.desktop_report(root, proj, WANT, _jst("2026-10-12 08:00"), JST)
    assert not any("那次一直没动" in x for _, x in rows), rows


def test_a_run_followed_by_a_later_run_is_not_stuck(tmp_path):
    """2026-10-21：10/19 那次在对话里被停掉（对话记录最后照旧是没有结果的工具调用）、10/20 又开始了新的一次 → 旧的那次不再报「一直没动」。"""
    root, proj = _stuck_desktop(tmp_path)
    d = root / "acct" / "org"
    (d / "local_99999999-0000.json").write_text(json.dumps(_session("qbreak-sim-daily", "2026-10-16 10:48:00", sid="dddd-new")), encoding="utf-8")
    (proj / "-x-qbreak-sim" / "dddd-new.jsonl").write_text(json.dumps(_turn("user", "2026-10-16 10:48:01")) + "\n"
                                         + json.dumps(_turn("assistant", "2026-10-16 10:49:00")) + "\n", encoding="utf-8")
    rows = routines.desktop_report(root, proj, WANT, _jst("2026-10-16 13:00"), JST)
    stuck = [x for m, x in rows if m == "NG" and "那次一直没动" in x]
    assert not any("日报" in x for x in stuck) and any("季度复核" in x for x in stuck), stuck


def test_desktop_report_paused_skips_only_and_unreadable_state(tmp_path):
    t1 = tmp_path / "a"
    root, proj = _desktop(t1, [{**DAILY_TASK, "enabled": False, "lastRunAt": _utc_iso("2026-10-12 06:45")}],
                          skips={"qbreak-sim-daily": [{"at": _ms("2026-10-16 10:40"), "reason": "per_task_limit"},
                                                      {"at": _ms("2026-10-13 06:32"), "reason": "per_task_limit"},
                                                      {"at": _ms("2026-10-16 10:41"), "reason": "some_new reason!"}]})
    rows = routines.desktop_report(root, proj, {"qbreak-sim-daily": "日报", "qbreak-shadow": "影子账户"}, _jst("2026-10-16 10:50"), JST)
    assert rows[0][0] == "NG" and "暂停的（Paused）" in rows[0][1]
    assert ("NG", "本机任务「日报」：桌面版从 10/13 06:32 起一直跳过它（上一次运行还没结束） → 在桌面版 Code → Routines 打开还没结束的那次运行、"
                  "停止它；让它不再问：说明书里的命令都要一字不差地在允许规则里（见 routines/README.md）") in rows, rows
    assert ("?", "本机任务「日报」最近被桌面版跳过（原因 some_newreason）：在桌面版 Code → Routines → Review history 看") in rows
    assert rows[-1][0] == "?" and "「影子账户」：桌面版的运行记录里没有它" in rows[-1][1]
    assert not any(m == "WARN" for m, _ in rows)
    # 没有运行记录 / 格式不同 → 只是「?」（check 里是 [—]，不算要处理）
    assert routines.desktop_report(tmp_path / "none", proj, WANT, _jst("2026-10-16 10:50"), JST) == [
        ("?", "没有桌面版的运行记录（scheduled-tasks.json）：跳过「按时跑了没有」（在桌面版 Code → Routines → Review history 看）")]
    bad = tmp_path / "b" / "x" / "y"
    bad.mkdir(parents=True)
    (bad / "scheduled-tasks.json").write_text("[1, 2]", encoding="utf-8")
    rows = routines.desktop_report(tmp_path / "b", proj, WANT, _jst("2026-10-16 10:50"), JST)
    assert len(rows) == 1 and rows[0][0] == "?" and "格式和预期不同" in rows[0][1]


def test_transcript_tail_only_counts_a_call_still_without_its_result(tmp_path):
    proj = tmp_path / "projects"
    (proj / "x").mkdir(parents=True)
    res = {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]},
           "timestamp": _utc_iso("2026-10-12 06:46:10")}
    for sid, entries, want in (
            ("s1-00000001", [_turn("assistant", "2026-10-12 06:46:00", "Bash"), res], False),             # 有结果了
            ("s2-00000002", [_turn("assistant", "2026-10-12 06:46:00", "Bash"), res,
                             _turn("assistant", "2026-10-12 06:46:20", "WebFetch")], True),                # 下一个还没有结果
            ("s3-00000003", [{"type": "summary"}], None)):                                                 # 没有消息
        (proj / "x" / f"{sid}.jsonl").write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
        got = routines._transcript_tail(proj, sid)
        assert (got if got is None else got[0]) is want, (sid, got)
    assert routines._transcript_tail(proj, "s2-00000002")[1] == "WebFetch"
    assert routines._transcript_tail(proj, "../../etc/passwd") is None and routines._transcript_tail(proj, "nope-0000") is None


def test_desktop_cli_reads_now_from_the_env(tmp_path, monkeypatch, capsys):
    import time
    if not hasattr(time, "tzset"):
        pytest.skip("cron 按本机时区算：这里改不了进程的时区")
    root, proj = _stuck_desktop(tmp_path)
    monkeypatch.setenv("QBREAK_ROUTINES_NOW", "2026-10-16T10:50:00+09:00")
    old = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Tokyo"                                                      # 桌面版的 cron 是 Mac 的本机时间（JST）
    time.tzset()
    try:
        assert routines.main(["desktop", str(root), str(proj), "qbreak-sim-daily=日报\nqbreak-shadow=影子账户"]) == 0
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()
    out = capsys.readouterr().out
    assert "NG\t本机任务「日报」最后一次运行 10/12 06:45；之后应该跑的 10/13〜10/16 没跑" in out, out
    assert "OK\t本机任务「影子账户」" in out and "季度复核" not in out


def _skills(t: Path):
    for name, md in (("qbreak-sim-daily", "sim_daily"), ("qbreak-shadow", "shadow"), ("qbreak-quarterly", "quarterly")):
        (t / "cfg" / "scheduled-tasks" / name).mkdir(parents=True, exist_ok=True)
        (t / "cfg" / "scheduled-tasks" / name / "SKILL.md").write_text(f"读 ~/qbreak-sim/quant_breakout/routines/{md}.md 照做",
                                                                     encoding="utf-8")


@need_git
def test_check_flags_stuck_local_tasks_and_reads_the_newest_clone(repos):
    """2026-10-16 的情形：本机任务卡在 10-12、~/qbreak-sim 没人 fetch → 以前「全部 [OK]」、表里全是「—」。"""
    t = repos
    _push_cloud(t, _daily("2026-10-16"), "sim: 2026-10-15 日报（无下单）", "2026-10-16T07:21:00+09:00")
    _push_cloud(t, {"quant_breakout/var/out/shadow_today.json": "{}"}, "shadow: 2026-10-16 判断", "2026-10-16T08:06:00+09:00")
    _git(t, "clone", "-q", "-b", BRANCH, str(t / "remote.git"), "src", ident=False)       # ~/qbreak-src：每天 07:40 拉，远端记录最新
    _stuck_desktop(t)
    _skills(t)
    b = _bin(t, "Darwin", security=0, pmset="Repeating power events:\n  wakepoweron at 6:40AM weekdays only\n")
    env = dict(path_extra=b, today="2026-10-16", CLAUDE_CONFIG_DIR=str(t / "cfg"), QBREAK_DESKTOP_DIR=str(t / "sessions"),
               QBREAK_ROUTINES_NOW="2026-10-16T10:50:00+09:00", TZ="Asia/Tokyo", QBREAK_CLAUDE_APP=str(t / "nope.app"))
    rc, out = _run(t, "check", **env)
    assert rc == 1, out
    for s in ("[★] 本机任务「日报」最后一次运行 10/12 06:45；之后应该跑的 10/13〜10/16 没跑（4 次",
              "[★] 本机任务「日报」10/12 06:45 那次一直没动（停在工具调用（Bash、Read）上",
              "[OK] 本机任务「影子账户」：最后一次运行 10/16 07:47",
              "[!] 本机任务最近一次运行用的是要确认的权限模式",
              "最近 5 个工作日（看 ~/src 上次拉到的远端记录（三个克隆里最新的：远端最后一个提交 10/16 08:06 JST",
              "2026-10-16（周五）：日报 云端；影子账户 云端", "条 [!] 提醒）"):
        assert s in out, (s, out)
    assert "全部 [OK]" not in out and "SECRET-CMD" not in out and str(t) not in out
    rc, out = _run(t, "check", **{**env, "QBREAK_DESKTOP_DIR": str(t / "nowhere")})        # 读不到运行记录：跳过、不算要处理
    assert "[—] 本机任务按时跑了没有：没有桌面版的运行记录目录 ~/nowhere，跳过" in out, out
    assert "那次一直没动" not in out
    assert _git(t / "sim", "status", "--porcelain", ident=False) == ""                    # 只读
    assert _git(t / "sim", "rev-parse", f"origin/{BRANCH}", ident=False) != _git(t / "src", "rev-parse", f"origin/{BRANCH}", ident=False)   # 没 fetch


# ────────── 09:30 自检的推送里的「本机例行任务」（2026-10-16）──────────
_REAL_ROUTINE_LINES = watchdog._routine_lines          # 收集测试时（conftest 把它换成「没有」之前）
TUE_1020 = "2026-10-20"                                 # 周二（交易日）


def _today_tasks(t: Path, daily: dict, shadow: dict, sessions=(), transcripts=None, skips=None):
    tasks = [{**DAILY_TASK, **daily}, {"id": "qbreak-shadow", "cronExpression": "45 7 * * 1-5", "enabled": True, **shadow},
             {"id": "qbreak-quarterly", "cronExpression": "56 9 12 1,4,7,10 *", "enabled": True,
              "lastRunAt": _utc_iso("2026-10-12 10:07:58")}]
    root, _ = _desktop(t, tasks, sessions, transcripts, skips)
    _skills(t)
    return root


def _lines(t: Path, root: Path, now: str) -> list[str]:
    return routines.today_lines(_jst(now), root=root, cfg=t / "cfg", tz=JST)


def test_today_lines_stuck_runs_say_where_and_what_to_do(tmp_path):
    """10-16 的实况在下一个交易日 09:30：日报 10/12 起卡住、季度复核那次开始几秒就停 → 各一行（停止它）；影子账户正常 → 不说。"""
    root, _ = _stuck_desktop(tmp_path)
    _skills(tmp_path)
    got = routines.today_lines(_jst("2026-10-16 09:30"), root=root, cfg=tmp_path / "cfg", tz=JST)
    assert got == [
        "本机例行任务：日报卡住了（多半在等权限确认；10/12 06:45 起）→ 在桌面版 Code → Routines 打开那次运行、停止它"
        "（不停止，之后到点也不会再跑）；今天的要补：在 Mac 对话里说「补跑」；在 Mac 对话里问「例行任务今天跑了吗」",
        "本机例行任务：季度复核卡住了（多半在等权限确认；10/12 10:07 起）→ 在桌面版 Code → Routines 打开那次运行、停止它"
        "（不停止，之后到点也不会再跑）；今天的要补：在 Mac 对话里说「补跑」；在 Mac 对话里问「例行任务今天跑了吗」"], got
    assert not any("SECRET-CMD" in x or str(tmp_path) in x for x in got)
    # 今天开始的那次卡在工具调用上（2 小时以上）→ 点允许（或停止）
    t2 = tmp_path / "today"
    root = _today_tasks(t2, {"lastRunAt": _utc_iso(f"{TUE_1020} 06:33:10"), "lastScheduledFor": _utc_iso(f"{TUE_1020} 06:32")},
                        {"lastRunAt": _utc_iso(f"{TUE_1020} 07:46:00"), "lastScheduledFor": _utc_iso(f"{TUE_1020} 07:45")},
                        [_session("qbreak-sim-daily", f"{TUE_1020} 06:33:10", sid="dddddddd-4444")],
                        {"dddddddd-4444": [_turn("user", f"{TUE_1020} 06:33:11"), _turn("assistant", f"{TUE_1020} 06:33:12", "Bash")]})
    assert _lines(t2, root, f"{TUE_1020} 08:00") == []                                    # 还不到 2 小时：照常在跑
    got = _lines(t2, root, f"{TUE_1020} 09:30")
    assert got == ["本机例行任务：日报卡住了（多半在等权限确认；10/20 06:33 起）→ 在桌面版 Code → Routines 打开那次运行点允许（或停止它）"
                   "；今天的要补：在 Mac 对话里说「补跑」；在 Mac 对话里问「例行任务今天跑了吗」"], got


def test_today_lines_missed_and_late_runs_only_on_trading_days(tmp_path):
    root = _today_tasks(tmp_path, {"lastRunAt": _utc_iso("2026-10-19 06:33"), "lastScheduledFor": _utc_iso("2026-10-19 06:32")},
                        {"lastRunAt": _utc_iso(f"{TUE_1020} 08:20"), "lastScheduledFor": _utc_iso(f"{TUE_1020} 07:45")})
    got = _lines(tmp_path, root, f"{TUE_1020} 09:30")
    assert got == ["本机例行任务：日报今天 06:32 没跑（桌面版没开 / Mac 睡着？）→ 今天的要补：在 Mac 对话里说「补跑」；在 Mac 对话里问「例行任务今天跑了吗」",
                   "本机例行任务：影子账户今天 08:20 才开始（应在 07:45：那时 Mac 睡着 / 桌面版没开 / 前一次运行还没结束？）"
                   "→ 那之前执行器用的是旧的输入；在 Mac 对话里问「例行任务今天跑了吗」"], got
    assert _lines(tmp_path, root, f"{TUE_1020} 06:55") == []                               # 到点 + 30 分钟还没过
    assert len(_lines(tmp_path, root, f"{TUE_1020} 07:05")) == 1                            # 日报过了 30 分钟；影子账户还没到点
    assert _lines(tmp_path, root, "2026-10-12 09:30") == []                                # 休市的工作日（スポーツの日）：不该跑
    # 准时的 / 晚不到 30 分钟（Mac 06:50 才醒、补跑）→ 不说；暂停的不说（check 里报）
    t2 = tmp_path / "ok"
    root = _today_tasks(t2, {"lastRunAt": _utc_iso(f"{TUE_1020} 06:55"), "lastScheduledFor": _utc_iso(f"{TUE_1020} 06:32")},
                        {"enabled": False, "lastRunAt": _utc_iso("2026-10-12 07:45")})
    assert _lines(t2, root, f"{TUE_1020} 09:30") == []


def test_today_lines_never_raise_and_stay_quiet_without_records(tmp_path, monkeypatch):
    assert routines.today_lines(_jst(f"{TUE_1020} 09:30"), root=tmp_path / "none", cfg=tmp_path / "cfg") == []   # 没有任务目录
    _skills(tmp_path)
    assert routines.today_lines(_jst(f"{TUE_1020} 09:30"), root=tmp_path / "none", cfg=tmp_path / "cfg") == []   # 没有运行记录
    bad = tmp_path / "bad" / "a" / "b"
    bad.mkdir(parents=True)
    (bad / "scheduled-tasks.json").write_text('{"scheduledTasks": [{"id": "qbreak-sim-daily", "cronExpression": 5}]}', encoding="utf-8")
    assert routines.today_lines(_jst(f"{TUE_1020} 09:30"), root=tmp_path / "bad", cfg=tmp_path / "cfg") == []   # 读不懂的 cron
    monkeypatch.delenv("QBREAK_DESKTOP_DIR", raising=False)
    monkeypatch.setattr(routines.sys, "platform", "linux")
    assert routines.desktop_dir() is None and routines.today_lines(_jst(f"{TUE_1020} 09:30")) == []   # 不是 Mac：不看
    monkeypatch.setattr(routines, "today_lines", lambda now: 1 / 0)                         # 出错 → 自检照常（什么都不说）
    assert _REAL_ROUTINE_LINES(_jst(f"{TUE_1020} 09:30")) == []
    monkeypatch.setattr(routines, "today_lines", lambda now: ["本机例行任务：日报今天 06:32 没跑"])
    assert _REAL_ROUTINE_LINES(_jst(f"{TUE_1020} 09:30")) == ["本机例行任务：日报今天 06:32 没跑"]


def test_watchdog_push_carries_the_routine_line_without_failing_or_repushing(tmp_path, monkeypatch):
    """通过：标题加「· ★ 本机例行任务」、正文加一行，结论照旧通过（rc 0）；同一天再自检不为它再推；没通过：附在原因后面。"""
    line = "本机例行任务：日报卡住了（多半在等权限确认；10/05 06:32 起）→ 在桌面版 Code → Routines 打开那次运行点允许（或停止它）"
    monkeypatch.setattr(watchdog, "_routine_lines", lambda now: [line])
    _wd_env("2026-10-06")
    agents = tmp_path / "ag"
    agents.mkdir()
    (agents / f"{watchdog.PAPER_PLIST}.plist").write_text("x", encoding="utf-8")
    sent, out = [], []

    def run(now):
        sent.clear()
        out.clear()
        return watchdog.run(agents, now, send=lambda t, x, lv="info", resend=False: sent.append((t, x, lv)) or {"push": True},
                            beat=lambda ok, m="": None, mac=lambda *a: True, out=out.append, sleep=lambda s: None)
    assert run(TUE) == 0
    assert sent == [("qbreak 模拟操盘 ✓ 09:30 自检通过 · ★ 本机例行任务",
                     f"决策 2026-10-05 处理完；今天没有单。\n★ {line}\n{watchdog.DAILY_LINE}", "info")], sent
    wd = json.loads(watchdog.path("paper").read_text(encoding="utf-8"))
    assert wd["ok"] is True and wd["reasons"] == [] and wd["routines"] == [line]
    assert run(TUE.replace(hour=10, minute=5)) == 0 and sent == [] and "今天已经推过" in out[0]   # 同一天只推一次
    assert watchdog.run(agents, TUE, dry=True, out=out.append) == 0 and f"- ★ {line}（不算没通过）" in out[-1]
    _wd_env("2026-10-05")                                                                  # 日报没入库：没通过（每次推）+ 附上那一行
    assert run(TUE.replace(hour=10, minute=10)) == 1
    assert sent[0][0] == "qbreak 模拟操盘 ★ 10:10 自检没通过" and sent[0][2] == "warn"
    assert sent[0][1].startswith(f"- {watchdog.DAILY_REASON}") and sent[0][1].endswith(f"\n- ★ {line}")
    monkeypatch.setattr(watchdog, "_routine_lines", lambda now: [])                        # 没问题：文件里也不写
    _wd_env("2026-10-06")
    run(TUE.replace(hour=10, minute=20))
    assert "routines" not in json.loads(watchdog.path("paper").read_text(encoding="utf-8"))


# ────────── 说明书的命令在不在允许规则里（2026-10-16）──────────
def test_rule_matching_follows_claude_code_semantics():
    m = routines.rule_matches
    assert m("bash scripts/routines.sh push", "bash scripts/routines.sh push")
    assert not m("bash scripts/routines.sh push", "bash scripts/routines.sh push; echo rc=$?")
    assert m("bash scripts/routines.sh done-today:*", "bash scripts/routines.sh done-today sim")
    assert m("bash scripts/routines.sh done-today:*", "bash scripts/routines.sh done-today")
    assert not m("bash scripts/routines.sh done-today:*", "bash scripts/routines.sh done-todayx")
    assert m("git commit -m *", 'git commit -m "sim(mac): 2026-10-16 日报"') and m("TZ=Asia/Tokyo date *", "TZ=Asia/Tokyo date")
    assert m("git add quant_breakout/var/*", "git add quant_breakout/var/out/a.* quant_breakout/var/b.json")
    assert not m("git add quant_breakout/var/*", "git add quant_breakout/var/x && git push")   # 前缀规则不放行连起来的命令
    loop = 'until bash scripts/routines.sh done-today sim >/dev/null 2>&1 || [ "$(TZ=Asia/Tokyo date +%H%M)" -ge 0840 ]; do sleep 120; done'
    assert m(loop, loop) and not m("until *", loop)
    assert routines.split_top("cd ~/qbreak-sim && a 2>&1 | b || c; d") == ["cd ~/qbreak-sim", "a 2>&1", "b", "c", "d"]
    assert routines.split_top('a "x && y" && b $(c; d)') == ['a "x && y"', "b $(c; d)"]
    assert routines.missing_parts('cd ~/qbreak-sim && git add quant_breakout/var && git commit -m "sim(mac): <日期> 日报"',
                                  ["git add quant_breakout/var", "git commit -m *"]) == []
    assert routines.missing_parts('cd ~/qbreak-sim && git add quant_breakout/var && git commit -m "sim(mac): <日期> 日报"',
                                  ["git add quant_breakout/var", 'git commit -m "sim(mac): 2026-10-16 日报"']) == [
        'git commit -m "sim(mac): <日期> 日报"']                                       # 占位的地方规则里要有 *
    assert routines.missing_parts(f"cd ~/qbreak-sim/quant_breakout && {loop}", [loop]) == []
    assert routines.missing_parts("cd /tmp && bash x", ["bash x"]) == ["cd /tmp"]           # 只有 ~/qbreak-sim 里的 cd 不用规则
    assert routines.missing_parts("anything at all", ["*"]) == []                            # 规则「Bash」= 全部
    assert routines.suggest_rule('git commit -m "sim(mac): <最新 bar_date> 日报"') == "Bash(git commit -m *)"
    assert routines.suggest_rule("bash scripts/routines.sh push") == "Bash(bash scripts/routines.sh push)"


def test_manual_commands_are_the_ones_to_run_not_the_mentions():
    cmds = routines.manual_commands()
    assert set(cmds) == {"sim_daily", "shadow", "quarterly"}
    first = f"git -C ~/qbreak-sim pull -q --ff-only origin {BRANCH}"                        # README 固定文字的第 1 步
    assert all(c[0] == first for c in cmds.values())
    assert "cd ~/qbreak-sim/quant_breakout && bash scripts/routines.sh done-today sim" in cmds["sim_daily"]
    assert "bash scripts/routines.sh run run.py sim-day" in cmds["sim_daily"]
    assert any(c.startswith("cd ~/qbreak-sim/quant_breakout && until bash scripts/routines.sh done-today sim") for c in cmds["shadow"])
    assert any(c.startswith('git commit -m "季度复核(mac)：') for c in cmds["quarterly"])      # 「&& git commit …」另起的一段
    assert "bash scripts/with_jquants.sh bash scripts/routines.sh run scripts/w2_forward_all.py --review" in cmds["quarterly"]
    every = [c for v in cmds.values() for c in v]
    for mention in ("bash scripts/routines.sh run <参数>", "bash scripts/routines.sh run X", "git reset", "git pull --ff-only",
                    "git push --force", "bash scripts/with_jquants.sh bash scripts/routines.sh run X"):
        assert mention not in every, mention


def _settings(t: Path, rules: list) -> Path:
    p = t / "sim" / ".claude" / "settings.local.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"permissions": {"allow": rules + ["Read(//SECRET-RULE/**)", "Edit(~/x)"]}, "env": {"K": "SECRET-VAL"}}),
                 encoding="utf-8")
    return p


def test_allow_missing_round_trip_and_per_task_approvals(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QBREAK_DESKTOP_DIR", str(tmp_path / "no-desktop"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-cfg"))
    monkeypatch.setenv("QBREAK_SIM_SETTINGS", str(tmp_path / "nope.json"))
    assert routines.main(["allow-missing"]) == 1 and capsys.readouterr().out.strip() == "[]"        # 没有规则文件
    assert routines.main(["allow-check"]) == 0 and capsys.readouterr().out.startswith("?\t允许规则：没有")
    p = _settings(tmp_path, [])
    monkeypatch.setenv("QBREAK_SIM_SETTINGS", str(p))
    assert routines.main(["allow-missing"]) == 0
    want = json.loads(capsys.readouterr().out)
    assert "Bash(git commit -m *)" in want and "Bash(bash scripts/routines.sh done-today sim)" in want
    assert not any(r.startswith("Bash(cd ") for r in want)                                  # cd 进 ~/qbreak-sim 不用规则
    assert any(r.startswith("Bash(until bash scripts/routines.sh done-today sim") for r in want)   # 循环整条一个规则
    _settings(tmp_path, want)                             # 照它加上 → 全都对得上
    assert routines.main(["allow-missing"]) == 0 and json.loads(capsys.readouterr().out) == []
    assert routines.main(["allow-check"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("OK\t允许规则：说明书要运行的命令（") and "SECRET" not in out
    # 少两条：只打印少的命令（不打印规则文件的别的内容）；任务自己允许过的（桌面版 approvedPermissions）只算那个任务
    echo = "Bash(echo ~/qbreak-sim/quant_breakout/var/out/report.html)"
    _settings(tmp_path, [r for r in want if r not in (echo, "Bash(bash scripts/routines.sh push)")])
    assert routines.main(["allow-check"]) == 0
    out = capsys.readouterr().out
    assert "NG\t允许规则里没有（日报；无人值守时会停在权限确认）：echo ~/qbreak-sim/quant_breakout/var/out/report.html" in out, out
    assert "NG\t允许规则里没有（日报、影子账户、季度复核；无人值守时会停在权限确认）：bash scripts/routines.sh push" in out, out
    assert out.count("NG\t") == 2 and "HINT\t→ 加规则" in out and "SECRET" not in out
    tasks = [{**DAILY_TASK, "approvedPermissions": [{"toolName": "Bash", "ruleContent": "bash scripts/routines.sh push"},
                                                    {"toolName": "Read", "ruleContent": "//x"}]}]
    _desktop(tmp_path, tasks)
    _skills(tmp_path)
    monkeypatch.setenv("QBREAK_DESKTOP_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    assert routines.main(["allow-check"]) == 0
    out = capsys.readouterr().out
    assert "（影子账户、季度复核；无人值守时会停在权限确认）：bash scripts/routines.sh push" in out, out
    assert routines.main(["allow-missing"]) == 0
    assert json.loads(capsys.readouterr().out) == [echo, "Bash(bash scripts/routines.sh push)"]


@need_git
def test_check_reports_commands_missing_from_the_allow_rules(repos):
    t = repos
    _git(t / "sim", "pull", "-q", "--ff-only", "origin", BRANCH, ident=False)
    allp = _settings(t / "x", [])
    env = dict(today="2026-10-16", CLAUDE_CONFIG_DIR=str(t / "cfg"), QBREAK_DESKTOP_DIR=str(t / "nowhere"), QBREAK_SIM_SETTINGS=str(allp))
    rc, out = _run(t, "check", **env)
    assert rc == 1 and "[★] 允许规则里没有（日报、影子账户、季度复核；无人值守时会停在权限确认）：bash scripts/routines.sh push" in out, out
    assert "     → 加规则：在 Mac 对话里说「把例行任务缺的允许规则加上」" in out and "SECRET" not in out
    r = subprocess.run([sys.executable, "-m", "qbreak.routines", "allow-missing"], cwd=ROOT, capture_output=True, text=True,
                       env={**os.environ, **env})
    _settings(t / "x", json.loads(r.stdout))
    rc, out = _run(t, "check", **env)
    assert "[OK] 允许规则：说明书要运行的命令（" in out and "允许规则里没有" not in out, out
    rc, out = _run(t, "check", **{**env, "QBREAK_SIM_SETTINGS": str(t / "none.json")})
    assert "[—] 允许规则：没有 ~/qbreak-sim/.claude/settings.local.json（允许规则）" in out, out


def test_allow_gaps_are_ok_when_the_sim_folder_skips_all_prompts(repos):
    """用户 2026-10-17 决定本机任务保持「跳过全部确认」：规则缺的不再报 [★]（不会停在权限确认），只说改回逐项确认前要补。"""
    t = repos
    _git(t / "sim", "pull", "-q", "--ff-only", "origin", BRANCH, ident=False)
    allp = _settings(t / "x", [])
    conf = t / "desk.json"

    def mode(m):
        conf.write_text(json.dumps({"preferences": {"epitaxyPrefs": {"epitaxy-folder-permission-mode.acct": {
            str(t / "other"): "default", str(t / "sim"): m}}}}), encoding="utf-8")

    env = dict(today="2026-10-16", CLAUDE_CONFIG_DIR=str(t / "cfg"), QBREAK_DESKTOP_DIR=str(t / "nowhere"),
               QBREAK_SIM_SETTINGS=str(allp), QBREAK_DESKTOP_CONFIG=str(conf))
    mode("bypassPermissions")
    rc, out = _run(t, "check", **env)
    assert "允许规则里没有" not in out and "[OK] 允许规则：本机任务的文件夹是「跳过全部确认」" in out and "SECRET" not in out, out
    assert str(t) not in out.split("允许规则：", 1)[1].splitlines()[0]                  # 不打印文件夹路径
    mode("default")
    rc, out = _run(t, "check", **env)
    assert "[★] 允许规则里没有" in out, out
    conf.write_text("{broken", encoding="utf-8")                                         # 读不懂 → 当成要确认（照旧报）
    rc, out = _run(t, "check", **env)
    assert "[★] 允许规则里没有" in out, out


# ────────── 09:30 自检：今天的日报没入库 ──────────
TUE = dt.datetime(2026, 10, 6, 9, 30, tzinfo=JST)


def _wd_env(daily_date: str | None, sim: dict | None = None):
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps({"state": {"last_date": "2026-10-05"}, "orders": []}),
                                                               encoding="utf-8")
    (paths.home() / "sim.json").write_text(json.dumps(sim or {"start": "2026-09-28", "end": "2026-12-24"}), encoding="utf-8")
    if daily_date is not None:
        watchdog.DAILY_FILE.parent.mkdir(parents=True, exist_ok=True)
        watchdog.DAILY_FILE.write_text(json.dumps({"date": daily_date}), encoding="utf-8")


def test_watchdog_flags_a_missing_daily_report():
    _wd_env("2026-10-05")
    r = watchdog.evaluate("paper", TUE)
    assert r["ok"] is False and r["reasons"][-1].startswith(watchdog.DAILY_REASON) and "最新的是 2026-10-05" in r["reasons"][-1]
    r = watchdog.evaluate("tachibana", TUE)                                               # 立花本番也看（执行器用的是它）
    assert any(x.startswith(watchdog.DAILY_REASON) for x in r["reasons"])
    _wd_env("2026-10-06")
    r = watchdog.evaluate("paper", TUE)
    assert r["ok"] is True and r["reasons"] == []


def test_watchdog_says_when_the_daily_is_upstream_but_not_pulled(monkeypatch):
    """远端（@{u}）已经有今天的日报、~/qbreak-src 的工作区没有（git pull 失败 / 入库晚于 08:35）→ 不怪例行任务（R-7）。"""
    import subprocess as sp
    _wd_env("2026-10-05")
    monkeypatch.setattr(watchdog, "_remote_daily_date", lambda run=None: "2026-10-06")
    r = watchdog.evaluate("paper", TUE)
    assert r["ok"] is False and r["reasons"][-1].startswith(watchdog.DAILY_UNPULLED) and "dev.sh check" in r["reasons"][-1]
    assert not any(x.startswith(watchdog.DAILY_REASON) for x in r["reasons"])
    monkeypatch.setattr(watchdog, "_remote_daily_date", lambda run=None: "2026-10-05")   # 远端也没有：照旧是例行任务没跑
    assert watchdog.evaluate("paper", TUE)["reasons"][-1].startswith(watchdog.DAILY_REASON)
    seen = []

    def run(args, **kw):
        seen.append(args)
        return sp.CompletedProcess(args, 0, json.dumps({"date": "2026-10-06"}), "")
    real = _REAL_REMOTE_DAILY                                                              # conftest 换掉之前的那个
    assert real(run=run) == "2026-10-06" and seen[0][:2] == ["git", "-C"] and seen[0][-1] == "@{u}:./var/out/unified_today.json"
    assert real(run=lambda a, **k: sp.CompletedProcess(a, 128, "", "fatal")) is None


def test_watchdog_daily_check_is_quiet_outside_the_sim_period_holidays_and_without_the_file(tmp_path):
    _wd_env(None)                                                                   # 文件不在（不是仓库的克隆）
    assert watchdog.evaluate("paper", TUE)["reasons"] == []
    _wd_env("2026-10-01", sim={"start": "2026-10-13"})                              # 模拟期开始前（立花也不报这一条）
    assert not any(x.startswith(watchdog.DAILY_REASON) for x in watchdog.evaluate("tachibana", TUE)["reasons"])
    _wd_env("2026-10-01", sim={"start": "2026-09-28", "end": "2026-10-02"})         # 模拟期结束后
    assert watchdog.evaluate("paper", TUE)["reasons"] == []
    _wd_env("2026-10-09")
    r = watchdog.evaluate("paper", dt.datetime(2026, 10, 12, 9, 30, tzinfo=JST))          # 休市
    assert r["ok"] is True and r["reasons"] == [] and "休市" in r["note"]
    (paths.home() / "sim.json").unlink()                                                  # 数据目录没有 sim.json → 读仓库的 var/sim.json
    (watchdog.DAILY_FILE.parent.parent / "sim.json").write_text(json.dumps({"start": "2026-10-13"}), encoding="utf-8")
    assert not any(x.startswith(watchdog.DAILY_REASON) for x in watchdog.evaluate("tachibana", TUE)["reasons"])


def test_watchdog_run_sends_the_daily_reason(tmp_path):
    _wd_env("2026-10-05")
    agents = tmp_path / "ag"
    agents.mkdir()
    (agents / f"{watchdog.PAPER_PLIST}.plist").write_text("x", encoding="utf-8")
    sent, beats = [], []
    rc = watchdog.run(agents, TUE, send=lambda t, x, lv="info": sent.append((t, x)) or {}, beat=lambda ok, m="": beats.append(ok),
                      mac=lambda *a: True, out=lambda *a: None)
    assert rc == 1 and beats == [False] and "今天的模拟盘日报没入库（Mac 的本机例行任务没跑？桌面版开着吗？）" in sent[0][1]


# ────────── 说明书与文档：路径、命令都在 ──────────
MDS = ["README.md", "sim_daily.md", "shadow.md", "quarterly.md"]


def _md(name: str) -> str:
    return (ROOT / "routines" / name).read_text(encoding="utf-8")


def test_routine_docs_reference_existing_scripts_and_valid_subcommands():
    subs = {"done-today", "check", "run", "deps", "push"}
    for name in MDS:
        text = _md(name)
        for rel in set(re.findall(r"\b(scripts/[\w./-]+\.(?:py|sh)|tests/[\w./-]+\.py|run\.py)", text)):
            assert (ROOT / rel).exists(), (name, rel)
        for sub in re.findall(r"routines\.sh ([\w-]+)", text):
            assert sub in subs, (name, sub)
        for kind in re.findall(r"done-today (\w+)", text):
            assert kind in ("sim", "shadow", "quarterly"), (name, kind)
        assert "/home/user/public" not in text and "pip install -" not in text, name   # Mac 的路径；依赖经 routines.sh deps
        assert "7yUZBHV5FjcL4EV6HFEPMK" not in text, name                            # 市场风险报告的链接不入库
        assert not re.search(r"(?m)^\s*\d+\w?\.\s.*`python ", text), name              # Python 一律经 routines.sh run（去掉 QBREAK_HOME）
    for name, kind in (("sim_daily.md", "sim"), ("shadow.md", "shadow"), ("quarterly.md", "quarterly")):
        text = _md(name)
        assert f"bash scripts/routines.sh done-today {kind}" in text and "bash scripts/routines.sh push" in text
        assert f"routines/{name}" in _md("README.md")                                  # 固定说明文字指向它（routines.sh check 据此找本机任务）
    assert 'git commit -m "sim(mac): ' in _md("sim_daily.md") and 'git commit -m "shadow(mac): ' in _md("shadow.md")
    assert 'git commit -m "季度复核(mac)：' in _md("quarterly.md")
    q = _md("quarterly.md")
    for step in ("w2_forward_all.py --review", "era_outlook.py", "data_audit.py --warm"):     # 要 J-Quants キー的步骤经 with_jquants.sh
        assert f"bash scripts/with_jquants.sh bash scripts/routines.sh run scripts/{step}" in q, step


def test_routines_are_wired_into_setup_and_docs():
    setup = (ROOT / "scripts" / "mac_setup.sh").read_text(encoding="utf-8")
    assert 'SIM="${QBREAK_SIM:-$HOME/qbreak-sim}"' in setup and "routines.sh\\\" check" in setup
    from qbreak import live_gate
    assert live_gate.WAKE_CMD.endswith("MTWRF 06:40:00") and routines.WAKE_CMD == live_gate.WAKE_CMD
    assert live_gate._wake("Repeating power events:\n  wakepoweron at 7:30AM weekdays only\n")[0] is True   # gate 的判断照旧 ≤ 07:40
    assert "MTWRF 06:40:00" in (ROOT / "scripts" / "install_launchd_live_u.sh").read_text(encoding="utf-8")
    claude = (ROOT.parent / "CLAUDE.md")
    if claude.exists():
        c = claude.read_text(encoding="utf-8")
        assert "~/qbreak-sim" in c and "routines.sh check" in c and "MTWRF 06:40:00" in c
    for doc in ("HANDOFF.md", "MACOS.md"):
        d = (ROOT / doc).read_text(encoding="utf-8")
        assert "routines.sh check" in d and "MTWRF 07:30:00" not in d, doc


@need_git
def test_mac_setup_creates_and_fast_forwards_the_routine_clone(repos):
    """mac_setup.sh ⑤c：没有 → git clone；干净 → 快进；工作日 06:40〜09:05 → 不动；有本地改动 → 不动（其余步骤用假的 Python / launchctl）。"""
    t = repos
    shutil.rmtree(t / "sim")
    b = t / "bin2"
    b.mkdir()
    for n, body in {"launchctl": "#!/bin/sh\nexit 0\n", "fakepy": "#!/bin/sh\nexit 1\n"}.items():
        (b / n).write_text(body, encoding="utf-8")
        (b / n).chmod(0o755)
    agents = t / "agents"
    agents.mkdir()
    (agents / "com.qbreak.liveu.paper.plist").write_text("x", encoding="utf-8")

    def setup(clock):
        env = {**_base_env(t), "PATH": f"{b}{os.pathsep}{os.environ['PATH']}", "QBREAK_PYTHON": str(b / "fakepy"),
               "QBREAK_LIVEU_HOME": str(t / "lh"), "QBREAK_LAUNCH_AGENTS": str(agents), "QBREAK_SKIP_VENV": "1",
               "QBREAK_WATCHDOG_WAIT": "0", "QBREAK_REPO": str(t / "remote.git"), "QBREAK_SIM": str(t / "sim"),
               "QBREAK_DEV": str(t / "dev"), "QBREAK_SIM_CLOCK": clock}
        r = subprocess.run(["bash", str(ROOT / "scripts" / "mac_setup.sh")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        return r.stdout + r.stderr

    out = setup("6 1200")
    assert "⑤c 已建本机例行任务用的克隆 " in out and (t / "sim" / ".git").exists(), out
    assert "unbound variable" not in out and "routines.sh\" check" in out
    _push_cloud(t, _daily("2026-10-09"), "sim: 2026-10-08 日报", "2026-10-09T07:11:00+09:00")
    out = setup("1 0700")
    assert "工作日 06:40〜09:05 是本机例行任务的时段，不动" in out
    out = setup("1 1000")
    assert "⑤c " in out and "（本机例行任务用）已更新到最新" in out
    assert json.loads((t / "sim" / DAILY).read_text(encoding="utf-8"))["date"] == "2026-10-09"
    (t / "sim" / DAILY).write_text("改了\n", encoding="utf-8")
    out = setup("6 1200")
    assert "有未提交的改动：不动" in out and (t / "sim" / DAILY).read_text(encoding="utf-8") == "改了\n"


# ────────── macOS 自带 bash 3.2 的坑：在 ISO-8859-1 locale 下真的跑一遍（同 test_shell_scripts.py）──────────
@pytest.fixture(scope="module")
def latin1(tmp_path_factory):
    if not sys.platform.startswith("linux") or not shutil.which("localedef") or not shutil.which("bash"):
        pytest.skip("需要 Linux + localedef + bash")
    loc = tmp_path_factory.mktemp("loc")
    subprocess.run(["localedef", "-i", "en_US", "-f", "ISO-8859-1", str(loc / "en_US.ISO-8859-1")], capture_output=True)
    if not (loc / "en_US.ISO-8859-1").is_dir():
        pytest.skip("en_US.ISO-8859-1 编不出来")
    r = subprocess.run(["bash", "-uc", 'X=1; echo "$X（"'], env={**os.environ, "LOCPATH": str(loc), "LC_ALL": "en_US.ISO-8859-1"},
                       capture_output=True)
    if b"unbound variable" not in r.stderr:
        pytest.skip("这台机器的 glibc 在 ISO-8859-1 下没有复现 macOS 的行为")
    return loc


@need_git
def test_routines_sh_prints_chinese_after_variables_without_dying(repos, latin1):
    t = repos
    extra = {"LOCPATH": str(latin1), "LC_ALL": "en_US.ISO-8859-1", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    for args, kw in ((["done-today", "sim"], {}), (["done-today", "shadow"], {}), (["done-today", "sim"], {"today": "2026-10-12"}),
                     (["check"], {}), (["push"], {}), (["run"], {}), (["run", "-c", "1"], {"uname": "Darwin"}), ([], {})):
        rc, out = _run(t, *args, **kw, **extra)
        assert "unbound variable" not in out, (args, out)


def _fail_first_pull(t: Path) -> Path:
    """假的 git：第一次 pull 失败（网络 / .git 锁），之后照真的 git。"""
    b = _bin(t)
    real_git = shutil.which("git")
    (b / "git").write_text(f'#!/bin/sh\nfor a in "$@"; do\n  if [ "$a" = pull ] && [ ! -f "{t}/pulled" ]; then\n'
                           f'    : > "{t}/pulled"; echo "fatal: unable to access (测试)" >&2; exit 1\n  fi\ndone\n'
                           f'exec "{real_git}" "$@"\n', encoding="utf-8")
    (b / "git").chmod(0o755)
    return b


@need_git
def test_push_checks_identity_and_model_names_even_after_a_failed_first_pull(repos):
    """第一次 git pull --rebase 失败、重试时也照样查（以前只在第一轮查：重试会把带模型名 / 别的身份的提交推上去）。"""
    t = repos
    before = _git(t / "remote.git", "rev-parse", BRANCH, ident=False)
    _commit(t / "sim", {"quant_breakout/var/c.txt": "x"}, "sim(mac): x\n\nCo-Authored-By: Claude Foo 9.9 <noreply@anthropic.com>")
    rc, out = _run(t, "push", path_extra=_fail_first_pull(t))
    assert rc == 1 and "没成功" in out and "带模型名的署名行" in out, out
    _git(t / "sim", "reset", "-q", "--hard", "origin/" + BRANCH, ident=False)
    (t / "pulled").unlink()
    _commit(t / "sim", {"quant_breakout/var/c.txt": "y"}, "sim(mac): y", ident=("someone", "me@host.local"))
    rc, out = _run(t, "push", path_extra=_fail_first_pull(t))
    assert rc == 1 and "不是现在设的 git 身份" in out, out
    assert _git(t / "remote.git", "rev-parse", BRANCH, ident=False) == before             # 什么都没推


@need_git
def test_done_today_counts_only_what_is_on_the_remote(repos):
    """只在本机的日报提交不算「做过」（R-2）：推不上去 → 2；能推 → 先推上去再算（做过 = Mac）。"""
    t = repos
    _commit(t / "sim", {**_daily("2026-10-09")}, "sim(mac): 2026-10-08 日报\n\nCo-Authored-By: Claude Foo 9.9 <noreply@anthropic.com>",
            date="2026-10-09T06:58:00+09:00")
    rc, out = _run(t, "done-today", "sim", QBREAK_ROUTINES_PULL="0")                      # 只 fetch：看远端 → 还没入库
    assert rc == 1 and "还没入库" in out, out
    rc, out = _run(t, "done-today", "sim")                                                # 先推 → 推不上去（带模型名）→ 2
    assert rc == 2 and "没推上去" in out and "已经做过" not in out, out
    _git(t / "sim", "reset", "-q", "--hard", "origin/" + BRANCH, ident=False)
    _commit(t / "sim", {**_daily("2026-10-09")}, "sim(mac): 2026-10-08 日报", date="2026-10-09T06:58:00+09:00")
    rc, out = _run(t, "done-today", "sim")
    assert rc == 0 and "先推上去" in out and "[OK] 已推送 1 个提交" in out and "今天已经做过（Mac）" in out, out
    _commit(t / "sim", {"quant_breakout/var/out/shadow_today.json": "{}"}, "shadow(mac): 2026-10-09 判断",
            date="2026-10-09T07:50:00+09:00")
    rc, out = _run(t, "done-today", "shadow", QBREAK_ROUTINES_PULL="0")
    assert rc == 1 and "还没入库" in out, out


@need_git
def test_collision_with_the_cloud_backup_drops_the_redundant_mac_commit(repos):
    """Mac 和云端后备同一天都做了日报：Mac 后推 → rebase 冲突 → 云端已经入库了同一份 → Mac 的提交留在本地备份分支、克隆回到远端（R-3）；
    下一次 done-today 不再停在退出码 2。"""
    t = repos
    _push_cloud(t, _daily("2026-10-09"), "sim: 2026-10-08 日报", "2026-10-09T07:21:00+09:00")
    _commit(t / "sim", {DAILY: json.dumps({"date": "2026-10-09", "bar_date": "mac"})}, "sim(mac): 2026-10-08 日报",
            date="2026-10-09T07:25:00+09:00")
    mine = _git(t / "sim", "rev-parse", "--short", "HEAD", ident=False).strip()
    rc, out = _run(t, "push")
    assert rc == 0 and "云端后备已经入库了同一份结果" in out and f"backup/routines-2026-10-09-{mine}" in out, out
    assert _git(t / "sim", "rev-parse", "HEAD", ident=False) == _git(t / "remote.git", "rev-parse", BRANCH, ident=False)
    assert mine in _git(t / "sim", "rev-parse", "--short", f"backup/routines-2026-10-09-{mine}", ident=False)
    _commit(t / "sim", {"quant_breakout/var/out/shadow_today.json": "{1}"}, "shadow(mac): 2026-10-09 判断",
            date="2026-10-09T08:10:00+09:00")
    _push_cloud(t, {"quant_breakout/var/out/shadow_today.json": "{2}"}, "shadow: 2026-10-09 判断", "2026-10-09T08:06:00+09:00")
    rc, out = _run(t, "done-today", "shadow")                                             # 分叉（pull --ff-only 失败）→ 同样处理
    assert rc == 0 and "云端后备已经入库了同一份结果" in out and "今天已经做过（云端）" in out, out


def test_deps_leaves_the_shared_venv_alone_during_trading_hours(tmp_path):
    """routines.sh deps：共用的 ~/.qbreak/venv 在交易日 07:30〜15:30 不改（执行器 / 面板在用），只报和 requirements.lock 的差别（R-5）。"""
    if not shutil.which("bash"):
        pytest.skip("需要 bash")
    home = tmp_path / "home"
    vb = home / ".qbreak" / "venv" / "bin"
    vb.mkdir(parents=True)
    log = tmp_path / "pip.log"
    (vb / "python").write_text(f'#!/bin/sh\ncase "$1 $2" in "-m pip") echo "pip $*" >> "{log}"; exit 0 ;; esac\nexec "{sys.executable}" "$@"\n',
                               encoding="utf-8")
    (vb / "python").chmod(0o755)
    env = {**_base_env(home), "PATH": os.environ["PATH"], "QBREAK_PYTHON": str(vb / "python"),
           "QBREAK_ROUTINES_TODAY": "2026-10-09", "QBREAK_ROUTINES_HHMM": "0956"}
    r = subprocess.run(["bash", str(SH), "deps"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "不改共用的虚拟环境" in r.stdout and "requirements.lock" in r.stdout, r.stdout + r.stderr
    assert not log.exists()                                                               # 没有 pip install
    for hhmm, today in (("0646", "2026-10-09"), ("0956", "2026-10-12")):                # 开盘前 / 休市日：照常装
        r = subprocess.run(["bash", str(SH), "deps"], cwd=ROOT, env={**env, "QBREAK_ROUTINES_HHMM": hhmm, "QBREAK_ROUTINES_TODAY": today},
                           capture_output=True, text=True, timeout=120)
        assert "pip install" in log.read_text(encoding="utf-8"), r.stdout + r.stderr
        log.unlink()
