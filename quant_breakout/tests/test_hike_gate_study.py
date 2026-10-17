"""加息预期闸门研究（scripts/hike_gate_study.py 登记检验）：闸门三种构造（每天 / 滞回 / 月度）、与美股熊的合并、循环平移保持开着的天数、判定四条与入选、常数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hike_gate_study as H                                                  # noqa: E402


def test_constants():
    assert (H.ON, H.OFF, H.CALMAR_UP, H.DD_TOL, H.CAGR_TOL, H.TIE, H.SEEDS, H.SHIFT_MIN) == (80.0, 70.0, 0.03, 2.0, 1.0, 0.02, 30, 252)
    assert H.CHECK == {"E": -5.03, "J": -0.93} and H.CHECK_TOL == 0.05 and H.GATES == ("G1", "G2", "G3") and H.KEY == "USHG"


def test_gates():
    days = pd.bdate_range("2020-01-01", periods=70)
    v = np.full(70, 50.0)
    v[:3] = np.nan
    v[10:20] = 85.0            # 开
    v[20:25] = 75.0            # G1 关、G2 仍开
    v[25:30] = 60.0            # G2 关
    pct = pd.Series(v, index=days)
    g1, g2, g3 = H.gate("G1", pct), H.gate("G2", pct), H.gate("G3", pct)
    assert not g1.iloc[:10].any() and g1.iloc[10:20].all() and not g1.iloc[20:].any()
    assert g2.iloc[10:25].all() and not g2.iloc[25:].any() and not g2.iloc[:10].any()
    ms = H.month_starts(days)
    assert len(ms) == 4 and ms[0] == days[0]
    # 月度：只看每月第一个东证日的读数；85 落在 1 月中旬 → 1 月第一天 50 → 关，整月关
    assert not g3.any()
    pct2 = pct.copy(); pct2[ms[1]] = 90.0
    g3b = H.gate("G3", pct2)
    feb = (days >= ms[1]) & (days < ms[2])
    assert g3b[feb].all() and not g3b[~feb].any()


def test_combined_bear_and_shift():
    days = pd.bdate_range("2020-01-06", periods=10)
    us = pd.Series([False, True, True, False, False], index=pd.DatetimeIndex(["2020-01-03", "2020-01-08", "2020-01-09", "2020-01-10", "2020-01-20"]))
    g = pd.Series([False] * 5 + [True] * 5, index=days)
    cb = H.combined_bear(us, g)
    assert cb.loc["2020-01-06"] == False and cb.loc["2020-01-08"] == True and cb.loc["2020-01-10"] == False and cb.iloc[5:].all()   # noqa: E712
    sh = H.circular_shift(g, 3)
    assert sh.sum() == g.sum() and sh.iloc[:3].all() and not sh.iloc[3:5].any()


def test_on_share_switches_spans():
    days = pd.bdate_range("2020-01-01", periods=260)
    g = pd.Series(False, index=days); g.iloc[100:152] = True
    assert H.on_share(g, "2020-01-01", None) == 20.0
    assert H.on_spans(g) == [(str(days[100].date()), str(days[152].date()))]
    assert H.switches_py(g, "2020-01-01", None) > 0


def test_verdict_and_pick():
    g0 = {"cagr": 12.0, "dd": -22.0, "calmar": 0.545}
    good = {"cagr": 12.5, "dd": -20.0, "calmar": 0.62, "placebo95": 0.60}
    acct = {"E": {"G0": g0, "G1": good, "G2": {**good, "dd": -24.5}, "G3": {**good, "cagr": 10.9}},
            "J": {"G0": g0, "G1": good, "G2": good, "G3": {**good, "placebo95": 0.62}}}
    assert H.verdict(acct, "G1") == (True, [])
    assert H.verdict(acct, "G2")[1] == ["b:E"] and H.verdict(acct, "G3")[1] == ["c:E", "d:J"]
    assert H.pick(acct)[0] == "G1"
    acct2 = {t: {**acct[t], "G2": {**good, "calmar": 0.63}} for t in ("E", "J")}    # 相差 < 0.02 → 编号小的
    assert H.pick(acct2)[0] == "G1"
    acct3 = {t: {**acct[t], "G2": {**good, "calmar": 0.65}} for t in ("E", "J")}
    assert H.pick(acct3)[0] == "G2"
    acct4 = {t: {**acct[t], "G1": {**good, "calmar": 0.56}} for t in ("E", "J")}    # 0.56 < 0.545 + 0.03
    assert H.verdict(acct4, "G1")[1] == ["a:E", "d:E", "a:J", "d:J"]
