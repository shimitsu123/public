"""W2 结合日 / 周 / 月线的量（scripts/w2mtf_study.py 登记检验）：候选目录（60 种含现行）、周 / 月量比只用已完成的 K 线且 n = 10 的周量比 = mtf.weekly_volume_ratio、
过滤的四种搭法与缺值不过滤、现行组合 = leap_confirm.w2_keep、随机对照保留同样多、判定规则。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leap_confirm as LF                                                    # noqa: E402
import w2mtf_study as W                                                      # noqa: E402

from qbreak import candles as K                                              # noqa: E402
from qbreak import mtf                                                       # noqa: E402
from qbreak.config import StrategyParams                                    # noqa: E402
from qbreak.strategy import compute_indicators                              # noqa: E402

P0 = StrategyParams(max_distribution_days=6, max_upper_shadow_ratio=3.0, min_weekly_vol_ratio=0.0)


def _synthetic(n_stocks=3, n=700, seed=0, start="2019-01-04"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    data = {}
    for i in range(n_stocks):
        r = rng.normal(0.0003, 0.006, n)
        r[rng.integers(0, n, 12)] += 0.03
        c = 1000.0 * np.cumprod(1 + r)
        o = c * (1 + rng.normal(0, 0.003, n))
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.004, n)))
        l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.004, n)))
        v = rng.lognormal(13, 0.5, n)
        v[rng.integers(0, n, 40)] *= 3.0
        data[f"{1000 + i}.T"] = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}, index=idx)
    names = list(data)
    P = K.panel(data, idx, names)
    ctx = {"P": P, "days": idx, "names": names, "cols": list(range(len(names)))}
    fa = {t: compute_indicators(df, P0) for t, df in data.items()}
    return ctx, fa, data


def test_catalogue_and_constants():
    assert len(W.VARIANTS) == 60 and W.CUR_ID == "d1.5·W10/1·M0" and W.VARIANTS[W.CUR_ID] == W.CUR
    assert set(W.EXTRA) == {"OR6", "OR12", "MOD1", "MOD2", "SC10", "SC12"} and all(k in W.VARIANTS for k in W.EXTRA)
    assert (W.CAL_UP, W.DD_TOL, W.MIN_TRADES, W.EXP_GAIN, W.MAX_FINAL, W.CONF_TOL, W.CONF_GAIN, W.HARD_TOL, W.PLACEBO_SEEDS) == (0.02, 2.0, 30, 0.04, 3, 0.01, 0.02, 0.001, 30)
    assert all(W.zh(v) for v in W.VARIANTS.values())


def test_period_ratio_matches_w5v_and_uses_completed_bars_only():
    ctx, fa, data = _synthetic(n_stocks=1)
    t, df = next(iter(fa.items()))
    raw = data[t]
    r10 = W.period_ratio(raw, ctx["days"], "W", 10, df.index)
    ref = mtf.weekly_volume_ratio(raw, ctx["days"])
    a, b = r10.to_numpy(float), ref.reindex(df.index).to_numpy(float)
    ok = np.isfinite(a) & np.isfinite(b)
    assert ok.sum() > 400 and np.allclose(a[ok], b[ok]) and np.array_equal(np.isfinite(a), np.isfinite(b))
    m6 = W.period_ratio(raw, ctx["days"], "M", 6, df.index)
    assert m6.iloc[:140].isna().all() and m6.iloc[-1] > 0                                  # 7 个完成的月之后才有值（7 月末）
    d0 = df.index[400]
    raw2 = raw.copy()
    raw2.loc[raw2.index > d0, "Volume"] *= 10                                             # 改未来 → d0 及以前的比值不变
    m6b = W.period_ratio(raw2, ctx["days"], "M", 6, df.index)
    assert np.allclose(m6.loc[:d0].fillna(-1), m6b.loc[:d0].fillna(-1))
    mb = mtf.bars(raw, ctx["days"], "M")
    last_done = mb.index[mb.index <= d0][-1]                                              # d0 那天的值 = 最近完成的月
    v = mb["Volume"].astype(float)
    exp = (v / v.shift(1).rolling(6).mean()).loc[last_done]
    assert abs(m6.loc[d0] - exp) < 1e-9


def test_keep_mask_semantics_and_nan_keeps():
    nan = np.nan
    r = {"vr": np.array([1.6, 2.5, nan, 1.6, 1.6]), "W10": np.array([1.1, 0.7, 0.9, nan, 1.3]), "W5": np.array([1.1, 1.1, 1.1, 1.1, 1.1]), "W20": np.array([0.5] * 5),
         "M6": np.array([1.2, 0.5, 1.2, 0.8, nan]), "M12": np.array([0.5] * 5)}
    assert W.keep_mask(r, W.CUR).tolist() == [True, False, False, True, True]
    assert W.keep_mask(r, {"kind": "and", "d": 2.0, "n": 10, "t": 1.0, "m": 0}).tolist() == [False, False, False, False, False]   # 日 ≥ 2 只剩第 2、3 个，再与周 AND → 全没
    assert W.keep_mask(r, {"kind": "and", "d": 1.5, "n": 10, "t": 1.0, "m": 6}).tolist() == [True, False, False, False, True]
    assert W.keep_mask(r, W.EXTRA["OR6"]).tolist() == [True, False, True, True, True]
    assert W.keep_mask(r, W.EXTRA["MOD1"]).tolist() == [False, False, False, True, True]     # M ≥ 1 → 周要 ≥ 1.2；M 缺 → 1.0
    assert W.keep_mask(r, W.EXTRA["MOD2"]).tolist() == [True, False, True, True, True]
    sc = W.keep_mask(r, W.EXTRA["SC10"])
    assert sc.tolist() == [True, False, True, False, True]                                  # (1.07+1.1+1.2)/3、(1.67+0.7+0.5)/3=0.96、(0.9+1.2)/2、(1.07+0.8)/2=0.93、(1.07+1.3)/2
    assert W.keep_mask(r, {"kind": "and", "d": 1.5, "n": 20, "t": 0.8, "m": 0}).tolist() == [False] * 5


def test_current_variant_equals_w2_keep_and_random_keep_counts():
    ctx, fa, _ = _synthetic(n_stocks=3, seed=3)
    R = W.ratios(ctx, fa)
    ref = LF.w2_keep(ctx, fa)
    for t in fa:
        assert np.array_equal(W.keep_mask(R[t], W.CUR), np.asarray(ref[t], bool)), t
        assert set(R[t]) == {"vr", "W5", "W10", "W20", "M6", "M12"}
    a, b = "2019-06-01", "2021-06-30"
    full = {t: np.ones(len(df), bool) for t, df in fa.items()}
    raw_n = W.kept_count(fa, full, a, b)
    k = max(1, raw_n // 2)
    keep = W.random_keep(fa, a, b, k, seed=1)
    assert W.kept_count(fa, keep, a, b) == k and W.random_keep(fa, a, b, k, seed=1)[list(fa)[0]].tolist() == keep[list(fa)[0]].tolist()
    for t, df in fa.items():                                                               # 窗口外全保留
        out = (df.index < pd.Timestamp(a)) | (df.index > pd.Timestamp(b))
        assert keep[t][out].all()
    assert W.kept_count(fa, W.random_keep(fa, a, b, raw_n + 100, seed=2), a, b) == raw_n


def test_verdicts():
    seg = lambda c, dd, n=40: {"calmar": c, "dd": dd, "n": n}                              # noqa: E731
    cur = W.CUR_ID
    ACCT = {"E": {cur: seg(0.32, -27.5), "X": seg(0.36, -27.0)}, "J": {cur: seg(0.40, -35.0), "X": seg(0.43, -34.0)}}
    assert W.pass_a("X", ACCT)
    ok, f = W.explore_verdict("X", ACCT, {"X": {"E": 0.35, "J": 0.42}})
    assert ok and not f
    ok, f = W.explore_verdict("X", ACCT, {"X": {"E": 0.37, "J": 0.42}})
    assert not ok and any(x.startswith("b E") for x in f)
    ACCT2 = {"E": {cur: seg(0.32, -27.5), "X": seg(0.36, -30.0)}, "J": ACCT["J"]}
    assert not W.pass_a("X", ACCT2)
    few = {"E": {cur: seg(0.32, -27.5), "X": seg(0.36, -27.0, n=20)}, "J": ACCT["J"]}
    assert any(x.startswith("c E") for x in W.explore_verdict("X", few, {"X": {"E": 0.3, "J": 0.4}})[1])
    small = {"E": {cur: seg(0.32, -27.5), "X": seg(0.341, -27.0)}, "J": {cur: seg(0.40, -35.0), "X": seg(0.421, -34.0)}}
    assert abs(W.gain_sum(small, "X", ("E", "J")) - 0.042) < 1e-9 and W.explore_verdict("X", small, {"X": {"E": 0.3, "J": 0.4}})[0]   # a 各 +0.02 ⇒ d 自然满足
    C = {"Z": {cur: seg(1.7, -8.0), "X": seg(1.72, -8.0)}, "W": {cur: seg(0.36, -30.0), "X": seg(0.37, -29.0)}}
    assert W.confirm_verdict("X", C)[0] == "确认"
    C2 = {"Z": {cur: seg(1.7, -8.0), "X": seg(1.68, -8.0)}, "W": {cur: seg(0.36, -30.0), "X": seg(0.37, -29.0)}}
    assert W.confirm_verdict("X", C2)[0] == "不通过"
    assert W.gain_sum(C, "X", ("Z", "W")) == 0.03
