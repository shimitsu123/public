"""kline.py — 操作面板的 K 线：日K / 周K / 月K 的蜡烛 + MA5 / MA10 / MA20 / MA30 + 每个周期一个趋势标签
（2026-10-06 用户：「趋势也要能看到 趋势是做一个和图中一样的日周月的块块和线 方便看的」，参照同花顺的日K / 周K / 月K）。

只展示，不改交易。执行器每次运行把持仓个股、核心 ETF、「建议的股票」的 K 线写进数据目录 out/charts_<账本>.json
（不入库）；操作面板（本机 + 手机）打开某只票的图时才按需取（/api/chart），页面本身不内嵌这些数据。
周K = 每周（周五为一周的结束）实际交易日聚合：开 = 第一天开盘、高 / 低 = 最高 / 最低、收 = 最后一天收盘、量 = 合计，K 线的日期
= 那周最后一个交易日；月K 同理按月。休市的周 / 月没有 K 线；最新一根可能还没走完（本周 / 本月到最新收盘为止）。
MA 用全部历史算（窗口开头不缺）。趋势标签是均线位置的机械描述，不是预测：
副图（2026-10-06 用户「加 MACD（规则用的就是它）或 DMI 副图」）：MACD = 规则同一组参数（StrategyParams 12 / 26 / 9，EMA；
  柱 = DIF − DEA，同花顺的柱是它的 2 倍、形状一样）；DMI = 同花顺 / 通达信的写法（N 14、M 6：+DI / −DI 用 N 根的简单合计，
  ADX = |+DI − −DI| ÷ (+DI + −DI) × 100 的 M 根平均，ADXR = (ADX + M 根前的 ADX) ÷ 2）；都在那个周期的 K 线上、用全部历史算。
趋势线（qbreak/trendline.py：连波谷的支撑线、连波峰的压力线、往后延长的虚线、破线点）也在每个周期上算（tl）。
  上升 = 收盘在 MA20 上、MA20 比 3 根前高、MA5 在 MA20 上；下降 = 三个条件都反过来；其余 = 震荡。
  多头排列 = MA5 > MA10 > MA20 > MA30；空头排列 = 反过来（MA30 还没有时只看前三条）。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

MAS = (5, 10, 20, 30)
BARS = {"D": 250, "W": 160, "M": 120}            # 每个周期给页面的最近 K 线根数（日 ≈ 1 年、周 ≈ 3 年、月 = 10 年）
DMI_N, DMI_M = 14, 6                              # 同花顺 DMI 的默认参数
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


def macd(b: pd.DataFrame) -> dict[str, pd.Series]:
    """规则同一组参数的 MACD（qbreak.strategy.macd）：dif / dea / mh（柱 = DIF − DEA）。"""
    from .config import StrategyParams
    from .strategy import macd as _macd
    p = StrategyParams()
    dif, dea, mh = _macd(b["Close"].astype(float), p.macd_fast, p.macd_slow, p.macd_signal)
    return {"dif": dif, "dea": dea, "mh": mh}


def dmi(b: pd.DataFrame, n: int = DMI_N, m: int = DMI_M) -> dict[str, pd.Series]:
    """同花顺 / 通达信写法的 DMI：pdi（+DI）/ mdi（−DI）/ adx / adxr（见模块说明）。"""
    h, lo, c = (b[k].astype(float) for k in ("High", "Low", "Close"))
    pc = c.shift(1)
    tr = pd.Series(np.fmax(np.fmax((h - lo).to_numpy(), (h - pc).abs().to_numpy()), (lo - pc).abs().to_numpy()), index=b.index)
    hd, ld = h - h.shift(1), lo.shift(1) - lo
    dmp = hd.where((hd > 0) & (hd > ld), 0.0)
    dmm = ld.where((ld > 0) & (ld > hd), 0.0)
    trs = tr.rolling(n).sum().replace(0.0, np.nan)
    pdi, mdi = dmp.rolling(n).sum() * 100 / trs, dmm.rolling(n).sum() * 100 / trs
    adx = ((mdi - pdi).abs() / (mdi + pdi).replace(0.0, np.nan) * 100).rolling(m).mean()
    return {"pdi": pdi, "mdi": mdi, "adx": adx, "adxr": (adx + adx.shift(m)) / 2}


def series(b: pd.DataFrame, n: int) -> dict:
    """最近 n 根 K 线（列式：d / o / h / l / c / v / ma5 / ma10 / ma20 / ma30 + 副图 dif / dea / mh / pdi / mdi / adx / adxr）。"""
    c = b["Close"].astype(float)
    ma = {f"ma{k}": c.rolling(k).mean() for k in MAS}
    t = b.tail(int(n))
    ix = t.index
    out = {"d": [str(x.date()) for x in ix], "o": [_r(x) for x in t["Open"]], "h": [_r(x) for x in t["High"]],
           "l": [_r(x) for x in t["Low"]], "c": [_r(x) for x in t["Close"]],
           "v": [int(x) if _num(x) is not None else 0 for x in t["Volume"]]}
    for k, s in ma.items():
        out[k] = [_r(x) for x in s.loc[ix]]
    for k, s in macd(b).items():
        out[k] = [_r(x, 3) for x in s.loc[ix]]
    for k, s in dmi(b).items():
        out[k] = [_r(x, 1) for x in s.loc[ix]]
    return out


def payload(df: pd.DataFrame, bar_date=None, info: dict | None = None) -> dict | None:
    """一只票三个周期的 K 线 + 趋势标签；info（kind / name / entry_px / entry_date / stop_px / signal_date）原样带上。"""
    if df is None or not len(df):
        return None
    d = df.loc[:pd.Timestamp(str(bar_date))] if bar_date else df
    if d["Close"].astype(float).notna().sum() < 2:
        return None
    from .config import StrategyParams
    sp = StrategyParams()
    out = {**(info or {}), "tf": {}, "trend": {}, "ind": {"macd": [sp.macd_fast, sp.macd_slow, sp.macd_signal], "dmi": [DMI_N, DMI_M]}}
    for tf in ("D", "W", "M"):
        b = bars(d, tf)
        if len(b) < 2:
            continue
        out["tf"][tf] = series(b, BARS[tf])
        tl = _trendline(b, tf)
        if tl is not None:
            out["tf"][tf]["tl"] = tl
        tr = trend(b)
        if tr is not None:
            out["trend"][tf] = tr
    return out if out["tf"] else None


def _trendline(b: pd.DataFrame, tf: str) -> dict | None:
    """那个周期最后一根时的趋势线（qbreak/trendline.summary；锚点位置按给页面的最近 BARS 根算）；算不出 → None。"""
    from . import trendline as TL
    try:                                                                 # 最后 BARS 根用得到的只有之前 L 根（ATR 的平滑 300 根后差 < 1e-9）→ 只扫这一段
        return TL.summary(b.tail(BARS[tf] + TL.PARAMS[tf][1] + 300), tf, BARS[tf])
    except Exception:                                                    # noqa: BLE001  只展示：算不出就不画
        return None


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


__all__ = ["MAS", "BARS", "TF_NAME", "LABELS", "DMI_N", "DMI_M", "ohlcv", "bars", "trend", "macd", "dmi", "series", "payload",
           "trends", "chips"]
