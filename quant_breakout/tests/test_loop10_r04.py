"""第十个研究循环第 4 轮（scripts/loop10_r04_mktstate.py）：门槛、按日子一致、常量。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop10_r02_diagfeat as R2  # noqa: E402
import loop10_r04_mktstate as R  # noqa: E402


def test_rules_directions_and_boundaries():
    X = pd.DataFrame({"n225_vol20": [0.19, 0.18, 0.1, np.nan], "breadth50": [0.52, 0.53, 0.9, np.nan], "n225_r63": [-0.01, 0.0, 0.05, np.nan]})
    assert list(R.feature_gate(X, R.RULES["NVL"])) == [True, False, False, False]    # > 0.18
    assert list(R.feature_gate(X, R.RULES["BRD"])) == [True, False, False, False]    # < 0.53
    assert list(R.feature_gate(X, R.RULES["N3M"])) == [True, False, False, False]    # < 0（正好 0 不挡）


def test_same_day_consistency_and_gated_days():
    d = pd.to_datetime(["2020-01-06", "2020-01-06", "2020-01-07", "2020-01-08"])
    assert R.same_day_consistent(d, [True, True, False, True]) and R.gated_days(d, [True, True, False, True]) == 2
    assert not R.same_day_consistent(d, [True, False, False, False])
    assert R.same_day_consistent([], []) and R.gated_days([], []) == 0


def test_round_constants():
    assert R.ROUND == 4 and R.IDS == ("NVL", "BRD", "N3M") and R.feature_gate is R2.feature_gate
    assert set(R.KINDS.values()) == {"date"} and all(R.POSTHOC.values())
    assert all(v.startswith("选股") for v in R.FAMILY.values()) and len(set(R.FAMILY.values())) == 3
    assert R.RULES == {"NVL": ("n225_vol20", ">", 0.18), "BRD": ("breadth50", "<", 0.53), "N3M": ("n225_r63", "<", 0.0)}
