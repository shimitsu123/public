"""exec_quality.py — 执行质量汇总（〔77〕C LU-18；只读，不改规则）：上线头几周判断「能不能加到计划金额」时看（配合〔77〕E1 开户后定的判定条件）。

数据都在账本里：history（每天的单：ref_px、limit、filled_qty、filled_px、status）、compare_history（与云端模拟盘逐日比较）。
  - 成交价差（bp，对你不利为正）：买 = 成交价 / 参考价 − 1；卖 = 1 − 成交价 / 参考价（参考价 = 决策日收盘；个股买单 = 信号日收盘）
  - 没成交 / 部分成交 / 被挡 / 被拒 / 放弃 / 状态不明 的次数，成交率（成交股数 / 发出股数）
  - 与云端模拟盘：比较了几天、一致几天、最近一次不一致
"""
from __future__ import annotations

from statistics import mean, median

BAD = ("BLOCKED", "REJECTED", "ERROR", "SENDING", "MISSED", "SKIPPED", "EXPIRED", "UNFILLED", "CANCELLED")


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def report(book: dict | None, since: str | None = None) -> dict:
    """{days, orders, filled, fill_rate, status: {状态: 次数}, slip: {BUY/SELL: {n, mean_bp, median_bp, worst_bp}},
    compare: {n, same, last_diff}}。since：只算这天（成交日）之后的。"""
    book = book or {}
    days = [h for h in book.get("history") or [] if not since or str(h.get("fill_bar") or "") >= since]
    status: dict[str, int] = {}
    sent = got = 0
    slips: dict[str, list[float]] = {"BUY": [], "SELL": []}
    n = 0
    for h in days:
        for o in h.get("orders") or []:
            n += 1
            s = str(o.get("status") or "")
            status[s] = status.get(s, 0) + 1
            q = int(_f(o.get("sent_qty") or o.get("qty")))
            fq = int(_f(o.get("filled_qty")))
            if s not in ("BLOCKED", "SKIPPED", "MISSED", "PLANNED", "DEFERRED"):
                sent += q
                got += min(fq, q) if q else fq
            ref, px = _f(o.get("ref_px")), _f(o.get("filled_px"))
            if fq > 0 and ref > 0 and px > 0 and o.get("side") in slips:
                bp = (px / ref - 1) * 1e4 if o["side"] == "BUY" else (1 - px / ref) * 1e4
                slips[o["side"]].append(bp)
    sl = {k: ({"n": len(v), "mean_bp": round(mean(v), 1), "median_bp": round(median(v), 1), "worst_bp": round(max(v), 1)}
              if v else {"n": 0}) for k, v in slips.items()}
    ch = [c for c in book.get("compare_history") or [] if c.get("comparable") and (not since or str(c.get("date")) >= since)]
    diff = [c for c in ch if not c.get("same")]
    return {"days": len(days), "orders": n, "filled": sum(1 for h in days for o in h.get("orders") or [] if _f(o.get("filled_qty")) > 0),
            "fill_rate": round(got / sent * 100, 1) if sent else None, "status": status, "slip": sl,
            "compare": {"n": len(ch), "same": len(ch) - len(diff), "last_diff": diff[-1].get("date") if diff else None}}


def lines(r: dict) -> list[str]:
    out = [f"统计 {r['days']} 个成交日、{r['orders']} 笔单：成交 {r['filled']} 笔"
           + (f"，成交率 {r['fill_rate']:.1f}%（成交股数 / 发出股数）" if r.get("fill_rate") is not None else "")]
    bad = {k: v for k, v in (r.get("status") or {}).items() if k in BAD}
    if bad:
        from .broker_snapshot import STATUS_ZH
        out.append("没成交 / 被挡等：" + "、".join(f"{STATUS_ZH.get(k, k)} {v} 次" for k, v in sorted(bad.items())))
    for side, name in (("BUY", "买"), ("SELL", "卖")):
        s = (r.get("slip") or {}).get(side) or {}
        if s.get("n"):
            out.append(f"{name}的成交价差（对你不利为正，bp = 0.01%）：平均 {s['mean_bp']:+.1f} bp、中位 {s['median_bp']:+.1f} bp、"
                       f"最差 {s['worst_bp']:+.1f} bp（{s['n']} 笔；参考价 = 决策日 / 信号日收盘，含开盘跳空）")
    c = r.get("compare") or {}
    if c.get("n"):
        out.append(f"与云端模拟盘：比较 {c['n']} 天、一致 {c['same']} 天" + (f"，最近一次不一致 {c['last_diff']}" if c.get("last_diff") else ""))
    out.append("只读汇总；加到计划金额的判定条件按〔77〕E1（开户后由你定）。非投资建议。")
    return out
