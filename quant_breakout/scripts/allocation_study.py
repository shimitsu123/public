"""allocation_study.py — 收益最大化的资金配置（事先登记，跑之前写定）。

方案（每个市场）：
  P0  只做突破（个股仓位网格）
  P3  核心-卫星：突破 + 闲置资金在牛市持指数 ETF、熊市持现金（牛熊分界 250 日线 ±3% / 连续 5 天）
  P3b 核心-卫星但不择时（闲置资金一直持指数）
  P2  只持指数 ETF + 牛熊择时
  P5  只持指数 ETF（买入持有）
个股仓位网格：JP (3,34%) 现行 / (2,50%) / (4,25%) / (5,20%)；US (5,20%) 现行 / (3,34%) / (8,12.5%) / (10,10%)
美股另测核心用 SPYM（单价 <$100、买卖都收 0.495%）的成本。
个股入场仍按现行：量化状态层倍数 × 宏观倍数 × 板块倾斜。

选择规则：
  主标准   20 年（2006-10-01～2026-09-24）年化最高
  约束     20 年最大回撤 ≥ −30%，近 5 年（2021-09-24～）最大回撤 ≥ −20%，近 5 年年化 ≥ 现行方案
  平局     年化差 < 0.5pp 时取 20 年 Calmar 高者
另外报告回撤上限 −20 / −25 / −35% / 无上限 时各自的最优方案（前沿），供按风险偏好改选。
注意：个股池是 2026-09 时点的成分股 → 突破部分有幸存者偏差（偏乐观）；指数部分没有。税前、未计 NISA。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                   # noqa: E402
from qbreak.bullbear import BEAR, Detector, load_config                   # noqa: E402
from qbreak.config import BacktestConfig, DataConfig, universe             # noqa: E402
from qbreak.core import CORE_COST, SPYM_COST, core_frame                   # noqa: E402
from qbreak.data import load_universe                                      # noqa: E402
from qbreak.engine import run_backtest                                     # noqa: E402
from qbreak.macro import build_entry_mult, features_frame, load_macro_series  # noqa: E402
from qbreak.regime import quant_regime_series                             # noqa: E402
from qbreak.strategy import IndicatorCache                                 # noqa: E402
from qbreak.trader import load_params                                      # noqa: E402
from bullbear_study import SYM, load                                       # noqa: E402

W20, W5 = "2006-10-01", "2021-09-24"
CASH = {"JP": 1_000_000, "US": 6_336.37}
GRID = {"JP": [(3, 0.34), (2, 0.50), (4, 0.25), (5, 0.20)], "US": [(5, 0.20), (3, 0.34), (8, 0.125), (10, 0.10)]}
CAPS = [-20.0, -25.0, -30.0, -35.0, -999.0]


def main() -> int:
    market = sys.argv[1].upper()
    cfg = load_config()
    det = Detector(cfg["detector"]["kind"], cfg["detector"]["params"])
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    mc = sim.get(market.lower(), {})
    flag = lambda k, d=True: mc.get(k, sim.get(k, d))                          # noqa: E731
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    t0 = time.time()
    data = load_universe(universe(market, "broad"), d21)
    idx_full = load(*SYM[market])
    p = load_params(market=market)
    ind = IndicatorCache(data).all(p)
    # 核心 ETF
    if market == "JP":
        etf = load_universe(["1329.T"], d21)["1329.T"]
        cores = {"core": (core_frame(etf, idx_full, div_yield_pct=1.6), CORE_COST["JP"])}
    else:
        spy = load_universe(["SPY"], d21)["SPY"]
        spym = load_universe(["SPYM"], d21)["SPYM"]
        cores = {"core": (core_frame(spy), CORE_COST["US"]), "spym": (core_frame(spym), SPYM_COST)}
    print(f"[{market}] 数据 {len(data)} 只，{time.time() - t0:.0f}s", flush=True)
    tickers = list(ind)
    rows = []
    for ckey, (cf, cost) in cores.items():
        ind2 = dict(ind); ind2["CORE"] = cf
        names = list(ind2)
        gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind2.values()])))
        closes = pd.DataFrame({t: df["Close"] for t, df in data.items()})
        frame = features_frame(load_macro_series(d21))
        M, _ = build_entry_mult(gidx, names, market, frame, use_macro=bool(flag("use_macro")),
                                use_sector=bool(flag("use_sector_tilt")), use_events=False, closes=closes)
        qprev = quant_regime_series(idx_full).reindex(gidx).ffill().shift(1).fillna(1.0).values
        M = M * qprev[:, None]
        M[:, names.index("CORE")] = 0.0
        Mzero = np.zeros_like(M)
        st = pd.Series(det.states(idx_full["Close"]), index=idx_full.index).reindex(gidx).ffill()
        bear = (st == BEAR).values
        schemes = []
        for n, pct in GRID[market]:
            tag = f"{n}x{int(round(pct * 100))}%"
            if ckey == "core":
                schemes.append((f"P0 {tag}", dict(core=None, M=M, n=n, pct=pct)))
            schemes.append((f"P3 {tag}" + ("" if ckey == "core" else " SPYM"), dict(core=True, timing=True, M=M, n=n, pct=pct)))
            schemes.append((f"P3b {tag}" + ("" if ckey == "core" else " SPYM"), dict(core=True, timing=False, M=M, n=n, pct=pct)))
        schemes.append(("P2 指数+择时" + ("" if ckey == "core" else " SPYM"), dict(core=True, timing=True, M=Mzero, n=1, pct=0.01)))
        schemes.append(("P5 指数持有" + ("" if ckey == "core" else " SPYM"), dict(core=True, timing=False, M=Mzero, n=1, pct=0.01)))
        for name, s in schemes:
            row = {"scheme": name}
            for wname, start in (("w20", W20), ("w5", W5)):
                bt = BacktestConfig.for_market(market, 21)
                bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions = CASH[market], s["pct"], s["n"]
                bt.sizing.max_position_pct = max(bt.sizing.max_position_pct, s["pct"])
                bt.sizing.validate()
                core = None
                if s["core"]:
                    core = {"ticker": "CORE", "buffer_pct": 0.0, "band_pct": 10.0, **cost}
                r = run_backtest(ind2, p, bt, start=start, entry_mult=s["M"], core=core,
                                 core_bear=bear if (s["core"] and s.get("timing")) else None)
                m = r.metrics
                row.update({f"{wname}_cagr": m.get("cagr_pct"), f"{wname}_dd": m.get("max_dd_pct"),
                            f"{wname}_sharpe": m.get("sharpe"), f"{wname}_calmar": m.get("calmar"),
                            f"{wname}_trades": m.get("trades"),
                            f"{wname}_core_fees": (r.extra.get("core") or {}).get("fees"),
                            f"{wname}_core_trades": (r.extra.get("core") or {}).get("trades")})
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False, default=float), flush=True)
    df = pd.DataFrame(rows)
    cur = df[df["scheme"] == f"P0 {GRID[market][0][0]}x{int(round(GRID[market][0][1] * 100))}%"].iloc[0]
    out = {"current": cur["scheme"], "frontier": {}}
    for cap in CAPS:
        ok = df[(df["w20_dd"] >= cap) & (df["w5_dd"] >= -20.0) & (df["w5_cagr"] >= cur["w5_cagr"])].copy()
        if ok.empty:
            out["frontier"][str(cap)] = None
            continue
        top = ok["w20_cagr"].max()
        pick = ok[ok["w20_cagr"] >= top - 0.5].sort_values("w20_calmar", ascending=False).iloc[0]
        out["frontier"][str(cap)] = pick["scheme"]
    out["pick"] = out["frontier"].get("-30.0")
    print(f"\n[{market}] 前沿 {out['frontier']} → 选定（回撤上限 −30%）{out['pick']}")
    base = paths.out_dir() / f"allocation_{market}"
    df.to_csv(f"{base}.csv", index=False, encoding="utf-8-sig")
    Path(f"{base}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
