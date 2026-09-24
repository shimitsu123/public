"""optimize.py — 网格搜索（グリッドサーチ）+ Walk-Forward 验证。

原版最严重的方法论问题：样本外（OOS）窗口是把数据切成 6 个月再计算指标，
于是 range_n=60~90 的预热期就吃掉了 OOS 窗口的一半以上，
「样本外表现差」有很大一部分只是因为前 3 个月根本不可能产生信号。

这里改成：**指标始终在完整历史上计算，只限制引擎的交易窗口**。
因为指标在 t 时刻只用 ≤t 的数据，这样做不引入前视偏差，却让每个 OOS 窗口
从第一天起就是满血状态。

另外补充：
  • IS 分数加入「最少交易数」「最大回撤上限」双重过滤，避免 2 笔运气胜出
  • 输出参数敏感度（同一参数取不同值时的中位分数）——比单一最优组合更有信息量
  • 结果可直接 --save 写入 best_params.json
"""
from __future__ import annotations

import itertools
from dataclasses import replace

import numpy as np
import pandas as pd

from . import paths
from .config import BacktestConfig, StrategyParams
from .engine import run_backtest
from .metrics import compute_metrics
from .strategy import IndicatorCache
from .utils import setup_logging

log = setup_logging("optimize")

# 默认搜索空间（组合数 = 各列表长度乘积）
DEFAULT_GRID: dict[str, list] = {
    "range_n":      [40, 60, 90],
    "range_x_pct":  [10.0, 15.0, 20.0],
    "macd_fast":    [8, 12],
    "macd_slow":    [21, 26],
    "macd_signal":  [9],
}
OBJECTIVE = "calmar"   # calmar(年化/回撤) 比 cagr 抗过拟合；也可用 "sharpe" / "expectancy_pct"
MIN_TRADES = 8
MAX_DD_LIMIT = -60.0   # IS 回撤超过该值直接淘汰


def _coerce(grid: dict[str, list], k: str, v) -> object:
    proto = grid[k][0]
    if isinstance(proto, bool):
        return bool(v)
    if isinstance(proto, int):
        return int(round(float(v)))
    if isinstance(proto, float):
        return float(v)
    return v


def grid_search(cache: IndicatorCache, bt: BacktestConfig, base: StrategyParams,
                grid: dict[str, list] | None = None, start=None, end=None,
                objective: str = OBJECTIVE) -> pd.DataFrame:
    grid = grid or DEFAULT_GRID
    keys, values = list(grid), list(grid.values())
    rows = []
    for combo in itertools.product(*values):
        kw = dict(zip(keys, combo))
        try:
            p = replace(base, **kw).validate()
        except Exception:                 # 非法组合（如 fast>=slow）直接跳过
            continue
        try:
            res = run_backtest(cache.all(p), p, bt, start=start, end=end)
        except Exception as e:            # noqa: BLE001
            log.warning("参数 %s 回测失败: %s", kw, e)
            continue
        m = res.metrics
        score = float(m.get(objective, -np.inf))
        if (m.get("trades", 0) < MIN_TRADES or not np.isfinite(score)
                or m.get("max_dd_pct", 0) < MAX_DD_LIMIT):
            score = -np.inf
        rows.append({**kw, **m, "score": score})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.sort_values(["score", "trades"], ascending=[False, False]).reset_index(drop=True)


def walk_forward(data: dict[str, pd.DataFrame], bt: BacktestConfig, base: StrategyParams,
                 grid: dict[str, list] | None = None, train_years: float = 2.0,
                 test_months: int = 6, objective: str = OBJECTIVE,
                 index_close: pd.Series | None = None):
    """滚动窗口：训练 train_years → 测试 test_months → 向前滚动 test_months。
    index_close：基准指数收盘（相对强度过滤）；不传则该过滤在优化里不生效。"""
    grid = grid or DEFAULT_GRID
    cache = IndicatorCache(data, index_close)
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in data.values()])))
    start, end = gidx[0], gidx[-1]
    t0 = start
    windows, oos_eq_parts, oos_trades = [], [], []
    yrs, mos = int(train_years), int(round((train_years - int(train_years)) * 12))

    while True:
        is_end = t0 + pd.DateOffset(years=yrs, months=mos)
        oos_end = min(is_end + pd.DateOffset(months=test_months), end)
        if is_end >= end or (oos_end - is_end).days < 20:
            break
        gs = grid_search(cache, bt, base, grid, start=t0, end=is_end, objective=objective)
        if gs.empty or not np.isfinite(gs.iloc[0]["score"]):
            log.warning("窗口 %s~%s 没有任何合格参数组合（交易数不足），跳过",
                        t0.date(), is_end.date())
            t0 = t0 + pd.DateOffset(months=test_months)
            continue
        best = gs.iloc[0]
        best_kw = {k: _coerce(grid, k, best[k]) for k in grid}
        p_oos = replace(base, **best_kw).validate()
        oos = run_backtest(cache.all(p_oos), p_oos, bt, start=is_end, end=oos_end)
        m = oos.metrics
        windows.append({"is_start": t0.date(), "is_end": is_end.date(), "oos_end": oos_end.date(),
                        **best_kw, "is_score": round(float(best["score"]), 2),
                        "is_trades": int(best["trades"]),
                        "oos_cagr": m.get("cagr_pct"), "oos_dd": m.get("max_dd_pct"),
                        "oos_sharpe": m.get("sharpe"), "oos_trades": m.get("trades"),
                        "oos_win": m.get("win_rate"), "_gs": gs})
        e = oos.equity / oos.equity.iloc[0]
        if oos_eq_parts:
            e = e * float(oos_eq_parts[-1].iloc[-1])
            e = e.iloc[1:]                       # 去掉与上一段重复的首日
        oos_eq_parts.append(e)
        if not oos.trades.empty:
            oos_trades.append(oos.trades)
        t0 = t0 + pd.DateOffset(months=test_months)

    wf = pd.DataFrame(windows)
    eq = pd.concat(oos_eq_parts) if oos_eq_parts else pd.Series(dtype=float)
    eq = eq[~eq.index.duplicated(keep="last")].sort_index()
    tr = pd.concat(oos_trades, ignore_index=True) if oos_trades else pd.DataFrame(
        columns=["pnl", "ret_pct", "hold_days", "reason", "exit_date"])
    return wf, eq, tr


def robust_ranges(wf: pd.DataFrame, grid: dict[str, list]) -> pd.DataFrame:
    rows = []
    for k in grid:
        v = pd.to_numeric(wf[k], errors="coerce")
        mode = v.mode()
        mv = mode.iloc[0] if len(mode) else np.nan
        rows.append({"param": k, "min": v.min(), "median": v.median(), "max": v.max(),
                     "mode": mv, "stability%": round(float((v == mv).mean() * 100), 0)})
    return pd.DataFrame(rows)


def consistently_good(wf: pd.DataFrame, grid: dict[str, list],
                      top_frac: float = 0.2) -> pd.DataFrame:
    """在**每一个** IS 窗口都排进前 top_frac 的参数组合 —— 跨期稳定才不容易是过拟合。"""
    sets = []
    for gs in wf["_gs"]:
        gs = gs[np.isfinite(gs["score"])]
        if gs.empty:
            return pd.DataFrame()
        k = max(1, int(len(gs) * top_frac))
        sets.append(set(gs.head(k)[list(grid)].astype(str).agg("|".join, axis=1)))
    common = set.intersection(*sets) if sets else set()
    if not common:
        return pd.DataFrame()
    rows = [{k: _coerce(grid, k, v) for k, v in zip(grid, c.split("|"))} for c in sorted(common)]
    return pd.DataFrame(rows)


def sensitivity(wf: pd.DataFrame, grid: dict[str, list]) -> pd.DataFrame:
    """参数敏感度：把所有 IS 窗口的网格结果合并，看每个参数取不同值时的中位分数。
    某个参数换一档分数就崩 → 该策略对它过敏，实盘会很难受。"""
    allgs = pd.concat(list(wf["_gs"]), ignore_index=True)
    allgs = allgs[np.isfinite(allgs["score"])]
    rows = []
    for k in grid:
        for v in sorted(allgs[k].unique()):
            s = allgs.loc[allgs[k] == v, "score"]
            rows.append({"param": k, "value": v, "n": len(s),
                         "median_score": round(float(s.median()), 3),
                         "p25": round(float(s.quantile(0.25)), 3)})
    return pd.DataFrame(rows)


def save_best(params: StrategyParams, path=None) -> str:
    path = path or paths.params_file()
    params.save(path)
    return str(path)


def report(wf: pd.DataFrame, oos_eq: pd.Series, oos_tr: pd.DataFrame,
           grid: dict[str, list]) -> str:
    if wf.empty:
        return "没有完成任何 walk-forward 窗口：数据太短，或每个窗口的交易数都不足 MIN_TRADES。"
    L = ["\n═══ Walk-Forward 各窗口（IS 最优 → OOS 实测）═══",
         wf.drop(columns="_gs").to_string(index=False),
         "\n═══ 稳健参数区间（stability% = 众数出现比例）═══",
         robust_ranges(wf, grid).to_string(index=False),
         "\n═══ 参数敏感度（中位分数随取值变化；断崖=过敏）═══",
         sensitivity(wf, grid).to_string(index=False)]
    cg = consistently_good(wf, grid)
    L.append("\n═══ 在所有 IS 窗口都进前 20% 的参数组合（优先用这些）═══")
    L.append(cg.to_string(index=False) if not cg.empty
             else "（无 —— 说明策略对参数敏感，应该改规则而不是继续调参）")
    if not oos_eq.empty:
        m = compute_metrics(oos_tr, oos_eq)
        L.append(f"\n═══ 拼接 OOS 曲线（最接近实盘期望的数字）═══\n"
                 f"年化 {m['cagr_pct']}%  最大回撤 {m['max_dd_pct']}%  夏普 {m['sharpe']}  "
                 f"Calmar {m['calmar']}  交易 {m['trades']} 笔  胜率 {m['win_rate']}%")
        L.append("注意：IS 分数再漂亮也不算数，只看这一行和上面那张表。")
    return "\n".join(L)
