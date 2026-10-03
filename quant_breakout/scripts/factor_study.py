"""factor_study.py — 把美日各期限国债、政策利率、油价（现货 / 期货 / 期限结构）、汇率、信用利差、VIX、
跨资产 ETF 都加进来，能否更精确地 ①解释 ②预测 股市？（事先登记：以下规则在运行前写定，结果出来后不改）

数据：qbreak/factors.py（FRED / 財務省 / 日本銀行，免费官方源）+ yfinance（BZ=F 期货、ETF）；目标指数 ^N225 / ^GSPC。
时点对齐（只用该市场收盘时已公布的数据）：
  日本收盘时：美国数据（收益率、油价、VIX、信用利差、ETF）用前一日（美国收盘在日本开盘前）；
              日本国债（財務省）、日银利率、美元日元（纽约正午）一律滞后 1 日
  美国收盘时：美国数据当日；日本国债、美元日元当日；日银利率滞后 1 日

A 解释（描述性，不交易）：指数日收益 ~ 当日已知的各因子变动。前半（≤2008）估计，后半检验，报告 R²。
B 预测：收盘时的因子 → 未来 20 个交易日 ①对数收益 R20 ②期间最大回撤是否超过阈值 DD20（日本 −7%、美国 −5%）
  F0 现行信息：指数 200 日线乖离 / 20 日波动 / 252 日回撤 / 20·60 日动量 + 现行宏观层 4 个量（Brent、美 10Y、VIX、美元日元）
  F1 = F0 + 美日收益率曲线（3M/2Y/10Y/30Y、JGB 1Y/2Y/10Y/20Y 的水平、斜率、20·60 日变动）+ 联邦基金 / 日银利率
          + 美日 2Y/10Y 利差 + Baa 信用利差 + VIX 20 日变动
  F2 = F1 + 油价（Brent 现货、现货−期货、Brent−WTI、20/60/250 日涨跌）+ 美元日元 20/60 日涨跌
  F3 = F2 + 跨资产 ETF 20 日收益（TLT、HYG−IEF、GLD、UUP、DBC、EEM、IWM−SPY、XLU−SPY），2008 年起
  模型：特征用训练期均值 / 标准差标准化（缺失 → 0），岭回归 alpha = 训练样本数（R20），L2 逻辑回归 C = 0.05（DD20）；
        超参固定、不调参。训练标签与检验期之间隔 20 个交易日（防止重叠标签泄漏）。
  样本：F0～F2 训练 1991-01～2008-12，检验 2009-01～；F3 训练 2008-06～2016-12，检验 2017-01～。
        另做逐年扩窗 walk-forward（2001～，F3 2012～），检验点取月末（不重叠）。
  「有预测力」= 检验期 R20 的样本外 R² > 0 且 Clark-West t > 1.645；或 DD20 的 AUC ≥ 0.60 且比 F0 高 ≥ 0.03。
C 交易（只对 B 判定有预测力的市场 / 目标做）：
  核心指数择时：预测 DD20 概率 > 训练期 80 分位 → 次日起持现金（得短端利率），否则持指数；
  对照：现行牛熊分界 ma_band（var/bullbear.json）与买入持有；换仓成本单边 0.05%。
  采用条件：检验期 Calmar 比 ma_band 高 ≥ 0.1、年化不低于 ma_band 0.5pp 以上，且检验期前后两半 Calmar 都 ≥ ma_band。
  否则维持现行，因子只作日报的描述性面板。
用法：python scripts/factor_study.py → var/out/factor_study.md / .json
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
from qbreak import factors as F                                          # noqa: E402
from qbreak import paths                                                  # noqa: E402
from qbreak.bullbear import BEAR, Detector, load_config                  # noqa: E402
from qbreak.config import DataConfig                                     # noqa: E402
from qbreak.data import load_universe                                    # noqa: E402
from bullbear_study import load                                          # noqa: E402

IDX = {"JP": "^N225", "US": "^GSPC"}
DD_X = {"JP": 0.07, "US": 0.05}
H = 20
ETFS = ["TLT", "HYG", "IEF", "GLD", "UUP", "DBC", "EEM", "IWM", "SPY", "XLU"]
SPLIT = {"F0": ("1991-01-01", "2008-12-31"), "F1": ("1991-01-01", "2008-12-31"),
         "F2": ("1991-01-01", "2008-12-31"), "F3": ("2008-06-01", "2016-12-31")}
WF_START = {"F0": 2001, "F1": 2001, "F2": 2001, "F3": 2012}
OUT: dict = {}
LINES: list[str] = []


def say(s: str = "") -> None:
    print(s, flush=True)
    LINES.append(s)


# ─────────────────────────── 数据 ───────────────────────────
def asof(s: pd.Series, dates: pd.DatetimeIndex, lag_days: int) -> pd.Series:
    """s 的值从 (日期 + lag_days 个日历日) 起才可用；返回 dates 上最近一个可用值。"""
    s = s.dropna().copy()
    if s.empty:
        return pd.Series(np.nan, index=dates)
    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize() + pd.Timedelta(days=lag_days)
    s = s[~s.index.duplicated(keep="last")]
    return s.reindex(s.index.union(dates)).ffill().reindex(dates)


def load_all():
    lv = F.macro_levels()
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False, min_bars=250).validate()
    bz = load_universe(["BZ=F"], d21).get("BZ=F")
    etf = load_universe(ETFS, d21)
    idx = {m: load(IDX[m], "1985-01-01")["Close"] for m in IDX}
    return lv, (bz["Close"] if bz is not None else None), {k: v["Close"] for k, v in etf.items()}, idx


def features(m: str, lv: pd.DataFrame, bz, etf: dict, idx: dict) -> tuple[pd.DataFrame, dict]:
    c = idx[m]
    D = c.index
    us_lag, jp_lag = (1, 1) if m == "JP" else (0, 0)
    fx_lag, boj_lag = (1, 1) if m == "JP" else (0, 1)
    g = lambda k, lag: asof(lv[k], D, lag)                                   # noqa: E731
    X = pd.DataFrame(index=D)
    lr = np.log(c).diff()
    # F0：指数自身 + 现行宏观层 4 个量
    X["ma200_gap"] = c / c.rolling(200).mean() - 1
    X["vol20"] = lr.rolling(20).std() * np.sqrt(252)
    X["dd252"] = c / c.rolling(252, min_periods=60).max() - 1
    X["mom20"], X["mom60"] = c.pct_change(20), c.pct_change(60)
    brent_spot = g("brent_spot", us_lag)
    brent_fut = asof(bz, D, us_lag) if bz is not None else pd.Series(np.nan, index=D)
    X["brent"] = brent_fut.fillna(brent_spot)                               # 现行用期货；2007 年前用现货代替
    X["us10y"] = g("us10y", us_lag)
    X["vix"] = g("vix", us_lag)
    X["usdjpy"] = g("usdjpy", fx_lag)
    f0 = list(X.columns)
    # F1：收益率曲线 + 政策利率 + 利差 + 信用
    for k in ("us3m", "us2y", "us30y", "fed_funds", "baa_spread"):
        X[k] = g(k, us_lag)
    for k in ("jgb1y", "jgb2y", "jgb10y", "jgb20y"):
        X[k] = g(k, jp_lag)
    X["jp_short"] = asof(lv["boj_call"], D, boj_lag).fillna(X["jgb1y"])
    X["us_10y3m"], X["us_10y2y"], X["us_30y10y"] = X.us10y - X.us3m, X.us10y - X.us2y, X.us30y - X.us10y
    X["jgb_20y2y"], X["jgb_10y2y"] = X.jgb20y - X.jgb2y, X.jgb10y - X.jgb2y
    X["spr2y"], X["spr10y"] = X.us2y - X.jgb2y, X.us10y - X.jgb10y
    for k in ("us2y", "us10y", "jgb2y", "jgb10y", "spr2y", "spr10y"):
        X[f"d20_{k}"], X[f"d60_{k}"] = X[k].diff(20), X[k].diff(60)
    X["d60_fed"], X["d60_jpshort"] = X.fed_funds.diff(60), X.jp_short.diff(60)
    X["d20_baa"], X["d20_vix"] = X.baa_spread.diff(20), X.vix.diff(20)
    f1 = [k for k in X.columns if k not in f0]
    # F2：油价期限结构 + 汇率动量
    X["brent_spot"] = brent_spot
    X["spot_fut"] = (brent_spot - brent_fut).fillna(0.0)
    X["brent_wti"] = brent_spot - g("wti_spot", us_lag)
    for n in (20, 60, 250):
        X[f"oil{n}"] = brent_spot.pct_change(n)
    X["fx20"], X["fx60"] = X.usdjpy.pct_change(20), X.usdjpy.pct_change(60)
    f2 = [k for k in X.columns if k not in f0 + f1]
    # F3：跨资产 ETF 20 日收益（美国上市，日本侧滞后 1 日）
    er = {k: asof(v, D, us_lag).pct_change(20) for k, v in etf.items()}
    if all(k in er for k in ETFS):
        X["etf_tlt"], X["etf_gld"], X["etf_uup"] = er["TLT"], er["GLD"], er["UUP"]
        X["etf_dbc"], X["etf_eem"] = er["DBC"], er["EEM"]
        X["etf_hyg_ief"], X["etf_iwm_spy"], X["etf_xlu_spy"] = er["HYG"] - er["IEF"], er["IWM"] - er["SPY"], er["XLU"] - er["SPY"]
    f3 = [k for k in X.columns if k not in f0 + f1 + f2]
    sets = {"F0": f0, "F1": f0 + f1, "F2": f0 + f1 + f2, "F3": f0 + f1 + f2 + f3}
    return X.replace([np.inf, -np.inf], np.nan), sets


def targets(c: pd.Series, x: float) -> tuple[pd.Series, pd.Series]:
    r20 = np.log(c.shift(-H) / c)
    fut_min = pd.concat([c.shift(-k) for k in range(1, H + 1)], axis=1).min(axis=1)
    dd = (fut_min / c - 1 <= -x).astype(float)
    dd[c.shift(-H).isna()] = np.nan
    return r20, dd


# ─────────────────────────── 模型（numpy 实现）───────────────────────────
def standardize(Xtr: pd.DataFrame, Xte: pd.DataFrame):
    mu, sd = Xtr.mean(), Xtr.std().replace(0, np.nan)
    f = lambda Z: ((Z - mu) / sd).fillna(0.0).clip(-6, 6).to_numpy()         # noqa: E731
    return f(Xtr), f(Xte)


def ridge(Xtr, ytr, Xte, alpha):
    ym = ytr.mean()
    A = Xtr.T @ Xtr + alpha * np.eye(Xtr.shape[1])
    b = np.linalg.solve(A, Xtr.T @ (ytr - ym))
    return ym + Xte @ b


def logit(Xtr, ytr, Xte, C=0.05, iters=50):
    n, k = Xtr.shape
    Z = np.c_[np.ones(n), Xtr]
    w = np.zeros(k + 1)
    w[0] = math.log((ytr.mean() + 1e-6) / (1 - ytr.mean() + 1e-6))
    lam = np.r_[0.0, np.full(k, 1.0 / C)]
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Z @ w)))
        grad = Z.T @ (p - ytr) + lam * w
        Hs = (Z * (p * (1 - p))[:, None]).T @ Z + np.diag(lam)
        step = np.linalg.solve(Hs, grad)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return 1 / (1 + np.exp(-(np.c_[np.ones(len(Xte)), Xte] @ w)))


def auc(y, p):
    y, p = np.asarray(y), np.asarray(p)
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    r = pd.Series(np.r_[pos, neg]).rank().to_numpy()
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def month_ends(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(idx, index=idx)
    return pd.DatetimeIndex(s.groupby([idx.year, idx.month]).max().values)


def fit_predict(X, y, cols, tr_start, tr_end, te_idx, kind):
    """训练 [tr_start, tr_end − 20 交易日]，预测 te_idx。"""
    dates = X.index
    end_pos = dates.searchsorted(pd.Timestamp(tr_end), side="right") - H      # 防止重叠标签泄漏
    tr = dates[(dates >= pd.Timestamp(tr_start)) & (dates < dates[max(end_pos, 1)])]
    tr = tr[y.reindex(tr).notna().to_numpy() & X.loc[tr, cols].notna().sum(axis=1).gt(0).to_numpy()]
    Xtr, Xte = standardize(X.loc[tr, cols], X.loc[te_idx, cols])
    ytr = y.reindex(tr).to_numpy()
    if kind == "r":
        return ridge(Xtr, ytr, Xte, alpha=float(len(tr))), ytr
    return logit(Xtr, ytr, Xte), ytr


def evaluate(m, X, sets, r20, dd):
    res = {}
    base_hist = r20.expanding(min_periods=252).mean().shift(H)                 # 只用已实现的历史均值
    for name, cols in sets.items():
        tr0, tr1 = SPLIT[name]
        dates = X.index
        te = dates[(dates > pd.Timestamp(tr1)) & r20.reindex(dates).notna().to_numpy()]
        if name == "F3":
            ok = X[[c for c in cols if c.startswith("etf_")]].notna().all(axis=1)
            te = te[ok.reindex(te).to_numpy()]
        me = month_ends(te)
        pr, _ = fit_predict(X, r20, cols, tr0, tr1, me, "r")
        pdd, ytr = fit_predict(X, dd, cols, tr0, tr1, me, "c")
        y, yb = r20.reindex(me).to_numpy(), base_hist.reindex(me).to_numpy()
        oos_r2 = 1 - np.nansum((y - pr) ** 2) / np.nansum((y - yb) ** 2)
        fcw = (y - yb) ** 2 - ((y - pr) ** 2 - (yb - pr) ** 2)
        cw_t = np.nanmean(fcw) / (np.nanstd(fcw, ddof=1) / math.sqrt(np.isfinite(fcw).sum()))
        yd = dd.reindex(me).to_numpy()
        base_p = np.full(len(yd), np.nanmean(ytr))
        brier = np.nanmean((pdd - yd) ** 2)
        bss = 1 - brier / np.nanmean((base_p - yd) ** 2)
        # walk-forward：每年 1 月用截至上年末的数据重估
        wf_y, wf_p, wf_b, wf_d, wf_pd, wf_idx = [], [], [], [], [], []
        for yr in range(WF_START[name], te[-1].year + 1):
            blk = dates[(dates.year == yr) & r20.reindex(dates).notna().to_numpy()]
            blk = month_ends(blk)
            if name == "F3":
                blk = blk[X.loc[blk, [c for c in cols if c.startswith("etf_")]].notna().all(axis=1).to_numpy()]
            if len(blk) == 0:
                continue
            p1, _ = fit_predict(X, r20, cols, tr0, f"{yr - 1}-12-31", blk, "r")
            p2, _ = fit_predict(X, dd, cols, tr0, f"{yr - 1}-12-31", blk, "c")
            wf_y += list(r20.reindex(blk)); wf_p += list(p1); wf_b += list(base_hist.reindex(blk))
            wf_d += list(dd.reindex(blk)); wf_pd += list(p2); wf_idx += list(blk)
        wy, wp, wb = np.array(wf_y), np.array(wf_p), np.array(wf_b)
        wf_r2 = 1 - np.nansum((wy - wp) ** 2) / np.nansum((wy - wb) ** 2)
        res[name] = {"n_features": len(cols), "test_months": int(len(me)), "test_start": str(me[0].date()),
                     "oos_r2_pct": round(oos_r2 * 100, 2), "cw_t": round(float(cw_t), 2),
                     "auc": round(auc(yd, pdd), 3), "brier_skill": round(float(bss), 3),
                     "dd_base_rate": round(float(np.nanmean(yd)), 3),
                     "wf_oos_r2_pct": round(wf_r2 * 100, 2), "wf_auc": round(auc(np.array(wf_d), np.array(wf_pd)), 3),
                     "wf_months": len(wf_idx)}
    return res


# ─────────────────────────── A 解释 ───────────────────────────
def explain(m, X, idx, etf):
    c = idx[m]
    y = np.log(c).diff()
    D = c.index
    Z = pd.DataFrame(index=D)
    lag = 1 if m == "JP" else 0
    if m == "JP":
        Z["sp500_prev"] = np.log(asof(idx["US"], D, 1)).diff()               # 前一晚美股
    for k in ("us10y", "us2y", "jgb10y", "jgb2y", "baa_spread", "vix"):
        Z[f"d_{k}"] = X[k].diff()
    Z["oil"] = np.log(X["brent_spot"]).diff()
    Z["fx"] = np.log(X["usdjpy"]).diff()
    out = {}
    for label, cols in (("全部因子", list(Z.columns)), ("不含 VIX", [k for k in Z.columns if k != "d_vix"])):
        ok = y.notna() & Z[cols].notna().all(axis=1)
        tr = ok & (D <= "2008-12-31") & (D >= "1991-01-01")
        te = ok & (D > "2008-12-31")
        A = np.c_[np.ones(tr.sum()), Z.loc[tr, cols].to_numpy()]
        b = np.linalg.lstsq(A, y[tr].to_numpy(), rcond=None)[0]
        r2 = lambda msk: 1 - np.sum((y[msk].to_numpy() - np.c_[np.ones(msk.sum()), Z.loc[msk, cols].to_numpy()] @ b) ** 2) / np.sum((y[msk] - y[msk].mean()) ** 2)  # noqa: E731
        out[label] = {"in_r2": round(float(r2(tr)), 3), "out_r2": round(float(r2(te)), 3),
                      "coef": {k: round(float(v), 4) for k, v in zip(["const"] + cols, b)}}
    return out, lag


# ─────────────────────────── C 择时 ───────────────────────────
def timing(m, X, sets, dd, idx, lv, name):
    c = idx[m]
    D = c.index
    tr0, tr1 = SPLIT[name]
    te = D[D > pd.Timestamp(tr1)]
    cols = sets[name]
    # 逐年重估的每日概率（每年 1 月用截至上年末的数据）
    prob = pd.Series(np.nan, index=D)
    thr = {}
    for yr in range(te[0].year, te[-1].year + 1):
        blk = te[te.year == yr]
        if len(blk) == 0:
            continue
        p, _ = fit_predict(X, dd, cols, tr0, f"{yr - 1}-12-31", blk, "c")
        prob[blk] = p
        dates = X.index
        tr_idx = dates[(dates >= pd.Timestamp(tr0)) & (dates <= pd.Timestamp(f"{yr - 1}-12-31"))]
        tr_idx = tr_idx[dd.reindex(tr_idx).notna().to_numpy()]
        ptr, _ = fit_predict(X, dd, cols, tr0, f"{yr - 1}-12-31", tr_idx[-2520:], "c")
        thr[yr] = float(np.nanpercentile(ptr, 80))
    th = pd.Series([thr.get(d.year, np.nan) for d in D], index=D)
    pos_f = (prob <= th).astype(float).where(prob.notna())
    cfg = load_config()
    det = Detector(cfg["detector"]["kind"], cfg["detector"]["params"])
    st = pd.Series(det.states(c), index=D)
    pos_b = (st != BEAR).astype(float)
    cash = (asof(lv["us3m"], D, 0) if m == "US" else asof(lv["boj_call"], D, 1).fillna(asof(lv["jgb1y"], D, 1))) / 100 / 252
    r = c.pct_change()

    def run(pos):
        p = pos.shift(1).reindex(te).fillna(1.0)                            # 收盘决定，次日生效
        turn = p.diff().abs().fillna(0)
        ret = p * r.reindex(te) + (1 - p) * cash.reindex(te).fillna(0) - turn * 0.0005
        eq = (1 + ret.fillna(0)).cumprod()
        yrs = (te[-1] - te[0]).days / 365.25
        cagr = eq.iloc[-1] ** (1 / yrs) - 1
        mdd = float((eq / eq.cummax() - 1).min())
        return {"cagr_pct": round(float(cagr) * 100, 2), "mdd_pct": round(mdd * 100, 1),
                "calmar": round(float(cagr) / abs(mdd), 3) if mdd < 0 else None,
                "switches_per_year": round(float(turn.sum() / yrs), 2), "cash_share": round(float((1 - p).mean()), 3)}

    out = {"factor": run(pos_f), "ma_band": run(pos_b), "buy_hold": run(pd.Series(1.0, index=D))}
    mid = te[len(te) // 2]
    for half, sl in (("h1", te[te < mid]), ("h2", te[te >= mid])):
        keep = te
        for k, pos in (("factor", pos_f), ("ma_band", pos_b)):
            te_save = sl
            p = pos.shift(1).reindex(te_save).fillna(1.0)
            turn = p.diff().abs().fillna(0)
            ret = p * r.reindex(te_save) + (1 - p) * cash.reindex(te_save).fillna(0) - turn * 0.0005
            eq = (1 + ret.fillna(0)).cumprod()
            yrs = (te_save[-1] - te_save[0]).days / 365.25
            cagr = eq.iloc[-1] ** (1 / yrs) - 1
            mdd = float((eq / eq.cummax() - 1).min())
            out[f"{k}_{half}"] = {"cagr_pct": round(float(cagr) * 100, 2), "mdd_pct": round(mdd * 100, 1),
                                  "calmar": round(float(cagr) / abs(mdd), 3) if mdd < 0 else None}
        te = keep
    return out, prob, th


# ─────────────────────────── 事后稳健性探索（不用于决策）───────────────────────────
def stationary(X: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """水平值换成 3 年滚动 z 分数（只用过去数据），避免零利率时期训练、在加息期外推。"""
    Z = X[cols].copy()
    for k in cols:
        if not k.startswith(("d20_", "d60_", "mom", "oil", "fx", "etf_", "ma200", "dd252")):
            r = X[k].rolling(756, min_periods=252)
            Z[k] = (X[k] - r.mean()) / r.std()
    return Z


def explore(lv, bz, etf, idx):
    say("## 事后稳健性探索（结果出来后追加，只用来检验结论是否依赖设计，不用于决策）")
    for m in ("JP", "US"):
        X, sets = features(m, lv, bz, etf, idx)
        r20, dd = targets(idx[m], DD_X[m])
        Xs = pd.concat([stationary(X, sets["F3"])], axis=1)
        ev = evaluate(m, Xs, sets, r20, dd)
        say(f"{m} 水平值改为 3 年滚动 z 分数：" + "；".join(
            f"{k} R² {v['oos_r2_pct']}%（CW t {v['cw_t']}）AUC {v['auc']} / WF R² {v['wf_oos_r2_pct']}% AUC {v['wf_auc']}"
            for k, v in ev.items()))
        # 经典单因子规则：信号日（月末）是否提高未来 20 日大跌概率
        me = month_ends(X.index[(X.index >= "1991-01-01") & dd.reindex(X.index).notna().to_numpy()])
        rules = {"美债 10Y−3M 倒挂": X["us_10y3m"] < 0, "Baa 利差 20 日走阔 >0.3pt": X["d20_baa"] > 0.3,
                 "油价 60 日 +30%": X["oil60"] > 0.30, "VIX > 30": X["vix"] > 30,
                 "美 10Y 60 日 +0.75pt": X["d60_us10y"] > 0.75, "美元日元 20 日 −5%": X["fx20"] < -0.05,
                 "JGB10Y 60 日 +0.3pt": X["d60_jgb10y"] > 0.3, "指数跌破 200 日线": X["ma200_gap"] < 0}
        base = float(dd.reindex(me).mean())
        parts = []
        for name, cond in rules.items():
            c_ = cond.reindex(me).fillna(False)
            n_on = int(c_.sum())
            if n_on < 8:
                parts.append(f"{name} n={n_on}（样本太少）")
                continue
            h1 = me < pd.Timestamp("2009-01-01")
            p_all = float(dd.reindex(me)[c_].mean())
            p_h1 = float(dd.reindex(me[h1])[c_[h1].to_numpy()].mean()) if c_[h1].sum() else float("nan")
            p_h2 = float(dd.reindex(me[~h1])[c_[~h1].to_numpy()].mean()) if c_[~h1].sum() else float("nan")
            parts.append(f"{name} n={n_on} 大跌概率 {p_all:.0%}（1991-2008 {p_h1:.0%} / 2009- {p_h2:.0%}）")
        say(f"{m} 单因子规则（月末信号 → 未来 20 日回撤超过 {DD_X[m]:.0%}，基准 {base:.0%}）：" + "；".join(parts))
    say("")


def main() -> int:
    lv, bz, etf, idx = load_all()
    say(f"# 多因子研究（{pd.Timestamp.today().date()}）：美日国债曲线 / 政策利率 / 油价期限结构 / 汇率 / 信用 / VIX / 跨资产 ETF")
    say("")
    for m in ("JP", "US"):
        X, sets = features(m, lv, bz, etf, idx)
        r20, dd = targets(idx[m], DD_X[m])
        ex, _ = explain(m, X, idx, etf)
        say(f"## {m}（{IDX[m]}）")
        say(f"A 解释当日涨跌：全部因子 R² 样本内 {ex['全部因子']['in_r2']} / 样本外 {ex['全部因子']['out_r2']}；"
            f"不含 VIX 样本内 {ex['不含 VIX']['in_r2']} / 样本外 {ex['不含 VIX']['out_r2']}")
        ev = evaluate(m, X, sets, r20, dd)
        say("B 预测未来 20 个交易日（检验期月末点）：")
        say("| 特征集 | 特征数 | 检验起 | 月数 | R20 样本外 R² | Clark-West t | DD20 AUC | Brier 技能 | walk-forward R² | walk-forward AUC |")
        say("|---|---|---|---|---|---|---|---|---|---|")
        for k, v in ev.items():
            say(f"| {k} | {v['n_features']} | {v['test_start']} | {v['test_months']} | {v['oos_r2_pct']}% | {v['cw_t']} | "
                f"{v['auc']} | {v['brier_skill']} | {v['wf_oos_r2_pct']}% | {v['wf_auc']} |")
        base_auc = ev["F0"]["auc"]
        useful = {k: bool((v["oos_r2_pct"] > 0 and v["cw_t"] > 1.645) or
                          (v["auc"] >= 0.60 and v["auc"] >= base_auc + 0.03)) for k, v in ev.items() if k != "F0"}
        say(f"判定（事先规则）：{ {k: ('有预测力' if u else '无') for k, u in useful.items()} }")
        OUT[m] = {"explain": ex, "predict": ev, "useful": useful}
        best = [k for k in ("F3", "F2", "F1") if useful.get(k)]
        if best:
            tm, prob, th = timing(m, X, sets, dd, idx, lv, best[0])
            OUT[m]["timing"] = {"set": best[0], **tm}
            f, b = tm["factor"], tm["ma_band"]
            adopt = (f["calmar"] is not None and b["calmar"] is not None and f["calmar"] >= b["calmar"] + 0.1
                     and f["cagr_pct"] >= b["cagr_pct"] - 0.5
                     and all((tm[f"factor_{h}"]["calmar"] or -9) >= (tm[f"ma_band_{h}"]["calmar"] or -9) for h in ("h1", "h2")))
            OUT[m]["adopt_timing"] = bool(adopt)
            say(f"C 核心指数择时（{best[0]}，检验期）：因子 {f} ｜ 牛熊分界 {b} ｜ 买入持有 {tm['buy_hold']}")
            say(f"   前后两半：因子 {tm['factor_h1']} / {tm['factor_h2']}；牛熊分界 {tm['ma_band_h1']} / {tm['ma_band_h2']}")
            say(f"   采用？{'是' if adopt else '否（未达事先条件）'}")
        say("")
    explore(lv, bz, etf, idx)
    out = paths.out_dir() / "factor_study"
    Path(f"{out}.md").write_text("\n".join(LINES) + "\n", encoding="utf-8")
    Path(f"{out}.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
