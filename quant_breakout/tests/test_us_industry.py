"""美国独立复现（qbreak/us_industry.py、qbreak/factors.py ff_industries、scripts/us_replication_study.py）：Ken French 表的解析、
相对收益、两半、埋进去的关系能被检验发现（错开 1 个月的偷看关系发现不了）、时间错开的对照、复现与汇总、V6 的扩张 z 值。"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak import factors
from qbreak import supply_chain as SC
from qbreak import us_industry as UI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import us_replication_study as USR                                          # noqa: E402

FF_TEXT = """This file was created using the 202608 CRSP database.

  Average Value Weighted Returns -- Monthly
,Agric,Food ,Chips
192607,   2.36,   0.09, -99.99
192608,   2.23,   2.71,   1.50
192609,  -0.57, -999.00,   4.02

  Average Equal Weighted Returns -- Monthly
,Agric,Food ,Chips
192607,   9.00,   9.00,   9.00

  Average Value Weighted Returns -- Annual
,Agric,Food ,Chips
1927,  10.00,  10.00,  10.00
"""


def test_parse_ff_monthly_tables_and_missing():
    vw = factors.parse_ff_monthly(FF_TEXT)
    assert list(vw.columns) == ["Agric", "Food", "Chips"]
    assert list(vw.index) == list(pd.to_datetime(["1926-07-01", "1926-08-01", "1926-09-01"]))
    assert vw.loc["1926-08-01", "Food"] == 2.71 and np.isnan(vw.loc["1926-07-01", "Chips"]) and np.isnan(vw.loc["1926-09-01", "Food"])
    ew = factors.parse_ff_monthly(FF_TEXT, "Average Equal Weighted Returns -- Monthly")
    assert len(ew) == 1 and ew.iloc[0].tolist() == [9.0, 9.0, 9.0]                  # 年度表（4 位数的年份）不会混进来


def test_relative_log_and_halves():
    R = pd.DataFrame({"a": [10.0, 0.0], "b": [-10.0, 0.0]}, index=pd.to_datetime(["2020-01-01", "2020-02-01"]))
    L = UI.relative_log(R)
    la, lb = math.log(1.1) * 100, math.log(0.9) * 100
    assert list(L.index) == list(pd.to_datetime(["2020-01-31", "2020-02-29"]))
    assert L.iloc[0, 0] == pytest.approx(la - (la + lb) / 2) and L.iloc[0].sum() == pytest.approx(0)
    m = pd.date_range("1970-01-31", periods=680, freq="ME")
    H = UI.halves(m)
    assert H["H1"][0] == m[0] and H["H2"][0] == m[340] and H["H2"][1] == m[-1] and H["H1"][1] < H["H2"][0]
    assert m[340] == pd.Timestamp("1998-05-31")                                     # 与登记的两半一致


def _planted(n=400, beta=-0.8, lag_months=2, seed=0):
    """物价 m 月的变化 → 行业 m+lag 月的相对收益（lag = 2：M+1 月中旬公布 → 合法；lag = 1：要偷看）。"""
    rng = np.random.default_rng(seed)
    starts = pd.date_range("1990-01-01", periods=n, freq="MS")
    P = pd.DataFrame({"x": 100 * np.exp(np.cumsum(rng.normal(0, 0.03, n))), "z": 100 * np.exp(np.cumsum(rng.normal(0, 0.03, n)))},
                     index=starts)
    months = starts.to_period("M").to_timestamp("M")
    d = np.log(P["x"]).diff().to_numpy() * 100
    eff = np.r_[np.full(lag_months, np.nan), d[:-lag_months]]
    M = pd.DataFrame({"A": rng.normal(0, 3, n) + beta * np.nan_to_num(eff), "B": rng.normal(0, 3, n)}, index=months)
    return P, M, months


def test_scan_finds_legal_relation_but_not_lookahead():
    for lag, should in ((2, True), (1, False)):
        P, M, months = _planted(lag_months=lag)
        dP = UI.ppi_changes(P, months, (1,))
        Y = {1: SC.ahead(M, 1)}
        mon = months[24:]
        S_ = UI.scan(dP, Y, [("x", "A"), ("z", "A"), ("x", "B")], mon, UI.halves(mon), 0, "成本")
        t = S_.set_index(["src", "target", "half"])["t"]
        if should:
            assert t[("x", "A", "H1")] < -4 and t[("x", "A", "H2")] < -4
        else:
            assert abs(t[("x", "A", "H1")]) < 3 and abs(t[("x", "A", "H2")]) < 3
        assert abs(t[("z", "A", "H1")]) < 3 and abs(t[("x", "B", "H2")]) < 3


def test_placebo_shift_breaks_relation_and_replicate_summary():
    P, M, months = _planted(lag_months=2)
    mon = months[24:]
    dP = UI.ppi_changes(P, months, (1,))
    Y = {1: SC.ahead(M, 1)}
    t0, pt = UI.placebo_ts(dP[1]["x"], Y[1]["A"], mon, (mon[0], mon[-1]), 0, 24)
    assert t0 < -5 and len(pt) == len(mon) - 48 + 1 and np.nanmax(np.abs(pt)) < abs(t0)
    assert SC.placebo_p(t0, pt, -1) == pytest.approx(1 / (1 + len(pt)), abs=1e-4)                # 比所有错开的都极端（p 取 4 位小数）
    S_ = pd.concat([UI.scan(dP, Y, [("x", "A"), ("z", "A"), ("z", "B")], mon, UI.halves(mon), 0, "成本"),
                    UI.scan(dP, Y, [("x", "A")], mon, UI.halves(mon), 120, "对照")], ignore_index=True)
    D = UI.replicate(S_, 0.10)
    r = D.set_index(["family", "src", "target"])
    assert bool(r.loc[("成本", "x", "A"), "rep"]) and not bool(r.loc[("对照", "x", "A"), "rep"])
    sm = UI.summary(D)
    assert sm["成本"]["n"] == 3 and sm["成本"]["rep"] >= 1 and sm["对照"]["rep"] == 0


def test_ppi_changes_publication_lag():
    P = pd.DataFrame({"x": [100.0, 110.0, 121.0, 133.1]}, index=pd.date_range("2020-01-01", periods=4, freq="MS"))
    months = pd.date_range("2020-01-31", periods=4, freq="ME")
    d = UI.ppi_changes(P, months, (1, 3))
    assert np.isnan(d[1]["x"].iloc[1]) and d[1]["x"].iloc[2] == pytest.approx(math.log(1.1) * 100)   # 3 月末只知道 2 月的物价
    assert d[3]["x"].isna().all()


def test_v6_uses_expanding_z_and_all_three_inputs():
    idx = pd.date_range("2000-01-01", periods=80, freq="MS")
    rng = np.random.default_rng(2)
    Pj = pd.DataFrame({c: 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 80))) for c in USR.JP_INPUTS}, index=idx)
    months = pd.date_range("2000-01-31", periods=80, freq="ME")
    v = USR.v6_panel(Pj, months)
    assert v.iloc[:39].isna().all() and v.iloc[45:].notna().all()                     # 3 个月变化从 2000-05 起，扩张 z 要 36 个月
    ch = SC.price_change(Pj, months, 3)
    k = 60
    z = [(ch[c].iloc[k] - ch[c].iloc[:k + 1].mean()) / ch[c].iloc[:k + 1].std() for c in USR.JP_INPUTS]
    assert v.iloc[k] == pytest.approx(-np.mean(z))                                    # 只用到当月为止的数据
    Pj2 = Pj.copy()
    Pj2.iloc[70:] *= 5                                                                # 之后的数据变了，之前的值不变
    assert USR.v6_panel(Pj2, months).iloc[:70].equals(v.iloc[:70])


def test_registered_lists_are_consistent():
    assert len(USR.R_LIST) == 12 and set(USR.R_CORE) <= {r[0] for r in USR.R_LIST}
    for code, src, tgt, sg, w, h in USR.R_LIST:
        assert src in UI.PPI and tgt in UI.FF49_CN and sg in (-1, 1) and w in SC.WINDOWS and h in SC.HORIZONS and code in USR.JP_OF
    for name, src, tgt, sg, kind in USR.U_LIST:
        assert (src in UI.PPI) if kind == "ppi" else (src in UI.FF49_CN)
        assert tgt in UI.FF49_CN and sg in (-1, 0, 1)
    assert len(UI.PPI) == 12 and len(UI.FF49_CN) == 49
