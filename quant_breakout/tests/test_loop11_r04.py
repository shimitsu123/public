"""第十一个研究循环第 4 轮（scripts/loop11_r04_industry.py）：业种等权指数、ATR 近似、常量。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop11_r01_cycle as R1  # noqa: E402
import loop11_r04_industry as R  # noqa: E402


def test_round_constants():
    assert R.ROUND == 4 and R.IDS == ("ICY", "RSD", "DVY") and all(not v for v in R.POSTHOC.values())
    assert R.TIGHT is R1.TIGHT and R.WIDE is R1.WIDE
    assert R.MENUS == {"ICY": {"short": R1.TIGHT, "long": R1.WIDE}, "RSD": {"low": R1.WIDE, "high": R1.TIGHT}, "DVY": {"low": R1.WIDE, "high": R1.TIGHT}}
    assert R.PANEL_COL == {"RSD": "corr60", "DVY": "dy"} and R.ERA_OF_POOL == {"W": "E", "Jx": "J", "Zx": "Z"}


def test_industry_index_equal_weight_log_returns():
    idx = pd.bdate_range("2026-01-01", periods=4)
    c = pd.DataFrame({"A": [100, 110, 121, 121.0], "B": [50, 50, 50, 55.0], "C": [10, 9, np.nan, 9.0], "D": [1, 1, 1, 1.0]}, index=idx)
    lv = R.industry_index(c, ["A", "B", "C"], min_members=2)
    r = np.log(lv).diff().round(6).tolist()
    assert np.isnan(r[0])
    assert abs(r[1] - (np.log(1.1) + 0 + np.log(0.9)) / 3) < 1e-6                    # 三个成员平均
    assert abs(r[2] - (np.log(1.1) + 0) / 2) < 1e-6                                   # C 缺值 → 两个成员平均
    assert R.industry_index(c, ["A", "Z"], min_members=3) is None                     # 成员不够


def test_atr_proxy():
    lv = pd.Series(100 * 1.01 ** np.arange(30.0))
    a = R.atr_proxy(lv, 14)
    assert np.isnan(a.iloc[13]) and abs(a.iloc[20] / lv.iloc[20] - 0.01) < 1e-9


def test_registered_cuts():
    assert R.CUTS == {"ICY": (8.0, 10.0), "RSD": (0.4363, 0.5904), "DVY": (1.3292, 2.4253)}
