"""scripts/breadth_ndx_study.py 的纯函数：宽度、样本（只取美股牛、之后 63 日）、判定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import breadth_ndx_study as S  # noqa: E402


def test_breadth_counts_industries_above_ma():
    idx = pd.bdate_range("2000-01-03", periods=10)
    R = pd.DataFrame({"up": 1.0, "down": -1.0, "flat": 0.0}, index=idx)
    b = S.breadth(R, n=3)
    assert b.iloc[:2].isna().all() and np.isclose(b.iloc[-1], 1 / 3)


def test_sample_only_bull_months_and_forward_return():
    idx = pd.bdate_range("2000-01-03", periods=400)
    B = pd.Series(0.6, index=idx)
    tr = pd.Series(np.linspace(100, 200, 400), index=idx)
    bear = pd.Series(False, index=idx)
    bear[idx >= pd.Timestamp("2000-06-01")] = True
    s = S.sample(B, tr, bear)
    assert len(s) and (s.index < pd.Timestamp("2000-06-01")).all()
    d = s.index[0]
    i = idx.get_loc(d)
    assert np.isclose(s.loc[d, "fwd"], tr.iloc[i + S.H] / tr.iloc[i] - 1)


def test_fisher_p():
    assert S.fisher_p(0.3, 80) < 0.01 and S.fisher_p(-0.1, 80) > 0.5 and S.fisher_p(0.5, 3) is None
