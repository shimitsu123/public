"""选股参数的联合调参（scripts/tune_common.py）：组的抽法、零件法与 compute_indicators 一致、PBO、挑选、两组的区间、判定。"""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import tune_common as TC                                                     # noqa: E402
from qbreak.config import StrategyParams                                     # noqa: E402
from qbreak.strategy import compute_indicators                               # noqa: E402


def test_sample_sets():
    s = TC.sample_sets()
    assert len(s) == 1 + 17 + TC.N_RANDOM and s[0] == TC.CURRENT
    ids = [TC.set_id(x) for x in s]
    assert len(set(ids)) == len(ids)
    for x in s[1:18]:
        assert sum(x[k] != TC.CURRENT[k] for k in TC.GRID) == 1
    assert TC.sample_sets() == s                                              # 种子固定 → 可重现
    assert TC.label(TC.CURRENT) == "现行"
    assert TC.label({**TC.CURRENT, "max_distribution_days": 0}) == "出货日上限 关"


def _ohlcv(n=700, seed=5):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    o = c * (1 + rng.normal(0, 0.004, n))
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.01, n))
    lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.01, n))
    v = rng.uniform(5e5, 1.5e6, n) * np.where(rng.random(n) < 0.08, 3.0, 1.0)
    return pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": v}, index=pd.bdate_range("2015-01-05", periods=n))


@pytest.mark.parametrize("seed", [5, 11])
def test_entry_mask_matches_compute_indicators(seed):
    df = _ohlcv(seed=seed)
    p0 = replace(StrategyParams(), min_weekly_vol_ratio=0.0)
    rng = np.random.default_rng(seed)
    w5v = np.where(rng.random(len(df)) < 0.1, np.nan, rng.uniform(0.5, 1.8, len(df)))
    P = TC.parts(df, p0, w5v)
    for s in TC.sample_sets()[:40]:
        ref = compute_indicators(df, TC.params_for(p0, s), None)["entry"].to_numpy(bool)
        if s["min_weekly_vol_ratio"]:
            ref = ref & (~np.isfinite(w5v) | (w5v >= s["min_weekly_vol_ratio"]))
        assert np.array_equal(TC.entry_mask(P, s, p0), ref), TC.label(s)
    assert any(TC.entry_mask(P, s, p0).any() for s in TC.sample_sets()[:40])  # 合成数据里至少有信号


def test_pbo_true_edge_vs_noise():
    rng = np.random.default_rng(0)
    nset, nb = 30, 10
    N = np.full((nset, nb), 50.0)
    noise = rng.normal(0, 0.3, (nset, nb))
    S = noise * N
    assert 0.3 < TC.pbo(S, N)["pbo"] < 0.7                                   # 全是噪声 → 约 0.5
    S2 = S.copy()
    S2[5] += 1.0 * N[5]                                                      # 第 5 组每块都真的更好
    r = TC.pbo(S2, N)
    assert r["pbo"] < 0.05 and r["median_rank"] > 0.9 and r["splits"] == 252


def test_choose_rules():
    st = {"cur": {"E": {"n": 100, "win": 40.0, "mean": 0.5}, "J": {"n": 100, "win": 40.0, "mean": 0.5}},
          "a": {"E": {"n": 60, "win": 42.0, "mean": 0.9}, "J": {"n": 60, "win": 41.0, "mean": 0.6}},
          "b": {"E": {"n": 60, "win": 45.0, "mean": 1.5}, "J": {"n": 60, "win": 39.0, "mean": 2.0}},   # J 胜率低 → 不行
          "c": {"E": {"n": 30, "win": 60.0, "mean": 3.0}, "J": {"n": 30, "win": 60.0, "mean": 3.0}},   # 笔数不够
          "d": {"E": {"n": 50, "win": 40.0, "mean": 0.7}, "J": {"n": 90, "win": 40.0, "mean": 0.8}}}
    assert TC.choose(st, "cur", ("E", "J")) == "d"                           # min 差：a 0.1、d 0.2
    assert TC.choose({"cur": st["cur"], "b": st["b"]}, "cur", ("E", "J")) == "cur"


def test_boot_unpaired_and_verdict():
    a = pd.DataFrame({"month": ["m1", "m1", "m2", "m3"], "net": [2.0, 1.0, -1.0, 3.0]})
    b = pd.DataFrame({"month": ["m1", "m2", "m2", "m3"], "net": [0.0, -1.0, 1.0, -2.0]})
    r = TC.boot_unpaired(a, b, n=500)
    assert r == TC.boot_unpaired(a, b, n=500)
    assert r["dmean_lo"] <= (a["net"].mean() - b["net"].mean()) <= r["dmean_hi"]
    c = {"dmean": 0.5, "dwin": 3.0, "dmean_lo": 0.1}
    assert TC.verdict(0.3, c, {"dmean": 0.1}, {"dmean": 0.2}, True) == "通过"
    assert TC.verdict(0.6, c, {"dmean": 0.1}, {"dmean": 0.2}, True) == "方向一致"   # PBO 太高
    assert TC.verdict(0.3, c, {"dmean": 0.1}, {"dmean": 0.2}, False) == "方向一致"  # 组合守门没过
    assert TC.verdict(0.3, {**c, "dwin": -0.1}, {"dmean": 0.1}, {"dmean": 0.2}, True) == "不通过"


def test_block_table():
    T = {"x": pd.DataFrame({"sample": ["E", "E", "J2"], "entry_date": ["2007-01-05", "2009-01-05", "2018-03-01"], "net": [1.0, -2.0, 3.0]})}
    S, N, W = TC.block_table(T, [("E", "2006-10-01", "2008-09-30"), ("E", "2008-10-01", "2010-09-30"), ("J2", "2017-01-01", "2018-12-31")])
    assert list(S[0]) == [1.0, -2.0, 3.0] and list(N[0]) == [1, 1, 1] and list(W[0]) == [1, 0, 1]
