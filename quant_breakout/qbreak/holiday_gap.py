"""holiday_gap.py — 东证休市期间（周末 / 祝日 / 年末年始）日経225先物的涨跌 → 下一个开盘的跳空参考（只展示，不改交易）。

2026-09-29 用户：「休息的时候没有交易的话要参照日经225指数主连指数」。
- 个股的日 / 周 / 月线不能拿指数先物去补休市日：那天个股没有成交，补进去的价格 / 成交量是假的
  （2026-09-28 去掉的 Yahoo 休市假行就是这种：把量比做高、按旧价成交）。
- 但先物在东证休市时照常交易（CME 的日経225先物几乎全天；大阪 2022-09-23 起有祝日取引，属于下一个营业日的取引日，
  J-Quants 要 Premium 才有先物数据），它的涨跌会在休市后第一个开盘兑现 → 这里只用来提示「今天开盘大概会跳多少」。
- 历史（scripts/holiday_gap_study.py → var/holiday_gaps.json，2006〜2026 日経225 225 只；只描述）：
  中间有休市平日时 CME 涨 > 2% → 平均约 29% 的票高开 3% 以上（个股买单限价 = 信号收盘 ×1.03，多半成交不了）；
  跌 < −2% → 约 23% 的票低开 3% 以上（卖单照常寄付成交）。交易规则（跳空 > 3% 不买）不变。
数据：Yahoo 的 NIY=F（CME 日経225 円建て先物）与 ^N225；取不到就不显示（不影响日报其它部分）。
"""
from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from . import paths

FUT, IDX = "NIY=F", "^N225"
HIST_FILE = "holiday_gaps.json"


def closed_weekdays(bar_date: dt.date, fill: dt.date) -> list[dt.date]:
    """bar_date 与成交日之间东证休市的平日（祝日 / 年末年始 / 临时休市）。"""
    from .calendar_jp import is_trading_day
    out, d = [], bar_date + dt.timedelta(days=1)
    while d < fill:
        if d.weekday() < 5 and not is_trading_day(d):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _yf_close(ticker: str) -> pd.Series:
    import logging

    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    h = yf.Ticker(ticker).history(period="1mo", auto_adjust=False)
    s = h["Close"].astype(float)
    s.index = pd.DatetimeIndex(s.index.tz_localize(None) if s.index.tz is not None else s.index).normalize()
    return s[s > 0]


def load_hist() -> dict:
    try:
        return json.loads((paths.PROJECT_ROOT / "var" / HIST_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def bucket(pct: float, hist: dict, holiday: bool) -> dict | None:
    """历史上同一档（CME 变化 ≤ −2% / −2〜+2% / ≥ +2%）重开那天的个股跳空统计；holiday = 中间有东证休市的平日。"""
    rows = (hist.get("holiday" if holiday else "normal") or {}).get("buckets") or []
    for b in rows:
        if b["lo"] < pct <= b["hi"]:
            return b
    return None


def panel(bar_date: str | None, today: dt.date, fetch=None, hist: dict | None = None) -> dict | None:
    """日报用：{bar_date, fill, closed, n225, niy, niy_date, pct, holiday, hist}；取不到行情 → None。"""
    if not bar_date:
        return None
    from .calendar_jp import next_trading_day
    b = dt.date.fromisoformat(str(bar_date)[:10])
    fill = next_trading_day(b)
    fetch = fetch or _yf_close
    try:
        n, f = fetch(IDX), fetch(FUT)
    except Exception:                                           # noqa: BLE001
        return None
    n = n[n.index <= pd.Timestamp(b)]
    f = f[f.index < pd.Timestamp(fill)]                     # 成交日之前结束的 CME 交易日（成交日那一段 07:00 JST 才开始；与研究同一口径）
    if not len(n) or not len(f) or n.index[-1].date() != b or f.index[-1].date() < b:
        return None
    pct = float(f.iloc[-1] / n.iloc[-1] - 1)
    closed = closed_weekdays(b, fill)
    hist = load_hist() if hist is None else hist
    return {"bar_date": b.isoformat(), "fill": fill.isoformat(), "closed": [d.isoformat() for d in closed],
            "n225": round(float(n.iloc[-1]), 2), "niy": round(float(f.iloc[-1]), 2), "niy_date": f.index[-1].date().isoformat(),
            "pct": round(pct * 100, 2), "holiday": bool(closed), "hist": bucket(pct, hist, bool(closed))}


def html(p: dict | None) -> str:
    """日报「09:00 日本开盘」下面的一行（只展示）。"""
    if not p:
        return ""
    from html import escape
    wd = "月火水木金土日"
    fill = dt.date.fromisoformat(p["fill"])
    hol = ""
    if p["closed"]:
        ds = "、".join(f"{dt.date.fromisoformat(x):%m/%d}（{wd[dt.date.fromisoformat(x).weekday()]}）" for x in p["closed"])
        hol = f"★ 其间东证休市 {ds}；"
    warn = " <b>≥ 3%：个股买单（限价 = 信号收盘 ×1.03）多半成交不了</b>" if p["pct"] >= 3 else (
        " <b>≤ −3%：今天开盘多半大幅低开（卖单照常寄付）</b>" if p["pct"] <= -3 else "")
    h = p.get("hist")
    ht = (f"；历史上同一档（{'有' if p['closed'] else '没有'}休市平日、CME {h['label']}）重开那天个股跳空中位 {h['med']:+.2f}%、"
          f"高开 3% 以上的票平均 {h['up3']:.1f}%、低开 3% 以上 {h['dn3']:.1f}%（{h['n']} 天）") if h else ""
    return (f"<p class='muted'>{hol}日経225先物（CME 円建て NIY=F，{escape(p['niy_date'])} 的交易日）{p['niy']:,.0f} 円 ÷ 东证 "
            f"{escape(p['bar_date'])} 收盘 {p['n225']:,.0f} 円 = <b>{p['pct']:+.2f}%</b>（含期现基差，通常 ±0.5% 以内）→ "
            f"{fill:%m/%d}（{wd[fill.weekday()]}）开盘的跳空参考{ht}。{warn}只展示，交易规则不变（跳空 > 3% 不买）。</p>")
