"""scripts/industry_cycle_study.py：年度 → 月度的事件、E 在 P 里不算、事件与基准的比较（合成数据）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import industry_cycle_study as S  # noqa: E402


def test_constants():
    assert (S.H_MAIN, S.H_SHORT, S.BOOT_N, S.SEED) == (24, 12, 2000, 20261005)
    assert S.US_SPLIT == pd.Timestamp("1976-01-01") and (S.US_E_MONTH, S.JP_E_MONTH) == (6, 9)
    assert np.isclose(S.GSY_LOG, np.log(2.0))


def test_annual_to_month():
    idx = pd.date_range("2000-01-01", periods=24, freq="MS")
    f = pd.DataFrame({"A": [True, False]}, index=pd.Index([2000, 2001]))
    m = S.annual_to_month(f, 6, idx)
    assert list(np.where(m["A"])[0]) == [5]                                  # 2000-06 那一行


def test_compare_block_and_mask():
    idx = pd.date_range("1970-01-01", periods=120, freq="MS")
    ret = pd.DataFrame({"A": np.full(120, 2.0), "B": np.full(120, 0.0)}, index=idx)
    mkt = pd.Series(np.full(120, 1.0), index=idx)
    oc = S.outcome_tables(ret, mkt)
    ev = pd.DataFrame(False, index=idx, columns=["A", "B"])
    ev.iloc[10, 0] = True
    ev.iloc[80, 0] = True
    r = S.compare(ev, oc, None, pd.Timestamp("1975-01-01"))
    assert r["all"]["n_events"] == 2 and r["all"]["diff"] > 0                # A 每月比市场多涨 → 事件的超额 > 全部的平均
    assert r["h1"]["n_events"] == 1 and r["h2"]["n_events"] == 1
    mask = S.month_mask(idx, ["A", "B"], 6)
    r2 = S.compare(ev, oc, mask, None)
    assert r2["all"]["base"] is not None
