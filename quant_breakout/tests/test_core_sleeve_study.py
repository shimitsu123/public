"""scripts/core_sleeve_study.py 的纯函数：分散那只的键、只有核心的持仓、美股牛里拿着的比例、候选与邻居。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import core_sleeve_study as S  # noqa: E402

IDX = pd.bdate_range("2020-01-06", periods=4)
BEAR = pd.Series([False, False, True, True], index=IDX)
BJ = pd.Series([False, True, False, True], index=IDX)
ON = pd.Series([True, False, True, False], index=IDX)


def test_sleeve_closed_keys():
    assert S.sleeve_closed(BEAR, BJ, True).tolist() == [False, True, True, True]        # SJP / SJH：美股熊 ∨ 日本熊 → 不拿
    assert S.sleeve_closed(BEAR, None, False).tolist() == [False, False, True, True]    # SSP / SJS：只看美股
    short = BJ.iloc[:3]
    assert S.sleeve_closed(BEAR, short.reindex(IDX).fillna(False), True).tolist() == [False, True, True, True]


def test_core_weights():
    b3 = S.core_weights(BEAR, BJ, ON, 1.0, 0.0, True)                                    # 分散权重 0 = B3
    assert b3["u"].tolist() == [1, 1, 0, 0] and b3["s"].tolist() == [0, 0, 0, 0] and b3["b"].tolist() == [0, 0, 1, 0]
    sjp = S.core_weights(BEAR, BJ, ON, 4.0, 1.0, True)
    assert np.allclose(sjp["u"], [0.8, 1, 0, 0]) and np.allclose(sjp["s"], [0.2, 0, 0, 0]) and np.allclose(sjp["b"], [0, 0, 1, 0])
    ssp = S.core_weights(BEAR, None, ON, 2.0, 1.0, False)
    assert np.allclose(ssp["u"], [2 / 3, 2 / 3, 0, 0]) and np.allclose(ssp["s"], [1 / 3, 1 / 3, 0, 0])
    assert (sjp.sum(axis=1) <= 1 + 1e-12).all() and (ssp.sum(axis=1) <= 1 + 1e-12).all()


def test_held_share():
    closed = pd.Series([False, True, True, False])
    bull = pd.Series([True, True, False, False])
    assert S.held_share(closed, bull, np.ones(4, bool)) == 50.0
    assert S.held_share(closed, bull, np.array([False, False, True, True])) == 0.0       # 没有美股牛的日子 → 0


def test_candidates_and_neighbors_registered():
    assert S.CANDS == {"SJP": ("1321.T", 4.0, 1.0, True), "SJH": ("1321.T", 2.0, 1.0, True), "SSP": ("1655.T", 4.0, 1.0, False)}
    assert S.DESCRIBE == {"SJS": ("1321.T", 4.0, 1.0, False)}
    for cid, (_, wc, ws, _) in S.CANDS.items():
        share = ws / (wc + ws)
        got = sorted(nb / (nc + nb) for nc, nb in S.NEIGHBORS[cid])
        assert np.allclose(got, [share - 0.1, share + 0.1])
    assert S.POSTHOC is True and S.FAMILY == "核心·牛市分散" and S.SKEY == {"1321.T": "SL:JP", "1655.T": "SL:SP"}


def test_mix_over_structure():
    import loop2_r02_bondrefuge as T2
    W = {"kw": {"Z": {"extra_core": {"1545.T": "f1545"}}}, "assets": {"1321.T": "f1321", "1655.T": "f1655"}}
    closed = pd.Series([True], index=IDX[:1])
    ov = S.mix_over(W, {"fb": "fbond"}, "1321.T", 4.0, 1.0, closed)
    c = ov["cfg_over"]
    assert c["core"] == {"1545.T": 4.0, "1321.T": 1.0, T2.BOND_T: 1.0} and c["core_mode"] == "follow"
    assert c["core_index"] == {"1545.T": "US", "1321.T": "SL:JP", T2.BOND_T: T2.BD_KEY}
    assert ov["extra_core"] == {"1545.T": "f1545", T2.BOND_T: "fbond", "1321.T": "f1321"} and list(ov["extra_bear"]) == ["SL:JP"]
    assert T2.BD_KEY not in ov["extra_bear"]                                             # 1482 的键用 B3 原样（merge_over 保留）
    assert W["kw"]["Z"]["extra_core"] == {"1545.T": "f1545"}                              # 不改 W
