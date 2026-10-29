"""scripts/vthrust_study.py：量的特征按日期对齐、缺值不过滤、门槛含等号、判定（E / 随机对照 / J / 比 W2 更好）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vol_explore as VE                                                     # noqa: E402
import vthrust_study as S                                                    # noqa: E402


def test_with_vol_aligns_by_date():
    days = pd.bdate_range("2026-01-05", periods=90)
    r = np.random.default_rng(1)
    C = 100 * np.cumprod(1 + r.normal(0, 0.02, (90, 2)), axis=0)
    P = {"O": C, "H": C * 1.01, "L": C * 0.99, "C": C, "V": r.uniform(1e5, 3e5, (90, 2))}
    fr = {"B.T": pd.DataFrame({"Close": C[30:, 1]}, index=days[30:])}
    out = S.with_vol(fr, P, days, ["A.T", "B.T"])
    F = VE.vol_features(P)
    assert np.allclose(out["B.T"]["vr1"].to_numpy(), F["VR1"][30:, 1], equal_nan=True)
    assert np.allclose(out["B.T"]["vexp"].to_numpy(), F["VEXP"][30:, 1], equal_nan=True)


def test_masks_keep_missing_and_inclusive_cuts():
    df = pd.DataFrame({"w5v": [1.0, 0.9, np.nan, 1.2], "vr1": [3.0, 5.0, 2.9, np.nan], "vexp": [0.99, 1.0, np.nan, 1.5]})
    m = S.masks(df)
    assert list(m["W2"]) == [True, False, True, True]
    assert list(m["V1"]) == [True, False, False, True]
    assert list(m["V2"]) == [False, False, True, True]
    assert list(m["V3"]) == [True, True, False, True] and list(m["V4"]) == [False, True, True, True]


def _r(e, dd=-30.0, e1=0.1, e2=0.9, j=0.4):
    return {"E": {"calmar": e, "dd": dd}, "E1": {"calmar": e1}, "E2": {"calmar": e2}, "J": {"calmar": j}}


def test_decide():
    RE = {"现行": _r(0.20), "W2": _r(0.28), "V1": _r(0.34), "V2": _r(0.30), "V3": _r(0.24), "V4": _r(0.34, j=0.30)}
    RJ = {k: {"J": {"calmar": v["J"]["calmar"]}} for k, v in RE.items()}
    p95 = {"V1": 0.30, "V2": 0.31, "V3": 0.20, "V4": 0.20}
    d = S.decide(RE, RJ, p95)
    assert d["passed"] == ["V1"]                                               # V2 没过随机对照；V3 没到 +0.05；V4 J 更差
    assert d["better_than_w2"] == ["V1"] and d["proposal"] == "V1"
    RE["V1"] = _r(0.31)
    d = S.decide(RE, RJ, p95)
    assert d["passed"] == ["V1"] and d["better_than_w2"] == [] and d["proposal"] == "W2"
