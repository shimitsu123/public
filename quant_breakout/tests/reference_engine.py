"""reference_engine.py — 独立的参考回测器（差分测试用）。

按 README「成交假设」逐条、逐日、逐票地模拟，刻意写成最直白的循环，不复用 qbreak.engine 的任何代码：
  • 信号在 T 日收盘成立 → T+1 开盘买入，价格 = 开盘 ×(1+滑点)；开盘高于信号日收盘 ×(1+跳空上限) 则放弃
  • 止损 / 跟踪止损 / 止盈用收盘价判断 → 次日开盘卖出，价格 = 开盘 ×(1−滑点)
  • 股数在信号日收盘就定：预算 = 收盘权益 × position_pct × 宏观倍数(成交日)，再受 单只上限、
    预计可用资金×(1−缓冲) 约束（预计可用 = 现金 + 待卖出按收盘估的净额 − 已计划买入的成本），
    按 收盘×(1+滑点) 换算、单元取整；名额 = 上限 − (持仓 − 待卖出) − 已计划
  • 开盘现金不够 → 按单元减；开盘时持仓已满（待卖出没卖掉）→ 放弃
  • 同一票当天卖出后不再买回；持仓满（含待卖出的）则当天收盘不扫描新信号
  • 日本株一整天张贴ストップ安 → 卖单顺延；张贴ストップ高 → 买单作废
  • 期末按最后收盘价平仓（"end"）
只覆盖现行配置用到的规则（next_open 止损、equity_pct 仓位、ATR 止损关闭）。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _limit_width_jp(base: float) -> float:
    table = [(100, 30), (200, 50), (500, 80), (700, 100), (1000, 150), (1500, 300), (2000, 400), (3000, 500),
             (5000, 700), (7000, 1000), (10000, 1500), (15000, 3000), (20000, 4000), (30000, 5000), (50000, 7000),
             (70000, 10000), (100000, 15000), (150000, 30000), (200000, 40000), (300000, 50000), (500000, 70000)]
    for upper, w in table:
        if base < upper:
            return w
    return 100000


def _locked(prev_close, hi, lo, cl, jp: bool) -> str | None:
    if not jp or not (prev_close and prev_close > 0):
        return None
    if hi - lo > prev_close * 0.005:
        return None
    w = _limit_width_jp(prev_close)
    if cl <= prev_close - 0.8 * w:
        return "down"
    if cl >= prev_close + 0.8 * w:
        return "up"
    return None


def reference_backtest(ind: dict[str, pd.DataFrame], p, bt, start=None, entry_mult=None,
                       lot_of=None) -> tuple[pd.DataFrame, pd.Series]:
    ex, sz = bt.exec_cfg, bt.sizing
    jp = ex.market.upper() == "JP"
    names = list(ind.keys())
    dates = sorted(set().union(*[df.index for df in ind.values()]))
    if start is not None:
        first = next(k for k, d in enumerate(dates) if d >= pd.Timestamp(start))
    else:
        first = 0
    col = {t: ind[t].reindex(dates) for t in names}
    lot_of = lot_of or (lambda t: 100 if jp else 1)

    def fee(x):
        f = abs(x) * ex.commission_pct / 100
        if ex.commission_min:
            f = max(f, ex.commission_min)
        if ex.commission_max:
            f = min(f, ex.commission_max)
        return f

    def bar(t, k):
        r = col[t].iloc[k]
        return None if pd.isna(r["Close"]) else r

    cash = float(sz.initial_cash)
    held: dict[str, dict] = {}
    buys: list[tuple[str, float, int]] = []
    sells: dict[str, str] = {}
    trades, eq = [], []
    slip = ex.slippage_pct / 100
    for k in range(first, len(dates)):
        d = dates[k]
        sold_today = set()
        # 卖出（开盘）
        for t in list(sells):
            if t not in held:
                sells.pop(t); continue
            r = bar(t, k)
            if r is None:
                continue
            prev = bar(t, k - 1) if k > 0 else None
            if _locked(prev["Close"] if prev is not None else None, r["High"], r["Low"], r["Close"], jp) == "down":
                continue
            h = held.pop(t)
            px = r["Open"] * (1 - slip)
            cash += h["shares"] * px - fee(h["shares"] * px)
            trades.append({"ticker": t, "entry_date": dates[h["entry_k"]], "exit_date": d, "entry_px": h["entry_px"],
                           "exit_px": px, "shares": h["shares"], "reason": sells.pop(t)})
            sold_today.add(t)
        # 买入（开盘）：股数是前一天收盘定好的
        todo, buys = buys, []
        for t, sig_close, shares in todo:
            r = bar(t, k)
            if r is None or t in held or len(held) >= sz.max_positions:
                continue
            if ex.forbid_same_day_rebuy and t in sold_today:
                continue
            o = r["Open"]
            if ex.max_entry_gap_pct and o > sig_close * (1 + ex.max_entry_gap_pct / 100):
                continue
            prev = bar(t, k - 1) if k > 0 else None
            if _locked(prev["Close"] if prev is not None else None, r["High"], r["Low"], r["Close"], jp) == "up":
                continue
            px = o * (1 + slip)
            lot = lot_of(t)
            while shares > 0 and shares * px + fee(shares * px) > cash:
                shares -= lot
            if shares <= 0:
                continue
            cash -= shares * px + fee(shares * px)
            held[t] = {"shares": shares, "entry_px": px, "entry_k": k, "stop": px * (1 - p.stop_loss_pct / 100),
                       "peak": px, "hold": 0, "armed": False, "last_close": px}
        # 收盘管理
        for t, h in held.items():
            r = bar(t, k)
            if r is None:
                continue
            h["hold"] += 1
            if p.trailing_arm_pct and not h["armed"] and r["High"] >= h["entry_px"] * (1 + p.trailing_arm_pct / 100):
                h["armed"] = True
            trail_on = p.trailing_stop_pct > 0 and (h["armed"] or not p.trailing_arm_pct)
            h["peak"] = max(h["peak"], r["High"])
            trail = h["peak"] * (1 - p.trailing_stop_pct / 100) if trail_on else -np.inf
            hard = max(h["stop"], trail)
            tp = h["entry_px"] * (1 + p.take_profit_pct / 100) if p.take_profit_pct else np.inf
            c = r["Close"]
            why = None
            if c <= hard:
                why = "trail" if trail > h["stop"] else "stop"
            elif c >= tp:
                why = "take_profit"
            h["last_close"] = c
            if why is None:
                if p.exit_on_climax and bool(r.get("climax", False)) and (c / h["entry_px"] - 1) * 100 >= p.climax_min_gain_pct:
                    why = "climax"
                elif p.exit_on_macd_dead_cross and bool(r["dead_cross"]):
                    why = "dead_cross"
                elif p.max_hold_days and h["hold"] >= p.max_hold_days:
                    why = "max_hold"
            if why:
                sells[t] = why
        # 新信号（收盘）：现在就定明天的股数
        if len(held) < sz.max_positions:
            eq_now = cash + sum(h["shares"] * h["last_close"] for h in held.values())
            leaving = [t for t in sells if t in held]
            est = cash
            for t in leaving:
                sp = held[t]["last_close"] * (1 - slip)
                est += held[t]["shares"] * sp - fee(held[t]["shares"] * sp)
            spent = 0.0
            for t in sorted(names):
                r = bar(t, k)
                if r is None or not bool(r["entry"]) or t in held or t in sells:
                    continue
                em = 1.0
                if entry_mult is not None and k + 1 < len(dates):
                    em = float(entry_mult[k + 1][names.index(t)])
                if em <= 0:
                    continue
                if len(held) - len(leaving) + len(buys) >= sz.max_positions:
                    continue
                c = float(r["Close"])
                px = c * (1 + slip)
                budget = min(eq_now * sz.position_pct * min(1.0, em), eq_now * sz.max_position_pct,
                             (est - spent) * (1 - sz.cash_buffer_pct / 100))
                lot = lot_of(t)
                shares = int(math.floor(budget / px / lot) * lot) if budget > 0 else 0
                if shares <= 0:
                    continue
                buys.append((t, c, shares))
                spent += shares * px + fee(shares * px)
        eq.append(cash + sum(h["shares"] * h["last_close"] for h in held.values()))
    for t, h in list(held.items()):
        trades.append({"ticker": t, "entry_date": dates[h["entry_k"]], "exit_date": dates[-1], "entry_px": h["entry_px"],
                       "exit_px": h["last_close"], "shares": h["shares"], "reason": "end"})
    return pd.DataFrame(trades), pd.Series(eq, index=pd.DatetimeIndex(dates[first:]))
