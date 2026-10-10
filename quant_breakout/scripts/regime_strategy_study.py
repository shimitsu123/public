"""regime_strategy_study.py — 20 年个股回测（2006-10～今天，含 2008 / 2020 / 2022）里比较状态层。

  R0 无状态层（只有牛市算法）
  R1 现行生产的量化状态层（指数 200 日线 / 20 日波动 / 252 日回撤 → 新仓 ×0 / 0.75 / 1），此前从未回测过
  R2 新牛熊分界（250 日线 ±3%、连续 5 天）：熊市不开新仓
  R3 R2 + 宣布熊市次日开盘清仓
  R4 R2 + R1
  R5 R3 + R1
宏观层按 sim.json 的现行开关（量化因子 + 板块，事件窗口关）。
事先登记的选择规则：以 R1（现行生产）为基准；候选 = 全期 Calmar 最高且 ①10 仓分散版 Calmar ≥ R1 ②三个子区间里至少两段 Calmar ≥ R1；
比 R1 高 ≥ 0.1 才换，否则保留 R1。
注意：股票池是 2026-09 时点的成分股 → 20 年回测有明显的幸存者偏差，只看方案之间的相对差异。
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
from qbreak.bullbear import BEAR, Detector, date_phases, load_config     # noqa: E402
from qbreak.config import BacktestConfig, DataConfig, universe             # noqa: E402
from qbreak.data import load_universe                                      # noqa: E402
from qbreak.engine import run_backtest                                     # noqa: E402
from qbreak.macro import build_entry_mult, features_frame, load_macro_series  # noqa: E402
from qbreak.regime import quant_regime_series                             # noqa: E402
from qbreak.strategy import IndicatorCache                                 # noqa: E402
from qbreak.trader import load_params                                      # noqa: E402
from bullbear_study import SYM, load                                       # noqa: E402

START = "2006-10-01"
SUB = [("2006-10-01", "2012-12-31"), ("2013-01-01", "2019-12-31"), ("2020-01-01", None)]
SIZING = {"JP": dict(cash=1_000_000, pct=0.34, n=3), "US": dict(cash=10_000, pct=0.20, n=5)}
VARIANTS = {"R0": dict(q=False, bb=False, exit=False), "R1": dict(q=True, bb=False, exit=False),
            "R2": dict(q=False, bb=True, exit=False), "R3": dict(q=False, bb=True, exit=True),
            "R4": dict(q=True, bb=True, exit=False), "R5": dict(q=True, bb=True, exit=True)}


def _bt(market, cash, pct, n):
    bt = BacktestConfig.for_market(market, 21)
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions = cash, pct, n
    bt.sizing.max_position_pct = max(bt.sizing.max_position_pct, pct)
    bt.sizing.validate()
    return bt


def seg_stats(eq: pd.Series, a, b) -> dict:
    e = eq[(eq.index >= a) & ((eq.index <= b) if b else True)]
    if len(e) < 20:
        return {}
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    cagr = (e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1
    dd = float((e / e.cummax() - 1).min())
    return {"cagr": round(cagr * 100, 2), "dd": round(dd * 100, 2), "calmar": round(cagr / abs(dd), 3) if dd < 0 else None}


def main() -> int:
    market = sys.argv[1].upper()
    cfg = load_config()
    det = Detector(cfg["detector"]["kind"], cfg["detector"]["params"])
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    mc = sim.get(market.lower(), {})
    flag = lambda k, d=True: mc.get(k, sim.get(k, d))                          # noqa: E731
    dcfg = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    t0 = time.time()
    data = load_universe(universe(market, "broad"), dcfg)
    print(f"[{market}] 载入 {len(data)} 只，{time.time() - t0:.0f}s", flush=True)
    idx_full = load(*SYM[market])
    st_full = pd.Series(det.states(idx_full["Close"], (cfg.get("hmm") or {}).get(market)), index=idx_full.index)
    labels = date_phases(idx_full["Close"])[1]
    qr = quant_regime_series(idx_full)
    p = load_params(market=market)
    cache = IndicatorCache(data)
    ind = cache.all(p)
    tickers = list(ind.keys())
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))
    closes = pd.DataFrame({t: df["Close"] for t, df in data.items()})
    frame = features_frame(load_macro_series(dcfg))
    M, _ = build_entry_mult(gidx, tickers, market, frame, use_macro=bool(flag("use_macro")),
                            use_sector=bool(flag("use_sector_tilt")), use_events=False, closes=closes)
    bear = (st_full.reindex(gidx).ffill() == BEAR).values
    qprev = qr.reindex(gidx).ffill().shift(1).fillna(1.0).values
    s = SIZING[market]
    rows = []
    for name, v in VARIANTS.items():
        Mv = M * (qprev[:, None] if v["q"] else 1.0)
        reg = bear if v["bb"] else None
        full = run_backtest(ind, p, _bt(market, s["cash"], s["pct"], s["n"]), start=START, entry_mult=Mv,
                            regime=reg, regime_exit=v["exit"])
        div = run_backtest(ind, p, _bt(market, s["cash"] * 10, 0.10, 10), start=START, entry_mult=Mv,
                           regime=reg, regime_exit=v["exit"])
        eq = full.equity
        m = full.metrics
        row = {"variant": name, "cagr": m.get("cagr_pct"), "dd": m.get("max_dd_pct"), "sharpe": m.get("sharpe"),
               "calmar": m.get("calmar"), "trades": m.get("trades"), "div_calmar": div.metrics.get("calmar"),
               "div_cagr": div.metrics.get("cagr_pct"), "div_dd": div.metrics.get("max_dd_pct")}
        for k, (a, b) in enumerate(SUB):
            for kk, vv in seg_stats(eq, a, b).items():
                row[f"s{k + 1}_{kk}"] = vv
        # 事后牛/熊阶段里的年化收益
        r = eq.pct_change().dropna()
        lab = labels.reindex(r.index).ffill()
        for ph, code in (("bull", 1), ("bear", -1)):
            x = r[lab == code]
            row[f"{ph}_ann"] = round(((1 + x).prod() ** (252 / max(len(x), 1)) - 1) * 100, 2) if len(x) else None
        for yr in (2008, 2020, 2022):
            e = eq[eq.index.year == yr]
            row[f"y{yr}"] = round((e.iloc[-1] / e.iloc[0] - 1) * 100, 2) if len(e) > 1 else None
        row["skipped_regime"] = full.skipped.get("regime", 0)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    df = pd.DataFrame(rows)
    base = df[df["variant"] == "R1"].iloc[0]
    def ok(r):
        subs_ok = sum(1 for k in (1, 2, 3) if (r.get(f"s{k}_calmar") or -9) >= (base.get(f"s{k}_calmar") or -9))
        return (r["div_calmar"] or -9) >= (base["div_calmar"] or -9) and subs_ok >= 2
    cand = df[df.apply(ok, axis=1) & (df["variant"] != "R0")].sort_values("calmar", ascending=False)
    pick = "R1"
    if len(cand) and cand.iloc[0]["calmar"] >= base["calmar"] + 0.1:
        pick = cand.iloc[0]["variant"]
    print(f"\n[{market}] 选定 {pick}（基准 R1 Calmar {base['calmar']}）")
    out = paths.out_dir() / f"regime_strategy_{market}"
    df.to_csv(f"{out}.csv", index=False, encoding="utf-8-sig")
    (Path(f"{out}.json")).write_text(json.dumps({"pick": pick}, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
