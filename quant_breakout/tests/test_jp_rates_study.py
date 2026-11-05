"""日本历年利率等 × 日経 横展开（scripts/jp_rates_study.py 登记检验）：月末化 / 补齐 / 分段 Δ12、状态门槛（缺值 = 平）、分组表与循环平移安慰剂、
加息 / 降息周期起点、事件路径、指数级规则评估（t − 1 月末状态 → t 月 ×0.5、两半、安慰剂）、横向状态、合并安慰剂与判定 D1〜D5。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import jp_rates_study as J                                                   # noqa: E402


def _m(start, vals):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="ME"), dtype=float)


def test_constants_and_rules():
    assert (J.EVAL0, J.SPLIT) == ("1975-09-30", "2005-12-31") and len(J.VARS) == 12 and set(J.RULES) == {"R1", "R2", "R3", "R4", "R5"}
    assert J.D["lt"] == 0.5 and J.D["real"] == 1.0 and J.D["cpi"] == 1.0 and J.D["fx"] == 5.0 and J.GROWTH == ("boj", "m2")
    assert (J.MIN_ERA, J.PLACEBO_N, J.SEEDS, J.SHIFT_MIN, J.MIN_MONTHS, J.MIN_HALF, J.Z_WIN) == (24, 200, 30, 12, 120, 60, 120)
    assert (J.DD_THR, J.EV_D3, J.EV_GAP, J.EV_H, J.HALF) == (-15.0, 0.1, 12, (3, 6, 12, 24), 0.5)
    assert (J.D1_MIN, J.D5_UP, J.D5_TOL, J.MIN_FOREIGN) == (0.02, 0.02, 0.01, 5) and abs(J.SHARE_2_3 - 2 / 3) < 1e-12
    assert J.RULES["R2"] == ("pol", "up", 0.1, "加息中") and J.RULES["R3"][1] == "down" and "IL" in J.MARKETS and len(J.MARKETS) == 26


def test_month_end_fill_and_segmented_delta():
    d = pd.Series(np.arange(1, 41, dtype=float), index=pd.bdate_range("2024-01-01", periods=40))
    m = J.me(d)
    assert list(m.index) == [pd.Timestamp("2024-01-31"), pd.Timestamp("2024-02-29")] and abs(m.iloc[0] - 12.0) < 1e-9     # 1 月 23 个交易日：1〜23 的均值
    g = _m("2020-01-31", [1, 2, 3]).drop(pd.Timestamp("2020-02-29"))
    f = J.full(g)
    assert len(f) == 3 and np.isnan(f.iloc[1])
    s = _m("2000-01-31", np.arange(24, dtype=float))
    assert np.isnan(J.d12(s).iloc[11]) and J.d12(s).iloc[12] == 12.0 and abs(J.pct12(s).iloc[-1] - (23 / 11 - 1) * 100) < 1e-9
    a = _m("2000-01-31", 1.0 + 0.1 * np.arange(48))                                                       # 到 2003-12
    b = _m("2002-01-31", 5.0 + 0.2 * np.arange(36))                                                       # 2002-01 起
    lv = J.splice(a, b, "2002-01-01")
    assert lv.loc["2001-12-31"] == a.loc["2001-12-31"] and lv.loc["2002-01-31"] == 5.0
    x = J.splice_d12(a, b, "2002-01-01")
    assert abs(x.loc["2001-12-31"] - 1.2) < 1e-9 and abs(x.loc["2002-06-30"] - 1.2) < 1e-9                  # b 的前 12 个月用 a 的 Δ12
    assert abs(x.loc["2003-01-31"] - 2.4) < 1e-9 and abs(x.loc["2003-12-31"] - 2.4) < 1e-9                  # 之后只用 b


def test_monthly_close_drops_the_unfinished_month():
    days = pd.bdate_range("2026-08-03", pd.Timestamp.today().normalize() + pd.Timedelta(days=1))
    mc = J.monthly_close(pd.Series(np.arange(len(days), dtype=float) + 1, index=days))
    assert mc.index[-1] <= pd.Timestamp.today().normalize() and mc.index[-1] == mc.index[-1] + pd.offsets.MonthEnd(0)
    assert J.monthly_close(pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-01-10", "2020-02-10"]))).tolist() == [1.0, 2.0]


def test_states_and_rule_state():
    x = _m("2010-01-31", [1.0, -1.0, 0.2, np.nan, -0.6])
    assert J.state_of("lt", x).tolist() == ["up", "down", "flat", "flat", "down"]
    assert J.state_of("boj", x).tolist() == ["up", "down", "up", "flat", "down"]
    assert J.state_of("fx", _m("2010-01-31", [6.0, -4.0])).tolist() == ["up", "flat"]
    assert J.rule_state(x, "up", 0.5).tolist() == [True, False, False, False, False]
    assert J.rule_state(x, "down", 0.5).tolist() == [False, True, False, False, True]
    z = J.z_state(_m("2000-01-31", np.r_[np.zeros(130), [5.0, -5.0]] + np.sin(np.arange(132))))
    assert z.iloc[-2] == "up" and z.iloc[-1] == "down"


def _blocks(start="1976-01-31", n=300, block=60):
    """状态 60 个月一换：上 的月份之后涨（每月 +3%）、下 的月份之后跌（−1%）。"""
    idx = pd.date_range(start, periods=n, freq="ME")
    st = pd.Series(["up" if (i // block) % 2 == 0 else "down" for i in range(n)], index=idx, dtype=object)
    r = np.where(st.to_numpy() == "up", 0.03, -0.01)
    mc = pd.Series(100 * np.cumprod(1 + np.r_[0.0, r[:-1]]), index=idx)
    return st, mc


def test_bucket_tables_placebo_and_stability():
    st, mc = _blocks()
    b = J.bucket(st, mc, placebo_n=50)
    assert b["n"] == 288 and set(b["all"]) == {"up", "down"} and b["all"]["up"]["med12"] > 20 and b["all"]["down"]["med12"] < 0
    assert b["all"]["up"]["hit12"] > 70 and b["all"]["down"]["dd15"] == 0.0 or b["all"]["down"]["dd15"] >= 0
    assert b["diff"] > 20 and b["pct"] >= 90 and set(b["eras"]) == {"E1", "E2"} and b["era_sign"] == {"E1": 1, "E2": 1} and b["stable"] is True
    assert "flat" not in b["all"]
    few = J.bucket(st.iloc[:30], mc, placebo_n=10)
    assert few["diff"] is None and few["stable"] is None


def test_cycle_starts_and_event_paths():
    p = np.full(120, 1.0)
    p[24:26], p[26:48] = 1.25, 1.5
    p[48:50], p[50:80] = 1.25, 1.0
    p[80:82], p[82:] = 1.25, 1.5
    pol = _m("1990-01-31", p)
    ups, downs = J.cycle_starts(pol, True), J.cycle_starts(pol, False)
    assert [t.strftime("%Y-%m") for t in ups] == ["1992-01", "1996-09"] and [t.strftime("%Y-%m") for t in downs] == ["1994-01"]
    mc = _m("1989-01-31", 100 * 1.01 ** np.arange(130))
    ev = J.event_paths(mc, ups, eval0="1989-01-31")
    assert ev["n"] == 2 and abs(ev["events"][0]["r12"] - (1.01 ** 12 - 1) * 100) < 0.05 and ev["neg12"] == 0.0 and "p12" in ev["events"][0]
    assert ev["events"][1]["date"] == "1996-09" and "r24" in ev["events"][1] and ev["med24"] > 0


def test_rule_eval_halves_and_placebo():
    idx = pd.date_range("1970-01-31", periods=680, freq="ME")
    rng = np.random.default_rng(0)
    on = pd.Series(rng.random(680) < 0.3, index=idx)
    prev = on.shift(1).fillna(False).astype(bool).to_numpy()
    r = np.where(prev, -0.03, 0.01)
    mc = pd.Series(100 * np.cumprod(1 + r), index=idx)
    x = J.rule_eval(mc, on, seeds=7)
    assert x["n"] == 611 and x["from"] == "1975-10-31" and x["delta"] > 0 and x["rule"]["calmar"] > x["hold"]["calmar"]
    assert set(x["halves"]) == {"h1", "h2"} and x["halves"]["h1"]["n"] == 363 and x["halves"]["h2"]["n"] == 248 and x["halves"]["h2"]["delta"] > 0
    assert len(x["placebo"]["vals"]) == 7 and x["placebo"]["q95"] is not None and x["delta"] > x["placebo"]["q95"]
    assert 20 < x["on_share"] < 40 and x["diff"] < 0
    assert J.rule_eval(mc.iloc[-40:], on.iloc[-40:], seeds=3)["skip"] == "评估月不够"                      # 不足 60 个月


def test_market_states_pooled_placebo_and_decision():
    idx = pd.date_range("1990-01-31", periods=200, freq="ME")
    lt = pd.Series(3 + np.sin(np.arange(200) / 7), index=idx)
    st = pd.Series(2 + np.cos(np.arange(200) / 9), index=idx)
    cpi = pd.Series(1 + np.sin(np.arange(200) / 11), index=idx)
    us10 = pd.Series(4 + np.sin(np.arange(200) / 5), index=idx)
    S = J.market_states({"lt": lt, "st": st, "cpi": cpi, "not_us": True}, us10)
    assert set(S) == {"R1", "R2", "R3", "R4", "R5"} and all(v.dtype == bool for v in S.values()) and S["R1"].sum() > 0
    assert J.market_states({"lt": lt, "st": None, "cpi": None, "not_us": False}, us10)["R2"] is None
    assert J.market_states({"lt": lt, "st": st, "cpi": cpi, "not_us": False}, us10)["R5"] is None
    ok = {"n": 300, "delta": 0.05, "halves": {"h1": {"delta": 0.03}, "h2": {"delta": 0.04}}, "placebo": {"q95": 0.02, "vals": [0.0, 0.01, 0.02]}, "on_share": 30.0}
    bad = {**ok, "halves": {"h1": {"delta": 0.03}, "h2": {"delta": -0.01}}}
    jp = {"R1": ok, "R2": bad, "R3": {**ok, "delta": 0.01}, "R4": {**ok, "on_share": 60.0}, "R5": ok}
    good_m = {"n": 200, "delta": 0.03, "placebo": {"vals": [0.0, 0.0, 0.0]}}
    bad_m = {"n": 200, "delta": -0.03, "placebo": {"vals": [0.0, 0.0, 0.0]}}
    short_m = {"n": 50, "delta": 0.5, "placebo": {"vals": [0.0, 0.0, 0.0]}}
    H = {"R1": {"US": good_m, "DE": good_m, "GB": good_m, "FR": good_m, "CA": bad_m, "AU": good_m, "JP": bad_m, "XX": short_m},
         "R2": {"US": good_m, "DE": good_m, "GB": good_m, "FR": good_m, "CA": good_m},
         "R3": {"US": good_m, "DE": good_m, "GB": good_m, "FR": good_m, "CA": good_m},
         "R4": {"US": good_m, "DE": good_m, "GB": good_m, "FR": good_m, "CA": good_m},
         "R5": {"US": good_m, "DE": good_m, "GB": bad_m, "FR": bad_m, "CA": good_m}}
    assert J.pooled_q95({"a": good_m, "b": bad_m}) == 0.0
    d = J.decide(jp, H)
    assert d["R1"] == {"D1": True, "D2": True, "D3": True, "D4": True, "pass14": True,
                       "h": {"n_foreign": 6, "share_pos": 83.0, "mean": 0.02, "pooled_q95": 0.0}}
    assert not d["R2"]["D1"] and d["R2"]["D4"] and not d["R2"]["pass14"]
    assert not d["R3"]["D2"] and not d["R4"]["D3"] and not d["R5"]["D4"] and d["R5"]["h"]["share_pos"] == 60.0
    A = {"JP-T": {"base": {"all": {"calmar": 0.20}, "E": {"calmar": 0.33}, "J": {"calmar": 0.06}},
                  "k": {"all": {"calmar": 0.23}, "E": {"calmar": 0.325}, "J": {"calmar": 0.06}}}}
    assert J.account_check(A)["D5"] is True
    A2 = {"JP-T": {"base": A["JP-T"]["base"], "k": {"all": {"calmar": 0.21}, "E": {"calmar": 0.33}, "J": {"calmar": 0.06}}}}
    assert J.account_check(A2)["D5"] is False
