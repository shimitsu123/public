"""scripts/jq_study.py（2026-09-26 事先登记）：门槛只用之前的年份且只用 2016-10 以后的交易、组合的逐年训练、判定与「最准确的方法」的选法、
真实一手的引擎子类。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import jq_study as JS                                                         # noqa: E402


def _trades(n=900, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2014-01-01", "2025-12-31")
    sig = pd.to_datetime(rng.choice(days, n))
    T = pd.DataFrame({"sig_date": sig, "exit_date": sig + pd.Timedelta(days=15), "sc_g1": rng.normal(0, 1, n),
                      "g1": rng.normal(0, 1, n), "m1": rng.normal(0, 1, n)})
    T["win"] = (T["g1"] + rng.normal(0, 1, n) > 0).astype(float)
    T["net"] = np.where(T["win"] > 0, 2.0, -1.5)
    T["pos"] = np.arange(n)
    return T


def test_single_thresholds_use_prior_years_after_jq_start():
    T = _trades()
    T.loc[T["sig_date"] < pd.Timestamp(JS.JQ0), "sc_g1"] = 1e6                    # 2016-10 以前的值如果被用上，门槛会变得离谱
    rows = pd.DataFrame({"date": pd.to_datetime(["2019-03-01", "2017-05-01"]), "ticker": ["A.T", "B.T"], "sc_g1": [0.1, 0.2]})
    sc = JS.single_thresholds(rows, T, "sc_g1")
    cut = pd.Timestamp("2019-01-01")
    tr = T[(T["sig_date"] >= pd.Timestamp(JS.JQ0)) & (T["sig_date"] < cut) & (T["exit_date"] < cut)]["sc_g1"]
    assert sc.loc[0, "thr"] == pytest.approx(np.quantile(tr, 1 / 3)) and sc.loc[0, "score"] == 0.1
    assert np.isnan(sc.loc[1, "thr"])                                              # 2018 年以前不打分


def test_combo_walk_trains_on_prior_jq_trades_only():
    T = _trades(1200, 1)
    rows = pd.DataFrame({"date": pd.to_datetime(["2020-06-01", "2021-06-01"]), "ticker": ["A.T", "B.T"], "g1": [2.0, -2.0],
                         "m1": [0.0, 0.0]})
    sc = JS.combo_walk(rows, T, ["g1", "m1"])
    assert np.isfinite(sc["score"]).all() and sc.loc[0, "score"] > sc.loc[1, "score"]   # g1 高 → 分数高（学到了埋进去的关系）
    assert np.isfinite(sc["thr"]).all()


def _r(**kw):
    r = {"auc": {"all": 0.57, "lo99": 0.52, "hi99": 0.62}, "seg": {"N225": 0.56, "大中型": 0.55}, "coverage_n225": 0.9,
         "kept": {"H1": {"n": 400, "win": 46.0, "exp": 1.0}, "H2": {"n": 400, "win": 45.0, "exp": 0.9}},
         "all_half": {"H1": {"n": 600, "win": 41.0, "exp": 0.5}, "H2": {"n": 600, "win": 40.0, "exp": 0.4}},
         "s0c2": {"w20_calmar_exact": 0.37, "w5_calmar_exact": 1.2, "w20_dd_exact": -34.0},
         "dauc": {"d": 0.03, "lo": 0.004, "hi": 0.06}}
    r.update(kw)
    return r


def test_decide_and_choose():
    base = {"w20_calmar_exact": 0.363, "w5_calmar_exact": 1.10, "w20_dd_exact": -35.02}
    assert JS.decide(_r(), base)["pass"]
    v = JS.decide(_r(s0c2={"w20_calmar_exact": 0.37, "w5_calmar_exact": 1.0, "w20_dd_exact": -34.0}), base)
    assert not v["pass"] and any("近 5 年" in f for f in v["fails"])               # 近 5 年 Calmar 变差 → 不通过
    R = {"g1": {**_r(), "decision": JS.decide(_r(), base)},
         "J": {**_r(auc={"all": 0.60, "lo99": 0.55, "hi99": 0.65}), "decision": {"pass": True, "fails": []}},
         "A": {**_r(auc={"all": 0.70, "lo99": 0.60, "hi99": 0.75}), "decision": {"pass": False, "fails": ["x"]}}}
    assert JS.choose(R) == "J"                                                     # 通过的里面 AUC 最高；没通过的再高也不选
    assert JS.choose({"A": R["A"]}) is None


def test_real_lot_engine_scales_lot_by_real_price():
    e = JS.RealLotEngine.__new__(JS.RealLotEngine)
    e.lots, e.col, e._rl = np.array([100]), {"7203.T": 0}, {}
    e.gidx = pd.bdate_range("2017-01-02", periods=5)
    JS.RealLotEngine.RATIO = {"7203.T": pd.Series([5.0, 5.0, np.nan, 1.0, 1.0], index=e.gidx)}
    try:
        assert [e._lot_for("7203.T", i) for i in range(5)] == [500, 500, 500, 100, 100]   # 拆股前 1:5 → 真实一手 = 500 复权股
        JS.RealLotEngine.RATIO = {}
        e._rl = {}
        assert e._lot_for("7203.T", 0) == 100
    finally:
        JS.RealLotEngine.RATIO = {}
