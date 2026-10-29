"""市场风险报告的判断放到过去的指数里（scripts/report_judgment_backtest.py 登记检验）：红线只用当时已知的数据（as-of / 滞后 / 过旧不用）、
各红线的定义、行动映射、结果（次日崩盘 / 5〜60 日 / 20 日内跌 5%）、照着做的净值与成本、循环平移、判定 V1〜V4、报告时段对齐、
Ken French 日度表解析，以及整条流水线截断数据后状态不变（没有前视）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import report_judgment_backtest as R                                         # noqa: E402


def test_constants_and_reports():
    assert R.ERAS["A"] == ("1990-01-01", "2000-12-31") and R.ERAS["E"] == ("2006-10-01", "2016-09-30") and R.ERAS["J"][0] == "2017-01-01"
    assert (R.NH_WIN, R.NH_RECENT, R.VIX_LVL, R.VIX_JUMP, R.EVENT_DAYS) == (252, 10, 22.0, 0.20, 5)
    assert (R.CR_WIN, R.CR_REF, R.CR_Q, R.SOX_DROP, R.BREADTH_MA, R.BREADTH_TH) == (63, 756, 0.90, -0.05, 50, 25.0)
    assert (R.OIL_WIN, R.OIL_UP, R.FX_DOWN_WIN, R.FX_DOWN, R.N225_WIN, R.N225_DD) == (63, 0.25, 20, -0.04, 63, 0.92)
    assert (R.JP_SEMI_DROP, R.JP_BREADTH_DOWN, R.JP_BREADTH_MIN, R.ADD_DD, R.CRASH, R.HS) == (-0.03, 70.0, 100, 0.10, -0.03, (5, 20, 60))
    assert (R.WEEK_WIN, R.WEEK_REF, R.WEEK_REF_MIN, R.WEEK_Q) == (5, 756, 252, 0.10)
    assert (R.V1_GAP, R.V2_RATIO, R.V3_CAL, R.ERAS_NEED, R.MIN_DAYS_ERA, R.BOOT, R.PLACEBO_SEEDS) == (-1.0, 1.5, 0.05, 3, 60, 2000, 200)
    assert R.EXPO == {"加仓观察": 1.0, "观望": 1.0, "减仓观察": 0.5, "避险": 0.0} and R.CORE == {"US": ("U1", "U3"), "JP": ("J1", "J2")}
    assert len(R.REPORTS) == 27
    times = [pd.Timestamp(r[0]) for r in R.REPORTS]
    assert times == sorted(times)
    acts = [r[2] for r in R.REPORTS]
    assert acts[:10] == ["观望"] * 10 and acts[10:16] == ["减仓观察"] * 6 and acts[16:] == ["避险"] * 11
    assert all(r[1] in ("早报", "晚报") for r in R.REPORTS) and all(len(r) == 13 for r in R.REPORTS)


def test_asof_lag_and_stale():
    s = pd.Series([1.0, 2.0, np.nan, 4.0], index=pd.DatetimeIndex(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"]))
    days = pd.DatetimeIndex(["2019-12-31", "2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07", "2020-01-20"])
    a = R.asof(s, days)
    assert np.isnan(a.iloc[0]) and a.iloc[1] == 2.0 and a.iloc[2] == 2.0 and a.iloc[3] == 4.0 and a.iloc[4] == 4.0
    assert np.isnan(a.iloc[5])                                                     # 最后一个值比那天早 14 天 > 10 天 → 不用
    b = R.asof(s, days, lag_days=1)
    assert b.iloc[1] == 1.0 and b.iloc[3] == 2.0 and b.iloc[4] == 4.0              # 只用 ≤ day − 1 的值


def test_new_high_recent_and_no_lookahead():
    d = pd.bdate_range("2020-01-01", periods=400)
    s = pd.Series(np.r_[np.linspace(1, 2, 250), np.full(150, 1.5)], index=d)
    s.iloc[300] = 2.5                                                              # 第 300 天创新高
    f = R.new_high_recent(s)
    assert not f.iloc[:199].any()                                                  # 窗口不够 200 天 → 不判
    assert f.iloc[299] == False and f.iloc[300] and f.iloc[309] and not f.iloc[310]  # noqa: E712  10 个交易日内
    s2 = s.copy()
    s2.iloc[350:] = 9.0                                                            # 改未来
    assert R.new_high_recent(s2).iloc[:350].equals(f.iloc[:350])


def test_recent_vix_spike_oil_fx_index():
    d = pd.bdate_range("2020-01-01", periods=8)
    ev = pd.Series([False, True, False, False, False, False, False, False], index=d)
    assert R.recent(ev).tolist() == [False, True, True, True, True, True, False, False]
    v = pd.Series([20.0, 24.5, 25.0, 31.0, 21.0, 26.0, 26.0, 26.0], index=d)
    assert R.vix_spike(v).tolist() == [False, True, False, True, False, True, False, False]    # 24.5 +22.5%、31 +24%、26 +23.8%（都 ≥ 22）
    v2 = pd.Series([15.0, 18.5, 21.9], index=d[:3])
    assert not R.vix_spike(v2).any()                                               # +23% 但 < 22 / +18% → 都不算
    n = 70
    di = pd.bdate_range("2020-01-01", periods=n)
    b = pd.Series(np.r_[np.full(64, 80.0), np.full(6, 101.0)], index=di)
    o = R.oil_spike(b)
    assert not o.iloc[:64].any() and o.iloc[64]                                    # 63 日前 80 → 101 = +26%
    c = pd.Series(np.r_[np.full(63, 100.0), [93.0, 91.0]], index=di[:65])
    ib = R.index_break(c)
    assert ib.tolist()[-2:] == [False, True] and not ib.iloc[:63].any()            # ≤ 63 日最高的 92%
    fx = pd.Series(np.r_[np.linspace(160, 150, 300), np.linspace(150, 143, 21)], index=pd.bdate_range("2019-01-01", periods=321))
    fl = R.fx_line(fx)
    assert not fl.iloc[200:300].any() and fl.iloc[-1]                              # 慢慢升值不算；20 日 −4.7%（急升值）→ 亮
    fx2 = pd.Series(np.linspace(140, 150, 300), index=pd.bdate_range("2019-01-01", periods=300))
    fl2 = R.fx_line(fx2)
    assert not fl2.iloc[:199].any() and fl2.iloc[250]                              # 日元一路变弱 → 52 周新高 → 亮


def test_credit_widening_uses_past_only():
    d = pd.bdate_range("2015-01-01", periods=1200)
    rng = np.random.default_rng(1)
    sp = pd.Series(2.0 + np.cumsum(rng.normal(0, 0.01, 1200)), index=d)
    sp.iloc[1100:1110] += np.linspace(0, 1.0, 10)                                  # 急扩大
    w = R.credit_widening(sp)
    assert not w.iloc[:R.CR_WIN + R.CR_REF_MIN - 1].any()                          # 参照不够 252 个 → 不判
    assert w.iloc[1105:1110].any()
    sp2 = sp.copy()
    sp2.iloc[1150:] += 5
    assert R.credit_widening(sp2).iloc[:1150].equals(w.iloc[:1150])


def test_breadth_semis_breadth_down():
    d = pd.bdate_range("2020-01-01", periods=60)
    up = pd.Series(1.0, index=d)
    dn = pd.Series(-1.0, index=d)
    r = pd.DataFrame({"a": up, "b": up, "c": dn, "d": dn})
    b = R.breadth_above_ma(r)
    assert b.iloc[:49].isna().all() and b.iloc[55] == 50.0
    rets = pd.DataFrame({"6857.T": [-0.04, -0.04, -0.01], "8035.T": [-0.05, -0.03, -0.05], "9984.T": [-0.03, np.nan, -0.06]}, index=d[:3])
    assert R.semis_all_down(rets).tolist() == [True, False, False]                 # 都 ≤ −3%；有缺值不算
    m = pd.DataFrame(np.r_[np.full((1, 100), -0.01), np.full((1, 100), 0.01)], index=d[:2])
    m.iloc[0, :25] = 0.01                                                          # 75% 下跌
    assert R.breadth_down(m).tolist() == [True, False]
    assert not R.breadth_down(m.iloc[:, :99]).any()                                # 不足 100 只 → 不判


def test_heavy_week_uses_past_only():
    d = pd.bdate_range("2015-01-01", periods=600)
    rng = np.random.default_rng(5)
    c = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 600))), index=d)
    c.iloc[500:505] *= np.linspace(0.98, 0.90, 5)                                  # 一周跌 10%
    h = R.heavy_week(c)
    assert not h.iloc[:R.WEEK_WIN + R.WEEK_REF_MIN].any()                          # 参照不够 → 不判
    assert h.iloc[502:505].any() and 0.03 < h.iloc[300:].mean() < 0.2
    c2 = c.copy()
    c2.iloc[550:] *= 0.5
    assert R.heavy_week(c2).iloc[:550].equals(h.iloc[:550])


def test_synth_days_fills_closed_gaps_only():
    import datetime as dt
    df = pd.DataFrame({"Open": [1.0, 2.0], "High": [1.0, 2.0], "Low": [1.0, 2.0], "Close": [1.0, 2.0], "Volume": [0.0, 0.0]},
                      index=pd.DatetimeIndex(["2026-10-01", "2026-10-02"]))
    ix = pd.DatetimeIndex(list(pd.date_range("2026-10-05 09:00", periods=40, freq="5min")) +
                          list(pd.date_range("2026-10-06 09:00", periods=40, freq="5min"))).tz_localize("Asia/Tokyo")
    bars = pd.DataFrame({"Open": np.arange(80.0), "High": np.arange(80.0) + 0.5, "Low": np.arange(80.0) - 0.5, "Close": np.arange(80.0) + 0.1,
                         "Volume": 1.0}, index=ix)
    out, add = R.synth_days(df, bars, dt.date(2026, 10, 6), False, min_bars=30)
    assert add == ["2026-10-05"] and len(out) == 3                                 # 10-06 还没收盘 → 不补
    row = out.loc["2026-10-05"]
    assert (row["Open"], row["High"], row["Low"], row["Close"], row["Volume"]) == (0.0, 39.5, -0.5, 39.1, 40.0)
    out2, add2 = R.synth_days(df, bars, dt.date(2026, 10, 6), True, min_bars=30)
    assert add2 == ["2026-10-05", "2026-10-06"]
    out3, add3 = R.synth_days(out2, bars, dt.date(2026, 10, 6), True, min_bars=30)
    assert add3 == [] and len(out3) == 4                                           # 已有的不重复补
    assert R.synth_days(df, bars.iloc[:20], dt.date(2026, 10, 6), True, min_bars=30)[1] == []   # 根数不够


def test_action_mapping_and_worse():
    d = pd.date_range("2020-01-01", periods=6)
    red = pd.DataFrame({"U1": [0, 1, 1, 0, 0, 0], "U2": [0, 0, 1, 1, 0, 0], "U3": [0, 0, 0, 0, 0, 0], "U5": [0, 0, 0, 1, 0, 0]}, index=d).astype(bool)
    dd = pd.Series([0.0, 0.0, 0.0, 0.0, -0.12, -0.05], index=d)
    st = R.action(red, ("U1", "U3"), dd)
    assert st.tolist() == ["观望", "减仓观察", "避险", "减仓观察", "加仓观察", "观望"]   # 2 条但没有核心 → 减仓观察
    assert R.worse("观望", "避险") == "避险" and R.worse("减仓观察", "加仓观察") == "减仓观察" and R.worse("观望", "加仓观察") == "观望"


def test_outcomes():
    d = pd.bdate_range("2020-01-01", periods=70)
    c = np.full(70, 100.0)
    lo = c.copy()
    c[1], lo[1] = 99.0, 96.5                                                       # 次日盘中 −3.5%，收盘 −1%
    c[2], lo[2] = 97.0, 97.0
    df = pd.DataFrame({"Close": c, "Low": lo}, index=d)
    o = R.outcomes(df)
    assert o["crash1"].iloc[0] == 1.0 and o["crash1c"].iloc[0] == 0.0
    assert o["crash1"].iloc[1] == 0.0                                              # 99 → 97 = −2.0%
    assert abs(o["r5"].iloc[0] - 0.0) < 1e-9 and abs(o["r5"].iloc[1] - (100 / 99 - 1) * 100) < 1e-9
    assert o["dd20"].iloc[0] == 0.0 and abs(o["mdd20"].iloc[0] - (-3.0)) < 1e-9  # 收盘最低 97 = −3%（盘中不算）
    assert np.isnan(o["crash1"].iloc[-1]) and not np.isnan(o["r5"].iloc[-6]) and np.isnan(o["r5"].iloc[-5])
    assert np.isnan(o["dd60"].iloc[10]) and not np.isnan(o["dd60"].iloc[9])        # 60 日窗口要满
    df2 = df.copy()
    df2.iloc[1, df2.columns.get_loc("Low")] = 0.0                                  # 坏的盘中最低 → 只看收盘
    assert R.outcomes(df2)["crash1"].iloc[0] == 0.0


def test_outcome_crash_on_close():
    d = pd.bdate_range("2020-01-01", periods=5)
    df = pd.DataFrame({"Close": [100.0, 96.9, 97.0, 97.0, 97.0], "Low": [100.0, 98.0, 97.0, 97.0, 97.0]}, index=d)
    o = R.outcomes(df)
    assert o["crash1"].iloc[0] == 1.0 and o["crash1c"].iloc[0] == 1.0             # 收盘 −3.1%


def test_strategy_returns_lag_and_cost():
    d = pd.bdate_range("2020-01-01", periods=5)
    st = pd.Series(["观望", "避险", "避险", "减仓观察", "观望"], index=d)
    rin = pd.Series([0.0, 0.01, 0.02, 0.03, 0.04], index=d)
    rc = pd.Series(0.001, index=d)
    r = R.strategy_returns(st, rin, rc)
    assert abs(r.iloc[1] - 0.01) < 1e-12                                           # 第 0 天观望 → 第 1 天还拿着
    assert abs(r.iloc[2] - (0.001 - R.COST)) < 1e-12                               # 第 1 天收盘避险 → 第 2 天现金，换仓 1 单位
    assert abs(r.iloc[3] - 0.001) < 1e-12
    assert abs(r.iloc[4] - (0.5 * 0.04 + 0.5 * 0.001 - 0.5 * R.COST)) < 1e-12


def test_curve_stats_and_placebo_keeps_counts():
    d = pd.bdate_range("2010-01-01", periods=800)
    rng = np.random.default_rng(3)
    rin = pd.Series(rng.normal(0.0004, 0.01, 800), index=d)
    rc = pd.Series(0.0, index=d)
    st = pd.Series(np.where(rng.random(800) < 0.2, "避险", "观望"), index=d)
    cs = R.curve_stats(rin)
    assert cs["mdd"] < 0 and abs(cs["calmar"] - cs["cagr"] / abs(cs["mdd"])) < 0.01
    assert R.curve_stats(rin.iloc[:30])["calmar"] is None
    pl = R.placebo_calmar(st, rin, rc, seeds=10)
    assert len(pl) == 10 and len(set(pl)) > 1
    k = 300
    sh = pd.Series(np.roll(st.to_numpy(), k), index=d)
    assert (sh == "避险").sum() == (st == "避险").sum()


def test_boot_compare_and_rate():
    d = pd.bdate_range("2020-01-01", periods=120)
    st = pd.Series(np.where(np.arange(120) % 2 == 0, "避险", "观望"), index=d)
    v = pd.Series(np.where(st == "避险", -1.0, 1.0), index=d)
    m = np.ones(120, bool)
    bc = R.boot_compare(st, v, m, "避险", "观望", "diff", n=50)
    assert bc["est"] == -2.0 and bc["lo"] == -2.0 and bc["hi"] == -2.0
    v2 = pd.Series(np.where(st == "避险", 0.4, 0.2), index=d)
    br = R.boot_compare(st, v2, m, "避险", "观望", "ratio", n=50)
    assert abs(br["est"] - 2.0) < 1e-9
    assert R.boot_compare(st, v, m, "避险", "加仓观察", "diff", n=5)["est"] is None
    rate = R.boot_rate(pd.Series(np.r_[np.ones(10), np.zeros(110)], index=d), m, n=200)
    assert abs(rate["est"] - 100 * 10 / 120) < 0.01 and rate["lo"] <= rate["est"] <= rate["hi"] and rate["n"] == 120


def _era_tab(hx, gw):
    return {"tab": {"避险": {"n": hx}, "观望": {"n": gw}}}


def test_verdict_market():
    by = {e: dict(_era_tab(100, 100), diff20={"est": -1.5}, ratio20={"est": 1.6}) for e in R.ERAS}
    full = {"diff20": {"hi": -0.2}, "ratio20": {"lo": 1.1}}
    strat = {e: {"E1": {"calmar": 0.6}, "BH": {"calmar": 0.5}} for e in list(R.ERAS) + ["FULL"]}
    v = R.verdict_market(by, full, strat, pl95=0.55)
    assert v["V1"] == "准" and v["V2"] == "准" and v["V3"] == "有用" and len(v["eras"]) == 4
    full2 = {"diff20": {"hi": 0.1}, "ratio20": {"lo": 0.9}}
    v2 = R.verdict_market(by, full2, strat, pl95=0.65)
    assert v2["V1"] == "不准" and v2["V2"] == "不准" and v2["V3"] == "没用"
    by3 = {e: dict(_era_tab(30 if e != "J" else 100, 100), diff20={"est": -2.0}, ratio20={"est": 2.0}) for e in R.ERAS}
    assert R.verdict_market(by3, full, strat, 0.55)["V1"] == "样本不够"
    by4 = dict(by)
    by4["A"] = dict(_era_tab(100, 100), diff20={"est": -0.5}, ratio20={"est": 1.2})
    by4["Z"] = dict(_era_tab(100, 100), diff20={"est": 0.5}, ratio20={"est": 1.0})
    assert R.verdict_market(by4, full, strat, 0.55)["V1"] == "不准"                 # 只有 2 个年代满足
    strat2 = dict(strat)
    strat2["A"] = {"E1": {"calmar": 0.52}, "BH": {"calmar": 0.5}}
    strat2["Z"] = {"E1": {"calmar": 0.52}, "BH": {"calmar": 0.5}}
    assert R.verdict_market(by, full, strat2, 0.55)["V3"] == "没用"                 # 高不到 0.05 的年代不算


def test_calib():
    ci = {"est": 2.0, "lo": 1.5, "hi": 2.6, "n": 500}
    assert R.calib(10.0, ci) == "过高" and R.calib(1.0, ci) == "过低" and R.calib(2.0, ci) == "大致合理" and R.calib(None, ci) is None
    assert R.calib(10.0, dict(ci, n=59)) == "样本不够"


def test_report_sessions():
    us = pd.DatetimeIndex(["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"])
    jp = pd.DatetimeIndex(["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-24"])
    e = R.report_sessions(pd.Timestamp("2026-09-17 07:40"), "早报", us, jp)
    assert us[e["us_next"]] == pd.Timestamp("2026-09-17") and us[e["us_prev"]] == pd.Timestamp("2026-09-16")
    assert jp[e["jp_next"]] == pd.Timestamp("2026-09-17") and jp[e["jp_prev"]] == pd.Timestamp("2026-09-16")
    v = R.report_sessions(pd.Timestamp("2026-09-18 22:25"), "晚报", us, jp)
    assert us[v["us_next"]] == pd.Timestamp("2026-09-18") and us[v["us_prev"]] == pd.Timestamp("2026-09-17")
    assert jp[v["jp_next"]] == pd.Timestamp("2026-09-24") and jp[v["jp_prev"]] == pd.Timestamp("2026-09-18")   # 跨日本连休
    z = R.report_sessions(pd.Timestamp("2026-09-19 07:40"), "早报", us, jp)
    assert z["us_next"] is None


def test_report_rows(monkeypatch):
    d = pd.DatetimeIndex(["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23"])
    us = pd.DataFrame({"Close": [100.0, 100.0, 98.0, 99.0, 99.0, 99.0, 99.0], "Low": [100.0, 96.0, 97.0, 99.0, 99.0, 99.0, 99.0]}, index=d)
    jp = us.copy()
    st = pd.Series(["观望", "避险", "观望", "观望", "观望", "观望", "观望"], index=d)
    st2 = pd.Series("减仓观察", index=d)
    monkeypatch.setattr(R, "REPORTS", [("2026-09-16 07:40", "早报", "避险", 12, 3, 2, 3, 1, 8, 2, 3, 2, 2)])
    rows = R.report_rows(us, jp, st, st2)
    r = rows[0]
    assert r["us_date"] == "2026-09-16" and r["us_crash"] == 1 and r["us_next"] == 0.0     # 盘中 −4%
    assert r["us_r5"] == -1.0 and r["us_proxy"] == "观望" and r["jp_proxy"] == "减仓观察" and r["proxy"] == "减仓观察"


def test_parse_ff_daily():
    txt = ("This file was created ...\n\n  Average Value Weighted Returns -- Daily\n,Agric,Food ,Soda \n"
           "19260701,   0.56,  -0.07, -99.99\n19260702,   1.00,   0.20,   0.30\n\n  Average Equal Weighted Returns -- Daily\n,Agric,Food ,Soda \n"
           "19260701,   9.00,   9.00,   9.00\n")
    df = R.parse_ff_daily(txt)
    assert list(df.columns) == ["Agric", "Food", "Soda"] and len(df) == 2
    assert df.index[0] == pd.Timestamp("1926-07-01") and np.isnan(df.iloc[0, 2]) and df.iloc[1, 0] == 1.0


def test_episodes_and_analog_starts():
    st = pd.Series(["避险"] * 6 + ["观望"] * 3 + ["避险"] * 2 + ["观望"] + ["避险"] * 5)
    assert R.episodes(st, "避险") == [(0, 5), (12, 16)]
    f = pd.Series([True, False, True] + [False] * 25 + [True])
    assert R.analog_starts(f, gap=20) == [0, 28]


def test_on_days():
    src = pd.Series([False, True, False], index=pd.DatetimeIndex(["2020-01-06", "2020-01-07", "2020-01-08"]))
    days = pd.DatetimeIndex(["2020-01-07", "2020-01-08", "2020-01-09"])
    assert R.on_days(src, days).tolist() == [True, False, False]
    assert R.on_days(src, days, lag_days=1).tolist() == [False, True, False]


# ───────── 整条流水线：截断数据后，截断点以前的红线与状态完全不变（没有前视） ─────────
def _synthetic_inputs(n=1100, seed=7):
    rng = np.random.default_rng(seed)
    d = pd.bdate_range("1989-03-01", periods=n)
    mkt = rng.normal(0.0002, 0.012, n)
    mkt[600:610] = -0.04                                                           # 一段急跌（让红线亮起来）

    def ohlc(beta=1.0, vol=0.01, start=100.0, drop=None):
        r = beta * mkt + rng.normal(0, vol, n)
        c = start * np.exp(np.cumsum(r))
        lo = c * (1 - np.abs(rng.normal(0, 0.01, n)))
        df = pd.DataFrame({"Open": c, "High": c * 1.005, "Low": lo, "Close": c, "Volume": 1e6}, index=d)
        return df.drop(df.index[drop]) if drop is not None else df
    jp_holidays = [5, 50, 51, 300, 700]
    idx = {t: ohlc() for t in ["^GSPC", "^IXIC", "^SP500TR", "^SOX"]}
    idx["^N225"] = ohlc(drop=jp_holidays)
    for t in R.JP_SEMI:
        idx[t] = ohlc(beta=2.0, drop=jp_holidays)
    v = 18 * np.exp(np.cumsum(rng.normal(0, 0.06, n)) * 0.3)
    v[600:603] = [24.0, 30.0, 38.0]
    idx["^VIX"] = pd.DataFrame({"Open": v, "High": v, "Low": v, "Close": v, "Volume": 0.0}, index=d)
    fred = {"us10y": pd.Series(5 + np.cumsum(rng.normal(0, 0.04, n)), index=d),
            "baa": pd.Series(2 + np.cumsum(rng.normal(0, 0.02, n)), index=d),
            "brent": pd.Series(60 * np.exp(np.cumsum(rng.normal(0, 0.02, n))), index=d),
            "dff": pd.Series(3.0, index=d),
            "usdjpy": pd.Series(140 * np.exp(np.cumsum(rng.normal(0, 0.006, n))), index=d)}
    jgb = pd.Series(1 + np.cumsum(rng.normal(0, 0.02, n)), index=d)
    ff = pd.DataFrame(100 * (mkt[:, None] + rng.normal(0, 0.008, (n, 49))), index=d, columns=[f"I{i}" for i in range(49)])
    mem = {f"{1000 + i}.T": ohlc(drop=jp_holidays) for i in range(110)}
    return {"idx": idx, "fred": fred, "jgb": jgb, "ff": ff, "mem": mem}


def _cut(inp, T):
    c = lambda x: x.loc[:T]                                                        # noqa: E731
    return {"idx": {k: c(v) for k, v in inp["idx"].items()}, "fred": {k: c(v) for k, v in inp["fred"].items()},
            "jgb": c(inp["jgb"]), "ff": c(inp["ff"]), "mem": {k: c(v) for k, v in inp["mem"].items()}}


@pytest.mark.parametrize("T", ["1991-06-14", "1992-01-31"])
def test_build_no_lookahead(T):
    inp = _synthetic_inputs()
    full, cut = R.build(inp), R.build(_cut(inp, T))
    for k in ("U", "J"):
        a, b = full[k].loc[:T], cut[k]
        assert a.index.equals(b.index) and (a.astype(bool) == b.astype(bool)).all().all(), k
    for k in ("st_us", "st_jp", "st_all"):
        assert full[k].loc[:T].equals(cut[k]), k
    assert full["U"].any().any() and full["J"].any().any()                          # 红线确实会亮
    assert set(full["st_us"].unique()) >= {"观望", "减仓观察"} and full["st_us"].index[0] >= pd.Timestamp(R.START)


def test_build_alignment_and_counts():
    inp = _synthetic_inputs()
    B = R.build(inp)
    assert B["st_all"].index.equals(B["jp"].index) and B["st_us"].index.equals(B["us"].index)
    for t in B["jp"].index[100:110]:                                                # 总行动 = 日本 t 与它之前最后一个美国日 取更严的
        up = B["st_us"].loc[:t - pd.Timedelta(days=1)]
        exp = R.worse(B["st_jp"].loc[t], up.iloc[-1]) if len(up) else B["st_jp"].loc[t]
        assert B["st_all"].loc[t] == exp
    c = R.counts(B)
    assert sum(c["US"]["A"].values()) == int(R.in_era(B["st_us"].index, "A").sum())
    assert set(c["lines"]["US"]) == set(R.US_LINES) and set(c["lines"]["JP"]) == set(R.JP_LINES)


def test_run_and_report_end_to_end_on_synthetic():
    inp = _synthetic_inputs()
    res = R.run(say=lambda *a: None, inp=inp)
    for m in ("US", "JP"):
        v = res["markets"][m]["verdict"]
        assert v["V1"] in ("准", "不准", "样本不够") and v["V3"] in ("有用", "没用")
        assert set(res["calib"][m]) == {"观望", "减仓观察", "避险"}
    assert len(res["reports"]) == 27 and all(r.get("us_crash") is None for r in res["reports"])   # 合成数据只到 1993 → 报告期没有结果
    md = R.report(res)
    assert md.startswith("# 市场风险报告的判断") and "## 六、" in md and "非投资建议" in md
    import json
    json.dumps(res, ensure_ascii=False, default=str)
