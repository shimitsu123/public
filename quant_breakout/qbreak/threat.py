"""threat.py — 「大事件威胁指数」：把历史上大跌之前常见的因素做成 0–100 的综合分（只用当时已公布的数据）。

每个因素换成「扩张窗口百分位」（在它自己过去全部历史里排第几；至少 3 年历史才开始用），等权平均 → 0–100。
不拟合任何系数（避免过度拟合）。因素（方向：越高越危险）：
  vix      VIX 水平                           vix_d20  VIX 20 日变化
  credit   Baa−10Y 利差 60 日变化（走阔）       curve    −(10Y−3M)（越倒挂越高）
  rates    美 10Y 利率 60 日变化（急升）         oil      WTI 60 日涨幅（油价冲击）
  jobs     失业率 3 个月均值 − 过去 12 个月最低（Sahm 型；按公布时滞）
  rvol     指数 20 日实现波动（年化）
  （日経另加）yen  −(USD/JPY 20 日变化，%)（日元急升）   jgb  日本 10Y 60 日变化
时滞：VIX / 指数 / 汇率当天收盘可用；Baa、美债、WTI 滞后 1 个营业日；失业率次月 10 日起可用；日本 10Y 当天（財務省）。
研究与是否用于交易见 scripts/threat_index_study.py；日报展示当前值与历史同档位后的大跌频率。
"""
from __future__ import annotations

import bisect

import numpy as np
import pandas as pd

from .timing import monthly_available

US_COLS = ["vix", "vix_d20", "credit", "curve", "rates", "oil", "jobs", "rvol"]
JP_COLS = US_COLS + ["yen", "jgb"]
LABELS = {"vix": "VIX 水平", "vix_d20": "VIX 20 日变化", "credit": "信用利差走阔", "curve": "利率曲线倒挂",
          "rates": "美债利率急升", "oil": "油价冲击", "jobs": "失业率上升", "rvol": "指数波动", "yen": "日元急升",
          "jgb": "日债利率急升"}
MIN_N = 750


def _daily(s: pd.Series, days: pd.DatetimeIndex, lag: int = 0) -> pd.Series:
    s = s.dropna()
    return s.reindex(days.union(s.index)).ffill().reindex(days).shift(lag)


def raw_features(days: pd.DatetimeIndex, close: pd.Series, vix: pd.Series, baa: pd.Series, dgs10: pd.Series,
                 dgs3m: pd.Series, wti: pd.Series, unrate: pd.Series, usdjpy: pd.Series | None = None,
                 jgb10: pd.Series | None = None) -> pd.DataFrame:
    """days：该市场的交易日；close：该市场指数收盘（与 days 对齐）。美国因素对日本交易日用「前一个美国收盘」的值
    （调用方把 days 传成日本交易日时，先把美国序列错开一天：见 us_asof_for_jp）。"""
    f = pd.DataFrame(index=days)
    v = _daily(vix, days)
    f["vix"] = v
    f["vix_d20"] = v - v.shift(20)
    b = _daily(baa, days, 1)
    f["credit"] = b - b.shift(60)
    f["curve"] = -(_daily(dgs10, days, 1) - _daily(dgs3m, days, 1))
    r10 = _daily(dgs10, days, 1)
    f["rates"] = r10 - r10.shift(60)
    w = _daily(wti.where(wti > 0), days, 1)
    f["oil"] = w / w.shift(60) - 1
    un = unrate.dropna()
    sahm = un.rolling(3).mean() - un.rolling(3).mean().rolling(12).min()
    f["jobs"] = monthly_available(sahm, days)
    c = close.reindex(days)
    f["rvol"] = np.log(c).diff().rolling(20).std() * np.sqrt(252)
    if usdjpy is not None:
        fx = _daily(usdjpy, days)
        f["yen"] = -(fx / fx.shift(20) - 1) * 100
    if jgb10 is not None:
        j = _daily(jgb10, days)
        f["jgb"] = j - j.shift(60)
    return f


def expanding_pct(x: pd.Series, min_n: int = MIN_N) -> pd.Series:
    """x_t 在 x_0..x_t（有效值）里的百分位（0–1，含自己；平局取中位）。历史不足 min_n 个有效值时为 NaN。"""
    out = np.full(len(x), np.nan)
    hist: list[float] = []
    for i, v in enumerate(x.to_numpy(float)):
        if not np.isfinite(v):
            continue
        bisect.insort(hist, v)
        n = len(hist)
        if n >= min_n:
            lo, hi = bisect.bisect_left(hist, v), bisect.bisect_right(hist, v)
            out[i] = (lo + hi) / 2 / n
    return pd.Series(out, index=x.index)


def threat_index(raw: pd.DataFrame, cols: list[str], min_n: int = MIN_N) -> tuple[pd.Series, pd.DataFrame]:
    """等权平均各因素的扩张百分位 → 0–100；至少一半因素可用才给值。返回 (指数, 各因素百分位)。"""
    pct = pd.DataFrame({c: expanding_pct(raw[c], min_n) for c in cols if c in raw})
    ok = pct.notna().sum(axis=1) >= max(1, len(cols) // 2)
    idx = (pct.mean(axis=1) * 100).where(ok)
    return idx, pct


def us_asof_for_jp(s: pd.Series, jp_days: pd.DatetimeIndex) -> pd.Series:
    """美国的日序列 → 日本交易日 D 早上已知的值（D 之前最后一个美国收盘）。"""
    s = s.dropna()
    prev = jp_days - pd.Timedelta(days=1)
    v = s.reindex(s.index.union(prev)).ffill().reindex(prev)
    return pd.Series(v.to_numpy(float), index=jp_days)


def forward_drawdown(close: pd.Series, n: int = 60) -> pd.Series:
    """今天收盘之后 n 个交易日内的最低收盘相对今天的跌幅（负数；最后 n 天为 NaN）。"""
    c = close.to_numpy(float)
    out = np.full(len(c), np.nan)
    for i in range(len(c) - n):
        out[i] = c[i + 1:i + 1 + n].min() / c[i] - 1
    return pd.Series(out, index=close.index)


def auc(score: pd.Series, event: pd.Series) -> float | None:
    """ROC AUC（Mann–Whitney），只用两者都有值的日子。"""
    d = pd.DataFrame({"s": score, "e": event}).dropna()
    pos, neg = d[d["e"] > 0.5]["s"], d[d["e"] <= 0.5]["s"]
    if len(pos) == 0 or len(neg) == 0:
        return None
    r = d["s"].rank()
    return float((r[d["e"] > 0.5].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


# ══════════════════════════ 日报用：最新读数 ══════════════════════════
def _yf_close(sym: str) -> pd.Series:
    import logging
    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    h = yf.Ticker(sym).history(period="max", auto_adjust=True)
    h.index = h.index.tz_localize(None).normalize()
    return h[~h.index.duplicated(keep="last")]["Close"]


def load_inputs() -> dict:
    """指数（yfinance 全历史）+ FRED + 財務省日本 10Y。与 scripts/threat_index_study.py 同一口径。"""
    from . import factors
    from .calendar_jp import now_jst
    spx = _yf_close("^GSPC")
    spx = spx[spx.index < pd.Timestamp(now_jst().date())]                  # 日本早上：美国前一日收盘已确定
    n225 = _yf_close("^N225")
    n = now_jst()
    if n.hour < 16 and len(n225) and n225.index[-1].date() == n.date():   # 当天未收盘的日経 K 线不用
        n225 = n225.iloc[:-1]
    fx = factors.fred("DEXJPUS").dropna()
    try:
        jpyx = _yf_close("JPY=X")
        jpyx = jpyx[(jpyx > 60) & (jpyx < 250) & (jpyx.index > fx.index[-1])]
        fx = pd.concat([fx, jpyx]).sort_index()
        fx = fx[~fx.index.duplicated(keep="first")]
    except Exception:                                                     # noqa: BLE001
        pass
    raw = {k: factors.fred(k) for k in ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "DCOILWTICO", "UNRATE")}
    return {"spx": spx, "n225": n225, "fx": fx, "raw": raw, "jgb": factors.jgb_curve()["10Y"].dropna()}


def build(d: dict) -> dict:
    """{"US": (指数, 百分位表), "JP": (…)}；日経用美国因素时取「前一个美国收盘」。"""
    r = d["raw"]
    us_days = d["spx"].index[d["spx"].index >= "1990-01-01"]
    raw_us = raw_features(us_days, d["spx"], r["VIXCLS"], r["BAA10Y"], r["DGS10"], r["DGS3MO"], r["DCOILWTICO"], r["UNRATE"])
    jp_days = d["n225"].index[d["n225"].index >= "1990-01-01"]
    m = {k: us_asof_for_jp(r[k], jp_days) for k in ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "DCOILWTICO")}
    raw_jp = raw_features(jp_days, d["n225"], m["VIXCLS"], m["BAA10Y"], m["DGS10"], m["DGS3MO"], m["DCOILWTICO"],
                          r["UNRATE"], usdjpy=us_asof_for_jp(d["fx"], jp_days), jgb10=d["jgb"].shift(1))
    return {"US": threat_index(raw_us, US_COLS), "JP": threat_index(raw_jp, JP_COLS)}


def snapshot(built: dict | None = None, table: dict | None = None, events: list | None = None,
             today=None, horizon_days: int = 45) -> dict:
    """最新读数 + 同档位的历史频率（var/threat_index.json）+ 接下来的已知大事件日程（var/macro_events.json）。只展示。"""
    from . import paths
    from .utils import read_json
    built = built if built is not None else build(load_inputs())
    table = table if table is not None else (read_json(paths.home() / "threat_index.json", {}) or {})
    out = {"note": "只展示，不参与交易（2026-09-25 事先登记研究：美股 AUC 0.66、日経 0.58，不足以预测时间段）",
           "event_def": table.get("event", "之后 60 个交易日内最低收盘比当天跌 ≥10%")}
    for m in ("US", "JP"):
        idx, pct = built[m]
        s = idx.dropna()
        if s.empty:
            continue
        v = float(s.iloc[-1])
        t = table.get(m) or {}
        dec = next((b for b in t.get("deciles", []) if b["lo"] <= v < b["hi"]), None)
        top = pct.loc[s.index[-1]].dropna().sort_values(ascending=False)
        out[m] = {"date": str(s.index[-1].date()), "value": round(v, 1), "prev20": round(float(s.iloc[-21]), 1) if len(s) > 20 else None,
                  "band": f"{dec['lo']}–{dec['hi']}" if dec else None, "band_freq": dec["freq"] if dec else None,
                  "base_rate": t.get("base_rate"), "auc": [t.get("auc_h1"), t.get("auc_h2")],
                  "hit80": t.get("episodes_hit80"),
                  "top": [{"k": k, "label": LABELS[k], "pct": round(float(p) * 100)} for k, p in top.head(3).items()]}
    ev = events if events is not None else (read_json(paths.home() / "macro_events.json", {}) or {})
    ev = ev.get("events", ev) if isinstance(ev, dict) else ev
    d0 = pd.Timestamp(today or pd.Timestamp.today().normalize())
    out["events"] = [e for e in (ev or []) if d0 <= pd.Timestamp(e.get("date", "1900-01-01")) <= d0 + pd.Timedelta(days=horizon_days)]
    out["events"].sort(key=lambda e: e["date"])
    return out
