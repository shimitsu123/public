"""scripts/kshape_joint_study.py 的纯函数：特征不偷看、正在走的这一周 / 月与走完的周 / 月、目标、判定、按块 t 检验、取样表的超额。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kshape_joint_study as S  # noqa: E402


def _df(n=500, seed=0, start="2019-01-01"):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    o = c * np.exp(rng.normal(0, 0.005, n))
    hi = np.maximum(c, o) * (1 + rng.uniform(0, 0.02, n))
    lo = np.minimum(c, o) * (1 - rng.uniform(0, 0.02, n))
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"Open": o, "High": hi, "Low": lo, "Close": c, "Volume": 1.0}, index=idx)


def test_feats_do_not_peek():
    df = _df()
    full = S.ticker_feats(df)
    for i in (330, 331, 332, 333, 334, 357, 420, 499):                       # 周一〜周五、月末、最后一天
        cut = S.ticker_feats(df.iloc[:i + 1])
        assert np.allclose(full["X"][i], cut["X"][i], equal_nan=True), i
    assert full["X"].shape == (500, len(S.FEATS)) == (500, 29)


def test_partial_and_completed_week_match_bars():
    from qbreak import kline as K
    df = _df(seed=1)
    f = S.ticker_feats(df)
    wb = K.bars(df, "W")
    wc = wb["Close"].to_numpy()
    lr = np.log(wc[1:] / wc[:-1])
    i = 402                                                                  # 一周中间的某一天
    d = df.index[i]
    j = int(np.searchsorted(wb.index.values, d.to_datetime64(), side="left"))  # d 所在的周（日期 = 那周最后一个交易日）
    assert wb.index[j] >= d and (j == 0 or wb.index[j - 1] < d)
    sig = np.std(lr[j - 21:j - 1], ddof=1)                                   # 第 j 周之前 20 个走完的周的涨跌（lr[k] = 第 k+1 周）
    wk = df.loc[(df.index > wb.index[j - 1]) & (df.index <= d)]
    col = {k: S.FEATS.index(k) for k in ("w_z0", "w_clv0", "w_rg0", "w_z1", "w_clv1", "w_frac")}
    assert np.isclose(f["X"][i, col["w_z0"]], (df["Close"].iloc[i] / wc[j - 1] - 1) / sig, rtol=1e-5)
    hi, lo = wk["High"].max(), wk["Low"].min()
    assert np.isclose(f["X"][i, col["w_clv0"]], (df["Close"].iloc[i] - lo) / (hi - lo), rtol=1e-5)
    assert np.isclose(f["X"][i, col["w_rg0"]], (hi - lo) / wc[j - 1] / sig, rtol=1e-5)
    sig1 = np.std(lr[j - 22:j - 2], ddof=1)
    assert np.isclose(f["X"][i, col["w_z1"]], (wc[j - 1] / wc[j - 2] - 1) / sig1, rtol=1e-5)
    hb, lb = wb["High"].iloc[j - 1], wb["Low"].iloc[j - 1]
    assert np.isclose(f["X"][i, col["w_clv1"]], (wc[j - 1] - lb) / (hb - lb), rtol=1e-5)
    assert np.isclose(f["X"][i, col["w_frac"]], len(wk) / 5)


def test_daily_lags():
    df = _df(seed=2)
    f = S.ticker_feats(df)
    z0, z2 = S.FEATS.index("d_z0"), S.FEATS.index("d_z2")
    assert np.isclose(f["X"][300, z2], f["X"][298, z0])
    c = df["Close"].to_numpy()
    lr = np.log(c[1:] / c[:-1])
    sig = np.std(lr[279:299], ddof=1)                                        # 第 300 天之前 20 天（lr[k] = 第 k+1 天）
    assert np.isclose(f["X"][300, z0], (c[300] / c[299] - 1) / sig, rtol=1e-5)


def test_targets():
    o = np.array([10.0, 11, 12, 13, 14, 15])
    c = np.array([10.5, 11.5, 12.5, 13.5, 14.5, 15.5])
    d = pd.bdate_range("2020-01-06", periods=6).values.astype("datetime64[ns]")
    r, e = S.targets(o, c, d, 2)
    assert np.isclose(r[0], (12.5 / 11 - 1) * 100) and np.isclose(r[3], (15.5 / 14 - 1) * 100)
    assert np.isnan(r[4:]).all() and e[0] == d[2] and np.isnat(e[5])


def test_verdict_and_constants():
    six = [0.01] * 6
    assert S.verdict(six, 0.001, 0.5, 5, 0.001, 5) == S.VERDICTS[0]
    assert S.verdict(six, 0.001, 0.5, 5, 0.5, 6) == S.VERDICTS[1]
    assert S.verdict(six, 0.001, 0.2, 5, 0.001, 6) == S.VERDICTS[2]           # 分档差不到 0.30
    assert S.verdict(six, 0.001, 0.2, 5, 0.001, 4) == S.VERDICTS[3]           # 只有 4 个样本多
    assert S.verdict([0.01] * 5 + [-0.01], 0.001, 0.9, 1, 0.001, 6) == S.VERDICTS[4]
    assert S.P_MAX == 0.05 / 6 and S.MIN_SPREAD == {1: 0.15, 5: 0.30, 21: 0.60} and S.HORIZONS == (1, 5, 21)
    assert S.GBM["n_trees"] == 300 and S.GBM["seed"] == 0 and S.STEP == 5 and S.CLIP == {1: 10.0, 5: 20.0, 21: 40.0}
    assert len(S.GROUP["D"]) == 9 and len(S.GROUP["W"]) == 10 and len(S.GROUP["M"]) == 10
    assert sorted(S.GROUP["D"] + S.GROUP["W"] + S.GROUP["M"]) == list(range(29))
    assert S.cols_of("SW") == S.GROUP["W"] and S.cols_of("JG") == list(range(29))


def test_block_t_groups_overlapping_days():
    s = pd.Series(np.r_[np.full(10, 1.0), np.full(10, 0.0)], index=np.arange(20))
    assert S.block_t(s, 5)["n"] == 20 and S.block_t(s, 21)["n"] == 4


def test_sample_table_excess_and_window():
    FR = {"a.T": _df(seed=3), "b.T": _df(seed=4), "c.T": _df(seed=5)}
    days = pd.bdate_range("2019-01-01", periods=500).values.astype("datetime64[ns]")
    sd = days[::5]
    X = S.sample_table(FR, sd, (pd.Timestamp("2019-12-01"), pd.Timestamp("2020-08-01")))
    assert len(X) and (X["date"] >= np.datetime64("2019-12-01")).all() and np.isin(X["date"].values, sd).all()
    assert np.allclose(X.groupby("date")["ex5"].sum(), 0, atol=1e-9)
    last = X["date"].max()
    assert X.loc[X["date"] == last, "tg21"].isna().all() or last + np.timedelta64(30, "D") < np.datetime64("2020-08-01")


def test_dir3_and_align_names():
    assert S.dir3(np.array([-1.0, 0.0, 0.6])).tolist() == [0, 1, 2]
    tabs = {s: pd.DataFrame({"d_z0": [1.0, -1.0], "w_z0": [1.0, 0.0], "m_z0": [1.0, 0.0], "ex5": [0.5, -0.5], "ex21": [1.0, -1.0]})
            for s in S.SAMPLES}
    A = S.align_table(tabs)
    up = [r for r in A[5] if r["k"] == 26][0]
    assert up["combo"] == "日涨 · 周涨 · 月涨" and up["same_sign"] and up["eras"]["2017〜26"]["n"] == 2
