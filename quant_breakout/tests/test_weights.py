import json

import numpy as np
import pandas as pd
import pytest

from qbreak import threat as TH
from qbreak import weights as WT


def test_auc_matches_threat_auc_with_ties():
    rng = np.random.default_rng(0)
    s = rng.integers(0, 20, 500).astype(float)
    y = (rng.random(500) < 0.3).astype(float)
    s[::7] = np.nan
    assert WT.auc_np(s, y) == pytest.approx(TH.auc(pd.Series(s), pd.Series(y)))
    assert WT.auc_np(s, np.zeros(500)) is None


def _logit_data(n=20000, beta=(1.5, -2.0, 0.0), b0=-1.0, seed=1):
    rng = np.random.default_rng(seed)
    X = rng.uniform(-0.5, 0.5, (n, len(beta)))
    y = (rng.random(n) < WT.sigmoid(b0 + X @ np.array(beta))).astype(float)
    return X, y


def test_newton_and_prox_recover_coefficients():
    X, y = _logit_data()
    w = WT.fit_newton(X, y, 1e-8)
    assert w == pytest.approx([-1.0, 1.5, -2.0, 0.0], abs=0.15)
    assert WT.fit_prox(X, y) == pytest.approx(w, abs=1e-3)           # 无惩罚的 FISTA ≈ 牛顿法
    wn = WT.fit_prox(X, y, l2=1e-6, nonneg=True)                     # 非负：负系数压到 0
    assert (wn[1:] >= 0).all() and wn[2] == 0 and wn[1] > 1.0
    assert (WT.fit_prox(X, y, l1=1.0)[1:] == 0).all()                # L1 很大 → 全 0
    assert np.abs(WT.fit_newton(X, y, 10.0)[1:]).max() < 0.2         # L2 很大 → 系数缩小


def test_cv_folds_embargo_and_cover():
    pos = np.arange(0, 3000, 5)
    folds = WT.cv_folds(pos)
    assert sorted(np.concatenate([va for _, va in folds]).tolist()) == list(range(len(pos)))
    for tr, va in folds:
        lo, hi = pos[va].min(), pos[va].max()
        assert ((pos[tr] < lo - WT.EMBARGO) | (pos[tr] > hi + WT.EMBARGO)).all() and len(tr)


def test_cv_pick_prefers_stronger_penalty_within_tie():
    X, y = _logit_data(n=3000)
    lam, sc = WT.cv_pick(lambda A, b, g: WT.fit_newton(A, b, g), WT.L2_GRID, X, y, np.arange(len(y)) * 5)
    best = max(s for s in sc if s is not None)
    i = WT.L2_GRID.index(lam)
    assert sc[i] >= best - WT.TIE and all(s is None or s < best - WT.TIE for s in sc[i + 1:])


def _panel(n=3000, p=12, seed=3):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("1996-01-01", periods=n)
    X = pd.DataFrame(rng.uniform(-0.5, 0.5, (n, p)), index=days, columns=[f"f{j}" for j in range(p)])
    z = np.cumsum(rng.normal(size=n)) * 0.05
    X["f0"] = np.clip(np.tanh(z) / 2 + rng.normal(size=n) * 0.1, -0.5, 0.5)
    y = pd.Series((rng.random(n) < WT.sigmoid(-1.5 + 3 * X["f0"].to_numpy())).astype(float), index=days)
    y.iloc[-60:] = np.nan
    meta = {"cols": list(X.columns), "domain": {c: f"d{int(c[1:]) % 4}" for c in X.columns}, "a0_idx": [0, 1, 2]}
    return X, y, meta


def _flip_unknown_at(y: pd.Series, when: str) -> pd.Series:
    k0 = int(np.flatnonzero(y.index >= when)[0])
    y2 = y.copy()
    y2.iloc[k0 - WT.HORIZON:] = 1 - y2.iloc[k0 - WT.HORIZON:]           # 该日还不知道答案的标签全部改掉
    return y2


def test_walk_forward_does_not_use_future_labels():
    X, y, meta = _panel()
    years, sch = list(range(2000, 2008)), ["RIDGE", "NNRIDGE", "AUCW", "LASSO", "PRIOR"]
    a0 = pd.Series(X[["f0", "f1", "f2"]].mean(axis=1).to_numpy() * 100, index=X.index)
    raw1, u1, fits = WT.walk_forward(X, y, sch, meta, years, pd.Timestamp("1996-01-01"), fixed={"A0": a0})
    raw2, u2, _ = WT.walk_forward(X, _flip_unknown_at(y, "2004-01-01"), sch, meta, years, pd.Timestamp("1996-01-01"),
                                  fixed={"A0": a0})
    before = X.index < "2005-01-01"
    for k in raw1:
        pd.testing.assert_series_equal(raw1[k][before], raw2[k][before])
        pd.testing.assert_series_equal(u1[k][before], u2[k][before])
    assert (raw1["RIDGE"][X.index >= "2006-01-01"] != raw2["RIDGE"][X.index >= "2006-01-01"]).any()
    assert raw1["RIDGE"][X.index < "2000-01-01"].isna().all() and u1["A0"].dropna().between(0, 1).all()
    assert [f["year"] for f in fits["RIDGE"]] == years and fits["A0"][0]["n"] == fits["RIDGE"][0]["n"]
    last = fits["RIDGE"][-1]                                          # 训练样本只到重估日之前 60 个交易日以前
    k0 = int(np.flatnonzero(X.index >= "2007-01-01")[0])
    assert last["n"] == len(WT.train_positions(X.index, y.to_numpy(), k0, pd.Timestamp("1996-01-01")))
    assert WT.train_positions(X.index, y.to_numpy(), k0, pd.Timestamp("1996-01-01")).max() <= k0 - WT.HORIZON - 1


def test_calibration_uses_only_known_past():
    X, y, _ = _panel()
    s = pd.Series(np.r_[np.full(800, np.nan), np.random.default_rng(0).uniform(size=2200)], index=X.index)
    years = list(range(2000, 2008))
    p1, c1 = WT.calibrate_walk_forward(s, y, years, pd.Timestamp("1999-01-01"))
    p2, c2 = WT.calibrate_walk_forward(s, _flip_unknown_at(y, "2004-01-01"), years, pd.Timestamp("1999-01-01"))
    before = X.index < "2005-01-01"
    pd.testing.assert_series_equal(p1[before], p2[before])
    pd.testing.assert_series_equal(c1[before], c2[before])
    assert p1[X.index >= "2002-01-01"].notna().all() and (p1[X.index >= "2006-01-01"] != p2[X.index >= "2006-01-01"]).any()


def test_u_and_platt():
    q = WT.quantiles(np.arange(101.0))
    u = WT.to_u([0.0, 50.0, 100.0, 200.0, -5.0, np.nan], q)
    assert u[:5].tolist() == pytest.approx([0, 0.5, 1, 1, 0]) and np.isnan(u[5])
    rng = np.random.default_rng(2)
    uu = rng.uniform(size=20000)
    y = (rng.random(20000) < WT.sigmoid(-2 + 3 * uu)).astype(float)
    a, b = WT.platt(uu, y)
    assert a == pytest.approx(-2, abs=0.15) and b == pytest.approx(3, abs=0.25)
    assert WT.prob([a, b], 0.5) == pytest.approx(float(WT.sigmoid(a + b * 0.5)))
    assert WT.prob([float("nan"), 1.0], 0.5) is None


def test_prior_with_huge_penalty_is_equal_weight():
    X, y, _ = _panel()
    Xn, yn = X.to_numpy(), y.fillna(0).to_numpy()
    p = Xn.shape[1]
    w = WT.fit_newton(np.c_[Xn.mean(axis=1, keepdims=True), Xn], yn, np.r_[0.0, np.full(p, 1e3)])
    beta = w[2:] + w[1] / p
    assert np.ptp(beta) < 1e-3 * np.abs(beta).max()


def test_schemes_shapes_and_rules():
    X, y, meta = _panel()
    sl = slice(0, 2000, 5)
    Xn, yn, pos = X.to_numpy()[sl], y.to_numpy()[sl], np.arange(0, 2000, 5)
    ws = {s: WT.fit_scheme(s, Xn, yn, pos, meta)[0] for s in WT.SCHEMES}
    for s, w in ws.items():
        assert w.shape == (X.shape[1] + 1,) and np.isfinite(w).all(), s
    assert ws["EW"][1:] == pytest.approx(np.full(12, 1 / 12))
    M, doms = WT._domain_matrix(meta["cols"], meta["domain"])
    assert (ws["DOM"][1:] @ (M > 0)).tolist() == pytest.approx([1 / len(doms)] * len(doms))   # 每个领域合计相同
    assert ws["DOM"][1:].sum() == pytest.approx(1.0)
    assert (ws["NNRIDGE"][1:] >= 0).all() and (ws["DOMLR"][1:] >= 0).all()
    assert (ws["A0NN"][4:] == 0).all()                                # 只用现行因素（a0_idx = 0, 1, 2）
    assert (ws["TOP10"][1:] > 0).sum() == 10 and ws["TOP10"][1:].sum() == pytest.approx(1.0)
    for s in ("RIDGE", "NNRIDGE", "AUCW", "STAB", "PRIOR"):           # 只有 f0 有信息 → f0 权重最大
        assert int(np.argmax(ws[s][1:])) == 0, s


def test_bootstrap_identical_scores_zero_delta():
    rng = np.random.default_rng(5)
    s = rng.uniform(size=600)
    y = (rng.random(600) < s).astype(float)
    d = WT.block_bootstrap_delta({"same": s.copy(), "noise": rng.uniform(size=600)}, s, y, block=50, reps=200)
    assert np.nanmax(np.abs(d["same"])) == 0 and np.nanmedian(d["noise"]) < 0


def test_forecast_applies_frozen_weights_and_log_keeps_first(tmp_path):
    rng = np.random.default_rng(7)
    days = pd.bdate_range("2015-01-01", periods=900)
    cols = TH.US_COLS + ["gold"]
    raw_ex = pd.DataFrame(rng.normal(size=(900, len(cols))), index=days, columns=cols)
    F = {"US": (raw_ex, None), "JP": (raw_ex, None)}
    q = np.linspace(-1, 1, 101).tolist()
    W = {"US": {"cols": cols, "a0_cols": TH.US_COLS, "adopted": "RIDGE", "best": "RIDGE", "base10": 0.12, "base15": 0.05,
                "schemes": {"A0": {"q": np.linspace(0, 100, 101).tolist(), "cal10": [-2.0, 1.0], "cal15": [-3.0, 1.0]},
                            "RIDGE": {"b0": 0.1, "beta": {"gold": 2.0, "vix": -0.5}, "q": q, "cal10": [-2.5, 2.0],
                                      "cal15": [-3.5, 2.0], "oos": {"auc10": 0.7}},
                            "DOM": {"b0": 0.0, "beta": {"gold": 0.5, "vix": 0.25, "credit": 0.25}, "q": q,
                                    "cal10": [-2.0, 1.0], "cal15": [-3.0, 1.0]}}}}
    fp = tmp_path / "w.json"
    fp.write_text(json.dumps(W), encoding="utf-8")
    fc = WT.forecast(F, {}, path=fp)
    assert set(fc) == {"US"}
    r = fc["US"]
    pg = TH.expanding_pct(raw_ex["gold"]).iloc[-1]
    pv = TH.expanding_pct(raw_ex["vix"]).iloc[-1]
    sc = 0.1 + 2.0 * (pg - 0.5) - 0.5 * (pv - 0.5)
    u = float(np.interp(sc, q, WT.QGRID))
    assert r["p10"]["RIDGE"] == pytest.approx(float(WT.sigmoid(-2.5 + 2.0 * u)))
    a0 = TH._eq(pd.DataFrame({c: TH.expanding_pct(raw_ex[c]) for c in TH.US_COLS})).iloc[-1]
    assert r["u"]["A0"] == pytest.approx(round(a0 / 100, 4), abs=1e-4)
    assert r["show"] == "RIDGE" and r["date"] == str(days[-1].date()) and r["oos"]["auc10"] == 0.7
    pc = TH.expanding_pct(raw_ex["credit"]).iloc[-1]
    assert r["dom"] == pytest.approx(round(100 * (0.5 * pg + 0.25 * pv + 0.25 * pc), 2))   # 领域均衡的 0–100 读数
    lp = tmp_path / "f.csv"
    WT.log_forward(fc, lp)
    fc["US"]["p10"]["RIDGE"] = 0.99
    WT.log_forward(fc, lp)                                            # 已记日期 × 市场保留最早值
    df = pd.read_csv(lp)
    assert len(df) == 1 and df["RIDGE"].iloc[0] < 0.99 and set(df.columns) >= {"date", "market", "A0", "RIDGE"}
