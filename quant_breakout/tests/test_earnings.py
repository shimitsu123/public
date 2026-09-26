"""决算数据研究（qbreak/earnings_hist.py、scripts/earnings_study.py；2026-09-26 事先登记）：日期换算成日本日期、只用信号日之前的发表、
EAR 窗口、离太久 → 缺值、近期 EAR、缓存与失败退回、门槛只用之前的年份、判定规则、埋进去的关系能被找出来、短観 X2 与前向记录一致。"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak import earnings_hist as EH
from qbreak import score_forward as SF
from qbreak import tankan as TK

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import earnings_study as ES                                                  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _yahoo(stamps, est, rep, sur):
    idx = pd.DatetimeIndex(pd.to_datetime(stamps, utc=True)).tz_convert("America/New_York")      # yfinance 给的是美东时区
    return pd.DataFrame({"EPS Estimate": est, "Reported EPS": rep, "Surprise(%)": sur}, index=idx)


def test_parse_converts_to_japan_dates():
    df = _yahoo(["2026-11-05 01:00:00-05:00", "2004-08-03 00:00:00-04:00", "2025-05-12 22:30:00-04:00", "2025-05-13 02:00:00-04:00"],
                [10.0, 5.0, 3.0, 3.0], [12.0, 4.0, 3.3, 9.9], [20.0, -20.0, 10.0, 99.0])
    E = EH.parse(df)
    assert list(E["date"].dt.strftime("%Y-%m-%d")) == ["2004-08-03", "2025-05-13", "2026-11-05"]   # 美东晚上 = 日本第二天；同一天只留第一条
    assert E.loc[E["date"] == "2025-05-13", "surprise"].item() == 10.0
    assert E.loc[E["date"] == "2026-11-05", "eps_rep"].item() == 12.0
    assert EH.parse(None).columns.tolist() == EH.COLS and len(EH.parse(pd.DataFrame())) == 0
    only = EH.parse(pd.DataFrame({"EPS Estimate": [1.0]}, index=pd.DatetimeIndex(["2020-01-01"], tz="UTC")))
    assert np.isnan(only["surprise"].iloc[0])                                     # 没有的列 → 缺值


def test_fetch_caches_and_falls_back():
    calls = []

    def ok(t):
        calls.append(t)
        return _yahoo(["2024-02-06 01:00:00-05:00"], [1.0], [1.5], [50.0])

    def down(t):
        raise RuntimeError("HTTP 429")
    a = EH.fetch("1111.T", getter=ok, wait=0)
    b = EH.fetch("1111.T", getter=down, wait=0)                                    # 缓存还新 → 不下载
    assert len(calls) == 1 and a.equals(b) and a["surprise"].item() == 50.0
    c = EH.fetch("1111.T", max_age_days=0, getter=down, tries=2, wait=0)           # 过期但下载失败 → 旧缓存
    assert c["surprise"].item() == 50.0
    with pytest.raises(RuntimeError, match="2222.T"):
        EH.fetch("2222.T", getter=down, tries=1, wait=0)
    got, bad = EH.load_many(["1111.T", "2222.T"], pause=0, getter=down)
    assert list(got) == ["1111.T"] and list(bad) == ["2222.T"]


def test_earnings_features_use_only_past_announcements():
    ix = pd.bdate_range("2024-01-01", periods=200)
    close = pd.Series(100 * np.exp(np.arange(200) * 0.01), index=ix)                # 每天 +1%
    idx = pd.Series(1000 * np.exp(np.arange(200) * 0.004), index=ix)                # 日経每天 +0.4%
    E = pd.DataFrame({"date": pd.to_datetime(["2024-01-10", "2024-01-20"]), "eps_est": [1.0, 1.0], "eps_rep": [1.2, 0.9],
                      "surprise": [20.0, -10.0]})
    d = lambda s: pd.Timestamp(s)                                                  # noqa: E731
    F = EH.earnings_features(close, idx, E, [d("2024-01-10"), d("2024-01-11"), d("2024-01-19"), d("2024-01-22"), d("2024-02-20"),
                                             d("2024-05-01")])
    assert F.loc["2024-01-10"].isna().all()                                        # 发表当天的信号不用这次（D < 信号日）
    r = F.loc["2024-01-11"]
    assert r["days_since"] == 1 and r["surprise"] == 20.0
    assert r["ear"] == pytest.approx(2 * (1.0 - 0.4))                              # 1/9 收盘 → 1/11 收盘：两天，个股 − 日経
    assert F.loc["2024-01-19", "surprise"] == 20.0                                 # 1/20（周六）的发表还没到
    w = F.loc["2024-01-22"]                                                        # 周六发表：1/19 收盘 → 1/22 收盘
    assert w["days_since"] == 1 and w["surprise"] == -10.0 and w["ear"] == pytest.approx(1.0 - 0.4)
    assert F.loc["2024-02-20", "ear_recent"] == 0.0 and F.loc["2024-02-20", "ear"] == pytest.approx(0.6)   # 超过 20 个交易日 → E3 = 0
    assert F.loc["2024-01-22", "ear_recent"] == pytest.approx(0.6)
    assert F.loc["2024-05-01"].isna().all()                                        # 离上次发表 > 70 个交易日 → 缺值
    assert EH.earnings_features(close, idx, E.iloc[0:0], [d("2024-01-11")]).isna().all().all()


def test_walk_thresholds_use_only_prior_closed_trades():
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2011-01-03", "2016-12-30")
    tr = pd.DataFrame({"sig_date": rng.choice(days, 600), "e2": rng.normal(0, 1, 600)})
    tr["sig_date"] = pd.to_datetime(tr["sig_date"])
    tr["exit_date"] = tr["sig_date"] + pd.Timedelta(days=20)
    rows = pd.DataFrame({"date": pd.to_datetime(["2015-03-02", "2012-05-01"]), "ticker": ["A.T", "B.T"], "e2": [0.1, 0.2]})
    sc = ES.walk_thresholds(rows, tr, "e2")
    cut = pd.Timestamp("2015-01-01")
    want = np.quantile(tr[(tr["sig_date"] < cut) & (tr["exit_date"] < cut)]["e2"], 1 / 3)
    assert sc.loc[0, "thr"] == pytest.approx(want) and sc.loc[0, "score"] == 0.1
    assert np.isnan(sc.loc[1, "thr"])                                              # 2013 年以前不打分（不跳过）


def _passing():
    return {"auc": {"all": 0.57, "lo99": 0.53, "hi99": 0.61}, "seg": {"N225": 0.56, "大中型": 0.55}, "coverage": 0.5, "coverage_n225": 0.9,
            "kept": {"O1": {"n": 500, "win": 45.0, "exp": 1.0}, "O2": {"n": 600, "win": 50.0, "exp": 1.2}},
            "all_half": {"O1": {"n": 800, "win": 40.0, "exp": 0.5}, "O2": {"n": 900, "win": 46.0, "exp": 0.8}},
            "s0c2": {"w20_calmar_exact": 0.40, "w20_dd_exact": -30.0}, "dauc": {"d": 0.03, "lo": 0.005, "hi": 0.06}}


def test_decide_rules():
    base = {"w20_calmar_exact": 0.363, "w20_dd_exact": -35.02}
    assert ES.decide(_passing(), base)["pass"]
    for key, patch, tag in (("auc", {"all": 0.57, "lo99": 0.49, "hi99": 0.6}, "①"), ("coverage_n225", 0.5, "①"),
                            ("seg", {"N225": 0.49, "大中型": 0.55}, "①"),
                            ("kept", {"O1": {"n": 500, "win": 42.0, "exp": 1.0}, "O2": {"n": 600, "win": 50.0, "exp": 1.2}}, "②"),
                            ("s0c2", {"w20_calmar_exact": 0.40, "w20_dd_exact": -36.0}, "③"),
                            ("dauc", {"d": 0.03, "lo": -0.001, "hi": 0.06}, "④")):
        r = _passing()
        r[key] = patch
        v = ES.decide(r, base)
        assert not v["pass"] and any(f.startswith(tag) for f in v["fails"]), key
    t = {"lo99": 0.51, "hi99": 0.6, "halves": {"O1": 0.55, "O2": 0.54}}
    assert ES.decide_tankan(t)["ok"] and not ES.decide_tankan({**t, "halves": {"O1": 0.55, "O2": 0.49}})["ok"]


def test_planted_relation_is_found_and_noise_is_not():
    rng = np.random.default_rng(1)
    n = 2500
    D = pd.DataFrame({"date": pd.to_datetime(rng.choice(pd.bdate_range("2013-01-01", "2025-12-31"), n)), "e2": rng.normal(0, 1, n),
                      "noise": rng.normal(0, 1, n)})
    D["win"] = (0.35 * D["e2"] + rng.normal(0, 1, n) > 0.3).astype(float)
    B = ES.boot(D, ["e2", "noise"])
    assert ES.auc_of(D, "e2") > 0.55 and ES.pct(B[:, 0], 0.5) > 0.5
    assert ES.pct(B[:, 1], 0.5) < 0.5 < ES.pct(B[:, 1], 99.5)
    pw = ES.power_row(D)
    assert pw["n"] == n and 0.008 < pw["se"] < 0.02 and pw["mde"] == pytest.approx(0.5 + 2.8 * pw["se"], abs=1e-3)
    ind = pd.Series(rng.choice(["化学", "銀行業", "機械"], n))
    svy = pd.Series(D["date"].dt.to_period("Q").astype(str))
    key = ind + "|" + svy                                                          # 同一业种 × 同一季度的交易结果一起好 / 一起坏（行业冲击）
    shock = key.map({k: rng.normal(0, 1) for k in sorted(set(key))}).to_numpy(float)
    D2 = D.assign(win=(shock + rng.normal(0, 1, n) > 0.3).astype(float))
    pw1, pw2 = ES.power_row(D2), ES.power_row(D2, industry=ind, survey=svy)
    assert pw2["se"] > 1.5 * pw1["se"]                                             # 行业层面的信号：同样的笔数，能分辨的效果粗得多


def test_tankan_tables_match_forward_record_x2():
    """研究里的 X2 与前向记录（qbreak/score_forward.py）的 X2 是同一个数。"""
    rng = np.random.default_rng(5)
    q_all = pd.date_range("1990-03-31", "2026-06-30", freq="QE")
    vals = {}
    for ind in TK.IND:
        for item in TK.ITEMS:
            vals[TK.code(ind, item)] = pd.Series(np.round(np.cumsum(rng.normal(0, 4, len(q_all))), 0), index=q_all)
        vals[TK.code(ind, "biz", True)] = pd.Series(0.0, index=q_all)
    fetch = lambda c: vals[c]                                                      # noqa: E731
    links = json.loads((ROOT / "var" / "io_links_2020.json").read_text(encoding="utf-8"))
    s33 = {f"{c}.T": v for c, v in json.loads((ROOT / "var" / "industry_s33.json").read_text(encoding="utf-8"))["s33"].items()}
    tabs = ES.tankan_tables(s33, links, fetch)
    rows = pd.DataFrame({"date": pd.to_datetime(["2015-07-06", "2020-12-21", "2026-07-06", "2026-07-03"]),
                         "ticker": ["4063.T", "8306.T", "6501.T", "7203.T"]})
    got = ES.tankan_columns(rows, s33, tabs)
    fwd, svy = SF.x2_lookup(SF.x2_load(s33, fetch=fetch, links=links), rows["date"], list(rows["ticker"]))
    assert np.allclose(got["x2"].to_numpy(float), fwd, equal_nan=True, atol=1e-6) and list(got["x2_svy"]) == svy
    assert list(got["x1_svy"]) == ["2015-06-30", "", "2026-06-30", "2026-03-31"]      # 银行业没有对应的短観业种 → X1 空（X2 有：顾客业种）
    assert np.isnan(got["x1"].iloc[1]) and np.isfinite(got["x2"].iloc[1])
