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
  7. 盘中取的缓存（最后一根是还没收盘的当日 K 线）在那个市场收盘后视为过期、重新下载（2026-09-29 空跑时发现：
     有效期 12 小时内会把盘中快照当成收盘价）；重下载失败就去掉那一根兜底并记为落后。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
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


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


ADJ_VERSION = 2                    # 价格调整口径的版本：2 = 自己按 Yahoo 的分红 / 拆股记录调整（拆股当天的分红按拆股后口径）；缓存口径不同 → 重新下载
ACTIONS: dict[str, dict] = {}      # 本进程里每只票的公司行为（随缓存保存）：{"div": {日期: 分红率 %}, "split": {日期: 比例}, "fixes": [修正过的分红]}


def _read_cache(ticker: str, years: int, ttl_hours: float) -> pd.DataFrame | None:
    fp, mp = _cache_path(ticker, years), _meta_path(ticker, years)
    if not fp.exists() or not mp.exists():
        return None
    try:
        meta = json.loads(mp.read_text(encoding="utf-8"))
        age = (_now_utc()
               - datetime.fromisoformat(meta["fetched_at"])).total_seconds() / 3600
        if age > ttl_hours:
            return None
        if meta.get("source") == "yfinance" and meta.get("adj") != ADJ_VERSION:
            log.info("缓存 %s 是旧的价格调整口径（%s ≠ %s）→ 重新下载", fp.name, meta.get("adj"), ADJ_VERSION)
            return None
        df = (pd.read_parquet(fp) if fp.suffix == ".parquet"
              else pd.read_csv(fp, index_col=0, parse_dates=True))
        df.index = pd.DatetimeIndex(df.index)
        if meta.get("actions") is not None:
            ACTIONS[ticker] = meta["actions"]
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("缓存读取失败 %s: %s", fp.name, e)
        return None


def _write_cache(ticker: str, years: int, df: pd.DataFrame, source: str, extra: dict | None = None) -> None:
    fp = _cache_path(ticker, years)
    try:
        if fp.suffix == ".parquet":
            df.to_parquet(fp)
        else:
            df.to_csv(fp)
        meta = {"ticker": ticker, "rows": len(df), "source": source,
                "first": str(df.index[0].date()), "last": str(df.index[-1].date()),
                "fetched_at": datetime.now(timezone.utc).isoformat()}
        if source == "yfinance":
            meta["adj"] = ADJ_VERSION
            meta["actions"] = ACTIONS.get(ticker) or {"div": {}, "split": {}, "fixes": []}
        if extra:
            meta.update(extra)
        _meta_path(ticker, years).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("缓存写入失败 %s: %s", fp.name, e)


def actions_of(ticker: str) -> dict:
    """这只票的公司行为（本进程里下载或从缓存读到的）：{"div": {日期: 分红率 %}, "split": {日期: 比例}, "fixes": [...]}；没有 → 空。"""
    a = ACTIONS.get(ticker) or {}
    return {"div": dict(a.get("div") or {}), "split": dict(a.get("split") or {}), "fixes": list(a.get("fixes") or [])}


def fixes_of(tickers) -> list[dict]:
    """这些票里修正过的分红（日报「数据完整性 · 自动修复」用）。"""
    out = []
    for t in tickers:
        for f in actions_of(t)["fixes"]:
            out.append({"ticker": t, **f})
    return out


# ────────────────────────── 质量检查 ──────────────────────────
_SPLIT_K = (2, 3, 4, 5, 8, 10, 20, 25, 50, 100, 200)       # 200：1545.T 2026-05-22 的 1 拆 200（yfinance 没复权；2026-09-29 模拟盘演练时发现）


def repair_jp_artifacts(ticker: str, df: pd.DataFrame, max_iter: int = 10) -> pd.DataFrame:
    """日本株 / ETF 的行情修补。东证有涨跌停，单日 ×0.6 以下或 ×1.7 以上的收盘变动不可能真实发生，
    一定是数据问题（2026-09-24 在 yfinance 数据里实测到：1329.T 2014-01 的 1 拆 10 未复权、
    1306.T 2026-03-30 连续两天被缩小 10 倍后恢复、2269.T / 8766.T 等合并新设时的衔接错误）。
      ① 5 根 K 线内回到原价位附近 → 瞬时错误，删掉这几根
      ② 持续跳变且接近 1/k 或 k（k=2,3,4,5,8,10,…，误差 6% 内）→ 未复权拆股 / 合并，按 k 复权更早的历史
      ③ 其余持续跳变 → 截掉跳变之前的历史（衔接不上的旧数据）"""
    out = df
    for _ in range(max_iter):
        c = out["Close"].astype(float)
        r = (c / c.shift(1)).values
        bad = np.flatnonzero((r < 0.6) | (r > 1.7))
        if not len(bad):
            return out
        i = int(bad[0])
        base = float(c.iloc[i - 1])
        back = next((j for j in range(i + 1, min(i + 6, len(c))) if 0.6 <= float(c.iloc[j]) / base <= 1.7), None)
        if back is not None:
            log.warning("%s: %s～%s 共 %d 根 K 线价格异常后恢复，判定为瞬时错误并删除", ticker,
                        out.index[i].date(), out.index[back - 1].date(), back - i)
            out = out.drop(out.index[i:back])
            continue
        ratio = float(r[i])
        k = next((k for k in _SPLIT_K for f in (1 / k, k) if abs(ratio / f - 1) < 0.06), None)
        if k is not None:
            f = 1 / k if ratio < 1 else k
            log.warning("%s: %s 收盘 ×%.4f，判定为未复权的 %s（×%g），已复权更早的历史", ticker,
                        out.index[i].date(), ratio, "拆股" if ratio < 1 else "合并", f)
            out = out.astype({c: float for c in ("Open", "High", "Low", "Close", "Volume")})   # 整数型也要能写入小数
            prior = out.index[:i]
            for col in ("Open", "High", "Low", "Close"):
                out.loc[prior, col] = out.loc[prior, col] * f
            out.loc[prior, "Volume"] = out.loc[prior, "Volume"] / f
            continue
        log.warning("%s: %s 收盘 ×%.4f 且不像拆股，截掉此前 %d 根衔接不上的历史", ticker, out.index[i].date(), ratio, i)
        out = out.iloc[i:]
    return out


def drop_jp_holiday_rows(ticker: str, df: pd.DataFrame) -> pd.DataFrame:
    """东证休市日（祝日 / 年末年始 / 全日休场）上的行 = Yahoo 的假行（价格不动、成交量 0 或抄前一天）→ 去掉。
    2026-09-28 数据核对（scripts/data_audit.py）：2005〜2021 每只约 20〜60 行（多在 2005〜2006、2017〜2018），2022 年以后没有；
    要原样重现以前的研究结果：QB_KEEP_HOLIDAY_ROWS=1。"""
    import os
    if os.environ.get("QB_KEEP_HOLIDAY_ROWS") == "1" or df.empty:
        return df
    from .calendar_jp import is_trading_day
    keep = np.array([is_trading_day(d.date()) for d in df.index], bool)
    if not keep.all():
        log.info("%s: 去掉 %d 行东证休市日的行情（Yahoo 假行）", ticker, int((~keep).sum()))
        df = df[keep]
    return df


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
    if ticker.upper().endswith(".T"):
        df = drop_jp_holiday_rows(ticker, df)
        df = repair_jp_artifacts(ticker, df)

    if len(df) < cfg.min_bars:
        raise DataError(f"{ticker}: 只有 {len(df)} 根 K 线，少于 min_bars={cfg.min_bars}")
    jump = df["Close"].pct_change().abs() * 100
    nj = int((jump > cfg.max_daily_move_pct).sum())
    if nj and not ticker.startswith("^"):        # 指数（^VIX 等）不会拆股；VIX 单日 +60% 以上是真实行情（例如 2024-08-05）
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
DIV_FIX_TOL = 1.0                  # 拆股当天的分红：默认按拆股后口径；只有拆股前口径明显更符合当天实际跌幅（差 ≥ 1 pp）才保留 Yahoo 的
DIV_FIX_MIN_GAP = 0.5              # 两种口径的分红率差 ≥ 0.5 pp 才记成「修正」（日报列出）；更小的差静默按拆股后口径


def adjust_prices(raw: pd.DataFrame, ticker: str = "") -> tuple[pd.DataFrame, dict]:
    """Yahoo 的未调整行情（auto_adjust=False + actions=True：价格已按拆股调整、分红另列）→ 与 yfinance auto_adjust 同一口径的
    调整后 OHLCV（除息日之前的价格整体 × (1 − 分红 ÷ 前一日收盘)），但**拆股当天的分红**按市场实际的除权除息幅度判断口径：
    Yahoo 把日本株「拆股生效日同一天除息」的分红记成拆股前每股的金额（日本的惯例：分割与配当同一基準日时，配当按分割前的股数宣布；
    例 8766.T 2026-09-29：1 拆 15 当天的分红 122.5 円，Yahoo 当成当天 523 円股价的 22.8% 分红，把之前的价格整体调低 22.8% → 当天「涨」25.8%；
    5706.T 同日 1 拆 10 也是；2026-09-29 横向扫描 1,076 只近 2 年：20 例，没有反例），这里默认按「分红 ÷ 拆股比 ÷ 前收」，
    只有「分红 ÷ 前收」明显更符合当天实际的价格跌幅（当天收益 + 分红率 ≈ 0，差 ≥ 1 pp）才保留 Yahoo 的口径。
    返回 (OHLCV, {"div": {日期: 分红率 %}, "split": {日期: 比例}, "fixes": [{"date", "div", "split", "yield_yahoo", "yield_fixed"}]})。"""
    df = raw.dropna(subset=["Close"]).copy()
    if not len(df):
        return df, {"div": {}, "split": {}, "fixes": []}
    c = pd.to_numeric(df["Close"], errors="coerce").astype(float)
    div = pd.to_numeric(df["Dividends"], errors="coerce").fillna(0.0) if "Dividends" in df.columns else pd.Series(0.0, index=df.index)
    spl = pd.to_numeric(df["Stock Splits"], errors="coerce").fillna(0.0) if "Stock Splits" in df.columns else pd.Series(0.0, index=df.index)
    prev = c.shift(1)
    f = pd.Series(1.0, index=df.index)
    acts: dict = {"div": {}, "split": {}, "fixes": []}
    for d in df.index[spl.to_numpy(float) > 0]:
        if float(spl[d]) != 1.0:
            acts["split"][str(d.date())] = float(spl[d])
    for d in df.index[div.to_numpy(float) > 0]:
        p0 = float(prev[d]) if np.isfinite(prev[d]) else np.nan
        if not np.isfinite(p0) or p0 <= 0:
            continue
        y = float(div[d]) / p0
        s = float(spl[d])
        if s > 0 and s != 1.0:
            y2 = y / s
            r = float(c[d]) / p0 - 1
            z1, z2 = abs(r + y) * 100, abs(r + y2) * 100                  # 两种口径各自与当天实际跌幅的差（pp）
            if not (z1 + DIV_FIX_TOL < z2):                                # 拆股前口径没有明显更符合 → 按拆股后口径
                if abs(y - y2) * 100 >= DIV_FIX_MIN_GAP:
                    acts["fixes"].append({"date": str(d.date()), "div": float(div[d]), "split": s,
                                          "yield_yahoo": round(y * 100, 2), "yield_fixed": round(y2 * 100, 2)})
                    log.warning("%s %s：拆股 %g 当天的分红 %g 按拆股前口径（%.1f%%）→ 改按拆股后口径（%.2f%%）", ticker, d.date(), s,
                                float(div[d]), y * 100, y2 * 100)
                y = y2
        if y >= 1.0:
            log.warning("%s %s：分红率 %.0f%% 不合理，忽略这笔分红的调整", ticker, d.date(), y * 100)
            continue
        f[d] = 1.0 - y
        acts["div"][str(d.date())] = round(y * 100, 4)
    cum = f[::-1].cumprod()[::-1].shift(-1).fillna(1.0)            # 第 i 天的系数 = 之后所有除息日系数的乘积
    out = pd.DataFrame(index=df.index)
    for k in ("Open", "High", "Low", "Close"):
        out[k] = pd.to_numeric(df[k], errors="coerce").astype(float) * cum
    out["Volume"] = pd.to_numeric(df["Volume"], errors="coerce") if "Volume" in df.columns else np.nan
    return out, acts


def _yf_download(tickers: list[str], years: int, attempts: int = 3) -> dict[str, pd.DataFrame]:
    import yfinance as yf
    # yfinance 自带的 logger 在网络不通时会刷屏，这里降噪（错误仍由我们自己的日志报告）
    for nm in ("yfinance", "yfinance.data", "yfinance.utils", "peewee"):
        logging.getLogger(nm).setLevel(logging.CRITICAL)
    cfg_attempts = [max(1, attempts)]
    out: dict[str, pd.DataFrame] = {}

    def _dl():
        return yf.download(tickers, period=f"{years}y", interval="1d", auto_adjust=False, actions=True,
                           progress=False, group_by="ticker", threads=False)

    raw = retry(_dl, attempts=cfg_attempts[0], base_delay=1.5, log=log)
    if raw is None or raw.empty:
        raise DataError("yfinance 返回空数据（可能被限流或代码错误）")
    if isinstance(raw.columns, pd.MultiIndex):
        got = {t: raw[t] for t in tickers if t in raw.columns.get_level_values(0)}
    else:                                   # 单只股票时 yfinance 返回单层列
        got = {tickers[0]: raw}
    for t, df in got.items():
        df = df.dropna(how="all")
        if "Close" not in df.columns:
            continue
        out[t], ACTIONS[t] = adjust_prices(df, t)
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
LAGGING: dict[str, dict] = {}      # 本进程里重下载后仍落后于「按日历应有的最新交易日」的标的：{代码: {"last", "expected"}}


def _market_of(t: str) -> str | None:
    """行情新鲜度检查用的市场：日本（.T、日経 / TOPIX 指数）、美国（无后缀代码、美股指数）；汇率 / 期货 / 其他交易所不查。"""
    if t.endswith(".T") or t in ("^N225", "^TOPX", "^TPX"):
        return "JP"
    if "=" in t or "." in t:
        return None
    return "US"


def behind(t: str, df: pd.DataFrame | None) -> tuple[str, str] | None:
    """最新 K 线早于该市场按交易日历「现在应该已经拿到」的交易日 → (最新, 应有)；否则 None。"""
    m = _market_of(t)
    if m is None or df is None or not len(df):
        return None
    from .calendar_jp import now_jst
    from .trader import expected_last_bar
    exp = expected_last_bar(now_jst().date(), m)
    last = pd.Timestamp(df.index[-1]).date()
    return (str(last), str(exp)) if last < exp else None


FILLED: dict[str, dict] = {}       # 本进程里用分钟线合成的指数日线：{代码: {"dates": [...], "gap_dates": [中间缺的], "close": 最新合成收盘, "source": "yfinance 5m"}}
FILL_MIN_BARS = 30                 # 一天至少要有这么多根 5 分钟线才合成（日本 60〜68 根、美国 78 根）
GAP_LOOKBACK = 10                  # 中间缺日：日线最后一天之前往回看多少个交易日（Yahoo 的 5 分钟线只给最近约 60 天）
GAP_TICKERS = {"JP": ("^N225", "^TPX", "^TOPX"),
               "US": ("^GSPC", "^IXIC", "^NDX", "^DJI", "^RUT", "^SOX", "^VIX", "^VIX3M", "^SKEW", "^SP500TR")}
GAPS: dict[str, dict] = {}         # 本进程里中间缺日、5 分钟线也补不上的指数：{代码: {"dates": [...]}}（日报「数据完整性」列出）


def missing_days(ticker: str, df: pd.DataFrame | None, lookback: int = GAP_LOOKBACK) -> list:
    """日线最后一天之前 lookback 个交易日里（按该市场的交易日历）缺的日子。Yahoo 指数日线偶尔中间漏一天
    （例 ^N225 2026-10-05：有 10-02 与 10-06、没有 10-05）；behind 只看最后一天，查不出来。
    只查交易日历确定的指数（GAP_TICKERS：东证 / 纽约的股票指数）；欧洲指数、债券 / 商品指数的休市日不同，不查（免得误报）。"""
    m = next((k for k, v in GAP_TICKERS.items() if ticker in v), None)
    if m is None or df is None or len(df) < 2:
        return []
    if m == "JP":
        from .calendar_jp import is_trading_day
    else:
        from .calendar_us import is_trading_day
    idx = pd.DatetimeIndex(df.index)
    have = set(idx.normalize().date)
    first, d = idx[0].date(), idx[-1].date()
    out, n = [], 0
    while n < lookback:
        d -= timedelta(days=1)
        if d < first:
            break
        if is_trading_day(d):
            n += 1
            if d not in have:
                out.append(d)
    return sorted(out)


def _yf_intraday(ticker: str, days: int = 5, interval: str = "5m") -> pd.DataFrame:
    import yfinance as yf
    for nm in ("yfinance", "yfinance.data", "yfinance.utils", "peewee"):
        logging.getLogger(nm).setLevel(logging.CRITICAL)
    return yf.Ticker(ticker).history(period=f"{days}d", interval=interval, auto_adjust=False)


def fill_index_from_intraday(ticker: str, df: pd.DataFrame | None, now: datetime | None = None) -> pd.DataFrame | None:
    """指数（^ 开头）的日线缺日 → 用那几天的 5 分钟线合成日线（开 = 第一根开盘、高 / 低 = 极值、收 = 最后一根收盘、量 = 合计）补上，
    只补已收盘、5 分钟线够 FILL_MIN_BARS 根的日子；合成的收盘与正式收盘可能差 0.1% 以内，下次整段重新下载时会被正式日线换掉。
    两种缺：① 最后一天落后于交易日历（behind；Yahoo 偶尔只给开盘、收盘是 NaN，例 ^N225 2026-09-29）；
    ② 最近 GAP_LOOKBACK 个交易日中间漏了一天（missing_days；例 ^N225 2026-10-05，2026-10-06 加）。
    补上的记进 FILLED（日报「数据完整性 · 自动修复」列出）；中间缺而分钟线也补不上的记进 GAPS（日报「数据完整性」列出）。
    取不到 / 不够 → 原样返回。"""
    if df is None or not len(df) or not ticker.startswith("^"):
        return df
    b = behind(ticker, df)
    gaps = missing_days(ticker, df)
    if b is None and not gaps:
        GAPS.pop(ticker, None)
        return df
    m = _market_of(ticker)
    n_now = now or _now_utc()
    span = (n_now.date() - min(gaps)).days + 3 if gaps else 5                     # 5 分钟线要盖到最早的缺日
    try:
        bars = _yf_intraday(ticker, days=max(5, min(59, span)))
    except Exception as e:                                             # noqa: BLE001
        log.warning("%s 分钟线取不到（不合成日线）：%s", ticker, e)
        bars = None
    if bars is None or not len(bars) or "Close" not in bars.columns:
        if gaps:
            GAPS[ticker] = {"dates": [str(d) for d in gaps]}
        return df
    from zoneinfo import ZoneInfo

    from .calendar_jp import JST
    from .trader import market_session_closed
    tz = JST if m == "JP" else ZoneInfo("America/New_York")
    idx = pd.DatetimeIndex(bars.index)
    idx = idx.tz_localize("UTC").tz_convert(tz) if idx.tz is None else idx.tz_convert(tz)
    bars = bars.copy()
    bars.index = idx
    bars = bars.dropna(subset=["Close"])
    last = pd.Timestamp(df.index[-1]).normalize()
    exp = pd.Timestamp(b[1]) if b else last
    want = {pd.Timestamp(g) for g in gaps}
    n_day, n_closed = market_session_closed(m, n_now.astimezone(tz))
    rows = {}
    for day, g in bars.groupby(bars.index.tz_localize(None).normalize()):
        day = pd.Timestamp(day)
        if not (last < day <= exp or day in want) or len(g) < FILL_MIN_BARS:
            continue
        if day.date() == n_day and not n_closed:
            continue                                                   # 今天还没收盘
        vol = pd.to_numeric(g["Volume"], errors="coerce").fillna(0).sum() if "Volume" in g.columns else 0.0
        rows[day] = {"Open": float(g["Open"].iloc[0]), "High": float(g["High"].max()), "Low": float(g["Low"].min()),
                     "Close": float(g["Close"].iloc[-1]), "Volume": float(vol)}
    left = [d for d in gaps if pd.Timestamp(d) not in rows]
    if left:
        GAPS[ticker] = {"dates": [str(d) for d in left]}
        log.warning("%s 日线中间缺 %s，5 分钟线也补不上", ticker, "、".join(str(d) for d in left))
    else:
        GAPS.pop(ticker, None)
    if not rows:
        return df
    added = sorted(rows)
    add = pd.DataFrame.from_dict(rows, orient="index")[OHLCV]
    out = pd.concat([df[[c for c in OHLCV if c in df.columns]], add]).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    FILLED[ticker] = {"dates": [str(d.date()) for d in added], "gap_dates": [str(d.date()) for d in added if d in want],
                      "close": rows[added[-1]]["Close"], "source": "yfinance 5m", "expected": b[1] if b else None}
    log.warning("%s 日线缺 %s（最新 %s%s）→ 用 5 分钟线合成（收盘 %.2f）", ticker, "、".join(str(d.date()) for d in added), last.date(),
                f"、应有 {b[1]}" if b else "", rows[added[-1]]["Close"])
    return out


def _fetched_at(ticker: str, years: int) -> datetime | None:
    try:
        return datetime.fromisoformat(json.loads(_meta_path(ticker, years).read_text(encoding="utf-8"))["fetched_at"])
    except Exception:  # noqa: BLE001
        return None


def partial_cached(t: str, df: pd.DataFrame | None, fetched_at: datetime | None, now: datetime | None = None) -> bool:
    """盘中取的缓存：最后一根是取数时那个市场还没收盘的当日 K 线（yfinance 盘中会返回），而现在那个市场已经收盘（或已是之后的日子）
    → True（有效期内也要重新下载，否则收盘后 12 小时内会把盘中快照当成收盘价）。现在还在盘中 → False（drop_partial_bar 照旧丢掉那根）。"""
    m = _market_of(t)
    if m is None or df is None or not len(df) or fetched_at is None:
        return False
    from zoneinfo import ZoneInfo

    from .calendar_jp import JST
    from .trader import market_session_closed
    tz = JST if m == "JP" else ZoneInfo("America/New_York")
    last = pd.Timestamp(df.index[-1]).date()
    f_day, f_closed = market_session_closed(m, fetched_at.astimezone(tz))
    if last != f_day or f_closed:
        return False                                            # 取数时这一根已经收盘（或是更早的日子）
    n_day, n_closed = market_session_closed(m, (now or _now_utc()).astimezone(tz))
    return n_day > last or n_closed


def load_universe(tickers: list[str], cfg: DataConfig | None = None,
                  use_cache: bool = True) -> dict[str, pd.DataFrame]:
    """返回 {ticker: OHLCV DataFrame}。失败的标的会被跳过并记录，
    全部失败时抛异常（而不是像原版那样悄悄换成假数据继续跑）。
    缓存除了有效期（TTL），还按交易日历查新鲜度：缺了应有的最近交易日（Yahoo 偶尔晚更新）→ 重新下载；
    重下载失败时退回旧缓存，重下载后仍落后的记进 LAGGING（日报「数据完整性」会列出）。"""
    cfg = (cfg or DataConfig()).validate()
    out: dict[str, pd.DataFrame] = {}
    todo: list[str] = []
    old: dict[str, pd.DataFrame] = {}

    for t in tickers:
        c = _read_cache(t, cfg.years, cfg.cache_ttl_hours) if use_cache else None
        if c is not None:
            try:
                c = validate_ohlcv(t, c, cfg)
                b = behind(t, c) if cfg.provider == "yfinance" else None
                if b is None and cfg.provider == "yfinance" and partial_cached(t, c, _fetched_at(t, cfg.years)):
                    log.info("缓存 %s 的最后一根（%s）是盘中取的、现在已收盘 → 重新下载", t, c.index[-1].date())
                    old[t] = c.iloc[:-1]                  # 重下载失败时不拿盘中快照兜底（少一天 → 记为落后）
                elif b is None:
                    out[t] = c
                    continue
                else:
                    log.info("缓存落后 %s：最新 %s，应有 %s → 重新下载", t, *b)
                    old[t] = c
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

    for t, c in old.items():                    # 重下载失败：用旧缓存（总比没有强），并记为落后
        if t not in out:
            log.warning("%s 重新下载失败，暂用旧缓存（最新 %s）", t, c.index[-1].date())
            out[t] = c
    if cfg.provider == "yfinance":              # 指数的日线落后 / 中间缺日（Yahoo 只给开盘、收盘 NaN，或漏一天）→ 用 5 分钟线合成，补上的写进缓存
        for t in tickers:
            if not t.startswith("^") or t not in out:
                continue
            try:
                if behind(t, out[t]) is None and not missing_days(t, out[t]):
                    GAPS.pop(t, None)
                    continue
                filled = fill_index_from_intraday(t, out[t])
            except Exception as e:                                         # noqa: BLE001  补缺失败绝不挡住载入行情
                log.warning("%s 指数日线补缺失败（按原样用）：%s", t, e)
                continue
            if filled is not None and len(filled) > len(out[t]):
                out[t] = filled
                _write_cache(t, cfg.years, filled, "yfinance", extra={"filled": FILLED[t]["dates"]})
    for t in tickers:
        b = behind(t, out.get(t))
        if b:
            LAGGING[t] = {"last": b[0], "expected": b[1]}
        else:
            LAGGING.pop(t, None)
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


def intraday_last(tickers: list[str], now: datetime | None = None, max_age_min: float = 60.0) -> dict[str, float]:
    """模拟账户盘中手动单用的现在价：yfinance 1 分钟线最后一根的收盘（東証は約 15〜20 分遅れ）。
    只认今天（JST）的、而且不早于 max_age_min 分钟之前的那一根（开盘后还没有今天的分钟线 / 停牌 → 不给价，执行器过几分钟再试）。
    实盘不用它（用立花的現在値）。"""
    import yfinance as yf

    from .calendar_jp import JST
    for nm in ("yfinance", "yfinance.data", "yfinance.utils"):
        logging.getLogger(nm).setLevel(logging.CRITICAL)
    tickers = sorted(set(tickers))
    if not tickers:
        return {}
    try:
        raw = yf.download(tickers, period="1d", interval="1m", progress=False, group_by="ticker", threads=False,
                          auto_adjust=False, prepost=False)
    except Exception as e:  # noqa: BLE001
        log.warning("盘中价取不到: %s", e)
        return {}
    if raw is None or raw.empty:
        return {}
    n = (now or _now_utc()).astimezone(JST)
    out: dict[str, float] = {}
    for t in tickers:
        try:
            col = raw[t]["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw["Close"]
        except KeyError:
            continue
        v = col.dropna()
        if not len(v):
            continue
        ts = pd.Timestamp(v.index[-1])
        ts = (ts.tz_localize("UTC") if ts.tzinfo is None else ts).tz_convert(JST)
        if ts.date() != n.date() or (n - ts.to_pydatetime()).total_seconds() > max_age_min * 60:
            continue
        px = float(v.iloc[-1])
        if px > 0:
            out[t] = px
    return out
