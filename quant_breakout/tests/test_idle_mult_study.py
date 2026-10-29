"""scripts/idle_mult_study.py（2026-10-05 登记）：登记值、倍数 = 三层取最小（缺 = 1）、宏观层与模拟盘同一个函数、接法（1545 / 1482）、
第二关只平移 m（窗外不动）、分布与「哪一层最小」的计数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import idle_mult_study as S  # noqa: E402
import loop2_r02_bondrefuge as T2  # noqa: E402
import research_loop6 as R6  # noqa: E402


def test_registered_constants():
    assert S.IDS == ("IM1", "IM2") and S.DESC == ("Q", "MAC", "MA")
    assert S.KIND == {"IM1": "signal", "IM2": "signal"}
    assert S.BOND == {"IM1": True, "IM2": False, "Q": True, "MAC": True, "MA": True}
    assert S.LAYER == {"Q": "q", "MAC": "mac", "MA": "ma"} and S.LEVELS == (0.0, 0.5, 0.75, 1.0) and S.MACRO_YEARS == 27
    assert R6.PLACEBO_N == 400 and R6.SHIFT_FROM == "2000-01-04"


def test_readings_take_min_and_fill_one():
    d = pd.bdate_range("2024-01-01", periods=5)
    qr = pd.Series([1.0, 0.75, 0.0, 1.0, 1.0], index=d)
    mac = pd.Series([1.0, 1.0, 0.5, 0.75, 1.0], index=d)
    ma = pd.Series([1.0, 0.5, 1.0], index=d[:3])                       # 后两天没有值 → 前向填充最后一个（1.0）
    R = S.readings(qr, mac, ma, d)
    assert R["m"].tolist() == [1.0, 0.5, 0.0, 0.75, 1.0]
    assert R["ma"].tolist() == [1.0, 0.5, 1.0, 1.0, 1.0]
    R2 = S.readings(qr, mac, pd.Series(dtype=float), d)                   # 判断层完全没有值 → 当 1
    assert R2["m"].tolist() == [1.0, 0.75, 0.0, 0.75, 1.0]


def test_macro_series_uses_production_rules():
    from qbreak.macro import TH
    d = pd.bdate_range("2024-01-01", periods=3)
    frame = pd.DataFrame({"brent": [90.0, TH["oil_high"] + 1, 90.0], "brent_chg20_pct": [0.0, 0.0, 0.0],
                          "us10y": [4.0, 4.0, TH["us10y_stress"] + 0.1], "vix": [15.0, 15.0, 15.0], "usdjpy": [140.0, 140.0, 140.0]}, index=d)
    m = S.macro_series(frame, d)
    assert m.tolist() == [1.0, 0.75, 0.5]
    assert (S.macro_series(pd.DataFrame(), d) == 1.0).all()


def test_over_for_keys():
    m = pd.Series([0.5, 1.2, -0.1], index=pd.bdate_range("2024-01-01", periods=3))
    a = S.over_for(m, True)
    assert set(a) == {"core_expo", "extra_expo"} and list(a["core_expo"]) == ["US"] and list(a["extra_expo"]) == [T2.BD_KEY]
    assert a["core_expo"]["US"].tolist() == [0.5, 1.0, 0.0] and a["extra_expo"][T2.BD_KEY].tolist() == [0.5, 1.0, 0.0]
    b = S.over_for(m, False)
    assert set(b) == {"core_expo"}


def test_shift_only_inside_window():
    idx = pd.bdate_range("1999-12-20", "2026-10-02")
    m = pd.Series(np.where(np.arange(len(idx)) % 7 == 0, 0.5, 1.0), index=idx)
    s0 = S.shifted(m, None)
    assert s0.equals(m.astype(float))
    k = 300
    s = S.shifted(m, k)
    w = R6.shift_window(m)
    assert np.allclose(s.loc[w.index].to_numpy(), np.roll(w.to_numpy(), k))
    out = ~idx.isin(w.index)
    assert np.allclose(s[out].to_numpy(), m[out].to_numpy())
    assert S.placebo_ks(len(w))[:3] == R6.shift_ks(len(w), 0)[:3]


def test_dist_and_binding():
    d = pd.bdate_range("2024-01-01", periods=6)
    R = pd.DataFrame({"q": [1.0, 0.75, 0.0, 1.0, 1.0, 1.0], "mac": [1.0, 0.75, 0.5, 0.5, 1.0, 1.0],
                      "ma": [1.0, 1.0, 1.0, 0.75, 0.75, 1.0]}, index=d)
    R["m"] = R[["q", "mac", "ma"]].min(axis=1)
    b = S.binding(R)
    assert b["days"] == 4 and b["q"] == 50.0 and b["mac"] == 50.0 and b["ma"] == 25.0      # 第 2 天 q、mac 并列
    x = S.dist(R, d)
    assert x["days"] == 6 and x["pct"] == {"0": 16.7, "0.5": 16.7, "0.75": 33.3, "1": 33.3}
    assert x["segments_lt1"] == 1 and x["q_lt1_pct"] == 33.3
    assert S.dist(R, pd.bdate_range("2030-01-01", periods=2)) == {"days": 0}
