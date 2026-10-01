"""研究循环第 7 轮 NDA（scripts/loop_r07_ndxboth.py，2026-10-01 登记）：登记值、「两个都熊」与「照拿」、引擎参数、第二关的随机改动（只在 S&P 熊的日子里平移）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_r07_ndxboth as N  # noqa: E402


def test_registered_constants():
    assert (N.ROUND, N.IDS, N.ND_KEY) == (7, ("NDA",), "US_ND")
    assert (N.SHIFT_FROM, N.SHIFT_GAP, N.SEED0) == ("2000-01-03", 250, 20261007)


def test_both_bear_and_hold_days_forward_fill_each_side():
    spx = pd.Series([False, True, True], index=pd.to_datetime(["2020-01-06", "2020-01-08", "2020-01-10"]))
    ndx = pd.Series([False, True, False], index=pd.to_datetime(["2020-01-06", "2020-01-09", "2020-01-10"]))
    k = N.both_bear(spx, ndx)
    h = N.hold_days(spx, ndx)
    assert k.index.strftime("%m-%d").tolist() == ["01-06", "01-08", "01-09", "01-10"]
    assert k.tolist() == [False, False, True, False]                                        # 01-09：两个都熊
    assert h.tolist() == [False, True, False, True]                                         # S&P 熊而纳指牛 → 照拿
    o = N.nda_over(k)
    assert o["cfg_over"] == {"core": {"1545.T": 1.0}, "core_index": {"1545.T": "US_ND"}, "core_mode": "split"}
    assert o["extra_bear"]["US_ND"] is k


def test_placebo_moves_hold_flags_only_inside_spx_bear_days():
    idx = pd.bdate_range("1999-01-04", "2026-10-30")
    t = np.arange(len(idx))
    spx = pd.Series((t % 500) < 160, index=idx)                                             # 熊的日子约 1/3
    ndx = pd.Series(((t % 500) < 160) & ~(((t % 500) >= 120) & ((t % 500) < 160)), index=idx)   # 熊的最后 40 天纳指先回到牛
    real = N.both_bear(spx, ndx)
    a, b = N.placebo_key(spx, ndx, 5), N.placebo_key(spx, ndx, 5)
    assert a.equals(b)
    w = (idx >= pd.Timestamp(N.SHIFT_FROM)) & (idx <= pd.Timestamp(N.LCM.J_END))
    sb = spx.to_numpy(bool)
    assert (a.to_numpy(bool)[~sb] == False).all()                                          # noqa: E712  S&P 牛的日子照旧拿
    assert (a.to_numpy(bool)[~w] == real.to_numpy(bool)[~w]).all()                          # 窗口外不变
    held_real = int((sb & w & ~real.to_numpy(bool)).sum())
    held_plc = int((sb & w & ~a.to_numpy(bool)).sum())
    assert held_real == held_plc and held_real > 0                                          # 照拿的天数不变
    assert not a.equals(real)
    n = int((sb & w).sum())
    ks = [N.shift_k(x, n) for x in range(400)]
    assert min(ks) >= 250 and max(ks) <= n - 250
