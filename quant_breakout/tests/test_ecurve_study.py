"""scripts/ecurve_study.py：按信号日的 D60 过滤（严格大于门槛、缺值不过滤）；判定借用 breadth_study 的写法。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import breadth_study as B                                                    # noqa: E402
import ecurve_study as S                                                     # noqa: E402


def test_gate_by_date():
    d = pd.bdate_range("2026-01-05", periods=5)
    df = pd.DataFrame({"entry": True}, index=d[1:])
    s = pd.Series([0.5, np.nan, 0.0, -0.5, -1.5], index=d)
    assert list(S.gate(df, s, 0.0)) == [True, False, False, False]
    assert list(S.gate(df, s, -1.0)) == [True, True, True, False]


def test_candidates_and_decide_labels():
    assert set(S.CANDS) == {"Q1", "Q2", "Q3", "Q4"} and S.CANDS["Q4"][:2] == ("宽", -1.0)
    r = lambda e, j=0.4: {"E": {"calmar": e, "dd": -30.0}, "E1": {"calmar": 0.1}, "E2": {"calmar": 0.9}, "J": {"calmar": j}}   # noqa: E731
    RE = {"现行": r(0.20), "W2": r(0.28), "Q1": r(0.40), "Q2": r(0.22), "Q3": r(0.30), "Q4": r(0.35, 0.3)}
    RJ = {k: {"J": {"calmar": v["J"]["calmar"]}} for k, v in RE.items()}
    saved = B.CANDS
    B.CANDS = {k: v[2] for k, v in S.CANDS.items()}
    try:
        d = B.decide(RE, RJ, {"Q1": 0.3, "Q2": 0.3, "Q3": 0.25, "Q4": 0.3})
    finally:
        B.CANDS = saved
    assert d["passed"] == ["Q1", "Q3"] and d["better_than_w2"] == ["Q1"] and d["proposal"] == "Q1"
