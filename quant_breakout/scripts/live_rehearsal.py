"""live_rehearsal.py — 实盘执行器（qbreak/live_unified.py）用模拟账户演练：真实历史行情，逐日走「早上对账 → 决策 → 下单 → 开盘 → 开盘后补单」。

与 scripts/broker_s0c2_study.py 同一套输入（S0C2、立花個別コース、宏观 / 板块倍数 × 量化状态层、S&P500 牛熊分界、1655 上市前的拼接）。
每个窗口走两种模拟账户，与回测引擎（= 模拟盘的撮合）逐日比较：
  ① paper：PaperBroker（成交规则与引擎逐条相同）→ 应该逐笔一致：验证执行器的对账、下单先后、两段式买入、现金与持仓核对
  ② tachibana-sim：真实的立花适配器代码 + 模拟交易所（qbreak/brokers/tachibana_sim.py）→ 加上真实下单的约束
     （限价按呼値取整、1655 买单限价 +2%、开盘后补单按限价估余力、开盘前不知道卖单能否成交），差异 = 实盘相对模型会出现的差异
输出 var/out/live_rehearsal.md / .json。个股有幸存者偏差（与所有回测相同，不影响「执行器是否忠实执行模型」这个问题）。
用法：python scripts/live_rehearsal.py [--windows 5y,20y]
"""
from __future__ import annotations

import argparse
import json
import logging
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
from qbreak.live_unified import rehearse                                   # noqa: E402
from qbreak.macro import build_entry_mult, features_frame, load_macro_series  # noqa: E402
from qbreak.regime import quant_regime_series                             # noqa: E402
from qbreak.strategy import IndicatorCache                                 # noqa: E402
from qbreak.trader import load_params                                      # noqa: E402
from qbreak.unified import UnifiedConfig, UnifiedEngine, exec_configs      # noqa: E402
from bullbear_study import SYM, load                                       # noqa: E402
from unified_study import W5, W20, spx_jpy_on_jp_days                     # noqa: E402

WINDOWS = {"5y": ("5 年", W5), "20y": ("20 年", W20)}
KINDS = {"paper": "模拟券商（PaperBroker，规则与引擎相同）", "tachibana-sim": "立花适配器 + 模拟交易所（真实下单约束）"}


def inputs():
    """与 broker_s0c2_study 相同的输入。"""
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
    return ind, params, fxdf, em, bear


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", default="5y,20y")
    a = ap.parse_args(argv)
    logging.getLogger("qbreak").setLevel(logging.ERROR)                   # 几千笔单的逐笔日志不打印
    t0 = time.time()
    ind, params, fxdf, em, bear = inputs()
    ex = exec_configs(("JP",), {"broker": "tachibana"})
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34,
                        stock_markets=("JP",), core={"1655.T": 1.0}, core_index={"1655.T": "US"}, core_mode="split")
    cc = {"1655.T": etf_cost("tachibana", "1655.T", "JP")}

    def make():
        return UnifiedEngine(ind, cfg, params, ex, cc, fx=fxdf[["Open", "Close"]], entry_mult=em, bear=bear)
    out, lines = {}, [f"# 实盘执行器 · 模拟账户演练（{pd.Timestamp.today().date()}；S0C2、立花個別コース、100 万円起）", "",
                      "同一套历史行情走两遍：回测引擎（= 模拟盘的撮合） vs 执行器逐日「早上对账 → 决策 → 下单 → 开盘 → 开盘后补单」。", "",
                      "| 窗口 | 模拟账户 | 引擎年化 | 执行器年化 | 最终权益差 | 逐日最大差 | 交易逐笔一致 | 1655 调仓一致 | 成交笔数 | "
                      "开盘后补单（其中降限价） | 模型会买但没成交 | 卖单没成交（顺延） | 报错 |",
                      "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for w in [x.strip() for x in a.windows.split(",") if x.strip()]:
        lab, start = WINDOWS[w]
        for kind, klab in KINDS.items():
            r = rehearse(make, start, kind=kind)
            e, x, st = r["engine"], r["executor"], r["stats"]
            me, mx = e.metrics, x.metrics
            row = {"window": lab, "kind": kind, "engine_cagr": me.get("cagr_pct"), "exec_cagr": mx.get("cagr_pct"),
                   "engine_dd": me.get("max_dd_pct"), "exec_dd": mx.get("max_dd_pct"),
                   "engine_final": float(e.equity.iloc[-1]), "exec_final": float(x.equity.iloc[-1]),
                   "final_diff": r["final_diff"], "max_abs_diff": r["max_abs_diff"], "same_trades": r["same_trades"],
                   "same_core": r["same_core"], "stats": st, "errors": r["errors"], "calls": r["calls"],
                   "days": int(len(x.equity)), "secs": round(time.time() - t0)}
            out[f"{w}_{kind}"] = row
            lines.append(f"| {lab} | {klab} | {row['engine_cagr']}% | {row['exec_cagr']}% | ¥{row['final_diff']:+,.0f} | "
                         f"¥{row['max_abs_diff']:,.0f} | {'是' if row['same_trades'] else '否'} | {'是' if row['same_core'] else '否'} | "
                         f"{st['fills']} 笔 | {st['deferred']} 笔（{st['limit_lowered']}） | {st['model_diff']} 笔 | "
                         f"{st['unfilled_sell']} 笔 | {len(r['errors'])} 条 |")
            print(w, kind, {k: row[k] for k in ("engine_cagr", "exec_cagr", "final_diff", "max_abs_diff", "same_trades",
                                                  "same_core")}, st, f"{time.time() - t0:.0f}s", flush=True)
    lines += ["", "读法：",
              "- 「模拟券商」一行应该完全一致（差 ¥0）：说明执行器把成交记进状态、下单先后、两段式买入（开盘前余力不够的买单留到开盘后）、"
              "持仓与现金核对都与模型相同。",
              "- 「立花适配器 + 模拟交易所」一行走的是真实的立花发单 / 約定照会 / 持仓 / 余力代码，撮合假设与回测相同；"
              "差异只来自真实下单的约束：寄付指値按呼値向下取整、1655 买单限价 = 收盘 +2%、开盘前不知道同一开盘的卖单能否成交。",
              "- 「开盘后补单」：开盘前的余力放不下（要等开盘卖出 1655 / 个股的钱）的买单，开盘后按始値做同样的跳空与名额检查、"
              "按模型的规则（开盘价 + 滑点）减股再下；「降限价」= 原限价占用的余力放不下，限价降到余力能承受的最高呼値（仍 ≥ 开盘价）。",
              "- 「模型会买但没成交」是实盘相对模拟盘的差异来源（之后的持仓、现金都会跟着不同）；每天的执行器汇报里也会逐笔列出。",
              "- 没有模拟：盘中价格路径（开盘后补单在模拟里按开盘价成交）、ストップ高 / 安时的比例配分、券商的实际手续费与税。"]
    fp = paths.out_dir() / "live_rehearsal"
    Path(f"{fp}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
