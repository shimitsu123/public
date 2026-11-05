"""unified_study.py — 一个账户 ¥1,000,000（楽天）里日本株 + 美股 + 东证 ETF 怎么配（事先写定，先提交后运行，结果出来不改规则）。

账户：总资金 ¥1,000,000（不是日本、美股各 100 万）。楽天费用：日本株 / 东证 ETF 0 円（ゼロコース），美股 0.495%（上限 $22）。
换汇（运行前按 2026-09-25 的官方核对修订，结果出来之前）：リアルタイム為替 手数料 0 銭、买卖价差按片道 3 銭估；
平日 8:00 起可换 → 美股买入当天先换汇、当晚开盘成交；美股卖出的美元次日 8:00 换回日元、9:00 日本开盘可用；
日本祝日（海外市场开）也能换汇（qbreak/unified.py 的默认值）。敏感性：另报告换汇按 ±25 銭（円貨決済 / 定時為替的水平）时 S1 的结果，不参与选择。
个股：现行参数（best_params_JP / best_params_US），日本与美股的新信号一起排名、共用名额（执行成本低的优先）。
候选（2 × 4 = 8 个，个股仓位固定 4×25%，避免多重比较）：
  个股范围  S0 只做日本个股（日経225，按偏好剔除）   S1 日本 + 美股个股（NASDAQ-100 + Dow30，按偏好剔除）一起排名
  闲置资金  C1 只买 1329（日経225）  C2 只买 1655（S&P500，东证，日元）  C3 1329 / 1655 各半（熊市那份留现金）
            C4 1329 / 1655 各半但熊市那份转给牛市的一只（都熊 → 现金）
  两只 ETF 各按自己指数的牛熊分界择时（var/bullbear.json 的检测器；日経 / S&P500）。
  1655 上市（2017-09）前用 S&P500 ×USD/JPY（前一个美股收盘 × 当日汇率）+ 估计股息 1.3%/年拼接；1329 上市前用日経 + 1.6%。
窗口：20 年（2006-10～）与 5 年（2021-09～）。
选择规则（与资金配置「进取」档相同）：20 年回撤 ≥ −35% 且 5 年回撤 ≥ −30% 的方案里取 20 年年化最高；
  年化差 < 0.5pp 取 Calmar 高者。另报告「加美股个股」（S1 − S0）在每种闲置资金方案下的差。
个股部分有幸存者偏差（偏乐观，两种个股范围都有）；指数部分没有。
输出 var/out/unified_study.md / .json / .csv。

运行后修订（2026-09-25，只改比较精度，规则不变）：第一次运行拿四舍五入到 0.01 的回撤去比较，
S0C2 的 20 年回撤精确值 −35.0011% 显示成 −35.0% 而「通过」。规则原文是「≥ −35%」，改用未四舍五入的值比较；
按四舍五入值的判定（第一次运行的结果）也一并输出（pick_rounded），不隐藏。
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
from qbreak.config import DataConfig, ExecConfig, universe                 # noqa: E402
from qbreak.core import core_frame                                         # noqa: E402
from qbreak.data import load_universe                                      # noqa: E402
from qbreak.fees import etf_cost                                           # noqa: E402
from qbreak.macro import build_entry_mult, features_frame, load_macro_series  # noqa: E402
from qbreak.regime import quant_regime_series                             # noqa: E402
from qbreak.strategy import IndicatorCache                                 # noqa: E402
from qbreak.trader import load_params                                      # noqa: E402
from qbreak.unified import UnifiedConfig, UnifiedEngine                    # noqa: E402
from bullbear_study import SYM, load                                       # noqa: E402

W20, W5 = "2006-10-01", "2021-09-24"
CORES = {"C1": ({"1329.T": 1.0}, "split"), "C2": ({"1655.T": 1.0}, "split"),
         "C3": ({"1329.T": 0.5, "1655.T": 0.5}, "split"), "C4": ({"1329.T": 0.5, "1655.T": 0.5}, "follow")}
STOCKS = {"S0": ("JP",), "S1": ("JP", "US")}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def spx_jpy_on_jp_days(spx: pd.DataFrame, fx: pd.Series, jp_days: pd.DatetimeIndex) -> pd.DataFrame:
    """东证交易日 d 的「S&P500 日元价」= 前一个美股收盘 × d 日早上的 USD/JPY（前一日收盘）。"""
    us_prev = spx["Close"].shift(0).reindex(jp_days.union(spx.index)).ffill().shift(1).reindex(jp_days)
    fxp = fx.reindex(jp_days.union(fx.index)).ffill().shift(1).reindex(jp_days)
    c = (us_prev * fxp).dropna()
    return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 1e9}, index=c.index)


def choose(df: pd.DataFrame, dd: str) -> str | None:
    """事先规则：20 年回撤 ≥ −35% 且 5 年回撤 ≥ −30% 里取 20 年年化最高；年化差 < 0.5pp 取 Calmar 高者。"""
    ok = df[(df[f"w20{dd}"] >= -35.0) & (df[f"w5{dd}"] >= -30.0)]
    if ok.empty:
        return None
    cand = ok[ok["w20_cagr"] >= ok["w20_cagr"].max() - 0.5].copy()
    cand["calmar_exact"] = cand["w20_cagr"] / cand[f"w20{dd}"].abs()
    return str(cand.sort_values("calmar_exact", ascending=False).iloc[0]["scheme"])


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
    etf = load_universe(["1329.T", "1655.T"], d21)
    jp_days = idx["JP"].index
    ind["1329.T"] = core_frame(etf["1329.T"], idx["JP"], div_yield_pct=1.6)
    ind["1655.T"] = core_frame(etf["1655.T"], spx_jpy_on_jp_days(idx["US"], fxdf["Close"], jp_days), div_yield_pct=1.3)
    say(f"# 一个账户 ¥1,000,000（楽天）：日本株 + 美股 + 东证 ETF（{pd.Timestamp.today().date()}；数据 {time.time() - t0:.0f}s）")
    # 宏观 / 板块倍数 × 量化状态层（与模拟盘同口径），按市场
    macro = features_frame(load_macro_series(d21))
    em = {}
    for m in ("JP", "US"):
        names = list(data[m])
        g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
        mc = sim.get(m.lower(), {})
        flag = lambda k, d=True, mc=mc: mc.get(k, sim.get(k, d))            # noqa: E731
        closes = pd.DataFrame({t: data[m][t]["Close"] for t in names})
        M, _ = build_entry_mult(g, names, m, macro, use_macro=bool(flag("use_macro")),
                                use_sector=bool(flag("use_sector_tilt")), use_events=False, closes=closes)
        M = M * quant_regime_series(idx[m]).reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
        em[m] = pd.DataFrame(M, index=g, columns=names)
    cfgd = load_config()
    det = Detector(cfgd["detector"]["kind"], cfgd["detector"]["params"])
    bear = {m: pd.Series(np.asarray(det.states(idx[m]["Close"])) == BEAR, index=idx[m].index) for m in ("JP", "US")}
    ex = {m: ExecConfig.for_market(m, "rakuten") for m in ("JP", "US")}
    ccost = {t: etf_cost("rakuten", t, "JP") for t in ("1329.T", "1655.T")}
    fx = fxdf[["Open", "Close"]]
    rows = []
    for sk, mk in STOCKS.items():
        for ck, (core, mode) in CORES.items():
            row = {"scheme": f"{sk}{ck}", "stocks": "+".join(mk), "core": core, "mode": mode}
            for wname, start in (("w20", W20), ("w5", W5)):
                use = {t: df for t, df in ind.items()
                       if (t in core) or (t not in ("1329.T", "1655.T") and ("JP" if t.endswith(".T") else "US") in mk)}
                cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34,
                                    stock_markets=mk, core=core,
                                    core_index={t: ("JP" if t == "1329.T" else "US") for t in core}, core_mode=mode)
                ue = UnifiedEngine(use, cfg, params, ex, {t: ccost[t] for t in core}, fx=fx, entry_mult=em, bear=bear)
                r = ue.run(start=start)
                mt, tr = r.metrics, r.trades[r.trades["reason"] != "end"]
                dd_exact = float((r.equity / r.equity.cummax() - 1).min() * 100)   # 不四舍五入，判定用
                row.update({f"{wname}_cagr": mt.get("cagr_pct"), f"{wname}_dd": mt.get("max_dd_pct"),
                            f"{wname}_dd_exact": dd_exact,
                            f"{wname}_calmar": mt.get("calmar"),
                            f"{wname}_jp_trades": int((tr["market"] == "JP").sum()),
                            f"{wname}_us_trades": int((tr["market"] == "US").sum()),
                            f"{wname}_fx": len(r.state.fx_trades)})
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "core"}, ensure_ascii=False, default=float),
                  f"{time.time() - t0:.0f}s", flush=True)
    sens = {}                                               # 敏感性：换汇 ±25 銭（不参与选择）
    for ck, (core, mode) in CORES.items():
        use = {t: df for t, df in ind.items() if (t in core) or (t not in ("1329.T", "1655.T"))}
        cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34,
                            stock_markets=("JP", "US"), core=core,
                            core_index={t: ("JP" if t == "1329.T" else "US") for t in core}, core_mode=mode,
                            fx_spread_yen=0.25)
        r = UnifiedEngine(use, cfg, params, ex, {t: ccost[t] for t in core}, fx=fx, entry_mult=em, bear=bear).run(start=W20)
        sens[f"S1{ck}"] = r.metrics.get("cagr_pct")
    df = pd.DataFrame(rows)
    say("\n| 方案 | 个股 | 闲置资金 | 20 年年化 | 20 年回撤 | Calmar | 5 年年化 | 5 年回撤 | 20 年成交 日本 / 美股 / 换汇 |")
    say("|---|---|---|---|---|---|---|---|---|")
    for _, r in df.iterrows():
        cdesc = " + ".join(f"{t.split('.')[0]}×{w:g}" for t, w in r["core"].items()) + ("（跟随牛市）" if r["mode"] == "follow" else "")
        say(f"| {r['scheme']} | {r['stocks']} | {cdesc} | {r['w20_cagr']}% | {r['w20_dd']}% | {r['w20_calmar']} | "
            f"{r['w5_cagr']}% | {r['w5_dd']}% | {r['w20_jp_trades']} / {r['w20_us_trades']} / {r['w20_fx']} |")
    pick, pick_rounded = choose(df, "_dd_exact"), choose(df, "_dd")
    say(f"\n判定（事先规则，回撤按精确值比较）：{pick or '没有方案满足回撤约束'}")
    edge = df[(df["w20_dd"] >= -35.0) & (df["w5_dd"] >= -30.0)
              & ~((df["w20_dd_exact"] >= -35.0) & (df["w5_dd_exact"] >= -30.0))]
    for _, r in edge.iterrows():
        say(f"压线：{r['scheme']} 20 年回撤精确值 {r['w20_dd_exact']:.4f}%、5 年 {r['w5_dd_exact']:.4f}%"
            f"（表中四舍五入为 {r['w20_dd']}% / {r['w5_dd']}%），不满足约束")
    if pick_rounded != pick:
        say(f"按四舍五入后的回撤判定会是 {pick_rounded}（第一次运行的结果；精度修订见文件头）")
    say("\n加美股个股（S1 − S0）的 20 年年化差：" + "；".join(
        f"{ck} {float(df.loc[df.scheme == 'S1' + ck, 'w20_cagr'].iloc[0]) - float(df.loc[df.scheme == 'S0' + ck, 'w20_cagr'].iloc[0]):+.2f}pp"
        for ck in CORES))
    say("换汇按 ±25 銭时 S1 的 20 年年化（敏感性，不参与选择）：" + "；".join(f"{k} {v}%" for k, v in sens.items()))
    fp = paths.out_dir() / "unified_study"
    df.drop(columns=["core"]).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"pick": pick, "pick_rounded": pick_rounded, "rows": df.drop(columns=["core"]).to_dict("records")},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
