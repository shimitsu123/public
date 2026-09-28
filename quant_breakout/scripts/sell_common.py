"""sell_common.py — 「卖出判定」横展开的共用部分（2026-09-28）：像 MACD 死叉那样「收盘时成立 → 次日开盘卖」的判定。
探索 scripts/sell_explore.py（只用 E / J）与之后可能的登记检验共用这里的定义与实现。

现行卖法：MACD 死叉（组合里 95〜100% 的出场）+ 止损 −7%、跟踪 12%、止盈 +25%、放量阴线、最长 60 个交易日。
每个变体只改「死叉」那一条（指标表的 dead_cross 列；回测引擎本来就读这一列，引擎不动），其余卖法与买点完全不变：
  R 换判定：用另一个判定代替死叉；A 另外加：死叉照旧，另一个判定成立也卖；C 死叉要确认：死叉当天另一个条件也成立才卖（否则这次死叉不算）。
以前做过、这里不再重复（照实写）：死叉两天确认 X9、20 日线 / 前 10 日低点 / 吊灯止损代替死叉（X4〜X7）、赢家放宽 X1〜X3、假突破就走 X8、
  前几天不看死叉 H3 / H4（bsh_explore）；死叉要跌破 20 日线确认（signal_study X1）；锁利 5 / 8%、止盈 +6 / +10%（leap2_s1b_exits）；
  「另外加」跌破 5 / 10 / 20 日线（exit_explore）、按行情切换（regime_exit_explore）；止损 / 跟踪 / 止盈 / 最长持有的参数（param_study）。
所有判定只用当天收盘为止的数据（有测试）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 变体：fam（R 换判定 / A 另外加 / C 死叉要确认）、zh、sig（判定名，见 signals）、mode（replace / or / and）
VARIANTS: dict[str, dict] = {
    "R1": {"fam": "R", "zh": "KD 死叉（慢速随机指标 14 / 3 / 3：%K 下穿 %D）代替 MACD 死叉", "sig": "kd_dead", "mode": "replace"},
    "R2": {"fam": "R", "zh": "RSI(14) 下穿 50 代替", "sig": "rsi50_down", "mode": "replace"},
    "R3": {"fam": "R", "zh": "5 日均线下穿 20 日均线代替", "sig": "ma5_20_dead", "mode": "replace"},
    "R4": {"fam": "R", "zh": "抛物线 SAR（0.02 / 0.02 / 0.2）翻到价格上方代替", "sig": "sar_flip", "mode": "replace"},
    "R5": {"fam": "R", "zh": "DMI：−DI(14) 上穿 +DI(14) 代替", "sig": "dmi_dead", "mode": "replace"},
    "R6": {"fam": "R", "zh": "MACD 柱连续 2 天变小（比死叉早）代替", "sig": "hist_down2", "mode": "replace"},
    "R7": {"fam": "R", "zh": "平均足（Heikin-Ashi）连续 2 根阴线代替", "sig": "ha_bear2", "mode": "replace"},
    "R8": {"fam": "R", "zh": "收盘跌破前一天最低价代替", "sig": "below_prev_low", "mode": "replace"},
    "A1": {"fam": "A", "zh": "死叉照旧 + RSI(14) 从 70 以上跌回 70 以下也卖", "sig": "rsi70_down", "mode": "or"},
    "A2": {"fam": "A", "zh": "死叉照旧 + KD 在 80 以上死叉也卖", "sig": "kd_dead_hi", "mode": "or"},
    "A3": {"fam": "A", "zh": "死叉照旧 + 收盘从布林上轨（20 日、2σ）之外回到之内也卖", "sig": "bb_fall", "mode": "or"},
    "A4": {"fam": "A", "zh": "死叉照旧 + 看跌吞没（阴线实体包住前一天阳线实体）也卖", "sig": "engulf_bear", "mode": "or"},
    "A5": {"fam": "A", "zh": "死叉照旧 + 收盘比 25 日均线高 10% 以上（乖离过大）也卖", "sig": "dev25_10", "mode": "or"},
    "C1": {"fam": "C", "zh": "死叉当天 RSI(14) < 50 才卖（否则这次死叉不算）", "sig": "rsi_lt50", "mode": "and"},
    "C2": {"fam": "C", "zh": "死叉当天是阴线（收盘 < 开盘）才卖", "sig": "bear_candle", "mode": "and"},
}
NEUTRAL = {"sig": "_none", "mode": "or"}                                     # 核对用：死叉 ∨ 全 False → 应与现行完全相同
SIGNALS = sorted({v["sig"] for v in VARIANTS.values()}) + ["dead_cross"]


# ───────────────────────── 指标（纯函数，只用当天为止）─────────────────────────
def sma(x, n: int) -> np.ndarray:
    return pd.Series(np.asarray(x, float)).rolling(n, min_periods=n).mean().to_numpy()


def wilder(x, n: int) -> np.ndarray:
    return pd.Series(np.asarray(x, float)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()


def cross_down(a, b) -> np.ndarray:
    """今天 a < b、昨天 a ≥ b（任何一个缺值 → False）。"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    out = np.zeros(len(a), bool)
    with np.errstate(invalid="ignore"):
        out[1:] = (a[1:] < b[1:]) & (a[:-1] >= b[:-1])
    return out


def rsi(c, n: int = 14) -> np.ndarray:
    from qbreak.strategy import rsi as _rsi
    return _rsi(pd.Series(np.asarray(c, float)), n).to_numpy()


def stoch(h, lo, c, n: int = 14, k: int = 3, d: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """慢速随机指标：原始 %K = (C − n 日最低) / (n 日最高 − n 日最低) × 100 → 慢 %K = k 日平均，%D = 慢 %K 的 d 日平均。"""
    hh = pd.Series(np.asarray(h, float)).rolling(n, min_periods=n).max().to_numpy()
    ll = pd.Series(np.asarray(lo, float)).rolling(n, min_periods=n).min().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        raw = np.where(hh > ll, (np.asarray(c, float) - ll) / (hh - ll) * 100, 50.0)
    raw[~np.isfinite(hh) | ~np.isfinite(ll)] = np.nan
    kk = sma(raw, k)
    return kk, sma(kk, d)


def dmi(h, lo, c, n: int = 14) -> tuple[np.ndarray, np.ndarray]:
    """+DI / −DI（Wilder）：+DM = 今天高 − 昨天高（比 −DM 大且 > 0 才算），−DM = 昨天低 − 今天低（同样）。"""
    h, lo, c = (np.asarray(x, float) for x in (h, lo, c))
    up, dn = np.r_[np.nan, np.diff(h)], np.r_[np.nan, -np.diff(lo)]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.c_[h - lo, np.abs(h - pc), np.abs(lo - pc)], axis=1)
    pdm[0] = mdm[0] = np.nan
    atr = wilder(tr, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return 100 * wilder(pdm, n) / atr, 100 * wilder(mdm, n) / atr


def psar(h, lo, step: float = 0.02, mx: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    """抛物线 SAR（Wilder）。返回 (SAR, up)：up = True 表示上升趋势（SAR 在价格下方）。第一天按「第二天收在第一天之上 → 上升」起算。"""
    h, lo = np.asarray(h, float), np.asarray(lo, float)
    n = len(h)
    sar, up = np.full(n, np.nan), np.zeros(n, bool)
    if n < 2:
        return sar, up
    trend = h[1] >= h[0]
    ep = h[0] if trend else lo[0]
    s = lo[0] if trend else h[0]
    af = step
    for i in range(1, n):
        s = s + af * (ep - s)
        if trend:
            s = min(s, lo[i - 1], lo[i - 2] if i >= 2 else lo[i - 1])
            if lo[i] < s:                                                    # 跌破 → 翻成下降
                trend, s, ep, af = False, ep, lo[i], step
            elif h[i] > ep:
                ep, af = h[i], min(af + step, mx)
        else:
            s = max(s, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > s:                                                     # 突破 → 翻成上升
                trend, s, ep, af = True, ep, h[i], step
            elif lo[i] < ep:
                ep, af = lo[i], min(af + step, mx)
        sar[i], up[i] = s, trend
    return sar, up


def heikin_bear(o, h, lo, c) -> np.ndarray:
    """平均足：HA 收 = (开 + 高 + 低 + 收) / 4，HA 开 = (前一根 HA 开 + 前一根 HA 收) / 2（第一根 = (开 + 收) / 2）；HA 收 < HA 开 → 阴线。"""
    o, h, lo, c = (np.asarray(x, float) for x in (o, h, lo, c))
    hc = (o + h + lo + c) / 4
    ho = np.empty(len(o))
    if len(o):
        ho[0] = (o[0] + c[0]) / 2
        for i in range(1, len(o)):
            ho[i] = (ho[i - 1] + hc[i - 1]) / 2
    return hc < ho


# ───────────────────────── 判定（收盘时成立 → 次日开盘卖）─────────────────────────
def signals(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """一只票的指标表（Open / High / Low / Close / macd / macd_sig / dead_cross）→ 全部判定（布尔数组）。"""
    o, h, lo, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    n = len(c)
    prev = lambda x: np.r_[np.nan, np.asarray(x, float)[:-1]]                                        # noqa: E731
    r = rsi(c, 14)
    kk, dd = stoch(h, lo, c)
    pdi, mdi = dmi(h, lo, c)
    _, up = psar(h, lo)
    hist = (df["macd"] - df["macd_sig"]).to_numpy(float)
    hb = heikin_bear(o, h, lo, c)
    m20, s20 = sma(c, 20), pd.Series(c).rolling(20, min_periods=20).std(ddof=0).to_numpy()
    upper = m20 + 2 * s20
    m25 = sma(c, 25)
    with np.errstate(invalid="ignore"):
        out = {
            "kd_dead": cross_down(kk, dd),
            "rsi50_down": cross_down(r, np.full(n, 50.0)),
            "ma5_20_dead": cross_down(sma(c, 5), m20),
            "sar_flip": np.r_[False, up[:-1] & ~up[1:]] if n else np.zeros(0, bool),
            "dmi_dead": cross_down(pdi, mdi),
            "hist_down2": (hist < prev(hist)) & (prev(hist) < prev(prev(hist))),
            "ha_bear2": hb & np.r_[False, hb[:-1]],
            "below_prev_low": c < prev(lo),
            "rsi70_down": cross_down(r, np.full(n, 70.0)),
            "kd_dead_hi": cross_down(kk, dd) & (prev(dd) >= 80),
            "bb_fall": (prev(c) > prev(upper)) & (c <= upper),
            "engulf_bear": (c < o) & (prev(c) > prev(o)) & (o >= prev(c)) & (c <= prev(o)),
            "dev25_10": c / m25 - 1 >= 0.10,
            "rsi_lt50": r < 50,
            "bear_candle": c < o,
        }
    out = {k: np.nan_to_num(np.asarray(v, float), nan=0.0).astype(bool) for k, v in out.items()}
    out["_none"] = np.zeros(n, bool)
    out["dead_cross"] = df["dead_cross"].to_numpy(bool)
    return out


def exit_transform(fr: dict[str, pd.DataFrame], key: str | None, cache: dict | None = None) -> dict[str, pd.DataFrame]:
    """把每只票的 dead_cross 列换成变体的卖出判定（key = None → 原样；"_neutral" → 死叉 ∨ 全 False）。cache：{票: signals} 复用。"""
    if not key:
        return fr
    V = NEUTRAL if key == "_neutral" else VARIANTS[key]
    out = {}
    for t, df in fr.items():
        S = cache.get(t) if cache is not None else None
        if S is None:
            S = signals(df)
            if cache is not None:
                cache[t] = S
        d, s = S["dead_cross"], S[V["sig"]]
        new = s if V["mode"] == "replace" else (d | s if V["mode"] == "or" else d & s)
        out[t] = df.assign(dead_cross=new)
    return out
