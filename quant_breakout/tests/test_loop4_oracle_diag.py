"""事后诊断 scripts/loop4_oracle_diag.py：核心同期收益、「亏的 / 跑输核心的」判定、信号日 = 成交日前一个交易日。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop4_oracle_diag as T  # noqa: E402


def test_core_ret_and_bad_mask():
    idx = pd.bdate_range("2024-01-01", periods=10)
    core = pd.Series(np.linspace(100, 109, 10), index=idx)                  # 每天 +1
    assert T.core_ret(core, idx[0], idx[5]) == pytest.approx(5.0)
    assert np.isnan(T.core_ret(core, idx[0], idx[-1] + pd.Timedelta(days=30)))
    tr = pd.DataFrame({"entry_date": [str(idx[0].date())] * 3, "exit_date": [str(idx[5].date())] * 3, "ret_pct": [-1.0, 3.0, 8.0]})
    assert list(T.bad_mask(tr, core, "O1")) == [True, False, False]          # 亏的
    assert list(T.bad_mask(tr, core, "O2")) == [True, True, False]           # 跑输核心同期 +5% 的


def test_signal_days_previous_trading_day():
    days = pd.bdate_range("2024-01-01", periods=10)
    tr = pd.DataFrame({"entry_date": [str(days[3].date()), str(days[0].date())]})
    assert T.signal_days(tr, days) == [days[2], days[0]]
    assert T.ITER == 3
