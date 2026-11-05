"""broker_s0c2_study.py — 现行方案 S0C2（日本个股 4×25% + 闲置资金 1655.T，按 S&P500 牛熊分界择时）
在楽天（日本株 / 东证 ETF 0 円）与立花 e支店（個別コース）两种手续费下的 20 年 / 5 年结果（描述性对比，不做方案选择）。

用户问（2026-09-25）：不做美股的话没必要用楽天的逻辑，直接用立花的自动交易。这里只回答「换到立花要付多少手续费、少赚多少」。
与 scripts/unified_study.py 同一个推进器与同一套输入（宏观 / 板块倍数 × 量化状态层、牛熊分界、1655 上市前的拼接）。
立花的新开户前 60 个营业日现物手续费 0 円不计入（偏保守）。个股部分有幸存者偏差（两种券商相同）。
输出 var/out/broker_s0c2_study.md / .json。
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
from qbreak.config import DataConfig, universe                             # noqa: E402
from qbreak.core import core_frame                                         # noqa: E402
from qbreak.data import load_universe                                      # noqa: E402
from qbreak.fees import etf_cost                                           # noqa: E402
from qbreak.macro import build_entry_mult, features_frame, load_macro_series  # noqa: E402
from qbreak.regime import quant_regime_series                             # noqa: E402
from qbreak.strategy import IndicatorCache                                 # noqa: E402
from qbreak.trader import load_params                                      # noqa: E402
from qbreak.unified import UnifiedConfig, UnifiedEngine, exec_configs      # noqa: E402
from bullbear_study import SYM, load                                       # noqa: E402
from unified_study import W5, W20, spx_jpy_on_jp_days                     # noqa: E402

BROKERS = {"rakuten": "楽天（日本株 / 东证 ETF 0 円）", "tachibana": "立花 e支店 個別コース"}


def main() -> int:
    t0 = time.time()
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    params = {m: load_params(market=m) for m in ("JP", "US")}
    data = load_universe(universe("JP", "broad"), d21)
    ind = IndicatorCache(data).all(params["JP"])
    idx = {m: load(*SYM[m]) for m in ("JP", "US")}
    fxdf = load("JPY=X", "2000-01-01")
    fxdf = fxdf[(fxdf["Close"] > 60) & (fxdf["Close"] < 250)]
    etf = load_universe(["1655.T"], d21)
    ind["1655.T"] = core_frame(etf["1655.T"], spx_jpy_on_jp_days(idx["US"], fxdf["Close"], idx["JP"].index), div_yield_pct=1.3)
    macro = features_frame(load_macro_series(d21))
    names = list(data)
    g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
    mc = sim.get("jp", {})
    flag = lambda k, d=True: mc.get(k, sim.get(k, d))                      # noqa: E731
    closes = pd.DataFrame({t: data[t]["Close"] for t in names})
    M, _ = build_entry_mult(g, names, "JP", macro, use_macro=bool(flag("use_macro")),
                            use_sector=bool(flag("use_sector_tilt")), use_events=False, closes=closes)
    M = M * quant_regime_series(idx["JP"]).reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
    em = {"JP": pd.DataFrame(M, index=g, columns=names)}
    cfgd = load_config()
    det = Detector(cfgd["detector"]["kind"], cfgd["detector"]["params"])
    bear = {m: pd.Series(np.asarray(det.states(idx[m]["Close"])) == BEAR, index=idx[m].index) for m in ("JP", "US")}
    out, lines = {}, [f"# 现行方案 S0C2 在楽天 / 立花两种手续费下（{pd.Timestamp.today().date()}；描述性对比）",
                      "", "| 券商 | 窗口 | 年化 | 最大回撤 | Calmar | 成交笔数（个股 / 1655） | 手续费合计 | 每年手续费 |",
                      "|---|---|---|---|---|---|---|---|"]
    for b, lab in BROKERS.items():
        ex = exec_configs(("JP",), {"broker": b})                           # 只做日本个股；美股只是推进器的结构
        for wname, start in (("20 年", W20), ("5 年", W5)):
            cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34,
                                stock_markets=("JP",), core={"1655.T": 1.0}, core_index={"1655.T": "US"}, core_mode="split")
            r = UnifiedEngine(ind, cfg, params, ex, {"1655.T": etf_cost(b, "1655.T", "JP")}, fx=fxdf[["Open", "Close"]],
                              entry_mult=em, bear=bear).run(start=start)
            mt = r.metrics
            tr = r.trades[r.trades["reason"] != "end"]
            ct = r.state.core_trades
            fe = ex["JP"].fee                                                # 个股来回：买入额 + 卖出额各收一次
            fee_st = float(sum(fe(x.shares * x.entry_px) + fe(x.shares * x.exit_px) for x in tr.itertuples()))
            fee_core = float(sum(float(x[-1]) for x in ct))
            yrs = (r.equity.index[-1] - r.equity.index[0]).days / 365.25
            fee = fee_st + fee_core
            row = {"cagr": mt.get("cagr_pct"), "dd": mt.get("max_dd_pct"), "calmar": mt.get("calmar"),
                   "stock_trades": int(len(tr)), "core_trades": len(ct), "fees": fee, "fees_per_year": fee / yrs if yrs else None,
                   "years": round(yrs, 1)}
            out[f"{b}_{wname}"] = row
            lines.append(f"| {lab} | {wname} | {row['cagr']}% | {row['dd']}% | {row['calmar']} | {row['stock_trades']} 笔 / "
                         f"{row['core_trades']} 笔 | ¥{fee:,.0f} | ¥{row['fees_per_year']:,.0f} |")
            print(b, wname, row, f"{time.time() - t0:.0f}s", flush=True)
    for w in ("20 年", "5 年"):
        a, c = out[f"rakuten_{w}"], out[f"tachibana_{w}"]
        lines.append(f"\n{w}：立花 − 楽天 年化 {c['cagr'] - a['cagr']:+.2f} pp，最大回撤 {c['dd'] - a['dd']:+.2f} pp")
    lines.append("\n立花新开户前 60 个营业日现物手续费 0 円没有计入；个股有幸存者偏差（两种券商相同）。")
    fp = paths.out_dir() / "broker_s0c2_study"
    Path(f"{fp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
