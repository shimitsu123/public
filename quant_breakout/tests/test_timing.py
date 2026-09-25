"""顶底择时候选（qbreak/timing.py）：只用当时已公布的数据；各规则的逻辑与文档一致。"""
import numpy as np
import pandas as pd
import pytest

from qbreak import timing as T


def _data(n=900, seed=3):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2019-01-01", periods=n)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n))), index=days)
    close.iloc[500:560] *= np.linspace(1.0, 0.7, 60)             # 一段下跌，制造熊市
    close.iloc[560:] *= 0.7
    fx = pd.Series(110 + np.cumsum(rng.normal(0, 0.4, n)), index=days)
    vix = pd.Series(np.clip(18 + np.cumsum(rng.normal(0, 0.8, n)), 10, 60), index=days)
    vix.iloc[520:540] = 35.0
    baa = pd.Series(2.0 + np.cumsum(rng.normal(0, 0.02, n)), index=days)
    baa.iloc[515:560] += np.linspace(0, 1.0, 45)
    dgs10 = pd.Series(3 + np.cumsum(rng.normal(0, 0.02, n)), index=days)
    dgs3m = pd.Series(2 + np.cumsum(rng.normal(0, 0.02, n)), index=days)
    months = pd.date_range("2017-01-01", periods=60, freq="MS")
    un = pd.Series(np.r_[np.linspace(5, 3.5, 40), np.linspace(3.5, 6, 20)], index=months)
    return close, T.factor_frame(days, fx, vix, baa, dgs10, dgs3m, un), (days, fx, vix, baa, dgs10, dgs3m, un)


def test_unemployment_only_after_release():
    days = pd.bdate_range("2026-08-25", "2026-09-15")
    un = pd.Series([4.0, 4.3], index=pd.DatetimeIndex(["2026-07-01", "2026-08-01"]))
    a = T.monthly_available(un, days)
    assert a[pd.Timestamp("2026-09-09")] == 4.0 and a[pd.Timestamp("2026-09-10")] == 4.3   # 8 月值 9/10 起可用


def test_factor_lags():
    close, f, raw = _data()
    days, _, vix, baa = raw[:4]
    assert f["baa"].iloc[100] == baa.iloc[99] and f["vix"].iloc[100] == vix.iloc[100]      # 利差滞后 1 天，VIX 当天


@pytest.mark.parametrize("key", list(T.CANDIDATES))
def test_no_lookahead(key):
    """把第 t 天以后的数据全部改掉，第 t 天及以前的状态不变。"""
    close, f, raw = _data()
    full = T.CANDIDATES[key](close, f)
    t = 600
    days, fx, vix, baa, dgs10, dgs3m, un = raw
    cut = days[t]
    noise = lambda s: s.where(s.index <= cut, s * 1.7)                                      # noqa: E731
    published = un.index + pd.offsets.MonthBegin(1) + pd.Timedelta(days=9) <= cut          # 截止日已公布的月份
    un2 = un.where(published, 9.9)
    assert (~published).sum() > 0
    f2 = T.factor_frame(days, noise(fx), noise(vix), noise(baa), noise(dgs10), noise(dgs3m), un2)
    alt = T.CANDIDATES[key](noise(close), f2)
    assert full.iloc[:t + 1].equals(alt.iloc[:t + 1])


def test_rule_logic():
    close, f, _ = _data()
    tr = T.t0_trend(close)
    assert tr.any() and not tr.all()
    assert (T.t2_growth_trend(close, f) <= tr).all() and (T.t3_credit_confirm(close, f) <= tr).all()   # 「且」只会更少熊
    assert (T.t4_stress_exit(close, f) >= tr).all()                                                   # 「或」只会更多熊
    st = T.stress_state(f)
    on = st[st].index
    assert len(on) and f.loc[on[0], "vix"] >= 30 and f.loc[on[0], "baa_d20"] >= 0.30
    assert (f.loc[on, "vix"] >= 22).all()                                                              # 压力态期间 VIX 未跌破 22
    m = T.t5_momentum(close)
    changes = m.index[m.ne(m.shift()) & m.shift().notna()]
    assert all(d == m.index[m.index.to_period("M") == d.to_period("M")].max() for d in changes)       # 只在月末切换


def test_persist_needs_k_days():
    raw = pd.Series([False] * 5 + [True] * 4 + [False] + [True] * 5 + [False] * 2)
    out = T._persist(raw, 5)
    assert not out.iloc[:14].any() and out.iloc[14] and out.iloc[15:].all()   # 连续 5 天才切到熊；之后 2 天不回切


def test_momentum_ignores_unfinished_month():
    close, _, _ = _data()
    part = close[close.index <= "2021-06-17"]                    # 6 月还没结束
    m = T.t5_momentum(part)
    assert m.loc["2021-06-01":].nunique() == 1 and m.loc["2021-06-17"] == m.loc["2021-05-31"]
