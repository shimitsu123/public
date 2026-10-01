"""研究循环第 8 轮 NDR（scripts/loop_r08_ndxreentry.py，2026-10-01 登记）：登记值、「早回来」状态机、1545 的键、第二关的随机改动。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_r08_ndxreentry as R  # noqa: E402


def test_registered_constants():
    assert (R.ROUND, R.IDS, R.NR_KEY, R.OLD) == (8, ("NDR",), "US_NR", ("1987-01-01", "2000-12-31"))
    assert (R.SHIFT_FROM, R.SHIFT_GAP, R.SEED0) == ("2000-01-03", 250, 20261008)


def test_reentry_needs_ndx_bear_inside_the_same_spx_bear_episode():
    d = pd.bdate_range("2020-01-06", periods=12)
    spx = pd.Series([0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 0], index=d).astype(bool)
    ndx = pd.Series([0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0], index=d).astype(bool)
    re = R.reentry(spx, ndx)
    # 第一段 S&P 熊（1〜5）：纳指 3 熊 → 4 早回来；5 又熊 → 不是；第二段（7〜10）纳指在这一段里没熊过 → 都不是（离场照 B0）
    assert re.astype(int).tolist() == [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0]
    k = R.nr_key(spx, ndx)
    assert k.astype(int).tolist() == [0, 1, 1, 1, 0, 1, 0, 1, 1, 1, 1, 0]
    o = R.ndr_over(k)
    assert o["cfg_over"] == {"core": {"1545.T": 1.0}, "core_index": {"1545.T": "US_NR"}, "core_mode": "split"}
    assert o["extra_bear"]["US_NR"] is k


def test_reentry_counts_ndx_bear_that_started_before_the_spx_bear():
    d = pd.bdate_range("2022-01-03", periods=6)
    spx = pd.Series([0, 0, 1, 1, 1, 0], index=d).astype(bool)
    ndx = pd.Series([1, 1, 1, 0, 0, 0], index=d).astype(bool)                               # 纳指先熊、S&P 后熊
    assert R.reentry(spx, ndx).astype(int).tolist() == [0, 0, 0, 1, 1, 0]


def test_placebo_moves_reentry_flags_only_inside_spx_bear_days():
    idx = pd.bdate_range("1999-01-04", "2026-10-30")
    t = np.arange(len(idx)) % 500
    spx = pd.Series(t < 160, index=idx)
    ndx = pd.Series((t >= 10) & (t < 120), index=idx)                                       # 熊市里纳指 10〜119 熊、120〜159 先回到牛
    real = R.nr_key(spx, ndx)
    a = R.placebo_key(spx, ndx, 9)
    assert a.equals(R.placebo_key(spx, ndx, 9)) and not a.equals(real)
    w = (idx >= pd.Timestamp(R.SHIFT_FROM)) & (idx <= pd.Timestamp(R.LCM.J_END))
    sb = spx.to_numpy(bool)
    assert not a.to_numpy(bool)[~sb].any()                                                  # S&P 牛的日子照旧拿
    assert (a.to_numpy(bool)[~w] == real.to_numpy(bool)[~w]).all()                          # 窗口外不变
    assert int((sb & w & ~a.to_numpy(bool)).sum()) == int((sb & w & ~real.to_numpy(bool)).sum()) > 0
    seg = R.segments(R.reentry(spx, ndx), "2001-01-01", "2001-12-31")
    assert all(n == 40 for _, _, n in seg[1:-1])
