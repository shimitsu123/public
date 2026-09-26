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
            "install_launchd_news.sh", "install_launchd_jquants.sh", "mac_setup.sh"} <= {p.name for p in scripts}
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
            "QBREAK_SKIP_VENV": "1", "QBREAK_LAUNCH_AGENTS": str(tmp_path / "agents")}


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
    assert "⑤ ★ 没能建" in out and "已注册的定时任务：" in out
