"""第二个研究循环第 8 轮 NDRH（scripts/loop2_r08_ndrhedged.py，2026-10-02 登记）：登记值、核心用的熊 = S&P 熊 且 不是早回来（NDR 原样）。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r08_ndrhedged as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.OLD) == (8, ("NDRH",), "核心·择时（早回来）", True, ("1987-01-01", "2000-12-31"))


def test_core_bear_is_spx_bear_minus_early_return():
    idx = pd.bdate_range("2020-01-01", periods=8)
    spx = pd.Series([False, True, True, True, True, True, False, False], index=idx)
    ndx = pd.Series([False, False, True, False, False, True, False, False], index=idx)
    # S&P 熊的这一段：纳指第 3 天翻熊、第 4〜5 天回到牛（早回来）、第 6 天又熊 → 现金
    assert T.core_bear(spx, ndx).tolist() == [False, True, True, False, False, True, False, False]
    assert T.core_bear(spx, pd.Series(False, index=idx)).tolist() == spx.tolist()            # 纳指从不翻熊 → 没有早回来 = B1


def test_cli_takes_no_options():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "NDRH"])
