"""scripts/div_explore.py：权利付最终日（T+3 → T+2）与「只用 t0 之前开示的予想配当」。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import div_explore as X                                                      # noqa: E402


def test_last_cum_day():
    days = pd.bdate_range("2018-09-03", "2018-10-05").union(pd.bdate_range("2024-03-01", "2024-04-05"))
    days = days.drop(pd.Timestamp("2018-09-24"))                              # 振替休日
    assert days[X.last_cum_day(days, 2018, 9)] == pd.Timestamp("2018-09-25")  # 月末 9/28，T+3
    assert days[X.last_cum_day(days, 2024, 3)] == pd.Timestamp("2024-03-27")  # 月末 3/29，T+2


def test_forecast_div_uses_only_earlier_disclosures():
    F = pd.DataFrame({"DiscDate": pd.to_datetime(["2024-02-10", "2024-03-20", "2023-05-10"]), "t": ["A.T", "A.T", "B.T"],
                      "CurFYEn": pd.to_datetime(["2024-03-31", "2024-03-31", "2023-03-31"]), "CurPerType": ["3Q", "3Q", "FY"],
                      "FDivFY": [30.0, 50.0, 10.0], "FDiv2Q": [np.nan] * 3, "NxFDivFY": [np.nan, np.nan, 12.0], "NxFDiv2Q": [np.nan, np.nan, 6.0]})
    d = X.forecast_div(F, pd.Timestamp("2024-03-15"), 3)
    assert d["A.T"] == 30.0 and d["B.T"] == 12.0                              # 3/20 的修正还没开示；B 用上期 FY 短信的下期予想
    s = X.forecast_div(F, pd.Timestamp("2023-09-15"), 9)
    assert s.to_dict() == {"B.T": 6.0}
