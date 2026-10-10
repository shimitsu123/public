"""lagscan.py — 「把因子曲线左右平移，看能不能对上股价曲线」：因子 × 个股的周变化互相关（cross-correlation），找时间差
（scripts/lagscan_study.py；2026-09-26 事先登记）。

用户的想法：因子的时间序列图上下左右平移后如果和某只股票的走势相似，就说明两者相关；左右平移（时间差）能对上 = 错峰。
写成统计：
  上下平移 / 放大缩小 —— 相关系数本来就不受影响（对 x 加常数、乘正数，相关不变），所以只需要找左右平移；
  左右平移 k 周 —— 因子第 t−k 周的变化 与 股票第 t 周的相对收益 的相关 r(k)；k > 0 = 因子领先股票 k 周（能用来预测），
    k < 0 = 股票领先因子；
  必须用「变化」而不是「水平」：两条都在涨 / 跌的曲线（水平）几乎总能对上（伪相关，spurious correlation），换一段时间就不成立；
  因子 × 股票 × 时间差 的组合有几十万个 → 光凭「最像的那个」一定会找到很像的 → 要用「发现期选、验证期检验」和「时间错开的对照」
  （把因子整条循环错开 ≥ 1 年，真实的对齐被打乱，数一数偶然能对上多少）来区分真假。
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


def weekly_last(df: pd.DataFrame) -> pd.DataFrame:
    """日数据 → 每周五（或那周最后一个有数据的日子）的值；缺的周保留缺值。"""
    return df.sort_index().resample("W-FRI").last()


def weekly_changes(levels: pd.DataFrame, pct_cols: set[str] | None = None) -> pd.DataFrame:
    """周水平 → 周变化：pct_cols 里的列（价格类，水平是对数）× 100 = %；其余（利率、利差）= 差。"""
    ch = levels.diff()
    for c in (pct_cols or set()) & set(ch.columns):
        ch[c] *= 100
    return ch


def lag_corr(F: np.ndarray, R: np.ndarray, lags) -> tuple[np.ndarray, np.ndarray]:
    """因子变化 F（周 × 因子）与股票收益 R（周 × 股票）：返回 r[k, f, s] = corr(F[t−k, f], R[t, s]) 与样本数 n[k, f, s]。
    缺值成对剔除（各自先按全段均值去中心化；近似，周数据的偏差很小）。"""
    F = np.asarray(F, float)
    R = np.asarray(R, float)
    with warnings.catch_warnings():                                            # 整列缺值的均值 = 缺值（不报警告）
        warnings.simplefilter("ignore", RuntimeWarning)
        Fc, Rc = F - np.nanmean(F, axis=0), R - np.nanmean(R, axis=0)
    Mf, Mr = np.isfinite(Fc).astype(float), np.isfinite(Rc).astype(float)
    F0, R0 = np.nan_to_num(Fc), np.nan_to_num(Rc)
    T = len(F)
    out = np.full((len(lags), F.shape[1], R.shape[1]), np.nan)
    nn = np.zeros_like(out)
    for i, k in enumerate(lags):
        if k >= 0:
            a, b = slice(0, T - k), slice(k, T)                             # F[t−k] 对 R[t]
        else:
            a, b = slice(-k, T), slice(0, T + k)
        x, y, mx, my = F0[a], R0[b], Mf[a], Mr[b]
        num = x.T @ y
        sx = (x * x).T @ my
        sy = mx.T @ (y * y)
        n = mx.T @ my
        with np.errstate(invalid="ignore", divide="ignore"):
            out[i] = np.where((sx > 0) & (sy > 0) & (n >= 30), num / np.sqrt(sx * sy), np.nan)
        nn[i] = n
    return out, nn


def t_of(r: np.ndarray, n: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return r * np.sqrt(np.maximum(n - 2, 0)) / np.sqrt(np.maximum(1e-12, 1 - r * r))


def select_leading(r: np.ndarray, n: np.ndarray, lags, t_min: float = 3.0) -> dict:
    """发现期：每个 因子 × 股票 在领先的时间差（k ≥ 1）里取 |r| 最大的 k*；|t| ≥ t_min 的记为「发现」。
    返回 {"k": k* 数组 [f, s], "r": r(k*), "t": t(k*), "found": 布尔 [f, s]}。"""
    lags = np.asarray(lags)
    lead = np.flatnonzero(lags >= 1)
    rl, nl = r[lead], n[lead]
    a = np.where(np.isfinite(rl), np.abs(rl), -1.0)
    j = a.argmax(axis=0)
    fi, si = np.indices(j.shape)
    rk, nk = rl[j, fi, si], nl[j, fi, si]
    tk = t_of(rk, nk)
    return {"k": lags[lead][j], "r": rk, "t": tk, "found": np.isfinite(tk) & (np.abs(tk) >= t_min)}


def best_any(r: np.ndarray, lags) -> np.ndarray:
    """每个 因子 × 股票 在全部时间差（含 0 与负的）里 |r| 最大的 k（画「最像时的平移量」分布用）。"""
    a = np.where(np.isfinite(r), np.abs(r), -1.0)
    return np.asarray(lags)[a.argmax(axis=0)]


def replicate(sel: dict, r_val: np.ndarray, n_val: np.ndarray, lags, t_min: float = 2.0) -> np.ndarray:
    """验证期：在发现期选出的同一个 k* 上，相关同号且 |t| ≥ t_min → 复现。返回布尔 [f, s]（没被选中的 = False）。"""
    idx = {int(k): i for i, k in enumerate(lags)}
    ki = np.vectorize(lambda k: idx[int(k)])(sel["k"])
    fi, si = np.indices(ki.shape)
    rv, nv = r_val[ki, fi, si], n_val[ki, fi, si]
    tv = t_of(rv, nv)
    return sel["found"] & np.isfinite(tv) & (np.sign(tv) == np.sign(sel["t"])) & (np.abs(tv) >= t_min)


def roll_rows(F: np.ndarray, s: int) -> np.ndarray:
    """因子整条循环错开 s 周（对照：保留因子自己的形状与自相关，打乱与股票的对齐）。"""
    return np.roll(np.asarray(F, float), s, axis=0)


def pair_score(Fw: pd.DataFrame, pairs: list[tuple[str, str, int, float]], stats: dict[str, tuple[float, float]],
               ticker: str, dates) -> np.ndarray:
    """信号日 → 这只票的「错峰预测分」= Σ 方向 × 因子标准化变化（第 w+1−k 周，w = 信号日所在的周（周五收盘为止已知））。
    pairs：[(因子, 股票, k, 方向)]（发现期选出的领先对）；stats：因子 → 发现期的 (均值, 标准差)。这只票没有对 → 缺值。"""
    mine = [(f, k, sg) for f, t, k, sg in pairs if t == ticker]
    D = pd.DatetimeIndex(dates)
    if not mine:
        return np.full(len(D), np.nan)
    fri = Fw.index.searchsorted(D, side="right") - 1                         # 信号日收盘时最后一个完整的周（周五 ≤ 信号日）
    out = np.zeros(len(D))
    for f, k, sg in mine:
        mu, sd = stats[f]
        col = Fw[f].to_numpy(float)
        w = fri + 1 - int(k)
        v = np.array([col[i] if 0 <= i < len(col) else np.nan for i in w])
        out += sg * (v - mu) / sd if sd > 0 else 0.0
    return out


def spurious_levels(L: pd.DataFrame, S: pd.DataFrame, split: pd.Timestamp) -> dict:
    """「水平」的伪相关：发现期 |r| ≥ 0.8 的 因子 × 股票（水平直接比）有多少、它们在验证期同号且 |r| ≥ 0.5 的比例。"""
    def corr(A, B):
        A = (A - A.mean()) / A.std(ddof=0)
        B = (B - B.mean()) / B.std(ddof=0)
        M = np.isfinite(A.to_numpy())[:, :, None] & np.isfinite(B.to_numpy())[:, None, :]
        a, b = np.nan_to_num(A.to_numpy()), np.nan_to_num(B.to_numpy())
        n = M.sum(axis=0)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(n >= 30, np.einsum("ti,tj->ij", a, b) / n, np.nan)
    d, v = L.index < split, L.index >= split
    r1, r2 = corr(L[d], S[d]), corr(L[v], S[v])
    hi = np.isfinite(r1) & (np.abs(r1) >= 0.8)
    keep = hi & np.isfinite(r2) & (np.sign(r2) == np.sign(r1)) & (np.abs(r2) >= 0.5)
    return {"pairs": int(np.isfinite(r1).sum()), "hi": int(hi.sum()), "hi_share": round(float(hi.mean()) * 100, 1),
            "kept": int(keep.sum()), "kept_share": round(float(keep.sum() / max(hi.sum(), 1)) * 100, 1)}
