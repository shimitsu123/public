"""
data.py — 行情数据加载。
优先 yfinance（本地 pip install yfinance），失败/未安装时用合成数据（テストデータ / synthetic）
让整套流程仍可运行，方便先调通代码。
"""
import os
import numpy as np
import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _synthetic(ticker: str, years: int, seed: int | None = None) -> pd.DataFrame:
    """生成带"横盘→突破"结构的合成 OHLCV，仅用于跑通代码，不代表真实市场。"""
    rng = np.random.default_rng(seed if seed is not None else abs(hash(ticker)) % (2**32))
    n = years * 252
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    # 混合：低波动横盘段 + 偶发趋势段
    regime = np.zeros(n)
    i = 0
    while i < n:
        L = rng.integers(40, 120)
        regime[i:i + L] = rng.choice([0, 1], p=[0.7, 0.3])  # 0=横盘 1=趋势
        i += L
    vol = np.where(regime == 0, 0.008, 0.02)
    drift = np.where(regime == 0, 0.0, rng.choice([-0.002, 0.003], size=n))
    ret = rng.normal(drift, vol)
    close = 1000 * np.exp(np.cumsum(ret))
    high = close * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.006, n)))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.003, n))
    volume = rng.lognormal(13, 0.4, n) * np.where(regime == 1, 1.6, 1.0)
    df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                       "Volume": volume}, index=idx)
    df.index.name = "Date"
    return df


def load_ohlcv(ticker: str, years: int = 5, use_cache: bool = True,
               allow_synthetic: bool = True) -> pd.DataFrame:
    """返回列为 Open/High/Low/Close/Volume 的日线 DataFrame（已去除 NaN）。"""
    path = os.path.join(CACHE_DIR, f"{ticker}_{years}y.parquet")
    if use_cache and os.path.exists(path):
        return pd.read_parquet(path)
    try:
        import yfinance as yf                                     # 本地: pip install yfinance
        df = yf.download(ticker, period=f"{years}y", interval="1d",
                         auto_adjust=True, progress=False)         # auto_adjust: 复权（調整後株価）
        if isinstance(df.columns, pd.MultiIndex):                  # yfinance 新版返回多级列
            df.columns = df.columns.get_level_values(0)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        if len(df) < 200:
            raise ValueError("数据太短")
        df.index.name = "Date"
        if use_cache:
            df.to_parquet(path)
        return df
    except Exception as e:  # noqa: BLE001
        if not allow_synthetic:
            raise
        print(f"[data] {ticker}: yfinance 不可用({type(e).__name__})，改用合成数据 ← 仅供调试")
        return _synthetic(ticker, years)


def load_universe(tickers: list[str], years: int = 5, **kw) -> dict[str, pd.DataFrame]:
    return {t: load_ohlcv(t, years, **kw) for t in tickers}
