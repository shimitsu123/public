"""第二个研究循环第 10 轮 NVU（scripts/loop2_r10_ndrvol.py，2026-10-02 登记）：登记值、NDRH 与 VTU 两条原样合并（键不重叠）。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r10_ndrvol as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.OLD) == (10, ("NVU",), "核心·择时（早回来）", True, ("1987-01-01", "2000-12-31"))


def test_union_wiring_merges_both_rules():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=6)
    spx = pd.Series([False, True, True, True, True, False], index=idx)
    ndx = pd.Series([False, False, True, False, False, False], index=idx)
    uni = pd.Series([False, False, True, True, False, False], index=idx)
    x = pd.Series([1.0, 1.0, 0.7, 0.7, 1.0, 1.0], index=idx)
    W = {"bear": {"US": spx}, "inp": {"_stub": True}, "kw": {"Z": {"extra_core": {}}}}
    orig = Y.hedged_frame
    Y.hedged_frame = lambda inp: pd.DataFrame({"Close": [1.0]}, index=[idx[0]])      # 只测接法，不取数据
    try:
        o = T.nvu_over(W, ndx, uni, x)
    finally:
        Y.hedged_frame = orig
    assert {"cfg_over", "extra_core", "extra_bear", "extra_expo"} <= set(o)
    assert o["extra_expo"][Y.UH_KEY].tolist() == x.tolist() and o["extra_expo"][Y.HG_KEY].tolist() == x.tolist()
    # 1545 的熊 = （S&P 熊 且 不是早回来）或 对冲中：第 4〜5 天早回来、第 4 天对冲中 → 1545 熊、2845 不熊
    assert o["extra_bear"][Y.UH_KEY].tolist() == [False, True, True, True, False, False]
    assert o["extra_bear"][Y.HG_KEY].tolist() == [True, True, True, False, True, True]


def test_cli_takes_no_options():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "NVU"])
