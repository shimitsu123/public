"""us_stock_data.py — 美国个股行情（横展开检验用，2026-09-27）。

股票池 = 今天的 S&P 500 / S&P 400 成分（Wikipedia 2026-09-27 时点，冻结在 var/us_constituents_2026-09.json；幸存者偏差同日本 E 窗口
「今天的日経225」口径）。行情 = yfinance 27 年日线（调整后 OHLCV，qbreak.data.load_universe 同一口径，缓存在 var/cache/，不入库），
另取未复权收盘与每股分红（算股息率；缓存 var/cache/us_yf/）。
用法：python scripts/us_stock_data.py --prefetch
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402

YEARS = 27
ACT_DIR = "us_yf"
CONST_FILE = "us_constituents_2026-09.json"
INDEXES = {"sp500": "^GSPC", "sp400": "^MID"}


def constituents() -> dict:
    return json.loads((paths.PROJECT_ROOT / "var" / CONST_FILE).read_text(encoding="utf-8"))


def names(pool: str = "sp500") -> list[str]:
    """pool = sp500 / sp400 / all；同一公司的双重股份只留第一只（GOOGL / GOOG、FOXA / FOX、NWSA / NWS、BRK-B 只有一只）。"""
    c = constituents()
    pools = ["sp500", "sp400"] if pool == "all" else [pool]
    out, seen = [], set()
    dup = {"GOOG": "GOOGL", "FOX": "FOXA", "NWS": "NWSA"}
    for p in pools:
        for r in c[p]:
            t = r["ticker"]
            if t in seen or dup.get(t) in seen:
                continue
            seen.add(t)
            out.append(t)
    return out


def sector_map() -> dict[str, str]:
    c = constituents()
    return {r["ticker"]: r["sector"] for p in ("sp500", "sp400") for r in c[p]}


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


def prefetch(pool: str = "all") -> int:
    t0 = time.time()
    n = names(pool) + list(INDEXES.values())
    data = ohlcv(n)
    print(f"行情：{len(data)}/{len(n)} 只（{time.time() - t0:.0f}s）", flush=True)
    ok = 0
    for k, t in enumerate(names(pool), 1):
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
            print(f"  分红 {k}/{len(names(pool))}（{time.time() - t0:.0f}s）", flush=True)
    print(f"分红：{ok} 只；用时 {time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(prefetch() if "--prefetch" in sys.argv else 0)
