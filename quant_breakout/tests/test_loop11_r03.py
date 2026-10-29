"""第十一个研究循环第 3 轮（scripts/loop11_r03_info.py）：信息离散度、学参数复用第 1 轮规则、常量。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop11_r01_cycle as R1  # noqa: E402
import loop11_r03_info as R  # noqa: E402


def test_round_constants():
    assert R.ROUND == 3 and R.IDS == ("FRG", "BTK", "SMK") and all(not v for v in R.POSTHOC.values())
    assert R.OPTIONS is R1.OPTIONS and R.MENUS["FRG"] == {"low": R.WIDE, "high": R.TIGHT} and R.MENUS["SMK"] == {"low": R.TIGHT, "high": R.WIDE}
    assert R.PANEL_COL == {"BTK": "b_n225", "SMK": "sec"} and R.FIP_N == 250


def test_info_discreteness():
    up_smooth = 100 * np.cumprod(np.r_[1.0, np.full(250, 1.002)])             # 每天都小涨 → ID = −1
    assert R.info_discreteness(up_smooth, 250) == -1.0
    jumpy = np.r_[100.0, 100 * np.cumprod(np.where(np.arange(250) % 25 == 0, 1.08, 0.999))]   # 少数大跳、多数小跌 → ID > 0
    assert R.info_discreteness(jumpy, 250) > 0.5
    down_smooth = 100 * np.cumprod(np.r_[1.0, np.full(250, 0.998)])           # 一直小跌：sign − × (1 − 0) = −1（顺着方向连续）
    assert R.info_discreteness(down_smooth, 250) == -1.0
    assert np.isnan(R.info_discreteness(up_smooth, 100))


def test_learn_map_btk():
    T = pd.DataFrame({"label": ["high"] * 25, "net_tight": [0.5] * 25, "net_base": [0.4] * 20 + [-0.1] * 5, "net_wide": [-1.0] * 25})
    assert R.learn_map(T) == {"low": "base", "mid": "base", "high": "tight"}


def test_registered_cuts():
    assert R.CUTS == {"FRG": (-0.04, 0.0), "BTK": (0.5886, 0.873), "SMK": (0.3333, 0.6291)}
