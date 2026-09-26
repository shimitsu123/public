"""J-Quants 付费档的特征（qbreak/jq_data.py；scripts/jq_study.py 用）：会社予想修正与增益率、信用余额的公布滞后、大额空头合计、
当时真实的一手价格、批量下载的缓存；引擎的「一手」钩子默认不改变任何结果。"""
import gzip

import numpy as np
import pandas as pd
import pytest

from qbreak import jq_data as JD


def _fins(rows):
    cols = JD.DATASETS["fins"][1]
    return pd.DataFrame([{c: r.get(c, np.nan) for c in cols} for r in rows], columns=cols).astype(object)


def _company():
    return _fins([
        {"DiscDate": "2017-05-10", "DiscTime": "15:00", "DocType": "FYFinancialStatements_Consolidated_JP", "CurPerType": "FY",
         "CurFYEn": "2017-03-31", "NxtFYEn": "2018-03-31", "OP": "100", "FOP": "", "NxFOP": "120"},
        {"DiscDate": "2017-08-05", "DiscTime": "15:00", "DocType": "1QFinancialStatements_Consolidated_JP", "CurPerType": "1Q",
         "CurFYEn": "2018-03-31", "OP": "30", "FOP": "120"},
        {"DiscDate": "2017-10-20", "DiscTime": "15:00", "DocType": "EarnForecastRevision", "CurPerType": "FY",
         "CurFYEn": "2018-03-31", "FOP": "150"},
        {"DiscDate": "2017-11-05", "DiscTime": "15:00", "DocType": "2QFinancialStatements_Consolidated_JP", "CurPerType": "2Q",
         "CurFYEn": "2018-03-31", "OP": "70", "FOP": "150"},
        {"DiscDate": "2018-05-10", "DiscTime": "15:00", "DocType": "FYFinancialStatements_Consolidated_JP", "CurPerType": "FY",
         "CurFYEn": "2018-03-31", "NxtFYEn": "2019-03-31", "OP": "160", "NxFOP": "170"},
    ])


def test_fins_events_revision_and_growth():
    ev = JD.fins_events(_company())
    assert list(ev["fy"]) == ["2018-03-31", "2018-03-31", "2018-03-31", "2018-03-31", "2019-03-31"]
    assert np.isnan(ev["rev"].iloc[0]) and ev["rev"].iloc[1] == 0 and ev["rev"].iloc[2] == pytest.approx(25.0)   # 120 → 150
    assert ev["rev"].iloc[3] == 0 and np.isnan(ev["rev"].iloc[4])                  # 新一年的第一个予想 → 没有修正
    assert ev["yoy"].iloc[4] == pytest.approx(60.0) and ev["yoy"].iloc[:4].isna().all()   # FY：160 vs 上年 100


def test_fins_features_only_use_earlier_disclosures():
    ev = JD.fins_events(_company())
    d = pd.to_datetime(["2017-10-20", "2017-10-23", "2017-11-06", "2018-02-01", "2018-05-11", "2019-06-01"])
    F = JD.fins_features(ev, d)
    assert F.loc["2017-10-20", "g1"] == 0.0                                        # 修正当天的信号还不能用（D < 信号日）
    assert F.loc["2017-10-23", "g1"] == pytest.approx(25.0)
    assert F.loc["2017-11-06", "g1"] == pytest.approx(25.0)                        # 之后的季报只是重申 → 仍是 90 天内那次修正
    assert F.loc["2018-02-01", "g1"] == 0.0                                        # 修正已超过 90 天
    assert F.loc["2018-05-11", "g2"] == pytest.approx(60.0) and np.isnan(F.loc["2018-02-01", "g2"])
    assert F.loc["2019-06-01"].isna().all()                                        # 最近一次开示离信号日 > 200 天 → 缺值
    assert JD.fins_features(JD.fins_events(_fins([])), d).isna().all().all()


def test_profit_level_falls_back_for_banks():
    bank = _fins([{"DiscDate": "2017-05-10", "DocType": "FYFinancialStatements_Consolidated_JP", "CurPerType": "FY",
                   "CurFYEn": "2017-03-31", "NxtFYEn": "2018-03-31", "OdP": "500", "NxFOdP": "550"}])
    assert JD.profit_level(bank) == ("OdP", "FOdP", "NxFOdP")
    assert JD.fins_events(bank)["fc"].iloc[0] == 550


def test_margin_features_publication_lag_and_units():
    days = pd.bdate_range("2019-11-01", periods=90)                                # 20 日均量要先攒够 15 天
    daily = pd.DataFrame({"Date": days.strftime("%Y-%m-%d"), "Vo": "1000"})
    M = pd.DataFrame({"Date": ["2020-01-17", "2020-01-24"], "LongVol": ["5000", "8000"], "ShrtVol": ["2000", "1000"]})
    F = JD.margin_features(M, daily, days)
    fri = days.get_loc(pd.Timestamp("2020-01-17"))
    assert F.iloc[:fri + 3].isna().all().all()                                     # 周五的余额：之后第 3 个交易日前不用
    assert F.iloc[fri + 3]["m1"] == pytest.approx(5.0) and F.iloc[fri + 3]["m2"] == pytest.approx(2.0)
    nxt = days.get_loc(pd.Timestamp("2020-01-24")) + 3
    assert F.iloc[nxt]["m1"] == pytest.approx(8.0) and F.iloc[nxt - 1]["m1"] == pytest.approx(5.0)
    assert F.iloc[nxt + 16].isna().all()                                           # 之后没有新余额，超过 15 个交易日 → 缺值


def test_short_features_sum_latest_positions_above_threshold():
    R = pd.DataFrame({"DiscDate": ["2021-01-05", "2021-01-10", "2021-02-01", "2021-02-10"], "CalcDate": "",
                      "SSName": ["A", "B", "A", "C"], "ShrtPosToSO": ["0.0060", "0.0070", "0.0040", "0.0050"]})
    d = pd.to_datetime(["2021-01-05", "2021-01-06", "2021-01-11", "2021-02-02", "2021-02-11", "2022-03-01"])
    F = JD.short_features(R, d)
    assert list(F["s1"].round(4)) == [0.0, 0.6, 1.3, 0.7, 1.2, 0.0]               # A 降到 0.5% 以下 → 不算；一年以前的不算
    assert JD.short_features(R.iloc[0:0], d)["s1"].eq(0).all()


def test_real_ratio_and_bulk_cache(monkeypatch, tmp_path):
    daily = pd.DataFrame({"Date": ["2020-01-06", "2020-01-07"], "C": ["2000", "2100"]})
    adj = pd.Series([1000.0, 1050.0], index=pd.to_datetime(["2020-01-06", "2020-01-07"]))
    assert list(JD.real_ratio(daily, adj)) == [2.0, 2.0]                          # 拆股前：真实价 = 复权价 × 2

    class C:
        calls = 0

        def get(self, path, **kw):
            return [{"Key": "x/historical/2020/a.csv.gz", "Size": "0"}]

        def _once(self, path, params):
            C.calls += 1
            return 200, {"url": "https://example.invalid/a"}

        def _sleep(self, s):
            pass
    blob = gzip.compress(b"Date,Code,C,Vo,AdjC\n2020-01-06,72030,2000,10,1000\n2020-01-06,99990,1,1,1\n")
    monkeypatch.setattr(JD, "bulk_dir", lambda: tmp_path)
    files = JD.bulk_download(C(), "/equities/bars/daily", http_get=lambda url: blob, log=lambda s: None)
    files2 = JD.bulk_download(C(), "/equities/bars/daily", http_get=lambda url: blob, log=lambda s: None)
    assert files == files2 and C.calls == 1                                        # 已下载的文件不再下（月度文件不会变）

    class C2(C):
        lm = "2026-09-01T00:00:00Z"

        def get(self, path, **kw):
            return [{"Key": "x/historical/2020/a.csv.gz", "Size": "0", "LastModified": C2.lm}]
    JD.bulk_download(C2(), "/equities/bars/daily", http_get=lambda url: blob, log=lambda s: None)
    n = C.calls
    JD.bulk_download(C2(), "/equities/bars/daily", http_get=lambda url: blob, log=lambda s: None)
    assert C.calls == n                                                           # LastModified 没变 → 不重下
    C2.lm = "2026-09-26T00:00:00Z"                                               # 订正覆盖了同一个 Key → 重下
    JD.bulk_download(C2(), "/equities/bars/daily", http_get=lambda url: blob, log=lambda s: None)
    assert C.calls == n + 1
    df = JD.read_bulk(files, JD.DATASETS["daily"][1], {"72030"})
    assert list(df["Code"]) == ["72030"] and JD.code5("7203.T") == "72030" and JD.code5("285A.T") == "285A0"


def test_engine_lot_hook_is_inert_by_default():
    from qbreak.unified import UnifiedEngine
    e = UnifiedEngine.__new__(UnifiedEngine)
    e.lots, e.col = np.array([100, 1]), {"7203.T": 0, "1655.T": 1}
    assert e._lot_for("7203.T", 5) == 100 and e._lot_for("1655.T", 5) == 1
