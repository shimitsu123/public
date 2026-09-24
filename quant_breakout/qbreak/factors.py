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
