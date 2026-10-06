"""趋势线（qbreak/trendline.py；2026-10-06 用户「K线上面比如画一个直线 直线上面每次都可以到波谷的那个线 再画一个线每次都可以波峰」）：
波谷 / 波峰的确认、连线的选法、没有用到未来的 K 线、破线事件、通道的名字、给面板的摘要。"""
import numpy as np
import pandas as pd

from qbreak import trendline as TL


def _df(c, spread=1.0, start="2024-01-01"):
    c = np.asarray(c, float)
    return pd.DataFrame({"Open": c, "High": c + spread, "Low": c - spread, "Close": c}, index=pd.bdate_range(start, periods=len(c)))


def _channel(n=200, slope=0.5, amp=10.0, period=20):
    x = np.arange(n)
    return 100 + slope * x + amp * np.sin(2 * np.pi * (x % period) / period)


def test_pivots_need_k_bars_on_both_sides():
    x = np.array([5, 4, 3, 2, 3, 4, 5, 4, 3, 4, 5], float)
    lows = TL.pivots(x, 2, "low")
    assert list(np.flatnonzero(lows)) == [3, 8]
    highs = TL.pivots(x, 2, "high")
    assert list(np.flatnonzero(highs)) == [6]
    assert not TL.pivots(x[:4], 2, "low").any()                          # 不满 2k + 1 根
    flat = np.array([3, 2, 1, 1, 2, 3], float)                             # 一样低的两根：只算第一根
    assert list(np.flatnonzero(TL.pivots(flat, 2, "low"))) == [2]


def test_rising_channel_lines_pass_through_troughs_and_peaks():
    df = _df(_channel())
    s = TL.scan(df, "D")
    t = 150
    lows = df["Low"].to_numpy()
    assert s["sup_touch"][t] >= 5 and s["res_touch"][t] >= 5
    a1, a2 = s["sup_a1"][t], s["sup_a2"][t]
    assert TL.pivots(lows, 5, "low")[[a1, a2]].all()                      # 两个锚点都是波谷
    want = lows[a1] + (lows[a2] - lows[a1]) / (a2 - a1) * (t - a1)
    assert abs(s["sup"][t] - want) < 1e-9 and abs(s["sup_b"][t] - 0.5) < 1e-9
    assert abs(s["res_b"][t] - 0.5) < 1e-9 and s["res"][t] > s["sup"][t]
    assert TL.channel(s["sup_slope"][t], s["res_slope"][t], "D") == "上升通道"


def test_no_lookahead_truncated_scan_matches():
    rng = np.random.default_rng(5)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0002, 0.018, 700)))
    df = _df(c, spread=0.0).assign(High=c * (1 + rng.random(700) * 0.01), Low=c * (1 - rng.random(700) * 0.01))
    full = TL.scan(df, "D")
    for cut in (120, 333, 517, 699):
        part = TL.scan(df.iloc[:cut], "D")
        for k, v in part.items():
            a = np.nan_to_num(np.asarray(full[k][:cut], float), nan=-1e9)
            b = np.nan_to_num(np.asarray(v, float), nan=-1e9)
            assert np.allclose(a, b, rtol=0, atol=1e-9), (cut, k)


def test_break_below_support_is_an_event_against_yesterdays_line():
    c = _channel()
    c[181:] -= 40                                                          # 第 181 根收盘直接掉到支撑线下面
    df = _df(c)
    s = TL.scan(df, "D")
    assert not s["sup_break"][:181].any()
    assert s["sup_break"][181]
    line = s["sup_prev"][181]                                              # 前一天那条线在今天的值
    assert c[181] < line - s["tol"][181]
    assert TL.first_events(np.array([0, 1, 1, 0, 1, 0, 0, 0, 1], bool), 3).tolist() == [0, 1, 0, 0, 0, 0, 0, 0, 1]


def test_channel_names():
    e = TL.EPS["D"]
    cases = {(1, 1): "上升通道", (-1, -1): "下降通道", (0, 0): "横盘通道", (1, -1): "对称三角", (1, 0): "上升三角",
             (0, -1): "下降三角", (-1, 1): "扩散", (0, 1): "扩散", (-1, 0): "扩散"}
    for (a, b), name in cases.items():
        assert TL.channel(a * 3 * e, b * 3 * e, "D") == name
    assert TL.channel(None, 0.1) is None and TL.channel(float("nan"), 0.1) is None
    assert set(cases.values()) == set(TL.CHANNELS)


def test_summary_gives_window_positions_projection_and_events():
    c = _channel(400)
    c[390:] += 30                                                          # 最后几根收盘突破压力线
    df = _df(c)
    sm = TL.summary(df, "D", 250)
    off = 400 - 250
    s = TL.scan(df, "D")
    sup = sm["sup"]
    assert sup["i1"] == s["sup_a1"][-1] - off and sup["i2"] == s["sup_a2"][-1] - off
    assert abs(sup["now"] - s["sup"][-1]) < 0.01 and abs(sup["proj"] - (s["sup"][-1] + s["sup_b"][-1] * TL.PROJ["D"])) < 0.01
    assert sm["proj"] == TL.PROJ["D"] and all(0 <= i < 250 for i, _ in sm["ev"])
    assert [390 - off, "rb"] in sm["ev"]
    assert TL.summary(df.iloc[:5], "D", 250) is None
