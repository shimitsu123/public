"""kline.py — 操作面板的 K 线：日K / 周K / 月K 的蜡烛 + MA5 / MA10 / MA20 / MA30 + 每个周期一个趋势标签
（2026-10-06 用户：「趋势也要能看到 趋势是做一个和图中一样的日周月的块块和线 方便看的」，参照同花顺的日K / 周K / 月K）。

只展示，不改交易。执行器每次运行把持仓个股、核心 ETF、「建议的股票」的 K 线写进数据目录 out/charts_<账本>.json
（不入库）；操作面板（本机 + 手机）打开某只票的图时才按需取（/api/chart），页面本身不内嵌这些数据。
周K = 每周（周五为一周的结束）实际交易日聚合：开 = 第一天开盘、高 / 低 = 最高 / 最低、收 = 最后一天收盘、量 = 合计，K 线的日期
= 那周最后一个交易日；月K 同理按月。休市的周 / 月没有 K 线；最新一根可能还没走完（本周 / 本月到最新收盘为止）。
MA 用全部历史算（窗口开头不缺）。趋势标签是均线位置的机械描述，不是预测：
  上升 = 收盘在 MA20 上、MA20 比 3 根前高、MA5 在 MA20 上；下降 = 三个条件都反过来；其余 = 震荡。
  多头排列 = MA5 > MA10 > MA20 > MA30；空头排列 = 反过来（MA30 还没有时只看前三条）。
"""
from __future__ import annotations

import math

import pandas as pd

MAS = (5, 10, 20, 30)
BARS = {"D": 250, "W": 160, "M": 120}            # 每个周期给页面的最近 K 线根数（日 ≈ 1 年、周 ≈ 3 年、月 = 10 年）
TF_NAME = {"D": "日K", "W": "周K", "M": "月K"}
LABELS = ("上升", "下降", "震荡")
SLOPE_BARS = 3                                     # MA20 的方向：比 3 根 K 线之前高 / 低


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _r(x, nd: int = 2) -> float | None:
    v = _num(x)
    return None if v is None else round(v, nd)


def ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """日线 → 干净的 Open / High / Low / Close / Volume（收盘缺的行去掉；开高低缺的用收盘补；量缺 = 0）。"""
    d = df.loc[df["Close"].astype(float).notna()].copy()
    c = d["Close"].astype(float)
    out = pd.DataFrame({"Close": c}, index=d.index)
    for k in ("Open", "High", "Low"):
        out[k] = d[k].astype(float).fillna(c) if k in d.columns else c
    out["High"] = out[["High", "Open", "Close"]].max(axis=1)
    out["Low"] = out[["Low", "Open", "Close"]].min(axis=1)
    out["Volume"] = d["Volume"].astype(float).fillna(0.0) if "Volume" in d.columns else 0.0
    return out[["Open", "High", "Low", "Close", "Volume"]].sort_index()


def bars(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """日线 → tf（D / W / M）的 K 线；W / M 的日期 = 那周 / 那月最后一个交易日。"""
    d = ohlcv(df)
    if tf == "D" or d.empty:
        return d
    key = d.index.to_period("W-FRI" if tf == "W" else "M")
    g = d.groupby(key)
    out = pd.DataFrame({"Open": g["Open"].first(), "High": g["High"].max(), "Low": g["Low"].min(),
                        "Close": g["Close"].last(), "Volume": g["Volume"].sum()})
    out.index = pd.DatetimeIndex(d.index.to_series().groupby(key).last().loc[out.index].to_numpy())
    return out


def trend(b: pd.DataFrame) -> dict | None:
    """一个周期的趋势标签（见模块说明）；K 线不到 MA20 + 3 根 → None。"""
    c = b["Close"].astype(float)
    if len(c) < 20 + SLOPE_BARS:
        return None
    m = {k: c.rolling(k).mean() for k in MAS}
    last, m5, m10, m20 = float(c.iloc[-1]), float(m[5].iloc[-1]), float(m[10].iloc[-1]), float(m[20].iloc[-1])
    m30 = _num(m[30].iloc[-1])
    prev20 = float(m[20].iloc[-1 - SLOPE_BARS])
    slope = (m20 / prev20 - 1) * 100 if prev20 > 0 else 0.0
    if last > m20 and slope > 0 and m5 > m20:
        lab = "上升"
    elif last < m20 and slope < 0 and m5 < m20:
        lab = "下降"
    else:
        lab = "震荡"
    seq = [m5, m10, m20] + ([m30] if m30 is not None else [])
    align = ("多头排列" if all(a > b_ for a, b_ in zip(seq, seq[1:])) else
             "空头排列" if all(a < b_ for a, b_ in zip(seq, seq[1:])) else "")
    chg = (last / float(c.iloc[-2]) - 1) * 100 if float(c.iloc[-2]) > 0 else None
    return {"label": lab, "align": align, "above20": last > m20, "slope20_pct": round(slope, 2),
            "chg_pct": _r(chg), "close": _r(last), "ma20": _r(m20), "date": str(b.index[-1].date())}


def series(b: pd.DataFrame, n: int) -> dict:
    """最近 n 根 K 线（列式：d / o / h / l / c / v / ma5 / ma10 / ma20 / ma30）。"""
    c = b["Close"].astype(float)
    ma = {f"ma{k}": c.rolling(k).mean() for k in MAS}
    t = b.tail(int(n))
    ix = t.index
    out = {"d": [str(x.date()) for x in ix], "o": [_r(x) for x in t["Open"]], "h": [_r(x) for x in t["High"]],
           "l": [_r(x) for x in t["Low"]], "c": [_r(x) for x in t["Close"]],
           "v": [int(x) if _num(x) is not None else 0 for x in t["Volume"]]}
    for k, s in ma.items():
        out[k] = [_r(x) for x in s.loc[ix]]
    return out


def payload(df: pd.DataFrame, bar_date=None, info: dict | None = None) -> dict | None:
    """一只票三个周期的 K 线 + 趋势标签；info（kind / name / entry_px / entry_date / stop_px / signal_date）原样带上。"""
    if df is None or not len(df):
        return None
    d = df.loc[:pd.Timestamp(str(bar_date))] if bar_date else df
    if d["Close"].astype(float).notna().sum() < 2:
        return None
    out = {**(info or {}), "tf": {}, "trend": {}}
    for tf in ("D", "W", "M"):
        b = bars(d, tf)
        if len(b) < 2:
            continue
        out["tf"][tf] = series(b, BARS[tf])
        tr = trend(b)
        if tr is not None:
            out["trend"][tf] = tr
    return out if out["tf"] else None


def trends(df: pd.DataFrame, bar_date=None) -> dict:
    """只要三个周期的趋势标签（汇总 / 卡片用；不带 K 线）。"""
    if df is None or not len(df):
        return {}
    d = df.loc[:pd.Timestamp(str(bar_date))] if bar_date else df
    out = {}
    for tf in ("D", "W", "M"):
        tr = trend(bars(d, tf))
        if tr is not None:
            out[tf] = tr
    return out


def chips(tr: dict | None) -> str:
    """「日 上升 · 周 震荡 · 月 上升」（日志 / 命令行用）。"""
    tr = tr or {}
    return " · ".join(f"{TF_NAME[k][0]} {tr[k]['label']}" for k in ("D", "W", "M") if k in tr) or "—"


__all__ = ["MAS", "BARS", "TF_NAME", "LABELS", "ohlcv", "bars", "trend", "series", "payload", "trends", "chips"]
