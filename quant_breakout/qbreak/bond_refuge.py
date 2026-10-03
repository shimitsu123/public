"""bond_refuge.py — 闲置资金「美股熊市里、股债负相关时拿对冲版美债 1482」BCU（第六个研究循环第 1 轮 scripts/loop6_r01_bondcorr.py：
登记 42376b0、第二关登记 41b24b6、结果 526910a；2026-10-03 用户「采用」→ var/sim.json idle_cash.mode = "Q1HB"，见 qbreak/idle_cash.py）。

可拿 = 东证交易日上最近 WIN = 63 天 S&P500 与对冲版美国 7〜10 年国债日收益的相关 < 0（国债起避险作用）；不到 63 天 / 算不出 → 不可拿。
  两边都放在东证交易日 d 上 = d 之前最近的美国收盘（d 当天的不用；= 研究 equity_idle_study.on_jp / prev_on）。
  国债 = 研究同一个合成价（loop2_r02_bondrefuge.bond_hedged(bond_usd())）：FRED DGS7 与 DGS10 都有的日子取平均收益率，当作 8.5 年平价债的美元总收益；
  对冲 = 每天 + (日本拆借 − 联邦基金) / 252（fxhedge_study.hedged_index：美国利率用前一天、日本月利率下个月初起才用）；每年扣 0.754%（信託報酬 + 跟踪差）。
引擎（qbreak/unified.py，follow 模式）：键 BR:BD = 美股牛 或 不可拿（True = 1482 目标 0）→ 美股熊且可拿：闲置资金全部拿 1482；
  美股熊且不可拿：现金（= 采用前的 Q1H）；美股牛：1482 目标 0，FJE 照旧（1545 / 2845）。
时点：日本 d 日收盘的决策（d+1 开盘成交）用 d 之前最近的美国收盘为止的 S&P500 与国债收益率（= 研究）。
  FRED 的收益率实际晚 1〜3 个美国交易日才公布 → 只算到「要用的美国收盘两边都有」的最后一个东证交易日，之后沿用那天的判定
  （研究口径晚 1 / 2 / 3 天：2006〜2026 美股熊的日子与研究的判定一致 99.5% / 99.1% / 98.9%，见 var/sim_changes.md 2026-10-03 采用一节）；
  国债收益率落后最新 K 线 > LAG_WARN 天 → 标出来；> LAG_MAX 天 → 算不了（按不可拿 = 现金）。
云端 sim-day 决策前算 → var/bond_refuge.json（最近 60 天）；Mac 执行器读 scripts/liveu.sh 同步过来的同一个文件
  （同一个决策；文件不在 / 没覆盖最新 K 线 → 本机现算并在日志与页面写明）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .fx_hedge import asof, covers, load, since, state_from_payload   # noqa: F401（文件 / 状态的读法与 FJE 相同）

WIN = 63                                       # 相关的窗口（东证交易日）
TENOR = 8.5                                    # 年：7 年与 10 年的平均收益率当作 8.5 年平价债（1482 加权平均残存 8.49 年）
TRUST_FEE, BASIS = 0.154, 0.6                  # 年 %：信託報酬（税込）+ 合成价相对真实 1482 的跟踪差
FRED_IDS = ("DGS7", "DGS10", "DFF", "IRSTCI01JPM156N")
BOND_T = "1482.T"
FILE = "bond_refuge.json"
KEY = "BR:BD"
KEEP_DAYS = 60
LAG_WARN, LAG_MAX = 7, 14                      # 日历天：国债收益率最后一天落后最新 K 线多少天 → 标出 / 算不了（运行上的数据检查，不是策略参数）


def _ff(s: pd.Series, idx: pd.DatetimeIndex) -> np.ndarray:
    return (s.astype(float).reindex(idx).ffill().fillna(0.0) > 0.5).to_numpy(bool)


# ───────────────────────── 合成价（= 研究的同名函数） ─────────────────────────
def par_bond_tr(yield_pct: pd.Series, tenor: float = TENOR) -> pd.Series:
    """固定期限平价债的美元总收益指数（从 1 起）：每天 = 按前一天收益率作票息、新收益率下的价格 − 1 + 前一天收益率 × 天数 / 365（半年付息）。"""
    y = yield_pct.dropna().sort_index().astype(float) / 100
    y0 = y.shift(1)
    disc = (1 + y / 2) ** (-2 * tenor)
    price = (y0 / y) * (1 - disc) + disc
    dt = y.index.to_series().diff().dt.days.to_numpy(float) / 365.0
    r = (price - 1 + y0 * dt).fillna(0.0)
    return (1 + r).cumprod()


def grow(s: pd.Series, pct: float) -> pd.Series:
    """× exp(pct% × 年数)（扣费用 = 负）。"""
    s = s.dropna().sort_index()
    yrs = (s.index - s.index[0]).days.to_numpy(float) / 365.25
    return s * np.exp(pct / 100 * yrs)


def hedged_index(tr: pd.Series, us_rate: pd.Series, jp_rate: pd.Series) -> pd.Series:
    """对冲版：每天本地收益 + (日本 − 美国 短期利率)/252；美国利率用前一天、日本月利率用前一个月的值（下个月初起）。"""
    idx = tr.index
    us = us_rate.shift(1).reindex(idx.union(us_rate.index)).ffill().reindex(idx) / 100
    jm = jp_rate.copy()
    jm.index = jm.index + pd.offsets.MonthBegin(1)
    jp = jm.reindex(idx.union(jm.index)).ffill().reindex(idx) / 100
    carry = (jp - us).fillna(0.0) / 252
    r = tr.pct_change().fillna(0.0)
    return (1 + r + carry).cumprod() * float(tr.iloc[0])


def bond_hedged(dgs7: pd.Series, dgs10: pd.Series, dff: pd.Series, jpcall: pd.Series) -> pd.Series:
    """对冲版美国 7〜10 年国债的合成价（美国日期，水平不定）：两个收益率都有的日子取平均 → 平价债总收益 → 对冲 → 扣费用。"""
    y = pd.concat([dgs7.astype(float), dgs10.astype(float)], axis=1).dropna().mean(axis=1)
    return grow(hedged_index(par_bond_tr(y), dff.astype(float), jpcall.astype(float)), -(TRUST_FEE + BASIS))


def prev_on(days: pd.DatetimeIndex, s: pd.Series) -> pd.Series:
    """东证交易日 d 的值 = d 之前最近的一个值（d 当天的不用）。"""
    s = s.dropna().sort_index()
    return s.reindex(days.union(s.index)).ffill().shift(1).reindex(days)


# ───────────────────────── 判定 ─────────────────────────
def corr_values(stock: pd.Series, asset: pd.Series, win: int = WIN) -> pd.Series:
    """asset 的日期上：最近 win 天两者日收益的相关（不到 win 天 = NaN）。"""
    a = asset.dropna().astype(float)
    s = stock.astype(float).reindex(a.index.union(stock.index)).ffill().reindex(a.index)
    return s.pct_change().rolling(win, min_periods=win).corr(a.pct_change())


def corr_on(stock: pd.Series, asset: pd.Series, win: int = WIN) -> pd.Series:
    """可拿：相关 < 0；不到 win 天 / 算不出 → False。= 研究 loop6_r01_bondcorr.corr_on。"""
    c = corr_values(stock, asset, win)
    return pd.Series(np.where(c.to_numpy(float) < 0, True, False), index=c.index)


def fresh_days(days: pd.DatetimeIndex, spx: pd.Series, bond: pd.Series) -> pd.DatetimeIndex:
    """要用的美国收盘两边都已有的东证交易日：d 之前最近的美国收盘（两边日期的并集里）不晚于两边共同的最后一天。
    之后的日子（FRED 还没公布）不算，沿用最后一个（keys 向后填）。"""
    days = pd.DatetimeIndex(days)
    s, b = spx.dropna(), bond.dropna()
    if not len(s) or not len(b):
        return days[:0]
    last = min(s.index[-1], b.index[-1])
    us = s.index.union(b.index)
    later = us[us > last]
    return days if not len(later) else days[days <= later[0]]


def state(spx: pd.Series, bond: pd.Series, days: pd.DatetimeIndex, win: int = WIN) -> dict[str, pd.Series]:
    """{corr, on}（东证交易日，只到 fresh_days 为止）。spx：S&P500 收盘（美国日期）；bond：bond_hedged（美国日期）。"""
    d = fresh_days(days, spx, bond)
    st = prev_on(d, spx.astype(float)).dropna()
    bt = prev_on(d, bond.astype(float)).dropna()
    c = corr_values(st, bt, win)
    return {"corr": c, "on": pd.Series(np.where(c.to_numpy(float) < 0, True, False), index=c.index)}


def keys(on: pd.Series, us_bear: pd.Series) -> dict[str, pd.Series]:
    """引擎的开关键（True = 1482 目标 0）：BR:BD = 美股牛 或 不可拿。两边各自向后填；没有值 = 不拿（美股牛熊不知道 / 判定还没开始 → 1482 目标 0）。"""
    idx = on.index.union(us_bear.index)
    o, ub = _ff(on, idx), _ff(us_bear, idx)
    return {KEY: pd.Series(~ub | ~o, index=idx)}


def payload(bar_date: str, st: dict[str, pd.Series], us_bear: pd.Series | None, spx: pd.Series, bond: pd.Series,
            errors: dict | None = None) -> dict:
    """var/bond_refuge.json：最新 K 线那天的判定 + 最近 KEEP_DAYS 天的状态（执行器补跑用）。"""
    d = pd.Timestamp(bar_date)
    on_s, c = st["on"], st["corr"]
    on_s = on_s[on_s.index <= d]
    tail = on_s.tail(KEEP_DAYS)
    on = asof(on_s, d)
    ub = asof(us_bear, d) if us_bear is not None else None
    cv = asof(c, d)
    b, s = bond.dropna(), spx.dropna()
    bd = b.index[b.index <= d][-1] if (b.index <= d).any() else None
    sd = s.index[s.index < d][-1] if (s.index < d).any() else None
    out = {"version": 1, "as_of": bar_date, "on": None if on is None else bool(on),
           "since": since(on_s, d) if on is not None else None, "win": WIN,
           "corr": None if cv is None or not np.isfinite(float(cv)) else round(float(cv), 3),
           "corr_date": str(on_s.index[-1].date()) if len(on_s) else None,
           "us_bear": None if ub is None else bool(ub),
           "hold": None if on is None or ub is None else bool(on) and bool(ub),
           "bond_date": str(bd.date()) if bd is not None else None, "spx_date": str(sd.date()) if sd is not None else None,
           "lag_days": int((d - bd).days) if bd is not None else None,
           "series": {str(k.date()): bool(v) for k, v in tail.items()}, "errors": dict(errors or {})}
    if out["lag_days"] is None or out["lag_days"] > LAG_MAX:
        out["errors"]["国债收益率"] = f"FRED 只到 {out['bond_date'] or '—'}（最新 K 线 {bar_date}，> {LAG_MAX} 天）→ 算不了、按不拿"
        out["on"] = out["hold"] = None
    elif out["lag_days"] > LAG_WARN:
        out["errors"]["国债收益率"] = f"FRED 只到 {out['bond_date']}（最新 K 线 {bar_date}，> {LAG_WARN} 天；判定沿用 {out['corr_date']}）"
    return out


def text(pl: dict | None) -> str:
    """日报 / 页面 / 执行器日志的一句话。"""
    if not pl or pl.get("on") is None:
        return "股债相关判定算不了 → 美股熊时现金"
    c = f"{pl['corr']:+.2f}" if pl.get("corr") is not None else "—"
    cond = f"股债 {pl.get('win', WIN)} 天相关 {c}（到 {pl.get('corr_date')}，{'< 0 → 可拿' if pl.get('on') else '≥ 0 → 不拿'}，{pl.get('since')} 起）"
    if pl.get("us_bear") is None:
        head = "美股牛熊不知道 → 不拿 1482"
    elif pl.get("us_bear"):
        head = "美股熊 + 股债负相关 → 闲置资金拿对冲版美债 1482" if pl.get("on") else "美股熊 + 股债不是负相关 → 现金"
    else:
        head = "美股牛 → 不拿 1482（美股熊时才看）"
    lag = f"；国债收益率到 {pl.get('bond_date')}" if pl.get("bond_date") else ""
    return f"{head}：{cond}{lag}"
