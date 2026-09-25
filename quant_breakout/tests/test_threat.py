"""大事件威胁指数（qbreak/threat.py）：只用当时已公布的数据；百分位 / 未来回撤 / AUC 计算正确。"""
import numpy as np
import pandas as pd

from qbreak import threat as TH


def test_expanding_pct_basic():
    x = pd.Series([3.0, 1.0, 2.0, np.nan, 5.0])
    p = TH.expanding_pct(x, min_n=1)
    assert p.iloc[0] == 0.5 and p.iloc[1] == 0.25 and abs(p.iloc[2] - 0.5) < 1e-12   # [1,2,3] 里的 2 → 中间
    assert np.isnan(p.iloc[3]) and p.iloc[4] == (3 + 4) / 2 / 4
    assert TH.expanding_pct(x, min_n=4).notna().sum() == 1


def _inputs(n=1500, seed=1):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2010-01-01", periods=n)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))), index=days)
    mk = lambda base, sc: pd.Series(base + np.cumsum(rng.normal(0, sc, n)), index=days)   # noqa: E731
    months = pd.date_range("2008-01-01", periods=80, freq="MS")
    un = pd.Series(5 + np.cumsum(rng.normal(0, 0.1, 80)), index=months)
    return days, close, mk(20, 0.5).clip(9), mk(2, 0.02), mk(3, 0.03), mk(2, 0.03), mk(70, 0.8).clip(10), un, \
        mk(110, 0.4), mk(1, 0.01)


def test_no_lookahead():
    days, close, vix, baa, d10, d3, wti, un, fx, jgb = _inputs()
    raw = TH.raw_features(days, close, vix, baa, d10, d3, wti, un, fx, jgb)
    idx, _ = TH.threat_index(raw, TH.JP_COLS, min_n=200)
    t = 1200
    cut = days[t]
    alt = lambda s: s.where(s.index <= cut, s * 1.5 + 3)                                   # noqa: E731
    published = un.index + pd.offsets.MonthBegin(1) + pd.Timedelta(days=9) <= cut
    raw2 = TH.raw_features(days, alt(close), alt(vix), alt(baa), alt(d10), alt(d3), alt(wti), un.where(published, 99.0),
                           alt(fx), alt(jgb))
    idx2, _ = TH.threat_index(raw2, TH.JP_COLS, min_n=200)
    assert idx.iloc[:t + 1].equals(idx2.iloc[:t + 1]) and idx.iloc[t] == idx.iloc[t]    # 前 t 天完全相同、且有值


def test_forward_drawdown_and_auc():
    c = pd.Series([100, 90, 95, 80, 120, 110.0])
    fd = TH.forward_drawdown(c, 2)
    assert abs(fd.iloc[0] - (90 / 100 - 1)) < 1e-12 and abs(fd.iloc[2] - (80 / 95 - 1)) < 1e-12 and fd.iloc[4:].isna().all()
    s = pd.Series([0.1, 0.2, 0.8, 0.9])
    assert TH.auc(s, pd.Series([0, 0, 1, 1])) == 1.0 and TH.auc(s, pd.Series([1, 1, 0, 0])) == 0.0
    assert TH.auc(pd.Series([0.5, 0.5]), pd.Series([0, 1])) == 0.5


def test_us_asof_for_jp_uses_previous_us_close():
    us = pd.Series([1.0, 2.0, 3.0], index=pd.DatetimeIndex(["2026-09-23", "2026-09-24", "2026-09-25"]))
    jp = pd.DatetimeIndex(["2026-09-24", "2026-09-25", "2026-09-28"])
    v = TH.us_asof_for_jp(us, jp)
    assert list(v) == [1.0, 2.0, 3.0]                                  # 9/28（周一）早上已知的是 9/25（周五）的美国收盘
