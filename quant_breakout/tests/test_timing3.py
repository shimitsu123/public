"""顶底择时第三轮候选（qbreak/timing.py 的 T12〜T15）：只用当天为止的数据；确认条件缺席时退回 T0。"""
import numpy as np
import pandas as pd
import pytest

from qbreak import timing as T
from qbreak.bullbear import BEAR, BULL

from test_timing import _data
from test_timing2 import _path


def _with_other(close, f, other):
    f = f.copy()
    ma = other.rolling(T.L).mean()
    f["other_below"] = (other < ma).reindex(close.index).fillna(False)
    return f


@pytest.mark.parametrize("key", list(T.STATES3))
def test_no_lookahead_third_round(key):
    """把第 t 天以后的价格、因子、另一个市场全部改掉，第 t 天及以前的状态不变。"""
    close, f, raw = _data()
    days, fx, vix, baa, dgs10, dgs3m, un = raw
    rng = np.random.default_rng(11)
    other = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.012, len(days)))), index=days)
    t = 600
    cut = days[t]
    noise = lambda s: s.where(s.index <= cut, s * 1.7)                                      # noqa: E731
    f2 = T.factor_frame(days, noise(fx), noise(vix), noise(baa), noise(dgs10), noise(dgs3m), un)
    full = T.STATES3[key](close, _with_other(close, f, other))
    alt = T.STATES3[key](noise(close), _with_other(close, f2, noise(other)))
    assert np.array_equal(full[:t + 1], alt[:t + 1])


def _crash():
    return _path((300, 0.30), (12, -0.16), (60, 0.0), (120, 0.40))       # 急跌：T7 的快速条件会先于 T0 触发


def test_t12_needs_credit_and_t13_needs_the_other_market():
    c = _crash()
    s0, s7 = T.s0_states(c), T.s7_dual_speed(c)
    first = lambda s: int(np.argmax(s == BEAR))                        # noqa: E731
    assert first(s7) < first(s0)                                       # 前提：T7 比 T0 早
    on = pd.DataFrame({"baa": 3.0, "baa_ma250": 2.0, "other_below": True}, index=c.index)
    off = pd.DataFrame({"baa": 2.0, "baa_ma250": 3.0, "other_below": False}, index=c.index)
    assert np.array_equal(T.s12_fast_credit(c, on), s7) and np.array_equal(T.s13_fast_global(c, on), s7)
    assert np.array_equal(T.s12_fast_credit(c, off), s0) and np.array_equal(T.s13_fast_global(c, off), s0)


def test_t14_early_reentry_only_when_trend_turned_up():
    c = _path((300, 0.30), (60, -0.40), (15, 0.25), (10, -0.12), (40, 0.0), (200, 0.60))
    never = T._state_machine(c, np.full(len(c), T.B), early=True, early_ok=np.zeros(len(c), bool))
    assert np.array_equal(never, T.s0_states(c))                       # 趋势从不转好 → 与 T0 相同
    always = T._state_machine(c, np.full(len(c), T.B), early=True, early_ok=np.ones(len(c), bool))
    assert np.array_equal(always, T.s11_v_reentry(c))                  # 趋势总是好 → 与 T11 相同
    s14, s0, ok = T.s14_v_trend(c), T.s0_states(c), T.trend_up(c)
    early = np.where((s14 == BULL) & (s0 == BEAR))[0]
    assert len(early) and ok[early[0]]                                 # 提前回补的那天趋势确实转好


def test_trend_up_uses_only_past_closes():
    c = _path((200, 0.2), (100, -0.1))
    a = T.trend_up(c)
    c2 = c.copy()
    c2.iloc[250:] *= 3.0
    assert np.array_equal(a[:250], T.trend_up(c2)[:250])


def test_t15_combines_t12_exit_and_t14_reentry():
    c = _path((300, 0.30), (12, -0.16), (60, -0.30), (15, 0.25), (60, 0.30), (120, 0.40))
    on = pd.DataFrame({"baa": 3.0, "baa_ma250": 2.0}, index=c.index)
    off = pd.DataFrame({"baa": 2.0, "baa_ma250": 3.0}, index=c.index)
    assert np.array_equal(T.s15_both(c, off), T.s14_v_trend(c))        # 没有信用压力 → 离场同 T0，只剩回补的改动
    fast = int(np.argmax(T.s15_both(c, on) == BEAR))
    assert fast == int(np.argmax(T.s12_fast_credit(c, on) == BEAR))    # 有信用压力 → 离场同 T12
