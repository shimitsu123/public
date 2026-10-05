"""第十个研究循环第 6 轮（scripts/loop10_r06_riskdisp.py）：三选二、按日子一致、门槛、常量。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop10_r02_diagfeat as R2  # noqa: E402
import loop10_r06_riskdisp as R  # noqa: E402


def test_vote_gate_exact():
    X = pd.DataFrame({"vol60": [0.30, 0.30, 0.10, np.nan, 0.24, 0.23], "b_n225": [1.00, 0.50, 1.00, 1.00, np.nan, 0.87],
                      "corr60": [0.10, 0.60, 0.60, 0.60, 0.50, 0.59]})
    # 第 1 行 vol ✓ β ✓；第 2 行 vol ✓ corr ✓；第 3 行 β ✓ corr ✓；第 4 行 vol 缺 → β ✓ corr ✓；第 5 行 只有 vol ✓；第 6 行 都正好在门槛上 → 都不成立
    assert list(R.vote_gate(X)) == [True, True, True, True, False, False]
    assert list(R.vote_gate(X.drop(columns=["corr60"]))) == [True, False, False, False, False, False]


def test_date_rules_and_same_day():
    X = pd.DataFrame({"disp20": [0.08, 0.076, np.nan], "spx_r63": [-0.01, 0.0, np.nan]})
    assert list(R.gate_of("DSW", X)) == [True, False, False] and list(R.gate_of("USR", X)) == [True, False, False]
    d = pd.to_datetime(["2020-01-06", "2020-01-06", "2020-01-07"])
    assert R.same_day_consistent(d, [True, True, False]) and not R.same_day_consistent(d, [True, False, False])


def test_round_constants():
    assert R.ROUND == 6 and R.IDS == ("RKB", "DSW", "USR") and R.feature_gate is R2.feature_gate
    assert R.KINDS == {"RKB": "stock", "DSW": "date", "USR": "date"} and all(R.POSTHOC.values())
    assert R.RKB_PARTS == (("vol60", ">", 0.23), ("b_n225", ">", 0.87), ("corr60", ">", 0.59)) and R.RKB_MIN == 2
    assert R.RULES == {"DSW": ("disp20", ">", 0.076), "USR": ("spx_r63", "<", 0.0)}
    assert all(v.startswith("选股") for v in R.FAMILY.values()) and len(set(R.FAMILY.values())) == 3
