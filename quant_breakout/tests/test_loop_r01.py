"""研究循环第 1 轮 VT20（scripts/loop_r01_voltarget.py，2026-10-01 登记）：登记值、日元计纳指、σ20、扩展中位数目标、滞后带、循环平移的随机改动。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_r01_voltarget as V  # noqa: E402


def test_registered_constants():
    assert (V.ROUND, V.ID, V.WIN_N, V.TGT_START, V.TGT_MIN, V.BAND) == (1, "VT20", 20, "1986-01-01", 250, 0.10)
    assert (V.SHIFT_FROM, V.SHIFT_GAP, V.SEED0) == ("2000-01-03", 250, 20261001)


def test_jpy_ndx_forward_fills_fx():
    d = pd.bdate_range("2020-01-06", periods=4)
    tr = pd.Series([100.0, 101.0, 102.0, 103.0], index=d)
    fx = pd.Series([110.0, np.nan, 112.0], index=d[[0, 1, 3]])
    out = V.jpy_ndx(tr, fx)
    assert out.tolist() == [11000.0, 11110.0, 11220.0, 103.0 * 112.0]                      # 缺的汇率向前填


def test_sigma_and_expanding_median_target():
    d = pd.bdate_range("1985-06-03", periods=600)
    rng = np.random.default_rng(0)
    px = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.01, 600))), index=d)
    s = V.sigma(px)
    assert s.iloc[:20].isna().all() and np.isfinite(s.iloc[20])                          # 要 20 个收益
    r = np.log(px).diff()
    assert abs(s.iloc[100] - r.iloc[81:101].std() * np.sqrt(252)) < 1e-12
    t = V.target(s)
    assert t.index[0] >= pd.Timestamp("1986-01-01")                                      # 1986 起
    k = t.first_valid_index()
    assert (s[(s.index >= "1986-01-01")].dropna().index.get_loc(k)) == 249                # 第 250 个值才给
    assert abs(t.iloc[-1] - s[s.index >= "1986-01-01"].median()) < 1e-12                  # 扩展窗口 = 到当天的中位数


def test_exposure_caps_at_one_and_uses_band():
    idx = pd.bdate_range("2001-01-01", periods=6)
    sig = pd.Series([0.20, 0.40, 0.42, 0.25, 0.10, np.nan], index=idx)
    tgt = pd.Series(0.20, index=idx)
    e = V.exposure(sig, tgt)
    assert e.tolist() == [1.0, 0.5, 0.5, 0.8, 1.0, 1.0]                                   # 0.476 与 0.5 差 < 0.10 → 不换；算不了 = 1
    assert (e <= 1.0).all()
    sig2 = pd.Series([0.21, 0.30, 0.205, 0.19], index=idx[:4])
    e2 = V.exposure(sig2, tgt.iloc[:4])
    assert e2.round(3).tolist() == [1.0, 0.667, 0.976, 1.0]                                # 0.952 不换；σ ≤ 目标 → 直接回到 1


def test_shift_placebo_is_reproducible_and_keeps_distribution():
    idx = pd.bdate_range("1999-06-01", "2026-10-30")
    e = pd.Series(np.where(np.arange(len(idx)) % 97 < 30, 0.6, 1.0), index=idx)
    a, b = V.shifted(e, 3), V.shifted(e, 3)
    assert a.equals(b) and a.index[0] >= pd.Timestamp("2000-01-03") and a.index[-1] <= pd.Timestamp("2026-09-30")
    w = V.shift_domain(e)
    assert sorted(a.tolist()) == sorted(w.tolist())                                      # 比例的分布不变
    ks = [V.shift_k(s, len(w)) for s in range(400)]
    assert min(ks) >= 250 and max(ks) <= len(w) - 250 and len(set(ks)) > 300               # 400 个种子大多不同
    assert not V.shifted(e, 0).equals(V.shifted(e, 1))
