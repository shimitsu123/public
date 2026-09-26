"""qbreak/macro_now.py：健康度用宏观层自己的阈值上色、综合分；新数据的变换、改善 / 恶化、「第一次看到」与「新」标记；日程过滤。"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from qbreak import macro_now as MN
from qbreak.calendar_jp import JST
from qbreak.macro import TH


def test_status_rules():
    assert MN.status(None, 1, 2) == "none"
    assert MN.status(1.9, 2, 3) == "good" and MN.status(2, 2, 3) == "warn" and MN.status(3, 2, 3) == "bad"
    assert MN.status(30, 25, None, higher_is_worse=False) == "good" and MN.status(20, 25, None, higher_is_worse=False) == "warn"


def _frame(vix=15.0, us10y=4.5, brent=80.0, chg=2.0, fx=150.0):
    idx = pd.bdate_range("2025-01-01", periods=300)
    return pd.DataFrame({"vix": vix, "us10y": us10y, "brent": brent, "brent_chg20_pct": chg, "usdjpy": fx}, index=idx)


def test_health_tiles_thresholds_and_score():
    idx = pd.bdate_range("2024-01-01", periods=400)
    n225 = pd.Series(np.r_[np.full(390, 100.0), np.full(10, 120.0)], index=idx)       # 最后远高于 250 日线
    fr = _frame(vix=TH["vix_panic"] + 1, us10y=TH["us10y_high"] + 0.01, brent=TH["oil_high"] - 1, chg=TH["oil_shock20_pct"] + 1)
    jgb = pd.Series(1.0, index=idx)
    thr = {"US": pd.Series(85.0, index=idx), "JP": pd.Series(65.0, index=idx)}
    h = MN.health(fr, n225, jgb, None, {"hy_oas_bp": 250, "breadth_pct": 20, "as_of": "2026-09-24"}, thr)
    t = {x["key"]: x for x in h["tiles"]}
    assert t["n225_ma"]["status"] == "good" and t["n225_ma"]["value"] > 3
    assert t["vix"]["status"] == "bad" and t["us10y"]["status"] == "warn" and t["jgb10y"]["status"] == "good"
    assert t["brent"]["status"] == "warn" and "近 20 日" in t["brent"]["note"]      # 价位没到线，但 20 日急涨 → 注意
    assert t["hy"]["status"] == "good" and t["hy"]["value"] == 250 and t["breadth"]["status"] == "warn"
    assert t["threat_us"]["status"] == "bad" and t["threat_jp"]["status"] == "warn"
    assert len(t["vix"]["spark"]) == MN.SPARK_N and t["vix"]["ref"] == TH["vix_high"]
    c = h["counts"]
    assert c == {"good": 4, "warn": 4, "bad": 2, "none": 0}
    assert h["score"] == round((4 * 1 + 4 * 0.5) / 10 * 100)
    empty = MN.health()
    assert empty["score"] is None and empty["counts"]["none"] == len(empty["tiles"])


def test_n225_band_edges():
    idx = pd.bdate_range("2024-01-01", periods=300)
    down = pd.Series(np.r_[np.full(290, 100.0), np.full(10, 90.0)], index=idx)
    t = {x["key"]: x for x in MN.health(None, down)["tiles"]}
    assert t["n225_ma"]["status"] == "bad"


def test_transform_units():
    s = pd.Series([100.0, 110.0, 99.0], index=pd.date_range("2026-01-01", periods=3, freq="MS"))
    assert MN.transform(s, "mom").round(4).tolist()[1:] == [10.0, -10.0]
    assert MN.transform(pd.Series([197000.0]), "k10").tolist() == [19.7]
    assert MN.transform(pd.Series([100.0, 262.0]), "diff10").tolist()[1] == pytest.approx(16.2)
    y = pd.Series(np.arange(100, 114, dtype=float), index=pd.date_range("2025-01-01", periods=14, freq="MS"))
    assert MN.transform(y, "yoy").iloc[-1] == pytest.approx((113 / 101 - 1) * 100)


def test_releases_direction_and_new_flags():
    now = dt.datetime(2026, 9, 26, 10, 0, tzinfo=JST)
    m = pd.date_range("2024-01-01", periods=30, freq="MS")
    raw = {"us_retail": pd.Series(np.linspace(100, 130, 30), index=m),
           "us_claims": pd.Series(np.r_[np.full(29, 200000.0), 230000.0], index=pd.date_range("2026-03-01", periods=30, freq="W-SAT"))}
    rel, seen = MN.releases(raw, {}, now)
    r = {x["key"]: x for x in rel}
    assert r["us_retail"]["good"] == -1 and r["us_retail"]["new"] is False        # 环比从 +1.0% 降到 +0.97% → 恶化；第一次运行不算「新」
    assert r["us_claims"]["value"] == 23.0 and r["us_claims"]["good"] == -1 and "裁员增加" in r["us_claims"]["impact"]
    assert r["us_sent"]["value"] is None and r["us_sent"]["error"]
    assert seen["us_retail"] == {"obs": "2026-06", "seen": None}
    raw["us_retail"] = pd.Series(np.linspace(100, 131, 31), index=pd.date_range("2024-01-01", periods=31, freq="MS"))
    rel2, seen2 = MN.releases(raw, seen, now)
    r2 = {x["key"]: x for x in rel2}
    assert r2["us_retail"]["new"] is True and r2["us_retail"]["obs"] == "2026-07" and seen2["us_retail"]["seen"].startswith("2026-09-26T10:00")
    later = now + dt.timedelta(hours=MN.NEW_HOURS + 1)
    rel3, _ = MN.releases(raw, seen2, later)
    assert {x["key"]: x for x in rel3}["us_retail"]["new"] is False             # 24 小时后不再标「新」
    assert r["us_claims"]["obs"] == str(raw["us_claims"].index[-1].date())       # 每周的数据期写到日


def test_upcoming_events_window():
    ev = [{"date": "2026-09-25", "kind": "CPI"}, {"date": "2026-10-02", "kind": "NFP", "name": "9月"}, {"date": "2026-11-30", "kind": "BOJ"},
          {"date": "bad"}]
    out = MN.upcoming(ev, dt.date(2026, 9, 26))
    assert [e["kind"] for e in out] == ["NFP"] and out[0]["name"] == "9月"
