"""timing.py — 核心 ETF 的顶底（牛熊）择时候选：现行价格均线带之外，加入汇率 / 失业率 / 信用利差 / 波动率 / 利率曲线 / 动量。

全部返回「熊市」布尔序列（美国交易日索引；当天收盘后、日本次日开盘前已知）。参数事先固定，
比较与选择见 scripts/timing_study.py。发布时滞：VIX 当天收盘可用；Baa 利差、美债利率滞后 1 个营业日
（FRED 次日才更新）；失业率（月度）在次月 10 日起可用（就业统计通常在次月第一个周五公布）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .bullbear import BEAR, BULL, _sma, ma_band

L, B, K = 250, 0.03, 5            # 现行分界（var/bullbear.json）
VIX_HIGH, VIX_PANIC = 22.0, 30.0  # 现行宏观层阈值 vix_high / vix_panic
BAA_JUMP = 0.30                   # 多因子研究的单因子规则：Baa 利差 20 日走阔 ≥ 0.3pt


def monthly_available(s: pd.Series, days: pd.DatetimeIndex, lag_day: int = 10) -> pd.Series:
    """月度序列（索引 = 月初）→ 每个交易日「已经公布」的最新值：M 月的值在 M+1 月 lag_day 日起可用。"""
    s = s.dropna()
    avail = pd.DatetimeIndex([d + pd.offsets.MonthBegin(1) + pd.Timedelta(days=lag_day - 1) for d in s.index])
    a = pd.Series(s.values, index=avail)
    a = a[~a.index.duplicated(keep="last")].sort_index()
    return a.reindex(days.union(a.index)).ffill().reindex(days)


def factor_frame(days: pd.DatetimeIndex, fx: pd.Series, vix: pd.Series, baa: pd.Series, dgs10: pd.Series,
                 dgs3m: pd.Series, unrate: pd.Series) -> pd.DataFrame:
    """各因子对齐到美国交易日（只用当时已公布的数据）。"""
    def daily(s, lag):
        return s.dropna().reindex(days.union(s.dropna().index)).ffill().reindex(days).shift(lag)
    f = pd.DataFrame(index=days)
    f["fx"] = daily(fx, 0)
    f["vix"] = daily(vix, 0)
    f["baa"] = daily(baa, 1)
    f["curve"] = daily(dgs10, 1) - daily(dgs3m, 1)
    un = unrate.dropna()
    f["un"] = monthly_available(un, days)
    f["un_ma12"] = monthly_available(un.rolling(12).mean(), days)
    f["baa_ma250"] = f["baa"].rolling(250, min_periods=200).mean()
    f["baa_d20"] = f["baa"] - f["baa"].shift(20)
    return f


def _trend(close: pd.Series) -> pd.Series:
    return pd.Series(ma_band(close, L, B, K) == BEAR, index=close.index)


def _persist(raw: pd.Series, k: int = K) -> pd.Series:
    """原始判断连续 k 天一致才切换（与均线带的 k 相同）。"""
    out, state, run, last = [], None, 0, None
    for v in raw.to_numpy(bool):
        run = run + 1 if v == last else 1
        last = v
        if state is None:
            state = bool(v)
        elif v != state and run >= k:
            state = bool(v)
        out.append(state)
    return pd.Series(out, index=raw.index)


def t0_trend(close: pd.Series, f: pd.DataFrame | None = None) -> pd.Series:
    """T0 现行：收盘连续 5 天 < 250 日线 ×0.97 → 熊；连续 5 天 > ×1.03 → 牛。"""
    return _trend(close)


def t1_fx_trend(close: pd.Series, f: pd.DataFrame) -> pd.Series:
    """T1 汇率：同一规则用在日元计价的指数（指数 × USD/JPY）上。"""
    j = (close * f["fx"]).dropna()
    return _trend(j).reindex(close.index).fillna(False).astype(bool)


def t2_growth_trend(close: pd.Series, f: pd.DataFrame) -> pd.Series:
    """T2 增长 + 趋势：趋势熊 且 失业率 > 其 12 个月均值（衰退风险）才熊。"""
    return _trend(close) & (f["un"] > f["un_ma12"]).fillna(False)


def t3_credit_confirm(close: pd.Series, f: pd.DataFrame) -> pd.Series:
    """T3 信用确认：趋势熊 且 Baa−10Y 利差 > 其 250 日均值 才熊。"""
    return _trend(close) & (f["baa"] > f["baa_ma250"]).fillna(False)


def stress_state(f: pd.DataFrame) -> pd.Series:
    """压力态：VIX ≥ 30 且 Baa 利差 20 日走阔 ≥ 0.3pt 时进入，VIX < 22 时解除。"""
    out, on = [], False
    for v, d in zip(f["vix"].to_numpy(float), f["baa_d20"].to_numpy(float)):
        if not on and v >= VIX_PANIC and d >= BAA_JUMP:
            on = True
        elif on and v < VIX_HIGH:
            on = False
        out.append(on)
    return pd.Series(out, index=f.index)


def t4_stress_exit(close: pd.Series, f: pd.DataFrame) -> pd.Series:
    """T4 压力提前离场：趋势熊 或 压力态。"""
    return _trend(close) | stress_state(f)


def t5_momentum(close: pd.Series, f: pd.DataFrame | None = None) -> pd.Series:
    """T5 12 个月绝对动量：每月最后一个交易日 252 日涨幅 ≤ 0 → 熊，持有到下个月末再判断。"""
    mom = close / close.shift(252) - 1
    me = close.index.to_series().groupby(close.index.to_period("M")).max()
    last = close.index[-1]
    if last < last + pd.offsets.BMonthEnd(0):                     # 最后一个月还没到月末：不算月末（与每日实盘一致）
        me = me[me < last.to_period("M").start_time]
    sig = pd.Series(np.nan, index=close.index)
    sig.loc[me.values] = (mom.loc[me.values] <= 0).astype(float)
    return sig.ffill().fillna(0.0).astype(bool)


def t6_majority(close: pd.Series, f: pd.DataFrame) -> pd.Series:
    """T6 多数表决：趋势熊、Baa 利差 > 250 日均值、VIX ≥ 22、失业率 > 12 个月均值、10Y−3M < 0，
    5 项里 ≥3 项为熊的状态连续 5 天才切换。"""
    flags = pd.DataFrame({"trend": _trend(close), "credit": (f["baa"] > f["baa_ma250"]).fillna(False),
                          "vix": (f["vix"] >= VIX_HIGH).fillna(False), "jobs": (f["un"] > f["un_ma12"]).fillna(False),
                          "curve": (f["curve"] < 0).fillna(False)})
    return _persist(flags.sum(axis=1) >= 3)


CANDIDATES = {"T0": t0_trend, "T1": t1_fx_trend, "T2": t2_growth_trend, "T3": t3_credit_confirm,
              "T4": t4_stress_exit, "T5": t5_momentum, "T6": t6_majority}
LABELS = {"T0": "现行 250 日线 ±3%、连续 5 天", "T1": "同规则用在日元计价指数（汇率）",
          "T2": "趋势熊 且 失业率上升（增长+趋势）", "T3": "趋势熊 且 信用利差高于均值",
          "T4": "趋势熊 或 压力态（VIX≥30 且利差急扩）", "T5": "12 个月绝对动量（月度）",
          "T6": "5 因子多数表决（趋势/信用/VIX/失业率/曲线）"}


# ══════════ 第二轮候选（2026-09-26 登记，scripts/timing2_study.py；参数全部事先固定，不做网格搜索）══════════
# 针对现行 T0 的弱点：离场慢（样本外熊市识别中位延迟 美 39.5 / 日 30 交易日）、回补慢（美 98 / 日 62 交易日，
# 2009、2020 回补时已比底部高 40% 以上）、误报（样本外 美 5 / 日 3 次，每次回补价比离场价高 5〜17%）。
# 返回整数状态数组（+1 牛 / −1 熊 / 0 = 250 日线还没有），与 bullbear.ma_band 相同，评估用 bullbear.evaluate。
FAST_DD, FAST_K = 0.10, 2                  # T7：距 250 日最高收盘回落 ≥10% 且收在 250 日线下，连续 2 天 → 快速离场
VOL_LO, VOL_HI = 0.015, 0.06               # T9：带宽 = c × 250 日年化波动率，夹在 T0 带宽（3%）的一半〜两倍
TRAIN_END = "2005-12-31"                   # T9 的 c 只用这天以前的数据定：训练期内带宽中位数 = 3%（与 T0 相同）
HALF = 0.5                                 # T10：临界（连续 5 天在 250 日线的另一侧）时的持仓比例
RALLY, TRAIL = 0.20, 0.10                  # T11：熊市里从最低收盘反弹 ≥20% 提前回补；回补后自最高收盘回落 ≥10% 再离场


def _state_machine(close: pd.Series, band: np.ndarray, fast_bear=None, early=False, early_ok=None) -> np.ndarray:
    """T0 的状态机（连续 K 天收在 250 日线 ×(1−b) 之下 → 熊，×(1+b) 之上 → 牛），b 可以逐日不同；
    fast_bear[i]：这一天另有「快速离场」条件成立（T7 / T8 / T12 / T13）；early：T11 的提前回补（见 s11_v_reentry）；
    early_ok[i]：提前回补另要满足的条件（T14 / T15；None = 不另加条件）。"""
    v = close.to_numpy(float)
    ma = _sma(v, L)
    st = np.zeros(len(v), dtype=int)
    state, run_dn, run_up = 0, 0, 0
    in_early, lo, hi = False, np.inf, -np.inf
    for i in range(len(v)):
        if np.isnan(ma[i]):
            continue
        b = band[i] if np.isfinite(band[i]) else B
        dn, up = v[i] < ma[i] * (1 - b), v[i] > ma[i] * (1 + b)
        run_dn = run_dn + 1 if dn else 0
        run_up = run_up + 1 if up else 0
        if state == 0:
            state = BULL if v[i] >= ma[i] else BEAR
            lo = hi = v[i]
        elif state == BULL:
            if in_early:                                   # T11：提前回补之后，回到 250 日线上方之前用 10% 回落离场
                hi = max(hi, v[i])
                if v[i] >= ma[i]:
                    in_early = False
                elif v[i] <= hi * (1 - TRAIL):
                    state, lo, in_early = BEAR, v[i], False
            elif run_dn >= K or (fast_bear is not None and fast_bear[i]):
                state, lo = BEAR, v[i]
        else:
            lo = min(lo, v[i])
            if run_up >= K:
                state, in_early = BULL, False
            elif early and (early_ok is None or early_ok[i]) and v[i] >= lo * (1 + RALLY):
                state, in_early, hi = BULL, True, v[i]
        st[i] = state
    return st


def _runs_of(mask: np.ndarray) -> np.ndarray:
    """每天「连续为真的天数」（今天为假 → 0）。"""
    out = np.zeros(len(mask), dtype=int)
    r = 0
    for i, m in enumerate(mask):
        r = r + 1 if m else 0
        out[i] = r
    return out


def s0_states(close: pd.Series, f: pd.DataFrame | None = None) -> np.ndarray:
    """T0 现行（整数状态）。"""
    return ma_band(close, L, B, K)


def s7_dual_speed(close: pd.Series, f: pd.DataFrame | None = None) -> np.ndarray:
    """T7 双速离场：T0 之外，「收在 250 日线下 且 距 250 日最高收盘回落 ≥10%」连续 2 天 → 立即转熊；回补同 T0。"""
    v = close.to_numpy(float)
    ma = _sma(v, L)
    hi = close.rolling(L, min_periods=1).max().to_numpy(float)
    fast = _runs_of((v < ma) & (v <= hi * (1 - FAST_DD))) >= FAST_K
    return _state_machine(close, np.full(len(v), B), fast_bear=fast)


def s8_credit_fast_exit(close: pd.Series, f: pd.DataFrame) -> np.ndarray:
    """T8 信用只用来加快离场：Baa−10Y 利差 > 其 250 日均值（T3 的信用条件）时，转熊线从 250 日线 ×0.97 提到 250 日线本身
    （连续 5 天收在线下）；利差正常时与 T0 相同；回补同 T0（信用不延迟任何切换）。利差数据之前（1986 年以前）= T0。"""
    v = close.to_numpy(float)
    ma = _sma(v, L)
    stress = (f["baa"] > f["baa_ma250"]).reindex(close.index).fillna(False).to_numpy(bool)
    fast = stress & (_runs_of(v < ma) >= K)
    return _state_machine(close, np.full(len(v), B), fast_bear=fast)


def vol_ann(close: pd.Series, win: int = L) -> pd.Series:
    """过去 win 个交易日（含当天）日对数收益的年化标准差。"""
    r = np.log(close.astype(float)).diff()
    return r.rolling(win, min_periods=win).std() * np.sqrt(252)


def t9_scale(close: pd.Series, train_end: str = TRAIN_END) -> float:
    """c = 3% ÷ 训练期（≤ train_end）250 日年化波动率的中位数 → 训练期内带宽的中位数与 T0 相同。"""
    vol = vol_ann(close)
    vol = vol[vol.index <= pd.Timestamp(train_end)].dropna()
    if len(vol) < L:
        raise ValueError(f"T9：{train_end} 以前的数据不够定带宽系数（{len(vol)} 天）")
    return B / float(vol.median())


def s9_vol_band(close: pd.Series, f: pd.DataFrame | None = None, c: float | None = None,
                train_end: str = TRAIN_END) -> np.ndarray:
    """T9 波动率自适应带宽：b_t = clip(c × 250 日年化波动率, 1.5%, 6%)，其余同 T0（连续 5 天）。"""
    c = t9_scale(close, train_end) if c is None else c
    band = np.clip(c * vol_ann(close).to_numpy(float), VOL_LO, VOL_HI)
    return _state_machine(close, band)


def t10_half_expo(close: pd.Series, f: pd.DataFrame | None = None) -> pd.Series:
    """T10 临界减半（牛熊状态 = T0，只改持仓比例）：牛市里连续 5 天收在 250 日线下 → 持 50%，连续 5 天回到线上 → 100%；
    熊市里连续 5 天收在 250 日线上 → 持 50%，连续 5 天回到线下 → 0%。T0 转熊 → 0%，转牛 → 100%。
    「250 日线」= 日报「牛熊阶段」里临界的边界（离翻转线 3% = 带宽）。"""
    v = close.to_numpy(float)
    ma = _sma(v, L)
    st = s0_states(close)
    below, above = _runs_of(v < ma) >= K, _runs_of(v > ma) >= K
    out = np.ones(len(v))
    e, prev = 1.0, 0
    for i in range(len(v)):
        if st[i] == 0:
            continue
        if st[i] != prev:                                  # T0 刚切换（或第一天）
            e = 1.0 if st[i] == BULL else 0.0
        if st[i] == BULL:
            e = HALF if below[i] else (1.0 if above[i] else e)
        else:
            e = HALF if above[i] else (0.0 if below[i] else e)
        out[i], prev = e, st[i]
    return pd.Series(out, index=close.index)


def s11_v_reentry(close: pd.Series, f: pd.DataFrame | None = None) -> np.ndarray:
    """T11 V 形提前回补：熊市里收盘比熊市以来的最低收盘高 ≥20%（事后标注「牛市开始」的同一标准）→ 立即转牛；
    这样回补之后、重新收在 250 日线上方之前，离场改用「自回补后最高收盘回落 ≥10%」（否则仍在转熊线下会马上又转熊）；
    回到 250 日线上方之后恢复 T0 规则。离场与其余同 T0。"""
    return _state_machine(close, np.full(len(close), B), early=True)


STATES2 = {"T0": s0_states, "T7": s7_dual_speed, "T8": s8_credit_fast_exit, "T9": s9_vol_band,
           "T10": s0_states, "T11": s11_v_reentry}           # T10 的牛熊状态 = T0，差别在持仓比例（t10_half_expo）
LABELS2 = {"T0": "现行 250 日线 ±3%、连续 5 天", "T7": "双速离场（跌破 250 日线且距高点 −10%，连续 2 天）",
           "T8": "信用只加快离场（利差高于均值时 250 日线本身即转熊线）", "T9": "波动率自适应带宽（1.5%〜6%）",
           "T10": "临界减半（在 250 日线另一侧连续 5 天 → 持 50%）", "T11": "V 形提前回补（自低点 +20%，回补后 −10% 离场）"}


def bear2(key: str, close: pd.Series, f: pd.DataFrame | None = None, **kw) -> pd.Series:
    """第二轮候选的熊市布尔序列（0 = 还没有 250 日线 → 不算熊）。"""
    return pd.Series(STATES2[key](close, f, **kw) == BEAR, index=close.index)


def expo2(key: str, close: pd.Series, f: pd.DataFrame | None = None, **kw) -> pd.Series:
    """持有核心 ETF 的比例（0〜1）：T10 分级，其余 = 1 − 熊。"""
    if key == "T10":
        return t10_half_expo(close, f)
    return (~bear2(key, close, f, **kw)).astype(float)


# ══════════ 第三轮候选（2026-09-26 登记，scripts/timing3_study.py；看过第二轮结果之后设计，参数沿用或取常用值）══════════
# 第二轮的教训：离场快了误报就多（T7 日本样本外误报 3→9 次），回补早了就在多段下跌的熊市里反复被套（T11）。
# 这一轮给「快」加一个独立的确认：快速离场要信用或另一个大市场同时确认；提前回补要短期趋势已经转好。
MA_SHORT, SLOPE_WIN = 50, 20               # T14 / T15：提前回补另要「收在 50 日线上 且 50 日线比 20 个交易日前高」


def fast7(close: pd.Series) -> np.ndarray:
    """T7 的快速离场条件：收在 250 日线下 且 距 250 日最高收盘回落 ≥10%，连续 2 天。"""
    v = close.to_numpy(float)
    ma = _sma(v, L)
    hi = close.rolling(L, min_periods=1).max().to_numpy(float)
    return _runs_of((v < ma) & (v <= hi * (1 - FAST_DD))) >= FAST_K


def credit_stress(close: pd.Series, f: pd.DataFrame) -> np.ndarray:
    """T3 / T8 的信用条件：Baa−10Y 利差 > 其 250 日均值（没有数据 → 不算压力）。"""
    return (f["baa"] > f["baa_ma250"]).reindex(close.index).fillna(False).to_numpy(bool)


def trend_up(close: pd.Series) -> np.ndarray:
    """短期趋势转好：收在 50 日线上 且 50 日线比 20 个交易日前高（只用当天为止的收盘）。"""
    v = close.to_numpy(float)
    m = _sma(v, MA_SHORT)
    prev = np.r_[np.full(SLOPE_WIN, np.nan), m[:-SLOPE_WIN]] if len(m) > SLOPE_WIN else np.full(len(m), np.nan)
    with np.errstate(invalid="ignore"):
        return (v > m) & (m > prev)


def s12_fast_credit(close: pd.Series, f: pd.DataFrame) -> np.ndarray:
    """T12 快速离场要信用确认：T0 之外，「T7 的快速条件 且 信用利差高于均值」→ 立即转熊；回补同 T0。"""
    return _state_machine(close, np.full(len(close), B), fast_bear=fast7(close) & credit_stress(close, f))


def s13_fast_global(close: pd.Series, f: pd.DataFrame) -> np.ndarray:
    """T13 快速离场要另一个大市场确认：T0 之外，「T7 的快速条件 且 另一个大市场收在它自己的 250 日线下」→ 立即转熊；
    回补同 T0。另一个市场：美股用日経（同一天已收盘），其他市场用 S&P500（前一天收盘）；f["other_below"] 由研究脚本对齐。"""
    other = f["other_below"].reindex(close.index).fillna(False).to_numpy(bool)
    return _state_machine(close, np.full(len(close), B), fast_bear=fast7(close) & other)


def s14_v_trend(close: pd.Series, f: pd.DataFrame | None = None) -> np.ndarray:
    """T14 V 形回补要趋势确认：T11 的提前回补（自熊市低点 +20%，回补后 −10% 离场，回到 250 日线上方后恢复 T0），
    另要当天「收在 50 日线上 且 50 日线比 20 个交易日前高」。离场同 T0。"""
    return _state_machine(close, np.full(len(close), B), early=True, early_ok=trend_up(close))


def s15_both(close: pd.Series, f: pd.DataFrame) -> np.ndarray:
    """T15 两头都改：离场同 T12（快速离场要信用确认），回补同 T14（V 形回补要趋势确认）。"""
    return _state_machine(close, np.full(len(close), B), fast_bear=fast7(close) & credit_stress(close, f),
                          early=True, early_ok=trend_up(close))


STATES3 = {"T0": s0_states, "T12": s12_fast_credit, "T13": s13_fast_global, "T14": s14_v_trend, "T15": s15_both}
REF3 = {"T7": s7_dual_speed, "T8": s8_credit_fast_exit, "T11": s11_v_reentry}   # 第二轮的对照（不参与判定）
LABELS3 = {"T0": "现行 250 日线 ±3%、连续 5 天", "T12": "快速离场要信用确认（T7 条件 且 利差高于均值）",
           "T13": "快速离场要另一个大市场确认（T7 条件 且 另一市场在 250 日线下）",
           "T14": "V 形回补要趋势确认（+20% 且 在 50 日线上、50 日线上升）", "T15": "T12 的离场 + T14 的回补",
           "T7": "（对照）第二轮 T7 双速离场", "T8": "（对照）第二轮 T8 信用只加快离场", "T11": "（对照）第二轮 T11 V 形提前回补"}
