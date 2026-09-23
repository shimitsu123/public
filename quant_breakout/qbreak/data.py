"""data.py — 行情数据层（データ取得）。

相对原版的关键改动
  1. **合成数据默认关闭**。原版 `allow_synthetic=True`：yfinance 一失败就静默造假数据，
     回测照样打印漂亮的 CAGR —— 这是最危险的默认值。现在必须显式 `--synthetic`，
     且所有产出文件会被打上 SYNTHETIC 标记。
  2. **缓存带 TTL 和元数据**。原版 parquet 缓存永不过期，第二天跑的还是昨天的数据。
  3. **批量下载**。原版逐只 download，20 只 = 20 次请求，yfinance 很容易限流。
  4. **数据质量检查**：重复日期、非单调、负价、零成交量、未处理拆股造成的异常跳变。
  5. 不依赖 pyarrow：没装就自动退回 CSV。
  6. 新增 CSV provider —— 可以用券商/RSS 导出的本地数据，彻底摆脱 yfinance 的不确定性。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import paths
from .config import DataConfig
from .utils import retry, setup_logging

log = setup_logging("data")
OHLCV = ["Open", "High", "Low", "Close", "Volume"]


class DataError(RuntimeError):
    pass


# ────────────────────────── 缓存 ──────────────────────────
def _has_parquet() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


def _cache_path(ticker: str, years: int) -> Path:
    safe = ticker.replace("/", "_").replace("^", "idx_")
    ext = "parquet" if _has_parquet() else "csv"
    return paths.cache_dir() / f"{safe}_{years}y.{ext}"


def _meta_path(ticker: str, years: int) -> Path:
    return _cache_path(ticker, years).with_suffix(".meta.json")


def _read_cache(ticker: str, years: int, ttl_hours: float) -> pd.DataFrame | None:
    fp, mp = _cache_path(ticker, years), _meta_path(ticker, years)
    if not fp.exists() or not mp.exists():
        return None
    try:
        meta = json.loads(mp.read_text(encoding="utf-8"))
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(meta["fetched_at"])).total_seconds() / 3600
        if age > ttl_hours:
            return None
        df = (pd.read_parquet(fp) if fp.suffix == ".parquet"
              else pd.read_csv(fp, index_col=0, parse_dates=True))
        df.index = pd.DatetimeIndex(df.index)
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("缓存读取失败 %s: %s", fp.name, e)
        return None


def _write_cache(ticker: str, years: int, df: pd.DataFrame, source: str) -> None:
    fp = _cache_path(ticker, years)
    try:
        if fp.suffix == ".parquet":
            df.to_parquet(fp)
        else:
            df.to_csv(fp)
        _meta_path(ticker, years).write_text(json.dumps({
            "ticker": ticker, "rows": len(df), "source": source,
            "first": str(df.index[0].date()), "last": str(df.index[-1].date()),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("缓存写入失败 %s: %s", fp.name, e)


# ────────────────────────── 质量检查 ──────────────────────────
def validate_ohlcv(ticker: str, df: pd.DataFrame, cfg: DataConfig) -> pd.DataFrame:
    if df is None or df.empty:
        raise DataError(f"{ticker}: 无数据")
    df = df[[c for c in OHLCV if c in df.columns]].copy()
    if len(df.columns) < 5:
        raise DataError(f"{ticker}: 缺少列 {set(OHLCV) - set(df.columns)}")
    df = df.apply(pd.to_numeric, errors="coerce")
    df.index = pd.DatetimeIndex(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df.index = df.index.normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df["Volume"] = df["Volume"].fillna(0)

    bad = (df[["Open", "High", "Low", "Close"]] <= 0).any(axis=1)
    if bad.any():
        log.warning("%s: 丢弃 %d 根非正价格 K 线", ticker, int(bad.sum()))
        df = df[~bad]
    # High/Low 一致性（某些数据源偶发错位）
    fix = (df["High"] < df["Low"])
    if fix.any():
        log.warning("%s: %d 根 K 线 High<Low，已丢弃", ticker, int(fix.sum()))
        df = df[~fix]
    df["High"] = df[["High", "Open", "Close"]].max(axis=1)
    df["Low"] = df[["Low", "Open", "Close"]].min(axis=1)

    if len(df) < cfg.min_bars:
        raise DataError(f"{ticker}: 只有 {len(df)} 根 K 线，少于 min_bars={cfg.min_bars}")
    jump = df["Close"].pct_change().abs() * 100
    nj = int((jump > cfg.max_daily_move_pct).sum())
    if nj:
        log.warning("%s: %d 天单日变动 >%.0f%%，可能是未复权的拆股/合并，请核对",
                    ticker, nj, cfg.max_daily_move_pct)
    return df


# ────────────────────────── 合成数据（仅调试）──────────────────────────
def synthetic(ticker: str, years: int, seed: int | None = None) -> pd.DataFrame:
    """带「横盘→突破」结构的假数据。**任何基于它的收益数字都没有意义。**
    seed 由 ticker 稳定派生（原版用内置 hash()，受 PYTHONHASHSEED 影响每次运行都不同，
    结果无法复现）。"""
    import zlib
    rng = np.random.default_rng(seed if seed is not None else zlib.crc32(ticker.encode()))
    n = max(int(years * 252), 300)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    regime, i = np.zeros(n), 0
    while i < n:
        L = int(rng.integers(40, 120))
        regime[i:i + L] = rng.choice([0, 1], p=[0.7, 0.3])
        i += L
    vol = np.where(regime == 0, 0.008, 0.02)
    drift = np.where(regime == 0, 0.0, rng.choice([-0.002, 0.003], size=n))
    ret = rng.normal(drift, vol)
    close = 1000 * np.exp(np.cumsum(ret))
    high = close * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.006, n)))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.003, n))
    volume = rng.lognormal(13, 0.4, n) * np.where(regime == 1, 1.6, 1.0)
    df = pd.DataFrame({"Open": open_, "High": np.maximum.reduce([high, open_, close]),
                       "Low": np.minimum.reduce([low, open_, close]), "Close": close,
                       "Volume": volume}, index=idx)
    df.index.name = "Date"
    return df


# ────────────────────────── Provider ──────────────────────────
def _yf_download(tickers: list[str], years: int, attempts: int = 3) -> dict[str, pd.DataFrame]:
    import yfinance as yf
    # yfinance 自带的 logger 在网络不通时会刷屏，这里降噪（错误仍由我们自己的日志报告）
    for nm in ("yfinance", "yfinance.data", "yfinance.utils", "peewee"):
        logging.getLogger(nm).setLevel(logging.CRITICAL)
    cfg_attempts = [max(1, attempts)]
    out: dict[str, pd.DataFrame] = {}

    def _dl():
        return yf.download(tickers, period=f"{years}y", interval="1d", auto_adjust=True,
                           progress=False, group_by="ticker", threads=False)

    raw = retry(_dl, attempts=cfg_attempts[0], base_delay=1.5, log=log)
    if raw is None or raw.empty:
        raise DataError("yfinance 返回空数据（可能被限流或代码错误）")
    if isinstance(raw.columns, pd.MultiIndex):
        for t in tickers:
            if t in raw.columns.get_level_values(0):
                out[t] = raw[t].dropna(how="all")
    else:                                   # 单只股票时 yfinance 返回单层列
        out[tickers[0]] = raw.dropna(how="all")
    return out


def _csv_load(ticker: str, cfg: DataConfig) -> pd.DataFrame:
    """本地 CSV：var/csv/<ticker>.csv，列 Date,Open,High,Low,Close,Volume。
    用于把券商/RSS 导出的数据接进来（推荐：实盘与回测同源，避免 yfinance 复权差异）。"""
    fp = paths.sub("csv") / f"{csv_name(ticker)}.csv"
    if not fp.exists():
        raise DataError(f"{ticker}: 找不到 {fp}")
    df = pd.read_csv(fp)
    dcol = next((c for c in df.columns if c.lower() in ("date", "日付", "日付け", "datetime")), None)
    if dcol is None:
        raise DataError(f"{fp}: 找不到日期列")
    df = df.rename(columns={dcol: "Date"}).set_index("Date")
    df.index = pd.to_datetime(df.index)
    df.columns = [c.capitalize() if c.lower() in
                  ("open", "high", "low", "close", "volume") else c for c in df.columns]
    return df


def csv_name(ticker: str) -> str:
    return ticker.replace("/", "_").replace("^", "idx_").replace("=", "_")


def dump_csv(data: dict[str, pd.DataFrame]) -> int:
    """把 {ticker: OHLCV} 写到 var/csv/，供没有外网的机器用 --provider csv 读取。"""
    n = 0
    for t, df in data.items():
        out = df[[c for c in OHLCV if c in df.columns]].copy()
        out.index.name = "Date"
        (paths.sub("csv") / f"{csv_name(t)}.csv").write_text(out.to_csv(), encoding="utf-8")
        n += 1
    return n


# ────────────────────────── 对外入口 ──────────────────────────
def load_universe(tickers: list[str], cfg: DataConfig | None = None,
                  use_cache: bool = True) -> dict[str, pd.DataFrame]:
    """返回 {ticker: OHLCV DataFrame}。失败的标的会被跳过并记录，
    全部失败时抛异常（而不是像原版那样悄悄换成假数据继续跑）。"""
    cfg = (cfg or DataConfig()).validate()
    out: dict[str, pd.DataFrame] = {}
    todo: list[str] = []

    for t in tickers:
        c = _read_cache(t, cfg.years, cfg.cache_ttl_hours) if use_cache else None
        if c is not None:
            try:
                out[t] = validate_ohlcv(t, c, cfg)
                continue
            except DataError as e:
                log.warning("缓存数据不合格，重新下载: %s", e)
        todo.append(t)

    if todo and cfg.provider == "yfinance":
        for k in range(0, len(todo), cfg.batch_size):
            batch = todo[k:k + cfg.batch_size]
            try:
                got = _yf_download(batch, cfg.years, cfg.retry_attempts)
            except Exception as e:  # noqa: BLE001
                log.error("批量下载失败(%s): %s", type(e).__name__, e)
                got = {}
            for t in batch:
                df = got.get(t)
                try:
                    if df is None:
                        raise DataError(f"{t}: yfinance 未返回该代码")
                    df = validate_ohlcv(t, df, cfg)
                    out[t] = df
                    _write_cache(t, cfg.years, df, "yfinance")
                except DataError as e:
                    log.error("跳过 %s：%s", t, e)
            time.sleep(0.5)                     # 轻微退避，别把 yfinance 打挂
    elif todo:
        for t in todo:
            try:
                out[t] = validate_ohlcv(t, _csv_load(t, cfg), cfg)
            except DataError as e:
                log.error("跳过 %s：%s", t, e)

    missing = [t for t in tickers if t not in out]
    if missing and cfg.allow_synthetic:
        log.warning("★★★ 以下标的改用【合成数据】，结果没有任何投资参考价值：%s", missing)
        for t in missing:
            out[t] = synthetic(t, cfg.years)
    if not out:
        raise DataError(
            "没有取到任何行情数据。请检查：①网络/代理 ②yfinance 是否被限流"
            "（稍后重试或改用 --provider csv）③股票代码是否正确。"
            "若只是想跑通流程，加 --synthetic（结果不可用于决策）。")
    if missing and not cfg.allow_synthetic:
        log.warning("有 %d 只标的缺数据，已从股票池剔除：%s", len(missing), missing)
    return out


def freshness(df: pd.DataFrame) -> tuple[pd.Timestamp, int]:
    """返回 (最新 K 线日期, 距今自然日)。实盘前用来确认拿到的是今天的收盘数据。"""
    last = df.index[-1]
    return last, (pd.Timestamp.today().normalize() - last.normalize()).days


def realtime_quotes(tickers: list[str]) -> dict[str, float]:
    """yfinance 的分钟线最新价。**東証は 15~20 分遅延**なので、
    実弾では使わないこと（券商 API の現在値を使う）。
    用途は一つ：立花の口座が開くまでの間、`daemon --broker paper` で
    守护进程の挙動をリハーサルすること。"""
    import yfinance as yf
    for nm in ("yfinance", "yfinance.data", "yfinance.utils"):
        logging.getLogger(nm).setLevel(logging.CRITICAL)
    out: dict[str, float] = {}
    try:
        raw = yf.download(tickers, period="1d", interval="1m", progress=False,
                          group_by="ticker", threads=False, auto_adjust=False)
    except Exception as e:  # noqa: BLE001
        log.warning("实时报价获取失败: %s", e)
        return out
    if raw is None or raw.empty:
        return out
    for t in tickers:
        try:
            col = raw[t]["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw["Close"]
            v = col.dropna()
            if len(v):
                out[t] = float(v.iloc[-1])
        except (KeyError, IndexError):
            continue
    return out
