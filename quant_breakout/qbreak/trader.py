"""trader.py — 每日收盘后跑一次的交易主流程（第3阶段模拟盘 / 第4阶段实盘共用）。

执行顺序（和回测引擎保持同一套规则，避免"回测赢、实盘输"）：
  0. 券商侧同步 → 读数据 → **数据新鲜度检查**（拿旧 K 线下单是实盘最常见的事故）
  1. 更新持仓跟踪字段（peak / hold_bars），并落盘
  2. 风控 begin：当日熔断、总回撤 HALT、连亏 HALT
  3. 先卖后买（先释放资金，也避免"满仓时错过止损"）；买入在收盘时就定好股数 / 名额 / 资金，
     规则与回测引擎第 4、5 步逐条相同（预计可用资金含排队卖出的净额；核心指数仓位用 core.core_orders）
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
from .brokers.base import BaseBroker, Order, Position, state_tag
from .config import (DataConfig, ExecConfig, RiskConfig, SizingConfig,
                     StrategyParams)
from .core import core_orders
from .fees import side_fee
from .data import DataError, load_universe
from .risk import RiskManager
from .strategy import compute_indicators
from .tick import limit_lock, lot_size
from .utils import read_json, setup_logging, write_json

log = setup_logging("trader")


def bar_key_of(bar_date) -> str:
    return str(pd.Timestamp(bar_date).date())


def _earnings_days(provider, ticker: str, today: dt.date) -> int | None:
    """距下次决算的交易日数；无数据源或取不到 → None（不拦截，但也不假装知道）。"""
    if provider is None:
        return None
    try:
        d = provider.next_earnings(ticker)
    except Exception:                                   # noqa: BLE001
        return None
    if d is None:
        return None
    from .events import trading_days_until
    return trading_days_until(d, today)


def market_session_closed(market: str, now: dt.datetime | None = None) -> tuple[dt.date, bool]:
    """返回 (该市场的"今天", 今天的交易时段是否已经收盘)。"""
    from zoneinfo import ZoneInfo
    if market.upper() == "JP":
        from .calendar_jp import now_jst, session_of
        n = now or now_jst()
        return n.date(), session_of(n) in ("post", "closed")
    et = (now or dt.datetime.now(ZoneInfo("America/New_York"))).astimezone(ZoneInfo("America/New_York"))
    return et.date(), et.weekday() >= 5 or et.time() >= dt.time(16, 0)


def drop_partial_bar(df, market: str, now: dt.datetime | None = None):
    """yfinance 在盘中会把**还没收盘的当日 K 线**也返回。用它算信号等于偷看未来的一半。
    若最后一根 K 线的日期 = 该市场的今天，且今天尚未收盘 → 丢掉这根。"""
    if df is None or len(df) == 0:
        return df
    today, closed = market_session_closed(market, now)
    last = df.index[-1]
    if hasattr(last, "date") and last.date() == today and not closed:
        log.info("[%s] 丢弃未收盘的当日 K 线 %s", market, today)
        return df.iloc[:-1]
    return df


def expected_last_bar(today: dt.date, market: str) -> dt.date:
    """按交易日历，今天运行时"应该已经拿到"的最新 K 线日期。
    收盘前/开盘前运行 → 上一交易日；日本用祝日カレンダー，美股用工作日并容忍 1 个假日。
    原版用「距今自然日 ≤ 1」，周一早上（最新 K 线是周五）就会误判为过期。"""
    from .calendar_jp import is_trading_day, now_jst, prev_trading_day, session_of
    if market.upper() == "JP":
        # 收盘后（post）且今天是交易日 → 今天的 K 线应已生成；否则是上一交易日
        if is_trading_day(today) and session_of(now_jst()) == "post" and now_jst().date() == today:
            return today
        return prev_trading_day(today)
    # US：上一工作日；美国假日没有单独日历，多容忍一个工作日
    d = today - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    d2 = d - dt.timedelta(days=1)
    while d2.weekday() >= 5:
        d2 -= dt.timedelta(days=1)
    return d2


def _apply_corp_actions(provider, broker, book, ind: dict, bar_key: str, market: str, res) -> None:
    """把 (上一根已处理 K 线, 本根 K 线] 之间的除息 / 拆股补到持仓与排队订单上。
    provider 取不到数据时：只用「昨天记下的真实收盘 vs 今天的复权收盘」兜底识别拆股（分红金额无法可靠推断，跳过）。"""
    from .corpactions import DIV_NET, due, infer_split
    held = broker.positions()
    pend = broker.pending() if hasattr(broker, "pending") else []
    after_of: dict[str, str] = {}
    for t in held:
        lb = (book.book.get(t) or {}).get("last_bar") or held[t].last_bar
        if lb:
            after_of[t] = lb
    for o in pend:
        after_of.setdefault(o["ticker"], o.get("bar", ""))
    for t, after in after_of.items():
        if not after or after >= bar_key:
            continue
        try:
            acts = due(provider, t, after, bar_key)
        except Exception as e:                              # noqa: BLE001
            acts = []
            b = book.book.get(t) or {}
            df = ind.get(t)
            if df is not None and b.get("last_close"):
                ts = pd.Timestamp(after)
                if ts in df.index:
                    k = infer_split(float(b["last_close"]), float(df.loc[ts, "Close"]))
                    if k:
                        acts = [{"date": bar_key, "dividend": 0.0, "split": k}]
            log.warning("[%s] %s 公司行为数据取不到（%s）%s", market, t, e,
                        f"，按价格比推断拆股 1:{acts[0]['split']:g}" if acts else "，本次跳过")
        for a in acts:
            k, dv = float(a.get("split") or 0), float(a.get("dividend") or 0)
            b = book.book.get(t)
            if b:
                if k > 0 and abs(k - 1) > 1e-9:
                    for f in ("peak", "stop_px", "last_close"):
                        if b.get(f):
                            b[f] = float(b[f]) / k
                if dv > 0 and t in held:
                    for f in ("peak", "stop_px"):
                        if b.get(f):
                            b[f] = max(0.0, float(b[f]) - dv)
            note = None
            if hasattr(broker, "apply_corporate_action"):
                note = broker.apply_corporate_action(t, a["date"], dividend=dv, split=k,
                                                     div_net=DIV_NET.get(market.upper(), 1.0))
            elif k or dv:
                note = (f"株式分割 1:{k:g}" if k else "") + (f" 配当落ち {dv:g}" if dv else "") + "（止损/峰值已同步调整）"
            if note:
                res.notes.append(f"{t} {a['date']}：{note}")
                log.info("[%s] %s %s：%s", market, t, a["date"], note)
    book.save()


def exit_reason(p: StrategyParams, pos: Position, px: float, dead: bool,
                stop_px: float, trail_px: float, tp_px: float,
                stop_handled_by_broker: bool = False, climax: bool = False,
                earnings_in_days: int | None = None) -> str | None:
    """按收盘价判断是否该离场。优先级：止损 > 跟踪止损 > 止盈 > 出货日 > 死叉 > 决算前 > 超时 > 时间止损。
    stop_handled_by_broker=True 时（已挂逆指値）程序不再重复发止损单。"""
    ret_pct = (px / pos.avg_px - 1) * 100 if pos.avg_px else 0.0
    if not stop_handled_by_broker:
        if px <= stop_px:
            return f"stop(止损 {stop_px:.1f})"
        if px <= trail_px:
            return f"trail(跟踪止损 {trail_px:.1f} 峰值 {pos.peak:.1f})"
    if px >= tp_px:
        return f"take_profit(止盈 {tp_px:.1f})"
    if p.exit_on_climax and climax and ret_pct >= p.climax_min_gain_pct:
        return f"climax(高位放量陰線，浮盈 {ret_pct:+.1f}%)"
    if p.exit_on_macd_dead_cross and dead:
        return "dead_cross(死叉)"
    if p.exit_before_earnings and earnings_in_days is not None and earnings_in_days <= 1:
        return f"pre_earnings(决算前 {earnings_in_days} 日)"
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

    @classmethod
    def for_broker(cls, broker) -> "PositionBook":
        return cls(paths.state_dir() / f"position_book{state_tag(broker)}.json")

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

    @classmethod
    def for_broker(cls, broker) -> "OrderGuard":
        """每种券商各记各的：同一台机器上模拟盘与实盘同时跑，也不会互相把对方的单当成「已发过」。"""
        return cls(paths.state_dir() / f"sent_orders{state_tag(broker)}.json")

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
    bar_date: str = ""         # 数据所代表的交易日（报表按这个归档，而不是运行日）
    fill_date: str = ""            # 新仓的 T+1 成交日（宏观事件窗口用）
    equity: float = 0.0
    cash: float = 0.0
    positions: dict = field(default_factory=dict)
    orders: list = field(default_factory=list)
    signals: list = field(default_factory=list)
    blocked: list = field(default_factory=list)
    risk: str = ""
    notes: list = field(default_factory=list)
    core: dict = field(default_factory=dict)       # 核心指数仓位：份额 / 市值 / 目标 / 今晚排的单

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
             protective_stop: bool = False, entry_scale: float = 1.0,
             index_close=None, earnings=None, ticker_mult: dict | None = None,
             entry_block=None, corp_actions=None, force_exit_all: str | None = None,
             core: dict | None = None, account: str | None = None) -> DayResult:
    """entry_scale：市场级新仓倍数（regime / 汇率 / 宏观取 min）；ticker_mult：{票: 板块倾斜倍数}；
    entry_block：字符串 = 今日所有新仓被拦的原因；可调用对象 = f(成交日) -> 原因或 None，
    成交日由本函数按真实最新 K 线 + 交易日历算出（T+1 开盘），避免估算偏差。
    core：核心指数仓位（None = 关闭）。{"ticker": "1329.T", "bear": bool, "buffer_pct", "band_pct",
      "slip_pct", "buy_fee_pct", "sell_fee_pct", "sell_fee_max", "lot"}；不受个股止损 / 熊市清仓规则影响，
      由 core.core_orders 按「权益 − 个股 − 明天要买的个股」决定份额（与回测引擎同一函数）。
    market：成交所在市场（日历 / 呼値 / 单元 / 费用）；account：账户标签（风控基准、流水按它记，默认 = market）。
      例：美股指数仓位用东证上市的 S&P500 ETF 时 market="JP"、account="US"。"""
    today = today or dt.date.today()
    res = DayResult(date=today.isoformat())
    p.validate()
    ex = (exec_cfg or ExecConfig.for_market(market)).validate()
    intraday = ex.stop_fill_mode == "intraday"
    book, guard = PositionBook.for_broker(broker), OrderGuard.for_broker(broker)
    acct = (account or market).upper()
    rm = RiskManager(risk_cfg, market=acct, tag=state_tag(broker))

    # ── 0. 同步 + 取数 ──
    try:
        broker.sync()
    except Exception as e:                                  # noqa: BLE001
        log.error("券商同步失败：%s", e)
        res.notes.append(f"券商同步失败：{e}")
        return res

    held = list(broker.positions())
    core_t = core["ticker"] if core else None
    tickers = sorted(set(universe) | set(held) | ({core_t} if core_t else set()))
    try:
        data = load_universe(tickers, data_cfg, use_cache=False)
    except DataError as e:
        log.error("取数失败，今日不交易：%s", e)
        res.notes.append(f"取数失败：{e}")
        notify.send("取数失败，今日未交易", str(e), "error")
        return res

    data = {t: drop_partial_bar(df, market) for t, df in data.items()}
    ind = {t: compute_indicators(df, p, index_close) for t, df in data.items()}
    bars = {t: df.index[-1] for t, df in ind.items()}
    bar_date = max(bars.values())
    res.bar_date = bar_key_of(bar_date)
    expected = expected_last_bar(today, market)
    behind = (expected - bar_date.normalize().date()).days       # 比"应有的最新 K 线"晚几天
    if behind > 0 and not allow_stale:
        msg = (f"最新 K 线 {bar_date.date()}，但按交易日历应已有 {expected} 的数据"
               f"（落后 {behind} 天），判定为数据过期，今日不交易。"
               "（收盘后 yfinance 通常延迟 15~30 分钟；若今天本就是休市日则属正常）")
        log.warning(msg)
        res.notes.append(msg)
        return res

    if callable(entry_block):
        from .calendar_jp import next_trading_day as _jp_next
        from .calendar_us import next_trading_day as _us_next
        fill_d = (_jp_next if market.upper() == "JP" else _us_next)(bar_date.date())
        entry_block = entry_block(fill_d)
        res.fill_date = fill_d.isoformat()
        if entry_block:
            log.info("[%s] 成交日 %s 在宏观事件窗口：%s", market, fill_d, entry_block)

    last_close = {t: float(df["Close"].iloc[-1]) for t, df in ind.items()}
    opens = {t: float(df["Open"].iloc[-1]) for t, df in ind.items()}
    if hasattr(broker, "set_prices"):
        broker.set_prices(last_close)

    # ── 0.4 公司行为：上一根已处理 K 线之后的除息 / 拆股（行情是复权价，持仓是真实价）──
    if corp_actions is not None and not dry_run:
        _apply_corp_actions(corp_actions, broker, book, ind, bar_key_of(bar_date), market, res)

    # ── 0.5 撮合昨日排队的「次日开盘」订单（与回测引擎的 T+1 开盘成交对齐）──
    if hasattr(broker, "fill_pending"):
        prev_bars = {t: bar_key_of(df.index[-2]) for t, df in ind.items() if len(df) > 1}
        locked = {}
        for t, df in ind.items():
            if len(df) > 1:
                lk = limit_lock(float(df["Close"].iloc[-2]), float(df["High"].iloc[-1]),
                                float(df["Low"].iloc[-1]), float(df["Close"].iloc[-1]), market)
                if lk:
                    locked[t] = lk
        for o in broker.fill_pending(opens, bar_key_of(bar_date), ex.max_entry_gap_pct, prev_bars,
                                     locked=locked):
            res.orders.append(o.to_dict())
            if o.ticker == core_t:
                continue                                   # 核心仓位调仓不是策略交易（不计连亏）
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
            if not pos.stop_px and t != core_t:
                # 与引擎一致：ATR 取**信号日（前一根）**的值，而不是成交当天的
                prev_atr = float(ind[t]["atr"].iloc[-2]) if len(ind[t]) > 1 else np.nan
                pos.stop_px = (pos.avg_px - prev_atr * p.atr_stop_mult
                               if p.atr_stop_mult > 0 and np.isfinite(prev_atr)
                               else pos.avg_px * (1 - p.stop_loss_pct / 100))
        book.update(pos)
        if t in last_close:
            book.book.setdefault(t, {})["last_close"] = last_close[t]    # 拆股兜底判断用（真实价）
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

    def place(side: str, ticker: str, qty: int, reason: str,
              stop_px: float = 0.0, extra: dict | None = None) -> Order | None:
        cid = f"{bar_key}-{ticker}-{side}"
        if not dry_run and guard.seen(cid):                  # 只算不发单时不拦（dry-run 从不发单，也从不记账）
            res.blocked.append(f"{side} {ticker}: 本交易日已发过同样的单（幂等拦截）")
            return None
        is_core = bool((extra or {}).get("core"))
        # 买单用 寄付指値 = 收盘 ×(1+跳空上限)：开盘更高就不成交 —— 与回测 / 模拟盘的跳空过滤是同一条规则
        limit = None
        if side == "BUY" and ex.max_entry_gap_pct and last_close.get(ticker):
            from .tick import round_to_tick
            limit = round_to_tick(last_close[ticker] * (1 + ex.max_entry_gap_pct / 100), ticker, "BUY")
        if dry_run:
            res.orders.append({"side": side, "ticker": ticker, "qty": qty,
                               "price": last_close.get(ticker, 0), "status": "DRY_RUN",
                               "note": reason, "stop_px": round(stop_px, 2),
                               "limit": limit, "core": is_core})
            return None
        fn = broker.buy if side == "BUY" else broker.sell
        kw = {"extra": extra} if extra and getattr(broker, "supports_order_extra", False) else {}
        o = fn(ticker, qty, limit=limit, client_id=cid, ref_px=last_close.get(ticker), bar=bar_key, **kw)
        o.note = f"{reason} {o.note}".strip()
        o.extra.update({"limit": limit, "stop_px": round(stop_px, 2), "core": is_core})
        if o.ok:
            guard.mark(cid, f"{o.status} {o.note}")
        res.orders.append(o.to_dict())
        return o

    # ── 3a. 卖出（核心指数仓位不走个股离场规则，见 3d）──
    exiting: set[str] = set()
    for t, pos in list(positions.items()):
        if t == core_t:
            continue
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
        e_days = _earnings_days(earnings, t, today)
        reason = exit_reason(p, pos, px, bool(row["dead_cross"]),
                             stop_px, trail_px, tp_px,
                             stop_handled_by_broker=intraday and protective_stop,
                             climax=bool(row.get("climax", False)), earnings_in_days=e_days)
        if not reason and force_exit_all:
            reason = force_exit_all                     # 熊市（牛熊分界）→ 全部持仓次日开盘卖出
        if reason and hasattr(broker, "pending") and any(
                q.get("ticker") == t and q.get("side") == "SELL" for q in broker.pending()):
            res.notes.append(f"SELL {t}: 已有顺延中的卖单（ストップ安），不重复下单")
            exiting.add(t)
            continue
        if reason:
            o = place("SELL", t, pos.qty, reason)
            if dry_run or (o is not None and o.ok and o.status != "FILLED"):
                exiting.add(t)                            # 明天开盘卖出 → 名额与资金可用于明天的买入
            if o and o.status == "FILLED":
                pnl = (o.filled_px - pos.avg_px) * o.filled_qty
                rm.on_trade_closed(pnl)
                book.drop(t)
    book.save()

    # ── 3b. 买入：收盘时规划（股数 / 名额 / 资金一次定好，与回测引擎第 4 步逐条相同）──
    slip = ex.slippage_pct / 100
    cur = broker.positions()
    stock_held = {t: q for t, q in cur.items() if t != core_t}
    leaving = {t for t in exiting if t in stock_held}
    if hasattr(broker, "pending"):
        leaving |= {q["ticker"] for q in broker.pending() if q["side"] == "SELL" and q["ticker"] in stock_held}

    def px_of(t: str) -> float:
        return float(last_close.get(t) or stock_held[t].avg_px)

    cash_est = broker.cash()                          # 现金 + 明天开盘卖出的预计净额（按收盘价估）
    for t in leaving:
        sp = px_of(t) * (1 - slip)
        cash_est += stock_held[t].qty * sp - ex.fee(stock_held[t].qty * sp)
    equity = broker.equity()
    cc = core or {}
    c_slip, c_lot = float(cc.get("slip_pct", 0.0)) / 100, int(cc.get("lot", 1) or 1)

    c_fees = {s: side_fee(cc, s) for s in ("BUY", "SELL")}

    def c_fee(side: str, notional: float) -> float:
        return c_fees[side](notional)

    core_units = cur[core_t].qty if core_t in cur else 0
    core_px = float(last_close.get(core_t) or 0.0) if core_t else 0.0
    core_liq = 0.0
    if core_units and core_px:
        cs = core_px * (1 - c_slip)
        core_liq = core_units * cs - c_fee("SELL", core_units * cs)

    entry_today = [t for t, df in ind.items()
                   if t in universe and t != core_t and bool(df["entry"].iloc[-1]) and df.index[-1] == bar_date]
    res.signals = entry_today
    planned: list[tuple] = []                         # (票, 股数, 参考止损, 说明, 单元)
    plan_cost = 0.0
    if entry_today and not decision.allow_open:
        res.blocked.append(f"熔断中，今日不开仓（信号: {', '.join(entry_today)}）")
    elif entry_today and entry_scale <= 0:
        res.blocked.append(f"市场状态 risk_off / 避险，今日不开新仓（信号: {', '.join(entry_today)}）")
    elif entry_today and entry_block:
        res.blocked.append(f"宏观事件窗口：{entry_block}（信号: {', '.join(entry_today)}）")
    elif entry_today and len(stock_held) >= sizing.max_positions:
        res.blocked.append(f"持仓数已达上限 {sizing.max_positions}（信号: {', '.join(entry_today)}）")
    elif entry_today:
        if entry_scale < 1.0:
            res.notes.append(f"市场状态：新仓规模 ×{entry_scale:.2f}")
        n_after = len(stock_held) - len(leaving)
        for t in sorted(entry_today):
            if t in cur:
                continue
            e_days = _earnings_days(earnings, t, today)
            if p.earnings_blackout_days and e_days is not None and e_days <= p.earnings_blackout_days:
                res.blocked.append(f"BUY {t}: 决算前 {e_days} 个交易日内（回避期 {p.earnings_blackout_days} 日）")
                continue
            tm = float((ticker_mult or {}).get(t, 1.0))
            if tm <= 0:
                res.blocked.append(f"BUY {t}: 板块倾斜 ×0（宏观层）")
                continue
            if n_after + len(planned) >= sizing.max_positions:
                res.blocked.append(f"BUY {t}: 名额已满（上限 {sizing.max_positions}，"
                                   f"明天持有 {n_after} + 已计划 {len(planned)}）")
                continue
            row = ind[t].iloc[-1]
            px = last_close[t] * (1 + slip)               # 按 收盘×(1+滑点) 定股数（与回测相同）
            atr_v = float(row["atr"])
            stop_px = (px - atr_v * p.atr_stop_mult if p.atr_stop_mult > 0 and np.isfinite(atr_v)
                       else px * (1 - p.stop_loss_pct / 100))
            if not (0 < stop_px < px):
                stop_px = px * (1 - p.stop_loss_pct / 100)
            if sizing.mode == "risk_pct":
                budget = equity * (sizing.risk_pct / 100) / max(px - stop_px, 1e-9) * px
            else:
                budget = equity * sizing.position_pct
            em = max(0.0, min(1.0, entry_scale)) * min(1.0, tm)
            if tm < 1.0:
                res.notes.append(f"{t} 板块倾斜 ×{tm:g}")
            avail = cash_est - plan_cost + core_liq
            budget = min(budget * em, equity * sizing.max_position_pct,
                         avail * (1 - sizing.cash_buffer_pct / 100), risk_cfg.max_order_value)
            lot = lot_size(t, market)
            qty = int(budget // (px * lot)) * lot if budget > 0 else 0
            if qty <= 0:
                res.blocked.append(f"BUY {t}: 预算 {max(budget, 0):,.0f} 不够 1 单元({lot}股 ≈{px*lot:,.0f})")
                continue
            ok, why = rm.check_order(qty * px, len(stock_held))
            if not ok:
                res.blocked.append(f"BUY {t}: {why}")
                continue
            planned.append((t, qty, stop_px, f"entry(range={row['range_pct']:.1f}% vol×{row['vol_ratio']:.1f})", lot))
            plan_cost += qty * px + ex.fee(qty * px)

    # ── 3d. 核心指数仓位：收盘决定明天开盘的买卖份额（core.core_orders，与回测引擎第 5 步同一函数）──
    core_sell = core_buy = 0
    if core_t:
        stock_after = sum(q.qty * px_of(t) for t, q in stock_held.items() if t not in leaving)
        if not core_px:
            res.notes.append(f"核心 {core_t}: 无行情，今日不调整")
        else:
            cs = core_px * (1 - c_slip)
            core_sell, core_buy = core_orders(
                equity, stock_after, plan_cost, cash_est, core_units, core_px, bool(cc.get("bear")),
                buffer_pct=float(cc.get("buffer_pct", 0.0)), band_pct=float(cc.get("band_pct", 10.0)),
                lot=c_lot, margin_pct=ex.max_entry_gap_pct,
                sell_net=lambda u: u * cs - c_fee("SELL", u * cs))
            if core_buy and not decision.allow_open:
                res.blocked.append(f"BUY {core_t}: 熔断中，核心仓位今日不加仓")
                core_buy = 0
        tgt_val = 0.0 if cc.get("bear") else max(
            0.0, equity * (1 - float(cc.get("buffer_pct", 0.0)) / 100) - stock_after - plan_cost)
        res.core = {"ticker": core_t, "units": core_units, "price": core_px,
                    "value": round(core_units * core_px, 2), "target_value": round(tgt_val, 2),
                    "bear": bool(cc.get("bear")), "timing": bool(cc.get("timing", True)),
                    "sell": core_sell, "buy": core_buy,
                    "weight_pct": round(core_units * core_px / equity * 100, 1) if equity > 0 else 0.0}
    c_extra = {"core": True, "cost": {k: (list(map(list, v)) if k.endswith("_tiers") else v) for k, v in cc.items()
                                      if k == "slip_pct" or k.startswith(("buy_fee_", "sell_fee_"))},
               "lot": c_lot}

    # 排队顺序 = 开盘成交顺序：核心卖出 → 个股买入 → 核心买入（个股卖单已在 3a 排好）
    if core_sell:
        why = ("bear(牛熊分界：熊市，核心仓位清空)" if cc.get("bear")
               else "core(为明天的个股买入腾资金 / 再平衡)")
        place("SELL", core_t, core_sell, why, extra=c_extra)
    for t, qty, stop_px, note, lot in planned:
        o = place("BUY", t, qty, note, stop_px=stop_px,
                  extra={"lot": lot, "cap": sizing.max_positions, "excl": [core_t] if core_t else []})
        if o and o.ok:
            rm.on_open()
            if o.filled_qty > 0:      # 立即成交（非排队）
                row = ind[t].iloc[-1]
                pos = Position(ticker=t, qty=o.filled_qty, avg_px=o.filled_px or last_close[t],
                               peak=max(o.filled_px or last_close[t], float(row["High"])),
                               stop_px=stop_px, entry_date=bar_key, hold_bars=0,
                               last_bar=bar_key)
                book.update(pos)
                broker.update_position(pos)
            else:
                res.notes.append(f"{t} 已排队，次日开盘成交（参考止损 {stop_px:.1f}）")
    if core_buy:
        place("BUY", core_t, core_buy, "core(闲置资金买入指数 ETF)", extra=c_extra)
    book.save()

    # ── 3c. 逆指値（protective stop）维护：让盘中止损在实盘真正生效 ──
    if protective_stop and hasattr(broker, "place_protective_stop") and not dry_run:
        for t, pos in broker.positions().items():
            if t == core_t:
                continue
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
    if not dry_run:                                   # 只算不发单的清单不进流水（流水是模拟盘 / 实盘日报的数据源）
        rm.end(res.equity, today)
        _journal(res, acct, broker)
    if res.orders or decision.daily_loss_pct <= -abs(risk_cfg.daily_max_loss_pct):
        notify.send(f"{res.date} 交易汇总", res.summary(),
                    "warn" if not decision.allow_open else "info")
    return res


def _journal(res: DayResult, market: str = "JP", broker=None) -> None:
    fp = paths.out_dir() / f"journal{state_tag(broker)}.csv"          # 模拟盘与实盘各记各的
    row = pd.DataFrame([{ "date": res.date, "market": market, "bar_date": res.bar_date,
                          "equity": round(res.equity, 2),
                          "cash": round(res.cash, 2),
                          "positions": ";".join(f"{k}:{v}" for k, v in res.positions.items()),
                          "orders": len(res.orders), "signals": ";".join(res.signals),
                          "risk": res.risk }])
    row.to_csv(fp, mode="a", header=not fp.exists(), index=False, encoding="utf-8-sig")


def load_params(path=None, market: str | None = None) -> StrategyParams:
    """optimize 产出的稳健参数写进 var/best_params.json 就自动生效。
    market 给定且存在 var/best_params_<MARKET>.json 时，把其中字段**覆盖**到基础参数上：
    文件可以只写差异（例如日本株单独打开顶部过滤，美股保持关闭）。"""
    fp = path or paths.params_file()
    try:
        p = StrategyParams.load(fp)
    except Exception as e:                                  # noqa: BLE001
        log.error("best_params.json 读取失败（%s），改用默认参数", e)
        p = None
        fp = None
    if p is None:
        if fp is not None:
            log.info("未找到 %s，使用默认参数", fp)
        p = StrategyParams()
    else:
        log.info("已加载参数 %s", fp)
    if market:
        ov = paths.params_file(market)
        if ov.exists():
            try:
                d = read_json(ov) or {}
                p = StrategyParams.from_dict({**p.to_dict(), **d})
                log.info("已叠加 %s 市场覆盖参数 %s：%s", market, ov, d)
            except Exception as e:                          # noqa: BLE001
                log.error("%s 读取失败（%s），忽略覆盖", ov, e)
    return p


def operation_sheet(res: DayResult, p: StrategyParams, positions: dict[str, Position],
                    limit_buffer_pct: float = 0.5) -> str:
    """把当日结果整理成一张**人能照着下单**的清单（半自动模式）。
    每一行都给出：动作、数量、寄付指値、逆指値（止损）—— 你在券商 App 里照抄即可。
    买入指値 = 收盘 ×(1+跳空上限)（run_once 已算好并按呼値取整）：开盘更高就不成交，与回测的跳空过滤一致；
    订单里没有指値时才退回用 limit_buffer_pct。"""
    from .tick import round_to_tick
    L = [f"═══ {res.date} 操作清单（信号已算好，由你手工下单）═══"]
    buys = [o for o in res.orders if o["side"] == "BUY"]
    sells = [o for o in res.orders if o["side"] == "SELL"]
    x_of = lambda o: o.get("extra") or {}                                   # noqa: E731
    is_core = lambda o: bool(o.get("core") or x_of(o).get("core"))          # noqa: E731
    fm = lambda t, v: f"{v:,.0f}" if t.endswith(".T") else f"{v:,.2f}"      # noqa: E731  日本株整数、美股到分
    core_t = (res.core or {}).get("ticker")
    if not buys and not sells:
        L.append("今日无买卖动作。")
    for o in sells:
        tag = "核心指数仓位" if is_core(o) else "个股"
        L.append(f"卖出  {o['ticker']:<8} {o['qty']:>6} 股  寄付成行（{tag}）  ← {o.get('note', '')}")
    if any(is_core(o) for o in sells) and any(not is_core(o) for o in buys):
        L.append("  ↳ 个股买入的资金来自上面卖出的指数 ETF：先等 9:00 寄付卖出成交（买付余力到账），再下个股买单。")
    for o in sorted(buys, key=is_core):
        px = float(o.get("price") or 0)
        lim = o.get("limit") or x_of(o).get("limit") or (
            round_to_tick(px * (1 + limit_buffer_pct / 100), o["ticker"], "BUY") if px else 0)
        pct = (lim / px - 1) * 100 if px and lim else 0.0
        if is_core(o):
            L.append(f"买入  {o['ticker']:<8} {o['qty']:>6} 口  寄付指値 ≤ {fm(o['ticker'], lim)}"
                     f"（收盘 {fm(o['ticker'], px)} {pct:+.1f}%）"
                     f"  核心指数仓位：个股买完后用剩余现金，买不起就少买  ← {o.get('note', '')}")
            continue
        stop = float(o.get("stop_px") or x_of(o).get("stop_px") or 0) or px * (1 - p.stop_loss_pct / 100)
        L.append(f"买入  {o['ticker']:<8} {o['qty']:>6} 股  寄付指値 ≤ {fm(o['ticker'], lim)}"
                 f"（收盘 {fm(o['ticker'], px)} {pct:+.1f}%，开盘更高就不成交）  逆指値(止损) {fm(o['ticker'], stop)}"
                 f"  ← {o.get('note', '')}")
    held = {t: pos for t, pos in positions.items()
            if t not in {o["ticker"] for o in sells} and t != core_t}       # 核心 ETF 不挂逆指値
    if held:
        L.append("持仓维护（逆指値应放在这里；比现有挂单高就上移，不要下移）：")
        for t, pos in sorted(held.items()):
            stop = pos.stop_px or pos.avg_px * (1 - p.stop_loss_pct / 100)
            trail = pos.peak * (1 - p.trailing_stop_pct / 100) if p.trailing_stop_pct else 0
            want = max(stop, trail)
            tag = "跟踪止损" if trail > stop else "固定止损"
            L.append(f"  {t:<8} {pos.qty:>6} 股  逆指値 {want:,.0f}（{tag}，峰值 {pos.peak:,.0f}，"
                     f"成本 {pos.avg_px:,.0f}）")
    if res.blocked:
        L.append("被拦截：")
        L += [f"  {b}" for b in res.blocked]
    L.append(res.risk)
    return "\n".join(L)
