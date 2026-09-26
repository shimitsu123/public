"""strategy.py — 信号量化（シグナル生成 / signal generation）。回测与实盘共用。

入场（全部成立才发出 entry）：
  ① 横盘   : 截至【昨日】的 N 日 (High.max − Low.min)/Low.min < X%
  ② 金叉   : MACD 上穿 Signal（ゴールデンクロス / golden cross）
  ③ 0 轴附近: |MACD| / Close × 100 < zero_band%
  ④ 放量   : Volume > MA(Volume, vol_ma_n) × vol_mult
  ⑤ 可选   : 真突破 / 趋势 / 流动性 / 最低价

前视偏差（先読みバイアス / look-ahead bias）约定
  本模块所有列在时刻 t 的取值只允许使用 ≤ t 的数据；
  tests/test_strategy.py 用「逐步截断重算」property test 强制保证这一点。
  信号在 T 日收盘成立 → 由引擎在 T+1 开盘执行，执行侧的偏差在 engine.py 处理。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import StrategyParams

OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def macd(close: pd.Series, fast: int, slow: int, signal: int):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    """真实波幅均值（ATR / アベレージ・トゥルー・レンジ）——Wilder 平滑。"""
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int) -> pd.Series:
    """Wilder RSI。"""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.mask((dn == 0) & up.notna(), 100.0)      # 只涨不跌 → 100，而不是 NaN


def compute_indicators(df: pd.DataFrame, p: StrategyParams,
                       index_close: pd.Series | None = None) -> pd.DataFrame:
    """在 OHLCV 上追加指标与信号列。输入必须按日期升序且无重复。
    index_close：基准指数收盘价（用于相对强度）；None 时相对强度过滤自动跳过。"""
    missing = [c for c in OHLCV if c not in df.columns]
    if missing:
        raise ValueError(f"缺少列 {missing}")
    if not df.index.is_monotonic_increasing:
        raise ValueError("数据索引必须按日期升序")
    if df.index.has_duplicates:
        raise ValueError("数据索引存在重复日期")

    out = df.copy()
    c, h, l, v = out["Close"], out["High"], out["Low"], out["Volume"]

    # ── ① 横盘 ──
    hi_n = h.rolling(p.range_n).max()
    lo_n = l.rolling(p.range_n).min()
    with np.errstate(divide="ignore", invalid="ignore"):
        out["range_pct"] = (hi_n - lo_n) / lo_n.replace(0, np.nan) * 100
    # shift(1)：用「昨日为止」的振幅判定，避免当日突破的大阳线把箱体自己撑大
    out["is_range"] = out["range_pct"].shift(1) < p.range_x_pct

    # ── ② ③ MACD ──
    m, s, hst = macd(c, p.macd_fast, p.macd_slow, p.macd_signal)
    out["macd"], out["macd_sig"], out["macd_hist"] = m, s, hst
    out["golden_cross"] = (m > s) & (m.shift(1) <= s.shift(1))
    out["dead_cross"] = (m < s) & (m.shift(1) >= s.shift(1))
    out["near_zero"] = (m.abs() / c * 100) < p.macd_zero_band_pct

    # ── ④ 放量 ──
    out["vol_ma"] = v.rolling(p.vol_ma_n).mean()
    out["vol_ratio"] = v / out["vol_ma"].replace(0, np.nan)
    out["vol_surge"] = out["vol_ratio"] > p.vol_mult

    # ── ⑤ 可选过滤器 ──
    box_top = hi_n.shift(1)                       # 不含当日的箱顶
    out["box_top"] = box_top
    out["breakout"] = c > box_top * (1 + p.breakout_buffer_pct / 100)
    out["trend_ok"] = (c > c.rolling(p.trend_ma_n).mean()) if p.trend_ma_n else True
    out["turnover_ma"] = (c * v).rolling(p.vol_ma_n).mean()
    out["liq_ok"] = (out["turnover_ma"] >= p.min_turnover) if p.min_turnover else True
    out["price_ok"] = (c >= p.min_price) if p.min_price else True

    out["atr"] = atr(out, p.atr_n)

    # ── 顶部 / 出货识别（天井・分配）──
    ma20 = c.rolling(20).mean()
    out["ext_ma20_pct"] = (c / ma20 - 1) * 100                  # 相对 20 日线伸展度
    out["rsi"] = rsi(c, p.rsi_n)
    down_on_vol = (c.pct_change() < -0.002) & (v > v.shift(1))   # 出货日：收跌且放量
    out["dist_days"] = down_on_vol.astype(int).rolling(p.distribution_lookback).sum()
    body = (c - out["Open"]).abs().replace(0, np.nan)
    out["upper_shadow_ratio"] = (h - np.maximum(c, out["Open"])) / body
    climax = (v > out["vol_ma"] * p.climax_vol_mult) & (c < out["Open"])
    out["climax"] = climax.fillna(False).astype(bool)           # 高位放量陰線（是否"高位"由持仓浮盈判断）

    # ── 相对强度（対指数）：有指数就算出来供候补队列展示；只有 min_rs_pct > -900 才作为过滤 ──
    if index_close is not None:
        ic = index_close.reindex(out.index).ffill()
        out["rs_pct"] = (c / c.shift(p.rs_n) - 1) * 100 - (ic / ic.shift(p.rs_n) - 1) * 100
    else:
        out["rs_pct"] = np.nan
    rs_filter = index_close is not None and p.min_rs_pct > -900
    out["rs_ok"] = (out["rs_pct"] >= p.min_rs_pct) if rs_filter else True

    cond = out["is_range"] & out["golden_cross"] & out["near_zero"] & out["vol_surge"]
    if p.max_ext_ma20_pct:
        cond &= out["ext_ma20_pct"] <= p.max_ext_ma20_pct
    if p.max_rsi:
        cond &= out["rsi"] <= p.max_rsi
    if p.max_distribution_days:
        cond &= out["dist_days"] < p.max_distribution_days
    if p.max_upper_shadow_ratio:
        cond &= ~(out["upper_shadow_ratio"] > p.max_upper_shadow_ratio)
    if rs_filter:
        cond &= out["rs_ok"]
    if p.require_breakout:
        cond &= out["breakout"]
    if p.trend_ma_n:
        cond &= out["trend_ok"]
    if p.min_turnover:
        cond &= out["liq_ok"]
    if p.min_price:
        cond &= out["price_ok"]

    # 预热期内一律不发信号（数据不足时 rolling 得到 NaN → 比较结果为 False，这里再兜一层）
    warm = np.arange(len(out)) >= p.warmup_bars
    out["entry"] = (cond.fillna(False).to_numpy(dtype=bool)) & warm
    out["dead_cross"] = out["dead_cross"].fillna(False).astype(bool)
    return out


# ────────────────────── 指标缓存（给网格搜索加速）──────────────────────
# 会改变 compute_indicators 输出的全部字段（离场参数不在其中：它们只在引擎里用）
INDICATOR_FIELDS = (
    "range_n", "range_x_pct", "macd_fast", "macd_slow", "macd_signal", "macd_zero_band_pct",
    "vol_ma_n", "vol_mult", "require_breakout", "breakout_buffer_pct", "trend_ma_n",
    "min_price", "min_turnover", "atr_n",
    "max_ext_ma20_pct", "rsi_n", "max_rsi", "distribution_lookback", "max_distribution_days",
    "max_upper_shadow_ratio", "rs_n", "min_rs_pct", "climax_vol_mult",
)


class IndicatorCache:
    """网格搜索里 range_n 只影响横盘列、MACD 三参数只影响 MACD 列。
    原版每个参数组合都对全部股票整套重算，36 组 × 5 窗口 = 180 次全量重算。
    这里按「子参数」缓存中间结果，默认网格下重算量降到约 1/6。
    index_close：基准指数收盘序列（相对强度过滤用）；None 时该过滤自动跳过。"""

    def __init__(self, data: dict[str, pd.DataFrame], index_close: pd.Series | None = None):
        self.data = data
        self.index_close = index_close
        self._cache: dict[tuple, pd.DataFrame] = {}

    def get(self, ticker: str, p: StrategyParams) -> pd.DataFrame:
        key = (ticker,) + tuple(getattr(p, f) for f in INDICATOR_FIELDS)
        hit = self._cache.get(key)
        if hit is None:
            hit = compute_indicators(self.data[ticker], p, self.index_close)
            self._cache[key] = hit
        return hit

    def all(self, p: StrategyParams) -> dict[str, pd.DataFrame]:
        return {t: self.get(t, p) for t in self.data}

    def clear(self):
        self._cache.clear()


def latest_signal(df: pd.DataFrame, p: StrategyParams) -> dict:
    """实盘用：最后一根 K 线的信号快照（便于写日志/通知）。"""
    ind = compute_indicators(df, p)
    r = ind.iloc[-1]
    def f(x):
        return None if pd.isna(x) else round(float(x), 4)
    return {
        "date": str(r.name.date()) if hasattr(r.name, "date") else str(r.name),
        "close": f(r["Close"]), "entry": bool(r["entry"]), "dead_cross": bool(r["dead_cross"]),
        "range_pct": f(r["range_pct"]), "macd": f(r["macd"]), "vol_ratio": f(r["vol_ratio"]),
        "breakout": bool(r["breakout"]) if not pd.isna(r["breakout"]) else False,
        "atr": f(r["atr"]),
    }
