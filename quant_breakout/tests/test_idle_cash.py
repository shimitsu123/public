"""闲置资金的方式（qbreak/idle_cash.py + 引擎的额外开关键）：月末才判定、第二天开盘执行；10 个月线 / 12 个月动量；
换方式时还拿着的旧 ETF 下一次决策全部卖掉；开关键没给 → 按熊（留现金）；研究脚本的合成价只用开盘前已知的数。"""
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qbreak import idle_cash as IC                                           # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.unified import UnifiedEngine, UState                             # noqa: E402

from test_live_unified import CFG, EX, P, _frame                             # noqa: E402


def _daily(values_per_month, start="2024-01-01"):
    """每个月一个水平（月内不变）→ 工作日序列；最后一个月少 3 天（没走完）。"""
    months = pd.period_range(start, periods=len(values_per_month), freq="M")
    idx = pd.bdate_range(months[0].start_time, months[-1].end_time)[:-3]
    lvl = dict(zip(months, values_per_month))
    return pd.Series([float(lvl[m]) for m in idx.to_period("M")], index=idx)


def test_modes_mode_of_and_apply():
    assert set(IC.MODES) == {"K0", "K1", "K2", "K3", "K4", "K5", "K6"} and IC.mode_of({}) == "K0"
    assert IC.mode_of({"idle_cash": {"mode": "K2"}}) == "K2" and IC.mode_of({"idle_cash": {"mode": "zz"}}) == "K0"
    c = IC.apply(CFG, "K2", held={"1655.T": 30, "1540.T": 0})
    assert c.core == {"1540.T": 1.0, "1655.T": 0.0} and c.core_index["1540.T"] == "TR:1540.T" and c.core_mode == "split"
    assert IC.apply(CFG, "K1").core == {} and IC.apply(CFG, "K6").core_mode == "follow"
    assert IC.apply(CFG, "K0").core == {"1655.T": 1.0}
    with pytest.raises(KeyError):
        IC.apply(CFG, "K9")


def test_trend_off_decides_only_at_month_end():
    s = _daily([100 + k for k in range(14)])                                    # 每月涨 1
    off = IC.trend_off(s)
    me = IC.month_ends(s.index)
    assert len(me) == 13                                                        # 最后一个月没走完 → 不算
    assert off[s.index <= me[8]].all()                                          # 月末不到 10 个 → 现金
    assert not off[(s.index > me[9]) & (s.index <= me[12])].any()               # 第 10 个月末起：收盘 > 10 个月平均 → 拿
    assert bool(off.loc[me[9]]) is False and bool(off.loc[s.index[s.index < me[9]][-1]]) is True   # 月末那天收盘时切换
    down = _daily([100 + k for k in range(13)] + [80])
    od = IC.trend_off(down, last_complete=True)
    assert bool(od.iloc[-1]) is True and not IC.trend_off(down).iloc[-1]       # 实时：只有「今天是本月最后一个交易日」才用这个月


def test_rotation_pick_and_off():
    a = _daily([100 * 1.02 ** k for k in range(15)])
    b = _daily([100 * 1.01 ** k for k in range(15)])
    c = _daily([100 * 0.99 ** k for k in range(15)])
    short = _daily([50 * 1.2 ** k for k in range(15)]).iloc[-150:]            # 历史不到 12 个月 → 不参加
    p = IC.rotation_pick({"A": a, "B": b, "C": c, "S": short})
    assert p.iloc[:12].isna().all() and (p.iloc[12:] == "A").all()
    assert IC.rotation_pick({"C": c}).iloc[12:].isna().all()                  # 都跌 → 现金
    off = IC.rotation_off({"A": a, "B": b}, a.index)
    me = IC.month_ends(a.index)
    assert set(off) == {"RT:A", "RT:B"} and not off["RT:A"].loc[me[12]] and off["RT:B"].loc[me[12]]


def test_extra_bear_keys_per_mode():
    s = _daily([100 + k for k in range(14)])
    closes = {t: s for t in IC.ROT}
    ub = pd.Series(False, index=s.index)
    ub.iloc[100:] = True
    assert set(IC.extra_bear("K2", closes, ub, s.index)) == {"TR:1540.T"} and IC.extra_bear("K1", closes, ub, s.index) == {}
    xr = IC.extra_bear("K5", closes, ub, s.index)["XR"]
    assert (xr == ~ub).all()                                                    # 美股熊 → 拿反向；牛 → 现金
    assert set(IC.extra_bear("K6", closes, ub, s.index)) == {f"RT:{t}" for t in IC.ROT}
    st = IC.status("K2", IC.extra_bear("K2", closes, ub, s.index), s.index[-1])
    assert st["hold"] == ["1540.T"] and "黄金" in st["text"] and IC.status("K1", {}, s.index[-1])["text"] == "现金"


def _core(n, px):
    f = _frame([px] * n)
    f["entry"] = False
    return f


def test_engine_idle_cash_switch_and_legacy_sell():
    n = 40
    ind = {"A.T": _frame([1000.0] * n), "1655.T": _core(n, 700.0), "1540.T": _core(n, 2000.0)}
    idx = ind["1655.T"].index
    flag = pd.Series(True, index=idx)
    flag.iloc[10:20] = False                                                   # 第 10〜19 天收盘时「拿」
    cc = {t: etf_cost("tachibana", t, "JP") for t in ("1655.T", "1540.T")}
    cfg = IC.apply(CFG, "K2")
    e = UnifiedEngine(ind, cfg, {"JP": P, "US": P}, EX, {"1540.T": cc["1540.T"]},
                      bear={"US": pd.Series(False, index=idx), "TR:1540.T": flag})
    e.run(idx[2])
    tr = [(d, t, s) for d, t, s, *_ in e.st.core_trades]
    assert tr[0] == (str(idx[11].date()), "1540.T", "BUY") and tr[-1] == (str(idx[21].date()), "1540.T", "SELL")
    assert e.st.core_units["1540.T"] == 0
    st = UState(cash_jpy=300_000.0, core_units={"1655.T": 1000})                # 以前的方式留下的 1655
    cfg2 = IC.apply(CFG, "K2", held=st.core_units)
    e2 = UnifiedEngine(ind, cfg2, {"JP": P, "US": P}, EX, cc, bear={"US": pd.Series(False, index=idx), "TR:1540.T": flag}, state=st)
    e2.run(idx[2])
    t2 = [(d, t, s, u) for d, t, s, u, *_ in e2.st.core_trades]
    assert t2[0] == (str(idx[3].date()), "1655.T", "SELL", 1000) and e2.st.core_units["1655.T"] == 0
    e3 = UnifiedEngine(ind, replace(cfg, core_index={"1540.T": "TR:没给"}), {"JP": P, "US": P}, EX, {"1540.T": cc["1540.T"]},
                       bear={"US": pd.Series(False, index=idx)})
    e3.run(idx[2])
    assert e3.st.core_trades == []                                             # 开关键没给 → 按熊，留现金


def test_study_synthetic_prices_use_only_known_values():
    import idle_cash_study as S
    days = pd.DatetimeIndex(["2024-01-04", "2024-01-05", "2024-01-09"])
    us = pd.Series([10.0, 11.0, 12.0, 13.0], index=pd.DatetimeIndex(["2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]))
    fx = pd.Series([140.0, 141.0, 142.0, 143.0], index=us.index)
    v = S.jp_series(us, fx, days)
    assert v.tolist() == [10.0 * 140.0, 11.0 * 141.0, 13.0 * 143.0]            # 东证 d 日 = 前一个美国收盘 × 前一个汇率
    acc = S.accrual(pd.Series([3.6, 3.6], index=pd.DatetimeIndex(["2024-01-01", "2024-01-11"])))
    assert abs(acc.iloc[-1] - (1 + 0.036 * 10 / 360)) < 1e-12
    inv = S.inverse_index(pd.Series([100.0, 110.0], index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"])),
                          pd.Series([0.0], index=pd.DatetimeIndex(["2024-01-01"])), 0.0, start=1000.0)
    assert abs(inv.iloc[-1] - 900.0) < 1e-9                                     # 涨 10% → 反向 −10%
    acct = {t: {"K1": {"calmar": 0.30, "dd": -10.0}, "K2": {"calmar": 0.31, "dd": -20.0}, "K3": {"calmar": 0.10, "dd": -5.0},
                "K4": {"calmar": None, "dd": None}, "K5": {"calmar": 0.0, "dd": -1.0}, "K6": {"calmar": 0.2, "dd": -9.0}}
            for t in ("E", "J")}
    ch, sc = S.pick(acct)
    assert ch == "K1" and "K4" not in sc                                        # 0.31 vs 0.30 相差 < 0.02 → 回撤浅的
    acct["E"]["K0"] = {"calmar": 0.28}
    acct["J"]["K0"] = {"calmar": 0.35}
    assert S.reading(acct, "K2") == "差不多"


def test_live_helpers_and_displays():
    from qbreak.live_unified import daily_text, ic_text
    assert IC.last_month_complete("2026-09-30") is True and IC.last_month_complete("2026-09-29") is False
    s = _daily([100 + k for k in range(13)] + [80])
    det = IC.detail("K3", {"133A.T": s}, s.index[-1])
    assert det["month_end"] == str(IC.month_ends(s.index)[-1].date()) and det["close"] == 112.0 and det["sma"] == 107.5
    ic = {"mode": "K3", "label": IC.LABELS["K3"], "text": "美元短期国债（133A）", **det}
    assert "112.00 > 10 个月均线 ¥107.50" in ic_text(ic)
    assert "12 个月" in ic_text({"text": "现金", "ret12": {"1540.T": 40.2}})
    _, _, body = daily_text({"decided_on": "2026-09-30", "orders": [], "idle_cash": ic}, UState(cash_jpy=1e6), None, True, 1e6)
    assert "- 闲置资金：美元趋势" in body and "现在：美元短期国债（133A）" in body
    _, _, body0 = daily_text({"decided_on": "2026-09-30", "orders": [], "idle_cash": {"mode": "K0"}}, UState(cash_jpy=1e6), None, True, 1e6)
    assert "闲置资金" not in body0
    from qbreak import dashboard as DB
    parts = {k for k, _, _ in DB.exposure({"equity_jpy": 1e6, "cash_jpy": 1e5, "core_units": {"133A.T": 100}, "core_last": {"133A.T": 1000.0}})}
    assert "核心 ETF（133A）" in parts
