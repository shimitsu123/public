"""timing_study.py — 顶底（牛熊）择时是否最优：现行价格均线带 vs 加入汇率 / 失业率 / 信用利差 / 波动率 / 利率曲线 / 动量
（事先写定，先提交后运行，结果出来不改规则）。

要决定的事：S0C2（日本个股 4×25% + 闲置资金全部 1655.T）里，1655 什么时候持有、什么时候拿日元现金。
现行 T0 = ma_band(L=250, b=3%, k=5)（var/bullbear.json，^GSPC 美元价格；2026-09-24 研究选定：训练 1951–2005 平衡准确率）。

候选（qbreak/timing.py，参数全部事先固定，来自现行设定或文献，不做网格搜索）：
  T0  现行：^GSPC 250 日线 ±3%、连续 5 天
  T1  汇率（投资者是日元）：同一规则用在 ^GSPC × USD/JPY（日元计价的 S&P500，≈1655）
  T2  增长 + 趋势（Philosophical Economics 2016「Growth-Trend Timing」）：趋势熊 且 失业率 > 其 12 个月均值 才熊
  T3  信用确认：趋势熊 且 Baa−10Y 利差 > 其 250 日均值 才熊
  T4  压力提前离场：趋势熊 或 压力态（VIX ≥ 30 且 Baa 利差 20 日走阔 ≥ 0.3pt 时进入；VIX < 22 时解除）
  T5  12 个月绝对动量（Moskowitz-Ooi-Pedersen 2012 / Antonacci 2014）：月末 252 日涨幅 ≤ 0 → 熊，持有到下个月末
  T6  多数表决：趋势熊、Baa 利差 > 250 日均值、VIX ≥ 22、失业率 > 12 个月均值、10Y−3M < 0 里 ≥3 项，连续 5 天才切换
  阈值来源：VIX 22 / 30 = 现行宏观层 vix_high / vix_panic；Baa 20 日 +0.3pt = 多因子研究的单因子规则。
数据与时滞：VIX 当天收盘；Baa 利差、美债利率滞后 1 个美国营业日；失业率在次月 10 日起可用（FRED 现行版本，未用实时版本）。
  美元日元 = FRED DEXJPUS（纽约正午），最后几天用 yfinance JPY=X 补；日本现金利率 = FRED IRSTCI01JPM156N（call，月度，次月起用）。

检验 A（指数层，决定用）：日元计价的 S&P500 总收益（^SP500TR × USD/JPY），1990-01～，前半 1990–2005 / 后半 2006–。
  东证 D 日的价格 = D 日之前最后一个美股收盘 × 当时的美元日元；信号用同一个美股收盘（D 日早上已知），D 日按该价格调仓；
  熊市拿日元现金（计 call 利率）；每次切换成本 0.02%（楽天 1655：手续费 0 円，买卖价差）。
检验 B（组合层）：统一引擎 S0C2（与 unified_study 同一构造），20 年 2006-10～ / 5 年 2021-09～，只换「美股牛熊」序列。

采用规则（全部满足才换掉 T0）：
  ① 检验 A 两个半段的 Calmar 都 ≥ T0 + 0.05；② 两个半段的年化都 ≥ T0 − 0.5pp；
  ③ 检验 B 20 年年化 ≥ T0 − 0.3pp、20 年最大回撤不深于 T0（精确值）、5 年回撤 ≥ −30%。
  多个满足：检验 A 两半段 Calmar 均值最高；差 < 0.02 取每年切换更少者。都不满足 → 维持 T0。
另报（不参与决定）：各候选在 9 次美股下跌中的表现（顶→底、底后 12 个月，日元计）；同一组候选用在日経225
  （T1 与 T0 相同不列；因子仍用美国的全球风险因子；日経信号晚一天执行）。
输出 var/out/timing_study.md / .json / .csv。

季度复核（2026-09-25 用户要求；规则不变，只加数据）：`python scripts/timing_study.py --only T0,T2,T3 --review`
  只比较所列候选（T0 必须在内），同一套采用规则；输出 var/out/timing_review_<日期>.md / .json，
  并在 var/out/timing_review_history.csv 追加一行（各候选的两半段 Calmar、组合 20 年年化 / 回撤、判定）。
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
from qbreak import factors, paths                                            # noqa: E402
from qbreak import timing as T                                               # noqa: E402
from qbreak.bullbear import BEAR, Detector, load_config                      # noqa: E402
from qbreak.config import DataConfig, ExecConfig, universe                   # noqa: E402
from qbreak.core import core_frame                                           # noqa: E402
from qbreak.data import load_universe                                        # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.macro import build_entry_mult, features_frame, load_macro_series  # noqa: E402
from qbreak.regime import quant_regime_series                               # noqa: E402
from qbreak.strategy import IndicatorCache                                   # noqa: E402
from qbreak.trader import drop_partial_bar, load_params                      # noqa: E402
from qbreak.unified import UnifiedConfig, UnifiedEngine                      # noqa: E402
from bullbear_study import SYM, load                                         # noqa: E402
from unified_study import W5, W20, spx_jpy_on_jp_days                        # noqa: E402

H1, H2 = ("1990-01-01", "2005-12-31"), ("2006-01-01", None)
COST = 0.0002
EPISODES = [("海湾战争", "1990-07-16", "1990-10-11"), ("LTCM", "1998-07-17", "1998-10-08"),
            ("互联网泡沫", "2000-03-24", "2002-10-09"), ("金融危机", "2007-10-09", "2009-03-09"),
            ("欧债", "2011-04-29", "2011-10-03"), ("中国 / 油价", "2015-05-21", "2016-02-11"),
            ("2018 Q4", "2018-09-20", "2018-12-24"), ("新冠", "2020-02-19", "2020-03-23"),
            ("2022 加息", "2022-01-03", "2022-10-12")]
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def asof(s: pd.Series, when: pd.DatetimeIndex) -> np.ndarray:
    s = s.dropna()
    return s.reindex(s.index.union(when)).ffill().reindex(when).to_numpy(float)


def sim_timing(price: np.ndarray, pos: np.ndarray, cash_rate: np.ndarray, days: pd.DatetimeIndex) -> pd.Series:
    """pos[d]：D 日按 price[d] 调仓后持有到 D+1（1 = 持有指数，0 = 日元现金）。"""
    dt = np.diff(days.values).astype("timedelta64[D]").astype(float)
    r_idx = price[1:] / price[:-1] - 1
    r_cash = cash_rate[:-1] / 100 * dt / 365
    r = pos[:-1] * r_idx + (1 - pos[:-1]) * r_cash
    sw = np.abs(np.diff(np.r_[pos[0], pos]))[:-1] if len(pos) > 1 else np.zeros(0)
    r = r - sw * COST
    eq = np.r_[1.0, np.cumprod(1 + r)]
    return pd.Series(eq, index=days)


def stats(eq: pd.Series, pos: pd.Series) -> dict:
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1
    dd = float((eq / eq.cummax() - 1).min())
    sw = int((pos.diff().abs() > 0).sum())
    return {"cagr": round(cagr * 100, 2), "dd": round(dd * 100, 2), "dd_exact": dd * 100,
            "calmar": round(cagr / abs(dd), 3) if dd < 0 else None, "calmar_exact": cagr / abs(dd) if dd < 0 else None,
            "sw_yr": round(sw / yrs, 2), "invested": round(float(pos.mean()) * 100, 1)}


def window(days: pd.DatetimeIndex, w) -> np.ndarray:
    m = days >= pd.Timestamp(w[0])
    if w[1]:
        m &= days <= pd.Timestamp(w[1])
    return m


def index_test(name: str, price: pd.Series, bears: dict, cash: np.ndarray, lag_signal: bool) -> dict:
    """price：东证交易日的日元价格；bears：候选 → 熊市布尔（已对齐到东证交易日，D 日早上已知）。"""
    days = price.index
    out = {}
    for key, b in {"BH": pd.Series(False, index=days), **bears}.items():
        pos = (~b.astype(bool)).astype(float)
        if lag_signal:                                          # 日経：收盘后才知道 → 晚一天执行
            pos = pos.shift(1).fillna(1.0)
        row = {}
        for wn, w in (("H1", H1), ("H2", H2), ("ALL", (H1[0], None))):
            m = window(days, w)
            d = days[m]
            eq = sim_timing(price.to_numpy(float)[m], pos.to_numpy(float)[m], cash[m], d)
            row[wn] = stats(eq, pos[m])
            row[wn + "_eq"] = eq
        eps = {}
        for en, a, z in EPISODES:
            for tag, lo, hi in (("跌", a, z), ("后12月", z, str((pd.Timestamp(z) + pd.DateOffset(years=1)).date()))):
                m = (days >= pd.Timestamp(lo)) & (days <= pd.Timestamp(hi))
                if m.sum() < 5:
                    continue
                eq = sim_timing(price.to_numpy(float)[m], pos.to_numpy(float)[m], cash[m], days[m])
                eps[f"{en}|{tag}"] = round((eq.iloc[-1] - 1) * 100, 1)
        row["episodes"] = eps
        out[key] = row
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只比较这些候选（逗号分隔，须含 T0），例如 T0,T2,T3")
    ap.add_argument("--review", action="store_true", help="季度复核：输出带日期的文件并追加历史")
    args = ap.parse_args(argv)
    cands = {k: T.CANDIDATES[k] for k in (args.only.split(",") if args.only else T.CANDIDATES)}
    if "T0" not in cands:
        raise SystemExit("--only 必须包含 T0（现行）")
    t0 = time.time()
    end_us = pd.Timestamp.today().normalize() - pd.Timedelta(days=1)
    spx = load("^GSPC", "1950-01-01")["Close"]
    spx = spx[spx.index <= end_us]
    tr = load("^SP500TR", "1988-01-01")["Close"]
    tr = tr[tr.index <= end_us]
    n225 = drop_partial_bar(load("^N225", "1965-01-01"), "JP")["Close"]
    fx = factors.fred("DEXJPUS").dropna()
    jpyx = load("JPY=X", "1996-01-01")["Close"]
    jpyx = jpyx[(jpyx > 60) & (jpyx < 250) & (jpyx.index > fx.index[-1])]
    fx = pd.concat([fx, jpyx]).sort_index()
    fx = fx[~fx.index.duplicated(keep="first")]
    raw = {k: factors.fred(k) for k in ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "UNRATE", "IRSTCI01JPM156N")}
    say(f"# 顶底（牛熊）择时：现行 vs 多重因素（{pd.Timestamp.today().date()}；数据 {time.time() - t0:.0f}s）")
    say(f"数据截至：S&P500 {spx.index[-1].date()}，日経 {n225.index[-1].date()}，美元日元 {fx.index[-1].date()}，"
        f"VIX {raw['VIXCLS'].dropna().index[-1].date()}，Baa {raw['BAA10Y'].dropna().index[-1].date()}，"
        f"失业率 {raw['UNRATE'].dropna().index[-1].strftime('%Y-%m')}")
    us_days = spx.index[spx.index >= "1985-01-01"]
    f_us = T.factor_frame(us_days, fx, raw["VIXCLS"], raw["BAA10Y"], raw["DGS10"], raw["DGS3MO"], raw["UNRATE"])
    close_us = spx.loc[us_days]
    bears_us = {k: fn(close_us, f_us).astype(bool) for k, fn in cands.items()}

    # ── 检验 A：日元计价 S&P500 总收益 ──
    jp_days = n225.index[(n225.index >= H1[0])]
    prev = jp_days - pd.Timedelta(days=1)                       # D 日早上已知的最后一个美股收盘
    price = pd.Series(asof(tr, prev) * asof(fx, prev), index=jp_days)
    cash = asof(T.monthly_available(raw["IRSTCI01JPM156N"], jp_days, lag_day=1), jp_days)
    bears_jp_days = {k: pd.Series(asof(b.astype(float), prev) > 0.5, index=jp_days) for k, b in bears_us.items()}
    A = index_test("SPX_JPY", price, bears_jp_days, np.nan_to_num(cash), lag_signal=False)
    say("\n## 检验 A：日元计价的 S&P500 总收益（≈1655），熊市拿日元现金")
    say("| 方案 | 1990–2005 年化 / 回撤 / Calmar | 2006– 年化 / 回撤 / Calmar | 每年切换 | 持有时间 |")
    say("|---|---|---|---|---|")
    for k, r in A.items():
        lab = "买入持有" if k == "BH" else f"{k} {T.LABELS[k]}"
        say(f"| {lab} | {r['H1']['cagr']}% / {r['H1']['dd']}% / {r['H1']['calmar']} | "
            f"{r['H2']['cagr']}% / {r['H2']['dd']}% / {r['H2']['calmar']} | {r['ALL']['sw_yr']} | {r['ALL']['invested']}% |")

    # ── 检验 B：统一引擎 S0C2 ──
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    params = {m: load_params(market=m) for m in ("JP", "US")}
    data = load_universe(universe("JP", "broad"), d21)
    ind = dict(IndicatorCache(data).all(params["JP"]))
    idx = {m: load(*SYM[m]) for m in ("JP", "US")}
    fxdf = load("JPY=X", "2000-01-01")
    fxdf = fxdf[(fxdf["Close"] > 60) & (fxdf["Close"] < 250)]
    etf = load_universe(["1655.T"], d21)
    ind["1655.T"] = core_frame(etf["1655.T"], spx_jpy_on_jp_days(idx["US"], fxdf["Close"], idx["JP"].index), div_yield_pct=1.3)
    macro = features_frame(load_macro_series(d21))
    names = list(data)
    g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
    mc = sim.get("jp", {})
    flag = lambda k, d=True: mc.get(k, sim.get(k, d))                          # noqa: E731
    closes = pd.DataFrame({t: data[t]["Close"] for t in names})
    M, _ = build_entry_mult(g, names, "JP", macro, use_macro=bool(flag("use_macro")),
                            use_sector=bool(flag("use_sector_tilt")), use_events=False, closes=closes)
    M = M * quant_regime_series(idx["JP"]).reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
    em = {"JP": pd.DataFrame(M, index=g, columns=names)}
    cfgd = load_config()
    det = Detector(cfgd["detector"]["kind"], cfgd["detector"]["params"])
    bear_jp = pd.Series(np.asarray(det.states(idx["JP"]["Close"])) == BEAR, index=idx["JP"].index)
    ex = {m: ExecConfig.for_market(m, "rakuten") for m in ("JP", "US")}
    cc = {"1655.T": etf_cost("rakuten", "1655.T", "JP")}
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34,
                        stock_markets=("JP",), core={"1655.T": 1.0}, core_index={"1655.T": "US"}, core_mode="split")
    Bres = {}
    for k, b in bears_us.items():
        row = {}
        for wn, st in (("w20", W20), ("w5", W5)):
            ue = UnifiedEngine(ind, cfg, params, ex, cc, fx=fxdf[["Open", "Close"]], entry_mult=em,
                               bear={"JP": bear_jp, "US": b})
            r = ue.run(start=st)
            dd = float((r.equity / r.equity.cummax() - 1).min() * 100)
            row.update({f"{wn}_cagr": r.metrics.get("cagr_pct"), f"{wn}_dd": round(dd, 2), f"{wn}_dd_exact": dd,
                        f"{wn}_calmar": r.metrics.get("calmar"), f"{wn}_core_trades": len(r.state.core_trades)})
        Bres[k] = row
        print(k, json.dumps(row, default=float), f"{time.time() - t0:.0f}s", flush=True)
    say("\n## 检验 B：S0C2 组合（统一引擎，楽天费用），只换美股牛熊序列")
    say("| 方案 | 20 年年化 / 回撤 / Calmar | 5 年年化 / 回撤 | 20 年 1655 调仓笔数 |")
    say("|---|---|---|---|")
    for k, r in Bres.items():
        say(f"| {k} | {r['w20_cagr']}% / {r['w20_dd_exact']:.2f}% / {r['w20_calmar']} | {r['w5_cagr']}% / {r['w5_dd_exact']:.2f}% | "
            f"{r['w20_core_trades']} |")

    # ── 判定（事先规则）──
    base_a, base_b = A["T0"], Bres["T0"]
    why, ok = {}, []
    for k in cands:
        if k == "T0":
            continue
        a, b = A[k], Bres[k]
        fails = []
        for h in ("H1", "H2"):
            if a[h]["calmar_exact"] is None or a[h]["calmar_exact"] < base_a[h]["calmar_exact"] + 0.05:
                fails.append(f"{h} Calmar {a[h]['calmar']} < T0 {base_a[h]['calmar']} + 0.05")
            if a[h]["cagr"] < base_a[h]["cagr"] - 0.5:
                fails.append(f"{h} 年化 {a[h]['cagr']}% < T0 {base_a[h]['cagr']}% − 0.5")
        if b["w20_cagr"] < base_b["w20_cagr"] - 0.3:
            fails.append(f"组合 20 年年化 {b['w20_cagr']}% < T0 {base_b['w20_cagr']}% − 0.3")
        if b["w20_dd_exact"] < base_b["w20_dd_exact"]:
            fails.append(f"组合 20 年回撤 {b['w20_dd_exact']:.2f}% 深于 T0 {base_b['w20_dd_exact']:.2f}%")
        if b["w5_dd_exact"] < -30.0:
            fails.append(f"组合 5 年回撤 {b['w5_dd_exact']:.2f}% < −30%")
        why[k] = fails
        if not fails:
            ok.append(k)
    if ok:
        mean = {k: (A[k]["H1"]["calmar_exact"] + A[k]["H2"]["calmar_exact"]) / 2 for k in ok}
        top = max(mean.values())
        near = [k for k in ok if mean[k] >= top - 0.02]
        pick = min(near, key=lambda k: (A[k]["ALL"]["sw_yr"], -mean[k]))
    else:
        pick = "T0"
    say(f"\n判定（事先规则）：{pick}（{T.LABELS[pick]}）")
    for k, fl in why.items():
        say(f"- {k}：{'全部满足' if not fl else '；'.join(fl)}")

    # ── 另报：9 次下跌 ──
    say("\n## 另报：美股 9 次下跌里的表现（日元计，检验 A 的口径；「跌」= 顶→底，「后 12 月」= 底后一年）")
    heads = [f"{en}|{tag}" for en, _, _ in EPISODES for tag in ("跌", "后12月")]
    say("| 方案 | " + " | ".join(h.replace("|", " ") for h in heads) + " |")
    say("|---|" + "---|" * len(heads))
    for k, r in A.items():
        say(f"| {k} | " + " | ".join(f"{r['episodes'].get(h, '—')}%" for h in heads) + " |")

    # ── 另报：日経225（1329 的择时）──
    jd = n225.index[n225.index >= "1985-01-01"]
    f_jp = pd.DataFrame({c: asof(f_us[c], jd - pd.Timedelta(days=1)) for c in f_us.columns}, index=jd)
    nk = n225.loc[jd]
    bears_nk = {k: fn(nk, f_jp).astype(bool) for k, fn in cands.items() if k != "T1"}
    days_nk = jd[jd >= H1[0]]
    div = (1 + 0.016) ** (np.arange(len(days_nk)) / 245.0)
    price_nk = pd.Series(nk.loc[days_nk].to_numpy(float) * div, index=days_nk)
    cash_nk = asof(T.monthly_available(raw["IRSTCI01JPM156N"], days_nk, lag_day=1), days_nk)
    N = index_test("N225", price_nk, {k: b.loc[days_nk] for k, b in bears_nk.items()}, np.nan_to_num(cash_nk),
                   lag_signal=True)
    say("\n## 另报：日経225（+股息 1.6%/年，日元），同一组候选（不参与决定）")
    say("| 方案 | 1990–2005 年化 / 回撤 / Calmar | 2006– 年化 / 回撤 / Calmar | 每年切换 | 持有时间 |")
    say("|---|---|---|---|---|")
    for k, r in N.items():
        lab = "买入持有" if k == "BH" else f"{k} {T.LABELS[k]}"
        say(f"| {lab} | {r['H1']['cagr']}% / {r['H1']['dd']}% / {r['H1']['calmar']} | "
            f"{r['H2']['cagr']}% / {r['H2']['dd']}% / {r['H2']['calmar']} | {r['ALL']['sw_yr']} | {r['ALL']['invested']}% |")

    fp = paths.out_dir() / ("timing_study" if not args.review else f"timing_review_{pd.Timestamp.today().date()}")
    if args.review:
        hist = paths.out_dir() / "timing_review_history.csv"
        row = {"run": str(pd.Timestamp.today().date()), "data_end": str(spx.index[-1].date()), "pick": pick}
        for k in cands:
            row.update({f"{k}_A_H1_calmar": A[k]["H1"]["calmar"], f"{k}_A_H2_calmar": A[k]["H2"]["calmar"],
                        f"{k}_B20_cagr": Bres[k]["w20_cagr"], f"{k}_B20_dd": round(Bres[k]["w20_dd_exact"], 2)})
        old_h = pd.read_csv(hist) if hist.exists() else pd.DataFrame()
        prev = old_h["pick"].iloc[-1] if len(old_h) else "T0"
        say(f"\n季度复核：上次判定 {prev} → 本次 {pick}" + ("（★ 判定改变：需用户确认后才改模拟盘）" if pick != prev else "（未改变）"))
        pd.concat([old_h, pd.DataFrame([row])], ignore_index=True).to_csv(hist, index=False)
    strip = lambda r: {k: v for k, v in r.items() if not k.endswith("_eq")}   # noqa: E731
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps({"pick": pick, "why": why, "A": {k: strip(v) for k, v in A.items()},
                                              "B": Bres, "N225": {k: strip(v) for k, v in N.items()}},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    rows = [{"cand": k, **{f"A_{h}_{m}": A[k][h][m] for h in ("H1", "H2", "ALL") for m in ("cagr", "dd", "calmar", "sw_yr")},
             **(Bres.get(k) or {})} for k in A]
    pd.DataFrame(rows).to_csv(f"{fp}.csv", index=False, encoding="utf-8-sig")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
