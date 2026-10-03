"""选股第三轮（scripts/combo3_common.py，2026-10-01 登记）：登记值、随机切法（按年、信号数尽量各半、可复现）、袋装投票、稳定选择、判定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import combo3_common as C3  # noqa: E402
import combo_all_common as CA  # noqa: E402

from test_combo2_study import _panel  # noqa: E402


def test_registered_constants():
    assert (C3.B_SPLITS, C3.VOTE, C3.PI_MIN, C3.SEED) == (50, 0.5, 0.6, 20261004)
    assert (CA.MIN_RHO_C, CA.CELL_MIN_N, CA.SKIP_Q, CA.C_VIX) == (0.05, 60, 1 / 3, 20.0)     # C 的其余做法不动


def test_year_splits_balanced_by_count_and_reproducible():
    X = _panel(900)
    sp = C3.year_splits(X["date"], 20, seed=1)
    sp2 = C3.year_splits(X["date"], 20, seed=1)
    assert len(sp) == 20 and all((a == b).all() for a, b in zip(sp, sp2))
    yrs = pd.to_datetime(X["date"]).dt.year.to_numpy()
    per_year = pd.Series(1, index=yrs).groupby(level=0).sum()
    for g in sp:
        assert set(np.unique(g)) <= {0, 1}
        for y in np.unique(yrs):                                              # 同一年整年在同一组
            assert len(set(g[yrs == y])) == 1
        assert abs(int(g.sum()) - int((1 - g).sum())) <= per_year.max()     # 信号数尽量各半
    assert len({tuple(g) for g in sp}) > 1                                  # 不是每次都一样
    assert all(len(g) == 0 for g in C3.year_splits(X["date"].iloc[0:0], 3))


def test_bag_votes_and_keeps_when_no_rule():
    X = _panel(1200, seed=3)
    rules = C3.fit_bag(X, n=10, seed=2)
    assert len(rules) == 10 and C3.bag_active(rules) == 1.0
    Y = _panel(300, seed=4, start="2020-01-06")
    k = C3.apply_bag(rules, Y)
    skip = np.mean([~CA.apply_c(r, Y) for r in rules], axis=0)
    assert (k == ~(skip >= 0.5)).all()
    assert Y.loc[k, "net"].mean() > Y.loc[~k, "net"].mean()                 # 合成数据：学到的方向有用
    assert C3.apply_bag([], Y).all() and C3.bag_active([]) == 0.0
    few = C3.fit_bag(X.iloc[:80], n=5)                                      # 每组不到 60 笔 → 每份都学不出 → 全部保留
    assert C3.bag_active(few) == 0.0 and C3.apply_bag(few, Y).all()


def test_stability_selects_the_real_signal_and_rule_matches_c_format():
    X = _panel(1500, seed=5)
    prof = C3.stability(X, n=20, seed=3)
    assert prof[2]["vexp"][0] >= 0.9 and prof[2]["vexp"][1] == 1                # 真的信号几乎每次都入选
    noise = [p for f, (p, s) in prof[2].items() if f != "vexp"]
    assert not noise or max(noise) < 0.6                                       # 噪声特征入选占比低
    assert prof[0] == {} and prof[1] == {} and prof[3] == {}                   # 别的格子没有样本
    rules = C3.fit_stable(X, n=20, seed=3)
    assert rules[2] is not None and rules[2]["sel"] == {"vexp": 1} and rules[0] is None
    k = CA.apply_c(rules, X)                                                   # 和 C 同样形式，CA.apply_c 直接能用
    assert X.loc[k, "net"].mean() > X.loc[~k, "net"].mean()
    assert "vexp+" in C3.profile_text(prof) and C3.profile_text({}) == "—"
    assert all(v is None for v in C3.fit_stable(X.iloc[:100], n=5).values())


def test_verdict():
    assert C3.verdict(True, True) == "通过" and C3.verdict(True, False) == "方向一致"
    assert C3.verdict(False, True) == "方向一致" and C3.verdict(False, False) == "不通过"
