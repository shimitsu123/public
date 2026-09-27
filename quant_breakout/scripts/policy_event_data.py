"""policy_event_data.py — 政策事件反应库的数据层（G1；不含分类表、判定规则 —— 那些在 scripts/policy_event_study.py 头部登记）。

事件表（入库，公开事实）：var/policy_events.csv —— date（公布日 JST）, time_jst（HH:MM 或空）, category, name_ja, name_en, description, source_url, verified, notes。
反应日 r（与 fins_event_data 同一口径）：公布时刻 < 当天收盘时刻（2024-11-05 起 15:30、之前 15:00）且当天是交易日 → r = 当天；否则 = 之后第一个交易日；
  缺时刻 → 当收盘后（偏保守）。可交易的买点 = r 的下一个开盘（t0 = r+1）。
收益序列（都是日收盘对收盘的简单收益，%）：
  bench：日経225（yfinance ^N225，1965〜）、TOPIX（1306.T，2009〜）；
  sector17：東証 17 业种 ETF 1617〜1633（var/cache/<code>_21y.csv，2008-03〜；名字用 qbreak/sectors.SECTOR_ETF_JP）；
  sector33_long：日経225 + 扩大池（scripts/leap_data.names）按今天的 33 业种（var/industry_s33.json）等权，2001〜（业种用今天的分类 = 局限）；
  sector33_all：全市场面板（scripts/allstock_data）按同一 33 业种等权、只算时点上市的票，2016-09〜。
反应（每个事件 × 每个序列 × 每个期限 h ∈ {1, 5, 20, 60} 个交易日）：
  incl = 从 r−1 收盘到 r+h 收盘的累计收益（含反应日；描述用）；post = 从 r 收盘到 r+h 收盘（反应日之后；接近 t0 开盘买能拿到的部分）；
  excess = 序列 − 基准（同一窗口）。打乱日期对照：同一年内随机换成别的交易日（保持每年的事件数），种子写定。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                      # noqa: E402

EVENT_COLS = ["date", "time_jst", "category", "name_ja", "name_en", "description", "source_url", "verified", "notes"]
HORIZONS = (1, 5, 20, 60)
CLOSE_CHANGE, CLOSE_OLD, CLOSE_NEW = pd.Timestamp("2024-11-05"), "15:00", "15:30"
EVENTS_PATH = Path(paths.PROJECT_ROOT) / "var" / "policy_events.csv"          # 仓库里的事件表（Mac 上 paths.home() 是 ~/.qbreak/home，不在那里）


# ───────────────────────── 事件表 ─────────────────────────
def load_events(path: Path | str | None = None) -> pd.DataFrame:
    fp = Path(path) if path else EVENTS_PATH
    E = pd.read_csv(fp, dtype=str).fillna("")
    for c in EVENT_COLS:
        if c not in E.columns:
            E[c] = ""
    E["date"] = pd.to_datetime(E["date"])
    E["time_jst"] = E["time_jst"].astype(str).str.strip()
    return E.sort_values(["date", "category"]).reset_index(drop=True)


def close_time(d: pd.Timestamp) -> str:
    return CLOSE_NEW if pd.Timestamp(d) >= CLOSE_CHANGE else CLOSE_OLD


def reaction_days(E: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """每个事件的反应日 r（见模块开头）；数据末尾之后 → NaT。"""
    out = []
    for d, tm in zip(E["date"], E["time_jst"]):
        d = pd.Timestamp(d).normalize()
        tm = str(tm or "")
        intraday = bool(tm) and tm < close_time(d)
        if intraday and d in days:
            out.append(d)
        else:
            k = days.searchsorted(d, side="right")
            out.append(days[k] if k < len(days) else pd.NaT)
    return pd.DatetimeIndex(out)


# ───────────────────────── 收益序列 ─────────────────────────
def _cache_csv(name: str) -> pd.Series | None:
    fp = Path(paths.cache_dir()) / name if hasattr(paths, "cache_dir") else Path("var/cache") / name
    if not fp.exists():
        return None
    df = pd.read_csv(fp)
    df["Date"] = pd.to_datetime(df["Date"])
    s = df.set_index("Date")["Close"].astype(float)
    return s[~s.index.duplicated()].sort_index()


def benchmarks() -> dict[str, pd.Series]:
    """{'N225': 收盘, 'TOPIX': 收盘（1306.T，可能缺）}。"""
    out = {}
    try:
        from bullbear_study import SYM, load
        out["N225"] = load(*SYM["JP"])["Close"].astype(float)
    except Exception:                                                        # noqa: BLE001
        pass
    t = _cache_csv("1306.T_21y.csv")
    if t is not None:
        out["TOPIX"] = t
    return out


def sector17_closes() -> pd.DataFrame:
    from qbreak.sectors import SECTOR_ETF_JP
    cols = {}
    for code, name in SECTOR_ETF_JP.items():
        s = _cache_csv(f"{code}_21y.csv")
        if s is not None:
            cols[name] = s
    return pd.DataFrame(cols).sort_index()


def s33_map() -> dict[str, str]:
    """票（1234.T）→ 33 业种名（今天的分类）。"""
    import json
    fp = Path(paths.home()) / "industry_s33.json"
    d = json.loads(Path(fp).read_text(encoding="utf-8"))
    return {f"{k}.T": v for k, v in (d.get("s33") or {}).items()}


def equal_weight_returns(rets: pd.DataFrame, groups: dict[str, str], mask: pd.DataFrame | None = None, min_n: int = 3) -> pd.DataFrame:
    """个股日收益（天 × 票）→ 每个业种等权的日收益（天 × 业种）；mask（同形，bool）= 那天算不算这只票；少于 min_n 只 → NaN。"""
    out = {}
    by: dict[str, list[str]] = {}
    for t, g in groups.items():
        if t in rets.columns:
            by.setdefault(g, []).append(t)
    for g, ts in sorted(by.items()):
        r = rets[ts]
        ok = np.isfinite(r.to_numpy())
        if mask is not None:
            ok &= mask.reindex(index=r.index, columns=ts).fillna(False).to_numpy(bool)
        v = np.where(ok, r.to_numpy(), np.nan)
        n = ok.sum(1)
        with np.errstate(invalid="ignore"):
            m = np.nansum(v, axis=1) / np.where(n > 0, n, np.nan)
        out[g] = pd.Series(np.where(n >= min_n, m, np.nan), index=r.index)
    return pd.DataFrame(out, index=rets.index)


def sector33_all(A: dict) -> pd.DataFrame:
    """全市场面板 → 33 业种等权日收益（只算时点上市的票）。"""
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    C = pd.DataFrame(A["C"], index=days, columns=names)
    rets = C.pct_change() * 100
    mask = pd.DataFrame(A["listed"], index=days, columns=names)
    return equal_weight_returns(rets, s33_map(), mask)


def s33_map_pit(snaps: dict[pd.Timestamp, pd.DataFrame]) -> dict[pd.Timestamp, dict[str, str]]:
    """每份月末上市一览 → {票: 33 业种名}（时点分类）。"""
    from qbreak import jquants as JQ
    out = {}
    for d, m in snaps.items():
        col = "S33Nm" if "S33Nm" in m.columns else None
        if col is None:
            continue
        mp = {}
        for c, g in zip(m["Code"].astype(str), m[col].astype(str)):
            t = JQ.to_yf(c)
            if t and g and g != "-":
                mp[t] = g
        out[pd.Timestamp(d)] = mp
    return out


def sector33_all_pit(A: dict, snaps: dict[pd.Timestamp, pd.DataFrame], min_n: int = 5) -> pd.DataFrame:
    """全市场面板 → 33 业种等权日收益，业种按「严格早于那天的最近一份上市一览」（时点分类；第一份快照之前 → 用第一份）。"""
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    C = pd.DataFrame(A["C"], index=days, columns=names)
    rets = C.pct_change() * 100
    mask = pd.DataFrame(A["listed"], index=days, columns=names)
    maps = s33_map_pit(snaps)
    sd = sorted(maps)
    if not sd:
        return equal_weight_returns(rets, s33_map(), mask, min_n)
    parts = []
    bounds = [days[0] - pd.Timedelta(days=1)] + sd
    for k, lo in enumerate(bounds):
        hi = bounds[k + 1] if k + 1 < len(bounds) else days[-1]
        rows = (days > lo) & (days <= hi)
        if not rows.any():
            continue
        mp = maps[sd[0]] if k == 0 else maps[lo]
        parts.append(equal_weight_returns(rets[rows], mp, mask[rows], min_n))
    return pd.concat(parts).sort_index()


def sector33_long(tickers: list[str] | None = None) -> pd.DataFrame:
    """日経225 + 扩大池（yfinance 长历史）→ 33 业种等权日收益（今天的分类）。"""
    import leap_data as LD
    names = tickers or list(LD.names())
    data = LD.ohlcv(names)
    closes = pd.DataFrame({t: df["Close"].astype(float) for t, df in data.items() if len(df)}).sort_index()
    rets = closes.pct_change() * 100
    return equal_weight_returns(rets, s33_map())


# ───────────────────────── 反应 ─────────────────────────
def window_returns(closes: pd.Series, r: pd.Timestamp, h: int) -> tuple[float, float]:
    """(incl, post)：从 r−1 收盘 / r 收盘 到 r+h 收盘的累计收益 %；数据不够 → NaN。"""
    idx = closes.index
    k = idx.get_indexer([r])[0] if r in idx else -1
    if k < 1 or k + h >= len(idx):
        return np.nan, np.nan
    c = closes.to_numpy(float)
    if not (np.isfinite(c[k - 1]) and np.isfinite(c[k]) and np.isfinite(c[k + h])) or c[k - 1] <= 0 or c[k] <= 0:
        return np.nan, np.nan
    return (c[k + h] / c[k - 1] - 1) * 100, (c[k + h] / c[k] - 1) * 100


def cum_from_returns(rets: pd.DataFrame) -> pd.DataFrame:
    """日收益 %（天 × 序列）→ 累计指数（起点 100；NaN 当 0 收益）。"""
    return (1 + rets.fillna(0) / 100).cumprod() * 100


def reactions(E: pd.DataFrame, r_days: pd.DatetimeIndex, series: pd.DataFrame, bench: pd.Series | None, horizons=HORIZONS) -> pd.DataFrame:
    """事件 × 序列 × 期限 的长表：event_i, r, series, h, incl, post, bench_incl, bench_post, ex_incl, ex_post（超额 = 序列 − 基准）。"""
    rows = []
    b = bench.reindex(series.index).ffill() if bench is not None else None
    for i, r in enumerate(r_days):
        if pd.isna(r):
            continue
        for h in horizons:
            bi, bp = window_returns(b, r, h) if b is not None else (np.nan, np.nan)
            for col in series.columns:
                inc, post = window_returns(series[col], r, h)
                rows.append((i, r, col, h, inc, post, bi, bp, inc - bi, post - bp))
    return pd.DataFrame(rows, columns=["event_i", "r", "series", "h", "incl", "post", "bench_incl", "bench_post", "ex_incl", "ex_post"])


def shuffle_dates(r_days: pd.DatetimeIndex, days: pd.DatetimeIndex, seed: int, exclude_gap: int = 5) -> pd.DatetimeIndex:
    """打乱日期对照：每个事件换成同一年内随机另一个交易日（离原日期 ≥ exclude_gap 个交易日）。"""
    rng = np.random.default_rng(seed)
    pos = pd.Series(np.arange(len(days)), index=days)
    out = []
    for r in r_days:
        if pd.isna(r):
            out.append(pd.NaT)
            continue
        k = int(pos.get(r, -1))
        cand = np.where(days.year == r.year)[0]
        if k >= 0:
            cand = cand[np.abs(cand - k) >= exclude_gap]
        out.append(days[int(rng.choice(cand))] if len(cand) else pd.NaT)
    return pd.DatetimeIndex(out)


def summarize(R: pd.DataFrame, col: str = "ex_post") -> pd.DataFrame:
    """按 序列 × 期限：n、均值、中位数、命中率（> 0 的比例，%）。"""
    g = R.dropna(subset=[col]).groupby(["series", "h"])[col]
    out = g.agg(n="count", mean="mean", median="median", hit=lambda x: float((x > 0).mean() * 100)).reset_index()
    return out


# ───────────────────────── 第 3 步扩展：可交易窗口、掩码、对照、事前 β ─────────────────────────
def _cache_ohlcv(name: str) -> pd.DataFrame | None:
    fp = Path(paths.cache_dir()) / name
    if not fp.exists():
        return None
    df = pd.read_csv(fp)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    return df[~df.index.duplicated()][["Open", "Close", "Volume"]].astype(float)


def sector17_frames() -> dict[str, pd.DataFrame]:
    """17 业种 ETF 的 Open / Close / Volume（var/cache/<code>_21y.csv）。"""
    from qbreak.sectors import SECTOR_ETF_JP
    out = {}
    for code, name in SECTOR_ETF_JP.items():
        df = _cache_ohlcv(f"{code}_21y.csv")
        if df is not None:
            out[name] = df
    return out


def etf_daily(frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """→ (cc 收对收 %, oc 开对收 %, ok 成交量 > 0 掩码)；成交量 = 0 的日子 cc / oc = NaN。"""
    cc, oc, ok = {}, {}, {}
    for n, df in frames.items():
        good = df["Volume"] > 0
        c = df["Close"].where(good)
        cc[n] = c.pct_change() * 100
        oc[n] = (df["Close"] / df["Open"] - 1).where(good & (df["Open"] > 0)) * 100
        ok[n] = good
    return pd.DataFrame(cc), pd.DataFrame(oc), pd.DataFrame(ok)


def panel_daily(closes: pd.DataFrame, opens: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """个股 收盘 / 开盘（天 × 票）→ (cc, oc) 日收益 %。"""
    cc = closes.pct_change() * 100
    oc = (closes / opens - 1) * 100
    return cc, oc


def sector_daily_pit(A: dict, snaps: dict[pd.Timestamp, pd.DataFrame], min_n: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """全市场面板 → 33 业种等权的 (cc, oc) 日收益（时点分类、只算时点上市的票）。"""
    days, names = pd.DatetimeIndex(A["days"]), list(A["names"])
    C = pd.DataFrame(A["C"], index=days, columns=names)
    O = pd.DataFrame(A["O"], index=days, columns=names)
    cc, oc = panel_daily(C, O)
    mask = pd.DataFrame(A["listed"], index=days, columns=names)
    maps = s33_map_pit(snaps)
    sd = sorted(maps)
    if not sd:
        mp = s33_map()
        return equal_weight_returns(cc, mp, mask, min_n), equal_weight_returns(oc, mp, mask, min_n)
    pcc, poc = [], []
    bounds = [days[0] - pd.Timedelta(days=1)] + sd
    for k, lo in enumerate(bounds):
        hi = bounds[k + 1] if k + 1 < len(bounds) else days[-1]
        rows = (days > lo) & (days <= hi)
        if not rows.any():
            continue
        mp = maps[sd[0]] if k == 0 else maps[lo]
        pcc.append(equal_weight_returns(cc[rows], mp, mask[rows], min_n))
        poc.append(equal_weight_returns(oc[rows], mp, mask[rows], min_n))
    return pd.concat(pcc).sort_index(), pd.concat(poc).sort_index()


def sector_daily_long(tickers: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """长历史池（yfinance 27 年）→ 33 业种等权 (cc, oc)（今天的分类）。"""
    import leap_data as LD
    names = tickers or list(LD.names())
    data = LD.ohlcv(names)
    closes = pd.DataFrame({t: df["Close"].astype(float) for t, df in data.items() if len(df)}).sort_index()
    opens = pd.DataFrame({t: df["Open"].astype(float) for t, df in data.items() if len(df)}).reindex(closes.index)
    cc, oc = panel_daily(closes, opens)
    mp = s33_map()
    return equal_weight_returns(cc, mp), equal_weight_returns(oc, mp)


def window_open(cc: pd.DataFrame, oc: pd.DataFrame, t0: pd.Timestamp, h: int) -> pd.Series:
    """可交易窗口：t0 开盘 → t0+h−1 收盘的累计收益 %（每列一个序列；数据不够 → NaN）。"""
    idx = cc.index
    k = idx.get_indexer([t0])[0] if t0 in idx else -1
    if k < 0 or k + h - 1 >= len(idx):
        return pd.Series(np.nan, index=cc.columns)
    first = oc.iloc[k] / 100
    rest = (1 + cc.iloc[k + 1:k + h] / 100).prod(axis=0, skipna=False) if h > 1 else pd.Series(1.0, index=cc.columns)
    return ((1 + first) * rest - 1) * 100


def window_close(cc: pd.DataFrame, r: pd.Timestamp, lo: int, hi: int) -> pd.Series:
    """收盘口径：从 r+lo−1 收盘到 r+hi 收盘的累计收益 %（lo ≤ hi；lo = 0、hi = 0 → D0 = [r−1 收 → r 收]）。"""
    idx = cc.index
    k = idx.get_indexer([r])[0] if r in idx else -1
    a, b = k + lo, k + hi
    if k < 0 or a < 0 or b >= len(idx):
        return pd.Series(np.nan, index=cc.columns)
    return ((1 + cc.iloc[a:b + 1] / 100).prod(axis=0, skipna=False) - 1) * 100


def spread(x: pd.Series, benef: list[str], victim: list[str]) -> float:
    """事件级价差：受益篮子等权 − 受损篮子等权（只有一侧 → 该侧 − 其余业种等权）；缺值的业种跳过；两侧都没有可得业种 → NaN。"""
    x = x.dropna()
    b = [s for s in benef if s in x.index]
    v = [s for s in victim if s in x.index]
    if b and v:
        return float(x[b].mean() - x[v].mean())
    if b:
        rest = x.drop(b)
        return float(x[b].mean() - rest.mean()) if len(rest) else np.nan
    if v:
        rest = x.drop(v)
        return float(rest.mean() - x[v].mean()) if len(rest) else np.nan
    return np.nan


def shuffle_sectors(benef: list[str], victim: list[str], available: list[str], seed: int) -> tuple[list[str], list[str]]:
    """随机业种对照：受益 / 受损换成同样个数的随机可得业种（两侧不重叠）。"""
    rng = np.random.default_rng(seed)
    pool = list(available)
    k = len(benef) + len(victim)
    if k == 0 or len(pool) < k:
        return [], []
    pick = list(rng.choice(pool, size=k, replace=False))
    return [str(x) for x in pick[:len(benef)]], [str(x) for x in pick[len(benef):]]


def cluster_boot_month(values: np.ndarray, months: np.ndarray, n: int = 2000, seed: int = 20260927) -> tuple[float, float]:
    """按事件所在日历月聚类的自助法：均值的 2.5 / 97.5 分位；样本 < 5 → (nan, nan)。"""
    v = np.asarray(values, float)
    ok = np.isfinite(v)
    v, m = v[ok], np.asarray(months)[ok]
    if len(v) < 5:
        return np.nan, np.nan
    codes, uniq = pd.factorize(pd.Index(m))
    sums = np.bincount(codes, weights=v, minlength=len(uniq))
    cnt = np.bincount(codes, minlength=len(uniq)).astype(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(uniq), size=(n, len(uniq)))
    means = sums[idx].sum(1) / cnt[idx].sum(1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def overlap_flags(r_days: pd.DatetimeIndex, days: pd.DatetimeIndex, gap: int = 20) -> np.ndarray:
    """|r_i − r_j| ≤ gap 个交易日 → overlap = 1（与任一其他事件）。"""
    pos = np.array([days.searchsorted(r) if pd.notna(r) else -10 ** 9 for r in r_days])
    out = np.zeros(len(pos), int)
    for i in range(len(pos)):
        for j in range(len(pos)):
            if i != j and abs(pos[i] - pos[j]) <= gap:
                out[i] = 1
                break
    return out


CRISIS = (("2008-09-01", "2009-03-31"), ("2020-02-01", "2020-05-31"))


def crisis_flag(r: pd.Timestamp) -> int:
    return int(any(pd.Timestamp(a) <= r <= pd.Timestamp(b) for a, b in CRISIS)) if pd.notna(r) else 0


def adjacent_flag(r: pd.Timestamp, dates, days: pd.DatetimeIndex, gap: int = 3) -> int:
    """r 前后 gap 个交易日内有 dates 里的日子（FOMC / 日银 / NFP / CPI 等）→ 1。"""
    if pd.isna(r) or dates is None or not len(dates):
        return 0
    k = days.searchsorted(r)
    ks = days.searchsorted(pd.DatetimeIndex(pd.to_datetime(dates)))
    return int(bool(np.any(np.abs(ks - k) <= gap)))


# ── 事前 β 通道（P2）──
FACTOR_FILES = {"rate_jp": ("mof_jgb_curve.csv", "10Y", "diff"), "rate_us": ("fred_DGS10.csv", None, "diff"),
                "oil": ("fred_DCOILWTICO.csv", None, "logpct"), "fx": ("fred_DEXJPUS.csv", None, "logpct"), "credit": ("fred_BAA10Y.csv", None, "diff")}


def _factor_series(fname: str, col: str | None) -> pd.Series | None:
    fp = Path(paths.cache_dir()) / "factors" / fname
    if not fp.exists():
        return None
    df = pd.read_csv(fp)
    dcol = df.columns[0]
    df[dcol] = pd.to_datetime(df[dcol], errors="coerce")
    df = df.dropna(subset=[dcol]).set_index(dcol).sort_index()
    s = pd.to_numeric(df[col] if col else df.iloc[:, 0], errors="coerce").dropna()
    return s[~s.index.duplicated()]


def factor_weekly() -> pd.DataFrame:
    """因子周变化（W-FRI）：利率 pp 差、汇率 / 油价 对数变化 %；缺文件的因子不出现。"""
    out = {}
    for f, (fname, col, kind) in FACTOR_FILES.items():
        s = _factor_series(fname, col)
        if s is None:
            continue
        w = s.resample("W-FRI").last().ffill()
        out[f] = w.diff() if kind == "diff" else np.log(w).diff() * 100
    return pd.DataFrame(out)


def weekly_from_daily(cc: pd.DataFrame) -> pd.DataFrame:
    """日收益 %（天 × 序列）→ 周收益 %（W-FRI）。"""
    return ((1 + cc / 100).resample("W-FRI").prod(min_count=1) - 1) * 100


def betas_asof(sec_w: pd.DataFrame, fac_w: pd.DataFrame, mkt_w: pd.Series, end: pd.Timestamp, weeks: int = 104, min_weeks: int = 60) -> pd.DataFrame | None:
    """截至 end 之前（不含 end 所在周）的 weeks 周：业种超额周收益（− 日経）对因子周变化的多元 OLS β（业种 × 因子）；不足 min_weeks → None。"""
    cutoff = pd.Timestamp(end) - pd.Timedelta(days=pd.Timestamp(end).weekday() + 3)      # 上一周的周五
    X = fac_w[fac_w.index <= cutoff].tail(weeks)
    Y = (sec_w.sub(mkt_w, axis=0)).reindex(X.index)
    ok = X.notna().all(axis=1) & Y.notna().any(axis=1)
    X, Y = X[ok], Y[ok]
    if len(X) < min_weeks:
        return None
    Xm = np.column_stack([np.ones(len(X)), X.to_numpy(float)])
    out = {}
    for col in Y.columns:
        y = Y[col].to_numpy(float)
        m = np.isfinite(y)
        if m.sum() < min_weeks:
            continue
        b, *_ = np.linalg.lstsq(Xm[m], y[m], rcond=None)
        out[col] = b[1:]
    if not out:
        return None
    return pd.DataFrame(out, index=X.columns).T


def beta_lists(B: pd.DataFrame, shocks: dict[str, float], k: int = 4) -> tuple[list[str], list[str]]:
    """Σ β × 冲击 → 前 k（受益）/ 后 k（受损）。"""
    if B is None or not shocks:
        return [], []
    fs = [f for f in shocks if f in B.columns]
    if not fs:
        return [], []
    score = sum(B[f] * shocks[f] for f in fs).dropna().sort_values()
    if len(score) < 2 * k:
        return [], []
    return list(score.index[-k:][::-1]), list(score.index[:k])
