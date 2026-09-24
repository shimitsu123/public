"""scorecard.py — 现行模型「猜中」的概率（只描述，不改规则）：
  ① 单笔突破信号：胜率、平均盈亏、盈亏比、期望值（按月聚类的 95% 区间），2006-10～
  ② 现行模拟盘配置（进取档）在 20 年回测里：未来 1 个月 / 1 年 / 3 年赚钱的概率、1 年收益的中位数与 5% 分位
     JP = 个股 4×25% + 闲置资金 1329（牛熊分界择时）；US = 只持 SPYM + 择时；对照 = 指数买入持有
输出 var/out/scorecard.md / .json。个股部分有幸存者偏差（偏乐观），指数部分没有。
"""
from __future__ import annotations

import json
import math
import sys
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

START = "2006-10-01"
LINES: list[str] = []


def say(s=""):
    print(s, flush=True)
    LINES.append(s)


def trade_stats(ind, start=START):
    rows = []
    for t, df in ind.items():
        o, c, dead = df["Open"].values, df["Close"].values, df["dead_cross"].values
        for i in np.where(df["entry"].values)[0]:
            if df.index[i] < pd.Timestamp(start) or i + 2 >= len(df):
                continue
            e, ex = o[i + 1], None
            for k in range(i + 1, min(i + 61, len(df) - 1)):
                if c[k] / e - 1 <= -0.07 or (dead[k] and k > i + 1):
                    ex = o[k + 1]
                    break
            if ex is None:
                ex = c[min(i + 60, len(df) - 1)]
            rows.append((df.index[i].to_period("M"), ex / e - 1))
    d = pd.DataFrame(rows, columns=["m", "r"])
    w, l = d.r[d.r > 0], d.r[d.r <= 0]
    mm = d.groupby("m").r.mean()
    se = mm.std(ddof=1) / math.sqrt(len(mm))
    return {"n": len(d), "win_rate": round(float((d.r > 0).mean()) * 100, 1),
            "avg_win": round(float(w.mean()) * 100, 2), "avg_loss": round(float(l.mean()) * 100, 2),
            "payoff": round(float(w.mean() / -l.mean()), 2), "expect": round(float(d.r.mean()) * 100, 2),
            "ci95": [round(float(d.r.mean() - 1.96 * se) * 100, 2), round(float(d.r.mean() + 1.96 * se) * 100, 2)]}


def horizon_probs(eq: pd.Series) -> dict:
    out = {}
    for name, n in (("1个月", 21), ("1年", 252), ("3年", 756)):
        r = (eq.shift(-n) / eq - 1).dropna()
        out[name] = {"p_gain": round(float((r > 0.001).mean()) * 100, 1), "p_loss": round(float((r < -0.001).mean()) * 100, 1),
                     "median": round(float(r.median()) * 100, 1),
                     "p5": round(float(r.quantile(0.05)) * 100, 1)}
    return out


def main() -> int:
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    cfg = load_config()
    det = Detector(cfg["detector"]["kind"], cfg["detector"]["params"])
    out = {}
    say(f"# 现行模型的「命中率」记分卡（{pd.Timestamp.today().date()}，回测 {START}～）")
    for market in ("JP", "US"):
        mc = sim.get(market.lower(), {})
        data = load_universe(universe(market, "broad"), d21)
        p = load_params(market=market)
        ind = IndicatorCache(data).all(p)
        ts = trade_stats(ind)
        idx_full = load(*SYM[market])
        if market == "JP":
            etf = load_universe(["1329.T"], d21)["1329.T"]
            cf, cost, n, pct, brk = core_frame(etf, idx_full, div_yield_pct=1.6), CORE_COST["JP"], 4, 0.25, True
        else:
            spym = load_universe(["SPYM"], d21)["SPYM"]
            cf, cost, n, pct, brk = core_frame(spym), SPYM_COST, 1, 0.01, False
        ind2 = dict(ind); ind2["CORE"] = cf
        names = list(ind2)
        gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind2.values()])))
        closes = pd.DataFrame({t: df["Close"] for t, df in data.items()})
        M, _ = build_entry_mult(gidx, names, market, features_frame(load_macro_series(d21)),
                                use_macro=bool(mc.get("use_macro", True)), use_sector=bool(mc.get("use_sector_tilt", True)),
                                use_events=False, closes=closes)
        M = M * quant_regime_series(idx_full).reindex(gidx).ffill().shift(1).fillna(1.0).values[:, None]
        M[:, names.index("CORE")] = 0.0
        if not brk:
            M[:] = 0.0
        bear = (pd.Series(det.states(idx_full["Close"]), index=idx_full.index).reindex(gidx).ffill() == BEAR).values
        bt = BacktestConfig.for_market(market, 21)
        bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions = (1_000_000 if market == "JP" else 6_336.37), pct, n
        bt.sizing.max_position_pct = max(bt.sizing.max_position_pct, pct)
        r = run_backtest(ind2, p, bt, start=START, entry_mult=M,
                         core={"ticker": "CORE", "buffer_pct": 0.0, "band_pct": 10.0, **cost}, core_bear=bear)
        live = horizon_probs(r.equity)
        bh = idx_full["Close"]
        bh = bh[bh.index >= START]
        hold = horizon_probs(bh)
        m = r.metrics
        say(f"\n## {market}")
        say(f"单笔突破信号（{ts['n']} 个，2006-10～）：胜率 {ts['win_rate']}%，平均赚 {ts['avg_win']}% / 平均亏 {ts['avg_loss']}%，"
            f"盈亏比 {ts['payoff']}，每笔期望 {ts['expect']}%（95% 区间 {ts['ci95'][0]}%～{ts['ci95'][1]}%）")
        say(f"现行配置（{'个股 4×25% + 1329 择时' if market == 'JP' else 'SPYM + 择时'}）20 年：年化 {m.get('cagr_pct')}%，最大回撤 {m.get('max_dd_pct')}%")
        say("| 持有期 | 现行配置 赚 / 亏 / 持平 | 收益中位数 | 最差 5% | 指数买入持有 赚 / 亏 | 中位数 | 最差 5% |")
        say("|---|---|---|---|---|---|---|")
        for h in live:
            a, b = live[h], hold[h]
            flat = round(100 - a['p_gain'] - a['p_loss'], 1)
            say(f"| {h} | {a['p_gain']}% / {a['p_loss']}% / {flat}% | {a['median']}% | {a['p5']}% | "
                f"{b['p_gain']}% / {b['p_loss']}% | {b['median']}% | {b['p5']}% |")
        out[market] = {"trades": ts, "live": live, "buy_hold_price": hold, "cagr": m.get("cagr_pct"), "mdd": m.get("max_dd_pct")}
    say("\n注：指数买入持有用价格指数（不含分红）；现行配置的 1329 部分含估计股息。个股部分有幸存者偏差。")
    fp = paths.out_dir() / "scorecard"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
