"""K4 横向研究（scripts/k4_horizontal_study.py 登记检验）：θ 的取法（发现期 30% 分位、月数不够 → 无）、月末收盘与月度规则（上月末满足 → 当月 ×0.5）、
Calmar、循环平移安慰剂保持满足月数、指数级 / 账户级判定与「五条全过才启用」。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import k4_horizontal_study as K                                              # noqa: E402


def test_constants_and_markets():
    assert (K.W, K.LAG, K.Q, K.HALF, K.THETA_JP, K.THETA_TOL) == (3, 2, 0.30, 0.5, -4.626, 0.15)
    assert K.DISC == ("2006-10-31", "2015-12-31") and K.SPLIT == "2016-09-30" and (K.MIN_DISC, K.MIN_MONTHS, K.SEEDS, K.SHIFT_MIN) == (60, 120, 30, 12)
    assert (K.US_UP, K.TOL, K.DD_TOL) == (0.03, 0.01, 2.0) and abs(K.SHARE_2_3 - 2 / 3) < 1e-12
    assert len(K.MARKETS) == 25 and K.MARKETS["JP"][0] == "^N225" and K.MARKETS["US"][0] == "^GSPC" and "KR" in K.MARKETS and "CN" in K.MARKETS


def test_theta_quantile_and_min_months():
    m = pd.date_range("2004-01-31", "2020-12-31", freq="ME")
    sig = pd.Series(np.linspace(-10, 10, len(m)), index=m)
    th = K.theta_of(sig)
    d = sig[(sig.index >= pd.Timestamp("2006-10-31")) & (sig.index <= pd.Timestamp("2015-12-31"))]
    assert abs(th - round(float(d.quantile(0.3)), 3)) < 1e-9
    assert K.theta_of(sig.iloc[:40]) is None                                              # 发现期有效月不够


def test_month_close_rule_and_calmar():
    days = pd.bdate_range("2006-01-02", "2008-12-31")
    close = pd.Series(100.0 * np.cumprod(1 + np.where(np.arange(len(days)) % 2 == 0, 0.001, -0.0005)), index=days)
    months = pd.date_range("2005-12-31", "2008-12-31", freq="ME")
    mc = K.month_close(close, months)
    assert np.isnan(mc.iloc[0]) and mc.iloc[-1] == close.iloc[-1] and mc.loc["2006-06-30"] == close[close.index <= "2006-06-30"].iloc[-1]
    r = pd.Series([0.10, -0.20, 0.10, 0.05, -0.10, 0.02], index=pd.date_range("2007-01-31", periods=6, freq="ME"))
    st = pd.Series([False, True, True, False, False, True], index=r.index)                 # t−1 满足 → t 月 ×0.5
    R = K.rule_returns(r, st)
    assert R.tolist() == [0.10, -0.20, 0.05, 0.025, -0.10, 0.02]
    c = K.calmar_m(pd.Series([0.01] * 12, index=pd.date_range("2007-01-31", periods=12, freq="ME")))
    assert c["dd"] == 0.0 and c["calmar"] is None and abs(c["cagr"] - 12.68) < 0.01
    c2 = K.calmar_m(pd.Series([0.05, -0.10, 0.05] * 6, index=pd.date_range("2007-01-31", periods=18, freq="ME")))
    assert c2["dd"] < 0 and c2["calmar"] is not None
    sh = K.shifted(st, 2)
    assert sh.sum() == st.sum() and sh.tolist() == [False, True, False, True, True, False]


def test_market_eval_placebo_and_index_decision():
    rng = np.random.default_rng(3)
    days = pd.bdate_range("2004-01-01", "2026-08-31")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, len(days)))), index=days)
    months = K.month_ends(pd.Timestamp("2026-08-31"))
    sig = pd.Series(rng.normal(0, 5, len(months)), index=months)
    th = K.theta_of(sig)
    x = K.market_eval(close, sig, th, months, seeds=5, rng_seed=1)
    assert x["n"] >= 230 and x["hold"]["calmar"] is not None and len(x["placebo"]["vals"]) == 5 and 0 < x["on_share"] < 100
    assert set(x["halves"]) == {"h1", "h2"} and x["delta"] == round(x["rule"]["calmar"] - x["hold"]["calmar"], 3)
    good = {"delta": 0.05, "diff": -0.5, "n": 200, "placebo": {"vals": [0.0] * 5}}
    bad = {"delta": -0.05, "diff": 0.5, "n": 200, "placebo": {"vals": [0.0] * 5}}
    RES = {"JP": dict(good), "US": dict(good), "DE": dict(good), "GB": dict(bad), "XX": {**good, "n": 50}}
    d = K.decide_index(RES)
    assert d["F"] == ["US", "DE", "GB"] and abs(d["share_pos"] - 2 / 3) < 1e-3 and d["h1a"] and d["h1c"] and d["h1b"]      # 2/3 刚好过；平均 Δ +0.0167 > 0
    RES2 = {**RES, "DE": dict(bad)}
    d2 = K.decide_index(RES2)
    assert not d2["h1a"] and not d2["h1c"] and not d2["h1b"]


def test_account_decision_and_verdict():
    seg = lambda c, dd: {"calmar": c, "dd": dd}                                            # noqa: E731
    A = {"US-0": {"base": {"all": seg(0.20, -30.0), "E": seg(0.25, -27.0), "J": seg(0.05, -22.0)},
                  "k": {"all": seg(0.24, -29.0), "E": seg(0.25, -26.0), "J": seg(0.045, -21.0)}},
         "JP-T": {"base": {"all": seg(0.20, -12.0), "E": seg(0.33, -7.0), "J": seg(0.06, -12.0)},
                  "k": {"all": seg(0.21, -12.0), "E": seg(0.325, -7.0), "J": seg(0.06, -12.0)}}}
    d2 = K.decide_account(A)
    assert d2 == {"h2a": True, "h2b": True}
    A2 = {**A, "US-0": {"base": A["US-0"]["base"], "k": {"all": seg(0.22, -29.0), "E": seg(0.25, -26.0), "J": seg(0.045, -21.0)}}}   # 20 年只 +0.02
    assert K.decide_account(A2)["h2a"] is False
    A3 = {**A, "JP-T": {"base": A["JP-T"]["base"], "k": {"all": seg(0.19, -12.0), "E": seg(0.33, -7.0), "J": seg(0.06, -12.0)}}}     # 日本 20 年更差
    assert K.decide_account(A3)["h2b"] is False
    ok, fails = K.verdict({"h1a": True, "h1b": True, "h1c": True}, d2)
    assert ok and fails == []
    ok2, fails2 = K.verdict({"h1a": True, "h1b": False, "h1c": True}, K.decide_account(A3))
    assert not ok2 and len(fails2) == 2 and fails2[0].startswith("H1b") and fails2[1].startswith("H2b")
