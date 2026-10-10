"""市场风险报告参数 × 方向 研究（scripts/risk_param_direction_study.py 登记检验）：百分位只用过去、东证日对齐用前一日、压力数（百分位版 / 报告阈值版）、
规则映射（R1 / R2 / R3 / R5 与月度更新）、成本与净值、循环平移保持状态个数、判定四条与入选。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import risk_param_direction_study as R                                       # noqa: E402


def test_constants():
    assert R.WIN["E"] == ("2006-10-01", "2016-09-30") and R.WIN["J"][0] == "2017-01-01" and R.FULL[0] == "2006-10-01"
    assert (R.PCT_WIN, R.PCT_MIN, R.STRESS_PCT, R.MOM_LB, R.SAMPLE_STEP) == (2520, 1260, 80.0, 126, 21)
    assert (R.CALMAR_UP, R.DD_TOL, R.CAGR_TOL, R.TIE, R.SEEDS, R.SHIFT_MIN, R.IC_MIN) == (0.03, 2.0, 1.0, 0.02, 30, 12, 0.05)
    assert len(R.STRESS_ITEMS) == 7 and "curve" in R.STRESS_ITEMS and R.RULES == ("R1", "R2", "R3", "R4", "R5")
    assert R.ABS_TH == dict(us10y=5.0, vix=22.0, brent=100.0, brent_chg20=15.0, usdjpy=158.0, jgb10y=3.05)
    assert R.SIDE_COST["C"] == 0.0 and R.SIDE_COST["N"] > R.SIDE_COST["S"] and R.SIDE_COST["J"] > R.SIDE_COST["N"]


def test_pct_rank_no_lookahead_and_align_prev():
    s = pd.Series(np.arange(1.0, 11.0), index=pd.date_range("2020-01-01", periods=10))
    p = R.pct_rank(s, win=5, mn=3)
    assert np.isnan(p.iloc[1]) and p.iloc[2] == 100.0 and p.iloc[-1] == 100.0     # 一直上升 → 每天都是过去里的最高
    s2 = pd.Series([5.0, 1.0, 3.0, 2.0, 4.0], index=pd.date_range("2020-01-01", periods=5))
    p2 = R.pct_rank(s2, win=5, mn=2)
    assert p2.iloc[1] == 50.0 and abs(p2.iloc[4] - 80.0) < 1e-9                    # 4 在 [5,1,3,2,4] 里排第 4 / 5
    days = pd.DatetimeIndex(["2020-01-03", "2020-01-06", "2020-01-07"])
    a = R.align_prev(s2, days)
    assert np.isnan(a.iloc[0]) and a.loc["2020-01-06"] == 3.0 and a.loc["2020-01-07"] == 4.0   # 用 ≤ 前一个东证日 的值


def test_stress_counts():
    idx = pd.date_range("2020-01-01", periods=3)
    lvl = pd.DataFrame({"us10y": [5.1, 4.0, 4.0], "vix": [25.0, 10.0, 10.0], "brent": [101.0, 50.0, 50.0], "brent_chg20": [0.0, 0.0, 16.0],
                        "usdjpy": [160.0, 100.0, 100.0], "jgb10y": [3.1, 1.0, 1.0], "curve": [-0.1, 1.0, 1.0]}, index=idx)
    pct = pd.DataFrame({k: [85.0, 10.0, 10.0] for k in ("us10y", "vix", "hy", "brent_chg20", "usdjpy", "jgb10y")}, index=idx)
    S, Sa = R.stress_count(lvl, pct), R.stress_count_abs(lvl, pct)
    assert S.tolist() == [7, 0, 0] and Sa.tolist() == [7, 0, 1]


def _px(n=400):
    days = pd.bdate_range("2019-01-01", periods=n)
    px = pd.DataFrame({"N": np.linspace(100, 200, n), "S": np.linspace(100, 150, n), "J": np.linspace(100, 90, n), "C": 1.0}, index=days)
    return px


def test_rule_states_and_monthly_update():
    px = _px()
    S = pd.Series(0, index=px.index)
    S[px.index[:130]] = 3                                                    # 前 130 天压力 ≥ 3
    bear = pd.Series(False, index=px.index)
    st1 = R.rule_states("R1", px, S, S, bear)
    ms = R.month_starts(px.index)
    assert st1.loc[ms[0]] == "C" and st1.iloc[-1] == "N" and (st1.loc[ms[0]:ms[1]].iloc[:-1] == "C").all()   # 月内不变
    st2 = R.rule_states("R2", px, S, S, bear)
    assert st2.dropna().iloc[-1] == "N"                                          # 纳指涨最多
    st3 = R.rule_states("R3", px, S, S, bear)
    assert st3.loc[ms[0]] == "C" and st3.iloc[-1] == "N"
    st0 = R.rule_states("R0", px, S, S, bear)
    assert (st0 == "N").all()
    bear2 = pd.Series(True, index=px.index)
    assert (R.rule_states("R0", px, S, S, bear2) == "C").all()
    assert (R.rule_states("HJ", px, S, S, bear) == "J").all()


def test_equity_costs_and_stats():
    px = _px(6)
    st = pd.Series(["C", "N", "N", "S", "S", "S"], index=px.index)
    eq = R.equity(px, st, str(px.index[0].date()), str(px.index[-1].date()))
    r = px.pct_change().fillna(0.0)
    e1 = 1 * (1 + 0 - (R.SIDE_COST["C"] + R.SIDE_COST["N"]) / 100)                 # 第 2 天：前一天是 C（收益 0）、换成 N 扣成本
    assert abs(eq.iloc[1] - e1) < 1e-12
    e2 = e1 * (1 + r["N"].iloc[2])                                               # 第 3 天：拿 N
    assert abs(eq.iloc[2] - e2) < 1e-12
    e3 = e2 * (1 + r["N"].iloc[3] - (R.SIDE_COST["N"] + R.SIDE_COST["S"]) / 100)   # 第 4 天：N 的收益 + 换 S 的成本
    assert abs(eq.iloc[3] - e3) < 1e-12
    c = R.curve_stats(pd.Series([1.0, 1.1, 0.99, 1.2], index=pd.date_range("2020-01-01", periods=4, freq="YS")))
    assert c["dd"] == -10.0 and c["calmar"] is not None


def test_circular_shift_and_placebo_shape():
    lbl = pd.Series(list("NNSCJ"), index=pd.date_range("2020-01-01", periods=5, freq="MS"))
    sh = R.circular_shift(lbl, 2)
    assert sorted(sh.tolist()) == sorted(lbl.tolist()) and sh.tolist() == ["C", "J", "N", "N", "S"]


def test_verdict_and_pick():
    base = {"E": {"cagr": 8.0, "dd": -30.0, "calmar": 0.267}, "J": {"cagr": 12.0, "dd": -25.0, "calmar": 0.48}, "FULL": {"cagr": 10.0}}
    good = {"E": {"cagr": 9.0, "dd": -31.0, "calmar": 0.30}, "J": {"cagr": 12.5, "dd": -24.0, "calmar": 0.52}, "FULL": {"cagr": 9.5},
            "placebo95": {"E": 0.29, "J": 0.50}}
    deep = {**good, "E": {"cagr": 9.0, "dd": -32.5, "calmar": 0.30}}
    lowcagr = {**good, "FULL": {"cagr": 8.9}}
    weak = {**good, "placebo95": {"E": 0.31, "J": 0.50}}
    acct = {"R0": base, "R1": good, "R2": deep, "R3": lowcagr, "R4": weak, "R5": {**good, "J": {"cagr": 12.5, "dd": -24.0, "calmar": 0.50}, "placebo95": {"E": 0.29, "J": 0.40}}}
    assert R.verdict(acct, "R1") == (True, [])
    assert R.verdict(acct, "R2")[1] == ["b:E"] and R.verdict(acct, "R3")[1] == ["c"] and R.verdict(acct, "R4")[1] == ["d:E"]
    assert R.verdict(acct, "R5")[1] == ["a:J"]                                    # 0.50 < 0.48 + 0.03
    win, res = R.pick(acct)
    assert win == "R1" and res["R2"]["pass"] is False
    acct2 = {**acct, "R2": {**good, "E": {"cagr": 9.0, "dd": -31.0, "calmar": 0.31}}}   # 与 R1 相差 < 0.02 → 编号小的
    assert R.pick(acct2)[0] == "R1"
    acct3 = {**acct, "R2": {**good, "E": {"cagr": 9.0, "dd": -31.0, "calmar": 0.33}}}   # 差 ≥ 0.02 → R2
    assert R.pick(acct3)[0] == "R2"
