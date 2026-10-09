"""paths.py — 运行期文件位置的唯一真相来源。

原版把 paper_state.json / trader.log / best_params.json 写在「当前工作目录」(CWD)。
用 Windows 任务计划程序（タスクスケジューラ）启动时 CWD 会变成 C:\\Windows\\System32，
结果是：手动跑有持仓、定时跑却每次都从空仓开始 —— 这是实盘阶段最容易踩的坑之一。
这里统一改为：

    QBREAK_HOME 环境变量  >  <项目根>/var

所有状态/日志/缓存/输出都落在该目录下，与启动方式无关。
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def home() -> Path:
    """数据根目录。设 QBREAK_HOME 可指向任意位置（如 D:\\trading\\var）。"""
    p = Path(os.environ.get("QBREAK_HOME") or (PROJECT_ROOT / "var"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def repo_root() -> Path:
    """git 仓库的根：项目根或它的上一级（仓库布局是 <仓库>/quant_breakout）里有 .git 的那个；都没有 → 项目根。
    只往上看一级：再往上（例如家目录本身是 git 仓库）不算，免得把 ~/.qbreak/home 也当成仓库里面。"""
    for d in (PROJECT_ROOT, PROJECT_ROOT.parent):
        if (d / ".git").exists():
            return d
    return PROJECT_ROOT


def inside_repo() -> bool:
    """数据目录（照 home() 的算法，但不建目录）解析后在仓库里面 → True。
    这是公开仓库：立花的账本 / 检查结果写进仓库的 var/，一次 git add 就会推上去（撤不回）；run.py 的立花入口用它拒绝运行。"""
    p = Path(os.environ.get("QBREAK_HOME") or (PROJECT_ROOT / "var"))
    try:
        p = p.resolve()                                       # 相对路径按当前目录、符号链接按实际位置算
    except OSError:
        p = p.absolute()
    root = repo_root().resolve()
    return p == root or root in p.parents


def sub(name: str) -> Path:
    p = home() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    return sub("cache")


def state_dir() -> Path:
    return sub("state")


def log_dir() -> Path:
    return sub("logs")


def out_dir() -> Path:
    return sub("out")


def params_file(market: str | None = None) -> Path:
    """optimize 产出的稳健参数；trader 自动读取。
    market 给定时返回该市场的**覆盖文件**（best_params_JP.json 等，可只写差异字段）。"""
    if market:
        return home() / f"best_params_{market.upper()}.json"
    return home() / "best_params.json"


def halt_file() -> Path:
    """紧急停止开关（キルスイッチ / kill switch）：该文件存在则任何下单都被拒绝。"""
    return home() / "HALT"


ARM_WORD = "ARMED"


def arm_state() -> str:
    """ARM（解锁发单）现在的状态 —— 和立花适配器同一个判断（UX-12：面板 / gate / manual / doctor 都用这里）：
    环境变量 QBREAK_ARM=ARMED →「env」；数据目录的 ARM 文件内容（去空白、不分大小写）是 ARMED →「file」；
    文件在、内容不是 ARMED（适配器会把每一笔挡成 BLOCKED）→「bad」；没有 →「off」。只读：不建、不删、不改 ARM。"""
    if os.environ.get("QBREAK_ARM", "").strip().upper() == ARM_WORD:
        return "env"
    f = home() / "ARM"
    if not f.exists():
        return "off"
    try:
        txt = f.read_text(encoding="utf-8").strip().upper()
    except (OSError, UnicodeDecodeError):
        return "bad"
    return "file" if txt == ARM_WORD else "bad"


def armed() -> bool:
    """解锁发单了吗（arm_state 是 env / file）。"""
    return arm_state() in ("env", "file")


LIVE_AGENT, PAPER_AGENT = "com.qbreak.liveu.morning", "com.qbreak.liveu.paper"


def launch_agents() -> Path:
    """LaunchAgents 目录（QBREAK_LAUNCH_AGENTS 可改：测试 / 别的位置）。只给路径，不建目录。"""
    return Path(os.environ.get("QBREAK_LAUNCH_AGENTS") or Path.home() / "Library" / "LaunchAgents")


def live_installed(agents: Path | None = None) -> bool:
    """装了立花本番吗（B12 / LU-20 / OPS-06）：LaunchAgents 有 com.qbreak.liveu.morning 的 plist；
    或立花本番的账本在、而模拟操盘的 plist（com.qbreak.liveu.paper）不在（install_launchd_live_u.sh tachibana 会卸掉它）。
    只看文件，不调 launchctl、不建目录。"""
    ag = Path(agents) if agents is not None else launch_agents()
    if (ag / f"{LIVE_AGENT}.plist").exists():
        return True
    p = Path(os.environ.get("QBREAK_HOME") or (PROJECT_ROOT / "var"))
    return (p / "state" / "live_unified_tachibana.json").exists() and not (ag / f"{PAPER_AGENT}.plist").exists()


def default_book(agents: Path | None = None) -> str:
    """面板（Mac + 手机）没指定账本时打开哪一个：装了立花本番 → tachibana（真钱）；否则 paper（模拟账户）。"""
    return "tachibana" if live_installed(agents) else "paper"
