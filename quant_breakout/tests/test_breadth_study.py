"""scripts/breadth_study.py：A50 只用当天为止、成员与缺值、过滤缺值不过滤、按周整体抽签、判定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import breadth_study as S                                                    # noqa: E402


def test_a50_uses_members_and_no_lookahead():
    T = 80
    up = np.linspace(100, 180, T)
    dn = np.linspace(180, 100, T)
    C = np.column_stack([up, dn, up])
    mem = np.ones_like(C, dtype=bool)
    mem[:, 2] = False                                                         # 第三只不是成员
    a = S.a50(C, mem)
    assert np.isnan(a[48]) and a[60] == 0.5                                   # 50 日均线之前缺值；一涨一跌 → 0.5
    C2 = C.copy()
    C2[70:] *= 0.5
    assert np.allclose(S.a50(C2, mem)[:70], a[:70], equal_nan=True)


def test_masks_and_week_lottery():
    d = pd.bdate_range("2026-01-05", periods=10)
    df = pd.DataFrame({"entry": True, "w5v": [1.2, 0.8] * 5}, index=d)
    a = pd.Series([0.65, np.nan, 0.75, 0.5, 0.7, 0.6, 0.59, 0.8, 0.9, 0.1], index=d)
    m = S.masks(df, a)
    assert list(m["B1"]) == [True, True, True, False, True, True, False, True, True, False]
    assert list(m["B2"]) == [False, True, True, False, True, False, False, True, True, False]
    assert list(m["B3"]) == [True, False, True, False, True, False, False, False, True, False]
    fr = {"A.T": df, "B.T": df.copy()}
    out = S.week_lottery_all(fr, 0.5, 7)
    assert (out["A.T"]["entry"] == out["B.T"]["entry"]).all()               # 所有票同一周一起
    wk = d.to_period("W-FRI")
    assert all(out["A.T"]["entry"][wk == w].nunique() == 1 for w in wk.unique())


def _r(e, dd=-30.0, e1=0.1, e2=0.9, j=0.4):
    return {"E": {"calmar": e, "dd": dd}, "E1": {"calmar": e1}, "E2": {"calmar": e2}, "J": {"calmar": j}}


def test_decide():
    RE = {"现行": _r(0.20), "W2": _r(0.28), "B1": _r(0.34), "B2": _r(0.30), "B3": _r(0.24), "B4": _r(0.34, j=0.30)}
    RJ = {k: {"J": {"calmar": v["J"]["calmar"]}} for k, v in RE.items()}
    d = S.decide(RE, RJ, {"B1": 0.30, "B2": 0.31, "B3": 0.2, "B4": 0.2})
    assert d["passed"] == ["B1"] and d["better_than_w2"] == ["B1"] and d["proposal"] == "B1"
    RE["B1"] = _r(0.30)
    d = S.decide(RE, RJ, {"B1": 0.25, "B2": 0.31, "B3": 0.2, "B4": 0.2})
    assert d["passed"] == ["B1"] and d["better_than_w2"] == [] and d["proposal"] == "W2 或 B1"
