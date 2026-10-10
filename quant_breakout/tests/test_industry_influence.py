"""qbreak/industry_influence.py：占比、到顶区 P、到头确认 R、起步 E、事件去重、前向超额、「崩」、按年整块重抽。"""
import numpy as np
import pandas as pd

from qbreak import industry_influence as II


def _months(n, start="2000-01-01"):
    return pd.date_range(start, periods=n, freq="MS")


def test_shares_sum_to_one_and_skip_missing():
    me = pd.DataFrame({"A": [1.0, 2.0], "B": [3.0, np.nan], "C": [0.0, 2.0]}, index=_months(2))
    s = II.shares(me)
    assert np.allclose(s.sum(axis=1), 1.0)
    assert s.loc[s.index[0], "A"] == 0.25 and np.isnan(s.loc[s.index[0], "C"]) and np.isnan(s.loc[s.index[1], "B"])
    assert list(II.avg_share(s)) == [0.5, 0.5]


def test_peak_zone_needs_doubling_new_high_and_size():
    n = 80
    idx = _months(n)
    a = np.r_[np.full(40, 0.2), np.linspace(0.2, 0.6, 40)]                   # 后 40 个月从 0.2 涨到 0.6
    b = np.full(n, 0.05)                                                      # 小、平
    share = pd.DataFrame({"A": a, "B": b, "C": 1 - a - b}, index=idx)
    pz = II.peak_zone(share)
    assert not pz["B"].any() and not pz["C"].any()
    first = pz.index[pz["A"]][0]
    i = list(idx).index(first)
    assert i >= II.HIGH_N - 1 and a[i] >= 2 * a[i - II.UP_N]                 # 有 60 个月历史、36 个月翻倍
    assert not pz["A"].iloc[: II.HIGH_N - 1].any()                           # 不够 60 个月 → 不判


def test_first_events_gap():
    f = pd.DataFrame({"A": [True, True, False, True] + [False] * 22 + [True]}, index=_months(27))
    ev = II.first_events(f, gap=24)
    assert list(np.where(ev["A"])[0]) == [0, 26]                             # 第 3 个月离第 0 个月 < 24 → 不算


def test_rollover_after_peak():
    idx = _months(10)
    share = pd.DataFrame({"A": [0.1, 0.2, 0.3, 0.3, 0.26, 0.23, 0.2, 0.2, 0.2, 0.2]}, index=idx)
    pz = pd.DataFrame({"A": [False, False, True, False, False, False, False, False, False, False]}, index=idx)
    r = II.rollover(share, pz, look=24, drop=0.20)
    assert list(np.where(r["A"])[0]) == [5, 6, 7, 8, 9]                      # 0.23 ≤ 0.8 × 0.3 = 0.24 起
    r2 = II.rollover(share, pz, look=2, drop=0.20)
    assert list(np.where(r2["A"])[0]) == []                                   # P 已经超过 2 个月


def test_fwd_log_net_and_crash():
    idx = _months(6)
    ri = pd.DataFrame({"A": [0.0, 10.0, 10.0, -50.0, 0.0, 0.0]}, index=idx)
    rm = pd.Series([0.0, 0.0, 0.0, 0.0, 0.0, 0.0], index=idx)
    f2 = II.fwd_log_net(ri, rm, 2)
    assert np.isclose(f2["A"].iloc[0], 2 * np.log(1.1)) and np.isnan(f2["A"].iloc[4])
    c = II.crash_fwd(ri, h=3, dd=0.40)
    assert c["A"].iloc[0] == 0.0                                              # 1.1 × 1.1 × 0.5 = 0.605 → 跌 39.5% < 40%
    assert c["A"].iloc[1] == 1.0 or c["A"].iloc[2] == 1.0                     # 从更高处起算 → 跌 50%
    assert np.isnan(c["A"].iloc[3])


def test_emerging_requires_streak_and_lagging_price():
    idx = pd.Index([2000, 2001, 2002, 2003])
    f = pd.DataFrame({"A": [0.10, 0.11, 0.12, 0.13], "B": [0.10, 0.11, 0.10, 0.13]}, index=idx)
    m = pd.DataFrame({"A": [0.10, 0.10, 0.10, 0.11], "B": [0.10, 0.10, 0.10, 0.10]}, index=idx)
    e = II.emerging(f, m, years=3, rise=0.20)
    assert bool(e.loc[2003, "A"]) and not bool(e.loc[2003, "B"])             # B 中间跌过一年
    m2 = m.copy()
    m2.loc[2003, "A"] = 0.14                                                  # 市值占比涨得比基本面多 → 不是「没反应」
    assert not bool(II.emerging(f, m2).loc[2003, "A"])


def test_event_rows_and_block_bootstrap():
    idx = _months(36)
    ev = pd.DataFrame(False, index=idx, columns=["A", "B"])
    ev.iloc[0, 0] = True
    ev.iloc[30, 1] = True
    val = pd.DataFrame({"A": np.full(36, 1.0), "B": np.full(36, -1.0)}, index=idx)
    rows = II.event_rows(ev, v=val)
    assert list(rows["ind"]) == ["A", "B"] and list(rows["v"]) == [1.0, -1.0]
    base = II.all_rows(v=val)
    assert len(base) == 72
    st = II.year_block_diff(rows, base, "v", n=200, seed=1)
    assert st["n"] == 2 and np.isclose(st["diff"], 0.0) and st["lo"] <= st["hi"]


def test_splice_caps_backfills_with_returns():
    idx = _months(4)
    true = pd.DataFrame({"A": [np.nan, np.nan, 110.0, 121.0], "B": [np.nan, np.nan, 90.0, 90.0]}, index=idx)
    ret = pd.DataFrame({"A": [np.nan, 0.0, 10.0, 10.0], "B": [np.nan, 0.0, -10.0, 0.0]}, index=idx)
    c = II.splice_caps(true, ret)
    assert np.isclose(c.loc[idx[1], "A"], 100.0) and np.isclose(c.loc[idx[1], "B"], 100.0)     # 110 ÷ 1.1、90 ÷ 0.9
    assert np.isclose(c.loc[idx[0], "A"], 100.0) and c.loc[idx[3], "A"] == 121.0                # 第一个月：收益 0 → 不变；真值不动


def test_mof_fy_sum_four_quarters_to_june():
    rows = []
    for y in (2020, 2021):
        for q in (1, 2, 3, 4):
            rows.append({"ind": "105", "q": f"{y}{q}", "item": "078", "value": "10"})
            rows.append({"ind": "109", "q": f"{y}{q}", "item": "078", "value": "1"})
    df = pd.DataFrame(rows)
    out = II.mof_fy_sum(df, "078", {"1": ["105", "109"]}, end_q=2)
    assert np.isnan(out.loc[2020, "1"]) and out.loc[2021, "1"] == 44.0                         # 2020Q3〜2021Q2 = 4 × 11


def test_verdict_rules():
    neg = {"diff": -0.05, "lo": -0.10, "hi": -0.01}
    assert II.verdict(neg, {"diff": -0.02}, {"diff": -0.03}, {"n": 0}, -1)["label"] == "通过（日本样本不够，只按美国判）"
    assert II.verdict(neg, {"diff": -0.02}, {"diff": -0.03}, {"n": 5, "diff": -0.01}, -1)["label"] == "通过"
    assert not II.verdict(neg, {"diff": -0.02}, {"diff": -0.03}, {"n": 5, "diff": 0.01}, -1)["pass"]     # 日本方向相反
    assert not II.verdict(neg, {"diff": -0.02}, {"diff": 0.01}, {"n": 0}, -1)["pass"]                     # 一半相反
    assert not II.verdict({"diff": -0.05, "lo": -0.10, "hi": 0.01}, {"diff": -0.02}, {"diff": -0.03}, {"n": 0}, -1)["pass"]   # 区间含 0
    pos = {"diff": 0.05, "lo": 0.01, "hi": 0.10}
    assert II.verdict(pos, {"diff": 0.02}, {"diff": 0.03}, {"n": 3, "diff": 0.01}, +1)["pass"]
    assert not II.verdict({"diff": None, "lo": None, "hi": None}, {}, {}, {"n": 0}, -1)["pass"]


def test_names_and_groups():
    assert II.norm_s33("情報･通信業") == "情報・通信業" and II.norm_s33("証券･商品先物取引業") == "証券、商品先物取引業"
    assert len(II.S33_TO_S17) == 33 and sorted(set(II.S33_TO_S17.values())) == list(range(1, 18))
    assert II.ETF17[1] == "1617.T" and II.ETF17[17] == "1633.T"
    g = II.mof_groups()
    assert set(g) == set(II.E_GROUPS) and g["9"] == ["122", "145", "124"] and "149" not in sum(g.values(), [])
