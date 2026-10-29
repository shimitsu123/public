"""第二个研究循环第 7 轮 TOMB（scripts/loop2_r07_tomcore.py，2026-10-02 登记）：登记值、月末月初标记、只在美股熊里起作用。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r07_tomcore as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.OLD) == (7, ("TOMB",), "核心·熊市日历", False, ("1987-01-01", "2000-12-31"))


def test_tom_flags_mark_l_minus_1_to_f2():
    days = pd.DatetimeIndex(["2020-01-27", "2020-01-28", "2020-01-29", "2020-01-30", "2020-01-31",
                             "2020-02-03", "2020-02-04", "2020-02-05", "2020-02-06", "2020-02-27", "2020-02-28", "2020-03-02"])
    f = T.tom_flags(days)
    want = {"2020-01-30", "2020-01-31", "2020-02-03", "2020-02-04", "2020-02-27", "2020-02-28", "2020-03-02"}
    assert {str(d.date()) for d in f.index[f.to_numpy()]} == want                # 1 月 L = 01-31：01-30 / 01-31 / 02-03 / 02-04；2 月 L = 02-28
    assert not f.loc["2020-02-05"] and not f.loc["2020-01-29"]


def test_bear_eff_only_lifts_flagged_bear_days():
    idx = pd.bdate_range("2020-01-01", periods=6)
    bear = pd.Series([True, True, False, False, True, True], index=idx)
    flags = pd.Series([False, True, True, False, True, False], index=idx)
    assert T.bear_eff(bear, flags).tolist() == [True, False, False, False, False, True]
    assert T.bear_eff(bear, pd.Series(False, index=idx)).tolist() == bear.tolist()             # 永远不标记 = B1 的熊


def test_cli_takes_no_options():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "TOMB"])
