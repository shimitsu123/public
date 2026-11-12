"""scripts/vol_explore.py：量的特征只用当天收盘为止的数据；UD50 的手算。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vol_explore as VE                                                     # noqa: E402


def _panel(T=140, seed=0):
    r = np.random.default_rng(seed)
    C = 100 * np.cumprod(1 + r.normal(0, 0.02, (T, 2)), axis=0)
    H, L = C * 1.01, C * 0.99
    return {"O": C.copy(), "H": H, "L": L, "C": C, "V": r.uniform(1e5, 2e5, (T, 2))}


def test_features_do_not_look_ahead():
    P = _panel()
    F = VE.vol_features(P)
    Q = {k: v.copy() for k, v in P.items()}
    for k in Q:
        Q[k][100:] *= 1.5
    G = VE.vol_features(Q)
    for k in F:
        a, b = F[k][:100], G[k][:100]
        assert np.allclose(np.nan_to_num(a, nan=-9), np.nan_to_num(b, nan=-9)), k


def test_ud50_hand_check():
    T = 80
    C = np.array([100.0 + (i % 2) for i in range(T)])[:, None]              # 涨、跌交替
    V = np.where(np.arange(T) % 2 == 1, 2e5, 1e5)[:, None]                  # 涨的日子量 2 倍
    P = {"O": C, "H": C + 1, "L": C - 1, "C": C, "V": V}
    ud = VE.vol_features(P)["UD50"][:, 0]
    assert abs(ud[70] - 2.0) < 1e-9
