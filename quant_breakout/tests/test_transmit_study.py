"""scripts/transmit_study.py：Leontief 的直接 / 间接分解、东証业种的暴露、信号（不偷看）、T4 / T5 的保留规则、传导时间的回归。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import transmit_study as TS  # noqa: E402


def test_io_matrices_indirect_is_higher_order():
    codes = ["06", "21", "20"]
    x = pd.DataFrame([[0, 40, 0], [0, 0, 30], [0, 0, 10]], index=codes, columns=codes, dtype=float)   # 原油 → 石油製品 → 化学
    X = pd.Series([100.0, 100.0, 100.0], index=codes)
    A, N = TS.io_matrices(x, X)
    assert np.isclose(A.loc["06", "21"], 0.4) and np.isclose(A.loc["06", "20"], 0.0)
    # 化学没有直接买原油，但经过石油製品间接用了：0.4 × 0.3 ×（1 / (1 − 0.1)）
    assert np.isclose(N.loc["06", "20"], 0.4 * 0.3 / 0.9) and np.isclose(N.loc["06", "21"], 0.0)
    A2 = A.to_numpy()
    assert np.allclose(N.to_numpy(), A2 @ A2 @ np.linalg.inv(np.eye(3) - A2))


def test_exposures_weighting_and_source_excluded(monkeypatch):
    codes = ["06", "26", "27", "01", "29", "30"]
    A = pd.DataFrame(0.0, index=codes, columns=codes)
    A.loc["26", "29"], A.loc["26", "30"] = 0.2, 0.1
    N = A * 0.5
    X = pd.Series([1.0, 1.0, 1.0, 1.0, 300.0, 100.0], index=codes)
    monkeypatch.setattr(TS.SC, "IO_TSE", {"29": ["機械"], "30": ["機械"], "26": ["鉄鋼"]})
    ex = TS.exposures(A, N, X, ["機械", "鉄鋼"])
    assert np.isclose(ex["direct"]["26"]["機械"], 0.2 * 0.75 + 0.1 * 0.25)          # 按国内生产额加权
    assert np.isclose(ex["indirect"]["26"]["機械"], 0.5 * (0.2 * 0.75 + 0.1 * 0.25))
    assert "鉄鋼" not in ex["direct"]["26"]                                          # 产出业种对自己那一种不算成本


def _ex():
    return {"direct": {"06": {"a": 0.5, "b": 0.0, "c": 0.02}, "26": {}, "27": {}, "01": {}},
            "indirect": {"06": {"a": 0.1, "b": 0.3, "c": 0.0}, "26": {}, "27": {}, "01": {}}}


def test_signals_weighted_and_prop_excludes_self():
    months = pd.date_range("2000-01-31", periods=12, freq="ME")
    Mret = pd.DataFrame({"a": 1.0, "b": 2.0, "c": 3.0}, index=months)
    P = pd.DataFrame({k: 100.0 for k in TS.SHOCKS}, index=pd.date_range("2000-01-01", periods=12, freq="MS"))
    P["06"] = 100 * np.exp(np.arange(12) * 0.01)                                     # 每个月 +1%
    s = TS.signals(Mret, P, _ex(), 1)
    t = months[5]
    assert np.isclose(s["DIR"].loc[t, "a"], 0.5 * 1.0) and np.isclose(s["IND"].loc[t, "b"], 0.3 * 1.0)
    # PROP_b = 间接_b × 直接受影响业种（a 0.5、c 0.02，不含 b 自己）按直接份额加权的过去收益
    assert np.isclose(s["PROP"].loc[t, "b"], 0.3 * (0.5 * 1.0 + 0.02 * 3.0) / 0.52)
    assert np.isclose(s["PROP"].loc[t, "a"], 0.1 * (0.02 * 3.0) / 0.02)             # a 的 PROP 不含 a 自己
    assert s["DIR"].iloc[:2].isna().all().all()                                      # 发布滞后：头两个月没有值


def test_shock_z_uses_only_past_std():
    P = pd.DataFrame({k: 100.0 for k in TS.SHOCKS}, index=pd.date_range("2000-01-01", periods=40, freq="MS"))
    rng = np.random.default_rng(0)
    P["06"] = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 40)))
    months = pd.date_range("2000-01-31", periods=40, freq="ME")
    z = TS.shock_z(P, months)
    d1 = TS.SC.price_change(P, months, 1)["06"]
    k = 35
    sd = d1.iloc[:k].std()                                                          # 到上个月为止
    assert np.isclose(z["06"].iloc[k], d1.iloc[k] / sd)
    assert z["06"].iloc[: TS.Z_MIN_HIST].isna().all()


def test_daily_from_monthly_uses_previous_month_end():
    M = pd.Series([1.0, 2.0, 3.0], index=pd.DatetimeIndex(["2020-01-31", "2020-02-29", "2020-03-31"]))
    days = pd.DatetimeIndex(["2020-02-03", "2020-02-28", "2020-03-02"])
    assert TS.daily_from_monthly(M, days).tolist() == [1.0, 1.0, 2.0]


def test_t4_t5_keep_rules():
    days = pd.bdate_range("2020-02-03", "2020-03-31")
    fa = {"X.T": pd.DataFrame({"Close": 1.0}, index=days), "Y.T": pd.DataFrame({"Close": 1.0}, index=days)}
    s33 = {"X.T": "a", "Y.T": "b"}
    Z = pd.DataFrame({k: 0.0 for k in TS.SHOCKS}, index=pd.DatetimeIndex(["2020-01-31", "2020-02-29"]))
    Z.loc["2020-01-31", "06"] = 2.0                                                  # 1 月末：原油大变动
    k4 = TS.t4_keep(fa, s33, Z, _ex())
    feb = days.month == 2
    assert (~k4["X.T"][feb]).all() and k4["X.T"][~feb].all()                       # a 直接份额 50% → 2 月不做
    assert k4["Y.T"].all()                                                           # b 只有间接 → 照做
    IND3 = pd.DataFrame({"a": [0.1, 0.9], "b": [0.9, 0.1], "c": [0.5, 0.5]}, index=Z.index)
    k5 = TS.t5_keep(fa, s33, IND3)
    assert k5["X.T"][feb].all() and (~k5["X.T"][~feb]).all()                        # 2 月末 a 最高 → 3 月不做
    assert (~k5["Y.T"][feb]).all() and k5["Y.T"][~feb].all()


def test_fm_lag_coefs_finds_delayed_effect_and_effective_rule():
    rng = np.random.default_rng(1)
    months = pd.date_range("2005-01-31", periods=120, freq="ME")
    cols = [f"i{j}" for j in range(20)]
    D = pd.DataFrame(rng.normal(size=(120, 20)), index=months, columns=cols)
    I = pd.DataFrame(rng.normal(size=(120, 20)), index=months, columns=cols)
    R = pd.DataFrame(rng.normal(scale=0.5, size=(120, 20)), index=months, columns=cols)
    R.iloc[3:] -= 1.0 * I.iloc[:-3].to_numpy()                                       # 间接压力 3 个月后才反映
    c = TS.fm_lag_coefs(D, I, R)
    st = TS.t2_stat(c, TS.half_windows(months), months[0])
    assert st["profile"]["ind"][3] < -0.5 and abs(st["profile"]["ind"][1]) < 0.3 and st["ind"]["t"] < -2
    assert TS.ic_effective({"t": 2.5, "ic_H1": 0.1, "ic_H2": 0.05, "hit": 60.0, "placebo_p": 0.01}) == []
    assert len(TS.ic_effective({"t": 1.5, "ic_H1": 0.1, "ic_H2": -0.05, "hit": 50.0, "placebo_p": 0.2})) == 4
