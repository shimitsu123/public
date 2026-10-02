"""第二个研究循环第 18 轮 FMB（scripts/loop2_r18_fomcbear.py，2026-10-02 登记）：登记值、定期公布日（去掉临时会议）、标记日 = 前一个美国交易日、接法、命令行。"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop2_r18_fomcbear as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC) == (18, ("FMB",), "核心·熊市日历", False)


def test_fomc_dates_drop_unscheduled_and_dedupe():
    ev = pd.DataFrame({
        "name_en": ["FOMC statement and Board discount rate action"] * 4 + ["Announcement of the Monetary Policy Meeting Decisions"],
        "description": ["meeting: January 30-31 Meeting", "unscheduled: January 3 Conference Call", "meeting: March 20 Meeting",
                        "meeting: March 20 Meeting", "policy unchanged"],
        "date": ["2001-01-31", "2001-01-03", "2001-03-20", "2001-03-20", "2001-01-19"],
        "excluded": [0, 0, 0, 0, 0]})
    assert list(T.fomc_dates(ev)) == [pd.Timestamp("2001-01-31"), pd.Timestamp("2001-03-20")]


def test_real_file_has_scheduled_meetings_from_2001():
    d = T.fomc_dates(pd.read_csv(ROOT / "var" / "policy_events.csv"))
    assert d[0].year == 2001 and len(d) >= 190 and d.is_unique              # 约 8 次 / 年


def test_flags_are_previous_us_trading_day():
    days = pd.bdate_range("2022-03-10", periods=8)                            # 3/10〜3/21
    f = T.fmb_flags(days, pd.DatetimeIndex(["2022-03-16", "2022-03-19"]))     # 3/19 是周六 → 跳过
    assert list(f.index[f]) == [pd.Timestamp("2022-03-15")]


def test_wiring_is_tomb():
    import inspect
    assert "R7.tomb_over(W, flags, uni)" in inspect.getsource(T.fmb_over)


def test_cli_takes_no_options():
    import pytest
    with pytest.raises(SystemExit):
        T.main(["--stage2", "FMB"])
