"""scripts/threat_pressure_global.py（「威胁高 + 压力已释放」全球确认）：常数与事先写定的判定、压力分项只用当时能知道的数据、
P_g 需要 ≥ 4 个分项、月末表（还没结束的月份不用、组合公式、事件）、按月份一起抽的自助法可重现。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import threat_pressure_global as G                                           # noqa: E402


def test_constants():
    assert (G.H, G.SPLIT, G.DROP10, G.DROP15) == (60, pd.Timestamp("2011-01-01"), -10.0, -15.0)
    assert G.PCOMP == ["runup", "ma", "calm", "rate", "curve", "credit"] and G.MIN_COMP == 4 and G.MIN_ROWS == 60
    assert (G.G1_MEAN, G.G2_MIN_N, G.ALPHA) == (0.03, 10, 0.05)
    assert (G.BOOT_REPS, G.BOOT_BLOCK, G.BOOT_SEED) == (2000, 24, 20260929)
    dev = [k for k, v in G.MARKETS.items() if v[2] == "dev"]
    em = [k for k, v in G.MARKETS.items() if v[2] == "em"]
    assert len(dev) == 15 and len(em) == 6 and sorted(sum(G.REGIONS.values(), [])) == sorted(dev)


def test_p_scores_needs_four_components():
    idx = pd.date_range("1990-01-31", periods=100, freq="ME")
    raw = pd.DataFrame({k: np.arange(100, dtype=float) for k in ["runup", "ma", "calm"]}, index=idx)
    for k in ["rate", "curve", "credit"]:
        raw[k] = np.nan
    S = G.p_scores(raw)
    assert np.isnan(S["P_g"].iloc[-1]) and S["P_price"].iloc[-1] == 100.0     # 只有 3 个分项 → P_g 不算
    raw["rate"] = 0.0
    assert G.p_scores(raw)["P_g"].iloc[-1] == 100.0                            # 4 个 → 算


def _synthetic(n=2600, seed=1):
    days = pd.bdate_range("1995-01-02", periods=n)
    rng = np.random.default_rng(seed)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n))), index=days)
    a0 = pd.Series(rng.uniform(0, 100, n), index=days)
    macro = lambda dates: pd.DataFrame({"rate": 0.0, "curve": 0.0, "credit": 0.0}, index=dates)   # noqa: E731
    return close, a0, macro


def test_frame_formula_events_and_incomplete_month():
    close, a0, macro = _synthetic()
    X = G.frame(close, a0, macro_fn=macro)
    assert X.index[-1].to_period("M") < close.index[-1].to_period("M")      # 最后一个（没结束的）月份不用
    assert np.allclose(X["C_rel"], (X["A0"] + 100 - X["P_g"]) / 2)
    assert np.allclose(X["P_inv"], 100 - X["P_g"])
    assert ((X["ev10"] == 1) == (X["min"] <= -10)).all() and ((X["ev15"] == 1) == (X["min"] <= -15)).all()
    d = X.index[5]
    assert X.loc[d, "A0"] == a0.loc[d]                                       # 月末当天的 A0
    k = close.index.get_loc(d)
    assert np.isclose(X.loc[d, "min"], (close.iloc[k + 1:k + 61].min() / close.iloc[k] - 1) * 100)


def test_frame_no_lookahead():
    close, a0, macro = _synthetic()
    X = G.frame(close, a0, macro_fn=macro)
    cut = X.index[20]
    c2 = close.copy()
    c2[c2.index > cut] *= 3.0                                                # 改掉以后的价格：以前月末的压力不变
    X2 = G.frame(c2, a0, macro_fn=macro)
    cols = ["A0", "P_g", "P_price"]
    assert np.allclose(X.loc[:cut, cols].to_numpy(), X2.loc[:cut, cols].to_numpy(), equal_nan=True)


def test_evaluate_perfect_score_and_delta():
    idx = pd.date_range("2000-01-31", periods=200, freq="ME")
    ev = (np.arange(200) % 5 == 0).astype(float)
    X = pd.DataFrame({"A0": np.random.default_rng(0).uniform(0, 100, 200), "P_g": 50.0, "P_price": 50.0, "min": np.where(ev > 0, -12.0, -2.0)},
                     index=idx)
    X["C_rel"] = ev * 100
    X["P_inv"] = 50.0
    X["C_relp"] = X["A0"]
    X["ev10"], X["ev15"] = ev, 0.0
    X.iloc[0, X.columns.get_loc("ev15")] = 1.0
    e = G.evaluate(X)
    assert e["ok"] and e["C_rel"]["auc10"] == 1.0 and np.isclose(e["C_rel"]["d10"], 1.0 - e["A0"]["auc10"])
    assert e["C_relp"]["d10"] == 0.0 and e["n"] == 200
    assert G.evaluate(X.iloc[:50])["ok"] is False                           # 月末 < 60 个 → 不算


def _E(delta_sign=1.0, n=240, seed=0):
    """合成的各市场评估：C_rel 比 A0 好（delta_sign=1）或差（−1）。"""
    rng = np.random.default_rng(seed)
    E = {}
    for i, k in enumerate(G.MARKETS):
        idx = pd.date_range("1996-01-31", periods=n, freq="ME")
        y = (rng.uniform(size=n) < 0.2).astype(float)
        a0 = rng.normal(size=n) + 0.3 * y
        c = a0 + delta_sign * 1.0 * y
        X = pd.DataFrame({"A0": a0, "C_rel": c, "P_inv": c, "C_relp": c, "P_g": 50.0, "P_price": 50.0,
                          "min": np.where(y > 0, -12.0, -1.0), "ev10": y, "ev15": y}, index=idx)
        E[k] = G.evaluate(X)
    return E


def test_joint_bootstrap_reproducible_and_judge():
    E = _E(1.0)
    dev = [k for k, v in G.MARKETS.items() if v[2] == "dev"]
    em = [k for k, v in G.MARKETS.items() if v[2] == "em"]
    b1 = G.joint_bootstrap(E, dev, reps=50)
    b2 = G.joint_bootstrap(E, dev, reps=50)
    assert np.array_equal(b1, b2, equal_nan=True) and np.isfinite(b1).all()
    J = G.judge(E, dev, em, b1)
    assert J["pass"] and J["n_pos"] == 15 and J["boot_p"] == 0.0
    E2 = _E(-1.0)
    J2 = G.judge(E2, dev, em, G.joint_bootstrap(E2, dev, reps=50))
    assert not J2["pass"] and not J2["checks"]["G1 地区均衡 ΔAUC ≥ +0.03"]
