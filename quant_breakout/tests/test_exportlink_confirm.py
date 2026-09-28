"""EX1 的确认（scripts/exportlink_confirm.py）：只检验 EX1、窗口、直接 / 间接分开的描述。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import exportlink_confirm as EC                                              # noqa: E402


def test_only_ex1_and_windows():
    assert EC.KEY == "EX1"
    assert EC.WIN == {"Z": ("2001-01-04", "2006-09-30"), "W": ("2006-10-01", "2016-09-30")}


def test_group_split():
    S = pd.DataFrame({"group": ["direct", "direct", "indirect", "indirect", "domestic"],
                      "ov": [0.5, -0.5, 1.0, np.nan, -1.0], "net": [2.0, -1.0, 1.0, 5.0, -3.0]})
    g = EC.group_split(S)
    assert g["direct"]["n"] == 2 and g["direct"]["kept"] == 1 and g["direct"]["dmean"] == pytest.approx(2.0 - 0.5)
    assert g["indirect"]["n"] == 1 and g["indirect"]["dmean"] == pytest.approx(0.0)   # 缺值的不算进范围
