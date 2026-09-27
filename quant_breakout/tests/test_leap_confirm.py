"""「质的飞跃」确认框架（scripts/leap_confirm.py）的纯函数：逐笔按买入日分窗口、过滤掩码、保留比例。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leap_confirm as LF  # noqa: E402


def test_trade_stats_by_entry_date_and_net_of_fees():
    tr = pd.DataFrame({"entry_date": ["2001-02-01", "2004-03-01", "2006-12-01"], "pnl": [900.0, -500.0, 100.0],
                       "shares": [100, 100, 100], "entry_px": [1000.0, 1000.0, 1000.0]})
    s = LF.trade_stats(tr, "2001-01-04", "2006-09-30")
    assert s["n"] == 2 and np.isclose(s["mean"], (0.9 - 0.5) / 2) and s["win"] == 50.0
    assert LF.trade_stats(tr, "2006-10-01", None)["n"] == 1
    assert LF.trade_stats(tr.iloc[:0], "2001-01-04", None) == {"n": 0, "mean": None, "win": None}


def test_masks_and_keep_fraction():
    idx = pd.bdate_range("2020-01-01", periods=4)
    fr = {"A.T": pd.DataFrame({"entry": [True, False, True, True]}, index=idx), "B.T": pd.DataFrame({"entry": [True] * 4}, index=idx)}
    keep = {"A.T": np.array([True, True, False, True])}
    out = LF.with_mask(fr, keep)
    assert out["A.T"]["entry"].tolist() == [True, False, False, True] and out["B.T"]["entry"].all()
    assert np.isclose(LF.keep_frac(fr, keep), 6 / 7)
    assert not any(df["entry"].any() for df in LF.no_entries(fr).values())


def test_windows_follow_charter():
    w = LF._windows("Z")
    assert w["Z"] == ("2001-01-04", "2006-09-30") and w["Z1"][1] == "2003-12-31" and w["Z2"][0] == "2004-01-01"
