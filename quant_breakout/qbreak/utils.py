"""utils.py — 通用工具：原子写文件、JSON 读写、日志、重试。"""
from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from . import paths

T = TypeVar("T")


# ────────────────────────── 原子写 ──────────────────────────
def atomic_write_text(path: str | Path, text: str) -> None:
    """先写临时文件再 os.replace。

    原版 PaperBroker 直接 open(w) 覆盖 state 文件：进程在写一半时被杀（关机、Ctrl-C、
    任务计划程序超时）会留下半截 JSON，下次启动直接崩溃且持仓丢失。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # 同一文件系统上是原子操作


def write_json(path: str | Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        # 不静默吞掉：坏掉的状态文件必须让人看见，否则会"莫名其妙从空仓开始"
        bad = p.with_suffix(p.suffix + f".corrupt.{int(time.time())}")
        p.rename(bad)
        logging.getLogger("qbreak").error("状态文件损坏，已改名为 %s（%s）", bad, e)
        return default


# ────────────────────────── 日志 ──────────────────────────
_LOG_READY = False


def setup_logging(name: str = "qbreak", level: int = logging.INFO,
                  to_file: bool = True) -> logging.Logger:
    global _LOG_READY
    if not _LOG_READY:
        handlers: list[logging.Handler] = []
        if to_file:
            from logging.handlers import RotatingFileHandler
            fh = RotatingFileHandler(paths.log_dir() / "qbreak.log", maxBytes=5_000_000,
                                     backupCount=10, encoding="utf-8")
            handlers.append(fh)
        sh = logging.StreamHandler(sys.stdout)
        handlers.append(sh)
        fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)-14s %(message)s")
        for h in handlers:
            h.setFormatter(fmt)
        root = logging.getLogger("qbreak")
        root.handlers.clear()
        for h in handlers:
            root.addHandler(h)
        root.setLevel(level)
        root.propagate = False
        _LOG_READY = True
    return logging.getLogger(name if name.startswith("qbreak") else f"qbreak.{name}")


# ────────────────────────── 重试 ──────────────────────────
def retry(fn: Callable[[], T], attempts: int = 4, base_delay: float = 2.0,
          exceptions: tuple[type[BaseException], ...] = (Exception,),
          log: logging.Logger | None = None) -> T:
    """指数退避重试（yfinance 限流、Excel COM 偶发忙）。"""
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except exceptions as e:  # noqa: PERF203
            last = e
            if i == attempts - 1:
                break
            delay = base_delay * (2 ** i) + random.uniform(0, 0.5)
            if log:
                log.warning("第 %d/%d 次失败(%s)，%.1fs 后重试", i + 1, attempts, type(e).__name__, delay)
            time.sleep(delay)
    assert last is not None
    raise last


def fmt_money(x: float, market: str = "JP") -> str:
    return f"¥{x:,.0f}" if market == "JP" else f"${x:,.2f}"
