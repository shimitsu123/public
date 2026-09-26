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
