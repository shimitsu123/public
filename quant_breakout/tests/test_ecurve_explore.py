"""scripts/ecurve_explore.py：影子交易的近期表现只用信号日收盘前已卖出的交易。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ecurve_explore as E                                                   # noqa: E402


def test_shadow_perf_uses_only_completed_trades():
    ex = pd.bdate_range("2026-01-05", periods=60)
    sh = pd.DataFrame({"exit_date": ex, "net": np.arange(60, dtype=float)})
    X = E.shadow_perf(sh, pd.DatetimeIndex([ex[18], ex[19], ex[59]]))
    assert np.isnan(X["R20"].iloc[0])                                        # 19 笔 < 20
    assert X["R20"].iloc[1] == np.mean(np.arange(20))                        # 当天卖出的算（exit_date ≤ d）
    assert X["R50"].iloc[2] == np.mean(np.arange(10, 60))
    d60 = sh[(sh["exit_date"] > ex[59] - pd.Timedelta(days=60)) & (sh["exit_date"] <= ex[59])]["net"].mean()
    assert abs(X["D60"].iloc[2] - d60) < 1e-12
