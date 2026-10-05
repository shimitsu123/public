"""第十一个研究循环第 6 轮（scripts/loop11_r06_stage.py）：单边放宽、三档标签、常量。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop11_r01_cycle as R1  # noqa: E402
import loop11_r06_stage as R  # noqa: E402


def test_round_constants():
    assert R.ROUND == 6 and R.IDS == ("SZS", "TAG", "N52") and all(R.POSTHOC.values())
    assert R.MENUS == {"SZS": {"small": R1.WIDE}, "TAG": {"low": R1.WIDE, "high": R1.TIGHT}, "N52": {"low": R1.TIGHT, "high": R1.WIDE}}
    assert R.SZS_CUT == 9.1557 and R.PANEL_COL == {"SZS": "lturn", "TAG": "r120", "N52": "hi52"}


def test_szs_one_sided():
    X = pd.DataFrame({"lturn": [9.0, 9.1557, 9.2, np.nan]})
    assert list(R.labels_of("SZS", X)) == ["small", "small", "base", "base"]


def test_registered_cuts():
    assert R.CUTS == {"TAG": (0.0133, 0.1065), "N52": (0.8965, 0.9558)}
    X = pd.DataFrame({"r120": [0.0, 0.05, 0.2, np.nan], "hi52": [0.8, 0.9, 0.99, np.nan]})
    assert list(R.labels_of("TAG", X)) == ["low", "mid", "high", "na"]
    assert list(R.labels_of("N52", X)) == ["low", "mid", "high", "na"]
