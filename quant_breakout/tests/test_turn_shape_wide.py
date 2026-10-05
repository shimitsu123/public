"""scripts/turn_shape_wide.py（2026-10-05 登记）：登记值、三个样本的划分（U0 = 原研究的 sample_mask）、分组 / 分档、组内统计的方向判定、复现比对。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import turn_shape_study as S  # noqa: E402
import turn_shape_wide as W  # noqa: E402


def test_registered_constants():
    assert W.HIST_WIDE == 60 and W.VA_BUCKETS == (1e6, 1e7) and W.BIN_RULE == ((50, 10), (20, 5)) and W.INFO_PP == 1.0
    assert list(W.GROUPS) == ["A", "B", "C", "D", "E", "F"] and list(W.BUCKETS) == ["L1", "L2", "L3"] and list(W.UNIVERSES) == ["U0", "U1", "U2"]
    assert [W.n_bins(v) for v in (80, 50, 49.9, 20, 19.9, 0)] == [10, 10, 5, 5, 0, 0]


def _panel(T=420, N=4, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2017-06-01", periods=T)
    C = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, size=(T, N)), axis=0))
    VA = np.full((T, N), 5e7)
    VA[:, 1] = 2e6                                                             # 成交少
    cat = np.ones((T, N), np.int8)
    cat[:, 2] = 4                                                              # ETF
    C[:300, 3] = np.nan                                                        # 新上市（第 300 天起才有价格）
    return days, {"C": C, "VA": VA, "cat": cat}


def test_panel_masks_u0_is_original_rule_and_union_covers():
    days, A = _panel()
    pm = W.panel_masks(A, days)
    ref = S.sample_mask({**A, "listed": A["cat"] == 1}, days)
    assert np.array_equal(pm["u0"], ref)
    assert not (pm["u0"] & ~pm["union"]).any()                                # U0 ⊂ 样本表
    on = W.day_grid(days)
    k = np.where(on)[0]
    assert pm["union"][k, 1].any() and not pm["u0"][k, 1].any()               # 成交少：只在放宽版里
    assert pm["union"][k, 2].any() and not pm["u0"][k, 2].any()               # ETF：只在放宽版里
    first3 = np.where(pm["union"][:, 3])[0]
    assert len(first3) and first3[0] >= 300 + W.HIST_WIDE - 1                   # 新股满 60 根才进


def test_groups_and_buckets():
    x = pd.DataFrame({"cat": [1, 1, 1, 4, 5, 3, 2, 6, 7, 1],
                      "hist": [300, 300, 100, 500, 500, 500, 500, 500, 500, 300],
                      "va20": [2e7, 5e6, 2e7, 1e9, 1e3, 1e8, 1e3, 1e3, 1e3, np.nan],
                      "u0": [True, False, False, False, False, False, False, False, False, False]})
    assert W.groups_of(x).tolist() == ["A", "B", "C", "D", "D", "E", "F", "F", "F", "B"]
    assert W.buckets_of(x).tolist() == ["L3", "L2", "L3", "L3", "L1", "L3", "L1", "L1", "L1", "L1"]


def test_cell_stats_direction_and_group_relative_excess():
    rng = np.random.default_rng(1)
    days = np.repeat(pd.bdate_range("2022-01-04", periods=60).to_numpy(), 100)
    n = len(days)
    sc = rng.normal(size=n)
    r20 = 0.004 * sc + rng.normal(0, 0.01, n) + 0.05                          # 分数越高之后越好；整组平均 +5%（组内超额要去掉）
    D = pd.DataFrame({"date": pd.to_datetime(days), "R20": r20, "RS": (sc > 1.5).astype(float), "FS": (sc < -1.5).astype(float),
                      "M": 0.2, "U": 0.0, "D": 0.0, "lo10": sc < 0, "hi10": sc > 0})
    D["month"] = D["date"].dt.to_period("M").astype(str)
    out = W.cell_stats(D, {"rise": sc, "fall": sc}, np.ones(n, bool))
    assert out["bins"] == 10 and out["per_day"] == 100.0
    r, f = out["rise"], out["fall"]
    assert r["info"] and r["spread_pp"] >= 1.0 and r["top_pp"] > 0 and abs(r["top_pp"] + r["bottom_pp"]) < 0.3   # 减了本组同一天平均
    assert not f["info"] and f["spread_pp"] < 0                               # 下跌模型要「最像的跑输」，这里方向相反
    assert r["auc"] > 0.9 and W.cell_stats(D, {"rise": sc, "fall": sc}, np.zeros(n, bool)) == {"rows": 0}


def test_reproduce_compare():
    dec = {d: {"R20x": 0.1 * d} for d in range(10)}
    mine = {"counts": {"rows": 10, "X": {"rows": 4}, "C": {"rows": 6}}, "models": {mk: {"auc": 0.9, "deciles": dec} for mk in S.MODELS}}
    orig = {"counts": {"rows": 10, "X": {"rows": 4}, "C": {"rows": 6}}, "models": {mk: {"auc": 0.9, "deciles": {str(d): v for d, v in dec.items()}} for mk in S.MODELS}}
    assert W.reproduce(mine, orig)["same"] is True
    orig["models"]["rise"]["auc"] = 0.8
    assert W.reproduce(mine, orig)["same"] is False and W.reproduce(mine, None) == {"available": False}


def test_fit_models_imputation_scores_all_confirm_rows():
    rng = np.random.default_rng(2)
    d1 = pd.bdate_range("2019-01-07", periods=40, freq="5B")
    d2 = pd.bdate_range("2022-01-04", periods=30, freq="5B")
    dates = np.repeat(np.r_[d1.to_numpy(), d2.to_numpy()], 120)
    n = len(dates)
    x = pd.DataFrame(rng.normal(size=(n, len(S.FEATS))), columns=S.FEATS)
    x["date"] = pd.to_datetime(dates)
    z = 1.2 * x["d_r5"].to_numpy()
    x["RS"] = (rng.random(n) < 1 / (1 + np.exp(-(-3 - z)))).astype(float)
    x["FS"] = (rng.random(n) < 1 / (1 + np.exp(-(-3 + z)))).astype(float)
    x["lmc"] = np.where(rng.random(n) < 0.1, np.nan, x["lmc"])                 # 10% 没有时价总额（像 ETF）
    x.loc[x.index % 7 == 0, "m_r12"] = np.nan                                  # 新股：月线特征缺
    for c in ("R20x", "R40x"):
        x[c] = rng.normal(0, 0.05, n)
    x["U"] = x["D"] = 0.0
    x["month"] = x["date"].dt.to_period("M").astype(str)
    x["mc_rank"] = x.groupby("date")["lmc"].rank(ascending=False, method="first")
    x["n225"] = False
    x["lo10"], x["hi10"] = rng.random(n) < 0.2, rng.random(n) < 0.2
    nC = int((x["date"] >= pd.Timestamp(S.C_START)).sum())
    out, sc, Dc = W.fit_models(x, impute=True)
    assert out["rise"]["n_test"] == nC == len(Dc) == len(sc["rise"]) and np.isfinite(sc["rise"]).all()
    assert out["rise"]["n_test_complete"] < nC and "complete_only" in out["rise"] and out["rise"]["auc"] > 0.6
    out0, sc0, Dc0 = W.fit_models(x, impute=False)
    compC = ((x["date"] >= pd.Timestamp(S.C_START)) & x[S.FEATS].notna().all(axis=1)).sum()
    assert out0["rise"]["n_test"] == compC and "complete_only" not in out0["rise"]
    assert out0["rise"]["n_train"] < out["rise"]["n_train"]                   # 补了 log 时价总额的行也能学（只补 lmc）


def test_labels_ffill_equals_original_without_gaps_and_fills_gaps():
    rng = np.random.default_rng(4)
    T, N = 260, 3
    C = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, size=(T, N)), axis=0))
    O = C * np.exp(rng.normal(0, 0.005, size=(T, N)))
    a, b = S.labels({"O": O, "C": C}), W.labels_ffill({"O": O, "C": C})
    for k in W.LABEL_COLS:
        assert np.array_equal(np.nan_to_num(np.asarray(a[k], float), nan=-9), np.nan_to_num(np.asarray(b[k], float), nan=-9)), k   # 每天有成交 → 完全相同
    C2, O2 = C.copy(), O.copy()
    C2[100::7, 1] = np.nan                                                     # 每 7 天有一天没有成交
    O2[100::7, 1] = np.nan
    a2, b2 = S.labels({"O": O2, "C": C2}), W.labels_ffill({"O": O2, "C": C2})
    t = 200
    assert np.isfinite(C2[t, 1]) and np.isnan(a2["M"][t, 1]) and np.isfinite(b2["M"][t, 1])   # 原定义算不出，向前填补口径算得出
    assert np.allclose(a2["M"][:, 0], b2["M"][:, 0], equal_nan=True)            # 别的票不受影响


def test_universe_flags_use_ffill_m():
    T = pd.DataFrame({"cat": [1, 1, 4, 4, 1], "u0": [True, False, False, False, True],
                      "M": [0.2, np.nan, np.nan, 0.1, np.nan], "M_f": [0.2, 0.15, np.nan, 0.1, 0.3]})
    F = W.universe_flags(T)
    assert F["U0"].tolist() == [True, False, False, False, True]               # U0 = 原研究（不看 M）
    assert F["U1"].tolist() == [True, True, False, False, True] and F["U2"].tolist() == [True, True, False, True, True]
