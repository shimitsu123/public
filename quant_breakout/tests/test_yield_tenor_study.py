"""上述利率 × 各期限国债收益率（scripts/yield_tenor_study.py 登记检验）：期限表与日美对应、利差与 A / B 条件、上 / 下 / 平、
族内最大值安慰剂（同一相对平移位置 → 取最大 → 95 分位）、一条规则的判定 D1〜D5（含不适用 → 前向记录）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import yield_tenor_study as Y                                                # noqa: E402


def _m(start, vals):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="ME"), dtype=float)


def test_constants_and_tenor_maps():
    assert Y.JP_TENORS == ("1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y", "40Y") and len(Y.US_TENORS) == 10
    assert Y.US_TENORS["3M"] == "DGS3MO" and Y.US_TENORS["30Y"] == "DGS30" and Y.THETAS == (-0.25, -0.50)
    assert set(Y.JP_TO_US) == set(Y.JP_TENORS) and set(Y.JP_TO_US.values()) <= set(Y.US_TENORS)
    assert Y.JP_TO_US["15Y"] == "20Y" and Y.JP_TO_US["40Y"] == "30Y"
    assert (Y.UP_D, Y.HIKE_D, Y.HALF, Y.SHIFT_MIN, Y.MIN_HALF, Y.SPLIT, Y.ACCT0) == (0.5, 0.1, 0.5, 12, 60, "2000-12-31", "2006-09-30")
    assert (Y.D_MIN, Y.MAX_ON, Y.N_FW, Y.SEEDS, Y.HARD_TOL) == (0.02, 50.0, 200, 30, 0.002)
    assert Y.HARD == {("A", "JP", -0.25, "2Y"): -0.008, ("A", "US", -0.25, "2Y"): -0.001}


def test_spread_and_conditions():
    days = pd.bdate_range("2000-01-03", "2001-12-31")
    y = pd.Series(np.where(days < pd.Timestamp("2001-01-01"), 1.0, 3.0), index=days)
    pol = _m("2000-01-31", [1.5] * 24)
    s = Y.spread(y, pol)
    assert abs(s.loc["2000-06-30"] + 0.5) < 1e-9 and abs(s.loc["2001-06-30"] - 1.5) < 1e-9
    hk = pd.Series([False] * 3 + [True] * 3 + [False] * 18, index=pol.index)
    a = Y.cond_a(y, pol, hk, -0.25)
    assert a.loc["2000-02-29"] and not a.loc["2000-05-31"] and a.loc["2000-08-31"] and not a.loc["2001-03-31"]   # 加息中不变
    assert Y.cond_a(y, pol, hk, -0.50).loc["2000-02-29"] and not Y.cond_a(y, pol, hk, -0.60).loc["2000-02-29"]
    b = Y.cond_b(y)
    assert not b.loc["2000-12-31"] and b.loc["2001-01-31"] and b.loc["2001-12-31"]                                # 1.0 → 3.0：+2 pp
    st = Y.st3(_m("2000-01-31", [0.6, -0.6, 0.1, np.nan]), 0.5)
    assert st.tolist() == ["up", "down", "flat", "flat"]


def test_shift_deltas_and_family_max_placebo():
    idx = pd.date_range("1990-01-31", periods=300, freq="ME")
    rng = np.random.default_rng(1)
    on = pd.Series(rng.random(300) < 0.3, index=idx)
    prev = on.shift(1).fillna(False).astype(bool).to_numpy()
    mc = pd.Series(100 * np.cumprod(1 + np.where(prev, -0.03, 0.01)), index=idx)
    us = np.array([0.0, 0.5, 0.99])
    d = Y.shift_deltas(mc, on, us)
    assert len(d) == 3 and all(x is not None for x in d)
    r, pv = Y.prep(mc, on)
    assert len(r) == 299 and pv.iloc[0] == bool(on.iloc[0])
    assert Y.shift_deltas(mc.iloc[:40], on.iloc[:40], us) == [None, None, None]                                  # 不足 60 个月
    rows = [[0.01, 0.05, None], [0.02, 0.00, 0.03], [None, None, None]]
    assert Y.fw_q95(rows) == round(float(np.percentile([0.02, 0.05, 0.03], 95)), 3)
    assert Y.fw_q95([]) is None


def _x(delta, h1=0.01, h2=0.01, on=10.0):
    return {"delta": delta, "on_share": on, "halves": {"h1": {"delta": h1}, "h2": {"delta": h2}}}


def test_decide_rule_paths():
    ok_cross = {"delta": 0.001}
    d = Y.decide_rule(_x(0.03), 0.025, ok_cross, {"D5": True}, True)
    assert d["pass14"] and d["D5"] is True and d["verdict"] == "提议（要用户确认）"
    d2 = Y.decide_rule(_x(0.03), 0.025, ok_cross, None, False)
    assert d2["D5"] is None and d2["verdict"].startswith("提议做前向记录")
    d3 = Y.decide_rule(_x(0.03), 0.025, ok_cross, None, True)                                                   # 触发过但账户没跑 / 不过
    assert d3["D5"] is False and d3["verdict"] == "不通过"
    assert not Y.decide_rule(_x(0.03), 0.035, ok_cross, None, False)["D1"]                                     # 没超过族内门槛
    assert not Y.decide_rule(_x(0.015), 0.0, ok_cross, None, False)["D1"]                                      # 不到 +0.02
    assert not Y.decide_rule(_x(0.03, h2=-0.001), 0.0, ok_cross, None, False)["D2"]
    assert not Y.decide_rule({**_x(0.03), "halves": {"h2": {"delta": 0.05}}}, 0.0, ok_cross, None, False)["D2"]   # 一半不够 60 个月
    assert not Y.decide_rule(_x(0.03, on=55.0), 0.0, ok_cross, None, False)["D3"]
    assert not Y.decide_rule(_x(0.03), 0.0, None, None, False)["D4"] and not Y.decide_rule(_x(0.03), 0.0, {"delta": -0.001}, None, False)["D4"]
