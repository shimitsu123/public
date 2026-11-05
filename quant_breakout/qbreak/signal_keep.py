"""signal_keep.py — 出过买入信号的票留在「选股」里，直到你点「删除」（2026-10-19 用户：「有买入信号机会（已经出了信号而不是还没出信号）
过了买入机会的股票就会消失 不在选股里面显示 改为有买入信号机会就要一直显示除非点击删除 点击删除后要出确认dialog」）。只展示，不下单、不改规则。

记什么：执行器汇总的候选（suggest.rows）里 status = triggered 的票 —— 一次「信号」= 连续几次决策都是 triggered 算同一次（since = 第一次那根 K 线、
  last = 最近一次）；中间断过（某次决策不是 triggered）之后又出 = 新的一次（以前删掉的那次不挡它）。
  记在数据目录 out/signal_keep_<账本>.json（{"asof": 最近记过的汇总 K 线, "items": {票: {since, last, fill, close, row}}, "deleted": {票: since}}；
  只在本机，不入库）。row = 出信号那次的候选行（之后没有新的行时用它显示）。
谁来记：执行器早上的运行（run.py live-u，写完汇总之后）与面板每次显示选股（同一个函数，没变就不写）。
删除：只从「选股」里拿掉这一次信号（规则照样按自己的判断买 / 不买；要不买 = 撤单 / HALT）；同一只之后再出新的信号会再显示。
"""
from __future__ import annotations

import datetime as dt
import json
import threading

from . import paths
from .utils import atomic_write_text, read_json

MAX_ITEMS = 60                                              # 留着的最多几只（太旧的先去掉：按最近一次信号排）
_LOCK = threading.Lock()


def path(tag: str):
    return paths.out_dir() / f"signal_keep_{tag}.json"


def _load(tag: str) -> dict:
    d = read_json(path(tag), {}) or {}
    return {"asof": d.get("asof"), "items": dict(d.get("items") or {}), "deleted": dict(d.get("deleted") or {})}


def _save(tag: str, d: dict) -> None:
    atomic_write_text(path(tag), json.dumps(d, ensure_ascii=False, default=str))


def note(tag: str, sg: dict | None) -> dict:
    """把这份汇总（sm["suggest"]）里出了买入信号的记下来；返回记录。没有新的 / 没变 → 不写。"""
    sg = sg or {}
    asof = str(sg.get("asof") or "")
    with _LOCK:
        d = _load(tag)
        if not asof or (d["asof"] and asof < str(d["asof"])):   # 没有 K 线日 / 比记过的还旧（旧汇总）→ 不动
            return d
        prev = str(d["asof"] or "")
        trig = [r for r in (sg.get("rows") or []) if r.get("status") == "triggered" and r.get("ticker")]
        changed = asof != prev
        for r in trig:
            t = str(r["ticker"])
            it = d["items"].get(t)
            if it and str(it.get("last")) in (asof, prev):      # 同一次信号（上一次记的汇总里也是 triggered / 同一份汇总重看）
                if it.get("last") != asof or it.get("row") != r:
                    it.update(last=asof, row=r)
                    changed = True
                continue
            d["items"][t] = {"since": asof, "last": asof, "fill": sg.get("fill_day"), "close": r.get("close"), "row": r}
            changed = True
        for t, s in list(d["deleted"].items()):              # 删掉的那一次已经不在记录里（换成了新的一次 / 太旧去掉）→ 不再记
            if (d["items"].get(t) or {}).get("since") != s:
                d["deleted"].pop(t)
                changed = True
        if len(d["items"]) > MAX_ITEMS:
            keep = sorted(d["items"], key=lambda t: str(d["items"][t].get("last")), reverse=True)[:MAX_ITEMS]
            d["items"] = {t: d["items"][t] for t in keep}
            changed = True
        d["asof"] = asof
        if changed:
            _save(tag, d)
        return d


def kept(tag: str, sg: dict | None = None) -> list[dict]:
    """要显示的「以前出过买入信号」：没删的、这份汇总里已经不是 triggered 的（最近的在前）。每项 = {ticker, since, last, fill, close, row}。"""
    d = _load(tag)
    now_trig = {str(r.get("ticker")) for r in ((sg or {}).get("rows") or []) if r.get("status") == "triggered"}
    out = [{"ticker": t, **it} for t, it in d["items"].items()
           if d["deleted"].get(t) != it.get("since") and t not in now_trig]
    return sorted(out, key=lambda x: (str(x.get("last")), str(x.get("since"))), reverse=True)


def deleted_now(tag: str) -> set[str]:
    """删掉的、还是这一次信号的票（这份汇总里还 triggered 的也不显示）。"""
    d = _load(tag)
    return {t for t, s in d["deleted"].items() if (d["items"].get(t) or {}).get("since") == s}


def delete(tag: str, ticker: str, since: str) -> tuple[bool, str]:
    """「删除」：这一次信号（since）不再在选股里显示。since 对不上（已经换成新的一次）→ 不删（页面刷新后再看）。"""
    with _LOCK:
        d = _load(tag)
        it = d["items"].get(ticker)
        if not it:
            return False, "没有这只的记录（可能已经删掉了）：刷新页面"
        if str(it.get("since")) != str(since):
            return False, "这只又出了新的买入信号（页面上的是旧的）：刷新页面后再看"
        if d["deleted"].get(ticker) == it.get("since"):
            return True, "已经删掉了"
        d["deleted"][ticker] = it.get("since")
        _save(tag, d)
        return True, "已从选股里删掉（只是不再显示；规则照样按自己的判断买 / 不买）"


def tickers(books=("paper", "tachibana")) -> set[str]:
    """各账本留着显示的票（决算小图要取的范围用）。"""
    out: set[str] = set()
    for b in books:
        d = _load(b)
        out |= {t for t, it in d["items"].items() if d["deleted"].get(t) != it.get("since")}
    return out


def md(day) -> str:
    try:
        x = dt.date.fromisoformat(str(day)[:10])
    except ValueError:
        return str(day or "")
    return f"{x.month}/{x.day}（周{'一二三四五六日'[x.weekday()]}）"


__all__ = ["note", "kept", "deleted_now", "delete", "tickers", "path", "md"]
