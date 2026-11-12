"""market_compare_study.py — 现在的选股方法放在「楽天的美股」和「立花的日経225」哪边表现更好
（2026-09-29 登记；先提交后只跑一次，看完不改规则）。

用户（2026-09-29）：「现在进行的所有研究，选股方法等等来看在乐天的美股里面表现好还是在立花的日经里面表现更好」。
已经知道的（照实写 —— 这次不是没看过的检验）：
  ① unified_study（2026-09-25，旧规则：死叉离场、没有 W2）：日本 + 美股个股一起排名，在楽天费用下 20 年年化少 2.0〜3.4 pp；
     美股突破每笔期望约 +0.4%，楽天来回 0.99% 的手续费把它吃掉。
  ② H1（hx_select_study，2026-09-27，旧离场）：S&P 500（没用过的 398 只）1995〜2026 突破 1,708 笔，胜率 43.7%、每笔 +0.37%（只扣来回 0.15%）；
     1995〜2010 +0.85%、2011〜2026 +0.12%；W2 在美国几乎没有区别。
  ③ X6 离场（模拟盘 2026-09-30 起）在日本把每笔从约 +0.6% 提到 +1.35〜2.10%；在美国没测过 —— 这是这次真正新的部分。
一 规则（两边同一套 = 模拟盘 2026-09-30 起的个股规则）：var/best_params.json + best_params_JP.json（W2 周线量比 ≥ 1.0、派发日 ≤ 6、
  上影线比 ≤ 3）+ 离场 X6（收盘 < 持有以来最高价 − 3 × ATR14 代替死叉；止损 7% / 跟踪 12% / 止盈 25% / 放量阴线 / 最长 60 天照旧）；
  4 个名额 × 25%、单只 ≤ 34%；新仓倍数 = 各自市场的量化状态层（自己的指数）× 宏观层 × 板块倾斜（与 unified_study 同一个函数，各算各的）；
  前向记录判断层没有历史，不在里面。资金 ¥1,000,000；没有个股时拿日元现金（主比较 = 只比选股这一层）。引擎 = 研究框架的同一个推进器
  （jq_study.RealLotEngine ⊂ qbreak/unified.UnifiedEngine：日本 T 日收盘决定 → T+1 开盘成交；美股 T 日收盘决定 → 日本白天换汇 → 当晚美股开盘成交）。
二 两边：
  JP-T 日経225 × 立花 ｅ支店 個別コース（按约定金额分档，滑点 0.10%），一手 100 股（2016-09 以后有 J-Quants 真实股价的票按真实价算一手）；
    成员 = 近似时点（qbreak/n225_history：今天的成员 + 2001 年以后剔除、还上市的旧成员，只在当年是成员时开新仓）。
  US-R 今天的 S&P 500（var/us_constituents_2026-09.json，500 只）× 楽天（约定 0.495%、上限 22 美元、滑点 0.05%；换汇 片道 3 銭，
    美股候补快触发时美元先留着 = sim-unify 的美股默认），一股起买；只在加入 S&P 500 之后开新仓（与 H1 同一口径）。
    两边的股票池都去掉你一贯不要的行业（qbreak/universes.py 的 JP_EXCLUDED / US_EXCLUDED 同一个口径）：日本 = 航空、陆运 / 物流；
    美国 = GICS 细分 航空 / 空运物流 / 铁路 / 陆运、服装 / 鞋、包装食品 / 饮料 / 酒 / 餐厅 / 食品流通 / 食品零售、日用品综合零售（WMT 等），
    再加 US_EXCLUDED 里的票（剩 451 只）。
三 另报（只描述，不参与读法）：US-0 = US-R 去掉楽天的手续费与换汇成本（方法本身在美股有没有优势）；
  US-P = 美股用它以前的参数（best_params_US：不看死叉、+3% 之后 10% 跟踪止损、没有 W2；当时在美国数据上调过的）；
  JP-LF = 研究框架（leap_confirm：今天的日経225、2017 年以后真实一手）同一套规则只有个股层（与以前研究的数字对得上）；
  整个账户 = 加上现在的闲置资金（纳指 1545 + 美股牛熊分界；美股那边也在楽天买 1545，东证 ETF 0 円）。
四 窗口：E 2006-10〜2016-09、J 2017-01〜2026-09（从 2006-10-01 连续回测一次，按窗口切）；每笔按买入日归窗口。
五 看什么：① 每笔（引擎真的做了的交易）：笔数、胜率、每笔净收益（扣手续费、滑点；本币）、中位数、减去同期自己指数（日経225 / S&P500）后的超额、
  平均持有天数；② 只有个股层的账户（日元）：年化、最大回撤、Calmar、平均持仓只数 ÷ 4、每年手续费 + 换汇成本（日元）。
六 读法（事先写定）：E、J 两个窗口都是「JP-T 每笔净收益 ≥ US-R」且「JP-T 的 Calmar ≥ US-R」→「日経（立花）更好」；两个窗口都反过来 →
  「美股（楽天）更好」；其余 →「各有胜负」（写明哪项哪段）。每笔差（JP − US）的 95% 区间（按买入月聚类自助法 2,000 次）照报，不参与读法。
  这只是回答问题：模拟盘 / 执行器不变（立花 ｅ支店不做美股；楽天的美股不能由程序自动下单 —— MARKETSPEED II RSS 只能下日本株，
  CLAUDE.md 也不允许自动操作楽天网站 / iSPEED）。
七 事前预期：「日経更好」约 65%（①② 已知美股每笔被楽天费用吃掉；X6 在美国未知）；US-R 每笔净收益为负约 55%；US-0 每笔低于 JP-T 约 60%。
八 照实写：两边都是今天的成员加上能取到行情的旧成员（倒闭 / 被收购的没有行情，美股的成员变动更多 → 美股偏乐观更多）；美股一股起买、名额更容易填满；
  日本 2006〜2016 用复权价算一手（比真实便宜）；美股按日元计的账户收益含汇率；税前（美股分红的外国税不算）。非投资建议。
登记前的检查（只数了票与信号，没有跑任何回测、没有算收益）：日本 254 只（今天的成员去掉航空 / 陆运 + 能取到行情的旧成员；1805.T 取不到）、
  美国 449 只（有 ≥ 300 根 K 线的）；2006-10 以后的进场信号（W2 与成员过滤之后）日本 299 个、美国 737 个；USD/JPY 修正 4 天（2008）。
输出：var/out/market_compare_study.md / .json（只有统计）。
"""
from __future__ import annotations

import json
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
from qbreak import exit_rules as EXR                                         # noqa: E402
from qbreak import paths                                                     # noqa: E402

START = "2006-10-01"
WIN = {"E": ("2006-10-01", "2016-09-30"), "J": ("2017-01-04", None)}
JUDGE = ("E", "J")
SLOTS = 4
BOOT, SEED = 2000, 20260929
US_EXCL_SUBS = {"Passenger Airlines", "Air Freight & Logistics", "Cargo Ground Transportation", "Passenger Ground Transportation",
                "Rail Transportation", "Marine Transportation", "Airport Services", "Highways & Railtracks",
                "Apparel, Accessories & Luxury Goods", "Apparel Retail", "Footwear", "Packaged Foods & Meats",
                "Soft Drinks & Non-alcoholic Beverages", "Restaurants", "Food Distributors", "Food Retail", "Brewers",
                "Distillers & Vintners", "Consumer Staples Merchandise Retail"}
ARMS = {"JP-T": "日経225 × 立花 個別コース", "US-R": "S&P 500 × 楽天（0.495%、换汇 3 銭）",
        "US-0": "S&P 500 去掉楽天费用（只描述）", "US-P": "S&P 500 × 楽天，美股以前的参数（只描述）"}


# ───────────────────────── 每笔 ─────────────────────────
def trade_table(trades: pd.DataFrame, market: str, index_close: pd.Series, fx_close: pd.Series | None = None) -> pd.DataFrame:
    """引擎的成交记录 → 每笔：净收益 %（扣手续费与滑点，本币）、手续费（日元）、同期指数收益与超额。
    同期指数 = 买入日前一个交易日收盘 → 卖出日收盘（与开盘买入、按收盘或开盘卖出的口径差不到一天）。"""
    t = trades[(trades["market"] == market) & (trades["reason"] != "end")].copy()
    if not len(t):
        return pd.DataFrame(columns=["ticker", "entry_date", "exit_date", "net", "fee_jpy", "idx", "excess", "hold_days", "win"])
    cost = t["entry_px"].astype(float) * t["shares"].astype(float)
    t["net"] = t["pnl"].astype(float) / cost * 100
    fee_local = (t["exit_px"].astype(float) - t["entry_px"].astype(float)) * t["shares"].astype(float) - t["pnl"].astype(float)
    ic = index_close.dropna().sort_index()
    ent = pd.to_datetime(t["entry_date"])
    ext = pd.to_datetime(t["exit_date"])
    i0 = _asof(ic, ent, strict=True)                                        # 买入日前一个交易日的收盘
    i1 = _asof(ic, ext, strict=False)                                       # 卖出日（或之前最后一天）的收盘
    t["idx"] = (i1 / i0 - 1) * 100
    t["excess"] = t["net"] - t["idx"]
    if fx_close is not None:
        rate = _asof(fx_close.dropna().sort_index(), ext, strict=False)
        t["fee_jpy"] = fee_local.to_numpy(float) * rate
    else:
        t["fee_jpy"] = fee_local.to_numpy(float)
    t["win"] = t["net"] > 0
    t["entry_date"], t["exit_date"] = ent, ext
    return t


def _asof(s: pd.Series, dates, strict: bool) -> np.ndarray:
    """每个日期：s 在那天（strict = 那天之前）最后一个值；没有 → NaN。"""
    ix = s.index.values
    k = np.searchsorted(ix, pd.DatetimeIndex(dates).values, side="left" if strict else "right") - 1
    v = s.to_numpy(float)
    return np.where(k >= 0, v[np.clip(k, 0, len(v) - 1)], np.nan)


def window_trades(T: pd.DataFrame, a: str, b: str | None) -> pd.DataFrame:
    if not len(T):
        return T
    m = T["entry_date"] >= pd.Timestamp(a)
    if b:
        m &= T["entry_date"] <= pd.Timestamp(b)
    return T[m]


def trade_stats(T: pd.DataFrame) -> dict:
    if not len(T):
        return {"n": 0}
    return {"n": int(len(T)), "win": round(float(T["win"].mean() * 100), 1), "mean": round(float(T["net"].mean()), 3),
            "median": round(float(T["net"].median()), 3), "excess": round(float(T["excess"].mean()), 3),
            "idx": round(float(T["idx"].mean()), 3), "hold": round(float(T["hold_days"].astype(float).mean()), 1)}


def boot_diff(A: pd.DataFrame, B: pd.DataFrame, reps: int = BOOT, seed: int = SEED) -> tuple[float | None, float | None]:
    """mean(A.net) − mean(B.net) 的 95% 区间：两边各自按买入月聚类重抽。"""
    if not len(A) or not len(B):
        return None, None
    rng = np.random.default_rng(seed)

    def groups(T):
        g = T.groupby(T["entry_date"].dt.to_period("M"))["net"]
        return [v.to_numpy(float) for _, v in g]
    ga, gb = groups(A), groups(B)
    out = []
    for _ in range(reps):
        sa = np.concatenate([ga[k] for k in rng.integers(0, len(ga), len(ga))])
        sb = np.concatenate([gb[k] for k in rng.integers(0, len(gb), len(gb))])
        out.append(sa.mean() - sb.mean())
    return round(float(np.percentile(out, 2.5)), 3), round(float(np.percentile(out, 97.5)), 3)


def avg_positions(T: pd.DataFrame, days: pd.DatetimeIndex, a: str, b: str | None) -> float | None:
    """窗口里每天持有的个股只数的平均 ÷ 名额（买入日起、卖出日前）。"""
    w = days[(days >= pd.Timestamp(a)) & ((days <= pd.Timestamp(b)) if b else True)]
    if not len(w):
        return None
    cnt = np.zeros(len(w))
    for e, x in zip(T["entry_date"], T["exit_date"]):
        cnt += (w >= e) & (w < x)
    return round(float(cnt.mean() / SLOTS * 100), 1)


def verdict(res: dict) -> tuple[str, list[str]]:
    """六：两个窗口都 JP ≥ US（每笔与 Calmar）→ 日経更好；都反过来 → 美股更好；其余各有胜负。"""
    jp, us, notes = [], [], []
    for t in JUDGE:
        a, b = res[t]["JP-T"], res[t]["US-R"]
        tm = a["trades"].get("mean"), b["trades"].get("mean")
        cm = a["acct"].get("calmar"), b["acct"].get("calmar")
        if None in tm or None in cm:
            return "没有值", [f"{t} 缺值"]
        jp.append(tm[0] >= tm[1] and cm[0] >= cm[1])
        us.append(tm[1] > tm[0] and cm[1] > cm[0])
        notes.append(f"{t}：每笔 {'日経' if tm[0] >= tm[1] else '美股'}高、Calmar {'日経' if cm[0] >= cm[1] else '美股'}高")
    if all(jp):
        return "日経（立花）更好", notes
    if all(us):
        return "美股（楽天）更好", notes
    return "各有胜负", notes


# ───────────────────────── 数据 ─────────────────────────
def load_all() -> dict:
    import equity_idle_study as EQ
    import us_stock_data as UD
    from bullbear_study import SYM, load
    from qbreak import n225_history as NH
    from qbreak import factors
    from qbreak.config import DataConfig
    from qbreak.data import load_universe
    from qbreak.universes import nikkei225
    d21 = DataConfig(provider="yfinance", years=21, allow_synthetic=False).validate()
    jp = load_universe(NH.pit_names(nikkei225()), d21)
    us_names = us_pool()
    us = UD.ohlcv(us_names)
    added = {r["ticker"]: pd.Timestamp(r["date_added"]) for r in UD.constituents()["sp500"] if r.get("date_added")}
    idx = {m: load(*SYM[m]) for m in ("JP", "US")}
    fxdf = load("JPY=X", "2000-01-01")
    fxdf = fxdf[(fxdf["Close"] > 60) & (fxdf["Close"] < 250)].copy()
    dex = factors.fred("DEXJPUS").dropna()
    _, fixed = EQ.clean_fx(fxdf["Close"], dex)
    for d in fixed:
        fxdf.loc[pd.Timestamp(d), ["Open", "Close"]] = float(dex.loc[pd.Timestamp(d)])
    fr, _cl = EQ.assets(EQ.load_inputs())
    return {"jp": jp, "us": {t: df for t, df in us.items() if t in set(us_names)}, "added": added, "idx": idx, "fx": fxdf[["Open", "Close"]],
            "fx_fixed": fixed, "q1": fr["1545.T"], "d21": d21}


def us_pool() -> list[str]:
    """今天的 S&P 500 去掉 US_EXCL_SUBS 的细分行业与 qbreak/universes.US_EXCLUDED 的票。"""
    import us_stock_data as UD
    from qbreak.universes import US_EXCLUDED
    excl = {t for v in US_EXCLUDED.values() for t in v}
    sub = {r["ticker"]: r["sub"] for r in UD.constituents()["sp500"]}
    return [t for t in UD.names("sp500") if t not in excl and sub.get(t) not in US_EXCL_SUBS]


def membership(ind: dict[str, pd.DataFrame], market: str, added: dict[str, pd.Timestamp]) -> dict[str, pd.DataFrame]:
    """只在当时是指数成员时开新仓：日本 = n225_history 的近似时点（按年，进出那年不算）；美国 = 加入 S&P 500 之后（没有日期 → 不开）。"""
    from qbreak import n225_history as NH
    out = {}
    if market == "JP":
        mm = NH.member_mask(ind, strict=True)
        for t, df in ind.items():
            out[t] = df.assign(entry=df["entry"].to_numpy(bool) & mm[t])
    else:
        for t, df in ind.items():
            a = added.get(t)
            ok = np.zeros(len(df), bool) if a is None else (df.index >= a)
            out[t] = df.assign(entry=df["entry"].to_numpy(bool) & ok)
    return out


def entry_mult(ind: dict[str, pd.DataFrame], market: str, idx_df: pd.DataFrame, d21) -> pd.DataFrame:
    """新仓倍数（与 unified_study 同一口径）：宏观 × 板块倾斜 × 量化状态层（前一天收盘）。"""
    from qbreak.macro import build_entry_mult, features_frame, load_macro_series
    from qbreak.regime import quant_regime_series
    sim = json.loads((paths.home() / "sim.json").read_text(encoding="utf-8"))
    mc = sim.get(market.lower(), {})
    names = list(ind)
    g = pd.DatetimeIndex(sorted(set().union(*[ind[t].index for t in names])))
    closes = pd.DataFrame({t: ind[t]["Close"] for t in names})
    macro = features_frame(load_macro_series(d21))
    M, _ = build_entry_mult(g, names, market, macro, use_macro=bool(mc.get("use_macro", True)),
                            use_sector=bool(mc.get("use_sector_tilt", True)), use_events=False, closes=closes)
    M = M * quant_regime_series(idx_df).reindex(g).ffill().shift(1).fillna(1.0).values[:, None]
    return pd.DataFrame(M, index=g, columns=names)


def jp_ratio(names: list[str]) -> dict[str, pd.Series]:
    """2016-09 以后 J-Quants 的「真实价 ÷ 复权价」（研究框架同一份）→ 一手按真实股价。"""
    import candle_data as CD
    D = CD.load()
    col = {t: j for j, t in enumerate(D["names"])}
    return {t: pd.Series(D["ratio"][:, col[t]], index=D["days"]) for t in names if t in col}


# ───────────────────────── 回测 ─────────────────────────
def run_arm(market: str, ind: dict, em: dict, bear: dict, fx: pd.DataFrame, params: dict, ex: dict, ratio: dict,
            core_frame: pd.DataFrame | None = None, core_broker: str | None = None, fx_spread_yen: float = 0.03,
            passive: pd.DataFrame | None = None):
    """一个账户（¥100 万、4 × 25%）；core_frame 给了 → 闲置资金拿 1545 + 美股牛熊分界（整个账户）；否则日元现金。"""
    import jq_study as JS
    from qbreak.fees import etf_cost
    from qbreak.unified import UnifiedConfig
    use = dict(ind)
    core, ci, cc = {}, {}, {}
    if core_frame is not None:
        use["1545.T"] = core_frame
        core, ci = {"1545.T": 1.0}, {"1545.T": "US"}
        cc = {"1545.T": etf_cost(core_broker or "tachibana", "1545.T", "JP")}
    elif market == "US" and passive is not None:
        use["1545.T"] = passive                                                # 只为了有东证的日子（换汇在日本白天）；不是核心、不交易
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=SLOTS, max_position_pct=0.34, stock_markets=(market,),
                        core=core, core_index=ci, core_mode="split", fx_spread_yen=fx_spread_yen, usd_keep_imminent=(market == "US"))
    JS.RealLotEngine.RATIO, JS.RealLotEngine.LAST = ratio, []
    e = JS.RealLotEngine(use, cfg, params, ex, cc, fx=fx, entry_mult=em, bear=bear)
    return e.run(start=START)


def fx_cost_jpy(fx_trades: list, spread: float) -> float:
    return float(sum(abs(float(u)) * spread for _d, _dir, u, _r in fx_trades))


def summarize(r, market: str, idx_close: pd.Series, fx_close: pd.Series | None, days: pd.DatetimeIndex, spread: float) -> dict:
    import capital_study as CS
    T = trade_table(r.trades, market, idx_close, fx_close if market == "US" else None)
    out = {}
    fxc = fx_cost_jpy(getattr(r.state, "fx_trades", []) or [], spread)
    for w, (a, b) in WIN.items():
        Tw = window_trades(T, a, b)
        acct = CS.seg_stats(r.equity, a, b)
        e = r.equity.dropna()
        e = e[(e.index >= pd.Timestamp(a)) & ((e.index <= pd.Timestamp(b)) if b else True)]
        yrs = max((e.index[-1] - e.index[0]).days / 365.25, 1e-9) if len(e) else None
        fx_w = sum(abs(float(u)) * spread for d, _dir, u, _r in (getattr(r.state, "fx_trades", []) or [])
                   if pd.Timestamp(d) >= pd.Timestamp(a) and (b is None or pd.Timestamp(d) <= pd.Timestamp(b)))
        out[w] = {"trades": trade_stats(Tw), "acct": acct, "slots": avg_positions(Tw, days, a, b),
                  "fee_yr": round(float(Tw["fee_jpy"].sum()) / yrs, 0) if yrs and len(Tw) else 0.0,
                  "fx_yr": round(fx_w / yrs, 0) if yrs else 0.0, "_T": Tw}
    out["_fx_total"] = round(fxc, 0)
    return out


def lf_reference() -> dict:
    """JP-LF：研究框架（leap_confirm，今天的日経225、2017 年以后真实一手）同一套规则、只有个股层（闲置资金 = 现金）。"""
    import leap_confirm as LF
    from qbreak import score_forward as SF
    from qbreak.trader import load_params
    p = load_params(market="JP")
    p0, px6 = SF.no_w2_params(p), EXR.apply(p, "X6")
    out = {}
    for tag in JUDGE:
        ctx = LF.context(tag)
        fa = LF.frames(ctx, p0)
        run_fn = LF.runner(ctx, fa)
        fw = LF.with_mask(fa, LF.w2_keep(ctx, fa))
        r = LF.run(ctx, run_fn, fw, px6, cfg_over={"core": {}, "core_index": {}, "core_mode": "split"})
        out[tag] = {k: r[tag].get(k) for k in ("cagr", "dd", "calmar", "n", "mean", "win")}
    return out


# ───────────────────────── 运行 ─────────────────────────
def main() -> int:
    import equity_idle_study as EQ
    from qbreak.config import ExecConfig
    from qbreak.strategy import compute_indicators
    from qbreak.trader import load_params
    t0 = time.time()
    L = load_all()
    pj = load_params(market="JP")
    px6, pus = EXR.apply(pj, "X6"), load_params(market="US")
    bear = {m: EQ.t0_bear(L["idx"][m]["Close"]) for m in ("JP", "US")}
    ex = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
    ex0 = {**ex, "US": replace(ex["US"], commission_pct=0.0, commission_max=0.0)}

    def build(data: dict, p) -> dict:
        return {t: compute_indicators(df, p) for t, df in data.items() if len(df) >= 300}
    jp_ind = membership(build(L["jp"], px6), "JP", L["added"])
    us_ind = membership(build(L["us"], px6), "US", L["added"])
    us_indP = membership(build(L["us"], pus), "US", L["added"])
    print(f"数据与指标（{time.time() - t0:.0f}s）：日本 {len(jp_ind)} 只、美国 {len(us_ind)} 只", flush=True)
    em = {"JP": entry_mult(jp_ind, "JP", L["idx"]["JP"], L["d21"]), "US": entry_mult(us_ind, "US", L["idx"]["US"], L["d21"])}
    ratio = jp_ratio(list(jp_ind))
    fx = L["fx"]
    params, paramsP = {"JP": px6, "US": px6}, {"JP": px6, "US": pus}
    q1 = L["q1"]
    runs = {"JP-T": run_arm("JP", jp_ind, em, bear, fx, params, ex, ratio),
            "US-R": run_arm("US", us_ind, em, bear, fx, params, ex, {}, passive=q1),
            "US-0": run_arm("US", us_ind, em, bear, fx, params, ex0, {}, fx_spread_yen=0.0, passive=q1),
            "US-P": run_arm("US", us_indP, em, bear, fx, paramsP, ex, {}, passive=q1),
            "JP-T+Q1": run_arm("JP", jp_ind, em, bear, fx, params, ex, ratio, core_frame=q1, core_broker="tachibana"),
            "US-R+Q1": run_arm("US", us_ind, em, bear, fx, params, ex, {}, core_frame=q1, core_broker="rakuten")}
    print(f"回测完成（{time.time() - t0:.0f}s）", flush=True)
    idx_close = {m: L["idx"][m]["Close"] for m in ("JP", "US")}
    days = {m: L["idx"][m].index for m in ("JP", "US")}
    res: dict = {w: {} for w in WIN}
    for k, r in runs.items():
        m = "JP" if k.startswith("JP") else "US"
        sp = 0.0 if k == "US-0" else 0.03
        sm = summarize(r, m, idx_close[m], fx["Close"], days[m], sp)
        for w in WIN:
            res[w][k] = sm[w]
    v, notes = verdict(res)
    ci = {w: {"JP-T − US-R": boot_diff(res[w]["JP-T"]["_T"], res[w]["US-R"]["_T"]),
              "JP-T − US-0": boot_diff(res[w]["JP-T"]["_T"], res[w]["US-0"]["_T"])} for w in WIN}
    try:
        lf = lf_reference()
    except Exception as e:                                                   # noqa: BLE001
        lf = {"err": f"{type(e).__name__}: {e}"}
    write_report(res, v, notes, ci, lf, L["fx_fixed"])
    print(f"完成（{time.time() - t0:.0f}s）", flush=True)
    return 0


def _f(v, f="{:.2f}") -> str:
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f.format(v)


LABEL = {**ARMS, "JP-T+Q1": "整个账户：日経225 × 立花 + 闲置资金 1545（只描述）", "US-R+Q1": "整个账户：S&P 500 × 楽天 + 闲置资金 1545（只描述）"}


def write_report(res: dict, v: str, notes: list[str], ci: dict, lf: dict, fx_fixed: list[str]) -> None:
    L = ["# 现在的选股方法：楽天的美股 vs 立花的日経225（2026-09-29 登记，只跑一次；规则见本脚本开头）", "",
         f"**按登记的读法：{v}**（" + "；".join(notes) + "）", ""]
    for w, (a, b) in WIN.items():
        L += [f"## {w}：{a}〜{b or '最新'}", "",
              "| 方式 | 笔数 | 胜率 | 每笔净收益（均值 / 中位） | 每笔 − 同期指数 | 持有天数 | 个股层年化 / 最大回撤 / Calmar | 名额使用 | 每年手续费 + 换汇 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for k in ("JP-T", "US-R", "US-0", "US-P", "JP-T+Q1", "US-R+Q1"):
            x = res[w].get(k)
            if not x:
                continue
            t, ac = x["trades"], x["acct"]
            L.append(f"| {k} {LABEL[k]} | {t.get('n', 0)} | {_f(t.get('win'), '{:.1f}')}% | {_f(t.get('mean'), '{:+.2f}')}% / "
                     f"{_f(t.get('median'), '{:+.2f}')}% | {_f(t.get('excess'), '{:+.2f}')}% | {_f(t.get('hold'), '{:.1f}')} | "
                     f"{_f(ac.get('cagr'), '{:+.2f}')}% / {_f(ac.get('dd'))}% / {_f(ac.get('calmar'), '{:.3f}')} | {_f(x.get('slots'), '{:.0f}')}% | "
                     f"¥{_f(x.get('fee_yr'), '{:,.0f}')} + ¥{_f(x.get('fx_yr'), '{:,.0f}')} |")
        c = ci[w]
        L += ["", "每笔差的 95% 区间（按买入月聚类自助法；只描述）：" + "；".join(
            f"{k} {_f(lo, '{:+.2f}')}〜{_f(hi, '{:+.2f}')} pp" for k, (lo, hi) in c.items()), ""]
    if "err" in lf:
        L += [f"JP-LF（研究框架对照）没算出来：{lf['err']}"]
    else:
        L += ["JP-LF（研究框架：今天的日経225、2017 年以后真实一手；同一套规则、只有个股层；与以前研究的数字对得上）：" + "；".join(
            f"{w} {_f(x.get('cagr'), '{:+.2f}')}% / {_f(x.get('dd'))}% / {_f(x.get('calmar'), '{:.3f}')}，{x.get('n')} 笔、胜率 {_f(x.get('win'), '{:.1f}')}%、"
            f"每笔 {_f(x.get('mean'), '{:+.2f}')}%" for w, x in lf.items())]
    L += ["", "USD/JPY 换成 FRED 的错价：" + ("、".join(fx_fixed) or "没有"),
          "", "照实写：两边都是今天的成员加上能取到行情的旧成员（倒闭 / 被收购的没有行情，美股的成员变动更多 → 美股偏乐观更多）；"
          "美股一股起买、名额更容易填满；日本 2006〜2016 按复权价算一手；美股账户的日元收益含汇率；税前。"
          "立花 ｅ支店不做美股、楽天的美股不能由程序自动下单 → 这个比较不改模拟盘。非投资建议。"]
    print("\n".join(L))
    fp = paths.out_dir() / "market_compare_study"
    Path(f"{fp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    clean = {w: {k: {kk: vv for kk, vv in x.items() if kk != "_T"} for k, x in d.items()} for w, d in res.items()}
    Path(f"{fp}.json").write_text(json.dumps({"verdict": v, "notes": notes, "results": clean, "ci": ci, "jp_lf": lf, "fx_fixed": fx_fixed},
                                             ensure_ascii=False, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
