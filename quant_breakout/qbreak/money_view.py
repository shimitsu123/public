"""money_view.py — 账本的「钱」一栏（〔77〕C：UX-10 / T7 / UX-09 / UX-17；面板（Mac + 手机）与 Mac 账本页共用；只读、只展示）。

  summary(tag, book)   → 总权益、当日 / 累计损益（入金不算赚、出金不算亏）、迷你权益曲线、年内已实现损益与预计代扣、最近成交、日志最新一节
  core_name(t, sm)     → 核心 ETF 的名字（执行器汇总 holding_view 里的；没有 → 已知的几只；再没有 → 代码）
数字都来自执行器自己的文件（账本、汇总、日志），不连券商。税只是估算（特定口座、源泉徴収あり），以立花的取引報告書为准。
"""
from __future__ import annotations

from . import paths
from .utils import read_json

CORE_NAMES = {"1545.T": "纳斯达克 100（1545）", "1482.T": "美国 7〜10 年国债・对冲（1482）", "2845.T": "纳斯达克 100・对冲（2845）",
              "1655.T": "S&P500（1655）", "1329.T": "日経225（1329）"}


def sim_capital(default: float = 1_000_000.0) -> float:
    """sim.json 的起始本金（仓库 var/sim.json，07:40 拉代码时同步）；读不了 → default。"""
    try:
        cfg = read_json(paths.PROJECT_ROOT / "var" / "sim.json", {}) or {}
        return float(cfg.get("capital_jpy") or (cfg.get("unified") or {}).get("capital_jpy") or default)
    except (TypeError, ValueError):
        return float(default)


def core_name(t: str, sm: dict | None = None) -> str:
    for r in ((sm or {}).get("holding_view") or {}).get("core") or []:
        if str(r.get("ticker")) == t and r.get("name"):
            return str(r["name"])
    return CORE_NAMES.get(t, t)


def recent_fills(book: dict | None, n: int = 10) -> list[dict]:
    """最近的成交（新的在前）：账本 history 里每天的单（filled_qty > 0）→ {date, side, ticker, kind, qty, px}。"""
    out: list[dict] = []
    for h in reversed((book or {}).get("history") or []):
        for o in h.get("orders") or []:
            q = int(o.get("filled_qty") or 0)
            if q > 0:
                out.append({"date": str(h.get("fill_bar") or ""), "side": o.get("side"), "ticker": str(o.get("ticker")),
                            "kind": o.get("kind") or "stock", "qty": q, "px": float(o.get("filled_px") or 0)})
        if len(out) >= n:
            break
    return out[:n]


def journal_latest(tag: str) -> tuple[str, list[str]] | None:
    """日志（out/live_unified_<账本>_journal.md）最新的一节 →（标题，要点）；没有 → None。"""
    p = paths.out_dir() / f"live_unified_{tag}_journal.md"
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return None
    parts = [x for x in ("\n" + text).split("\n## ") if x.strip() and not x.lstrip().startswith("# ")]
    if not parts:
        return None
    lines = parts[-1].strip().splitlines()
    return lines[0].strip(), [x[2:].strip() for x in lines[1:] if x.startswith("- ")]


def summary(tag: str, book: dict | None, capital: float | None = None, today: str | None = None) -> dict:
    """{eq, day, day_pct, tot, tot_pct, inv, spark: [权益…（最近 60 个）], ytd: {year, gain, withheld, n, stock_gain, core_gain},
    realized: [最近 10 笔已实现（新的在前）], fills: [...], journal: (标题, 要点) | None}。账本没有 → {}。"""
    from . import tax_ytd as TY
    from .live_unified import flows_in_change, invested_jpy, start_capital
    book = book or {}
    st = book.get("state") or {}
    if not st:
        return {}
    cap = start_capital(book, sim_capital() if capital is None else capital)
    hist = st.get("history") or []
    eq = float(hist[-1][1]) if hist else float(st.get("cash_jpy") or 0)
    last_d = str(hist[-1][0]) if hist else None
    prev_d = str(hist[-2][0]) if len(hist) > 1 else None
    inv = invested_jpy(cap, book, last_d)
    day = eq - float(hist[-2][1]) - flows_in_change(book, prev_d, last_d) if len(hist) > 1 else 0.0
    tot = eq - inv
    year = (today or last_d or "")[:4] or None
    y = TY.ytd(st, year) if year else {}
    rows = [r for r in TY.realized(st)][::-1][:10]
    return {"eq": eq, "day": day, "day_pct": (day / (eq - day) * 100) if eq - day else 0.0, "tot": tot,
            "tot_pct": (tot / inv * 100) if inv else 0.0, "inv": inv, "cap": cap,
            "spark": [float(h[1]) for h in hist[-60:]], "ytd": {k: v for k, v in y.items() if k != "rows"},
            "realized": rows, "fills": recent_fills(book), "journal": journal_latest(tag)}


def sparkline(vals: list[float], w: int = 240, h: int = 40) -> str:
    """权益的迷你曲线（内联 SVG；颜色跟着 currentColor）。少于 2 个点 → ""。"""
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    pts = " ".join(f"{i * (w - 2) / (len(vals) - 1) + 1:.1f},{h - 1 - (v - lo) / rng * (h - 2):.1f}" for i, v in enumerate(vals))
    return (f"<svg class='spark' viewBox='0 0 {w} {h}' width='100%' height='{h}' preserveAspectRatio='none' role='img' "
            f"aria-label='最近 {len(vals)} 个交易日的总权益'><polyline fill='none' stroke='currentColor' stroke-width='1.5' points='{pts}'/></svg>")
