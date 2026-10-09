"""scripts/*.sh 要能在 macOS 自带的 /bin/bash 3.2 上跑。

那个 bash 判断变量名用 macOS 的 isalnum()，而它在 UTF-8 locale 下把 0xC0〜0xFF 这些字节当成 Latin-1 字母：紧跟在 $变量 后面的
全角括号 / 中文（UTF-8 的第一个字节是 0xE3〜0xEF）会被算进变量名 ——「$DEST（」变成「DEST\\xEF: unbound variable」，
脚本都开了 set -u，直接退出（一行安装命令在终端里跑、定时任务 plist 的 LANG=en_US.UTF-8 都会触发）。写成「${DEST}（」就没事。
Linux 的 bash 在 UTF-8 下复现不了，所以 ① 静态扫描所有脚本（主要的防线）；② 有 localedef 时，在 ISO-8859-1 locale 下真的跑一遍
几条会打印「变量 + 中文」的路径（glibc 的 isalnum 在这里和 macOS 一样把 0xEF 当字母 → 能复现），在 en_US.UTF-8 下也跑一遍。
"""
import os
import re
import shutil
import site
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BARE_VAR_THEN_NON_ASCII = re.compile(rb"\$[A-Za-z_][A-Za-z0-9_]*(?=[\x80-\xff])")


def _shell_scripts() -> list[Path]:
    """仓库里所有 *.sh，加上 scripts/ 下没有扩展名但第一行是 sh / bash 的脚本。"""
    out = {p for p in ROOT.rglob("*.sh") if not {".git", "cache", "__pycache__"} & set(p.parts)}
    for p in (ROOT / "scripts").iterdir():
        if p.is_file() and p.suffix != ".py":
            first = p.read_bytes().split(b"\n", 1)[0]
            if first.startswith(b"#!") and first.rstrip().endswith((b"sh", b"bash")):
                out.add(p)
    return sorted(out)


def test_no_bare_variable_followed_by_non_ascii():
    scripts = _shell_scripts()
    assert {"liveu.sh", "install_launchd_live_u.sh", "mac_bootstrap.sh", "install_launchd_fetch.sh",
            "install_launchd_news.sh", "install_launchd_jquants.sh", "mac_setup.sh", "install_launchd_login.sh",
            "install_launchd_watchdog.sh", "dev.sh"} <= {p.name for p in scripts}
    hits = [f"{p.relative_to(ROOT)}:{n}: {m.group().decode()}{line[m.end():].decode('utf-8', 'replace')[:1]}"
            for p in scripts for n, line in enumerate(p.read_bytes().splitlines(), 1)
            for m in BARE_VAR_THEN_NON_ASCII.finditer(line)]
    assert not hits, "macOS 的 bash 3.2 会把后面那个字节算进变量名（set -u 下直接退出）→ 改成 ${VAR}：\n" + "\n".join(hits)


def test_scan_pattern_catches_the_known_bad_form():
    assert BARE_VAR_THEN_NON_ASCII.search('echo "下载代码到 $DEST（约 15 MB）"'.encode())
    assert BARE_VAR_THEN_NON_ASCII.search('echo "等了 $waited分钟"'.encode())
    assert not BARE_VAR_THEN_NON_ASCII.search('echo "下载代码到 ${DEST}（约 15 MB）"'.encode())
    assert not BARE_VAR_THEN_NON_ASCII.search('echo "$HOME/logs（"'.encode())         # 后面先是 ASCII 的「/」
    assert not BARE_VAR_THEN_NON_ASCII.search('echo "$1（ $?（"'.encode())             # 位置参数 / 特殊参数只取一个字符


# ────────── 真的跑一遍（只在 Linux：靠 glibc 的 locale 模拟 macOS 的 isalnum）──────────
@pytest.fixture(scope="module")
def locales(tmp_path_factory):
    if not sys.platform.startswith("linux") or not shutil.which("localedef") or not shutil.which("bash"):
        pytest.skip("需要 Linux + localedef + bash")
    loc = tmp_path_factory.mktemp("loc")
    for name, charmap in (("en_US.ISO-8859-1", "ISO-8859-1"), ("en_US.UTF-8", "UTF-8")):
        subprocess.run(["localedef", "-i", "en_US", "-f", charmap, str(loc / name)], capture_output=True)   # 有警告也会生成
    return loc


def _env(tmp_path, locales, name: str) -> dict:
    if not (locales / name).is_dir():
        pytest.skip(f"{name} 编不出来（缺 /usr/share/i18n 的源文件）")
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    stubs = {
        "git": '#!/bin/sh\ncase "$*" in *rev-parse*) echo origin/x; exit 0 ;; esac\nexit 1\n',   # git pull 失败，不碰真仓库
        "launchctl": "#!/bin/sh\nexit 0\n",                                                      # 不注册任何定时任务
        "fakepy": f'#!/bin/sh\ncase " $* " in *" --status "*) exec "{sys.executable}" "$@" ;; esac\nexit 1\n',  # 其余一律「出错」
    }
    for n, body in stubs.items():
        (b / n).write_text(body, encoding="utf-8")
        (b / n).chmod(0o755)
    (tmp_path / "home").mkdir(exist_ok=True)
    return {**os.environ, "PATH": f"{b}{os.pathsep}{os.environ['PATH']}", "LOCPATH": str(locales), "LC_ALL": name,
            # Python 按 UTF-8 解参数（ISO-8859-1 只是为了让 bash 复现 macOS 的行为；Mac 上本来就是 UTF-8）
            "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
            "HOME": str(tmp_path / "home"), "PYTHONUSERBASE": site.getuserbase(), "TZ": "UTC",
            "QBREAK_PYTHON": str(b / "fakepy"), "QBREAK_LIVEU_HOME": str(tmp_path / "lh"), "QBREAK_LIVEU_WAIT_MIN": "0",
            "QBREAK_SKIP_VENV": "1", "QBREAK_LAUNCH_AGENTS": str(tmp_path / "agents"), "QBREAK_WATCHDOG_WAIT": "0"}


def _bash(env, *args) -> tuple[str, str]:
    r = subprocess.run(["bash", *args], cwd=ROOT, env=env, capture_output=True, timeout=120)
    return r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


@pytest.mark.parametrize("name", ["en_US.ISO-8859-1", "en_US.UTF-8"])
def test_scripts_print_chinese_after_variables_without_dying(tmp_path, locales, name):
    """liveu.sh run（git pull 失败 / 等不到云端 / 运行没走完）、liveu.sh trial、install_launchd_live_u.sh（时区不是 +0900、注册、结尾说明）。"""
    env = _env(tmp_path, locales, name)
    if name == "en_US.ISO-8859-1":                           # 先确认这个 locale 真能复现（否则这一组没有意义）
        _, err = _bash(env, "-uc", 'X=1; echo "$X（"')
        if "unbound variable" not in err:
            pytest.skip("这台机器的 glibc 在 ISO-8859-1 下没有复现 macOS 的行为")
    out, err = _bash(env, "scripts/liveu.sh", "run", "--broker", "paper")
    assert "unbound variable" not in err, err
    assert "git pull 失败" in out and "★ 等了 0 分钟" in out and "运行没有完成（退出码 1）" in out
    assert "运行没有完成（退出码 1）" in (tmp_path / "lh" / "out" / "page_paper.html").read_text(encoding="utf-8")
    out, err = _bash(env, "scripts/liveu.sh", "trial")
    assert "unbound variable" not in err, err
    assert "试跑（临时目录 " in out and "★ 试跑失败" in out
    out, err = _bash(env, "scripts/install_launchd_live_u.sh", "paper")
    assert "unbound variable" not in err, err
    assert "时区是 UTC+0000" in out and "已注册 com.qbreak.liveu.paper：" in out and "数据目录 " in out
    out, err = _bash(env, "scripts/install_launchd_news.sh")                  # 市场仪表盘 + 经济威胁提醒（每 15 分钟）
    assert "unbound variable" not in err, err
    plist = tmp_path / "agents" / "com.qbreak.news.plist"
    assert "已注册 com.qbreak.news：每 15 分钟一次" in out and plist.exists()
    assert "<string>news</string>" in plist.read_text(encoding="utf-8") and "<integer>900</integer>" in plist.read_text(encoding="utf-8")
    out, err = _bash(env, "scripts/liveu.sh", "news")
    assert "unbound variable" not in err, err
    out, err = _bash(env, "scripts/install_launchd_news.sh", "uninstall")
    assert "已卸载 com.qbreak.news" in out and not plist.exists()
    out, err = _bash(env, "scripts/install_launchd_jquants.sh")               # J-Quants：周一至五 19:30 + 07:05
    assert "unbound variable" not in err, err
    jp = tmp_path / "agents" / "com.qbreak.jquants.plist"
    assert "已注册 com.qbreak.jquants：" in out and jp.read_text(encoding="utf-8").count("<key>Weekday</key>") == 10
    out, err = _bash({**env, "JQUANTS_API_KEY": ""}, "scripts/liveu.sh", "jq")   # 没有キー → 说明怎么放进钥匙串（不回显任何值）
    assert "unbound variable" not in err, err
    assert "钥匙串里没有 qbreak-jquants" in out
    (tmp_path / "agents" / "com.qbreak.liveu.paper.plist").write_text("x", encoding="utf-8")
    out, err = _bash(env, "scripts/mac_setup.sh")                             # 一条命令：已装的跳过、没键就说明、克隆失败也不中断
    assert "unbound variable" not in err, err
    assert "② 模拟操盘已安装" in out and "已注册 com.qbreak.news" in out and "④ J-Quants：钥匙串里还没有" in out
    assert "已注册 com.qbreak.login" in out and (tmp_path / "agents" / "com.qbreak.login.plist").exists()
    wdp = tmp_path / "agents" / "com.qbreak.watchdog.plist"                     # 09:30 自检（两种模式都装）
    assert "已注册 com.qbreak.watchdog：周一至五 09:30" in out and wdp.exists()
    assert "<string>watchdog</string>" in wdp.read_text(encoding="utf-8") and wdp.read_text(encoding="utf-8").count("<key>Weekday</key>") == 5
    assert "⑤ ★ 没能建" in out and "已注册的定时任务：" in out
    assert "⑤b 本地改代码 / 推送（不需要云端）：" in out and "/scripts/dev.sh\" check" in out
    out, err = _bash(env, "scripts/mac_setup.sh", "--phone", "node")               # 连手机一起：假 Python 出错 → 如实说，其他步骤照常
    assert "unbound variable" not in err, err
    assert "④d ★ 手机访问没打开（退出码 1）" in out and "已注册的定时任务：" in out
    (tmp_path / "lh" / "panel_phone.json").write_text("{}", encoding="utf-8")       # 以前打开过：每次更新都确认还在（不弹页面）
    out, err = _bash(env, "scripts/mac_setup.sh")
    assert "unbound variable" not in err, err
    assert "④d ★ 手机访问没打开（退出码 1）" in out and "mac_setup.sh --phone <Tailscale 机器名>" not in out
    out, err = _bash(env, "scripts/mac_setup.sh", "--bogus")
    assert "不认识的参数 --bogus" in out
    out, err = _bash({**env, "QBREAK_LOGIN_DELAY": "0"}, "scripts/liveu.sh", "login")   # 登录时的检查（假 Python 出错 → 如实说，不中断）
    assert "unbound variable" not in err, err
    assert "登录时的检查失败" in out


@pytest.mark.parametrize("name", ["en_US.ISO-8859-1", "en_US.UTF-8"])
def test_live_ops_paths_print_chinese_without_dying(tmp_path, locales, name):
    """立花本番的定时任务（07:40 / 08:35 重试 / 09:05 / 09:20 重试）与 gate / flow / probe / halt-drill 子命令（2026-10-04 加）。"""
    env = _env(tmp_path, locales, name)
    out, err = _bash(env, "scripts/install_launchd_live_u.sh", "tachibana")
    assert "unbound variable" not in err, err
    for lb, hm in (("morning", "07:40"), ("retry", "08:35"), ("open", "09:05"), ("open2", "09:20")):
        assert f"已注册 com.qbreak.liveu.{lb}：周一至五 {hm}" in out
    retry = (tmp_path / "agents" / "com.qbreak.liveu.retry.plist").read_text(encoding="utf-8")
    assert "<string>--retry</string>" in retry and "<string>tachibana</string>" in retry and "上线前检查（只读）" in out
    out, err = _bash(env, "scripts/liveu.sh", "run", "--broker", "tachibana", "--phase", "open", "--retry")
    assert "unbound variable" not in err, err
    assert "运行没有完成（退出码 1）" in out                       # 假 Python 出错：重试没走完也照样标红
    for args in (["gate"], ["flow"], ["flow", "300000"], ["probe"], ["halt-drill"], ["notify-test"], ["watchdog"],
                 ["email-setup"], ["email-setup", "--host", "smtp.example.com", "--port", "465"]):
        out, err = _bash(env, "scripts/liveu.sh", *args)
        assert "unbound variable" not in err, (args, err)
    out, _ = _bash(env, "scripts/liveu.sh", "flow")
    assert "用法：bash scripts/liveu.sh flow 300000" in out
    out, err = _bash(env, "scripts/install_launchd_watchdog.sh")
    assert "unbound variable" not in err, err
    assert "已注册 com.qbreak.watchdog：" in out and (tmp_path / "agents" / "com.qbreak.watchdog.plist").exists()
    out, err = _bash(env, "scripts/install_launchd_watchdog.sh", "uninstall")
    assert "已卸载 com.qbreak.watchdog" in out and not (tmp_path / "agents" / "com.qbreak.watchdog.plist").exists()
    out, err = _bash(env, "scripts/install_launchd_live_u.sh", "uninstall")
    assert "已卸载 com.qbreak.liveu.open2" in out and not (tmp_path / "agents" / "com.qbreak.liveu.retry.plist").exists()


@pytest.mark.parametrize("name", ["en_US.ISO-8859-1", "en_US.UTF-8"])
def test_dev_sh_prints_chinese_without_dying(tmp_path, locales, name):
    """本地开发脚本 dev.sh（2026-10-09 加）：check / push / test 的各条提示（假 git：什么都失败，只有 rev-parse 成功）。"""
    env = _env(tmp_path, locales, name)
    for d in ("dev", "src"):
        (tmp_path / d / ".git").mkdir(parents=True)                # 看起来像克隆（假 git 让 rev-parse 成功）
    env = {**env, "QBREAK_DEV": str(tmp_path / "dev"), "QBREAK_SRC": str(tmp_path / "src")}
    out, err = _bash(env, "scripts/dev.sh", "check")
    assert "unbound variable" not in err, err
    assert "[★] 当前分支是 （没有分支：detached HEAD），不是 claude/" in out and "[★] 连不上远端 origin" in out
    assert "[★] 推不上去" in out and "[★] git 的 user.name user.email 没设" in out and "低于 3.10" in out and "项要处理" in out
    out, err = _bash(env, "scripts/dev.sh", "push")
    assert "unbound variable" not in err, err
    assert "不推（只推这个分支）" in out
    out, err = _bash(env, "scripts/dev.sh", "test")
    assert "unbound variable" not in err, err
    out, err = _bash({**env, "QBREAK_DEV": str(tmp_path / "none"), "QBREAK_SRC": str(tmp_path / "none")}, "scripts/dev.sh", "check")
    assert "unbound variable" not in err, err
    assert "[★] 没有研究用的克隆 " in out and "[★] 没有定时任务用的克隆 " in out
    out, err = _bash(env, "scripts/dev.sh")
    assert "用法：bash scripts/dev.sh check" in out


# ────────── liveu.sh run 的收尾（不需要 locale）：通知去重、早上跑完之后让 Mac 醒着 ──────────
def _run_env(tmp_path, rc: int, **extra) -> tuple[dict, Path]:
    """假 Python（记下参数；live-u 按 rc 退出、不写页面）+ 假 osascript / caffeinate（只记下被叫了）。"""
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    stubs = {
        "fakepy": ('#!/bin/sh\necho "py $*" >> "$CALLS"\n'
                   'case " $* " in *" -c "*) case "$*" in *Asia/Tokyo*) echo 600 ;; esac; exit 0 ;; esac\n'
                   'case " $* " in *" --status "*|*" notify "*) exit 0 ;; *" live-u "*) exit "$FAKE_RC" ;; esac\nexit 0\n'),
        "osascript": '#!/bin/sh\necho "osascript" >> "$CALLS"\n',
        "caffeinate": '#!/bin/sh\necho "caffeinate $*" >> "$CALLS"\n',
    }
    for n, body in stubs.items():
        (b / n).write_text(body, encoding="utf-8")
        (b / n).chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("QBREAK_", "XPC_"))}
    env.update({"PATH": f"{b}{os.pathsep}{os.environ['PATH']}", "HOME": str(tmp_path / "home"), "CALLS": str(log),
                "FAKE_RC": str(rc), "QBREAK_PYTHON": str(b / "fakepy"), "QBREAK_LIVEU_HOME": str(tmp_path / "lh"),
                "QBREAK_LIVEU_WAIT_MIN": "0", "QBREAK_LIVEU_PULL": "0", "QBREAK_CAFFEINATED": "1",
                "QBREAK_LAUNCH_AGENTS": str(tmp_path / "agents"), "LC_ALL": "C.UTF-8", **extra})
    (tmp_path / "home").mkdir(exist_ok=True)
    if log.exists():
        log.unlink()
    return env, log


def _calls(log: Path) -> str:
    return log.read_text(encoding="utf-8") if log.exists() else ""


@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_liveu_run_does_not_repeat_the_notice_when_run_py_already_notified(tmp_path):
    """退出码 3（执行器停下 / 拿不到运行锁）：run.py 自己已经通知过（同一天同一个原因只发一次）→ liveu.sh 不再发 Mac / 手机通知；
    别的退出码（Python 出错等）照旧发。页面标红（--status --alert）两种都照写。"""
    env, log = _run_env(tmp_path, 3)
    out, err = _bash(env, "scripts/liveu.sh", "run", "--broker", "paper", "--retry")
    c = _calls(log)
    assert "运行没有完成（退出码 3）" in out and "--status --alert" in c
    assert "osascript" not in c and " notify " not in c
    env, log = _run_env(tmp_path, 1)
    out, err = _bash(env, "scripts/liveu.sh", "run", "--broker", "paper", "--retry")
    c = _calls(log)
    assert "运行没有完成（退出码 1）" in out and "osascript" in c and "py run.py notify --subject" in c


@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_liveu_run_keeps_the_mac_awake_for_the_watchdog_only_in_the_scheduled_runs(tmp_path):
    """早上跑完之后醒到 09:35（09:30 的自检要按时跑）：立花照旧；模拟账户只在 07:40 的定时任务本身、而且装了自检时
    （登录时的补跑、面板叫的重试 / 盘中不等）。"""
    agents = tmp_path / "agents"
    agents.mkdir()
    job = {"XPC_SERVICE_NAME": "com.qbreak.liveu.paper"}
    env, log = _run_env(tmp_path, 1, **job)
    _bash(env, "scripts/liveu.sh", "run", "--broker", "paper")
    assert "caffeinate" not in _calls(log)                              # 没装 09:30 自检：不用等
    (agents / "com.qbreak.watchdog.plist").write_text("x", encoding="utf-8")
    env, log = _run_env(tmp_path, 1, **job)
    out, _ = _bash(env, "scripts/liveu.sh", "run", "--broker", "paper")
    assert "caffeinate -i -t 600" in _calls(log) and "09:30 的自检按时运行" in out
    for args, extra in ((["run", "--broker", "paper"], {}),                              # 登录时的补跑（不是定时任务本身）
                        (["run", "--broker", "paper", "--retry"], job),                  # 面板叫的重试
                        (["run", "--broker", "paper", "--phase", "now"], job)):          # 盘中
        env, log = _run_env(tmp_path, 1, **extra)
        _bash(env, "scripts/liveu.sh", *args)
        assert "caffeinate" not in _calls(log), args
    env, log = _run_env(tmp_path, 1)
    _bash(env, "scripts/liveu.sh", "run", "--broker", "tachibana", "--retry")
    assert "caffeinate -i -t 600" in _calls(log)                        # 立花：照旧
    env, log = _run_env(tmp_path, 0, QBREAK_WATCHDOG_WAIT="0")
    _bash(env, "scripts/liveu.sh", "watchdog", "--dry")
    assert "py run.py live-watchdog --dry" in _calls(log)
