"""第九个研究循环第 5 轮（scripts/loop9_r05_marketext.py）的纯函数。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop9_r05_marketext as R  # noqa: E402


def test_overheat_days_needs_full_window_and_threshold():
    c = pd.Series([100.0, 100.0, 100.0, 108.0], index=pd.bdate_range("2020-01-06", periods=4))
    # 第 3 天起均线满 3 天：第 4 天 108 ÷ 均线 102.67 − 1 = +5.2% → 成立
    assert list(R.overheat_days(c, n=3, thr=0.05)) == [False, False, False, True]
    assert list(R.overheat_days(c, n=3, thr=0.06)) == [False, False, False, False]


def test_drawdown_days_uses_max_including_today():
    c = pd.Series([100.0, 110.0, 104.0, 104.4, 120.0], index=pd.bdate_range("2020-01-06", periods=5))
    # 窗口 3：第 3 天 104 ÷ 110 − 1 = −5.5% → 成立；第 4 天 104.4 ÷ 110 − 1 = −5.1% → 成立；第 5 天新高 → 不成立
    assert list(R.drawdown_days(c, n=3, thr=-0.05)) == [False, False, True, True, False]


def test_round_constants():
    assert R.IDS == ("N25U", "NDD") and set(R.KINDS.values()) == {"date"} and R.POSTHOC is False
    assert all(v.startswith("选股") for v in R.FAMILY.values())
