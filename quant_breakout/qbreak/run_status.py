"""run_status.py — 执行器这次跑成没有（面板 / 手机 / 09:30 自检读；只展示与提醒，不影响下单）。

文件：数据目录的 out/live_unified_<账本>_run.json（Mac：~/.qbreak/home/out/；.gitignore 已忽略，不入库）。
run.py live-u 每次运行结束时写一份（正常结束 / 执行器停下 / 拿不到运行锁 / 程序出错；scripts/liveu.sh「运行没有完成」那条路
经 --status --alert 也写）；没事可做的重试 / 盘中运行不写（不覆盖上一次有内容的状态）。
  {"at": ISO, "phase": morning | retry | open | now, "ok": bool, "rc": int, "error": str | null, "blocked": str | null,
   "decided_on": 决策日, "bad_orders": [{cid, side, ticker, qty, status, note, kind}],  ← 当前决策里被挡 / 被拒 / 状态不明的单
   "errors": [这次运行 error 级事件的文字，最多 5 条],
   "code": git 短 hash（"?" = 读不了；云端每天推 var/ 也会变）, "code_tree": 只看代码的标识（代码真的变了才变）,
   "py": {python, pandas, numpy, yfinance}（B6：qbreak/versions.py）,
   "unknown": [{cid, ticker, side, qty, candidates: [{order_no, status, filled_qty, filled_px, …}]}]}  ← 只在因状态不明停下时（B2）
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path

from . import paths
from .calendar_jp import JST, now_jst
from .utils import atomic_write_text

BAD = ("BLOCKED", "REJECTED", "ERROR", "SENDING", "EXPIRED")    # 没下成（被挡 / 被拒）、状态不明（发送中断 / 网络错误）或在立花那边已失效的单
STATUS_TEXT = {"BLOCKED": "被挡", "REJECTED": "被拒", "ERROR": "状态不明", "SENDING": "状态不明", "EXPIRED": "已失效"}
PHASE_TEXT = {"morning": "早上的运行", "retry": "早上的重试", "open": "开盘后补单", "now": "盘中手动指令", "cancel": "撤单"}
KEEP_FAIL_S = 900                                     # liveu.sh 的「运行没有完成」紧跟在一次具体的失败之后：15 分钟内不盖掉更具体的原因
MAX_ERROR = 600                                       # 错误文字最多留多少字（面板 / 手机显示）
_URL = re.compile(r"https?://\S+")


def path(tag: str) -> Path:
    return paths.out_dir() / f"live_unified_{tag}_run.json"


def peek_json(p) -> dict | None:
    """读一个小的状态文件：没有 / 读坏 / 不是 dict → None（不改名、不报错；账本文件的损坏处理留给执行器自己）。"""
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:                                 # noqa: BLE001
        return None
    return d if isinstance(d, dict) else None


def bad_orders(orders, decided_on: str | None = None) -> list[dict]:
    """决策 decided_on（None = 不筛）里被挡 / 被拒 / 状态不明的单（只取展示要的字段）。orders：账本里的单（dict）。"""
    out = []
    for o in orders or []:
        if not isinstance(o, dict) or o.get("status") not in BAD:
            continue
        if decided_on is not None and o.get("decided_on") != decided_on:
            continue
        out.append({"cid": str(o.get("cid") or ""), "side": str(o.get("side") or ""), "ticker": str(o.get("ticker") or ""),
                    "qty": int(o.get("sent_qty") or o.get("qty") or 0), "status": str(o["status"]),
                    "note": str(o.get("note") or ""), "kind": str(o.get("kind") or "stock")})
    return out


HALT_NOTE = "存在 HALT 文件"                          # HALT 挡下的单的 note 开头（live_unified.UnifiedExecutor._gate）


def is_halt(o: dict) -> bool:
    """HALT 挡下的单（BLOCKED，note 以「存在 HALT 文件」开头）。"""
    return o.get("status") == "BLOCKED" and str(o.get("note") or "").startswith(HALT_NOTE)


def actionable(bad: list[dict]) -> list[dict]:
    """去掉 HALT 挡下的单：HALT 生效中不下单是预期的，不算失败（通知不标 ★、级别不升到 warn）。"""
    return [o for o in bad if not is_halt(o)]


def uncovered(bad: list[dict], blocked: str | None) -> list[dict]:
    """整次运行被挡时（「★ 没下单：{blocked}」已经说了），说明就是那个原因（之一）的 BLOCKED 单不再逐笔算。"""
    b = scrub(blocked)
    if not b:
        return list(bad)
    return [o for o in bad if not (o.get("status") == "BLOCKED" and (scrub(o.get("note")) or "\0") in b)]


def bad_text(bad: list[dict]) -> str:
    """「被挡 1、状态不明 2」（按 被挡 → 被拒 → 状态不明 的顺序，只列有的）。"""
    n = Counter(STATUS_TEXT.get(o.get("status"), str(o.get("status"))) for o in bad)
    order = list(dict.fromkeys(STATUS_TEXT.values()))
    return "、".join(f"{k} {n[k]}" for k in sorted(n, key=lambda k: order.index(k) if k in order else 99))


def ts(s) -> dt.datetime | None:
    """ISO 时刻 → 带时区的 datetime（没带时区的按 JST）；读不了 → None。"""
    try:
        t = dt.datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=JST)


def run_errors(events, since: str | None) -> list[str]:
    """since（这次运行开始的时刻，ISO）之后的 error 级事件的文字（最多 5 条，取最后的）。since 为空 → 没有。"""
    t0 = ts(since) if since else None
    if t0 is None:
        return []
    out = []
    for e in events or []:
        e = e if isinstance(e, dict) else {}
        t = ts(e.get("at"))
        if t is not None and t >= t0 and e.get("level") == "error":
            out.append(str(e.get("msg") or ""))
    return out[-5:]


def local_paths_out(text: str) -> str:
    """本机路径换成短的说法：数据目录（QBREAK_HOME）→「数据目录」、家目录 →「~」（手机通知 / 心跳 / 面板的文字不带 Mac 的用户名）。"""
    import os
    s = str(text)
    reps = []
    qh = os.environ.get("QBREAK_HOME")
    if qh:
        reps.append((str(Path(qh).expanduser()).rstrip("/"), "数据目录"))
    try:
        reps.append((str(Path.home()).rstrip("/"), "~"))
    except (RuntimeError, KeyError):                    # 没有家目录（极少见）
        pass
    for a, b in sorted(reps, key=lambda x: -len(x[0])):  # 长的（更具体的）先换
        if len(a) > 1:
            s = s.replace(a, b)
    return s


def scrub(text) -> str | None:
    """错误文字：去掉网址（立花的虚拟 URL 里有会话信息）、本机路径换成「数据目录」/「~」，限制长度。空 → None。"""
    if text is None:
        return None
    s = local_paths_out(_URL.sub("（网址已省略）", str(text))).strip()
    return s[:MAX_ERROR] or None


def build(book: dict | None, *, phase: str, ok: bool, rc: int, error: str | None = None, blocked: str | None = None,
          since: str | None = None, events=(), now: dt.datetime | None = None, unknown: list | None = None) -> dict:
    """一条运行状态。book：账本（dict；当前决策与单从这里取）；events：还没写进账本的事件（执行器停下时）；
    unknown：状态不明的单在注文一覧里的候选（执行器因状态不明停下时；qbreak/live_ops.unknown_candidates）→ 字段 unknown。"""
    from .versions import code_tree, code_version, py_versions
    book = book or {}
    d = (book.get("state") or {}).get("last_date")
    rec = {"at": (now or now_jst()).isoformat(timespec="seconds"), "phase": phase, "ok": bool(ok), "rc": int(rc),
           "error": scrub(error), "blocked": scrub(blocked), "decided_on": d,
           "bad_orders": bad_orders(book.get("orders"), d),
           "errors": run_errors(list(book.get("events") or []) + list(events or []), since),
           "code": code_version(), "code_tree": code_tree(),          # B6：这次用的提交（git 短 hash）、只看代码的标识（var/ 提交不变）
           "py": dict(py_versions())}                                  # 与 Python / 依赖的版本
    if unknown is not None:
        rec["unknown"] = unknown_brief(unknown)
    return rec


def unknown_brief(unknown: list | None) -> list[dict]:
    """状态不明的单与候选（面板 / 手机显示用的字段；文字去掉网址与本机路径）。"""
    out = []
    for u in unknown or []:
        if not isinstance(u, dict):
            continue
        if u.get("error"):
            out.append({"error": scrub(u["error"])})
            continue
        out.append({"cid": str(u.get("cid") or ""), "ticker": str(u.get("ticker") or ""), "side": str(u.get("side") or ""),
                    "qty": int(u.get("qty") or 0), "kind": str(u.get("kind") or "stock"),
                    **({"stale": str(u["stale"])[:10]} if u.get("stale") else {}),
                    "candidates": [{k: c.get(k) for k in ("order_no", "status", "final", "qty", "filled_qty", "filled_px", "price", "time")}
                                   for c in (u.get("candidates") or [])[:5] if isinstance(c, dict)]})
    return out


def write(tag: str, rec: dict, keep_recent_fail: bool = False) -> bool:
    """写运行状态文件。keep_recent_fail：同一阶段 15 分钟内已经记了一次失败（更具体的原因，例如拿不到运行锁）→ 不盖掉。
    返回是否写了。"""
    p = path(tag)
    if keep_recent_fail:
        old = peek_json(p)
        t_old, t_new = ts((old or {}).get("at")), ts(rec.get("at"))
        if (old and old.get("ok") is False and old.get("phase") == rec.get("phase") and t_old and t_new
                and 0 <= (t_new - t_old).total_seconds() <= KEEP_FAIL_S):
            return False
    atomic_write_text(p, json.dumps(rec, ensure_ascii=False, indent=1, default=str))
    return True


def read(tag: str) -> dict | None:
    """读运行状态文件：没有 / 读坏 → None（面板不显示，不报错）。"""
    return peek_json(path(tag))
