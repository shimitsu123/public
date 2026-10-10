"""lag_factors.py — 「错峰」：因子的影响是不是要过几天才到股价上（scripts/lag_study.py；2026-09-26 事先登记）。

Part A 外部因子 → 行业的延迟反应：因子日变化 x_f(D)（日本交易日 D 收盘时已知的水平之差；美国的量 = D 之前最后一个美国收盘，
  与 qbreak/sensitivity.factor_levels 同一口径）与之后第 L 个交易日的行业相对收益 y_s(D+L)
  （行业 = qbreak/sectors.py 的分组，成员等权日对数收益 − 全池平均，%）的相关；另看累计窗口（之后 1〜5 天、6〜20 天之和）。
Part B 错峰进买点质量分：信号的 15 个因子改用信号日之前 L 个交易日的值（L 在训练样本里逐年选）；
  行业「延迟顺风分」：用外部因子 L 天前的 5 日变化预测信号所在行业之后 10 天的相对收益（逐年估计、L 在训练期选）。
只用当时已知的数据。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import signal_score as S
from .sectors import SECTOR_JP
from .sensitivity import LOG_COLS
from .weights import auc_np

LAGS = (0, 1, 2, 3, 5, 10, 20)                   # Part B：因子值取信号日之前几个交易日
A_LAGS = (0, 1, 2, 3, 4, 5, 10, 20)              # Part A：之后第 L 个交易日
A_WINDOWS = {"1-5": (1, 5), "6-20": (6, 20)}     # Part A：之后第 a〜b 个交易日之和
TW_H, TW_W, TW_T, TW_EMB, TW_MIN = 10, 5, 2.0, 20, 500


# ═══════════ Part A ═══════════
def sector_returns(closes: pd.DataFrame, sector: dict[str, str] | None = None) -> pd.DataFrame:
    """日期 × 行业：成员等权日对数收益 − 全池平均（%）。"""
    sector = sector or {t: SECTOR_JP.get(t.split(".")[0], "other") for t in closes.columns}
    r = np.log(closes.where(closes > 0)).diff() * 100
    univ = r.mean(axis=1)
    groups: dict[str, list[str]] = {}
    for t in closes.columns:
        groups.setdefault(sector.get(t, "other"), []).append(t)
    return pd.DataFrame({s: r[m].mean(axis=1) - univ for s, m in sorted(groups.items())})


def factor_changes(lv: pd.DataFrame) -> pd.DataFrame:
    """sensitivity.factor_levels 的水平 → 日变化（对数量 ×100 = %）；去掉大盘列。"""
    ch = lv.drop(columns=[c for c in ("mkt",) if c in lv.columns]).diff()
    for c in LOG_COLS & set(ch.columns):
        ch[c] *= 100
    return ch


def ahead(y: pd.DataFrame, lag) -> pd.DataFrame:
    """之后第 lag 个交易日（int），或之后第 a〜b 个交易日之和（(a, b)）。"""
    if isinstance(lag, tuple):
        a, b = lag
        return y.rolling(b - a + 1, min_periods=b - a + 1).sum().shift(-b)
    return y.shift(-lag)


def _winsor(a: np.ndarray, q: float = 0.01) -> np.ndarray:
    lo, hi = np.nanpercentile(a, [q * 100, 100 - q * 100])
    return np.clip(a, lo, hi)


def corr_t(x: np.ndarray, y: np.ndarray) -> tuple[float, float, int]:
    """两边各在 1% / 99% 分位截尾后的相关、t 值、样本数。"""
    m = np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < 30:
        return float("nan"), float("nan"), n
    a, b = _winsor(x[m]), _winsor(y[m])
    if np.ptp(a) == 0 or np.ptp(b) == 0:
        return 0.0, 0.0, n
    r = float(np.corrcoef(a, b)[0, 1])
    t = r * math.sqrt((n - 2) / max(1e-12, 1 - r * r))
    return r, t, n


def p_two(t: float) -> float:
    return float(math.erfc(abs(t) / math.sqrt(2))) if np.isfinite(t) else float("nan")


def bh(p: np.ndarray, q: float) -> np.ndarray:
    """Benjamini–Hochberg：返回每个检验是否「发现」（缺值 = 否）。"""
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    out = np.zeros(len(p), bool)
    if not ok.any():
        return out
    idx = np.flatnonzero(ok)
    ps = p[idx]
    o = np.argsort(ps, kind="mergesort")
    m = len(ps)
    below = ps[o] <= q * (np.arange(1, m + 1) / m)
    if below.any():
        k = int(np.max(np.flatnonzero(below)))
        out[idx[o[:k + 1]]] = True
    return out


def leadlag_scan(X: pd.DataFrame, Y: pd.DataFrame, start: str) -> pd.DataFrame:
    """每个 因子 × 行业 × 错开（单日 A_LAGS + 窗口 A_WINDOWS）× 两半（按该因子有数据的日子在中位日期切开）：r、t、n、p。"""
    lagspec = [(str(L), L) for L in A_LAGS] + [(k, v) for k, v in A_WINDOWS.items()]
    fut = {name: ahead(Y, spec) for name, spec in lagspec}
    rows = []
    for f in X.columns:
        x = X[f]
        valid = x.index[(x.index >= pd.Timestamp(start)) & x.notna().to_numpy() & (x != 0).to_numpy()]
        if len(valid) < 200:
            continue
        mid = valid[len(valid) // 2]
        halves = {"H1": (valid[0], mid - pd.Timedelta(days=1)), "H2": (mid, valid[-1])}
        for h, (a, b) in halves.items():
            sel = (x.index >= a) & (x.index <= b) & x.notna().to_numpy()
            xv = x[sel].to_numpy(float)
            for name, _ in lagspec:
                Fy = fut[name][sel]
                for s in Y.columns:
                    r, t, n = corr_t(xv, Fy[s].to_numpy(float))
                    rows.append((f, s, name, h, str(a.date()), str(b.date()), r, t, n, p_two(t)))
    return pd.DataFrame(rows, columns=["factor", "sector", "lag", "half", "from", "to", "r", "t", "n", "p"])


def discoveries(scan: pd.DataFrame, q: float, pairs: set | None = None, delayed_only: bool = True) -> pd.DataFrame:
    """前半 BH 发现（q）→ 后半同号且单侧 p < 0.05 = 复现。pairs：只看这些（因子, 行业）。"""
    d = scan.pivot_table(index=["factor", "sector", "lag"], columns="half", values=["r", "t", "p", "n"]).reset_index()
    d.columns = ["_".join(c).strip("_") for c in d.columns]
    if delayed_only:
        d = d[d["lag"] != "0"]
    if pairs is not None:
        d = d[[(f, s) in pairs for f, s in zip(d["factor"], d["sector"])]]
    d = d.reset_index(drop=True)
    d["found"] = bh(d["p_H1"].to_numpy(float), q)
    d["replicated"] = d["found"] & (np.sign(d["t_H2"]) == np.sign(d["t_H1"])) & (d["p_H2"] / 2 < 0.05)
    return d


# ═══════════ Part B：错峰的信号因子 ═══════════
def lagged_rows(panel: dict[str, pd.DataFrame], ind: dict[str, pd.DataFrame], start: str | None = None,
                lags=LAGS) -> pd.DataFrame:
    """每个信号一行：date、ticker、15 个因子（当天）与各因子 k@L（信号日之前 L 个交易日的值）。"""
    R = S.signal_rows(panel, ind, start)
    cols = {}
    for L in lags:
        for k in S.ALL:
            P = panel[k].shift(L)
            cols[f"{k}@{L}"] = P.to_numpy(float)[P.index.get_indexer(R["date"]), P.columns.get_indexer(R["ticker"])]
    return pd.concat([R, pd.DataFrame(cols, index=R.index)], axis=1)


def choose_lags(train: pd.DataFrame, cols: list[str], kind: str, lags=LAGS) -> dict[str, int]:
    """每个因子在训练样本里选错开天数：等权（ew）按事先方向的 AUC 最高；逻辑回归（lr）按 |AUC − 0.5| 最大；平局取小的。"""
    y = train["win"].to_numpy(float)
    out = {}
    for k in cols:
        best, bv = 0, -np.inf
        for L in lags:
            a = auc_np(train[f"{k}@{L}"].to_numpy(float), y)
            if a is None:
                continue
            v = S.SIGN[k] * (a - 0.5) if kind == "ew" else abs(a - 0.5)
            if v > bv + 1e-12:
                best, bv = L, v
        out[k] = best
    return out


def lagged_frame(df: pd.DataFrame, choice: dict[str, int]) -> pd.DataFrame:
    out = df[[c for c in df.columns if "@" not in c]].copy()
    for k, L in choice.items():
        out[k] = df[f"{k}@{L}"].to_numpy(float)
    return out


def walk_forward_lagged(rows: pd.DataFrame, trades: pd.DataFrame, kind: str, cols: list[str], years: list[int],
                        lags=LAGS) -> tuple[pd.DataFrame, dict, dict]:
    """与 signal_score.walk_forward 相同，只是每年先在训练样本里给每个因子选错开天数。"""
    out = rows.copy()
    out["score"], out["thr"] = np.nan, np.nan
    models, choices = {}, {}
    for y in years:
        cut = pd.Timestamp(f"{y}-01-01")
        tr = trades[(trades["sig_date"] < cut) & (trades["exit_date"] < cut)]
        sel = (out["date"] >= cut) & (out["date"] < pd.Timestamp(f"{y + 1}-01-01"))
        if not len(tr) or not sel.any():
            continue
        ch = choose_lags(tr, cols, kind, lags)
        m = S.fit(kind, cols, lagged_frame(tr, ch))
        models[y], choices[y] = m, ch
        out.loc[sel, "score"] = m.score(lagged_frame(out[sel], ch))
        out.loc[sel, "thr"] = m.thr
    return out, models, choices


# ═══════════ Part B：行业延迟顺风分 ═══════════
def tailwind_fit(X: pd.DataFrame, Y: pd.DataFrame, cut_pos: int, lags=LAGS, fixed_lag: int | None = None) -> dict:
    """训练 = 位置 < cut_pos − TW_EMB 的日子（之后 TW_H 天的标签已知）。每个因子：各错开 L 的 5 日变化（标准化）对各行业之后 TW_H 天
    相对收益的斜率与 t（按重叠样本 ÷ √TW_H 修正）；L 取各行业 t² 之和最大的（fixed_lag 给出时固定）；只留 |t| ≥ TW_T 的行业 × 因子。"""
    Yf = ahead(Y, (1, TW_H)).to_numpy(float)
    end = cut_pos - TW_EMB
    model = {}
    for f in X.columns:
        best = None
        for L in ([fixed_lag] if fixed_lag is not None else lags):
            xw = X[f].rolling(TW_W, min_periods=TW_W).sum().shift(L).to_numpy(float)
            xt = xw[:max(end, 0)]
            ok = np.isfinite(xt)
            if ok.sum() < TW_MIN:
                continue
            mu, sd = float(np.mean(xt[ok])), float(np.std(xt[ok]))
            if sd <= 0:
                continue
            z = (xt - mu) / sd
            b, t = {}, {}
            for j, s in enumerate(Y.columns):
                yy = Yf[:max(end, 0), j]
                m = ok & np.isfinite(yy)
                n = int(m.sum())
                if n < TW_MIN:
                    continue
                zz, yv = z[m], yy[m]
                sxx = float(np.dot(zz - zz.mean(), zz - zz.mean()))
                if sxx <= 0:
                    continue
                bb = float(np.dot(zz - zz.mean(), yv - yv.mean()) / sxx)
                res = yv - yv.mean() - bb * (zz - zz.mean())
                se = math.sqrt(max(float(np.dot(res, res)) / (n - 2), 0) / sxx)
                b[s], t[s] = bb, (bb / se / math.sqrt(TW_H) if se > 0 else 0.0)
            score = sum(v * v for v in t.values())
            if best is None or score > best["score"] + 1e-12:
                best = {"L": int(L), "mu": mu, "sd": sd, "b": b, "t": t, "score": score}
        if best is not None:
            best["keep"] = {s: best["b"][s] for s, tv in best["t"].items() if abs(tv) >= TW_T}
            model[f] = best
    return model


def tailwind_score(model: dict, X: pd.DataFrame, sectors: list[str]) -> pd.DataFrame:
    """日期 × 行业：Σ（保留的 行业 × 因子）斜率 × 标准化的错开 5 日变化 = 预计之后 TW_H 天的行业相对收益（%）。"""
    out = pd.DataFrame(0.0, index=X.index, columns=sectors)
    for f, m in model.items():
        if not m["keep"]:
            continue
        z = ((X[f].rolling(TW_W, min_periods=TW_W).sum().shift(m["L"]) - m["mu"]) / m["sd"]).fillna(0.0)
        for s, b in m["keep"].items():
            if s in out.columns:
                out[s] += b * z
    return out


def tailwind_walk_forward(X: pd.DataFrame, Y: pd.DataFrame, years: list[int], lags=LAGS,
                          fixed_lag: int | None = None) -> tuple[pd.DataFrame, dict]:
    """每年年初用之前的日子重新估计（标签窗口已结束的），给这一年的每一天、每个行业打分；返回 (日期 × 行业, {年: 各因子的 L 与保留数})。"""
    idx = X.index
    out = pd.DataFrame(np.nan, index=idx, columns=Y.columns)
    info = {}
    for y in years:
        cut = int(idx.searchsorted(pd.Timestamp(f"{y}-01-01")))
        sel = (idx >= pd.Timestamp(f"{y}-01-01")) & (idx < pd.Timestamp(f"{y + 1}-01-01"))
        if not sel.any():
            continue
        m = tailwind_fit(X, Y, cut, lags, fixed_lag)
        out.loc[sel] = tailwind_score(m, X, list(Y.columns)).loc[sel].to_numpy()
        info[y] = {f: {"L": v["L"], "keep": len(v["keep"])} for f, v in m.items()}
    return out, info


def lookup(frame: pd.DataFrame, dates: pd.Series, tickers: pd.Series, sector: dict[str, str] | None = None) -> np.ndarray:
    """信号（日期, 票）→ 该票所在行业当天的值。"""
    sector = sector or {}
    sec = [sector.get(t, SECTOR_JP.get(t.split(".")[0], "other")) for t in tickers]
    ri = frame.index.get_indexer(pd.DatetimeIndex(dates))
    ci = frame.columns.get_indexer(sec)
    v = frame.to_numpy(float)
    return np.array([v[r, c] if r >= 0 and c >= 0 else np.nan for r, c in zip(ri, ci)])
