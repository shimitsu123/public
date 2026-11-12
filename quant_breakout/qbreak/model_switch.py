"""model_switch.py — 「按当前局势判断用哪个模型」第三轮的通用部分（scripts/model_switch_study.py 用；规则写在那个脚本开头）。

- 局势特征（月末）：离 200 日线、60 日实现波动、60 日效率比（趋势 / 震荡）、N 日涨跌 / 变化；到当月为止的扩张窗口标准化。
- 判断法（全部只用决定时已经知道的数据，walk-forward）：
  KNN 相似局势：现在的状态与过去「结果已知」的月份比距离，最近 k 个月的下一个月里平均最好的模型；
  HMM 隐藏局势：两态对角高斯隐马尔可夫模型（Baum–Welch 拟合，只用滤波概率 = 只用到当月为止）→ 过去同一个状态的下一个月里平均最好的模型；
  MOM 模型动量：最近 n 个「结果已知」的月份里平均最好的模型；
  TAB 趋势 × 波动表：（美日两个指数都在 200 日线上 / 一上一下 / 都在下）×（VIX 高于 / 低于到当月为止的中位数）6 格 → 过去同格最好的模型。
- 门槛：选到的模型 − 菜单等权平均（g）的平均、Newey–West t、各年代的平均；选到的 − 现行模型（h）；
  对照 = 把「选择序列」整体循环错开（≥ min_shift 个月，全部错法）→ 经验 p。
非投资建议。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


# ───────────────────────── 局势特征 ─────────────────────────
def sma_gap(close: pd.Series, n: int = 200) -> pd.Series:
    """离 n 日均线的距离（%）。"""
    return (close / close.rolling(n, min_periods=n).mean() - 1) * 100


def realized_vol(close: pd.Series, n: int = 60) -> pd.Series:
    """n 日实现波动（对数收益标准差 × √252，%）。"""
    r = np.log(close.where(close > 0)).diff()
    return r.rolling(n, min_periods=n).std() * math.sqrt(252) * 100


def efficiency_ratio(close: pd.Series, n: int = 60) -> pd.Series:
    """效率比 = |n 日涨跌| ÷ 每日涨跌绝对值之和（1 = 单边、0 = 来回震荡）。"""
    path = close.diff().abs().rolling(n, min_periods=n).sum()
    return (close - close.shift(n)).abs() / path.where(path > 0)


def month_end(daily: pd.Series, months: pd.PeriodIndex) -> pd.Series:
    """每个月最后一个有值的日子的值（索引 = 月份 Period）。"""
    s = daily.dropna()
    if not len(s):
        return pd.Series(np.nan, index=months)
    m = s.groupby(s.index.to_period("M")).last()
    return m.reindex(months)


def expanding_z(X: pd.DataFrame, min_n: int = 36) -> pd.DataFrame:
    """每列按到当月为止（含当月）的均值 / 标准差标准化；不到 min_n 个值 → NaN。"""
    mu = X.expanding(min_periods=min_n).mean()
    sd = X.expanding(min_periods=min_n).std(ddof=0)
    return (X - mu) / sd.where(sd > 0)


# ───────────────────────── 结果何时已知 ─────────────────────────
def known_outcome_months(P: pd.DataFrame, t: pd.Period, lag: int) -> list:
    """在 t 月末能用的「结果月」u：u + lag ≤ t，且那个月至少一个模型有结果。lag = 0：当月收益月末就知道；
    个股层的单笔要等卖出（最长持有 90 天）→ lag = 5。"""
    idx = P.index[(P.index <= t - lag) & P.notna().any(axis=1).to_numpy()]
    return list(idx)


def _best(mean: pd.Series) -> str | None:
    mean = mean.dropna()
    if not len(mean):
        return None
    return str(mean.index[int(np.argmax(mean.to_numpy(float)))])           # 并列取菜单里靠前的


# ───────────────────────── 判断法 ─────────────────────────
def knn_pick(Z: pd.DataFrame, P: pd.DataFrame, t: pd.Period, lag: int, k: int = 12, min_hist: int = 24) -> str | None:
    """相似局势：t 月末的状态与「状态月 s、结果月 s + 1 已知」的过去月份比欧氏距离，最近 k 个 s 的 s + 1 月里平均结果最好的模型。"""
    if t not in Z.index or Z.loc[t].isna().any():
        return None
    outs = set(known_outcome_months(P, t, lag))
    cand = [s for s in Z.index if s < t and (s + 1) in outs and not Z.loc[s].isna().any()]
    if len(cand) < min_hist:
        return None
    H = Z.loc[cand].to_numpy(float)
    d = np.sqrt(((H - Z.loc[t].to_numpy(float)) ** 2).sum(axis=1))
    near = [cand[i] for i in np.argsort(d, kind="stable")[:k]]
    return _best(P.loc[[s + 1 for s in near]].mean(axis=0, skipna=True))


def mom_pick(P: pd.DataFrame, t: pd.Period, lag: int, n: int) -> str | None:
    """模型动量：最近 n 个已知结果月里平均最好的模型。"""
    outs = known_outcome_months(P, t, lag)
    if not outs:
        return None
    return _best(P.loc[outs[-n:]].mean(axis=0, skipna=True))


def map_pick(labels: pd.Series, P: pd.DataFrame, t: pd.Period, lag: int, min_n: int = 12, default: str | None = None) -> str | None:
    """按标签学的映射（HMM 状态 / 趋势 × 波动格）：过去「标签月 s、结果月 s + 1 已知」里与 t 同标签的月份，s + 1 月平均最好的模型；
    同标签的月份 < min_n → default。"""
    if t not in labels.index or pd.isna(labels.loc[t]):
        return None
    outs = set(known_outcome_months(P, t, lag))
    same = [s for s in labels.index if s < t and (s + 1) in outs and labels.loc[s] == labels.loc[t]]
    if len(same) < min_n:
        return default
    return _best(P.loc[[s + 1 for s in same]].mean(axis=0, skipna=True))


def trend_vol_cells(spx_gap: pd.Series, n225_gap: pd.Series, vix: pd.Series, min_n: int = 36) -> pd.Series:
    """趋势 × 波动 6 格：两个指数都在 200 日线上 = up / 一上一下 = mix / 都在下 = down；VIX ≥ 到当月为止的中位数 = hi，否则 lo。"""
    med = vix.expanding(min_periods=min_n).median()
    up = (spx_gap > 0).astype(float) + (n225_gap > 0).astype(float)
    tr = up.map({2.0: "up", 1.0: "mix", 0.0: "down"})
    vo = pd.Series(np.where(vix >= med, "hi", "lo"), index=vix.index)
    ok = spx_gap.notna() & n225_gap.notna() & vix.notna() & med.notna()
    return (tr + "_" + vo).where(ok)


# ───────────────────────── 两态高斯 HMM（只用滤波概率） ─────────────────────────
def _log_emis(X: np.ndarray, mu: np.ndarray, var: np.ndarray) -> np.ndarray:
    """n × k：每个状态的对角高斯对数密度。"""
    return -0.5 * (np.log(2 * np.pi * var)[None, :, :] + (X[:, None, :] - mu[None, :, :]) ** 2 / var[None, :, :]).sum(axis=2)


def _lse(a: np.ndarray, axis: int) -> np.ndarray:
    m = np.max(a, axis=axis, keepdims=True)
    return (m + np.log(np.exp(a - m).sum(axis=axis, keepdims=True))).squeeze(axis)


def hmm_fit(X: np.ndarray, k: int = 2, iters: int = 200, tol: float = 1e-6, order_col: int = 0) -> dict:
    """Baum–Welch（对角高斯）。初值：按 order_col 的大小切成 k 段。结果按 order_col 的均值从小到大排序状态（0 = 最小）。"""
    X = np.asarray(X, float)
    n, d = X.shape
    seg = np.array_split(np.argsort(X[:, order_col], kind="stable"), k)
    mu = np.vstack([X[s].mean(axis=0) for s in seg])
    floor = np.maximum(X.var(axis=0) * 1e-3, 1e-10)
    var = np.vstack([np.maximum(X[s].var(axis=0), floor) for s in seg])
    logA = np.log(np.full((k, k), 0.1 / max(k - 1, 1)) + np.eye(k) * (0.9 - 0.1 / max(k - 1, 1)))
    logpi = np.log(np.full(k, 1.0 / k))
    prev = -np.inf
    ll = -np.inf
    for _ in range(iters):
        le = _log_emis(X, mu, var)
        la = np.empty((n, k))
        la[0] = logpi + le[0]
        for i in range(1, n):
            la[i] = le[i] + _lse(la[i - 1][:, None] + logA, axis=0)
        lb = np.zeros((n, k))
        for i in range(n - 2, -1, -1):
            lb[i] = _lse(logA + le[i + 1][None, :] + lb[i + 1][None, :], axis=1)
        ll = float(_lse(la[-1], axis=0))
        lg = la + lb - ll
        g = np.exp(lg)
        xi = np.zeros((k, k))
        for i in range(n - 1):
            xi += np.exp(la[i][:, None] + logA + le[i + 1][None, :] + lb[i + 1][None, :] - ll)
        logpi = np.log(np.maximum(g[0], 1e-300))
        A = xi / np.maximum(xi.sum(axis=1, keepdims=True), 1e-300)
        logA = np.log(np.maximum(A, 1e-300))
        w = g.sum(axis=0)
        mu = (g.T @ X) / np.maximum(w[:, None], 1e-300)
        var = np.maximum((g.T @ (X ** 2)) / np.maximum(w[:, None], 1e-300) - mu ** 2, floor)
        if ll - prev < tol:
            break
        prev = ll
    o = np.argsort(mu[:, order_col], kind="stable")
    return {"pi": np.exp(logpi)[o], "A": np.exp(logA)[np.ix_(o, o)], "mu": mu[o], "var": var[o], "ll": ll}


def hmm_filter(X: np.ndarray, prm: dict) -> np.ndarray:
    """滤波概率 P(状态_t | x_1..x_t)：第 t 行只用到 t 为止的数据。"""
    X = np.asarray(X, float)
    le = _log_emis(X, prm["mu"], prm["var"])
    logA = np.log(np.maximum(prm["A"], 1e-300))
    la = np.empty_like(le)
    la[0] = np.log(np.maximum(prm["pi"], 1e-300)) + le[0]
    for i in range(1, len(X)):
        la[i] = le[i] + _lse(la[i - 1][:, None] + logA, axis=0)
    return np.exp(la - _lse(la, axis=1)[:, None])


def hmm_labels(F: pd.DataFrame, refit_month: int = 1, min_n: int = 60, order_col: int = 0) -> pd.Series:
    """每年 refit_month 月末用到那时为止的全部月份重新拟合；之后每个月末的标签 = 用最近一次拟合的参数、只到当月的滤波概率最大的状态。
    第一次拟合要 ≥ min_n 个月。"""
    F = F.dropna()
    lab = pd.Series(np.nan, index=F.index, dtype=object)
    prm = None
    X = F.to_numpy(float)
    for i, t in enumerate(F.index):
        if (prm is None and i + 1 >= min_n) or (prm is not None and t.month == refit_month):
            prm = hmm_fit(X[: i + 1], order_col=order_col)
        if prm is not None:
            p = hmm_filter(X[: i + 1], prm)[-1]
            lab.iloc[i] = f"s{int(np.argmax(p))}"
    return lab


# ───────────────────────── 门槛 ─────────────────────────
def nw_t(x: np.ndarray, lags: int = 3) -> float | None:
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 10:
        return None
    u = x - x.mean()
    s = float(np.dot(u, u)) / n
    for L in range(1, min(lags, n - 1) + 1):
        s += 2 * (1 - L / (lags + 1)) * float(np.dot(u[L:], u[:-L])) / n
    se = math.sqrt(max(s, 0) / n)
    return round(float(x.mean() / se), 2) if se > 0 else None


def gains(picks: pd.Series, P: pd.DataFrame, base: str) -> pd.DataFrame:
    """picks：决定月 t → 用于 t + 1 月的模型。→ 每个有结果的 t：pick、r（选到的）、eq（菜单里有结果的模型的等权平均）、
    g = r − eq、h = r − 现行（base）。"""
    rows = {}
    for t, m in picks.dropna().items():
        u = t + 1
        if u not in P.index or m not in P.columns:
            continue
        row = P.loc[u]
        r = row[m]
        if not np.isfinite(r):
            continue
        eq = float(row.dropna().mean())
        hb = row.get(base, np.nan)
        rows[t] = {"pick": m, "r": float(r), "eq": eq, "g": float(r) - eq, "h": float(r) - float(hb) if np.isfinite(hb) else np.nan}
    return pd.DataFrame.from_dict(rows, orient="index")


def shift_placebo(picks: pd.Series, P: pd.DataFrame, base: str, min_shift: int = 12) -> np.ndarray:
    """全部循环错开（min_shift〜len − min_shift 个月）：选择序列整体后移，其余不动 → 每种错法的 g 平均。"""
    pk = picks.dropna()
    n = len(pk)
    vals = pk.to_numpy(object)
    out = []
    for s in range(min_shift, n - min_shift + 1):
        sh = pd.Series(np.roll(vals, s), index=pk.index)
        G = gains(sh, P, base)
        if len(G):
            out.append(float(G["g"].mean()))
    return np.array(out)


def emp_p(actual: float, placebo: np.ndarray) -> float | None:
    a = np.asarray(placebo, float)
    a = a[np.isfinite(a)]
    if not len(a) or not np.isfinite(actual):
        return None
    return float((1 + np.sum(a >= actual)) / (1 + len(a)))


def era_of(t: pd.Period, eras: dict) -> str | None:
    """eras = {名: (起始月, 结束月)}（含两端，按结果月 t + 1 归属）。"""
    u = t + 1
    for k, (a, b) in eras.items():
        if pd.Period(a, "M") <= u <= pd.Period(b, "M"):
            return k
    return None


def gate(G: pd.DataFrame, eras: dict, placebo: np.ndarray, p_max: float, t_min: float = 2.0, lags: int = 3) -> dict:
    """事先写定的四条：① g 平均 > 0 且 NW t ≥ t_min；② 各年代 g 平均都 > 0；③ h 平均 > 0；④ 错开对照的经验 p ≤ p_max。"""
    if not len(G):
        return {"n": 0, "g": None, "t": None, "eras": {k: None for k in eras}, "h": None, "p": None, "n_placebo": int(len(placebo)),
                "c": [False] * 4, "pass": False}
    g = G["g"].to_numpy(float)
    m, t = float(np.mean(g)), nw_t(g, lags)
    em = {}
    for k in eras:
        sel = [era_of(x, eras) == k for x in G.index]
        v = G.loc[sel, "g"]
        em[k] = round(float(v.mean()), 4) if len(v) else None
    h = float(np.nanmean(G["h"].to_numpy(float))) if G["h"].notna().any() else float("nan")
    p = emp_p(m, placebo)
    c = [m > 0 and (t or 0) >= t_min, all(v is not None and v > 0 for v in em.values()), bool(np.isfinite(h) and h > 0),
         p is not None and p <= p_max]
    return {"n": int(len(g)), "g": round(m, 4), "t": t, "eras": em, "h": round(h, 4) if np.isfinite(h) else None,
            "p": None if p is None else round(p, 4), "n_placebo": int(len(placebo)), "c": [bool(x) for x in c], "pass": bool(all(c))}
