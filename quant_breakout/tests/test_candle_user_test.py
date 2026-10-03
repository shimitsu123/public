"""scripts/candle_user_test.py：按月聚类的差的区间、用户形状的三个定义（基本 / 不限大小 / 严格）与情境。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_user_test as U                                                 # noqa: E402


def test_boot_diff_simple_and_clustered():
    m, d, lo, hi = U.boot_diff(np.ones(10), np.arange(10) % 5, np.zeros(50), np.arange(50) % 5)
    assert (m, d, lo, hi) == (1.0, 1.0, 1.0, 1.0)
    rng = np.random.default_rng(0)
    yb = rng.normal(0, 1, 5000)
    mb = rng.integers(0, 60, 5000)
    m, d, lo, hi = U.boot_diff(yb[:500] + 0.5, mb[:500], yb, mb)
    assert lo < d < hi and lo > 0
    assert np.isnan(U.boot_diff(np.array([]), np.array([]), yb, mb)[0])


def test_shape_variants_on_the_user_candle():
    flat = [[100.0, 101.0, 99.0, 100.0]] * 20
    rows = np.array(flat + [[100.0, 104.0, 99.9, 101.6], [100.0, 101.2, 99.97, 100.48], [100.0, 103.3, 99.95, 101.8]], float)
    P = {"O": rows[:, [0]], "H": rows[:, [1]], "L": rows[:, [2]], "C": rows[:, [3]], "V": np.full((len(rows), 1), 1e5)}
    s, c, g = U.shapes(P)
    assert s["LUB"][20, 0] and s["LUB_any"][20, 0] and s["LUB_strict"][20, 0]
    assert not s["LUB"][21, 0] and s["LUB_any"][21, 0]                           # 小 K 线：只有不限大小的算
    assert s["LUB"][22, 0] and not s["LUB_strict"][22, 0]                        # 上影 1.5 < 实体 1.8 → 不算严格
    assert not c["上涨后（前一天 > 25 日线）"][20, 0] and not c["下跌后（前一天 < 25 日线）"][20, 0]     # 25 日线还没有 → 两个都不算
