"""「短债远低于政策利率就减仓」（scripts/bill_stress_study.py 登记检验）：利差与 120 个月 z、条件（缺值 = 不满足）、只用没看过的时期的截断、
月末状态 → 东证日闸门的时点（两天之后才用）、闲置资金三条检查、判定 D1〜D5。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bill_stress_study as B                                                # noqa: E402


def _m(start, vals):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="ME"), dtype=float)


def test_constants():
    assert B.CANDS == {"S1": -1.0, "S2": -1.5} and B.FRESH_END == "1981-08-31" and B.GATE_LAG_DAYS == 2
    assert len(B.COUNTRIES) == 10 and "JP" not in B.COUNTRIES and B.JP_BILL == ("INTGSTJPM193N", "IRSTCI01JPM156N")
    assert (B.D_MIN, B.MAX_ON, B.MIN_MONTHS, B.MIN_FOREIGN, B.SEEDS) == (0.02, 50.0, 120, 5, 30)
    assert (B.D5A_UP, B.D5A_TOL, B.D5B_UP, B.D5B_DD, B.D5B_CAGR, B.D5B_SEEDS, B.D5B_SHIFT) == (0.02, 0.01, 0.03, 2.0, 1.0, 30, 252)


def test_spread_z_and_condition():
    days = pd.bdate_range("1990-01-01", "2002-12-31")
    rng = np.random.default_rng(0)
    bill = pd.Series(5.0 + rng.normal(0, 0.05, len(days)), index=days)
    bill[(days >= "2002-06-01")] -= 1.5                                              # 最后半年：短债大跌到政策利率之下
    pol = pd.Series(5.2, index=days)
    s, z = B.spread_z(bill, pol)
    assert abs(s.iloc[0] + 0.2) < 0.05 and z.index[0] == pd.Timestamp("1994-12-31")      # 至少 60 个月才有 z
    c = B.cond(z, -1.0)
    assert c.loc["2002-07-31"] and not c.loc["2001-06-30"] and c.dtype == bool
    zz = _m("2000-01-31", [-2.0, np.nan, -0.5, -1.2])
    assert B.cond(zz, -1.0).tolist() == [True, False, False, True] and B.cond(zz, -1.5).tolist() == [True, False, False, False]
    assert list(B.until(zz, "2000-02-29").index) == [pd.Timestamp("2000-01-31"), pd.Timestamp("2000-02-29")]


def test_gate_days_uses_month_end_state_two_days_later():
    on = pd.Series([False, True, False], index=pd.to_datetime(["2008-08-31", "2008-09-30", "2008-10-31"]))
    days = pd.bdate_range("2008-09-29", "2008-11-05")
    g = B.gate_days(on, days)
    assert not g.loc["2008-09-30"] and not g.loc["2008-10-01"] and g.loc["2008-10-02"]                    # 9 月末的状态从 10-02 起
    assert g.loc["2008-10-31"] and not g.loc["2008-11-03"] and g.loc["2008-11-01":"2008-11-05"].sum() <= 2
    assert not B.gate_days(on, pd.bdate_range("2008-01-01", "2008-01-10")).any()                          # 没有状态 → 不满足


def test_idle_checks_and_decision():
    base = {"E": {"cagr": 10.0, "dd": -20.0, "calmar": 0.50}, "J": {"cagr": 15.0, "dd": -25.0, "calmar": 0.60}}
    good = {"E": {"cagr": 9.5, "dd": -15.0, "calmar": 0.63}, "J": {"cagr": 14.5, "dd": -22.0, "calmar": 0.66}}
    assert B.check_d5b(base, good)["abc"]
    assert not B.check_d5b(base, {**good, "J": {"cagr": 13.0, "dd": -22.0, "calmar": 0.66}})["abc"]       # 年化少 2 pp
    assert not B.check_d5b(base, {**good, "E": {"cagr": 9.5, "dd": -23.0, "calmar": 0.63}})["abc"]        # 回撤深 3 pp
    assert not B.check_d5b(base, {**good, "E": {"cagr": 9.5, "dd": -15.0, "calmar": 0.52}})["abc"]        # Calmar 只 +0.02
    fresh = {"delta": 0.03, "placebo": {"q95": 0.02}}
    g = {"n": 200, "delta": 0.01, "placebo": {"vals": [0.0, 0.0, 0.0]}}
    bad = {"n": 200, "delta": -0.01, "placebo": {"vals": [0.0, 0.0, 0.0]}}
    horiz = {"CA": g, "GB": g, "AU": g, "DE": g, "FR": bad, "XX": {**g, "n": 60}}
    usf, nku = {"on_share": 20.0}, {"delta": 0.001}
    d = B.decide(fresh, horiz, usf, nku, None, True, False)
    assert d["pass14"] and d["verdict"] == "提议（要用户确认）：个股层 JP-T" and d["h"] == {"n_foreign": 5, "share_pos": 80.0, "mean": 0.006, "pooled_q95": 0.0}
    assert B.decide(fresh, horiz, usf, nku, None, False, False)["verdict"] == "不通过"
    assert not B.decide({"delta": 0.03, "placebo": {"q95": 0.04}}, horiz, usf, nku, None, True, True)["D1"]
    assert not B.decide(fresh, {**horiz, "GB": bad, "AU": bad}, usf, nku, None, True, True)["D2"]
    assert not B.decide(fresh, horiz, {"on_share": 60.0}, nku, None, True, True)["D3"]
    assert not B.decide(fresh, horiz, usf, {"delta": -0.001}, None, True, True)["D4"]
    assert not B.decide(fresh, horiz, usf, nku, {"n": 200, "delta": -0.01}, True, True)["D4"]
    assert B.decide(fresh, horiz, usf, nku, {"n": 60, "delta": -0.01}, True, True)["D4"]                     # 日本月数不够 → 只看美国信号 → 日経
