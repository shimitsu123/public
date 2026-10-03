"""scripts/demand_features.py：信用残高特征（可用日、相隔、下限、拆股）、決算特征（b、since / to_exp、应计 FY 行、最近开示类型）、资格池与候选规则、进场前计数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import demand_features as DF  # noqa: E402

DAYS = pd.bdate_range("2024-01-01", "2024-12-31")
POS = pd.Series(np.arange(len(DAYS)), index=DAYS)


def _margin(dates, L, Ls=None, Ln=None, iss="1"):
    n = len(dates)
    M = pd.DataFrame({"ticker": ["1.T"] * n, "date": pd.to_datetime(dates), "long_vol": L, "long_std": Ls or L, "long_neg": Ln or [0] * n, "iss_type": [iss] * n})
    M["pub"] = M["date"] + pd.Timedelta(days=4)
    M["avail"] = M["pub"] + pd.Timedelta(days=1)
    return M


def test_margin_features_rules():
    fridays = pd.date_range("2024-01-05", periods=10, freq="7D")                   # 申込日每周五
    L = [10000, 11000, 12000, 13000, 14000, 12600, 12000, 11000, 10000, 9000]
    M = _margin(fridays, L, Ls=[x * 0.7 for x in L], Ln=[x * 0.3 for x in L])
    T = pd.DataFrame({"ticker": ["1.T"] * 3, "sig_date": pd.to_datetime(["2024-02-13", "2024-03-12", "2024-01-16"])})
    cumj = np.zeros((len(DAYS), 1), int)
    F = DF.margin_features(T, M, DAYS, POS, cumj, {"1.T": 0})
    # 2024-02-13：avail ≤ d 的最新 = 申込 02-02（avail 02-07）→ L_now 14000？ 02-02 是第 5 条（index 4）→ L_4 = index 0 = 10000，相隔 28 天 → ΔL% = +40%
    r0 = F.iloc[0]
    assert r0["margin_has"] and np.isclose(r0["dL_pct"], 40.0) and r0["L_4"] == 10000 and r0["margin_gap"] == 28 and np.isclose(r0["dL_std_pct"], 40.0)
    # 2024-03-12：最新 = 03-01（index 8，L 10000）→ L_4 = index 4 = 14000 → −28.6%
    r1 = F.iloc[1]
    assert np.isclose(r1["dL_pct"], (10000 - 14000) / 14000 * 100) and r1["iss_type"] == "1"
    # 2024-01-16：最新 = 01-05（index 0）→ 没有第 4 条 → 缺值
    assert np.isnan(F.iloc[2]["dL_pct"]) and F.iloc[2]["margin_has"]
    # 可用日太旧（> 15 个交易日）→ 缺值；拆股 → split
    T2 = pd.DataFrame({"ticker": ["1.T"], "sig_date": pd.to_datetime(["2024-05-30"])})
    assert np.isnan(DF.margin_features(T2, M, DAYS, POS, cumj, {"1.T": 0}).iloc[0]["dL_pct"])
    cumj2 = cumj.copy(); cumj2[POS[pd.Timestamp("2024-02-01")]:, 0] = 1
    assert DF.margin_features(T, M, DAYS, POS, cumj2, {"1.T": 0}).iloc[0]["split"]


def test_fins_features_rules():
    BB = pd.DataFrame({"ticker": ["1.T"] * 4, "date": pd.to_datetime(["2023-05-10", "2023-11-10", "2024-05-10", "2024-08-09"]), "per": ["FY", "2Q", "FY", "1Q"],
                       "b": [np.nan, 0.004, 0.0, 0.003], "tr_chg": [np.nan, 0.4, 0.0, 0.3], "prev_date": [pd.NaT, pd.Timestamp("2023-05-10"), pd.Timestamp("2023-11-10"), pd.Timestamp("2024-05-10")],
                       "NP": [10, 5, 12, 3], "CFO": [20, 6, 30, np.nan], "TA": [200, 200, 200, 200], "ShEq": [100] * 4, "CashEq": [50] * 4, "Eq": [100] * 4, "ROE": [0.1] * 4, "EqAR": [0.5] * 4})
    EV = pd.DataFrame({"ticker": ["1.T"] * 5, "date": pd.to_datetime(["2023-05-10", "2023-11-10", "2024-05-10", "2024-06-20", "2024-08-09"]), "rev": [0, 0, 0, 1, 0]})
    T = pd.DataFrame({"ticker": ["1.T"] * 3, "sig_date": pd.to_datetime(["2024-07-01", "2024-09-02", "2024-05-10"])})
    F = DF.fins_features(T, BB, EV, DAYS, POS, np.zeros((len(DAYS), 1), int), {"1.T": 0})
    r = F.iloc[0]                                                                # 2024-07-01：最近开示 06-20 修正 → since = 7 个交易日、last_rev 1；最近 FS 行 05-10（52 天）→ b 0.0
    assert r["since"] == 7 and r["last_rev"] == 1 and np.isclose(r["b"], 0.0) and r["fs_age"] == 52
    exp_ = min(d for d in (pd.Timestamp("2023-05-10") + pd.Timedelta(days=364), pd.Timestamp("2023-11-10") + pd.Timedelta(days=364), pd.Timestamp("2024-05-10") + pd.Timedelta(days=364)) if d > pd.Timestamp("2024-07-01"))
    assert r["to_exp"] == POS[DAYS[DAYS.searchsorted(exp_)]] - POS[pd.Timestamp("2024-07-01")]    # 所有 < d 的 FS 行 + 364 里第一个 > d（= 2023-11-10 + 364 = 2024-11-08）
    assert np.isclose(r["accrual"], (12 - 30) / 200) and r["cfo"] == 30 and r["acc_age"] == 52     # 最近 FY 行 2024-05-10
    r2 = F.iloc[1]                                                               # 2024-09-02：最近 FS 行 08-09（1Q）→ b 0.3%；应计仍取 FY 05-10
    assert np.isclose(r2["b"], 0.3) and np.isclose(r2["accrual"], (12 - 30) / 200) and r2["last_rev"] == 0
    r3 = F.iloc[2]                                                               # 信号日 = 开示日 → 当天开示不用：最近 FS 行 2023-11-10（182 天 > 140 → b 缺值），应计 FY 2023-05-10（366 天 ≤ 400 → 仍用）
    assert np.isnan(r3["b"]) and np.isclose(r3["accrual"], (10 - 20) / 200) and r3["since"] == POS[pd.Timestamp("2024-05-10")] - POS[DAYS[DAYS.searchsorted(pd.Timestamp("2023-11-10"))]]


def _frame(n=12):
    F = pd.DataFrame({"P": [True] * n, "dL_pct": [-20, -5, -15, np.nan, -12, -30, -11, -50, 5, -10, -10, -10], "L_4": [20000] * 7 + [5000, 20000, 20000, 20000, 20000],
                      "split": [False] * 5 + [True] + [False] * 6, "iss_type": ["1", "2", "1", "1", "3", "1", "2", "1", "1", "1", "2", "1"], "vr1": [2.5, 1.0, 1.5, 2.0, 2.2, 3.0, 2.0, 2.0, 2.0, 1.0, np.nan, 2.0],
                      "b": [0.3, 0.1, np.nan, 0.5, 25.0, 0.25, -0.3, 0.0, 0.26, 0.24, 1.0, 0.3], "split_fs": [False] * 11 + [True],
                      "since": [12, 5, 10, 30, np.nan, 10, 9, 11, 10, 10, 10, 10], "to_exp": [20, 20, 9, 41, 20, 10, 40, 40, np.nan, 20, 20, 20],
                      "accrual": [-0.06, -0.05, -0.04, np.nan, -0.1, -0.2, 0.1, -0.3, -0.05, -0.05, -0.05, -0.05], "cfo": [1, 1, 1, 1, -1, 1, 1, np.nan, 1, 1, 1, 1],
                      "fin": [False] * 9 + [True, False, False]})
    return F


def test_eligible_and_keep_rules():
    F = _frame()
    e1, k1 = DF.eligible(F, "N1"), DF.keep(F, "N1")
    assert list(e1) == [True, True, True, False, False, False, True, False, True, True, True, True]           # 缺值 / IssType 3 / 拆股 / L_4 < 1 万 → 不在资格池
    assert list(k1) == [True, False, True, False, False, False, True, False, False, True, True, True]         # ΔL% ≤ −10（含 −10）
    assert list(DF.keep(F, "N5")) == [True, False, False, False, False, False, True, False, False, False, False, True]   # ∧ vr1 ≥ 2（缺值 → 不在池）
    assert list(DF.eligible(F, "N5"))[10] is False or not DF.eligible(F, "N5")[10]
    assert list(DF.keep(F, "N2")) == [True, False, False, True, False, True, False, False, True, False, True, False]     # 0.25 ≤ b ≤ 20；缺值 / 拆股不在池
    assert list(DF.keep(F, "N3")) == [True, False, False, False, False, True, False, True, False, True, True, True]      # since ≥ 10 ∧ 10 ≤ to_exp ≤ 40
    assert list(DF.keep(F, "N4")) == [True, True, False, False, False, True, False, False, True, False, True, True]      # accrual ≤ −0.05 ∧ CFO > 0 ∧ 非金融
    assert not DF.eligible(F, "N4")[9] and not DF.eligible(F, "N4")[7]


def test_counts_structure():
    F = _frame()
    F["sig_date"] = pd.to_datetime(["2018-03-01"] * 6 + ["2023-03-01"] * 6)
    F["band"] = [0, 1, 2] * 4
    for c in DF.FEATS18:
        if c not in F.columns:
            F[c] = np.arange(len(F), dtype=float)
    F["lturn"] = F["lturn"].astype(float); F["r20"] = F["r20"].astype(float)
    out = DF.counts(F, {"X": ("2017-01-04", "2021-12-30"), "C": ("2022-01-04", "2026-06-25")})
    assert out["X"]["P"] == 6 and out["C"]["P"] == 6 and out["X"]["N1"]["eligible"] == 3 and out["X"]["N1"]["keep"] == 2 and set(out["X"]["N1"]["by_band"]) == {0, 1, 2}
    assert "rank_corr_dL" in out
