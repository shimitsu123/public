"""第二个研究循环第 11 轮 VTD（scripts/loop2_r11_voldown.py，2026-10-02 登记）：登记值、下行半偏差、比例 = VT20 的机制用在下行半偏差上。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r11_voldown as T  # noqa: E402
import loop_r01_voltarget as VT  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.OLD) == (11, ("VTD",), "核心·波动率仓位", True, ("1987-01-01", "2000-12-31"))


def test_downside_sigma_counts_only_down_days():
    idx = pd.bdate_range("2020-01-01", periods=25)
    up = pd.Series(np.exp(np.cumsum(np.r_[0.0, np.full(24, 0.02)])), index=idx)      # 只涨 → 下行半偏差 = 0
    assert np.allclose(T.downside_sigma(up).dropna().to_numpy(), 0.0)
    r = np.r_[0.0, np.tile([0.01, -0.01], 12)]
    px = pd.Series(np.exp(np.cumsum(r)), index=idx)
    want = np.sqrt(np.mean(np.clip(r[-20:], None, 0.0) ** 2)) * np.sqrt(252)
    assert np.isclose(T.downside_sigma(px).iloc[-1], want)


def test_ratio_is_vt20_mechanism_on_downside_sigma():
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("1986-01-01", periods=900)
    vol = np.where((np.arange(900) // 150) % 2 == 0, 0.01, 0.03)
    px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, vol))), index=idx)
    sd = T.downside_sigma(px)
    assert np.allclose(T.ratio_down(px).to_numpy(), VT.exposure(sd, VT.target(sd)).to_numpy())


def test_cli_takes_no_options():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "VTD"])
