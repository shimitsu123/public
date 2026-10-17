"""周 / 月线严重脱离之后怎么走（scripts/madev_event.py）：事件（两根 / 下一个交易日、同一段只算第一次）、前向收益的下标、成员等权、
过滤状态不偷看、自助法、三种判定、登记的常数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import madev_event as ME                                                    # noqa: E402


def _daily(closes: np.ndarray, start="2020-01-06"):
    days = pd.bdate_range(start, periods=len(closes))
    c = np.asarray(closes, float)
    return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": np.full(len(c), 1e6)}, index=days), days


def _weeks(vals):
    return np.repeat(np.asarray(vals, float), 5)


def test_two_bar_event_only_first_in_episode():
    raw, days = _daily(_weeks([100.0] * 20 + [130.0, 130.0, 130.0] + [100.0] * 5))
    ed = ME.event_days(raw, days, ME.EVENTS["U1"])                          # 13 周线、两根、+15%
    assert list(ed) == [days[21 * 5 + 4]]                                   # 第 22 周的周五（第 23 周仍成立，但同一段不再算）
    assert len(ME.event_days(raw, days, ME.EVENTS["U2"])) == 0              # 第二根 +24% < 25%


def test_next_day_rule_down():
    c = _weeks([100.0] * 21)
    c[20 * 5 + 4] = 80.0                                                    # 第 21 周周五收 80：13 周线 98.46 → −18.8%（刚脱离）
    c = np.r_[c, [82.0, 100.0, 100.0, 100.0, 100.0]]                        # 下一个交易日（周一）收 82：相对那条线 −16.7%
    raw, days = _daily(c)
    ed = ME.event_days(raw, days, ME.EVENTS["N4"])
    assert list(ed) == [days[21 * 5]]
    c2 = c.copy()
    c2[21 * 5] = 90.0                                                       # 周一回到 90（−8.6%）→ 这一段没有事件
    raw2, days2 = _daily(c2)
    assert len(ME.event_days(raw2, days2, ME.EVENTS["N4"])) == 0


def test_next_day_rule_needs_fresh_departure():
    c = _weeks([100.0] * 20 + [80.0, 80.0, 80.0])                           # 第 21、22 周都在 −15% 以下：只有第 21 周是「刚脱离」
    c = np.r_[c, [80.0] * 5]
    raw, days = _daily(c)
    ed = ME.event_days(raw, days, ME.EVENTS["N4"])
    assert list(ed) == [days[21 * 5]]                                       # 第 21 周完成后的下一个交易日（第 22 周周一）


def test_fwd_returns_and_market_mean():
    op = np.array([[10.0, 20.0], [11.0, 21.0], [12.0, 22.0], [13.0, 23.0]])
    cl = op + 0.5
    R = ME.fwd_returns({"O": op, "C": cl}, horizons=(2,))[2]
    assert np.isclose(R[0, 0], cl[2, 0] / op[1, 0] - 1) and np.isclose(R[1, 1], cl[3, 1] / op[2, 1] - 1)
    assert np.isnan(R[2:]).all()                                            # 后面不够 2 天 → 不算
    mem = np.array([[True, False], [True, True], [True, True], [True, True]])
    m = ME.market_mean(R, mem)
    assert np.isclose(m[0], R[0, 0]) and np.isclose(m[1], R[1].mean()) and np.isnan(m[3])


def test_filter_state_from_completion_day_only():
    raw, days = _daily(_weeks([100.0] * 20 + [130.0] + [100.0] * 3))
    st = ME.filter_state(raw, days, ME.FILTERS["F1"], raw.index)
    fri21 = 20 * 5 + 4
    assert not st[:fri21].any() and st[fri21] and st[fri21 + 1:fri21 + 5].all()     # 那个周五收盘起到下一根完成前
    assert not st[fri21 + 5]                                                        # 下一周（回到 100）完成 → 不再成立
    assert not ME.filter_state(raw, days, ME.FILTERS["F2"], raw.index).any()        # 只有一根 → 两根的不成立


def test_boot_mean():
    x = np.array([1.0, 2.0, -1.0, 3.0, 0.5, 2.5])
    months = np.array(["a", "a", "b", "c", "c", "d"])
    lo, hi = ME.boot_mean(x, months, n=500)
    assert (lo, hi) == ME.boot_mean(x, months, n=500) and lo <= x.mean() <= hi


def _ev(n, x, lo, hi):
    return {"n": n, "x_mean": x, "lo": lo, "hi": hi}


def test_verdict_event():
    per_down = {t: {"n": 50, "x_mean": -0.5} for t in ME.SAMPLES}
    assert ME.verdict_event(_ev(500, -0.6, -1.0, -0.2), per_down, side=1) == "成立"          # 上涨 → 预期跑输
    assert ME.verdict_event(_ev(500, 0.6, 0.2, 1.0), per_down, side=1) == "相反"
    assert ME.verdict_event(_ev(500, -0.1, -0.5, 0.3), per_down, side=1) == "方向一致但不显著"
    mixed = {**per_down, "J": {"n": 50, "x_mean": 0.3}}
    assert ME.verdict_event(_ev(500, -0.6, -1.0, -0.2), mixed, side=1) == "不成立（有一段相反）"
    assert ME.verdict_event(_ev(500, -0.1, -0.5, 0.3), {**mixed, "J": {"n": 5, "x_mean": 0.3}}, side=1) == "方向一致但不显著"  # < 20 个不看
    assert ME.verdict_event(_ev(29, -0.6, -1.0, -0.2), per_down, side=1) == "事件太少"
    per_up = {t: {"n": 50, "x_mean": 0.5} for t in ME.SAMPLES}
    assert ME.verdict_event(_ev(500, 0.6, 0.2, 1.0), per_up, side=-1) == "成立"             # 下跌 → 预期跑赢


def _port(dcal=0.0, ddd=0.0):
    return {t: {"cur": {"calmar": 0.3, "dd": -30.0}, "var": {"calmar": 0.3 + dcal, "dd": -30.0 + ddd}} for t in ME.PORT}


def test_verdict_filter_and_dip():
    per = {t: {"removed": 15, "dmean": 0.2, "dwin": 1.0} for t in ME.SAMPLES}
    pool = {"removed": 100, "keep_frac": 0.8, "dmean": 0.3, "dwin": 2.0, "dmean_lo": 0.05}
    assert ME.verdict_filter(pool, per, _port()) == "提高胜率与收益率"
    assert ME.verdict_filter({**pool, "removed": 19}, per, _port()) == "几乎不触发"
    assert ME.verdict_filter({**pool, "keep_frac": 0.4}, per, _port()) == "方向一致但不够"
    assert ME.verdict_filter(pool, per, _port(dcal=-0.02)) == "方向一致但不够"
    assert ME.verdict_filter(pool, {**per, "E": {"removed": 15, "dmean": -0.1, "dwin": 1.0}}, _port()) == "不成立"
    dper = {t: {"n": 40, "mean": 0.5} for t in ME.SAMPLES}
    assert ME.verdict_dip({"n": 300, "mean": 0.5, "lo": 0.1}, dper, _port()) == "搭配成立"
    assert ME.verdict_dip({"n": 300, "mean": 0.5, "lo": 0.1}, dper, _port(dcal=-0.001)).startswith("不成立")    # 组合要不低于现行
    assert ME.verdict_dip({"n": 300, "mean": 0.5, "lo": -0.1}, dper, _port()).startswith("不成立")
    assert ME.verdict_dip({"n": 20, "mean": 0.5, "lo": 0.1}, dper, _port()) == "事件太少"


def test_registered_constants():
    got = {k: (v["side"], v["freq"], v["n"], v["theta"], v["mode"]) for k, v in ME.EVENTS.items()}
    assert got == {"U1": (1, "W", 13, 15.0, "2bar"), "U2": (1, "W", 13, 25.0, "2bar"), "U3": (1, "M", 12, 35.0, "2bar"),
                   "U4": (1, "W", 13, 15.0, "next"), "U5": (1, "M", 12, 35.0, "next"),
                   "N1": (-1, "W", 13, 15.0, "2bar"), "N2": (-1, "W", 13, 25.0, "2bar"), "N3": (-1, "M", 12, 25.0, "2bar"),
                   "N4": (-1, "W", 13, 15.0, "next"), "N5": (-1, "M", 12, 25.0, "next"), "N6": (-1, "W", 13, 25.0, "next")}
    assert {k: (v["freq"], v["n"], v["theta"], v["k"]) for k, v in ME.FILTERS.items()} == {
        "F1": ("W", 13, 15.0, 1), "F2": ("W", 13, 15.0, 2), "F3": ("M", 12, 35.0, 1)}
    assert ME.DIPS == {"D1": "N4", "D2": "N1", "D3": "N5"} and ME.PRIMARY == {"W": 20, "M": 60}
