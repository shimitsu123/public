"""
backtest.py — 第1阶段：组合级回测引擎（バックテスト / backtest）。
纯 pandas/numpy 实现，无需 backtrader（沙箱不可装；若你本地想用 backtrader，信号逻辑可直接搬到 next()）。

成交假设（保守）：
  • 信号出现在 T 日收盘 → T+1 日开盘价 × (1+滑点) 买入   ← 消除前视偏差
  • 止损/止盈/跟踪止损：盘中触及即按触发价成交；若开盘跳空越过则按开盘价成交
  • MACD 死叉 / 最长持有：T+1 开盘卖出
  • 手续费双边收取
运行：python backtest.py [JP|US]
"""
import sys
import math
import numpy as np
import pandas as pd
from config import (StrategyParams, BacktestConfig, DEFAULT_PARAMS, DEFAULT_BT,
                    UNIVERSE_JP, UNIVERSE_US)
from data import load_universe
from strategy import compute_indicators


# ────────────────────────── 核心引擎 ──────────────────────────
def run_backtest(data: dict[str, pd.DataFrame], p: StrategyParams, bt: BacktestConfig,
                 verbose: bool = False) -> dict:
    """返回 {'trades': DataFrame, 'equity': Series, 'metrics': dict}"""
    ind = {t: compute_indicators(df, p) for t, df in data.items()}
    all_dates = sorted(set().union(*[df.index for df in ind.values()]))
    cash = bt.initial_cash
    positions: dict[str, dict] = {}          # ticker -> {shares, entry_px, entry_date, peak, stop}
    pending_entry: set[str] = set()          # T 日信号，T+1 开盘执行
    pending_exit: dict[str, str] = {}        # ticker -> reason
    trades, equity = [], []
    fee = bt.commission_pct / 100
    slip = bt.slippage_pct / 100

    def mark_to_market(d):
        v = cash
        for t, pos in positions.items():
            row = ind[t].loc[d] if d in ind[t].index else None
            v += pos["shares"] * (row["Close"] if row is not None else pos["last_close"])
        return v

    for d in all_dates:
        # ── 1. 先处理昨日排队的卖出（T+1 开盘）──
        for t, reason in list(pending_exit.items()):
            if t in positions and d in ind[t].index:
                px = ind[t].at[d, "Open"] * (1 - slip)
                _close_position(t, px, d, reason, positions, trades, fee)
                cash += positions.pop(t)["shares"] * px * (1 - fee)
                pending_exit.pop(t)

        # ── 2. 处理昨日排队的买入（T+1 开盘）──
        for t in list(pending_entry):
            pending_entry.discard(t)
            if t in positions or len(positions) >= bt.max_positions or d not in ind[t].index:
                continue
            px = ind[t].at[d, "Open"] * (1 + slip)
            budget = min(mark_to_market(d) * bt.position_pct, cash)
            shares = math.floor(budget / (px * (1 + fee)) / bt.lot_size) * bt.lot_size
            if shares <= 0:
                continue
            cash -= shares * px * (1 + fee)
            positions[t] = dict(shares=shares, entry_px=px, entry_date=d, peak=px,
                                last_close=px, hold=0)

        # ── 3. 盘中止损/止盈/跟踪 ──
        for t, pos in list(positions.items()):
            if d not in ind[t].index:
                continue
            row = ind[t].loc[d]
            pos["hold"] += 1
            pos["last_close"] = row["Close"]
            stop_px = pos["entry_px"] * (1 - p.stop_loss_pct / 100)
            trail_px = pos["peak"] * (1 - p.trailing_stop_pct / 100) if p.trailing_stop_pct else -np.inf
            tp_px = pos["entry_px"] * (1 + p.take_profit_pct / 100) if p.take_profit_pct else np.inf
            exit_px, reason = None, None
            hard_stop = max(stop_px, trail_px)
            if row["Open"] <= hard_stop:                 # 跳空低开直接止损
                exit_px, reason = row["Open"], "gap_stop"
            elif row["Low"] <= hard_stop:                # 盘中触及
                exit_px, reason = hard_stop, ("trail" if trail_px > stop_px else "stop")
            elif row["High"] >= tp_px:
                exit_px, reason = max(tp_px, row["Open"]), "take_profit"
            if exit_px is not None:
                exit_px *= (1 - slip)
                _close_position(t, exit_px, d, reason, positions, trades, fee)
                cash += positions.pop(t)["shares"] * exit_px * (1 - fee)
                continue
            pos["peak"] = max(pos["peak"], row["High"])
            # 收盘后判断：死叉 / 超时 → 明日开盘卖
            if (p.exit_on_macd_dead_cross and row["dead_cross"]):
                pending_exit[t] = "dead_cross"
            elif p.max_hold_days and pos["hold"] >= p.max_hold_days:
                pending_exit[t] = "max_hold"

        # ── 4. 收盘后扫描新信号 ──
        for t, df in ind.items():
            if d in df.index and df.at[d, "entry"] and t not in positions:
                pending_entry.add(t)

        equity.append((d, mark_to_market(d)))

    # 期末强平（统计用）
    last = all_dates[-1]
    for t, pos in list(positions.items()):
        px = pos["last_close"]
        _close_position(t, px, last, "end", positions, trades, fee)
        cash += positions.pop(t)["shares"] * px * (1 - fee)

    trades_df = pd.DataFrame(trades)
    eq = pd.Series(dict(equity)).sort_index()
    return {"trades": trades_df, "equity": eq, "metrics": compute_metrics(trades_df, eq, bt)}


def _close_position(t, px, d, reason, positions, trades, fee):
    pos = positions[t]
    gross = (px - pos["entry_px"]) * pos["shares"]
    cost = (pos["entry_px"] + px) * pos["shares"] * fee
    trades.append(dict(ticker=t, entry_date=pos["entry_date"], exit_date=d,
                       entry_px=round(pos["entry_px"], 2), exit_px=round(px, 2),
                       shares=pos["shares"], pnl=round(gross - cost, 2),
                       ret_pct=round((px / pos["entry_px"] - 1) * 100, 2),
                       hold_days=pos["hold"], reason=reason))


# ────────────────────────── 指标 ──────────────────────────
def compute_metrics(trades: pd.DataFrame, eq: pd.Series, bt: BacktestConfig) -> dict:
    if eq.empty:
        return {}
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    total_ret = eq.iloc[-1] / eq.iloc[0] - 1
    cagr = (1 + total_ret) ** (1 / years) - 1                       # 年化收益（年率リターン / CAGR）
    daily = eq.pct_change().dropna()
    sharpe = (daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0.0  # 夏普（シャープレシオ）
    dd = eq / eq.cummax() - 1
    max_dd = dd.min()                                               # 最大回撤（最大ドローダウン）
    n = len(trades)
    win_rate = (trades["pnl"] > 0).mean() if n else 0.0            # 胜率（勝率）
    gp = trades.loc[trades["pnl"] > 0, "pnl"].sum() if n else 0
    gl = -trades.loc[trades["pnl"] <= 0, "pnl"].sum() if n else 0
    pf = gp / gl if gl > 0 else np.inf                              # 盈亏比（プロフィットファクター）
    return dict(
        trades=n, win_rate=round(win_rate * 100, 1), cagr_pct=round(cagr * 100, 2),
        total_ret_pct=round(total_ret * 100, 2), max_dd_pct=round(max_dd * 100, 2),
        sharpe=round(sharpe, 2), profit_factor=round(pf, 2),
        avg_ret_pct=round(trades["ret_pct"].mean(), 2) if n else 0,
        avg_hold=round(trades["hold_days"].mean(), 1) if n else 0,
        calmar=round(cagr / abs(max_dd), 2) if max_dd < 0 else np.inf,
    )


def print_report(res: dict):
    m = res["metrics"]
    print("\n═══ 回测结果 ═══")
    print(f"交易次数      : {m['trades']}")
    print(f"胜率          : {m['win_rate']}%")
    print(f"年化收益 CAGR : {m['cagr_pct']}%   (累计 {m['total_ret_pct']}%)")
    print(f"最大回撤      : {m['max_dd_pct']}%")
    print(f"夏普比率      : {m['sharpe']}")
    print(f"盈亏比 PF     : {m['profit_factor']}   平均单笔 {m['avg_ret_pct']}%  平均持有 {m['avg_hold']} 日")
    if not res["trades"].empty:
        print("\n出场原因分布:\n", res["trades"]["reason"].value_counts().to_string())
        print("\n最近 5 笔:\n", res["trades"].tail(5).to_string(index=False))


if __name__ == "__main__":
    market = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BT.market).upper()
    bt = BacktestConfig(market=market, lot_size=100 if market == "JP" else 1,
                        commission_pct=0.055 if market == "JP" else 0.1)
    universe = UNIVERSE_JP if market == "JP" else UNIVERSE_US
    print(f"加载 {market} 股票池 {len(universe)} 只，{bt.years} 年 …")
    data = load_universe(universe, bt.years)
    res = run_backtest(data, DEFAULT_PARAMS, bt)
    print_report(res)
    res["trades"].to_csv("trades.csv", index=False)
    res["equity"].to_csv("equity.csv", header=["equity"])
    print("\n已保存 trades.csv / equity.csv")
