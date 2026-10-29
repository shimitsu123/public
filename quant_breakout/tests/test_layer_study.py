"""scripts/layer_study.py：主门槛（2006〜2016 Calmar ≥ 现行 + 0.05、回撤、两半）与次门槛（2017〜2026 不更差）；
scripts/candle_portfolio.bull_only：日本熊市收盘 → 第二天个股新仓倍数 = 0。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import layer_study as L                                                      # noqa: E402


def _r(e, dd, e1, e2, j=0.3):
    f = lambda c, d=-30.0: {"cagr": 10.0, "dd": d, "calmar": c}               # noqa: E731
    return {"E": f(e, dd), "E1": f(e1), "E2": f(e2), "J": f(j)}


def test_gates():
    base = _r(0.30, -30.0, 0.20, 0.40)
    assert L.e_fails(_r(0.35, -31.9, 0.20, 0.40), base) == [] and L.j_fails(_r(0.35, -31.9, 0.2, 0.4, j=0.3), base) == []
    f = L.e_fails(_r(0.34, -32.5, 0.19, 0.41), base)
    assert len(f) == 3 and "Calmar" in f[0] and "回撤" in f[1] and "前半" in f[2]
    assert L.j_fails(_r(0.4, -30.0, 0.3, 0.5, j=0.29), base)


def test_bull_only_blocks_the_day_after_a_bear_close():
    idx = pd.bdate_range("2026-01-05", periods=5)
    em = pd.DataFrame({"A": 1.0, "B": 0.5}, index=idx)
    bear = pd.Series([False, True, True, False, False], index=idx)
    out = CP.bull_only(em, bear)
    assert out["A"].tolist() == [1.0, 1.0, 0.0, 0.0, 1.0] and out["B"].tolist() == [0.5, 0.5, 0.0, 0.0, 0.5]
