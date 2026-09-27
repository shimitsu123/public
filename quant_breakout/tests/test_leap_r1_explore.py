"""第 1 轮探索的特征（scripts/leap_r1_explore.py）：长期涨跌、业种强弱只用当天为止；分红收益率只用已发生的分红。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leap_data as LD  # noqa: E402
import leap_r1_explore as X  # noqa: E402


def test_long_returns_skip_last_month_and_no_lookahead():
    C = np.exp(np.arange(1400, dtype=float) / 100.0)[:, None] * np.ones((1, 2))
    R = X.long_returns(C)
    assert np.isnan(R["r3y"][755, 0]) and np.isclose(R["r3y"][800, 0], (756 - 21) / 100.0)
    C2 = C.copy()
    C2[900:] *= 5                                                                   # 之后的大涨不影响之前的值
    assert np.allclose(X.long_returns(C2)["r2y"][:900], R["r2y"][:900], equal_nan=True)


def test_sector_strength_ranks_sectors_without_future():
    n = 400
    up = np.exp(np.arange(n) / 200.0)
    C = np.column_stack([up, up, up, np.ones(n), np.ones(n), np.ones(n)])
    pct, rsec = X.sector_strength(C, ["A", "A", "A", "B", "B", "B"])
    assert pct[300, 0] > pct[300, 3] and np.isclose(rsec[300, 0], 0.0, atol=1e-9)
    C2 = C.copy()
    C2[350:, 3:] *= 10
    p2, _ = X.sector_strength(C2, ["A", "A", "A", "B", "B", "B"])
    assert np.allclose(p2[:350], pct[:350], equal_nan=True)


def test_div_yield_uses_only_paid_dividends():
    idx = pd.bdate_range("2020-01-01", "2022-12-30")
    act = pd.DataFrame({"close_raw": 1000.0, "div": 0.0}, index=idx)
    act.loc[pd.Timestamp("2021-03-29"), "div"] = 20.0
    y = LD.div_yield(act, idx)
    assert y.loc["2021-03-26"] == 0.0 and np.isclose(y.loc["2021-03-29"], 2.0) and np.isclose(y.loc["2022-03-28"], 2.0)
    assert y.loc["2022-03-30"] == 0.0 and np.isnan(y.loc["2020-06-01"])            # 历史不满一年 → 缺值


def test_quintiles_and_composite_directions():
    T = pd.DataFrame({"dy": np.arange(50.0), "r3y": -np.arange(50.0), "sec": np.arange(50.0), "vr1": np.arange(50.0),
                      "w5v": np.arange(50.0), "net": np.arange(50.0)})
    q = X.quintiles(T["dy"])
    assert q.iloc[0] == 1 and q.iloc[-1] == 5
    c = X.composite(T)
    assert c.iloc[-1] > c.iloc[0]                                                  # 高股息 + 3 年跌得多 + 强业种 + 放量 → 分高
