"""factor_combo.py — 全部因子的组合网罗（单个 / 两两 / 三个）：打分、AUC、平衡准确率、随机对照的经验 p 值、BH 校正与门槛
（scripts/factor_combo_study.py 用；2026-09-26 事先登记）。

做法（不拟合系数，防过拟合）：每个因子先换成「当时为止」的扩张百分位（0〜1），方向在发现期定（单因子 AUC < 0.5 → 反过来用 1 − 百分位），
组合分数 = 各因子（带方向）百分位的等权平均；组合里任一因子缺值 → 那一行没有分数。
显著性：随机对照 = 所有因子一起按同一个随机偏移循环错开（保留因子自身与因子之间的结构，只打乱和目标的时间关系），同一套流程（含发现期定方向）
重跑；真实组合验证期 AUC 的经验 p 值 = 对照里验证期 AUC ≥ 它的比例；再做 Benjamini–Hochberg。
"""
from __future__ import annotations

from itertools import combinations
from math import comb

import numpy as np
import pandas as pd


def n_combos(n: int, kmax: int) -> dict[int, int]:
    """{组合大小: 个数}（1〜kmax）。"""
    return {k: comb(n, k) for k in range(1, kmax + 1)}


def enumerate_combos(n: int, kmax: int) -> list[tuple[int, ...]]:
    return [c for k in range(1, kmax + 1) for c in combinations(range(n), k)]


def auc(score: np.ndarray, y: np.ndarray) -> tuple[float, int, int]:
    """ROC AUC（秩和；平局取平均秩）；只用两者都有值的行。返回 (AUC, 正例数, 负例数)；某一类为 0 → NaN。"""
    s, y = np.asarray(score, float), np.asarray(y, float)
    m = np.isfinite(s) & np.isfinite(y)
    s, y = s[m], y[m] > 0.5
    n1, n0 = int(y.sum()), int((~y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan"), n1, n0
    order = np.argsort(s, kind="mergesort")
    ss = s[order]
    new = np.r_[True, ss[1:] != ss[:-1]]                         # 平局取平均秩（向量化）
    first = np.flatnonzero(new)
    last = np.r_[first[1:] - 1, len(ss) - 1]
    ranks = np.empty(len(ss))
    ranks[order] = ((first + last) / 2 + 1)[np.cumsum(new) - 1]
    return float((ranks[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)), n1, n0


def balanced_accuracy(score: np.ndarray, y: np.ndarray, thr: float) -> float:
    """score ≥ thr 判为正例；(真正率 + 真负率) / 2。"""
    s, y = np.asarray(score, float), np.asarray(y, float)
    m = np.isfinite(s) & np.isfinite(y)
    s, y = s[m], y[m] > 0.5
    if not y.any() or y.all():
        return float("nan")
    pred = s >= thr
    return float((pred[y].mean() + (~pred[~y]).mean()) / 2)


def expanding_pct(x: pd.Series, min_n: int) -> pd.Series:
    """x_t 在 x_0..x_t（有效值）里的百分位（0〜1，含自己，平局取中）；有效值 < min_n 时 NaN。"""
    from .threat import expanding_pct as ep
    return ep(x, min_n)


def directions(P: pd.DataFrame, y: pd.Series, disc: np.ndarray) -> dict[str, int]:
    """每个因子的方向：发现期单因子 AUC ≥ 0.5 → +1，否则 −1（没有值 → +1）。"""
    out = {}
    for c in P.columns:
        a, _, _ = auc(P[c].to_numpy(float)[disc], y.to_numpy(float)[disc])
        out[c] = 1 if not np.isfinite(a) or a >= 0.5 else -1
    return out


def signed(P: pd.DataFrame, sign: dict[str, int]) -> np.ndarray:
    """带方向的百分位矩阵（−1 的因子用 1 − 百分位）。"""
    A = P.to_numpy(float).copy()
    for j, c in enumerate(P.columns):
        if sign.get(c, 1) < 0:
            A[:, j] = 1 - A[:, j]
    return A


def combo_score(A: np.ndarray, combo: tuple[int, ...]) -> np.ndarray:
    """等权平均；任一因子缺值 → NaN。"""
    return A[:, list(combo)].mean(axis=1)


def ba_threshold(sd: np.ndarray, yd: np.ndarray, min_class: int = 20) -> float:
    """平衡准确率判「正」的门槛 = 发现期分数在「1 − 发现期正例比例」处的分位（判为正的比例 ≈ 发现期的正例比例）；样本太少 → NaN。"""
    sd, yd = np.asarray(sd, float), np.asarray(yd, float)
    ok = np.isfinite(sd) & np.isfinite(yd)
    base = float(yd[np.isfinite(yd)].mean()) if np.isfinite(yd).any() else float("nan")
    if ok.sum() < 2 * min_class or not 0 < base < 1:
        return float("nan")
    return float(np.quantile(sd[ok], 1 - base))


def search(A: np.ndarray, y: np.ndarray, masks: dict[str, np.ndarray], combos: list[tuple[int, ...]],
           min_class: int = 20) -> pd.DataFrame:
    """每个组合在各时段（masks 的键，例 disc / val）的 AUC 与正负例数（任一类 < min_class → AUC 记 NaN）；平衡准确率见 ba_threshold。"""
    rows = []
    yd = y[masks["disc"]]
    for c in combos:
        s = combo_score(A, c)
        r = {"combo": c, "k": len(c)}
        thr = ba_threshold(s[masks["disc"]], yd, min_class)
        for key, m in masks.items():
            a, n1, n0 = auc(s[m], y[m])
            r[f"{key}_auc"] = a if n1 >= min_class and n0 >= min_class else float("nan")
            r[f"{key}_n1"], r[f"{key}_n0"] = n1, n0
            r[f"{key}_ba"] = balanced_accuracy(s[m], y[m], thr) if np.isfinite(thr) else float("nan")
        rows.append(r)
    return pd.DataFrame(rows)


def empirical_p(obs: np.ndarray, null: np.ndarray) -> np.ndarray:
    """单侧经验 p：(1 + 对照里 ≥ 观察值的个数) / (1 + 对照个数)；观察值缺 → 1。"""
    nul = np.sort(np.asarray(null, float)[np.isfinite(null)])
    obs = np.asarray(obs, float)
    ge = len(nul) - np.searchsorted(nul, obs, side="left")
    p = (1 + ge) / (1 + len(nul))
    return np.where(np.isfinite(obs), p, 1.0)


def bh(p: np.ndarray, q: float) -> np.ndarray:
    """Benjamini–Hochberg：返回每个假设是否被拒绝（显著）。"""
    p = np.asarray(p, float)
    n = len(p)
    if n == 0:
        return np.zeros(0, bool)
    order = np.argsort(p)
    thr = q * np.arange(1, n + 1) / n
    passed = p[order] <= thr
    k = np.max(np.nonzero(passed)[0]) + 1 if passed.any() else 0
    out = np.zeros(n, bool)
    out[order[:k]] = True
    return out


def shift_rows(A: np.ndarray, k: int) -> np.ndarray:
    """所有列一起循环错开 k 行（随机对照：保留因子自身与因子之间的结构，只打乱与目标的时间关系）。"""
    return np.roll(A, k, axis=0)


def purge_mask(dates: pd.DatetimeIndex, start: str, end: str, horizon_end: pd.DatetimeIndex | None = None) -> np.ndarray:
    """时段 [start, end] 的样本，且（给了 horizon_end 时）结果窗口的结束日也 ≤ end（不偷看下一个时段）。"""
    d = pd.DatetimeIndex(dates)
    m = (d >= pd.Timestamp(start)) & (d <= pd.Timestamp(end))
    if horizon_end is not None:
        m &= pd.DatetimeIndex(horizon_end) <= pd.Timestamp(end)
    return np.asarray(m)


def gate_stats(R: pd.DataFrame, bench_val: float, margin: float, min_auc: float | None, ba_min: float | None,
               q: float, p_col: str = "p") -> pd.DataFrame:
    """G1 BH 显著、G2 两个半段同号（发现期与验证期 AUC 都 > 0.5）、G3 比现行好 ≥ 幅度（验证期 AUC ≥ max(现行 + 幅度, 下限)、平衡准确率 ≥ 下限）。"""
    R = R.copy()
    R["g1"] = bh(R[p_col].to_numpy(float), q)
    R["g2"] = (R["disc_auc"] > 0.5) & (R["val_auc"] > 0.5)
    need = max(bench_val + margin, min_auc if min_auc is not None else -1)
    g3 = R["val_auc"] >= need
    if ba_min is not None:
        g3 &= R["val_ba"] >= ba_min
    R["g3"] = g3
    R["g123"] = R["g1"] & R["g2"] & R["g3"]
    return R
