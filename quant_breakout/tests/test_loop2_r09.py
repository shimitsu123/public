"""第二个研究循环第 9 轮 VTU（scripts/loop2_r09_voltusd.py，2026-10-02 登记）：登记值、比例 = VT20 的机制用在美元计纳指上、接到 B1 的两个核心键。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r09_voltusd as T  # noqa: E402
import loop_r01_voltarget as VT  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.OLD) == (9, ("VTU",), "核心·波动率仓位", True, ("1987-01-01", "2000-12-31"))
    assert (VT.WIN_N, VT.TGT_START, VT.TGT_MIN, VT.BAND) == (20, "1986-01-01", 250, 0.10)        # VT20 的参数原样


def test_ratio_is_vt20_mechanism_on_usd_series():
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("1986-01-01", periods=900)
    vol = np.where((np.arange(900) // 150) % 2 == 0, 0.01, 0.03)                 # 平静 / 动荡交替
    px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, vol))), index=idx)
    got = T.ratio_usd(px)
    sg = VT.sigma(px)
    want = VT.exposure(sg, VT.target(sg))
    assert got.index.equals(want.index) and np.allclose(got.to_numpy(), want.to_numpy())
    assert got.max() <= 1.0 and got.min() < 1.0                                   # 动荡的段会减仓


def test_wiring_to_b1_core_keys():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=3)
    o = T.vtu_over(pd.Series([1.0, 0.6, 1.2], index=idx))
    assert set(o) == {"extra_expo"} and set(o["extra_expo"]) == {Y.UH_KEY, Y.HG_KEY}
    assert o["extra_expo"][Y.UH_KEY].tolist() == [1.0, 0.6, 1.0]                  # 截到 0〜1


def test_stage2_registered_constants_and_shift():
    assert (T.SHIFT_FROM, T.SHIFT_GAP, T.SEED0) == ("2000-01-03", 250, 20262009)
    idx = pd.bdate_range("1999-06-01", periods=1500)
    x = pd.Series(np.where((np.arange(1500) // 90) % 3 == 0, 0.6, 1.0), index=idx)
    w = x[x.index >= pd.Timestamp("2000-01-03")]
    for seed in (0, 9, 399):
        s = T.shifted(x, seed)
        k = T.shift_k(seed, len(w))
        assert 250 <= k <= len(w) - 250 and s.index.equals(w.index)
        assert np.array_equal(s.to_numpy(), np.roll(w.to_numpy(), k))            # 同样多、同样形状（整体循环平移）


def test_stage2_cli_choices():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "XXX"])
