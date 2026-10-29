"""us_selection_study.py — 美股选股研究：现在的美股规则在 NASDAQ-100 + Dow 30 里选出来的票跑不跑得赢指数、有没有更好的美股选法
（2026-10-28 登记 = 本提交；之后不改规则、只运行一次）。

用户（2026-10-28）：「选股里面的也要加上美股被选出来的股票，进行美股的选股的研究」。面板「选股」将另外加一张只展示的美股卡片，
用的是现在的美股规则 = var/best_params.json 叠加 var/best_params_US.json（qbreak/trader.load_params(market="US")）→ 本研究的基准 U0。
已经看过的（照实写 —— 这不是没看过的检验）：
  ① market_compare_study（2026-09-29）：日本那套规则（W2 + X6）放在今天的 S&P 500 × 楽天：每笔 E +0.30% / J −0.86%，减同期 S&P500 E +0.21% / J −1.79%；
     去掉楽天费用（US-0）每笔 E +1.29% / J +0.13%；美股以前的参数（US-P = 本研究的 U0 规则，但股票池是 S&P 500）每笔 E +1.14% / J +0.50%，
     减同期指数 E −0.08% / J −1.51%，个股层 Calmar E 0.123 / J 0.130；读法「日経（立花）更好」。
  ② unified_study（2026-09-25）：美股突破每笔期望约 +0.4%，楽天来回约 0.99% 的手续费把它吃掉；H1（hx_select_study）S&P 500 1995〜2026 每笔 +0.37%。
  ③ 本研究新的部分：股票池换成面板实际用的 qbreak/universes.us_broad()（NASDAQ-100 + Dow 30，今天的名单）、基准指数换成 ^NDX、
     加上相对强度过滤（U2）与经典的横截面动量（U3），以及 U0 进场信号的前向质量表。登记前只数了票与 K 线根数（见文末），没跑任何回测、没算收益。

一 股票池：qbreak/universes.us_broad()（今天的名单，去掉中国背景；双重股份只留一只：GOOG → 只留 GOOGL），取得到 ≥ 300 根 K 线的票。
   **幸存者偏差很大**：今天的 NASDAQ-100 成员大多是过去 20 年涨得最多的（被剔除 / 倒闭 / 被收购的不在里面），而 ^NDX 当时的成员不是这批 →
   「减指数的超额」偏乐观；另报「股票池等权」（每天等权平均今天的成员、有行情就算，同样带偏差）作为对照：跑不赢等权 = 选股没有加分。
   没有成员时点过滤（没有 NDX 加入日期的数据），所有票有行情就能开新仓。
二 规则（四个，各跑一次；4 个名额 × 每只 25%、单只 ≤ 34%；T 日收盘决定 → T+1 开盘成交）：
   U0 现在的美股规则：best_params + best_params_US（不看死叉、+3% 之后 10% 跟踪止损；止损 7% / 止盈 25% / 放量阴线 / 最长 60 天；没有 W2）。基准。
   U1 日本那套规则用在美股：best_params + best_params_JP（W2 周线量比 ≥ 1.0、派发日 ≤ 6、上影线比 ≤ 3）+ 离场 X6（qbreak/exit_rules，日本模拟盘用的）。
   U2 U0 + 相对强度：只在这只票最近 63 个交易日的收益 ≥ ^NDX 同期收益时进场（StrategyParams rs_n = 63、min_rs_pct = 0，compute_indicators 的 index_close = ^NDX）。
   U3 横截面动量（没有突破条件）：每月最后一个美股交易日按 12−1 月收益（收盘[t−21] ÷ 收盘[t−252] − 1；要有 ≥ 253 根 K 线）排名，
      取一股价格 ≤ 当时权益 25% 的前 4 名；第二天开盘卖掉掉出前 4 的、用卖得的现金（加剩余现金）等分买新进的（每只 ≤ 权益 25%），
      留下的不调仓位；整数股。现金一直是美元（只在开始时换一次汇）→ 日元权益 = 美元权益 × USD/JPY 收盘。
   U0〜U2 用研究框架的引擎（scripts/jq_study.RealLotEngine ⊂ qbreak/unified.UnifiedEngine，同 market_compare_study.run_arm）：账户 ¥1,000,000、
   stock_markets = ("US",)、没有核心 ETF（没有个股时拿日元现金）、美股 T 日收盘决定 → 日本白天换汇 → 当晚美股开盘成交、usd_keep_imminent = True、
   一股起买；新仓倍数 = 1（不加宏观 / 板块 / 量化状态层：只比选股）；候选多于名额时按引擎原来的顺序（同 market_compare）。
三 成本：(a) 楽天：约定 0.495%、上限 22 美元（qbreak/fees.py 的 rakuten US）、滑点单边 0.05%、换汇 片道 3 銭（リアルタイム為替，UnifiedConfig 默认）；
   (a25) 同 (a) 但换汇 片道 25 銭（定時為替 / 円貨決済；只描述）；(b) 手续费 0、换汇 0（滑点照旧；只描述）。U3 同样的费率（换汇只在开始一次）。
四 年代：Z 2001-01-04〜2006-09-30、E 2006-10-01〜2016-09-30、J 2017-01-04〜最新（与近来的研究同一口径）；从 2001-01-04 连续回测一次，按年代切；每笔按买入日归年代。
五 看什么：① 每笔：笔数、胜率、每笔净收益（美元口径，扣手续费与滑点）均值 / 中位、减同期 ^NDX（买入前一天收盘 → 卖出日收盘）、减同期股票池等权、持有天数；
   每笔减 ^NDX 的均值的 95% 区间（按买入月聚类自助法 2,000 次）；
   ② 只有个股层的账户（日元）：年化、最大回撤、Calmar、名额使用、每年手续费 + 换汇（日元）、每年成交额 ÷ 平均权益（换手）；
   ③ 基准（日元、不扣成本）：^NDX、^GSPC 买入持有、股票池等权；
   ④ U0 进场信号的前向质量（只描述）：U0 的 entry 信号（同一只票前 20 个交易日内已有信号的不算），T+1 开盘 → T+20 / T+60 收盘的收益（不扣成本），
      减 ^NDX 同期（T+1 开盘 → T+h 收盘），按年代：个数、均值、中位数、跑赢比例、均值的 95% 区间（按信号月聚类自助法 2,000 次）。
六 读法（事先写定）：
   - U0：E、J 两个年代 (a) 的每笔减 ^NDX 均值都 > 0，而且至少一个年代的 95% 区间下限 > 0 →「U0 有用（选出来的票跑赢指数）」；
     E、J 都 < 0 而且至少一个年代的 95% 区间上限 < 0 →「U0 跑输指数」；其余 →「看不出 U0 比指数好」。
   - U1 / U2 / U3：(a) 的个股层 Calmar 在 Z、E、J 每个年代都比 U0 高 ≥ +0.03 →「比 U0 更好」；每个年代都低 ≥ 0.03 →「比 U0 差」；其余 →「看不出更好」。
     注意 U3 一直满仓，U0〜U2 大部分时间拿现金：Calmar 比较的是「这样做整个个股层」，不是同样风险下的选股能力 → 另看每笔超额与等权对照。
   - (a25)、(b)、等权对照、前向质量表只描述，不参与读法。
   不管结果如何：模拟盘 / 执行器 / sim.json / 参数 / 股票池都不变；不会自动交易美股（立花 ｅ支店不做美股；楽天的美股不能由程序自动下单，
   CLAUDE.md 也不允许自动操作楽天网站 / iSPEED）；面板的美股卡片只展示，用不用、怎么用由用户决定。
七 事前预期（看结果之前）：①② 已知美股突破被楽天费用吃掉、S&P 500 上 U0 规则每笔减指数为负 → 「U0 有用」约 15%、「跑输指数」约 25%、「看不出」约 60%；
   U1 更好约 10%（W2 在美国几乎没区别，X6 在 S&P 500 每笔不如 U0 规则）；U2 更好约 20%；U3 更好约 50%
   （一直满仓、股票池是今天的赢家 → 幸存者偏差最有利于 U3；这正是要看等权对照的原因）。
八 局限：幸存者偏差（一）；Z 年代有行情的票少（2001 年有行情的约 78 只，2006 年约 89 只）；Yahoo 调整后价格（含分红再投资，税前，美股分红的外国税不算）；
   日元账户收益含汇率；U3 现金留美元、U0〜U2 卖出后换回日元，口径不同（写明）；名额 4 只（模拟盘 2026-10-24 起不设上限，这里按用户给的 4 × 25%）。
登记前的检查（只数了票与 K 线，没算收益）：us_broad() 125 只，WBD 取不到行情 → 124 只（去掉 GOOG 后 123 只）；2001-01 已有行情 78 只、2006-10 已有 89 只；^NDX 1991 起；
  另用 6 只票、2025-06 起的小样本盲跑一次只确认程序能跑通（输出写到临时目录、没看任何数字）。
运行：python scripts/us_selection_study.py --run（只运行一次；输出已存在就拒绝）→ var/out/us_selection_study.md / .json（只有统计）。非投资建议。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qbreak import paths                                                     # noqa: E402

OUT = "us_selection_study"
START = "2001-01-04"
WIN = {"Z": ("2001-01-04", "2006-09-30"), "E": ("2006-10-01", "2016-09-30"), "J": ("2017-01-04", None)}
ERAS = ("Z", "E", "J")
U0_ERAS = ("E", "J")
SLOTS = 4
POS_PCT = 0.25
CAPITAL = 1_000_000.0
BOOT, SEED = 2000, 20261028
BETTER = 0.03
RS_N, RS_MIN = 63, 0.0
MOM_LONG, MOM_SKIP, MOM_MIN_BARS = 252, 21, 253
DEDUP = 20
HORIZONS = (20, 60)
FX = {"a": 0.03, "a25": 0.25, "b": 0.0}
VARIANTS = ("U0", "U1", "U2", "U3")
LABEL = {"U0": "现在的美股规则（best_params + US）", "U1": "日本那套规则（+ JP 过滤 + X6）",
         "U2": "U0 + 相对强度（63 日 ≥ ^NDX）", "U3": "横截面动量 12−1 月、前 4、每月"}
DROP = {"GOOG"}                                                              # 双重股份只留 GOOGL


# ───────────────────────── 纯函数（tests/test_us_selection_study.py） ─────────────────────────
def month_ends(days: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """每个月最后一个交易日。"""
    s = pd.Series(days, index=days)
    return pd.DatetimeIndex(s.groupby(days.to_period("M")).max().values)


def mom_score(close: pd.DataFrame, d: pd.Timestamp) -> pd.Series:
    """d 那天的 12−1 月动量：close[t−21] / close[t−252] − 1（按每只票自己的 K 线数；不够 253 根或 d 没有收盘 → 不排）。"""
    out = {}
    for t in close.columns:
        s = close[t].loc[:d].dropna()
        if len(s) < MOM_MIN_BARS or s.index[-1] != d:
            continue
        a, b = float(s.iloc[-1 - MOM_SKIP]), float(s.iloc[-1 - MOM_LONG])
        if a > 0 and b > 0:
            out[t] = a / b - 1
    return pd.Series(out, dtype=float).sort_values(ascending=False)


def rakuten_fee(notional: float, pct: float, cap: float) -> float:
    return min(abs(notional) * pct / 100, cap) if cap else abs(notional) * pct / 100


def dedup_signals(flag: np.ndarray, gap: int = DEDUP) -> np.ndarray:
    """同一只票：前 gap 个交易日内已有信号的不算（只看原始信号，不看被去掉的）。"""
    f = np.asarray(flag, bool)
    out = np.zeros(len(f), bool)
    last = -10 ** 9
    for i in np.flatnonzero(f):
        if i - last > gap:
            out[i] = True
        last = i
    return out


def boot_mean(x: pd.Series, groups: pd.Series, reps: int = BOOT, seed: int = SEED) -> tuple[float | None, float | None]:
    """均值的 95% 区间：按组（月）聚类重抽。"""
    x = pd.Series(np.asarray(x, float))
    if len(x) < 2:
        return None, None
    g = [v.to_numpy(float) for _, v in x.groupby(np.asarray(groups))]
    rng = np.random.default_rng(seed)
    m = [np.concatenate([g[k] for k in rng.integers(0, len(g), len(g))]).mean() for _ in range(reps)]
    return round(float(np.percentile(m, 2.5)), 3), round(float(np.percentile(m, 97.5)), 3)


def read_u0(stats: dict) -> str:
    """六：U0 每笔减 ^NDX（成本 a）。stats = {era: {"excess": 均值, "ci": (lo, hi)}}。"""
    ex = [stats[e].get("excess") for e in U0_ERAS]
    ci = [stats[e].get("ci") or (None, None) for e in U0_ERAS]
    if any(v is None for v in ex):
        return "没有值"
    if all(v > 0 for v in ex) and any(c[0] is not None and c[0] > 0 for c in ci):
        return "U0 有用（选出来的票跑赢指数）"
    if all(v < 0 for v in ex) and any(c[1] is not None and c[1] < 0 for c in ci):
        return "U0 跑输指数"
    return "看不出 U0 比指数好"


def read_variant(cal: dict, cal0: dict) -> str:
    """六：每个年代 Calmar 差（成本 a）都 ≥ +0.03 → 更好；都 ≤ −0.03 → 差；其余看不出。"""
    d = [None if cal.get(e) is None or cal0.get(e) is None else cal[e] - cal0[e] for e in ERAS]
    if any(v is None for v in d):
        return "没有值"
    if all(v >= BETTER - 1e-12 for v in d):
        return "比 U0 更好"
    if all(v <= -BETTER + 1e-12 for v in d):
        return "比 U0 差"
    return "看不出更好"


# ───────────────────────── U3：动量账户 ─────────────────────────
def run_momentum(close: pd.DataFrame, opn: pd.DataFrame, fx_close: pd.Series, start: str, comm_pct: float, comm_max: float,
                 slip_pct: float, fx_spread: float) -> tuple[pd.Series, pd.DataFrame, float]:
    """→ (日元权益, 每笔, 总成交额 USD)。美元现金；开始时 ¥CAPITAL 按 USD/JPY 收盘 + 点差换成美元。"""
    days = close.index[close.index >= pd.Timestamp(start)]
    fxs = fx_close.reindex(close.index.union(fx_close.index)).ffill().reindex(close.index)
    rate0 = float(fxs.loc[days[0]])
    cash = CAPITAL / (rate0 + fx_spread)
    hold: dict[str, dict] = {}
    trades, turnover = [], 0.0
    me = set(month_ends(close.index))
    pending: list[str] | None = None
    eq = []
    slip = slip_pct / 100
    for i, d in enumerate(days):
        if pending is not None:                                              # 开盘执行上个交易日（月末）的决定
            for t in [t for t in hold if t not in pending]:
                o = opn.at[d, t] if t in opn.columns else np.nan
                if not np.isfinite(o) or o <= 0:
                    continue                                                 # 今天没有开盘价 → 留着，下个月再看
                h = hold.pop(t)
                px = float(o) * (1 - slip)
                val = px * h["sh"]
                fee = rakuten_fee(val, comm_pct, comm_max)
                cash += val - fee
                turnover += val
                trades.append(dict(ticker=t, market="US", entry_date=h["d"], exit_date=d, entry_px=h["px"], exit_px=px, shares=h["sh"],
                                   pnl=(px - h["px"]) * h["sh"] - fee - h["fee"], hold_days=i - h["i"], reason="rebalance"))
            new = [t for t in pending if t not in hold]
            px_now = {t: float(opn.at[d, t]) for t in new if np.isfinite(opn.at[d, t]) and opn.at[d, t] > 0}
            equity = cash + sum(h["sh"] * float(close[t].loc[:d].dropna().iloc[-1]) for t, h in hold.items())
            left = [t for t in new if t in px_now]
            for k, t in enumerate(left):
                budget = min(cash / (len(left) - k), equity * POS_PCT)
                px = px_now[t] * (1 + slip)
                sh = int(budget / (px * (1 + comm_pct / 100)))
                if sh <= 0:
                    continue
                val = px * sh
                fee = rakuten_fee(val, comm_pct, comm_max)
                cash -= val + fee
                turnover += val
                hold[t] = {"sh": sh, "px": px, "fee": fee, "d": d, "i": i}
            pending = None
        if d in me:
            equity = cash + sum(h["sh"] * float(close[t].loc[:d].dropna().iloc[-1]) for t, h in hold.items())
            sc = mom_score(close, d)
            pick = [t for t in sc.index if float(close.at[d, t]) <= equity * POS_PCT][:SLOTS]
            pending = pick
        mv = sum(h["sh"] * float(close[t].loc[:d].dropna().iloc[-1]) for t, h in hold.items())
        eq.append((cash + mv) * float(fxs.loc[d]))
    for t, h in hold.items():
        trades.append(dict(ticker=t, market="US", entry_date=h["d"], exit_date=days[-1], entry_px=h["px"],
                           exit_px=float(close[t].dropna().iloc[-1]), shares=h["sh"], pnl=0.0, hold_days=len(days) - 1 - h["i"], reason="end"))
    return pd.Series(eq, index=days), pd.DataFrame(trades), turnover


# ───────────────────────── 数据 ─────────────────────────
def load_all() -> dict:
    import equity_idle_study as EQ
    import us_stock_data as UD
    from bullbear_study import load
    from qbreak import factors
    from qbreak.universes import us_broad
    names = [t for t in us_broad() if t not in DROP]
    data = UD.ohlcv(names + ["^NDX", "^GSPC"])
    stocks = {t: data[t] for t in names if t in data and len(data[t]) >= 300}
    fxdf = load("JPY=X", "2000-01-01")
    fxdf = fxdf[(fxdf["Close"] > 60) & (fxdf["Close"] < 250)].copy()
    dex = factors.fred("DEXJPUS").dropna()
    _, fixed = EQ.clean_fx(fxdf["Close"], dex)
    for d in fixed:
        fxdf.loc[pd.Timestamp(d), ["Open", "Close"]] = float(dex.loc[pd.Timestamp(d)])
    fr, _cl = EQ.assets(EQ.load_inputs())
    return {"names": names, "stocks": stocks, "ndx": data["^NDX"], "spx": data["^GSPC"], "fx": fxdf[["Open", "Close"]],
            "fx_fixed": fixed, "jp_days": fr["1545.T"]}


def run_engine(ind: dict, p, ex, fx: pd.DataFrame, jp_days: pd.DataFrame, fx_spread: float):
    import jq_study as JS
    from qbreak.unified import UnifiedConfig
    use = dict(ind)
    use["1545.T"] = jp_days                                                  # 只为了有东证的日子（换汇在日本白天）；不是核心、不交易
    cfg = UnifiedConfig(capital_jpy=CAPITAL, position_pct=POS_PCT, max_positions=SLOTS, max_position_pct=0.34, stock_markets=("US",),
                        core={}, core_index={}, core_mode="split", fx_spread_yen=fx_spread, usd_keep_imminent=True)
    JS.RealLotEngine.RATIO, JS.RealLotEngine.LAST = {}, []
    e = JS.RealLotEngine(use, cfg, {"JP": p, "US": p}, {"JP": ex, "US": ex}, {}, fx=fx)
    r = e.run(start=START)
    return r, dict(e.skipped)


def ew_index(stocks: dict) -> pd.Series:
    """股票池等权（每天等权平均有收盘的票的日收益；美元，不扣成本）。"""
    C = pd.DataFrame({t: df["Close"] for t, df in stocks.items()}).sort_index()
    r = C.pct_change(fill_method=None)
    return (1 + r.mean(axis=1, skipna=True).fillna(0.0)).cumprod()


def per_trade(trades: pd.DataFrame, ndx: pd.Series, ew: pd.Series, fx_close: pd.Series) -> pd.DataFrame:
    import market_compare_study as MC
    T = MC.trade_table(trades, "US", ndx, fx_close)
    if not len(T):
        return T
    i0 = MC._asof(ew.dropna().sort_index(), T["entry_date"], strict=True)
    i1 = MC._asof(ew.dropna().sort_index(), T["exit_date"], strict=False)
    T["ew"] = (i1 / i0 - 1) * 100
    T["excess_ew"] = T["net"] - T["ew"]
    return T


def window(T: pd.DataFrame, a: str, b: str | None) -> pd.DataFrame:
    if not len(T):
        return T
    m = T["entry_date"] >= pd.Timestamp(a)
    if b:
        m &= T["entry_date"] <= pd.Timestamp(b)
    return T[m]


def trade_stats(T: pd.DataFrame) -> dict:
    if not len(T):
        return {"n": 0}
    lo, hi = boot_mean(T["excess"], T["entry_date"].dt.to_period("M").astype(str))
    return {"n": int(len(T)), "win": round(float(T["win"].mean() * 100), 1), "mean": round(float(T["net"].mean()), 3),
            "median": round(float(T["net"].median()), 3), "excess": round(float(T["excess"].mean()), 3), "ci": (lo, hi),
            "excess_ew": round(float(T["excess_ew"].mean()), 3), "hold": round(float(T["hold_days"].astype(float).mean()), 1)}


def acct_stats(eq: pd.Series, T: pd.DataFrame, a: str, b: str | None, fx_cost: float, turnover_jpy: float, days: pd.DatetimeIndex) -> dict:
    import capital_study as CS
    import market_compare_study as MC
    bb = None if b is None else str((pd.Timestamp(b) + pd.Timedelta(days=1)).date())
    s = CS.seg_stats(eq, a, bb)
    e = eq.dropna()
    e = e[(e.index >= pd.Timestamp(a)) & ((e.index <= pd.Timestamp(b)) if b else True)]
    yrs = max((e.index[-1] - e.index[0]).days / 365.25, 1e-9) if len(e) else None
    MC.SLOTS = SLOTS
    s.update({"slots": MC.avg_positions(T, days, a, b) if len(T) else 0.0,
              "fee_yr": round(float(T["fee_jpy"].sum()) / yrs, 0) if yrs and len(T) else 0.0,
              "fx_yr": round(fx_cost / yrs, 0) if yrs else 0.0,
              "turn": round(turnover_jpy / yrs / float(e.mean()) * 100, 0) if yrs and len(e) else None})
    return s


def engine_turnover(trades: pd.DataFrame, fx_close: pd.Series, a: str, b: str | None) -> float:
    """窗口内（按成交日）买卖成交额合计（日元）。"""
    import market_compare_study as MC
    t = trades[trades["market"] == "US"]
    out = 0.0
    for col_d, col_p in (("entry_date", "entry_px"), ("exit_date", "exit_px")):
        tt = t if col_d == "entry_date" else t[t["reason"] != "end"]
        d = pd.to_datetime(tt[col_d])
        m = (d >= pd.Timestamp(a)) & ((d <= pd.Timestamp(b)) if b else True)
        rate = MC._asof(fx_close.dropna().sort_index(), d[m], strict=False)
        out += float(np.nansum(tt.loc[m, col_p].astype(float).to_numpy() * tt.loc[m, "shares"].astype(float).to_numpy() * rate))
    return out


def fx_cost(fx_trades, spread: float, a: str, b: str | None) -> float:
    return float(sum(abs(float(u)) * spread for d, _dir, u, _r in (fx_trades or [])
                     if pd.Timestamp(d) >= pd.Timestamp(a) and (b is None or pd.Timestamp(d) <= pd.Timestamp(b))))


def bench_stats(close_usd: pd.Series, fx_close: pd.Series) -> dict:
    import capital_study as CS
    c = close_usd.dropna()
    fxs = fx_close.reindex(c.index.union(fx_close.index)).ffill().reindex(c.index)
    eq = (c * fxs).dropna()
    out = {}
    for w, (a, b) in WIN.items():
        bb = None if b is None else str((pd.Timestamp(b) + pd.Timedelta(days=1)).date())
        out[w] = CS.seg_stats(eq, a, bb)
    return out


def signal_quality(ind: dict, ndx: pd.DataFrame) -> dict:
    """四④：U0 的进场信号（去重）T+1 开盘 → T+h 收盘，减 ^NDX 同期；按年代。"""
    no, nc = ndx["Open"], ndx["Close"]
    rows = []
    for t, df in ind.items():
        f = dedup_signals(df["entry"].to_numpy(bool))
        o, c = df["Open"].to_numpy(float), df["Close"].to_numpy(float)
        idx = df.index
        for i in np.flatnonzero(f):
            if i + 1 >= len(df):
                continue
            r = {"date": idx[i]}
            for h in HORIZONS:
                if i + h < len(df) and o[i + 1] > 0:
                    d1, dh = idx[i + 1], idx[i + h]
                    io, ic = no.get(d1, np.nan), nc.get(dh, np.nan)
                    r[f"r{h}"] = (c[i + h] / o[i + 1] - 1) * 100
                    r[f"x{h}"] = r[f"r{h}"] - ((ic / io - 1) * 100 if np.isfinite(io) and np.isfinite(ic) and io > 0 else np.nan)
            rows.append(r)
    S = pd.DataFrame(rows)
    out = {}
    for w, (a, b) in WIN.items():
        m = S["date"] >= pd.Timestamp(a)
        if b:
            m &= S["date"] <= pd.Timestamp(b)
        Sw = S[m]
        out[w] = {}
        for h in HORIZONS:
            x = Sw[f"x{h}"].dropna() if f"x{h}" in Sw else pd.Series(dtype=float)
            if not len(x):
                out[w][h] = {"n": 0}
                continue
            g = Sw.loc[x.index, "date"].dt.to_period("M").astype(str)
            out[w][h] = {"n": int(len(x)), "raw": round(float(Sw.loc[x.index, f"r{h}"].mean()), 3), "mean": round(float(x.mean()), 3),
                         "median": round(float(x.median()), 3), "beat": round(float((x > 0).mean() * 100), 1), "ci": boot_mean(x, g)}
    return out


# ───────────────────────── 运行 ─────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    out = paths.out_dir()
    if not a.run:
        print("登记的研究：加 --run 才运行（只运行一次）")
        return 0
    if (out / f"{OUT}.json").exists():
        print(f"{OUT}.json 已存在：只运行一次，拒绝重跑")
        return 1
    from qbreak import exit_rules as EXR
    from qbreak.config import ExecConfig
    from qbreak.strategy import compute_indicators
    from qbreak.trader import load_params
    t0 = time.time()
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          cwd=str(Path(__file__).resolve().parent)).stdout.strip()
    L = load_all()
    ndx_c = L["ndx"]["Close"]
    fxc = L["fx"]["Close"]
    p0 = load_params(market="US")
    p1 = EXR.apply(load_params(market="JP"), "X6")
    p2 = replace(p0, rs_n=RS_N, min_rs_pct=RS_MIN)
    P = {"U0": p0, "U1": p1, "U2": p2}
    ind = {k: {t: compute_indicators(df, p, index_close=ndx_c if k == "U2" else None) for t, df in L["stocks"].items()} for k, p in P.items()}
    n_bars = {"n": len(L["stocks"]), "have_2001": sum(1 for df in L["stocks"].values() if df.index[0] <= pd.Timestamp("2001-01-31")),
              "have_2006": sum(1 for df in L["stocks"].values() if df.index[0] <= pd.Timestamp("2006-10-31"))}
    print(f"数据与指标（{time.time() - t0:.0f}s）：{n_bars}", flush=True)
    ex = ExecConfig.for_market("US", "rakuten")
    exs = {"a": ex, "a25": ex, "b": replace(ex, commission_pct=0.0, commission_max=0.0)}
    ew = ew_index(L["stocks"])
    days = L["ndx"].index
    res: dict = {}
    skipped: dict = {}
    for k in ("U0", "U1", "U2"):
        for c in ("a", "a25", "b"):
            r, sk = run_engine(ind[k], P[k], exs[c], L["fx"], L["jp_days"], FX[c])
            T = per_trade(r.trades, ndx_c, ew, fxc)
            res[(k, c)] = {}
            for w, (wa, wb) in WIN.items():
                Tw = window(T, wa, wb)
                res[(k, c)][w] = {"trades": trade_stats(Tw),
                                  "acct": acct_stats(r.equity, Tw, wa, wb, fx_cost(getattr(r.state, "fx_trades", []), FX[c], wa, wb),
                                                     engine_turnover(r.trades, fxc, wa, wb), days)}
            if c == "a":
                skipped[k] = sk
            print(f"  {k}/{c} 完成（{time.time() - t0:.0f}s）", flush=True)
    C = pd.DataFrame({t: df["Close"] for t, df in L["stocks"].items()}).sort_index()
    O = pd.DataFrame({t: df["Open"] for t, df in L["stocks"].items()}).reindex(C.index)
    for c in ("a", "a25", "b"):
        cp, cm = (0.0, 0.0) if c == "b" else (ex.commission_pct, ex.commission_max)
        eq, tr, turn_usd = run_momentum(C, O, fxc, START, cp, cm, ex.slippage_pct, FX[c])
        T = per_trade(tr, ndx_c, ew, fxc)
        res[("U3", c)] = {}
        for w, (wa, wb) in WIN.items():
            Tw = window(T, wa, wb)
            res[("U3", c)][w] = {"trades": trade_stats(Tw),
                                 "acct": acct_stats(eq, Tw, wa, wb, (FX[c] * CAPITAL / float(fxc.dropna().iloc[0]) if w == "Z" else 0.0),
                                                    engine_turnover(tr, fxc, wa, wb) if len(tr) else 0.0, days)}
        print(f"  U3/{c} 完成（{time.time() - t0:.0f}s）", flush=True)
    bench = {"^NDX": bench_stats(ndx_c, fxc), "^GSPC": bench_stats(L["spx"]["Close"], fxc), "等权": bench_stats(ew, fxc)}
    sq = signal_quality(ind["U0"], L["ndx"])
    u0 = {w: {"excess": res[("U0", "a")][w]["trades"].get("excess"), "ci": res[("U0", "a")][w]["trades"].get("ci")} for w in ERAS}
    reading = {"U0": read_u0(u0)}
    cal0 = {w: res[("U0", "a")][w]["acct"].get("calmar") for w in ERAS}
    for k in ("U1", "U2", "U3"):
        reading[k] = read_variant({w: res[(k, "a")][w]["acct"].get("calmar") for w in ERAS}, cal0)
    write_report(res, bench, sq, reading, skipped, n_bars, L["fx_fixed"], head, round(time.time() - t0))
    print(f"完成（{time.time() - t0:.0f}s）", flush=True)
    return 0


def _f(v, f="{:.2f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


def _ci(c) -> str:
    if not c or c[0] is None:
        return "—"
    return f"{c[0]:+.2f}〜{c[1]:+.2f}"


def write_report(res, bench, sq, reading, skipped, n_bars, fx_fixed, head, secs) -> None:
    L = [f"# 美股选股研究（2026-10-28 登记，只运行一次；规则见 scripts/{OUT}.py 开头；运行时 HEAD {head}）", "",
         "**按登记的读法**：" + "；".join(f"{k} {v}" for k, v in reading.items()), "",
         f"股票池：us_broad() 今天的名单（去掉 GOOG）有 ≥ 300 根 K 线的 {n_bars['n']} 只；2001-01 已有行情 {n_bars['have_2001']} 只、2006-10 已有 {n_bars['have_2006']} 只。"
         "**幸存者偏差大**（今天的成员）→ 减 ^NDX 的超额偏乐观，另看「减等权」。", ""]
    for w, (a, b) in WIN.items():
        end = b or "最新"
        L += [f"## {w}：{a}〜{end}", "",
              "| 规则 / 成本 | 笔数 | 胜率 | 每笔净收益 均值 / 中位 | 每笔 − ^NDX（95% 区间） | 每笔 − 等权 | 持有天数 | 个股层 年化 / 最大回撤 / Calmar | 名额使用 | 每年手续费 + 换汇 | 换手 / 年 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for k in VARIANTS:
            for c in ("a", "a25", "b"):
                x = res[(k, c)][w]
                t, ac = x["trades"], x["acct"]
                L.append(f"| {k} {LABEL[k]} / {c} | {t.get('n', 0)} | {_f(t.get('win'), '{:.1f}')}% | {_f(t.get('mean'), '{:+.2f}')}% / "
                         f"{_f(t.get('median'), '{:+.2f}')}% | {_f(t.get('excess'), '{:+.2f}')}%（{_ci(t.get('ci'))}） | {_f(t.get('excess_ew'), '{:+.2f}')}% | "
                         f"{_f(t.get('hold'), '{:.1f}')} | {_f(ac.get('cagr'), '{:+.2f}')}% / {_f(ac.get('dd'))}% / {_f(ac.get('calmar'), '{:.3f}')} | "
                         f"{_f(ac.get('slots'), '{:.0f}')}% | ¥{_f(ac.get('fee_yr'), '{:,.0f}')} + ¥{_f(ac.get('fx_yr'), '{:,.0f}')} | {_f(ac.get('turn'), '{:.0f}')}% |")
        L += ["", "基准（日元、不扣成本、一直满仓）：" + "；".join(
            f"{k} {_f(v[w].get('cagr'), '{:+.2f}')}% / {_f(v[w].get('dd'))}% / {_f(v[w].get('calmar'), '{:.3f}')}" for k, v in bench.items()), ""]
        L += ["U0 进场信号的前向质量（去重、不扣成本；减 ^NDX 同期；只描述）：" + "；".join(
            f"{h} 日 {q.get('n', 0)} 个、原始 {_f(q.get('raw'), '{:+.2f}')}%、超额 均值 {_f(q.get('mean'), '{:+.2f}')}%（{_ci(q.get('ci'))}）/ 中位 "
            f"{_f(q.get('median'), '{:+.2f}')}%、跑赢 {_f(q.get('beat'), '{:.1f}')}%" for h, q in sq[w].items()), ""]
    L += ["成本：a = 楽天 0.495%（上限 22 美元）+ 滑点 0.05% + 换汇 片道 3 銭；a25 = 换汇 25 銭（只描述）；b = 手续费 0、换汇 0（只描述）。",
          "U0〜U2 没有个股时拿日元现金；U3 一直满仓、现金留美元。Calmar 比较的是整个个股层，不是同样风险下的选股能力。",
          "引擎跳过的信号（成本 a）：" + "；".join(f"{k} " + "、".join(f"{kk} {vv}" for kk, vv in v.items() if vv) for k, v in skipped.items()),
          "USD/JPY 换成 FRED 的错价：" + ("、".join(fx_fixed) or "没有") + f"；用时 {secs} s。", "",
          "不管结果如何：模拟盘 / 执行器 / sim.json / 参数 / 股票池都不变；不自动交易美股（立花不做美股，楽天美股不能程序下单）；"
          "面板的美股卡片只展示，用不用由用户决定。税前、调整后价格。非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / OUT
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    clean = {f"{k}/{c}": v for (k, c), v in res.items()}
    Path(f"{fp}.json").write_text(json.dumps({"reading": reading, "head": head, "results": clean, "bench": bench, "signal_quality": sq,
                                              "skipped": skipped, "n_bars": n_bars, "fx_fixed": fx_fixed},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
