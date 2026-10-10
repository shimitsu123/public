"""K 线（qbreak/kline.py；2026-10-06 用户「趋势是做一个和图中一样的日周月的块块和线」）：周K / 月K 的聚合（休市的周没有 K 线、
日期 = 那周 / 那月最后一个交易日）、MA 用全部历史、趋势标签、给页面的列式数据。"""
import numpy as np
import pandas as pd

from qbreak import kline as K


def _df(close, start="2026-01-05", idx=None, vol=1000.0):
    idx = idx if idx is not None else pd.bdate_range(start, periods=len(close))
    c = np.asarray(close, float)
    return pd.DataFrame({"Open": c * 0.99, "High": c * 1.02, "Low": c * 0.97, "Close": c, "Volume": vol}, index=idx)


def test_weekly_and_monthly_bars_follow_actual_trading_days():
    idx = pd.DatetimeIndex(["2026-04-27", "2026-04-28", "2026-04-30",           # 一周只有 3 天（4/29 昭和の日）
                            "2026-05-07", "2026-05-08",                         # 黄金周：5/1〜5/6 没有交易 → 这一周只有 2 天
                            "2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15"])
    c = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    df = _df(c, idx=idx)
    w = K.bars(df, "W")
    assert [str(x.date()) for x in w.index] == ["2026-04-30", "2026-05-08", "2026-05-15"]
    assert list(w["Close"]) == [102, 104, 109] and list(w["Volume"]) == [3000, 2000, 5000]
    assert w["Open"].iloc[1] == 103 * 0.99 and w["High"].iloc[1] == 104 * 1.02 and w["Low"].iloc[1] == 103 * 0.97
    m = K.bars(df, "M")
    assert [str(x.date()) for x in m.index] == ["2026-04-30", "2026-05-15"] and list(m["Volume"]) == [3000, 7000]
    assert K.bars(df, "D").equals(K.ohlcv(df))


def test_ohlcv_fills_gaps_and_drops_rows_without_close():
    df = _df([100, 101, 102])
    df.loc[df.index[1], ["Open", "High"]] = np.nan
    df.loc[df.index[2], "Close"] = np.nan
    o = K.ohlcv(df)
    assert len(o) == 2 and o["Open"].iloc[1] == 101 and o["High"].iloc[1] == 101 and o["Low"].iloc[1] <= 101


def test_series_moving_averages_use_full_history():
    df = _df(np.arange(1, 101, dtype=float))
    s = K.series(K.bars(df, "D"), 10)
    assert len(s["d"]) == 10 and s["c"][-1] == 100.0
    assert s["ma5"][-1] == 98.0 and s["ma30"][0] == round(np.mean(np.arange(62, 92)), 2)    # 窗口开头的 MA 也是满的
    for k in ("o", "h", "l", "v", "ma10", "ma20"):
        assert len(s[k]) == 10


def test_trend_labels():
    up = _df(np.linspace(100, 200, 80))
    down = _df(np.linspace(200, 100, 80))
    flat = _df(list(np.linspace(100, 200, 79)) + [180.0])          # 收盘跌破 MA20、MA20 还在往上 → 震荡
    tu, td, tf = K.trend(K.bars(up, "D")), K.trend(K.bars(down, "D")), K.trend(K.bars(flat, "D"))
    assert tu["label"] == "上升" and tu["align"] == "多头排列" and tu["above20"] and tu["slope20_pct"] > 0
    assert td["label"] == "下降" and td["align"] == "空头排列" and not td["above20"]
    assert tf["label"] == "震荡" and not tf["above20"] and tf["slope20_pct"] > 0
    assert K.trend(K.bars(_df(np.linspace(100, 120, 22)), "D")) is None          # 不到 MA20 + 3 根
    assert K.chips({"D": tu, "M": td}) == "日K 往上走 · 月K 往下走" and K.chips(None) == "—"
    assert K.plain("震荡") == "横着走" and K.plain("别的") == "别的" and K.plain(None) == "—"          # 页面上的说法；数据里的标签不变
    from qbreak import trendline as TLm
    assert set(K.PLAIN) == set(K.LABELS) and set(K.CHAN_PLAIN) == set(TLm.CHANNELS)      # 每种通道都有通俗说法


def test_payload_trims_to_decision_day_and_carries_info():
    df = _df(np.linspace(100, 300, 900), start="2023-01-02")
    day = str(df.index[-11].date())
    p = K.payload(df, day, {"kind": "stock", "entry_px": 250.0})
    assert p["kind"] == "stock" and p["entry_px"] == 250.0
    assert p["tf"]["D"]["d"][-1] == day and len(p["tf"]["D"]["d"]) == K.BARS["D"]
    assert p["tf"]["W"]["d"][-1] <= day and p["tf"]["M"]["d"][-1] <= day
    assert set(p["trend"]) == {"D", "W", "M"} and p["trend"]["M"]["label"] == "上升"
    assert K.trends(df, day) == p["trend"]
    assert K.payload(None) is None and K.payload(df.iloc[:1]) is None


def test_sub_charts_macd_is_the_rules_and_dmi_follows_ths():
    from qbreak.config import StrategyParams
    from qbreak.strategy import macd as rule_macd
    rng = np.random.default_rng(2)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, 300)))
    df = _df(c)
    b = K.bars(df, "D")
    s = K.series(b, 50)
    p = StrategyParams()
    dif, dea, mh = rule_macd(b["Close"], p.macd_fast, p.macd_slow, p.macd_signal)
    assert s["dif"][-1] == round(float(dif.iloc[-1]), 3) and s["dea"][-1] == round(float(dea.iloc[-1]), 3)
    assert s["mh"][-1] == round(float(mh.iloc[-1]), 3) and len(s["mh"]) == 50
    up = _df(np.arange(100, 160, dtype=float))                             # 每天都比前一天高：+DI 有值、−DI = 0 → ADX = 100
    d = K.dmi(K.bars(up, "D"))
    assert d["mdi"].iloc[-1] == 0 and d["pdi"].iloc[-1] > 0 and abs(d["adx"].iloc[-1] - 100) < 1e-9
    assert abs(d["adxr"].iloc[-1] - 100) < 1e-9 and np.isnan(d["adx"].iloc[K.DMI_N - 2])
    for k in ("pdi", "mdi", "adx", "adxr"):
        assert len(s[k]) == 50


def test_payload_carries_trendlines_and_indicator_params():
    rng = np.random.default_rng(4)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, 900)))
    p = K.payload(_df(c, start="2023-01-02"), None, {"kind": "suggest"})
    assert p["ind"] == {"macd": [12, 26, 9], "dmi": [K.DMI_N, K.DMI_M]}
    tl = p["tf"]["D"].get("tl")
    assert tl and tl["proj"] == 10 and ("sup" in tl or "res" in tl)
    for side in ("sup", "res"):
        if side in tl:
            assert tl[side]["i2"] < K.BARS["D"] and tl[side]["touch"] >= 2
