"""perf_attrib.py — 现行策略为什么在不同年份 / 月 / 周表现不一样（只描述，不改任何规则；2026-09-27）。

用户：「调查现在使用模型为什么在各个年段表现都不一样，精确到月、周来分析对应的影响因素」。

方法：同一套 S0C2（var/sim.json，现行参数含 W2）跑两次 —— 现行，与「只有核心」（个股一笔不买，闲置资金全部 1655，同一套牛熊择时）。
  个股层的贡献（超额）= 现行的收益 − 只有核心的收益（每月 / 每周，pp）；账户总收益 = 核心 + 这个超额。
  E = 2006-10〜2016-09（yfinance 今天的日経225），J = 2017-01〜2026-09（J-Quants 今天的日経225，真实一手）；两个年代分开看，
  两个年代方向一致的才算「稳定的影响因素」。
因素（按月 / 周算。「当期」= 同一个月 / 周里发生的，用来解释「为什么」；「期初」= 月 / 周开始前一天收盘就知道的，看能不能事先判断）：
  市场：日経225 当期涨跌、期初离 200 日线、期初 20 天波动（年化）；S&P500（日元计 = 核心的来源）当期涨跌、USD/JPY 当期变化；
  个股之间：期初站上 50 日线的比例（宽度）、当期个股收益的横截面标准差（分化）、当期「等权 − 指数」（少数权重股主导 → 负）、
    当期动量风格（期初过去 12-1 个月涨得最多的 1/5 − 最少的 1/5）；
  信号：当期突破信号数（不加 W2）、W2 保留的比例、当期开始的独立交易（W2 保留）每笔净收益；个股仓位的平均占比；
  宏观：美 10 年、日本 10 年利率当期变化（pp）、WTI 当期涨跌、期初 VIX；牛熊：期初日本 / 美国是不是熊市；日历：决算月（2 / 5 / 8 / 11 月）。
输出：var/out/perf_attrib.md / .json（只有统计）。
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import candle_data as CD                                                     # noqa: E402
import candle_portfolio as CP                                                # noqa: E402
import candle_posthoc as CPH                                                 # noqa: E402
import candle_study as CS_                                                   # noqa: E402
import jq_study as JS                                                        # noqa: E402
import pit_retrain_study as PRS                                              # noqa: E402
from qbreak import paths                                                     # noqa: E402

ERAS = {"E": ("2006-10-02", "2016-09-30"), "J": ("2017-01-04", "2026-09-30")}
FACTORS = {  # 键: (说明, 类型)  类型：cur = 当期、pre = 期初
    "n225": ("日経225 当期涨跌 %", "cur"), "spx_jpy": ("S&P500（日元计）当期涨跌 %", "cur"), "usdjpy": ("USD/JPY 当期变化 %", "cur"),
    "disp": ("个股收益横截面标准差（分化）%", "cur"), "ew_idx": ("等权 − 日経225 指数 pp", "cur"), "mom": ("动量风格（强 1/5 − 弱 1/5）pp", "cur"),
    "n_sig": ("突破信号数（不加 W2）", "cur"), "w2_frac": ("W2 保留的比例 %", "cur"), "trade_net": ("当期开始的交易每笔净收益 %", "cur"),
    "expo": ("个股仓位平均占比 %", "cur"), "us10y": ("美 10 年利率变化 pp", "cur"), "jgb10y": ("日本 10 年利率变化 pp", "cur"),
    "wti": ("WTI 当期涨跌 %", "cur"), "trend": ("期初日経225 离 200 日线 %", "pre"), "vol20": ("期初日経225 20 天波动（年化）%", "pre"),
    "breadth": ("期初站上 50 日线的比例 %", "pre"), "vix": ("期初 VIX", "pre"), "bear_jp": ("期初日本熊市（1 = 是）", "pre"),
    "bear_us": ("期初美国熊市（1 = 是）", "pre"), "earn": ("决算月（2 / 5 / 8 / 11 月 = 1）", "pre"),
    "mom_pre": ("上一期的动量风格 pp", "pre"), "disp_pre": ("上一期的分化 %", "pre"), "n_sig_pre": ("上一期的突破信号数", "pre"),
    "ex_pre": ("上一期的个股层超额 pp", "pre"),
}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ── 小工具（有测试）──
def period_ends(idx: pd.DatetimeIndex, freq: str) -> pd.DatetimeIndex:
    """交易日 → 每个月 / 周（周五结束）最后一个交易日。"""
    s = pd.Series(idx, index=idx)
    key = idx.to_period("M" if freq == "M" else "W-FRI")
    return pd.DatetimeIndex(s.groupby(key).last().to_numpy())


def period_change(x: pd.Series, ends: pd.DatetimeIndex, how: str = "pct") -> pd.Series:
    """期末值相对上一期末：pct = 涨跌 %；diff = 差。第一期 = 缺值。"""
    v = x.reindex(ends)
    out = (v / v.shift(1) - 1) * 100 if how == "pct" else v - v.shift(1)
    return out


def at_prev_end(x: pd.Series, ends: pd.DatetimeIndex) -> pd.Series:
    """期初 = 上一期末的值（第一期 = 缺值）；index = 本期末。"""
    return pd.Series(x.reindex(ends).shift(1).to_numpy(), index=ends)


def stock_exposure(trades: pd.DataFrame, closes: pd.DataFrame, equity: pd.Series) -> pd.Series:
    """每天个股仓位 ÷ 账户权益（按成交记录重建：买入日（含）到卖出日（不含）按收盘价计值）。核心 ETF 不算。"""
    val = pd.Series(0.0, index=equity.index)
    if trades is None or not len(trades):
        return val
    for r in trades.itertuples(index=False):
        t = r.ticker
        if t not in closes.columns:
            continue
        a, b = pd.Timestamp(r.entry_date), pd.Timestamp(r.exit_date)
        m = (val.index >= a) & (val.index < b)
        c = closes[t].reindex(val.index[m]).ffill()
        val.iloc[np.flatnonzero(m)] += (c * float(r.shares)).fillna(0.0).to_numpy()
    return (val / equity).clip(lower=0) * 100


def spearman(a: pd.Series, b: pd.Series) -> tuple[float, int]:
    a, b = pd.to_numeric(a, errors="coerce").astype(float), pd.to_numeric(b, errors="coerce").astype(float)
    ok = a.notna() & b.notna()
    if ok.sum() < 12 or a[ok].nunique() < 2 or b[ok].nunique() < 2:
        return float("nan"), int(ok.sum())
    return float(a[ok].rank().corr(b[ok].rank())), int(ok.sum())


def ols_r2(y: pd.Series, X: pd.DataFrame) -> tuple[float, dict]:
    """标准化后的 OLS：R² 与各因素的系数 / t 值（缺值的月份去掉）。"""
    d = pd.concat([y.rename("y"), X], axis=1).apply(pd.to_numeric, errors="coerce").astype(float).dropna()
    if len(d) < X.shape[1] + 10:
        return float("nan"), {}
    Z = (d - d.mean()) / d.std(ddof=0).replace(0, np.nan)
    Z = Z.dropna(axis=1)
    cols = [c for c in Z.columns if c != "y"]
    A = np.c_[np.ones(len(Z)), Z[cols].to_numpy()]
    yv = Z["y"].to_numpy()
    beta, *_ = np.linalg.lstsq(A, yv, rcond=None)
    res = yv - A @ beta
    r2 = 1 - res.var() / yv.var()
    s2 = res @ res / max(1, len(yv) - A.shape[1])
    cov = s2 * np.linalg.pinv(A.T @ A)
    se = np.sqrt(np.clip(np.diag(cov), 1e-18, None))
    return float(r2), {c: {"b": float(beta[k + 1]), "t": float(beta[k + 1] / se[k + 1])} for k, c in enumerate(cols)}


def tercile_table(y: pd.Series, x: pd.Series) -> list[dict]:
    """按 x 三等分：每组 y 的平均、为正的比例、个数。"""
    d = pd.concat([y.rename("y"), x.rename("x")], axis=1).apply(pd.to_numeric, errors="coerce").astype(float).dropna()
    if len(d) < 15 or d["x"].nunique() < 3:
        return []
    q = d["x"].rank(pct=True)
    out = []
    for k, (lo, hi) in enumerate(((0, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 1.0001))):
        g = d[(q > lo) & (q <= hi)] if k else d[q <= hi]
        out.append({"x_lo": float(g["x"].min()), "x_hi": float(g["x"].max()), "mean": float(g["y"].mean()),
                    "pos": float((g["y"] > 0).mean() * 100), "n": int(len(g))})
    return out


# ── 数据 ──
def era_inputs(D: dict, era: str, p0, pb) -> dict:
    """某个年代：指标表（现行 = W2、不加 W2）、收盘宽表、真实一手比例、组合回测。"""
    if era == "E":
        P, days, names = D["E"], D["edays"], D["enames"]
        cols, ratio = list(range(len(names))), {}
        PRS.PitEngine.DELIST = {}
    else:
        P, days, names = D["P"], D["days"], D["names"]
        last = {names[j]: days[np.where(np.isfinite(P["C"][:, j]))[0][-1]] for j in range(len(names)) if np.isfinite(P["C"][:, j]).any()}
        PRS.PitEngine.DELIST = {t: d for t, d in last.items() if d < pd.Timestamp(PRS.WINDOW[1]) - pd.Timedelta(days=PRS.DELIST_GAP_DAYS)}
        cols = [j for j in range(len(names)) if D["mem"]["U0"][:, j].any()]
        ratio = {names[j]: pd.Series(D["ratio"][:, j], index=days) for j in cols}
    fw = CS_.frames_from(P, days, names, cols, p0, {})
    fb = CS_.frames_from(P, days, names, cols, pb, {})
    closes = pd.DataFrame({t: fw[t]["Close"] for t in fw}).reindex(days)
    a, b = ERAS[era]
    run = CP.make_runner(closes, ratio, {era: (a, None)}, end=b, start=a)
    return {"fw": fw, "fb": fb, "closes": closes, "run": run, "days": days, "start": a, "end": b}


def run_equity(run, fr: dict, p) -> tuple[pd.Series, pd.DataFrame, dict]:
    r = run(fr, p)
    eng = JS.RealLotEngine.LAST[-1]
    h = eng.st.history
    eq = pd.Series([x[1] for x in h], index=pd.to_datetime([x[0] for x in h]), name="equity")
    tr = pd.DataFrame(eng.st.trades)
    return eq, tr, r


def factor_frame(freq: str, ends: pd.DatetimeIndex, X: dict) -> pd.DataFrame:
    """所有因素 → 期末 × 因素。X：日频输入（指数、宏观、横截面）。"""
    f = pd.DataFrame(index=ends)
    f["n225"] = period_change(X["n225"], ends)
    f["spx_jpy"] = period_change(X["spx_jpy"], ends)
    f["usdjpy"] = period_change(X["fx"], ends)
    f["us10y"] = period_change(X["us10y"], ends, "diff")
    f["jgb10y"] = period_change(X["jgb10y"], ends, "diff")
    f["wti"] = period_change(X["wti"], ends)
    C = X["C"]                                                              # 全部历史（期初的指标要用到开始之前的日子）
    Cp = C.reindex(ends)
    pr = (Cp / Cp.shift(1) - 1) * 100                                      # 每只票当期涨跌 %
    f["disp"] = pr.std(axis=1)
    f["ew_idx"] = pr.mean(axis=1) - f["n225"]
    past = C.shift(21) / C.shift(252) - 1                                   # 12-1 个月
    mom = []
    for k, e in enumerate(ends):
        if k == 0:
            mom.append(np.nan)
            continue
        s = past.loc[ends[k - 1]].dropna()
        r = pr.loc[e].reindex(s.index).dropna()
        s = s.reindex(r.index)
        if len(s) < 25:
            mom.append(np.nan)
            continue
        q = s.rank(pct=True)
        mom.append(float(r[q > 0.8].mean() - r[q <= 0.2].mean()))
    f["mom"] = mom
    N = X["n225_full"]
    f["trend"] = at_prev_end((N / N.rolling(200).mean() - 1) * 100, ends)
    f["vol20"] = at_prev_end(np.log(N).diff().rolling(20).std() * np.sqrt(252) * 100, ends)
    f["breadth"] = at_prev_end((C > C.rolling(50, min_periods=40).mean()).where(C.notna()).mean(axis=1) * 100, ends)
    f["vix"] = at_prev_end(X["vix"], ends)
    f["bear_jp"] = at_prev_end(X["bear_jp"].astype(float), ends)
    f["bear_us"] = at_prev_end(X["bear_us"].astype(float), ends)
    f["earn"] = ends.month.isin([2, 5, 8, 11]).astype(float)
    return f.apply(pd.to_numeric, errors="coerce").astype(float)


def signal_frame(ends: pd.DatetimeIndex, fb: dict, fw: dict, T: pd.DataFrame) -> pd.DataFrame:
    """当期的突破信号数（不加 W2）、W2 保留的比例、当期开始的交易每笔净收益。"""
    edges = pd.DatetimeIndex([ends[0] - pd.Timedelta(days=40)]).append(ends)
    def count(frames):
        s = pd.Series(0.0, index=ends)
        for df in frames.values():
            d = df.index[df["entry"].to_numpy(bool)]
            k = edges.searchsorted(d, side="left") - 1
            k = k[(k >= 0) & (k < len(ends))]
            s.iloc[:] += np.bincount(k, minlength=len(ends))[:len(ends)]
        return s
    nb, nw = count(fb), count(fw)
    out = pd.DataFrame({"n_sig": nb, "w2_frac": (nw / nb.replace(0, np.nan)) * 100}, index=ends)
    if len(T):
        k = edges.searchsorted(pd.DatetimeIndex(T["sig_date"]), side="left") - 1
        g = pd.Series(T["net"].to_numpy(float)).groupby(k).mean()
        out["trade_net"] = [g.get(i, np.nan) for i in range(len(ends))]
    else:
        out["trade_net"] = np.nan
    return out


def analyse(freq: str, ex: pd.Series, F: pd.DataFrame, era: str) -> dict:
    out = {"n": int(ex.notna().sum()), "mean": float(ex.mean()), "pos": float((ex > 0).mean() * 100), "corr": {}, "terc": {}}
    for k in FACTORS:
        if k in F.columns:
            r, n = spearman(ex, F[k])
            out["corr"][k] = {"rho": r, "n": n}
    for k in ("n225", "spx_jpy", "disp", "ew_idx", "mom", "trade_net", "trend", "vol20", "breadth", "vix"):
        if k in F.columns:
            out["terc"][k] = tercile_table(ex, F[k])
    cur = [k for k, (_, t) in FACTORS.items() if t == "cur" and k in F.columns and k not in ("trade_net", "expo")]
    pre = [k for k, (_, t) in FACTORS.items() if t == "pre" and k in F.columns]
    out["r2_cur"], out["ols_cur"] = ols_r2(ex, F[cur])
    out["r2_pre"], out["ols_pre"] = ols_r2(ex, F[pre])
    out["r2_cur_trade"], _ = ols_r2(ex, F[cur + ["trade_net", "expo"]])
    return out


def main() -> int:
    from bullbear_study import SYM, load
    from dataclasses import replace
    from qbreak import factors as FX
    from qbreak.bullbear import BEAR, Detector, load_config
    from qbreak.trader import load_params
    t0 = time.time()
    p0 = load_params(market="JP")
    pb = replace(p0, min_weekly_vol_ratio=0.0)
    D = CD.load()
    n225 = load(*SYM["JP"])["Close"]
    spx = load(*SYM["US"])["Close"]
    fxs = load("JPY=X", "2000-01-01")["Close"]
    fxs = fxs[(fxs > 60) & (fxs < 250)]
    L = FX.macro_levels()
    det = load_config()["detector"]
    det = Detector(det["kind"], det["params"])
    bear = {"JP": pd.Series(np.asarray(det.states(n225)) == BEAR, index=n225.index),
            "US": pd.Series(np.asarray(det.states(spx)) == BEAR, index=spx.index)}
    res: dict = {}
    say("# 现行策略为什么在不同年份 / 月 / 周表现不一样（只描述，2026-09-27）")
    say("方法见 scripts/perf_attrib.py 开头。「超额」= 现行 − 只有核心（1655）的收益，单位 pp；为正 = 个股层这个月 / 周帮了忙。")
    for era in ("E", "J"):
        I = era_inputs(D, era, p0, pb)
        eq, tr, r_cur = run_equity(I["run"], I["fw"], p0)
        none = {t: df.assign(entry=False) for t, df in I["fw"].items()}
        eq0, _, r_core = run_equity(I["run"], none, p0)
        idx = eq.index
        a, b = pd.Timestamp(I["start"]), pd.Timestamp(I["end"])
        idx = idx[(idx >= a) & (idx <= b) & idx.isin(I["closes"].index)]       # 只用日本的交易日（引擎日历里还有美股的日子）
        eq, eq0 = eq.reindex(idx), eq0.reindex(idx)
        expo = stock_exposure(tr[tr["ticker"] != "1655.T"] if len(tr) else tr, I["closes"], eq)
        T = CPH.trades(I["fw"], p0, I["start"])
        T = T[(T["sig_date"] >= a) & (T["sig_date"] <= b)] if len(T) else T
        ff = lambda s: s.reindex(idx.union(s.index)).ffill().reindex(idx)                      # noqa: E731
        full = I["closes"].index                                            # 这个年代全部的交易日（含开始之前的预热）
        ffa = lambda s: s.reindex(full.union(s.index)).ffill().reindex(full)                     # noqa: E731
        X = {"n225": ff(n225), "spx_jpy": ff(spx) * ff(fxs), "fx": ff(fxs), "us10y": ff(L["us10y"].dropna()),
             "jgb10y": ff(L["jgb10y"].dropna()), "wti": ff(L["wti_spot"].where(L["wti_spot"] > 0).dropna()),
             "vix": ff(L["vix"].dropna()), "bear_jp": ff(bear["JP"]).fillna(False), "bear_us": ff(bear["US"]).fillna(False),
             "C": I["closes"], "n225_full": ffa(n225)}
        res[era] = {}
        for freq in ("M", "W"):
            ends = period_ends(idx, freq)
            rc, r0 = period_change(eq, ends), period_change(eq0, ends)
            ex = (rc - r0).rename("ex")
            F = factor_frame(freq, ends, X).join(signal_frame(ends, I["fb"], I["fw"], T))
            F["expo"] = expo.groupby(expo.index.to_period("M" if freq == "M" else "W-FRI")).mean().to_numpy()[:len(ends)] \
                if len(expo) else np.nan
            F["mom_pre"], F["disp_pre"], F["n_sig_pre"], F["ex_pre"] = F["mom"].shift(1), F["disp"].shift(1), F["n_sig"].shift(1), ex.shift(1)
            A = analyse(freq, ex, F, era)
            A["cur_ret"], A["core_ret"] = rc.to_dict(), r0.to_dict()
            yr = pd.DataFrame({"cur": rc, "core": r0, "ex": ex}).dropna()
            if freq == "M":
                g = yr.groupby(yr.index.year)
                A["years"] = {int(y): {"cur": float(((1 + v["cur"] / 100).prod() - 1) * 100), "core": float(((1 + v["core"] / 100).prod() - 1) * 100),
                                       "ex_sum": float(v["ex"].sum()), "pos": float((v["ex"] > 0).mean() * 100),
                                       "expo": float(F.loc[v.index, "expo"].mean()), "n_sig": float(F.loc[v.index, "n_sig"].sum()),
                                       "trade_net": float(T[pd.DatetimeIndex(T["sig_date"]).year == y]["net"].mean()) if len(T) else float("nan")}
                              for y, v in g}
                best = ex.dropna().sort_values()
                A["worst"] = [(str(d.date()), float(best[d]), {k: _r(F.loc[d, k]) for k in ("n225", "spx_jpy", "usdjpy", "disp", "ew_idx", "mom", "trade_net", "expo")})
                              for d in best.index[:8]]
                A["best"] = [(str(d.date()), float(best[d]), {k: _r(F.loc[d, k]) for k in ("n225", "spx_jpy", "usdjpy", "disp", "ew_idx", "mom", "trade_net", "expo")})
                             for d in best.index[::-1][:8]]
            res[era][freq] = A
        res[era]["calmar"] = {"cur": r_cur[era], "core": r_core[era]}
        print(f"  {era} 完成 {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    report(res)
    say(f"\n用时 {time.time() - t0:.0f}s")
    fp = paths.out_dir() / "perf_attrib"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    slim = {e: {f: {k: v for k, v in res[e][f].items() if k not in ("cur_ret", "core_ret")} for f in ("M", "W")} | {"calmar": res[e]["calmar"]}
            for e in res}
    Path(f"{fp}.json").write_text(json.dumps(slim, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


def _r(v) -> float | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, 3) if np.isfinite(v) else None


def report(res: dict) -> None:
    fa = lambda v, f="{:+.2f}": "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)   # noqa: E731
    lab = {"E": "2006-10〜2016-09", "J": "2017-01〜2026-09"}
    say("\n## 一、每一年：现行 vs 只有核心（%），个股层超额（每月超额之和，pp）")
    say("| 年 | 现行 | 只有核心 | 个股层超额（月加总） | 超额为正的月份 | 个股仓位平均占比 | 突破信号数 | 每笔净收益 |")
    say("|---|---|---|---|---|---|---|---|")
    for era in ("E", "J"):
        for y, v in res[era]["M"].get("years", {}).items():
            say(f"| {y} | {fa(v['cur'], '{:+.1f}')}% | {fa(v['core'], '{:+.1f}')}% | {fa(v['ex_sum'], '{:+.1f}')} | {v['pos']:.0f}% | "
                f"{fa(v['expo'], '{:.0f}')}% | {v['n_sig']:.0f} | {fa(v['trade_net'], '{:+.2f}')}% |")
    for era in ("E", "J"):
        c = res[era]["calmar"]
        say(f"\n{lab[era]}：现行 年化 {fa(c['cur']['cagr'], '{:.2f}')}% / 回撤 {fa(c['cur']['dd'], '{:.2f}')}% / Calmar {fa(c['cur']['calmar'], '{:.3f}')}；"
            f"只有核心 {fa(c['core']['cagr'], '{:.2f}')}% / {fa(c['core']['dd'], '{:.2f}')}% / {fa(c['core']['calmar'], '{:.3f}')}")
    for freq, name in (("M", "月"), ("W", "周")):
        say(f"\n## 二、每{name}的个股层超额和各因素的秩相关（两个年代分开；★ = 两个年代同号且 |秩相关| ≥ 0.15）")
        say(f"E：{res['E'][freq]['n']} 个{name}，平均 {fa(res['E'][freq]['mean'], '{:+.3f}')} pp，为正 {res['E'][freq]['pos']:.0f}%；"
            f"J：{res['J'][freq]['n']} 个{name}，平均 {fa(res['J'][freq]['mean'], '{:+.3f}')} pp，为正 {res['J'][freq]['pos']:.0f}%")
        say("| 因素 | 类型 | 2006〜2016 | 2017〜2026 | 稳定 |")
        say("|---|---|---|---|---|")
        for k, (desc, typ) in FACTORS.items():
            a, b = res["E"][freq]["corr"].get(k, {}), res["J"][freq]["corr"].get(k, {})
            ra, rb = a.get("rho", float("nan")), b.get("rho", float("nan"))
            star = "★" if np.isfinite(ra) and np.isfinite(rb) and ra * rb > 0 and min(abs(ra), abs(rb)) >= 0.15 else ""
            say(f"| {desc} | {'当期' if typ == 'cur' else '期初'} | {fa(ra, '{:+.2f}')} | {fa(rb, '{:+.2f}')} | {star} |")
        say(f"\n多因素（标准化 OLS）能解释的比例 R²：当期因素 E {fa(res['E'][freq]['r2_cur'], '{:.2f}')} / J {fa(res['J'][freq]['r2_cur'], '{:.2f}')}；"
            f"加上「交易本身好不好 + 仓位」E {fa(res['E'][freq]['r2_cur_trade'], '{:.2f}')} / J {fa(res['J'][freq]['r2_cur_trade'], '{:.2f}')}；"
            f"只用期初（事先知道的）E {fa(res['E'][freq]['r2_pre'], '{:.2f}')} / J {fa(res['J'][freq]['r2_pre'], '{:.2f}')}")
        for era in ("E", "J"):
            o = res[era][freq]["ols_cur"]
            top = sorted(o.items(), key=lambda kv: -abs(kv[1]["t"]))[:5]
            say(f"- {lab[era]} 当期 t 值最大的 5 个：" + "；".join(f"{FACTORS[k][0]} {v['b']:+.2f}（t {v['t']:+.1f}）" for k, v in top))
    say("\n## 三、按因素三等分：每月个股层超额的平均（pp）/ 为正的比例")
    say("| 因素 | 年代 | 低 1/3 | 中 1/3 | 高 1/3 |")
    say("|---|---|---|---|---|")
    for k in ("n225", "spx_jpy", "disp", "ew_idx", "mom", "trade_net", "trend", "vol20", "breadth", "vix"):
        for era in ("E", "J"):
            t = res[era]["M"]["terc"].get(k) or []
            if len(t) == 3:
                say(f"| {FACTORS[k][0]} | {lab[era]} | " + " | ".join(f"{fa(g['mean'], '{:+.2f}')}（{g['pos']:.0f}%，{fa(g['x_lo'], '{:.1f}')}〜{fa(g['x_hi'], '{:.1f}')}）"
                                                                   for g in t) + " |")
    for era in ("E", "J"):
        for key, title in (("worst", "最差"), ("best", "最好")):
            say(f"\n## 四、{lab[era]} 个股层{title}的 8 个月（超额 pp；当月 日経 / S&P 日元 / USD/JPY / 分化 / 等权 − 指数 / 动量风格 / 每笔 / 仓位）")
            for d, v, f in res[era]["M"][key]:
                say(f"- {d[:7]}：{v:+.2f} pp｜日経 {fa(f['n225'], '{:+.1f}')}% / S&P 日元 {fa(f['spx_jpy'], '{:+.1f}')}% / 円 {fa(f['usdjpy'], '{:+.1f}')}% / "
                    f"分化 {fa(f['disp'], '{:.1f}')}% / 等权 − 指数 {fa(f['ew_idx'], '{:+.1f}')} / 动量 {fa(f['mom'], '{:+.1f}')} / 每笔 {fa(f['trade_net'], '{:+.1f}')}% / "
                    f"仓位 {fa(f['expo'], '{:.0f}')}%")


if __name__ == "__main__":
    raise SystemExit(main())
