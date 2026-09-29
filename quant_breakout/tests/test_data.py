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


def _meta_fetched(t, years, iso):
    mp = D._meta_path(t, years)
    import json
    m = json.loads(mp.read_text(encoding="utf-8"))
    m["fetched_at"] = iso
    mp.write_text(json.dumps(m), encoding="utf-8")


def test_partial_cached_detects_intraday_snapshot():
    f = dt.datetime.fromisoformat("2026-09-29T00:32:00+00:00")                  # 09:32 JST 取的：9/29 那根还没收盘
    df = _bars("2026-09-29")
    at = lambda iso: dt.datetime.fromisoformat(iso)                              # noqa: E731
    assert D.partial_cached("2432.T", df, f, now=at("2026-09-29T12:10:00+00:00"))        # 21:10 JST：已收盘 → 要重新下载
    assert not D.partial_cached("2432.T", df, f, now=at("2026-09-29T02:00:00+00:00"))    # 11:00 JST 还在盘中 → 不管
    assert not D.partial_cached("2432.T", df, at("2026-09-29T07:00:00+00:00"),           # 16:00 JST 取的：已收盘，完整
                                now=at("2026-09-29T12:10:00+00:00"))
    assert not D.partial_cached("2432.T", _bars("2026-09-28"), f, now=at("2026-09-29T12:10:00+00:00"))  # 最后一根是前一天
    us = _bars("2026-09-28")                                                     # 美股：14:00 ET 取的 9/28
    fu = at("2026-09-28T18:00:00+00:00")
    assert D.partial_cached("SPY", us, fu, now=at("2026-09-28T21:30:00+00:00"))            # 17:30 ET 已收盘
    assert not D.partial_cached("SPY", us, fu, now=at("2026-09-28T19:00:00+00:00"))        # 15:00 ET 还在盘中
    assert not D.partial_cached("JPY=X", df, f, now=at("2026-09-29T12:10:00+00:00"))       # 汇率 / 期货不管
    assert not D.partial_cached("2432.T", df, None)


def test_intraday_cache_is_refetched_after_close(monkeypatch):
    _at(monkeypatch, 2026, 9, 29, 21, 10)                                        # 收盘后、缓存取了不到 12 小时
    monkeypatch.setattr(D, "_now_utc", lambda: dt.datetime(2026, 9, 29, 12, 10, tzinfo=dt.timezone.utc))
    monkeypatch.setattr(D.time, "sleep", lambda s: None)
    cfg = DataConfig(provider="yfinance", years=10, allow_synthetic=False)
    snap = _bars("2026-09-29")
    snap.iloc[-1, snap.columns.get_loc("Volume")] = 114_900                      # 盘中快照：成交量很小
    D._write_cache("7203.T", 10, snap, "yfinance")
    _meta_fetched("7203.T", 10, "2026-09-29T00:32:00+00:00")
    full = _bars("2026-09-29")
    full.iloc[-1, full.columns.get_loc("Volume")] = 2_061_100
    monkeypatch.setattr(D, "_yf_download", lambda batch, years, tries: {t: full for t in batch})
    got = D.load_universe(["7203.T"], cfg)
    assert got["7203.T"]["Volume"].iloc[-1] == 2_061_100 and "7203.T" not in D.LAGGING
    D._write_cache("7203.T", 10, snap, "yfinance")
    _meta_fetched("7203.T", 10, "2026-09-29T00:32:00+00:00")

    def boom(batch, years, tries):
        raise RuntimeError("Yahoo 不通")
    monkeypatch.setattr(D, "_yf_download", boom)
    got = D.load_universe(["7203.T"], cfg)                                        # 重下载失败：不拿盘中快照兜底
    assert got["7203.T"].index[-1] == pd.Timestamp("2026-09-28")
    assert D.LAGGING["7203.T"] == {"last": "2026-09-28", "expected": "2026-09-29"}
    D.LAGGING.clear()
    D._write_cache("7203.T", 10, snap, "yfinance")                               # 盘中再读（还没收盘）→ 用缓存，不重新下载
    _meta_fetched("7203.T", 10, "2026-09-29T00:32:00+00:00")
    _at(monkeypatch, 2026, 9, 29, 11, 0)
    monkeypatch.setattr(D, "_now_utc", lambda: dt.datetime(2026, 9, 29, 2, 0, tzinfo=dt.timezone.utc))
    got = D.load_universe(["7203.T"], cfg)
    assert got["7203.T"]["Volume"].iloc[-1] == 114_900
