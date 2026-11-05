"""scripts/pressure_study.py（股市压力指数）：分项只用当时能知道的数据（月度用上个月、日本利率用前一天）、涨幅跌回两年低点 = 0、
分位窗口与最少月数、综合需要 ≥ 4 个分项、目标（之后 H 天内最低 ≤ −10%）、按段重抽可重现、事先写定的判定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pressure_study as PS                                                  # noqa: E402


def test_constants():
    assert (PS.HS, PS.H_MAIN, PS.DROP) == ((60, 120, 250, 500), 250, -10.0)
    assert (PS.RUNUP_D, PS.MA_D, PS.VOL_D, PS.BR_MA) == (500, 250, 60, 200)
    assert (PS.WIN_M, PS.MIN_M, PS.MIN_COMP, PS.BR_MIN_N) == (120, 60, 4, 100)
    assert (PS.BLOCK_M, PS.N_BOOT, PS.SEED, PS.US_START, PS.US_SPLIT) == (24, 2000, 20260929, "1960-01-01", "1993-01-01")
    assert PS.COMP == ["runup", "ma", "rate", "curve", "credit", "calm", "breadth"]


def test_price_parts_runup_releases_on_fall_and_no_lookahead():
    days = pd.bdate_range("2000-01-03", periods=1600)
    c = pd.Series(np.linspace(100, 200, len(days)), index=days)
    c.iloc[1200:] = 80.0                                                     # 跌到两年最低之下
    pp = PS.price_parts(c)
    assert pp["runup"].iloc[1100] > 0.1 and np.isclose(pp["runup"].iloc[1300], 0.0)   # 涨 → 加压；跌回两年低点 → 0
    assert pp["ma"].iloc[1100] > 0 and pp["ma"].iloc[1300] < 0
    c2 = c.copy()
    c2.iloc[1101:] = 999.0                                                   # 改掉以后的数据
    assert np.allclose(PS.price_parts(c2).iloc[:1101].fillna(-1), pp.iloc[:1101].fillna(-1))


def test_month_and_day_lags():
    m = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]))
    d = pd.DatetimeIndex(["2020-03-31", "2020-02-28"])
    assert list(PS.month_lag1(m, d)) == [2.0, 1.0]                           # 3 月底用 2 月的月均
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-03-30", "2020-03-31"]))
    assert list(PS.day_lag1(s, pd.DatetimeIndex(["2020-03-31"]))) == [1.0]   # 严格早于当天
    assert list(PS.asof(s, pd.DatetimeIndex(["2020-03-31"]))) == [2.0]


def test_rolling_pct_and_scores():
    x = pd.Series(np.arange(200, dtype=float))
    p = PS.rolling_pct(x)
    assert np.isnan(p.iloc[58]) and p.iloc[59] == 100.0 and p.iloc[150] == 100.0   # 一直在涨 → 100
    y = pd.Series(np.r_[np.arange(100, dtype=float), -1.0])
    assert PS.rolling_pct(y).iloc[-1] < 1.0
    idx = pd.date_range("1990-01-31", periods=100, freq="ME")
    raw = pd.DataFrame({k: np.arange(100, dtype=float) for k in ["runup", "ma", "rate"]}, index=idx)
    S = PS.scores(raw)
    assert S["P_price"].iloc[-1] == 100.0 and np.isnan(S["P_all"].iloc[-1])  # 只有 3 个分项 → 综合压力不算
    raw["calm"] = 0.0
    assert PS.scores(raw)["P_all"].iloc[-1] == 100.0                         # 4 个 → 算（常数分项的分位 = 100）


def test_breadth_share():
    days = pd.bdate_range("2000-01-03", periods=300)
    up = pd.Series(np.linspace(1, 2, 300), index=days)
    C = pd.DataFrame({"a": up, "b": up, "c": up[::-1].to_numpy(), "d": up})
    s = PS.breadth_share(C)
    assert np.isnan(s.iloc[100]) and s.iloc[-1] == 75.0
    assert np.isnan(PS.breadth_share(C, min_n=5).iloc[-1])


def test_targets():
    days = pd.bdate_range("2000-01-03", periods=400)
    c = pd.Series(100.0, index=days)
    c.iloc[100:130] = 85.0
    T = PS.targets(c, pd.DatetimeIndex([days[50], days[200], days[390]]), hs=(60,))
    assert T["ev60"].iloc[0] == 1.0 and np.isclose(T["min60"].iloc[0], -15.0)
    assert T["ev60"].iloc[1] == 0.0 and np.isnan(T["ev60"].iloc[2])          # 不够 60 天 → 空


def test_auc_boot_and_verdict():
    rng = np.random.default_rng(0)
    s = pd.Series(rng.normal(size=400))
    e = pd.Series((s + rng.normal(size=400) > 0.5).astype(float))
    a = PS.auc(s, e)
    ci = PS.boot_auc(s, e, n_boot=300)
    assert a > 0.7 and ci == PS.boot_auc(s, e, n_boot=300) and ci[0] < a < ci[1]
    ok = {"auc": 0.65, "lo": 0.55, "hi": 0.75, "half1": 0.6, "half2": 0.62}
    assert PS.verdict(ok, {"auc": 0.58}) == "有预警力"
    assert PS.verdict(ok, {"auc": 0.52}) == "没有预警力"
    assert PS.verdict({**ok, "half2": 0.49}, {"auc": 0.6}) == "没有预警力"
    assert PS.verdict({"auc": 0.35, "lo": 0.28, "hi": 0.45}, {"auc": 0.4}) == "方向相反"
    assert PS.verdict({"auc": 0.35, "lo": 0.28, "hi": 0.52}, {"auc": 0.4}) == "没有预警力"


def test_quintiles_and_now_reading():
    idx = pd.date_range("1990-01-31", periods=200, freq="ME")
    S = pd.DataFrame({"P_price": np.linspace(0, 100, 200), "P_all": np.linspace(0, 100, 200)}, index=idx)
    T = pd.DataFrame({"ev250": (np.arange(200) >= 120).astype(float), "ret250": np.ones(200)}, index=idx)
    q = PS.quintiles(S["P_all"], T)
    assert [x["event"] for x in q] == [0.0, 0.0, 0.0, 100.0, 100.0] and sum(x["n"] for x in q) == 200
    raw = pd.DataFrame({k: np.arange(200, dtype=float) for k in PS.COMP}, index=idx)
    cur = pd.Series({k: 1000.0 for k in PS.COMP})
    n = PS.now_reading(raw, cur, S, T)
    assert n["P_all"] == 100.0 and n["P_all_q"]["q"] == 5 and n["P_all_q"]["event"] == 100.0
