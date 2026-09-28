"""scripts/core_mix_study.py：按比例的核心模拟（进出场成本、熊市现金、每月调仓）、牛熊不偷看、Ken French 日收益解析、分段指标与判定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import core_mix_study as CM  # noqa: E402


def test_simulate_single_asset_all_bull():
    r = np.array([[0.01, 0.0], [0.02, 0.0], [-0.01, 0.0]])
    eq = CM.simulate(r, np.array([1.0, 0.0]), np.ones(3, bool), np.zeros(3, bool), cost=0.001)
    assert np.allclose(eq, (1 - 0.001) * np.cumprod([1.01, 1.02, 0.99]))           # 只有第一次买入扣成本


def test_simulate_bear_goes_to_cash_with_exit_cost():
    r = np.array([[0.10, 0.0], [0.50, 0.0], [0.10, 0.0]])
    bull = np.array([True, False, True])
    eq = CM.simulate(r, np.array([1.0, 0.0]), bull, np.zeros(3, bool), cost=0.01)
    e0 = 0.99 * 1.10
    e1 = e0 * 0.99                                                                   # 熊：清仓扣 1%，当天 +50% 不算
    e2 = e1 * 0.99 * 1.10                                                            # 转牛：再买入扣 1%
    assert np.allclose(eq, [e0, e1, e2])


def test_simulate_monthly_rebalance_restores_weights():
    r = np.array([[0.0, 0.0], [0.10, 0.0], [0.0, 0.0]])
    reb = np.array([True, False, True])
    eq = CM.simulate(r, np.array([0.5, 0.5]), np.ones(3, bool), reb, cost=0.0)
    assert np.allclose(eq, [1.0, 1.05, 1.05])
    eq2 = CM.simulate(r, np.array([0.5, 0.5]), np.ones(3, bool), reb, cost=0.01)
    # 调仓日成交额 = |0.5775 − 0.5247…| + |0.4725 − 0.5247…| 的 1%
    e1 = 0.99 * (0.5 * 1.1 + 0.5)
    h = np.array([0.99 * 0.5 * 1.1, 0.99 * 0.5])
    tr = np.abs(e1 * 0.5 - h).sum()
    assert np.isclose(eq2[2], e1 - tr * 0.01)


def test_bull_prev_uses_previous_close_only():
    st = pd.Series([1, 1, -1, -1, 1], index=pd.bdate_range("2020-01-01", periods=5))
    days = pd.DatetimeIndex(list(st.index) + [pd.Timestamp("2020-01-08")])
    b = CM.bull_prev(st, days)
    # 当天持仓 = 前一天收盘的状态；第一天没有前一天 → 不持有；1-08 用 1-07 的状态（牛）
    assert b.tolist() == [False, True, True, False, False, True]


def test_parse_ff_daily():
    text = "\n".join(["header", "", "  Average Value Weighted Returns -- Daily", ",A,B",
                      "19260701,   0.10,  -99.99", "19260702,   -0.50,   1.00", "", "  Average Equal Weighted Returns -- Daily", ",A,B",
                      "19260701,   9.00,  9.00"])
    df = CM.parse_ff_daily(text, "Average Value Weighted Returns -- Daily")
    assert list(df.columns) == ["A", "B"] and len(df) == 2
    assert np.isclose(df.iloc[0, 0], 0.001) and np.isnan(df.iloc[0, 1]) and np.isclose(df.iloc[1, 1], 0.01)
    f3 = CM.parse_ff_daily("\n".join(["x", "", ",Mkt-RF,RF", "19260701, 0.09, 0.01", ""]), None)
    assert list(f3.columns) == ["Mkt-RF", "RF"] and np.isclose(f3.iloc[0, 0], 0.0009)


def test_seg_and_rolling10():
    idx = pd.bdate_range("1990-01-01", "2012-12-31")
    e = pd.Series(np.exp(np.linspace(0, np.log(2), len(idx))), index=idx)
    s = CM.seg(e, "1990-01-01", "2013-01-01")
    assert s["dd"] == 0.0 and s["calmar"] is None and 3.0 < s["cagr"] < 3.3
    e2 = e * np.exp(np.linspace(0, 0.1, len(idx)))
    rr = CM.rolling10({0: e, 50: e2}, "1990-01-01", "2013-01-01")
    assert rr[0]["n"] == rr[50]["n"] > 0 and rr[50]["beat_base"] == 100.0 and rr[0]["beat_base"] is None


def test_p1_fails():
    b = {"full": {"calmar": 0.30, "dd": -40.0}, **{k: {"calmar": 0.2} for k in CM.P1_BLOCKS}}
    ok = {"full": {"calmar": 0.36, "dd": -41.5}, **{k: {"calmar": 0.25} for k in CM.P1_BLOCKS}}
    bad = {"full": {"calmar": 0.34, "dd": -43.0}, **{k: {"calmar": 0.25} for k in CM.P1_BLOCKS}}
    bad["1948〜1966"] = {"calmar": 0.1}
    res = {0: b, 25: ok, 50: bad}
    assert CM.p1_fails(res, 25) == []
    f = CM.p1_fails(res, 50)
    assert any(x.startswith("C1") for x in f) and any(x.startswith("C2") for x in f) and any("1948〜1966" in x for x in f)


def test_report_pipeline_smoke(monkeypatch):
    """合成数据走一遍：各比例的净值、分段、10 年窗口、判定器准确率与表格输出，不出错。"""
    rng = np.random.default_rng(0)
    days = pd.bdate_range("1928-12-03", "1986-12-31")
    R = pd.DataFrame({"S": rng.normal(0.0003, 0.01, len(days)), "N": rng.normal(0.0004, 0.015, len(days))}, index=days)
    px = pd.Series(np.cumprod(1 + R["S"].to_numpy()), index=days)
    st = pd.Series(np.where(px.rolling(250).mean().to_numpy() < px.to_numpy(), 1, -1), index=days)
    monkeypatch.setattr(CM, "LINES", [])
    t, b = CM.run_weights(R, CM.bull_prev(st, days), CM.month_starts(days))
    E = CM.evaluate_part(t, b, CM.P1, CM.P1_BLOCKS)
    fails = {w: CM.p1_fails(E["timed"], w) for w in CM.WEIGHTS if w}
    CM.table("择时", E["timed"], CM.P1_BLOCKS, fails)
    CM.roll_table("10 年", E["roll10"]["timed"])
    acc = CM.timing_accuracy(st, b[50], *CM.P1)
    assert set(E["timed"]) == set(CM.WEIGHTS) and E["roll10"]["timed"][0]["n"] > 400
    assert acc is None or 0.0 <= acc <= 1.0
    assert any(line.startswith("| W100 |") for line in CM.LINES)
