"""timeline.py — 买卖时间线（2026-09-29 用户要求：「按照算法挑出来的股票群 自动进行买卖时机规划 比如几号买什么 卖什么 预计未来
什么时候买/卖 等等 横展开一下 然后每天根据前一天的闭盘来随时更新买卖时间线」）。

只展示、不改交易：模拟盘与执行器照旧按规则决策；这里把同一套规则翻译成「哪天、什么价位、会发生什么」，每个交易日早上按前一天收盘重算。
  ① s1 开盘（已确定）：今天早上已经决定的单（s1 = 数据日之后的第一个交易日）。
  ② 持仓：s1 收盘到哪个价位会触发哪条卖出规则（→ s2 开盘卖）；最迟哪天满 60 个交易日；情景（持平 / 每天 ±1%）下最早哪天卖；
     历史上同一套规则的持有天数（var/timeline_stats.json）给「预计」的统计参考。
  ③ 候补：s1 收盘落在什么价格区间、成交量多少以上会出买点（→ s2 开盘买）；挡住的理由（横盘不成立 / MACD 已在信号线之上 /
     决算前 / 名额满 / 一手买不起 / 资格检查 …）。
  ④ 横展开（整个股票池）：情景推算股价持平 / 每天 +1% / 每天 −1% 时，接下来 10 个交易日里最早哪天会出买点
     （价格条件成立的那天把成交量设成刚好放量、那天完成一周时凑够 W2 的周线量比，再用完整的买入条件核对）。情景推算不是预测。
  ⑤ 闲置资金：牛熊分界的翻转价位与要连续几天。⑥ 日历：决算日、满 60 天、指数入替、周线完成。
价位的算法：在最后一根 K 线后面接假设的 K 线（开盘 = 前收，最高 / 最低 = 开盘与收盘之间，没有影线），用 qbreak/strategy 的
  compute_indicators 重算买点；卖出按引擎的离场判定（qbreak/unified.UnifiedEngine._check_exits，收盘判定 → 次日开盘卖）同样的顺序
  （tests/test_timeline.py 用真实引擎逐条核对）。
非投资建议。
"""
from __future__ import annotations

import datetime as dt
import math
from html import escape

import numpy as np
import pandas as pd

from .strategy import OHLCV, atr, compute_indicators, ema

TAIL = 500                                  # 用最近 500 根 K 线重算（EMA / ATR 的起点影响 < 1e-9）
SCEN = (("持平", 0.0), ("每天 +1%", 0.01), ("每天 −1%", -0.01))
SCEN_DAYS = 10
REASON = {"stop": "止损（买价 −7%）", "trail": "跟踪止损（峰值 −12%）", "take_profit": "止盈（+25%）", "climax": "放量阴线",
          "dead_cross": "MACD 死叉", "chandelier": "吊灯止损 X6", "sar_flip": "SAR 翻转", "max_hold": "满 60 个交易日",
          "time_stop": "时间止损"}


# ───────────────────────── 日历与假设 K 线 ─────────────────────────
def sessions_after(d: dt.date, n: int) -> list[dt.date]:
    """d 之后的 n 个东证交易日。"""
    from .calendar_jp import next_trading_day
    out, x = [], d
    for _ in range(n):
        x = next_trading_day(x)
        out.append(x)
    return out


def week_end(d: dt.date) -> dt.date:
    """d 所在那一周的最后一个东证交易日（那天收盘时这一周完成，W2 的周线量比从那天收盘的判定起换成这一周）。"""
    from .calendar_jp import is_trading_day, next_trading_day
    x = d if is_trading_day(d) else next_trading_day(d)
    while next_trading_day(x).isocalendar()[:2] == x.isocalendar()[:2]:
        x = next_trading_day(x)
    return x


def _tail(df: pd.DataFrame) -> pd.DataFrame:
    return df[OHLCV].astype(float).tail(TAIL)


def with_bars(df: pd.DataFrame, days, closes, volumes) -> pd.DataFrame:
    """接上假设的 K 线：开盘 = 前收，最高 / 最低 = 开盘与收盘之间（没有影线）。"""
    base = _tail(df)
    prev = float(base["Close"].iloc[-1])
    rows = []
    for c, v in zip(closes, volumes):
        rows.append({"Open": prev, "High": max(prev, float(c)), "Low": min(prev, float(c)), "Close": float(c), "Volume": float(v)})
        prev = float(c)
    add = pd.DataFrame(rows, index=pd.DatetimeIndex([pd.Timestamp(x) for x in days]), columns=OHLCV)
    return pd.concat([base, add])


def min_volume(df: pd.DataFrame, n: int, mult: float) -> int | None:
    """下一根 K 线的成交量至少多少，量比（÷ 含当天的 n 日平均）才 > mult：V > mult × S ÷ (n − mult)，S = 之前 n − 1 天的合计。"""
    v = df["Volume"].astype(float).tail(n - 1)
    if len(v) < n - 1 or mult >= n:
        return None
    return int(math.floor(mult * float(v.sum()) / (n - mult))) + 1


def cross_level(close: pd.Series, p) -> tuple[float, float, float]:
    """(MACD 线, 信号线, 下一根收盘的临界价)：下一根收盘 > 临界价 ⇔ 下一根 MACD 线 > 今天的信号线（金叉 / 死叉的分界）。
    EMA（span, adjust=False）：ema' = a·x + (1 − a)·ema；信号线' = a9·m' + (1 − a9)·s，所以 m' > s' ⇔ m' > s。"""
    c = close.astype(float).tail(TAIL)
    ef, es = float(ema(c, p.macd_fast).iloc[-1]), float(ema(c, p.macd_slow).iloc[-1])
    m = ef - es
    s = float(ema(ema(c, p.macd_fast) - ema(c, p.macd_slow), p.macd_signal).iloc[-1])
    af, as_ = 2 / (p.macd_fast + 1), 2 / (p.macd_slow + 1)
    x = (s - (1 - af) * ef + (1 - as_) * es) / (af - as_)
    return m, s, x


# ───────────────────────── 候补：下一交易日收盘的买点区间 ─────────────────────────
def _fails(r: pd.Series, p, close: float) -> list[str]:
    out = []
    if not bool(r.get("is_range")):
        out.append(f"横盘不成立（{p.range_n} 日振幅 ≥ {p.range_x_pct:g}%）")
    if not bool(r.get("golden_cross")):
        out.append("MACD 没有金叉")
    if not bool(r.get("near_zero")):
        out.append(f"MACD 离 0 轴太远（{abs(float(r['macd'])) / close * 100:.2f}% ≥ {p.macd_zero_band_pct:g}%）")
    if not bool(r.get("vol_surge")):
        out.append(f"没放量（量比 ≤ {p.vol_mult:g}）")
    if p.max_distribution_days and not (float(r.get("dist_days", 0)) < p.max_distribution_days):
        out.append(f"出货日 {int(r['dist_days'])} ≥ {p.max_distribution_days}")
    if p.max_upper_shadow_ratio and float(r.get("upper_shadow_ratio") or 0) > p.max_upper_shadow_ratio:
        out.append("长上影")
    w = r.get("w5v")
    if p.min_weekly_vol_ratio and w is not None and np.isfinite(float(w)) and float(w) < p.min_weekly_vol_ratio:
        out.append(f"周线量比 {float(w):.2f} < {p.min_weekly_vol_ratio:g}（W2）")
    return out


def w2_min_volume(df: pd.DataFrame, p, s1: dt.date) -> int | None:
    """s1 收盘时这一周刚好完成（周五 / 连休前）→ W2 的周线量比含 s1 的成交量：(本周其余几天 + V) ÷ 前 10 周平均，对 V 是线性的
    → 量比 ≥ 门槛所需的 V（≤ 0 → 0）。s1 不完成一周（量比与 s1 的成交量无关）/ 没开 W2 / 历史不够 → None。"""
    if not p.min_weekly_vol_ratio:
        return None
    from .mtf import live_calendar, weekly_volume_ratio
    base = _tail(df)
    c = float(base["Close"].iloc[-1])

    def w(v: float) -> float:
        fr = with_bars(base, [s1], [c], [v])
        return float(weekly_volume_ratio(fr, live_calendar(fr.index)).iloc[-1])
    v0, v1 = 0.0, max(float(base["Volume"].tail(60).mean()), 1.0) * 10
    w0, w1 = w(v0), w(v1)
    if not (np.isfinite(w0) and np.isfinite(w1)) or abs(w1 - w0) < 1e-12:
        return None
    a = (v1 - v0) / (w1 - w0)                                    # 前 10 周平均（股 / 周）
    need = p.min_weekly_vol_ratio * a - w0 * a                   # 门槛 × 平均 − 本周其余几天的合计
    return max(0, int(math.floor(need)) + 1)


_PRICE_FAILS = ("MACD 离 0 轴", "MACD 没有金叉")


def buy_trigger(df: pd.DataFrame, p, s1: dt.date) -> dict:
    """s1 收盘落在 [lo, hi]（且成交量 ≥ v_need）→ 当天出买点。区间外 / 条件不全 → why 列出理由。
    v_need = 放量的门槛（v_min）；s1 完成一周时还要凑够 W2 的周线量比（v_w2），取两者较大的。"""
    base = _tail(df)
    close = float(base["Close"].iloc[-1])
    x0 = compute_indicators(base, p)
    r = x0.iloc[-1]
    vmin = min_volume(base, int(p.vol_ma_n), float(p.vol_mult))
    out = {"close": round(close, 2), "range_pct": round(float(r["range_pct"]), 1) if np.isfinite(r["range_pct"]) else None,
           "vol_ma": round(float(r["vol_ma"])) if np.isfinite(r["vol_ma"]) else None, "v_min": vmin, "v_w2": None, "v_need": vmin,
           "w5v": round(float(r["w5v"]), 2) if "w5v" in x0.columns and np.isfinite(r["w5v"]) else None,
           "lo": None, "hi": None, "why": []}
    if not (np.isfinite(r["range_pct"]) and r["range_pct"] < p.range_x_pct):
        out["why"].append(f"横盘不成立：{p.range_n} 日振幅 {out['range_pct']}% ≥ {p.range_x_pct:g}%")
        return out
    m, s, xgc = cross_level(base["Close"], p)
    out["x_gc"] = round(xgc, 2)
    if m > s:
        out["why"].append("MACD 已在信号线之上（金叉已经过去）：要先回落到信号线下方再金叉")
        return out
    if vmin is None:
        out["why"].append("成交量历史不够")
        return out
    vol = vmin

    def ok(x: float) -> tuple[bool, pd.Series]:
        row = compute_indicators(with_bars(base, [s1], [x], [vol]), p).iloc[-1]
        return bool(row["entry"]), row

    top, step = close * 1.30, 1.005

    def scan() -> tuple[float | None, float | None, list[str] | None]:
        x, lo, hi, first = max(xgc, 0.01) * (1 + 1e-7), None, None, None
        while x <= top:
            good, row = ok(x)
            if good:
                lo = x if lo is None else lo
                hi = x
            elif lo is not None:
                break
            elif first is None:
                first = _fails(row, p, x)
                down = x < close * 0.998                               # 收跌 + 放量 = 出货日：收高一点就不算了 → 继续往上找
                if any(not f.startswith(_PRICE_FAILS) and not (down and f.startswith("出货日")) for f in first):
                    break                                               # 跟价格无关的条件不成立（W2 / 横盘 …）→ 涨多少都不会出
                first = None if down and any(f.startswith("出货日") for f in first) else first
            x *= step
        return lo, hi, first

    lo, hi, first = scan()
    if lo is None and first and any(f.startswith("周线量比") for f in first):
        v2 = w2_min_volume(base, p, s1)                                 # s1 完成一周：成交量够大 W2 也能过
        if v2 is not None and v2 > vol:
            out["v_w2"] = v2
            vol = v2
            lo, hi, first = scan()
    out["v_need"] = vol
    if lo is None:
        why = "收在临界价以上也不会出买点：" + "；".join(first or ["条件不全"])
        if first and any(f.startswith("周线量比") for f in first) and out["v_w2"] is None:
            why += f"（这一周 {week_end(s1).isoformat()[5:]} 收盘完成后才换成新的一周）"
        out["why"].append(why)
        return out
    if lo > xgc * (1 + 1e-6):                                   # 下沿在临界价之上 → 二分细化
        a, b = lo / step, lo
        for _ in range(12):
            mid = (a + b) / 2
            a, b = (a, mid) if ok(mid)[0] else (mid, b)
        lo = b
    a, b = hi, hi * step                                        # 上沿二分细化
    if b <= top:
        for _ in range(12):
            mid = (a + b) / 2
            a, b = (mid, b) if ok(mid)[0] else (a, mid)
        hi = a
        out["hi_open"] = False
    else:
        out["hi_open"] = True                                   # 到 +30% 还成立（涨停也在区间里）
    out["lo"], out["hi"] = round(lo, 2), round(hi, 2)
    return out


def scenario_entry(df: pd.DataFrame, p, days: list[dt.date], rate: float) -> dict | None:
    """情景：之后每天收盘按 rate 变动、成交量 = 20 日平均；最早哪天会出买点 ——
    先找「价格条件」（横盘 + 0 轴附近金叉 + 出货日 < 6）成立的日子，再把那一天的成交量设成刚好放量（> 20 日均量 × 1.5；
    那天完成一周时还要凑够 W2 的周线量比），用完整的买入条件（compute_indicators 的 entry）核对；不成立就看下一个。
    返回 signal_day（那天收盘出信号）/ buy_day（下一交易日开盘买）/ close / vol（那天至少要的成交量）；10 天内都不成立 → None。"""
    base = _tail(df)
    c0 = float(base["Close"].iloc[-1])
    n = len(days) - 1
    vol = float(base["Volume"].tail(int(p.vol_ma_n)).mean())
    closes = [c0 * (1 + rate) ** (k + 1) for k in range(n)]
    x = compute_indicators(with_bars(base, days[:n], closes, [vol] * n), p).iloc[-n:]
    okm = x["is_range"].to_numpy(bool) & x["golden_cross"].to_numpy(bool) & x["near_zero"].to_numpy(bool)
    if p.max_distribution_days:
        okm &= (x["dist_days"].to_numpy(float) < p.max_distribution_days)
    for k in np.flatnonzero(okm):
        k = int(k)
        prev = with_bars(base, days[:k], closes[:k], [vol] * k) if k else base
        need = min_volume(prev, int(p.vol_ma_n), float(p.vol_mult))
        if need is None:
            continue

        def entry_at(v: float) -> tuple[bool, pd.Series]:
            row = compute_indicators(with_bars(base, days[:k + 1], closes[:k + 1], [vol] * k + [v]), p).iloc[-1]
            return bool(row["entry"]), row
        good, row = entry_at(need)
        if not good and p.min_weekly_vol_ratio and "w5v" in row and np.isfinite(row["w5v"]) and row["w5v"] < p.min_weekly_vol_ratio:
            v2 = w2_min_volume(prev, p, days[k])                        # 那天完成一周：成交量够大 W2 也能过
            if v2 is not None and v2 > need:
                need = v2
                good, row = entry_at(need)
        if good:
            return {"signal_day": days[k].isoformat(), "buy_day": days[k + 1].isoformat(), "close": round(closes[k], 2),
                    "vol": int(need), "k": k + 1}
    return None


# ───────────────────────── 持仓：卖出线 ─────────────────────────
def sell_levels(df: pd.DataFrame, p, pos: dict, days: list[dt.date]) -> dict:
    """s1 收盘触发各条卖出规则的价位（收盘判定 → s2 开盘卖；与引擎 _check_exits 相同的规则）。"""
    base = _tail(df)
    close = float(base["Close"].iloc[-1])
    entry, peak, stop_px = float(pos["entry_px"]), float(pos["peak"]), float(pos["stop_px"])
    hold, armed = int(pos.get("hold") or 0), bool(pos.get("armed"))
    trail_on = p.trailing_stop_pct > 0 and (armed or not p.trailing_arm_pct)
    lv = []
    trail = peak * (1 - p.trailing_stop_pct / 100) if trail_on else -np.inf
    hard = max(stop_px, trail)
    lv.append({"rule": REASON["trail" if trail > stop_px else "stop"], "side": "down", "op": "≤", "px": round(hard, 2)})
    if p.take_profit_pct:
        lv.append({"rule": REASON["take_profit"], "side": "up", "op": "≥", "px": round(entry * (1 + p.take_profit_pct / 100), 2)})
    if p.exit_chandelier_k > 0:
        def f(x: float) -> float:                               # < 0 ⇔ 收在 x 会触发吊灯
            fr = with_bars(base, [days[0]], [x], [float(base["Volume"].iloc[-1])])
            a = float(atr(fr, p.atr_n).iloc[-1])
            pk = max(peak, float(fr["High"].iloc[-1]))
            return x - (pk - p.exit_chandelier_k * a)
        a, b = close * 0.3, close * 1.3
        if f(a) < 0 <= f(b):
            for _ in range(40):
                mid = (a + b) / 2
                a, b = (mid, b) if f(mid) < 0 else (a, mid)
            lv.append({"rule": REASON["chandelier"] + "（持有以来最高价 − 3 × ATR14）", "side": "down", "op": "<", "px": round(a, 2)})
    if p.exit_on_macd_dead_cross:
        m, s, x = cross_level(base["Close"], p)
        if m >= s:
            lv.append({"rule": REASON["dead_cross"], "side": "down", "op": "<", "px": round(x, 2)})
    extra = []
    if p.exit_on_climax:
        vc = min_volume(base, int(p.vol_ma_n), float(p.climax_vol_mult))
        extra.append({"rule": REASON["climax"], "text": f"放量（> {vc:,} 股）收阴、且收盘 ≥ ¥{entry * (1 + p.climax_min_gain_pct / 100):,.1f}"
                      f"（浮盈 ≥ {p.climax_min_gain_pct:g}%）" if vc else "放量收阴且浮盈 ≥ 5%"})
    mh = None
    if p.max_hold_days:
        k = int(p.max_hold_days) - hold
        if k >= 1 and k < len(days):
            mh = {"close_day": days[k - 1].isoformat(), "sell_day": days[k].isoformat(), "k": k}
        elif k < 1:
            mh = {"close_day": None, "sell_day": days[0].isoformat(), "k": 0}
    downs = [x for x in lv if x["side"] == "down"]
    first = max(downs, key=lambda x: x["px"]) if downs else None
    return {"close": round(close, 2), "entry_px": round(entry, 2), "ret_pct": round((close / entry - 1) * 100, 2), "peak": round(peak, 2),
            "hold": hold, "levels": lv, "extra": extra, "max_hold": mh,
            "first_down": first, "first_down_pct": round((first["px"] / close - 1) * 100, 2) if first else None}


def scenario_exit(df: pd.DataFrame, p, pos: dict, days: list[dt.date], rate: float) -> dict | None:
    """情景：之后每天收盘按 rate 变动、成交量 = 20 日平均；按引擎 _check_exits（收盘判定）的顺序，最早哪天触发卖出。"""
    base = _tail(df)
    c0 = float(base["Close"].iloc[-1])
    n = len(days) - 1
    vol = float(base["Volume"].tail(int(p.vol_ma_n)).mean())
    closes = [c0 * (1 + rate) ** (k + 1) for k in range(n)]
    x = compute_indicators(with_bars(base, days[:n], closes, [vol] * n), p).iloc[-n:]
    entry, peak, stop_px = float(pos["entry_px"]), float(pos["peak"]), float(pos["stop_px"])
    hold, armed = int(pos.get("hold") or 0), bool(pos.get("armed"))
    tp = entry * (1 + p.take_profit_pct / 100) if p.take_profit_pct else np.inf
    for k in range(n):
        r = x.iloc[k]
        hold += 1
        h, c = float(r["High"]), float(r["Close"])
        if p.trailing_arm_pct and not armed and h >= entry * (1 + p.trailing_arm_pct / 100):
            armed = True
        trail_on = p.trailing_stop_pct > 0 and (armed or not p.trailing_arm_pct)
        peak = max(peak, h)
        trail = peak * (1 - p.trailing_stop_pct / 100) if trail_on else -np.inf
        hard = max(stop_px, trail)
        q = None
        if c <= hard:
            q = "trail" if trail > stop_px else "stop"
        elif c >= tp:
            q = "take_profit"
        if q is None:
            a = float(r["atr"])
            if p.exit_on_climax and bool(r["climax"]) and (c / entry - 1) * 100 >= p.climax_min_gain_pct:
                q = "climax"
            elif p.exit_on_macd_dead_cross and bool(r["dead_cross"]):
                q = "dead_cross"
            elif p.exit_chandelier_k > 0 and np.isfinite(a) and c < peak - p.exit_chandelier_k * a:
                q = "chandelier"
            elif p.exit_sar_flip and bool(r.get("sar_flip", False)):
                q = "sar_flip"
            elif p.max_hold_days and hold >= p.max_hold_days:
                q = "max_hold"
            elif p.time_stop_days and hold >= p.time_stop_days and (c / entry - 1) * 100 < p.time_stop_min_ret_pct:
                q = "time_stop"
        if q:
            return {"close_day": days[k].isoformat(), "sell_day": days[k + 1].isoformat(), "reason": REASON[q], "close": round(c, 2)}
    return None


def hold_estimate(stats: dict | None, hold: int, days: list[dt.date]) -> dict | None:
    """历史上同一套规则、已经持有 hold 天的交易，剩下的持有天数（中位 / 25〜75%）→ 预计卖出日（统计参考）。"""
    rem = ((stats or {}).get("remaining") or {}).get(str(min(int(hold), 59)))
    if not rem or not rem.get("n"):
        return None
    med = int(round(rem["p50"]))
    d = days[min(max(med, 1), len(days) - 1)] if len(days) > 1 else None
    return {"n": rem["n"], "p25": rem["p25"], "p50": rem["p50"], "p75": rem["p75"], "date": d.isoformat() if d else None}


# ───────────────────────── 组装 ─────────────────────────
def build(frames: dict, p_entry, p_exit, *, bar_date: dt.date, positions: dict, pending: dict, plan: dict, todo: dict,
          watch: list[dict], pool: list[str], equity: float, position_pct: float, max_positions: int,
          em: dict | None = None, earn: dict | None = None, blocked: dict | None = None, index_pend: dict | None = None,
          bullbear_us: dict | None = None, idle: dict | None = None, stats: dict | None = None, estate: dict | None = None,
          core: set | None = None, top_n: int = 15, horizon: int = 25) -> dict:
    """frames：{ticker: OHLCV（到 bar_date 为止的完整 K 线）}；positions：{ticker: {entry_px, entry_date, stop_px, peak, hold, armed, shares}}。
    em：{ticker: 明天的新仓倍数}；earn：{ticker: 下次决算日}；blocked：{ticker: 资格检查挡住的理由}。"""
    em, earn, blocked, index_pend, estate, core = em or {}, earn or {}, blocked or {}, index_pend or {}, estate or {}, set(core or ())
    days = sessions_after(bar_date, max(horizon, int(p_exit.max_hold_days or 0) + 6))
    s1, s2 = days[0], days[1]
    cal_end = days[horizon - 1]
    from .events import trading_days_until
    out: dict = {"bar_date": bar_date.isoformat(), "s1": s1.isoformat(), "s2": s2.isoformat(), "orders": [], "holdings": [],
                 "candidates": [], "sweep": [], "calendar": [], "notes": []}
    # ① s1 开盘（已确定）
    for m in ("JP", "US", "FX"):
        for o in (todo or {}).get(m) or []:
            out["orders"].append({**{k: o.get(k) for k in ("side", "ticker", "qty", "type", "limit", "reason") if o.get(k) is not None},
                                  "unit": "口" if o.get("ticker") in core else "股"})
    # ② 持仓
    n_stock = 0
    for t, ps in sorted(positions.items()):
        if t not in frames:
            continue
        n_stock += 1
        row = {"ticker": t, "shares": ps.get("shares"), "entry_date": ps.get("entry_date"), "state": estate.get(t)}
        if t in pending:
            row["queued"] = {"sell_day": s1.isoformat(), "reason": REASON.get(pending[t], str(pending[t]))}
        row.update(sell_levels(frames[t], p_exit, ps, days))
        row["scen"] = {nm: scenario_exit(frames[t], p_exit, ps, days[:SCEN_DAYS + 1], r) for nm, r in SCEN}
        row["est"] = hold_estimate(stats, row["hold"], days)
        if earn.get(t):
            row["earnings"] = earn[t]
        out["holdings"].append(row)
    out["holdings"].sort(key=lambda r: -(r.get("first_down_pct") if r.get("first_down_pct") is not None else -1e9))
    out["buying"] = []
    for t, pl in sorted((plan or {}).items()):
        c0 = float(pl[0]) if pl else None
        mh = int(p_exit.max_hold_days or 0)
        out["buying"].append({"ticker": t, "shares": int(pl[1]) if len(pl) > 1 else None, "signal_close": c0, "state": estate.get(t),
                              "stop_est": round(c0 * (1 - p_exit.stop_loss_pct / 100), 2) if c0 else None,
                              "tp_est": round(c0 * (1 + p_exit.take_profit_pct / 100), 2) if c0 and p_exit.take_profit_pct else None,
                              "max_hold_close": days[mh - 1].isoformat() if mh and mh - 1 < len(days) else None,
                              "max_hold_sell": days[mh].isoformat() if mh and mh < len(days) else None})
    # ③ 候补（队列前 top_n 只，不含持仓 / 今天已计划买的）
    free = max(0, int(max_positions) - len(positions) + len(pending) - len(plan))
    out["slots"] = {"max": int(max_positions), "held": len(positions), "selling": len(pending), "buying": len(plan), "free": free}
    budget_full = float(equity) * float(position_pct)
    cands = [w for w in watch if w.get("ticker") in frames and w.get("ticker") not in positions and w.get("ticker") not in plan][:top_n]
    for w in cands:
        t = w["ticker"]
        bt = buy_trigger(frames[t], p_entry, s1)
        mult = float(em.get(t, 1.0))
        budget = budget_full * min(1.0, mult)
        lot_px = bt["lo"] if bt.get("lo") else bt["close"]
        blocks = []
        if blocked.get(t):
            blocks.append(f"资格检查：{blocked[t]}")
        pend = index_pend.get(t.split(".")[0]) or {}
        if pend.get("action") == "delete":
            blocks.append(f"指数剔除（{pend.get('effective')} 生效），不开新仓")
        if mult <= 0:
            blocks.append("新仓倍数 0（宏观 / 板块 / 判断层）")
        elif lot_px * 100 > budget:
            blocks.append(f"一手 ¥{lot_px * 100:,.0f} > 每个名额 ¥{budget:,.0f}（权益 × {position_pct:g} × 新仓倍数 {mult:g}）→ 买不起就跳过")
        ed = earn.get(t)
        if ed:
            e_days = trading_days_until(dt.date.fromisoformat(ed), s2)
            if e_days <= int(p_entry.earnings_blackout_days or 0):
                blocks.append(f"{ed} 决算：{s2} 在决算前 {e_days} 个交易日内，不进场")
        if free <= 0:
            blocks.append("名额已满（要有持仓先卖出）")
        out["candidates"].append({"ticker": t, "status": w.get("status"), "score": w.get("score"), "sector": w.get("sector"),
                                  **bt, "mult": mult, "budget": round(budget), "blocks": blocks, "earnings": ed, "state": estate.get(t),
                                  "scen": {nm: scenario_entry(frames[t], p_entry, days[:SCEN_DAYS + 1], r) for nm, r in SCEN}})
    # ④ 横展开：整个股票池的情景推算
    for t in pool:
        if t not in frames or t in positions:
            continue
        sc = {nm: scenario_entry(frames[t], p_entry, days[:SCEN_DAYS + 1], r) for nm, r in SCEN}
        if any(sc.values()):
            first = min((v["signal_day"] for v in sc.values() if v), default=None)
            out["sweep"].append({"ticker": t, "first": first, "scen": sc, "state": estate.get(t)})
    out["sweep"].sort(key=lambda r: (r["first"] or "9999", r["ticker"]))
    out["sweep_n"] = len([t for t in pool if t in frames and t not in positions])
    # ⑤ 闲置资金
    if bullbear_us:
        bb = bullbear_us
        out["idle"] = {"mode": (idle or {}).get("mode"), "label": (idle or {}).get("label"), "state": bb.get("state"),
                       "flip_to": bb.get("flip_to"), "level": bb.get("level"), "close": bb.get("close"),
                       "distance_pct": bb.get("distance_pct"), "need_days": bb.get("need_days") or bb.get("confirm_need"),
                       "confirm_days": bb.get("confirm_days"), "asof": bb.get("asof")}
    # ⑥ 日历（接下来 horizon 个交易日）
    cal: dict[str, list[str]] = {}

    def add(d, text):
        if d and s1.isoformat() <= str(d) <= cal_end.isoformat():
            cal.setdefault(str(d), []).append(text)
    for h in out["holdings"]:
        mh = h.get("max_hold") or {}
        if mh.get("close_day"):
            add(mh["close_day"], f"{h['ticker']} 收盘满 {p_exit.max_hold_days} 个交易日 → {mh['sell_day']} 开盘卖")
        if h.get("earnings"):
            add(h["earnings"], f"{h['ticker']} 决算（持仓；规则不因决算卖出）")
    for c in out["candidates"]:
        if c.get("earnings"):
            add(c["earnings"], f"{c['ticker']} 决算（前 {p_entry.earnings_blackout_days} 个交易日不进场）")
    for code, pdn in index_pend.items():
        add(pdn.get("effective"), f"{code} 日経225 {'剔除' if pdn.get('action') == 'delete' else '纳入'}生效")
    wk = next((d for i, d in enumerate(days[:horizon]) if days[i + 1].isocalendar()[:2] != d.isocalendar()[:2]), None)
    if wk:                                                      # 只列最近一次（以后每周最后一个交易日同样）
        add(wk.isoformat(), "周线完成：这天收盘的判定起 W2 用这一周的成交量（→ 下一交易日开盘买；以后每周最后一个交易日同样）")
    out["calendar"] = [{"date": d, "items": v} for d, v in sorted(cal.items())]
    return out


def attach_states(tl: dict, states: dict) -> dict:
    """决算形态（qbreak/earn_state.panel 的 states）放进持仓 / 明天买 / 候补 / 横展开的每一行。就地修改并返回。"""
    for key in ("holdings", "buying", "candidates", "sweep"):
        for r in tl.get(key) or []:
            if r.get("ticker") in states:
                r["state"] = states[r["ticker"]]
    return tl


# ───────────────────────── 展示（日报与 Mac 账本页面共用）─────────────────────────
def _px(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    return f"¥{v:,.1f}" if v < 1000 else f"¥{v:,.0f}"


def _md(d) -> str:
    return str(d or "—")[5:] if d else "—"


def _scen_txt(sc: dict | None, sell: bool = False) -> str:
    if not sc:
        return "—"
    if not any(sc.get(nm) for nm, _ in SCEN):
        return f"<span class='muted'>三种情景 {SCEN_DAYS} 个交易日内都不会</span>"
    parts, miss = [], []
    for nm, _ in SCEN:
        v = sc.get(nm)
        if v:
            parts.append(f"{nm}：{_md(v['close_day'] if sell else v['signal_day'])} 收盘"
                         + (f"（{escape(v['reason'])}）" if sell else "") + f" → {_md(v['sell_day'] if sell else v['buy_day'])}")
        else:
            miss.append(nm)
    if miss:
        parts.append(f"<span class='muted'>{'、'.join(miss)}：{SCEN_DAYS} 天内不会</span>")
    return "<br>".join(parts)


def html(tl: dict, state_tag=None) -> str:
    """一个 section 的内容（h2 + 表），两边页面都用 card / scroll / muted / n / pos / neg 这些 class。"""
    if not tl:
        return ""
    if tl.get("error"):
        return f"<h2>买卖时间线</h2><div class='muted'>这次没算出来：{escape(str(tl['error']))}</div>"
    st = state_tag or (lambda s: escape(str((s or {}).get("label") or "—")))
    s1, s2 = tl.get("s1"), tl.get("s2")
    H = [f"<h2>买卖时间线（按 {escape(str(tl.get('bar_date')))} 收盘；每个交易日早上重算）</h2>",
         f"<div class='muted'>把现行规则翻译成日期与价位：{escape(str(s1))} 收盘落在哪里 → {escape(str(s2))} 开盘做什么。只展示，不改交易；"
         "价位按「开盘 = 前收、没有影线」的假设 K 线算，情景推算不是预测。</div>"]
    od = tl.get("orders") or []
    H.append(f"<h3>① {escape(str(s1))} 开盘（今天早上已经决定）</h3>")
    H.append("<ul>" + "".join(f"<li>{'卖' if o.get('side') == 'SELL' else '买'} {escape(str(o.get('ticker')))} "
                               f"{int(o.get('qty') or 0):,} {escape(str(o.get('unit') or '股'))}"
                               f"（{escape(str(o.get('type') or ''))}{('，' + escape(str(o.get('reason')))) if o.get('reason') else ''}）</li>"
                               for o in od) + "</ul>" if od else "<div class='muted'>没有单</div>")
    hs = tl.get("holdings") or []
    H.append(f"<h3>② 持仓：{escape(str(s1))} 收盘到哪里就卖（→ {escape(str(s2))} 开盘卖）</h3>")
    if hs:
        rows = []
        for h in hs:
            lv = "<br>".join(f"{escape(x['rule'])}：收盘 {x['op']} {_px(x['px'])}（{(x['px'] / h['close'] - 1) * 100:+.1f}%）" for x in h["levels"])
            lv += "".join(f"<br>{escape(x['rule'])}：{escape(x['text'])}" for x in h.get("extra") or [])
            mh = h.get("max_hold") or {}
            est = h.get("est")
            est_t = (f"历史 {est['n']:,} 笔：再持有中位 {est['p50']:g} 天（25〜75%：{est['p25']:g}〜{est['p75']:g} 天）→ {_md(est['date'])} 前后"
                     if est else "—")
            q = h.get("queued")
            rows.append(f"<tr><td>{escape(h['ticker'])}<br><span class='muted'>{st(h.get('state'))}</span></td>"
                        f"<td class='n'>{_px(h['close'])}<br><span class='{'pos' if h['ret_pct'] >= 0 else 'neg'}'>{h['ret_pct']:+.1f}%</span>"
                        f"<br><span class='muted'>第 {h['hold']} 天</span></td>"
                        f"<td>{('<b>已排定 ' + escape(q['sell_day']) + ' 开盘卖（' + escape(q['reason']) + '）</b><br>') if q else ''}{lv}</td>"
                        f"<td>{_md(mh.get('close_day'))} 收盘满 → {_md(mh.get('sell_day'))} 开盘</td>"
                        f"<td>{_scen_txt(h.get('scen'), sell=True)}<br><span class='muted'>{est_t}</span></td>"
                        f"<td class='muted'>{escape(str(h.get('earnings') or '—'))}</td></tr>")
        H.append("<div class='scroll'><table style='min-width:680px'><tr><th>代码 / 决算形态</th><th class='n'>现价 / 浮盈</th><th>卖出线（收盘价）</th>"
                 "<th>最迟（满 60 天）</th><th>情景：最早哪天卖 / 统计参考</th><th>决算日</th></tr>" + "".join(rows) + "</table></div>")
    else:
        H.append("<div class='muted'>没有个股持仓</div>")
    for b in tl.get("buying") or []:
        H.append(f"<div class='muted'>{escape(b['ticker'])}（{escape(str(s1))} 开盘买，{st(b.get('state'))}）：买入之后 —— 止损约 {_px(b.get('stop_est'))}"
                 f"（成交价 × 0.93）、止盈约 {_px(b.get('tp_est'))}（× 1.25）、吊灯 = 持有以来最高价 − 3 × ATR14、跟踪 = 峰值 × 0.88；"
                 f"最迟 {_md(b.get('max_hold_close'))} 收盘满 60 天 → {_md(b.get('max_hold_sell'))} 开盘卖</div>")
    sl = tl.get("slots") or {}
    cs = tl.get("candidates") or []
    H.append(f"<h3>③ 候补：{escape(str(s1))} 收盘在区间里 + 放量 → {escape(str(s2))} 开盘买</h3>"
             f"<div class='muted'>名额 {sl.get('max', '—')} 个：持有 {sl.get('held', 0)}、明天卖 {sl.get('selling', 0)}、明天买 {sl.get('buying', 0)} → "
             f"空 {sl.get('free', 0)} 个；那天 K 线上影不能超过实体 × 3；买单 = 寄付指値（信号日收盘 × 1.03），开盘跳空 > 3% 不买；"
             "同一天几只都成立按队列顺序</div>")
    if cs:
        rows = []
        for c in cs:
            band = (f"{_px(c['lo'])}〜{'涨停' if c.get('hi_open') else _px(c['hi'])}" if c.get("lo") else "—")
            why = "；".join(c.get("why") or [])
            blk = "；".join(c.get("blocks") or [])
            vn = c.get("v_need") or c.get("v_min")
            vol = (f"≥ {int(vn):,} 股" + ("<br><span class='muted'>（那天收盘这一周完成：含凑够周线量比所需）</span>" if c.get("v_w2") else "")
                   if vn and c.get("lo") else "—")
            rows.append(f"<tr><td>{escape(c['ticker'])}<br><span class='muted'>{escape(str(c.get('sector') or ''))}</span>"
                        f"<br><span class='muted'>{st(c.get('state'))}</span></td>"
                        f"<td class='n'>{_px(c['close'])}</td><td>{band}{('<br><span class=muted>' + escape(why) + '</span>') if why else ''}</td>"
                        f"<td class='n'>{vol}</td><td class='{'neg' if blk else 'muted'}'>{escape(blk) or '—'}</td>"
                        f"<td>{_scen_txt(c.get('scen'))}</td></tr>")
        H.append("<div class='scroll'><table style='min-width:680px'><tr><th>代码 / 决算形态</th><th class='n'>现价</th><th>买点区间（收盘价）</th>"
                 "<th class='n'>那天成交量</th><th>挡住的理由</th><th>情景：最早哪天出买点 → 买</th></tr>" + "".join(rows) + "</table></div>")
    else:
        H.append("<div class='muted'>候补队列是空的</div>")
    sw = tl.get("sweep") or []
    H.append(f"<h3>④ 横展开：股票池 {tl.get('sweep_n', '—')} 只里，未来 10 个交易日在情景下会出买点的票</h3>")
    if sw:
        rows = "".join(f"<tr><td>{escape(r['ticker'])}<br><span class='muted'>{st(r.get('state'))}</span></td>"
                       f"<td>{_scen_txt(r.get('scen'))}</td></tr>" for r in sw[:40])
        H.append("<div class='scroll'><table><tr><th>代码 / 决算形态</th><th>最早出买点（那天收盘）→ 买入日（开盘）</th></tr>" + rows + "</table></div>"
                 + (f"<div class='muted'>只列前 40 只（共 {len(sw)} 只）</div>" if len(sw) > 40 else ""))
    else:
        H.append("<div class='muted'>三种情景下 10 个交易日内都不会出买点</div>")
    H.append("<div class='muted'>情景：之后每天收盘持平 / +1% / −1%、成交量 = 20 日平均；出买点那一天的成交量设成刚好放量"
             "（&gt; 20 日均量 × 1.5；那天完成一周时还要凑够周线量比 ≥ 1），用完整的买入条件（横盘 + MACD 在 0 轴附近金叉 + 放量 + 出货日 &lt; 6 + W2）核对；"
             "再下一个交易日开盘买（名额 / 资金 / 资格检查 / 决算前照旧）。情景是机械推算，不是预测。</div>")
    idl = tl.get("idle") or {}
    if idl:
        to_bear = idl.get("flip_to") == "bear"
        H.append(f"<h3>⑤ 闲置资金（{escape(str(idl.get('label') or idl.get('mode') or '—'))}）</h3><div>S&amp;P 500 "
                 f"{'牛市' if idl.get('state') == 'bull' else '熊市'}；{'转熊' if to_bear else '转牛'}线 {float(idl.get('level') or 0):,.2f} pt"
                 f"（现价 {float(idl.get('close') or 0):,.2f}，距离 {float(idl.get('distance_pct') or 0):+.2f}%，数据日 {escape(str(idl.get('asof')))}）："
                 f"连续 {idl.get('need_days') or 5} 天收在线{'下' if to_bear else '上'} → 下一个日本交易日开盘"
                 f"{'卖出闲置资金 ETF、那份留现金' if to_bear else '买回闲置资金 ETF'}</div>")
    cal = tl.get("calendar") or []
    H.append("<h3>⑥ 日历（接下来的交易日）</h3>")
    H.append("<ul>" + "".join(f"<li><b>{escape(c['date'])}</b>：{escape('；'.join(c['items']))}</li>" for c in cal) + "</ul>"
             if cal else "<div class='muted'>没有</div>")
    H.append("<div class='muted'>非投资建议。</div>")
    return "".join(H)
