"""watch_prob.py — 「观察中」的买入优先级：历史上同样情况的股票，之后 10 个交易日内出买入信号的比例（只排序与展示，不改交易）。

来由：2026-10-07 用户「观察的股票要进行买入优先级排序 比如最上面的最大概率会买入」。
登记：scripts/watch_prob_study.py（规则与代码先提交、只运行一次）。判定通过才有 var/watch_prob.json；没有这个文件 = 照旧的顺序
（qbreak/suggest.near_key：闸门 → 还差的条件数 → 估计几天金叉 → 量比 → 就绪度）。

「情况」（cell）= 三个维度，都只用今天收盘为止的数据（与 suggest.proximity / scan 同一个定义）：
  ① wb  MACD 在哪：up_d1 / up_d2 / up_d3_4 / up_d5_9 / up_d10（在信号线下、往上靠，按最近一天的变化估计第几天金叉；10 = 10 天以上）、
        down_near / down_far（在线下、还在往下走；离信号线 < / ≥ 收盘价的 0.15% —— scan「快要出」的同一个界线）、
        above_near / above_far（已经在线上：要先回落再金叉）、unknown（算不出来）
  ② mb  今天就不满足、金叉那天多半也不满足的条件数（proximity 的 miss）：m0 / m1 / m2（2 个以上）
  ③ vb  今天的量比（scan 的 vol_ratio，缺值 = 0）：v_lo（< 1.0）/ v_hi（≥ 1.0）
比例 = 三层收缩（m = 50 个样本的权重）：情况 → ①×② → ① → 全部（样本少的情况往上一层靠；没见过的情况 = 上一层）。
出了信号还要过闸门（资格检查 / 新仓倍数 / 决算前 / 名额 / 钱）—— 页面照旧先按闸门分（被挡的放最后），这个比例只管「会不会出信号」。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .paths import PROJECT_ROOT

FILE = PROJECT_ROOT / "var" / "watch_prob.json"     # 入库的汇总表（研究判定通过才有；不随 QBREAK_HOME 变）
H = 10                                              # 之后几个交易日内（不含今天）
M = 50                                              # 收缩强度（样本权重）
NEAR_GAP = 0.15                                     # 离信号线 < 收盘价的 0.15% = 「近」（scan 的「快要出」界线）
WB = ("up_d1", "up_d2", "up_d3_4", "up_d5_9", "up_d10", "down_near", "down_far", "above_near", "above_far", "unknown")
MB = ("m0", "m1", "m2")
VB = ("v_lo", "v_hi")
WB_TEXT = {"up_d1": "MACD 估计 1 天后金叉", "up_d2": "MACD 估计 2 天后金叉", "up_d3_4": "MACD 估计 3〜4 天后金叉",
           "up_d5_9": "MACD 估计 5〜9 天后金叉", "up_d10": "MACD 往上靠、离金叉还远", "down_near": "MACD 在信号线下往下走（离得近）",
           "down_far": "MACD 在信号线下往下走（离得远）", "above_near": "MACD 已在信号线上（离得近）",
           "above_far": "MACD 已在信号线上（离得远）", "unknown": "MACD 算不出来"}


def wb_of(where, days, gap_pct) -> str:
    """① MACD 在哪（where / days = suggest.proximity 的；gap_pct = scan 的 macd_gap_pct：(MACD − 信号线) ÷ 收盘 × 100，保留 3 位）。"""
    if where == "below_up":
        d = int(days) if days is not None else 99
        return "up_d1" if d <= 1 else "up_d2" if d == 2 else "up_d3_4" if d <= 4 else "up_d5_9" if d <= 9 else "up_d10"
    try:
        g = abs(float(gap_pct))
    except (TypeError, ValueError):
        g = float("nan")
    near = math.isfinite(g) and g < NEAR_GAP
    if where == "below_down":
        return "down_near" if near else "down_far"
    if where == "above":
        return "above_near" if near else "above_far"
    return "unknown"


def mb_of(n_miss) -> str:
    n = int(n_miss or 0)
    return "m0" if n <= 0 else "m1" if n == 1 else "m2"


def vb_of(vol) -> str:
    try:
        v = float(vol)
    except (TypeError, ValueError):
        return "v_lo"
    return "v_hi" if math.isfinite(v) and v >= 1.0 else "v_lo"


def cell_of(near: dict | None, gap_pct, vol) -> tuple[str, str, str]:
    n = near or {}
    return wb_of(n.get("where"), n.get("days"), gap_pct), mb_of(len(n.get("miss") or [])), vb_of(vol)


def _est(y: float, n: float, prior: float, m: float) -> float:
    return (float(y) + m * prior) / (float(n) + m)


def fit(rows, h: int = H, m: float = M, extra: dict | None = None) -> dict:
    """rows：可迭代的 (wb, mb, vb, y)（y = 0 / 1）→ 汇总表（只有个数与比例，没有个股 / 日期）。"""
    c3: dict[tuple, list] = {}
    for wb, mb, vb, y in rows:
        k = (str(wb), str(mb), str(vb))
        a = c3.setdefault(k, [0, 0])
        a[0] += 1
        a[1] += int(y)
    n_all = sum(a[0] for a in c3.values())
    y_all = sum(a[1] for a in c3.values())
    if n_all == 0:
        raise ValueError("没有样本")
    pg = y_all / n_all
    c1: dict[str, list] = {}
    c2: dict[tuple, list] = {}
    for (wb, mb, vb), (n, y) in c3.items():
        for d, k in ((c1, wb), (c2, (wb, mb))):
            a = d.setdefault(k, [0, 0])
            a[0] += n
            a[1] += y
    l1 = {wb: {"n": n, "y": y, "p": _est(y, n, pg, m)} for wb, (n, y) in c1.items()}
    l2 = {f"{wb}|{mb}": {"n": n, "y": y, "p": _est(y, n, l1[wb]["p"], m)} for (wb, mb), (n, y) in c2.items()}
    l3 = {f"{wb}|{mb}|{vb}": {"n": n, "y": y, "p": _est(y, n, l2[f"{wb}|{mb}"]["p"], m)} for (wb, mb, vb), (n, y) in c3.items()}
    out = {"h": int(h), "m": float(m), "global": {"n": n_all, "y": y_all, "p": pg}, "l1": l1, "l2": l2, "l3": l3}
    if extra:
        out.update(extra)
    return out


def prob(table: dict, wb: str, mb: str, vb: str) -> dict:
    """查表：{"p", "n"（这个情况的样本数）, "y"}；没见过的情况 / 层 → 上一层的比例（与收缩公式在 n = 0 时相同）。"""
    g = table["global"]
    m = float(table.get("m", M))
    e1 = table["l1"].get(wb)
    p1 = e1["p"] if e1 else g["p"]
    e2 = table["l2"].get(f"{wb}|{mb}")
    p2 = e2["p"] if e2 else _est(0, 0, p1, m)
    e3 = table["l3"].get(f"{wb}|{mb}|{vb}")
    p3 = e3["p"] if e3 else _est(0, 0, p2, m)
    return {"p": float(p3), "n": int(e3["n"]) if e3 else 0, "y": int(e3["y"]) if e3 else 0}


_CACHE: dict = {}


def load(path: Path | None = None) -> dict | None:
    """var/watch_prob.json（研究判定通过才有）→ 表；没有 / 读不了 → None（= 照旧的顺序）。按修改时间缓存。"""
    fp = Path(path) if path else FILE
    try:
        mt = fp.stat().st_mtime
    except OSError:
        return None
    hit = _CACHE.get(str(fp))
    if hit and hit[0] == mt:
        return hit[1]
    try:
        t = json.loads(fp.read_text(encoding="utf-8"))
        if not (isinstance(t, dict) and {"global", "l1", "l2", "l3"} <= set(t)):
            t = None
    except (OSError, ValueError):
        t = None
    _CACHE[str(fp)] = (mt, t)
    return t


def for_row(row: dict, table: dict | None) -> dict | None:
    """建议的股票一行（suggest.build 的；有 near）→ {"p", "n", "y", "h", "cell", "show"}；没有表 / 出了信号的行 → None。
    show = 页面能不能写百分比（研究判定「排序可以、比例不准」时只排序不写数）。"""
    if not table or row.get("status") == "triggered" or not row.get("near"):
        return None
    wb, mb, vb = cell_of(row.get("near"), row.get("macd_gap_pct"), row.get("vol_ratio"))
    r = prob(table, wb, mb, vb)
    return {**r, "h": int(table.get("h", H)), "cell": f"{wb}|{mb}|{vb}", "show": bool(table.get("show_pct", True))}


__all__ = ["FILE", "H", "M", "NEAR_GAP", "WB", "MB", "VB", "WB_TEXT", "wb_of", "mb_of", "vb_of", "cell_of", "fit", "prob",
           "load", "for_row"]
