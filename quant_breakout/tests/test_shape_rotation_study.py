"""scripts/shape_rotation_study.py 的纯函数：形状分类与月度 IC。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import shape_rotation_study as S  # noqa: E402


def test_classify_shapes():
    flat = np.full(300, 100.0)
    assert S.classify(flat[:100]) is None                                    # 不够 250 根
    assert S.classify(flat) == "S4"                                          # 一直在最高价附近 → 高位整理
    up = np.linspace(50, 100, 300)
    assert S.classify(up) == "S2"
    down = np.linspace(100, 50, 300)
    assert S.classify(down) == "S3"
    rebound = np.concatenate([np.full(240, 100.0), np.linspace(100, 70, 50), np.linspace(70, 78, 10)])
    assert S.classify(rebound) == "S1"
    side = np.concatenate([np.full(200, 130.0), 100 + 5 * np.sin(np.arange(100) / 5)])
    assert S.classify(side) == "S5"


def test_monthly_ic_and_verdict():
    idx = pd.date_range("2017-01-31", periods=6, freq="ME")
    base = np.array([0.03, 0.02, 0.01, -0.01, -0.02, 0.0])
    perf = pd.DataFrame([dict(zip(S.SHAPES, base * (1 + 0.1 * k))) for k in range(6)], index=idx)
    ic = S.monthly_ic(perf)
    assert len(ic) == 5 and np.allclose(ic.to_numpy(), 1.0)
    v = S.verdict(ic.set_axis(pd.date_range("2008-01-31", periods=5, freq="ME")) * 0 + 0.2 + np.array([0, .1, -.1, .05, -.05]),
                  pd.Series([0.2, 0.3, 0.1, 0.25] * 3, index=pd.date_range("2018-01-31", periods=6, freq="ME").append(
                      pd.date_range("2023-01-31", periods=6, freq="ME"))))
    assert v["info"] and v["p"] < 0.10
