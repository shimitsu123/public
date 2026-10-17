"""threat_index_study.py — 大事件威胁指数：大跌之前常见的因素能不能提前标出高风险时间段（事先写定，先提交后运行，结果出来不改规则）。

用户问（2026-09-25）：做一个即将大事件的威胁指数，结合之前大事件发生前的因素推测以后大概发生的时间段，来规避风险。
指数：qbreak/threat.py —— 美股 8 个因素、日経 10 个因素（VIX、VIX 急升、信用利差走阔、利率曲线倒挂、美债利率急升、油价冲击、
  失业率上升、指数波动；日経另加日元急升、日债利率急升）的扩张窗口百分位等权平均，0–100，不拟合任何系数。
「大事件」：今天收盘后 60 个交易日内，指数最低收盘比今天跌 ≥10%（S&P500 / 日経225 各自）。
检验（1995-01～；因素要 3 年历史才开始用；最后 60 个交易日没有答案不计）：
  ① 预测力：AUC，前半 1995–2010 / 后半 2011–；② 分档：指数十分位 → 之后 60 日出现 ≥10% 下跌的频率；
  ③ 提前量：每次 ≥10% 下跌（10% / 10% 阈值法标注的高点）之前 60 / 20 个交易日与高点当天的指数值，高点前 60 日内是否到过 80；
  ④ 交易用法（组合 S0C2 20 年，统一引擎，楽天费用）：
     O1 美股威胁 ≥ 80 时 1655 也清仓（< 70 恢复；叠加在现行牛熊分界上）；O2 日本威胁 ≥ 80 时日本个股新仓 ×0.5；O3 = O1 + O2。
采用规则（全部满足才用于交易，否则只在日报展示）：
  对应市场（O1 看美股、O2 看日本、O3 两个都看）AUC 两个半段都 ≥ 0.65；
  组合 S0C2 20 年 Calmar ≥ 现行 + 0.03、年化 ≥ 现行 − 0.5pp、最大回撤不深于现行（精确值）。多个满足取 Calmar 最高者。
另报：当前读数、各因素当前百分位、当前档位的历史频率；分档表写入 var/threat_index.json 供日报使用。
输出 var/out/threat_index_study.md / .json。
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
from qbreak import threat as TH                                              # noqa: E402
from qbreak.bullbear import BEAR, Detector, date_phases, load_config         # noqa: E402
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

EVAL0, SPLIT = pd.Timestamp("1995-01-01"), pd.Timestamp("2011-01-01")
ON, OFF = 80.0, 70.0
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def hysteresis(x: pd.Series, on: float = ON, off: float = OFF) -> pd.Series:
    out, st = [], False
    for v in x.to_numpy(float):
        if not st and v >= on:
            st = True
        elif st and (v < off or not np.isfinite(v)):
            st = False
        out.append(st)
    return pd.Series(out, index=x.index)


def load_inputs() -> dict:
    end_us = pd.Timestamp.today().normalize() - pd.Timedelta(days=1)
    spx = load("^GSPC", "1950-01-01")["Close"]
    spx = spx[spx.index <= end_us]
    n225 = drop_partial_bar(load("^N225", "1965-01-01"), "JP")["Close"]
    fx = factors.fred("DEXJPUS").dropna()
    jpyx = load("JPY=X", "1996-01-01")["Close"]
    jpyx = jpyx[(jpyx > 60) & (jpyx < 250) & (jpyx.index > fx.index[-1])]
    fx = pd.concat([fx, jpyx]).sort_index()
    fx = fx[~fx.index.duplicated(keep="first")]
    raw = {k: factors.fred(k) for k in ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "DCOILWTICO", "UNRATE")}
    jgb = factors.jgb_curve()["10Y"].dropna()
    return {"spx": spx, "n225": n225, "fx": fx, "raw": raw, "jgb": jgb}


def build_indices(d: dict) -> dict:
    r = d["raw"]
    us_days = d["spx"].index[d["spx"].index >= "1990-01-01"]
    raw_us = TH.raw_features(us_days, d["spx"], r["VIXCLS"], r["BAA10Y"], r["DGS10"], r["DGS3MO"], r["DCOILWTICO"],
                             r["UNRATE"])
    idx_us, pct_us = TH.threat_index(raw_us, TH.US_COLS)
    jp_days = d["n225"].index[d["n225"].index >= "1990-01-01"]
    m = {k: TH.us_asof_for_jp(r[k], jp_days) for k in ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "DCOILWTICO")}
    raw_jp = TH.raw_features(jp_days, d["n225"], m["VIXCLS"], m["BAA10Y"], m["DGS10"], m["DGS3MO"], m["DCOILWTICO"],
                             r["UNRATE"], usdjpy=TH.us_asof_for_jp(d["fx"], jp_days), jgb10=d["jgb"].shift(1))
    idx_jp, pct_jp = TH.threat_index(raw_jp, TH.JP_COLS)
    return {"US": (idx_us, pct_us, raw_us, d["spx"].reindex(us_days)), "JP": (idx_jp, pct_jp, raw_jp, d["n225"].reindex(jp_days))}


def evaluate(idx: pd.Series, close: pd.Series) -> dict:
    fdd = TH.forward_drawdown(close, 60)
    ev = (fdd <= -0.10).astype(float).where(fdd.notna())
    m = (idx.index >= EVAL0) & idx.notna() & ev.notna()
    s, e = idx[m], ev[m]
    h1, h2 = s.index < SPLIT, s.index >= SPLIT
    out = {"base_rate": round(float(e.mean()) * 100, 1), "n": int(len(s)),
           "auc_all": TH.auc(s, e), "auc_h1": TH.auc(s[h1], e[h1]), "auc_h2": TH.auc(s[h2], e[h2])}
    bins = np.arange(0, 101, 10)
    cat = pd.cut(s, bins, include_lowest=True, right=False)
    tab = e.groupby(cat, observed=False).agg(["mean", "size"])
    out["deciles"] = [{"lo": int(b.left), "hi": int(b.right), "freq": round(float(r["mean"]) * 100, 1) if r["size"] else None,
                       "n": int(r["size"])} for b, r in tab.iterrows()]
    hi = s >= ON
    out["ge80"] = {"share_days": round(float(hi.mean()) * 100, 1),
                   "freq": round(float(e[hi].mean()) * 100, 1) if hi.any() else None}
    return out


def episodes(idx: pd.Series, close: pd.Series) -> list[dict]:
    tp, _ = date_phases(close.dropna(), 0.10, 0.10)
    rows = []
    pos = {d: k for k, d in enumerate(idx.index)}
    for _, r in tp[tp["kind"] == "peak"].iterrows():
        if r["date"] < EVAL0 or r["date"] not in pos:
            continue
        k = pos[r["date"]]
        nxt = tp[(tp["kind"] == "trough") & (tp["date"] > r["date"])]
        depth = float(nxt["close"].iloc[0] / r["close"] - 1) * 100 if len(nxt) else None
        win = idx.iloc[max(0, k - 60):k + 1]
        rows.append({"peak": str(r["date"].date()), "depth_pct": round(depth, 1) if depth is not None else None,
                     "t_60": round(float(idx.iloc[k - 60]), 0) if k >= 60 and idx.iloc[k - 60] == idx.iloc[k - 60] else None,
                     "t_20": round(float(idx.iloc[k - 20]), 0) if k >= 20 and idx.iloc[k - 20] == idx.iloc[k - 20] else None,
                     "t_0": round(float(idx.iloc[k]), 0) if idx.iloc[k] == idx.iloc[k] else None,
                     "hit80_before": bool((win >= ON).any())})
    return rows


def s0c2_setup() -> dict:
    """与 timing_study 检验 B 相同的 S0C2 构造。"""
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
    flag = lambda k, dflt=True: mc.get(k, sim.get(k, dflt))                     # noqa: E731
    closes = pd.DataFrame({t: data[t]["Close"] for t in names})
    M, _ = build_entry_mult(g, names, "JP", macro, use_macro=bool(flag("use_macro")),
                            use_sector=bool(flag("use_sector_tilt")), use_events=False, closes=closes)
    M = M * quant_regime_series(idx["JP"]).reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
    cfgd = load_config()
    det = Detector(cfgd["detector"]["kind"], cfgd["detector"]["params"])
    bear = {m: pd.Series(np.asarray(det.states(idx[m]["Close"])) == BEAR, index=idx[m].index) for m in ("JP", "US")}
    return {"ind": ind, "params": params, "em_jp": pd.DataFrame(M, index=g, columns=names), "bear": bear,
            "fx": fxdf[["Open", "Close"]], "grid": g}


def run_s0c2(S: dict, bear_us: pd.Series, em_jp: pd.DataFrame) -> dict:
    ex = {m: ExecConfig.for_market(m, "rakuten") for m in ("JP", "US")}
    cc = {"1655.T": etf_cost("rakuten", "1655.T", "JP")}
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34,
                        stock_markets=("JP",), core={"1655.T": 1.0}, core_index={"1655.T": "US"}, core_mode="split")
    row = {}
    for wn, st in (("w20", W20), ("w5", W5)):
        ue = UnifiedEngine(S["ind"], cfg, S["params"], ex, cc, fx=S["fx"], entry_mult={"JP": em_jp},
                           bear={"JP": S["bear"]["JP"], "US": bear_us})
        r = ue.run(start=st)
        dd = float((r.equity / r.equity.cummax() - 1).min() * 100)
        row.update({f"{wn}_cagr": r.metrics.get("cagr_pct"), f"{wn}_dd": dd, f"{wn}_calmar": r.metrics.get("calmar")})
    return row


def main() -> int:
    t0 = time.time()
    d = load_inputs()
    I = build_indices(d)
    say(f"# 大事件威胁指数（{pd.Timestamp.today().date()}；数据截至 S&P500 {d['spx'].index[-1].date()} / 日経 {d['n225'].index[-1].date()}）")
    say("「大事件」= 之后 60 个交易日内最低收盘比当天跌 ≥10%；评估 1995-01～（最后 60 日无答案不计）")
    out = {}
    for m, name in (("US", "S&P500"), ("JP", "日経225")):
        idx, pct, raw, close = I[m]
        ev = evaluate(idx, close)
        ep = episodes(idx, close)
        out[m] = {"eval": ev, "episodes": ep}
        say(f"\n## {name}：基准频率 {ev['base_rate']}%（{ev['n']} 天）；AUC 全期 {ev['auc_all']:.3f}，1995–2010 {ev['auc_h1']:.3f}，"
            f"2011– {ev['auc_h2']:.3f}")
        say("| 指数档位 | 天数 | 之后 60 日 ≥10% 下跌的频率 |")
        say("|---|---|---|")
        for b in ev["deciles"]:
            say(f"| {b['lo']}–{b['hi']} | {b['n']} | {b['freq'] if b['freq'] is not None else '—'}% |")
        say(f"指数 ≥ 80 的日子占 {ev['ge80']['share_days']}%，其后 60 日 ≥10% 下跌的频率 {ev['ge80']['freq']}%")
        say(f"\n历次 ≥10% 下跌（高点 → 跌幅；高点前 60 / 20 个交易日与高点当天的指数；高点前 60 日内是否到过 {ON:.0f}）：")
        hits = sum(e["hit80_before"] for e in ep)
        for e in ep:
            say(f"- {e['peak']}（{e['depth_pct']}%）：{e['t_60']} → {e['t_20']} → {e['t_0']}；{'到过' if e['hit80_before'] else '没到'}")
        say(f"高点前 60 日内到过 {ON:.0f} 的：{hits} / {len(ep)} 次")
        last = idx.dropna()
        cur = float(last.iloc[-1])
        dec = next((b for b in ev["deciles"] if b["lo"] <= cur < b["hi"] or (b["hi"] == 100 and cur >= 100)), None)
        top = pct.iloc[-1].dropna().sort_values(ascending=False)
        out[m]["current"] = {"date": str(last.index[-1].date()), "value": round(cur, 1),
                             "decile_freq": dec["freq"] if dec else None,
                             "factors": {k: round(float(v) * 100, 0) for k, v in top.items()}}
        say(f"\n当前（{last.index[-1].date()}）：{cur:.0f}；同档位历史 60 日 ≥10% 下跌频率 {dec['freq'] if dec else '—'}%；"
            "各因素百分位：" + "、".join(f"{TH.LABELS[k]} {v * 100:.0f}" for k, v in top.items()))

    # ── ④ 交易用法：组合 S0C2 ──
    S = s0c2_setup()
    base = run_s0c2(S, S["bear"]["US"], S["em_jp"])
    t0_bear = S["bear"]["US"]                                    # 与「现行」同一条牛熊序列
    stress_us = hysteresis(I["US"][0]).reindex(t0_bear.index).fillna(False).astype(bool)
    o1_bear = (t0_bear | stress_us).astype(bool)
    g = S["grid"]
    jp_hot = (I["JP"][0].reindex(g.union(I["JP"][0].index)).ffill().reindex(g) >= ON).shift(1).fillna(False)
    em_o2 = S["em_jp"].mul(np.where(jp_hot.to_numpy(bool), 0.5, 1.0), axis=0)
    res = {"now": base, "O1": run_s0c2(S, o1_bear, S["em_jp"]), "O2": run_s0c2(S, S["bear"]["US"], em_o2),
           "O3": run_s0c2(S, o1_bear, em_o2)}
    out["portfolio"] = res
    say("\n## 交易用法：组合 S0C2（统一引擎，楽天费用）")
    say("| 方案 | 20 年年化 / 回撤 / Calmar | 5 年年化 / 回撤 |")
    say("|---|---|---|")
    lab = {"now": "现行", "O1": "O1 美股威胁≥80 时 1655 清仓", "O2": "O2 日本威胁≥80 时个股新仓×0.5", "O3": "O3 = O1 + O2"}
    for k, r in res.items():
        say(f"| {lab[k]} | {r['w20_cagr']}% / {r['w20_dd']:.2f}% / {r['w20_calmar']} | {r['w5_cagr']}% / {r['w5_dd']:.2f}% |")
    need = {"O1": ["US"], "O2": ["JP"], "O3": ["US", "JP"]}
    ok = []
    for k in ("O1", "O2", "O3"):
        auc_ok = all((out[m]["eval"]["auc_h1"] or 0) >= 0.65 and (out[m]["eval"]["auc_h2"] or 0) >= 0.65 for m in need[k])
        r = res[k]
        port_ok = ((r["w20_calmar"] or 0) >= (base["w20_calmar"] or 0) + 0.03 and r["w20_cagr"] >= base["w20_cagr"] - 0.5
                   and r["w20_dd"] >= base["w20_dd"])
        out.setdefault("checks", {})[k] = {"auc_ok": bool(auc_ok), "portfolio_ok": bool(port_ok)}
        if auc_ok and port_ok:
            ok.append(k)
    pick = max(ok, key=lambda k: res[k]["w20_calmar"] or 0) if ok else None
    out["pick"] = pick
    say(f"\n判定（事先规则）：{('采用 ' + pick + '，用于交易') if pick else '不用于交易，只在日报展示（当前值 + 同档位的历史频率）'}")
    for k, c in out["checks"].items():
        say(f"- {k}：AUC 条件 {'满足' if c['auc_ok'] else '不满足'}；组合条件 {'满足' if c['portfolio_ok'] else '不满足'}")
    say(f"\n（耗时 {time.time() - t0:.0f}s）")
    fp = paths.out_dir() / "threat_index_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    (paths.home() / "threat_index.json").write_text(json.dumps(
        {"generated": str(pd.Timestamp.today().date()), "pick": pick, "on": ON, "off": OFF,
         "event": "之后 60 个交易日内最低收盘比当天跌 ≥10%", "eval_from": str(EVAL0.date()),
         **{m: {"auc_h1": out[m]["eval"]["auc_h1"], "auc_h2": out[m]["eval"]["auc_h2"], "base_rate": out[m]["eval"]["base_rate"],
                "deciles": out[m]["eval"]["deciles"],
                "episodes_hit80": [sum(e["hit80_before"] for e in out[m]["episodes"]), len(out[m]["episodes"])]}
            for m in ("US", "JP")}}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
