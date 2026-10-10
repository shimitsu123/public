"""关联搭配 C（qbreak/combo_c.py，2026-10-01 用户「加进模拟盘并记录」）：冻结的规则、特征与研究同一算法、只用信号日为止的数据、
平静的牛市才起作用、日期对不上 = 原规则、云端现算写文件、执行器读同一个文件、基准账户不加、前向记录的列与第十二节复核。"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qbreak import combo_c as CC  # noqa: E402
from qbreak import paths  # noqa: E402
from qbreak import w2_forward as W2F  # noqa: E402


def _ohlcv(n=320, seed=0, start="2025-01-06"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, n)))
    o = c * (1 + rng.normal(0, 0.004, n))
    h, lo = np.maximum(o, c) * (1 + rng.uniform(0, 0.01, n)), np.minimum(o, c) * (1 - rng.uniform(0, 0.01, n))
    return pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": rng.uniform(5e5, 2e6, n)}, index=idx)


def test_frozen_rule_matches_registered_all_eras_fit():
    """规则 = 三个年代一起学的那一份（var/out/combo_all_posthoc.json 的 rules_all_detail 第 2 格），之后不改。"""
    assert CC.RULE == {"vexp": (1, 0.9350, 1.1258), "upper": (-1, 0.4667, 0.9000), "atrp": (-1, 0.015620, 0.019263),
                       "r12": (-1, 0.023723, 0.15838), "us12": (-1, 0.3265, 0.6327)}
    assert (CC.VIX_MAX, CC.MA_N, CC.MA_MIN, CC.SKIP_BELOW, CC.SINCE) == (20.0, 200, 150, -1.0, "2026-10-01")
    fp = Path(__file__).resolve().parents[1] / "var" / "out" / "combo_all_posthoc.json"
    if fp.exists():
        r = json.loads(fp.read_text(encoding="utf-8"))["rules_all_detail"]
        assert r["0"] is None and r["1"] is None and r["3"] is None and r["2"]["thr"] == -1.0
        assert r["2"]["sel"] == {f: d for f, (d, _, _) in CC.RULE.items()}
        for f, (_, lo, hi) in CC.RULE.items():                                    # 那边取 4 位小数
            assert abs(r["2"]["cut"][f][0] - lo) < 6e-5 and abs(r["2"]["cut"][f][1] - hi) < 6e-5


def test_stock_features_match_formulas_and_use_only_data_up_to_signal_day():
    df = _ohlcv()
    d = df.index[300]
    f = CC.stock_features(df, d)
    x = df.iloc[:301]
    v, c, h, lo = x["Volume"], x["Close"], x["High"], x["Low"]
    vexp = v.iloc[-20:].mean() / v.iloc[-80:-20].mean()
    assert abs(f["vexp"] - vexp) < 1e-12
    tr = pd.concat([h - lo, (h - c.shift(1)).abs(), (lo - c.shift(1)).abs()], axis=1).max(axis=1)
    a = np.nan
    for i, t in enumerate(tr.to_numpy()):                                         # Wilder：前 14 个是普通递推（adjust=False）
        a = t if i == 0 else a + (t - a) / 14
    assert abs(f["atrp"] - a / c.iloc[-1]) < 1e-12
    assert abs(f["r12"] - (np.log(c.iloc[-22]) - np.log(c.iloc[-253]))) < 1e-12   # 跳过最近 21 个交易日的 12 个月
    H, L, C = h.iloc[-61:-1], lo.iloc[-61:-1], c.iloc[-61:-1]                     # 信号日之前 60 根（不含信号日）
    assert f["upper"] == float(np.mean(C.iloc[-20:].to_numpy() >= (H.max() + L.min()) / 2))
    later = df.copy()
    later.iloc[301:] *= 3                                                         # 信号日之后的行情变了 → 特征不变
    assert CC.stock_features(later, d) == f
    assert all(np.isnan(v_) for v_ in CC.stock_features(df, pd.Timestamp("2030-01-01")).values())
    assert all(np.isnan(v_) for v_ in CC.stock_features(None, d).values())


def test_zero_volume_rows_dropped_and_r12_counts_union_calendar():
    """研究先去掉成交量 0 的行；r12 按全部日本股票的交易日并集数 21 / 252 天（这只票缺的日子 = 缺值）。"""
    df = _ohlcv()
    d = df.index[300]
    z = df.copy()
    z.iloc[200, z.columns.get_loc("Volume")] = 0.0                                # 成交量 0 的一行 = 研究里没有这一行
    assert CC.stock_features(z, d) == CC.stock_features(z.drop(index=z.index[200]), d)
    other = _ohlcv(seed=1)
    cal = CC.calendar({"A.T": df, "B.T": other, "^N225": _ohlcv(seed=3, start="2024-01-01")})   # 只用 .T、Volume > 0
    assert cal.equals(df.index) and CC.calendar({}) is None
    gap = df.drop(index=df.index[[100, 150]])                                    # 这只票自己缺两天
    own = CC.stock_features(gap, d)["r12"]
    on_cal = CC.stock_features(gap, d, cal)["r12"]
    c = df["Close"]
    assert abs(on_cal - (np.log(c.iloc[279]) - np.log(c.iloc[48]))) < 1e-12      # 按日历数：21 / 252 个交易日前
    assert abs(own - (np.log(c.iloc[279]) - np.log(c.iloc[46]))) < 1e-12         # 按自己的行数会多退两天
    hole = df.drop(index=df.index[48])                                            # 252 天前那天正好缺 → 缺值（宽表同样）
    assert np.isnan(CC.stock_features(hole, d, cal)["r12"])


def test_market_state_uses_ma200_upto_day_and_vix_strictly_before():
    idx = pd.bdate_range("2025-01-01", periods=260)
    n = pd.Series(np.linspace(100, 160, 260), index=idx)
    vix = pd.Series(15.0, index=idx)
    vix.iloc[-1] = 35.0                                                           # 信号日当天的 VIX 不能用
    d = idx[-1]
    m = CC.market_state(n, vix, d)
    assert abs(m["n225_ma200"] - (n.iloc[-1] / n.iloc[-200:].mean() - 1)) < 1e-12 and m["vix"] == 15.0 and m["on"] is True
    v2 = vix.copy()
    v2.iloc[-2] = 25.0
    assert CC.market_state(n, v2, d)["on"] is False and CC.market_state(n, v2, d)["vix"] == 25.0   # 前一天 25 → 不是
    assert CC.market_state(-n + 400, vix, d)["on"] is False                       # 跌到 200 日线下 → 不是
    assert CC.market_state(n.iloc[:149], vix, idx[148])["on"] is None              # 不到 150 天算不了 200 日线
    assert CC.market_state(None, vix, d)["on"] is None and CC.market_state(n, None, d)["on"] is None
    later = n.copy()
    later.loc[d + pd.Timedelta(days=1)] = 1.0                                     # 之后的数据不影响
    assert CC.market_state(later, vix, d) == m


def test_votes_boundaries_and_skip_only_in_calm_bull():
    lo = {f: v[1] for f, v in CC.RULE.items()}
    hi = {f: v[2] for f, v in CC.RULE.items()}
    assert CC.votes(hi) == {f: d for f, (d, _, _) in CC.RULE.items()}             # 等于上切点 → 上三分之一
    assert CC.votes(lo) == {f: -d for f, (d, _, _) in CC.RULE.items()}            # 等于下切点 → 下三分之一
    assert CC.votes({"vexp": np.nan}) == {f: 0 for f in CC.FEATS}                 # 缺值 = 0 票
    bad2 = {"vexp": 0.5, "upper": 0.95, "atrp": 0.01, "r12": 0.1, "us12": 0.5}     # −1、−1、+1、0、0 → −1
    assert CC.decide(bad2, {"on": True}) == {"votes": {"vexp": -1, "upper": -1, "atrp": 1, "r12": 0, "us12": 0}, "score": -1, "skip": False}
    bad3 = {**bad2, "atrp": 0.03}                                                 # −2 → 跳过
    assert CC.decide(bad3, {"on": True})["skip"] is True
    assert CC.decide(bad3, {"on": False})["skip"] is False and CC.decide(bad3, {"on": None})["skip"] is False
    P = pd.DataFrame({"Chips": [16 / 49, 31 / 49]}, index=pd.to_datetime(["2026-09-01", "2026-10-01"]))
    u = CC.us12_of(P, {"8035.T": "電気機器"}, "8035.T", "2026-09-15")
    assert u == 0.3265 and CC.votes({"us12": u})["us12"] == 1                     # 取 4 位（研究同样）→ 正好在下切点上 = 有利
    assert np.isnan(CC.us12_of(None, {}, "8035.T", "2026-09-15")) and np.isnan(CC.us12_of(P, {}, "8035.T", "2026-09-15"))


def test_payload_apply_brief_and_text():
    good = {"vexp": 1.3, "upper": 0.2, "atrp": 0.01, "r12": 0.0, "us12": 0.2}
    bad = {"vexp": 0.5, "upper": 0.95, "atrp": 0.03, "r12": 0.3, "us12": np.nan}
    mk = {"n225_ma200": 0.14, "vix": 16.3, "on": True}
    pl = CC.payload("2026-10-01", mk, {"A.T": good, "B.T": bad}, {"us12": "x"})
    assert pl["stocks"]["A.T"]["skip"] is False and pl["stocks"]["B.T"]["skip"] is True and pl["stocks"]["B.T"]["score"] == -4
    assert pl["stocks"]["B.T"]["features"]["us12"] is None and pl["market"] == {"n225_ma200": 0.14, "vix": 16.3, "on": True}
    json.dumps(pl)                                                                # 能写成 JSON
    tm, used = CC.apply({"A.T": 0.5}, pl, "2026-10-01")
    assert used is pl and tm == {"A.T": 0.5, "B.T": 0.0}                          # 只把跳过的设 0，其余不动（不放大）
    assert CC.apply({"A.T": 0.5}, pl, "2026-10-02") == ({"A.T": 0.5}, None)        # 日期对不上 → 原规则
    assert CC.apply({}, {**pl, "enabled": False}, "2026-10-01") == ({}, None) and CC.apply({}, None, "2026-10-01") == ({}, None)
    b = CC.brief(pl, "2026-10-01", True)
    assert b["applied"] and b["skipped"] == ["B.T"] and b["kept"] == ["A.T"] and b["on"] is True
    assert "跳过 1 只：B.T" in CC.text(b) and "起作用" in CC.text(b)
    off = CC.payload("2026-10-01", {"n225_ma200": -0.02, "vix": 16.0, "on": False}, {"B.T": bad})
    assert off["stocks"]["B.T"]["skip"] is False and "C 不动" in CC.text(CC.brief(off, "2026-10-01", True))
    stale = CC.brief(pl, "2026-10-02", True)
    assert stale["applied"] is False and "2026-10-01" in stale["why"] and "没生效" in CC.text(stale)
    assert CC.brief(None, "2026-10-01", True)["applied"] is False and CC.brief(pl, "x", False) == {"enabled": False}
    assert CC.text({"enabled": False}) == "" and CC.summary(pl, "2026-10-01", True)["stocks"]["B.T"]["skip"] is True
    fp = paths.home() / CC.FILE
    fp.write_text(json.dumps(pl), encoding="utf-8")
    assert CC.load(fp) == json.loads(json.dumps(pl)) and CC.load(paths.home() / "nope.json") is None


def test_fields_columns_and_missing_market():
    a, b = _ohlcv(seed=4), _ohlcv(seed=5)
    idx = a.index
    n = pd.Series(np.linspace(100, 160, len(idx)), index=idx)
    vix = pd.Series(15.0, index=idx)
    dates, tks = [idx[300], idx[310], idx[310]], ["A.T", "B.T", "A.T"]
    f = CC.fields({"A.T": a, "B.T": b}, dates, tks, n, vix)
    assert tuple(f) == CC.COLS and all(len(v) == 3 for v in f.values())
    assert f["cc_on"] == [1, 1, 1] and all(np.isnan(x) for x in f["cc_us12"])     # 没给美国行业 → 空 = 0 票
    one = CC.stock_features(b, idx[310], CC.calendar({"A.T": a, "B.T": b}))
    assert abs(f["cc_vexp"][1] - round(one["vexp"], 6)) < 1e-12
    g = CC.fields({"A.T": a}, [idx[300]], ["A.T"], None, vix)
    assert np.isnan(g["cc_on"][0]) and g["cc_skip"] == [0]                        # 市场格算不了 → 空、不跳过


def _pairs():
    """第十节配对表的样子：日経225 / 扩大池、W2 保留、平静的牛市、会跳过 / 保留。"""
    rows = []
    rng = np.random.default_rng(7)
    for i in range(60):
        skip = int(i % 4 == 0)
        rows.append({"date": pd.Timestamp("2026-10-01") + pd.Timedelta(days=7 * i), "ticker": f"{1000 + i}.T",
                     "segment": "N225" if i % 3 else "T500x", "w2_keep": 1, "cc_on": 1, "cc_skip": skip,
                     "status": "ok", "mature": True, "net_x6": (-2.0 if skip else 1.5) + rng.normal(0, 0.5), "net_cur": 0.0})
    rows.append({**rows[1], "cc_on": 0, "ticker": "X.T"})                         # 不在那一格 → 不算
    rows.append({**rows[1], "w2_keep": 0, "ticker": "Y.T"})                       # W2 挡掉 → 不算
    rows.append({**rows[1], "date": pd.Timestamp("2026-09-30"), "ticker": "Z.T"})   # C 之前 → 不算
    rows.append({**rows[1], "cc_on": np.nan, "cc_skip": np.nan, "ticker": "W.T"})   # 市场格为空 → 不算
    rows.append({**rows[1], "mature": False, "ticker": "V.T"})                    # 未成熟 → 不算
    return pd.DataFrame(rows)


def test_review_sample_and_yearly_judgment():
    P = _pairs()
    C = CC.review_frame(P)
    assert len(C) == 60 and set(C["cc_keep"]) == {0, 1} and (C["cc_keep"] == 1 - C["cc_skip"]).all()
    r = CC.review(P, P, None, pd.Timestamp("2027-10-05"))
    ev = r["eval"]
    assert ev["n"] == 40 and ev["drop"]["n"] >= CC.MIN_GROUP - 1                 # 主 = 日経225
    assert r["eval_all"]["n"] == 60 and r["year"] == "2027-09-28"
    want = W2F.evaluate(C[C["segment"] == "N225"], keep_col="cc_keep", net_col="net_x6")
    assert ev["diff"] == want["diff"] and ev.get("lo99") == want.get("lo99")
    assert r["enough"] is True and r["confirmed"] is True and r["alarm"] is False   # 日経225 跳过 10 笔：保留明显更好 → 证实
    rev = P.assign(net_x6=-P["net_x6"])                                           # 反过来：跳过的更好 → 失效警报
    r2 = CC.review(rev, rev, None, pd.Timestamp("2027-10-05"))
    assert r2["enough"] is True and r2["alarm"] is True and r2["confirmed"] is False
    small = P.iloc[:12]                                                           # 任一组 < 10 笔 → 样本不够、不判定（这一年记为做过）
    r3 = CC.review(small, small, None, pd.Timestamp("2027-10-05"))
    assert r3["year"] == "2027-09-28" and r3["enough"] is False and r3["alarm"] is None and r3["confirmed"] is None
    assert any("样本不够" in x for x in CC.say_lines(r3))
    h = pd.DataFrame([CC.history_row(r3, "2027-10-05", {"logged": 1})])
    assert h.loc[0, "scope"] == "CC" and h.loc[0, "cc_year"] == "2027-09-28"
    assert CC.review(P, P, h, pd.Timestamp("2027-12-20"))["year"] is None         # 这一年做过了
    assert CC.review(P, P, None, pd.Timestamp("2027-06-01"))["year"] is None      # 还没到第一个日期 → 只报告进度
    cnt = r["counts"]["N225"]
    assert cnt["on"] >= 40 and cnt["skip"] >= 1 and cnt["no_cc"] == 1
    empty = CC.review(pd.DataFrame(), None, None, pd.Timestamp("2027-10-05"))
    assert empty["eval"]["n"] == 0 and empty["enough"] is False


def test_apply_live_mults_skips_c_flagged_candidate_on_last_bar_only():
    import run
    from test_fwd_judgment_live import _engine, _ind, _plan_after
    ind, bear = _ind()
    bar = str(ind["1655.T"].index[-1].date())
    plans = {"JP": SimpleNamespace(scale=1.0, tmult={}, block=None)}
    bad = {"vexp": 0.5, "upper": 0.95, "atrp": 0.03, "r12": 0.3, "us12": 0.9}
    pl = CC.payload(bar, {"n225_ma200": 0.1, "vix": 15.0, "on": True}, {"A.T": bad, "B.T": {}})
    e0, e1, e2 = _engine(ind, bear), _engine(ind, bear), _engine(ind, bear)
    run._apply_live_mults(e0, plans, None, bar)
    run._apply_live_mults(e1, plans, None, bar, pl)
    run._apply_live_mults(e2, plans, None, "2026-01-05", pl)                     # 文件日期对不上 → 原规则
    (s0, o0), (s1, o1), (s2, o2) = _plan_after(e0), _plan_after(e1), _plan_after(e2)
    assert o0 == o2 == ["A.T", "B.T"] and s2 == s0
    assert o1 == ["B.T"] and s1["B.T"] == s0["B.T"]                               # A 跳过、B 不变（不放大）
    assert e1.live_mult["JP"][1] == {"A.T": 0.0} and e1.skipped["macro"] >= 1


def test_cc_compute_writes_file_and_handles_stale_or_missing_market(monkeypatch):
    import run
    from test_fwd_judgment_live import _ind
    ind, _ = _ind()
    bar = str(ind["1655.T"].index[-1].date())
    ind["B.T"].loc[ind["B.T"].index[-1], "entry"] = False
    monkeypatch.setattr(run, "_sim_cfg", lambda: {"unified": {"core": {"1655.T": 1.0}}})
    (paths.home() / "industry_s33.json").write_text(json.dumps({"s33": {"A": "電気機器"}}), encoding="utf-8")
    from qbreak import factors as F
    monkeypatch.setattr(F, "ff_industries", lambda *a, **k: pd.DataFrame({"Chips": [1.0] * 30},
                                                                         index=pd.date_range("2024-01-01", periods=30, freq="MS")))
    idx = pd.bdate_range(end=bar, periods=260)
    n225 = pd.Series(np.linspace(100, 160, 260), index=idx)
    vix = pd.Series(15.0, index=idx)
    pl = run._cc_compute(ind, bar, "yfinance", market=(n225, vix))
    assert pl["as_of"] == bar and pl["market"]["on"] is True and list(pl["stocks"]) == ["A.T"]   # 只有最新 K 线上成立的个股
    assert json.loads((paths.home() / CC.FILE).read_text(encoding="utf-8"))["as_of"] == bar
    old = run._cc_compute(ind, bar, "yfinance", market=(n225.iloc[:-3], vix))   # 日経225 落后 3 天 → C 不动
    assert old["market"]["on"] is None and "日経225 只到" in old["errors"]["市场格"]
    vx_old = run._cc_compute(ind, bar, "yfinance", market=(n225, vix.iloc[:-10]))
    assert vx_old["market"]["on"] is None and "VIX 只到" in vx_old["errors"]["市场格"]
    monkeypatch.setattr(run, "_cc_market", lambda p: (_ for _ in ()).throw(RuntimeError("yahoo 取不到")))
    bad = run._cc_compute(ind, bar, "yfinance")
    assert bad["market"]["on"] is None and not any(v["skip"] for v in bad["stocks"].values())   # 整个算不了 → 原规则


def test_score_forward_logs_cc_columns(tmp_path, monkeypatch):
    """第十二节：每个信号另记 C 的列（与 combo_c.fields 同一个值）；cc 给不了 → 全部为空。"""
    from qbreak import score_forward as SF
    from test_score_forward import PW2, TICKERS, _ind_w2, _models
    live, base, idx = _ind_w2()
    models, _ = _models(base, idx)
    mp, lp, lp2 = tmp_path / "m.json", tmp_path / "log.csv", tmp_path / "log2.csv"
    SF.save_model(models, {"id": "t1"}, mp)
    days = list(base[TICKERS[0]].index[-250:])
    monkeypatch.setattr(SF, "FORWARD_START", str(days[0].date()))
    f = SF.no_w2_frames(live, PW2, TICKERS)
    vix = pd.Series(15.0, index=idx.index)
    SF.run_daily(f, idx, TICKERS, days, None, mp, lp, "2026-10-01", cc={"n225": idx, "vix": vix, "us_pct": None, "s33": None})
    got = pd.read_csv(lp)
    assert set(CC.COLS) <= set(got.columns) and len(got)
    want = CC.fields(f, pd.to_datetime(got["date"]), list(got["ticker"]), idx, vix)
    for c in ("cc_on", "cc_score", "cc_skip", "cc_vexp", "cc_r12"):
        a, b = got[c].to_numpy(float), np.asarray(want[c], float)
        assert np.allclose(a, b, equal_nan=True)
    SF.run_daily(f, idx, TICKERS, days, None, mp, lp2, "2026-10-01")
    assert pd.read_csv(lp2)[list(CC.COLS)].isna().all().all()


def test_report_card_and_executor_text():
    from qbreak.live_unified import daily_text
    from qbreak.report_unified import _combo_c_html
    pl = CC.payload("2026-10-01", {"n225_ma200": 0.14, "vix": 16.3, "on": True},
                    {"A.T": {"vexp": 0.5, "upper": 0.95, "atrp": 0.03, "r12": 0.3, "us12": 0.9}, "B.T": {}})
    h = _combo_c_html({"combo_c": CC.summary(pl, "2026-10-01", True)})
    assert "关联搭配 C" in h and "A.T" in h and "跳过" in h and "非投资建议" in h
    assert _combo_c_html({"combo_c": {"enabled": False}}) == ""
    assert "今天没生效" in _combo_c_html({"combo_c": CC.summary(pl, "2026-10-02", True)})
    st = SimpleNamespace(pos={}, core_units={}, cash_jpy=1_000_000.0, history=[])
    sm = {"equity_jpy": 1_000_000.0, "orders": [], "combo_c": CC.brief(pl, "2026-10-02", True)}
    _, short, body = daily_text(sm, st, None, True, 1_000_000.0)
    assert "关联搭配 C 没生效" in short and "关联搭配 C 没生效" in body
