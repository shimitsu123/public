"""scripts/core_bullmix_study.py 的纯函数：1482 的键、只有核心的持仓、稳健与判定、段内回撤。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import core_bullmix_study as S  # noqa: E402

IDX = pd.bdate_range("2020-01-06", periods=4)
BEAR = pd.Series([False, False, True, True], index=IDX)
ON = pd.Series([True, False, True, False], index=IDX)


def test_bond_closed_keys():
    assert S.bond_closed(BEAR, ON, False).tolist() == [False, False, False, True]      # SBS：牛一直拿；熊只在负相关时拿
    assert S.bond_closed(BEAR, ON, True).tolist() == [False, True, False, True]        # SBC / SBH：只看负相关
    assert S.b3_closed(BEAR, ON).tolist() == [True, True, False, True]                 # B3：牛不拿；熊 ∧ 负相关才拿


def test_core_weights():
    b3 = S.core_weights(BEAR, ON, 1.0, 1.0, None)
    assert b3["u"].tolist() == [1, 1, 0, 0] and b3["b"].tolist() == [0, 0, 1, 0]
    sbs = S.core_weights(BEAR, ON, 4.0, 1.0, False)
    assert np.allclose(sbs["u"], [0.8, 0.8, 0, 0]) and np.allclose(sbs["b"], [0.2, 0.2, 1, 0])
    sbc = S.core_weights(BEAR, ON, 2.0, 1.0, True)
    assert np.allclose(sbc["u"], [2 / 3, 1, 0, 0]) and np.allclose(sbc["b"], [1 / 3, 0, 1, 0])
    assert (sbc.sum(axis=1) <= 1 + 1e-12).all()


def test_candidates_and_neighbors_registered():
    assert S.CANDS == {"SBS": (4.0, 1.0, False), "SBC": (4.0, 1.0, True), "SBH": (2.0, 1.0, True)}
    for cid, (wc, wb, _) in S.CANDS.items():
        share = wb / (wc + wb)
        got = sorted(nb / (nc + nb) for nc, nb in S.NEIGHBORS[cid])
        assert np.allclose(got, [share - 0.1, share + 0.1])
    assert S.POSTHOC is True and S.FAMILY.startswith("核心")


def test_verdict_and_robust():
    ok = {"ok": True}
    good, bad = {"S1": True, "S2": True, "S3": True}, {"S1": True, "S2": False, "S3": True}
    assert S.verdict({"ok": False}, []) == "第一关不过"
    assert S.verdict(ok, [good, good]).startswith("第一关与稳健都过")
    assert S.verdict(ok, [good, bad]) == "第一关过、稳健不过"


def test_dd_in_uses_prior_peak():
    eq = pd.Series([100, 120, 110, 90, 130], index=pd.bdate_range("2020-01-06", periods=5), dtype=float)
    assert S.dd_in(eq, eq.index[2], eq.index[3]) == -25.0                             # 前高 120（段之前）→ 90
    assert S.dd_in(eq, eq.index[4], eq.index[4]) == 0.0
