"""signal_push.py — 出买点 / 卖点的票推送一次（2026-10-18 用户：「出买点/卖点股票的时候要用推送信息推送一次」）。只是通知，不下单、不改规则。

什么时候：执行器早上的决策（run.py live-u 早上那次运行，写完汇总之后）。
  买点 = 汇总的候选（suggest.rows）里 status = triggered：这次决策那根 K 线出了买入信号（会不会真的买写在后面：已安排 / 规则不买的理由）；
  卖点 = 账本 pending_exit 里规则判卖的（止损 / 跟踪止损 / 止盈 / 死叉 …；你自己写的卖出 / 减仓不算）。
推一次：同一只、同一方向「刚出现」才推 —— 上一次决策时已经在里面的不再推（连续几天都是信号只推第一天）；同一次决策重跑（重试）不重推。
  记在数据目录 out/signal_push_<账本>.json（{"decided_on", "buy": [...], "sell": [...]}；只在本机）。
一次运行的新信号合成一条推送（qbreak 推送 + 通知记录 + Mac 通知）。盘中暂定卖点（intraday_watch，14:10 之后）照旧另推。
代码一律带名字（qbreak/names.py）。非投资建议。
"""
from __future__ import annotations

import datetime as dt
import json
import logging

from . import names as NM
from . import paths
from .utils import atomic_write_text, read_json

log = logging.getLogger(__name__)

SELF_EXITS = ("manual", "manual_trim")


def path(tag: str):
    return paths.out_dir() / f"signal_push_{tag}.json"


def _md(d) -> str:
    try:
        x = dt.date.fromisoformat(str(d)[:10])
    except ValueError:
        return str(d or "")
    return f"{x.month}/{x.day}（周{'一二三四五六日'[x.weekday()]}）"


def current(sm: dict, pending: dict) -> tuple[list[dict], list[tuple[str, str]]]:
    """这次决策的买点（候选行）与卖点（[(票, 理由)]）。"""
    buys = [r for r in ((sm.get("suggest") or {}).get("rows") or []) if r.get("status") == "triggered" and r.get("ticker")]
    sells = sorted((str(t), str(w)) for t, w in (pending or {}).items() if str(w) not in SELF_EXITS)
    return buys, sells


def _buy_line(r: dict) -> str:
    ru, b = r.get("rule") or {}, r.get("buy") or {}
    s = f"{NM.label(r['ticker'])}：{ru.get('text') or '出了买入信号'}"
    if ru.get("state") in ("planned", "manual") and b.get("limit"):
        s += f"（最高 ¥{float(b['limit']):,.0f} = 收盘 ×1.03；开盘更高就不买）"
    return s


def _sell_line(t: str, why: str, shares: dict, sm: dict) -> str:
    from .holding_view import EXIT_TEXT
    n = int((shares or {}).get(t) or 0)
    return (f"{NM.label(t)}" + (f" {n:,} 股" if n else "") + f"：{EXIT_TEXT.get(why, why)}（按 {_md(sm.get('decided_on'))}收盘）"
            + (f"→ {_md(sm.get('fill_day'))} 09:00 开盘卖" if sm.get("fill_day") else "→ 下一个开盘卖"))


def run(tag: str, sm: dict, pending: dict, shares: dict, paper: bool, send=None, mac=None) -> dict | None:
    """新出现的买点 / 卖点推一条；返回 {"title", "body", "buy", "sell"}（没有新的 → None，记录照样更新）。"""
    d = str(sm.get("decided_on") or "")
    buys, sells = current(sm, pending)
    prev = read_json(path(tag), {}) or {}
    same = prev.get("decided_on") == d
    base_b, base_s = set(prev.get("buy") or []), set(prev.get("sell") or [])
    nb = [r for r in buys if r["ticker"] not in base_b]
    ns = [(t, w) for t, w in sells if t not in base_s]
    keep_b = {r["ticker"] for r in buys} | (base_b if same else set())
    keep_s = {t for t, _ in sells} | (base_s if same else set())
    atomic_write_text(path(tag), json.dumps({"decided_on": d, "buy": sorted(keep_b), "sell": sorted(keep_s)}, ensure_ascii=False))
    if not nb and not ns:
        return None
    who = "模拟操盘" if paper else "立花实盘"
    head = "、".join(x for x in (f"买点 {len(nb)} 只" if nb else "", f"卖点 {len(ns)} 只" if ns else "") if x)
    title = f"qbreak {who}：{head}"
    halt = paths.halt_file().exists()
    body = ([f"- 卖点 {_sell_line(t, w, shares, sm)}" for t, w in ns] + [f"- 买点 {_buy_line(r)}" for r in nb]
            + [("- ★ HALT 中：不会下单" if halt else "- 执行器照常处理，不需要操作") + "（非投资建议）"])
    short = "；".join([f"卖 {NM.label(t, short=True)}" for t, _ in ns] + [f"买点 {NM.label(r['ticker'], short=True)}" for r in nb])
    if send is None:
        from .notify import send
    if mac is None:
        from .live_unified import mac_notify as mac
    try:
        mac(title, short[:200])
        send(title, "\n".join(body), "info")
    except Exception as e:                                    # noqa: BLE001  通知失败不影响执行器
        log.warning("买卖点的推送失败：%s", type(e).__name__)
    return {"title": title, "body": body, "buy": [r["ticker"] for r in nb], "sell": [t for t, _ in ns]}


__all__ = ["run", "current", "path"]
