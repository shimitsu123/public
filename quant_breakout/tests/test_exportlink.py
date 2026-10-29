"""出口股 × 海外联动（scripts/exportlink_common.py / exportlink_study.py）：时间对齐不看未来、个股联动的挑法、面板回归、过滤的范围与规则。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import exportlink_common as EL                                               # noqa: E402
import exportlink_study as ES                                                # noqa: E402


# ───────────────────────── 时间对齐 ─────────────────────────
def test_us_rel_returns_relative_to_spy():
    d = pd.bdate_range("2020-01-06", periods=4)
    spy = pd.Series([100, 101, 102, 101.0], index=d)
    a = pd.Series([50, 51.5, 51.5, 52.0], index=d)
    R = EL.us_rel_returns({"A": a}, spy)
    assert np.isnan(R["A"].iloc[0])
    assert R["A"].iloc[1] == pytest.approx((np.log(51.5 / 50) - np.log(101 / 100)) * 100)


def test_overnight_sum_uses_us_days_between_jp_close_and_next_open():
    us = pd.DatetimeIndex(["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09", "2020-01-10", "2020-01-13", "2020-01-14"])
    R = pd.DataFrame({"A": [np.nan, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0]}, index=us)
    # 日本：1/7（二）、1/8（三）、1/10（五）、1/14（二；1/13 日本休市）
    jp = pd.DatetimeIndex(["2020-01-07", "2020-01-08", "2020-01-10", "2020-01-14"])
    X = EL.overnight_sum(R, jp)
    # [1/7, 1/8) = 美国 1/7；[1/8, 1/10) = 1/8 + 1/9；[1/10, 1/14) = 1/10 + 1/13（日本 1/13 休市，美国那天也算进隔夜）；最后一天 NaN
    assert list(X["A"].iloc[:3]) == [1.0, 6.0, 24.0]
    assert np.isnan(X["A"].iloc[-1])


def test_overnight_sum_exact_windows():
    us = pd.bdate_range("2020-01-06", periods=10)                            # 1/6〜1/17 美国每个工作日
    R = pd.DataFrame({"A": np.arange(10, dtype=float)}, index=us)            # 1/6 的值 0 不算（第一行 NaN 以外都算）
    R.iloc[0, 0] = np.nan
    jp = pd.DatetimeIndex(["2020-01-07", "2020-01-08", "2020-01-10", "2020-01-14"])
    X = EL.overnight_sum(R, jp)
    # [1/7, 1/8) = 美国 1/7（1）；[1/8, 1/10) = 1/8（2）+ 1/9（3）；[1/10, 1/14) = 1/10（4）+ 1/13（5）
    assert list(X["A"].iloc[:3]) == [1.0, 5.0, 9.0]
    X2 = EL.overnight_sum(R.assign(A=R["A"].where(R.index < "2020-01-15", 999.0)), jp)
    assert list(X2["A"].iloc[:3]) == [1.0, 5.0, 9.0]                         # 之后的美国行情不影响


def test_overnight_sum_before_listing_is_nan():
    us = pd.bdate_range("2020-01-06", periods=6)
    R = pd.DataFrame({"A": [np.nan, np.nan, np.nan, 1.0, 1.0, 1.0]}, index=us)
    jp = pd.DatetimeIndex(["2020-01-06", "2020-01-07", "2020-01-10", "2020-01-13"])
    X = EL.overnight_sum(R, jp)
    assert np.isnan(X["A"].iloc[0]) and np.isnan(X["A"].iloc[1])
    assert X["A"].iloc[2] == 1.0                                             # [1/10, 1/13) = 美国 1/10


def test_momentum_sum_last_w_before_next_open():
    us = pd.bdate_range("2020-01-06", periods=10)
    R = pd.DataFrame({"A": np.arange(1, 11, dtype=float)}, index=us)
    jp = pd.DatetimeIndex(["2020-01-08", "2020-01-10", "2020-01-14"])
    M = EL.momentum_sum(R, jp, 3)
    # D = 1/8：Dn = 1/10 → 美国 < 1/10 的最近 3 天 = 1/7、1/8、1/9 = 2 + 3 + 4
    assert M["A"].iloc[0] == 9.0
    assert M["A"].iloc[1] == 15.0                                            # D = 1/10：Dn = 1/14 → 1/9、1/10、1/13 = 4 + 5 + 6
    assert M["A"].iloc[2] == 18.0                                            # 最后一天：Dn 当作 D 的下一天 → 1/10、1/13、1/14
    assert np.isnan(EL.momentum_sum(R, jp, 30)["A"]).all()


# ───────────────────────── 日本一边 ─────────────────────────
def test_jp_components_values_and_relative():
    op = np.array([[10, 20], [11, 20], [12, 22], [12, 22], [12, 22], [12, 22], [13, 22]], float)
    cl = np.array([[10, 20], [11.5, 21], [12, 22], [12, 22], [12, 22], [12.5, 22], [13, 23]], float)
    comp = EL.jp_components(op, cl)
    on0 = (np.log(11 / 10) - np.log(20 / 20)) / 2 * 100                      # 两只的相对：减去平均
    assert comp["on"][0, 0] == pytest.approx(on0)
    assert comp["on"][0, 0] + comp["on"][0, 1] == pytest.approx(0.0)
    assert comp["id1"][0, 0] == pytest.approx((np.log(11.5 / 11) - np.log(21 / 20)) / 2 * 100)
    assert comp["r2_5"][0, 0] == pytest.approx((np.log(12.5 / 11.5) - np.log(22 / 21)) / 2 * 100)
    assert np.isnan(comp["r6_20"]).all() and np.isnan(comp["s20"]).all()     # 不够 20 天
    assert np.isnan(comp["on"][-1]).all()


def test_corr_cols_matches_numpy():
    rng = np.random.default_rng(0)
    x = rng.normal(size=300)
    Y = np.column_stack([x + rng.normal(size=300), rng.normal(size=300)])
    Y[:50, 1] = np.nan
    r, n = EL._corr_cols(x, Y, 200)
    assert r[0] == pytest.approx(np.corrcoef(x, Y[:, 0])[0, 1])
    assert r[1] == pytest.approx(np.corrcoef(x[50:], Y[50:, 1])[0, 1]) and n[1] == 250
    assert np.isnan(EL._corr_cols(x, Y, 260)[0][1])


def test_fit_links_picks_best_and_uses_only_past():
    rng = np.random.default_rng(1)
    days = pd.bdate_range("2014-01-01", "2016-12-31")
    X1 = pd.DataFrame({"SMH": rng.normal(size=len(days)), "XLI": rng.normal(size=len(days))}, index=days)
    cc1 = np.column_stack([0.6 * X1["SMH"] + rng.normal(size=len(days)), 0.6 * X1["XLI"] + rng.normal(size=len(days)),
                           -0.6 * (X1["SMH"] + X1["XLI"]) + rng.normal(size=len(days))])        # C 与两个都负相关 → 没有联动
    L = EL.fit_links(cc1, X1, days, ["A.T", "B.T", "C.T"], [2016])
    assert L[2016]["A.T"][0] == "SMH" and L[2016]["B.T"][0] == "XLI" and "C.T" not in L[2016]
    cc2 = cc1.copy()
    cc2[days >= "2016-01-01", 0] = -X1["SMH"].to_numpy()[days >= "2016-01-01"]   # 当年的数据变了 → 当年的联动不变
    assert EL.fit_links(cc2, X1, days, ["A.T", "B.T", "C.T"], [2016])[2016]["A.T"] == L[2016]["A.T"]
    assert EL.fit_links(cc1, X1, days, ["A.T"], [2014]) == {2014: {}}       # 之前 2 年没有数据


def test_link_panels_and_kr3_lag():
    days = pd.bdate_range("2016-01-04", periods=5)
    X1 = pd.DataFrame({"SMH": [1.0, 2, 3, 4, 5], "XLI": [9.0] * 5}, index=days)
    M20 = X1 * 10
    M60 = X1 * 100
    LP = EL.link_panels({2016: {"A.T": ("SMH", 0.3, 2.0)}}, X1, M20, M60, days, ["A.T", "B.T"])
    assert list(LP["ov"][:, 0]) == [1, 2, 3, 4, 5] and np.isnan(LP["ov"][:, 1]).all()
    assert LP["z1"][0, 0] == pytest.approx(0.5) and LP["z20"][0, 0] == pytest.approx(10 / (2 * np.sqrt(20)))
    kr = pd.Series([100.0, 110, 121, 133.1, 146.41], index=pd.date_range("2020-01-01", periods=5, freq="MS"))
    v = EL.kr3_on(pd.DatetimeIndex(["2020-06-30", "2020-07-01", "2020-08-03"]), kr)
    # 4 月（2020-04）的 3 个月变化 = log(133.1 / 100)，7 月 1 日起才能用；6 月 30 日只能用 3 月的（没有 3 个月前 → NaN）
    assert np.isnan(v[0]) and v[1] == pytest.approx(np.log(1.331) * 100) and v[2] == pytest.approx(np.log(146.41 / 110) * 100)


# ───────────────────────── 统计与规则 ─────────────────────────
def test_pooled_nw_recovers_slope():
    rng = np.random.default_rng(2)
    x = rng.normal(size=(400, 30))
    y = 0.5 * x + rng.normal(size=(400, 30))
    m = np.ones_like(x, bool)
    r = EL.pooled_nw(y, x, m, 5)
    assert r["b"] == pytest.approx(0.5, abs=0.05) and r["t"] > 10 and r["days"] == 400
    y0 = rng.normal(size=(400, 30))
    assert abs(EL.pooled_nw(y0, x, m, 5)["t"]) < 4
    assert np.isnan(EL.pooled_nw(y, x, np.zeros_like(m), 5)["b"])


def test_keep_and_scope_masks():
    S = pd.DataFrame({"group": ["direct", "indirect", "domestic", "direct", "indirect"],
                      "ov": [-1.0, -1.0, -1.0, np.nan, 0.5], "m20": [-1.0, -1.0, -1.0, 1.0, -0.1],
                      "m60": [0.0] * 5, "gap": [0.0] * 5, "kr3": [0.0] * 5})
    assert list(EL.keep_mask(S, "EX1")) == [False, False, True, True, True]   # 内需不动、缺值保留
    assert list(EL.keep_mask(S, "EX5")) == [True, False, True, True, False]   # 只动间接
    assert list(EL.keep_mask(S, "EX6")) == [False, True, True, True, True]    # 只动直接
    assert list(EL.scope_mask(S, "EX6")) == [True, False, False, True, False]
    assert list(EL.scope_mask(S, "EX1")) == [True, True, False, False, True]  # 缺值（没有联动）不算进范围
    assert EL.group_of("7203.T", {"7203": "輸送用機器"}) == "direct"
    assert EL.group_of("4063.T", {"4063": "化学"}) == "indirect"
    assert EL.group_of("8306.T", {"8306": "銀行業"}) == "domestic" and EL.group_of("9999.T", {}) == "unknown"


def test_qualifies_adds_nikkei_direction_rule():
    j2 = {"frac": 0.6, "dwin": 2.5, "dmean": 0.3, "dmean_q95": 0.2}
    e = {"frac": 0.5, "dwin": 0.1, "dmean": 0.0}
    base = {"E": {"calmar": 0.30, "dd": -30.0}, "J": {"calmar": 0.40, "dd": -35.0}}
    port = {"E": {"calmar": 0.30, "dd": -30.0}, "J": {"calmar": 0.40, "dd": -35.0}}
    assert EL.qualifies(j2, e, {"dwin": 0.0, "dmean": 0.1}, port, base) == []
    assert "J（日経225）方向不一致" in EL.qualifies(j2, e, {"dwin": -0.5, "dmean": 0.1}, port, base)
    res = {k: {"fails": [], "j2": {"dmean": v}} for k, v in {"EX1": 0.5, "EX2": 0.6, "EX3": 0.7, "EX4": 0.8, "EX5": 0.1}.items()}
    assert EL.pick(res) == ["EX4", "EX3", "EX1"]                              # 月差族（EX2〜EX4）最多 2 个


def test_study_labels_and_per_set():
    seg = lambda b, t: {"b": b, "t": t}                                      # noqa: E731
    g = lambda on, id1, r25, share, mon: {"seg": {"on": seg(*on), "id1": seg(*id1), "r2_5": seg(*r25), "r6_20": seg(0.0, 0.0)},  # noqa: E731
                                           "late_share": share, "mon": {"z20": seg(*mon), "z60": seg(0.0, 0.0)}}
    A = {t: {"direct": g((1.0, 20), (0.2, 3), (0.1, 1), 0.2, (0.1, 1)), "indirect": g((0.5, 10), (0.2, 2.5), (0.0, 0), 0.3, (0.1, 1))}
         for t in ("E", "J2")}
    L = ES.labels(A)
    assert L == {"day1": True, "day2_5": False, "month": False, "indirect_slower": True}
    S = pd.DataFrame({"ticker": ["A", "B", "C", "D"], "week": ["w1"] * 4, "net": [2.0, -1.0, 3.0, 1.0],
                      "group": ["direct", "direct", "domestic", "indirect"], "ov": [1.0, -1.0, -1.0, 1.0], "m20": [np.nan] * 4,
                      "m60": [np.nan] * 4, "gap": [np.nan] * 4, "kr3": [np.nan] * 4})
    st = ES.per_set(S)
    assert st["EX1"]["n"] == 3 and st["EX1"]["kept"] == 2                    # 范围内 3 个（直接 2 + 间接 1），去掉 B
    assert st["EX1"]["dmean"] == pytest.approx(1.5 - 2 / 3)
    assert st["EX6"]["n"] == 0 and st["EX2"]["n"] == 0                      # m20 全缺值 → 范围内没有信号
