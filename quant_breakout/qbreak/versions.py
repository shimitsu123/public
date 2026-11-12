"""versions.py — 实盘用的代码版本与依赖版本（立花实盘缺口 B6：LU-17 / C-10；只记录与提醒，不影响下单）。

① code_version()：项目所在仓库的 git 短 hash（git -C <项目> rev-parse --short HEAD；读不了 → "?"）。
   执行器每次运行写进运行状态文件（out/live_unified_<账本>_run.json 的 code）与日志：这次用的是哪个提交。
   code_tree()：只看代码（qbreak / run.py / scripts / tests / requirements.*）的标识 —— 云端每天推的 var/ 提交不改变它；
   运行状态文件的 code_tree；scripts/liveu.sh 用同一个算法判断「立花本番这次用的是不是新代码」（新代码先跑冒烟测试，数据目录 .smoke_ok 记着验证过的标识）。
② py_versions()：python / pandas / numpy / yfinance 的版本（importlib.metadata 读，不 import 这些包）→ 运行状态文件的 py。
③ requirements.lock：云端测试通过的那一套确切版本（pip freeze 风格）。mac_setup.sh / install_launchd_live_u.sh 按它装（装不上 →
   退回 requirements.txt 并提醒）；scripts/dev.sh check 用 `python -m qbreak.versions lock-check` 比较虚拟环境与它（不一致只提醒）。
"""
from __future__ import annotations

import importlib.metadata as md
import platform
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from . import paths

LOCK = paths.PROJECT_ROOT / "requirements.lock"
PY_PKGS = ("pandas", "numpy", "yfinance")
_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;#]+)\s*(?:;\s*([^#]+?))?\s*(?:#.*)?$")


@lru_cache(maxsize=4)
def code_version(root: str | None = None) -> str:
    """git 短 hash（同一个进程里只问一次 git）；不是 git 仓库 / 没有 git / 超时 → "?"。"""
    try:
        r = subprocess.run(["git", "-C", str(root or paths.PROJECT_ROOT), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "?"
    h = (r.stdout or "").strip()
    return h if r.returncode == 0 and re.fullmatch(r"[0-9a-f]{4,40}", h) else "?"


CODE_PATHS = ("qbreak", "run.py", "scripts", "tests", "requirements.txt", "requirements.lock")


@lru_cache(maxsize=4)
def code_tree(root: str | None = None) -> str:
    """只看代码的标识（12 位）：HEAD 里 qbreak / run.py / scripts / tests / requirements.* 的 git 对象 id
    （git -C <项目> ls-tree HEAD -- …）合起来的摘要。云端例行任务每天推的 var/ 提交不改变它 → scripts/liveu.sh 的冒烟测试
    只在代码真的变了时跑（数据目录 .smoke_ok 记的就是它；liveu.sh 用同一个命令 + git hash-object 算，两边一致）。读不了 → "?"。"""
    import hashlib
    try:
        r = subprocess.run(["git", "-C", str(root or paths.PROJECT_ROOT), "ls-tree", "HEAD", "--", *CODE_PATHS],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "?"
    out = (r.stdout or "").rstrip("\n")
    if r.returncode != 0 or not out:
        return "?"
    data = (out + "\n").encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()[:12]     # = git hash-object --stdin


def _ver(name: str) -> str:
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return "没装"
    except Exception:                                      # noqa: BLE001  元数据坏了也不影响运行
        return "?"


@lru_cache(maxsize=1)
def py_versions() -> dict[str, str]:
    """{"python": "3.12.7", "pandas": …, "numpy": …, "yfinance": …}（没装 → "没装"）。"""
    return {"python": platform.python_version(), **{p: _ver(p) for p in PY_PKGS}}


def brief() -> str:
    """日志一行：「代码 1a2b3c4 · Python 3.12.7 · pandas 3.0.6 · numpy 2.4.6 · yfinance 1.7.0」。"""
    v = py_versions()
    return f"代码 {code_version()} · Python {v['python']} · " + " · ".join(f"{p} {v[p]}" for p in PY_PKGS)


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", str(name)).lower()


def read_lock(path=None) -> dict[str, tuple[str, str, str]]:
    """requirements.lock → {规范化的包名: (包名, 版本, 环境标记)}；注释 / 空行 / 不是「名==版本」的行跳过。没有文件 → {}。"""
    p = Path(path or LOCK)
    if not p.exists():
        return {}
    out = {}
    for ln in p.read_text(encoding="utf-8").splitlines():
        m = _LINE.match(ln)
        if m:
            out[norm(m.group(1))] = (m.group(1), m.group(2), (m.group(3) or "").strip())
    return out


def marker_applies(marker: str) -> bool:
    """环境标记（只用到 sys_platform == / != "…"）在这台机器上成立吗；没有标记 → True；认不出的标记 → True（照样比较）。"""
    if not marker:
        return True
    m = re.fullmatch(r"""sys_platform\s*(==|!=)\s*["']([^"']+)["']""", marker.strip())
    if not m:
        return True
    return (sys.platform == m.group(2)) == (m.group(1) == "==")


def lock_diff(path=None, version_of=None) -> list[tuple[str, str, str]]:
    """虚拟环境（这个 Python）里和 requirements.lock 不同的包 → [(包名, 现在的版本 | "没装", 锁定的版本)]。
    version_of：测试注入（包名 → 版本）。只比较锁里有、标记在这台机器上成立的包。"""
    get = version_of or _ver
    out = []
    for _, (name, want, marker) in sorted(read_lock(path).items()):
        if not marker_applies(marker):
            continue
        have = get(name)
        if have != want:
            out.append((name, have, want))
    return out


def lock_check_lines(path=None, version_of=None) -> tuple[list[str], bool]:
    """scripts/dev.sh check 的一行（或几行）：一致 → [OK]；不一致 → [提醒]（不算 ★：只提醒，交易照常）。"""
    lock = read_lock(path)
    if not lock:
        return [f"[提醒] 没有 {Path(path or LOCK).name}：依赖没锁版本（mac_setup.sh 照 requirements.txt 装）"], False
    diff = lock_diff(path, version_of)
    if not diff:
        return [f"[OK] 虚拟环境的依赖版本与 requirements.lock 一致（{len(lock)} 个包；Python {platform.python_version()}）"], True
    head = "、".join(f"{n} {h}（锁 {w}）" for n, h, w in diff[:8]) + (f" 等 {len(diff)} 个" if len(diff) > 8 else "")
    return [f"[提醒] 虚拟环境有 {len(diff)} 个包和 requirements.lock 不同：{head}",
            "       不影响今天的运行；要和云端测试同一套：bash scripts/mac_setup.sh（按 requirements.lock 装；"
            "Python 低于 3.11 装不上锁定的 pandas / numpy → 用 Python ≥ 3.11 重建 ~/.qbreak/venv）"], False


def main(argv: list[str] | None = None) -> int:
    """python -m qbreak.versions [lock-check [锁文件] | brief | code | code-tree]：只读，永远退出 0（不一致只提醒）。"""
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "brief"
    if cmd == "lock-check":
        lines, _ = lock_check_lines(argv[1] if len(argv) > 1 else None)
        print("\n".join(lines))
    elif cmd == "code":
        print(code_version())
    elif cmd == "code-tree":
        print(code_tree())
    else:
        print(brief())
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
