"""adaptive.py — 「随着时间与科技的发展，行业之间的影响度会变」：同一组关系，用最近 5 年估计 vs 用全部历史估计，
哪个在之后一年（样本外）预测得更准（scripts/fund_study.py F4；2026-09-26 事先登记）。

每个样本外年份 Y、每个（来源, 被预测）对：斜率 = 之后 h 个月的相对收益 ~ 过去 w 个月的信号（普通最小二乘）
  （a）全期：Y 年以前的全部月份；（b）滚动：Y−window〜Y−1 年的月份（至少 min_obs 个月）。
Y 年各月的预测 = 斜率 × 当月信号（信号与斜率都是当时已知的；目标窗口跨到 Y+1 年的月份也照算，h 个月后才知道结果）。
每年把全部对、全部月份的预测与实际放在一起算相关系数 → 两种估计各一个数；比较各年的差。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _slope(x: np.ndarray, y: np.ndarray, min_obs: int) -> float:
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < min_obs:
        return np.nan
    xc = x[m] - x[m].mean()
    sxx = float(np.dot(xc, xc))
    return float(np.dot(xc, y[m] - y[m].mean()) / sxx) if sxx > 0 else np.nan


def compare(X: pd.DataFrame, Y: pd.DataFrame, pairs: list[tuple[str, str]], years: list[int], window: int = 5,
            min_obs: int = 36, h: int = 3) -> pd.DataFrame:
    """X：月末 × 来源（过去 w 个月的信号）；Y：月末 × 被预测（之后 h 个月的相对收益，t+1〜t+h）。
    返回每个样本外年份：全期 / 滚动 的预测与实际的相关系数、样本数。训练只用「标签已经结束」的月份（月末 + h 个月 < Y 年 1 月 1 日）。"""
    idx = X.index
    rows = []
    for yr in years:
        start = pd.Timestamp(f"{yr}-01-01")
        known = idx + pd.DateOffset(months=h) < start                    # 这些月份的之后 h 个月在 Y 年之前已经结束
        roll = known & (idx >= pd.Timestamp(f"{yr - window}-01-01"))
        test = (idx >= start) & (idx < pd.Timestamp(f"{yr + 1}-01-01"))
        if not test.any():
            continue
        pe, pr, act = [], [], []
        for s, t in pairs:
            x, y = X[s].to_numpy(float), Y[t].to_numpy(float)
            be, br = _slope(x[known], y[known], min_obs), _slope(x[roll], y[roll], min_obs)
            if not (np.isfinite(be) and np.isfinite(br)):
                continue
            xt, yt = x[test], y[test]
            m = np.isfinite(xt) & np.isfinite(yt)
            pe.append(be * xt[m])
            pr.append(br * xt[m])
            act.append(yt[m])
        if not act:
            continue
        a, e, r = np.concatenate(act), np.concatenate(pe), np.concatenate(pr)
        ce = float(np.corrcoef(e, a)[0, 1]) if e.std() > 0 else np.nan
        cr = float(np.corrcoef(r, a)[0, 1]) if r.std() > 0 else np.nan
        rows.append({"year": yr, "n": int(len(a)), "n_pairs": len(act), "corr_expanding": round(ce, 4), "corr_rolling": round(cr, 4),
                     "diff": round(cr - ce, 4)})
    return pd.DataFrame(rows)


def verdict(R: pd.DataFrame, t_min: float = 2.0, share_min: float = 2 / 3) -> dict:
    """滚动 − 全期 的年度差：平均、t（年度当作独立样本）、为正的年份比例；「滚动更准」= 平均 > 0 且 t ≥ t_min 且 ≥ share_min 的年份为正。"""
    d = R["diff"].dropna().to_numpy(float)
    if len(d) < 3:
        return {"n_years": int(len(d)), "better": False}
    t = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))) if d.std(ddof=1) > 0 else 0.0
    share = float((d > 0).mean())
    return {"n_years": int(len(d)), "mean_diff": round(float(d.mean()), 4), "t": round(t, 2), "share_pos": round(share, 3),
            "better": bool(d.mean() > 0 and t >= t_min and share >= share_min)}
