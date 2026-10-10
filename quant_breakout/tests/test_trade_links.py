"""qbreak/trade_links.py：HS → 业种、出口结构、关系变密切 DE、出口增速、组汇总、时点（weight_year / 严格早于 D 的收盘）、海外消息 F。"""
import math

import numpy as np
import pandas as pd

from qbreak import trade_links as TL


def _x(rows):
    return pd.DataFrame(rows, columns=["year", "s33", "partner", "usd"])


def test_partners_and_hs_map():
    assert len(TL.PARTNERS) == 35 and sum(1 for v in TL.PARTNERS.values() if v[1]) == 26
    m = TL.HS2_S33
    assert (m["84"], m["85"], m["87"], m["30"], m["27"], m["72"], m["74"], m["90"]) == (
        "機械", "電気機器", "輸送用機器", "医薬品", "石油・石炭製品", "鉄鋼", "非鉄金属", "精密機器")
    assert "93" not in m and "97" not in m and "99" not in m
    assert len(set(m.values())) == 18 and len(m) == 95                 # 01〜96 去掉 93（武器）


def test_exposure_and_partner_share():
    x = _x([(2000, "A", 1, 30.0), (2000, "A", 2, 10.0), (2000, "B", 2, 60.0), (2001, "A", 1, 5.0)])
    e = TL.exposure(x)
    assert np.isclose(e[2000].loc["A", 1], 0.75) and np.isclose(e[2000].loc["B", 1], 0.0)
    assert np.allclose(e[2000].sum(axis=1), 1.0)
    s = TL.japan_partner_share(x)
    assert np.isclose(s.loc[2000, 1], 0.3) and np.isclose(s.loc[2000, 2], 0.7) and np.isclose(s.loc[2001, 1], 1.0)


def test_deepening_weights_partner_share_change_by_exposure():
    x = _x([(2000, "A", 1, 50.0), (2000, "B", 2, 50.0),            # 2000：两国各 50%
            (2003, "A", 1, 80.0), (2003, "B", 2, 20.0)])           # 2003：国 1 占 80%
    e, s = TL.exposure(x), TL.japan_partner_share(x)
    de = TL.deepening(e, s, 2003, 3)
    assert np.isclose(de["A"], 0.30) and np.isclose(de["B"], -0.30)
    assert TL.deepening(e, s, 2001, 3).empty                        # 没有 3 年前 → 空


def test_export_growth_relative_to_total():
    x = _x([(2000, "A", 1, 100.0), (2000, "B", 1, 100.0), (2003, "A", 1, 300.0), (2003, "B", 1, 100.0)])
    g = TL.export_growth(x, 2003, 3)
    tot = math.log(400 / 200)
    assert np.isclose(g["A"], (math.log(3) - tot) * 100) and np.isclose(g["B"], (0 - tot) * 100)
    assert TL.export_growth(x, 2002, 3).empty


def test_group_exports_and_intensity():
    mapping = {"A": 1, "B": 1, "C": 2, "D": 3}
    x = _x([(2020, "A", 1, 60.0), (2020, "B", 1, 40.0), (2020, "C", 2, 10.0), (2020, "D", 2, 5.0)])
    g = TL.group_exports(x, mapping, (1, 2))
    assert set(g["s33"]) == {1, 2} and np.isclose(g[g["s33"] == 1]["usd"].sum(), 100.0)       # 组 3 不要
    e = TL.group_intensity(x, {"A": 0.5, "B": 0.1, "C": 0.2}, mapping, (1, 2))
    assert np.isclose(e[1], 100 / (60 / 0.5 + 40 / 0.1)) and np.isclose(e[2], 0.2)


def test_weight_year():
    assert TL.weight_year(pd.Period("2010-03", "M")) == 2008 and TL.weight_year(pd.Period("2010-04", "M")) == 2009
    assert TL.weight_year(pd.Period("2010-12", "M")) == 2009


def test_prior_close_is_strictly_before():
    d = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-03"]))
    pc = TL.prior_close(d, pd.DatetimeIndex(["2020-01-31", "2020-02-28", "2020-01-30"]))
    assert list(pc.iloc[:2]) == [1.0, 3.0] and np.isnan(pc.iloc[2])                         # 当天的不算


def test_month_returns_before():
    days = pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-27", "2020-02-28", "2020-03-30", "2020-03-31"])
    jp_end = pd.Series(pd.to_datetime(["2020-01-31", "2020-02-28", "2020-03-31"]), index=pd.period_range("2020-01", periods=3, freq="M"))
    c = {1: pd.Series([100.0, 999.0, 110.0, 999.0, 121.0, 999.0], index=days),
         2: pd.Series([100.0, 100.0, 100.0, 100.0, 100.0, 100.0], index=days)}                # 一直不动 → 不算
    r = TL.month_returns_before(c, jp_end)
    assert np.isnan(r.loc[pd.Period("2020-01", "M"), 1]) and np.isclose(r.loc[pd.Period("2020-02", "M"), 1], 10.0)
    assert np.isclose(r.loc[pd.Period("2020-03", "M"), 1], 10.0) and r[2].isna().all()


def test_foreign_signal_renormalises_and_uses_known_year():
    exp = {2008: pd.DataFrame({1: [0.5, 0.0], 2: [0.25, 1.0], 3: [0.25, 0.0]}, index=["A", "B"]),
           2009: pd.DataFrame({1: [1.0, 0.0], 2: [0.0, 1.0], 3: [0.0, 0.0]}, index=["A", "B"])}
    cret = pd.DataFrame({1: [10.0, 10.0], 2: [-10.0, -10.0], 3: [np.nan, np.nan]}, index=pd.PeriodIndex(["2010-03", "2010-04"], freq="M"))
    f = TL.foreign_signal(exp, cret)
    a = f.loc[pd.Period("2010-03", "M")]                                                      # 1〜3 月 → 2008 年的结构
    assert np.isclose(a["A"], (0.5 * 10 - 0.25 * 10) / 0.75) and np.isclose(a["B"], -10.0)   # 国 3 没收益 → 在 1、2 之间归一
    assert np.isclose(f.loc[pd.Period("2010-04", "M"), "A"], 10.0)                            # 4 月起 → 2009 年
    fi = TL.foreign_signal(exp, cret, intensity=pd.Series({"A": 0.5, "B": 0.1}))
    assert np.isclose(fi.loc[pd.Period("2010-04", "M"), "A"], 5.0) and np.isclose(fi.loc[pd.Period("2010-04", "M"), "B"], -1.0)
    base = pd.DataFrame({1: [0.5], 2: [0.5], 3: [0.0]}, index=[2009])
    fm = TL.foreign_signal(exp, cret, base=base)
    assert np.isclose(fm.loc[pd.Period("2010-04", "M"), "A"], 10.0) and np.isclose(fm.loc[pd.Period("2010-04", "M"), "B"], -10.0)
    assert pd.Period("2010-03", "M") not in fm.index or fm.loc[pd.Period("2010-03", "M")].isna().all()   # 2008 年没有 base → NaN
