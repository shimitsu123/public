"""engine.py — 组合级回测引擎（バックテストエンジン）。纯 numpy，单次回测比原版快 1~2 个数量级。

成交假设（保守，逐条对应实盘能做到的动作）
  • 信号在 T 日收盘成立 → T+1 开盘价 ×(1+滑点) 买入；信号只在 T+1 有效，过期作废
  • T+1 开盘相对 T 日收盘跳空超过 max_entry_gap_pct → 放弃（ストップ高 追不进去）
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
from .tick import lot_size

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
                 start=None, end=None, entry_mult=None) -> BacktestResult:
    """ind: {ticker: compute_indicators(...) 的结果}。start/end 只限制**交易窗口**，
    指标仍在完整历史上计算 —— 这样 walk-forward 的样本外窗口不会被指标预热期吃掉，
    同时因为指标在 t 时刻只用 ≤t 的数据，也不会引入前视偏差。
    entry_mult：可选 [len(全局日期) × n 票] 矩阵（0~1），成交日 i 的新仓预算 × entry_mult[i, j]；
    0 = 该日不开该票新仓（宏观层 / 板块倾斜 / 事件窗口，见 macro.build_entry_mult）。"""
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
    pending_entry: dict[int, float] = {}        # j -> 信号日收盘价
    pending_exit: dict[int, str] = {}
    trades: list[dict] = []
    eq_hist, exp_hist = np.empty(i1 - i0), np.empty(i1 - i0)
    skipped = dict(gap=0, cash=0, lot=0, full=0, no_bar=0, daily_cap=0, rebuy=0, macro=0)
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

    for i in range(i0, i1):
        sold_today.clear()
        equity_prev = equity_at(i - 1) if i > i0 else cash + sum(
            ps.shares * ps.last_close for ps in pos.values())

        # ── 1. 执行昨日排队的卖出（T+1 开盘）──
        for j in list(pending_exit):
            if j not in pos:
                pending_exit.pop(j)          # 已被盘中止损平掉 → 清理，避免"幽灵卖单"
                continue
            if not A.has[i, j]:
                continue                      # 停牌：保留到下一个有交易的日子
            close_pos(j, A.open[i, j] * (1 - slip), i, pending_exit.pop(j))

        # ── 2. 执行昨日排队的买入（T+1 开盘）──
        opened_today = 0
        for j, sig_close in list(pending_entry.items()):
            pending_entry.pop(j)
            if not A.has[i, j]:
                skipped["no_bar"] += 1
                continue
            if j in pos:
                continue
            if len(pos) >= sz.max_positions:
                skipped["full"] += 1
                continue
            if ex.forbid_same_day_rebuy and j in sold_today:
                skipped["rebuy"] += 1
                continue
            o = A.open[i, j]
            if ex.max_entry_gap_pct and o > sig_close * (1 + ex.max_entry_gap_pct / 100):
                skipped["gap"] += 1
                continue
            em = float(entry_mult[i, j]) if entry_mult is not None else 1.0
            if em <= 0:
                skipped["macro"] += 1
                continue
            px = o * (1 + slip)
            stop_px = (px - A.atr[i - 1, j] * p.atr_stop_mult
                       if p.atr_stop_mult > 0 and i > 0 and np.isfinite(A.atr[i - 1, j])
                       else px * (1 - p.stop_loss_pct / 100))
            if not (0 < stop_px < px):
                stop_px = px * (1 - p.stop_loss_pct / 100)

            if sz.mode == "risk_pct":
                budget = equity_prev * (sz.risk_pct / 100) / max(px - stop_px, 1e-9) * px
            else:
                budget = equity_prev * sz.position_pct
            budget = min(budget, equity_prev * sz.max_position_pct,
                         cash * (1 - sz.cash_buffer_pct / 100)) * min(1.0, em)
            lot = int(lots[j])
            shares = int(math.floor(budget / px / lot) * lot)
            while shares > 0 and shares * px + fee_f(shares * px) > cash:
                shares -= lot
            if shares <= 0:
                skipped["lot" if budget > 0 else "cash"] += 1
                continue
            notional = shares * px
            cash -= notional + fee_f(notional)
            pos[j] = _Pos(A.tickers[j], shares, px, i, stop_px, px, px, hold=0)
            opened_today += 1

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

        # ── 4. 收盘后扫描新信号（仅对次日有效）──
        if len(pos) < sz.max_positions:
            for j in np.flatnonzero(A.entry[i] & A.has[i]):
                j = int(j)
                if j in pos or j in pending_exit:
                    continue
                pending_entry[j] = float(A.close[i, j])

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
