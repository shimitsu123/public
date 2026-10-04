"""第九个研究循环第 6 轮（scripts/loop9_r06_distrev.py）的纯函数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop9_r06_distrev as R  # noqa: E402


def _df(vols, closes=None):
    idx = pd.bdate_range("2020-01-06", periods=len(vols))
    c = closes if closes is not None else [100.0] * len(vols)
    return pd.DataFrame({"Close": np.asarray(c, float), "Volume": np.asarray(vols, float)}, index=idx)


def test_vol_up_days_compares_same_stocks_only():
    fa = {"A": _df([100, 120, 0, 150]), "B": _df([50, 40, 60, 10])}
    V = R.volumes_of(fa)
    up = R.vol_up_days(V)
    # 第 2 天：A 100→120、B 50→40 → 160 > 150 ✓；第 3 天：A 是 0（当作没有）→ 只比 B 40→60 ✓；第 4 天：A 前一天没有 → 只比 B 60→10 ✗
    assert list(up) == [False, True, True, False]


def test_dist_days_and_gate_count():
    idx = pd.bdate_range("2020-01-06", periods=6)
    close = pd.Series([100, 99.7, 99.9, 99.6, 99.0, 99.5], index=idx, dtype=float)
    up = pd.Series([False, True, True, False, True, True], index=idx)
    dd = R.dist_days(close, up)
    # 第 2 天 −0.3% 且放量 ✓；第 4 天 −0.3% 但缩量 ✗；第 5 天 −0.6% 放量 ✓
    assert list(dd) == [False, True, False, False, True, False]
    assert list(R.dist_gate_days(dd, n=3, k=2)) == [False] * 6                      # 任何 3 天的窗口里最多 1 个
    assert list(R.dist_gate_days(dd, n=4, k=2)) == [False, False, False, False, True, False]   # 第 2〜5 天有 2 个；不满 4 天 → 不成立


def test_dist_gate_expires_after_5pct_rally():
    idx = pd.bdate_range("2020-01-06", periods=5)
    dd = pd.Series([True, True, False, False, False], index=idx)
    flat = pd.Series([100.0, 99.0, 99.5, 100.0, 100.0], index=idx)
    rally = pd.Series([100.0, 99.0, 104.0, 106.0, 106.0], index=idx)
    assert list(R.dist_gate_days(dd, flat, n=4, k=2)) == [False, False, False, True, False]   # 窗口 4：第 4 天还有 2 个；第 5 天第 1 个过期
    # 第 4 天：第 1 个出货日（100）之后最高 106 ≥ 105 → 作废；第 2 个（99）之后 106 ≥ 103.95 → 也作废 → 不成立
    assert list(R.dist_gate_days(dd, rally, n=4, k=2)) == [False, False, False, False, False]


def test_ret_pct_and_rev_gate_use_past_only():
    idx = pd.bdate_range("2020-01-06", periods=4)
    closes = pd.DataFrame({"A": [10, 10, 10, 20], "B": [10, 11, 12, 13], "C": [10, 9, 8, 7]}, index=idx, dtype=float)
    pct = R.ret_pct(closes, n=2)
    assert np.isnan(pct.iloc[1]["A"])                                          # 不够 2 天 → NaN
    assert pct.iloc[3]["A"] == 1.0 and pct.iloc[3]["C"] < pct.iloc[3]["B"]
    g = R.rev_gate(["A", "B", "Z"], [idx[3]] * 3, pct, top=0.9)
    assert list(g) == [True, False, False]                                     # A 排第一（> 0.9）→ 挡；B 不是；Z 不在池子 → 不挡
    assert not R.rev_gate(["A"], [idx[2]], pct, top=0.9)[0]                     # 第 3 天 A 还没涨（之后的大涨不影响）


def test_round_constants():
    assert R.IDS == ("MDD", "RVS") and R.KINDS == {"MDD": "date", "RVS": "stock"} and R.POSTHOC is False
    assert all(v.startswith("选股") for v in R.FAMILY.values())
