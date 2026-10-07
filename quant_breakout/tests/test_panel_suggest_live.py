"""建议的股票的盘中现价 / K 线 + 下单按什么价（2026-10-07 用户：「现在卖出的时候看到的股价差了20分钟 不能直接知道当时股价的话能依据什么价位进行下单 /
建议的股票中也要能看到当天实时的K线 点击买入的时候也可以看到当前的价格 / 现在持有的etf要预估出大概的卖价，建议的股票要给出合适的买价」）。
① MO.order_basis / delay_range；② /api/quotes?t=…：只接受汇总里列着的、没拿着的建议股票（一次最多 SG_MAX 只）、现在买的限价（≤ 收盘 ×1.03）、
晚了几分钟的范围；③ K 线并进今天这一根（建议的股票也并）；④ 页面：规则的买价一行、K 线里的现价位置、买入框的现价；⑤ 页面脚本（node）。"""
import datetime as dt
import json
import math
import shutil
import subprocess

import pytest

from qbreak import data as D
from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST

from test_manual_core import AT, _pbook
from test_panel import _js_fn, _req
from test_panel_phone import servers  # noqa: F401

SG = [{"ticker": "6501.T", "code": "6501", "name": "日立", "status": "triggered", "signal": True, "close": 3500.0, "score": 80.0,
       "rule": {"state": "planned", "text": "规则已安排"}, "buy": {"block": None, "warn": [], "lot": 100, "px": 3500.0, "limit": 3605,
                                                                   "rule_shares": 200}},
      {"ticker": "9984.T", "code": "9984", "name": "ソフトバンクG", "status": "watch", "signal": False, "close": 9000.0, "score": 50.0,
       "rule": {"state": "none", "text": ""}, "buy": {"block": None, "warn": [], "lot": 100, "px": 9000.0, "limit": 9270,
                                                      "rule_shares": 100}}]


@pytest.fixture(autouse=True)
def _clean():
    panel._QUOTE_CACHE.clear()
    panel._CHART_CACHE.clear()
    yield
    panel._QUOTE_CACHE.clear()
    panel._CHART_CACHE.clear()


def _setup(rows=None, charts=True):
    _pbook()                                                               # 拿着 7203.T 100 股 + 1655.T 1,130 口
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"suggest": {"asof": "2026-10-05", "fill_day": "2026-10-06",
                                                                                     "rows": rows or SG}}, ensure_ascii=False), encoding="utf-8")
    if charts:                                                             # K 线文件：日K 收盘每天交替 ±1%（日波动约 1%）
        c = [1000.0 * (1.01 if k % 2 else 1.0) for k in range(80)]
        d = [f"2026-06-{k % 28 + 1:02d}" for k in range(80)]
        tick = {"kind": "suggest", "tf": {"D": {"d": d, "o": c, "h": c, "l": c, "c": c, "v": [1] * 80}}}
        (paths.out_dir() / "charts_paper.json").write_text(json.dumps({"asof": "2026-10-05", "tickers": {
            "9984.T": tick, "6501.T": tick, "7203.T": tick, "1111.T": tick}}), encoding="utf-8")


def _fetch(calls: list, px=None, at="2026-10-06T09:40+09:00"):
    px = px or {"7203.T": 2650.0, "1655.T": 707.0, "6501.T": 3530.0, "9984.T": 9400.0, "1111.T": 500.0}

    def f(ts):
        calls.append(list(ts))
        return {t: {"px": px[t], "at": at, "bar": {"d": at[:10], "o": px[t], "h": px[t], "l": px[t], "c": px[t], "v": 100}}
                for t in ts if t in px}
    return f


# ────────── ① 下单按什么价 / 晚了几分钟的范围 ──────────
def test_order_basis_and_delay_range():
    at = lambda h, m: dt.datetime(2026, 10, 6, h, m, tzinfo=JST)          # noqa: E731
    assert "Yahoo 现价" in MO.order_basis(True, at(10, 0), "SELL") and "超过收盘 ×1.03 → 不买" in MO.order_basis(True, at(10, 0), "BUY")
    assert MO.order_basis(False, at(10, 0), "SELL") == "立花在执行器下单那一刻取实时现价，限价 = 实时现价 −0.5%（成交多在限价〜现价之间）"
    assert "min(实时现价 +0.5%, 收盘 ×1.03)" in MO.order_basis(False, at(10, 0), "BUY")
    assert MO.order_basis(False, at(12, 0), "SELL").startswith("12:30 后场开始后，立花在执行器下单那一刻")
    assert MO.order_basis(False, at(8, 0), "SELL") == "今天 09:00 开盘按开盘价卖（寄付成行）"
    assert MO.order_basis(True, at(16, 0), "BUY").startswith("10/07 开盘买：寄付指値 = 收盘 ×1.03")
    assert MO.delay_range(0.02, 300) == 4.0 and MO.delay_range(0.02, 20) == round(2 * 0.02 * math.sqrt(20 / 300) * 100, 2)
    assert MO.delay_range(0.02, 900) == 4.0                                # 最多一天
    assert MO.delay_range(None, 20) is None and MO.delay_range(0.02, 0) is None and MO.delay_range(float("nan"), 20) is None
    assert panel._delay_min("2026-10-06T09:40+09:00", at(10, 0)) == 20.0
    assert panel._delay_min("2026-10-05T15:24+09:00", at(10, 0)) is None   # 不是今天的：那就是收盘价
    assert panel._delay_min("2026-10-06T15:24+09:00", at(16, 0)) is None   # 收盘后
    assert panel._delay_min("bad", at(10, 0)) is None


# ────────── ② /api/quotes?t=… ──────────
def test_suggestion_quotes_only_listed_not_held_and_capped(monkeypatch):
    _setup()
    calls = []
    code, js = panel.quotes_json("paper", now=AT, fetch=_fetch(calls), extra=["9984.T", "6501.T", "7203.T", "1111.T", "9984.T"])
    assert code == 200 and calls == [["6501.T", "9984.T"]]                # 7203.T 拿着（走持仓那条）、1111.T 不在建议里 → 不取
    assert set(js["rows"]) == {"6501.T", "9984.T"} and js["basis"]["BUY"].startswith("模拟账户")
    w = js["rows"]["9984.T"]
    assert (w["kind"], w["n"], w["chg_pct"]) == ("suggest", 0, round((9400 / 9000 - 1) * 100, 2)) and "est" not in w
    assert w["buy"] == {"cap": 9270.0, "lim": 9270.0, "over": True, "close": 9000.0}   # 现价 9,400 > 收盘 ×1.03 = 9,270 → 不买
    t = js["rows"]["6501.T"]["buy"]
    assert t["over"] is False and t["lim"] == 3545.0 and t["cap"] == 3605.0  # min(3,530 × 1.005 → 3,545（呼値 5 円）, 3,605)
    assert w["delay"] == 20 and w["rng"] == MO.delay_range(panel._dvol("paper", "9984.T"), 20) and 0 < w["rng"] < 2
    assert 0.009 < panel._dvol("paper", "9984.T") < 0.011                  # K 线文件的日波动（约 1%）
    held = panel.quotes_json("paper", now=AT, fetch=_fetch(calls))[1]
    assert set(held["rows"]) == {"7203.T", "1655.T"} and "est" in held["rows"]["7203.T"] and held["rows"]["7203.T"]["rng"] > 0
    assert held["basis"]["SELL"].startswith("模拟账户")
    monkeypatch.setattr(panel, "SG_MAX", 1)
    panel._QUOTE_CACHE.clear()
    assert set(panel.quotes_json("paper", now=AT, fetch=_fetch(calls), extra=["9984.T", "6501.T"])[1]["rows"]) == {"9984.T"}
    assert panel.quotes_json("paper", now=AT, fetch=_fetch(calls), extra=[])[1]["rows"] == {}
    night = dt.datetime(2026, 10, 6, 18, 0, tzinfo=JST)                     # 收盘后：没有「晚了几分钟」（那就是收盘价）
    r = panel.quotes_json("paper", now=night, fetch=_fetch(calls), extra=["9984.T"])[1]
    assert "rng" not in r["rows"]["9984.T"] and r["basis"]["BUY"].startswith("10/07 开盘买")
    assert panel._extra_of("book=paper&t=9984.t,6501.T,%3Cx%3E,,9984.T") == ["9984.T", "6501.T"] and panel._extra_of("book=paper") is None


def test_suggestion_quotes_endpoint_and_live_candle(servers, monkeypatch):  # noqa: F811
    lp, pp, tok = servers
    _setup()
    calls = []
    monkeypatch.setattr(D, "intraday_quotes", _fetch(calls))
    code, body, _ = _req(lp, "GET", "/api/quotes?book=paper&t=9984.T,1111.T")
    js = json.loads(body)
    assert code == 200 and set(js["rows"]) == {"9984.T"} and calls == [["9984.T"]]
    code, cj = panel.chart_json("paper", "9984.T", AT)                     # 建议的股票：现价取过 → K 线并进今天这一根
    assert code == 200 and cj["data"]["tf"]["D"]["d"][-1] == "2026-10-06" and cj["data"]["live"]["open"] is True
    panel._QUOTE_CACHE[("paper", ("1111.T",))] = (1e12, {"1111.T": {"px": 500.0, "at": "2026-10-06T09:40+09:00",
                                                                   "bar": {"d": "2026-10-06", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}}})
    code, cj = panel.chart_json("paper", "1111.T", AT)                     # 不在建议里、也没拿着 → 不并
    assert code == 200 and "live" not in cj["data"]


# ────────── ④ 页面 ──────────
def test_page_rule_buy_price_live_slot_and_buy_dialog():
    _setup()
    h = panel.render("paper", "tok", now=AT)
    assert "规则的买价：10/06 开盘、最高 <b>¥3,605</b>（= 收盘 ¥3,500 ×1.03；开盘价更高就不买）" in h
    assert "<div class='qt small' data-sq='6501.T' data-planned='1'></div>" in h   # 已排在开盘买：现价那行只写现价
    assert "规则的买价：出信号那天的收盘 ×1.03 是第二天开盘的最高价（按今天收盘 ≈ ¥9,270）" in h
    assert "<summary>K 线 · 现价</summary><div class='qt small' data-sq='9984.T'></div>" in h
    assert "<div id='buy-live' class='small pl'></div>" in h
    for s in ("&t=", "loadSQ", "buyLive()", "#suggest details.kl[open]", "priceHead(q)",
              "KP[t].then(()=>{ if(KD[t] && typeof KD[t]==='object') reloadK(t); })"):   # 图比现价先到：取完再要一次（并进今天这一根）
        assert s in panel._JS


# ────────── ⑤ 页面脚本 ──────────
def test_buy_lines_in_node(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    fns = "\n".join(_js_fn(panel._JS, n) for n in ("pxs", "pcs", "hmOf", "rngText", "priceHead", "buyLines"))
    js = """
const CFG={paper:false};
__FNS__
const J={live:true, basis:{BUY:'立花在执行器下单那一刻取实时现价，限价 = min(实时现价 +0.5%, 收盘 ×1.03)'}};
const q={px:3530, at:'2026-10-06T09:40+09:00', today:true, chg_pct:0.86, delay:20, rng:0.5, buy:{cap:3605, lim:3545, over:false}};
const over={...q, px:9400, buy:{cap:9270, lim:9270, over:true}};
const out={h:priceHead(q), a:buyLines(q, J, false), f:buyLines(q, J, true), b:buyLines(over, J, false),
           c:buyLines({...q, delay:null, rng:null}, {live:false, basis:{BUY:'10/07 开盘买：寄付指値 = 收盘 ×1.03'}}, false)};
CFG.paper=true; out.p=buyLines(q, J, false);
console.log(JSON.stringify(out));
""".replace("__FNS__", fns)
    f = tmp_path / "b.js"
    f.write_text(js, encoding="utf-8")
    p = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    o = json.loads(p.stdout)
    assert o["h"] == "现价 ¥3,530（09:40，约晚 20 分钟） · 比收盘 +0.86%"
    assert o["a"] == ["现在买：限价约 ¥3,545；上限 = 收盘 ×1.03 = ¥3,605", "晚约 20 分钟：现在的价通常在 ¥3,512〜¥3,548（±0.5%）"]
    assert o["p"][0] == "现在买：约 ¥3,530 成交（模拟账户按现价）；上限 = 收盘 ×1.03 = ¥3,605"   # 模拟账户：按现价成交
    assert o["f"][1] == "下单：立花在执行器下单那一刻取实时现价，限价 = min(实时现价 +0.5%, 收盘 ×1.03)"   # 买入框多写下单依据
    assert o["b"][0] == "★ 现价已超过收盘 ×1.03（¥9,270）：现在不买（规则和手动买入都一样）" and not any("限价约" in x for x in o["b"])
    assert o["c"] == ["10/07 开盘买：寄付指値 = 收盘 ×1.03"]                 # 收盘后：开盘买的说法
