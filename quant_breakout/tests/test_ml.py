"""qbreak/ml.py（纯 numpy 的机器学习小工具）：截面排名、岭回归、直方图梯度提升树（学得会已知的非线性关系、缺值、分层预测、
可复现）、按日期的秩相关与 Spearman 一致、按块的自助法。"""
import numpy as np
import pandas as pd

from qbreak import ml
from qbreak.factor_combo import auc


def test_rank_by_date_symmetric_ties_and_nan():
    v = np.array([1.0, 2.0, 3.0, np.nan, 5.0, 5.0, 7.0])
    d = np.array([0, 0, 0, 0, 1, 1, 1])
    r = ml.rank_by_date(v, d)
    assert np.allclose(r[:3], [-1 / 3, 0.0, 1 / 3]) and np.isnan(r[3])
    assert np.allclose(r[4:], [(1.5 - 0.5) / 3 - 0.5] * 2 + [(3 - 0.5) / 3 - 0.5])   # 平局取平均秩
    big = ml.rank_by_date(np.random.default_rng(0).normal(size=1000), np.zeros(1000))
    assert abs(big.mean()) < 1e-12 and big.max() < 0.5 and big.min() > -0.5


def test_ridge_recovers_linear_relation_and_shrinks():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(5000, 3))
    y = 2.0 + X @ np.array([1.0, -0.5, 0.0]) + rng.normal(0, 0.1, 5000)
    w = ml.ridge_fit(X, y, 1e-6)
    assert np.allclose(w, [2.0, 1.0, -0.5, 0.0], atol=0.02)
    w2 = ml.ridge_fit(X, y, 10.0)
    assert abs(w2[0] - 2.0) < 0.05 and np.linalg.norm(w2[1:]) < 0.2 * np.linalg.norm(w[1:])   # 截距不惩罚，系数整体被压小
    Xn = X.copy()
    Xn[0, 0] = np.nan
    assert np.isfinite(ml.ridge_predict(w, Xn)).all()


def _nonlinear(n, seed):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 5))
    f = np.where(X[:, 0] > 0, 1.0, -1.0) + np.where(X[:, 1] > 0.5, X[:, 2], 0.0)       # 阶梯 + 交互
    return X, f, f + rng.normal(0, 0.3, n)


def test_gbm_learns_step_and_interaction_better_than_linear():
    X, f, y = _nonlinear(12000, 2)
    g = ml.HistGBM(n_trees=150, min_leaf=40, seed=1).fit(X[:9000], y[:9000])
    st = g.predict_staged(X[9000:], [10, 50, 150])
    mse = {k: float(np.mean((v - f[9000:]) ** 2)) for k, v in st.items()}
    assert mse[150] < mse[50] < mse[10]
    lin = ml.ridge_predict(ml.ridge_fit(X[:9000], y[:9000], 1e-6), X[9000:])
    assert mse[150] < 0.5 * float(np.mean((lin - f[9000:]) ** 2))
    g2 = ml.HistGBM(n_trees=150, min_leaf=40, seed=1).fit(X[:9000], y[:9000])
    assert np.array_equal(g.predict(X[9000:]), g2.predict(X[9000:]))                  # 同一个种子 → 完全一样
    assert np.allclose(g.predict(X[9000:], 50), st[50])


def test_gbm_missing_values_get_their_own_bin():
    rng = np.random.default_rng(3)
    n = 6000
    X = rng.normal(size=(n, 2))
    miss = rng.random(n) < 0.3
    X[miss, 0] = np.nan
    y = np.where(miss, 2.0, 0.0) + rng.normal(0, 0.1, n)                               # 缺值本身有信息
    g = ml.HistGBM(n_trees=60, min_leaf=30, seed=0, subsample=1.0, colsample=1.0).fit(X, y)
    p = g.predict(X)
    assert p[miss].mean() > 1.8 and p[~miss].mean() < 0.2


def test_gbm_logloss_probabilities_and_auc():
    X, f, _ = _nonlinear(10000, 4)
    yc = (f + np.random.default_rng(5).normal(0, 0.7, 10000) > 0).astype(float)
    g = ml.HistGBM(loss="logloss", n_trees=120, min_leaf=40, seed=2).fit(X[:7000], yc[:7000])
    p = g.predict(X[7000:])
    assert ((p > 0) & (p < 1)).all() and auc(p, yc[7000:])[0] > 0.8


def test_ic_by_date_matches_pandas_spearman_and_skips_small_dates():
    rng = np.random.default_rng(6)
    d = np.r_[np.repeat(np.arange(30), 40), np.full(3, 99)]
    s = rng.normal(size=len(d))
    t = 0.3 * s + rng.normal(size=len(d))
    s[5] = np.nan
    ic = ml.ic_by_date(s, t, d)
    df = pd.DataFrame({"d": d, "s": s, "t": t}).dropna()
    ref = df.groupby("d").apply(lambda g: g["s"].rank().corr(g["t"].rank()))
    assert 99 not in ic.index and np.allclose(ic.to_numpy(), ref.loc[ic.index].to_numpy())


def test_block_boot_mean():
    x = pd.Series(np.arange(24, dtype=float))
    blocks = np.repeat(np.arange(6), 4)
    m, lo, hi = ml.block_boot_mean(x, blocks, n=500, seed=1)
    assert m == x.mean() and lo < m < hi
    assert ml.block_boot_mean(x, blocks, n=500, seed=1) == (m, lo, hi)
    assert np.isnan(ml.block_boot_mean(pd.Series([np.nan]), [0])[0])
