"""第二个研究循环第 16 轮 ERA（scripts/loop2_r16_earlyreentry.py，2026-10-02 登记）：登记值、不对称带 = ma_band 的写法、+3% 时 = 现行检测器、早回来的定义。"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop2_r16_earlyreentry as T  # noqa: E402


@pytest.fixture
def repo_detector(monkeypatch):
    """测试在临时 QBREAK_HOME 下跑 → 检测器参数用仓库的 var/bullbear.json。"""
    cfg = json.loads((ROOT / "var" / "bullbear.json").read_text(encoding="utf-8"))
    monkeypatch.setattr("qbreak.bullbear.load_config", lambda: cfg)
    return cfg


def _walk(n=1500, seed=16):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2000-01-03", periods=n)
    r = rng.normal(0.0003, 0.012, n) + np.where((np.arange(n) // 300) % 2 == 0, 0.001, -0.0015)
    return pd.Series(100 * np.exp(np.cumsum(r)), index=idx)


def test_registered_constants(repo_detector):
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.OLD, T.B_UP) == (16, ("ERA",), "核心·择时（早回来）", True, ("1987-01-01", "2000-12-31"), 0.0)
    p = T.detector_params()
    assert (int(p["L"]), float(p["b"]), int(p["k"])) == (250, 0.03, 5)                 # var/bullbear.json


def test_symmetric_band_equals_ma_band():
    from qbreak.bullbear import ma_band
    c = _walk()
    for b in (0.0, 0.03):
        assert np.array_equal(T.asym_ma_band(c, 250, b, b, 5), ma_band(c, 250, b, 5))


def test_plus3_band_equals_current_detector(repo_detector):
    import equity_idle_study as EI
    c = _walk(seed=7)
    assert T.era_bear(c, b_up=0.03).equals(EI.t0_bear(c))


def test_era_bull_contains_b1_bull_and_early_days(repo_detector):
    import equity_idle_study as EI
    c = _walk(seed=3)
    b1, era = EI.t0_bear(c), T.era_bear(c)
    assert not (era & ~b1).any()                                              # ERA 是熊的日子 B1 一定是熊（只会更早回来）
    e = T.early_days(b1, era)
    assert e.tolist() == (b1 & ~era).tolist() and e.any()


def test_cli_takes_no_options():
    with pytest.raises(SystemExit):
        T.main(["--stage2", "ERA"])
