"""顶底择时第二轮候选（qbreak/timing.py 的 T7〜T11）：只用当天为止的数据；各规则按文档动作；
引擎的 core_expo（分级持仓）缺省时与原来逐笔相同。"""
import numpy as np
import pandas as pd
import pytest

from qbreak import timing as T
from qbreak.bullbear import BEAR, BULL, ma_band

from test_plan_alignment import _synthetic
from test_timing import _data


def _path(*legs, start="2001-01-01", base=100.0):
    """分段直线（对数）价格：legs = [(天数, 这段的总涨跌幅), ...]。"""
    v = [base]
    for n, chg in legs:
        v += list(v[-1] * (1 + chg) ** (np.arange(1, n + 1) / n))
    return pd.Series(v, index=pd.bdate_range(start, periods=len(v)))


@pytest.mark.parametrize("key", list(T.STATES2) + ["T10-expo"])
def test_no_lookahead_second_round(key):
    """把第 t 天以后的价格与因子全部改掉，第 t 天及以前的状态 / 持仓比例不变。"""
    close, f, raw = _data()
    t = 600
    days, fx, vix, baa, dgs10, dgs3m, un = raw
    cut = days[t]
    noise = lambda s: s.where(s.index <= cut, s * 1.7)                                      # noqa: E731
    f2 = T.factor_frame(days, noise(fx), noise(vix), noise(baa), noise(dgs10), noise(dgs3m), un)
    kw = {"train_end": str(days[550].date())} if key == "T9" else {}              # 训练期在 t 之前（波动率要 250 天）
    if key == "T10-expo":
        full, alt = T.t10_half_expo(close, f), T.t10_half_expo(noise(close), f2)
    else:
        full, alt = T.STATES2[key](close, f, **kw), T.STATES2[key](noise(close), f2, **kw)
    assert np.array_equal(np.asarray(full)[:t + 1], np.asarray(alt)[:t + 1])


def test_t7_exits_on_a_deep_fast_break_before_t0_and_reenters_like_t0():
    c = _path((300, 0.30), (12, -0.16), (60, 0.0), (120, 0.40))       # 上涨 → 12 天急跌 16% → 横盘 → 回升
    s0, s7 = T.s0_states(c), T.s7_dual_speed(c)
    first = lambda s: int(np.argmax(s == BEAR))                        # noqa: E731
    assert (s7 == BEAR).any() and first(s7) < first(s0)
    up0, up7 = int(np.argmax((s0 == BULL) & (np.arange(len(c)) > first(s0)))), \
        int(np.argmax((s7 == BULL) & (np.arange(len(c)) > first(s7))))
    assert up0 == up7                                                  # 回补规则与 T0 相同


def test_t8_uses_the_ma_itself_only_under_credit_stress():
    c = _path((300, 0.0), (5, -0.015), (40, 0.0))                      # 横盘后跌到 250 日线下约 1.5%（没到 −3%）
    ma = pd.Series(c).rolling(250).mean()
    assert ((c < ma) & (c > ma * 0.97)).iloc[-20:].all()               # 前提：在线下但在 T0 的转熊线上方
    f = pd.DataFrame({"baa": 3.0, "baa_ma250": 2.0}, index=c.index)    # 一直有信用压力
    assert (T.s8_credit_fast_exit(c, f) == BEAR).any() and not (T.s0_states(c) == BEAR).any()
    calm = pd.DataFrame({"baa": 2.0, "baa_ma250": 3.0}, index=c.index)
    assert np.array_equal(T.s8_credit_fast_exit(c, calm), T.s0_states(c))


def test_t9_scale_uses_only_the_training_window_and_band_is_clipped():
    rng = np.random.default_rng(5)
    c = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, 1500))), index=pd.bdate_range("2001-01-01", periods=1500))
    end = str(c.index[800].date())
    c2 = c.where(c.index <= end, c * np.exp(np.cumsum(rng.normal(0, 0.05, 1500))))   # 训练期之后波动大增
    assert T.t9_scale(c, end) == T.t9_scale(c2, end)
    band = np.clip(T.t9_scale(c2, end) * T.vol_ann(c2).to_numpy(float), T.VOL_LO, T.VOL_HI)
    assert np.nanmax(band) == T.VOL_HI and np.nanmin(band) >= T.VOL_LO
    const = T._state_machine(c, np.full(len(c), T.B))
    assert np.array_equal(const, ma_band(c, T.L, T.B, T.K))           # 带宽恒为 3% 时就是 T0


def test_t10_steps_one_half_zero_and_back():
    c = _path((300, 0.30), (40, -0.07), (40, -0.12), (80, 0.0), (60, 0.40))
    e = T.t10_half_expo(c).to_numpy()
    s = T.s0_states(c)
    seq = [x for i, x in enumerate(e) if i == 0 or x != e[i - 1]]
    assert seq[:4] == [1.0, 0.5, 0.0, 0.5] and seq[-1] == 1.0
    assert np.all(e[s == BEAR] <= 0.5) and np.all(e[s == BULL] >= 0.5)   # 熊市最多持一半，牛市至少一半
    assert np.array_equal(T.STATES2["T10"](c), s)                          # 牛熊状态 = T0


def test_t11_reenters_at_plus_20pct_and_trails_10pct_until_back_above_ma():
    c = _path((300, 0.30), (60, -0.40), (15, 0.25), (10, -0.12), (40, 0.0), (200, 0.60))
    s11, s0 = T.s11_v_reentry(c), T.s0_states(c)
    v = c.to_numpy()
    bear_at = int(np.argmax(s11 == BEAR))
    lo_i = bear_at + int(np.argmin(v[bear_at:360]))
    early = lo_i + int(np.argmax(s11[lo_i:] == BULL))
    assert v[early] >= v[lo_i:early + 1].min() * 1.20 and s0[early] == BEAR   # T0 还在熊市时提前回补
    back = early + int(np.argmax(s11[early:] == BEAR))
    assert back > early and v[back] <= v[early:back + 1].max() * 0.90         # 回落 10% 再离场
    assert s11[-1] == BULL


def test_engine_core_expo_default_is_unchanged_and_half_halves_the_core():
    from test_live_unified import CC, CFG, EX, P
    from qbreak.unified import UnifiedEngine
    ind, core_df, bear = _synthetic("JP", seed=7, n=260)
    ind = {**ind, "1655.T": core_df}
    bear = pd.Series(bear, index=core_df.index)
    start = core_df.index[60]
    run = lambda **kw: UnifiedEngine(ind, CFG, {"JP": P, "US": P}, EX, CC, bear={"US": bear}, **kw).run(start=start)  # noqa: E731
    base, ones = run(), run(core_expo={"US": pd.Series(1.0, index=core_df.index)})
    assert np.array_equal(base.equity.to_numpy(), ones.equity.to_numpy()) and base.state.core_trades == ones.state.core_trades
    half = run(core_expo={"US": pd.Series(0.5, index=core_df.index)})
    u = lambda r: max(int(x[3]) for x in r.state.core_trades if x[2] == "BUY")                   # noqa: E731
    assert 0.35 < u(half) / u(base) < 0.65
