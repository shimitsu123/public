"""engine.py — 组合级回测引擎（バックテストエンジン）。纯 numpy，单次回测比原版快 1~2 个数量级。

成交假设（保守，逐条对应实盘能做到的动作；实盘 trader.run_once + PaperBroker 用同一套规则，
verify_all.py 的 V4 逐笔对照）
  • 信号在 T 日收盘成立 → **T 日收盘时就定好股数**（与实盘前一晚下单相同）：
      预算 = T 日收盘权益 × position_pct × 宏观倍数，再受 单只上限、预计可用资金×(1−缓冲) 约束；
      预计可用资金 = 现金 + 已排队卖出的预计净额 − 已计划买入的预计成本 (+ 核心仓位可变现额)；
      股数 = floor(预算 / (收盘×(1+滑点)) / 单元) × 单元；名额 = 上限 − (持仓 − 排队卖出) − 已计划
  • T+1 开盘价 ×(1+滑点) 成交；信号只在 T+1 有效，过期作废；开盘现金不够 → 按单元减到买得起
  • T+1 开盘相对 T 日收盘跳空超过 max_entry_gap_pct → 放弃（实盘用 寄付指値 = 收盘×(1+上限) 实现）
  • 止损/跟踪止损/止盈在盘中触发；同一根 K 线内 **优先假设先触发止损**（最悲观）
  • 开盘跳空越过止损 → 按开盘价成交（gap_stop），不是按止损价
  • 死叉 / 最长持有 / 时间止损 → 次日开盘卖出
  • 手续费双边收取；仓位大小用【前一日收盘权益】计算，绝不使用当日数据

与原版的关键修正
  1. 原版 `budget = mark_to_market(d) * position_pct` 用的是**当日收盘**权益去决定
     **当日开盘**的买入金额 —— 这是前视偏差。
  2. 原版 pending_exit 在标的当日无数据时不会清理，重新建仓后会被"幽灵卖单"立刻平掉。
  3. 原版没有跳空过滤，隔夜 +15% 开盘也照单全收。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import BacktestConfig, StrategyParams
from .core import core_orders
from .tick import limit_lock, lot_size

EXIT_REASONS = ("stop", "gap_stop", "trail", "take_profit", "dead_cross", "climax",
                "max_hold", "time_stop", "end")


@dataclass
class _Pos:
    ticker: str
    shares: int
    entry_px: float
    entry_i: int
    stop_px: float
    peak: float
    last_close: float
    hold: int = 0
    armed: bool = False          # 跟踪止损是否已启动


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.Series
    exposure: pd.Series
    metrics: dict = field(default_factory=dict)
    skipped: dict = field(default_factory=dict)   # 被过滤掉的信号计数，用于诊断
    extra: dict = field(default_factory=dict)     # 核心指数仓位的成交 / 费用统计等


class _Aligned:
    """把每只股票的列对齐到全局交易日轴，之后引擎只跟 numpy 打交道。"""

    def __init__(self, ind: dict[str, pd.DataFrame], gidx: pd.DatetimeIndex):
        self.tickers = list(ind.keys())
        n, m = len(gidx), len(self.tickers)
        self.has = np.zeros((n, m), dtype=bool)
        self.open = np.full((n, m), np.nan)
        self.high = np.full((n, m), np.nan)
        self.low = np.full((n, m), np.nan)
        self.close = np.full((n, m), np.nan)
        self.atr = np.full((n, m), np.nan)
        self.entry = np.zeros((n, m), dtype=bool)
        self.dead = np.zeros((n, m), dtype=bool)
        self.climax = np.zeros((n, m), dtype=bool)
        for j, t in enumerate(self.tickers):
            df = ind[t]
            loc = gidx.get_indexer(df.index)
            ok = loc >= 0
            loc = loc[ok]
            self.has[loc, j] = True
            self.open[loc, j] = df["Open"].to_numpy(dtype=float)[ok]
            self.high[loc, j] = df["High"].to_numpy(dtype=float)[ok]
            self.low[loc, j] = df["Low"].to_numpy(dtype=float)[ok]
            self.close[loc, j] = df["Close"].to_numpy(dtype=float)[ok]
            self.atr[loc, j] = df["atr"].to_numpy(dtype=float)[ok]
            self.entry[loc, j] = df["entry"].to_numpy(dtype=bool)[ok]
            self.dead[loc, j] = df["dead_cross"].to_numpy(dtype=bool)[ok]
            if "climax" in df.columns:
                self.climax[loc, j] = df["climax"].fillna(False).to_numpy(dtype=bool)[ok]


def _window(gidx: pd.DatetimeIndex, start, end) -> tuple[int, int]:
    lo = 0 if start is None else int(gidx.searchsorted(pd.Timestamp(start), side="left"))
    hi = len(gidx) if end is None else int(gidx.searchsorted(pd.Timestamp(end), side="right"))
    return lo, hi


def run_backtest(ind: dict[str, pd.DataFrame], p: StrategyParams, bt: BacktestConfig,
                 start=None, end=None, entry_mult=None, regime=None,
                 regime_exit: bool = False, core: dict | None = None,
                 core_bear=None) -> BacktestResult:
    """ind: {ticker: compute_indicators(...) 的结果}。start/end 只限制**交易窗口**，
    指标仍在完整历史上计算 —— 这样 walk-forward 的样本外窗口不会被指标预热期吃掉，
    同时因为指标在 t 时刻只用 ≤t 的数据，也不会引入前视偏差。
    entry_mult：可选 [len(全局日期) × n 票] 矩阵（0~1），成交日 i 的新仓预算 × entry_mult[i, j]；
    0 = 该日不开该票新仓（宏观层 / 板块倾斜 / 事件窗口，见 macro.build_entry_mult）。
    regime：可选 bool 数组 [len(全局日期)]，True = 该日收盘时处于熊市（bullbear 分界算法）。
      熊市收盘产生的信号不在次日开新仓；regime_exit=True 时，宣布熊市当天收盘把全部持仓排队到次日开盘卖出。
    core：核心指数仓位（闲置资金买指数 ETF，见 qbreak/core.py）。{"ticker", "buffer_pct", "band_pct"（均为 %）,
      "buy_fee_pct", "sell_fee_pct", "sell_fee_max", "slip_pct", "lot"}；ticker 必须在 ind 里（entry 全 False）。
      每天收盘用 core.core_orders 决定次日开盘的买卖份额（与实盘同一函数）；次日开盘顺序：
      个股卖出 → 核心卖出 → 个股买入 → 核心买入（用剩余现金，买不起的部分放弃）。
      core_bear（bool 数组）为 True 的日子目标 = 0（熊市清空核心仓位）。"""
    p.validate()
    ex, sz = bt.exec_cfg.validate(), bt.sizing.validate()
    if not ind:
        raise ValueError("没有可回测的标的")

    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))
    A = _Aligned(ind, gidx)
    i0, i1 = _window(gidx, start or bt.start, end or bt.end)
    if i1 - i0 < 2:
        raise ValueError(f"交易窗口太短: {gidx[i0] if i0 < len(gidx) else None} ~ {end}")

    lots = np.array([lot_size(t, ex.market) for t in A.tickers])
    intraday_stop = ex.stop_fill_mode == "intraday"
    slip, fee_f = ex.slippage_pct / 100, ex.fee
    cash = float(sz.initial_cash)
    pos: dict[int, _Pos] = {}
    plan: dict[int, tuple[float, int]] = {}     # j -> (信号日收盘价, 收盘时定好的股数)
    pending_exit: dict[int, str] = {}
    trades: list[dict] = []
    eq_hist, exp_hist = np.empty(i1 - i0), np.empty(i1 - i0)
    skipped = dict(gap=0, cash=0, lot=0, full=0, no_bar=0, daily_cap=0, rebuy=0, macro=0,
                   limit_up=0, limit_down_hold=0, regime=0)
    if regime is not None:
        regime = np.asarray(regime, dtype=bool)
        if regime.shape != (len(gidx),):
            raise ValueError(f"regime 长度 {regime.shape} ≠ {len(gidx)}")
    jc, core_units, core_order, core_last = None, 0, None, np.nan
    core_log = {"trades": 0, "fees": 0.0, "bought": 0.0, "sold": 0.0}
    if core:
        jc = A.tickers.index(core["ticker"])
        c_lot = int(core.get("lot", 1))
        c_slip = float(core.get("slip_pct", 0.02)) / 100
        if core_bear is not None:
            core_bear = np.asarray(core_bear, dtype=bool)
            if core_bear.shape != (len(gidx),):
                raise ValueError(f"core_bear 长度 {core_bear.shape} ≠ {len(gidx)}")

    def c_fee(side: str, notional: float) -> float:
        pct = float(core.get("buy_fee_pct" if side == "BUY" else "sell_fee_pct", 0.0))
        f = abs(notional) * pct / 100
        cap = float(core.get("buy_fee_max" if side == "BUY" else "sell_fee_max", 0.0) or 0.0)
        return min(f, cap) if cap else f

    def core_trade(side: str, units: int, i: int) -> None:
        nonlocal cash, core_units
        if units <= 0 or not A.has[i, jc]:
            return
        px = A.open[i, jc] * (1 + c_slip if side == "BUY" else 1 - c_slip)
        notional = units * px
        f = c_fee(side, notional)
        if side == "BUY":
            cash -= notional + f; core_units += units; core_log["bought"] += notional
        else:
            cash += notional - f; core_units -= units; core_log["sold"] += notional
        core_log["trades"] += 1; core_log["fees"] += f
    jp_limits = ex.market.upper() == "JP"

    def locked(i: int, j: int) -> str | None:
        """当日是否一整天张贴在ストップ高/安（寄付无法成交）。仅日本株。"""
        if not jp_limits or i == 0 or not A.has[i - 1, j]:
            return None
        return limit_lock(A.close[i - 1, j], A.high[i, j], A.low[i, j], A.close[i, j], "JP")
    sold_today: set[int] = set()
    if entry_mult is not None:
        entry_mult = np.asarray(entry_mult, dtype=float)
        if entry_mult.shape != (len(gidx), len(A.tickers)):
            raise ValueError(f"entry_mult 形状 {entry_mult.shape} ≠ {(len(gidx), len(A.tickers))}")

    def equity_at(i: int) -> float:
        v = cash
        for j, ps in pos.items():
            px = A.close[i, j] if A.has[i, j] else ps.last_close
            v += ps.shares * px
        if jc is not None and core_units:
            v += core_units * (A.close[i, jc] if A.has[i, jc] else core_last)
        return v

    def close_pos(j: int, px: float, i: int, reason: str):
        nonlocal cash
        ps = pos.pop(j)
        proceeds = ps.shares * px
        fee = fee_f(proceeds) + fee_f(ps.shares * ps.entry_px)
        cash += proceeds - fee_f(proceeds)
        trades.append(dict(
            ticker=ps.ticker, entry_date=gidx[ps.entry_i], exit_date=gidx[i],
            entry_px=round(ps.entry_px, 4), exit_px=round(px, 4), shares=ps.shares,
            pnl=round((px - ps.entry_px) * ps.shares - fee, 2),
            ret_pct=round((px / ps.entry_px - 1) * 100, 3),
            hold_days=ps.hold, reason=reason))
        sold_today.add(j)

    def sell_net(j: int, i: int) -> float:
        """已排队卖出的个股按收盘价估计的净额（规划用，与实盘相同的估计口径）。"""
        px = (A.close[i, j] if A.has[i, j] else pos[j].last_close) * (1 - slip)
        return pos[j].shares * px - fee_f(pos[j].shares * px)

    for i in range(i0, i1):
        sold_today.clear()
        if jc is not None and A.has[i, jc]:
            core_last = A.close[i, jc]

        # ── 1. 执行昨日排队的卖出（T+1 开盘）──
        for j in list(pending_exit):
            if j not in pos:
                pending_exit.pop(j)          # 已被盘中止损平掉 → 清理，避免"幽灵卖单"
                continue
            if not A.has[i, j]:
                continue                      # 停牌：保留到下一个有交易的日子
            if locked(i, j) == "down":
                skipped["limit_down_hold"] += 1
                continue                      # ストップ安張り付き：卖不掉，留到下一个交易日
            close_pos(j, A.open[i, j] * (1 - slip), i, pending_exit.pop(j))

        # ── 1b. 核心仓位减仓（昨日收盘决定，今日开盘成交；先于个股买入，腾出现金）──
        if jc is not None and core_order and core_order[0] == "SELL":
            core_trade("SELL", min(core_order[1], core_units), i)

        # ── 2. 执行昨日排队的买入（T+1 开盘；股数在信号日收盘已定）──
        for j, (sig_close, shares) in list(plan.items()):
            plan.pop(j)
            if not A.has[i, j]:
                skipped["no_bar"] += 1
                continue
            if j in pos:
                continue
            if len(pos) >= sz.max_positions:
                skipped["full"] += 1              # 排队卖出没成交（ストップ安）→ 名额不够
                continue
            if ex.forbid_same_day_rebuy and j in sold_today:
                skipped["rebuy"] += 1
                continue
            o = A.open[i, j]
            if ex.max_entry_gap_pct and o > sig_close * (1 + ex.max_entry_gap_pct / 100):
                skipped["gap"] += 1
                continue
            if locked(i, j) == "up":
                skipped["limit_up"] += 1          # ストップ高張り付き：买不到
                continue
            px = o * (1 + slip)
            lot = int(lots[j])
            while shares > 0 and shares * px + fee_f(shares * px) > cash:
                shares -= lot                     # 开盘比收盘贵、现金不够 → 按单元减
            if shares <= 0:
                skipped["cash"] += 1
                continue
            stop_px = (px - A.atr[i - 1, j] * p.atr_stop_mult
                       if p.atr_stop_mult > 0 and i > 0 and np.isfinite(A.atr[i - 1, j])
                       else px * (1 - p.stop_loss_pct / 100))
            if not (0 < stop_px < px):
                stop_px = px * (1 - p.stop_loss_pct / 100)
            notional = shares * px
            cash -= notional + fee_f(notional)
            pos[j] = _Pos(A.tickers[j], shares, px, i, stop_px, px, px, hold=0)

        # ── 2b. 核心仓位加仓（个股买完之后，用剩余现金；买不起的部分放弃）──
        if jc is not None and core_order and core_order[0] == "BUY" and A.has[i, jc]:
            bpx = A.open[i, jc] * (1 + c_slip)
            u = core_order[1]
            while u > 0 and u * bpx + c_fee("BUY", u * bpx) > cash:
                u -= c_lot
            core_trade("BUY", u, i)
        core_order = None

        # ── 3. 盘中止损 / 跟踪止损 / 止盈 ──
        for j in list(pos):
            if not A.has[i, j]:
                continue
            ps = pos[j]
            ps.hold += 1
            o, h, l, c = A.open[i, j], A.high[i, j], A.low[i, j], A.close[i, j]
            if p.trailing_arm_pct and not ps.armed and h >= ps.entry_px * (1 + p.trailing_arm_pct / 100):
                ps.armed = True
            trail_on = p.trailing_stop_pct > 0 and (ps.armed or not p.trailing_arm_pct)
            tp_px = ps.entry_px * (1 + p.take_profit_pct / 100) if p.take_profit_pct else np.inf
            queued = None

            if intraday_stop:
                # 盘中成交假设：需要你真的挂了逆指値，否则这里的收益是虚的
                trail_px = ps.peak * (1 - p.trailing_stop_pct / 100) if trail_on else -np.inf
                hard = max(ps.stop_px, trail_px)
                exit_px = reason = None
                if o <= hard:
                    exit_px, reason = o, "gap_stop"           # 跳空越过 → 按开盘价，不是止损价
                elif l <= hard:
                    exit_px, reason = hard, ("trail" if trail_px > ps.stop_px else "stop")
                elif h >= tp_px:
                    exit_px, reason = max(tp_px, o), "take_profit"
                if exit_px is not None:
                    if locked(i, j) == "down":        # 逆指値も約定しない → 次の寄付で成行
                        skipped["limit_down_hold"] += 1
                        pending_exit[j] = reason
                        ps.last_close = c
                        continue
                    close_pos(j, exit_px * (1 - slip), i, reason)
                    continue
                ps.peak = max(ps.peak, h)
            else:
                # 收盘价触发 → 次日开盘成交（每日运行一次的程序真正能做到的）
                ps.peak = max(ps.peak, h)
                trail_px = ps.peak * (1 - p.trailing_stop_pct / 100) if trail_on else -np.inf
                hard = max(ps.stop_px, trail_px)
                if c <= hard:
                    queued = "trail" if trail_px > ps.stop_px else "stop"
                elif c >= tp_px:
                    queued = "take_profit"

            ps.last_close = c
            if queued is None:
                if (p.exit_on_climax and A.climax[i, j]
                        and (c / ps.entry_px - 1) * 100 >= p.climax_min_gain_pct):
                    queued = "climax"                  # 高位放量陰線 = 出货日
                elif p.exit_on_macd_dead_cross and A.dead[i, j]:
                    queued = "dead_cross"
                elif p.max_hold_days and ps.hold >= p.max_hold_days:
                    queued = "max_hold"
                elif (p.time_stop_days and ps.hold >= p.time_stop_days
                      and (c / ps.entry_px - 1) * 100 < p.time_stop_min_ret_pct):
                    queued = "time_stop"
            if queued:
                pending_exit[j] = queued

        # ── 3b. 牛熊分界：宣布熊市当天收盘 → 全部持仓次日开盘卖出（可选）──
        if regime_exit and regime is not None and i > 0 and regime[i] and not regime[i - 1]:
            for j in list(pos):
                pending_exit.setdefault(j, "regime_bear")

        # ── 4. 收盘规划次日开盘的买入（股数现在就定，与实盘前一晚下单相同）──
        exit_js = [j for j in pending_exit if j in pos]
        cash_est = cash + sum(sell_net(j, i) for j in exit_js)
        plan_cost = 0.0
        core_liq = 0.0
        if jc is not None and core_units and A.has[i, jc]:
            cpx_s = A.close[i, jc] * (1 - c_slip)
            core_liq = core_units * cpx_s - c_fee("SELL", core_units * cpx_s)
        if len(pos) < sz.max_positions:
            eq_now = equity_at(i)
            n_after = len(pos) - len(exit_js)
            # 按代码字母序规划（与实盘 sorted(信号) 相同；名额 / 资金不够时先后顺序决定谁买得到）
            for j in sorted((int(x) for x in np.flatnonzero(A.entry[i] & A.has[i])), key=A.tickers.__getitem__):
                if j in pos or j in pending_exit:
                    continue
                if regime is not None and regime[i]:
                    skipped["regime"] += 1                # 收盘已是熊市 → 牛市算法不开新仓
                    continue
                em = (float(entry_mult[i + 1, j]) if entry_mult is not None and i + 1 < len(gidx)
                      else 1.0)                           # 宏观倍数按成交日（T+1）取，收盘时已知
                if em <= 0:
                    skipped["macro"] += 1
                    continue
                if n_after + len(plan) >= sz.max_positions:
                    skipped["full"] += 1
                    continue
                c = float(A.close[i, j])
                px = c * (1 + slip)
                stop_ref = (px - A.atr[i, j] * p.atr_stop_mult
                            if p.atr_stop_mult > 0 and np.isfinite(A.atr[i, j])
                            else px * (1 - p.stop_loss_pct / 100))
                if not (0 < stop_ref < px):
                    stop_ref = px * (1 - p.stop_loss_pct / 100)
                if sz.mode == "risk_pct":
                    budget = eq_now * (sz.risk_pct / 100) / max(px - stop_ref, 1e-9) * px
                else:
                    budget = eq_now * sz.position_pct
                avail = cash_est - plan_cost + core_liq
                budget = min(budget * min(1.0, em), eq_now * sz.max_position_pct,
                             avail * (1 - sz.cash_buffer_pct / 100))
                lot = int(lots[j])
                shares = int(math.floor(budget / px / lot) * lot) if budget > 0 else 0
                if shares <= 0:
                    skipped["lot" if budget > 0 else "cash"] += 1
                    continue
                plan[j] = (c, shares)
                plan_cost += shares * px + fee_f(shares * px)

        # ── 5. 核心仓位：收盘决定次日开盘的买卖份额（core.core_orders，与实盘同一函数）──
        if jc is not None and A.has[i, jc]:
            cpx = float(A.close[i, jc])
            stock_after = sum(ps.shares * (A.close[i, j] if A.has[i, j] else ps.last_close)
                              for j, ps in pos.items() if j not in pending_exit)
            c_sell_px = cpx * (1 - c_slip)
            sell_u, buy_u = core_orders(
                equity_at(i), stock_after, plan_cost, cash_est, core_units, cpx,
                bool(core_bear is not None and core_bear[i]),
                buffer_pct=float(core.get("buffer_pct", 0.0)), band_pct=float(core.get("band_pct", 10.0)),
                lot=c_lot, margin_pct=ex.max_entry_gap_pct,
                sell_net=lambda u: u * c_sell_px - c_fee("SELL", u * c_sell_px))
            core_order = ("SELL", sell_u) if sell_u else (("BUY", buy_u) if buy_u else None)

        eq = equity_at(i)
        eq_hist[i - i0] = eq
        exp_hist[i - i0] = 1 - cash / eq if eq > 0 else 0.0

    # 期末按最后收盘价强平（仅为统计口径完整）
    for j in list(pos):
        close_pos(j, pos[j].last_close, i1 - 1, "end")

    tdf = pd.DataFrame(trades, columns=[
        "ticker", "entry_date", "exit_date", "entry_px", "exit_px", "shares",
        "pnl", "ret_pct", "hold_days", "reason"])
    idx = gidx[i0:i1]
    from .metrics import compute_metrics
    eq_s = pd.Series(eq_hist, index=idx, name="equity")
    res = BacktestResult(trades=tdf, equity=eq_s,
                         exposure=pd.Series(exp_hist, index=idx, name="exposure"),
                         skipped=skipped)
    res.metrics = compute_metrics(tdf, eq_s, res.exposure)
    if jc is not None:
        core_log["units_end"] = core_units
        res.extra["core"] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in core_log.items()}
    return res


def buy_and_hold(ind: dict[str, pd.DataFrame], bt: BacktestConfig,
                 start=None, end=None) -> pd.Series:
    """等权买入持有基准（ベンチマーク）：把策略收益放在"什么都不做"旁边看。"""
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))
    i0, i1 = _window(gidx, start or bt.start, end or bt.end)
    idx = gidx[i0:i1]
    cols = []
    for df in ind.values():
        s = df["Close"].reindex(idx).ffill()
        if s.notna().sum() < 2:
            continue
        s = s / s.dropna().iloc[0]
        cols.append(s)
    if not cols:
        return pd.Series(dtype=float)
    return pd.concat(cols, axis=1).mean(axis=1) * bt.sizing.initial_cash
