"""scripts/wvol_study.py：周线量比的过滤（严格 / 不严格的门槛）与缺值不过滤。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import wvol_study as W                                                       # noqa: E402


def test_keep_mask():
    v = np.array([np.nan, 0.9, 1.0, 1.142, 1.2])
    assert W.keep_mask(v, W.CUT1, True).tolist() == [True, False, False, False, True]
    assert W.keep_mask(v, W.CUT2, False).tolist() == [True, False, True, True, True]


def test_week_lottery_keeps_whole_weeks():
    import pandas as pd
    import wvol_placebo as WP
    d = pd.bdate_range("2026-01-05", periods=20)
    fr = {"A.T": pd.DataFrame({"entry": True}, index=d), "B.T": pd.DataFrame({"entry": [True, False] * 10}, index=d)}
    assert not any(WP.week_lottery(fr, 0.0, 1)[t]["entry"].any() for t in fr)
    one = WP.week_lottery(fr, 1.0, 1)
    assert all((one[t]["entry"] == fr[t]["entry"]).all() for t in fr)
    half = WP.week_lottery(fr, 0.5, 3)["A.T"]["entry"]
    wk = half.index.to_period("W-FRI")
    assert all(half[wk == w].nunique() == 1 for w in wk.unique())            # 同一周一起留或一起去
