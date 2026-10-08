"""dip_stats.py — 操作面板趋势标签旁边的「历史统计」：月K 往上走时日K / 周K 往下走的三种组合（只展示，不改交易）。

来由：2026-10-08 用户选待办〔75〕②「在面板的趋势标签旁边只展示这几种组合的历史统计」。数字来自登记研究
scripts/month_up_dip_study.py（登记 ddfc854、只运行一次）的结果 var/out/month_up_dip_study.json（入库的汇总，不随 QBREAK_HOME 变）：
合并 Z + E + W + J2（2001〜2026）、进入这种组合的第一天 → 第二天开盘买、拿 20 个交易日（扣来回手续费）的成功率 / 平均 / 比大盘，和判定。
三种组合（与研究同一个定义，面板的趋势标签 = qbreak/kline.trend）：
  MUDW 月K 往上走（且前 3 个已完成月K 都往上走）+ 日K、周K 都往下走；MUD 只有日K 往下走（周K 没在跌）；MUW 只有周K 往下走（日K 没在跌）。
「前 3 个已完成月K 都往上走」= kline.month_up（执行器写进 K 线汇总的 trend.M.up3）；旧的汇总没有 → 不显示。
研究的对象是个股（不含核心 ETF），所以面板只在个股（持仓 / 建议的股票）上显示。研究结论：三种都不是好买点也不是好卖点 —— 这里照实写，不是预测。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .paths import PROJECT_ROOT

FILE = PROJECT_ROOT / "var" / "out" / "month_up_dip_study.json"
STATES = ("MUDW", "MUD", "MUW")
NAME = {"MUDW": "月K 往上走 + 日K、周K 都往下走", "MUD": "月K 往上走 + 只有日K 往下走", "MUW": "月K 往上走 + 只有周K 往下走"}
SPAN = "2001〜2026"


def state_of(tr: dict | None) -> str | None:
    """面板的趋势（{"D"/"W"/"M": {"label", …}}，M 带 up3）→ "MUDW" / "MUD" / "MUW" / None。
    标签缺一个、或月线条件不知道（up3 不是 True / False）→ None（不猜）。"""
    tr = tr or {}
    d, w, m = (str((tr.get(k) or {}).get("label") or "") for k in ("D", "W", "M"))
    if not d or not w or m != "上升" or (tr.get("M") or {}).get("up3") is not True:
        return None
    if d == "下降" and w == "下降":
        return "MUDW"
    if d == "下降":
        return "MUD"
    if w == "下降":
        return "MUW"
    return None


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


_CACHE: dict = {}


def load(path: Path | None = None) -> dict | None:
    """研究结果 → {状态: {"n", "months", "win", "net", "x", "verdict"}}；没有 / 读不了 → None（面板不显示）。按修改时间缓存。"""
    fp = Path(path) if path else FILE
    try:
        mt = fp.stat().st_mtime
    except OSError:
        return None
    hit = _CACHE.get(str(fp))
    if hit and hit[0] == mt:
        return hit[1]
    try:
        A = (json.loads(fp.read_text(encoding="utf-8")) or {}).get("A") or {}
        out = {}
        for k in STATES:
            p = ((A.get("states") or {}).get(k) or {}).get("pool") or {}
            win, net, x = _f(p.get("win")), _f(p.get("net_mean")), _f(p.get("x_mean"))
            if win is None or net is None or x is None:
                continue
            out[k] = {"n": int(p.get("n") or 0), "months": int(p.get("months") or 0), "win": win, "net": net, "x": x,
                      "verdict": str((A.get("verdict") or {}).get(k) or "")}
        out = out or None
    except (OSError, ValueError, TypeError):
        out = None
    _CACHE[str(fp)] = (mt, out)
    return out


def say(st: dict) -> str:
    """判定 → 一句日常的话（研究的判定写法，不另加解释）。"""
    v = st.get("verdict") or ""
    if v.startswith("没有信息"):
        return "和平常差不多（不是好买点，也不是好卖点）"
    if v.startswith("方向一致但不够"):
        return f"略{'差' if st['x'] < 0 else '好'}于大盘，但不够确定"
    if v.startswith("买点成立"):
        return "历史上比大盘好"
    if v.startswith("卖点成立"):
        return "历史上比大盘差"
    return v or "—"


def line(tr: dict | None, table: dict | None = None) -> dict | None:
    """一只票现在的趋势 → {"state", "name", "text"}；不是这三种组合 / 没有结果 → None。"""
    k = state_of(tr)
    tab = load() if table is None else table
    if not k or not tab or k not in tab:
        return None
    s = tab[k]
    text = (f"历史上（{SPAN}，{s['n']:,} 次）刚变成这样之后 20 个交易日：赚钱的比例 {s['win']:.0f}%、平均 {s['net']:+.1f}%、"
            f"比大盘 {s['x']:+.1f} pp → {say(s)}；不是预测").replace("+-", "−").replace(" -", " −")
    return {"state": k, "name": NAME[k], "text": text}


__all__ = ["FILE", "STATES", "NAME", "state_of", "load", "say", "line"]
