"""unified.py — 一个账户（日元 + 美元）同时交易日本株 / 美股 / 指数 ETF 的统一引擎。回测与模拟盘共用同一个逐日推进器。

为什么要统一：真实账户只有一笔钱（例如 100 万円）。买美股要先把日元换成美元（楽天 リアルタイム為替：手数料 0 銭、有买卖价差，按片道 3 銭估；円貨決済 / 定時為替是 ±25 銭），
美股卖出后的美元要换回日元才能买日本股；日本与美股的买入机会要放在一起排名、共用名额，而不是两个互不相干的账户。

楽天的规则（官方页面，2026-09-25 核对，仅对该时点有效）：リアルタイム為替 平日 8:00～翌 6:00（夏 5:00），手数料 0 銭（有买卖价差），
换得的美元立即可用于美股外貨決済买入；美股卖出的美元在国内約定日（美股交易日的下一个日本营业日）8:00 起即可换回日元；
日本株卖出所得即时反映到买付余力；RSS 只能下日本株 / ETF 的单（美股、换汇只能手动：网页 / iSPEED / MARKETSPEED II）。

一个日历日 D（日本时间）里的事件顺序 —— 引擎按这个顺序推进，绝不用到还没发生的价格或现金：
  08:00 换汇开放  ⓪ 闲置美元（美股昨夜卖出所得等）换回日元（fx_before_jp_open）
  09:00 日本开盘  ① 日本个股卖出 → ② 核心 ETF（东证上市，日元）卖出 → ③ 日本个股买入 → ④ 核心 ETF 买入
                   （③④ 都要给当天计划的「日元→美元」换汇留出日元）
  日间    换汇     ⑤ 执行前一晚计划的换汇（日元→美元供今晚美股买入；闲置美元→日元）。汇率 = 当天开盘时的 USD/JPY 中值 ± 点差
  15:30 日本收盘  ⑥ 日本持仓的止损 / 离场判断 → 排到下一个日本开盘
  夜间 美股开盘    ⑦ 美股卖出 → ⑧ 美股买入（只能用美元）
  次晨 美股收盘    ⑨ 美股持仓的止损 / 离场判断 → 排到下一个美股开盘
  07:00 统一决策  ⑩ 日本收盘与美股收盘都已知：两个市场的新信号一起排名、共用名额；决定明天的日本单、换汇、美股单、核心 ETF 调整

统一排名（事先写定）：7 个信号强度指标都没有稳定的预测力（README），所以不按「强弱」排，而按**执行成本**从低到高：
  0 = 日本株（楽天 ゼロコース 0 円、不用换汇）；1 = 美股且美元已够（只付美股手续费）；2 = 美股且要先换汇（手续费 + 换汇来回）。
  同档按代码字母序（与原引擎相同）。每只票的预算 = 权益（日元计）× position_pct × 宏观 / 板块倍数。
「合不合适」的判断在规则里：美股机会只在「名额还有、换汇来得及（当天的换汇窗口在美股开盘之前）」时才成立；
美股卖出后的美元默认在下一个换汇窗口换回日元（usd_keep=False），日本新仓最早在换回之后的下一个日本开盘成交。
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from .config import ExecConfig, StrategyParams
from .engine import _Aligned
from .fees import side_fee
from .tick import limit_lock, lot_size

MKT = ("JP", "US")
CCY = {"JP": "JPY", "US": "USD"}


def market_of(ticker: str) -> str:
    return "JP" if ticker.endswith(".T") else "US"


@dataclass
class UnifiedConfig:
    capital_jpy: float = 1_000_000
    position_pct: float = 0.25            # 单只个股占总权益（日元计）
    max_positions: int = 4                # 日本 + 美股合计的个股名额
    max_position_pct: float = 0.34
    cash_buffer_pct: float = 1.0
    stock_markets: tuple = ("JP", "US")   # 个股参与统一排名的市场
    core: dict = field(default_factory=lambda: {"1329.T": 1.0})       # 核心 ETF → 权重（闲置资金按权重分）
    core_index: dict = field(default_factory=lambda: {"1329.T": "JP"})  # 该 ETF 跟哪个市场的牛熊分界
    core_mode: str = "split"              # split：熊市那份留现金；follow：熊市那份转给牛市的 ETF
    core_buffer_pct: float = 0.0
    band_pct: float = 10.0
    margin_pct: float = 3.0               # 资金缺口按开盘跳空上限多预留
    fx_spread_yen: float = 0.03           # 楽天リアルタイム為替：手数料 0 銭（2023-12-04 起），业者间买卖价差未公布 → 按片道 3 銭估
                                          # （定時為替 / 米国株円貨決済是 ±25 銭；「先换汇再买」更便宜）
    fx_on_jp_holidays: bool = True        # リアルタイム為替：日本祝日按海外先物取引日可以下单（土日不行，引擎里本来就没有周末）
    fx_before_jp_open: bool = True        # リアルタイム為替 8:00 起：美股卖出的美元次日 8 点换回日元，赶上 9:00 日本开盘
    usd_keep: bool = False                # False：美股卖出后的美元在下一个换汇窗口换回日元
    usd_min_back: float = 100.0           # 闲置美元少于这个数（例如换汇时多换的零头）就留着下次买美股用，不来回付点差
    usd_keep_imminent: bool = False       # True：美股候补里有「即将触发 / 已触发」的票时，闲置美元先不换回日元
    us_same_open_reuse: bool = True       # 美股卖出所得当晚可再买美股

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UPos:
    ticker: str
    market: str
    shares: int
    entry_px: float
    entry_date: str
    stop_px: float
    peak: float
    last_close: float
    hold: int = 0
    armed: bool = False
    entry_fx: float = 1.0                 # 美股：买入当天的 USD/JPY（算日元损益用）


def exec_configs(stock_markets, u: dict | None = None) -> dict:
    """推进器要的两个市场的执行参数：做个股的市场按所选券商（sim.json unified.broker）；
    不做个股的市场（例如立花不做美股，美股只经由东证 1655）只是结构需要，不会产生手续费 → 用默认值，不套用别家的费率。"""
    from .config import ExecConfig
    from .fees import BROKERS, broker_of
    out = {}
    for m in ("JP", "US"):
        b = broker_of(m, u)
        if m not in tuple(stock_markets) and m not in BROKERS[b]["markets"]:
            out[m] = ExecConfig(market=m).validate()
        else:
            out[m] = ExecConfig.for_market(m, b)
    return out


@dataclass
class UState:
    cash_jpy: float
    cash_usd: float = 0.0
    pos: dict = field(default_factory=dict)            # ticker -> UPos
    core_units: dict = field(default_factory=dict)     # ticker -> 份额
    core_last: dict = field(default_factory=dict)      # ticker -> 最近收盘价
    pending_exit: dict = field(default_factory=dict)   # ticker -> 离场原因（下一个该市场开盘卖出）
    plan: dict = field(default_factory=dict)           # ticker -> [信号日收盘, 股数, 决策日]
    core_plan: dict = field(default_factory=dict)      # ticker -> ["SELL"/"BUY", 份额]
    fx_plan: list = field(default_factory=list)        # [{"dir": "JPY>USD"/"USD>JPY", "usd": 金额}]
    fx_reserve_jpy: float = 0.0                        # 日本开盘时要给换汇留的日元
    last_date: str = ""
    trades: list = field(default_factory=list)
    core_trades: list = field(default_factory=list)
    fx_trades: list = field(default_factory=list)
    history: list = field(default_factory=list)       # [日期, 日元权益, 日元现金, 美元现金, USD/JPY]
    corp_done: list = field(default_factory=list)     # 已处理的公司行为 "代码|日期"（模拟盘；幂等用）
    corp_log: list = field(default_factory=list)      # [{"date", "ticker", "note"}]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pos"] = {t: asdict(p) if isinstance(p, UPos) else p for t, p in self.pos.items()}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "UState":
        s = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        s.pos = {t: (p if isinstance(p, UPos) else UPos(**p)) for t, p in (d.get("pos") or {}).items()}
        return s


def imminent_flags(df: pd.DataFrame) -> pd.Series:
    """候补队列的「已触发 / 即将触发」（qbreak/scan.py 同一定义）：横盘 且 MACD 在 0 轴附近 且 MACD 在信号线下方不到
    收盘价的 0.15% 且 量比 ≥ 1；或当天已发出 entry。只用当天收盘为止的数据。"""
    if not {"macd", "macd_sig", "is_range", "near_zero", "vol_ratio"} <= set(df.columns):
        return df["entry"].astype(bool)
    gap = (df["macd"] - df["macd_sig"]) / df["Close"] * 100
    imm = df["is_range"].astype(bool) & df["near_zero"].astype(bool) & (gap < 0) & (gap > -0.15) & (df["vol_ratio"] >= 1.0)
    return (imm.fillna(False) | df["entry"].astype(bool)).astype(bool)


def config_from_sim(sim: dict) -> UnifiedConfig:
    """sim.json 的 unified 段 → UnifiedConfig（楽天：日本株 / 东证 ETF 0 円、美股 0.495% 上限 $22、换汇按片道 3 銭估）。"""
    u = sim.get("unified") or {}
    d = UnifiedConfig()
    kw = {k: u[k] for k in ("position_pct", "max_positions", "max_position_pct", "cash_buffer_pct", "core_mode",
                           "core_buffer_pct", "band_pct", "margin_pct", "fx_spread_yen", "fx_on_jp_holidays",
                           "usd_keep", "usd_keep_imminent", "us_same_open_reuse") if k in u}
    return UnifiedConfig(capital_jpy=float(sim.get("capital_jpy") or d.capital_jpy),
                         stock_markets=tuple(u.get("stock_markets", d.stock_markets)),
                         core=dict(u.get("core", d.core)), core_index=dict(u.get("core_index", d.core_index)), **kw)


def apply_corp_action(st: UState, ticker: str, date: str, dividend: float = 0.0, split: float = 0.0,
                      div_net: float = 1.0) -> str | None:
    """把一次除息 / 拆股补到状态上（模拟盘：行情是复权价，持仓按真实价格记账；规则与 PaperBroker 相同）。
    拆股 1→k：股数 ×k，成本 / 止损 / 峰值 / 收盘 ÷k，计划单股数 ×k、信号价 ÷k。除息：到手分红（税后）进该市场的现金，
    止损与峰值各减一个分红额。同一票同一日期只处理一次；没有持仓 / 计划时返回 None。"""
    key = f"{ticker}|{date}"
    if key in st.corp_done:
        return None
    m, notes = market_of(ticker), []
    p = st.pos.get(ticker)
    k = float(split or 0)
    if k > 0 and abs(k - 1) > 1e-9:
        if p:
            old = p.shares
            p.shares = int(old * k + 1e-6)
            for f in ("entry_px", "stop_px", "peak", "last_close"):
                setattr(p, f, float(getattr(p, f)) / k)
            notes.append(f"株式分割 1:{k:g}（{old}→{p.shares} 株）")
        if int(st.core_units.get(ticker) or 0):
            old = int(st.core_units[ticker])
            st.core_units[ticker] = int(old * k + 1e-6)
            if st.core_last.get(ticker):
                st.core_last[ticker] = float(st.core_last[ticker]) / k
            notes.append(f"分割 1:{k:g}（{old}→{st.core_units[ticker]} 口）")
        if ticker in st.plan:
            pl = st.plan[ticker]
            pl[0], pl[1] = float(pl[0]) / k, int(int(pl[1]) * k + 1e-6)
            notes.append("计划单同步调整")
        if ticker in st.core_plan:
            st.core_plan[ticker][1] = int(int(st.core_plan[ticker][1]) * k + 1e-6)
    dv = float(dividend or 0)
    qty = (p.shares if p else 0) + int(st.core_units.get(ticker) or 0)
    if dv > 0 and qty > 0:
        net = dv * qty * div_net
        if m == "US":
            st.cash_usd += net
        else:
            st.cash_jpy += net
        if p:
            p.stop_px, p.peak = max(0.0, p.stop_px - dv), max(0.0, p.peak - dv)
        notes.append(f"配当落ち {dv:g} × {qty:,} → 税后 {'$' if m == 'US' else '¥'}{net:,.2f} 入账" if div_net > 0
                     else f"配当落ち {dv:g} × {qty:,}（止损 / 峰值同步下调；现金以券商实际入账为准）")
    if not notes:
        return None
    st.corp_done.append(key)
    note = "；".join(notes)
    st.corp_log.append({"date": date, "ticker": ticker, "note": note})
    return note


@dataclass
class UnifiedResult:
    equity: pd.Series
    trades: pd.DataFrame
    state: UState
    skipped: dict
    metrics: dict = field(default_factory=dict)


class UnifiedEngine:
    """ind：{ticker: compute_indicators 的结果}（日本票以 .T 结尾）；core ETF 也放在 ind 里（entry 全 False）。
    params：{"JP": StrategyParams, "US": StrategyParams}（离场规则按市场）；ex：{"JP": ExecConfig, "US": ExecConfig}；
    core_cost：{ETF: 成本字典}；fx：DataFrame(Open, Close)（USD/JPY）；entry_mult：{"JP"/"US": DataFrame(日期 × 票)}，
    按成交日取（缺省 1）；bear：{"JP"/"US": 布尔 Series}，True = 该市场收盘时熊市（核心 ETF 目标 0）。"""

    def __init__(self, ind: dict[str, pd.DataFrame], cfg: UnifiedConfig, params: dict[str, StrategyParams],
                 ex: dict[str, ExecConfig], core_cost: dict[str, dict], fx: pd.DataFrame | None = None,
                 entry_mult: dict[str, pd.DataFrame] | None = None, bear: dict[str, pd.Series] | None = None,
                 state: UState | None = None):
        self.cfg, self.params, self.ex, self.core_cost = cfg, params, ex, core_cost
        self.gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))
        self.A = A = _Aligned(ind, self.gidx)
        self.col = {t: j for j, t in enumerate(A.tickers)}
        self.mkt = np.array([market_of(t) for t in A.tickers])
        self.core_set = set(cfg.core)
        n = len(self.gidx)
        self.sess = {m: (A.has[:, self.mkt == m].any(axis=1) if (self.mkt == m).any() else np.zeros(n, bool))
                     for m in MKT}
        self.nxt = {m: self._next_true(self.sess[m]) for m in MKT}
        self.lots = np.array([int(core_cost[t].get("lot", 1)) if t in self.core_set else lot_size(t, market_of(t))
                              for t in A.tickers])
        if fx is None:
            fx = pd.DataFrame({"Open": 1.0, "Close": 1.0}, index=self.gidx)
        f = fx.reindex(self.gidx.union(fx.index)).ffill().bfill().reindex(self.gidx)
        self.fx_open, self.fx_close = f["Open"].to_numpy(float), f["Close"].to_numpy(float)
        self.em = {}
        for m in MKT:
            M = (entry_mult or {}).get(m)
            self.em[m] = M.reindex(self.gidx).fillna(1.0) if M is not None else None
        self.us_imminent = np.zeros(n, bool)                   # 当天收盘时美股候补里有「即将触发 / 已触发」
        if cfg.usd_keep_imminent:
            for t, df in ind.items():
                if market_of(t) != "US" or t in self.core_set or "US" not in cfg.stock_markets:
                    continue
                self.us_imminent |= imminent_flags(df).reindex(self.gidx).fillna(False).to_numpy(bool)
        self.bear = {m: (bear[m].reindex(self.gidx.union(bear[m].index)).ffill().reindex(self.gidx)
                         .fillna(False).to_numpy(bool) if bear and bear.get(m) is not None else np.zeros(n, bool))
                     for m in MKT}
        self.fees = {m: ex[m].fee for m in MKT}
        self.slip = {m: ex[m].slippage_pct / 100 for m in MKT}
        self.c_fee = {t: {s: side_fee(core_cost[t], s) for s in ("BUY", "SELL")} for t in cfg.core}
        self.c_slip = {t: float(core_cost[t].get("slip_pct", 0.02)) / 100 for t in cfg.core}
        self.st = state or UState(cash_jpy=float(cfg.capital_jpy))
        for t in cfg.core:
            self.st.core_units.setdefault(t, 0)
        self.last_bar = np.full(len(A.tickers), -1)        # 每只票最近一根 K 线的位置（上一根 ATR / 涨跌停判断用）
        self.skipped: dict[str, int] = {k: 0 for k in ("gap", "cash", "lot", "full", "no_bar", "rebuy", "macro",
                                                        "limit_up", "limit_down_hold", "usd", "fx_window",
                                                        "earnings")}
        self._sold_today: set[str] = set()
        # 模拟盘最后一天的决策：明天还不在数据里 → 用当天算好的倍数（{市场: (市场倍数, {票: 板块倍数}, 拦截原因)}）
        # 与「明天白天能否换汇」（日本营业日才有换汇窗口）
        self.live_mult: dict[str, tuple] = {}
        self.live_fx_ok: bool = True
        self.entry_block_fn = None                          # (票, 日) -> 拦截原因 | None（模拟盘：决算前 N 日不进场）

    # ── 工具 ──
    @staticmethod
    def _next_true(mask: np.ndarray) -> np.ndarray:
        out = np.full(len(mask), -1)
        nxt = -1
        for i in range(len(mask) - 1, -1, -1):
            out[i] = nxt
            if mask[i]:
                nxt = i
        return out

    def _p(self, t: str) -> StrategyParams:
        return self.params[market_of(t)]

    def _px_close(self, t: str, i: int) -> float:
        j = self.col[t]
        if self.A.has[i, j]:
            return float(self.A.close[i, j])
        if t in self.st.pos:
            return self.st.pos[t].last_close
        return float(self.st.core_last.get(t, np.nan))

    def equity(self, i: int) -> float:
        st, fx = self.st, self.fx_close[i]
        v = st.cash_jpy + st.cash_usd * fx
        for t, ps in st.pos.items():
            px = self._px_close(t, i)
            v += ps.shares * px * (fx if ps.market == "US" else 1.0)
        for t, u in st.core_units.items():
            if u:
                v += u * self._px_close(t, i)
        return v

    def _locked(self, i: int, j: int) -> str | None:
        if self.mkt[j] != "JP":
            return None
        k = int(self.last_bar[j])
        if k < 0 or not self.A.has[k, j]:
            return None
        return limit_lock(self.A.close[k, j], self.A.high[i, j], self.A.low[i, j], self.A.close[i, j], "JP")

    # ── 成交 ──
    def _close(self, t: str, px: float, i: int, reason: str) -> None:
        st = self.st
        ps = st.pos.pop(t)
        m, fee = ps.market, self.fees[ps.market]
        proceeds = ps.shares * px
        f = fee(proceeds) + fee(ps.shares * ps.entry_px)
        pnl = (px - ps.entry_px) * ps.shares - f
        if m == "US":
            st.cash_usd += proceeds - fee(proceeds)
        else:
            st.cash_jpy += proceeds - fee(proceeds)
        fx = self.fx_close[i] if m == "US" else 1.0
        st.trades.append(dict(ticker=t, market=m, entry_date=ps.entry_date, exit_date=str(self.gidx[i].date()),
                              entry_px=round(ps.entry_px, 4), exit_px=round(px, 4), shares=ps.shares,
                              pnl=round(pnl, 2), pnl_jpy=round(pnl * fx, 0),
                              ret_pct=round((px / ps.entry_px - 1) * 100, 3), hold_days=ps.hold, reason=reason))
        self._sold_today.add(t)

    def _core_trade(self, t: str, side: str, units: int, i: int, px: float | None = None) -> None:
        """核心 ETF 成交记账。px=None：回测撮合（开盘价 ± 滑点）；给了 px：实盘执行器的实际成交价。"""
        st, j = self.st, self.col[t]
        if units <= 0 or (px is None and not self.A.has[i, j]):
            return
        if px is None:
            px = self.A.open[i, j] * (1 + self.c_slip[t] if side == "BUY" else 1 - self.c_slip[t])
        notional = units * px
        f = self.c_fee[t][side](notional)
        if side == "BUY":
            st.cash_jpy -= notional + f
            st.core_units[t] = st.core_units.get(t, 0) + units
        else:
            st.cash_jpy += notional - f
            st.core_units[t] = st.core_units.get(t, 0) - units
        st.core_trades.append((str(self.gidx[i].date()), t, side, units, round(px, 4), round(f, 2)))

    def _exec_exits(self, m: str, i: int) -> None:
        st = self.st
        for t in list(st.pending_exit):
            if market_of(t) != m:
                continue
            if t not in st.pos:
                st.pending_exit.pop(t)
                continue
            j = self.col[t]
            if not self.A.has[i, j]:
                continue
            if self._locked(i, j) == "down":
                self.skipped["limit_down_hold"] += 1
                continue
            self._close(t, self.A.open[i, j] * (1 - self.slip[m]), i, st.pending_exit.pop(t))

    def _exec_buys(self, m: str, i: int) -> None:
        st, A, cfg = self.st, self.A, self.cfg
        ex, slip, fee = self.ex[m], self.slip[m], self.fees[m]
        for t in [x for x in list(st.plan) if market_of(x) == m]:
            sig_close, shares, _ = st.plan.pop(t)
            j = self.col[t]
            if not A.has[i, j]:
                self.skipped["no_bar"] += 1
                continue
            if t in st.pos:
                continue
            if len(st.pos) >= cfg.max_positions:
                self.skipped["full"] += 1
                continue
            if ex.forbid_same_day_rebuy and t in self._sold_today:
                self.skipped["rebuy"] += 1
                continue
            o = A.open[i, j]
            if ex.max_entry_gap_pct and o > sig_close * (1 + ex.max_entry_gap_pct / 100):
                self.skipped["gap"] += 1
                continue
            if self._locked(i, j) == "up":
                self.skipped["limit_up"] += 1
                continue
            px = o * (1 + slip)
            lot = int(self.lots[j])
            cash = st.cash_jpy - st.fx_reserve_jpy if m == "JP" else st.cash_usd
            while shares > 0 and shares * px + fee(shares * px) > cash:
                shares -= lot
            if shares <= 0:
                self.skipped["cash" if m == "JP" else "usd"] += 1
                continue
            self._open(t, m, shares, px, i)

    def _open(self, t: str, m: str, shares: int, px: float, i: int) -> None:
        """按成交价开仓：止损按开仓前一根 K 线的 ATR（没有就按固定比例），扣现金与手续费。
        回测撮合（_exec_buys）与实盘执行器（券商回报的实际成交价）共用。"""
        st, A, fee = self.st, self.A, self.fees[m]
        j = self.col[t]
        p = self._p(t)
        k = int(self.last_bar[j])
        atr_prev = A.atr[k, j] if k >= 0 else np.nan
        stop_px = (px - atr_prev * p.atr_stop_mult if p.atr_stop_mult > 0 and np.isfinite(atr_prev)
                   else px * (1 - p.stop_loss_pct / 100))
        if not (0 < stop_px < px):
            stop_px = px * (1 - p.stop_loss_pct / 100)
        notional = shares * px
        if m == "JP":
            st.cash_jpy -= notional + fee(notional)
        else:
            st.cash_usd -= notional + fee(notional)
        st.pos[t] = UPos(t, m, shares, px, str(self.gidx[i].date()), stop_px, px, px, hold=0,
                         entry_fx=float(self.fx_close[i]) if m == "US" else 1.0)

    def sell_fill(self, t: str, qty: int, px: float, i: int, reason: str) -> None:
        """实盘执行器：个股卖出的实际成交（可能部分成交：只卖出 qty 股，剩下的继续持有、留在待卖）。"""
        ps = self.st.pos[t]
        if qty >= ps.shares:
            self._close(t, px, i, reason)
            return
        rest = UPos(**{**asdict(ps), "shares": ps.shares - int(qty)})
        ps.shares = int(qty)
        self._close(t, px, i, reason + "（部分成交）")
        self.st.pos[t] = rest

    def _exec_fx(self, i: int, only: str | None = None) -> None:
        """执行计划的换汇。only="USD>JPY"：日本开盘前只换回日元（fx_before_jp_open）；其余留到开盘后。"""
        st, sp = self.st, self.cfg.fx_spread_yen
        mid = float(self.fx_open[i])
        keep = []
        for o in st.fx_plan:
            if only and o["dir"] != only:
                keep.append(o)
                continue
            if o["dir"] == "JPY>USD":
                rate = mid + sp
                usd = min(float(o["usd"]), math.floor(st.cash_jpy / rate * 100) / 100)
                if usd <= 0:
                    continue
                st.cash_jpy -= usd * rate
                st.cash_usd += usd
            else:
                rate = mid - sp
                usd = min(float(o["usd"]), st.cash_usd)
                if usd <= 0:
                    continue
                st.cash_usd -= usd
                st.cash_jpy += usd * rate
            st.fx_trades.append((str(self.gidx[i].date()), o["dir"], round(usd, 2), round(rate, 4)))
        st.fx_plan = keep
        if not keep:
            st.fx_reserve_jpy = 0.0

    def _check_exits(self, m: str, i: int) -> None:
        """收盘：止损 / 跟踪止损 / 止盈 / 死叉 / 出货日 / 最长持有 / 时间止损（与 engine.run_backtest 的第 3 步相同）。"""
        st, A = self.st, self.A
        for t in list(st.pos):
            ps = st.pos[t]
            if ps.market != m:
                continue
            j = self.col[t]
            if not A.has[i, j]:
                continue
            p, ex = self._p(t), self.ex[m]
            ps.hold += 1
            o, h, l, c = A.open[i, j], A.high[i, j], A.low[i, j], A.close[i, j]
            if p.trailing_arm_pct and not ps.armed and h >= ps.entry_px * (1 + p.trailing_arm_pct / 100):
                ps.armed = True
            trail_on = p.trailing_stop_pct > 0 and (ps.armed or not p.trailing_arm_pct)
            tp_px = ps.entry_px * (1 + p.take_profit_pct / 100) if p.take_profit_pct else np.inf
            queued = None
            if ex.stop_fill_mode == "intraday":
                trail_px = ps.peak * (1 - p.trailing_stop_pct / 100) if trail_on else -np.inf
                hard = max(ps.stop_px, trail_px)
                exit_px = reason = None
                if o <= hard:
                    exit_px, reason = o, "gap_stop"
                elif l <= hard:
                    exit_px, reason = hard, ("trail" if trail_px > ps.stop_px else "stop")
                elif h >= tp_px:
                    exit_px, reason = max(tp_px, o), "take_profit"
                if exit_px is not None:
                    if self._locked(i, j) == "down":
                        self.skipped["limit_down_hold"] += 1
                        st.pending_exit[t] = reason
                        ps.last_close = c
                        continue
                    self._close(t, exit_px * (1 - self.slip[m]), i, reason)
                    continue
                ps.peak = max(ps.peak, h)
            else:
                ps.peak = max(ps.peak, h)
                trail_px = ps.peak * (1 - p.trailing_stop_pct / 100) if trail_on else -np.inf
                hard = max(ps.stop_px, trail_px)
                if c <= hard:
                    queued = "trail" if trail_px > ps.stop_px else "stop"
                elif c >= tp_px:
                    queued = "take_profit"
            ps.last_close = c
            if queued is None:
                if p.exit_on_climax and A.climax[i, j] and (c / ps.entry_px - 1) * 100 >= p.climax_min_gain_pct:
                    queued = "climax"
                elif p.exit_on_macd_dead_cross and A.dead[i, j]:
                    queued = "dead_cross"
                elif p.max_hold_days and ps.hold >= p.max_hold_days:
                    queued = "max_hold"
                elif (p.time_stop_days and ps.hold >= p.time_stop_days
                      and (c / ps.entry_px - 1) * 100 < p.time_stop_min_ret_pct):
                    queued = "time_stop"
            if queued:
                st.pending_exit[t] = queued

    # ── 统一决策（日本时间次日 07:00：日本收盘与美股收盘都已知）──
    def _sell_net(self, t: str, i: int) -> float:
        ps = self.st.pos[t]
        m = ps.market
        px = self._px_close(t, i) * (1 - self.slip[m])
        return ps.shares * px - self.fees[m](ps.shares * px)

    def _entry_mult(self, t: str, i: int) -> float:
        m = market_of(t)
        k = int(self.nxt[m][i])
        if k < 0 and m in self.live_mult:                  # 模拟盘：成交日在明天
            scale, tmult, block = self.live_mult[m]
            return 0.0 if block else float(scale) * float((tmult or {}).get(t, 1.0))
        M = self.em[m]
        if M is None or k < 0 or t not in M.columns:
            return 1.0
        return float(M.iat[k, M.columns.get_loc(t)])

    def _fx_ok(self, i: int) -> bool:
        """决策后的第一个换汇日（日本营业日；fx_on_jp_holidays 时每天）是否不晚于下一个美股开盘日 ——
        例：周四收盘后决策，周五白天换汇、周五夜美股买入；周一若是日本假日，周五就已换好。"""
        k = int(self.nxt["US"][i])
        if k < 0:
            return self.live_fx_ok
        if self.cfg.fx_on_jp_holidays:
            return True
        j = int(self.nxt["JP"][i])
        return 0 <= j <= k

    def _fx_ok_jp(self, i: int) -> bool:
        """明早日本开盘那天是否有换汇窗口（开盘前换回日元用）。"""
        k = int(self.nxt["JP"][i])
        return self.live_fx_ok if k < 0 else bool(self.sess["JP"][k])

    def _decide(self, i: int) -> None:
        st, A, cfg = self.st, self.A, self.cfg
        fx = float(self.fx_close[i])
        eq = self.equity(i)
        exit_ts = [t for t in st.pending_exit if t in st.pos]
        jp_exit_net = sum(self._sell_net(t, i) for t in exit_ts if market_of(t) == "JP")
        us_exit_net = sum(self._sell_net(t, i) for t in exit_ts if market_of(t) == "US")
        core_liq = 0.0
        for t, u in st.core_units.items():
            if u and A.has[i, self.col[t]]:
                cpx = float(A.close[i, self.col[t]]) * (1 - self.c_slip[t])
                core_liq += u * cpx - self.c_fee[t]["SELL"](u * cpx)
        cash_est = st.cash_jpy + jp_exit_net                     # 明早日本开盘时的日元（不含核心卖出）
        sp, mg, buf = cfg.fx_spread_yen, 1 + cfg.margin_pct / 100, 1 - cfg.cash_buffer_pct / 100
        rb, rs = fx + sp, fx - sp                                # 买美元 / 卖美元的汇率（中值 ± 点差）
        jpy0 = cash_est + core_liq                               # 日元池：明早开盘可用（含核心卖出）
        reuse = us_exit_net if cfg.us_same_open_reuse else 0.0
        usd0 = st.cash_usd + reuse                               # 美元池：现有 + 今晚美股卖出所得
        pre = cfg.fx_before_jp_open and not cfg.usd_keep and self._fx_ok_jp(i)
        post = self._fx_ok(i)
        used_jpy = used_usd = 0.0                                # 已计划的日本 / 美股买入成本
        for t0, (c0, sh0, _) in st.plan.items():                 # 还没成交的旧计划（另一个市场休市时会跨过一次决策）先占住资金
            m0 = market_of(t0)
            px0 = c0 * (1 + self.slip[m0])
            if m0 == "JP":
                used_jpy += sh0 * px0 + self.fees[m0](sh0 * px0)
            else:
                used_usd += sh0 * px0 + self.fees[m0](sh0 * px0)
        x_usd = 0.0                                              # 开盘前 美元→日元（给日本买入）
        y_usd = 0.0                                              # 开盘后 日元→美元（给美股买入）

        def jpy_avail() -> float:
            return jpy0 - used_jpy - y_usd * rb + x_usd * rs

        def usd_cash_free() -> float:                           # 现有美元里还没被占用、明早能先换回日元的部分
            return st.cash_usd - max(0.0, used_usd - reuse) - x_usd
        # ── 候选：两个市场今天收盘成立的信号，一起按执行成本排名 ──
        cands = []
        for m in cfg.stock_markets:
            if not self.sess[m][i]:
                continue
            cols = np.flatnonzero(A.entry[i] & A.has[i] & (self.mkt == m))
            cands += [A.tickers[j] for j in cols if A.tickers[j] not in self.core_set]
        n_after = len(st.pos) - len(exit_ts)

        def tier(t: str) -> int:
            if market_of(t) == "JP":
                return 0
            c = float(A.close[i, self.col[t]]) * (1 + self.slip["US"])
            return 1 if usd0 >= c else 2
        if len(st.pos) >= cfg.max_positions:          # 与 engine 相同：持仓已满（含明天要卖的）时不规划新仓
            cands = []
        for t in sorted(cands, key=lambda x: (tier(x), x)):
            if t in st.pos or t in st.pending_exit or t in st.plan:
                continue
            m = market_of(t)
            em = self._entry_mult(t, i)
            if em <= 0:
                self.skipped["macro"] += 1
                continue
            if self.entry_block_fn is not None and self.entry_block_fn(t, i):
                self.skipped["earnings"] += 1
                continue
            if n_after + len(st.plan) >= cfg.max_positions:
                self.skipped["full"] += 1
                continue
            if m == "US" and not post and usd0 + y_usd - used_usd - x_usd <= 0:
                self.skipped["fx_window"] += 1
                continue
            c = float(A.close[i, self.col[t]])
            px = c * (1 + self.slip[m])
            budget_jpy = min(eq * cfg.position_pct * min(1.0, em), eq * cfg.max_position_pct)
            fee = self.fees[m]
            lot = int(self.lots[self.col[t]])
            if m == "JP":
                avail = jpy_avail()
                conv = max(0.0, usd_cash_free()) * rs / mg if pre else 0.0
                budget = min(budget_jpy, (avail + conv) * buf)
                shares = int(math.floor(budget / px / lot) * lot) if budget > 0 else 0
                if shares <= 0:
                    self.skipped["lot" if budget > 0 else "cash"] += 1
                    continue
                cost = shares * px + fee(shares * px)
                if cost > avail and pre:
                    x_usd += (cost - max(0.0, avail)) * mg / rs
                used_jpy += cost
            else:
                avail = usd0 + y_usd - used_usd - x_usd
                conv = max(0.0, jpy_avail()) / rb / mg if post else 0.0
                budget = min(budget_jpy / fx, (max(0.0, avail) + conv) * buf)
                shares = int(math.floor(budget / px / lot) * lot) if budget > 0 else 0
                if shares <= 0:
                    self.skipped["lot" if budget > 0 else "usd"] += 1
                    continue
                cost = shares * px + fee(shares * px)
                if cost > avail:
                    y_usd += (cost - max(0.0, avail)) * mg
                used_usd += cost
            st.plan[t] = [c, shares, str(self.gidx[i].date())]
        # ── 换汇计划：开盘前 美元→日元（日本买入所需 + 不再需要的闲置美元），开盘后 日元→美元（美股买入所需）──
        st.fx_plan = []
        back = x_usd
        if (not cfg.usd_keep and y_usd <= 0 and not any(market_of(t) == "US" for t in st.plan)
                and st.cash_usd - back >= cfg.usd_min_back
                and not (cfg.usd_keep_imminent and self.us_imminent[i])):
            back = max(back, st.cash_usd)                        # 闲置美元全部换回日元（零头留着）
        back = min(back, st.cash_usd)
        if back > 1.0:
            st.fx_plan.append({"dir": "USD>JPY", "usd": math.floor(back * 100) / 100})
        if y_usd > 0:
            st.fx_plan.append({"dir": "JPY>USD", "usd": math.ceil(y_usd * 100) / 100})
        fx_jpy = y_usd * rb
        st.fx_reserve_jpy = fx_jpy
        pre_jpy = back * rs if pre and back > 1.0 else 0.0      # 开盘前换回、开盘时已到账的日元
        # ── 核心 ETF：目标 = 权益 − 个股 − 计划买入 − 换汇预留 − 留作美元的部分，按权重分给各 ETF ──
        self._decide_core(i, eq, exit_ts, used_jpy + fx_jpy, cash_est + pre_jpy, used_usd, fx,
                          usd_stay=st.cash_usd - (back if pre and back > 1.0 else 0.0))

    def _decide_core(self, i: int, eq: float, exit_ts: list, reserve: float, cash_est: float,
                     plan_usd: float, fx: float, usd_stay: float | None = None) -> None:
        """核心 ETF（东证上市、日元）目标额 = 权益 − 继续持有的个股 − 明早的日本买入与换汇预留 − 美元现金
        − 今晚美股卖出的部分（卖出所得是美元，换回日元之前不能买东证 ETF）。按权重分给各 ETF；熊市那份为 0。
        只有一只 ETF、没有美股时，与 core.core_orders 完全相同（引擎差分测试保证）。"""
        st, A, cfg = self.st, self.A, self.cfg
        st.core_plan = {}
        if not cfg.core:
            return
        stock_after = us_exiting = 0.0
        for t, ps in st.pos.items():
            v = ps.shares * self._px_close(t, i) * (fx if ps.market == "US" else 1.0)
            if t in exit_ts:
                us_exiting += v if ps.market == "US" else 0.0
            else:
                stock_after += v
        usd_stay = st.cash_usd if usd_stay is None else max(0.0, usd_stay)
        tgt_total = (eq * (1 - cfg.core_buffer_pct / 100) - stock_after - reserve
                     - usd_stay * fx - us_exiting)
        w = {t: float(v) for t, v in cfg.core.items()}
        bear = {t: bool(self.bear[cfg.core_index.get(t, "JP")][i]) for t in w}
        if cfg.core_mode == "follow":
            bull_w = sum(v for t, v in w.items() if not bear[t])
            share = {t: (v / bull_w if bull_w > 0 and not bear[t] else 0.0) for t, v in w.items()}
        else:
            tot = sum(w.values()) or 1.0
            share = {t: (0.0 if bear[t] else v / tot) for t, v in w.items()}
        band = cfg.band_pct / 100 * eq
        orders = {}
        for t in w:
            j = self.col[t]
            if not A.has[i, j]:
                continue
            price = float(A.close[i, j])
            if price <= 0 or not np.isfinite(price):
                continue
            units, lot = int(st.core_units.get(t, 0)), int(self.lots[j])
            tgt = 0 if bear[t] or share[t] <= 0 else int(np.floor(max(0.0, tgt_total * share[t]) / price / lot)) * lot
            sell = buy = 0
            if tgt < units and (tgt == 0 or (units - tgt) * price > band):
                sell = units - tgt
            elif tgt > units and (tgt - units) * price > band:
                buy = tgt - units
            orders[t] = [sell, buy]
        # 日元缺口（明早日本买入 + 换汇 > 现金 + 日本卖出所得）→ 卖核心补足，按跳空上限多卖
        short = reserve - cash_est
        if short > 0:
            need = short * (1 + self.ex["JP"].max_entry_gap_pct / 100)
            for t in sorted(orders, key=lambda x: -st.core_units.get(x, 0) * float(A.close[i, self.col[x]])):
                units = int(st.core_units.get(t, 0))
                if units <= 0 or need <= 0:
                    orders[t][1] = 0
                    continue
                j = self.col[t]
                price, lot, sl = float(A.close[i, j]), int(self.lots[j]), self.c_slip[t]
                net = (lambda u, p=price * (1 - sl), tt=t: u * p - self.c_fee[tt]["SELL"](u * p))
                u = min(units, int(np.ceil(need / price / lot)) * lot)
                while u < units and net(u) < need:
                    u += lot
                orders[t] = [max(orders[t][0], u), 0]
                need -= net(orders[t][0])
            for t in orders:
                orders[t][1] = 0
        for t, (sell, buy) in orders.items():
            if sell:
                st.core_plan[t] = ["SELL", int(sell)]
            elif buy:
                st.core_plan[t] = ["BUY", int(buy)]

    # ── 分阶段（实盘执行器：开盘的成交来自券商，收盘后的离场判断与决策用同一套代码）──
    def begin_day(self, i: int) -> None:
        """第 i 天开始：清空「今天卖过」、记下核心 ETF 的收盘价。"""
        st, A = self.st, self.A
        self._sold_today = set()
        for t in self.cfg.core:
            j = self.col[t]
            if A.has[i, j]:
                st.core_last[t] = float(A.close[i, j])

    def open_phase(self, i: int) -> None:
        """第 i 天日本开盘（回测撮合）：换汇 → 个股卖 → 核心卖 → 个股买 → 核心买 → 开盘后的换汇。
        实盘执行器不调用它，而是把券商的实际成交记进状态。"""
        st, A = self.st, self.A
        fx_day = bool(st.fx_plan) and (self.cfg.fx_on_jp_holidays or self.sess["JP"][i])
        if fx_day and self.cfg.fx_before_jp_open:
            self._exec_fx(i, only="USD>JPY")                          # 开盘前把闲置美元换回日元
        if self.sess["JP"][i]:
            self._exec_exits("JP", i)
            for t, (side, u) in list(st.core_plan.items()):          # 核心卖出先于个股买入，腾出现金
                if side == "SELL" and A.has[i, self.col[t]]:
                    self._core_trade(t, "SELL", min(int(u), int(st.core_units.get(t, 0))), i)
                    st.core_plan.pop(t)
            self._exec_buys("JP", i)
            for t, (side, u) in list(st.core_plan.items()):          # 核心买入：个股买完后用剩余日元（留出换汇）
                j = self.col[t]
                if side == "BUY" and A.has[i, j]:
                    bpx = A.open[i, j] * (1 + self.c_slip[t])
                    u, lot = int(u), int(self.lots[j])
                    while u > 0 and u * bpx + self.c_fee[t]["BUY"](u * bpx) > st.cash_jpy - st.fx_reserve_jpy:
                        u -= lot
                    self._core_trade(t, "BUY", u, i)
                    st.core_plan.pop(t)
        if st.fx_plan and (self.cfg.fx_on_jp_holidays or self.sess["JP"][i]):
            self._exec_fx(i)                                          # 开盘后：日元→美元（可用早上卖出所得）

    def close_phase(self, i: int) -> None:
        """第 i 天日本收盘之后：日本持仓的离场判断 → 夜间美股（回测撮合）→ 统一决策（明天的单）→ 记账。"""
        st, A = self.st, self.A
        if self.sess["JP"][i]:
            self._check_exits("JP", i)
        if self.sess["US"][i]:
            self._exec_exits("US", i)
            self._exec_buys("US", i)
            self._check_exits("US", i)
        for j in np.flatnonzero(A.has[i]):
            self.last_bar[j] = i
        self._decide(i)
        eq = self.equity(i)
        st.last_date = str(self.gidx[i].date())
        st.history.append([st.last_date, round(eq, 2), round(st.cash_jpy, 2), round(st.cash_usd, 2),
                           round(float(self.fx_close[i]), 4)])

    # ── 推进一天 ──
    def step(self, i: int) -> None:
        self.begin_day(i)
        self.open_phase(i)
        self.close_phase(i)

    def apply_corp_actions(self, i: int, provider, credit_dividends: bool = True, on_action=None) -> list[str]:
        """模拟盘 / 实盘执行器专用（回测的复权价天然正确，不用）：推进第 i 天之前，把 (上一根已处理 K 线, 第 i 天] 之间的除息 / 拆股
        补到持仓、核心 ETF 与计划单上。provider 取不到时只按「记下的真实收盘 vs 今天的复权收盘」兜底识别拆股（分红跳过）。
        credit_dividends=False（实盘）：分红只调整止损 / 峰值，现金以券商实际入账为准（执行器每天与券商核对现金）。
        on_action(票, 日期, 分红, 拆股, 税后比例)：每处理一次就回调一次（执行器用它把同一事件同步给模拟券商）。"""
        from .corpactions import DIV_NET, due, infer_split
        st = self.st
        after, upto = st.last_date, str(self.gidx[i].date())
        if not after or after >= upto:
            return []
        out = []
        names = set(st.pos) | {t for t, u in st.core_units.items() if u} | set(st.plan) | set(st.core_plan)
        for t in sorted(names):
            try:
                acts = due(provider, t, after, upto)
            except Exception as e:                            # noqa: BLE001
                acts = []
                j, ps = self.col.get(t), st.pos.get(t)
                stored = ps.last_close if ps else st.core_last.get(t)
                ia = int(self.gidx.searchsorted(pd.Timestamp(after)))
                if j is not None and stored and ia < len(self.gidx) and str(self.gidx[ia].date()) == after \
                        and self.A.has[ia, j]:
                    k = infer_split(float(stored), float(self.A.close[ia, j]))
                    if k:
                        acts = [{"date": upto, "dividend": 0.0, "split": k}]
                out.append(f"{t} 公司行为数据取不到（{type(e).__name__}）" + (f"，按价格比推断拆股 1:{acts[0]['split']:g}"
                                                                         if acts else "，本次跳过"))
            for a in acts:
                dv, sp = float(a.get("dividend") or 0), float(a.get("split") or 0)
                net = DIV_NET.get(market_of(t), 1.0)
                n = apply_corp_action(st, t, a["date"], dividend=dv, split=sp, div_net=net if credit_dividends else 0.0)
                if n:
                    out.append(f"{t} {a['date']}：{n}")
                    if on_action is not None:
                        on_action(t, a["date"], dv, sp, net)
        return out

    def prime(self, lo: int) -> None:
        """从第 lo 天开始推进之前：每只票在 lo 之前的最后一根 K 线（ATR / 涨跌停判断用）。"""
        for j in range(len(self.A.tickers)):
            prev = np.flatnonzero(self.A.has[:lo, j])
            self.last_bar[j] = int(prev[-1]) if len(prev) else -1

    def run(self, start=None, end=None) -> UnifiedResult:
        lo = 0 if start is None else int(self.gidx.searchsorted(pd.Timestamp(start), side="left"))
        hi = len(self.gidx) if end is None else int(self.gidx.searchsorted(pd.Timestamp(end), side="right"))
        self.prime(lo)
        for i in range(lo, hi):
            self.step(i)
        return self.result(lo, hi)

    def todo(self, i: int) -> dict:
        """当前状态下「下一步要做的事」（模拟盘日报 / 操作清单 / RSS 用）：日本开盘单、换汇、美股开盘单、核心 ETF。
        寄付指値 = 信号日收盘 ×(1+跳空上限)，与回测的跳空过滤是同一条规则。"""
        from .tick import round_to_tick
        st, out = self.st, {"JP": [], "FX": [], "US": []}
        for t, why in st.pending_exit.items():
            if t in st.pos:
                ps = st.pos[t]
                out[ps.market].append({"side": "SELL", "ticker": t, "qty": ps.shares, "type": "寄付成行" if ps.market == "JP"
                                       else "开盘成行", "reason": why})
        for t, (side, u) in st.core_plan.items():
            if side == "SELL":
                out["JP"].insert(0, {"side": "SELL", "ticker": t, "qty": int(u), "type": "寄付成行", "reason": "核心 ETF 调整"})
        for t, (c, sh, d) in st.plan.items():
            m = market_of(t)
            lim = c * (1 + self.ex[m].max_entry_gap_pct / 100)
            lim = round_to_tick(lim, t, "BUY") if m == "JP" else round(lim, 2)
            out[m].append({"side": "BUY", "ticker": t, "qty": int(sh), "type": "寄付指値" if m == "JP" else "开盘指値",
                           "limit": lim, "signal_close": c, "signal_date": d})
        for t, (side, u) in st.core_plan.items():
            if side == "BUY":
                j = self.col.get(t)
                c = float(self.A.close[i, j]) if j is not None and self.A.has[i, j] else float(st.core_last.get(t) or 0)
                lim = round_to_tick(c * 1.02, t, "BUY") if c > 0 else None   # 实盘：成行会按涨停价占用余力 → 用指値
                out["JP"].append({"side": "BUY", "ticker": t, "qty": int(u),
                                  "type": "寄付指値（个股买完后，用剩余日元；卖单成交后再下）", "limit": lim,
                                  "reason": "核心 ETF 调整"})
        for o in st.fx_plan:
            out["FX"].append({"dir": o["dir"], "usd": o["usd"],
                              "jpy_est": round(o["usd"] * (float(self.fx_close[i]) + (self.cfg.fx_spread_yen if o["dir"] == "JPY>USD"
                                                                                       else -self.cfg.fx_spread_yen)))})
        return out

    def result(self, lo: int, hi: int) -> UnifiedResult:
        from .metrics import compute_metrics
        st = self.st
        eq = pd.Series([h[1] for h in st.history[-(hi - lo):]], index=self.gidx[lo:hi], name="equity")
        last = hi - 1
        for t in list(st.pos):                                 # 期末按最后收盘价强平（统计口径）
            ps = st.pos[t]
            self._close(t, ps.last_close, last, "end")
        tdf = pd.DataFrame(st.trades, columns=["ticker", "market", "entry_date", "exit_date", "entry_px", "exit_px",
                                               "shares", "pnl", "pnl_jpy", "ret_pct", "hold_days", "reason"])
        m_df = tdf.assign(pnl=tdf["pnl_jpy"]) if len(tdf) else tdf
        res = UnifiedResult(equity=eq, trades=tdf, state=st, skipped=dict(self.skipped))
        res.metrics = compute_metrics(m_df, eq)
        return res
