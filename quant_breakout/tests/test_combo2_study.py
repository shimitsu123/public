"""选股第二轮（scripts/combo2_common.py，2026-10-01 登记）：登记值、逐年前推只用过去、补回 / 换掉的规则、随机对照、判定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import combo2_common as C2  # noqa: E402
import combo_all_common as CA  # noqa: E402


def _panel(n=600, seed=0, start="2003-01-06", signal="vexp"):
    """平静的牛市格子里 signal 越大越赚钱；其余特征是噪声。"""
    rng = np.random.default_rng(seed)
    d = pd.bdate_range(start, periods=n * 5)[::5][:n]
    X = pd.DataFrame({f: rng.normal(size=n) for f in CA.STOCK_FEATS})
    X["date"] = d
    X["ticker"] = [f"{1000 + i % 50}.T" for i in range(n)]
    X["week"] = pd.to_datetime(X["date"]).dt.to_period("W").astype(str)
    X["n225_ma200"] = 0.05
    X["vix"] = 15.0
    X["net"] = 2.0 * X[signal] + rng.normal(0, 1.0, n)
    return X


def test_registered_constants():
    assert (C2.GAP_DAYS, C2.RESCUE_MIN) == (120, 2)
    assert (C2.F1_WIN, C2.F1_MEAN) == (2.0, 0.20) and (C2.F4_TOL, C2.F4_DD, C2.F4_SUM) == (0.02, 2.0, 0.02)
    assert (C2.G_DILUTE, C2.G_WIN_DILUTE, C2.G_SUM) == (0.30, 3.0, 0.03)
    assert (C2.PLACEBO_N, C2.ACCT_SEEDS) == (200, 30)
    assert (CA.MIN_RHO_C, CA.CELL_MIN_N, CA.C_VIX) == (0.05, 60, 20.0)          # C 的做法本身不动


def test_halves_split_by_median_date():
    X = _panel(11)
    a, b = C2.halves(X)
    assert len(a) == 6 and len(b) == 5 and a["date"].max() < b["date"].min()
    e = C2.halves(X.iloc[0:0])
    assert len(e[0]) == 0 and len(e[1]) == 0


def test_forward_rules_use_only_past_signals():
    X = _panel(800)
    yrs = [2008, 2012, 2016]
    R = C2.forward_rules(X, yrs)
    cut = C2.train_cut(2012)
    assert cut == pd.Timestamp("2011-09-03")
    later = X.copy()
    m = pd.to_datetime(later["date"]) > cut
    later.loc[m, "net"] = -later.loc[m, "net"]                                 # 之后的结果反过来 → 2012 的规则不变
    R2 = C2.forward_rules(later, [2012])
    assert R2[2012] == R[2012] or (str(R2[2012]) == str(R[2012]))
    assert C2.active(R[2016]) and "vexp" in R[2016][2]["sel"] and R[2016][2]["sel"]["vexp"] == 1
    few = C2.forward_rules(X.iloc[:100], [2004])                               # 每半不到 60 笔 → 没有规则
    assert not C2.active(few[2004]) and C2.rule_features(few[2004]) == "—"
    assert "vexp+" in C2.rule_features(R[2016])


def test_apply_forward_keeps_all_in_years_without_rules():
    X = _panel(800)
    R = C2.forward_rules(X, range(2003, 2015))
    keep, on = C2.apply_forward(R, X)
    yr = pd.to_datetime(X["date"]).dt.year.to_numpy()
    for y in np.unique(yr):
        m = yr == y
        if not C2.active(R.get(int(y))):
            assert keep[m].all() and not on[m].any()
        else:
            assert on[m].all()
    k2 = keep & on
    assert X.loc[k2, "net"].mean() > X.loc[on & ~keep, "net"].mean()        # 学到的方向有用（合成数据）
    e, o = C2.apply_forward(R, X.iloc[0:0])
    assert len(e) == 0 and len(o) == 0


def test_rescue_needs_rule_cell_and_score_two():
    X = _panel(400, seed=1)
    rules = CA.fit_c(C2.halves(X))
    assert rules[2] is not None and rules[0] is None
    Y = _panel(200, seed=2, start="2015-01-05")
    sc, has = C2.c_score(rules, Y)
    assert has.all() and np.isfinite(sc).all()
    r = C2.rescue(rules, Y)
    assert (r == (sc >= 2)).all()
    Y.loc[:49, "n225_ma200"] = -0.05                                          # 200 日线下：那一格没有规则 → 不补回
    sc2, has2 = C2.c_score(rules, Y)
    assert not has2[:50].any() and np.isnan(sc2[:50]).all() and not C2.rescue(rules, Y)[:50].any()


def test_random_pick_and_rescue_placebo_are_reproducible():
    rng = np.random.default_rng(0)
    tk = np.array([f"{i % 30}" for i in range(300)])
    wk = np.array([f"w{i // 30}" for i in range(300)])
    pick = C2.random_pick(tk, wk, 60, rng)
    assert 30 <= pick.sum() <= 90
    assert not C2.random_pick(tk, wk, 0, rng).any() and len(C2.random_pick(tk[:0], wk[:0], 5, rng)) == 0
    net = np.linspace(-5, 5, 300)
    q1 = C2.rescue_placebo([(net, tk, wk, 60)], n=50, seed=1)
    q2 = C2.rescue_placebo([(net, tk, wk, 60)], n=50, seed=1)
    assert q1 == q2 and np.isfinite(q1)


def test_decisions():
    good = {"dwin": 3.0, "dmean": 0.5}
    assert C2.f1(good, 0.3) and not C2.f1(good, 0.6) and not C2.f1({"dwin": 1.9, "dmean": 0.5}, 0.0)
    assert C2.f2({"dmean": 0.0}, {"dmean": 0.1}) and not C2.f2({"dmean": -0.01}, {"dmean": 1.0})
    assert C2.f3({"W": {"dwin": 0.0, "dmean": 0.0}, "Jx": {"dwin": 0.1, "dmean": 0.2}})
    assert not C2.f3({"W": {"dwin": -0.1, "dmean": 0.0}, "Jx": {"dwin": 0.1, "dmean": 0.2}})
    base = {e: {"calmar": 0.30, "dd": -30.0} for e in ("Z", "E", "J")}
    up = {e: {"calmar": 0.32, "dd": -31.0} for e in ("Z", "E", "J")}
    assert C2.acct_ok(up, base, ("Z", "E", "J"), 0.02, 2.0, 0.03) and abs(C2.acct_sum(up, base, ("Z", "E", "J")) - 0.06) < 1e-12
    deep = {**up, "E": {"calmar": 0.35, "dd": -32.5}}
    assert not C2.acct_ok(deep, base, ("Z", "E", "J"), 0.02, 2.0, 0.03)       # 回撤深 2.5 pp
    low = {**up, "J": {"calmar": 0.27, "dd": -30.0}}
    assert not C2.acct_ok(low, base, ("Z", "E", "J"), 0.02, 2.0, 0.03)        # J 低 0.03
    assert not C2.acct_ok({"Z": up["Z"]}, base, ("Z", "E", "J"), 0.02, 2.0, 0.03)
    st = lambda n, w, m: {"n": n, "win": w, "mean": m}                         # noqa: E731
    assert C2.g1_rescue({"Z": st(0, np.nan, np.nan), "E": st(3, 66.0, 0.5), "J": st(5, 40.0, 0.1)})
    assert not C2.g1_rescue({"Z": st(2, 50.0, -0.1), "E": st(3, 66.0, 0.5), "J": st(5, 40.0, 0.1)})
    assert C2.g2_rescue(st(20, 45.0, 1.0), st(100, 45.0, 1.2), 0.8) and not C2.g2_rescue(st(20, 45.0, 0.8), st(100, 45.0, 1.2), 0.5)
    assert not C2.g2_rescue(st(20, 45.0, 1.0), st(100, 45.0, 1.2), 1.1) and not C2.g2_rescue(st(0, np.nan, np.nan), st(100, 45.0, 1.2), 0.0)
    assert C2.g3_rescue({"W": st(0, np.nan, np.nan), "Jx": st(5, 40.0, 0.0)}) and not C2.g3_rescue({"W": st(4, 25.0, -0.2), "Jx": st(5, 40.0, 0.0)})
    b3 = {e: st(50, 45.0, 1.0) for e in ("Z", "E", "J")}
    assert C2.g1_replace({e: st(80, 42.5, 0.75) for e in ("Z", "E", "J")}, b3)
    assert not C2.g1_replace({e: st(80, 41.0, 0.75) for e in ("Z", "E", "J")}, b3)    # 胜率低 4 pp
    assert not C2.g1_replace({**{e: st(80, 45.0, 1.0) for e in ("Z", "E")}, "J": st(80, 45.0, 0.6)}, b3)
    assert C2.g2_replace({"dmean": 0.3}, 0.2) and not C2.g2_replace({"dmean": 0.19}, 0.0) and not C2.g2_replace({"dmean": 0.3}, 0.4)
    assert C2.g3_replace({"W": st(9, 40.0, 0.8), "Jx": st(9, 40.0, 0.7)}, {"W": st(9, 40.0, 1.0), "Jx": st(9, 40.0, 1.0)})
    assert C2.verdict([True, True, True], True, True) == "通过" and C2.verdict([True, True, True], False, False) == "方向一致"
    assert C2.verdict([True, False, True], True, True) == "不通过"


def test_stat():
    s = C2.stat([1.0, -1.0, 2.0, np.nan])
    assert s["n"] == 3 and abs(s["win"] - 200 / 3) < 1e-9 and abs(s["mean"] - 2 / 3) < 1e-12
    assert C2.stat([])["n"] == 0
