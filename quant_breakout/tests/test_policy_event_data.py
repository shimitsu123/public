"""scripts/policy_event_data.py：反应日 / 买点规则（含主场与 07:40 门槛）、窗口收益（逐个与向量化一致）、等权业种（成员下限、错价剔除、时点分类、名字归一）、
篮子下限、打乱日期 / 随机业种对照、事件链聚类、基准体检、事前 β。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import policy_event_data as PE  # noqa: E402

DAYS = pd.bdate_range("2024-10-01", "2025-03-31")


def test_reaction_and_entry_rules():
    E = pd.DataFrame({"date": pd.to_datetime(["2024-10-31", "2024-10-31", "2024-11-06", "2024-11-06", "2024-11-09", "2024-12-19", "2024-11-06"]),
                      "time_jst": ["12:30", "15:10", "15:10", "15:35", "", "", "05:00"]})
    r, t0 = PE.reaction_and_entry(E, DAYS)
    assert list(r.strftime("%Y-%m-%d")) == ["2024-10-31", "2024-11-01", "2024-11-06", "2024-11-07", "2024-11-11", "2024-12-20", "2024-11-06"]
    assert list(t0.strftime("%Y-%m-%d")) == ["2024-11-01", "2024-11-01", "2024-11-07", "2024-11-07", "2024-11-11", "2024-12-20", "2024-11-06"]
    # 15:10：2024-11-05 前 = 盘后 → 次日；之后 = 盘中 → 当天、t0 次日；周六 → 下周一；缺时刻 → 当盘后（t0 = r）；05:00 → 当天开盘就能买
    assert list(PE.reaction_days(E, DAYS).strftime("%m-%d")) == list(r.strftime("%m-%d"))
    days = pd.bdate_range("2010-01-01", "2025-12-31")
    U = pd.DataFrame({"date": pd.to_datetime(["2025-04-02", "2025-04-09", "2020-03-15", "2025-07-22", "2018-03-08", "2010-09-15", "2011-03-18"]),
                      "date_jst": ["2025-04-03", "2025-04-10", "2020-03-15", "2025-07-22", "2018-03-08", "2010-09-15", "2011-03-18"],
                      "time_jst": ["05:00", "02:18", "", "", "", "10:30", "07:00"]})
    r, t0 = PE.reaction_and_entry(U, days)
    assert list(r.strftime("%Y-%m-%d")) == ["2025-04-03", "2025-04-10", "2020-03-16", "2025-07-23", "2018-03-09", "2010-09-15", "2011-03-18"]
    assert list(t0.strftime("%Y-%m-%d")) == ["2025-04-03", "2025-04-10", "2020-03-16", "2025-07-23", "2018-03-09", "2010-09-16", "2011-03-18"]


def test_window_returns_and_reactions():
    idx = DAYS[:10]
    c = pd.Series([100, 100, 110, 121, 121, 121, 121, 121, 121, 121], index=idx, dtype=float)
    inc, post = PE.window_returns(c, idx[2], 1)
    assert np.isclose(inc, 21.0) and np.isclose(post, 10.0)                    # r−1 → r+1：100 → 121；r → r+1：110 → 121
    assert np.isnan(PE.window_returns(c, idx[0], 1)[0]) and np.isnan(PE.window_returns(c, idx[9], 1)[0])
    S = pd.DataFrame({"a": c, "b": c * 0 + 100})
    R = PE.reactions(pd.DataFrame({"x": [1]}), pd.DatetimeIndex([idx[2]]), S, c, horizons=(1,))
    assert len(R) == 2 and np.isclose(R.loc[R["series"] == "a", "ex_post"].iloc[0], 0.0) and np.isclose(R.loc[R["series"] == "b", "ex_post"].iloc[0], -10.0)
    summ = PE.summarize(R)
    assert set(summ["series"]) == {"a", "b"} and summ.loc[summ["series"] == "b", "hit"].iloc[0] == 0.0


def test_equal_weight_returns_mask_and_outliers():
    idx = DAYS[:3]
    rets = pd.DataFrame({"1.T": [1.0, 2.0, np.nan], "2.T": [3.0, 4.0, 5.0], "3.T": [5.0, 6.0, 7.0], "4.T": [9.0, 9.0, 9.0]}, index=idx)
    groups = {"1.T": "A", "2.T": "A", "3.T": "A", "4.T": "B"}
    ew = PE.equal_weight_returns(rets, groups, min_n=2)
    assert np.isclose(ew.loc[idx[0], "A"], 3.0) and np.isclose(ew.loc[idx[2], "A"], 6.0) and ew["B"].isna().all()   # B 只有 1 只 → 不够
    mask = pd.DataFrame(True, index=idx, columns=rets.columns); mask.loc[idx[0], "3.T"] = False
    ew2 = PE.equal_weight_returns(rets, groups, mask, min_n=2)
    assert np.isclose(ew2.loc[idx[0], "A"], 2.0)
    rets.loc[idx[1], "3.T"] = 900.0                                             # 错价（+900%）→ 当缺值
    ew3 = PE.equal_weight_returns(rets, groups, min_n=2)
    assert np.isclose(ew3.loc[idx[1], "A"], 3.0)
    assert PE.MIN_N == 5


def test_shuffle_dates_same_year_and_gap():
    r = pd.DatetimeIndex(["2024-10-15", "2025-02-03", pd.NaT])
    s = PE.shuffle_dates(r, DAYS, 0)
    assert s[0].year == 2024 and s[1].year == 2025 and pd.isna(s[2])
    assert abs(DAYS.get_loc(s[0]) - DAYS.get_loc(r[0])) >= 5
    assert list(PE.shuffle_dates(r, DAYS, 0)) == list(s)                       # 种子可复现
    cum = PE.cum_from_returns(pd.DataFrame({"a": [1.0, np.nan, -1.0]}, index=DAYS[:3]))
    assert np.isclose(cum["a"].iloc[-1], 100 * 1.01 * 0.99)


def test_sector33_all_pit_uses_strictly_earlier_snapshot_and_normalises_names():
    idx = DAYS[:6]
    n = len(idx)
    C = np.ones((n, 2)); C[:, 0] = np.cumprod([1, 1.01, 1.01, 1.01, 1.01, 1.01]); C[:, 1] = np.cumprod([1, 1.03, 1.03, 1.03, 1.03, 1.03])
    A = {"days": idx, "names": ["1000.T", "2000.T"], "C": C, "listed": np.ones((n, 2), bool)}
    snaps = {pd.Timestamp(idx[0]): pd.DataFrame({"Code": ["10000", "20000"], "S33Nm": ["電気･ガス業", "電気･ガス業"]}),
             pd.Timestamp(idx[3]): pd.DataFrame({"Code": ["10000", "20000"], "S33Nm": ["電気･ガス業", "証券･商品先物取引業"]})}
    ew = PE.sector33_all_pit(A, snaps, min_n=1)
    assert "電気・ガス業" in ew.columns and "証券、商品先物取引業" in ew.columns                    # 半角中点 / 別名 → 東証正式名
    assert np.isclose(ew.loc[idx[2], "電気・ガス業"], 2.0) and np.isnan(ew.loc[idx[2]].get("証券、商品先物取引業", np.nan))
    assert np.isclose(ew.loc[idx[4], "電気・ガス業"], 1.0) and np.isclose(ew.loc[idx[4], "証券、商品先物取引業"], 3.0)
    assert np.isnan(ew.loc[idx[3]].get("証券、商品先物取引業", np.nan))                            # 快照当天还用旧分类


def test_open_close_windows_vectorised_and_spread():
    idx = DAYS[:8]
    cc = pd.DataFrame({"a": [np.nan, 1.0, 1.0, 1.0, 1.0, 1.0, np.nan, 1.0], "b": [np.nan, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}, index=idx)
    oc = pd.DataFrame({"a": [0.5] * 8, "b": [0.0] * 8}, index=idx)
    w = PE.window_open(cc, oc, idx[2], 3)                                   # t0 开 → t0+2 收：(1.005)(1.01)(1.01) − 1
    assert np.isclose(w["a"], (1.005 * 1.01 * 1.01 - 1) * 100) and np.isclose(w["b"], 0.0)
    assert PE.window_open(cc, oc, idx[6], 3).isna().all()                    # 数据不够
    d0 = PE.window_close(cc, idx[2], 0, 0); assert np.isclose(d0["a"], 1.0)
    w5 = PE.window_close(cc, idx[1], 1, 4); assert np.isclose(w5["a"], (1.01 ** 4 - 1) * 100)
    W = PE.WindowCache(cc, oc)
    M = W.open_windows([idx[2], idx[6], pd.Timestamp("2030-01-01")], 3)
    assert np.isclose(M[0, 0], w["a"]) and np.isclose(M[0, 1], 0.0) and np.isnan(M[1, 0]) and np.isnan(M[2, 0])
    assert np.isclose(W.open_windows([idx[4]], 3)[0, 0], (1.005 * 1.01 - 1) * 100)          # 窗口内一个缺值（当 0）：缺值 ≤ 一半 → 仍算
    assert np.isclose(W.close_windows([idx[2]], 0, 0)[0, 0], 1.0) and np.isclose(W.close_windows([idx[1]], 1, 4)[0, 0], w5["a"])
    x = pd.Series({"a": 2.0, "b": -1.0, "c": 0.0, "d": np.nan, "e": 1.0})
    assert np.isclose(PE.spread(x, ["a", "e"], ["b", "c"]), 1.5 - (-0.5)) and np.isnan(PE.spread(x, ["a"], ["b"]))     # 一侧 < 2 → 缺值
    assert np.isclose(PE.spread(x, ["a"], ["b"], min_side=1), 3.0) and np.isclose(PE.spread(x, ["a", "e"], [], ), 1.5 - (-0.5))
    assert np.isnan(PE.spread(x, ["d", "a"], [])) and np.isnan(PE.spread(x, [], []))
    assert PE.basket_sizes(x, ["a", "d"], ["b"]) == (1, 1)


def test_controls_chains_and_boot():
    b, v = PE.shuffle_sectors(["a", "b"], ["c"], list("abcdefgh"), 0)
    assert len(b) == 2 and len(v) == 1 and not set(b) & set(v) and (b, v) == PE.shuffle_sectors(["a", "b"], ["c"], list("abcdefgh"), 0)
    assert PE.shuffle_sectors([], [], list("abc"), 0) == ([], [])
    lo, hi = PE.cluster_boot(np.r_[np.ones(20) * 2, -np.ones(20)], np.r_[[0] * 20, [1] * 20], n=300)
    assert lo <= 0.5 <= hi
    assert PE.cluster_boot_month(np.r_[np.ones(20) * 2, -np.ones(20)], np.r_[["2020-01"] * 20, ["2020-02"] * 20], n=300) == (lo, hi)
    r = pd.DatetimeIndex([DAYS[10], DAYS[15], DAYS[60], pd.NaT, DAYS[40]])
    assert list(PE.overlap_flags(r, DAYS, 20)) == [1, 1, 1, 0, 1]                  # 40 / 60 相隔正好 20 → 也算重叠
    assert list(PE.chain_ids(r, DAYS, 20)) == [0, 0, 1, -1, 1]                  # 10 / 15 一链；40 / 60 一链；NaT = −1
    assert PE.crisis_flag(pd.Timestamp("2020-03-16")) == 1 and PE.crisis_flag(pd.Timestamp("2024-10-01")) == 0
    assert PE.adjacent_flag(DAYS[10], [DAYS[12]], DAYS) == 1 and PE.adjacent_flag(DAYS[10], [DAYS[14]], DAYS) == 0 and PE.adjacent_flag(DAYS[10], [], DAYS) == 0
    s = pd.Series([100.0, 101.0, 90.0, 91.0], index=DAYS[:4])
    assert PE.check_series(s, "x") is s
    with pytest.raises(ValueError):
        PE.check_series(pd.Series([100.0, 10.0, 11.0], index=DAYS[:3]), "bad")


def test_betas_asof_use_only_past_weeks():
    weeks = pd.date_range("2020-01-03", periods=160, freq="W-FRI")
    rng = np.random.default_rng(0)
    fac = pd.DataFrame({"rate_jp": rng.normal(0, 0.05, 160), "fx": rng.normal(0, 1, 160)}, index=weeks)
    mkt = pd.Series(rng.normal(0, 1, 160), index=weeks)
    sec = pd.DataFrame({"銀行業": mkt + 10 * fac["rate_jp"] + rng.normal(0, 0.1, 160), "小売業": mkt - 0.5 * fac["fx"] + rng.normal(0, 0.1, 160)}, index=weeks)
    end = weeks[120] + pd.Timedelta(days=3)
    B = PE.betas_asof(sec, fac, mkt, end)
    assert B is not None and B.loc["銀行業", "rate_jp"] > 5 and B.loc["小売業", "fx"] < -0.3
    sec2 = sec.copy(); sec2.loc[weeks[121]:, :] = 999.0                        # 改掉 end 之后的周 → β 不变
    B2 = PE.betas_asof(sec2, fac, mkt, end)
    assert np.allclose(B.to_numpy(), B2.to_numpy())
    assert PE.betas_asof(sec, fac, mkt, weeks[30]) is None                      # 不足 60 周
    bl, vl = PE.beta_lists(B, {"rate_jp": 0.1, "fx": -1.0}, k=1)
    assert bl == ["銀行業"] and vl == ["小売業"]                                   # 加息 → 银行 β 高、零售 fx 负 → 受损
    assert PE.beta_lists(None, {"fx": 1.0}) == ([], [])
