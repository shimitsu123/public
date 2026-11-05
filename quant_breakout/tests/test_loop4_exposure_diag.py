"""只描述的诊断 scripts/loop4_exposure_diag.py：每天持有只数（买入日 ≤ d < 卖出日、未平仓到最后一天）、牛市日（200 日线、至少 150 天）、汇总。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop4_exposure_diag as T  # noqa: E402


def test_held_counts():
    days = pd.bdate_range("2024-01-01", periods=10)
    tr = pd.DataFrame({"entry_date": [str(days[1].date()), str(days[3].date()), str(days[8].date())],
                       "exit_date": [str(days[4].date()), str(days[5].date()), None]})
    c = T.held_counts(tr, days)
    assert list(c) == [0, 1, 1, 2, 1, 0, 0, 0, 1, 1]                        # 卖出日当天不算；未平仓持有到最后


def test_bull_days_and_summarize():
    idx = pd.bdate_range("2020-01-01", periods=400)
    close = pd.Series(np.r_[np.linspace(100, 200, 300), np.linspace(200, 120, 100)], index=idx)
    b = T.bull_days(close, idx)
    assert not b[:149].any() and b[200] and not b[-1]                       # 不到 150 天 → 不算；上涨中在线上；跌破之后不在
    cnt = pd.Series([0, 0, 1, 4, 2], index=idx[:5])
    s = T.summarize(cnt, np.array([True, False, True, True, False]))
    assert s["avg_held"] == pytest.approx(1.4) and s["avg_expo_pct"] == pytest.approx(35.0) and s["full_days_pct"] == pytest.approx(20.0)
    assert s["share_pct"]["0"] == pytest.approx(40.0) and s["bull_zero_pct"] == pytest.approx(100 / 3)
