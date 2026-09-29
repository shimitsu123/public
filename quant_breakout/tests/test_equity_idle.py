"""闲置资金第二轮（qbreak/idle_cash.py 的 Q1〜Q6 与反向开关 P1〜P4 + scripts/equity_idle_study.py）：
预计下跌 → 反向、熊 → 现金、牛 → 股票 ETF；牛熊没有值不猜；合成价只用开盘前已知的数；选择规则按登记写的门槛。"""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qbreak import idle_cash as IC                                           # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.unified import UnifiedEngine                                     # noqa: E402

from test_live_unified import CFG, EX, P, _frame                             # noqa: E402


def test_equity_modes_costs_and_overlay_cfg():
    assert {"Q1", "Q2", "Q3", "Q4", "Q5", "Q6"} <= set(IC.MODES) and IC.mode_of({"idle_cash": {"mode": "Q1"}}) == "Q1"
    assert IC.MODES["Q1"]["core_index"] == {"1545.T": "US"} and IC.MODES["Q4"]["core_index"] == {"1321.T": "JP"}
    assert IC.MODES["Q6"]["core_index"] == {"1678.T": "T0:IN"}
    c = IC.apply(CFG, "Q1", held={"133A.T": 7})
    assert c.core == {"1545.T": 1.0, "133A.T": 0.0} and c.core_mode == "split"             # 以前的 133A 下一次决策卖掉
    o = IC.overlay_cfg("Q4")
    assert o == {"core": {"1321.T": 1.0, "1571.T": 1.0}, "core_index": {"1321.T": "EQ", "1571.T": "IV"}, "core_mode": "follow"}
    assert IC.overlay_cfg("K0")["core"] == {"1655.T": 1.0, "2238.T": 1.0}
    with pytest.raises(KeyError):
        IC.overlay_cfg("Q6")                                                   # 东证没有印度反向
    assert etf_cost("tachibana", "1545.T", "JP")["lot"] == 10 and etf_cost("tachibana", "1678.T", "JP")["lot"] == 10
    assert etf_cost("tachibana", "1571.T", "JP")["slip_pct"] == 0.20 and etf_cost("tachibana", "2869.T", "JP")["lot"] == 1


def test_overlay_truth_table_and_unknown_bear():
    d = pd.bdate_range("2024-01-01", periods=6)
    bear = pd.Series([False, False, True, True, False, False], index=d)
    a0 = pd.Series([50, 85, 50, np.nan, 90, 10], index=d, dtype=float)
    cr = pd.Series([10, 10, 82, 10, 10, 10], index=d, dtype=float)
    exp = {"P1": [0, 0, 1, 1, 0, 0], "P2": [0, 1, 0, 0, 1, 0], "P3": [0, 0, 1, 0, 0, 0], "P4": [0, 0, 1, 0, 0, 0]}
    for v, e in exp.items():
        on = IC.overlay_on(v, bear, a0, cr)
        k = IC.overlay_keys(v, bear, a0, cr)
        assert on.astype(int).tolist() == e
        assert (k["IV"] == ~on).all() and (k["EQ"] == (bear | on)).all()             # 预计下跌 → 反向；熊 → 股票关
    early = pd.Series([95.0, 95.0], index=pd.DatetimeIndex(["2023-12-28", "2023-12-29"]))
    on = IC.overlay_on("P1", bear, early, None)
    assert not on.iloc[:2].any()                                                # 牛熊还没有值：不算预计下跌
    k = IC.overlay_keys("P2", bear, early, None)
    assert k["EQ"].iloc[:2].all() and not k["IV"].iloc[:2].any()                # …但 A0 ≥ 80 → 反向（股票关）
    with pytest.raises(KeyError):
        IC.overlay_on("P9", bear)


def _core(n, px):
    f = _frame([px] * n)
    f["entry"] = False
    return f


def test_engine_follow_switches_equity_inverse_cash():
    n = 40
    ind = {"A.T": _frame([1000.0] * n), "1545.T": _core(n, 240.0), "2842.T": _core(n, 12000.0)}
    idx = ind["1545.T"].index
    bear = pd.Series(False, index=idx)
    bear.iloc[10:20] = True                                                     # 第 10〜19 天收盘时熊
    keys = IC.overlay_keys("P1", bear)
    cc = {t: etf_cost("tachibana", t, "JP") for t in ("1545.T", "2842.T")}
    e = UnifiedEngine(ind, replace(CFG, **IC.overlay_cfg("Q1")), {"JP": P, "US": P}, EX, cc,
                      bear={"US": pd.Series(False, index=idx), **keys})
    e.run(idx[2])
    tr = [(d, t, s) for d, t, s, *_ in e.st.core_trades]
    assert tr[0] == (str(idx[3].date()), "1545.T", "BUY")
    assert (str(idx[11].date()), "1545.T", "SELL") in tr and (str(idx[11].date()), "2842.T", "BUY") in tr
    assert (str(idx[21].date()), "2842.T", "SELL") in tr and (str(idx[21].date()), "1545.T", "BUY") in tr
    assert e.st.core_units["2842.T"] == 0 and e.st.core_units["1545.T"] > 0 and e.st.core_units["1545.T"] % 10 == 0
    e2 = UnifiedEngine(ind, replace(CFG, **IC.overlay_cfg("Q1")), {"JP": P, "US": P}, EX, cc,
                       bear={"US": pd.Series(False, index=idx), **IC.overlay_keys("P4", bear)})
    e2.run(idx[2])
    t2 = [(d, t, s) for d, t, s, *_ in e2.st.core_trades]
    assert (str(idx[11].date()), "1545.T", "SELL") in t2 and all(t != "2842.T" for _, t, _ in t2)   # 熊但没有警示 → 现金


def test_study_builders_use_only_known_values():
    import equity_idle_study as S
    days = pd.DatetimeIndex(["2024-01-04", "2024-01-05", "2024-01-09"])
    us = pd.Series([10.0, 11.0, 12.0, 13.0], index=pd.DatetimeIndex(["2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]))
    assert S.on_jp(us, None, days).tolist() == [10.0, 11.0, 13.0]               # 东证 d 日 = 前一个美国收盘
    tr = pd.Series([100.0, 101.0, 99.99], index=pd.bdate_range("2024-01-01", periods=3))
    two = S.lev(tr, 2.0, None, None, 0.0)
    assert abs(two.iloc[1] - 1.02) < 1e-12 and abs(two.iloc[2] - 1.02 * 0.98) < 1e-9       # 每日重置
    inv = S.lev(pd.Series([100.0, 110.0], index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"])), -1.0, None, None, 0.0)
    assert abs(inv.iloc[-1] - 0.9) < 1e-12
    fin = pd.Series([3.6], index=pd.DatetimeIndex(["2023-12-01"]))
    t10 = pd.Series([100.0, 100.0], index=pd.DatetimeIndex(["2024-01-01", "2024-01-11"]))
    assert abs(S.lev(t10, 2.0, fin, None, 0.0).iloc[-1] - (1 - 2 * 0.036 * 10 / 360)) < 1e-12   # 融资按前一个观测日的利率
    assert abs(S.lev(t10, -1.0, fin, fin, 0.0, fin_basis=365).iloc[-1] - (1 + 2 * 0.036 * 10 / 365)) < 1e-12
    n = pd.DataFrame({"Open": [np.nan, 102.0, 99.0], "Close": [100.0, 104.0, 98.0]}, index=pd.bdate_range("2024-01-01", periods=3))
    f = S.jp_product(n, 2.0, None, None, 0.0, div_pct=0.0)
    assert abs(f["Close"].iloc[1] - 1.08) < 1e-12 and abs(f["Open"].iloc[1] - 1.04) < 1e-12              # 开盘 = 前收 × (1 + 2 × 跳空)
    assert abs(f["Open"].iloc[2] - 1.08 * (1 + 2 * (99.0 / 104.0 - 1))) < 1e-12 and f["Open"].iloc[0] == f["Close"].iloc[0]
    ch = S.chain(pd.Series([1.0, 2.0, 4.0], index=pd.bdate_range("2024-01-01", periods=3)),
                 pd.Series([40.0, 44.0], index=pd.bdate_range("2024-01-03", periods=2)))
    assert ch.tolist() == [10.0, 20.0, 40.0, 44.0]
    s = pd.Series([1.0, 2.0, 3.0], index=pd.DatetimeIndex(["2026-08-28", "2026-08-31", "2026-09-01"]))
    assert S.scale(s, "1545.T").loc["2026-08-31"] == S.REF_PX["1545.T"]
    fx = pd.Series([150.0], index=pd.DatetimeIndex(["2024-01-02"]))
    assert abs(S.jpy_per(fx, pd.Series([83.0], index=pd.DatetimeIndex(["2024-01-02"]))).iloc[0] - 150.0 / 83.0) < 1e-12


def _acct(vals: dict) -> dict:
    return {t: {k: {"cagr": v[0], "dd": v[1], "calmar": v[2]} for k, v in d.items()} for t, d in vals.items()}


def test_selection_rules():
    import equity_idle_study as S
    base = {"K0": (10.0, -30.0, 0.33), "S0": (10.5, -31.0, 0.34)}
    acct = _acct({t: {**base,
                      "Q1": (12.0, -31.5, 0.38),                               # 年化 +1.5（≥ 10.5 + 1）、回撤 −31.5 ≥ −32 ✓
                      "Q2": (15.0, -33.0, 0.45),                               # 回撤深 3 pp ✗
                      "Q3": (11.2, -20.0, 0.56),                               # 年化只高 0.7 ✗
                      "Q4": (12.3, -31.0, 0.397),                              # ✓，Calmar 与 Q5 相差 < 0.02
                      "Q5": (12.1, -30.0, 0.403),
                      "Q6": (11.6, -30.0, 0.39)} for t in ("E", "J")})       # 年化 +1.1 < 该候选的门槛 1.13 ✗
    win, q = S.pick_a(acct)
    assert q["Q2"] == (False, ["E 回撤", "J 回撤"]) and q["Q3"][1] == ["E 年化", "J 年化"] and q["Q6"][1] == ["E 年化", "J 年化"]
    assert win == "Q4"                                                          # Q5 0.403 最高，Q4 相差 < 0.02 且年化更高
    acct["J"]["Q4"]["cagr"] = 11.4                                              # J 只高 0.9 pp → 不入围
    assert S.pick_a(acct)[0] == "Q5"
    for t in ("E", "J"):
        acct[t].update({"Q1+P1": {"cagr": 12.5, "dd": -30.0, "calmar": 0.417}, "Q1+P2": {"cagr": 11.9, "dd": -20.0, "calmar": 0.6},
                        "Q1+P3": {"cagr": 12.1, "dd": -30.0, "calmar": 0.395}, "Q1+P4": {"cagr": 12.2, "dd": -30.5, "calmar": 0.40}})
    ad, res = S.pick_b(acct, "Q1")
    assert ad == "P1" and res["P2"]["why"] == ["E 年化", "J 年化"] and res["P3"]["why"] == ["E Calmar", "J Calmar"]
    assert res["P4"]["ok"] and res["P1"]["d_calmar"] == 0.037
    assert S.decision("Q1", "P1", None) == {"mode": "Q1", "overlay": "P1", "change": True}
    assert S.decision(None, None, "P3", True) == {"mode": "K0", "overlay": "P3", "change": True}
    assert S.decision(None, None, "P3", False)["change"] is False                # 只是不低于、没有高 1 pp → 不换
    assert S.decision(None, None, None)["change"] is False
    for t in ("E", "J"):
        acct[t]["S0+P1"] = {"cagr": 11.5, "dd": -30.0, "calmar": 0.38}
    assert S.fallback_ok(acct, "S0+P1")
    acct["E"]["S0+P1"]["cagr"] = 11.4
    assert not S.fallback_ok(acct, "S0+P1")
    for t in ("E", "J"):                                                        # 同分比较不四舍五入：0.0204 vs 0.0400 相差 0.0196 < 0.02
        acct[t].update({"Q1+P1": {"cagr": 12.5, "dd": -30.0, "calmar": 0.4004}, "Q1+P4": {"cagr": 12.5, "dd": -30.0, "calmar": 0.42}})
    assert S.pick_b(acct, "Q1")[0] == "P1"


def test_fx_cleaning_and_inverse_levels():
    import equity_idle_study as S
    d = pd.bdate_range("2008-04-01", periods=8)
    fx = pd.Series([102.0, 102.5, 102.3, 108.2, 102.6, 102.9, 106.4, 106.5], index=d)
    ref = pd.Series([102.1, 102.4, 102.2, 102.5, 102.7, 103.0, 106.3, 106.6], index=d)
    out, fixed = S.clean_fx(fx, ref)
    assert fixed == [str(d[3].date())] and out.iloc[3] == 102.5 and out.iloc[6] == 106.4   # 尖刺换成 FRED；真的跳动（不回来）不动
    idx = pd.bdate_range("2006-09-27", periods=6)
    f = pd.DataFrame({"Open": 100000.0, "High": 100000.0, "Low": 100000.0, "Close": [100000.0, 90000.0, 80000.0, 60000.0, 50000.0, 40000.0],
                      "Volume": 1e9, "entry": False}, index=idx)
    sp = {"cfg_over": IC.overlay_cfg("Q1"), "extra_core": {"1545.T": f.copy(), "2842.T": f.copy()}}
    sp2 = S.level_at(sp, "2006-10-01")                                           # 窗口第一天之前最后一天 = 09-29 的 80000
    assert sp2["extra_core"]["2842.T"]["Close"].loc["2006-09-29"] == S.REF_PX["2842.T"]
    assert sp2["extra_core"]["1545.T"] is sp["extra_core"]["1545.T"] and sp["extra_core"]["2842.T"]["Close"].iloc[0] == 100000.0
    b = S.spec_b("S0", "P1", {"1655.T": f, "2238.T": f}, {"US": pd.Series(False, index=idx)}, {})
    assert set(b["extra_core"]) == {"1655.T", "2238.T"} and b["cfg_over"]["core_index"] == {"1655.T": "EQ", "2238.T": "IV"}


def test_core_only_stats_share_and_switches():
    import equity_idle_study as S
    idx = pd.bdate_range("2020-01-01", periods=6)
    px = pd.Series([100.0, 110.0, 121.0, 60.5, 66.55, 73.205], index=idx)
    bear = pd.Series([False, False, True, True, False, False], index=idx)
    eq = S.core_only(px, bear, "2020-01-01")
    assert abs(eq.iloc[2] - (1 + 0.1 - 0.001) * 1.1) < 1e-12                  # 前一天的状态决定当天持仓；买进那天扣 0.1%
    assert abs(eq.iloc[3] / eq.iloc[2] - (1 - 0.001)) < 1e-12                    # 第 2 天收盘熊 → 第 3 天不拿（跌 50% 的那天），只扣卖出成本
    assert abs(eq.iloc[4] / eq.iloc[3] - 1.0) < 1e-12
    long = pd.Series(np.linspace(100, 300, 3000), index=pd.bdate_range("2000-01-03", periods=3000))
    st = S.curve_stats(long)
    assert st["dd"] == 0.0 and st["calmar"] is None and st["worst10"] > 0
    keys = IC.overlay_keys("P1", bear)
    sp = {"cfg_over": IC.overlay_cfg("Q1"), "extra_bear": keys}
    sh = S.held_share(sp, {"US": bear}, idx, "2020-01-01", None)
    assert sh == {"1545.T": 66.7, "2842.T": 33.3}
    assert S.held_share({}, {"US": bear}, idx, "2020-01-01", None) == {"1655.T": 66.7}
    assert S.switches_per_year(sp, idx, "2020-01-01", None) == round(2 / ((idx[-1] - idx[0]).days / 365.25), 1)
