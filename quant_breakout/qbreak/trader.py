"""trader.py — 每日收盘后跑一次的交易主流程（第3阶段模拟盘 / 第4阶段实盘共用）。

执行顺序（和回测引擎保持同一套规则，避免"回测赢、实盘输"）：
  0. 券商侧同步 → 读数据 → **数据新鲜度检查**（拿旧 K 线下单是实盘最常见的事故）
  1. 更新持仓跟踪字段（peak / hold_bars），并落盘
  2. 风控 begin：当日熔断、总回撤 HALT、连亏 HALT
  3. 先卖后买（先释放资金，也避免"满仓时错过止损"）
  4. 风控 end：把今日收盘权益存成明日的熔断基准
  5. 写 journal.csv + 通知

幂等（冪等性 / idempotency）：每个订单的 client_id = 交易日-代码-方向。
同一根 K 线重复运行（手滑、任务计划程序重叠触发）不会重复下单 —— 原版没有这层保护。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import notify, paths
from .brokers.base import BaseBroker, Order, Position
from .config import (DataConfig, ExecConfig, RiskConfig, SizingConfig,
                     StrategyParams)
from .data import DataError, load_universe
from .risk import RiskManager
from .strategy import compute_indicators
from .tick import lot_size
from .utils import read_json, setup_logging, write_json

log = setup_logging("trader")


def bar_key_of(bar_date) -> str:
    return str(pd.Timestamp(bar_date).date())


def exit_reason(p: StrategyParams, pos: Position, px: float, dead: bool,
                stop_px: float, trail_px: float, tp_px: float,
                stop_handled_by_broker: bool = False) -> str | None:
    """按收盘价判断是否该离场。优先级：止损 > 跟踪止损 > 止盈 > 死叉 > 超时 > 时间止损。
    stop_handled_by_broker=True 时（已挂逆指値）程序不再重复发止损单。"""
    ret_pct = (px / pos.avg_px - 1) * 100 if pos.avg_px else 0.0
    if not stop_handled_by_broker:
        if px <= stop_px:
            return f"stop(止损 {stop_px:.1f})"
        if px <= trail_px:
            return f"trail(跟踪止损 {trail_px:.1f} 峰值 {pos.peak:.1f})"
    if px >= tp_px:
        return f"take_profit(止盈 {tp_px:.1f})"
    if p.exit_on_macd_dead_cross and dead:
        return "dead_cross(死叉)"
    if p.max_hold_days and pos.hold_bars >= p.max_hold_days:
        return f"max_hold(持有 {pos.hold_bars} 根 K 线)"
    if (p.time_stop_days and pos.hold_bars >= p.time_stop_days
            and ret_pct < p.time_stop_min_ret_pct):
        return f"time_stop(持有 {pos.hold_bars} 日仅 {ret_pct:+.1f}%)"
    return None


# ────────────────────────── 持仓跟踪字段（券商不保存的那部分）──────────────────────────
class PositionBook:
    """券商只告诉你「持有多少股、成本多少」，但跟踪止损需要「入场后的最高价」、
    时间止损需要「持有了几根 K 线」。这些本地字段必须自己持久化 —— 原版把 peak
    放在内存里、每次运行重新用昨天的 High 初始化，跟踪止损因此形同虚设。"""

    def __init__(self, path=None):
        self.path = path or (paths.state_dir() / "position_book.json")
        self.book: dict[str, dict] = read_json(self.path, {}) or {}

    def merge(self, positions: dict[str, Position]) -> dict[str, Position]:
        for t, p in positions.items():
            b = self.book.get(t, {})
            p.peak = max(float(b.get("peak", 0.0)), p.avg_px, p.peak)
            p.stop_px = float(b.get("stop_px", 0.0)) or p.stop_px
            p.entry_date = b.get("entry_date") or p.entry_date or dt.date.today().isoformat()
            p.hold_bars = int(b.get("hold_bars", p.hold_bars))
            p.last_bar = b.get("last_bar", p.last_bar)
        for t in list(self.book):                      # 已平仓的清理掉
            if t not in positions:
                self.book.pop(t)
        return positions

    def update(self, p: Position) -> None:
        # 合并而不是覆盖：守护进程还往这里存逆指値的注文番号等字段，
        # 整个字典替换掉会把它们悄悄抹掉，导致逆指値被反复撤改。
        self.book.setdefault(p.ticker, {}).update(
            {"peak": p.peak, "stop_px": p.stop_px, "entry_date": p.entry_date,
             "hold_bars": p.hold_bars, "last_bar": p.last_bar})

    def drop(self, ticker: str) -> None:
        self.book.pop(ticker, None)

    def save(self) -> None:
        write_json(self.path, self.book)


class OrderGuard:
    """跨进程幂等：记录已发出的 client_id。"""

    def __init__(self, path=None):
        self.path = path or (paths.state_dir() / "sent_orders.json")
        self.ids: dict[str, str] = read_json(self.path, {}) or {}

    def seen(self, cid: str) -> bool:
        return cid in self.ids

    def mark(self, cid: str, info: str) -> None:
        self.ids[cid] = info
        if len(self.ids) > 5000:                       # 保留最近 5000 条
            for k in list(self.ids)[:1000]:
                self.ids.pop(k)
        write_json(self.path, self.ids)


# ────────────────────────── 结果 ──────────────────────────
@dataclass
class DayResult:
    date: str = ""
    equity: float = 0.0
    cash: float = 0.0
    positions: dict = field(default_factory=dict)
    orders: list = field(default_factory=list)
    signals: list = field(default_factory=list)
    blocked: list = field(default_factory=list)
    risk: str = ""
    notes: list = field(default_factory=list)

    def summary(self) -> str:
        L = [f"══ {self.date} 运行结果 ══",
             f"权益 {self.equity:,.0f}   现金 {self.cash:,.0f}   持仓 {self.positions or '无'}",
             self.risk]
        if self.orders:
            L.append("订单:")
            L += [f"  {o['side']} {o['ticker']} x{o['qty']} @{o.get('filled_px') or o['price']:.1f}"
                  f" [{o['status']}] {o.get('note','')}" for o in self.orders]
        if self.signals:
            L.append(f"今日入场信号: {', '.join(self.signals)}")
        if self.blocked:
            L.append("被拦截:")
            L += [f"  {b}" for b in self.blocked]
        if self.notes:
            L += self.notes
        return "\n".join(L)


# ────────────────────────── 主流程 ──────────────────────────
def run_once(universe: list[str], broker: BaseBroker, p: StrategyParams,
             risk_cfg: RiskConfig, sizing: SizingConfig, data_cfg: DataConfig,
             market: str = "JP", dry_run: bool = False, allow_stale: bool = False,
             today: dt.date | None = None, exec_cfg: ExecConfig | None = None,
             protective_stop: bool = False) -> DayResult:
    today = today or dt.date.today()
    res = DayResult(date=today.isoformat())
    p.validate()
    ex = (exec_cfg or ExecConfig.for_market(market)).validate()
    intraday = ex.stop_fill_mode == "intraday"
    book, guard = PositionBook(), OrderGuard()
    rm = RiskManager(risk_cfg)

    # ── 0. 同步 + 取数 ──
    try:
        broker.sync()
    except Exception as e:                                  # noqa: BLE001
        log.error("券商同步失败：%s", e)
        res.notes.append(f"券商同步失败：{e}")
        return res

    held = list(broker.positions())
    tickers = sorted(set(universe) | set(held))
    try:
        data = load_universe(tickers, data_cfg, use_cache=False)
    except DataError as e:
        log.error("取数失败，今日不交易：%s", e)
        res.notes.append(f"取数失败：{e}")
        notify.send("取数失败，今日未交易", str(e), "error")
        return res

    ind = {t: compute_indicators(df, p) for t, df in data.items()}
    bars = {t: df.index[-1] for t, df in ind.items()}
    bar_date = max(bars.values())
    stale_days = (pd.Timestamp(today) - bar_date.normalize()).days
    if stale_days > risk_cfg.stale_data_max_days and not allow_stale:
        msg = (f"最新 K 线 {bar_date.date()} 距今 {stale_days} 天 > "
               f"{risk_cfg.stale_data_max_days}，判定为数据过期，今日不交易。"
               "（收盘后 yfinance 通常延迟 15~30 分钟，建议 16:00 JST 以后运行；"
               "若今天本就是休市日则属正常）")
        log.warning(msg)
        res.notes.append(msg)
        return res

    last_close = {t: float(df["Close"].iloc[-1]) for t, df in ind.items()}
    opens = {t: float(df["Open"].iloc[-1]) for t, df in ind.items()}
    if hasattr(broker, "set_prices"):
        broker.set_prices(last_close)

    # ── 0.5 撮合昨日排队的「次日开盘」订单（与回测引擎的 T+1 开盘成交对齐）──
    if hasattr(broker, "fill_pending"):
        for o in broker.fill_pending(opens, bar_key_of(bar_date), ex.max_entry_gap_pct):
            res.orders.append(o.to_dict())
            if o.status == "FILLED" and o.side == "SELL":
                book.drop(o.ticker)
                rm.on_trade_closed(float(o.extra.get("pnl", 0.0)))
        if hasattr(broker, "set_prices"):
            broker.set_prices(last_close)

    # ── 1. 更新跟踪字段 ──
    positions = book.merge(broker.positions())
    bar_key = bar_key_of(bar_date)
    for t, pos in positions.items():
        row = ind[t].iloc[-1] if t in ind else None
        if row is not None and pos.last_bar != bar_key:
            pos.peak = max(pos.peak or pos.avg_px, float(row["High"]))
            pos.hold_bars += 1
            pos.last_bar = bar_key
            if not pos.stop_px:
                # 与引擎一致：ATR 取**信号日（前一根）**的值，而不是成交当天的
                prev_atr = float(ind[t]["atr"].iloc[-2]) if len(ind[t]) > 1 else np.nan
                pos.stop_px = (pos.avg_px - prev_atr * p.atr_stop_mult
                               if p.atr_stop_mult > 0 and np.isfinite(prev_atr)
                               else pos.avg_px * (1 - p.stop_loss_pct / 100))
        book.update(pos)
        broker.update_position(pos)
    book.save()

    # ── 2. 风控 ──
    equity = broker.equity()
    decision = rm.begin(equity, today)
    res.risk = str(decision)
    log.info("%s", decision)
    if decision.halted:
        notify.send("风控 HALT，今日不交易", "\n".join(decision.reasons), "error")
        res.equity, res.cash = equity, broker.cash()
        res.positions = {t: pos.qty for t, pos in positions.items()}
        return res

    def place(side: str, ticker: str, qty: int, reason: str) -> Order | None:
        cid = f"{bar_key}-{ticker}-{side}"
        if guard.seen(cid):
            res.blocked.append(f"{side} {ticker}: 本交易日已发过同样的单（幂等拦截）")
            return None
        if dry_run:
            res.orders.append({"side": side, "ticker": ticker, "qty": qty,
                               "price": last_close.get(ticker, 0), "status": "DRY_RUN",
                               "note": reason})
            return None
        fn = broker.buy if side == "BUY" else broker.sell
        o = fn(ticker, qty, client_id=cid, ref_px=last_close.get(ticker), bar=bar_key)
        o.note = f"{reason} {o.note}".strip()
        if o.ok:
            guard.mark(cid, f"{o.status} {o.note}")
        res.orders.append(o.to_dict())
        return o

    # ── 3a. 卖出 ──
    for t, pos in list(positions.items()):
        if t not in ind:
            res.blocked.append(f"SELL {t}: 无行情数据，跳过（请人工确认）")
            continue
        row = ind[t].iloc[-1]
        px = last_close[t]
        stop_px = pos.stop_px or pos.avg_px * (1 - p.stop_loss_pct / 100)
        trail_px = pos.peak * (1 - p.trailing_stop_pct / 100) if p.trailing_stop_pct else -np.inf
        if p.trailing_arm_pct and pos.peak < pos.avg_px * (1 + p.trailing_arm_pct / 100):
            trail_px = -np.inf
        tp_px = pos.avg_px * (1 + p.take_profit_pct / 100) if p.take_profit_pct else np.inf
        reason = exit_reason(p, pos, px, bool(row["dead_cross"]),
                             stop_px, trail_px, tp_px,
                             stop_handled_by_broker=intraday and protective_stop)
        if reason:
            o = place("SELL", t, pos.qty, reason)
            if o and o.status == "FILLED":
                pnl = (o.filled_px - pos.avg_px) * o.filled_qty
                rm.on_trade_closed(pnl)
                book.drop(t)
    book.save()

    # ── 3b. 买入 ──
    entry_today = [t for t, df in ind.items()
                   if t in universe and bool(df["entry"].iloc[-1]) and df.index[-1] == bar_date]
    res.signals = entry_today
    if entry_today and not decision.allow_open:
        res.blocked.append(f"熔断中，今日不开仓（信号: {', '.join(entry_today)}）")
    elif entry_today:
        equity = broker.equity()
        for t in sorted(entry_today):
            cur = broker.positions()
            if t in cur:
                continue
            row = ind[t].iloc[-1]
            px = last_close[t]
            stop_px = (px - float(row["atr"]) * p.atr_stop_mult
                       if p.atr_stop_mult > 0 and np.isfinite(row["atr"])
                       else px * (1 - p.stop_loss_pct / 100))
            if sizing.mode == "risk_pct" and px > stop_px:
                budget = equity * (sizing.risk_pct / 100) / (px - stop_px) * px
            else:
                budget = equity * sizing.position_pct
            budget = min(budget, equity * sizing.max_position_pct,
                         broker.cash() * (1 - sizing.cash_buffer_pct / 100),
                         risk_cfg.max_order_value)
            lot = lot_size(t, market)
            qty = int(budget // (px * lot)) * lot
            if qty <= 0:
                res.blocked.append(f"BUY {t}: 预算 {budget:,.0f} 不够 1 单元({lot}股 ≈{px*lot:,.0f})")
                continue
            ok, why = rm.check_order(qty * px, len(cur))
            if not ok:
                res.blocked.append(f"BUY {t}: {why}")
                continue
            o = place("BUY", t, qty, f"entry(range={row['range_pct']:.1f}% "
                                      f"vol×{row['vol_ratio']:.1f})")
            if o and o.ok:
                rm.on_open()
                if o.filled_qty > 0:      # 立即成交（非排队）
                    pos = Position(ticker=t, qty=o.filled_qty, avg_px=o.filled_px or px,
                                   peak=max(o.filled_px or px, float(row["High"])),
                                   stop_px=stop_px, entry_date=bar_key, hold_bars=0,
                                   last_bar=bar_key)
                    book.update(pos)
                    broker.update_position(pos)
                else:
                    res.notes.append(f"{t} 已排队，次日开盘成交（参考止损 {stop_px:.1f}）")
        book.save()

    # ── 3c. 逆指値（protective stop）维护：让盘中止损在实盘真正生效 ──
    if protective_stop and hasattr(broker, "place_protective_stop") and not dry_run:
        for t, pos in broker.positions().items():
            ann = book.book.get(t, {})
            want = max(pos.stop_px or ann.get("stop_px", 0.0),
                       (pos.peak * (1 - p.trailing_stop_pct / 100)) if p.trailing_stop_pct else 0.0)
            if want <= 0:
                continue
            cur = float(ann.get("stop_order_px", 0.0))
            if abs(want - cur) / max(cur, 1e-9) < 0.002:
                continue                                   # 变动不足 0.2%，不折腾
            if ann.get("stop_order_id"):
                broker.cancel(ann["stop_order_id"])
            cid = f"{bar_key}-{t}-STOP"
            o = broker.place_protective_stop(t, pos.qty, want, client_id=cid)
            if o.ok:
                book.book.setdefault(t, {}).update(
                    {"stop_order_id": cid, "stop_order_px": want})
                res.notes.append(f"{t} 逆指値更新至 {want:.1f}")
        book.save()

    # ── 4/5. 收尾 ──
    res.equity, res.cash = broker.equity(), broker.cash()
    res.positions = {t: pos.qty for t, pos in broker.positions().items()}
    if not dry_run:
        rm.end(res.equity, today)
    _journal(res)
    if res.orders or decision.daily_loss_pct <= -abs(risk_cfg.daily_max_loss_pct):
        notify.send(f"{res.date} 交易汇总", res.summary(),
                    "warn" if not decision.allow_open else "info")
    return res


def _journal(res: DayResult) -> None:
    fp = paths.out_dir() / "journal.csv"
    row = pd.DataFrame([{ "date": res.date, "equity": round(res.equity, 2),
                          "cash": round(res.cash, 2),
                          "positions": ";".join(f"{k}:{v}" for k, v in res.positions.items()),
                          "orders": len(res.orders), "signals": ";".join(res.signals),
                          "risk": res.risk }])
    row.to_csv(fp, mode="a", header=not fp.exists(), index=False, encoding="utf-8-sig")


def load_params(path=None) -> StrategyParams:
    """optimize 产出的稳健参数写进 var/best_params.json 就自动生效。"""
    fp = path or paths.params_file()
    try:
        p = StrategyParams.load(fp)
    except Exception as e:                                  # noqa: BLE001
        log.error("best_params.json 读取失败（%s），改用默认参数", e)
        return StrategyParams()
    if p is None:
        log.info("未找到 %s，使用默认参数", fp)
        return StrategyParams()
    log.info("已加载参数 %s", fp)
    return p
