"""第十个研究循环第 2 轮（scripts/loop10_r02_diagfeat.py）的纯函数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop10_r02_diagfeat as R  # noqa: E402


def test_feature_gate_thresholds_are_strict_or_inclusive_as_written():
    X = pd.DataFrame({"r12": [0.30, 0.12, 0.119, -0.5], "clv": [0.69, 0.70, 0.71, 0.0], "x2": [0.0, -3.0, 2.0, 1e-9]})
    assert list(R.feature_gate(X, R.RULES["MOM"])) == [True, False, False, False]   # > +0.12：正好 0.12 不挡
    assert list(R.feature_gate(X, R.RULES["CLW"])) == [True, False, False, True]    # < 0.70：正好 0.70 不挡
    assert list(R.feature_gate(X, R.RULES["X2G"])) == [True, True, False, False]    # ≤ 0：0 挡、正数不挡


def test_feature_gate_missing_values_and_columns_never_block():
    X = pd.DataFrame({"r12": [np.nan, 0.5, np.inf], "clv": [None, 0.1, -np.inf]})
    assert list(R.feature_gate(X, R.RULES["MOM"])) == [False, True, False]          # NaN / inf → 不挡
    assert list(R.feature_gate(X, R.RULES["CLW"])) == [False, True, False]
    assert list(R.feature_gate(X, R.RULES["X2G"])) == [False, False, False]         # 没有 x2 这一列 → 全不挡
    assert R.feature_gate(X.iloc[:0], R.RULES["MOM"]).shape == (0,)


def test_round_constants():
    assert R.ROUND == 2 and R.IDS == ("MOM", "CLW", "X2G")
    assert set(R.KINDS.values()) == {"stock"} and all(R.POSTHOC.values())
    assert all(v.startswith("选股") for v in R.FAMILY.values()) and len(set(R.FAMILY.values())) == 3
    assert R.RULES == {"MOM": ("r12", ">", 0.12), "CLW": ("clv", "<", 0.70), "X2G": ("x2", "<=", 0.0)}
