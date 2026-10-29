"""第二个研究循环第 5 轮 DDB（scripts/loop2_r05_ddbrake.py，2026-10-02 登记）：登记值、刹车规则、引擎的接法、刹车段。"""
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP  # noqa: E402
import loop2_r05_ddbrake as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC) == (5, ("DDB",), "风险层·账户回撤刹车", False)
    assert (T.LEVEL, T.MULT, T.BRAKE, T.OLD) == (0.10, 0.5, {"level": 0.10, "mult": 0.5}, ("1987-01-01", "2000-12-31"))


def test_brake_rule_peak_per_bull_run_and_same_line_release():
    b = CP.DDBrake(0.10, 0.5)
    seq = [(100, False, 1.0), (95, False, 1.0), (89.9, False, 0.5), (90, False, 1.0),      # 回到 0.90 × 高点就恢复（没有滞后带）
           (85, False, 0.5), (101, False, 1.0), (90.8, False, 0.5), (90.8, True, 1.0),     # 新高 101 → 线 90.9（90.8 在线下）；美股熊 → 1、清空
           (80, False, 1.0), (72.1, False, 1.0), (71.9, False, 0.5)]                       # 熊转牛重新起算：高点 80 → 线 72
    for eq, bear, want in seq:
        assert b.update(eq, bear) == want
    assert CP.DDBrake(1.0, 0.5).update(1.0, False) == 1.0 and CP.DDBrake(1.0, 0.5).update(1e-9, False) == 1.0   # level 1 = 永远不刹


def test_engine_hook_scales_each_core_key_and_logs():
    n = 5
    gidx = pd.bdate_range("2020-01-01", periods=n)
    eqs = [100.0, 95.0, 89.0, 91.0, 80.0]
    shared = np.ones(n)                                                          # 两个键共用一个数组的情形
    fake = types.SimpleNamespace(cfg=types.SimpleNamespace(core={"1545.T": 1.0, "2845.T": 1.0}, core_index={"1545.T": "UH", "2845.T": "HG"}),
                                 core_expo={"UH": shared, "HG": shared, "JP": np.full(n, 0.7)},
                                 bear={"US": np.array([False, False, False, False, True])}, gidx=gidx, equity=lambda i: eqs[i])
    for i in range(n):
        CP.MixEngine._dd_brake(fake, i, {"level": 0.10, "mult": 0.5})
    assert fake.core_expo["UH"].tolist() == [1, 1, 0.5, 1, 1] and fake.core_expo["HG"].tolist() == [1, 1, 0.5, 1, 1]
    assert fake.core_expo["UH"] is not fake.core_expo["HG"] and shared.tolist() == [1.0] * n
    assert fake.core_expo["JP"].tolist() == [0.7] * n                            # 核心以外的键不动
    assert [m for _, m in fake.ddb_log] == [1, 1, 0.5, 1, 1]
    assert T.brake_series(fake).tolist() == [1, 1, 0.5, 1, 1] and CP.MixEngine.DD_BRAKE is None


def test_segments():
    idx = pd.bdate_range("2020-01-01", periods=6)
    s = pd.Series([1, 0.5, 0.5, 1, 0.5, 1], index=idx, dtype=float)
    assert T.segments(s) == [(str(idx[1].date()), str(idx[2].date()), 2), (str(idx[4].date()), str(idx[4].date()), 1)]
    assert T.segments(pd.Series([1.0, 1.0], index=idx[:2])) == []


def test_cli_takes_no_options():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "DDB"])
