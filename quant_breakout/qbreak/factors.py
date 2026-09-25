"""factors.py — 多因子数据（免费官方源）：美日收益率曲线、政策利率、油价、汇率、信用利差、波动率、ETF。

来源（2026-09-24 从云端环境实测可下载）：
  FRED fredgraph.csv（无需 API key）：美债 3M/2Y/5Y/10Y/30Y、实际利率、通胀预期、联邦基金利率、
      Brent / WTI 现货、USD/JPY、穆迪 Baa−10Y 信用利差、VIX
      （ICE 高收益债利差 BAMLH0A0HYM2 自 2026-04 起 FRED 只给 3 年 → 长历史用 BAA10Y 代替）
  財務省「国債金利情報」jgbcm_all.csv + 当月 jgbcm.csv：1974-09 起，1～40 年，日期为和暦（S/H/R）
  日本銀行 時系列統計 API：FM01 STRDCLUCON 無担保コール O/N 物（日次）
  yfinance：ETF（由 data.load_universe 取，沿用其缓存与修复）
缓存：var/cache/factors/（var/cache 已被 .gitignore 忽略，不会进仓库），12 小时内不重复下载。
"""
from __future__ import annotations

import datetime as dt
import io
import json
import time

import numpy as np
import pandas as pd

from . import paths
from .utils import setup_logging

log = setup_logging("factors")

FRED_SERIES = {
    "us3m": "DGS3MO", "us2y": "DGS2", "us5y": "DGS5", "us10y": "DGS10", "us30y": "DGS30",
    "us10y_real": "DFII10", "us10y_bei": "T10YIE", "fed_funds": "DFF",
    "brent_spot": "DCOILBRENTEU", "wti_spot": "DCOILWTICO", "usdjpy": "DEXJPUS",
    "baa_spread": "BAA10Y", "vix": "VIXCLS",
}
JGB_TENORS = ["1Y", "2Y", "3Y", "4Y", "5Y", "6Y", "7Y", "8Y", "9Y", "10Y", "15Y", "20Y", "25Y", "30Y", "40Y"]
MOF_ALL = "https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv"
MOF_CUR = "https://www.mof.go.jp/jgbs/reference/interest_rate/jgbcm.csv"
BOJ_API = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"
ERA = {"S": 1925, "H": 1988, "R": 2018}               # 昭和 / 平成 / 令和 元年 = 基数 + 1


def _dir():
    return paths.sub("cache/factors")


def _get(url: str, timeout: int = 60, tries: int = 3) -> bytes:
    """用 curl_cffi（yfinance 的依赖）模拟浏览器 TLS 指纹下载：FRED 会让 Python 默认客户端一直卡到超时。
    没装 curl_cffi 时退回系统 curl。"""
    last = None
    for k in range(tries):
        try:
            try:
                from curl_cffi import requests as cr
            except ImportError:
                import subprocess
                return subprocess.run(["curl", "-sSfL", "--max-time", str(timeout), url],
                                      check=True, capture_output=True).stdout
            r = cr.get(url, impersonate="chrome", timeout=timeout)
            r.raise_for_status()
            return r.content
        except Exception as e:                          # noqa: BLE001
            last = e
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"下载失败 {url}: {last}")


def _cached(name: str, fetch, max_age_h: float = 12.0) -> pd.Series | pd.DataFrame:
    """fetch() 返回 DataFrame/Series；写 CSV 缓存。下载失败时退回旧缓存（并警告）。"""
    fp = _dir() / f"{name}.csv"
    if fp.exists() and time.time() - fp.stat().st_mtime < max_age_h * 3600:
        return _read(fp)
    try:
        obj = fetch()
        obj.to_csv(fp)
        return obj
    except Exception as e:                              # noqa: BLE001
        if fp.exists():
            log.warning("%s 下载失败，使用旧缓存：%s", name, e)
            return _read(fp)
        raise


def _read(fp):
    df = pd.read_csv(fp, index_col=0, parse_dates=True)
    return df.iloc[:, 0] if df.shape[1] == 1 else df


# ────────────────────────── FRED ──────────────────────────
def fred(series_id: str) -> pd.Series:
    def fetch():
        raw = _get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
        df = pd.read_csv(io.BytesIO(raw))
        s = pd.to_numeric(df.iloc[:, 1], errors="coerce")   # 缺值是 "."
        s.index = pd.to_datetime(df.iloc[:, 0])
        return s.dropna().rename(series_id)
    return _cached(f"fred_{series_id}", fetch)


# ────────────────────────── 財務省 JGB ──────────────────────────
def parse_era_date(s: str) -> pd.Timestamp | None:
    """'S49.9.24' → 1974-09-24；'H31.4.30' → 2019-04-30；'R8.9.18' → 2026-09-18。"""
    s = (s or "").strip()
    if len(s) < 2 or s[0] not in ERA:
        return None
    try:
        y, m, d = (int(x) for x in s[1:].split("."))
        return pd.Timestamp(ERA[s[0]] + y, m, d)
    except ValueError:
        return None


def _parse_mof(raw: bytes) -> pd.DataFrame:
    text = raw.decode("shift_jis", errors="replace")
    rows = []
    for line in text.splitlines():
        parts = line.split(",")
        d = parse_era_date(parts[0]) if parts else None
        if d is None:
            continue
        vals = [pd.to_numeric(x, errors="coerce") for x in parts[1:1 + len(JGB_TENORS)]]
        rows.append([d] + vals + [np.nan] * (len(JGB_TENORS) - len(vals)))
    df = pd.DataFrame(rows, columns=["date"] + JGB_TENORS).set_index("date")
    return df[~df.index.duplicated(keep="last")].sort_index()


def jgb_curve() -> pd.DataFrame:
    """日本国债到期收益率曲线（%），列 1Y…40Y。历史档 + 当月档合并（当月档更新）。"""
    def fetch():
        hist = _parse_mof(_get(MOF_ALL, timeout=120))
        try:
            cur = _parse_mof(_get(MOF_CUR))
            hist = pd.concat([hist, cur])
            hist = hist[~hist.index.duplicated(keep="last")].sort_index()
        except Exception as e:                          # noqa: BLE001
            log.warning("当月 JGB 档取不到（用历史档）：%s", e)
        return hist
    return _cached("mof_jgb_curve", fetch)


# ────────────────────────── 日本銀行 ──────────────────────────
def boj_series(code: str = "STRDCLUCON", db: str = "FM01", start_year: int = 1998) -> pd.Series:
    """日銀 時系列統計 API（日次系列按年分段取，避免单次返回过长）。默认 = 無担保コール O/N 物。"""
    def fetch():
        out = {}
        for y in range(start_year, dt.date.today().year + 1):
            url = (f"{BOJ_API}?format=json&lang=en&db={db}&code={code}"
                   f"&startDate={y}01&endDate={y}12")
            d = json.loads(_get(url))
            for r in d.get("RESULTSET") or []:
                v = r.get("VALUES") or {}
                for day, val in zip(v.get("SURVEY_DATES") or [], v.get("VALUES") or []):
                    if val is not None:
                        out[pd.Timestamp(str(day))] = float(val)
        return pd.Series(out, name=code).sort_index()
    return _cached(f"boj_{db}_{code}", fetch)


def boj_monthly(db: str, code: str, start: str = "196001") -> pd.Series:
    """日銀 API 的月度系列（例 PR01 企業物価指数、MD02 マネーストック）。索引 = 月初。"""
    def fetch():
        url = f"{BOJ_API}?format=json&lang=jp&db={db}&code={code}&startDate={start}&endDate={dt.date.today().year}12"
        out = {}
        for r in json.loads(_get(url)).get("RESULTSET") or []:
            v = r.get("VALUES") or {}
            for ym, val in zip(v.get("SURVEY_DATES") or [], v.get("VALUES") or []):
                if val is not None:
                    y, m = divmod(int(ym), 100)
                    out[pd.Timestamp(y, m, 1)] = float(val)
        return pd.Series(out, name=code).sort_index()
    return _cached(f"boj_{db}_{code}", fetch)


def tpu_monthly() -> pd.Series:
    """Caldara 等 贸易政策不确定性指数（月度，1960-；matteoiacoviello.com/tpu.htm）。索引 = 月初。"""
    def fetch():
        df = pd.read_excel(io.BytesIO(_get("https://www.matteoiacoviello.com/tpu_files/tpu_web_latest.xlsx", timeout=120)),
                           sheet_name="TPU_MONTHLY")
        return pd.Series(pd.to_numeric(df["TPU"], errors="coerce").to_numpy(), index=pd.to_datetime(df["DATE"]), name="TPU").dropna()
    return _cached("tpu_monthly", fetch, 24.0)


def shiller_cape() -> pd.Series:
    """Shiller CAPE（月度，econ.yale.edu；2026-09 核对时只更新到 2023-09 → 只用于历史研究）。索引 = 月初。"""
    def fetch():
        df = pd.read_excel(io.BytesIO(_get("http://www.econ.yale.edu/~shiller/data/ie_data.xls", timeout=120)),
                           sheet_name="Data", header=7)
        d = pd.to_numeric(df["Date"], errors="coerce")
        cape = pd.to_numeric(df["CAPE"], errors="coerce")
        ok = d.notna() & cape.notna()
        y = d[ok].astype(float)
        idx = [pd.Timestamp(int(v), int(round((v - int(v)) * 100)) or 1, 1) for v in y]
        return pd.Series(cape[ok].to_numpy(), index=pd.DatetimeIndex(idx), name="CAPE")
    return _cached("shiller_cape", fetch, 24.0)


def tankan(code: str) -> pd.Series:
    """日銀短観（季度 DI，db=CO）。索引 = 调查季度的最后一天（例 2026-06-30 = 6 月调查，7 月初公布）。"""
    def fetch():
        url = f"{BOJ_API}?format=json&lang=jp&db=CO&code={code}&startDate=197401&endDate={dt.date.today().year}04"
        out = {}
        for r in json.loads(_get(url)).get("RESULTSET") or []:
            v = r.get("VALUES") or {}
            for q, val in zip(v.get("SURVEY_DATES") or [], v.get("VALUES") or []):
                if val is not None:
                    y, k = divmod(int(q), 100)
                    out[pd.Timestamp(y, 3 * k, 1) + pd.offsets.MonthEnd(0)] = float(val)
        return pd.Series(out, name=code).sort_index()
    return _cached(f"boj_CO_{code}", fetch)


# ────────────────────────── 商品价格 / 地缘风险 ──────────────────────────
def yf_close(sym: str, max_age_h: float = 12.0) -> pd.Series:
    """yfinance 全历史收盘（复权）；商品 ETF / 期货连续合约 / 指数。"""
    def fetch():
        import logging
        import yfinance as yf
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
        h = yf.Ticker(sym).history(period="max", auto_adjust=True)
        if h.empty:
            raise RuntimeError(f"yfinance 没有 {sym}")
        h.index = h.index.tz_localize(None).normalize()
        c = h[~h.index.duplicated(keep="last")]["Close"]
        return c[c > 0].rename(sym)
    safe = "".join(ch if ch.isalnum() else "_" for ch in sym)
    return _cached(f"yf_{safe}", fetch, max_age_h)


def despike(s: pd.Series, jump: float = 0.25, back: float = 0.05) -> pd.Series:
    """单日涨跌超过 ±25%、第二天又几乎全部回去（两天合计 < ±5%）的报价视为错价（例 CPER 2014-12-04），用前一天的值代替。"""
    s = s.dropna()
    r = np.log(s).diff()
    bad = (r.abs() > jump) & ((r + r.shift(-1)).abs() < back)
    return s.mask(bad).ffill()


GPR_DAILY = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
GPR_MONTHLY = "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls"


def gpr_daily() -> pd.DataFrame:
    """Caldara & Iacoviello 日度地缘政治风险指数（1985-，每周一更新；CC BY，出处 matteoiacoviello.com/gpr.htm）。
    列：GPRD（总）、GPRD_THREAT（威胁）、GPRD_ACT（行动）。最新几周是初值，会小幅修订。"""
    def fetch():
        df = pd.read_excel(io.BytesIO(_get(GPR_DAILY, timeout=120)))
        df = df[pd.to_numeric(df["DAY"], errors="coerce").notna()]
        df.index = pd.to_datetime(df["DAY"].astype(int).astype(str), format="%Y%m%d")
        return df[["GPRD", "GPRD_THREAT", "GPRD_ACT"]].apply(pd.to_numeric, errors="coerce").dropna(how="all")
    return _cached("gpr_daily", fetch, 24.0)


def gpr_monthly(cols=("GPR", "GPRC_JPN", "GPRC_USA")) -> pd.DataFrame:
    """月度 GPR（含国别：GPRC_JPN = 提到日本的地缘风险文章占比）；每月初更新上月。索引 = 月初。"""
    def fetch():
        df = pd.read_excel(io.BytesIO(_get(GPR_MONTHLY, timeout=120)))
        df = df[pd.to_datetime(df["month"], errors="coerce").notna()]
        df.index = pd.to_datetime(df["month"])
        return df[list(cols)].apply(pd.to_numeric, errors="coerce").dropna(how="all")
    return _cached("gpr_monthly", fetch, 24.0)


# ────────────────────────── 汇总 ──────────────────────────
def macro_levels() -> pd.DataFrame:
    """所有免费宏观序列按日历日对齐（不前向填充；各市场按自己的可得时点再对齐）。"""
    cols = {}
    for k, sid in FRED_SERIES.items():
        try:
            cols[k] = fred(sid)
        except Exception as e:                          # noqa: BLE001
            log.warning("FRED %s 取不到：%s", sid, e)
    try:
        j = jgb_curve()
        for t in ("1Y", "2Y", "5Y", "10Y", "20Y", "30Y"):
            cols[f"jgb{t.lower()}"] = j[t]
    except Exception as e:                              # noqa: BLE001
        log.warning("JGB 曲线取不到：%s", e)
    try:
        cols["boj_call"] = boj_series()
    except Exception as e:                              # noqa: BLE001
        log.warning("日銀 コールレート取不到：%s", e)
    return pd.DataFrame(cols).sort_index()


# ────────────────────────── 日报用：多因子快照（只展示，不参与交易）──────────────────────────
PANEL = [  # (分组, 名称, 键, 单位, 类型) 类型：level = 水平；spread = 由两列相减
    ("美国利率", "联邦基金（实际成交）", "fed_funds", "%", None),
    ("美国利率", "美债 3 个月", "us3m", "%", None),
    ("美国利率", "美债 2 年", "us2y", "%", None),
    ("美国利率", "美债 10 年", "us10y", "%", None),
    ("美国利率", "美债 30 年", "us30y", "%", None),
    ("美国利率", "10 年 − 3 个月（倒挂 < 0）", ("us10y", "us3m"), "pt", None),
    ("美国利率", "实际利率 10 年", "us10y_real", "%", None),
    ("美国利率", "通胀预期 10 年", "us10y_bei", "%", None),
    ("日本利率", "日银 无担保 O/N", "boj_call", "%", None),
    ("日本利率", "日本国债 2 年", "jgb2y", "%", None),
    ("日本利率", "日本国债 10 年", "jgb10y", "%", None),
    ("日本利率", "日本国债 30 年", "jgb30y", "%", None),
    ("日本利率", "10 年 − 2 年", ("jgb10y", "jgb2y"), "pt", None),
    ("美日利差", "2 年（美 − 日）", ("us2y", "jgb2y"), "pt", None),
    ("美日利差", "10 年（美 − 日）", ("us10y", "jgb10y"), "pt", None),
    ("原油", "Brent 现货", "brent_spot", "$", None),
    ("原油", "Brent 期货（近月）", "brent_fut", "$", None),
    ("原油", "现货 − 期货（>0 = 现货紧张）", ("brent_spot", "brent_fut"), "$", None),
    ("原油", "WTI 现货", "wti_spot", "$", None),
    ("汇率·信用·波动", "美元日元", "usdjpy", "", None),
    ("汇率·信用·波动", "Baa − 美债 10 年 信用利差", "baa_spread", "pt", None),
    ("汇率·信用·波动", "VIX", "vix", "", None),
]
ETF_PANEL = [("TLT", "美长债 TLT"), ("GLD", "黄金 GLD"), ("UUP", "美元指数 UUP"), ("DBC", "商品 DBC"),
             ("EEM", "新兴市场 EEM"), (("HYG", "IEF"), "高收益债 − 中期国债"), (("IWM", "SPY"), "小盘 − 大盘"),
             (("XLU", "SPY"), "公用事业 − 大盘（防御轮动）")]
ETF_TICKERS = sorted({t for k, _ in ETF_PANEL for t in (k if isinstance(k, tuple) else (k,))})


def snapshot(levels: pd.DataFrame | None = None, brent_fut: pd.Series | None = None,
             etf: dict | None = None, years: int = 5) -> dict:
    """{"rows": [...], "etf": [...], "as_of": ...}：最新值、日期、20 个交易日变动、近 years 年分位（0～100）。"""
    lv = levels if levels is not None else macro_levels()
    lv = lv.copy()
    if brent_fut is not None:
        bf = brent_fut.copy()
        bf.index = pd.DatetimeIndex(bf.index).tz_localize(None).normalize()
        lv["brent_fut"] = bf[~bf.index.duplicated(keep="last")]
    rows = []
    for group, name, key, unit, _ in PANEL:
        if isinstance(key, tuple):
            if not all(k in lv for k in key):
                continue
            s = (lv[key[0]] - lv[key[1]]).dropna()
        elif key in lv:
            s = lv[key].dropna()
        else:
            continue
        if s.empty:
            continue
        rows.append(_row(group, name, s, unit, years))
    etf_rows = []
    for key, name in ETF_PANEL:
        try:
            if isinstance(key, tuple):
                a, b = etf[key[0]], etf[key[1]]
                r = (a.pct_change(20) - b.pct_change(20)).dropna() * 100
            else:
                r = etf[key].pct_change(20).dropna() * 100
        except (KeyError, TypeError):
            continue
        if r.empty:
            continue
        hist = r[r.index >= r.index[-1] - pd.Timedelta(days=365 * years)]
        etf_rows.append({"name": name, "ret20_pct": round(float(r.iloc[-1]), 2),
                         "date": str(pd.Timestamp(r.index[-1]).date()),
                         "pct_rank": round(float((hist < r.iloc[-1]).mean() * 100), 0)})
    return {"rows": rows, "etf": etf_rows, "years": years,
            "note": "只展示，不参与交易：2026-09-24 多因子研究（scripts/factor_study.py）样本外没有提高预测力"}


def _row(group: str, name: str, s: pd.Series, unit: str, years: int) -> dict:
    s = s.sort_index()
    last, d = float(s.iloc[-1]), pd.Timestamp(s.index[-1])
    chg20 = float(last - s.iloc[-21]) if len(s) > 21 else None
    hist = s[s.index >= d - pd.Timedelta(days=365 * years)]
    return {"group": group, "name": name, "value": round(last, 3), "unit": unit, "date": str(d.date()),
            "chg20": None if chg20 is None else round(chg20, 3),
            "pct_rank": round(float((hist < last).mean() * 100), 0),
            "stale": bool((pd.Timestamp.today().normalize() - d).days > 7)}
