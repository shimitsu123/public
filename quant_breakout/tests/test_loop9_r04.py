"""第九个研究循环第 4 轮（scripts/loop9_r04_base.py）的纯函数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop9_r04_base as R  # noqa: E402


def test_sector_breadth_and_gate():
    idx = pd.bdate_range("2020-01-06", periods=5)
    closes = pd.DataFrame({"A": [1, 2, 3, 4, 5], "B": [5, 4, 3, 2, 1], "C": [5, 4, 3, 2, 1], "D": [1, 1, 1, 1, 2]}, index=idx, dtype=float)
    sec_of = {"A": "x", "B": "x", "C": "x", "D": "y"}
    br = R.sector_breadth(closes, sec_of, n=2, min_n=2, min_peers=3)
    # 业种 x 第 2 天起：A 在均线上、B / C 在下 → 1/3；业种 y 只有 1 只 → NaN
    assert abs(br["x"].iloc[-1] - 1 / 3) < 1e-12 and np.isnan(br["y"].iloc[-1])
    g = R.sec_gate(["A", "D", "Z"], [idx[-1]] * 3, br, {**sec_of, "Z": None}, weak=0.34)
    assert list(g) == [True, False, False]                                     # x 的 1/3 < 0.34 → 挡；y 算不出、Z 没有业种 → 不挡


def test_sector_breadth_uses_only_past_closes():
    idx = pd.bdate_range("2020-01-06", periods=6)
    closes = pd.DataFrame({"A": [1, 1, 1, 1, 1, 9], "B": [1, 1, 1, 1, 1, 9], "C": [1, 1, 1, 1, 1, 9]}, index=idx, dtype=float)
    br = R.sector_breadth(closes, {"A": "x", "B": "x", "C": "x"}, n=3, min_n=3, min_peers=3)
    assert br["x"].iloc[4] == 0.0 and br["x"].iloc[5] == 1.0                   # 第 5 天的值不受第 6 天的大涨影响（没有用到未来）
    g = R.sec_gate(["A", "A"], [idx[4], idx[5]], br, {"A": "x"}, weak=1 / 3)
    assert list(g) == [True, False]


def test_round_constants():
    assert R.IDS == ("SBW",) and R.KINDS == {"SBW": "stock"} and R.POSTHOC is False
    assert R.FAMILY["SBW"].startswith("选股")
