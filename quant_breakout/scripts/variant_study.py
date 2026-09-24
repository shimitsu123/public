"""variant_study.py — 事先登记的变体一次跑完：全期路径 / 10 仓分散 / walk-forward 样本外。

用法：python scripts/variant_study.py JP [--only X0_M4,X1_M4] [--no-wf]
输出：var/out/variant_study_<市场>.md 与 .csv

选择规则（写在跑之前，避免挑结果）：
  主标准   walk-forward 拼接样本外 Calmar（年化 / |最大回撤|）
  稳健性   10 仓 × 10%、资金 ×10 的分散版全期 Calmar 不低于现行方案
  风险上限 样本外最大回撤不超过 −15%
  切换门槛 主标准比现行方案高 ≥ 0.2，否则保留现行（不为噪音换方案）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qbreak import paths                                            # noqa: E402
from qbreak.config import BENCHMARK, BacktestConfig, DataConfig, universe   # noqa: E402
from qbreak.data import load_universe                               # noqa: E402
from qbreak.engine import run_backtest                              # noqa: E402
from qbreak.macro import build_entry_mult, features_frame, load_events, load_macro_series  # noqa: E402
from qbreak.metrics import compute_metrics                          # noqa: E402
from qbreak.optimize import DEFAULT_GRID, walk_forward              # noqa: E402
from qbreak.strategy import IndicatorCache                          # noqa: E402
from qbreak.trader import load_params                               # noqa: E402

EXITS = {
    "X0": {},                                                        # 现行：死叉离场 + 跟踪 12% + 止盈 25%
    "X1": {"exit_on_macd_dead_cross": False, "trailing_stop_pct": 10.0, "trailing_arm_pct": 3.0},
    "X2": {"exit_on_macd_dead_cross": False, "trailing_stop_pct": 15.0, "trailing_arm_pct": 5.0},
}
MACROS = {
    "M0": dict(macro=False, sector=False, events=None),
    "M1": dict(macro=False, sector=True, events=None),
    "M2": dict(macro=True, sector=True, events=None),
    "M3": dict(macro=True, sector=True, events={"FOMC", "BOJ"}),
    "M4": dict(macro=True, sector=True, events={"FOMC", "BOJ", "CPI", "NFP"}),   # 现行
}
PLAN = ["X0_M4", "X1_M4", "X2_M4", "X0_M0", "X1_M0", "X2_M0", "X0_M2", "X1_M2", "X2_M2",
        "X0_M1", "X1_M1", "X0_M3", "X1_M3"]
CURRENT = "X0_M4"
SIM_SIZING = {"JP": dict(cash=1_000_000, pct=0.34, n=3), "US": dict(cash=10_000, pct=0.20, n=5)}


def _bt(market: str, cash: float, pct: float, n: int) -> BacktestConfig:
    bt = BacktestConfig.for_market(market, 5)
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions = cash, pct, n
    bt.sizing.max_position_pct = max(bt.sizing.max_position_pct, pct)
    bt.sizing.validate()
    return bt


def _m(res_or_eq, trades=None) -> dict:
    if isinstance(res_or_eq, pd.Series):
        m = compute_metrics(trades if trades is not None else pd.DataFrame(), res_or_eq)
    else:
        m = res_or_eq.metrics
    return {k: m.get(k) for k in ("cagr_pct", "max_dd_pct", "sharpe", "calmar", "trades", "win_rate")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("market")
    ap.add_argument("--only", default="")
    ap.add_argument("--no-wf", action="store_true")
    ap.add_argument("--tag", default="", help="输出文件名后缀，例如 confirm → variant_study_JP_confirm.csv")
    a = ap.parse_args()
    market = a.market.upper()
    plan = [x for x in PLAN if not a.only or x in a.only.split(",")]
    dcfg = DataConfig(provider="yfinance", years=5, allow_synthetic=False).validate()
    data = load_universe(universe(market, "broad"), dcfg)
    idx = load_universe([BENCHMARK[market]], dcfg).get(BENCHMARK[market])
    idx_close = idx["Close"] if idx is not None else None
    frame = features_frame(load_macro_series(dcfg))
    base = load_params(market=market)
    cache = IndicatorCache(data, idx_close if base.min_rs_pct > -900 else None)
    tickers = list(data.keys())
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in data.values()])))
    closes = pd.DataFrame({t: df["Close"] for t, df in data.items()})
    ev_all = load_events(include_history=True, nfp_heuristic_years=(gidx[0].year, gidx[-1].year))
    s = SIM_SIZING[market]
    rows = []
    for name in plan:
        t0 = time.time()
        xk, mk = name.split("_")
        p = replace(base, **EXITS[xk]).validate()
        mc = MACROS[mk]
        M = None
        if mc["macro"] or mc["sector"] or mc["events"]:
            ev = [e for e in ev_all if e.kind in mc["events"]] if mc["events"] else None
            M, _ = build_entry_mult(gidx, tickers, market, frame, use_macro=mc["macro"],
                                    use_sector=mc["sector"], use_events=bool(mc["events"]), events=ev,
                                    closes=closes)
        ind = cache.all(p)
        full = run_backtest(ind, p, _bt(market, s["cash"], s["pct"], s["n"]), entry_mult=M)
        div = run_backtest(ind, p, _bt(market, s["cash"] * 10, 0.10, 10), entry_mult=M)
        row = {"variant": name, "exit": xk, "macro": mk,
               **{f"full_{k}": v for k, v in _m(full).items()},
               **{f"div_{k}": v for k, v in _m(div).items()}}
        if not a.no_wf:
            wf, eq, tr = walk_forward(data, _bt(market, s["cash"], s["pct"], s["n"]), p, DEFAULT_GRID,
                                      2.0, 6, "calmar", index_close=idx_close if p.min_rs_pct > -900 else None,
                                      entry_mult=M)
            om = _m(eq * s["cash"], tr) if len(eq) else {}
            row.update({f"oos_{k}": v for k, v in om.items()})
            row["oos_pos_windows"] = int((wf["oos_cagr"] > 0).sum()) if not wf.empty else 0
            row["oos_windows"] = len(wf)
        row["secs"] = round(time.time() - t0)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    df = pd.DataFrame(rows)
    out = paths.out_dir() / (f"variant_study_{market}" + (f"_{a.tag}" if a.tag else ""))
    df.to_csv(f"{out}.csv", index=False, encoding="utf-8-sig")
    cols = list(df.columns)
    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    Path(f"{out}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"saved {out}.csv / .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
