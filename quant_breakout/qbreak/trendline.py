"""trendline.py — 趋势线：连波谷的支撑线 + 连波峰的压力线（2026-10-06 用户：「K线上面比如画一个直线 直线上面每次都可以到波谷的那个线
再画一个线每次都可以波峰 然后预测买卖点和未来走势 结合现在的选股方法 来预测行不行」）。

操作面板（qbreak/kline.py）与研究（scripts/trendline_study.py）用同一份定义；第 t 根只用到 t 为止的 K 线（没有未来数据）：
  波谷 / 波峰（pivot）：第 p 根的最低价比前 k 根都低、不高于后 k 根 → 波谷（最高价对称 → 波峰）；要等第 p + k 根收盘才确认。
  支撑线：过两个已确认、相隔 ≥ gap 根、都在最近 L 根里的波谷的直线，从第一个波谷到 t 每根收盘都不低于「线 − 容差」（收盘跌破才算破）；
    碰到 = 波谷的最低价离线 ≤ 容差；容差 = 0.3 × ATR14（那个周期、那一根的）；最近一次碰到要在最近 R 根里（太久没碰到的线不算）。
    候选里取碰到次数最多的；一样多取 t 处更高（离现价更近）的。
  压力线：对称（连波峰；收盘不高于「线 + 容差」；一样多取 t 处更低的）。
  k / L / gap / R：日K 5 / 250 / 10 / 60、周K 3 / 156 / 6 / 26、月K 2 / 120 / 4 / 12。
  事件（都用 t − 1 时有效的那条线在 t 的值）：跌破支撑 = 收盘 < 线 − 容差；突破压力 = 收盘 > 线 + 容差；
    回踩支撑 = 最低价 ≤ 线 + 容差 且没跌破；碰压力 = 最高价 ≥ 线 − 容差 且没突破。
  通道（两条线都有时）：斜率 = 每根 %（相对 t 处的线值），|斜率| ≤ ε 算平（ε：日K 0.02、周K 0.1、月K 0.4 %/根 ≈ 每年 5%）；
    两条都向上 = 上升通道、都向下 = 下降通道、都平 = 横盘通道、支撑向上压力向下 = 对称三角、支撑向上压力平 = 上升三角、
    支撑平压力向下 = 下降三角、两条线张开（支撑向下或压力向上、另一条不收）= 扩散；
    位置 = (收盘 − 支撑) ÷ (压力 − 支撑)（0% = 在支撑线上、100% = 在压力线上）。
画线是对过去的机械描述；往后延长的线不是验证过的预测。检验（scripts/trendline_study.py，登记 2f8b450 → var/out/trendline_study.md）：
通道方向、突破 / 跌破趋势线对之后 20 日的走势都没有可用的预测力，结合现在的选股方法（B4）的 5 个做法也都不过 → 只用来看图。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

PARAMS = {"D": (5, 250, 10, 60), "W": (3, 156, 6, 26), "M": (2, 120, 4, 12)}      # (k, L, gap, R)
EPS = {"D": 0.02, "W": 0.1, "M": 0.4}                                  # 平的门槛（每根 %）
PROJ = {"D": 10, "W": 6, "M": 4}                                       # 面板往后延长几根（虚线）
TOL_ATR = 0.3
ATR_N = 14
SIDES = ("sup", "res")
CHANNELS = ("上升通道", "下降通道", "横盘通道", "对称三角", "上升三角", "下降三角", "扩散")


def atr(h, lo, c, n: int = ATR_N) -> np.ndarray:
    """真实波幅的 Wilder 平均（qbreak.strategy.atr 同一个平滑；第一根起就有值）。"""
    h, lo, c = (np.asarray(x, float) for x in (h, lo, c))
    pc = np.r_[np.nan, c[:-1]]
    tr = np.fmax(np.fmax(h - lo, np.abs(h - pc)), np.abs(lo - pc))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def pivots(x, k: int, kind: str = "low") -> np.ndarray:
    """波谷（kind = low：比前 k 根都低、不高于后 k 根）/ 波峰（high：对称）的位置（bool）；前后不满 k 根的不算。"""
    v = np.asarray(x, float)
    v = -v if kind == "high" else v
    n = len(v)
    out = np.zeros(n, bool)
    if k < 1 or n < 2 * k + 1:
        return out
    wmin = np.lib.stride_tricks.sliding_window_view(v, k).min(axis=1)    # wmin[i] = min(v[i:i+k])
    mid = v[k:n - k]
    with np.errstate(invalid="ignore"):
        out[k:n - k] = (mid < wmin[0:n - 2 * k]) & (mid <= wmin[k + 1:n - k + 1])
    return out


def _best(lo: np.ndarray, c: np.ndarray, tol: np.ndarray, P: np.ndarray, t: int, L: int, gap: int, R: int):
    """t 这一根（含）为止的最佳支撑线（在「低」的一边；压力线用取负的数组调用）→ (p1, p2, y1, 每根斜率, 碰到次数) 或 None。"""
    P = P[P >= t - L]
    m = len(P)
    if m < 2:
        return None
    ii, jj = np.triu_indices(m, 1)
    p1, p2 = P[ii], P[jj]
    keep = (p2 - p1) >= gap
    if not keep.any():
        return None
    p1, p2 = p1[keep], p2[keep]
    y1 = lo[p1]
    b = (lo[p2] - y1) / (p2 - p1)
    s = int(p1.min())
    xs = np.arange(s, t + 1)
    room = c[s:t + 1] + tol[s:t + 1]
    room = np.where(np.isfinite(room), room, np.inf)                    # 停牌等没有收盘的那根不算破
    line = y1[:, None] + b[:, None] * (xs[None, :] - p1[:, None])
    diff = np.where(xs[None, :] >= p1[:, None], room[None, :] - line, np.inf)
    ok = diff.min(axis=1) >= 0
    if not ok.any():
        return None
    p1, p2, y1, b = p1[ok], p2[ok], y1[ok], b[ok]
    yq = y1[:, None] + b[:, None] * (P[None, :] - p1[:, None])
    hit = (np.abs(lo[P][None, :] - yq) <= tol[P][None, :]) & (P[None, :] >= p1[:, None])
    fresh = np.where(hit, P[None, :], -1).max(axis=1) >= t - R          # 最近一次碰到在最近 R 根里
    if not fresh.any():
        return None
    p1, p2, y1, b, n_hit = p1[fresh], p2[fresh], y1[fresh], b[fresh], hit[fresh].sum(axis=1)
    yt = y1 + b * (t - p1)
    i = int(np.lexsort((p1, -p2, -yt, -n_hit))[0])                      # 碰到最多 → t 处最近 → 第二个锚点更近 → 第一个更早
    return int(p1[i]), int(p2[i]), float(y1[i]), float(b[i]), int(n_hit[i])


def _scan(lo, c, tol, k: int, L: int, gap: int, R: int) -> dict:
    """一边（低）逐根扫：只在有新波谷确认、线被跌破、第一个锚点超出最近 L 根、最近一次碰到超出最近 R 根时重新找线
    （其余时候最佳线不会变：别的候选只会变得不成立）。"""
    n = len(c)
    val, b_, prev = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    touch, a1, a2 = np.zeros(n, np.int16), np.full(n, -1, np.int32), np.full(n, -1, np.int32)
    brk, hit = np.zeros(n, bool), np.zeros(n, bool)
    P_all = np.flatnonzero(pivots(lo, k, "low"))
    conf = P_all + k
    ptr, cur, last = 0, None, -1
    for t in range(n):
        redo = False
        if cur is not None:
            p1, _, y1, b, _ = cur
            yt = y1 + b * (t - p1)
            prev[t] = yt
            if c[t] < yt - tol[t]:
                brk[t] = redo = True
            elif lo[t] <= yt + tol[t]:
                hit[t] = True
            if p1 < t - L or last < t - R:
                redo = True
        while ptr < len(P_all) and conf[ptr] <= t:
            ptr += 1
            redo = True
        if redo:
            cur = _best(lo, c, tol, P_all[:ptr], t, L, gap, R)
            last = -1
            if cur is not None:                                         # 这条线最近一次被碰到的波谷
                p1, _, y1, b, _ = cur
                Pc = P_all[:ptr]
                Pc = Pc[Pc >= p1]
                on = np.abs(lo[Pc] - (y1 + b * (Pc - p1))) <= tol[Pc]
                last = int(Pc[on].max()) if on.any() else p1
        if cur is not None:
            p1, p2, y1, b, nh = cur
            val[t], b_[t], touch[t], a1[t], a2[t] = y1 + b * (t - p1), b, nh, p1, p2
    return {"val": val, "b": b_, "touch": touch, "a1": a1, "a2": a2, "brk": brk, "hit": hit, "prev": prev}


def scan(df: pd.DataFrame, tf: str = "D") -> dict[str, np.ndarray]:
    """每一根 t（只用到 t 为止）的支撑线 / 压力线：sup / res（t 处的线值）、*_b（每根斜率，円）、*_slope（每根 %）、*_touch（碰到几次）、
    *_a1 / *_a2（两个锚点的位置）、*_break（跌破支撑 / 突破压力）、*_hit（回踩支撑 / 碰压力）、*_prev（t − 1 的线在 t 的值）、tol（容差）。"""
    k, L, gap, R = PARAMS[tf]
    h, lo, c = (df[x].to_numpy(float) for x in ("High", "Low", "Close"))
    tol = TOL_ATR * atr(h, lo, c)
    tol = np.where(np.isfinite(tol), tol, 0.0)
    out: dict[str, np.ndarray] = {"tol": tol}
    for side, (x, cc, sg) in {"sup": (lo, c, 1.0), "res": (-h, -c, -1.0)}.items():
        r = _scan(x, cc, tol, k, L, gap, R)
        v = r["val"] * sg
        with np.errstate(invalid="ignore", divide="ignore"):
            slope = np.where(v > 0, r["b"] * sg / v * 100, np.nan)
        out.update({side: v, f"{side}_b": r["b"] * sg, f"{side}_slope": slope, f"{side}_touch": r["touch"],
                    f"{side}_a1": r["a1"], f"{side}_a2": r["a2"], f"{side}_break": r["brk"], f"{side}_hit": r["hit"],
                    f"{side}_prev": r["prev"] * sg})
    return out


def channel(sup_slope: float, res_slope: float, tf: str = "D") -> str | None:
    """两条线的斜率（每根 %）→ 通道的名字（见模块说明）；有一条没有 → None。"""
    if sup_slope is None or res_slope is None or not (math.isfinite(sup_slope) and math.isfinite(res_slope)):
        return None
    e = EPS[tf]
    s = 1 if sup_slope > e else -1 if sup_slope < -e else 0
    r = 1 if res_slope > e else -1 if res_slope < -e else 0
    return {(1, 1): "上升通道", (-1, -1): "下降通道", (0, 0): "横盘通道", (1, -1): "对称三角", (1, 0): "上升三角",
            (0, -1): "下降三角"}.get((s, r), "扩散")


def first_events(flags, k: int) -> np.ndarray:
    """连续破线（跌破一条线后马上又跌破下一条）只留第一次：前 k 根里有同一种事件的不算。"""
    f = np.asarray(flags, bool)
    prev = pd.Series(f).shift(1, fill_value=False).rolling(k, min_periods=1).max().astype(bool).to_numpy() if k > 0 else np.zeros(len(f), bool)
    return f & ~prev


def _rd(x, nd: int = 2):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if math.isfinite(v) else None


def summary(b: pd.DataFrame, tf: str, n_show: int) -> dict | None:
    """给面板：最后一根时的两条线（锚点在最近 n_show 根里的位置，可以 < 0 = 在窗口之前）+ 往后延长 PROJ 根 + 通道 + 最近 n_show 根里的破线事件。"""
    if b is None or len(b) < 2 * PARAMS[tf][0] + 2:
        return None
    s = scan(b, tf)
    n = len(b)
    t = n - 1
    off = n - min(n, int(n_show))                                       # 窗口第一根在全部 K 线里的位置
    c = float(b["Close"].iloc[-1])
    proj = PROJ[tf]
    out: dict = {"proj": proj, "eps": EPS[tf]}
    for side in SIDES:
        v = s[side][t]
        if not math.isfinite(v):
            continue
        p1, p2, bb = int(s[f"{side}_a1"][t]), int(s[f"{side}_a2"][t]), float(s[f"{side}_b"][t])
        out[side] = {"i1": p1 - off, "y1": _rd(v + bb * (p1 - t)), "i2": p2 - off, "y2": _rd(v + bb * (p2 - t)),
                     "b": _rd(bb, 4), "now": _rd(v), "proj": _rd(v + bb * proj), "slope_pct": _rd(s[f"{side}_slope"][t], 3),
                     "touch": int(s[f"{side}_touch"][t]), "dist_pct": _rd((v / c - 1) * 100) if c > 0 else None}
    if "sup" in out and "res" in out:
        out["chan"] = channel(out["sup"]["slope_pct"], out["res"]["slope_pct"], tf)
        w = out["res"]["now"] - out["sup"]["now"]
        out["pos"] = _rd((c - out["sup"]["now"]) / w * 100, 0) if w and w > 0 else None
    k = PARAMS[tf][0]
    sb, rb = first_events(s["sup_break"], k), first_events(s["res_break"], k)
    out["ev"] = [[i - off, kd] for i in range(off, n) for kd, f in (("sb", sb), ("rb", rb)) if f[i]]
    return out


__all__ = ["PARAMS", "EPS", "PROJ", "TOL_ATR", "CHANNELS", "atr", "pivots", "scan", "channel", "first_events", "summary"]
