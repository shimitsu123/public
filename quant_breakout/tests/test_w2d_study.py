"""W2d（周线量比的日均版，scripts/w2d_study.py 登记检验；qbreak/mtf.weekly_volume_ratio_per_day）：
连休周不再压低量比、周都一样长时与合计版相同、不偷看；「用到的那一周有几天」按完成日口径；判定规则按登记的门槛。"""
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import w2d_study as W                                                        # noqa: E402
from qbreak.calendar_jp import next_trading_day                              # noqa: E402
from qbreak.mtf import live_calendar, weekly_volume_ratio, weekly_volume_ratio_per_day   # noqa: E402


def _tse(start=dt.date(2026, 4, 1), end=dt.date(2026, 9, 29), vol=1e6, seed=None):
    idx, x = [], start
    while x < end:
        x = next_trading_day(x)
        idx.append(pd.Timestamp(x))
    v = np.full(len(idx), vol) if seed is None else np.random.default_rng(seed).lognormal(np.log(vol), 0.3, len(idx))
    return pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": v}, index=pd.DatetimeIndex(idx))


def test_short_week_no_longer_depresses_ratio():
    df = _tse()
    cal = live_calendar(df.index)
    a, b = weekly_volume_ratio(df, cal), weekly_volume_ratio_per_day(df, cal)
    assert abs(a.loc["2026-09-29"] - 2 / 4.8) < 1e-9                              # 合计版：2 天周 ÷ 前 10 周平均 4.8 天
    assert abs(b.loc["2026-09-29"] - 1.0) < 1e-12                                # 日均版：每天一样多 → 1.0
    assert abs(b.loc["2026-09-18"] - 1.0) < 1e-12 and a.loc["2026-09-18"] > 1.0  # 前 10 周里有短周 → 合计版偏高


def test_same_as_sum_when_all_weeks_have_five_days_and_no_lookahead():
    idx = pd.bdate_range("2025-01-06", periods=200)                              # 研究口径的日历：每周 5 天
    v = np.random.default_rng(3).lognormal(np.log(1e6), 0.4, len(idx))
    df = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": v}, index=idx)
    a, b = weekly_volume_ratio(df, idx), weekly_volume_ratio_per_day(df, idx)
    m = a.notna()
    assert m.sum() > 100 and np.allclose(a[m], b[m])
    cut = idx[120]
    b2 = weekly_volume_ratio_per_day(df.loc[:cut], idx)                           # 截掉之后的数据（日历不变）
    assert np.allclose(b.loc[:cut].dropna(), b2.dropna().loc[:cut])


def test_used_week_days_follow_completion_days():
    df = _tse()
    wd = W.week_days(df.index)
    assert wd.loc["2026-09-25"] == 2 and wd.loc["2026-09-18"] == 5
    got = W.used_week_days(wd, pd.DatetimeIndex(["2026-09-24", "2026-09-25", "2026-09-29"]))
    assert list(got) == [5, 2, 2]                                                # 9/25 收盘这一周完成；9/24 还用上一周


def test_keep_and_groups():
    assert list(W.keep(np.array([np.nan, 0.99, 1.0, 1.5]))) == [True, False, True, True]
    assert [W.group_of(True, True), W.group_of(True, False), W.group_of(False, True), W.group_of(False, False)] == list(W.GROUPS)


def _acct(ce, cj, cz, de=-30.0, dj=-30.0):
    def run(c, d, era):
        return {era: {"calmar": c, "dd": d}}
    return {"E": {"W2": run(0.30, -30.0, "E"), "W2d": run(ce, de, "E")},
            "J": {"W2": run(0.40, -30.0, "J"), "W2d": run(cj, dj, "J")},
            "Z": {"W2": run(0.20, -30.0, "Z"), "W2d": run(cz, -30.0, "Z")}}


def test_verdict_rules():
    solo_ok = {"换进来": {"n": 40, "mean": 0.8}, "换出去": {"n": 45, "mean": 0.2}}
    assert W.verdict(_acct(0.32, 0.41, 0.20), solo_ok) == (True, [])
    ok, f = W.verdict(_acct(0.33, 0.385, 0.20), solo_ok)                         # J 差 −0.015 < −0.01
    assert not ok and any(x.startswith("① J") for x in f)
    ok, f = W.verdict(_acct(0.31, 0.405, 0.20), solo_ok)                         # 差相加 +0.015 < +0.02
    assert not ok and any("差 +0.015" in x for x in f)
    ok, f = W.verdict(_acct(0.33, 0.42, 0.17), solo_ok)                          # Z 差 −0.03
    assert not ok and any(x.startswith("③") for x in f)
    ok, f = W.verdict(_acct(0.33, 0.42, 0.20, de=-32.5), solo_ok)                # E 回撤深 2.5 pp
    assert not ok and any(x.startswith("② E") for x in f)
    ok, f = W.verdict(_acct(0.33, 0.42, 0.20), {"换进来": {"n": 40, "mean": 0.1}, "换出去": {"n": 45, "mean": 0.2}})
    assert not ok and any(x.startswith("④") for x in f)
    assert W.verdict(_acct(0.33, 0.42, 0.20), {"换进来": {"n": 12, "mean": -5.0}, "换出去": {"n": 45, "mean": 0.2}})[0]   # < 20 笔不判
    assert W.verdict(_acct(0.33, 0.42, 0.20), {"换进来": {"n": 40, "mean": -5.0}, "换出去": {"n": 19, "mean": 0.2}})[0]
