"""scripts/kshape_link_study.py 的纯函数：形状编号、上下文（只用走完的块）、退回平滑、横截面 IC / 分档差、判定、打分不偷看。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kshape_link_study as S  # noqa: E402


def _ohlc(close, hi=None, lo=None, start="2020-01-06"):
    c = np.asarray(close, float)
    idx = pd.bdate_range(start, periods=len(c))
    return pd.DataFrame({"Open": c, "High": c if hi is None else hi, "Low": c if lo is None else lo, "Close": c, "Volume": 1.0}, index=idx)


def test_shape_codes_direction_position_and_warmup():
    rng = np.random.default_rng(0)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 40)))
    c = np.r_[c, c[-1] * 1.05, c[-1] * 1.05 * 0.95, c[-1] * 1.05 * 0.95 * 1.0001]
    hi, lo = c * 1.01, c * 0.99
    hi[-3], lo[-3] = c[-3], c[-3] * 0.97                                     # 大涨、收在最高 → 涨·高
    hi[-2], lo[-2] = c[-2] * 1.03, c[-2]                                     # 大跌、收在最低 → 跌·低
    k = S.shape_codes(pd.DataFrame({"High": hi, "Low": lo, "Close": c}), 20)
    assert (k[:21] == -1).all() and (k[21:] >= 0).all()                      # 前 20 块的波动 + 第一块没有涨跌 → 第 21 块起才有
    assert k[-3] == 3 * 2 + 2 and k[-2] == 0 and k[-1] // 3 == 1             # 几乎不动 → 平
    assert S.shape_name(8) == "涨·收在高位" and S.shape_name(0) == "跌·收在低位" and S.shape_name(-1) == "—"


def test_shape_codes_flat_range_is_middle_and_zero_vol_is_unknown():
    c = np.full(30, 100.0)
    assert (S.shape_codes(pd.DataFrame({"High": c, "Low": c, "Close": c}), 20) == -1).all()   # σ = 0 → 算不出


def test_contexts_use_only_completed_blocks():
    rng = np.random.default_rng(1)
    n = 400
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    df = _ohlc(c, c * 1.01, c * 0.99)
    B = S.ticker_blocks(df)
    D, Wk = B["D"], B["W"]
    c1, c2, c3 = S.contexts(B, "D-XC")
    for i in (150, 151, 152, 153, 154, 299):                                 # 周一〜周五都试
        d = D["date"][i]
        j = np.searchsorted(Wk["date"], d, side="right") - 1
        assert Wk["date"][j] <= d and c2[i] == Wk["code"][j]                 # 周K：日期 ≤ 那天的最后一根（走完的）
        assert j + 1 >= len(Wk["date"]) or Wk["date"][j + 1] > d
    a1, a2, a3 = S.contexts(B, "W-FD")
    for j in (40, 41):
        k = np.searchsorted(D["date"], Wk["date"][j], side="right") - 1
        assert (a1[j], a2[j], a3[j]) == (D["code"][k], D["code"][k - 1], D["code"][k - 2])
    s1, s2, s3 = S.contexts(B, "M-SC")
    assert (s1[10], s2[10], s3[10]) == tuple(B["M"]["code"][[10, 9, 8]])


def test_next_block_targets_and_gap():
    rng = np.random.default_rng(2)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 300)))
    df = _ohlc(c, c * 1.01, c * 0.99)
    df = df.drop(df.index[(df.index >= "2020-03-02") & (df.index <= "2020-03-13")])   # 整两周没有成交
    W = S.ticker_blocks(df)["W"]
    i = int(np.where(W["date"] == np.datetime64("2020-02-28"))[0][0])
    assert np.isnan(W["rx"][i]) and W["y"][i] == -1                          # 下一块不是紧接着的那一周 → 不算
    j = i + 2
    o = df.loc[df.index.to_period("W-FRI") == pd.Timestamp(W["date"][j + 1]).to_period("W-FRI")]
    assert np.isclose(W["rx"][j], (o["Close"].iloc[-1] / o["Open"].iloc[0] - 1) * 100)


def test_fit_backoff_math():
    c1 = np.array([0, 0, 0, 1])
    c2 = np.array([0, 0, 1, 0])
    c3 = np.zeros(4, int)
    y = np.array([8, 8, 0, 4])
    ex = np.array([1.0, 3.0, -2.0, 0.0])
    F = S.fit(c1, c2, c3, y, ex, alpha=2.0)
    p0 = (np.bincount(y, minlength=9) + 1) / (4 + 9)
    assert np.allclose(F["p0"], p0)
    p1_0 = (np.bincount([8, 8, 0], minlength=9) + 2 * p0) / (3 + 2)
    p2_00 = (np.bincount([8, 8], minlength=9) + 2 * p1_0) / (2 + 2)
    p3_000 = (np.bincount([8, 8], minlength=9) + 2 * p2_00) / (2 + 2)
    p, m = S.predict(F, [0], [0], [0])
    assert np.allclose(p[0], p3_000) and np.isclose(p[0].sum(), 1)
    m0 = ex.mean()
    m1 = (2.0 + 2 * m0) / (3 + 2)
    m2 = (4.0 + 2 * m1) / (2 + 2)
    assert np.isclose(m[0], (4.0 + 2 * m2) / (2 + 2))
    _, mu = S.predict(F, [5], [5], [5])                                      # 没见过的上下文 → 退回 m0
    assert np.isclose(mu[0], m0)
    assert F["n2"][0] == 2 and F["s2"][0] == 4.0


def test_per_block_ic_and_spread():
    k = np.repeat([1, 2, 3], 30)
    pred = np.tile(np.arange(30.0), 3)
    ex = np.r_[np.arange(30.0), -np.arange(30.0), np.zeros(30)]
    pb = S.per_block(k, pred, ex)
    assert np.isclose(pb.loc[1, "ic"], 1) and np.isclose(pb.loc[2, "ic"], -1) and 3 not in pb.index   # 实际全一样 → 不算
    assert np.isclose(pb.loc[1, "spread"], np.mean(np.arange(20, 30)) - np.mean(np.arange(0, 10)))
    assert S.per_block(k[:30], pred[:30], ex[:30], min_n=31).empty


def test_t_one_sided_and_verdict():
    t = S.t_one_sided(np.r_[np.full(50, 0.1), np.full(50, 0.0)])
    assert t["p"] < 0.001 and t["n"] == 100
    six = [0.01] * 6
    assert S.verdict(six, six, 0.001, 0.2, 0.5, "D") == S.VERDICTS[0]
    assert S.verdict(six, six, 0.001, 0.1, 0.5, "D") == S.VERDICTS[2]        # 分档差不到门槛
    assert S.verdict(six, [2.0] * 6, 0.5, 0.1, 1.5, "W") == S.VERDICTS[1]
    assert S.verdict([0.01] * 5 + [-0.01], six, 0.001, 0.9, 0.5, "M") == S.VERDICTS[3]
    assert S.P_MAX == 0.05 / 8 and S.MIN_SPREAD == {"D": 0.15, "W": 0.30, "M": 0.60}


def test_daily_scores_do_not_peek_and_flags_bottom_third():
    rng = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 600)))
    df = _ohlc(c, c * 1.01, c * 0.99)
    B = S.ticker_blocks(df)
    X = S.model_rows(B, "W-XC")
    F = S.fit(X["c1"], X["c2"], X["c3"], X["y"], X["rx"].fillna(0))
    days = df.index.values.astype("datetime64[ns]")
    sc = S.daily_scores(B, "W-XC", F, days)
    Bc = S.ticker_blocks(df.iloc[:450])                                      # 截到第 450 天：之前的分数完全一样（没有用到之后的数据）
    sc2 = S.daily_scores(Bc, "W-XC", F, days[:450])
    last_week_end = pd.Timestamp(days[449]).to_period("W-FRI")
    done = pd.DatetimeIndex(days[:450]).to_period("W-FRI") < last_week_end
    assert np.allclose(sc[:450][done], sc2[done], equal_nan=True)
    d = S.daily_scores(B, "D-XC", S.fit(*(S.model_rows(B, "D-XC")[k] for k in ("c1", "c2", "c3", "y")),
                                        S.model_rows(B, "D-XC")["rx"].fillna(0)), days)
    assert np.isfinite(d[300]) and not np.isfinite(S.daily_scores(B, "D-XC", F, days + np.timedelta64(12, "h"))[300])  # 没有这一天的块 → 不打分
    Sw = pd.DataFrame({"a": [1.0, 3.0], "b": [2.0, np.nan], "c": [3.0, 1.0], "d": [np.nan, 2.0]}, index=pd.to_datetime(["2020-01-06", "2020-01-07"]))
    Fl = S.block_flags(Sw)
    assert Fl.loc["2020-01-06"].tolist() == [True, False, False, False] and Fl.loc["2020-01-07"].tolist() == [False, False, True, False]
    assert S.lookup_wide(Fl, ["a", "c", "x"], ["2020-01-06", "2020-01-07", "2020-01-06"]).tolist() == [True, True, False]
    assert S.tercile_of(Sw, ["a", "b", "c"], ["2020-01-06"] * 3).tolist() == [0, 1, 2]


def test_registered_constants():
    assert S.MODELS == ("D-SC", "D-XC", "W-SC", "W-XC", "W-FD", "M-SC", "M-XC", "M-FW")
    assert S.B_MODEL == {"KXD": "D-XC", "KXW": "W-XC", "KXM": "M-XC"} and S.CUT == 1 / 3 and S.ALPHA == 30.0
    assert S.NVOL == {"D": 20, "W": 20, "M": 12} and S.DIR_Z == 0.5 and S.FP == "1241753c8f2529c6"
    assert S.TRAIN == {"I": ("E", "W"), "II": ("J", "Jx")}
    assert all(S.MODEL_OF[s] not in [f for f, tr in S.TRAIN.items() if s in tr] for s in S.SAMPLES)   # 每个样本都用没见过它的模型


def test_same_prep_requires_identical_b4():
    ref = {"n": 27, "win": 77.78, "calmar": 1.1861}
    assert S.same_prep({"n": 27, "win": 77.78, "calmar": 1.1861}, ref)
    assert not S.same_prep({"n": 28, "win": 77.78, "calmar": 1.1861}, ref)
    assert not S.same_prep({"n": 27, "win": 77.78, "calmar": 1.1862}, ref)
    assert not S.same_prep({"n": 27, "win": 77.78, "calmar": 1.1861}, None)
