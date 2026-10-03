"""研究循环第 9 轮 CPX（scripts/loop_r09_crashbreak.py，2026-10-01 登记）：登记值、急跌状态机、键的合并、循环平移。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_r09_crashbreak as C  # noqa: E402


def test_registered_constants():
    assert (C.ROUND, C.IDS, C.HI_N, C.DROP, C.MA_N, C.CX_KEY) == (9, ("CPX",), 10, 0.10, 20, "US_CX")
    assert (C.SHIFT_FROM, C.SHIFT_GAP, C.SEED0) == ("2000-01-03", 250, 20261009)


def test_crash_starts_on_10pct_below_10day_high_and_ends_above_20day_mean():
    idx = pd.bdate_range("2020-01-01", periods=60)
    px = np.r_[np.full(30, 100.0), [97.0, 94.0, 91.0, 89.5, 88.0], np.full(10, 88.0), np.linspace(88, 104, 15)]
    s = pd.Series(px, index=idx)
    st = C.crash_state(s)
    first = int(np.argmax(st.to_numpy()))
    assert px[first] == 89.5                                                                # 第一次 ≤ 100 × 0.9 那天开始
    ma = s.rolling(20).mean().to_numpy()
    end = first + int(np.argmax(~st.to_numpy()[first:]))
    assert px[end] > ma[end] and (px[first:end] <= ma[first:end]).all()                     # 第一次收在 20 日线之上那天结束
    assert C.episodes(st) == 1 and not st.iloc[:first].any()


def test_or_series_and_override():
    bear = pd.Series([False, True, False], index=pd.to_datetime(["2020-01-06", "2020-01-08", "2020-01-10"]))
    crash = pd.Series([True, False], index=pd.to_datetime(["2020-01-07", "2020-01-09"]))
    k = C.or_series(bear, crash)
    assert k.tolist() == [False, True, True, True, False]                                   # 01-09：熊向后填还是熊
    o = C.cpx_over(bear, crash)
    assert o["cfg_over"] == {"core": {"1545.T": 1.0}, "core_index": {"1545.T": "US_CX"}, "core_mode": "split"}
    assert o["extra_bear"]["US_CX"].tolist() == k.tolist()


def test_shift_placebo_keeps_crash_days_and_is_reproducible():
    idx = pd.bdate_range("1999-06-01", "2026-10-30")
    s = pd.Series((np.arange(len(idx)) % 700) < 15, index=idx)
    a, b = C.shifted(s, 11), C.shifted(s, 11)
    assert a.equals(b) and int(a.sum()) == int(C.shift_domain(s).sum())
    w = C.shift_domain(s)
    ks = [C.shift_k(x, len(w)) for x in range(400)]
    assert min(ks) >= 250 and max(ks) <= len(w) - 250 and len(set(ks)) > 300
    assert C.segments(s, "1999-06-01", "1999-12-31")[0][2] == 15
