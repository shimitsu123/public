"""scripts/state_model_study.py：三态只用到当时、输出暴露（输入内生化）与业种加权、特征的涨 / 跌指示与按月去均值、
walk-forward 不看未来且 = 标准化后的普通岭回归、销售 / 顾客三态、个股层跳过面板（上个月末的分数）、M1 的读法、只在窗口内错开、两窗口的选股改进门槛。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import state_model_study as SM  # noqa: E402


def test_tercile_state_is_causal_and_thresholds():
    idx = pd.date_range("2000-01-31", periods=100, freq="ME")
    x = pd.Series(np.arange(100, dtype=float), index=idx)
    s = SM.tercile_state(x, min_hist=60)
    assert s.iloc[:59].isna().all() and s.iloc[59] == 1.0                      # 第 60 个月：比以前都大 → 涨
    y = x.copy()
    y.iloc[80:] = -1000.0                                                       # 改掉未来的值，之前的三态不变
    s2 = SM.tercile_state(y, min_hist=60)
    pd.testing.assert_series_equal(s.iloc[:80], s2.iloc[:80])
    assert s2.iloc[80] == -1.0
    z = pd.Series(np.r_[np.linspace(0, 1, 60), [0.5]], index=idx[:61])
    assert SM.tercile_state(z, min_hist=60).iloc[-1] == 0.0                    # 在 1/3〜2/3 之间 → 不变


def test_export_shares_leontief_with_import_leakage():
    codes = ["001", "002"]
    x = pd.DataFrame([[10.0, 20.0], [5.0, 0.0]], index=codes, columns=codes)
    X = pd.Series([100.0, 50.0], index=codes)
    e = pd.Series([30.0, 10.0], index=codes)
    m = pd.Series([0.0, 12.5], index=codes)
    dd = pd.Series([80.0, 50.0], index=codes)
    d, n = SM.export_shares({"x": x, "X": X, "e": e, "m": m, "dd": dd})
    A = np.array([[0.1, 0.4], [0.05, 0.0]])
    L = np.linalg.inv(np.eye(2) - (1 - np.array([0.0, 0.25]))[:, None] * A)
    tot = L @ np.array([30.0, 10.0])
    assert np.allclose(d.to_numpy(), [0.3, 0.2])
    assert np.allclose(n.to_numpy(), (tot - np.array([30.0, 10.0])) / np.array([100.0, 50.0]))
    assert (n > 0).all()


def test_to_tse_weights_by_production():
    sec = pd.Series({"261": 0.2, "262": 0.4, "011": 0.1})
    X = pd.Series({"261": 300.0, "262": 100.0, "011": 50.0})
    out = SM.to_tse(sec, X, ["鉄鋼", "水産・農林業", "銀行業"])
    assert np.isclose(out["鉄鋼"], (0.2 * 300 + 0.4 * 100) / 400) and np.isclose(out["水産・農林業"], 0.1) and "銀行業" not in out


def _toy():
    months = pd.date_range("2020-01-31", periods=3, freq="ME")
    inds = ["a", "b", "c"]
    ms = pd.DataFrame({"OIL": [1, -1, 0], "STEEL": [0, 0, 1], "NONFER": [0, 0, 0], "FOOD": [0, 0, 0], "FX": [1, 1, -1]}, index=months, dtype=float)
    ss = pd.DataFrame([[1, 0, np.nan], [-1, 1, 0], [0, 0, 0]], index=months, columns=inds, dtype=float)
    cs = pd.DataFrame([[0, 1, -1], [np.nan, 0, 0], [0, 0, 0]], index=months, columns=inds, dtype=float)
    ex = {"direct": {k: {"a": 0.3, "b": 0.1} for k in "ESNF"}, "indirect": {k: {"c": 0.2} for k in "ESNF"}}
    exp = {"direct": {"a": 0.5}, "indirect": {"b": 0.4}}
    return months, inds, ms, ss, cs, ex, exp


def test_features_indicators_and_monthly_demeaning():
    months, inds, ms, ss, cs, ex, exp = _toy()
    names = SM.feature_names()
    assert len(names) == 32 and len(SM.feature_names(("SALES", "CUS"))) == 28 and len(SM.feature_names(("I", "EXi", "CUS"))) == 20
    F = SM.features(ms, ss, cs, SM.exposure_arrays(ex, exp, inds), names)
    assert np.allclose(np.nanmean(F, axis=1), 0)
    D = np.array([0.3, 0.1, 0.0])
    assert np.allclose(F[0, :, names.index("OIL_up_D")], D - D.mean())                       # 1 月原油涨
    assert np.allclose(F[1, :, names.index("OIL_up_D")], 0) and np.allclose(F[1, :, names.index("OIL_dn_D")], D - D.mean())
    assert np.allclose(F[0, :, names.index("OIL_up_I")], np.array([0, 0, 0.2]) - 0.2 / 3)
    assert np.allclose(F[0, :, names.index("OIL_up_OWN")], 0)                                 # a / b / c 都不是产出方
    assert np.allclose(F[0, :, names.index("SALES_up")], np.array([1, 0, 0]) - 1 / 3)         # SALES 缺值 = 普通
    assert np.allclose(F[1, :, names.index("CUS_dn")], 0)                                     # CUS 缺值 = 普通
    assert np.allclose(F[2, :, names.index("FX_dn_EXd")], np.array([0.5, 0, 0]) - 0.5 / 3)
    assert np.allclose(F[1, :, names.index("FX_up_EXi")], np.array([0, 0.4, 0]) - 0.4 / 3)
    ms2 = ms.copy()
    ms2.iloc[1, 0] = np.nan
    F2 = SM.features(ms2, ss, cs, SM.exposure_arrays(ex, exp, inds), names)
    assert np.isnan(F2[1]).all() and np.isfinite(F2[0]).all()                                # 宏观三态缺值的月 → 整月不用
    e = SM.exposure_arrays(ex, exp, inds, np.array([2, 0, 1]))                                # 产业链打乱：a 拿 c 的暴露
    assert np.allclose(e[("D", "OIL")], [0.0, 0.3, 0.1]) and np.allclose(e[("EXd", "FX")], [0.0, 0.5, 0.0])


def test_walk_forward_is_causal_and_equals_standardized_ridge():
    rng = np.random.default_rng(0)
    T, J, K = 90, 12, 4
    F = rng.normal(size=(T, J, K))
    F -= F.mean(axis=1, keepdims=True)
    Y = SM.demean(F @ np.array([1.0, -0.5, 0.0, 0.2]) + rng.normal(size=(T, J)))
    P = SM.walk_forward(F, Y, h=3, min_train=60, lam=0.1)
    assert np.isnan(P[:62]).all() and np.isfinite(P[62]).all()                               # 训练月 s ≤ i − 3 满 60 个才预测
    i = 70
    Y2 = Y.copy()
    Y2[i - 2:] = 99.0                                                                          # 在 i 时还不知道的目标
    P2 = SM.walk_forward(F, Y2, h=3, min_train=60, lam=0.1)
    assert np.allclose(P[: i + 1], P2[: i + 1], equal_nan=True) and not np.allclose(P[i + 1], P2[i + 1])
    X, y = F[: i - 2].reshape(-1, K), Y[: i - 2].reshape(-1)
    sd = X.std(axis=0)
    Z = X / sd
    bz = np.linalg.solve(Z.T @ Z + 0.1 * len(y) * np.eye(K), Z.T @ y)
    assert np.allclose(P[i], F[i] @ (bz / sd))


def test_sales_and_customer_states():
    idx = pd.date_range("2020-01-31", periods=1, freq="ME")
    sz = pd.DataFrame([[0.5, -0.5, 0.1, np.nan]], index=idx, columns=list("abcd"))
    ss = SM.sales_states(sz)
    assert ss.iloc[0, :3].tolist() == [1.0, -1.0, 0.0] and np.isnan(ss.iloc[0, 3])
    cs = SM.cus_states(ss, {"a": {"b": 0.5, "d": 0.5}, "b": {"a": 0.6, "c": 0.4}, "c": {"d": 1.0}}, list("abcd"))
    assert cs.loc[idx[0], "a"] == -1.0                                                          # 只有 b 有值（弱）→ 归一后 −1
    assert cs.loc[idx[0], "b"] == 1.0                                                           # 0.6 × 强 + 0.4 × 普通 = 0.6 > 1/3
    assert np.isnan(cs.loc[idx[0], "c"]) and np.isnan(cs.loc[idx[0], "d"])                     # 顾客都没有值 / 没有顾客


def test_skip_panel_and_stock_keep_use_previous_month_end():
    idx = pd.date_range("2020-01-31", periods=2, freq="ME")
    cols = list("abcdef")
    sc = pd.DataFrame([[6, 5, 4, 3, 2, 1], [np.nan] * 6], index=idx, columns=cols, dtype=float)
    assert SM.skip_panel(sc, "M2").iloc[0].tolist() == [False, False, False, False, True, True]
    assert SM.skip_panel(sc, "M3").iloc[0].tolist() == [False, False, False, True, True, True]
    assert not SM.skip_panel(sc, "M2").iloc[1].any() and not SM.skip_panel(sc, "M3").iloc[1].any()
    days = pd.bdate_range("2020-02-03", "2020-03-06")
    fr = {t: pd.DataFrame({"entry": True}, index=days) for t in ("X", "Y", "Z")}
    k = SM.stock_keep(fr, {"X": "f", "Y": "a", "Z": "zz"}, sc, "M2")
    feb = days.month == 2
    assert (~k["X"][feb]).all() and k["X"][~feb].all()        # 2 月用 1 月末的分数（最低 1/3 → 不做）；3 月用 2 月末（没有分数 → 照做）
    assert k["Y"].all() and k["Z"].all()


def test_m1_fails_and_reading():
    r = {"ic": 0.05, "t": 2.5, "H1": 0.03, "H2": 0.06, "hit": 60.0}
    assert SM.m1_fails(r, 0.01, 0.02) == [] and SM.m1_verdict([]) == "三态 × 产业链模型有预测力"
    f = SM.m1_fails(r, 0.01, 0.3)
    assert len(f) == 1 and SM.m1_verdict(f).startswith("有预测力，但来自行业自己的销售")
    assert SM.m1_verdict(SM.m1_fails({**r, "t": 1.0}, 0.01, 0.3)) == "无效"
    assert SM.m1_verdict(SM.m1_fails(r, 0.2, 0.01)) == "无效"


def test_roll_window_only_inside_and_perms_fixed():
    idx = pd.date_range("2020-01-31", periods=6, freq="ME")
    X = pd.DataFrame({"a": [1, 2, 3, 4, 5, 6]}, index=idx, dtype=float)
    assert SM.roll_window(X, 1, idx[1], idx[4])["a"].tolist() == [1, 5, 2, 3, 4, 6]
    a, b = SM.perms(30, 3), SM.perms(30, 3)
    assert all((x == y).all() for x, y in zip(a, b)) and sorted(a[0]) == list(range(30))


def test_improve2_two_windows():
    base = {"E": {"win": 50, "mean": 1.0, "n": 100, "calmar": 0.5, "dd": -10}, "J": {"win": 45, "mean": 0.8, "n": 120, "calmar": 0.4, "dd": -12}}
    good = {"E": {"win": 55, "mean": 1.6, "n": 40, "calmar": 0.49, "dd": -11}, "J": {"win": 50, "mean": 1.4, "n": 50, "calmar": 0.5, "dd": -12}}
    assert SM.improve2(good, base) == []
    assert SM.improve2({**good, "J": {**good["J"], "win": 47}}, base) == ["J 胜率没高 4 pp"]
    assert SM.improve2({**good, "E": {**good["E"], "n": 20}}, base) == ["E 笔数不到现行的 30%"]
