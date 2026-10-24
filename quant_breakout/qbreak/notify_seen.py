"""notify_seen.py — 同一个账本、同一天、同一段文字的提醒只发一次（Mac 通知 / 手机通知；终端与日志照写）。

2026-10-09 立花实盘缺口 A7（条目 UX-04 / C-01）：执行器失败时面板反复叫、每次都发「执行器停下」→ 通知轰炸。
文件：数据目录的 out/notify_seen_<账本>.json（{日期: [文字的 sha1 前 12 位, …]}；只记摘要不记原文；只留最近 7 天；
.gitignore 已忽略，不入库）。用在：run.py live-u 的「执行器停下」「拿不到运行锁」两条路；09:30 自检的「HALT 生效中」。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from . import paths
from .calendar_jp import JST, now_jst
from .utils import atomic_write_text, setup_logging

log = setup_logging("notify_seen")

KEEP_DAYS = 7
_TAG = re.compile(r"[a-z][a-z0-9_]{0,31}")
_VARY = (re.compile(r"https?://\S+"),                       # 网址（立花的虚拟 URL 每次登录都不同）
         re.compile(r"pid \d+"),                            # 运行锁的持有者（另一个进程）
         re.compile(r"\d{1,2}:\d{2}(?::\d{2})?"))           # 时刻（「从 … 09:20:01 JST」「08:35 的运行」）


def path(tag: str) -> Path:
    if not _TAG.fullmatch(str(tag)):
        raise ValueError(f"账本名不对：{tag!r}")
    return paths.out_dir() / f"notify_seen_{tag}.json"


def key(text) -> str:
    """一段文字的摘要（去掉每次都会变的网址 / 进程号 / 时刻，再 sha1 取前 12 位）。"""
    s = str(text or "")
    for rx in _VARY:
        s = rx.sub("#", s)
    s = " ".join(s.split())
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def _read(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001  没有 / 读坏 → 当作没发过
        return {}
    return {str(k): [str(x) for x in v] for k, v in d.items() if isinstance(v, list)} if isinstance(d, dict) else {}


def first(tag: str, text, now: dt.datetime | None = None) -> bool:
    """今天这个账本还没发过这段文字 → 记下、返回 True（该发通知）；发过 → False（只打印 / 写日志）。
    文件读写出错 → True（宁可多发一次，不漏发）。"""
    now = now or now_jst()
    now = now.astimezone(JST) if now.tzinfo else now
    today = now.date()
    try:
        p = path(tag)
        d = _read(p)
        k = key(text)
        seen = d.get(today.isoformat()) or []
        if k in seen:
            return False
        lo = (today - dt.timedelta(days=KEEP_DAYS - 1)).isoformat()
        d = {day: v for day, v in d.items() if lo <= day <= today.isoformat()}     # 只留最近 7 天
        d[today.isoformat()] = seen + [k]
        atomic_write_text(p, json.dumps(d, ensure_ascii=False, sort_keys=True))
    except Exception as e:                                   # noqa: BLE001
        log.warning("通知去重的记录读写不了（照常发）：%s", e)
    return True


__all__ = ["first", "key", "path", "KEEP_DAYS"]
