"""scripts/split_explore.py：拆股生效日的检测方向（生效日之前 ratio = k、之后 = 1）与超额收益的计算。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import split_explore as S                                                    # noqa: E402


def test_split_events_direction():
    r = np.ones((6, 2))
    r[:3, 0] = 25.0                                                           # 第 3 天生效 1 → 25
    r[:2, 1] = 0.5                                                            # 合并（1 → 0.5）不算
    ev = S.split_events(r)
    assert ev == [(3, 0, 25.0)]


def test_excess():
    C = np.array([[100.0, 100.0, 100.0], [110.0, 100.0, 100.0]])
    mem = np.ones_like(C, dtype=bool)
    assert abs(S.excess(C, mem, 0, 1, 0) - (10.0 - 10.0 / 3)) < 1e-9
