"""第十一个研究循环第 2 轮（scripts/loop11_r02_sector.py）：方差比、业种三类、学参数的规则复用第 1 轮、常量。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop11_r01_cycle as R1  # noqa: E402
import loop11_r02_sector as R  # noqa: E402


def test_round_constants():
    assert R.ROUND == 2 and R.IDS == ("SCY", "SZK", "VRK") and all(not v for v in R.POSTHOC.values())
    assert R.OPTIONS is R1.OPTIONS and R.TIGHT == {"k": 2.0, "mh": 60} and R.WIDE == {"k": 4.0, "mh": 90}
    assert R.MENUS["SZK"] == {"low": R.WIDE, "high": R.TIGHT} and R.MENUS["VRK"] == {"low": R.TIGHT, "high": R.WIDE}
    allg = [x for g in R.GROUPS.values() for x in g]
    assert len(allg) == len(set(allg)) == 33                                   # 33 业种各归一类


def test_variance_ratio():
    rng = np.random.default_rng(1)
    rw = np.exp(np.cumsum(rng.normal(0, 0.01, 2000)))                          # 随机游走 → VR ≈ 1
    assert 0.7 < R.variance_ratio(rw, 1999, n=1500) < 1.3
    zz = np.exp(np.cumsum(np.tile([0.01, -0.01], 300)))                        # 来回 → VR 很小
    assert R.variance_ratio(zz, 599, n=500) < 0.2
    tr = np.exp(np.cumsum(0.002 + np.repeat(rng.normal(0, 0.01, 60), 10)))    # 收益成块（正自相关）→ VR > 1
    assert R.variance_ratio(tr, 599, n=500) > 2.0
    assert np.isnan(R.variance_ratio(rw, 100, n=250))


def test_sector_groups():
    s33 = {"7203": "輸送用機器", "2914": "食料品", "8306": "銀行業", "9999": "謎"}
    lab = R.sector_labels(["7203.T", "2914.T", "8306.T", "9999.T", "1111.T"], s33)
    assert list(lab) == ["cyc", "def", "fin", "na", "na"]


def test_learn_map_uses_round1_rule():
    T = pd.DataFrame({"label": ["cyc"] * 25 + ["def"] * 25, "net_tight": [0.5] * 50,
                      "net_base": [0.4] * 20 + [-0.1] * 5 + [0.4] * 25, "net_wide": [-1.0] * 50})
    mp = R.learn_map(T)
    assert mp == {"cyc": "tight", "def": "base", "fin": "base"}
    assert R.apply_map(["cyc", "na", "fin"], mp) == ["tight", "base", "base"]


def test_registered_cuts():
    assert R.CUTS == {"SZK": (9.1557, 9.5445), "VRK": (0.7111, 0.8765)}
