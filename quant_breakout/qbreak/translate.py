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
import re
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
    return hashlib.sha1((str(s).strip() + "|" + _gloss_ver()).encode("utf-8")).hexdigest()[:16]   # 术语表 / 检查改了 → 重新翻


# ───────────────────────── 准确度对策（2026-10-11 实测 41 条：意思错 3 条（涨跌反了 / 数量级 / 整句）、繁体 2 条、小问题 4 条） ─────────────────────────
CHECK_VER = "4"
GLOSS_FILE = paths.PROJECT_ROOT / "var" / "translate_glossary.json"
# 价格的涨 / 跌 与 利率的加 / 减 分开数（「加息」不能算成「上涨」）；原文里每类有几个，译文里就要有至少几个，少了 → 标出
PAT = {
    "up": (r"\b(rise[sn]?|rising|rose|rall(?:y|ies|ied)|jump(?:s|ed)?|surg(?:e|es|ed)|soar(?:s|ed)?|gain(?:s|ed)?|climb(?:s|ed)?|"
           r"spik(?:e|es|ed)|rebound(?:s|ed)?|higher)\b|上昇|急騰|高騰|急伸|反発|値上がり|最高値|上振れ",
           r"上涨|涨|飙升|上升|攀升|走高|反弹|回升|走强|上扬|新高|提高|增长|上调"),
    "down": (r"\b(fall(?:s|en)?|fell|drop(?:s|ped)?|slump(?:s|ed)?|plung(?:e|es|ed)|tumbl(?:e|es|ed)|sink(?:s)?|sank|slid(?:e|es)?|"
             r"declin(?:e|es|ed)|lower|crash(?:es|ed)?)\b|下落|急落|暴落|反落|値下がり|最安値|安値|下振れ|減少",
             r"下跌|跌|下降|下滑|走低|走弱|回落|暴跌|崩|减少|下调|新低"),
    "hike": (r"\b(hike[sd]?|tighten(?:s|ing|ed)?)\b|利上げ|引き締め", r"加息|收紧|上调利率|提高利率"),
    "cut": (r"\brate cuts?\b|\bcuts? rates?\b|利下げ|緩和", r"降息|宽松|下调利率|降低利率"),
    # 制裁 / 限制的放松 vs 加强（2026-10-11 实测：Easing of Sanctions → 「放大…制裁」意思反了）
    "ease": (r"\b(eas(?:e|es|ed|ing)|lift(?:s|ed|ing)?|relax(?:es|ed|ing)?|loosen(?:s|ed|ing)?|suspend(?:s|ed|ing)?|scrap(?:s|ped)?)\b|解除|緩和措置|撤廃",
             r"放松|放宽|解除|取消|暂停|缓和|撤销|废除|放轻松"),
    "tighten": (r"\b(impos(?:e|es|ed|ing)|tighten(?:s|ed|ing)?|expand(?:s|ed)? sanctions)\b|発動|強化", r"实施|施加|加强|收紧|扩大|发动"),
}
MAG = ((r"hundreds of billions", "千亿"), (r"tens of billions", "百亿"), (r"\btrillions?\b", "万亿"), (r"\bbillions?\b", "亿"))


def _gloss() -> dict:
    return (read_json(GLOSS_FILE, {}) or {}).get("pre") or {}


def _gloss_ver() -> str:
    g = _gloss()
    return CHECK_VER + ":" + hashlib.sha1(json.dumps(g, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:8]


def pre(s: str) -> str:
    """翻译前：术语表（长的先换）+「【地名発】」→「【地名报道】」。"""
    for k in sorted(_gloss(), key=len, reverse=True):
        s = re.sub(r"\b" + re.escape(k) + r"\b" if re.match(r"^[A-Za-z ]+$", k) else re.escape(k), _gloss()[k], s)
    return re.sub(r"【([^】]{1,8})発】", r"【\1报道】", s)


def tidy(zh: str) -> str:
    """翻译后：去掉紧挨着重复的词（「中期中期」→「中期」）。"""
    return re.sub(r"([\u4e00-\u9fff]{2,4})\1", r"\1", zh)


def checks(src: str, zh: str) -> list[str]:
    """译文可能错的地方（规则检查；抓不到整句意思错 → 原文始终附在后面）：涨跌 / 加减息的个数、数字、数量级。"""
    flags = []
    for kind, (ps, pz) in PAT.items():
        n_src = len(re.findall(ps, src, re.I))
        if n_src and len(re.findall(pz, zh)) < n_src:
            flags.append({"up": "涨跌方向", "down": "涨跌方向", "hike": "加息 / 降息", "cut": "加息 / 降息"}.get(kind, "放松 / 加强"))
    nums = {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", src)}
    zn = zh.replace(",", "").replace("，", "")
    if any(n not in zn for n in nums):
        flags.append("数字")
    for pat, need in MAG:
        if re.search(pat, src, re.I):
            if need not in zh:
                flags.append("数量级")
            break
    return list(dict.fromkeys(flags))


def finish(src: str, zh: str) -> str:
    z = tidy(zh)
    f = checks(src, z)
    return z + (f"（⚠ {'、'.join(f)}可能译错，请看原文）" if f else "")


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
            r = run([str(b)], input=json.dumps([pre(t) for t in todo], ensure_ascii=False), capture_output=True, text=True, timeout=TIMEOUT_S)
            res = json.loads(r.stdout or "[]")
            got = {t: (finish(t, (x or {})["zh"]) if (x or {}).get("zh") else None) for t, x in zip(todo, res)}
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
