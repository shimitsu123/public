"""idle_cash.py — 没有个股可买时，闲置资金拿什么（var/sim.json 的 "idle_cash"；2026-09-29 用户要求：
「当没有候选股票的时候默认不要选择 sp500 可以选一个更稳定的也可以 换汇也可以 要考虑各国外汇兑日元的趋势 或者黄金 etf 石油 etf
什么的做空也可以 如果立花上面可以交易的话」）。

只作用在 qbreak/unified.py 的引擎（模拟盘、执行器、它们的演练账户）；基准账户（原规则）照旧 1655 + 美股牛熊分界。
立花 ｅ支店能做的（2026-09-29 查官方公开页面，仅对检索时点有效）：现物可以买卖东证上市的 ETF / ETN（含反向型）；
FX、外币存款、MMF、投信、美股 ｅ支店都没有；做空个股 / ETF 要另开信用账户（制度信用、只限貸借銘柄、保证金 ≥ 30 万円），
执行器只做现物 → 「做空」= 现物买反向 ETF；「换汇」= 东证的美国短期国债 ETF（不对冲，= 美元现金 + 美国短期利息；
欧元只有 2026-08 才上市、每天只成交约 133 万円的 613A，澳元没有短期品种 → 能买到量的只有美元）。
  K0 原规则：1655（S&P500）按美股牛熊分界，熊市那份留现金
  K1 现金：闲置资金不买任何东西（最稳定）
  K2 黄金趋势：1540 純金上場信託；月末收盘 > 最近 10 个月末收盘的平均（含这个月末）→ 下个月拿，否则现金
  K3 美元趋势：133A 超短期米国債（円換算、不对冲）；同一个 10 个月规则（看 ETF 自己的日元价 = 汇率 + 利息）
  K4 原油趋势：1671 WTI 原油（先物型）；同一个 10 个月规则
  K5 美股熊市做空：美股牛熊分界 = 熊 → 2238 S&P500 インバース（−1 倍，先物型）；牛 → 现金
  K6 趋势轮动：每个月末在 1540 / 133A / 1671 / 2238 里拿过去 12 个月涨得最多的那一只（最多的也 ≤ 0 → 现金）
月末 = 那个月最后一个交易日：收盘时决定、第二天开盘换（与引擎的牛熊分界同一个时点）；实时最后一个月只有「今天就是本月最后一个
交易日」才算（run.py 按东证日历判断）。选哪一个：scripts/idle_cash_study.py（登记后只跑一次）按事先写定的规则选，结果写进 var/sim.json。
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

TREND_MONTHS = 10
MOM_MONTHS = 12
ROT = ("1540.T", "133A.T", "1671.T", "2238.T")
MODES: dict[str, dict] = {
    "K0": {"core": {"1655.T": 1.0}, "core_index": {"1655.T": "US"}, "core_mode": "split"},
    "K1": {"core": {}, "core_index": {}, "core_mode": "split"},
    "K2": {"core": {"1540.T": 1.0}, "core_index": {"1540.T": "TR:1540.T"}, "core_mode": "split"},
    "K3": {"core": {"133A.T": 1.0}, "core_index": {"133A.T": "TR:133A.T"}, "core_mode": "split"},
    "K4": {"core": {"1671.T": 1.0}, "core_index": {"1671.T": "TR:1671.T"}, "core_mode": "split"},
    "K5": {"core": {"2238.T": 1.0}, "core_index": {"2238.T": "XR"}, "core_mode": "split"},
    "K6": {"core": {t: 1.0 for t in ROT}, "core_index": {t: f"RT:{t}" for t in ROT}, "core_mode": "follow"},
}
LABELS = {"K0": "1655 S&P500 + 美股牛熊分界（原规则）", "K1": "现金", "K2": "黄金趋势 1540（10 个月均线）",
          "K3": "美元趋势 133A 超短期美债（10 个月均线）", "K4": "原油趋势 1671（10 个月均线）",
          "K5": "美股熊市买 S&P500 反向 2238、牛市现金", "K6": "趋势轮动（1540 / 133A / 1671 / 2238 取 12 个月最强）"}
NAMES = {"1655.T": "S&P500（1655）", "1540.T": "黄金（1540）", "133A.T": "美元短期国债（133A）", "1671.T": "WTI 原油（1671）",
         "2238.T": "S&P500 反向（2238）"}


def mode_of(cfg: dict | None) -> str:
    """var/sim.json → 闲置资金方式（没写 / 写错 → K0 = 原规则）。"""
    m = str(((cfg or {}).get("idle_cash") or {}).get("mode") or "K0")
    return m if m in MODES else "K0"


def month_ends(idx: pd.DatetimeIndex, last_complete: bool = False) -> pd.DatetimeIndex:
    """索引里每个月最后一个交易日；最后一个月只有 last_complete = True 才算（实时：今天是本月最后一个交易日）。"""
    idx = pd.DatetimeIndex(idx).sort_values().unique()
    if not len(idx):
        return idx
    me = pd.DatetimeIndex(pd.Series(idx, index=idx).groupby(idx.to_period("M")).max().to_numpy())
    if not last_complete and len(me) and me[-1] == idx[-1]:
        me = me[:-1]
    return me


def _daily(flags: pd.Series, idx: pd.DatetimeIndex, before: bool) -> pd.Series:
    """月末的判定 → 每个交易日（向后填；第一个月末之前 = before）。"""
    idx = pd.DatetimeIndex(idx)
    return flags.reindex(idx.union(flags.index)).ffill().reindex(idx).fillna(before).astype(bool)


def trend_off(close: pd.Series, last_complete: bool = False, months: int = TREND_MONTHS) -> pd.Series:
    """True = 不拿（现金）：月末收盘 ≤ 最近 months 个月末收盘的平均（含这个月末）；月末不到 months 个 → True。按 close 的日期返回。"""
    c = close.dropna()
    c = c[c > 0]
    me = month_ends(c.index, last_complete)
    m = c.reindex(me)
    sma = m.rolling(months, min_periods=months).mean()
    off = ~(m > sma)
    return _daily(off, close.index, True)


def rotation_pick(closes: dict[str, pd.Series], last_complete: bool = False, months: int = MOM_MONTHS) -> pd.Series:
    """每个月末：过去 months 个月（月末收盘对月末收盘）涨得最多的那只；最多的也 ≤ 0 或都算不了 → None。按月末日期返回。"""
    idx = pd.DatetimeIndex(sorted(set().union(*[s.dropna().index for s in closes.values()]))) if closes else pd.DatetimeIndex([])
    me = month_ends(idx, last_complete)
    ret = {}
    for t, s in closes.items():
        c = s.dropna()
        c = c[c > 0]
        v = c.reindex(idx.union(c.index)).ffill().reindex(me)
        first = c.index.min() if len(c) else None
        v = v.where(me >= first) if first is not None else v * np.nan
        ret[t] = v / v.shift(months) - 1
    R = pd.DataFrame(ret, index=me)
    pick = []
    for d in me:
        r = R.loc[d].dropna()
        pick.append(str(r.idxmax()) if len(r) and float(r.max()) > 0 else None)
    return pd.Series(pick, index=me, dtype=object)


def rotation_off(closes: dict[str, pd.Series], idx: pd.DatetimeIndex, last_complete: bool = False,
                 months: int = MOM_MONTHS) -> dict[str, pd.Series]:
    """{"RT:<票>": True = 这个月没被选中（引擎 follow 模式下被选中的那只拿全部闲置资金）}。"""
    pick = rotation_pick(closes, last_complete, months)
    return {f"RT:{t}": _daily(pd.Series([p != t for p in pick], index=pick.index, dtype=bool), idx, True) for t in closes}


def extra_bear(mode: str, closes: dict[str, pd.Series], us_bear: pd.Series | None, idx: pd.DatetimeIndex,
               last_complete: bool = False) -> dict[str, pd.Series]:
    """这个方式在引擎里要的额外「熊」键（True = 那只 ETF 目标 0）。closes：ETF 自己的日元收盘；us_bear：美股牛熊分界（True = 熊）。"""
    if mode in ("K2", "K3", "K4"):
        t = next(iter(MODES[mode]["core"]))
        return {f"TR:{t}": _daily(trend_off(closes[t], last_complete), idx, True)}
    if mode == "K5":
        ub = us_bear if us_bear is not None else pd.Series(dtype=bool)
        return {"XR": ~_daily(ub, idx, False)}
    if mode == "K6":
        return rotation_off({t: closes[t] for t in ROT}, idx, last_complete)
    return {}


def apply(ucfg, mode: str, held: dict | None = None):
    """UnifiedConfig → 这个方式的闲置资金设定；held = 状态里还拿着的核心 ETF（不在这个方式里的 → 权重 0，引擎下一次决策全部卖掉）。
    K0 = var/sim.json 自己的 unified.core（原规则；以后那里改了也跟着）。"""
    if mode not in MODES:
        raise KeyError(f"未知闲置资金方式 {mode}，可选 {sorted(MODES)}")
    m = MODES[mode]
    if mode == "K0":
        core, ci, cm = dict(ucfg.core), dict(ucfg.core_index), ucfg.core_mode
    else:
        core, ci, cm = dict(m["core"]), dict(m["core_index"]), m["core_mode"]
    for t, u in (held or {}).items():
        if int(u or 0) and t not in core:
            core[t], ci[t] = 0.0, "US"
    return replace(ucfg, core=core, core_index=ci, core_mode=cm)


def last_month_complete(bar_date) -> bool:
    """实时：最新 K 线那天是不是那个月最后一个东证交易日（是 → 这个月末的判定今天收盘就定）。"""
    from .calendar_jp import next_trading_day
    d = pd.Timestamp(bar_date).date()
    return next_trading_day(d).month != d.month


def detail(mode: str, closes: dict[str, pd.Series], asof, last_complete: bool = False) -> dict:
    """日报 / 页面的读数：K2〜K4 = 用的那个月末的收盘与 10 个月均线；K6 = 各只 12 个月涨跌。"""
    d = pd.Timestamp(asof)
    out: dict = {}
    if mode in ("K2", "K3", "K4"):
        t = next(iter(MODES[mode]["core"]))
        c = closes.get(t)
        if c is not None and len(c.dropna()):
            c = c.dropna()
            c = c[c.index <= d]
            me = month_ends(c.index, last_complete)
            if len(me) >= TREND_MONTHS:
                m = c.reindex(me)
                out = {"month_end": str(me[-1].date()), "close": round(float(m.iloc[-1]), 2),
                       "sma": round(float(m.iloc[-TREND_MONTHS:].mean()), 2), "months": TREND_MONTHS}
    elif mode == "K6":
        r = {}
        for t in ROT:
            c = closes.get(t)
            if c is None or not len(c.dropna()):
                continue
            c = c.dropna()
            c = c[c.index <= d]
            me = month_ends(c.index, last_complete)
            if len(me) > MOM_MONTHS:
                v = c.reindex(me)
                r[t] = round(float(v.iloc[-1] / v.iloc[-1 - MOM_MONTHS] - 1) * 100, 1)
        out = {"ret12": r}
    return out


def status(mode: str, bear: dict[str, pd.Series], asof) -> dict:
    """日报 / 页面：这个方式今天（asof 收盘时的判定）拿哪只。"""
    m = MODES.get(mode, MODES["K0"])
    d = pd.Timestamp(asof)

    def on(key: str) -> bool:
        s = bear.get(key)
        if s is None or not len(s):
            return False
        s = s[s.index <= d]
        return bool(len(s)) and not bool(s.iloc[-1])
    hold = [t for t, k in m["core_index"].items() if on(k)]
    return {"mode": mode, "label": LABELS.get(mode, mode), "hold": hold,
            "text": ("、".join(NAMES.get(t, t) for t in hold) if hold else "现金")}
