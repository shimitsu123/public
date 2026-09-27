"""scripts/hx_select_study.py：保留规则（缺值的处理）、分层抽签（每层笔数与候选相同）、周聚类自助法、判定 G1〜G5、股票池划分、数据检查。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hx_select_study as HX  # noqa: E402


def _T(n=2000, seed=0, lift=0.0):
    rng = np.random.default_rng(seed)
    d = pd.bdate_range("2001-01-02", "2026-06-30")
    T = pd.DataFrame({"ticker": [f"T{rng.integers(0, 50)}" for _ in range(n)], "sig_date": pd.to_datetime(rng.choice(d, n))})
    T["w5v"] = rng.uniform(0.3, 2.5, n)
    T["vr1"] = rng.uniform(1.0, 4.0, n)
    T["beta"] = rng.uniform(0.2, 1.6, n)
    T["dy_rank"] = rng.uniform(0, 1, n)
    T["corr_rank"] = rng.uniform(0, 1, n)
    T["net"] = rng.normal(0.2, 6.0, n)
    T["sector"] = rng.choice(["IT", "Fin", "Util", "HC"], n)
    T["year"] = T["sig_date"].dt.year
    T["week"] = T["sig_date"].dt.to_period("W-FRI").astype(str)
    M = HX.keep_masks(T)
    T.loc[M["U5"], "net"] += lift
    T["win"] = T["net"] > 0
    return T.sort_values("sig_date").reset_index(drop=True)


def test_keep_masks_missing_values():
    T = pd.DataFrame({"w5v": [np.nan, 0.9, 1.0, 1.2, 1.2, 1.1], "vr1": [2.5, 2.5, np.nan, 2.0, 3.0, 1.0],
                      "beta": [0.5, 0.5, 0.5, np.nan, 0.7, 1.2], "dy_rank": [0.9, 0.9, 0.9, 0.9, np.nan, 0.1],
                      "corr_rank": [0.5, 0.2, np.nan, 0.9, 0.3, 0.2]})
    M = HX.keep_masks(T)
    assert M["W2"].tolist() == [True, False, True, True, True, True]           # W2 缺值 → 保留（同现行）
    assert M["U2"].tolist() == [True, False, False, False, True, False]        # 量比 / β 缺值 → 不满足
    assert M["U3"].tolist() == [False, False, False, False, True, True]        # 低相关 ≤ 1/3；缺值 → 不满足
    assert M["U4"].tolist() == [False, False, False, False, True, False]
    # U5：W2 ∧ 四条里至少两条（第 5 行只有低相关一条 → 不保留）
    assert M["U5"].tolist() == [True, False, True, True, True, False]


def test_lottery_keeps_stratum_counts_and_is_seeded():
    T = _T()
    M = HX.keep_masks(T)
    base, keep = M["W2"], M["U5"]
    strata = (T["year"].astype(str) + "|" + T["sector"]).to_numpy()
    a = HX.lottery(T, base, keep, strata, reps=20, seed=1)
    b = HX.lottery(T, base, keep, strata, reps=20, seed=1)
    assert np.allclose(a["mean"], b["mean"]) and np.isfinite(a["mean"]).all()
    # 候选 = 基准本身 → 每次抽的就是全部，均值等于基准
    c = HX.lottery(T, base, base, strata, reps=5, seed=2)
    assert np.allclose(c["mean"], T["net"].to_numpy()[base].mean())


def test_boot_and_gate():
    T0 = _T(n=6000, lift=0.0, seed=3)
    M0 = HX.keep_masks(T0)
    assert abs(HX.boot_diff_lo(T0, M0["W2"], M0["W2"], reps=50) or 0.0) < 1e-12   # 候选 = 基准 → 差 0
    g0 = HX.gate(T0, M0, "U5")
    assert not g0["pass"]                                                     # 没有真实效果 → 不成立
    T1 = _T(n=6000, lift=4.0, seed=3)                                          # U5 每笔 +4 pp、胜率也更高
    g1 = HX.gate(T1, HX.keep_masks(T1), "U5")
    assert g1["all"]["cand"]["mean"] > g1["all"]["base"]["mean"] + 1
    assert not [f for f in g1["fails"] if f.startswith(("G1", "G2", "G3", "G4"))], g1["fails"]


def test_gate_min_n():
    T = _T(n=600, lift=5.0, seed=4)
    g = HX.gate(T, HX.keep_masks(T), "U2")
    assert any(f.startswith("G5") for f in g["fails"])                       # 笔数不够 → 不成立


def test_pools_split():
    from qbreak.universes import US_BROAD
    x, _ = HX.pool_members("sp500x")
    s, _ = HX.pool_members("sp500seen")
    assert x and s and not (set(x) & set(s)) and set(s) <= set(US_BROAD)
    assert all(v >= HX.WIN0 for v in x.values())
    a, _ = HX.pool_members("sp500")
    assert set(x) | set(s) == set(a)


def test_bad_move_flags():
    d = pd.bdate_range("2010-01-01", periods=60)
    c = pd.Series(100.0, index=d)
    c.iloc[30:] = 250.0                                                       # 第 30 天 +150%（疑似未复权）
    df = pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 1e6})
    D = {"data": {"A": df}}
    T = pd.DataFrame({"ticker": ["A", "A"], "sig_date": [d[10], d[26]], "exit_date": [d[20], d[40]]})
    assert HX.bad_move_flags(T, D).tolist() == [False, True]


def test_corr60_frame_matches_definition():
    d = pd.bdate_range("2015-01-01", periods=200)
    rng = np.random.default_rng(7)
    m = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 200))), index=d)
    x = pd.Series(50 * np.exp(np.cumsum(0.5 * np.log(m).diff().fillna(0) + rng.normal(0, 0.01, 200))), index=d)
    C = pd.DataFrame({"X": x})
    cr = HX.corr60_frame(C, m)["X"]
    i = 150
    r = x.pct_change().iloc[i - 59:i + 1].to_numpy()
    mr = m.pct_change().iloc[i - 59:i + 1].to_numpy()
    assert np.isclose(cr.iloc[i], np.corrcoef(r, mr)[0, 1])
    assert cr.iloc[:40].isna().all()                                          # 不到 40 对 → 缺值
