"""研究循环第 11 轮 FXE（scripts/loop_r11_fxensemble.py，2026-10-01 登记）：登记值、9 组参数、多数决、循环平移。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_r04_yensurge as Y  # noqa: E402
import loop_r11_fxensemble as X  # noqa: E402


def test_registered_constants():
    assert (X.ROUND, X.IDS, X.WINS, X.THRS, X.MA_N, X.MAJ) == (11, ("FXE",), (5, 10, 20), (-0.02, -0.03, -0.04), 20, 5)
    assert X.OLD == ("1987-01-01", "2000-12-31")
    assert (X.SHIFT_FROM, X.SHIFT_GAP, X.SEED0) == ("2000-01-03", 250, 20261011)
    assert len(X.variants()) == 9 and (10, -0.03) in X.variants()                         # FXH 本身是其中一组


def test_ensemble_is_majority_of_the_nine_state_machines():
    idx = pd.bdate_range("2020-01-01", periods=120)
    rng = np.random.default_rng(3)
    fx = pd.Series(110 * np.exp(np.cumsum(rng.normal(0, 0.012, len(idx)))), index=idx)
    e = X.ensemble_state(fx)
    votes = sum(Y.surge_state(fx, n, t, 20).astype(int) for n, t in X.variants())
    assert e.tolist() == (votes >= 5).tolist()
    assert X.ensemble_state(fx, maj=10).sum() == 0                                         # 9 组不可能有 10 票


def test_shift_placebo_keeps_days_and_is_reproducible():
    idx = pd.bdate_range("1999-06-01", "2026-10-30")
    s = pd.Series((np.arange(len(idx)) % 120) < 12, index=idx)
    a, b = X.shifted(s, 4), X.shifted(s, 4)
    assert a.equals(b) and int(a.sum()) == int(X.shift_domain(s).sum())
    w = X.shift_domain(s)
    ks = [X.shift_k(x, len(w)) for x in range(400)]
    assert min(ks) >= 250 and max(ks) <= len(w) - 250 and len(set(ks)) > 300
