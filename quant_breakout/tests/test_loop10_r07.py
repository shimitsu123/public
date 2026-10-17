"""第十个研究循环第 7 轮（scripts/loop10_r07_final.py）：季节闸门、门槛、常量。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop10_r02_diagfeat as R2  # noqa: E402
import loop10_r07_final as R  # noqa: E402


def test_season_gate_may_to_october():
    d = ["2020-04-30", "2020-05-01", "2020-10-30", "2020-11-02", "2021-01-04", "2021-07-15"]
    assert list(R.season_gate(d)) == [False, True, True, False, False, True]
    X = pd.DataFrame({"date": pd.to_datetime(d)})
    assert list(R.gate_of("HWN", X)) == [False, True, True, False, False, True]
    assert R.same_day_consistent(X["date"], R.gate_of("HWN", X))


def test_stock_rules_and_missing():
    X = pd.DataFrame({"vexp": [0.93, 0.94, np.nan], "dy": [1.32, 1.33, np.nan]})
    assert list(R.gate_of("VEX", X)) == [True, False, False]                  # < 0.94
    assert list(R.gate_of("DYL", X)) == [True, False, False]                  # < 1.33（%）；缺值不挡


def test_round_constants():
    assert R.ROUND == 7 and R.IDS == ("HWN", "VEX", "DYL") and R.feature_gate is R2.feature_gate
    assert R.KINDS == {"HWN": "date", "VEX": "stock", "DYL": "stock"}
    assert R.POSTHOC == {"HWN": False, "VEX": True, "DYL": True}
    assert R.HWN_MONTHS == (5, 6, 7, 8, 9, 10) and R.RULES == {"VEX": ("vexp", "<", 0.94), "DYL": ("dy", "<", 1.33)}
    assert all(v.startswith("选股") for v in R.FAMILY.values()) and len(set(R.FAMILY.values())) == 3
