"""
strategy.py — 信号量化（シグナル生成 / signal generation）。
回测与模拟盘/实盘共用同一个函数，保证"回测的就是实盘跑的"。

入场条件（全部为 True 才发出 entry 信号）：
  1. 横盘：过去 N 日 (High.max − Low.min) / Low.min < X%
  2. MACD 金叉（ゴールデンクロス / golden cross）：MACD 从下方穿越信号线
  3. 0 轴附近：|MACD| / Close < zero_band%
  4. 放量：Volume > vol_ma_n 日均量 × vol_mult
注意：所有指标只用到当日及之前数据，**不含未来信息**（前视偏差 / look-ahead bias 防护）。
"""
import numpy as np
import pandas as pd
from config import StrategyParams


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def macd(close: pd.Series, fast: int, slow: int, signal: int):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def compute_indicators(df: pd.DataFrame, p: StrategyParams) -> pd.DataFrame:
    """在原 OHLCV 上追加指标列，返回新 DataFrame。"""
    out = df.copy()
    c = out["Close"]

    # ── 横盘振幅 ──
    hi = out["High"].rolling(p.range_n).max()
    lo = out["Low"].rolling(p.range_n).min()
    out["range_pct"] = (hi - lo) / lo * 100
    # 用"昨日为止"的振幅判定横盘，避免当日突破大阳线把振幅本身撑大
    out["is_range"] = out["range_pct"].shift(1) < p.range_x_pct

    # ── MACD ──
    out["macd"], out["macd_sig"], out["macd_hist"] = macd(
        c, p.macd_fast, p.macd_slow, p.macd_signal)
    out["golden_cross"] = (out["macd"] > out["macd_sig"]) & \
                          (out["macd"].shift(1) <= out["macd_sig"].shift(1))
    out["dead_cross"] = (out["macd"] < out["macd_sig"]) & \
                        (out["macd"].shift(1) >= out["macd_sig"].shift(1))
    out["near_zero"] = (out["macd"].abs() / c * 100) < p.macd_zero_band_pct

    # ── 成交量 ──
    out["vol_ma"] = out["Volume"].rolling(p.vol_ma_n).mean()
    out["vol_surge"] = out["Volume"] > out["vol_ma"] * p.vol_mult

    # ── 合成入场信号 ──
    out["entry"] = out["is_range"] & out["golden_cross"] & out["near_zero"] & out["vol_surge"]
    out["entry"] = out["entry"].fillna(False).astype(bool)
    return out


def latest_signal(df: pd.DataFrame, p: StrategyParams) -> dict:
    """给实盘用：返回最后一根 K 线的信号快照。"""
    ind = compute_indicators(df, p).iloc[-1]
    return {
        "date": str(ind.name.date()) if hasattr(ind.name, "date") else str(ind.name),
        "close": float(ind["Close"]),
        "entry": bool(ind["entry"]),
        "dead_cross": bool(ind["dead_cross"]),
        "range_pct": round(float(ind["range_pct"]), 2),
        "macd": round(float(ind["macd"]), 3),
        "vol_ratio": round(float(ind["Volume"] / ind["vol_ma"]), 2) if ind["vol_ma"] else None,
    }
