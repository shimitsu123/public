"""持仓的 K 线盘中画出「今天这一根」（2026-10-07 用户：「现在持有的ETF/股票等等当天日线在交易时间在K线中要随时价钱反映」）：
① qbreak/data.intraday_quotes：1 分钟线 → 现价 + 那一天到那个时刻为止的一根（只用最后一根所在的交易日）；
② kline.with_live：并进日K / 周K / 月K（同一周 / 月并进最后一根，否则新开一根），最后一根的均线 / MACD / DMI 与「全部历史重算」一致；
   图里已经有这一天 → 不动；不改原来的数据；趋势线的现在位置跟着更新；
③ /api/chart：只给持有的票并进去（建议的股票不并）、不在这里取价；现价接口带上这一根。"""
import datetime as dt
import json
import sys
import types

import numpy as np
import pandas as pd
import pytest

from qbreak import kline as KL
from qbreak import panel, paths
from qbreak.calendar_jp import JST

from test_manual_core import AT, _pbook


@pytest.fixture(autouse=True)
def _clean_quotes():
    panel._QUOTE_CACHE.clear()                                             # 现价缓存是进程里共用的：别带到别的测试
    yield
    panel._QUOTE_CACHE.clear()


def _daily(n=700, end="2026-10-06", seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=end, periods=n)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
    return pd.DataFrame({"Open": c * 0.999, "High": c * 1.01, "Low": c * 0.99, "Close": c,
                         "Volume": rng.integers(500_000, 1_500_000, n).astype(float)}, index=idx)


def _close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= max(1e-6, abs(b) * 2e-4) + 0.0011


@pytest.mark.parametrize("end,day", [("2026-10-06", "2026-10-07"),     # 火 → 水：同一周、同一个月（并进最后一根）
                                     ("2026-10-09", "2026-10-12"),     # 金 → 月：新的一周
                                     ("2026-09-30", "2026-10-01")])    # 月末 → 月初：新的一个月、同一周
def test_with_live_matches_a_full_recompute(end, day):
    df = _daily(end=end)
    pl = KL.payload(df, end, {"kind": "stock"})
    snap = json.dumps(pl, sort_keys=True)
    c0 = float(df["Close"].iloc[-1])
    bar = {"d": day, "o": c0 * 1.001, "h": c0 * 1.02, "l": c0 * 0.995, "c": c0 * 1.015, "v": 600_000}
    lv = KL.with_live(pl, bar, f"{day}T10:41+09:00")
    assert json.dumps(pl, sort_keys=True) == snap                           # 不改原来的
    ref = KL.payload(pd.concat([df, pd.DataFrame([[bar[k] for k in "ohlcv"]], columns=df.columns, index=pd.DatetimeIndex([day]))]),
                     day, {"kind": "stock"})
    assert lv["live"] == {"d": day, "at": f"{day}T10:41+09:00", "tf": ["D", "W", "M"]}
    for tf in ("D", "W", "M"):
        a, b = lv["tf"][tf], ref["tf"][tf]
        assert a["d"][-1] == day and a["d"][-2] == b["d"][-2]
        for k in KL.LIST_KEYS[1:]:
            assert _close(a[k][-1], b[k][-1]), (tf, k, a[k][-1], b[k][-1])
        assert a["c"][:-1] == pl["tf"][tf]["c"][:len(a["c"]) - 1]          # 之前的 K 线不动
    d0 = pl["tf"]["D"]
    assert len(lv["tf"]["D"]["d"]) == len(d0["d"]) + 1                       # 日K：加一根
    w_same = pd.Timestamp(day).to_period("W-FRI") == pd.Timestamp(end).to_period("W-FRI")
    assert len(lv["tf"]["W"]["d"]) == len(pl["tf"]["W"]["d"]) + (0 if w_same else 1)
    if w_same:                                                              # 同一周：开盘不变、高低取大小、量相加
        w0, w1 = pl["tf"]["W"], lv["tf"]["W"]
        assert w1["o"][-1] == w0["o"][-1] and w1["h"][-1] == round(max(w0["h"][-1], bar["h"]), 2)
        assert w1["v"][-1] == w0["v"][-1] + bar["v"] and w1["c"][-1] == round(bar["c"], 2)


def test_with_live_leaves_charts_that_already_have_the_day():
    df = _daily()
    pl = KL.payload(df, "2026-10-06", {"kind": "core"})
    c0 = float(df["Close"].iloc[-1])
    same = {"d": "2026-10-06", "o": c0, "h": c0, "l": c0, "c": c0 * 1.1, "v": 1}
    assert KL.with_live(pl, same) is pl                                    # 正式日线已经有这一天：不动
    assert KL.with_live(pl, {"d": "2026-10-05", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}) is pl
    assert KL.with_live(pl, None) is pl and KL.with_live(None, same) is None
    assert KL.with_live(pl, {"d": "2026-10-07", "o": 1, "h": 1, "l": 1, "c": 0, "v": 1}) is pl     # 价格不对
    assert KL.with_live(pl, {"d": "2026-10-07", "c": 1}) is pl                                    # 缺开高低
    bar = {"d": "2026-10-07", "o": c0, "h": c0, "l": c0, "c": c0, "v": 1}
    broken = {**pl, "tf": {**pl["tf"], "W": {"d": pl["tf"]["W"]["d"], "c": pl["tf"]["W"]["c"]},     # 周K 缺开高低量
                           "M": {**pl["tf"]["M"], "o": pl["tf"]["M"]["o"][:-1]}}}                  # 月K 长度对不上
    lv = KL.with_live(broken, bar)
    assert lv["live"]["tf"] == ["D"] and lv["tf"]["W"] is broken["tf"]["W"] and lv["tf"]["M"] is broken["tf"]["M"]
    assert KL.with_live({"tf": {"D": {"d": ["2026-10-05", "2026-10-06"]}}}, bar) == {"tf": {"D": {"d": ["2026-10-05", "2026-10-06"]}}}


def test_with_live_moves_the_trendline_reading_to_the_new_bar():
    df = _daily()
    pl = KL.payload(df, "2026-10-06", {"kind": "stock"})
    tl = pl["tf"]["D"].get("tl") or {}
    side = "sup" if tl.get("sup") else "res" if tl.get("res") else None
    if side is None:
        pytest.skip("这组数据没有趋势线")
    L = tl[side]
    c0 = float(df["Close"].iloc[-1])
    lv = KL.with_live(pl, {"d": "2026-10-07", "o": c0, "h": c0 * 1.01, "l": c0 * 0.99, "c": c0 * 1.005, "v": 1000})
    L2 = lv["tf"]["D"]["tl"][side]
    n1 = len(lv["tf"]["D"]["d"]) - 1
    assert L2["now"] == round(L["y1"] + L["b"] * (n1 - L["i1"]), 2)
    assert L2["dist_pct"] == round((L2["now"] / (c0 * 1.005) - 1) * 100, 2)
    assert pl["tf"]["D"]["tl"][side] == L                                  # 原来的不动


def test_intraday_quotes_aggregates_only_the_last_session(monkeypatch):
    """yfinance 换成假的：两天的 1 分钟线（UTC），今天这一根只合计最后一根所在的那一天（JST）。"""
    from qbreak import data as D
    idx = pd.DatetimeIndex(["2026-10-06 05:59", "2026-10-06 06:24",                       # 10/06 14:59 / 15:24 JST
                            "2026-10-07 00:00", "2026-10-07 00:01", "2026-10-07 00:41"], tz="UTC")   # 10/07 09:00 / 09:01 / 09:41 JST
    cols = pd.MultiIndex.from_product([["7203.T"], ["Open", "High", "Low", "Close", "Volume"]])
    raw = pd.DataFrame([[2600, 2610, 2590, 2605, 1000], [2605, 2620, 2600, 2615, 2000],
                        [2630, 2640, 2625, 2635, 50_000], [2635, 2660, 2630, 2655, 30_000], [2650, 2652, 2645, np.nan, 0]],
                       index=idx, columns=cols, dtype=float)
    fake = types.SimpleNamespace(download=lambda *a, **k: raw)
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    q = D.intraday_quotes(["7203.T"])["7203.T"]
    assert q["px"] == 2655.0 and q["at"] == "2026-10-07T09:01+09:00"      # 最后一个有收盘的 = 09:01
    assert q["bar"] == {"d": "2026-10-07", "o": 2630.0, "h": 2660.0, "l": 2625.0, "c": 2655.0, "v": 80_000}


def _charts(tickers: dict) -> None:
    (paths.out_dir() / "charts_paper.json").write_text(json.dumps({"asof": "2026-10-05", "tickers": tickers}, default=str),
                                                       encoding="utf-8")


def test_chart_endpoint_merges_the_cached_bar_only_for_held_tickers(monkeypatch):
    panel._QUOTE_CACHE.clear()
    _pbook()                                                               # 拿着 7203.T（100 股）与 1655.T（1,130 口）
    df = _daily(end="2026-10-05")
    pl = KL.payload(df, "2026-10-05", {"kind": "stock"})
    _charts({"7203.T": pl, "1655.T": {**pl, "kind": "core"}, "6501.T": {**pl, "kind": "suggest"}})
    code, js = panel.chart_json("paper", "7203.T")
    assert code == 200 and "live" not in js["data"]                        # 还没取过现价：原样
    c0 = float(df["Close"].iloc[-1])
    bar = {"d": "2026-10-06", "o": c0, "h": c0 * 1.02, "l": c0 * 0.99, "c": c0 * 1.01, "v": 12_345}
    calls = []

    def fetch(ts):
        calls.append(ts)
        return {t: {"px": bar["c"], "at": "2026-10-06T09:40+09:00", "bar": bar} for t in ts}
    code, q = panel.quotes_json("paper", now=AT, fetch=fetch)
    assert q["rows"]["7203.T"]["bar"] == {"d": "2026-10-06", **{k: round(bar[k], 2) for k in "ohlc"}, "v": 12_345}
    monkeypatch.setattr(panel, "quotes_json", lambda *a, **k: pytest.fail("K 线接口不该去取价"))
    for t in ("7203.T", "1655.T"):
        d = panel.chart_json("paper", t)[1]["data"]
        assert d["live"]["d"] == "2026-10-06" and d["live"]["at"] == "2026-10-06T09:40+09:00"
        assert d["tf"]["D"]["d"][-1] == "2026-10-06" and d["tf"]["D"]["c"][-1] == round(bar["c"], 2)
    d = panel.chart_json("paper", "6501.T")[1]["data"]
    assert "live" not in d and d["tf"]["D"]["d"][-1] == "2026-10-05"       # 建议的股票（没拿着）：不并
    assert len(calls) == 1
    for now, op in ((AT, True), (dt.datetime(2026, 10, 6, 12, 0, tzinfo=JST), True),      # 盘中 / 午休：还没收盘
                    (dt.datetime(2026, 10, 6, 15, 30, tzinfo=JST), False),                 # 收盘后：暂定
                    (dt.datetime(2026, 10, 7, 7, 0, tzinfo=JST), False)):                  # 第二天早上（正式日线还没换上）
        assert panel.chart_json("paper", "7203.T", now=now)[1]["data"]["live"]["open"] is op, now


def test_chart_endpoint_never_breaks_on_odd_chart_data(monkeypatch):
    """K 线文件缺字段（旧格式 / 写坏）或并的时候出错：照样给原来的图（200），不因为「今天这一根」打不开图。"""
    _pbook()
    _charts({"7203.T": {"kind": "stock", "tf": {"D": {"d": ["2026-10-02", "2026-10-05"], "c": [1, 2]}}}})
    panel._QUOTE_CACHE[("paper", ("1655.T", "7203.T"))] = (1e12, {"7203.T": {"px": 2.0, "at": "2026-10-06T09:40+09:00",
                                                                          "bar": {"d": "2026-10-06", "o": 1, "h": 2, "l": 1, "c": 2, "v": 5}}})
    code, js = panel.chart_json("paper", "7203.T", now=AT)
    assert code == 200 and "live" not in js["data"] and js["data"]["tf"]["D"]["c"] == [1, 2]
    monkeypatch.setattr(KL, "with_live", lambda *a, **k: 1 / 0)
    _charts({"7203.T": KL.payload(_daily(end="2026-10-05"), "2026-10-05", {"kind": "stock"})})
    code, js = panel.chart_json("paper", "7203.T", now=AT)
    assert code == 200 and "live" not in js["data"]


def test_page_script_reloads_held_charts_and_marks_the_live_bar():
    J = panel._JS
    for s in ("function liveK(R, on)", "function reloadK(t)", "liveK(x.j.rows||{}, x.j.live)", "(P.live.open ? '盘中 ' : '暂定 ')+liveAt(P)",
              "今天这一根（到 ", "暂定的一根（1 分钟线到 ", "P.live.open ? '盘中' : '暂定'", "' live' : ''", "box.dataset.hover"):
        assert s in J, s
    assert ".chart .live{stroke-dasharray:3 2}" in panel._CSS
