"""量化状态层的确认（scripts/regime_confirm.py；2026-09-26 登记）：分组差、聚类自助法、判定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import regime_confirm as RC                                                   # noqa: E402


def _T(n=240, gap=1.0, seed=1):
    rng = np.random.default_rng(seed)
    d = pd.to_datetime("2007-01-05") + pd.to_timedelta(rng.integers(0, 6900, n), unit="D")
    qr = rng.choice([0.0, 0.75, 1.0], n)
    net = rng.normal(0.3, 3.0, n) + np.where(qr == 0.0, gap, 0.0)
    return pd.DataFrame({"sig_date": d, "qr": qr, "net": net, "win": (net > 0).astype(float)})


def test_diff_stats_and_boot():
    T = _T(gap=3.0)
    h = RC.diff_stats(T)
    assert h["d_exp"] > 2 and h["n0"] + h["n1"] < len(T)                      # 0.75 倍不算在两组里
    lo, hi = RC.boot_diff(T)
    assert lo > 0 and hi > lo
    assert RC.diff_stats(T[T["qr"] == 1.0])["d_exp"] is None and RC.boot_diff(T.iloc[:5]) == (None, None)


def test_decide_rules():
    ok = {"d_exp": 0.5, "d_win": 2.0}
    assert RC.decide(ok, ok, 0.1) == []
    f = RC.decide({"d_exp": -0.1, "d_win": 1.0}, {"d_exp": 0.2, "d_win": -1.0}, -0.05)
    assert len(f) == 3
