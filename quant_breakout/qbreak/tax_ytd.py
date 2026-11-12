"""tax_ytd.py — 特定口座（源泉徴収あり）的年内已实现损益与预计代扣（〔77〕C：T3 / UX-08 / T4 / T7 / UX-09 / UX-18；只展示与提醒）。

账本（live_unified 的 state，dict）里：
  - 个股卖出：state["trades"]（引擎 _exec_exit 记的：exit_date、shares、exit_px、pnl_jpy = 卖价 − 买价 − 买卖手续费）
  - 核心 ETF：state["core_trades"]（[日期, 票, BUY/SELL, 口数, 成交价, 手续费]）→ 按移动平均算每笔卖出的损益（买入手续费进成本）
特定口座的源泉徴収按「年初以来的通算」算：年内累计收益为正时代扣 累计 × 20.315%，之后亏了会退还（还付）。
这里只做估算（不按所得税 / 住民税分开取整），以立花的取引報告書 / 年間取引報告書为准；不影响下单。
按约定日（成交日）分年：年末最后两个交易日的卖出按受渡日算属于下一年（以年間取引報告書为准）。
核心 ETF 的买入记录不全（第一次同步时已有的持仓、拆股后没有成交记录）→ 那只之后的卖出算不了，ytd() 的 incomplete 列出（不猜）。
"""
from __future__ import annotations

TAX_PCT = 20.315                      # 与 qbreak/manual_orders.TAX_PCT 相同（特定口座、源泉徴収あり）


def _rate() -> float:
    return TAX_PCT / 100.0


def _get(st, k: str):
    """账本 dict（state json）或引擎的状态对象（unified 的 State：属性）都能读。"""
    if st is None:
        return None
    return st.get(k) if isinstance(st, dict) else getattr(st, k, None)


def realized(st, bad: set | None = None) -> list[dict]:
    """全部已实现的卖出（日期升序）：{"date", "ticker", "kind": "stock" | "core", "shares", "px", "pnl"（円，含手续费）}。
    核心 ETF 的记录对不上（口数为负等）→ 那只的后面几笔跳过（不猜）。"""
    out: list[dict] = []
    for tr in _get(st, "trades") or []:
        try:
            if str(tr.get("market") or "JP") != "JP":
                continue
            out.append({"date": str(tr["exit_date"])[:10], "ticker": str(tr["ticker"]), "kind": "stock",
                        "shares": int(tr.get("shares") or 0), "px": float(tr.get("exit_px") or 0),
                        "pnl": float(tr.get("pnl_jpy", tr.get("pnl")) or 0)})
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    book: dict[str, list] = {}                        # 票 → [口数, 成本（含买入手续费）]
    bad = set() if bad is None else bad               # 记录对不上的核心 ETF（之后的卖出算不了 → 调用方标出「不完整」）
    for row in _get(st, "core_trades") or []:
        try:
            d, t, side, u, px, f = row[:6]
            u, px, f = int(u), float(px), float(f or 0)
        except (TypeError, ValueError):
            continue
        if t in bad or u <= 0:
            continue
        units, cost = book.get(t, [0, 0.0])
        if side == "BUY":
            book[t] = [units + u, cost + u * px + f]
        elif side == "SELL":
            if u > units:                             # 记录不全：成本算不了
                bad.add(t)
                continue
            part = cost * u / units
            out.append({"date": str(d)[:10], "ticker": str(t), "kind": "core", "shares": u, "px": px,
                        "pnl": u * px - f - part})
            book[t] = [units - u, cost - part]
    out.sort(key=lambda r: (r["date"], r["kind"], r["ticker"]))
    return out


def withheld(cum_gain: float) -> float:
    """年内累计收益 → 到那时为止的累计代扣（≥ 0；亏损时为 0 = 之前扣的全部还回）。"""
    return max(0.0, float(cum_gain)) * _rate()


def ytd(st: dict | None, year: int | str, upto: str | None = None) -> dict:
    """year 年（1/1 起，到 upto 为止，含当天）的汇总：
    {"year", "gain"（已实现损益合计，円）, "withheld"（预计累计代扣）, "n"（卖出笔数）, "stock_gain", "core_gain", "rows"}"""
    y = str(year)
    bad: set = set()
    rows = [r for r in realized(st, bad) if r["date"][:4] == y and (upto is None or r["date"] <= upto)]
    g = sum(r["pnl"] for r in rows)
    return {"year": int(y), "gain": round(g), "withheld": round(withheld(g)), "n": len(rows), "incomplete": sorted(bad),
            "stock_gain": round(sum(r["pnl"] for r in rows if r["kind"] == "stock")),
            "core_gain": round(sum(r["pnl"] for r in rows if r["kind"] == "core")), "rows": rows}


def withheld_change(st: dict | None, start: str, end: str) -> float:
    """start〜end（含两端，同一年内）卖出造成的预计代扣变化（円；正 = 多扣、负 = 还付）。跨年时只算 end 那一年（年初重新算）。"""
    y = end[:4]
    rows = [r for r in realized(st) if r["date"][:4] == y]
    before = sum(r["pnl"] for r in rows if r["date"] < start)
    after = sum(r["pnl"] for r in rows if r["date"] <= end)
    return withheld(after) - withheld(before if start[:4] == y else 0.0)


def sale_effect(st: dict | None, gain: float, day: str) -> float:
    """假设 day 这天再卖出一笔收益 gain（円）：预计代扣的变化（正 = 这笔要扣多少、负 = 退还多少）。按 day 那一年、到 day 为止的累计。"""
    cum = ytd(st, day[:4], upto=day)["gain"]
    return withheld(cum + float(gain)) - withheld(cum)


def after_tax(st: dict | None, tot: float, today: str) -> dict:
    """税后累计损益（估算；2026-10-11 用户「总览里要加上税后的盈利」）：
    累计损益 tot（账本的权益 − 投入本金，税前：账本里的现金不扣譲渡益税）
      − 历年已实现收益的代扣（每年 1/1 重新通算：那一年的已实现合计为正 → × 20.315%，为负 → 0）
      − 现在全部卖出还要多扣的（今年已实现 + 持仓的含み損益 一起通算后的代扣 − 今年已经扣的；含み損 → 负数 = 退还）。
    含み損益：个股 = 股数 ×（最近收盘 − 买入价），核心 ETF = 口数 × 最近价格 − 移动平均成本（含买入手续费）；卖出手续费不算。
    → {"after", "paid", "extra", "unreal", "by_year": {年: 已实现}, "incomplete": [...]}"""
    from .manual_orders import core_cost
    st = st or {}
    bad: set = set()
    by: dict[str, float] = {}
    for r in realized(st, bad):
        by[r["date"][:4]] = by.get(r["date"][:4], 0.0) + r["pnl"]
    paid = sum(withheld(g) for g in by.values())
    unreal = 0.0
    for t, p in (st.get("pos") or {}).items():
        try:
            px = float(p.get("last_close") or p.get("entry_px") or 0)
            unreal += int(p.get("shares") or 0) * (px - float(p.get("entry_px") or 0))
        except (TypeError, ValueError, AttributeError):
            bad.add(str(t))
    for t, u in (st.get("core_units") or {}).items():
        if int(u or 0) <= 0:
            continue
        c = core_cost(st, t)
        px = float((st.get("core_last") or {}).get(t) or 0)
        if c is None or px <= 0:
            bad.add(str(t))
            continue
        unreal += int(u) * px - float(c["cost"])
    g = by.get(str(today)[:4], 0.0)
    extra = withheld(g + unreal) - withheld(g)
    return {"after": round(float(tot) - paid - extra), "paid": round(paid), "extra": round(extra), "unreal": round(unreal),
            "by_year": {y: round(v) for y, v in sorted(by.items())}, "incomplete": sorted(bad)}
