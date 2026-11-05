"""earnings_hist.py — 个股的历史决算发表日与 EPS 惊喜（yfinance get_earnings_dates = Yahoo 的决算日历：分析师 EPS 预期、
实际 EPS、惊喜 %）。研究用（scripts/earnings_study.py）；缓存 var/cache/earnings_hist/（var/cache 已 gitignore，原始数据不入库）。

日期：Yahoo 的时间戳是美东时区 → 换成日本时间只取日期 D（时刻不可靠：很多记录是占位的 0 点）。
用法上的保守约定（earnings_features）：信号日 s 只用 D < s 的发表（严格早于信号日）；发表反应 EAR 用 D 之前最后一个交易日的收盘
→ D 之后第一个交易日的收盘（两天窗口，盘中发表、收盘后发表都包括在内），这个收盘 ≤ s 的收盘，所以信号日收盘时已知。
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import paths

COLS = ["date", "eps_est", "eps_rep", "surprise"]
MAX_AGE_DAYS = 20.0


def cache_dir() -> Path:
    return paths.sub("cache/earnings_hist")


def parse(df: pd.DataFrame | None) -> pd.DataFrame:
    """yfinance 的 earnings_dates → 列 date（日本日期）、eps_est、eps_rep、surprise（%）；同一天多条只留第一条。"""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=COLS)
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("America/New_York")
    d = idx.tz_convert("Asia/Tokyo").tz_localize(None).normalize()
    col = lambda name: pd.to_numeric(df[name], errors="coerce").to_numpy() if name in df.columns else np.full(len(df), np.nan)  # noqa: E731
    out = pd.DataFrame({"date": d, "eps_est": col("EPS Estimate"), "eps_rep": col("Reported EPS"), "surprise": col("Surprise(%)")})
    return out.drop_duplicates("date", keep="first").sort_values("date").reset_index(drop=True)


def fetch(ticker: str, max_age_days: float = MAX_AGE_DAYS, tries: int = 3, getter=None, wait: float = 2.0) -> pd.DataFrame:
    """一只票的历史决算（缓存 max_age_days 天；下载失败等 wait × 2^k 秒重试；都失败退回旧缓存；没有缓存 → 抛错）。"""
    fp = cache_dir() / f"{ticker}.csv"
    if fp.exists() and time.time() - fp.stat().st_mtime < max_age_days * 86400:
        return pd.read_csv(fp, parse_dates=["date"])
    if getter is None:
        def getter(t):
            import logging

            import yfinance as yf
            logging.getLogger("yfinance").setLevel(logging.CRITICAL)
            return yf.Ticker(t).get_earnings_dates(limit=100)
    last: Exception | None = None
    for k in range(tries):
        try:
            out = parse(getter(ticker))
            out.to_csv(fp, index=False)
            return out
        except Exception as e:                                         # noqa: BLE001
            last = e
            if wait:
                time.sleep(wait * (2 ** k))
    if fp.exists():
        return pd.read_csv(fp, parse_dates=["date"])
    raise RuntimeError(f"{ticker} 的决算日历取不到：{type(last).__name__}: {last}")


def load_many(tickers: list[str], pause: float = 0.3, getter=None) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """多只：{票: 表}，{票: 失败原因}。"""
    got, bad = {}, {}
    for t in tickers:
        fp = cache_dir() / f"{t}.csv"
        fresh = fp.exists() and time.time() - fp.stat().st_mtime < MAX_AGE_DAYS * 86400
        try:
            got[t] = fetch(t, getter=getter)
        except Exception as e:                                         # noqa: BLE001
            bad[t] = f"{type(e).__name__}: {e}"[:160]
        if not fresh and pause:
            time.sleep(pause)
    return got, bad


def earnings_features(close: pd.Series, index_close: pd.Series, E: pd.DataFrame, dates, stale: int = 70,
                      recent: int = 20) -> pd.DataFrame:
    """信号日（这只票的交易日）→ 最近一次已发表决算（D < 信号日）的特征：
    days_since（交易日数）、surprise（%）、ear（发表反应：D 之前最后一个交易日收盘 → D 之后第一个交易日收盘的对数收益 − 日経同窗口，%）、
    ear_recent（days_since ≤ recent 时 = ear，否则 0）。离上次发表 > stale 个交易日（数据缺了一季）→ 全部缺值。"""
    ix = close.index
    cl = np.log(close.where(close > 0)).to_numpy(float)
    ic = np.log(index_close.reindex(ix).ffill().where(lambda s: s > 0)).to_numpy(float)
    ed = pd.DatetimeIndex(pd.to_datetime(E["date"])).sort_values() if len(E) else pd.DatetimeIndex([])
    sur = pd.Series(pd.to_numeric(E["surprise"], errors="coerce").to_numpy(float), index=pd.DatetimeIndex(pd.to_datetime(E["date"]))
                    ).sort_index() if len(E) else pd.Series(dtype=float)
    rows = []
    for s in pd.DatetimeIndex(dates):
        k = int(ed.searchsorted(s, side="left")) - 1                   # 最近一次 D < s
        si = int(ix.searchsorted(s, side="left"))
        if k < 0 or si >= len(ix) or ix[si] != s:
            rows.append((np.nan, np.nan, np.nan, np.nan))
            continue
        D = ed[k]
        p = int(ix.searchsorted(D, side="left"))                       # D 本身（是交易日时）或 D 之后第一个交易日
        a, b = p - 1, int(ix.searchsorted(D, side="right"))            # D 之前最后一个交易日、D 之后第一个交易日
        days = si - p + (0 if p < len(ix) and ix[p] == D else 1)       # 信号日离 D 几个交易日（D 的第二天 = 1）
        if a < 0 or b > si or days > stale:
            rows.append((np.nan, np.nan, np.nan, np.nan))
            continue
        ear = (cl[b] - cl[a]) * 100 - (ic[b] - ic[a]) * 100
        sv = sur.iloc[k] if k < len(sur) else np.nan
        rows.append((float(days), float(sv) if np.isfinite(sv) else np.nan, float(ear) if np.isfinite(ear) else np.nan,
                     (float(ear) if days <= recent else 0.0) if np.isfinite(ear) else np.nan))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(dates), columns=["days_since", "surprise", "ear", "ear_recent"])
