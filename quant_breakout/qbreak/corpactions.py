"""corpactions.py — 配当落ち / 株式分割（コーポレートアクション）。

为什么需要：行情用的是**复权价**（yfinance auto_adjust=True）。回测因此天然正确（分红相当于再投资、
拆股前后价格连续），但模拟盘 / 实盘的持仓是按**真实价格**记账的：
  • 拆股（1→2）后真实价格腰斩，持仓股数却没变 → 看起来 −50%，止损被错误触发
  • 除息日真实价格下跌一个分红额 → 止损距离被吃掉一截，分红却没进现金
这里在每天撮合之前，把「上一根已处理 K 线 < 除权日 ≤ 本根 K 线」之间发生的公司行为补上。
"""
from __future__ import annotations

import datetime as dt
import time

from . import paths
from .utils import read_json, setup_logging, write_json

log = setup_logging("corpactions")

# 分红到手比例：日本株 特定口座 20.315%；美股 先扣美国 10% 预提、再扣日本 20.315%（外国税额控除不计）
DIV_NET = {"JP": 1 - 0.20315, "US": 0.9 * (1 - 0.20315)}


class YFinanceActions:
    """yfinance Ticker.actions（Dividends / Stock Splits）。按票缓存 12 小时。"""

    def __init__(self, ttl_hours: float = 12.0):
        self.path = paths.sub("cache") / "actions.json"
        self.ttl = ttl_hours * 3600
        self.cache: dict = read_json(self.path, {}) or {}

    def actions(self, ticker: str) -> list[dict]:
        hit = self.cache.get(ticker)
        if hit and time.time() - float(hit.get("at", 0)) < self.ttl:
            return hit["rows"]
        import logging
        import yfinance as yf
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
        df = yf.Ticker(ticker).actions
        rows = []
        if df is not None and len(df):
            for ts, r in df.iterrows():
                div = float(r.get("Dividends", 0) or 0)
                spl = float(r.get("Stock Splits", 0) or 0)
                if div > 0 or spl > 0:
                    rows.append({"date": str(ts.date()), "dividend": div, "split": spl})
        self.cache[ticker] = {"at": time.time(), "rows": rows}
        write_json(self.path, self.cache)
        return rows


class FakeActions:
    def __init__(self, rows: dict[str, list[dict]]):
        self.rows = rows

    def actions(self, ticker: str) -> list[dict]:
        return list(self.rows.get(ticker, []))


def due(provider, ticker: str, after: str, upto: str) -> list[dict]:
    """after < 日期 ≤ upto 的公司行为（字符串 YYYY-MM-DD 比较）。provider 失败时抛出异常，由调用方决定降级。"""
    if not after or not upto or after >= upto:
        return []
    return sorted((r for r in provider.actions(ticker) if after < r["date"] <= upto), key=lambda r: r["date"])


def infer_split(stored_close: float, adjusted_close_then: float) -> float | None:
    """provider 不可用时的兜底：同一根 K 线，昨天记下的真实收盘 vs 今天拿到的复权收盘。
    比值 ≤0.8 或 ≥1.25 只可能是拆股 / 合股（分红不会这么大）。返回拆股比例 k（1→k），否则 None。"""
    if not stored_close or not adjusted_close_then or stored_close <= 0:
        return None
    r = adjusted_close_then / stored_close
    if 0.8 < r < 1.25:
        return None
    k = 1 / r
    for nice in (1.5, 2, 3, 4, 5, 10, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10):
        if abs(k / nice - 1) < 0.03:
            return nice
    return round(k, 4)


def split_qty(qty: int, k: float, lot: int = 1) -> int:
    """拆股后的股数（向下取整到 1 股；日本株单元未满部分在真实账户里会变成端株，这里忽略）。"""
    return int(qty * k + 1e-6)


def today_str(d: dt.date | str) -> str:
    return d if isinstance(d, str) else d.isoformat()
