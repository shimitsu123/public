"""qbreak/energy_demand.py：同比的窗口与公布滞后（不看未来）、周度的可用日与过旧、STEO 只用当时那一版、各解析器。"""
import io

import numpy as np
import pandas as pd

from qbreak import energy_demand as E


def _monthly(start="2000-01", n=120, base=100.0):
    idx = pd.date_range(start, periods=n, freq="MS")
    return pd.Series(base, index=idx, dtype=float)


def test_monthly_growth_window_and_lag():
    s = _monthly()
    s[s.index >= "2005-01-01"] = 110.0                                        # 2005-01 起 +10%
    months = pd.date_range("2004-10-31", "2006-06-30", freq="ME")
    g = E.monthly_growth(s, months, 1, 2)
    assert not np.isnan(g["2004-10-31"]) and abs(g["2004-10-31"]) < 1e-9
    assert abs(g["2005-02-28"]) < 1e-9                                        # 2 个月滞后：2 月底只知道 2004-12
    assert abs(g["2005-03-31"] - 100 * np.log(1.1)) < 1e-9                    # 3 月底才知道 2005-01
    g3 = E.monthly_growth(s, months, 3, 0)
    assert abs(g3["2005-01-31"] - 100 * np.log((110 + 100 + 100) / 300)) < 1e-9
    assert abs(g["2006-03-31"]) < 1e-9                                        # 一年后同比回到 0


def test_monthly_growth_ignores_future_values():
    s = _monthly()
    months = pd.date_range("2003-01-31", "2008-12-31", freq="ME")
    a = E.monthly_growth(s, months, 3, 2)
    s2 = s.copy()
    s2[s2.index >= "2006-01-01"] *= 3                                         # 改 2006 年以后的数据
    b = E.monthly_growth(s2, months, 3, 2)
    keep = months < pd.Timestamp("2006-03-31")                                # 2006-01 的数据 2006-03 底才可用
    assert np.allclose(a[keep], b[keep], equal_nan=True) and not np.allclose(a[~keep], b[~keep], equal_nan=True)


def test_monthly_growth_missing_month_gives_nan():
    s = _monthly().drop(pd.Timestamp("2004-06-01"))
    g = E.monthly_growth(s, pd.date_range("2004-06-30", "2004-08-31", freq="ME"), 3, 0)
    assert g.isna().all()                                                     # 窗口里缺一个月 → 没有值（不补）


def test_weekly_growth_availability_and_staleness():
    idx = pd.date_range("2000-01-07", "2006-12-29", freq="W-FRI")
    s = pd.Series(100.0, index=idx)
    s[s.index >= "2005-06-03"] = 120.0
    months = pd.DatetimeIndex(["2005-05-31", "2005-06-30", "2005-07-31"])
    g = E.weekly_growth(s, months, 4)
    assert abs(g.iloc[0]) < 1e-9                                              # 5 月底：6/3 那周还没公布
    last = s.index[s.index + pd.Timedelta(days=E.WEEKLY_AVAIL_DAYS) <= pd.Timestamp("2005-06-30")][-4:]
    want = 100 * np.log(s[last].mean() / 100.0)
    assert abs(g.iloc[1] - want) < 1e-9
    g2 = E.weekly_growth(s[s.index <= "2005-06-03"], pd.DatetimeIndex(["2005-07-31"]), 4)
    assert g2.isna().all()                                                    # 最新一周太旧 → 没有值


def test_steo_growth_uses_only_that_vintage():
    rows = []
    for v in pd.date_range("2010-01-01", "2010-06-01", freq="MS"):
        for m in pd.date_range("2008-01-01", "2011-12-01", freq="MS"):
            val = 100.0 * (1.2 if (m >= pd.Timestamp("2009-06-01") and v >= pd.Timestamp("2010-05-01")) else 1.0)
            rows.append({"vintage": v, "month": m, "series": "patc_world", "value": val})
    V = pd.DataFrame(rows)
    months = pd.DatetimeIndex(["2010-03-31", "2010-05-31", "2010-08-31", "2010-09-30"])
    g = E.steo_growth(V, "patc_world", months, 1)
    assert abs(g.iloc[0]) < 1e-9                                              # 3 月版：没有修订
    assert abs(g.iloc[1] - 100 * np.log(1.2)) < 1e-9                          # 5 月版把 2009-06 以后改成 120（数据月 2010-03 vs 2009-03 → 120/100）
    assert abs(g.iloc[2] - 100 * np.log(1.2)) < 1e-9                          # 8 月底：最新是 6 月版（旧 2 个月以内）
    assert np.isnan(g.iloc[3])                                                # 9 月底：最新一版旧 3 个月 → 没有值


def test_steo_vintage_list():
    import datetime as dt
    L = E.steo_vintage_list(dt.date(2008, 1, 10))
    assert L[0] == (2007, 10) and L[-1] == (2007, 12)                         # 1 月版 13 日之后才算有
    assert E.steo_vintage_list(dt.date(2008, 1, 14))[-1] == (2008, 1)


def test_parse_steo_xlsx():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "3atab"
    ws.append(["Table of Contents", "Table 3a"])
    ws.append([None, "STEO"])
    ws.append(["Forecast date:", None, 2022] + [None] * 23)
    ws.append([None, None] + ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] * 2)
    ws.append(["patc_world", "Total World Consumption"] + list(range(24)))
    ws.append(["PATC_CH", "China"] + [5.0] * 24)
    buf = io.BytesIO()
    wb.save(buf)
    V = E.parse_steo(buf.getvalue())
    assert V.index[0] == pd.Timestamp("2022-01-01") and V.index[-1] == pd.Timestamp("2023-12-01")
    assert V.loc[pd.Timestamp("2023-02-01"), "patc_world"] == 13 and V["patc_ch"].eq(5.0).all()


def test_parse_customs_and_jodi():
    hdr = [["《世界》"], ["WORLD"], ["報道発表品目名", "総額", "原油及び粗油", "", "液化天然ガス", ""], ["概況品名"], ["コード"],
           ["", "金額", "数量", "金額", "数量", "金額"], ["1988/01", "1", "100", "5", "30", "6"], ["1988/02", "1", "-", "5", "31", "6"],
           ["Years/Months"]]
    raw = "\n".join(",".join(r) for r in hdr).encode("cp932")
    C = E.parse_customs(raw)
    assert list(C.columns) == ["原油及び粗油", "液化天然ガス"] and C.loc["1988-01-01", "原油及び粗油"] == 100
    assert np.isnan(C.loc["1988-02-01", "原油及び粗油"]) and C.loc["1988-02-01", "液化天然ガス"] == 31
    csv = ("REF_AREA,TIME_PERIOD,ENERGY_PRODUCT,FLOW_BREAKDOWN,UNIT_MEASURE,OBS_VALUE,ASSESSMENT_CODE\n"
           "JP,2006-01,TOTPRODS,TOTDEMO,KBD,5000.5,1\nJP,2006-01,TOTPRODS,TOTDEMO,KL,1,1\nJP,2006-01,NAPHTHA,TOTDEMO,KBD,-,1\n"
           "DE,2006-01,TOTPRODS,TOTDEMO,KBD,2000,1\n").encode()
    J = E.parse_jodi(csv, ["JP"], ["TOTPRODS", "NAPHTHA"])
    assert len(J) == 2 and J["value"].iloc[0] == 5000.5 and np.isnan(J["value"].iloc[1])


def test_sources_have_known_kinds():
    assert len(E.SOURCES) == 18
    assert {v[1] for v in E.SOURCES.values()} == {"eia_w", "eia_m", "fred", "jodi", "customs", "steo"}
