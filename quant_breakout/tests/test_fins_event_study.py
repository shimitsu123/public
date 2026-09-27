"""scripts/fins_event_study.py：候选选取、同票去重、对照抽样（只用过去信息 / 有界持仓）、统计 / 判定、逐笔机制（合成面板、单进程）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fins_event_study as ST  # noqa: E402


def _events():
    d = pd.Timestamp
    base = dict(first=True, fy12=True, retro=False, chg_acc=False, chg_sub=False, chg_scope=False, listed_t0=1.0, pos=True, per="1Q",
                doc="1QFinancialStatements_Consolidated_JP", yoy=np.nan, g_next=np.nan, beat=np.nan, react=np.nan, vr_r=np.nan, lot_yen=1e5, va20=1e8,
                mc=1e10, gap_t0=1.0, after_close=True, split_near=0.0, rev_np=5.0, up_r=np.nan)
    rows = [
        dict(base, ticker="1234.T", sig_day=d("2018-05-10"), t0=d("2018-05-11"), r=d("2018-05-11"), rev=15.0, yoy=20.0),       # C1 / C2
        dict(base, ticker="1234.T", sig_day=d("2018-05-20"), t0=d("2018-05-21"), r=d("2018-05-21"), rev=25.0, doc="EarnForecastRevision"),  # 20 日内 → 去重
        dict(base, ticker="1234.T", sig_day=d("2018-08-10"), t0=d("2018-08-13"), r=d("2018-08-10"), rev=12.0, react=4.0, vr_r=3.0, up_r=1.0, after_close=False),  # C3
        dict(base, ticker="5678.T", sig_day=d("2018-05-10"), t0=d("2018-05-11"), r=d("2018-05-11"), rev=400.0),                 # 极端 → 不算
        dict(base, ticker="5678.T", sig_day=d("2018-06-10"), t0=d("2018-06-11"), r=d("2018-06-11"), rev=0.0, rev_np=0.0, yoy=3.0),   # P3 信息对照
        dict(base, ticker="5678.T", sig_day=d("2018-06-20"), t0=d("2018-06-21"), r=d("2018-06-21"), rev=0.0, rev_np=0.0, yoy=3.0),   # 同日另一行上修 → 不是重申
        dict(base, ticker="5678.T", sig_day=d("2018-06-20"), t0=d("2018-06-21"), r=d("2018-06-21"), rev=30.0, doc="EarnForecastRevision"),
        dict(base, ticker="5678.T", sig_day=d("2018-07-10"), t0=d("2018-07-11"), r=d("2018-07-11"), rev=-30.0),                  # 方向对照
        dict(base, ticker="9999.T", sig_day=d("2018-05-15"), t0=d("2018-05-16"), r=d("2018-05-16"), rev=np.nan, per="FY",
             doc="FYFinancialStatements_Consolidated_JP", g_next=18.0, beat=2.0, pos=False, yoy=1.0),                          # C5
        dict(base, ticker="9999.T", sig_day=d("2019-05-15"), t0=d("2019-05-16"), r=d("2019-05-16"), rev=np.nan, per="FY",
             doc="FYFinancialStatements_Consolidated_JP", g_next=30.0, beat=-5.0, pos=False, yoy=1.0),                         # beat < 0 → 不算
        dict(base, ticker="9999.T", sig_day=d("2020-05-15"), t0=d("2020-05-18"), r=d("2020-05-18"), rev=np.nan, per="FY",
             doc="FYFinancialStatements_Consolidated_JP", g_next=2.0, beat=1.0, pos=False, yoy=1.0),                           # C5 的信息对照
        dict(base, ticker="5678.T", sig_day=d("2018-09-10"), t0=d("2018-09-11"), r=d("2018-09-11"), rev=15.0, split_near=1.0),   # 拆股当周 → 池外
        dict(base, ticker="1234.T", sig_day=d("2020-05-10"), t0=d("2020-05-11"), r=d("2020-05-11"), rev=50.0, first=False),      # 订正 → 池外
        dict(base, ticker="1234.T", sig_day=d("2023-05-10"), t0=d("2023-05-11"), r=d("2023-05-11"), rev=50.0),                  # C 窗口
    ]
    return pd.DataFrame(rows)


def test_pool_select_and_dedupe():
    E = ST.pool(_events())
    assert len(E) == 12                                                             # 订正行、拆股当周被排除
    days = pd.bdate_range("2018-01-01", "2023-12-31")
    c1 = ST.select(E, "C1")
    assert set(zip(c1["ticker"], c1["sig_day"].dt.strftime("%Y-%m-%d"))) == {("1234.T", "2018-05-10"), ("1234.T", "2018-05-20"), ("1234.T", "2018-08-10"),
                                                                                ("1234.T", "2023-05-10"), ("5678.T", "2018-06-20")}
    assert (c1["buy_sig"] == c1["sig_day"]).all() and c1["prio"].max() <= 100
    c1d = ST.dedupe(c1, days)
    assert len(c1d) == 4 and "2018-05-20" not in set(c1d["sig_day"].dt.strftime("%Y-%m-%d"))
    c2 = ST.select(E, "C2")
    assert len(c2) == 1 and c2.iloc[0]["sig_day"] == pd.Timestamp("2018-05-10")
    assert len(ST.select(E.assign(rev_np=-1.0), "C2")) == 0                          # 净利润予想下修 → 不算印证
    c3 = ST.select(E, "C3")
    assert len(c3) == 1 and c3.iloc[0]["buy_sig"] == pd.Timestamp("2018-08-10")   # 盘中开示 → r = 当天
    assert len(ST.select(E.assign(up_r=0.0), "C3")) == 0                             # 收阴 → 不算确认
    c5 = ST.select(E, "C5")
    assert len(c5) == 1 and c5.iloc[0]["ticker"] == "9999.T" and np.isclose(c5.iloc[0]["prio"], 18.0)
    assert len(ST.select(E, "C4")) == len(c1)
    n3 = ST.neutral(E)
    assert len(n3) == 1 and n3.iloc[0]["sig_day"] == pd.Timestamp("2018-06-10")     # 06-20 同日有上修 → 不是重申
    assert len(ST.neutral(E, "C3")) == 0 and len(ST.neutral(E, "C5")) == 1 and len(ST.down(E)) == 1
    assert ST.in_window(c1["sig_day"], ST.WIN_X).sum() == 4
    A = _panel(); days2 = pd.DatetimeIndex(A["days"])
    E2 = pd.DataFrame({"ticker": ["1234.T", "1234.T"], "t0": [days2[50], days2[200]]})
    assert list(ST.hist_days(A, E2)) == [50, 200]
    assert ST.eff_range(pd.DataFrame({"sig_date": pd.to_datetime(["2018-03-01", "2019-06-01", "2023-01-01"])}), ST.WIN_X) == ("2018-03-01", "2019-06-01")


def test_stats_gate_fails_pick():
    T = pd.DataFrame({"sig_date": pd.to_datetime(["2018-01-10", "2018-02-10", "2023-01-10"]), "net": [2.0, -1.0, 3.0], "hold_days": [5, 6, 7]})
    s = ST.stats(T, ST.WIN_X)
    assert s["n"] == 2 and np.isclose(s["win"], 50.0) and np.isclose(s["mean"], 0.5)
    assert ST.stats(pd.DataFrame(), ST.WIN_X)["n"] == 0
    c, base = {"win": 45.0, "mean": 1.4, "n": 1000}, {"win": 35.0, "mean": 0.3, "n": 3000}
    q = {"P0": {"win": 38.0, "mean": 0.5, "q": 99}, "PL-B": {"win": 40.0, "mean": 0.6, "q": 99}}
    assert ST.s_fails(c, base, q, {"win": 40.0, "mean": 0.8}, None, None, diff_lo=0.2) == []
    f = ST.s_fails({"win": 41.0, "mean": 1.4, "n": 250}, base, q, {"win": 40.0, "mean": 0.8}, {"calmar": 0.5, "dd": -30.0, "n": 10},
                   {"calmar": 0.6, "dd": -25.0, "n": 47}, diff_lo=-0.1)
    assert any(x.startswith("S1") for x in f) and any(x.startswith("S3") for x in f) and sum(x.startswith("S4") for x in f) == 3
    assert sum(x.startswith("S2") for x in f) == 1                                    # 点估计过、区间下限不过
    f4 = ST.s_fails({"win": 30.0, "mean": 1.4, "n": 1000}, base, q, {"win": 40.0, "mean": 0.8}, None, None, no_s1=True)
    assert f4 == []                                                                   # C4 免胜率类条件
    assert ST.improve_ok({"win": 41.0, "mean": 1.0, "n": 800}, base, q, {"win": 35.0, "mean": 0.3}, [])
    assert not ST.improve_ok({"win": 41.0, "mean": 1.0, "n": 800}, base, q, {"win": 40.0, "mean": 0.8}, [])   # P3 不过
    assert not ST.improve_ok({"win": 41.0, "mean": 1.0, "n": 800}, base, q, {"win": 35.0, "mean": 0.3}, ["P1 x"])
    assert ST.gate_x({"mean": 0.9, "win": 36.0}, base, {"mean": 0.5}, {"mean": 0.7}, 0.6, {"mean": 0.65})
    assert not ST.gate_x({"mean": 0.7, "win": 36.0}, base, {"mean": 0.5}, {"mean": 0.7}, 0.6, {"mean": 0.65})   # 每笔 < 基准 + 0.5
    assert not ST.gate_x({"mean": 0.9, "win": 34.0}, base, {"mean": 0.5}, {"mean": 0.7}, 0.6, {"mean": 0.65})   # 胜率 < 基准
    assert not ST.gate_x({"mean": 0.9, "win": 36.0}, base, {"mean": 0.5}, {"mean": 0.5}, 0.6, {"mean": 0.3})    # 20 日卖法 ≤ P1
    assert ST.p1_fails({"mean": 1.5}, {"mean_lo": 0.6}, 0.4) == [] and len(ST.p1_fails({"mean": 1.2}, {"mean_lo": 0.3}, 0.4)) == 2
    qq = ST.quantiles([{"win": 30.0, "mean": 0.1}, {"win": 40.0, "mean": 0.3}, {"win": 50.0, "mean": 0.5}], 50)
    assert np.isclose(qq["win"], 40.0) and np.isclose(qq["mean"], 0.3) and qq["seeds"] == 3
    runs = [{"win": 30.0 + i % 3, "mean": 0.1 * (i % 5)} for i in range(30)]
    qp = ST.quantiles(runs, 99, parametric=True)
    ws = np.array([r["win"] for r in runs]); assert np.isclose(qp["win"], ws.mean() + 2.462 * ws.std(ddof=1), atol=0.01) and qp["kind"] == "param"
    assert np.isclose(ST.t_quantile(0.99, 29), 2.462) and 2.462 < ST.t_quantile(0.99, 24) < 2.539
    T2 = pd.DataFrame({"sig_date": pd.date_range("2018-01-01", periods=60, freq="D"), "net": np.r_[np.ones(30), -np.ones(30)] * 2, "hold_days": 5})
    b = ST.cluster_boot(T2, ST.WIN_X, n=200)
    assert b["mean_lo"] <= 0 <= b["mean_hi"]
    T3 = T2.assign(net=T2["net"] + 3.0)
    assert ST.diff_lower(T3, T2, ST.WIN_X) > 0 and ST.diff_lower(T2, T3, ST.WIN_X) < 0


def _panel(n=400, seed=1):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2017-01-02", periods=n)
    c = 1000 * np.cumprod(1 + rng.normal(0, 0.01, (n, 3)), axis=0)
    V = np.full((n, 3), 1e5)
    return {"days": days, "names": ["1234.T", "5678.T", "9999.T"], "O": c * 0.999, "H": c * 1.01, "L": c * 0.99, "C": c, "V": V,
            "R": np.full((n, 3), 0.5), "VA": np.full((n, 3), 5e8), "MC": np.full((n, 3), 1e10), "listed": np.ones((n, 3), bool)}


def test_placebos_and_trades_on_synthetic_panel():
    from qbreak.trader import load_params
    A = _panel()
    days = pd.DatetimeIndex(A["days"])
    D_all = pd.DataFrame({"ticker": ["1234.T", "5678.T"], "sig_day": [days[200], days[205]]})
    quiet = ST.quiet_matrix(D_all, days, list(A["names"]))
    assert not quiet[200, 0] and not quiet[210, 0] and quiet[211, 0] and quiet[199, 0] and quiet[200, 2]   # 只看过去 10 日：开示前一天安静
    assert quiet[200, 1] and not quiet[205, 1]                                          # 5678 在 205 开示 → 200 那天还安静
    busy1 = ~ST.quiet_matrix(D_all, days, list(A["names"]), back=ST.PRE_BACK, fwd=ST.PRE_FWD)
    assert busy1[175, 0] and busy1[205, 0] and not busy1[174, 0] and not busy1[206, 0]  # [买入日−5, 买入日+25] 含开示 → 不能当 P1 买入日
    S = pd.DataFrame({"ticker": ["1234.T"], "buy_sig": [days[200]], "prio": [10.0]})
    hist = ST.hist_matrix(A)
    pa = ST.placebo_sameday(S, A, quiet, 0, hist)
    assert set(pa) <= {"5678.T", "9999.T"} and list(pa.values())[0] == [days[200]]     # 1234 自己不安静
    hist2 = hist.copy(); hist2[:, 1] = 0
    assert list(ST.placebo_sameday(S, A, quiet, 0, hist2)) == ["9999.T"]                  # 行情不够 120 日 → 不抽
    pp = ST.placebo_pre(S, A, 0, busy1)
    k = days.get_loc(pp["1234.T"][0])
    assert 200 - ST.PRE_LO <= k <= 200 - ST.PRE_HI and not busy1[k, 0]
    feats = ST.day_features(A)
    A2 = dict(A); C2 = A["C"].copy(); C2[150, 0] = C2[149, 0] * 1.05; V2 = A["V"].copy(); V2[150, 0] = 3e5
    A2["C"], A2["V"] = C2, V2
    pm, miss = ST.placebo_matched(S, A2, quiet, ST.day_features(A2), 0)
    assert pm == {"1234.T": [days[150]]} and miss == 0
    O3 = A2["O"].copy(); O3[150, 0] = C2[150, 0] * 1.01; A3 = dict(A2); A3["O"] = O3                       # 收阴 → 不匹配
    assert ST.placebo_matched(S, A3, quiet, ST.day_features(A3), 0) == ({}, 1)
    pm2, miss2 = ST.placebo_matched(S, A, quiet, feats, 0)
    assert pm2 == {} and miss2 == 1
    p = load_params(market="JP")
    ST._FR.clear(); ST._DELIST.clear()
    fr = ST.build_frames(A, p)
    assert set(fr) == set(A["names"])
    T = ST.run_trades({"1234.T": [days[200]], "9999.T": [days[300]]}, p, procs=1)
    assert len(T) == 2 and set(T["ticker"]) == {"1234.T", "9999.T"}
    for r in T.itertuples():
        assert pd.Timestamp(r.entry_date) == days[days.get_loc(pd.Timestamp(r.sig_date)) + 1]
    Sx = pd.DataFrame({"ticker": ["1234.T", "9999.T"], "buy_sig": [days[200], days[300]], "rev": [12.0, 30.0], "doc": ["x", "y"], "lot_yen": [1e5, 4e5],
                       "va20": [1e8, 2e8], "prio": [12.0, 30.0], "after_close": [True, False]})
    Ta = ST.attach(T, Sx)
    assert "ev_rev" in Ta.columns and np.isfinite(Ta["ev_rev"]).all() and np.isfinite(Ta["net"]).all()
    seg = ST.segments(Ta.assign(ev_doc=Ta["ev_doc"], ev_gap_t0=1.0), ("2017-01-01", "2020-12-31"))
    assert seg["一手 ≤ ¥25 万"]["n"] == 1 and seg["可行子集（一手 ≤ ¥34 万 ∧ 成交额 ≥ ¥500 万）"]["n"] == 1 and seg["盘后开示"]["n"] == 1 and seg["修正文档"]["n"] == 0
    t4 = ST.top4_per_day(pd.DataFrame({"ticker": list("abcdef"), "buy_sig": [days[1]] * 6, "prio": [1, 2, 3, 4, 5, 6]}))
    assert len(t4) == 4 and set(t4["ticker"]) == set("cdef")
    T2 = ST.run_trades({"1234.T": [days[200]]}, ST.replace(p, **ST.EVENT_EXIT), procs=1)
    assert len(T2) == 1 and T2.iloc[0]["hold_days"] <= 20 and T2.iloc[0]["reason"] in ("max_hold", "stop")
    A4 = dict(A); O4 = A["O"].copy(); O4[201, 0] = A["C"][200, 0] * 1.05; A4["O"] = O4                      # t0 跳空 +5% → 3% 规则放弃
    ST._FR.clear(); ST._DELIST.clear(); ST.build_frames(A4, p)
    assert len(ST.run_trades({"1234.T": [days[200]]}, p, procs=1)) == 0
    assert len(ST.run_trades({"1234.T": [days[200]]}, p, procs=1, gap=8.0)) == 1                             # 放宽到 8%（只描述）
