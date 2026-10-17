"""scripts/state_model_study.py：三态只用到当时、去季节只用以前的同月份、月平均不用东京最后一个交易日、输出暴露（输入内生化）与业种加权、
特征的涨 / 跌指示与按月去均值（30 个）、对照 ② / ②b 只置换对应的渠道、walk-forward 不看未来且 = 标准化后的岭回归、销售 / 顾客三态、
个股层（上个月末的分数、只算窗口内的信号、同月同数抽签、经验 p、去掉每笔之和最高的一年）、去掉行业动量的残差、M1 的判定与来源标签。"""
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


def test_deseason_uses_only_earlier_same_months():
    idx = pd.date_range("2000-01-31", periods=12 * 12, freq="ME")
    rng = np.random.default_rng(1)
    season = np.where(idx.month.isin([5, 6, 7]), 5.0, 0.0)                     # 5〜7 月每年都大（像鉄鋼的 4 月改定）
    x = pd.Series(season + rng.normal(0, 1, len(idx)), index=idx)
    d = SM.deseason(x, min_years=8)
    assert d.iloc[: 12 * 8].isna().all() and d.iloc[12 * 8:].notna().all()    # 同月份以前不到 8 年 → 缺值
    later = d.iloc[12 * 8:]
    assert abs(later[later.index.month.isin([5, 6, 7])].mean() - later[~later.index.month.isin([5, 6, 7])].mean()) < 1.0   # 季节差被去掉
    x2 = x.copy()
    x2.iloc[-1] = 999.0
    pd.testing.assert_series_equal(d.iloc[:-1], SM.deseason(x2, min_years=8).iloc[:-1])                                 # 改未来不影响以前
    i = len(idx) - 1
    prev = x.to_numpy()[np.arange(i - 12, -1, -12)]
    assert np.isclose(d.iloc[i], (x.iloc[i] - prev.mean()) / prev.std(ddof=1))


def test_monthly_mean_drops_last_tokyo_trading_day():
    days = pd.bdate_range("2026-07-01", "2026-07-31")                          # 7/31（五）是东京的最后一个交易日
    s = pd.Series(1.0, index=days)
    s.loc["2026-07-31"] = 100.0
    months = pd.DatetimeIndex([pd.Timestamp("2026-07-31")])
    assert SM.monthly_mean(s, months).iloc[0] == 1.0
    d2 = pd.bdate_range("2026-08-03", "2026-08-31")                            # 8/31（一）是最后一个交易日
    s2 = pd.Series(np.arange(len(d2), dtype=float), index=d2)
    assert np.isclose(SM.monthly_mean(s2, pd.DatetimeIndex([pd.Timestamp("2026-08-31")])).iloc[0], s2.iloc[:-1].mean())


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
    inds = ["a", "b", "鉱業"]
    ms = pd.DataFrame({"OIL": [1, -1, 0], "STEEL": [0, 0, 1], "NONFER": [0, 0, 0], "FOOD": [1, 0, 0], "FX": [1, 1, -1]}, index=months, dtype=float)
    ss = pd.DataFrame([[1, 0, np.nan], [-1, 1, 0], [0, 0, 0]], index=months, columns=inds, dtype=float)
    cs = pd.DataFrame([[0, 1, -1], [np.nan, 0, 0], [0, 0, 0]], index=months, columns=inds, dtype=float)
    ex = {"direct": {k: {"a": 0.3, "b": 0.1} for k in "ESNF"}, "indirect": {k: {"鉱業": 0.2, "a": 0.05} for k in "ESNF"}}
    exp = {"direct": {"a": 0.5, "鉱業": 0.9}, "indirect": {"b": 0.4, "鉱業": 0.6}}
    return months, inds, ms, ss, cs, ex, exp


def test_features_indicators_and_monthly_demeaning():
    months, inds, ms, ss, cs, ex, exp = _toy()
    names = SM.feature_names()
    assert len(names) == 30 and len(SM.feature_names(("SALES", "CUS"))) == 26 and len(SM.feature_names(("I", "EXi", "CUS"))) == 20
    assert len(SM.feature_names(("OIL",))) == 24 and not any("OWN" in n for n in SM.feature_names(("OWN",)))
    assert "FOOD_up_DI" in SM.feature_names(("I",))                                          # FOOD 的 DI 算直接
    expo = SM.exposure_arrays(ex, exp, inds)
    assert np.allclose(expo[("EXd", "FX")], [0.5, 0.0, 0.0]) and np.allclose(expo[("EXi", "FX")], [0.0, 0.4, 0.0])   # 鉱業 的汇率暴露 = 0
    assert np.allclose(expo[("DI", "FOOD")], [0.35, 0.1, 0.2]) and np.allclose(expo[("OWN", "OIL")], [0, 0, 1])
    F = SM.features(ms, ss, cs, expo, names)
    assert np.allclose(np.nanmean(F, axis=1), 0)
    D = np.array([0.3, 0.1, 0.0])
    assert np.allclose(F[0, :, names.index("OIL_up_D")], D - D.mean())                       # 1 月原油涨
    assert np.allclose(F[1, :, names.index("OIL_up_D")], 0) and np.allclose(F[1, :, names.index("OIL_dn_D")], D - D.mean())
    assert np.allclose(F[0, :, names.index("OIL_up_OWN")], np.array([0, 0, 1]) - 1 / 3)
    assert np.allclose(F[0, :, names.index("FOOD_up_DI")], np.array([0.35, 0.1, 0.2]) - 0.65 / 3)
    assert np.allclose(F[0, :, names.index("SALES_up")], np.array([1, 0, 0]) - 1 / 3)         # SALES 缺值 = 普通
    assert np.allclose(F[1, :, names.index("CUS_dn")], 0)                                     # CUS 缺值 = 普通
    assert np.allclose(F[2, :, names.index("FX_dn_EXd")], np.array([0.5, 0, 0]) - 0.5 / 3)
    ms2 = ms.copy()
    ms2.iloc[1, 0] = np.nan
    F2 = SM.features(ms2, ss, cs, expo, names)
    assert np.isnan(F2[1]).all() and np.isfinite(F2[0]).all()                                # 宏观三态缺值的月 → 整月不用


def test_placebo_permutations_touch_only_their_channels():
    months, inds, ms, ss, cs, ex, exp = _toy()
    base = SM.exposure_arrays(ex, exp, inds)
    pm = np.array([2, 0, 1])
    e2 = SM.exposure_arrays(ex, exp, inds, perm_io=pm)                                        # ②：产业连关表导出的全部暴露，OWN 不动
    for key, v in base.items():
        want = v[pm] if key[0] in SM.IO_CH else v
        assert np.allclose(e2[key], want), key
    e3 = SM.exposure_arrays(ex, exp, inds, perm_ind=pm)                                       # ②b：只有间接（I / EXi）
    for key, v in base.items():
        want = v[pm] if key[0] in SM.IND_CH else v
        assert np.allclose(e3[key], want), key
    assert np.allclose(e3[("DI", "FOOD")], base[("DI", "FOOD")]) and np.allclose(e3[("D", "OIL")], base[("D", "OIL")])


def test_walk_forward_is_causal_and_equals_standardized_ridge():
    rng = np.random.default_rng(0)
    T, J, K = 90, 12, 4
    F = rng.normal(size=(T, J, K))
    F -= F.mean(axis=1, keepdims=True)
    Y = SM.demean(F @ np.array([1.0, -0.5, 0.0, 0.2]) + rng.normal(size=(T, J)))
    P = SM.walk_forward(F, Y, h=3, min_train=60, lam=1.0)
    assert np.isnan(P[:62]).all() and np.isfinite(P[62]).all()                               # 训练月 s ≤ i − 3 满 60 个才预测
    i = 70
    Y2 = Y.copy()
    Y2[i - 2:] = 99.0                                                                          # 在 i 时还不知道的目标
    P2 = SM.walk_forward(F, Y2, h=3, min_train=60, lam=1.0)
    assert np.allclose(P[: i + 1], P2[: i + 1], equal_nan=True) and not np.allclose(P[i + 1], P2[i + 1])
    X, y = F[: i - 2].reshape(-1, K), Y[: i - 2].reshape(-1)
    sd = X.std(axis=0)
    Z = X / sd
    bz = np.linalg.solve(Z.T @ Z + 1.0 * len(y) * np.eye(K), Z.T @ y)
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


def test_in_window_and_month_lottery():
    days = pd.bdate_range("2010-12-01", "2011-02-28")
    fr = {t: pd.DataFrame({"entry": np.arange(len(days)) % 5 == j}, index=days) for j, t in enumerate("XYZ")}
    fw = SM.in_window(fr, "2011-01-04", "2011-02-15")
    for t, df in fw.items():
        e = df["entry"].to_numpy(bool)
        assert not e[df.index < "2011-01-04"].any() and not e[df.index > "2011-02-15"].any()
        assert e[(df.index >= "2011-01-04") & (df.index <= "2011-02-15")].sum() == fr[t]["entry"][(days >= "2011-01-04") & (days <= "2011-02-15")].sum()
    keep = {t: np.ones(len(days), bool) for t in "XYZ"}
    jan_x = np.flatnonzero(fw["X"]["entry"].to_numpy() & (days.month == 1))
    keep["X"][jan_x[:2]] = False                                                              # 候选：1 月去掉 X 的 2 个信号
    lot = SM.month_lottery(fw, keep, 7)
    removed = [(t, i) for t in "XYZ" for i in np.flatnonzero(~lot[t])]
    assert len(removed) == 2 and all(days[i].month == 1 and fw[t]["entry"].iloc[i] for t, i in removed)   # 同一个月、同样多、都是真信号
    lot2 = SM.month_lottery(fw, keep, 7)
    assert all((lot[t] == lot2[t]).all() for t in "XYZ")                                      # 固定种子


def test_emp_p_and_ex_best_sum():
    assert SM.emp_p(5.0, [1, 2, 3, None, np.nan]) == 1 / 4 and SM.emp_p(2.0, [1, 2, 3]) == 3 / 4 and SM.emp_p(None, [1]) is None
    tr = pd.DataFrame({"entry_date": pd.to_datetime(["2011-03-01", "2011-06-01", "2012-02-01", "2013-05-01", "2013-07-01"]),
                       "net": [10.0, -2.0, 5.0, 3.0, 3.0]})
    r = SM.ex_best_sum(tr, "2011-01-01", None)                                                # 每笔之和：2011 = 8、2012 = 5、2013 = 6 → 去 2011
    assert r["best_year"] == 2011 and r["n"] == 3 and np.isclose(r["mean"], 11 / 3) and r["win"] == 100.0


def test_momentum_residual_is_orthogonal_to_momentum():
    rng = np.random.default_rng(2)
    idx = pd.date_range("2020-01-31", periods=5, freq="ME")
    cols = [f"i{k}" for k in range(12)]
    mom = pd.DataFrame(rng.normal(size=(5, 12)), index=idx, columns=cols)
    pred = 2.0 * mom + pd.DataFrame(rng.normal(size=(5, 12)), index=idx, columns=cols)
    res = SM.momentum_residual(pred, mom)
    for t in idx:
        assert abs(np.corrcoef(res.loc[t], mom.loc[t])[0, 1]) < 1e-9 and abs(res.loc[t].mean()) < 1e-9


def test_tercile_spreads_and_unrounded_stats():
    idx = pd.date_range("2020-01-31", periods=6, freq="ME")
    cols = [f"i{k}" for k in range(9)]
    X = pd.DataFrame(np.tile(np.arange(9, dtype=float), (6, 1)), index=idx, columns=cols)
    Y = X * 1.0
    assert np.allclose(SM.tercile_spreads(X, Y, 3, 0), [6.0, 6.0])                           # 每 3 个月取一次：最高 3 个 − 最低 3 个
    assert len(SM.tercile_spreads(X, Y, 3, 1)) == 2
    m, t, n = SM.raw_stats(pd.Series(np.r_[np.full(10, 0.02), np.full(10, 0.01)]), 4)
    assert np.isclose(m, 0.015) and n == 20 and np.isfinite(t)


def test_m1_fails_label_and_verdict():
    r = {"ic": 0.05, "t": 2.5, "H1": 0.03, "H2": 0.06, "hit": 60.0}
    good_res = {"ic": 0.02, "t": 1.8}
    assert SM.m1_fails(r, 0.01, 0.01, good_res) == []
    assert SM.m1_fails({**r, "t": 1.9999}, 0.01, 0.01, good_res)                               # 没有四舍五入：1.9999 不算 2.0
    assert SM.m1_fails(r, 0.06, 0.01, good_res) and SM.m1_fails(r, 0.01, -0.001, good_res) and SM.m1_fails(r, 0.01, 0.01, {"ic": 0.02, "t": 1.6})
    assert SM.m1_new({"ic": 0.01, "t": 1.7}) and not SM.m1_new({"ic": 0.01, "t": 1.6})
    assert SM.m1_label(0.2, 0.01, 0.01).startswith("来自销售") and SM.m1_label(0.01, 0.2, 0.01).startswith("三态有增量")
    assert SM.m1_label(0.01, 0.01, 0.2).startswith("产业链有增量") and SM.m1_label(0.01, 0.01, 0.01) == "三态 × 间接（供应链）渠道有增量"
    assert SM.m1_verdict(["x"], True, "y") == "无效" and SM.m1_verdict([], False, "y").endswith("不算新证据")
    assert SM.m1_verdict([], True, "三态 × 间接（供应链）渠道有增量").startswith("三态 × 产业链模型有预测力（新证据")


def test_roll_window_only_inside_and_perms_fixed():
    idx = pd.date_range("2020-01-31", periods=6, freq="ME")
    X = pd.DataFrame({"a": [1, 2, 3, 4, 5, 6]}, index=idx, dtype=float)
    assert SM.roll_window(X, 1, idx[1], idx[4])["a"].tolist() == [1, 5, 2, 3, 4, 6]
    a, b = SM.perms(26, 3), SM.perms(26, 3)
    assert all((x == y).all() for x, y in zip(a, b)) and sorted(a[0]) == list(range(26))


def test_improve2_two_windows():
    base = {"E": {"win": 50, "mean": 1.0, "n": 100, "calmar": 0.5, "dd": -10}, "J": {"win": 45, "mean": 0.8, "n": 120, "calmar": 0.4, "dd": -12}}
    good = {"E": {"win": 55, "mean": 1.6, "n": 40, "calmar": 0.49, "dd": -11}, "J": {"win": 50, "mean": 1.4, "n": 50, "calmar": 0.5, "dd": -12}}
    assert SM.improve2(good, base) == []
    assert SM.improve2({**good, "J": {**good["J"], "win": 47}}, base) == ["J 胜率没高 4 pp"]
    assert SM.improve2({**good, "E": {**good["E"], "n": 20}}, base) == ["E 笔数不到现行的 30%"]


def test_stock_fails_needs_all_placebos_and_best_year():
    ok_pl = {k: {"win_p": 0.01, "mean_p": 0.02} for k in ("shift", "perm", "month")}
    base = {"E": {"win": 50, "mean": 1.0, "n": 100, "calmar": 0.5, "dd": -10}, "J": {"win": 45, "mean": 0.8, "n": 120, "calmar": 0.4, "dd": -12}}
    good = {"E": {"win": 55, "mean": 1.6, "n": 40, "calmar": 0.49, "dd": -11}, "J": {"win": 50, "mean": 1.4, "n": 50, "calmar": 0.5, "dd": -12}}
    W = {e: {"res": {"现行": {e: base[e]}, "M2": {e: good[e]}}, "pl": {"M2": dict(ok_pl)},
             "best": {"现行": {"mean": 0.5, "win": 45.0}, "M2": {"mean": 0.9, "win": 50.0}}} for e in ("E", "J")}
    assert SM.stock_fails("M2", W) == []
    W["J"]["pl"]["M2"]["month"] = {"win_p": 0.2, "mean_p": 0.01}
    assert SM.stock_fails("M2", W) == ["J ④ 同月同数对照 胜率 p 0.2"]
    W["J"]["pl"]["M2"]["month"] = {"win_p": 0.01, "mean_p": 0.01}
    W["E"]["best"]["M2"] = {"mean": 0.4, "win": 50.0}
    assert SM.stock_fails("M2", W) == ["E 去掉最好一年后不比现行好"]
