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
    monkeypatch.setattr(D, "_yf_intraday", lambda t, days=5, interval="5m": (_ for _ in ()).throw(RuntimeError("Yahoo 不通")))   # 分钟线也取不到
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


# ───────── 2026-09-29：Yahoo 拆股当天的分红口径、指数日线缺收盘用分钟线合成、缓存口径版本 ─────────
def _raw(closes, divs=None, splits=None, start="2026-09-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    c = np.array(closes, float)
    df = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Adj Close": c, "Volume": 1e5,
                       "Dividends": 0.0, "Stock Splits": 0.0}, index=idx)
    for i, v in (divs or {}).items():
        df.iloc[i, df.columns.get_loc("Dividends")] = v
    for i, v in (splits or {}).items():
        df.iloc[i, df.columns.get_loc("Stock Splits")] = v
    return df


def test_adjust_prices_replicates_yahoo_dividend_factor():
    raw = _raw([100, 100, 100, 99, 99, 99], divs={3: 1.0})                                 # 第 4 天除息 1 円（前收 100 → 1%）
    out, acts = D.adjust_prices(raw, "X.T")
    assert abs(out["Close"].iloc[0] - 99.0) < 1e-9 and abs(out["Close"].iloc[2] - 99.0) < 1e-9   # 除息日之前 × (1 − 1%)
    assert abs(out["Close"].iloc[3] - 99.0) < 1e-9 and abs(out["Open"].iloc[1] - 99.0) < 1e-9     # 之后不动；四价一起调
    assert acts["div"] == {str(raw.index[3].date()): 1.0} and acts["fixes"] == [] and acts["split"] == {}


def test_split_day_dividend_in_presplit_units_is_rescaled():
    # 8766.T 2026-09-29：Yahoo 价格已按 1 拆 15 调整（前收 538.33）、分红 122.5 是拆股前每股 → 22.8% 的分红把之前整体调低；当天实际 −2.8%
    raw = _raw([530, 532.8, 538.3333, 523.2, 525], divs={3: 122.5}, splits={3: 15.0})
    out, acts = D.adjust_prices(raw, "8766.T")
    assert len(acts["fixes"]) == 1 and acts["fixes"][0]["yield_fixed"] == 1.52 and acts["fixes"][0]["yield_yahoo"] == 22.76
    r = out["Close"].iloc[3] / out["Close"].iloc[2] - 1
    assert -0.02 < r < -0.01                                                               # 修正后当天 −1.3%（不是 +25.8%）
    assert acts["split"] == {str(raw.index[3].date()): 15.0}
    # 拆股前口径明显更符合当天跌幅（差 ≥ 1 pp）→ 保留 Yahoo 的：分红 5.4%、1 拆 3 当天跌 6.9%
    raw2 = _raw([100, 100, 100, 93.09, 93], divs={3: 5.4}, splits={3: 3.0})
    out2, acts2 = D.adjust_prices(raw2, "Y.T")
    assert acts2["fixes"] == [] and abs(acts2["div"][str(raw2.index[3].date())] - 5.4) < 1e-6
    # 特别分红没有拆股（3659.T：分红 415、前收 3068、当天 −14.4%）→ 照 Yahoo 的口径、不算修正
    raw3 = _raw([3100, 3116, 3068, 2625.5, 2630], divs={3: 415.0})
    out3, acts3 = D.adjust_prices(raw3, "3659.T")
    assert acts3["fixes"] == [] and abs(acts3["div"][str(raw3.index[3].date())] - 13.5267) < 0.01


def test_cache_with_old_adjustment_version_is_refetched(tmp_path, monkeypatch):
    from qbreak import paths
    monkeypatch.setattr(paths, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(D, "_has_parquet", lambda: False)
    df = _bars("2026-09-29")
    D.ACTIONS["Z.T"] = {"div": {"2026-09-10": 1.0}, "split": {}, "fixes": []}
    D._write_cache("Z.T", 2, df, "yfinance")
    D.ACTIONS.pop("Z.T")
    got = D._read_cache("Z.T", 2, 12)
    assert got is not None and len(got) == len(df) and D.actions_of("Z.T")["div"] == {"2026-09-10": 1.0}
    meta = D._meta_path("Z.T", 2)
    import json
    m = json.loads(meta.read_text(encoding="utf-8"))
    assert m["adj"] == D.ADJ_VERSION
    m["adj"] = 1
    meta.write_text(json.dumps(m), encoding="utf-8")
    assert D._read_cache("Z.T", 2, 12) is None                                              # 旧口径 → 当作没有缓存


def _bars5m(day: str, o=65558.0, h=65805.0, lo=64699.0, c=65209.0, n=68):
    idx = pd.date_range(f"{day} 09:00", periods=n, freq="5min", tz=cj.JST)
    x = np.linspace(o, c, n)
    df = pd.DataFrame({"Open": x, "High": x + 10, "Low": x - 10, "Close": x, "Volume": 1e6}, index=idx)
    df.iloc[0, df.columns.get_loc("Open")] = o
    df.iloc[n // 2, df.columns.get_loc("High")] = h
    df.iloc[n // 3, df.columns.get_loc("Low")] = lo
    df.iloc[-1, df.columns.get_loc("Close")] = c
    return df


def test_index_missing_close_is_filled_from_intraday(monkeypatch, tmp_path):
    from qbreak import paths
    monkeypatch.setattr(paths, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(D, "_has_parquet", lambda: False)
    _at(monkeypatch, 2026, 9, 30, 6, 57)                                                    # 09-30 早上：应有 09-29
    monkeypatch.setattr(D, "_now_utc", lambda: dt.datetime(2026, 9, 29, 21, 57, tzinfo=dt.timezone.utc))
    monkeypatch.setattr(D.time, "sleep", lambda s: None)
    daily = _bars("2026-09-28")                                                             # Yahoo 日线只到 09-28（09-29 收盘 NaN 被丢）
    monkeypatch.setattr(D, "_yf_download", lambda batch, years, tries: {t: daily.copy() for t in batch})
    calls = []

    def fake_intraday(t, days=5, interval="5m"):
        calls.append(t)
        return pd.concat([_bars5m("2026-09-28", c=65877.0), _bars5m("2026-09-29")])
    monkeypatch.setattr(D, "_yf_intraday", fake_intraday)
    D.FILLED.clear()
    D.LAGGING.clear()
    got = D.load_universe(["^N225", "7203.T"], DataConfig(provider="yfinance", years=2, allow_synthetic=False).validate())
    n = got["^N225"]
    assert str(n.index[-1].date()) == "2026-09-29" and abs(n["Close"].iloc[-1] - 65209.0) < 1e-6
    assert abs(n["Open"].iloc[-1] - 65558.0) < 1e-6 and abs(n["High"].iloc[-1] - 65805.0) < 1e-6 and abs(n["Low"].iloc[-1] - 64699.0) < 1e-6
    assert "^N225" not in D.LAGGING and D.FILLED["^N225"]["dates"] == ["2026-09-29"] and calls == ["^N225"]
    assert str(got["7203.T"].index[-1].date()) == "2026-09-28" and "7203.T" in D.LAGGING      # 个股不合成，照记落后
    import json
    m = json.loads(D._meta_path("^N225", 2).read_text(encoding="utf-8"))
    assert m["filled"] == ["2026-09-29"] and m["last"] == "2026-09-29"
    # 分钟线不够一天（< 30 根）或今天还没收盘 → 不合成
    D.FILLED.clear()
    monkeypatch.setattr(D, "_yf_intraday", lambda t, days=5, interval="5m": _bars5m("2026-09-29", n=10))
    assert D.fill_index_from_intraday("^N225", daily.copy()) is daily or len(D.fill_index_from_intraday("^N225", daily.copy())) == len(daily)
    _at(monkeypatch, 2026, 9, 29, 11, 0)                                                    # 09-29 盘中：应有 09-28 → 不落后、不合成
    assert D.fill_index_from_intraday("^N225", daily.copy()) is not None and not D.FILLED
