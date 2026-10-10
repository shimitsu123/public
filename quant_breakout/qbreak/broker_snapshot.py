"""broker_snapshot.py — 「立花那边实际是什么」快照 + 当天的成交（〔77〕C：UX-07 / TA-06 / UX-06 / TA-14；只读、只展示）。

数据目录 out/broker_snapshot_<账本>.json（~/.qbreak/home，不入库；不含账户号、认证 ID、密钥、虚拟 URL）：
  {"at", "book", "source", "positions": [{ticker, qty, avg_px}], "buying_power", "quotes": {ticker: px}, "quotes_at",
   "orders": [注文一覧的今天的行], "fills": [账本里今天的单在立花的成交], "compare": [账本 vs 立花 逐只]}
两个来源：
  ① 执行器每次核对券商（check_broker）→ 持仓 + 余力（record_check；不多调 API）
  ② bash scripts/liveu.sh broker（只读，拿账本运行锁 + 立花本番会话锁）→ ① + 注文一覧 + 今天每笔单的约定（order_status）+ 立花现价；
     立花本番装好后 LaunchAgent com.qbreak.liveu.broker 在 11:35 / 15:45 跑一次并发「今天的成交」通知。
不改账本、不改模型状态（正式记账仍在第二天 07:40 的对账）；面板只读这个文件，本身不连立花。
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import paths
from .calendar_jp import JST
from .utils import read_json, write_json

LIVE_STATUSES = ("SENT", "PARTIAL", "SENDING", "ERROR")   # 发出去了、可能还在交易所里的
STATUS_ZH = {"PLANNED": "计划中", "SENDING": "发送中（状态不明）", "SENT": "已发出", "FILLED": "已成交", "PARTIAL": "部分成交",
             "UNFILLED": "没成交", "DEFERRED": "开盘后再下", "MISSED": "错过", "SKIPPED": "放弃", "BLOCKED": "被挡（没发）",
             "REJECTED": "被拒", "EXPIRED": "已失效", "ERROR": "状态不明", "RESOLVED": "已登记", "CANCELLED": "已撤"}


def path(tag: str) -> Path:
    return paths.out_dir() / f"broker_snapshot_{tag}.json"


def _now() -> dt.datetime:
    return dt.datetime.now(JST)


def load(tag: str) -> dict:
    return read_json(path(tag), {}) or {}


def _positions(held: dict) -> list[dict]:
    out = []
    for t, p in sorted((held or {}).items()):
        q = int(getattr(p, "qty", 0) or 0)
        if q:
            out.append({"ticker": t, "qty": q, "avg_px": round(float(getattr(p, "avg_px", 0) or 0), 4)})
    return out


def compare(ledger_book: dict | None, positions: list[dict]) -> list[dict]:
    """账本（模型）的持仓 vs 立花：逐只 {ticker, ledger, broker, diff}（diff ≠ 0 的页面标红）。"""
    st = (ledger_book or {}).get("state") or {}
    led: dict[str, int] = {}
    for t, p in (st.get("pos") or {}).items():
        try:
            led[t] = int((p or {}).get("shares") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
    for t, u in (st.get("core_units") or {}).items():
        try:
            led[t] = led.get(t, 0) + int(u or 0)
        except (TypeError, ValueError):
            continue
    brk = {r["ticker"]: int(r["qty"]) for r in positions}
    rows = []
    for t in sorted(set(led) | set(brk)):
        a, b = led.get(t, 0), brk.get(t, 0)
        if a or b:
            rows.append({"ticker": t, "ledger": a, "broker": b, "diff": b - a})
    return rows


def record_check(tag: str, held: dict, buying_power: float, ledger_book: dict | None = None) -> None:
    """执行器核对券商时顺便记一份（只有持仓 + 余力；不另外调 API）。保留上一次 liveu.sh broker 记的注文 / 成交 / 现价（标上它们的时刻）。"""
    old = load(tag)
    pos = _positions(held)
    snap = {k: old[k] for k in ("orders", "orders_at", "fills", "fills_at", "quotes", "quotes_at") if k in old}
    snap.update({"at": _now().strftime("%Y-%m-%d %H:%M:%S"), "book": tag, "source": "执行器核对",
                 "positions": pos, "buying_power": round(float(buying_power), 0), "compare": compare(ledger_book, pos)})
    write_json(path(tag), snap)


def _num(v, typ=float):
    try:
        return typ(float(v))
    except (TypeError, ValueError):
        return typ(0)


def parse_orders(rows: list[dict], spec) -> list[dict]:
    """注文一覧（CLMOrderList）的行 → 只留页面要的字段（不带账户、密钥类字段）。"""
    out = []
    for r in rows or []:
        code = str(r.get(spec.r_list_code) or "").strip()
        if not code:
            continue
        side = str(r.get(spec.r_list_side) or "").strip()
        fq = _num(r.get(spec.r_list_filled_qty), int)
        st_code = str(r.get(spec.r_list_status_code) or "").strip()
        out.append({"ticker": f"{code}.T", "side": "BUY" if side == spec.side_buy else "SELL" if side == spec.side_sell else side,
                    "qty": _num(r.get(spec.r_list_qty), int), "price": _num(r.get(spec.r_list_price)),
                    "filled_qty": fq, "filled_px": _num(r.get(spec.r_list_filled_px)) if fq else 0.0,
                    "status": str(r.get(spec.r_list_status) or "") or (getattr(spec, "status_names", None) or {}).get(st_code, st_code),
                    "order_no": str(r.get(spec.r_list_order_no) or "").strip(), "time": str(r.get(spec.r_list_time) or "")[8:12]})
    return out


def today_orders(ledger_book: dict | None, day: dt.date) -> list[dict]:
    """账本里今天发出的单（有注文番号的）。"""
    out = []
    for o in (ledger_book or {}).get("orders") or []:
        if not o.get("broker_id"):
            continue
        od = str(o.get("order_date") or "")
        sent = str(o.get("sent_at") or "")[:10]
        if od.replace("-", "")[:8] == day.strftime("%Y%m%d") or sent == day.isoformat():
            out.append(o)
    return out


def fills_today(broker, ledger_book: dict | None, day: dt.date) -> list[dict]:
    """账本里今天的每笔单 → 立花的约定（order_status；只读）。读不了的那笔写 error，不猜。"""
    out = []
    for o in today_orders(ledger_book, day):
        row = {"cid": o.get("cid"), "ticker": o.get("ticker"), "side": o.get("side"), "kind": o.get("kind") or "stock",
               "qty": int(o.get("sent_qty") or o.get("qty") or 0), "ledger_status": o.get("status")}
        try:
            r = broker.order_status(o["broker_id"], o.get("order_date") or "")
            row.update({"filled_qty": int(r.get("filled_qty") or 0), "avg_px": float(r.get("avg_px") or 0),
                        "status": str(r.get("status") or ""), "final": str(r.get("final") or "")})
        except Exception as e:                            # noqa: BLE001
            row["error"] = type(e).__name__
        out.append(row)
    return out


def refresh(broker, tag: str, ledger_book: dict | None, managed: set | None = None) -> dict:
    """liveu.sh broker：持仓 + 余力 + 注文一覧 + 今天的约定 + 立花现价（持仓与今天的单的票）→ 写快照并返回。"""
    now = _now()
    held = broker.positions()
    bp = float(broker.cash())
    pos = _positions(held)
    spec = getattr(broker, "spec", None)
    orders = parse_orders(broker.open_orders() or [], spec) if spec is not None else []
    fills = fills_today(broker, ledger_book, now.date())
    want = sorted({r["ticker"] for r in pos} | {f["ticker"] for f in fills if f.get("ticker")})
    quotes = {}
    if want and hasattr(broker, "quotes"):
        try:
            quotes = {t: round(float(v), 4) for t, v in (broker.quotes(want) or {}).items() if v}
        except Exception:                                 # noqa: BLE001  现价只是展示
            quotes = {}
    stamp = now.strftime("%Y-%m-%d %H:%M:%S")
    snap = {"at": stamp, "book": tag, "source": "liveu.sh broker", "positions": pos, "buying_power": round(bp, 0),
            "orders": orders, "orders_at": stamp, "fills": fills, "fills_at": stamp, "quotes": quotes, "quotes_at": stamp,
            "compare": compare(ledger_book, pos),
            "foreign": sorted(r["ticker"] for r in pos if managed is not None and r["ticker"] not in managed)}
    write_json(path(tag), snap)
    return snap


def fills_lines(snap: dict) -> list[str]:
    """今天的成交（通知 / 命令行）：一笔一行。"""
    out = []
    for f in snap.get("fills") or []:
        unit = "口" if f.get("kind") == "core" else "股"
        side = "买" if f.get("side") == "BUY" else "卖"
        if f.get("error"):
            out.append(f"・{side} {f.get('ticker')} {f.get('qty'):,} {unit}：读不了约定（{f['error']}）→ 去立花网站看")
        elif int(f.get("filled_qty") or 0) > 0:
            out.append(f"・{side} {f.get('ticker')} 成交 {int(f['filled_qty']):,}/{f.get('qty'):,} {unit} @ ¥{float(f['avg_px']):,.1f}"
                       + (f"（{f['status']}）" if f.get("status") else ""))
        else:
            out.append(f"・{side} {f.get('ticker')} {f.get('qty'):,} {unit}：还没成交" + (f"（{f['status']}）" if f.get("status") else ""))
    return out


def diff_lines(snap: dict) -> list[str]:
    bad = [r for r in snap.get("compare") or [] if r.get("diff")]
    return [f"・{r['ticker']}：账本 {r['ledger']:,} / 立花 {r['broker']:,}（差 {r['diff']:+,}）" for r in bad]
