"""第二个研究循环第 4 轮 TBU（scripts/loop2_r04_bondunion.py，2026-10-02 登记）：登记值、两只债券的接法、只有核心的持仓（两只都牛各一半）。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r04_bondunion as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.OLD) == (4, ("TBU",), "核心·熊市避险资产", True, ("1987-01-01", "2000-12-31"))


def test_union_wiring_has_both_bonds():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=6)
    bear = pd.Series([False, True, True, True, True, False], index=idx)
    ub = pd.Series([True, True, False, True, False, True], index=idx)
    jb = pd.Series([True, True, True, False, False, True], index=idx)
    fr = pd.DataFrame({"Close": [1.0]}, index=[idx[0]])
    o = T.tbu_over(bear, ub, fr, jb, fr)
    assert o["cfg_over"]["core_mode"] == "follow"
    assert o["cfg_over"]["core_index"] == {"1545.T": Y.UH_KEY, "2845.T": Y.HG_KEY, "1482.T": "US_BD", "2561.T": "US_JG"}
    assert set(o["extra_core"]) == {"1482.T", "2561.T"} and set(o["extra_bear"]) == {"US_BD", "US_JG"}
    assert (~o["extra_bear"]["US_BD"]).tolist() == [False, True, False, True, False, False]
    assert (~o["extra_bear"]["US_JG"]).tolist() == [False, True, True, False, False, False]
    never = pd.Series(False, index=idx)
    o0 = T.tbu_over(bear, never, fr, never, fr)
    assert o0["extra_bear"]["US_BD"].all() and o0["extra_bear"]["US_JG"].all()           # 两只都从不是牛 = B1


def test_union_weights_split_when_both_bull():
    idx = pd.bdate_range("2020-01-01", periods=5)
    w = T.union_weights(pd.Series([False, True, True, True, True], index=idx), pd.Series([True, False, False, False, False], index=idx),
                        pd.Series([True, True, True, False, False], index=idx), pd.Series([True, True, False, True, False], index=idx))
    assert w.to_numpy().tolist() == [[0, 1, 0, 0], [0, 0, 0.5, 0.5], [0, 0, 1, 0], [0, 0, 0, 1], [0, 0, 0, 0]]


def test_stage2_registered_constants_and_joint_shift():
    import numpy as np
    assert (T.SHIFT_FROM, T.SHIFT_GAP, T.SEED0) == ("2000-01-04", 250, 20262004)
    idx = pd.bdate_range("2000-01-04", periods=1200)
    a = pd.Series((np.arange(1200) // 100) % 2 == 0, index=idx)
    b = pd.Series((np.arange(1200) // 70) % 3 == 0, index=idx)
    for seed in (0, 5, 399):
        sa, sb = T.shifted_pair(a, b, seed)
        k = T.shift_k(seed, 1200)
        assert 250 <= k <= 950 and sa.index.equals(idx) and sb.index.equals(idx)
        assert np.array_equal(sa.to_numpy(), np.roll(a.to_numpy(), k)) and np.array_equal(sb.to_numpy(), np.roll(b.to_numpy(), k))   # 同一个 k
        assert int(sa.sum()) == int(a.sum()) and int(sb.sum()) == int(b.sum())


def test_stage2_cli_choices():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "XXX"])
