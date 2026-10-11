"""events.py — 决算日（決算発表 / earnings）等事件日历。突破策略最大的单日风险是决算跳空，
所以进场前要知道"未来 N 个交易日内有没有决算"。

数据源（2026-10-11 起）：日本股 = J-Quants 的决算发表预定日为主（JQuantsFirstEarnings：Mac 每天 07:05 取的日程文件 / 云端有キー时现取），
J-Quants 里没有的 → yfinance 的 Ticker.calendar / earnings_dates（每只 1 次请求，只对候选票查，并缓存 3 天）；美股 = yfinance。
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


def trading_days_until(target: dt.date, today: dt.date, market: str = "JP") -> int:
    """today 之后到 target（含）的交易日数：日本按东证日历（周末 + 祝日 + 年末年始），美国按 NYSE 日历。
    2026-09-29 修正：以前只跳过周末 → 连休前后多数了祝日，「决算前 N 个交易日不进场」会漏挡
    （例：4/30 看 5/7 的决算，中间是黄金周，实际 2 个交易日，旧算法数成 5 个）。"""
    if str(market).upper() == "US":
        from .calendar_us import is_trading_day
    else:
        from .calendar_jp import is_trading_day
    n, d = 0, today
    while d < target:
        d += dt.timedelta(days=1)
        if is_trading_day(d):
            n += 1
    return n


# ───────────────────────── J-Quants 为主（2026-10-11 用户「决算日程换 J-Quants 为主」） ─────────────────────────
JQ_SCHED_MAX_AGE = 7                     # 日程文件最多用几天前取的（日历日）
JQ_SCHED_DAYS = 10                       # 现取时看接下来几个营业日（与 qbreak/jq_live.SOON_DAYS 相同）


def _code4(c) -> str:
    s = str(c).strip()
    return s[:4] if len(s) == 5 and s.endswith("0") else s


def jq_sched_files(today: dt.date) -> list:
    """候选的 J-Quants 决算日程文件（新的在前）：<数据目录>/cache/jquants/live/<日>_earn_sched.csv.gz（Mac 的 com.qbreak.jquants 每个营业日 07:05 取，
    覆盖那天之后 10 个营业日）。找的地方：这次的数据目录 → Mac 的数据目录（~/.qbreak/home；本机例行任务的 sim-day 用仓库 var/ 当数据目录、自己没有）。
    只用 today 之前取的（06:45 的 sim-day 与 07:40 的执行器读同一份 → 两边决策一致）；没有 → 今天取的。"""
    import os
    from pathlib import Path
    dirs = [paths.home() / "cache" / "jquants" / "live", Path(os.environ.get("QBREAK_JQ_LIVE") or Path.home() / ".qbreak" / "home" / "cache" / "jquants" / "live")]
    seen, out = set(), []
    for d in dirs:
        try:
            d = d.resolve()
        except OSError:
            continue
        if d in seen or not d.is_dir():
            continue
        seen.add(d)
        for fp in d.glob("*_earn_sched.csv.gz"):
            try:
                fd = dt.date.fromisoformat(fp.name[:10])
            except ValueError:
                continue
            if 0 <= (today - fd).days <= JQ_SCHED_MAX_AGE:
                out.append((fd, fp))
    older = sorted((x for x in out if x[0] < today), key=lambda x: x[0], reverse=True)
    same = [x for x in out if x[0] == today]
    return [fp for _, fp in older + same]


def _read_sched(fp) -> pd.DataFrame:
    import gzip
    import io
    df = pd.read_csv(io.BytesIO(gzip.decompress(fp.read_bytes())), dtype=str)
    return df[["Code", "SchDate"]].dropna() if {"Code", "SchDate"} <= set(df.columns) else pd.DataFrame(columns=["Code", "SchDate"])


def _fetch_sched(today: dt.date) -> pd.DataFrame | None:
    """没有日程文件、但有 JQUANTS_API_KEY（云端后备）→ 现取接下来 10 个营业日的决算预定日（缓存进 <数据目录>/cache/jquants/live，不入库）。"""
    import gzip
    import os
    if not os.environ.get("JQUANTS_API_KEY"):
        return None
    try:
        from .calendar_jp import next_trading_day
        from .jquants import JQuants
        cl, rows, x = JQuants(), [], today - dt.timedelta(days=1)
        for _ in range(JQ_SCHED_DAYS + 1):
            x = next_trading_day(x)
            rows += cl.get("/fins/earnings-date", scheduled_date=x.strftime("%Y-%m-%d"))
        df = pd.DataFrame(rows)
        d = paths.sub("cache/jquants/live")
        (d / f"{today.isoformat()}_earn_sched.csv.gz").write_bytes(gzip.compress(df.to_csv(index=False).encode("utf-8")))
        return df[["Code", "SchDate"]].dropna() if len(df) else pd.DataFrame(columns=["Code", "SchDate"])
    except Exception as e:                                   # noqa: BLE001
        log.warning("J-Quants 决算日程现取失败（用 Yahoo）：%s", e)
        return None


class JQuantsFirstEarnings:
    """决算日：J-Quants 的决算发表预定日（东证公布的、公司自己定的日子）为主；J-Quants 里没有这只（还没公布 / 10 个营业日以外）→ Yahoo（YFinanceEarnings）。
    美股 → Yahoo。self.source[票] = "jquants" / "yahoo"（日报 / 日志用）。J-Quants 取不到 → 全部 Yahoo（与以前相同），绝不伪造日期。"""

    def __init__(self, yahoo=None, today: dt.date | None = None):
        self.yahoo = yahoo or YFinanceEarnings()
        self.today = today or dt.date.today()
        self.source: dict[str, str] = {}
        self.sched_file = None
        self._map: dict[str, dt.date] | None = None

    def _sched(self) -> dict[str, dt.date]:
        if self._map is not None:
            return self._map
        df = None
        for fp in jq_sched_files(self.today):
            try:
                df = _read_sched(fp)
                self.sched_file = fp.name
                break
            except Exception as e:                           # noqa: BLE001
                log.warning("J-Quants 决算日程文件读不了 %s：%s", fp.name, e)
        if df is None:
            df = _fetch_sched(self.today)
            self.sched_file = "J-Quants API（现取）" if df is not None else None
        m: dict[str, dt.date] = {}
        for c, s in (df.itertuples(index=False) if df is not None else []):
            try:
                d = dt.date.fromisoformat(str(s)[:10])
            except ValueError:
                continue
            k = _code4(c)
            if d >= self.today and (k not in m or d < m[k]):
                m[k] = d
        self._map = m
        return m

    def next_earnings(self, ticker: str) -> dt.date | None:
        t = str(ticker)
        if t.endswith(".T"):
            d = self._sched().get(t.split(".")[0])
            if d is not None:
                self.source[t] = "jquants"
                return d
        self.source[t] = "yahoo"
        return self.yahoo.next_earnings(t)
