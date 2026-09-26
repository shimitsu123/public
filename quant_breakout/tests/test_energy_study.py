"""scripts/energy_study.py：z 分数只用当时为止、业种顺风分、按月末取值、跳过买点、新仓系数、θ 的选法、判定、同期表。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import energy_study as ES                                                     # noqa: E402


def test_expanding_z_uses_only_past():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2000-01-31", periods=80, freq="ME")
    s = pd.Series(rng.normal(size=80), index=idx)
    z = ES.expanding_z(s, 36)
    assert z.iloc[:35].isna().all() and z.iloc[35:].notna().all()
    s2 = s.copy()
    s2.iloc[60:] += 100                                                       # 改后面的值，前面的 z 不变
    z2 = ES.expanding_z(s2, 36)
    assert np.allclose(z.iloc[:60], z2.iloc[:60], equal_nan=True)
    k = 50
    want = (s.iloc[k] - s.iloc[:k + 1].mean()) / s.iloc[:k + 1].std()
    assert abs(z.iloc[k] - want) < 1e-12


def test_industry_scores_mean_of_signed_z():
    idx = pd.date_range("2010-01-31", periods=3, freq="ME")
    Z = pd.DataFrame({"a": [1.0, 2.0, np.nan], "b": [0.5, np.nan, np.nan], "c": [3.0, 3.0, 3.0]}, index=idx)
    pairs = [("a", "X", 1), ("b", "X", -1), ("c", "Y", 1), ("c", "T4", 1)]
    S = ES.industry_scores(Z, pairs, {"X", "Y"})
    assert list(S.columns) == ["X", "Y"]                                      # 主题（不在业种里）不算
    assert S.loc[idx[0], "X"] == (1.0 - 0.5) / 2 and S.loc[idx[1], "X"] == 2.0 and np.isnan(S.loc[idx[2], "X"])
    assert (S["Y"] == 3.0).all()


def test_asof_month_and_month_factor():
    s = pd.Series([1.0, -5.0], index=pd.DatetimeIndex(["2010-01-31", "2010-02-28"]))
    d = pd.DatetimeIndex(["2010-01-29", "2010-02-01", "2010-02-27", "2010-03-01"])
    v = ES.asof_month(s, d)
    assert np.isnan(v[0]) and v[1] == 1.0 and v[2] == 1.0 and v[3] == -5.0  # 2 月底的值 3 月起才用
    f = ES.month_factor(s, 0.0, d)
    assert list(f) == [1.0, 1.0, 1.0, ES.HALF]


def test_skip_entries_only_below_minus_theta():
    idx = pd.bdate_range("2010-02-01", periods=5)
    df = pd.DataFrame({"entry": [True, False, True, True, True]}, index=idx)
    ind = {"A.T": df, "B.T": df.copy(), "C.T": df.copy()}
    score = pd.DataFrame({"鉄鋼": [-2.0], "化学": [-0.4]}, index=pd.DatetimeIndex(["2010-01-31"]))
    out, n = ES.skip_entries(ind, {"A.T": "鉄鋼", "B.T": "化学"}, score, 1.0)
    assert n == 4 and not out["A.T"]["entry"].any()
    assert out["B.T"]["entry"].sum() == 4 and out["C.T"]["entry"].sum() == 4  # 分数不够低 / 没有业种 → 不动
    assert df["entry"].sum() == 4                                             # 原表没被改


def _st(c, dd=-30.0):
    return {"cagr": 10.0, "dd": dd, "calmar": c}


def test_pick_theta_and_decide():
    base = {"all": _st(0.36), "disc": _st(0.26), "val": _st(0.47), "v1": _st(0.3), "v2": _st(0.6)}
    res = {0.1: {**base, "disc": _st(0.27)}, 0.2: {**base, "disc": _st(0.30)}}
    th, ok = ES.pick_theta(res, base)
    assert th == 0.2 and ok
    th, ok = ES.pick_theta({0.1: {**base, "disc": _st(0.28)}}, base)
    assert th == 0.1 and not ok                                               # +0.02 < +0.03
    good = {"all": _st(0.40), "disc": _st(0.30), "val": _st(0.53), "v1": _st(0.31), "v2": _st(0.61)}
    assert ES.decide_one(good, base) == []
    bad = {**good, "v2": _st(0.55), "all": _st(0.40, dd=-33.0)}
    f = ES.decide_one(bad, base)
    assert any("验证期后半" in x for x in f) and any("回撤" in x for x in f)


def test_sync_table_flags_consistent_relation():
    rng = np.random.default_rng(1)
    months = pd.date_range("2006-10-31", periods=200, freq="ME")
    x = pd.Series(rng.normal(size=200), index=months)
    Y = pd.DataFrame({"good": 2.0 * x + rng.normal(scale=0.5, size=200), "noise": rng.normal(size=200)}, index=months)
    spans = {"H1": (months[0], months[99]), "H2": (months[100], months[-1])}
    T = ES.sync_table(pd.DataFrame({"s": x}), Y, months, spans)
    g = T.set_index("target")
    assert g.loc["good", "both"] and g.loc["good", "t"] > 5 and not g.loc["noise", "both"]


def test_pairs_and_candidates_are_fixed():
    assert len(ES.PAIRS) == 26 and all(s in ES.E.SOURCES for s, _, _ in ES.PAIRS)
    assert set(ES.CANDS) == {"K1", "K2", "K3", "K4", "K5"} and all(v in ES.E.SOURCES for v in ES.KSRC.values())
