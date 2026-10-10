"""第二个研究循环第 1 轮 TR3（scripts/loop2_r01_tranche.py，2026-10-02 登记）：登记值、分批规则、一步到位 = B1、引擎的持仓比例接口。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r01_tranche as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.N_STEPS, T.EVERY, T.OLD) == (1, ("TR3",), "执行·核心分批切换", 3, 5, ("1987-01-01", "2000-12-31"))


def _bear(vals):
    return pd.Series(vals, index=pd.bdate_range("2020-01-01", periods=len(vals)))


def test_one_step_is_the_plain_switch():
    b = _bear([False, False, True, True, False, True, False, False])
    e = T.tranche(b, n=1)
    assert e.tolist() == [1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 1.0, 1.0]
    assert T.out_of_core(e).tolist() == b.tolist()


def test_three_steps_every_five_days():
    b = _bear([False] * 3 + [True] * 15)
    e = T.tranche(b)
    assert np.allclose(e.iloc[:3], 1.0) and np.allclose(e.iloc[3:8], 2 / 3) and np.allclose(e.iloc[8:13], 1 / 3) and np.allclose(e.iloc[13:], 0.0)
    up = T.tranche(_bear([True] * 2 + [False] * 12))                                     # 熊 → 牛同样三步
    assert np.allclose(up.iloc[:2], 0.0) and np.allclose(up.iloc[2:7], 1 / 3) and np.allclose(up.iloc[7:12], 2 / 3) and np.allclose(up.iloc[12:], 1.0)


def test_reversal_mid_way_steps_back_from_current_level():
    b = _bear([False] * 3 + [True] * 3 + [False] * 12)
    e = T.tranche(b)
    assert np.allclose(e.iloc[3:6], 2 / 3) and np.allclose(e.iloc[6:], 1.0)               # 翻回牛：从 2/3 走一步就是 1
    b2 = _bear([False] * 3 + [True] * 6 + [False] * 12)
    e2 = T.tranche(b2)
    assert np.allclose(e2.iloc[8], 1 / 3) and np.allclose(e2.iloc[9:14], 2 / 3) and np.allclose(e2.iloc[14:], 1.0)


def test_over_with_one_step_equals_b1_wiring():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=10)
    bear = pd.Series([False, False, True, True, True, False, False, False, True, False], index=idx)
    state = pd.Series([False, True, True, False, False, False, True, True, False, False], index=idx)
    o = T.tranche_over(state, T.tranche(bear, n=1))
    fr = pd.DataFrame({"Close": [1.0]}, index=[idx[0]])
    b1 = Y.fxh_over({"kw": {"Z": {"extra_core": {"1545.T": fr}}}}, bear, state, fr)
    for k in (Y.UH_KEY, Y.HG_KEY):
        assert o["extra_bear"][k].tolist() == b1["extra_bear"][k].tolist()
    assert set(o["extra_expo"]) == {Y.UH_KEY, Y.HG_KEY}


def test_engine_hook_defaults_to_no_change():
    import candle_portfolio as CP
    assert CP.MixEngine.EXTRA_EXPO == {}
    assert T.flips(_bear([False, True, True, False])) == 2
