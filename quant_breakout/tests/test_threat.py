"""大事件威胁指数（qbreak/threat.py）：只用当时已公布的数据；百分位 / 未来回撤 / AUC 计算正确。"""
import numpy as np
import pytest
import pandas as pd

from qbreak import threat as TH


def test_expanding_pct_basic():
    x = pd.Series([3.0, 1.0, 2.0, np.nan, 5.0])
    p = TH.expanding_pct(x, min_n=1)
    assert p.iloc[0] == 0.5 and p.iloc[1] == 0.25 and abs(p.iloc[2] - 0.5) < 1e-12   # [1,2,3] 里的 2 → 中间
    assert np.isnan(p.iloc[3]) and p.iloc[4] == (3 + 4) / 2 / 4
    assert TH.expanding_pct(x, min_n=4).notna().sum() == 1


def _inputs(n=1500, seed=1):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2010-01-01", periods=n)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))), index=days)
    mk = lambda base, sc: pd.Series(base + np.cumsum(rng.normal(0, sc, n)), index=days)   # noqa: E731
    months = pd.date_range("2008-01-01", periods=80, freq="MS")
    un = pd.Series(5 + np.cumsum(rng.normal(0, 0.1, 80)), index=months)
    return days, close, mk(20, 0.5).clip(9), mk(2, 0.02), mk(3, 0.03), mk(2, 0.03), mk(70, 0.8).clip(10), un, \
        mk(110, 0.4), mk(1, 0.01)


def test_no_lookahead():
    days, close, vix, baa, d10, d3, wti, un, fx, jgb = _inputs()
    raw = TH.raw_features(days, close, vix, baa, d10, d3, wti, un, fx, jgb)
    idx, _ = TH.threat_index(raw, TH.JP_COLS, min_n=200)
    t = 1200
    cut = days[t]
    alt = lambda s: s.where(s.index <= cut, s * 1.5 + 3)                                   # noqa: E731
    published = un.index + pd.offsets.MonthBegin(1) + pd.Timedelta(days=9) <= cut
    raw2 = TH.raw_features(days, alt(close), alt(vix), alt(baa), alt(d10), alt(d3), alt(wti), un.where(published, 99.0),
                           alt(fx), alt(jgb))
    idx2, _ = TH.threat_index(raw2, TH.JP_COLS, min_n=200)
    assert idx.iloc[:t + 1].equals(idx2.iloc[:t + 1]) and idx.iloc[t] == idx.iloc[t]    # 前 t 天完全相同、且有值


def test_forward_drawdown_and_auc():
    c = pd.Series([100, 90, 95, 80, 120, 110.0])
    fd = TH.forward_drawdown(c, 2)
    assert abs(fd.iloc[0] - (90 / 100 - 1)) < 1e-12 and abs(fd.iloc[2] - (80 / 95 - 1)) < 1e-12 and fd.iloc[4:].isna().all()
    s = pd.Series([0.1, 0.2, 0.8, 0.9])
    assert TH.auc(s, pd.Series([0, 0, 1, 1])) == 1.0 and TH.auc(s, pd.Series([1, 1, 0, 0])) == 0.0
    assert TH.auc(pd.Series([0.5, 0.5]), pd.Series([0, 1])) == 0.5


def test_us_asof_for_jp_uses_previous_us_close():
    us = pd.Series([1.0, 2.0, 3.0], index=pd.DatetimeIndex(["2026-09-23", "2026-09-24", "2026-09-25"]))
    jp = pd.DatetimeIndex(["2026-09-24", "2026-09-25", "2026-09-28"])
    v = TH.us_asof_for_jp(us, jp)
    assert list(v) == [1.0, 2.0, 3.0]                                  # 9/28（周一）早上已知的是 9/25（周五）的美国收盘


def test_snapshot_band_top_factors_and_events():
    days = pd.bdate_range("2026-01-01", periods=30)
    idx = pd.Series(np.linspace(40, 55, 30), index=days)
    pct = pd.DataFrame({"oil": 0.96, "rates": 0.95, "vix": 0.2, "curve": 0.64}, index=days)
    table = {"event": "之后 60 个交易日内最低收盘比当天跌 ≥10%",
             "US": {"auc_h1": 0.67, "auc_h2": 0.61, "base_rate": 14.4, "episodes_hit80": [3, 27],
                    "deciles": [{"lo": 40, "hi": 50, "freq": 9.0, "n": 1}, {"lo": 50, "hi": 60, "freq": 17.5, "n": 1}]}}
    ev = [{"date": "2026-02-20", "kind": "FOMC"}, {"date": "2026-06-01", "kind": "BOJ"}, {"date": "2025-12-01", "kind": "CPI"}]
    s = TH.snapshot({"US": (idx, pct), "JP": (pd.Series(dtype=float), pct)}, table, ev, today="2026-02-11")
    u = s["US"]
    assert u["value"] == 55.0 and u["band"] == "50–60" and u["band_freq"] == 17.5 and u["hit80"] == [3, 27]
    assert [f["k"] for f in u["top"]] == ["oil", "rates", "curve"] and "JP" not in s
    assert [e["date"] for e in s["events"]] == ["2026-02-20"]                    # 60 天以内、今天以后


def test_weekly_available_lag():
    s = pd.Series([1.0, 2.0], index=pd.DatetimeIndex(["2026-09-11", "2026-09-18"]))     # 周五参考日
    days = pd.bdate_range("2026-09-21", "2026-09-25")
    a = TH.weekly_available(s, days, 6)
    assert list(a) == [1.0, 1.0, 1.0, 2.0, 2.0]                                        # 9/24（周四）起可用


def _v2_inputs(days, rng):
    mk = lambda base, sc, pos=False: (lambda v: pd.Series(np.abs(v) + 1 if pos else v, index=days))(  # noqa: E731
        base + np.cumsum(rng.normal(0, sc, len(days))))
    weeks = pd.date_range(days[0] - pd.Timedelta(days=400), days[-1], freq="W-FRI")
    wk = lambda base, sc: pd.Series(base + np.cumsum(rng.normal(0, sc, len(weeks))), index=weeks)   # noqa: E731
    sat = pd.date_range(days[0] - pd.Timedelta(days=400), days[-1], freq="W-SAT")
    months = pd.date_range(days[0] - pd.Timedelta(days=800), days[-1], freq="MS")
    return {"NFCI": wk(0, 0.05), "STLFSI4": wk(0, 0.05), "ICSA": pd.Series(250000 + np.cumsum(rng.normal(0, 3000, len(sat))),
                                                                        index=sat),
            "T10Y2Y": mk(1, 0.02), "DGS2": mk(3, 0.02), "DFF": mk(3, 0.01), "DXY": mk(100, 0.3, True),
            "SKEW": mk(130, 0.5, True), "VIX": mk(20, 0.3, True), "VIX3M": mk(22, 0.3, True), "MOVE": mk(100, 1, True),
            "HG": mk(3, 0.02, True), "GC": mk(1500, 5, True),
            "JPCALL": pd.Series(np.cumsum(rng.normal(0, 0.02, len(months))), index=months)}


def test_v2_features_no_lookahead():
    """每个序列只改「截止日时还没公布」的部分（按各自的公布时滞），截止日及以前的因素值不变。"""
    rng = np.random.default_rng(4)
    days, close, vix, baa, d10, d3, wti, un, fx, jgb = _inputs(1500, 2)
    x = _v2_inputs(days, rng)
    base = TH.raw_features(days, close, vix, baa, d10, d3, wti, un, fx, jgb)
    f = TH.raw_features_v2(base, days, close, x, usdjpy=fx, jp=True)
    t = 1300
    cut = days[t]
    unpublished = {"NFCI": lambda i: i + pd.Timedelta(days=6) > cut, "STLFSI4": lambda i: i + pd.Timedelta(days=7) > cut,
                   "ICSA": lambda i: i + pd.Timedelta(days=6) > cut, "JPCALL": lambda i: i + pd.offsets.MonthBegin(2) > cut}
    for k in ("T10Y2Y", "DGS2", "DFF"):                                   # 滞后 1 个营业日：当天的值当天不用
        unpublished[k] = lambda i: i >= cut
    x2 = {}
    for k, v in x.items():
        m = unpublished.get(k, lambda i: i > cut)(v.index)
        x2[k] = v.where(~np.asarray(m), v * 1.3 + 1)
    later = lambda sr: sr.where(sr.index <= cut, sr * 1.3 + 1)                            # noqa: E731
    f2 = TH.raw_features_v2(base, days, later(close), x2, usdjpy=later(fx), jp=True)
    cols = TH.V2_EXTRA + ["yen_vol", "boj"]
    assert f[cols].iloc[:t + 1].equals(f2[cols].iloc[:t + 1])
    assert not f[cols].iloc[t + 20:].equals(f2[cols].iloc[t + 20:])                      # 之后确实变了（测试本身有效）


def test_walkforward_logit_uses_only_known_targets():
    rng = np.random.default_rng(7)
    days = pd.bdate_range("1995-01-02", "2003-12-31")
    pct = pd.DataFrame({"a": rng.uniform(size=len(days)), "b": rng.uniform(size=len(days))}, index=days)
    ev = pd.Series((pct["a"] + rng.normal(0, 0.2, len(days)) > 0.8).astype(float), index=days)
    p = TH.walkforward_logit(pct, ev, first="2000-01-01")
    assert p[days < "2000-01-01"].isna().all() and p[days >= "2000-01-03"].notna().all()
    k0 = int(np.flatnonzero(days >= "2002-01-01")[0])
    ev2 = ev.copy()
    ev2.iloc[k0 - 60:] = 1 - ev2.iloc[k0 - 60:]                                            # 重估时还不知道答案的样本
    p2 = TH.walkforward_logit(pct, ev2, first="2000-01-01")
    yr = (days >= "2002-01-01") & (days < "2003-01-01")
    assert np.allclose(p[yr], p2[yr])
    w = TH.logit_fit(pct[["a", "b"]].to_numpy() - 0.5, ev.to_numpy())
    assert w[1] > 1 and abs(w[2]) < abs(w[1])                                               # 找回 a 的正向作用
    ts = TH.tail_share(pd.DataFrame({"a": [0.9, 0.1], "b": [0.85, np.nan], "c": [0.2, 0.95]}))
    assert ts.iloc[0] == pytest.approx(200 / 3) and ts.iloc[1] == pytest.approx(50.0)


def _v3_inputs(days, rng):
    mk = lambda base, sc: pd.Series(np.abs(base + np.cumsum(rng.normal(0, sc, len(days)))) + 1, index=days)   # noqa: E731
    cal = pd.date_range(days[0] - pd.Timedelta(days=800), days[-1], freq="D")
    qs = pd.date_range(days[0] - pd.Timedelta(days=1500), days[-1], freq="QS")
    qe = pd.date_range(days[0] - pd.Timedelta(days=1500), days[-1], freq="QE")
    ms = pd.date_range(days[0] - pd.Timedelta(days=1500), days[-1], freq="MS")
    x = {k: mk(100, 1) for k in ("GC", "SI", "HG", "NG", "ZW", "ZC", "ZS", "GSCI")}
    x.update({"SLOOS": pd.Series(rng.normal(0, 10, len(qs)), index=qs), "DELINQ": pd.Series(2 + rng.normal(0, 0.3, len(qs)), index=qs),
              "CHARGEOFF": pd.Series(1 + rng.normal(0, 0.2, len(qs)), index=qs),
              "EPU": pd.Series(np.abs(rng.normal(100, 30, len(cal))), index=cal),
              "GPRD": pd.Series(np.abs(rng.normal(100, 30, len(cal))), index=cal),
              "TK_LEND": pd.Series(rng.normal(10, 5, len(qe)), index=qe), "TK_CASH": pd.Series(rng.normal(5, 5, len(qe)), index=qe),
              "JPLNG": pd.Series(np.abs(rng.normal(10, 2, len(ms))), index=ms), "GPRC_JPN": pd.Series(np.abs(rng.normal(0.4, 0.1, len(ms))), index=ms)})
    return x


def test_gpr_available_monday_updates():
    s = pd.Series([1.0, 2.0, 3.0], index=pd.DatetimeIndex(["2026-09-16", "2026-09-21", "2026-09-22"]))   # 周三 / 周一 / 周二
    days = pd.bdate_range("2026-09-21", "2026-09-30")
    a = TH.gpr_available(s, days, 1)
    assert list(a.fillna(-1)) == [-1, 2, 2, 2, 2, 2, 3, 3]            # 9/16 与 9/21 的值 9/22 起可用；9/22 的值 9/29 起


def test_v3_features_no_lookahead():
    """v3 每个序列只改「截止日时还没公布」的部分（按各自的公布时滞），截止日及以前的因素值不变。"""
    rng = np.random.default_rng(11)
    days = pd.bdate_range("2015-01-01", periods=900)
    base = pd.DataFrame(index=days)
    x = _v3_inputs(days, rng)
    t = 800
    cut = days[t]
    for jp, extra in ((False, 0), (True, 1)):
        f = TH.raw_features_v3(base, days, x, jp=jp)
        monday_after = lambda i: i + pd.to_timedelta((7 - i.weekday) % 7, unit="D")                  # noqa: E731
        unpublished = {"SLOOS": lambda i: i + pd.Timedelta(days=45 + extra) > cut,
                       "DELINQ": lambda i: i + pd.Timedelta(days=160 + extra) > cut,
                       "CHARGEOFF": lambda i: i + pd.Timedelta(days=160 + extra) > cut,
                       "EPU": lambda i: i + pd.Timedelta(days=2 + extra) > cut,
                       "GPRD": lambda i: monday_after(i) + pd.Timedelta(days=1 + extra) > cut,
                       "TK_LEND": lambda i: i + pd.Timedelta(days=5) > cut, "TK_CASH": lambda i: i + pd.Timedelta(days=5) > cut,
                       "JPLNG": lambda i: i + pd.DateOffset(months=3) > cut,
                       "GPRC_JPN": lambda i: i + pd.offsets.MonthBegin(1) + pd.Timedelta(days=4) > cut}
        x2 = {k: v.where(~np.asarray(unpublished.get(k, lambda i: i > cut)(v.index)), v * 1.5 + 3) for k, v in x.items()}
        f2 = TH.raw_features_v3(base, days, x2, jp=jp)
        cols = TH.V3_EXTRA + (TH.JP_V3_ONLY if jp else [])
        assert f[cols].iloc[:t + 1].equals(f2[cols].iloc[:t + 1]), jp
        assert not f[cols].iloc[t + 60:].equals(f2[cols].iloc[t + 60:])                           # 之后确实变了


def test_category_mean_balances_groups():
    pct = pd.DataFrame({"vix": [1.0], "rvol": [1.0], "move": [1.0], "gold": [0.0]})             # 波动 3 个都 1，商品 1 个 0
    assert TH.category_mean(pct).iloc[0] == pytest.approx(50.0)


def test_v3_readings_and_forward_log(tmp_path):
    rng = np.random.default_rng(5)
    days = pd.bdate_range("2010-01-01", periods=900)
    raw = pd.DataFrame({c: rng.normal(size=len(days)) for c in TH.JP_V3}, index=days)
    F = {"US": (raw[TH.US_V3], None), "JP": (raw, None)}
    rd = TH.v3_readings(F, {"US": ["vix", "gold"], "JP": []})
    assert set(rd["US"]["idx"]) == {"A0", "B1", "B2", "B3", "B4", "A0x", "A0+gold_silver", "A0+commod_vol"}
    assert rd["JP"]["idx"]["B2"] is None and "A0+gold_silver" not in rd["JP"]["idx"]
    assert TH.forward_label("A0+gold_silver") == "现行 + 金银比上升"
    assert len(rd["JP"]["obs"]) == len(TH.V3_EXTRA + TH.JP_V3_ONLY) and len(rd["US"]["obs"]) == len(TH.V3_EXTRA)
    assert rd["US"]["obs"] == sorted(rd["US"]["obs"], key=lambda o: -o["pct"])
    fp = tmp_path / "fw.csv"
    TH.log_forward(rd, fp)
    TH.log_forward(rd, fp)                                                # 同一数据日重复运行：不重复记
    df = pd.read_csv(fp)
    assert len(df) == 2 and set(df["market"]) == {"US", "JP"}


def test_us_watch_series_and_keep_first_log(tmp_path):
    days = pd.bdate_range("2010-01-01", periods=900)
    rng = np.random.default_rng(8)
    pct = pd.DataFrame({"gold_silver": rng.uniform(size=900), "commod_vol": rng.uniform(size=900)}, index=days)
    ws = TH.us_watch_series(pct)
    assert np.allclose(ws["W"], (pct["gold_silver"] + pct["commod_vol"]) * 50)
    assert ws["W_pct"].dropna().between(0, 100).all() and ws["W_pct"].iloc[:700].isna().all()      # 自身历史不足 750 天不给值
    raw = pd.DataFrame({"gold_silver": rng.normal(0, 0.05, 900), "commod_vol": rng.uniform(0.1, 0.4, 900)}, index=days)
    rows = TH.us_watch_rows(raw, pct, pd.Series(rng.uniform(20, 80, 900), index=days))
    assert len(rows) == 5 and rows[-1]["date"] == str(days[-1].date()) and set(rows[0]) >= {"W", "W_pct", "A0", "A0_pct", "gs_raw"}
    fp = tmp_path / "w.csv"
    TH.log_us_watch({"US": {"watch_rows": rows}}, fp)
    changed = [dict(r, W=-1.0) for r in rows[1:]] + [dict(rows[-1], date="2099-01-01")]
    TH.log_us_watch({"US": {"watch_rows": changed}}, fp)
    df = pd.read_csv(fp)
    assert len(df) == 6 and (df["W"].iloc[:5] >= 0).all()                  # 已记过的日期保留最早那次，只补新日期


def test_watch_review_and_decision():
    days = pd.bdate_range("2020-01-01", periods=400)
    close = pd.Series(np.linspace(90, 100, 400), index=days)
    close.iloc[200:230] = np.linspace(99.5, 80, 30)                         # 第 199 天见顶，之后跌 20%
    close.iloc[230:] = 80.0
    log = pd.DataFrame({"date": [str(d.date()) for d in days[100:300]], "W": 30.0, "W_pct": 50.0, "A0": 40.0, "A0_pct": 50.0})
    log.loc[(log["date"] >= str(days[150].date())) & (log["date"] < str(days[200].date())), ["W", "W_pct"]] = [90.0, 95.0]
    r = TH.watch_review(log, close)
    assert r["auc_W"] > 0.8 and r["auc_A0"] == 0.5 and r["alert_days"] == 50
    assert [e["W_alert"] for e in r["episodes"]] == [True] and [e["A0_alert"] for e in r["episodes"]] == [False]
    assert r["decision"].startswith("继续观察")                               # 只有 1 次下跌、已知结果不足 500 天
    assert r["warn80_days"] == 50 and [e["W_warn80"] for e in r["episodes"]] == [True] and r["decision80"].startswith("继续观察")
    ok80 = {"episodes": [{"W_warn80": True, "A0_warn80": False}] * 2 + [{"W_warn80": False, "A0_warn80": True}], "known": 600,
            "warn80_hit": 0.30, "base_rate": 0.15}
    assert TH.warn80_decision(ok80).startswith("预警线有效")                # 2/3 事前预警、发生率 2 倍、不低于 A0
    assert TH.warn80_decision({**ok80, "warn80_hit": 0.20}).startswith("预警线未达门槛")      # 只有 1.3 倍
    base = {"episodes": [{"W_alert": True}, {"W_alert": True}, {"W_alert": False}], "known": 600}
    assert TH.watch_decision({**base, "auc_W": 0.70, "auc_A0": 0.60}).startswith("达到门槛")
    assert TH.watch_decision({**base, "auc_W": 0.52, "auc_A0": 0.60}).startswith("未达门槛且")
    assert TH.watch_decision({**base, "auc_W": 0.66, "auc_A0": 0.63}).startswith("未达门槛（")


def test_fill_gaps_only_adds_missing_days():
    y = pd.Series([1.0, 2.0, 4.0], index=pd.DatetimeIndex(["2026-09-18", "2026-09-21", "2026-09-23"]))
    f = pd.Series([9.0, 1.5, 2.5, 3.0, 5.0], index=pd.DatetimeIndex(["2026-09-17", "2026-09-18", "2026-09-22", "2026-09-23", "2026-09-24"]))
    g = TH.fill_gaps(y, f, pd.Timestamp("2026-09-24"))
    assert list(g.index.strftime("%m-%d")) == ["09-18", "09-21", "09-22", "09-23"] and list(g) == [1.0, 2.0, 2.5, 4.0]


def test_forward_review_compares_on_same_days():
    days = pd.bdate_range("2020-01-01", periods=400)
    close = pd.Series(np.linspace(90, 100, 400), index=days)
    close.iloc[200:230] = np.linspace(99.5, 80, 30)                             # 第 200 天见顶后跌 20%
    close.iloc[230:] = 80.0
    rows = []
    for i, d in enumerate(days[100:300], start=100):
        hot = 150 <= i < 200
        rows.append({"date": str(d.date()), "market": "US", "A0": 50.0, "A0x": 90.0 if hot else 40.0, "S": None})
    r = TH.forward_review(pd.DataFrame(rows), {"US": close})["US"]
    x = r["variants"]["A0x"]
    assert x["auc10"] > 0.8 and x["auc10_A0"] == 0.5 and r["variants"]["S"]["n"] == 0
    assert r["decision"].startswith("继续记录") and len(r["episodes"]) == 1
    full = {"episodes": ["a", "b", "c"], "known": 600,
            "variants": {"A0x": {"n": 600, "auc10": 0.70, "auc10_A0": 0.62, "auc15": 0.66, "auc15_A0": 0.60},
                         "S": {"n": 600, "auc10": 0.64, "auc10_A0": 0.62, "auc15": 0.70, "auc15_A0": 0.60}}}
    assert TH.forward_decision(full).startswith("去掉曲线倒挂与油价冲击 达到门槛")
    full["variants"]["A0x"]["auc15"] = 0.55                                     # ≥15% 不如 A0 → 不采用
    assert TH.forward_decision(full) == "没有版本达到门槛：继续记录"
