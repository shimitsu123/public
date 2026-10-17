"""第十个研究循环第 1 轮（scripts/loop10_r01_weakvote.py）的纯函数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop10_r01_weakvote as R  # noqa: E402


def test_vote_days_counts_aligned_series():
    idx = pd.bdate_range("2020-01-06", periods=4)
    a = pd.Series([True, True, False, False], index=idx)
    b = pd.Series([True, False, True, False], index=idx)
    c = pd.Series([False, True, True], index=idx[[0, 1, 3]])                  # 第 3 天没有值 → 用前一天的 True
    assert list(R.vote_days([a, b, c], 2)) == [True, True, True, False]       # 第 4 天只有 c 成立
    assert list(R.vote_days([a, b, c], 3)) == [False, False, False, False]
    assert list(R.both_days(a, b)) == [True, False, False, False]


def test_rel_gap_days_threshold_and_window():
    idx = pd.bdate_range("2020-01-06", periods=4)
    jp = pd.Series([100.0, 100.0, 95.0, 100.0], index=idx)
    core = pd.Series([100.0, 100.0, 104.0, 108.0], index=idx)
    g = R.rel_gap_days(jp, core, n=2, gap=-0.10)
    # 第 3 天：日経 −5%、核心 +4% → −9 pp（不到 −10）；第 4 天：日経 0%、核心 +8% → −8 pp
    assert list(g) == [False, False, False, False]
    assert list(R.rel_gap_days(jp, core, n=2, gap=-0.08)) == [False, False, True, True]


def test_round_constants():
    assert R.IDS == ("WMV", "MJR", "JRM") and set(R.KINDS.values()) == {"date"} and all(R.POSTHOC.values())
    assert all(v.startswith("选股") for v in R.FAMILY.values())
    assert R.ERA_OF["W"] == "E" and R.ERA_OF["Jx"] == "J" and R.ERA_OF["Zx"] == "Z"
