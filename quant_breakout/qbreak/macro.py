"""macro.py — 宏观因子层 + 板块倾斜 + 宏观事件窗口。

三部分，都只影响**新仓**（不碰已有持仓的离场规则）：
  ① 量化因子（可回测）：Brent(BZ=F)、美 10Y(^TNX)、VIX(^VIX)、USD/JPY(JPY=X) 的日线 → 阈值规则 → 市场倍数
  ② 判断层（不可回测，worker 每早从「市场风险报告」写 var/macro.json）：加息隐含、HY 利差、广度、JGB、BOJ 隐含
  ③ 板块倾斜：油价高位/冲击时 能源·商社·海运 ×1、航空 ×0、陆运/化学/纸浆/电力 ×0.5、内需 ×0.75；
     10Y ≥ 5% 时 半导体/软件互联网 ×0.5
  ④ 事件窗口：FOMC / BOJ / CPI / NFP 的反应交易日及其前一交易日不开新仓（var/macro_events.json，官方日程）

所有倍数取 min（更保守的一层生效），最终与 regime / 汇率层再取 min。
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from . import paths
from .calendar_jp import is_trading_day as jp_trading_day
from .calendar_jp import next_trading_day as jp_next
from .calendar_jp import prev_trading_day as jp_prev
from .calendar_us import is_trading_day as us_trading_day
from .calendar_us import next_trading_day as us_next
from .calendar_us import prev_trading_day as us_prev
from .sectors import HIGH_GROWTH, OIL_LOSERS, OIL_WINNERS, sector_of
from .utils import read_json, setup_logging

log = setup_logging("macro")

MACRO_SYMBOLS = {"brent": "BZ=F", "us10y": "^TNX", "vix": "^VIX", "usdjpy": "JPY=X"}
MACRO_FILE = "macro.json"
EVENTS_FILE = "macro_events.json"

# 阈值一览（README 同步）
TH = dict(oil_high=100.0, oil_extreme=115.0, oil_shock20_pct=15.0,
          us10y_high=5.0, us10y_stress=5.2,
          vix_high=22.0, vix_panic=30.0, usdjpy_watch=158.0,
          hy_oas_wide=330.0, hy_oas_stress=400.0, breadth_weak=25.0,
          fed_prob_window=60.0, jgb10y_high=3.05, jgb10y_stress=3.2, boj_prob_window=60.0)


# ────────────────────────── ① 量化因子 ──────────────────────────
@dataclass
class MacroFeatures:
    date: str = ""
    brent: float | None = None
    brent_chg20_pct: float | None = None
    us10y: float | None = None
    vix: float | None = None
    usdjpy: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def load_macro_series(dcfg) -> dict[str, pd.Series]:
    """{brent/us10y/vix/usdjpy: 收盘序列}。取不到的键缺失（规则自动跳过）。"""
    from .data import load_universe
    out: dict[str, pd.Series] = {}
    try:
        data = load_universe(list(MACRO_SYMBOLS.values()), dcfg)
    except Exception as e:                                    # noqa: BLE001
        log.warning("宏观序列取数失败，宏观量化层跳过: %s", e)
        return out
    for k, sym in MACRO_SYMBOLS.items():
        df = data.get(sym)
        if df is not None and len(df):
            out[k] = df["Close"].astype(float)
    return out


def features_frame(series: dict[str, pd.Series]) -> pd.DataFrame:
    """按日期对齐（并集 + 前向填充）；brent_chg20_pct = 20 个交易日涨幅。"""
    if not series:
        return pd.DataFrame(columns=["brent", "brent_chg20_pct", "us10y", "vix", "usdjpy"])
    idx = pd.DatetimeIndex(sorted(set().union(*[s.index for s in series.values()])))
    f = pd.DataFrame(index=idx)
    for k in ("brent", "us10y", "vix", "usdjpy"):
        f[k] = series[k].reindex(idx).ffill() if k in series else np.nan
    f["brent_chg20_pct"] = (f["brent"] / f["brent"].shift(20) - 1) * 100 if "brent" in series else np.nan
    return f


def features_at(frame: pd.DataFrame, when) -> MacroFeatures:
    """≤ when 的最近一行（信号日收盘时已知的信息）。"""
    if frame is None or frame.empty:
        return MacroFeatures()
    sub = frame.loc[:pd.Timestamp(when)]
    if sub.empty:
        return MacroFeatures()
    r = sub.iloc[-1]
    g = lambda k: (None if pd.isna(r.get(k, np.nan)) else round(float(r[k]), 3))  # noqa: E731
    return MacroFeatures(date=str(sub.index[-1].date()), brent=g("brent"), brent_chg20_pct=g("brent_chg20_pct"),
                         us10y=g("us10y"), vix=g("vix"), usdjpy=g("usdjpy"))


# ────────────────────────── ② 判断层（worker 写入） ──────────────────────────
@dataclass
class MacroOverlay:
    as_of: str = ""
    source: str = ""
    brent: float | None = None
    wti: float | None = None
    us10y: float | None = None
    us2y: float | None = None
    fed_hike_prob: float | None = None
    fed_next: str = ""
    vix: float | None = None
    hy_oas_bp: float | None = None
    usdjpy: float | None = None
    jgb10y: float | None = None
    boj_hike_prob: float | None = None
    boj_next: str = ""
    breadth_pct: float | None = None
    stale: bool = False
    age_days: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def load_overlay(max_age_days: int = 2, today: dt.date | None = None) -> MacroOverlay | None:
    d = read_json(paths.home() / MACRO_FILE, {}) or {}
    if not d or not d.get("as_of"):
        return None
    ov = MacroOverlay()
    for k in ov.__dict__:
        if k in d and k not in ("stale", "age_days"):
            v = d[k]
            if k in ("as_of", "source", "fed_next", "boj_next"):
                setattr(ov, k, str(v or ""))
            else:
                try:
                    setattr(ov, k, None if v is None else float(v))
                except (TypeError, ValueError):
                    setattr(ov, k, None)
    try:
        ov.age_days = ((today or dt.date.today()) - dt.date.fromisoformat(ov.as_of[:10])).days
        ov.stale = ov.age_days > max_age_days
    except ValueError:
        ov.stale = True
    return ov


# ────────────────────────── 规则 ──────────────────────────
def macro_mult(f: MacroFeatures, ov: MacroOverlay | None, market: str) -> tuple[float, list[str]]:
    """市场级新仓倍数（取所有触发规则的 min）。返回 (倍数, 触发说明列表)。"""
    m = market.upper()
    fired: list[tuple[str, float]] = []

    def rule(name: str, jp: float, us: float):
        fired.append((name, jp if m == "JP" else us))

    if f.brent is not None:
        if f.brent >= TH["oil_extreme"]:
            rule(f"Brent {f.brent:.0f} ≥ {TH['oil_extreme']:.0f}", 0.5, 0.75)
        elif f.brent >= TH["oil_high"]:
            rule(f"Brent {f.brent:.0f} ≥ {TH['oil_high']:.0f}", 0.75, 1.0)
    if f.brent_chg20_pct is not None and f.brent_chg20_pct >= TH["oil_shock20_pct"]:
        rule(f"Brent 20 日 +{f.brent_chg20_pct:.0f}%（供给冲击）", 0.75, 0.75)
    if f.us10y is not None:
        if f.us10y >= TH["us10y_stress"]:
            rule(f"美 10Y {f.us10y:.2f}% ≥ {TH['us10y_stress']}", 0.5, 0.5)
        elif f.us10y >= TH["us10y_high"]:
            rule(f"美 10Y {f.us10y:.2f}% ≥ {TH['us10y_high']}", 0.75, 0.75)
    if f.vix is not None:
        if f.vix >= TH["vix_panic"]:
            rule(f"VIX {f.vix:.1f} ≥ {TH['vix_panic']:.0f}", 0.5, 0.0)
        elif f.vix >= TH["vix_high"]:
            rule(f"VIX {f.vix:.1f} ≥ {TH['vix_high']:.0f}", 0.75, 0.5)
    if f.usdjpy is not None and f.usdjpy >= TH["usdjpy_watch"]:
        rule(f"USD/JPY {f.usdjpy:.1f} ≥ {TH['usdjpy_watch']:.0f}（介入区，出口股）", 0.75, 1.0)
    if ov is not None and not ov.stale:
        if ov.hy_oas_bp is not None:
            if ov.hy_oas_bp >= TH["hy_oas_stress"]:
                rule(f"HY 利差 {ov.hy_oas_bp:.0f}bp ≥ {TH['hy_oas_stress']:.0f}", 0.5, 0.0)
            elif ov.hy_oas_bp >= TH["hy_oas_wide"]:
                rule(f"HY 利差 {ov.hy_oas_bp:.0f}bp ≥ {TH['hy_oas_wide']:.0f}", 0.75, 0.5)
        if ov.breadth_pct is not None and ov.breadth_pct < TH["breadth_weak"]:
            rule(f"S&P >50 日线比例 {ov.breadth_pct:.0f}% < {TH['breadth_weak']:.0f}", 1.0, 0.75)
        if ov.fed_hike_prob is not None and ov.fed_hike_prob >= TH["fed_prob_window"]:
            rule(f"下次 FOMC 加息隐含 {ov.fed_hike_prob:.0f}% ≥ {TH['fed_prob_window']:.0f}（政策调整窗口）", 1.0, 0.75)
        if ov.jgb10y is not None:
            if ov.jgb10y >= TH["jgb10y_stress"]:
                rule(f"JGB 10Y {ov.jgb10y:.2f}% ≥ {TH['jgb10y_stress']}", 0.5, 1.0)
            elif ov.jgb10y >= TH["jgb10y_high"]:
                rule(f"JGB 10Y {ov.jgb10y:.2f}% ≥ {TH['jgb10y_high']}", 0.75, 1.0)
        if ov.boj_hike_prob is not None and ov.boj_hike_prob >= TH["boj_prob_window"]:
            rule(f"下次 BOJ 加息隐含 {ov.boj_hike_prob:.0f}% ≥ {TH['boj_prob_window']:.0f}", 0.75, 1.0)
    eff = [(n, v) for n, v in fired if v < 1.0]
    mult = min([v for _, v in eff], default=1.0)
    return mult, [f"{n} → ×{v:g}" for n, v in eff]


def oil_state(f: MacroFeatures) -> str:
    if f.brent is not None and f.brent >= TH["oil_high"]:
        return "high"
    if f.brent_chg20_pct is not None and f.brent_chg20_pct >= TH["oil_shock20_pct"]:
        return "shock"
    return "normal"


# "高估值成长 / 长久期"的判定方式（2026-09-24 信号层检验后按市场选定，见 README）：
#   US：利率 beta —— 250 日滚动，个股日收益对美 10Y 日变动的回归系数，截面最低 1/3
#       （收益率上行期这组信号比其余差 4.96pp，t=−2.54；板块近似在美股是反向的 +3.07pp）
#   JP：板块近似（半导体 + 软件互联网）—— 两种方法在日本都没有证据，保留用户要求的规则
DURATION_METHOD = {"JP": "sector", "US": "rate_beta"}
RATE_BETA_WINDOW = 250
RATE_BETA_FRAC = 1 / 3


def rate_beta_rank(closes: pd.DataFrame, us10y: pd.Series, market: str,
                   window: int = RATE_BETA_WINDOW) -> pd.DataFrame:
    """[日期 × 票] 利率 beta 的截面百分位（越小 = 收益率上行时跌得越多）。
    日本股用前一日的 10Y 变动（美债在东京收盘后才定价）。"""
    rets = closes.pct_change()
    dy = us10y.reindex(rets.index).ffill().diff()
    if market.upper() == "JP":
        dy = dy.shift(1)
    beta = rets.rolling(window, min_periods=int(window * 0.8)).cov(dy).div(
        dy.rolling(window, min_periods=int(window * 0.8)).var(), axis=0)
    return beta.rank(axis=1, pct=True)


def long_duration_set(closes: pd.DataFrame, us10y: pd.Series, market: str) -> set[str]:
    """当前（最后一行）利率 beta 截面最低 1/3 的票。数据不足返回空集。"""
    if closes is None or closes.empty or us10y is None or us10y.empty:
        return set()
    r = rate_beta_rank(closes, us10y, market).iloc[-1].dropna()
    return set(r[r <= RATE_BETA_FRAC].index)


def sector_mult(sector: str, f: MacroFeatures, long_duration: bool | None = None) -> tuple[float, str]:
    """板块倾斜倍数（≤1，不放大预算）。long_duration：按利率 beta 判定的结果；None = 用板块近似。"""
    mult, why = 1.0, ""
    if oil_state(f) != "normal":
        if sector in OIL_LOSERS:
            mult, why = OIL_LOSERS[sector], f"油价高位：{sector} ×{OIL_LOSERS[sector]:g}"
        elif sector in OIL_WINNERS:
            why = f"油价高位：{sector} 受益"
    is_ld = (sector in HIGH_GROWTH) if long_duration is None else bool(long_duration)
    if f.us10y is not None and f.us10y >= TH["us10y_high"] and is_ld:
        mult = min(mult, 0.5)
        tag = "高估值成长" if long_duration is None else "利率敏感（beta 最低 1/3）"
        why = (why + "；" if why else "") + f"10Y {f.us10y:.2f}% ≥ 5：{tag} ×0.5"
    return mult, why


def ticker_mults(tickers: list[str], market: str, f: MacroFeatures,
                 long_duration: set[str] | None = None) -> dict[str, tuple[float, str, str]]:
    """{ticker: (倍数, 板块, 说明)}。long_duration 给定（US 用利率 beta）时替代板块近似。"""
    out = {}
    for t in tickers:
        s = sector_of(t, market)
        m, why = sector_mult(s, f, None if long_duration is None else (t in long_duration))
        out[t] = (m, s, why)
    return out


# ────────────────────────── ④ 事件窗口 ──────────────────────────
# 回测用的历史决定日（第二天）。2026 上半年 BOJ 为公布日程；CPI 不在回测里（发布日不规则），NFP 用「首个周五」近似。
HIST_FOMC = """2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16""".split()
HIST_BOJ = """2021-01-21 2021-03-19 2021-04-27 2021-06-18 2021-07-16 2021-09-22 2021-10-28 2021-12-17
2022-01-18 2022-03-18 2022-04-28 2022-06-17 2022-07-21 2022-09-22 2022-10-28 2022-12-20
2023-01-18 2023-03-10 2023-04-28 2023-06-16 2023-07-28 2023-09-22 2023-10-31 2023-12-19
2024-01-23 2024-03-19 2024-04-26 2024-06-14 2024-07-31 2024-09-20 2024-10-31 2024-12-19
2025-01-24 2025-03-19 2025-05-01 2025-06-17 2025-07-31 2025-09-19 2025-10-30 2025-12-19
2026-01-23 2026-03-19 2026-04-28 2026-06-16 2026-07-31 2026-09-18""".split()


WINDOW_KINDS = ("FOMC", "BOJ", "CPI", "NFP")      # 事件窗口（不开新仓）只认这 4 类；选举 / 财政期限等只在日报日程里展示


@dataclass
class MacroEvent:
    date: dt.date
    kind: str            # FOMC / BOJ / CPI / NFP（窗口用）；ELECTION / POLITICS / FISCAL / TRADE / … 只展示
    home: str            # US / JP
    name: str = ""

    def reaction_date(self, market: str) -> dt.date:
        """该市场对事件作出反应的交易日（日报展示用）。
        US 主场事件（FOMC 14:00 ET、CPI/NFP 08:30 ET）：美股当日；日本股在次一交易日（JST 深夜/晚间发布）。
        BOJ（JST 正午前后）：日本股当日；美股同一历法日（前夜 ET 已知）。"""
        m = market.upper()
        if m == "JP":
            if self.home == "US":
                return jp_next(self.date)
            return self.date if jp_trading_day(self.date) else jp_next(self.date)
        return self.date if us_trading_day(self.date) else us_next(self.date)

    def exposed_sessions(self, market: str) -> list[dt.date]:
        """不开新仓的成交日 = 发布时刻之前最后一个开盘的交易日（"前一日"）；
        若发布发生在该市场盘中（FOMC 对美股、BOJ 对日本股），当日开盘买入同样暴露，再加其前一交易日。
          FOMC 14:00 ET  → 美股: 当日 + 前一日；日本股: 发布前最后一个 JST 交易日（= 会议第二天的 JST 日）
          CPI/NFP 08:30 ET（盘前）→ 美股: 前一交易日；日本股: 当日 JST 交易日（21:30 JST 发布，当日持仓暴露）
          BOJ 正午 JST   → 日本股: 当日 + 前一日；美股: 前一交易日（ET 前夜发布）"""
        m = market.upper()
        if self.kind == "BOJ":
            if m == "JP":
                s0 = self.date if jp_trading_day(self.date) else jp_prev(self.date)
                return [jp_prev(s0), s0]
            return [us_prev(self.date)]
        if m == "US":
            if self.kind == "FOMC":
                s0 = self.date if us_trading_day(self.date) else us_prev(self.date)
                return [us_prev(s0), s0]
            return [us_prev(self.date)]
        return [self.date if jp_trading_day(self.date) else jp_prev(self.date)]


def _parse_events(items) -> list[MacroEvent]:
    out = []
    for it in items or []:
        try:
            out.append(MacroEvent(dt.date.fromisoformat(str(it["date"])[:10]), str(it["kind"]).upper(),
                                  str(it.get("home") or ("JP" if str(it["kind"]).upper() == "BOJ" else "US")).upper(),
                                  str(it.get("name") or "")))
        except (KeyError, ValueError):
            continue
    return out


def load_events(include_history: bool = False, nfp_heuristic_years: tuple[int, int] | None = None,
                kinds=None) -> list[MacroEvent]:
    """官方日程（var/macro_events.json）；include_history 时并入历史 FOMC/BOJ 与 NFP 首周五近似（回测用）。
    kinds：只保留这些事件类型（如 {"FOMC","BOJ"}），None = 全部。"""
    d = read_json(paths.home() / EVENTS_FILE, {}) or {}
    ev = _parse_events(d.get("events"))
    if include_history:
        ev += [MacroEvent(dt.date.fromisoformat(x), "FOMC", "US") for x in HIST_FOMC]
        ev += [MacroEvent(dt.date.fromisoformat(x), "BOJ", "JP") for x in HIST_BOJ]
        if nfp_heuristic_years:
            for y in range(nfp_heuristic_years[0], nfp_heuristic_years[1] + 1):
                for mo in range(1, 13):
                    d1 = dt.date(y, mo, 1)
                    first_fri = d1 + dt.timedelta(days=(4 - d1.weekday()) % 7)
                    if first_fri.day <= 2 and mo in (1, 7):     # 元旦/独立日周通常顺延一周
                        first_fri += dt.timedelta(days=7)
                    ev.append(MacroEvent(first_fri, "NFP", "US", "首周五近似"))
    if kinds:
        want = {str(k).upper() for k in kinds}
        ev = [e for e in ev if e.kind in want]
    seen, uniq = set(), []
    for e in ev:
        k = (e.date, e.kind)
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return sorted(uniq, key=lambda e: e.date)


def blocked_fill_dates(events: list[MacroEvent], market: str) -> dict[dt.date, str]:
    """{不开新仓的成交日: 原因}，见 MacroEvent.exposed_sessions。"""
    out: dict[dt.date, str] = {}
    for e in events:
        for d in e.exposed_sessions(market):
            out.setdefault(d, f"{e.kind} {e.date.isoformat()} 发布前不开新仓")
    return out


def event_block(market: str, fill_date: dt.date, events: list[MacroEvent] | None = None) -> str | None:
    ev = events if events is not None else load_events(kinds=WINDOW_KINDS)
    return blocked_fill_dates(ev, market).get(fill_date)


def next_events(events: list[MacroEvent], today: dt.date, n: int = 4) -> list[dict]:
    return [{"date": e.date.isoformat(), "kind": e.kind, "name": e.name}
            for e in events if e.date >= today][:n]


# ────────────────────────── 回测：每日 × 每票 的新仓倍数矩阵 ──────────────────────────
def build_entry_mult(gidx: pd.DatetimeIndex, tickers: list[str], market: str, frame: pd.DataFrame | None,
                     use_macro: bool = True, use_sector: bool = True, use_events: bool = True,
                     events: list[MacroEvent] | None = None,
                     closes: pd.DataFrame | None = None) -> tuple[np.ndarray, dict]:
    """返回 (矩阵 [len(gidx) × n]，统计)。第 i 行 = 在 gidx[i] 开盘成交的新仓倍数，
    用的是 gidx[i-1]（信号日）收盘时已知的宏观值 → 无前视。
    closes：[日期 × 票] 收盘（US 的利率 beta 判定要用；不给则退回板块近似）。"""
    n = len(tickers)
    M = np.ones((len(gidx), n))
    stats = {"macro_days": 0, "sector_days": 0, "event_days": 0, "zero_days": 0}
    secs = [sector_of(t, market) for t in tickers]
    ld_rank = None
    if (use_sector and DURATION_METHOD.get(market.upper()) == "rate_beta" and closes is not None
            and frame is not None and "us10y" in frame and frame["us10y"].notna().any()):
        ld_rank = rate_beta_rank(closes.reindex(columns=tickers), frame["us10y"], market).reindex(gidx)
    blocked = blocked_fill_dates(events, market) if (use_events and events) else {}
    for i in range(len(gidx)):
        f = features_at(frame, gidx[i - 1]) if (frame is not None and i > 0) else MacroFeatures()
        row = np.ones(n)
        if use_macro:
            mm, _ = macro_mult(f, None, market)
            if mm < 1.0:
                stats["macro_days"] += 1
                row *= mm
        if use_sector:
            if ld_rank is not None and i > 0:
                rk = ld_rank.iloc[i - 1].values
                sm = np.array([sector_mult(s, f, bool(rk[j] <= RATE_BETA_FRAC) if rk[j] == rk[j] else False)[0]
                               for j, s in enumerate(secs)])
            else:
                sm = np.array([sector_mult(s, f)[0] for s in secs])
            if (sm < 1.0).any():
                stats["sector_days"] += 1
                row *= sm
        if use_events and gidx[i].date() in blocked:
            stats["event_days"] += 1
            row[:] = 0.0
        if (row <= 0).all():
            stats["zero_days"] += 1
        M[i] = row
    return M, stats


def snapshot(market: str, f: MacroFeatures, ov: MacroOverlay | None, mult: float, fired: list[str],
             tilts: dict[str, tuple[float, str, str]], today: dt.date, fill_date: dt.date,
             events: list[MacroEvent], block_reason: str | None) -> dict:
    """写进日报的宏观面板。"""
    tilt_summary: dict[str, dict] = {}
    for t, (m, s, why) in tilts.items():
        if m < 1.0 or "受益" in why:
            tilt_summary.setdefault(s, {"mult": m, "why": why, "n": 0})["n"] += 1
    return {"features": f.to_dict(), "overlay": ov.to_dict() if ov else None, "mult": mult, "fired": fired,
            "oil_state": oil_state(f), "sector_tilts": tilt_summary,
            "fill_date": fill_date.isoformat(), "event_block": block_reason,
            "next_events": next_events(events, today), "thresholds": TH}
