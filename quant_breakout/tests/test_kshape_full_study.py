"""scripts/kshape_full_study.py 的纯函数：完整 K 线的 5 个数还原得出 OHLC、不偷看、正在走的这一周用这周第一天的开盘、经典形状、判定、系数占比。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kshape_full_study as S  # noqa: E402
import kshape_joint_study as KJ  # noqa: E402


def _df(n=500, seed=0, start="2019-01-01"):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    o = c * np.exp(rng.normal(0, 0.005, n))
    hi = np.maximum(c, o) * (1 + rng.uniform(0, 0.02, n))
    lo = np.minimum(c, o) * (1 - rng.uniform(0, 0.02, n))
    return pd.DataFrame({"Open": o, "High": hi, "Low": lo, "Close": c, "Volume": 1.0}, index=pd.bdate_range(start, periods=n))


def test_five_recovers_ohlc():
    o, h, lo, c, p, s = 101.0, 106.0, 98.0, 104.0, 100.0, 0.02
    z, gap, body, up, lw = (float(x) for x in S.five(np.array(o), np.array(h), np.array(lo), np.array(c), np.array(p), np.array(s)))
    k = p * s
    assert np.isclose(p * (1 + gap * s), o) and np.isclose(o + body * k, c) and np.isclose(max(o, c) + up * k, h) and np.isclose(min(o, c) - lw * k, lo)
    assert np.isclose(z, gap + body)


def test_feats_do_not_peek_and_shape():
    df = _df()
    full = S.ticker_feats(df)
    assert full["X"].shape == (500, len(S.ALL)) and len(S.FEATS) == 47 and len(S.OLD) == 29
    for i in (330, 331, 334, 357, 420, 499):
        cut = S.ticker_feats(df.iloc[:i + 1])
        assert np.allclose(full["X"][i], cut["X"][i], equal_nan=True), i
    old = KJ.ticker_feats(df)["X"]
    assert np.allclose(full["X"][:, len(S.FEATS):], old, equal_nan=True)        # 后 29 列 = 以前的特征


def test_current_week_uses_week_open():
    df = _df(seed=2)
    f = S.ticker_feats(df)
    i = 402
    d = df.index[i]
    wk = df.index.to_period("W-FRI")
    first = int(np.flatnonzero(wk == wk[i])[0])
    prev_close = float(df["Close"].iloc[first - 1])                            # 上一周最后一天的收盘
    j = S.FEATS.index("w_gap0")
    jz = S.FEATS.index("w_z0")
    ratio = f["X"][i, j] / f["X"][i, jz]
    want = (df["Open"].iloc[first] / prev_close - 1) / (df["Close"].iloc[i] / prev_close - 1)
    assert np.isclose(ratio, want, rtol=1e-4), d
    jb = S.FEATS.index("w_body0")
    assert np.isclose(f["X"][i, jb] + f["X"][i, j], f["X"][i, jz], rtol=1e-4)


def test_shape_flags():
    fl = S.shape_flags(z=[0, 0, 0, 2, -2, 1.5, -1.5], gap=[0, 0, 0, 0, 0, 1.5, -1.5], body=[0.2, -0.2, 0.05, 1.5, -1.5, 0, 0],
                       up=[1.0, 0.1, 0.5, 0.1, 0.1, 0, 0], lw=[0.1, 1.0, 0.5, 0.1, 0.1, 0, 0])
    assert list(np.flatnonzero(fl["长上影"])) == [0] and list(np.flatnonzero(fl["长下影"])) == [1] and list(np.flatnonzero(fl["十字"])) == [2]
    assert list(np.flatnonzero(fl["大阳实体"])) == [3] and list(np.flatnonzero(fl["大阴实体"])) == [4]
    assert list(np.flatnonzero(fl["向上跳空"])) == [5] and list(np.flatnonzero(fl["向下跳空"])) == [6]
    assert not S.shape_flags([0], [0], [0.01], [0.3], [0.3])["十字"][0]        # 振幅 < 1σ 不算十字


def test_cols_and_constants():
    assert S.cols_of("JG") == list(range(47, 76)) and len(S.cols_of("FD")) == 15 and S.cols_of("FG") == list(range(47))
    assert S.MODELS == ("FG", "JG", "FD", "FR") and np.isclose(S.P_MAX, 0.05 / 3) and S.POSTHOC and S.B_H == {"FBD": 1, "FBW": 5, "FBM": 21}
    assert S.KJ.GBM["n_trees"] == 300 and S.MIN_TRIG == 10


def test_verdict_and_share():
    ok = [0.01] * 6
    assert S.verdict(ok, 0.001, 0.2, 1, 0.001, 6) == S.VERDICTS[0]
    assert S.verdict(ok, 0.001, 0.2, 1, 0.5, 6) == S.VERDICTS[1]
    assert S.verdict(ok, 0.001, 0.1, 1, 0.001, 5) == S.VERDICTS[2]
    assert S.verdict(ok, 0.5, 0.1, 1, 0.001, 4) == S.VERDICTS[3]
    assert S.verdict([0.01] * 5 + [-0.01], 0.001, 0.9, 1, 0.001, 6) == S.VERDICTS[4]
    w = np.zeros(47)
    w[S.FEATS.index("d_up0")] = 3.0
    w[S.FEATS.index("m_frac")] = 1.0
    sh = S.comp_share(w)
    assert np.isclose(sh["up"], 75) and np.isclose(sh["frac"], 25) and np.isclose(sh["d"], 75) and np.isclose(sh["m"], 25) and sh["gap"] == 0
