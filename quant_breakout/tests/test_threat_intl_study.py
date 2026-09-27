"""scripts/threat_intl_study.py：市场与分组的一致性、早收盘市场的时点（美国当天的数据不进当天的特征）、逐年权重的样本外应用、
合并训练只用别的组且只用答案已知的样本、联合自助法、判定 C1〜C6。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import threat_intl_study as TI  # noqa: E402


def test_markets_and_folds():
    allk = ["US", "JP"] + list(TI.MARKETS)
    flat = [k for f in TI.FOLDS for k in f]
    assert sorted(flat) == sorted(allk) and len(flat) == len(set(flat)) == 24
    assert sum(TI.group(k) == "dev" for k in TI.MARKETS) == 16
    assert sum(TI.group(k) == "em" for k in TI.MARKETS) == 6
    assert all(TI.MARKETS[k][3] in ("early", "americas") for k in TI.MARKETS)


def _series(days, seed, level=1.0, scale=0.01):
    rng = np.random.default_rng(seed)
    return pd.Series(level * np.exp(np.cumsum(rng.normal(0, scale, len(days)))), index=days)


def _inputs():
    us = pd.bdate_range("1993-01-01", "2012-12-31")
    mth = pd.date_range("1990-01-01", "2012-12-01", freq="MS")
    qtr = pd.date_range("1990-01-01", "2012-12-01", freq="QS")
    wk = pd.date_range("1990-01-05", "2012-12-28", freq="W-FRI")
    raw = {k: _series(us, i, 10) for i, k in enumerate(["VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "DCOILWTICO"])}
    raw["UNRATE"] = _series(mth, 9, 5)
    d = {"raw": raw, "fx": _series(us, 11, 110)}
    x = {k: _series(wk, 20 + i) for i, k in enumerate(["NFCI", "STLFSI4", "ICSA"])}
    for i, k in enumerate(["T10Y2Y", "DGS2", "DFF", "VIX", "DXY", "SKEW", "VIX3M", "MOVE", "GC", "SI", "HG", "NG", "ZW", "ZC", "ZS", "GSCI"]):
        x[k] = _series(us, 40 + i, 50)
    x["JPCALL"] = _series(mth, 70)
    for i, k in enumerate(["SLOOS", "DELINQ", "CHARGEOFF", "TK_LEND", "TK_CASH"]):
        x[k] = _series(qtr, 80 + i)
    x["EPU"] = _series(pd.date_range("1990-01-01", "2012-12-31"), 90, 100)
    x["JPLNG"] = _series(mth, 91)
    x["GPRD"] = _series(pd.date_range("1990-01-01", "2012-12-31"), 92, 100)
    x["GPRC_JPN"] = _series(mth, 93)
    return d, x


def test_early_market_uses_previous_us_close():
    d, x = _inputs()
    days = pd.bdate_range("1995-01-02", "2012-12-31")
    close = _series(days, 5, 1000)
    f1, _ = TI.build_market("DAX", close, d, x, {})
    D = pd.Timestamp("2008-06-10")
    d2 = {"raw": dict(d["raw"]), "fx": d["fx"]}
    v = d2["raw"]["VIXCLS"].copy()
    v.loc[v.index >= D] = v.loc[v.index >= D] * 3                          # 美国 D 当天起 VIX 变成 3 倍
    d2["raw"]["VIXCLS"] = v
    f2, _ = TI.build_market("DAX", close, d2, x, {})
    assert np.isclose(f1.at[D, "vix"], f2.at[D, "vix"])                     # 欧洲 D 日收盘时还不知道美国 D 日的收盘
    nxt = days[days.get_loc(D) + 1]
    assert not np.isclose(f1.at[nxt, "vix"], f2.at[nxt, "vix"])
    assert not any(c in f1 for c in TI.JP_ONLY)                             # 日本专用因素去掉
    fa, _ = TI.build_market("TSX", close, d2, x, {})                        # 美洲 = 当天
    fb, _ = TI.build_market("TSX", close, d, x, {})
    assert not np.isclose(fa.at[D, "vix"], fb.at[D, "vix"])


def _P(n_days=5000, seed=0, start="1994-01-03"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n_days)
    X = pd.DataFrame(rng.uniform(-0.5, 0.5, (n_days, 3)), index=idx, columns=["a", "b", "c"])
    y = pd.Series((rng.random(n_days) < 0.15).astype(float), index=idx)
    y.iloc[-60:] = np.nan
    return {"X": X, "y10": y}


def test_apply_fits_out_of_sample_and_bounds():
    P = _P()
    fits = {yr: (0.0, np.array([1.0, 0.0, 0.0])) for yr in TI.YEARS}
    raw, u = TI.apply_fits(P["X"], P["y10"], fits)
    assert u.dropna().between(0, 1).all()
    assert u[u.index < pd.Timestamp("2005-01-01")].isna().all()
    assert np.allclose(raw.dropna(), P["X"]["a"][raw.notna()])


def test_pooled_training_uses_answer_known_rows_only():
    P = {"A": _P(seed=1), "B": _P(seed=2), "C": _P(seed=3)}
    X, y, pos = TI.pooled_training(P, ["A", "B"], 2010)
    assert len(y) > 0 and np.all(np.diff(pos) >= 0)
    last_ok = {}
    for k in ("A", "B"):
        idx = P[k]["X"].index
        k0 = int(idx.searchsorted(pd.Timestamp("2010-01-01")))
        last_ok[k] = idx[k0 - 61]
    cutoff = TI.bday_ordinal(pd.DatetimeIndex([max(last_ok.values())]))[0]
    assert pos.max() <= cutoff


def test_joint_bootstrap_and_judge():
    rng = np.random.default_rng(0)
    E = {}
    for k in ("M1", "M2", "M3"):
        dates = pd.bdate_range("2011-01-03", periods=1500)
        y = (rng.random(1500) < 0.2).astype(float)
        u0 = rng.random(1500)
        E[k] = {"ok": True, "mask_dates": dates, "_y": y, "_u": {m: u0.copy() for m in TI.METHODS}}
    b = TI.joint_bootstrap(E, ["M1", "M2", "M3"], reps=30)
    assert all(np.allclose(v[np.isfinite(v)], 0.0) for v in b.values())    # 候选 = A0 → 差 0
    # 判定：构造 3 个发达 + 1 个新兴市场的汇总
    ev = {}
    for k, d in (("D1", 0.05), ("D2", 0.04), ("D3", 0.06), ("E1", 0.02)):
        ev[k] = {"ok": True, "A0": {"bss10": -0.01}}
        for m in TI.CANDS:
            ev[k][m] = {"d_auc10": d, "d_sub": [d, d], "bss10": 0.0}
    boot = {m: np.full(50, 0.02) for m in TI.CANDS}
    old = TI.C2_MIN_N
    TI.C2_MIN_N = 3
    try:
        J = TI.judge(ev, ["D1", "D2", "D3"], ["E1"], boot)
    finally:
        TI.C2_MIN_N = old
    assert J["passed"] == list(TI.CANDS) and J["adopted"] in TI.CANDS
    ev["E1"]["DOM"]["d_auc10"] = -0.01
    TI.C2_MIN_N = 3
    try:
        J2 = TI.judge(ev, ["D1", "D2", "D3"], ["E1"], boot)
    finally:
        TI.C2_MIN_N = old
    assert "DOM" not in J2["passed"]                                         # C6 新兴同号不满足
