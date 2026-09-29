"""大跌入场的深度 × 时代主线的关联（scripts/crash_mainline_study.py）：13 周线只用已完成的周线、多数个股的比例、同一段只算第一次、
反弹开始与暂时顶的定义、之后涨跌的下标、季度主线、去掉自己的主线篮子、超额、秩相关、挑选与判定、登记的常数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import crash_mainline_study as CM                                            # noqa: E402


def _weeks(vals, start="2020-01-06"):
    c = np.repeat(np.asarray(vals, float), 5)
    return pd.Series(c, index=pd.bdate_range(start, periods=len(c)))


def test_line_dev_uses_completed_weeks():
    s = _weeks([100.0] * 20 + [80.0, 80.0])                                  # 数据里最后一周之后没有交易日 → 不算完成（mtf 的口径）
    dv = CM.line_dev(s)
    mon21 = 20 * 5                                                           # 第 21 周周一：线 = 前 13 根已完成周线 = 100
    assert np.isclose(dv.iloc[mon21], -20.0)
    fri21 = mon21 + 4                                                        # 第 21 周周五完成：线含这一周（12 × 100 + 80）/ 13
    assert np.isclose(dv.iloc[fri21], (80 / ((12 * 100 + 80) / 13) - 1) * 100)
    assert dv.iloc[:12 * 5 + 4].isna().all() and np.isfinite(dv.iloc[12 * 5 + 4])   # 第 13 周完成之前没有线
    assert np.isclose(dv.iloc[-1], (80 / ((12 * 100 + 80) / 13) - 1) * 100)   # 最后一周（没完成）还用上一根的线


def test_breadth():
    DEV = np.array([[-20.0, -10.0, np.nan, -16.0], [0.0, 1.0, 2.0, 3.0]])
    M = np.array([[True, True, True, False], [True, True, True, True]])
    b = CM.breadth(DEV, M, -15.0, min_n=2)
    assert np.isclose(b[0], 50.0) and b[1] == 0.0                            # 非成员（第 4 只）不算、NaN 不算
    assert np.isnan(CM.breadth(DEV, M, -15.0, min_n=3)[0])


def test_depth_events_first_in_episode():
    dv = np.array([1.0, -7.0, -10.0, -12.0, -3.0, 0.5, -9.5, -2.0])
    B = np.array([0.0, 10.0, 30.0, 40.0, 5.0, 0.0, 10.0, 0.0])
    assert CM.depth_events(dv, None, -9.0, 0).tolist() == [2, 6]            # 回到 ≥ 0（第 5 天）之后才算新的一段
    assert CM.depth_events(dv, B, -9.0, 35.0).tolist() == [3]                # 比例要求：第 3 天才同时成立；第 6 天比例不够
    assert CM.depth_events(dv, B, -12.0, 0).tolist() == [3]


def test_rebound_anchor():
    c = np.array([100.0, 95.0, 90.0, 92.0, 94.6, 96.0])
    assert CM.rebound_anchor(c, 0, 5.0, 60) == 4                             # 90 × 1.05 = 94.5
    assert CM.rebound_anchor(c, 0, 5.0, 3) is None
    assert CM.rebound_anchor(np.array([100.0, 99.0, 98.0]), 0) is None


def test_top_events():
    c = np.r_[np.linspace(100, 120, 30), [118.0, 116.0, 113.9, 113.0, 112.0], np.linspace(112, 130, 70), [123.0]]
    dev = np.where(np.arange(len(c)) < 30, 7.0, 0.0)
    ev = CM.top_events(c, dev, hot=6.0, pull=5.0, look=20, reset=60)
    assert ev.tolist() == [32]                                               # 120 × 0.95 = 114 → 113.9 那天；之后乖离不够、不再算
    dev2 = np.full(len(c), 7.0)
    ev2 = CM.top_events(c, dev2, hot=6.0, pull=5.0, look=20, reset=60)
    assert ev2[0] == 32 and len(ev2) == 2 and ev2[1] == len(c) - 1          # 创 60 日新高之后重新算；130 × 0.95 = 123.5 ≥ 123


def test_forward_and_mae():
    c = np.array([10.0, 11.0, 12.0, 9.0, 13.0, 14.0])
    R = CM.fwd_all(c, 2)
    assert np.isclose(R[0], (9.0 / 11.0 - 1) * 100) and np.isnan(R[3:]).all()
    assert np.isclose(CM.mae(c, 0, 2), (9.0 / 11.0 - 1) * 100) and np.isnan(CM.mae(c, 4, 2))


def test_last_quarter():
    assert CM.last_quarter("2020-04-01") == (pd.Timestamp("2020-01-01"), pd.Timestamp("2020-03-31"))
    assert CM.last_quarter("2020-03-31") == (pd.Timestamp("2019-10-01"), pd.Timestamp("2019-12-31"))
    assert CM.last_quarter("2026-09-26") == (pd.Timestamp("2026-04-01"), pd.Timestamp("2026-06-30"))


def test_group_scores_and_mainline():
    days = pd.bdate_range("2020-01-01", "2020-04-10")
    n = len(days)
    REL = np.zeros((n, 7))
    REL[:, 0:3] = 0.1                                                        # 业种 A 三只每天 +0.1
    REL[:, 3:6] = -0.1
    REL[:, 6] = 0.5                                                          # 业种 C 只有一只 → 成员不够 3 只，不算
    groups = np.array(["A", "A", "A", "B", "B", "B", "C"], dtype=object)
    ml, sc, (qa, qb) = CM.mainline_at(REL, days, groups, "2020-04-02", 1)
    q1 = ((days >= "2020-01-01") & (days <= "2020-03-31")).sum()
    assert ml == ["A"] and np.isclose(sc["A"], 0.1 * q1) and "C" not in sc and qb == pd.Timestamp("2020-03-31")
    assert CM.mainline_at(REL, days, groups, "2020-04-02", 1, min_group=1)[0] == ["C"]


def test_assoc_leave_one_out():
    rng = np.random.default_rng(0)
    f = rng.normal(size=150)
    REL = np.column_stack([f + rng.normal(scale=0.1, size=150), f + rng.normal(scale=0.1, size=150), rng.normal(size=150), f])
    groups = np.array(["A", "A", "B", "B"], dtype=object)
    c = CM.assoc(REL, groups, ["A"], 150, win=126, min_obs=100)
    assert c[0] > 0.9 and c[1] > 0.9 and abs(c[2]) < 0.3 and c[3] > 0.9     # 主线成员的篮子不含自己
    y0 = REL[24:150, 1]
    assert np.isclose(c[0], np.corrcoef(REL[24:150, 0], y0)[0, 1])


def test_xs_excess():
    C = np.array([[10.0, 20.0, 30.0], [10.0, 20.0, 30.0], [11.0, 20.0, np.nan], [12.0, 18.0, 33.0]])
    M = np.array([[True, True, True]] * 4)
    x = CM.xs_excess(C, M, 0, 2)                                             # 第 1 天收盘买、第 3 天收盘：+20%、−10%、+10%
    assert np.allclose(x, np.array([20.0, -10.0, 10.0]) - 20 / 3)
    M2 = M.copy()
    M2[0, 2] = False
    assert np.isnan(CM.xs_excess(C, M2, 0, 2)[2]) and np.isnan(CM.xs_excess(C, M, 1, 5)).all()


def test_spearman_and_partial():
    x = np.array([1.0, 2.0, 3.0, 4.0, np.nan, 6.0])
    assert np.isclose(CM.spearman(x, x ** 3), 1.0) and np.isnan(CM.spearman(np.ones(5), np.arange(5.0)))
    rng = np.random.default_rng(1)
    z = rng.normal(size=300)
    a, b = z + rng.normal(scale=0.3, size=300), z + rng.normal(scale=0.3, size=300)
    assert CM.spearman(a, b) > 0.7 and abs(CM.partial_spearman(a, b, z)) < 0.2  # 控制共同因子之后没有关系


def test_pick_best():
    cells = {(-6.0, 0.0): {"n": 30, "lo": 0.5}, (-9.0, 20.0): {"n": 20, "lo": 1.2}, (-12.0, 0.0): {"n": 12, "lo": 1.2},
             (-20.0, 0.0): {"n": 3, "lo": 5.0}}
    assert CM.pick_best(cells) == (-9.0, 20.0)                               # 同分取浅的；段数不够 8 的不算
    assert CM.pick_best({(-20.0, 0.0): {"n": 3, "lo": 5.0}}) is None


def _s(n=20, mean=1.0, lo=0.2, hi=2.0, pos=70.0, neg=30.0):
    return {"n": n, "mean": mean, "lo": lo, "hi": hi, "pos": pos, "neg": neg}


def test_verdicts_and_decide():
    eras = {"Z": {"n": 5, "mean": 0.5}, "E": {"n": 11, "mean": 1.0}, "J": {"n": 1, "mean": -3.0}}
    ok = CM.s1_verdict(_s(), eras, _s(), _s(), _s(), None)
    assert ok["pass"]                                                        # 段数 < 2 的时期不看
    assert not CM.s1_verdict(_s(lo=-0.1), eras, _s(), _s(), _s(), None)["pass"]
    assert not CM.s1_verdict(_s(), {**eras, "E": {"n": 11, "mean": -0.1}}, _s(), _s(), _s(), None)["pass"]
    assert not CM.s1_verdict(_s(), eras, _s(lo=-0.1), _s(), _s(), None)["pass"]
    assert not CM.s1_verdict(_s(), eras, _s(), _s(), _s(), _s(mean=-0.5))["pass"]
    assert CM.s2_verdict(_s(), _s())["pass"] and not CM.s2_verdict(_s(pos=55.0), _s())["pass"]
    assert not CM.s2_verdict(_s(), _s(lo=-0.01))["pass"]
    neg = _s(mean=-0.1, lo=-0.2, hi=-0.01, pos=30.0, neg=70.0)
    assert CM.s3_verdict(neg, neg)["pass"] and not CM.s3_verdict({**neg, "hi": 0.01}, neg)["pass"]
    assert (CM.decide(True, True), CM.decide(True, False), CM.decide(False, True), CM.decide(False, False)) == ("B", "C", "C", "A")


def test_registered_constants():
    assert (CM.LINE_N, CM.STK_DEV, CM.DEPTHS, CM.BREADTHS) == (13, -15.0, (-6.0, -9.0, -12.0, -15.0, -20.0), (0.0, 20.0, 35.0, 50.0))
    assert (CM.H_MAIN, CM.MIN_EP, CM.CRASH_D, CM.REB_UP, CM.REB_WIN) == (60, 8, -9.0, 5.0, 60)
    assert (CM.TOP_HOT, CM.TOP_PULL, CM.TOP_LOOK, CM.TOP_RESET) == (6.0, 5.0, 20, 60)
    assert CM.ML_TOP == {"JP": 7, "US": 10} and (CM.CORR_WIN, CM.CORR_MIN, CM.H_XS_MAIN, CM.MIN_XS) == (126, 100, 20, 30)
    assert (CM.POS_SHARE, CM.BOOT_N, CM.SEED, CM.POOL) == (60.0, 2000, 20260929, ("Z", "E", "W", "J2"))
