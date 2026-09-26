"""因子调查（qbreak/survey.py）：每种变换只用截止日时已公布的数据；方向与停更判断。"""
import numpy as np
import pandas as pd

from qbreak import survey as SV


def _freq(kind: str, src: str) -> str:
    if kind == "c_ma30":
        return "D"
    if kind.startswith("d_"):
        return "B"
    if kind.startswith("w_"):
        return "W-WED"
    if kind.startswith("m_"):
        return "MS"
    return "QE" if src.startswith("tankan") else "QS"


def _raw(rng, start="2008-01-01", end="2014-12-31"):
    raw = {}
    for _, _, _, kind, srcs, _, _, _ in SV.SPECS:
        for s in srcs:
            if s in raw:
                continue
            idx = pd.date_range(start, end, freq=_freq(kind, s))
            raw[s] = pd.Series(np.abs(100 + np.cumsum(rng.normal(0, 1, len(idx)))) + 5, index=idx)
    return raw


def test_survey_features_no_lookahead():
    rng = np.random.default_rng(21)
    raw = _raw(rng)
    days = pd.bdate_range("2011-01-03", "2014-06-30")
    cut = days[600]
    for jp in (False, True):
        f = SV.features(days, raw, jp_market=jp)
        bad = {}                                                   # 各数据源在截止日还没公布的部分（按各自的时滞）
        for _, _, _, kind, srcs, lag, _, country in SV.SPECS:
            for s in srcs:
                x = raw[s]
                if kind.startswith("d_"):
                    same_day_ok = (not jp) and (country in ("JP", "CN") or lag == 0)
                    b = (x.index > cut) if same_day_ok else (x.index >= cut)
                else:
                    b = x.index + pd.Timedelta(days=lag + (1 if (jp and country == "US") else 0)) > cut
                bad[s] = np.asarray(b) if s not in bad else (bad[s] & np.asarray(b))
        raw2 = {s: x.where(~bad[s], x * 1.5 + 7) for s, x in raw.items()}
        f2 = SV.features(days, raw2, jp_market=jp)
        assert f.loc[:cut].equals(f2.loc[:cut]), jp
        assert not f.loc[cut + pd.Timedelta(days=120):].equals(f2.loc[cut + pd.Timedelta(days=120):])


def test_survey_directions_and_stale():
    days = pd.bdate_range("2012-01-02", periods=300)
    up = pd.Series(np.linspace(100, 200, 300), index=days)
    raw = {"yf:^SOX": up, "yf:^GSPC": pd.Series(100.0, index=days), "yf:^OVX": up}
    f = SV.features(days, raw, jp_market=False)
    assert (f["semis_rel"].dropna() < 0).all()                    # 半导体跑赢大盘 → 危险度为负（方向 −1）
    assert (f["oil_vol"].dropna() > 0).all() and "breadth" not in f   # 没有数据的因素不出现
    st = SV.stale({"fred:WALCL": pd.Series([1.0], index=[pd.Timestamp("2023-01-04")])}, pd.Timestamp("2026-09-25"))
    assert st.get("fed_bs") == "2023-01-04" and st.get("m2_us") == "取不到"


def test_readings_domains_and_S():
    rng = np.random.default_rng(3)
    days = pd.bdate_range("2008-01-01", periods=1000)
    ex = pd.DataFrame({c: rng.normal(size=1000) for c in ("vix", "credit", "gold", "claims")}, index=days)
    F = {"US": (ex, None), "JP": (ex, None)}
    r = SV.readings(F, {}, {"US": ["gold"], "JP": []}, {"US": ["vix", "credit"], "JP": ["vix", "credit"]})
    assert set(r["US"]["domains"]) == {"商品", "就业"} and 0 <= r["US"]["domains"]["商品"] <= 100
    assert r["US"]["S"] is not None and r["JP"]["S"] is not None


def test_jp_watch_rows_and_generic_review(tmp_path):
    from qbreak import threat as TH
    rng = np.random.default_rng(9)
    days = pd.bdate_range("2008-01-01", periods=1200)
    cols = SV.JP_WATCH + ["gold_silver", "commod_vol"] + TH.JP_COLS
    raw_ex = pd.DataFrame({c: rng.normal(size=1200) for c in dict.fromkeys(cols)}, index=days)
    rows = SV.jp_watch_rows({"JP": (raw_ex, None)}, {})
    assert len(rows) == 5 and {"Wj", "Wj_pct", "W2", "W2_pct", "A0", "A0_pct", "p_breadth"} <= set(rows[-1])
    assert {f"A0+{c}" for c in SV.JP_WATCH} | {"A0+Wj"} <= set(rows[-1])      # 现行 + 各因素 / 全部因素（前瞻对照）
    a0x = TH._eq(pd.DataFrame({c: TH.expanding_pct(raw_ex[c]) for c in TH.JP_COLS + SV.JP_WATCH}))   # 18 个因素等权
    assert rows[-1]["A0+Wj"] == round(float(a0x.iloc[-1]), 2)
    assert TH.forward_label("A0+Wj") == "现行 + 日経 Wj 8 个因素"
    assert TH.forward_label("A0+breadth") == "现行 + 等权相对市值加权下跌（RSP / SPY）" and TH.forward_label("A0+claims") == "现行 + 初请失业金上升"
    fp = tmp_path / "jw.csv"
    TH.log_watch_rows(rows, fp)
    TH.log_watch_rows([dict(r, Wj=-1.0) for r in rows], fp)                  # 已记日期保留最早值
    assert (pd.read_csv(fp)["Wj"] >= 0).all()
    d2 = pd.bdate_range("2020-01-01", periods=400)
    close = pd.Series(np.linspace(90, 100, 400), index=d2)
    close.iloc[200:230] = np.linspace(99.5, 80, 30)
    close.iloc[230:] = 80.0
    lg = pd.DataFrame({"date": [str(x.date()) for x in d2[100:300]], "Wj": 30.0, "Wj_pct": 50.0, "W2": 40.0, "W2_pct": 85.0,
                       "A0": 40.0, "A0_pct": 50.0})
    hot = (lg["date"] >= str(d2[150].date())) & (lg["date"] < str(d2[200].date()))
    lg.loc[hot, ["Wj", "Wj_pct"]] = [90.0, 95.0]
    r = TH.watch_review_generic(lg, close, {"Wj": "Wj_pct", "W2": "W2_pct"}, market="日経")
    wj, w2 = r["scores"]["Wj"], r["scores"]["W2"]
    assert wj["auc"] > 0.8 and wj["days90"] == 50 and [e["alert90"] for e in wj["episodes"]] == [True]
    assert w2["days80"] == 200 and w2["days90"] == 0 and wj["decision90"].startswith("继续观察")
    assert TH.watch_decision({"episodes": [{"W_alert": True}] * 3, "known": 600, "auc_W": 0.7, "auc_A0": 0.6},
                             name="Wj", market="日経").endswith("建议把 Wj 加进日経威胁指数的显示，需要用户确认")
