"""第十个研究循环第 3 轮（scripts/loop10_r03_relfx.py）：门槛与常量（纯函数复用第 2 轮的 feature_gate）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop10_r02_diagfeat as R2  # noqa: E402
import loop10_r03_relfx as R  # noqa: E402


def test_rules_are_strict_greater_and_missing_never_blocks():
    X = pd.DataFrame({"rsec": [0.031, 0.03, -0.5, np.nan], "b_fx": [0.5, 0.12, 0.1201, np.nan]})
    assert list(R.feature_gate(X, R.RULES["RSB"])) == [True, False, False, False]    # > 0.03：正好 0.03 不挡、缺值不挡
    assert list(R.feature_gate(X, R.RULES["BFX"])) == [True, False, True, False]     # > 0.12
    assert list(R.feature_gate(X.drop(columns=["b_fx"]), R.RULES["BFX"])) == [False] * 4


def test_round_constants_and_reuse():
    assert R.ROUND == 3 and R.IDS == ("RSB", "BFX") and R.feature_gate is R2.feature_gate
    assert set(R.KINDS.values()) == {"stock"} and all(R.POSTHOC.values())
    assert all(v.startswith("选股") for v in R.FAMILY.values()) and len(set(R.FAMILY.values())) == 2
    assert R.RULES == {"RSB": ("rsec", ">", 0.03), "BFX": ("b_fx", ">", 0.12)}
    assert not set(R.IDS) & set(R2.IDS)
