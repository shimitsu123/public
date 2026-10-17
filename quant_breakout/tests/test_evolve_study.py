"""scripts/evolve_study.py（跟着时代自己更新）：预测只用之前的月份、决定作用于那个月 / 下一季、门槛选择与业种排名不偷看、随机对照的比例。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evolve_study as EV                                                    # noqa: E402


def _xy(n=80, seed=2):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2006-10-31", periods=n, freq="ME")
    X = pd.DataFrame(rng.normal(0, 1, (n, 3)), index=idx, columns=["a", "b", "c"])
    Y = pd.Series(0.8 * X["a"].to_numpy() + rng.normal(0, 0.3, n), index=idx, name="ex")
    return Y, X


def test_ridge_walk_uses_only_earlier_months():
    Y, X = _xy()
    p = EV.ridge_walk(Y, X, min_train=36)
    assert p.iloc[:36].isna().all() and p.iloc[36:].notna().all()
    k = 50
    Y2 = Y.copy()
    Y2.iloc[k:] += 100.0                                                        # 改第 k 个月及以后 → 第 k 个月的预测不变
    p2 = EV.ridge_walk(Y2, X, min_train=36)
    assert np.allclose(p.iloc[:k + 1], p2.iloc[:k + 1], equal_nan=True) and not np.isclose(p.iloc[k + 1], p2.iloc[k + 1])
    assert p.iloc[36:].corr(Y.iloc[36:]) > 0.5                                  # 学到了 a 的关系
    ph = EV.ridge_walk(Y, X, min_train=36, halflife=12)
    assert ph.iloc[36:].notna().all() and not np.allclose(ph.iloc[40:], p.iloc[40:])
    Xn = X.assign(d=np.nan)                                                     # 全是缺值的因素不挡住预测
    assert np.allclose(EV.ridge_walk(Y, Xn, min_train=36).iloc[36:], p.iloc[36:])


def test_month_scale_and_random_months():
    days = pd.bdate_range("2020-01-01", "2020-04-30")
    pred = pd.Series([-0.5, 0.2, np.nan, -0.1], index=pd.to_datetime(["2020-01-31", "2020-02-28", "2020-03-31", "2020-04-30"]))
    s = EV.month_scale(pred, days, 0.0)
    assert (s[days.month == 1] == 0).all() and (s[days.month == 2] == 1).all() and (s[days.month == 3] == 1).all()
    assert (s[days.month == 4] == 0).all()
    r = EV.random_month_scale(pred, days, 0.5, seed=1)
    assert set(r.unique()) <= {0.5, 1.0} and (r.groupby(days.month).first() == 0.5).sum() == 2   # 有预测的 3 个月里随机挑 2 个
    assert (r[days.month == 3] == 1).all() or (r[days.month == 3] == 0.5).all()


def test_choose_cut_and_schedule_no_lookahead():
    rng = np.random.default_rng(0)
    n = 400
    sig = pd.to_datetime("2010-01-01") + pd.to_timedelta(rng.integers(0, 365 * 3, n), unit="D")
    w5v = rng.uniform(0.3, 2.0, n)
    net = np.where(w5v >= 1.2, 2.0, -1.0) + rng.normal(0, 0.1, n)              # 门槛 1.2 最好
    T = pd.DataFrame({"sig_date": sig, "exit_date": sig + pd.Timedelta(days=20), "w5v": w5v, "net": net})
    assert EV.choose_cut(T, pd.Timestamp("2013-01-15")) == 1.2
    assert EV.choose_cut(T, pd.Timestamp("2010-01-10")) == 1.0                  # 还没有已平仓的交易 → 1.0
    flat = T.assign(net=1.0)
    assert EV.choose_cut(flat, pd.Timestamp("2013-01-15")) == 1.0              # 一样高 → 1.0
    days = pd.bdate_range("2012-01-02", "2013-12-31")
    s = EV.cut_schedule(T, days, "2012-07-01")
    assert (s[days < "2012-07-01"] == 1.0).all()
    q3 = s[(days >= "2012-07-01") & (days < "2012-10-01")]
    assert q3.nunique() == 1 and q3.iloc[0] == EV.choose_cut(T, days[days < "2012-07-01"][-1])   # 6 月末选的 → 7〜9 月用
    late = T[T["exit_date"] >= "2012-06-29"].assign(net=-50.0)                   # 6 月末之后才平仓的交易改掉 → 7〜9 月的门槛不变
    T2 = pd.concat([T[T["exit_date"] < "2012-06-29"], late])
    assert EV.cut_schedule(T2, days, "2012-07-01")[q3.index].equals(q3)


def test_sector_top_half_and_mask():
    idx = pd.date_range("2019-01-01", periods=16, freq="MS")
    R = pd.DataFrame({"S1": 3.0, "S2": 2.0, "S3": -1.0, "S4": -2.0}, index=idx)
    top = EV.sector_top_half(R)
    assert not top.iloc[:11].any().any() and top.iloc[11].tolist() == [True, True, False, False]
    days = pd.bdate_range("2019-12-02", "2020-02-28")
    fr = {"A.T": pd.DataFrame({"entry": True}, index=days), "B.T": pd.DataFrame({"entry": True}, index=days),
          "C.T": pd.DataFrame({"entry": True}, index=days)}
    m = EV.sector_mask(fr, {"A.T": "S1", "B.T": "S4"}, top)
    jan, dec = days.month == 1, days.month == 12
    assert m["A.T"][jan].all() and not m["B.T"][jan].any()                     # 1 月看 12 月末的排名（第 12 行，已有）
    assert m["A.T"][dec].all() and m["B.T"][dec].all()                         # 12 月看 11 月末（第 11 行，还没有排名）→ 照旧
    assert m["C.T"].all()                                                       # 没有业种 → 照旧
    early = EV.sector_mask(fr, {"B.T": "S4"}, top.iloc[:11].reindex(top.index).fillna(False))
    assert early["B.T"].all()                                                   # 还没有排名的月份 → 照旧
