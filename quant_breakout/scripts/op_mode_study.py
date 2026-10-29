"""op_mode_study.py — 用户描述的操作方式 vs 现行 S0C2（事先写定，先提交后运行，结果出来不改规则）。

用户（2026-09-25）描述：100 万日元；日本有可买的就买，大约在高点卖；日本和美股都没有就观望；日本即将有信号就留着日元；
日本没有、美股有就换汇买美股；已经是美元且美股还有机会就一直拿着美元；中间考虑手续费和汇率。
对应的统一引擎设定（楽天：日本株 0 円，美股 0.495% 上限 $22，换汇片道 3 銭估；个股 4×25%，日本 + 美股一起排名）：
  S0C2  现行：只做日本个股 + 闲置资金在 S&P500 牛市时买 1655（熊市拿日元）
  U0    日本 + 美股个股，闲置资金拿日元观望；美股卖出的美元次日换回（当晚还要买美股就留着）
  U1    同 U0，但美股卖出的美元一直拿着、只用来买美股
  U2    同 U0，但美股候补里有「即将触发 / 已触发」时美元先不换回（= 「美股还有机会就拿着美元」）
  U3    只做日本个股，闲置资金拿日元观望
  换汇时点：楽天リアルタイム為替 平日 8:00 起、换得的美元立即可用 → 引擎在买美股当天白天换（不需要提前几天换）。
窗口：20 年 2006-10～ / 5 年 2021-09～。另报：换汇次数与点差成本、美股成交笔数。
判定（事先规则）：U2 的 20 年年化比 U0、U1 都高 ≥ 0.3pp 且回撤不更深（运行后补记：用未四舍五入的值比较；第一次运行用的是
  四舍五入到 0.01 的值，结论相同） → 日本 + 美股模式默认打开 usd_keep_imminent；
  是否把模拟盘从 S0C2 换成 U 系列由用户决定（本研究只报告差别）。
输出 var/out/op_mode_study.md / .json。
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
from qbreak import paths                                                     # noqa: E402
from qbreak.bullbear import BEAR, Detector, load_config                      # noqa: E402
from qbreak.config import DataConfig, ExecConfig, universe                   # noqa: E402
from qbreak.core import core_frame                                           # noqa: E402
from qbreak.data import load_universe                                        # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.macro import build_entry_mult, features_frame, load_macro_series  # noqa: E402
from qbreak.regime import quant_regime_series                               # noqa: E402
from qbreak.strategy import IndicatorCache                                   # noqa: E402
from qbreak.trader import load_params                                        # noqa: E402
from qbreak.unified import UnifiedConfig, UnifiedEngine                      # noqa: E402
from bullbear_study import SYM, load                                         # noqa: E402
from unified_study import W5, W20, spx_jpy_on_jp_days                        # noqa: E402

LINES: list[str] = []
MODES = {"S0C2": dict(stock_markets=("JP",), core={"1655.T": 1.0}, core_index={"1655.T": "US"}),
         "U0": dict(stock_markets=("JP", "US"), core={}, core_index={}),
         "U1": dict(stock_markets=("JP", "US"), core={}, core_index={}, usd_keep=True),
         "U2": dict(stock_markets=("JP", "US"), core={}, core_index={}, usd_keep_imminent=True),
         "U3": dict(stock_markets=("JP",), core={}, core_index={})}
LABEL = {"S0C2": "现行：日本个股 + 闲置资金 1655（牛市）", "U0": "日本 + 美股个股，没信号拿日元观望",
         "U1": "U0 + 美股卖出的美元一直拿着", "U2": "U0 + 美股即将有信号时美元先拿着",
         "U3": "只做日本个股，没信号拿日元观望"}


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def main() -> int:
    t0 = time.time()
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    params = {m: load_params(market=m) for m in ("JP", "US")}
    data = {m: load_universe(universe(m, "broad"), d21) for m in ("JP", "US")}
    ind = {}
    for m in ("JP", "US"):
        ind.update(IndicatorCache(data[m]).all(params[m]))
    idx = {m: load(*SYM[m]) for m in ("JP", "US")}
    fxdf = load("JPY=X", "2000-01-01")
    fxdf = fxdf[(fxdf["Close"] > 60) & (fxdf["Close"] < 250)]
    etf = load_universe(["1655.T"], d21)
    ind["1655.T"] = core_frame(etf["1655.T"], spx_jpy_on_jp_days(idx["US"], fxdf["Close"], idx["JP"].index), div_yield_pct=1.3)
    macro = features_frame(load_macro_series(d21))
    em = {}
    for m in ("JP", "US"):
        names = list(data[m])
        g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
        mc = sim.get(m.lower(), {})
        flag = lambda k, dflt=True, mc=mc: mc.get(k, sim.get(k, dflt))        # noqa: E731
        closes = pd.DataFrame({t: data[m][t]["Close"] for t in names})
        M, _ = build_entry_mult(g, names, m, macro, use_macro=bool(flag("use_macro")),
                                use_sector=bool(flag("use_sector_tilt")), use_events=False, closes=closes)
        M = M * quant_regime_series(idx[m]).reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
        em[m] = pd.DataFrame(M, index=g, columns=names)
    cfgd = load_config()
    det = Detector(cfgd["detector"]["kind"], cfgd["detector"]["params"])
    bear = {m: pd.Series(np.asarray(det.states(idx[m]["Close"])) == BEAR, index=idx[m].index) for m in ("JP", "US")}
    ex = {m: ExecConfig.for_market(m, "rakuten") for m in ("JP", "US")}
    cc = {"1655.T": etf_cost("rakuten", "1655.T", "JP")}
    say(f"# 用户描述的操作方式 vs 现行 S0C2（{pd.Timestamp.today().date()}；数据 {time.time() - t0:.0f}s）")
    rows = {}
    for k, kw in MODES.items():
        use = {t: df for t, df in ind.items()
               if t in kw["core"] or (t != "1655.T" and ("JP" if t.endswith(".T") else "US") in kw["stock_markets"])}
        row = {}
        for wn, st in (("w20", W20), ("w5", W5)):
            cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34,
                                core_mode="split", **kw)
            ue = UnifiedEngine(use, cfg, params, ex, {t: cc[t] for t in kw["core"]}, fx=fxdf[["Open", "Close"]],
                               entry_mult=em, bear=bear)
            r = ue.run(start=st)
            tr = r.trades[r.trades["reason"] != "end"] if len(r.trades) else r.trades
            dd = float((r.equity / r.equity.cummax() - 1).min() * 100)
            fx_cost = sum(abs(float(x[2])) * cfg.fx_spread_yen for x in r.state.fx_trades)
            yrs = (r.equity.index[-1] - r.equity.index[0]).days / 365.25
            cagr_x = ((r.equity.iloc[-1] / r.equity.iloc[0]) ** (1 / yrs) - 1) * 100 if yrs > 0 else float("nan")
            row.update({f"{wn}_cagr": r.metrics.get("cagr_pct"), f"{wn}_cagr_exact": cagr_x, f"{wn}_dd_exact": dd,
                        f"{wn}_dd": round(dd, 2), f"{wn}_calmar": r.metrics.get("calmar"),
                        f"{wn}_jp_trades": int((tr["market"] == "JP").sum()) if len(tr) else 0,
                        f"{wn}_us_trades": int((tr["market"] == "US").sum()) if len(tr) else 0,
                        f"{wn}_fx_n": len(r.state.fx_trades), f"{wn}_fx_cost_yr": round(fx_cost / yrs),
                        f"{wn}_usd_days_pct": round(float((np.array([h[3] for h in r.state.history[-len(r.equity):]]) > 100).mean())
                                                    * 100, 1)})
        rows[k] = row
        print(k, json.dumps(row, default=float), f"{time.time() - t0:.0f}s", flush=True)
    say("| 方案 | 20 年年化 / 回撤 / Calmar | 5 年年化 / 回撤 | 20 年成交 日本 / 美股 | 换汇次数 / 点差成本（円/年） | 持有美元的日子 |")
    say("|---|---|---|---|---|---|")
    for k, r in rows.items():
        say(f"| {k} {LABEL[k]} | {r['w20_cagr']}% / {r['w20_dd']}% / {r['w20_calmar']} | {r['w5_cagr']}% / {r['w5_dd']}% | "
            f"{r['w20_jp_trades']} / {r['w20_us_trades']} | {r['w20_fx_n']} / ¥{r['w20_fx_cost_yr']:,} | {r['w20_usd_days_pct']}% |")
    u0, u1, u2 = rows["U0"], rows["U1"], rows["U2"]
    ok = (u2["w20_cagr_exact"] >= u0["w20_cagr_exact"] + 0.3 and u2["w20_cagr_exact"] >= u1["w20_cagr_exact"] + 0.3
          and u2["w20_dd_exact"] >= min(u0["w20_dd_exact"], u1["w20_dd_exact"]))      # 精确值比较（不用四舍五入值）
    say(f"\n精确值：U2 − U0 = {u2['w20_cagr_exact'] - u0['w20_cagr_exact']:+.3f}pp，U2 − U1 = "
        f"{u2['w20_cagr_exact'] - u1['w20_cagr_exact']:+.3f}pp（门槛 +0.3pp）")
    say(f"\n判定（事先规则）：{'日本 + 美股模式默认打开 usd_keep_imminent' if ok else 'usd_keep_imminent 不设为默认（差别不够）'}；"
        "模拟盘是否从 S0C2 换成 U 系列由用户决定。")
    say(f"（耗时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "op_mode_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"rows": rows, "usd_keep_imminent_default": bool(ok)}, ensure_ascii=False,
                                             indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
