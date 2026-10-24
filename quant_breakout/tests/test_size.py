"""scripts/size_common.py / size_explore.py（个股仓位分配）：历史分位只用更早的信号、综合分、三档 / 连续 / 等风险权重（0.64〜1.36）、
K2 加码、walk-forward 模型只用已结束的交易（embargo）、打乱权重只在窗口里、入选规则（要比全部加码好、要超过打乱的 95% 分位）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import size_common as SZ  # noqa: E402
import size_explore as SX  # noqa: E402


def test_expanding_pct_uses_only_earlier_dates():
    d = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-02", "2020-01-03", "2020-01-04"])
    x = np.array([1.0, 2.0, 5.0, 3.0, 0.5])
    p = SZ.expanding_pct(d, x, min_prior=1)
    assert np.isnan(p[0])                                                   # 没有更早的
    assert p[1] == 1.0 and p[2] == 1.0                                      # 同一天的互相不算
    assert abs(p[3] - 2 / 3) < 1e-12                                        # 3 比 1、2 大、比 5 小
    assert p[4] == 0.0
    x2 = x.copy()
    x2[4] = 99.0                                                            # 改掉最后一个 → 之前的分位不变
    assert np.allclose(SZ.expanding_pct(d, x2, min_prior=1)[:4], p[:4], equal_nan=True)
    assert np.isnan(SZ.expanding_pct(d, x, min_prior=3)[2])


def test_expanding_median_and_weights():
    d = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])
    m = SZ.expanding_median(d, np.array([2.0, 4.0, 9.0]), min_prior=2)
    assert np.isnan(m[0]) and np.isnan(m[1]) and m[2] == 3.0
    assert list(SZ.tier_weight(np.array([0.1, 0.5, 0.9, np.nan]))) == [SZ.W_LO, 1.0, SZ.W_HI, 1.0]
    assert np.allclose(SZ.lin_weight(np.array([0.0, 0.5, 1.0, np.nan])), [SZ.W_LO, 1.0, SZ.W_HI, 1.0])
    vw = SZ.vol_weight(np.array([1.0, 4.0, 2.0, np.nan]), np.array([2.0, 2.0, 2.0, 2.0]))
    assert np.allclose(vw, [SZ.W_HI, SZ.W_LO, 1.0, 1.0])                    # 波动小 → 加码（截在 1.36）
    c = SZ.composite(np.array([1.0, np.nan]), np.array([0.0, np.nan]), np.array([0.0, np.nan]))
    assert abs(c[0] - 2 / 3) < 1e-12 and np.isnan(c[1])                     # β 低（分位 0）→ 算好


def test_weights_for_kinds_and_k2():
    S = pd.DataFrame({"vr": [2.5, 2.5, 1.6, np.nan], "beta": [0.5, 0.9, 0.5, 0.5], "w5v": 1.0, "atr_pct": 2.0, "med_atr": 2.0,
                      "pv": [0.9, 0.9, 0.1, np.nan], "pw": [0.9, 0.5, 0.1, np.nan], "pb": [0.1, 0.9, 0.1, np.nan], "mscore": [0.9, 0.2, 0.5, np.nan]})
    assert list(SZ.weights_for("k2", S)) == [SZ.W_HI, 1.0, 1.0, 1.0]
    assert list(SZ.weights_for("all_up", S)) == [SZ.W_HI] * 4
    assert list(SZ.weights_for("rank3", S)) == [SZ.W_HI, 1.0, 1.0, 1.0]     # 综合分 0.9 / 0.5 / 0.37 / 缺
    assert list(SZ.weights_for("model3", S)) == [SZ.W_HI, SZ.W_LO, 1.0, 1.0]
    w = SZ.weights_for("rank3_vol", S)
    assert w.min() >= SZ.W_LO and w.max() <= SZ.W_HI
    assert abs(SZ.BASE_PCT * SZ.W_HI - SZ.CAP_PCT) < 1e-12                  # 最高一档 = 现行的单只上限 34%


def test_model_scores_embargo_and_monotone():
    rng = np.random.default_rng(0)
    n = 400
    tr = pd.DataFrame({"sig_date": pd.date_range("2008-01-01", periods=n, freq="D"), "lvr": rng.normal(size=n), "lw5v": rng.normal(size=n),
                       "beta": rng.normal(size=n)})
    tr["net"] = 2.0 * tr["lvr"] + rng.normal(scale=0.1, size=n)
    sig = pd.DataFrame({"date": pd.to_datetime(["2008-06-01", "2010-06-15", "2010-06-20"]), "lvr": [3.0, 3.0, -3.0], "lw5v": 0.0, "beta": 0.0})
    s = SZ.model_scores(tr, sig)
    assert np.isnan(s[0])                                                   # 那时已结束的训练交易不到 300 笔
    assert s[1] > 0.95 and s[2] < 0.05                                      # 学到「量比高 → 收益高」
    tr2 = tr.copy()
    tr2.loc[tr2["sig_date"] >= pd.Timestamp("2010-03-01"), "net"] = -999.0  # 信号前 90 天以内的交易（未结束）改成怪值 → 不影响
    assert np.allclose(SZ.model_scores(tr2, sig)[1:], s[1:])


def test_shuffle_only_inside_window():
    w = np.array([1.36, 0.64, 1.0, 1.36, 0.64])
    win = np.array([False, True, True, True, False])
    s = SZ.shuffle_weights(w, win, 1)
    assert s[0] == 1.36 and s[4] == 0.64 and sorted(s[1:4]) == sorted(w[1:4])


def test_explore_qualifies_and_pick():
    def c(cal, dd=-30.0, halves=(0.3, 0.3)):
        return {"calmar": cal, "dd": dd, "halves": list(halves)}
    base = {"E": c(0.285), "J": c(0.388)}
    p0 = {"E": c(0.30), "J": c(0.40)}
    q95 = {"E": 0.31, "J": 0.41}
    good = {"E": c(0.33, halves=(0.31, 0.31)), "J": c(0.43, halves=(0.4, 0.29))}
    assert SX.qualifies(good, base, p0, q95) == []
    f = SX.qualifies({"E": c(0.33), "J": c(0.43)}, base, {"E": c(0.34), "J": c(0.40)}, {"E": 0.35, "J": 0.41})
    assert any("全部加码" in x for x in f) and any("打乱" in x for x in f)
    res = {"P0": {"E": c(0.5), "J": c(0.6)}, "P1": good, "P2": {"E": c(0.35, halves=(0.4, 0.4)), "J": c(0.45, halves=(0.4, 0.4))}}
    assert SX.pick(res, base, p0, {"P1": q95, "P2": q95}) == ["P2", "P1"]  # P0 是对照，不入选
