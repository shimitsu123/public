"""scripts/chance_pass_study.py 的纯函数：逐笔效果、宽松通过、随机挡保持笔数、Jaccard、共同特征、判定、做法清单。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import chance_pass_study as S  # noqa: E402


def test_ids_and_constants():
    assert len(S.AB_IDS) == 18 and len(S.J_IDS) == 18 and len(set(S.ALL_IDS)) == 36 and "ISS" not in S.ALL_IDS
    assert S.SPLIT == pd.Timestamp("2021-07-01") and S.EARLY_AB == ("Z", "E", "Zx", "W") and S.LATE_AB == ("J", "Jx")
    assert (S.NULL_N, S.PLACEBO_N, S.KEEP_R, S.P_MAX, S.OVERLAP_RATIO, S.FEAT_SD) == (2000, 400, 200, 0.05, 1.5, 0.3) and S.SEED == (20261024, 15)


def test_effect():
    net = np.array([1.0, 2.0, 3.0, -6.0, 100.0])
    cand = np.array([True, True, True, True, False])
    g = np.array([False, False, False, True, True])
    assert np.isclose(S.effect(net, cand, g), 2.0 - 0.0)                          # 候选外的不算
    assert np.isnan(S.effect(net, cand, np.zeros(5, bool))) and np.isnan(S.effect(net, cand, cand))


def test_loose_pass():
    assert S.loose_pass([0.1, 0.2, np.nan]) and not S.loose_pass([0.1, -0.01]) and not S.loose_pass([0.3, np.nan])


def test_shuffle_keeps_count():
    rng = np.random.default_rng(0)
    cand = np.array([True] * 8 + [False] * 2)
    g = np.array([True, True, False, False, False, False, False, False, True, False])
    for _ in range(20):
        r = S.shuffle_gate(g, cand, rng)
        assert (r & cand).sum() == 2 and r[8] and not r[9]


def test_jaccard_and_common():
    assert S.jaccard({1, 2}, {2, 3}) == 1 / 3 and np.isnan(S.jaccard(set(), set()))
    assert np.isclose(S.mean_pair_jaccard([{1, 2}, {2, 3}, {1, 2}]), (1 / 3 + 1 + 1 / 3) / 3)
    c = S.common_feats([{"a": 0.5, "b": 0.4, "c": 0.1}, {"a": 0.4, "b": -0.4, "c": 0.1}])
    assert c == [("a", 0.45)]
    assert S.common_feats([{"a": 1.0}]) == []


def test_verdict():
    assert S.verdict(0.01, True, 1.0, 0) == S.VERDICTS[0]
    assert S.verdict(0.01, False, 1.0, 0) == S.VERDICTS[1]
    assert S.verdict(0.2, True, 1.6, 0) == S.VERDICTS[2] and S.verdict(0.2, False, 1.0, 1) == S.VERDICTS[2]
    assert S.verdict(np.nan, False, np.nan, 0) == S.VERDICTS[3]


def test_stats_split_by_date():
    d = pd.DatetimeIndex(["2020-01-06", "2020-06-01", "2022-01-04", "2023-01-04"])
    SM = {s: {"net": np.array([1.0, -1.0, 1.0, -1.0]), "cand": np.ones(4, bool), "date": d} for s in ("J", "Jx")}
    g = np.array([False, True, False, True])                                   # 前段、后段都挡了亏的
    G = {k: {"era": {"J": g}, "pool": {"Jx": g}} if k in S.J_IDS else {"era": {}, "pool": {}} for k in S.ALL_IDS}
    st = S.stats_of(G, SM)
    v = st["PBH"]
    assert v["loose"] and v["early_pass"] and np.allclose(v["early"], [1.0, 1.0]) and np.isclose(v["late_mean"], 1.0)
    assert not st["MXR"]["loose"] and np.isnan(st["MXR"]["late_mean"])
