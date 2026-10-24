"""metrics.py 的直接测试（2026-10-24 复核）：CAGR / 最大回撤 / Calmar 是研究的判定门槛（例如「Calmar 要 +0.03」），以前没有直接测试。
用手算得出的序列：2021-01-01〜2025-01-01 正好 1461 天 = 4 × 365.25 天。"""
import math

import numpy as np
import pandas as pd
import pytest

from qbreak import metrics as M

IDX = pd.to_datetime(["2021-01-01", "2022-01-01", "2023-01-01", "2024-01-01", "2025-01-01"])
EQ = pd.Series([100.0, 125.0, 100.0, 75.0, 146.41], index=IDX)        # 146.41 / 100 = 1.1 ** 4 → CAGR 正好 10%
TRADES = pd.DataFrame({"pnl": [10.0, -5.0, -3.0, -1.0, 8.0, -2.0, 0.0],
                       "ret_pct": [5.0, -2.0, -1.0, -0.5, 4.0, -1.5, 0.0],
                       "hold_days": [3, 5, 2, 4, 10, 1, 3],
                       "exit_date": ["2021-06-01", "2022-03-01", "2022-04-01", "2023-05-01", "2023-06-01", "2024-02-01", "2024-03-01"]})


def test_cagr_max_drawdown_and_calmar_on_a_known_series():
    m = M.compute_metrics(TRADES, EQ)
    assert M._safe_cagr(EQ) == pytest.approx(0.10, abs=1e-12)
    assert m["cagr_pct"] == 10.0
    assert m["total_ret_pct"] == 46.41
    assert m["max_dd_pct"] == -40.0                                     # 峰 125 → 谷 75
    assert m["calmar"] == 0.25                                           # 10% / 40%
    assert m["dd_days"] == 2                                             # 水下的点：100（2023）、75（2024）；2025 创新高
    assert m["final_equity"] == 146.0


def test_max_drawdown_takes_the_deepest_not_the_latest():
    idx = pd.date_range("2022-01-03", periods=7, freq="D")
    eq = pd.Series([100, 80, 120, 108, 130, 65, 140], index=idx, dtype=float)   # -20%、-10%、-50%（最深的在后面）
    m = M.compute_metrics(pd.DataFrame(), eq)
    assert m["max_dd_pct"] == -50.0 and m["dd_days"] == 1
    eq2 = pd.Series([100, 50, 60, 70, 80, 90, 95], index=idx, dtype=float)     # 一直没回到 100：水下 6 个点
    m2 = M.compute_metrics(pd.DataFrame(), eq2)
    assert m2["max_dd_pct"] == -50.0 and m2["dd_days"] == 6 and m2["total_ret_pct"] == -5.0


def test_trade_stats():
    m = M.compute_metrics(TRADES, EQ)
    assert m["trades"] == 7 and m["trades_per_year"] == 1.8              # 7 笔 / 4 年
    assert m["win_rate"] == round(2 / 7 * 100, 1)                        # pnl = 0 算亏（不是 > 0）
    assert m["profit_factor"] == round(18 / 11, 2)                       # 盈 10 + 8；亏 5 + 3 + 1 + 2 + 0
    assert m["max_consec_loss"] == 3 and M.max_consecutive_losses(pd.Series([1, 0, -1, 2, -1])) == 2
    assert m["avg_win_pct"] == 4.5 and m["avg_loss_pct"] == -1.0
    assert m["expectancy_pct"] == round(2 / 7 * 4.5 + 5 / 7 * -1.0, 2)
    assert m["payoff"] == 4.5 and m["avg_hold"] == round(28 / 7, 1)


def test_sharpe_and_sortino_match_the_formula():
    idx = pd.date_range("2023-01-02", periods=6, freq="B")
    eq = pd.Series([100.0, 101.0, 100.0, 102.0, 101.0, 103.0], index=idx)
    d = eq.pct_change().dropna()
    m = M.compute_metrics(pd.DataFrame(), eq)
    assert m["sharpe"] == round(d.mean() / d.std(ddof=1) * math.sqrt(252), 2)
    assert m["sortino"] == round(d.mean() / d[d < 0].std(ddof=1) * math.sqrt(252), 2)
    rf = M.compute_metrics(pd.DataFrame(), eq, rf_annual=0.252)          # 每天 0.1% 的无风险利率
    assert rf["sharpe"] == round((d - 0.001).mean() / (d - 0.001).std(ddof=1) * math.sqrt(252), 2)


def test_edge_cases_flat_rising_and_empty():
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    flat = M.compute_metrics(pd.DataFrame(), pd.Series([100.0] * 5, index=idx))
    assert flat["max_dd_pct"] == 0.0 and flat["calmar"] == 0.0 and flat["sharpe"] == 0.0 and flat["cagr_pct"] == 0.0
    up = M.compute_metrics(pd.DataFrame(), pd.Series([100.0, 101, 102, 103, 104], index=idx))
    assert up["max_dd_pct"] == 0.0 and up["calmar"] == 0.0 and up["dd_days"] == 0      # 没有回撤：Calmar 记 0（不是无穷大）
    assert up["trades"] == 0 and up["profit_factor"] == 0.0
    assert M.compute_metrics(pd.DataFrame(), pd.Series(dtype=float)) == {}
    assert M._safe_cagr(pd.Series([100.0], index=idx[:1])) == 0.0
    assert M._safe_cagr(pd.Series([0.0, 10.0], index=idx[:2])) == 0.0   # 起点 ≤ 0：不算
    only_wins = TRADES.assign(pnl=[1.0] * 7, ret_pct=[1.0] * 7)
    assert M.compute_metrics(only_wins, EQ)["profit_factor"] == 999.0   # 没有亏损：PF 记 999
    assert np.isfinite(M.compute_metrics(only_wins, EQ)["calmar"])


def test_yearly_table():
    yt = M.yearly_table(EQ, TRADES)
    assert yt["year"].tolist() == [2021, 2022, 2023, 2024, 2025]
    assert yt["ret_pct"].tolist() == [0.0, 25.0, -20.0, -25.0, 95.21]   # 每年对上一年末：100 → 125 → 100 → 75 → 146.41
    assert yt["trades"].tolist() == [1, 2, 2, 2, 0]
    assert yt["max_dd_pct"].tolist() == [0.0, 0.0, 0.0, 0.0, 0.0]       # 每年只有一个点
