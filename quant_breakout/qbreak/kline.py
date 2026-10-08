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
页面上的说法（2026-10-07 用户：「K线解释换成通俗易懂的说法 横展开」）：数据里的标签不变，显示时换成 PLAIN / ALIGN_PLAIN / CHAN_PLAIN
  （操作面板、日志都从这里取）：上升 → 往上走、下降 → 往下走、震荡 → 横着走；多头排列 → 涨势整齐、空头排列 → 跌势整齐。
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
PLAIN = {"上升": "往上走", "下降": "往下走", "震荡": "横着走"}                 # 页面 / 日志上的说法（数据里的标签不变）
ALIGN_PLAIN = {"多头排列": "涨势整齐", "空头排列": "跌势整齐"}
UNIT = {"D": "天", "W": "周", "M": "个月"}                                      # 一根 K 线 = 一天 / 一周 / 一个月
CHAN_PLAIN = {"上升通道": "两条线都往上：股价在往上走的通道里",
              "下降通道": "两条线都往下：股价在往下走的通道里",
              "横盘通道": "两条线都差不多是平的：股价在一个箱子里上下",
              "对称三角": "下面的线往上、上面的线往下：越收越窄，快要选方向",
              "上升三角": "下面的线往上、上面的线是平的：低点越垫越高，顶着同一个价位",
              "下降三角": "下面的线是平的、上面的线往下：高点越压越低，底在同一个价位",
              "扩散": "两条线越张越开：上下波动越来越大"}
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


def month_up(b: pd.DataFrame, n: int = 3) -> bool | None:
    """月K：最后一根（本月到最新收盘为止）是上升，且之前 n 根已完成的月K（各自那个月最后一天收盘时的标签）也都是上升 → True；
    最后一根不是上升或之前有一根不是上升 → False；标签算不出（月K 不够 23 + n 根）→ None。
    = 登记研究 scripts/month_up_dip_study.py 的「月线一段时间上涨」MUB（qbreak/kline_series.mub，n = 3）；面板的历史统计（qbreak/dip_stats.py）用。"""
    if b is None or len(b) < 20 + SLOPE_BARS + n:
        return None
    labs = [trend(b.iloc[:len(b) - k]) for k in range(n + 1)]
    if any(x is None for x in labs):
        return None
    return all(x["label"] == "上升" for x in labs)


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
            if tf == "M":
                tr["up3"] = month_up(b)                     # 前 3 个已完成月K 也都往上走（面板的历史统计用）
            out["trend"][tf] = tr
    return out if out["tf"] else None


LIST_KEYS = ("d", "o", "h", "l", "c", "v", "ma5", "ma10", "ma20", "ma30", "dif", "dea", "mh", "pdi", "mdi", "adx", "adxr")


def with_live(pl: dict | None, bar: dict | None, at: str | None = None) -> dict | None:
    """持仓的「今天这一根」（2026-10-07 用户：「现在持有的ETF/股票等等当天日线在交易时间在K线中要随时价钱反映」）：
    bar = 那一天到 at 为止的 1 分钟线合计 {"d", "o", "h", "l", "c", "v"}（qbreak/data.intraday_quotes；约晚 20 分钟）。
    日K：图里还没有这一天 → 加一根；周K / 月K：同一周 / 同一个月 → 并进最后一根（高 / 低取大小、收 = 现价、量相加），否则新开一根；
    图里已经有这一天（正式日线）→ 不动。最后一根的均线 / MACD / DMI 用这一段重新算（之前的不动；MACD 的 EMA 从窗口开头起算，
    250 / 160 / 120 根之后和全部历史的差可以忽略），趋势线的「现在的位置 / 离收盘多远」跟着最后一根更新。不改原来的 pl。只展示。"""
    if not pl or not bar or not pl.get("tf"):
        return pl
    try:
        d = pd.Timestamp(str(bar["d"]))
        o, h, lo, c, v = (float(bar[k]) for k in ("o", "h", "l", "c", "v"))
    except (KeyError, TypeError, ValueError):
        return pl
    if not all(math.isfinite(x) for x in (o, h, lo, c)) or c <= 0:
        return pl
    out = {**pl, "tf": dict(pl["tf"])}
    done = []
    for tf, sr in pl["tf"].items():
        try:
            s2 = _live_tf(tf, sr, d, o, h, lo, c, v)
        except Exception:                                                # noqa: BLE001  只展示：这一个周期并不进去就照旧
            s2 = None
        if s2 is not None:
            out["tf"][tf] = s2
            done.append(tf)
    if not done:
        return pl
    out["live"] = {"d": d.date().isoformat(), "at": at, "tf": done}
    return out


def _live_tf(tf: str, sr: dict, d: pd.Timestamp, o: float, h: float, lo: float, c: float, v: float) -> dict | None:
    """with_live 的一个周期：并进去之后的那一段（不并 → None：图里已经有这一天、数据不全）。"""
    dd = sr.get("d") or []
    if len(dd) < 2 or any(len(sr.get(k) or []) != len(dd) for k in ("o", "h", "l", "c", "v")):
        return None
    last = pd.Timestamp(dd[-1])
    if d <= last:
        return None                                                      # 图里已经有这一天（或更新的）
    df = pd.DataFrame({"Open": sr["o"], "High": sr["h"], "Low": sr["l"], "Close": sr["c"], "Volume": sr["v"]},
                      index=pd.DatetimeIndex(dd), dtype=float)
    frq = {"W": "W-FRI", "M": "M"}.get(tf)
    same = frq is not None and d.to_period(frq) == last.to_period(frq)
    if same:                                                             # 同一周 / 同一个月：并进最后一根
        r = df.iloc[-1]
        row = [r["Open"] if math.isfinite(r["Open"]) else o, float(np.nanmax([r["High"], h])), float(np.nanmin([r["Low"], lo])), c,
               (r["Volume"] if math.isfinite(r["Volume"]) else 0.0) + v]
        df = pd.concat([df.iloc[:-1], pd.DataFrame([row], columns=df.columns, index=pd.DatetimeIndex([d]))])
    else:
        df = pd.concat([df, pd.DataFrame([[o, h, lo, c, v]], columns=df.columns, index=pd.DatetimeIndex([d]))])
    new = series(df, len(df))
    s2 = {k: x for k, x in sr.items() if k not in LIST_KEYS}
    for k in LIST_KEYS:
        old = list(sr.get(k) or [])
        s2[k] = (old[:-1] if same else old) + [new[k][-1]]
    tl = sr.get("tl")
    if tl:                                                               # 趋势线：现在的位置（最后一根）、离收盘多远
        tl = {**tl}
        n1 = len(s2["d"]) - 1
        for side in ("sup", "res"):
            L = tl.get(side)
            if L and L.get("y1") is not None and L.get("b") is not None and L.get("i1") is not None:
                now = float(L["y1"]) + float(L["b"]) * (n1 - int(L["i1"]))
                tl[side] = {**L, "now": _r(now), "dist_pct": _r((now / c - 1) * 100)}
        if tl.get("sup") and tl.get("res"):
            w = tl["res"]["now"] - tl["sup"]["now"]
            tl["pos"] = _r((c - tl["sup"]["now"]) / w * 100, 0) if w and w > 0 else None
        s2["tl"] = tl
    return s2


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
        b = bars(d, tf)
        tr = trend(b)
        if tr is not None:
            if tf == "M":
                tr["up3"] = month_up(b)
            out[tf] = tr
    return out


def plain(label) -> str:
    """数据里的趋势标签 → 页面上的说法（上升 → 往上走 …）；不认识的原样。"""
    return PLAIN.get(str(label), str(label or "—"))


def chips(tr: dict | None) -> str:
    """「日K 往上走 · 周K 横着走 · 月K 往上走」（日志 / 命令行用）。"""
    tr = tr or {}
    return " · ".join(f"{TF_NAME[k]} {plain(tr[k]['label'])}" for k in ("D", "W", "M") if k in tr) or "—"


__all__ = ["MAS", "BARS", "TF_NAME", "LABELS", "PLAIN", "ALIGN_PLAIN", "UNIT", "CHAN_PLAIN", "DMI_N", "DMI_M", "ohlcv", "bars", "month_up",
           "trend", "macd", "dmi", "series", "payload", "trends", "chips", "plain", "with_live", "LIST_KEYS"]
