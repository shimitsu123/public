"""「选股本身的飞跃」S1 / S2 探索的纯函数：回踩买的参数、决算季、事件特征只用信号日为止、多年新高不含当天。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leap2_s1_explore as S1  # noqa: E402
import leap2_s2_explore as S2  # noqa: E402
import leap2_s2b_explore as S2B  # noqa: E402


def test_limit_kw_registers_every_signal_with_current_exits():
    idx = pd.bdate_range("2020-01-06", periods=4)
    fr = {"A.T": pd.DataFrame({"entry": [True, False, True, False]}, index=idx), "B.T": pd.DataFrame({"entry": [False] * 4}, index=idx)}
    kw = S1.limit_kw(fr, 0.5)
    assert kw["pb"] == {"A.T": {idx[0], idx[2]}} and kw["limit_k"] == 0.5
    assert kw["pb_use_dead"] and not kw["pb_free"] and kw["hold_pb"] >= 10 ** 6


def test_earnings_season_window():
    assert S2.in_earn(pd.Timestamp("2020-05-20")) and S2.in_earn(pd.Timestamp("2020-01-25"))
    assert not S2.in_earn(pd.Timestamp("2020-05-21")) and not S2.in_earn(pd.Timestamp("2020-03-10"))


def test_event_features_use_only_data_up_to_signal():
    idx = pd.bdate_range("2015-01-01", periods=800)
    c = np.concatenate([np.linspace(50, 100, 300), np.linspace(99, 90, 500)])
    c[-1] = 200.0                                                                 # 最后一天创新高；上一次 250 日新高 = 第 299 天
    df = pd.DataFrame({"Open": c * 1.0, "Close": c, "Volume": 1000.0}, index=idx)
    df.iloc[-1, df.columns.get_loc("Open")] = 110.0
    df.iloc[-1, df.columns.get_loc("Volume")] = 3000.0
    f = S2.event_features(df, idx[-1])
    assert np.isclose(f["gap"], 110.0 / c[-2] - 1) and np.isclose(f["vr"], 3.0) and f["hi3y"] is True
    assert np.isnan(f["hi5y"]) and f["base"] == 500                              # 历史不满 1250 天；距上次 250 日新高 500 天
    later = df.copy()
    later.loc[idx[-2], "Close"] = 1e6                                            # 改信号日之前的一天 → 特征跟着变（证明只用到信号日为止）
    assert S2.event_features(later, idx[-1])["hi3y"] is False
    fut = pd.DataFrame({"Open": 1e6, "Close": 1e6, "Volume": 1e9}, index=pd.bdate_range(idx[-1] + pd.Timedelta(days=1), periods=5))
    g = S2.event_features(pd.concat([df, fut]), idx[-1])                          # 信号日之后的数据不影响特征
    assert all((np.isnan(g[k]) and np.isnan(f[k])) or g[k] == f[k] for k in f)
    assert S2.event_features(df, pd.Timestamp("1999-01-01")) == {}


def test_split_stats_counts_years():
    T = pd.DataFrame({"sig_date": pd.to_datetime(["2010-01-05"] * 6 + ["2011-01-05"] * 6),
                      "net": [3, 3, 3, -1, -1, -1, -2, -2, -2, 1, 1, 1]})
    m = pd.Series([True] * 3 + [False] * 3 + [True] * 3 + [False] * 3)
    s = S2.split_stats(T, m)
    assert s["yes"]["n"] == 6 and s["years"] == [1, 2] and s["no"]["win"] == 50.0


def test_multi_year_high_excludes_today_and_needs_history():
    c = pd.Series([1.0, 2.0, 3.0, 2.5, 3.0, 3.5])
    h = S2B.multi_year_high(c, 3)
    assert h.tolist() == [False, False, False, False, True, True]
    idx = pd.bdate_range("2020-01-06", periods=6)
    fr = {"A.T": pd.DataFrame({"entry": True}, index=idx[2:]), "B.T": pd.DataFrame({"entry": True}, index=idx)}
    m = S2B.hi_masks(fr, {"A.T": pd.Series(c.to_numpy(), index=idx)}, 3)
    assert m["A.T"].tolist() == [False, False, True, True] and not m["B.T"].any()


def test_asof_helpers_respect_us_timing():
    import leap2_s3_explore as S3
    s = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08"]))
    d = pd.DatetimeIndex(["2020-01-06", "2020-01-08", "2020-01-10"])
    assert np.allclose(S3.asof_before(s, d)[1:], [2.0, 3.0]) and np.isnan(S3.asof_before(s, d)[0])   # 美国同一天的收盘不能用
    assert np.allclose(S3.asof_upto(s, d), [1.0, 3.0, 3.0])


def test_tercile_table_high_minus_low():
    import leap2_s3_explore as S3
    V = pd.DataFrame({"sig_date": pd.to_datetime(["2010-01-05"] * 45), "x": np.arange(45, dtype=float),
                      "net": [-1.0] * 15 + [0.5] * 15 + [2.0] * 15})
    r = S3.tercile_table(V, "x")
    assert r["low"]["win"] == 0.0 and r["high"]["win"] == 100.0 and np.isclose(r["d_mean"], 3.0) and r["years"] == [1, 1]
    assert S3.tercile_table(V.iloc[:10], "x") == {}


def test_us_rank_uses_data_two_months_back():
    import leap2_s4_explore as S4
    idx = pd.date_range("2000-01-01", periods=16, freq="MS")
    R = pd.DataFrame({"A": 1.0, "B": 0.0, "C": -1.0}, index=idx)
    R.loc[idx[14], "C"] = 500.0                                                   # 第 15 个月 C 暴涨 → 只有两个月后才看得到
    P = S4.us_rank_asof(R)
    assert np.isnan(P.iloc[12]["A"]) and P.iloc[13]["A"] == 1.0 and P.iloc[13]["C"] == 1 / 3
    assert P.iloc[15]["C"] == 1 / 3 and not np.isnan(P.iloc[15]["A"])           # 第 16 个月用的是到第 14 个月为止
    from qbreak.us_industry import FF49_CN
    assert S4.S33_FF49["電気機器"] == "Chips" and set(S4.S33_FF49.values()) <= set(FF49_CN)    # 只用 Ken French 49 行业里真有的代码
    assert len(S4.S33_FF49) == 33


def test_us_pct_frames_maps_sector_and_month():
    import leap2_s4b_explore as S4B
    idx = pd.to_datetime(["2020-03-02", "2020-03-31", "2020-04-01"])
    P = pd.DataFrame({"Chips": [0.1, 0.9]}, index=pd.to_datetime(["2020-03-01", "2020-04-01"]))
    fr = {"A.T": pd.DataFrame({"entry": True}, index=idx), "B.T": pd.DataFrame({"entry": True}, index=idx)}
    u = S4B.us_pct_frames(fr, {"A.T": "電気機器", "B.T": "謎の業種"}, P)
    assert np.allclose(u["A.T"], [0.1, 0.1, 0.9]) and np.isnan(u["B.T"]).all()


def test_rolling_betas_recover_known_slope_and_use_only_past_weeks():
    import leap2_s5_explore as S5
    rng = np.random.default_rng(0)
    idx = pd.date_range("2010-01-01", periods=140, freq="W-FRI")
    m = pd.Series(rng.normal(0, 0.02, 140), index=idx)
    f = pd.Series(rng.normal(0, 0.01, 140), index=idx)
    y = pd.DataFrame({"A": 1.5 * m + 2.0 * f + rng.normal(0, 0.001, 140)}, index=idx)
    X = pd.DataFrame({"f": f, "n225": m})
    B = S5.rolling_betas(y, X[["f", "n225"]], "n225", weeks=104)["f"]
    assert B["A"].iloc[:104].isna().all() and abs(B["A"].iloc[-1] - 2.0) < 0.05     # 前 104 周没有；控制日経后的系数 ≈ 2
    y2 = y.copy()
    y2.iloc[120:] = 9.9                                                               # 改第 121 周以后 → 第 119 周的 β 不变
    B2 = S5.rolling_betas(y2, X[["f", "n225"]], "n225", weeks=104)["f"]
    assert np.isclose(B2["A"].iloc[119], B["A"].iloc[119])
    assert S5.weekly(pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-01-06", "2020-01-10"]))).iloc[-1] == 2.0


def test_combo_rules_pairs_and_screen():
    import leap2_s6_combo as S6
    n = 60
    P = pd.DataFrame({"a": np.arange(n, dtype=float), "b": np.r_[np.zeros(30), np.ones(30)], "w2": np.r_[np.ones(30), np.zeros(30)]})
    R, meta = S6.make_rules(P, [], ["w2"])
    assert R.shape == (2, n) and meta[0]["lab"] == "w2 是" and R[0].sum() == 30
    x = np.arange(300, dtype=float)
    R2, meta2 = S6.make_rules(pd.DataFrame({"a": x}), ["a"], [])
    assert [m["op"] for m in meta2] == ["<=", "<=", ">=", ">="] and R2[0].sum() == 100 and R2[3].sum() == 100    # 分位点固定
    y = np.r_[np.ones(150), -np.ones(150)]
    nn, w, mu = S6.pair_stats(R2, y, np.ones(300, bool))
    assert nn[0, 0] == 100 and w[0, 0] == 100.0 and np.isclose(mu[3, 3], -1.0) and nn[0, 3] == 0              # 对角 = 单条；互斥 → 0 笔
    sel = np.r_[np.ones(150, bool), np.zeros(150, bool)]
    assert S6.pair_stats(R2, y, sel)[0][1, 1] == 150


def test_screen_needs_both_eras_and_halves():
    import leap2_s6_combo as S6
    rng = np.random.default_rng(1)
    n = 400
    x = rng.random(n)
    y = np.where(x > 0.5, 3.0, -1.0)                                                                   # 指标高 → 全赚
    R, meta = S6.make_rules(pd.DataFrame({"x": x}), ["x"], [])
    era = np.r_[np.ones(200, bool), np.zeros(200, bool)]
    masks = {"E": era, "J": ~era, "E1": np.r_[np.ones(100, bool), np.zeros(300, bool)], "E2": np.r_[np.zeros(100, bool), np.ones(100, bool), np.zeros(200, bool)],
             "J1": np.r_[np.zeros(200, bool), np.ones(100, bool), np.zeros(100, bool)], "J2": np.r_[np.zeros(300, bool), np.ones(100, bool)]}
    base = {k: (45.0, 0.5) for k in masks}
    ok, _ = S6.screen(R, meta, y, masks, base)
    assert ok[3, 3] and ok[2, 2] and not ok[0, 0]                                                        # 「≥ 2/3」「≥ 中位数」过，「≤ 1/3」不过
    y2 = y.copy()
    y2[~era] = -1.0                                                                                     # J 全亏 → 什么都不过
    assert not S6.screen(R, meta, y2, masks, base)[0].any()


def test_daily_from_weekly_uses_previous_week():
    import leap2_s6b_portfolio as S6B
    M = pd.DataFrame({"A.T": [1.0, 2.0, 3.0]}, index=pd.to_datetime(["2020-01-03", "2020-01-10", "2020-01-17"]))
    days = pd.DatetimeIndex(["2020-01-13", "2020-01-17", "2020-01-20"])                             # 周一、周五、下周一
    assert S6B.daily_from_weekly(M, "A.T", days).tolist() == [2.0, 2.0, 3.0]                             # 本周五的值要到下周才用
    assert np.isnan(S6B.daily_from_weekly(M, "B.T", days)).all()


def test_s6_study_candidate_keep_and_registry():
    import leap2_s6_study as ST
    idx = pd.bdate_range("2020-01-06", periods=4)
    fa = {"A.T": pd.DataFrame({"entry": True}, index=idx)}
    vr = {"A.T": np.array([3.0, 1.0, np.nan, 2.5])}
    beta = {"A.T": np.array([0.5, 0.5, 0.5, np.nan])}
    k = ST.candidate_keep(fa, vr, beta, 2.0, 0.7)
    assert k["A.T"].tolist() == [True, False, False, False]                                    # 缺值 → 不买
    assert set(ST.CANDS) == {"K1", "K2", "K3"} and len(ST.CANDS) <= 5
    assert [ST.CANDS[c][1:] for c in ("K1", "K2", "K3")] == [(2.184, 0.78), (2.0, 0.70), (2.0, 0.78)]
