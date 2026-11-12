"""第十一个研究循环第 7 轮（scripts/loop11_r07_last.py）：TCY 周期 → 最长持有（限制在 20〜60、算不了 → 60）、常量。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop11_common as LC  # noqa: E402
import loop11_r01_cycle as R1  # noqa: E402
import loop11_r07_last as R  # noqa: E402


def test_round_constants():
    assert R.ROUND == 7 and R.IDS == ("TCY", "VBK") and R.POSTHOC == {"TCY": True, "VBK": False}
    assert R.MENUS == {"TCY": {}, "VBK": {"low": R1.TIGHT, "high": R1.WIDE}}
    assert (R.TCY_MULT, R.TCY_MIN, R.TCY_MAX) == (1.5, 20, 60)


def test_tcy_hold_clip_and_nan():
    h = R.tcy_hold([5.0, 13.0, 14.0, 30.0, 41.0, np.nan, np.inf])
    assert list(h) == [20, 20, 21, 45, 60, 60, 60]                             # 1.5 × 13 = 19.5 → 20（限下限）；1.5 × 14 = 21
    assert h.dtype.kind == "i"


def test_tcy_labels_are_specs():
    lab = R.tcy_labels([30.0, np.nan])
    assert list(lab) == [LC.spec_label({"k": 3.0, "mh": 45}), LC.spec_label({"k": 3.0, "mh": 60})]
    assert LC.is_base(LC.parse_spec_label(lab[1]))                              # 算不了 → 与 B3 同参数


def test_registered_cuts():
    import pandas as pd
    assert R.CUTS == {"VBK": (1.7761, 2.3092)}
    X = pd.DataFrame({"vr1": [1.5, 2.0, 3.0, np.nan]})
    assert list(R.labels_of("VBK", X, {})) == ["low", "mid", "high", "na"]
