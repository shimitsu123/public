"""VSX 美国长历史核对（scripts/vsx_us_history.py，2026-10-04 登记）：登记的常数、平移的 k、各段的切法、比例全 1 时 Δ = 0、
平移只在窗口内、结论的三档（强 / 弱 / 不支持）、VSX 的比例原样来自第七个循环第 3 轮。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import vsx_us_history as U  # noqa: E402


def _px(seed=9):
    idx = pd.bdate_range("1927-12-30", "1987-06-30")
    r = np.random.default_rng(seed).normal(0.0002, 0.011, len(idx))
    return pd.Series(100 * np.exp(np.cumsum(r)), index=idx)


def test_registered_constants():
    assert (U.SYMBOL, U.WINDOW, U.PLACEBO_N, U.SEED, U.GAP, U.DECADE_NEED, U.PCT_WEAK) == (
        "^GSPC", ("1929-01-02", "1986-12-31"), 400, 20261008, 250, 4, 95.0)
    assert [d[0][:4] for d in U.DECADES] == ["1929", "1940", "1950", "1960", "1970", "1980"] and U.DECADES[-1][1] == "1986-12-31"
    assert "P3.shock_ratio(c)" in inspect.getsource(U.inputs) and "R7.bull(c)" in inspect.getsource(U.inputs)


def test_shift_ks():
    ks = U.shift_ks(14600)
    assert len(ks) == 400 and min(ks) >= 250 and max(ks) <= 14600 - 250
    assert ks[0] == int(np.random.default_rng([20261008, 0, 0]).integers(250, 14600 - 250 + 1))


def test_spans_and_zero_delta():
    c = _px()
    sp = U.spans_of(c)
    days = U.window_days(c.index)
    assert sp[0] == (str(days[0].date()), str(days[-1].date())) and len(sp) == 3 + 6
    assert sp[1][1] < sp[2][0]
    bull = c > c.rolling(250, min_periods=250).mean()
    ones = pd.Series(1.0, index=c.index)
    for k in (None, 3000):
        assert all(v is not None and abs(v) < 1e-12 for v in U.deltas(c, bull, ones, k, sp))
    x = pd.Series(np.where(np.arange(len(c)) % 50 < 10, 0.5, 1.0), index=c.index)
    d0 = U.deltas(c, bull, x, None, sp)
    assert any(abs(v) > 1e-9 for v in d0 if v is not None)


def test_verdict_levels():
    real = [0.05, 0.02, 0.03, 0.01, 0.02, -0.01, 0.03, 0.01, -0.02]          # 6 段里 4 段为正
    assert U.verdict(real, [0.04] * 400)["verdict"] == U.STRONG
    w = U.verdict(real, [0.0] * 381 + [0.06] * 19)                              # 第 95.25 百分位、不到最大
    assert w["verdict"] == U.WEAK and not w["U1"] and w["U2"] and w["U3"]
    assert U.verdict(real, [0.0] * 379 + [0.06] * 21)["verdict"] == U.NONE      # 不到第 95 百分位
    assert U.verdict([0.05, 0.02, -0.01] + real[3:], [0.0] * 400)["verdict"] == U.NONE   # 后一半为负
    assert U.verdict([0.05, 0.02, 0.03, 0.01, -0.02, -0.01, 0.03, -0.01, -0.02], [0.0] * 400)["verdict"] == U.NONE   # 只有 2 段为正
    assert U.verdict(real, [None] + [0.0] * 399)["verdict"] == U.NONE
