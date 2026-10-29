"""leap_data.py — 「质的飞跃」研究循环的数据（2026-09-27）。

yfinance 27 年日线（今天的日経225 股票池 + 扩大池 var/universe_wide.json，调整后 OHLCV，qbreak.data.load_universe 同一口径），
另外每只票的未复权收盘（只做拆股调整）与每股分红（算股息率）。缓存只在 var/cache/（不入库）。
Z 年代（2000-01〜2006-09）的行情在这里一起取，但探索脚本不准用 Z 的信号（scripts/leap_common.py assert_explore_dates）。
用法：python scripts/leap_data.py --prefetch（先把行情与分红取好，约 10〜30 分钟）
"""
from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qbreak import paths                                                     # noqa: E402

YEARS = 27
ACT_DIR = "leap_yf"


def names(wide: bool = True) -> list[str]:
    from qbreak import wide_universe as WU
    from qbreak.config import universe
    n = list(universe("JP", "broad"))
    if wide:
        n += [t for t in WU.tickers(WU.load()) if t not in set(n)]
    return n


def ohlcv(tickers: list[str], years: int = YEARS) -> dict[str, pd.DataFrame]:
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    cfg = DataConfig(provider="yfinance", years=years, allow_synthetic=False, cache_ttl_hours=1e9, min_bars=60).validate()
    return load_universe(tickers, cfg)


def _act_path(t: str) -> Path:
    return paths.sub("cache") / ACT_DIR / f"{t.replace('^', '_')}.csv"


def actions(t: str, refresh: bool = False) -> pd.DataFrame:
    """未复权收盘（Yahoo 的 Close：只做拆股调整）与每股分红（同样按拆股调整）→ DataFrame[close_raw, div]。"""
    fp = _act_path(t)
    if fp.exists() and not refresh:
        return pd.read_csv(fp, index_col=0, parse_dates=True)
    import logging

    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    h = yf.Ticker(t).history(period="max", auto_adjust=False, actions=True)
    if h is None or not len(h):
        out = pd.DataFrame(columns=["close_raw", "div"])
    else:
        h.index = h.index.tz_localize(None).normalize()
        h = h[~h.index.duplicated(keep="last")]
        out = pd.DataFrame({"close_raw": h["Close"].astype(float), "div": h.get("Dividends", 0.0)})
    fp.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(fp)
    return out


def div_yield(act: pd.DataFrame, days: pd.DatetimeIndex, window_days: int = 365) -> pd.Series:
    """每个交易日：过去 window_days 天（含当天）的每股分红合计 ÷ 当天未复权收盘（%）。只用当天为止已知的分红（权利落ち日）。"""
    if act is None or not len(act):
        return pd.Series(np.nan, index=days)
    d = act["div"].fillna(0.0)
    cum = d.cumsum()
    c = cum.reindex(cum.index.union(days)).ffill().fillna(0.0)
    lag = c.reindex(days - pd.Timedelta(days=window_days), method="ffill").fillna(0.0).to_numpy()
    tot = c.reindex(days).to_numpy() - lag
    px = act["close_raw"].reindex(act.index.union(days)).ffill().reindex(days)
    y = tot / px.to_numpy() * 100
    first = act.index[0] + pd.Timedelta(days=window_days)                    # 历史不满一年 → 缺值
    return pd.Series(np.where(days >= first, y, np.nan), index=days)


def prefetch() -> int:
    t0 = time.time()
    n = names()
    data = ohlcv(n)
    print(f"行情：{len(data)}/{len(n)} 只（{time.time() - t0:.0f}s）", flush=True)
    ok = 0
    for k, t in enumerate(n, 1):
        for a in range(3):
            try:
                actions(t)
                ok += 1
                break
            except Exception as e:                                           # noqa: BLE001
                if a == 2:
                    print(f"  {t} 分红取不到：{e}", flush=True)
                time.sleep(2 * (a + 1))
        if k % 100 == 0:
            print(f"  分红 {k}/{len(n)}（{time.time() - t0:.0f}s）", flush=True)
    print(f"分红：{ok}/{len(n)} 只；用时 {time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(prefetch() if "--prefetch" in sys.argv else 0)
