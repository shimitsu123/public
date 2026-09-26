"""K 线形态（ローソク足 / candlestick patterns）：几何特征、经典形态（酒田五法与西方常用的）、情境、之后的收益（只用于评价）。
全部在「日期 × 票」的宽表上向量化。形态与情境只用当天收盘为止的数据；比例的分母用前一天的 ATR(14)（当天的 K 线不影响自己的尺度）。
scripts/candle_*.py 用（2026-09-27）。

记号：rng = 高 − 低（振幅）、ab = |收 − 开|（实体）、up = 高 − max(开, 收)（上影）、lo = min(开, 收) − 低（下影）；
body_r / up_r / lo_r = 各自 ÷ 振幅（振幅 = 0 → NaN，这一天不算任何形态）；size = 振幅 ÷ 前一天 ATR(14)。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PATTERNS = {
    # 名字: (日文 / 说明, 传统上的方向 +1 看涨 / −1 看跌 / 0 中性)
    "LUB": ("上影陽線（用户图中的形状：阳线、上影 ≥ 振幅 40%、下影 ≤ 15%、实体 ≥ 20%、振幅 ≥ ATR）", 0),
    "LUR": ("上影陰線（阴线、上影 ≥ 振幅 40%、下影 ≤ 15%、实体 ≥ 20%）", -1),
    "LLB": ("下影陽線（阳线、下影 ≥ 振幅 40%、上影 ≤ 15%、实体 ≥ 20%）", 1),
    "LLR": ("下影陰線（阴线、下影 ≥ 振幅 40%、上影 ≤ 15%、实体 ≥ 20%）", 1),
    "HAM": ("カラカサ / 锤子线（下跌中：下影 ≥ 2 倍实体、上影 ≤ 振幅 10%、实体 ≤ 35%）", 1),
    "HANG": ("首吊り線（上涨中的同一形状）", -1),
    "IHAM": ("トンカチ / 倒锤子（下跌中：上影 ≥ 2 倍实体、下影 ≤ 振幅 10%、实体 ≤ 35%）", 1),
    "STAR": ("流れ星（上涨中的同一形状）", -1),
    "DOJI": ("十字線（实体 ≤ 振幅 10%、振幅 ≥ 0.5 ATR）", 0),
    "DRAG": ("トンボ（十字線且下影 ≥ 振幅 60%）", 1),
    "GRAVE": ("塔婆（十字線且上影 ≥ 振幅 60%）", -1),
    "BIGB": ("大陽線（阳线、实体 ≥ 振幅 70%、振幅 ≥ 1.5 ATR）", 1),
    "BIGR": ("大陰線（阴线、实体 ≥ 振幅 70%、振幅 ≥ 1.5 ATR）", -1),
    "SPIN": ("コマ（实体 ≤ 30%、上下影各 ≥ 25%）", 0),
    "ENGB": ("陽の包み線（前阴今阳、今天的实体包住前一天的实体）", 1),
    "ENGR": ("陰の包み線（前阳今阴、包住）", -1),
    "HARB": ("陽のはらみ線（前一天大阴线、今天阳线实体在其实体之内）", 1),
    "HARR": ("陰のはらみ線（前一天大阳线、今天阴线实体在其实体之内）", -1),
    "PIER": ("切り込み線（前大阴；今天开在前一天最低之下、收在前一天实体中点之上）", 1),
    "DARK": ("かぶせ線（前大阳；今天开在前一天最高之上、收在前一天实体中点之下）", -1),
    "GAPU": ("窓開け上昇（今天最低 > 前一天最高）", 1),
    "GAPD": ("窓開け下落（今天最高 < 前一天最低）", -1),
    "TWB": ("毛抜き底（下跌中、两天最低几乎相同、今天阳线）", 1),
    "TWT": ("毛抜き天井（上涨中、两天最高几乎相同、今天阴线）", -1),
    "MSTAR": ("明けの明星（大阴、小实体在下、阳线收过第一天实体中点）", 1),
    "ESTAR": ("宵の明星（大阳、小实体在上、阴线收破第一天实体中点）", -1),
    "W3": ("赤三兵（三根阳线、收盘一根比一根高、每根开在前一根实体内、上影短）", 1),
    "B3": ("黒三兵 / 三羽烏（三根阴线、收盘一根比一根低、每根开在前一根实体内、下影短）", -1),
    "GAP3U": ("三空踏み上げ（连续三天向上跳空；传统：该卖）", -1),
    "GAP3D": ("三空叩き込み（连续三天向下跳空；传统：该买）", 1),
}


def sh(a: np.ndarray, k: int) -> np.ndarray:
    """往后挪 k 行（第 t 行 = 原来第 t − k 行），前面补 NaN（布尔补 False）。"""
    out = np.full_like(a, False if a.dtype == bool else np.nan)
    if k < len(a):
        out[k:] = a[:len(a) - k]
    return out


def rolling_mean(a: np.ndarray, n: int) -> np.ndarray:
    return pd.DataFrame(a).rolling(n, min_periods=n).mean().to_numpy()


def rolling_max(a: np.ndarray, n: int) -> np.ndarray:
    return pd.DataFrame(a).rolling(n, min_periods=n).max().to_numpy()


def rolling_min(a: np.ndarray, n: int) -> np.ndarray:
    return pd.DataFrame(a).rolling(n, min_periods=n).min().to_numpy()


def atr(H: np.ndarray, L: np.ndarray, C: np.ndarray, n: int = 14) -> np.ndarray:
    """Wilder ATR（与 qbreak/strategy.atr 同一口径：TR 的 ewm(alpha=1/n)）。"""
    pc = sh(C, 1)
    tr = np.fmax(H - L, np.fmax(np.abs(H - pc), np.abs(L - pc)))
    tr = np.where(np.isfinite(pc), tr, H - L)
    return pd.DataFrame(tr).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()


def panel(data: dict, days: pd.DatetimeIndex, names: list[str]) -> dict[str, np.ndarray]:
    """{票: DataFrame(Open, High, Low, Close, Volume)} → 宽表（days × names，缺 = NaN）。"""
    out = {}
    for k in ("Open", "High", "Low", "Close", "Volume"):
        out[k[0]] = pd.DataFrame({t: data[t][k] for t in names}).reindex(index=days, columns=names).to_numpy(float)
    return out


def geometry(P: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    O, H, L, C = P["O"], P["H"], P["L"], P["C"]
    rng = H - L
    ok = np.isfinite(rng) & (rng > 0) & np.isfinite(O) & np.isfinite(C)
    r = np.where(ok, rng, np.nan)
    ab = np.abs(C - O)
    up = H - np.fmax(O, C)
    lo = np.fmin(O, C) - L
    a = atr(H, L, C)
    a1 = sh(a, 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        g = {"ok": ok, "bull": ok & (C > O), "bear": ok & (C < O), "rng": r, "ab": np.where(ok, ab, np.nan),
             "up": np.where(ok, up, np.nan), "lo": np.where(ok, lo, np.nan),
             "body_r": ab / r, "up_r": up / r, "lo_r": lo / r, "atr": a, "atr1": a1, "size": r / a1,
             "gap": O / sh(C, 1) - 1, "clv": ((C - L) - (H - C)) / r}
    return g


def context(P: dict[str, np.ndarray], g: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """情境（都是那天收盘时已知）：趋势（前一天收盘在 25 日线上 / 下）、20 日高低点、放量、5 日涨跌。"""
    H, L, C, V = P["H"], P["L"], P["C"], P["V"]
    sma25 = rolling_mean(C, 25)
    c1, s1 = sh(C, 1), sh(sma25, 1)
    hi20 = sh(rolling_max(H, 20), 1)                       # 前 20 天（不含今天）的最高
    lo20 = sh(rolling_min(L, 20), 1)
    vma20 = sh(rolling_mean(V, 20), 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        x = {"up_tr": c1 > s1, "dn_tr": c1 < s1, "hi20_poke": H > hi20, "hi20_close": C > hi20,
             "lo20_poke": L < lo20, "lo20_close": C < lo20, "vsurge": V >= 1.5 * vma20, "vr": V / vma20,
             "ret5": C / sh(C, 5) - 1, "ma25_pos": C / sma25 - 1}
    for k in ("up_tr", "dn_tr", "hi20_poke", "hi20_close", "lo20_poke", "lo20_close", "vsurge"):
        x[k] = np.asarray(x[k], bool)
    return x


def patterns(P: dict[str, np.ndarray], g: dict[str, np.ndarray], x: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """经典形态（定义见 PATTERNS；全部只用 t、t−1、t−2 的 K 线与情境）。"""
    O, H, L, C = P["O"], P["H"], P["L"], P["C"]
    ok, bull, bear = g["ok"], g["bull"], g["bear"]
    br, ur, lr, size, ab, a1 = g["body_r"], g["up_r"], g["lo_r"], g["size"], g["ab"], g["atr1"]
    up, lo, rng = g["up"], g["lo"], g["rng"]
    utr, dtr = x["up_tr"], x["dn_tr"]
    top, bot = np.fmax(O, C), np.fmin(O, C)
    O1, H1, L1, C1 = sh(O, 1), sh(H, 1), sh(L, 1), sh(C, 1)
    O2, H2, L2, C2 = sh(O, 2), sh(H, 2), sh(L, 2), sh(C, 2)
    bull1, bear1, bull2, bear2 = sh(bull, 1), sh(bear, 1), sh(bull, 2), sh(bear, 2)
    br1, br2, size1, size2 = sh(br, 1), sh(br, 2), sh(size, 1), sh(size, 2)
    top1, bot1 = sh(top, 1), sh(bot, 1)
    with np.errstate(invalid="ignore"):
        pat = {
            "LUB": bull & (ur >= 0.4) & (lr <= 0.15) & (br >= 0.2) & (size >= 1.0),
            "LUR": bear & (ur >= 0.4) & (lr <= 0.15) & (br >= 0.2),
            "LLB": bull & (lr >= 0.4) & (ur <= 0.15) & (br >= 0.2),
            "LLR": bear & (lr >= 0.4) & (ur <= 0.15) & (br >= 0.2),
            "HAM": ok & (lo >= 2 * ab) & (ur <= 0.1) & (br <= 0.35) & dtr,
            "HANG": ok & (lo >= 2 * ab) & (ur <= 0.1) & (br <= 0.35) & utr,
            "IHAM": ok & (up >= 2 * ab) & (lr <= 0.1) & (br <= 0.35) & dtr,
            "STAR": ok & (up >= 2 * ab) & (lr <= 0.1) & (br <= 0.35) & utr,
            "DOJI": ok & (br <= 0.1) & (size >= 0.5),
            "DRAG": ok & (br <= 0.1) & (size >= 0.5) & (lr >= 0.6),
            "GRAVE": ok & (br <= 0.1) & (size >= 0.5) & (ur >= 0.6),
            "BIGB": bull & (br >= 0.7) & (size >= 1.5),
            "BIGR": bear & (br >= 0.7) & (size >= 1.5),
            "SPIN": ok & (br <= 0.3) & (ur >= 0.25) & (lr >= 0.25),
            "ENGB": bull & bear1 & (O <= C1) & (C >= O1) & (ab > sh(ab, 1)),
            "ENGR": bear & bull1 & (O >= C1) & (C <= O1) & (ab > sh(ab, 1)),
            "HARB": bull & bear1 & (br1 >= 0.6) & (size1 >= 1.0) & (top <= O1) & (bot >= C1),
            "HARR": bear & bull1 & (br1 >= 0.6) & (size1 >= 1.0) & (top <= C1) & (bot >= O1),
            "PIER": bull & bear1 & (br1 >= 0.5) & (O < L1) & (C > (O1 + C1) / 2) & (C < O1),
            "DARK": bear & bull1 & (br1 >= 0.5) & (O > H1) & (C < (O1 + C1) / 2) & (C > O1),
            "GAPU": ok & (L > H1),
            "GAPD": ok & (H < L1),
            "TWB": bull & sh(dtr, 1) & (np.abs(L - L1) <= 0.1 * a1),
            "TWT": bear & sh(utr, 1) & (np.abs(H - H1) <= 0.1 * a1),
            "MSTAR": bull & bear2 & (br2 >= 0.5) & (size2 >= 1.0) & (br1 <= 0.3) & (top1 < C2) & (C > (O2 + C2) / 2),
            "ESTAR": bear & bull2 & (br2 >= 0.5) & (size2 >= 1.0) & (br1 <= 0.3) & (bot1 > C2) & (C < (O2 + C2) / 2),
            "W3": bull & bull1 & bull2 & (C > C1) & (C1 > C2) & (O >= O1) & (O <= C1) & (O1 >= O2) & (O1 <= C2)
                  & (ur <= 0.3) & (sh(ur, 1) <= 0.3) & (sh(ur, 2) <= 0.3) & (br >= 0.5) & (br1 >= 0.5) & (br2 >= 0.5),
            "B3": bear & bear1 & bear2 & (C < C1) & (C1 < C2) & (O <= O1) & (O >= C1) & (O1 <= O2) & (O1 >= C2)
                  & (lr <= 0.3) & (sh(lr, 1) <= 0.3) & (sh(lr, 2) <= 0.3) & (br >= 0.5) & (br1 >= 0.5) & (br2 >= 0.5),
            "GAP3U": ok & (L > H1) & (L1 > H2) & (L2 > sh(H, 3)),
            "GAP3D": ok & (H < L1) & (H1 < L2) & (H2 < sh(L, 3)),
        }
    return {k: np.asarray(v, bool) & ok for k, v in pat.items()}


def targets(P: dict[str, np.ndarray], horizons=(5, 10, 20)) -> dict[str, np.ndarray]:
    """之后的收益（只用于评价）：n1_cc 第二天收盘 / 今天收盘 − 1、n1_oc 第二天 收盘 / 开盘 − 1、g1 第二天开盘 / 今天收盘 − 1、
    fH 第二天开盘买、再过 H 个交易日开盘卖（开盘 → 开盘）。缺 K 线 → NaN。"""
    O, C = P["O"], P["C"]
    n = len(C)

    def fwd(a, k):
        out = np.full_like(a, np.nan)
        if k < n:
            out[:n - k] = a[k:]
        return out
    O1, C1 = fwd(O, 1), fwd(C, 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        t = {"n1_cc": C1 / C - 1, "n1_oc": C1 / O1 - 1, "g1": O1 / C - 1}
        for h in horizons:
            t[f"f{h}"] = fwd(O, 1 + h) / O1 - 1
    return t


def excess(R: np.ndarray, member: np.ndarray) -> np.ndarray:
    """减去同一天成员的平均（成员外 → NaN）。"""
    import warnings
    x = np.where(member & np.isfinite(R), R, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)                   # 整行都没有成员 → NaN
        m = np.nanmean(x, axis=1, keepdims=True)
    return x - m


def pullback(P: dict[str, np.ndarray], drop: float = 0.10, v5max: float = 0.85, sma_n: int = 150) -> np.ndarray:
    """缩量押し目（2026-09-27 探索期 2017〜2021 找到、scripts/candle_study.py 登记）：那天收盘时——
    ① 最近 5 个交易日跌 ≥ drop（收盘 / 5 天前收盘 − 1 ≤ −drop）；② 最近 5 天均量 ≤ 之前 20 天均量 × v5max（缩量）；
    ③ 收盘在 sma_n 日线上、且 sma_n 日线比 20 天前高（长期上升）；④ 今天最低没跌破前 20 天最低（回调，不是破位）。"""
    C, L, V = P["C"], P["L"], P["V"]
    sma = rolling_mean(C, sma_n)
    with np.errstate(invalid="ignore", divide="ignore"):
        ret5 = C / sh(C, 5) - 1
        vr5 = rolling_mean(V, 5) / sh(rolling_mean(V, 20), 5)
        lo20 = sh(rolling_min(L, 20), 1)
        m = (ret5 <= -drop) & (vr5 <= v5max) & (C > sma) & (sma > sh(sma, 20)) & ~(L < lo20)
    ok = np.isfinite(C) & np.isfinite(L) & np.isfinite(ret5) & np.isfinite(vr5) & np.isfinite(sma) & np.isfinite(lo20)
    return np.asarray(m, bool) & ok
