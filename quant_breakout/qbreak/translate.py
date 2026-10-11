"""translate.py — 消息标题翻译成简体中文（2026-10-11 用户「通知里面的新闻都要翻译为中文后进行通知」）。

用 macOS 自带的离线翻译（scripts/translate/QbreakTranslate.swift → ~/.qbreak/app/qbreak-translate；标题不发给任何第三方）。
翻过的放 <数据目录>/cache/news/translations.json（第三方标题与译文只在本机，不入库）；同一条只翻一次。
小工具没装 / 语言包没下载 / 失败 → 返回 None：调用方照发通知，用中文的事件类别与影响 + 原文标题（绝不因为翻译不了而不通知）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path

from . import paths
from .utils import read_json, write_json

log = logging.getLogger("qbreak.translate")
KEEP = 3000
TIMEOUT_S = 60


def binary() -> Path:
    return Path(os.environ.get("QBREAK_TRANSLATE") or Path.home() / ".qbreak" / "app" / "qbreak-translate")


def _cache_path() -> Path:
    return paths.sub("cache/news") / "translations.json"


def _key(s: str) -> str:
    return hashlib.sha1(str(s).strip().encode("utf-8")).hexdigest()[:16]


def status() -> dict:
    """{"tool": bool, "langs": {"ja": "installed|supported|unsupported", "en": ...}}（菜单栏 / 排查用；只读）。"""
    b = binary()
    if not b.exists():
        return {"tool": False, "langs": {}}
    try:
        r = subprocess.run([str(b), "--status"], capture_output=True, text=True, timeout=20)
        return {"tool": True, "langs": json.loads(r.stdout or "{}")}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"tool": True, "langs": {}}


def to_zh(texts: list[str], run=subprocess.run) -> list[str | None]:
    """一批标题 → 中文（顺序对应；翻不了的 None）。缓存命中的不再翻；绝不抛。"""
    texts = [str(t or "") for t in texts]
    cache = read_json(_cache_path(), {}) or {}
    out: list[str | None] = [cache.get(_key(t)) if t else None for t in texts]
    todo = sorted({t for t, z in zip(texts, out) if t and z is None})
    b = binary()
    if todo and b.exists():
        try:
            r = run([str(b)], input=json.dumps(todo, ensure_ascii=False), capture_output=True, text=True, timeout=TIMEOUT_S)
            res = json.loads(r.stdout or "[]")
            got = {t: (x or {}).get("zh") for t, x in zip(todo, res)}
            new = {_key(t): z for t, z in got.items() if z}
            if new:
                cache.update(new)
                if len(cache) > KEEP:
                    cache = dict(list(cache.items())[-KEEP:])
                write_json(_cache_path(), cache)
            out = [z if z is not None else (got.get(t) if t else None) for t, z in zip(texts, out)]
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            log.warning("翻译失败（通知照发、用原文）：%s", type(e).__name__)
    return out


def annotate(events: list[dict], only=None) -> int:
    """给事件加 title_zh（only(e) 为 True 的才翻；缺省 = 全部）。返回翻好的条数。"""
    sel = [e for e in events if (only is None or only(e)) and e.get("title")]
    zh = to_zh([e["title"] for e in sel])
    n = 0
    for e, z in zip(sel, zh):
        if z and z.strip() != str(e["title"]).strip():
            e["title_zh"] = z
            n += 1
        elif z:
            e["title_zh"] = z                                  # 本来就是中文
            n += 1
    return n


def show(e: dict) -> str:
    """显示用的标题：有中文用中文，没有就原文。"""
    return str(e.get("title_zh") or e.get("title") or "")
