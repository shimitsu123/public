"""行情缓存的新鲜度：有效期内但缺了应有的最近交易日（Yahoo 晚更新）→ 重新下载；重下载失败退回旧缓存并记为落后。"""
import datetime as dt

import numpy as np
import pandas as pd

import qbreak.calendar_jp as cj
from qbreak import data as D
from qbreak.config import DataConfig


def _bars(end: str, n: int = 300) -> pd.DataFrame:
    idx = pd.bdate_range(end=end, periods=n)
    c = np.linspace(100, 120, n)
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6}, index=idx)


def _at(monkeypatch, y, m, d, hh, mm=0):
    monkeypatch.setattr(cj, "now_jst", lambda: dt.datetime(y, m, d, hh, mm, tzinfo=cj.JST))


def test_behind_uses_trading_calendar(monkeypatch):
    _at(monkeypatch, 2026, 9, 25, 17)                       # 金曜 17:00（收盘后）→ 日本应有 9/25
    assert D.behind("^N225", _bars("2026-09-18")) == ("2026-09-18", "2026-09-25")
    assert D.behind("7203.T", _bars("2026-09-25")) is None
    _at(monkeypatch, 2026, 9, 25, 10)                       # 盘中 → 应有上一交易日 9/24（9/21–23 连休）
    assert D.behind("^N225", _bars("2026-09-24")) is None and D.behind("^N225", _bars("2026-09-18"))
    assert D.behind("JPY=X", _bars("2026-01-05")) is None   # 汇率 / 期货不查


def test_stale_cache_within_ttl_is_refetched_or_flagged(monkeypatch):
    _at(monkeypatch, 2026, 9, 25, 17)
    cfg = DataConfig(provider="yfinance", years=10, allow_synthetic=False)
    D._write_cache("^N225", 10, _bars("2026-09-18"), "yfinance")          # 刚下载（有效期内），但停在 9/18
    monkeypatch.setattr(D, "_yf_download", lambda batch, years, tries: {t: _bars("2026-09-25") for t in batch})
    monkeypatch.setattr(D.time, "sleep", lambda s: None)
    got = D.load_universe(["^N225"], cfg)
    assert got["^N225"].index[-1] == pd.Timestamp("2026-09-25") and "^N225" not in D.LAGGING
    D._write_cache("^N225", 10, _bars("2026-09-18"), "yfinance")

    def boom(batch, years, tries):
        raise RuntimeError("Yahoo 不通")
    monkeypatch.setattr(D, "_yf_download", boom)
    got = D.load_universe(["^N225"], cfg)                                  # 重下载失败 → 旧缓存兜底 + 记为落后
    assert got["^N225"].index[-1] == pd.Timestamp("2026-09-18")
    assert D.LAGGING["^N225"] == {"last": "2026-09-18", "expected": "2026-09-25"}
    D.LAGGING.clear()
