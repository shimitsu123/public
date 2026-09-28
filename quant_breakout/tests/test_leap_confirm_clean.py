"""scripts/leap_confirm.py：QB_DROP_ZERO_VOL=1 时去掉成交量 ≤ 0 的行（缺省不去，以前的研究可重现）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leap_confirm as LF  # noqa: E402


def _fake(monkeypatch):
    idx = pd.bdate_range("2001-01-01", periods=120)
    df = pd.DataFrame({"Open": 10.0, "High": 11.0, "Low": 9.0, "Close": 10.0, "Volume": 1000.0}, index=idx)
    df.iloc[[3, 4], df.columns.get_loc("Volume")] = 0.0                          # 休市假行
    import leap_data as LD
    monkeypatch.setattr(LD, "ohlcv", lambda names: {n: df.copy() for n in names})
    return idx


def test_default_keeps_zero_volume_rows(monkeypatch):
    monkeypatch.delenv("QB_DROP_ZERO_VOL", raising=False)
    idx = _fake(monkeypatch)
    P, days, nm = LF.yf_panel(["A.T", "B.T"], "2001-01-01", "2001-12-31")
    assert len(days) == len(idx) and nm == ["A.T", "B.T"]


def test_env_drops_zero_volume_rows(monkeypatch):
    monkeypatch.setenv("QB_DROP_ZERO_VOL", "1")
    idx = _fake(monkeypatch)
    P, days, nm = LF.yf_panel(["A.T", "B.T"], "2001-01-01", "2001-12-31")
    assert len(days) == len(idx) - 2 and idx[3] not in days and np.isfinite(P["C"]).all()
