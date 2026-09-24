"""events.py — 决算日（決算発表 / earnings）等事件日历。突破策略最大的单日风险是决算跳空，
所以进场前要知道"未来 N 个交易日内有没有决算"。

数据源：yfinance 的 Ticker.calendar / earnings_dates（每只 1 次请求，只对候选票查，并缓存 3 天）。
取不到就当作"未知"——不拦截，但在日报里标注 unknown，绝不伪造日期。
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Protocol

import pandas as pd

from . import paths
from .utils import read_json, write_json

log = logging.getLogger("qbreak.events")
CACHE_TTL_DAYS = 3


class EarningsProvider(Protocol):
    def next_earnings(self, ticker: str) -> dt.date | None: ...


class YFinanceEarnings:
    def __init__(self, cache_path=None):
        self.path = cache_path or (paths.cache_dir() / "earnings.json")
        self.cache: dict = read_json(self.path, {}) or {}

    def next_earnings(self, ticker: str) -> dt.date | None:
        ent = self.cache.get(ticker)
        today = dt.date.today()
        if ent and (today - dt.date.fromisoformat(ent["fetched"])).days <= CACHE_TTL_DAYS:
            return dt.date.fromisoformat(ent["date"]) if ent.get("date") else None
        date = self._fetch(ticker, today)
        self.cache[ticker] = {"fetched": today.isoformat(), "date": date.isoformat() if date else None}
        try:
            write_json(self.path, self.cache)
        except Exception:                                    # noqa: BLE001
            pass
        return date

    @staticmethod
    def _fetch(ticker: str, today: dt.date) -> dt.date | None:
        try:
            import yfinance as yf
            for nm in ("yfinance", "yfinance.data", "yfinance.utils"):
                logging.getLogger(nm).setLevel(logging.CRITICAL)
            t = yf.Ticker(ticker)
            dates: list[dt.date] = []
            try:
                cal = t.calendar
                ed = cal.get("Earnings Date") if isinstance(cal, dict) else None
                if ed:
                    dates += [pd.Timestamp(x).date() for x in (ed if isinstance(ed, (list, tuple)) else [ed])]
            except Exception:                                # noqa: BLE001
                pass
            if not dates:
                try:
                    df = t.earnings_dates
                    if df is not None and len(df):
                        dates += [pd.Timestamp(x).date() for x in df.index]
                except Exception:                            # noqa: BLE001
                    pass
            future = sorted(d for d in dates if d >= today)
            return future[0] if future else None
        except Exception as e:                               # noqa: BLE001
            log.debug("决算日获取失败 %s: %s", ticker, e)
            return None


class FakeEarnings:
    def __init__(self, table: dict[str, dt.date | None] | None = None):
        self.table = table or {}
        self.calls: list[str] = []

    def next_earnings(self, ticker: str) -> dt.date | None:
        self.calls.append(ticker)
        return self.table.get(ticker)


def trading_days_until(target: dt.date, today: dt.date) -> int:
    """粗略交易日数（只跳过周末，足够做"N 日内回避"）。"""
    n, d = 0, today
    while d < target:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n
