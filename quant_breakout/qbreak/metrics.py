"""metrics.py — 绩效指标（パフォーマンス指標）。

原版只有 8 个指标，且 Sharpe 用的是「组合日收益」而不是超额收益；
这里补上实盘更关心的几个：Sortino、期望值、最大连亏、暴露度、年均交易次数、
以及**按年**拆分的收益 —— 一条 5 年 CAGR 常常是某一年暴涨撑起来的。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _safe_cagr(eq: pd.Series) -> float:
    if len(eq) < 2 or eq.iloc[0] <= 0:
        return 0.0
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    ratio = max(eq.iloc[-1] / eq.iloc[0], 1e-12)
    return ratio ** (1 / years) - 1


def max_consecutive_losses(pnl: pd.Series) -> int:
    run = best = 0
    for x in pnl:
        run = run + 1 if x <= 0 else 0
        best = max(best, run)
    return best


def compute_metrics(trades: pd.DataFrame, eq: pd.Series,
                    exposure: pd.Series | None = None,
                    rf_annual: float = 0.0) -> dict:
    if eq is None or eq.empty:
        return {}
    daily = eq.pct_change().dropna()
    rf_d = rf_annual / TRADING_DAYS
    exc = daily - rf_d
    sd = exc.std(ddof=1)
    sharpe = float(exc.mean() / sd * np.sqrt(TRADING_DAYS)) if sd and sd > 0 else 0.0
    dn = exc[exc < 0].std(ddof=1)
    sortino = float(exc.mean() / dn * np.sqrt(TRADING_DAYS)) if dn and dn > 0 else 0.0
    dd = eq / eq.cummax() - 1
    max_dd = float(dd.min()) if len(dd) else 0.0
    cagr = _safe_cagr(eq)
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)

    n = len(trades)
    if n:
        wins = trades["pnl"] > 0
        gp = float(trades.loc[wins, "pnl"].sum())
        gl = float(-trades.loc[~wins, "pnl"].sum())
        win_rate = float(wins.mean())
        avg_win = float(trades.loc[wins, "ret_pct"].mean()) if wins.any() else 0.0
        avg_loss = float(trades.loc[~wins, "ret_pct"].mean()) if (~wins).any() else 0.0
        pf = gp / gl if gl > 0 else (np.inf if gp > 0 else 0.0)
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss   # 每笔期望收益 %
        mcl = max_consecutive_losses(trades["pnl"])
    else:
        gp = gl = win_rate = avg_win = avg_loss = expectancy = 0.0
        pf, mcl = 0.0, 0

    # 最长回撤持续期（水下天数）
    under = (dd < -1e-12).to_numpy()
    longest, run = 0, 0
    for u in under:
        run = run + 1 if u else 0
        longest = max(longest, run)

    return dict(
        trades=n,
        trades_per_year=round(n / years, 1),
        win_rate=round(win_rate * 100, 1),
        cagr_pct=round(cagr * 100, 2),
        total_ret_pct=round((eq.iloc[-1] / eq.iloc[0] - 1) * 100, 2),
        max_dd_pct=round(max_dd * 100, 2),
        dd_days=int(longest),
        sharpe=round(sharpe, 2),
        sortino=round(sortino, 2),
        calmar=round(cagr / abs(max_dd), 2) if max_dd < -1e-12 else 0.0,
        profit_factor=round(pf, 2) if np.isfinite(pf) else 999.0,
        expectancy_pct=round(expectancy, 2),
        avg_win_pct=round(avg_win, 2),
        avg_loss_pct=round(avg_loss, 2),
        payoff=round(abs(avg_win / avg_loss), 2) if avg_loss else 0.0,
        max_consec_loss=int(mcl),
        avg_hold=round(float(trades["hold_days"].mean()), 1) if n else 0.0,
        exposure_pct=round(float(exposure.mean()) * 100, 1) if exposure is not None and len(exposure) else 0.0,
        final_equity=round(float(eq.iloc[-1]), 0),
    )


def yearly_table(eq: pd.Series, trades: pd.DataFrame) -> pd.DataFrame:
    """按年拆：看收益是不是全靠某一年。"""
    if eq.empty:
        return pd.DataFrame()
    yr = eq.resample("YE").last()
    first = pd.Series([eq.iloc[0]], index=[eq.index[0]])
    base = pd.concat([first, yr]).drop_duplicates()
    rows = []
    for y, g in eq.groupby(eq.index.year):
        prev = base[base.index < g.index[0]]
        start = float(prev.iloc[-1]) if len(prev) else float(g.iloc[0])
        ddy = float((g / g.cummax() - 1).min())
        nt = 0
        if not trades.empty:
            nt = int((pd.to_datetime(trades["exit_date"]).dt.year == y).sum())
        rows.append({"year": int(y), "ret_pct": round((float(g.iloc[-1]) / start - 1) * 100, 2),
                     "max_dd_pct": round(ddy * 100, 2), "trades": nt})
    return pd.DataFrame(rows)


def format_report(res, name: str = "回测", benchmark: pd.Series | None = None) -> str:
    m = res.metrics
    if not m:
        return "（无结果）"
    L = [f"\n═══ {name} 结果 ═══",
         f"期间          : {res.equity.index[0].date()} ~ {res.equity.index[-1].date()}",
         f"交易次数      : {m['trades']}  （年均 {m['trades_per_year']}）",
         f"胜率          : {m['win_rate']}%   盈亏比 PF {m['profit_factor']}   赔率 {m['payoff']}",
         f"每笔期望      : {m['expectancy_pct']}%  （平均盈 {m['avg_win_pct']}% / 平均亏 {m['avg_loss_pct']}%）",
         f"年化 CAGR     : {m['cagr_pct']}%   累计 {m['total_ret_pct']}%",
         f"最大回撤      : {m['max_dd_pct']}%   水下 {m['dd_days']} 个交易日",
         f"夏普 / 索提诺 : {m['sharpe']} / {m['sortino']}   Calmar {m['calmar']}",
         f"最大连亏      : {m['max_consec_loss']} 笔   平均持有 {m['avg_hold']} 日   资金暴露 {m['exposure_pct']}%",
         f"期末权益      : {m['final_equity']:,.0f}"]
    if benchmark is not None and not benchmark.empty:
        bm = compute_metrics(pd.DataFrame(columns=["pnl", "ret_pct", "hold_days"]), benchmark)
        L.append(f"基准(等权买入持有): CAGR {bm['cagr_pct']}%  最大回撤 {bm['max_dd_pct']}%  夏普 {bm['sharpe']}")
    if getattr(res, "skipped", None):
        sk = {k: v for k, v in res.skipped.items() if v}
        if sk:
            L.append(f"被过滤的信号  : {sk}  "
                     f"(gap=跳空过大 full=持仓已满 cash/lot=资金不足 no_bar=停牌 rebuy=当日已卖)")
    if not res.trades.empty:
        L.append("\n出场原因分布:\n" + res.trades["reason"].value_counts().to_string())
        yt = yearly_table(res.equity, res.trades)
        if not yt.empty:
            L.append("\n分年度:\n" + yt.to_string(index=False))
    return "\n".join(L)
