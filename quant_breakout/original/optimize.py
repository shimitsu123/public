"""
optimize.py — 第2阶段：网格搜索（グリッドサーチ / grid search）+ Walk-Forward 验证。

Walk-Forward（ウォークフォワード分析）：
  把 5 年切成若干段，每段用前 train_years 年做样本内（IS）优化，
  取最优参数在紧接着的 test_months 个月样本外（OOS）验证，向前滚动。
  OOS 拼接后的表现才是"接近实盘"的表现；IS 表现再好也不算数。

稳健参数区间：对每个 IS 窗口的最优参数取分布（min/中位/max），
  并列出"在所有窗口里都排进前 20% 的参数组合"——这类参数才值得用。
运行：python optimize.py [JP|US]
"""
import sys
import itertools
import numpy as np
import pandas as pd
from dataclasses import replace
from config import (StrategyParams, BacktestConfig, DEFAULT_PARAMS,
                    UNIVERSE_JP, UNIVERSE_US)
from data import load_universe
from backtest import run_backtest

# ── 搜索空间（按需增减；组合数 = 各列表长度乘积）──
GRID = {
    "range_n":      [40, 60, 90],
    "range_x_pct":  [10.0, 15.0, 20.0],
    "macd_fast":    [8, 12],
    "macd_slow":    [21, 26],
    "macd_signal":  [9],
}
OBJECTIVE = "calmar"   # 优化目标：calmar(年化/回撤) 比 cagr 更抗过拟合；可改 "sharpe"
MIN_TRADES = 8         # IS 窗口内交易数少于此值 → 该参数组视为无效（避免靠 2 笔运气胜出）


def slice_data(data: dict, start, end) -> dict:
    out = {t: df.loc[start:end] for t, df in data.items()}
    return {t: df for t, df in out.items() if len(df) > 120}


def grid_search(data: dict, bt: BacktestConfig, base: StrategyParams) -> pd.DataFrame:
    keys, values = list(GRID.keys()), list(GRID.values())
    rows = []
    for combo in itertools.product(*values):
        kw = dict(zip(keys, combo))
        if kw.get("macd_fast", 1) >= kw.get("macd_slow", 99):
            continue
        p = replace(base, **kw)
        m = run_backtest(data, p, bt)["metrics"]
        score = m.get(OBJECTIVE, -np.inf)
        if m.get("trades", 0) < MIN_TRADES or not np.isfinite(score):
            score = -np.inf
        rows.append({**kw, **m, "score": score})
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)


def walk_forward(data: dict, bt: BacktestConfig, base: StrategyParams,
                 train_years: float = 2.0, test_months: int = 6) -> tuple[pd.DataFrame, pd.Series]:
    all_idx = sorted(set().union(*[df.index for df in data.values()]))
    start, end = all_idx[0], all_idx[-1]
    windows, oos_equity = [], []
    t0 = start
    while True:
        is_end = t0 + pd.DateOffset(years=train_years)
        oos_end = is_end + pd.DateOffset(months=test_months)
        if is_end >= end:
            break
        oos_end = min(oos_end, end)
        is_data = slice_data(data, t0, is_end)
        oos_data = slice_data(data, is_end, oos_end)
        if not is_data or not oos_data:
            break
        gs = grid_search(is_data, bt, base)
        best = gs.iloc[0]
        best_kw = {k: (int(best[k]) if isinstance(GRID[k][0], int) else float(best[k])) for k in GRID}
        oos = run_backtest(oos_data, replace(base, **best_kw), bt)
        m = oos["metrics"]
        windows.append({"is_start": t0.date(), "is_end": is_end.date(), "oos_end": oos_end.date(),
                        **best_kw, "is_score": round(best["score"], 2),
                        "oos_cagr": m.get("cagr_pct"), "oos_dd": m.get("max_dd_pct"),
                        "oos_sharpe": m.get("sharpe"), "oos_trades": m.get("trades"),
                        "_gs": gs})
        # OOS 权益归一后拼接（每段从 1 开始），得到连续 OOS 曲线
        e = oos["equity"] / oos["equity"].iloc[0]
        if oos_equity:
            e = e * oos_equity[-1].iloc[-1]
        oos_equity.append(e)
        t0 = t0 + pd.DateOffset(months=test_months)
    wf = pd.DataFrame(windows)
    eq = pd.concat(oos_equity) if oos_equity else pd.Series(dtype=float)
    return wf, eq


def robust_ranges(wf: pd.DataFrame) -> pd.DataFrame:
    """每个参数在各窗口最优值的分布 → 稳健区间。"""
    rows = []
    for k in GRID:
        v = wf[k]
        rows.append({"param": k, "min": v.min(), "median": v.median(), "max": v.max(),
                     "mode": v.mode().iloc[0], "stability": round((v == v.mode().iloc[0]).mean() * 100, 0)})
    return pd.DataFrame(rows)


def consistently_good(wf: pd.DataFrame, top_frac: float = 0.2) -> pd.DataFrame:
    """在每个 IS 窗口都排进前 top_frac 的参数组合（跨期稳定 = 更不容易是过拟合）。"""
    sets = []
    for gs in wf["_gs"]:
        k = max(1, int(len(gs) * top_frac))
        top = gs.head(k)[list(GRID)].astype(str).agg("|".join, axis=1)
        sets.append(set(top))
    common = set.intersection(*sets) if sets else set()
    return pd.DataFrame([dict(zip(GRID, c.split("|"))) for c in common])


if __name__ == "__main__":
    market = (sys.argv[1] if len(sys.argv) > 1 else "JP").upper()
    bt = BacktestConfig(market=market, lot_size=100 if market == "JP" else 1)
    universe = UNIVERSE_JP if market == "JP" else UNIVERSE_US
    data = load_universe(universe, bt.years)

    n_combo = int(np.prod([len(v) for v in GRID.values()]))
    print(f"参数组合数 {n_combo}，Walk-Forward 训练 2 年 / 测试 6 个月 …")
    wf, oos_eq = walk_forward(data, bt, DEFAULT_PARAMS)

    print("\n═══ Walk-Forward 各窗口（IS 最优参数 → OOS 表现）═══")
    print(wf.drop(columns="_gs").to_string(index=False))

    print("\n═══ 稳健参数区间（各窗口最优值分布；stability=众数出现比例%）═══")
    print(robust_ranges(wf).to_string(index=False))

    cg = consistently_good(wf)
    print("\n═══ 在所有窗口都进前 20% 的参数组合（推荐优先用这些）═══")
    print(cg.to_string(index=False) if not cg.empty else "（无——说明策略对参数敏感，需重新设计规则而非调参）")

    if not oos_eq.empty:
        years = (oos_eq.index[-1] - oos_eq.index[0]).days / 365.25
        cagr = oos_eq.iloc[-1] ** (1 / years) - 1
        dd = (oos_eq / oos_eq.cummax() - 1).min()
        print(f"\n拼接 OOS 曲线：年化 {cagr*100:.2f}%  最大回撤 {dd*100:.2f}%  "
              f"（这是最接近实盘期望的数字）")
    wf.drop(columns="_gs").to_csv("walk_forward.csv", index=False)
    print("已保存 walk_forward.csv")
