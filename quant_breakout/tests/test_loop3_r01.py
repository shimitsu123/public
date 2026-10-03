"""第三个研究循环第 1 轮 BAJ / BAU / BAB（scripts/loop3_r01_bondswap.py，2026-10-02 登记）：登记值、不加过滤 = 美股熊就拿、
接法 = 第二个循环 TBH / TBJ / TBU 原样、1987〜2000 的持仓、ID 没用过、命令行。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop3_r01_bondswap as T  # noqa: E402
import research_loop3 as R3  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.KIND) == (1, ("BAJ", "BAU", "BAB"), "核心·熊市避险资产", True, "asset")
    assert T.KIND in R3.KINDS
    assert not set(T.IDS) & R3.previous_ids(ROOT / "var")                    # 第一 / 第二个循环没用过


def test_unconditional_bond_is_bear_exactly_when_us_bull():
    days = pd.bdate_range("2020-01-01", periods=6)
    bear_us = pd.Series([False, True, True, False, True, False], index=days)
    fr = pd.DataFrame({"Close": 1.0}, index=days)
    ov = T.overs(bear_us, fr, fr, T.always(days), T.always(days))
    import loop2_r02_bondrefuge as T2
    import loop2_r03_jgbrefuge as T3
    for k, key in (("BAU", T2.BD_KEY), ("BAJ", T3.JG_KEY)):
        assert list(ov[k]["extra_bear"][key].reindex(days)) == list(~bear_us)
    assert set(ov["BAB"]["extra_bear"]) == {T2.BD_KEY, T3.JG_KEY} and ov["BAB"]["cfg_over"]["core_mode"] == "follow"
    assert set(ov["BAB"]["extra_core"]) == {T2.BOND_T, T3.JGB_T}


def test_old_core_weights_split_bonds_in_bear():
    import loop2_r04_bondunion as T4
    idx = pd.bdate_range("1990-01-01", periods=4)
    bear = pd.Series([False, True, True, False], index=idx)
    hedge = pd.Series(False, index=idx)
    on, off = pd.Series(True, index=idx), pd.Series(False, index=idx)
    w = T4.union_weights(bear, hedge, on, on)
    assert list(w["b"]) == [0.0, 0.5, 0.5, 0.0] and list(w["j"]) == [0.0, 0.5, 0.5, 0.0] and list(w["u"]) == [1.0, 0.0, 0.0, 1.0]
    w1 = T4.union_weights(bear, hedge, off, on)
    assert list(w1["j"]) == [0.0, 1.0, 1.0, 0.0] and w1["b"].sum() == 0.0


def test_wiring_and_cli():
    import inspect
    src = inspect.getsource(T.stage_one)
    assert "always(bc.index), always(jc.index)" in src and "rb = L2.run(W, e)" in src and "posthoc=unseen" in src
    with pytest.raises(SystemExit):
        T.main(["--stage2"])
