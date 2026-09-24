"""beta_tilt_study.py — ①多因子概率做新仓倍数 ②个股滚动 beta 替代按板块写死的倾斜规则（事先登记，跑之前写定）

共同设定（与 regime_strategy_study 的「原规则」同口径）：
  20 年个股回测 2006-10-01～今天；宏观层按 sim.json 开关（量化因子 + 板块倾斜，事件窗口关）× 量化状态层（前一日）；
  仓位 = 现行模拟盘的个股档位：JP 4×25%（进取档的个股部分）、US 5×20%（安全档；进取档美股不做个股）；
  另报 JP 3×34%。只测个股部分（不含核心指数仓位），因为倾斜只影响个股新仓。
  子区间 2006-10～2012、2013～2019、2020～；分散版 = 10 只 × 10%。

C2 多因子「大跌概率」做新仓倍数（factor_study 的 F2 特征，逐年扩窗重估的样本外概率）：
  概率 > 训练期 80 分位 → 当天新仓 ×0（与现行倍数相乘）。
  采用条件（原规则 + 你要求的前后两段）：20 年 Calmar ≥ 现行 + 0.1，分散版 Calmar ≥ 现行，
  三个子区间至少两段 ≥ 现行，且前后两半（2006-10～2016-06 / 2016-07～）Calmar 都 ≥ 现行。

D 个股滚动 beta 倾斜（替代板块写死的规则；触发条件不变，只改「倾斜哪些票」）：
  beta：每 21 个交易日用之前 250 个交易日（不含当天）做多元回归
        个股日收益 ~ 市场（JP 1306.T / US SPY）+ 美 10Y 变动 + JGB 10Y 变动 + Brent 现货对数变动 + 美元日元对数变动；
        日本股用前一日的美国数据与汇率（美国收盘在东京开盘前），JGB 当日。数据：FRED、財務省（qbreak/factors.py）。
  T0 现行：油价高位/冲击 → OIL_LOSERS 板块 ×0～0.75；美 10Y ≥ 5% → JP 半导体+软件 / US 利率 beta 最低 1/3 ×0.5
  T1 beta 同触发：油价高位/冲击 → 油价 beta 最低 1/3 ×0.5；美 10Y ≥ 5% → 美 10Y beta 最低 1/3 ×0.5
  T2 T1 + 日本新增：JGB 10Y 60 日上升 ≥ 0.25pt → JGB beta 最低 1/3 ×0.5；
                   美元日元 20 日跌 ≥ 3%（日元急升）→ 汇率 beta 最高 1/3（弱日元受益股）×0.5（只用于 JP）
  T3 不做板块倾斜（参照）
  采用条件（原规则）：候选 = T1/T2 中 20 年 Calmar 最高且 分散版 Calmar ≥ T0、三个子区间至少两段 ≥ T0；
  比 T0 高 ≥ 0.1 才换，否则维持 T0。
用法：python scripts/beta_tilt_study.py → var/out/beta_tilt_study.md / .json
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
from qbreak import factors as FA                                           # noqa: E402
from qbreak import paths                                                    # noqa: E402
from qbreak.config import BacktestConfig, DataConfig, universe              # noqa: E402
from qbreak.data import load_universe                                       # noqa: E402
from qbreak.engine import run_backtest                                      # noqa: E402
from qbreak.macro import build_entry_mult, features_at, features_frame, load_macro_series, oil_state  # noqa: E402
from qbreak.regime import quant_regime_series                              # noqa: E402
from qbreak.strategy import IndicatorCache                                  # noqa: E402
from qbreak.trader import load_params                                       # noqa: E402
from bullbear_study import SYM, load                                        # noqa: E402
import factor_study as FS                                                   # noqa: E402

START = "2006-10-01"
SUB = [("2006-10-01", "2012-12-31"), ("2013-01-01", "2019-12-31"), ("2020-01-01", None)]
HALVES = [("2006-10-01", "2016-06-30"), ("2016-07-01", None)]
SIZES = {"JP": [(4, 0.25), (3, 0.34)], "US": [(5, 0.20)]}
CASH = {"JP": 1_000_000, "US": 10_000}
MKT = {"JP": "1306.T", "US": "SPY"}
WINDOW, EVERY, FRAC = 250, 21, 1 / 3
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


def _bt(market, cash, pct, n):
    bt = BacktestConfig.for_market(market, 21)
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions = cash, pct, n
    bt.sizing.max_position_pct = max(bt.sizing.max_position_pct, pct)
    bt.sizing.validate()
    return bt


def seg(eq: pd.Series, a, b) -> dict:
    e = eq[(eq.index >= a) & ((eq.index <= b) if b else True)]
    if len(e) < 20:
        return {}
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    cagr = (e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1
    dd = float((e / e.cummax() - 1).min())
    return {"cagr": round(float(cagr) * 100, 2), "dd": round(dd * 100, 2),
            "calmar": round(float(cagr) / abs(dd), 3) if dd < 0 else None}


# ─────────────────────────── 个股滚动 beta ───────────────────────────
def factor_changes(market: str, D: pd.DatetimeIndex, lv: pd.DataFrame, mkt: pd.Series) -> pd.DataFrame:
    us = 1 if market == "JP" else 0
    X = pd.DataFrame(index=D)
    X["mkt"] = mkt.reindex(D).pct_change(fill_method=None)
    X["us10y"] = FS.asof(lv["us10y"], D, us).diff()
    X["jgb10y"] = FS.asof(lv["jgb10y"], D, 0).diff()
    X["oil"] = np.log(FS.asof(lv["brent_spot"], D, us)).diff()
    X["fx"] = np.log(FS.asof(lv["usdjpy"], D, us)).diff()
    return X


def rolling_beta_ranks(rets: pd.DataFrame, X: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """{因子: [日期 × 票] beta 的截面百分位}，每 EVERY 天更新一次，只用更新日之前的 WINDOW 天。"""
    D, names = rets.index, list(rets.columns)
    cols = ["us10y", "jgb10y", "oil", "fx"]
    out = {c: pd.DataFrame(np.nan, index=D, columns=names) for c in cols}
    Xv, R = X[["mkt"] + cols].to_numpy(), rets.to_numpy()
    for u in range(WINDOW + 1, len(D), EVERY):
        sl = slice(u - WINDOW, u)                      # 不含当天 u
        xs, ys = Xv[sl], R[sl]
        okx = np.isfinite(xs).all(axis=1)
        betas = np.full((len(names), len(cols)), np.nan)
        full = okx[:, None] & np.isfinite(ys)
        good = full.sum(axis=0) >= int(WINDOW * 0.8)
        A = np.c_[np.ones(okx.sum()), xs[okx]]
        same = good & full[okx].all(axis=0)             # 窗口内完整的票一次解完
        if same.any():
            b = np.linalg.lstsq(A, ys[okx][:, same], rcond=None)[0]
            betas[same] = b[2:].T
        for j in np.flatnonzero(good & ~same):
            msk = full[:, j]
            Aj = np.c_[np.ones(msk.sum()), xs[msk]]
            betas[j] = np.linalg.lstsq(Aj, ys[msk, j], rcond=None)[0][2:]
        for k, c in enumerate(cols):
            s = pd.Series(betas[:, k], index=names)
            out[c].iloc[u] = s.rank(pct=True).to_numpy()
    return {c: df.ffill() for c, df in out.items()}


def beta_tilt_matrix(gidx, tickers, market, frame, lv, ranks, extra: bool) -> np.ndarray:
    """第 i 行 = gidx[i] 开盘成交的倾斜倍数，用 gidx[i-1]（信号日）收盘时已知的触发与 beta 排名。"""
    n = len(tickers)
    T = np.ones((len(gidx), n))
    rk = {c: df.reindex(index=gidx, columns=tickers).to_numpy() for c, df in ranks.items()}
    jgb = FS.asof(lv["jgb10y"], gidx, 1)
    jgb_up = (jgb - jgb.shift(60)).to_numpy() >= 0.25
    fx = FS.asof(lv["usdjpy"], gidx, 1)
    yen_up = (fx / fx.shift(20) - 1).to_numpy() <= -0.03
    for i in range(1, len(gidx)):
        f = features_at(frame, gidx[i - 1])
        row = np.ones(n)
        s = i - 1
        if oil_state(f) != "normal":
            row = np.where(rk["oil"][s] <= FRAC, np.minimum(row, 0.5), row)
        if f.us10y is not None and f.us10y >= 5.0:
            row = np.where(rk["us10y"][s] <= FRAC, np.minimum(row, 0.5), row)
        if extra and market == "JP":
            if jgb_up[s]:
                row = np.where(rk["jgb10y"][s] <= FRAC, np.minimum(row, 0.5), row)
            if yen_up[s]:
                row = np.where(rk["fx"][s] >= 1 - FRAC, np.minimum(row, 0.5), row)
        T[i] = row
    return T


# ─────────────────────────── C2 多因子大跌概率 ───────────────────────────
def factor_prob_mult(market, lv, bz, etf, idx, gidx) -> np.ndarray:
    X, sets = FS.features(market, lv, bz, etf, idx)
    r20, dd = FS.targets(idx[market], FS.DD_X[market])
    cols = sets["F2"]
    D = X.index
    prob = pd.Series(np.nan, index=D)
    thr = pd.Series(np.nan, index=D)
    for yr in range(2001, D[-1].year + 1):
        blk = D[D.year == yr]
        p, _ = FS.fit_predict(X, dd, cols, "1991-01-01", f"{yr - 1}-12-31", blk, "c")
        prob[blk] = p
        tr = D[(D >= "1991-01-01") & (D <= f"{yr - 1}-12-31")]
        tr = tr[dd.reindex(tr).notna().to_numpy()]
        ptr, _ = FS.fit_predict(X, dd, cols, "1991-01-01", f"{yr - 1}-12-31", tr[-2520:], "c")
        thr[blk] = float(np.nanpercentile(ptr, 80))
    hot = (prob > thr).reindex(gidx, method="ffill").fillna(False).to_numpy()
    m = np.ones(len(gidx))
    m[1:] = np.where(hot[:-1], 0.0, 1.0)              # 信号日的概率决定次日新仓
    return m


def run_variants(market, ind, p, Ms: dict, n, pct):
    rows = {}
    for name, M in Ms.items():
        full = run_backtest(ind, p, _bt(market, CASH[market], pct, n), start=START, entry_mult=M)
        div = run_backtest(ind, p, _bt(market, CASH[market] * 10, 0.10, 10), start=START, entry_mult=M)
        m = full.metrics
        row = {"cagr": m.get("cagr_pct"), "dd": m.get("max_dd_pct"), "calmar": m.get("calmar"),
               "sharpe": m.get("sharpe"), "trades": m.get("trades"), "div_calmar": div.metrics.get("calmar")}
        for k, (a, b) in enumerate(SUB):
            row[f"s{k + 1}"] = seg(full.equity, a, b).get("calmar")
        for k, (a, b) in enumerate(HALVES):
            row[f"h{k + 1}"] = seg(full.equity, a, b).get("calmar")
        rows[name] = row
    return rows


def ok_rule(r, base, halves=False) -> bool:
    subs = sum(1 for k in (1, 2, 3) if (r[f"s{k}"] or -9) >= (base[f"s{k}"] or -9))
    good = (r["div_calmar"] or -9) >= (base["div_calmar"] or -9) and subs >= 2 and (r["calmar"] or -9) >= (base["calmar"] or -9) + 0.1
    if halves:
        good = good and all((r[f"h{k}"] or -9) >= (base[f"h{k}"] or -9) for k in (1, 2))
    return bool(good)


def main() -> int:
    t0 = time.time()
    lv, bz, etf, idx = FS.load_all()
    dcfg = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    out = {}
    say(f"# 个股 beta 倾斜 + 多因子新仓倍数（{pd.Timestamp.today().date()}，20 年个股回测 {START}～）")
    for market in ("JP", "US"):
        mc = sim.get(market.lower(), {})
        flag = lambda k, d=True: mc.get(k, sim.get(k, d))                  # noqa: E731
        data = load_universe(universe(market, "broad"), dcfg)
        p = load_params(market=market)
        ind = IndicatorCache(data).all(p)
        tickers = list(ind)
        gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))
        closes = pd.DataFrame({t: df["Close"] for t, df in data.items()}).reindex(gidx)
        frame = features_frame(load_macro_series(dcfg))
        qprev = quant_regime_series(load(*SYM[market])).reindex(gidx).ffill().shift(1).fillna(1.0).values[:, None]
        M_cur, _ = build_entry_mult(gidx, tickers, market, frame, use_macro=bool(flag("use_macro")),
                                    use_sector=True, use_events=False, closes=closes)
        M_mac, _ = build_entry_mult(gidx, tickers, market, frame, use_macro=bool(flag("use_macro")),
                                    use_sector=False, use_events=False, closes=closes)
        mkt = load_universe([MKT[market]], dcfg)[MKT[market]]["Close"]
        X = factor_changes(market, gidx, lv, mkt)
        ranks = rolling_beta_ranks(closes[tickers].pct_change(fill_method=None), X)
        T1 = beta_tilt_matrix(gidx, tickers, market, frame, lv, ranks, extra=False)
        T2 = beta_tilt_matrix(gidx, tickers, market, frame, lv, ranks, extra=True)
        C2 = factor_prob_mult(market, lv, bz, etf, idx, gidx)
        Ms = {"T0 现行板块": M_cur * qprev, "T1 beta 同触发": M_mac * T1 * qprev,
              "T2 beta + JGB/汇率": M_mac * T2 * qprev, "T3 不倾斜": M_mac * qprev,
              "C2 现行 × 多因子大跌概率": M_cur * qprev * C2[:, None]}
        tilt_days = {k: int(((M < 1).any(axis=1)).sum()) for k, M in {"T1": T1, "T2": T2}.items()}
        say(f"\n## {market}（{len(tickers)} 只；beta 倾斜生效天数 T1 {tilt_days['T1']} / T2 {tilt_days['T2']}；"
            f"多因子概率拦截新仓的天数 {int((C2 == 0).sum())}；用时 {time.time() - t0:.0f}s）")
        out[market] = {}
        for n, pct in SIZES[market]:
            rows = run_variants(market, ind, p, Ms, n, pct)
            tag = f"{n}x{int(round(pct * 100))}%"
            say(f"### {tag}")
            say("| 方案 | 年化 | 回撤 | Calmar | 夏普 | 笔数 | 分散版 Calmar | 2006-12 | 2013-19 | 2020- | 前半 | 后半 |")
            say("|---|---|---|---|---|---|---|---|---|---|---|---|")
            for k, r in rows.items():
                say(f"| {k} | {r['cagr']}% | {r['dd']}% | {r['calmar']} | {r['sharpe']} | {r['trades']} | {r['div_calmar']} | "
                    f"{r['s1']} | {r['s2']} | {r['s3']} | {r['h1']} | {r['h2']} |")
            base = rows["T0 现行板块"]
            cands = [k for k in ("T1 beta 同触发", "T2 beta + JGB/汇率") if ok_rule(rows[k], base)]
            pick = max(cands, key=lambda k: rows[k]["calmar"] or -9) if cands else "T0 现行板块"
            c2 = ok_rule(rows["C2 现行 × 多因子大跌概率"], base, halves=True)
            say(f"判定：倾斜 → {pick}；多因子新仓倍数 → {'采用' if c2 else '不采用'}")
            out[market][tag] = {"rows": rows, "tilt_pick": pick, "c2_adopt": c2}
    fp = paths.out_dir() / "beta_tilt_study"
    Path(f"{fp}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{fp}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
