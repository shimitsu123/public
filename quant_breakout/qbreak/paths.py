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
