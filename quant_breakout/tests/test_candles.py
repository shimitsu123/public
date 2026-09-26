"""qbreak/candles.py：几何特征（用户图中的上影陽線）、形态只用当天为止的数据（截断不改变之前的值）、几个经典形态的手工例子、
之后的收益（第二天收盘 / 开盘 → 开盘）、同一天成员的超额。"""
import numpy as np

from qbreak import candles as K


def _p(rows):
    a = np.array(rows, float)
    return {"O": a[:, [0]], "H": a[:, [1]], "L": a[:, [2]], "C": a[:, [3]], "V": np.full((len(a), 1), 1e5)}


def _flat(n=20, px=100.0):
    return [[px, px + 1.0, px - 1.0, px]] * n                                   # 振幅 2 的平稳 K 线 → ATR ≈ 2


def test_user_shape_is_long_upper_shadow_bullish():
    P = _p(_flat() + [[100.0, 104.0, 99.9, 101.6]])                              # 实体 1.6、上影 2.4、下影 0.1、振幅 4.1
    g = K.geometry(P)
    x = K.context(P, g)
    pat = K.patterns(P, g, x)
    assert np.isclose(g["body_r"][-1, 0], 1.6 / 4.1) and np.isclose(g["up_r"][-1, 0], 2.4 / 4.1)
    assert pat["LUB"][-1, 0] and not pat["LUR"][-1, 0] and not pat["STAR"][-1, 0]
    small = _p(_flat() + [[100.0, 101.2, 99.97, 100.48]])                         # 同样的比例但振幅 < ATR → 不算
    assert not K.patterns(small, K.geometry(small), K.context(small, K.geometry(small)))["LUB"][-1, 0]


def test_patterns_never_use_future_rows():
    rng = np.random.default_rng(0)
    n, m = 300, 4
    C = 1000 * np.exp(np.cumsum(rng.normal(0, 0.02, (n, m)), axis=0))
    O = C * (1 + rng.normal(0, 0.01, (n, m)))
    H = np.fmax(O, C) * (1 + np.abs(rng.normal(0, 0.01, (n, m))))
    L = np.fmin(O, C) * (1 - np.abs(rng.normal(0, 0.01, (n, m))))
    P = {"O": O, "H": H, "L": L, "C": C, "V": rng.uniform(1e5, 1e6, (n, m))}
    full = K.patterns(P, K.geometry(P), K.context(P, K.geometry(P)))
    for cut in (120, 200, 299):
        Pc = {k: v[:cut + 1] for k, v in P.items()}
        part = K.patterns(Pc, K.geometry(Pc), K.context(Pc, K.geometry(Pc)))
        for k in K.PATTERNS:
            assert np.array_equal(full[k][:cut + 1], part[k]), k
    assert sum(int(v.sum()) for v in full.values()) > 200


def test_two_and_three_candle_patterns():
    base = _flat(25)
    eng = _p(base + [[101.0, 101.5, 97.5, 98.0], [97.8, 102.5, 97.5, 102.0]])   # 阴线后阳线包住
    g = K.geometry(eng)
    pat = K.patterns(eng, g, K.context(eng, g))
    assert pat["ENGB"][-1, 0] and not pat["ENGR"][-1, 0]
    ms = _p(base + [[101.0, 101.2, 96.0, 96.2], [95.5, 95.9, 94.8, 95.4], [95.6, 99.5, 95.5, 99.2]])
    g = K.geometry(ms)
    assert K.patterns(ms, g, K.context(ms, g))["MSTAR"][-1, 0]
    w3 = _p(base + [[100.0, 102.1, 99.9, 102.0], [101.0, 104.1, 100.9, 104.0], [103.0, 106.1, 102.9, 106.0]])
    g = K.geometry(w3)
    assert K.patterns(w3, g, K.context(w3, g))["W3"][-1, 0]
    gp = _p(base + [[102.0, 103.0, 101.5, 102.5], [104.0, 105.0, 103.5, 104.5], [106.0, 107.0, 105.5, 106.5]])
    g = K.geometry(gp)
    p = K.patterns(gp, g, K.context(gp, g))
    assert p["GAPU"][-1, 0] and p["GAP3U"][-1, 0] and not p["GAP3U"][-2, 0]


def test_zero_range_day_is_never_a_pattern():
    P = _p(_flat() + [[100.0, 100.0, 100.0, 100.0]])
    g = K.geometry(P)
    pat = K.patterns(P, g, K.context(P, g))
    assert not g["ok"][-1, 0] and not any(v[-1, 0] for v in pat.values())


def test_targets_and_excess():
    P = {"O": np.array([[10.0, 20.0], [11.0, 21.0], [12.0, np.nan], [13.0, 23.0]]),
         "C": np.array([[10.5, 20.5], [11.5, 21.5], [12.5, 22.5], [13.5, 23.5]])}
    t = K.targets(P, horizons=(2,))
    assert np.isclose(t["n1_cc"][0, 0], 11.5 / 10.5 - 1) and np.isclose(t["n1_oc"][0, 0], 11.5 / 11.0 - 1)
    assert np.isclose(t["g1"][0, 0], 11.0 / 10.5 - 1) and np.isclose(t["f2"][0, 0], 13.0 / 11.0 - 1)
    assert np.isnan(t["f2"][1, 1]) and np.isnan(t["n1_cc"][-1, 0])            # 缺开盘 / 最后一天 → NaN
    mem = np.array([[True, True], [True, False], [True, True], [False, False]])
    ex = K.excess(np.array([[1.0, 3.0], [2.0, 5.0], [np.nan, 4.0], [1.0, 1.0]]), mem)
    assert np.allclose(ex[0], [-1.0, 1.0]) and ex[1, 0] == 0.0 and np.isnan(ex[1, 1]) and ex[2, 1] == 0.0 and np.isnan(ex[3]).all()
