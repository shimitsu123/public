"""scripts/learned_exit_study.py 的纯函数：特征不偷看、目标、逐年前推只用之前卖掉的单笔、标记门槛、单笔统计、账户钩子按（票, 成交日）查。"""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import learned_exit_study as S  # noqa: E402


def _frame(n=120, seed=0):
    rng = np.random.default_rng(seed)
    d = pd.bdate_range("2010-01-04", periods=n)
    c = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    o = c * (1 + rng.normal(0, 0.005, n))
    h = np.maximum(c, o) * (1 + rng.random(n) * 0.01)
    lo = np.minimum(c, o) * (1 - rng.random(n) * 0.01)
    f = pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "atr": c * 0.02, "ext_ma20_pct": rng.normal(size=n), "rsi": 50 + rng.normal(size=n),
                      "vol_ratio": 1 + rng.random(n), "macd_hist": rng.normal(size=n), "upper_shadow_ratio": rng.random(n)}, index=d)
    return f


def test_features_do_not_peek():
    f = _frame()
    nk = pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.01, 300))), index=pd.bdate_range("2009-06-01", periods=300))
    nkf = S.nikkei_feats(nk)
    usb = pd.Series(np.r_[np.zeros(150), np.ones(150)], index=pd.bdate_range("2009-06-01", periods=300))
    kk, px = 10, float(f["Open"].iloc[10])
    full = S.features(f, kk, px, nkf, usb)
    assert list(full.columns) == S.FEATS and len(S.FEATS) == 15 and "rs" not in S.FEATS and len(full) == len(f) - kk
    for t in (12, 40, 90, 119):
        part = S.features(f.iloc[:t + 1], kk, px, nkf[nkf.index <= f.index[t]], usb[usb.index < f.index[t]])
        assert np.allclose(full.loc[f.index[t]].to_numpy(float), part.iloc[-1].to_numpy(float), equal_nan=True), t


def test_feature_values():
    f = _frame()
    kk, px = 5, 100.0
    X = S.features(f, kk, px)
    t = 30
    c = f["Close"].to_numpy()
    h = f["High"].to_numpy()
    row = X.iloc[t - kk]
    assert np.isclose(row["gain"], (c[t] / px - 1) * 100) and np.isclose(row["mfe"], (c[kk:t + 1].max() / px - 1) * 100)
    assert np.isclose(row["dd_atr"], (max(px, h[kk:t + 1].max()) - c[t]) / f["atr"].iloc[t]) and row["hold"] == t - kk + 1
    assert np.isclose(row["r5"], (c[t] / c[t - 5] - 1) * 100) and np.isnan(row["nk_r20"]) and np.isnan(row["us_bear"])
    assert list(S.since_peak(np.array([1, 3, 2, 3, 1]))) == [0, 0, 1, 0, 1]


def test_us_bear_uses_previous_day():
    f = _frame(30)
    usb = pd.Series(0.0, index=f.index)
    usb.iloc[20] = 1.0
    X = S.features(f, 0, 100.0, None, usb)
    assert X["us_bear"].iloc[20] == 0.0 and X["us_bear"].iloc[21] == 1.0                           # 当天的值第二天才用


def test_remaining():
    r = S.remaining([100.0, 110.0], 105.0, 0.001)
    assert np.allclose(r, [(105 / 99.9 - 1) * 100, (105 / (110 * 0.999) - 1) * 100])


def _traj(fill, exit_, n=5, sm="E"):
    idx = pd.bdate_range(fill, periods=n)
    return {"ticker": "1.T", "fill": pd.Timestamp(fill), "exit": pd.Timestamp(exit_), "X": pd.DataFrame(np.ones((n, len(S.FEATS))), index=idx, columns=S.FEATS),
            "rem": np.arange(n, dtype=float), "sm": sm, "nb": 1.0, "alt": np.arange(n, dtype=float) - 2, "hold": n + 1}


def test_fwd_uses_only_exited_before(monkeypatch):
    pool = [_traj(f"{y}-03-01", f"{y}-05-01") for y in range(2001, 2006) for _ in range(40)]
    seen = []

    def fake(Xtr, ytr, Xs):
        seen.append(len(ytr))
        return [np.full(len(x), float(len(ytr))) for x in Xs]
    monkeypatch.setattr(S, "fit_predict", fake)
    monkeypatch.setattr(S, "MIN_TRAIN", 100)
    tg = [_traj("2004-12-27", "2005-02-01", n=10)]
    p, cover = S.fwd_preds(pool, tg, years=range(2004, 2006))
    assert cover[2004] == 120 and cover[2005] == 160 and seen == [600, 800]
    yr = tg[0]["X"].index.year
    assert np.allclose(p[0][yr == 2004], 600) and np.allclose(p[0][yr == 2005], 800)
    p2, _ = S.fwd_preds(pool, tg, years=range(2002, 2003))
    assert np.isnan(p2[0]).all()                                                                  # 2002：之前卖掉的只有 40 笔 < 100


def test_loeo_excludes_window(monkeypatch):
    pool = [_traj("2003-03-01", "2003-04-01"), _traj("2008-03-03", "2008-04-01"), _traj("2012-03-01", "2012-04-02")]
    seen = []
    monkeypatch.setattr(S, "fit_predict", lambda Xtr, ytr, Xs: (seen.append(len(ytr)), [np.zeros(len(x)) for x in Xs])[1])
    S.loeo_preds(pool, [pool[1]], (pd.Timestamp("2006-10-01"), pd.Timestamp("2016-10-01")))
    assert seen == [5]


def test_flags_and_first():
    T = _traj("2010-01-04", "2010-02-01")
    p = np.array([0.5, np.nan, -0.2, 0.0, -2.0])
    assert S.first_flag(p, 0.0) == 2 and S.first_flag(p, -1.0) == 4 and S.first_flag(np.full(3, np.nan), 0.0) is None
    assert S.flag_days(T, p, 0.0) == frozenset([T["X"].index[2], T["X"].index[4]])
    assert S.CANDS == {"LXR0": 0.0, "LXR1": -1.0} and S.CLIP == 30.0 and S.MIN_TRAIN == 150 and S.GBM["loss"] == "l2" and S.POSTHOC


def test_pool_stats_and_oracle():
    st = S.pool_stats([1.0, -2.0, 3.0, -1.0], [1.0, -1.0, 2.0, 0.5], [False, True, True, True], [10, 10, 10, 10], [10, 5, 6, 7])
    assert st["n"] == 4 and st["changed"] == 3 and np.isclose(st["dwin"], 25.0) and np.isclose(st["dmean"], (0 + 1 - 1 + 1.5) / 4)
    assert np.isclose(st["g"], 1.5 / 3) and np.isclose(st["hold_c"], 7.0)
    T1, T2 = _traj("2010-01-04", "2010-02-01"), _traj("2010-01-04", "2010-02-01")
    T2["nb"] = 10.0
    assert np.isclose(S.oracle([T1, T2]), ((4 - 2) - 1 + 0) / 2)


def test_spearman_a1_verdict():
    x = np.arange(100.0)
    assert np.isclose(S.spearman(x, x ** 2), 1.0) and S.spearman(x[:10], x[:10]) is None
    assert S.a1_reading({"Z": 0.06, "E": 0.05, "J": 0.01})["ok"] and not S.a1_reading({"Z": None, "E": 0.2, "J": 0.0})["ok"]
    assert S.verdict({"ok": False}) == "第一关不过" and S.verdict({"ok": True}).startswith("第一关通过")


def test_entry_keyed_hook():
    d = pd.bdate_range("2020-01-06", periods=5)
    pos = {"1.T": SimpleNamespace(market="JP", entry_date="2020-01-07"), "2.T": SimpleNamespace(market="JP", entry_date=pd.Timestamp("2020-01-06")),
           "3.T": SimpleNamespace(market="US", entry_date="2020-01-06")}
    eng = SimpleNamespace(gidx=d, st=SimpleNamespace(pos=pos, pending_exit={}))
    xt = {("1.T", "2020-01-07"): frozenset([d[2]]), ("2.T", "2020-01-07"): frozenset([d[2]]), ("3.T", "2020-01-06"): frozenset([d[2]])}
    S._tick_exit_entry(eng, 2, xt)
    assert eng.st.pending_exit == {"1.T": S.REASON}                                              # 2.T 成交日对不上、3.T 不是日本
    eng.st.pending_exit = {"1.T": "chandelier"}
    S._tick_exit_entry(eng, 2, xt)
    assert eng.st.pending_exit == {"1.T": "chandelier"}                                          # 已排队的不改


def test_hook_restored():
    import candle_portfolio as CP
    old = CP.MixEngine._tick_exit
    with S.entry_hook():
        assert CP.MixEngine._tick_exit is S._tick_exit_entry
    assert CP.MixEngine._tick_exit is old
