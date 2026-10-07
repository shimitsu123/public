"""持仓的现价（2026-10-07 用户：「当天持有的股票、etf要知道现在的随时股价」）：/api/quotes（Yahoo 1 分钟线，约晚 20 分钟；只展示）。
① 行：个股（股数、比昨收、比成本）+ 核心 ETF（口数、比昨收）；票只来自账本；② 缓存：盘中 60 秒、其他时间 10 分钟、取不到 10 秒 / 1 分钟后再试；
③ 本机端口照常给；手机端口要你本人（没登录 → 401）；④ 页面：每只持仓下面的位置、说明一行、盘中 / 盘后的刷新间隔。"""
import datetime as dt
import json

import pytest

from qbreak import data as D
from qbreak import panel, paths
from qbreak.calendar_jp import JST

from test_manual_core import AT, _pbook
from test_panel import _req
from test_panel_phone import _book as _phone_book, _ident_setup, _ts, servers  # noqa: F401


@pytest.fixture(autouse=True)
def _clean():
    panel._QUOTE_CACHE.clear()
    yield
    panel._QUOTE_CACHE.clear()


def _fetch(calls: list, px=None):
    px = px or {"7203.T": 2650.0, "1655.T": 707.0, "1545.T": 20_100.0}

    def f(ts):
        calls.append(list(ts))
        return {t: {"px": px[t], "at": "2026-10-06T09:40+09:00"} for t in ts if t in px}
    return f


def test_quote_rows_for_held_stocks_and_etfs():
    _pbook()
    calls = []
    code, js = panel.quotes_json("paper", now=AT, fetch=_fetch(calls))
    assert code == 200 and js["ok"] and js["live"] and js["src"] == "Yahoo 1 分钟线（约晚 20 分钟）" and js["asof"] == "2026-10-06T10:00+09:00"
    assert calls == [["1655.T", "7203.T"]]                                 # 只取账本里持有的
    assert js["rows"]["7203.T"] == {"px": 2650.0, "at": "2026-10-06T09:40+09:00", "today": True, "kind": "stock", "n": 100,
                                    "value": 265_000, "chg_pct": 1.92, "pl_pct": 6.0}     # 比昨收 ¥2,600 / 比成本 ¥2,500
    c = js["rows"]["1655.T"]
    assert (c["kind"], c["n"], c["value"], c["chg_pct"], c["pl_pct"]) == ("core", 1130, 798_910, 1.0, None)   # 比上一次决策的收盘 ¥700
    night = dt.datetime(2026, 10, 7, 6, 30, tzinfo=JST)                      # 第二天开盘前：给的是前一个交易日的最后一根
    js = panel.quotes_json("paper", now=night, fetch=_fetch(calls))[1]
    assert not js["live"] and js["rows"]["7203.T"]["today"] is False


def test_quote_cache_and_retry(monkeypatch):
    _pbook()
    clock = {"t": 1000.0}
    monkeypatch.setattr(panel.time, "monotonic", lambda: clock["t"])
    calls = []
    panel.quotes_json("paper", now=AT, fetch=_fetch(calls))
    clock["t"] += 59
    panel.quotes_json("paper", now=AT, fetch=_fetch(calls))
    assert len(calls) == 1                                                 # 盘中：60 秒内不再取（Mac 与手机共用）
    clock["t"] += 2
    panel.quotes_json("paper", now=AT, fetch=_fetch(calls))
    assert len(calls) == 2
    eve = dt.datetime(2026, 10, 6, 18, 0, tzinfo=JST)
    clock["t"] += 599
    assert panel.quotes_json("paper", now=eve, fetch=_fetch(calls))[1]["rows"] and len(calls) == 2   # 收盘后：10 分钟
    clock["t"] += 2
    panel.quotes_json("paper", now=eve, fetch=_fetch(calls))
    assert len(calls) == 3
    panel._QUOTE_CACHE.clear()

    def bad(ts):
        calls.append(ts)
        raise RuntimeError("网络")
    code, js = panel.quotes_json("paper", now=AT, fetch=bad)
    assert code == 200 and js["ok"] and js["rows"] == {}                   # 取不到：空（页面写「取不到」），不报错
    clock["t"] += 9
    panel.quotes_json("paper", now=AT, fetch=bad)
    assert len(calls) == 4                                                 # 盘中取不到：10 秒后再试
    clock["t"] += 2
    panel.quotes_json("paper", now=AT, fetch=bad)
    assert len(calls) == 5


def test_quote_rows_empty_book_and_no_fetch():
    b = _pbook()
    b["state"].update(pos={}, core_units={"1655.T": 0})
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    calls = []
    assert panel.quotes_json("paper", now=AT, fetch=_fetch(calls))[1]["rows"] == {} and calls == []
    assert panel.quotes_json("tachibana", now=AT, fetch=_fetch(calls))[1]["rows"] == {} and calls == []   # 还没有账本


def test_quote_endpoint_local_and_phone(servers, monkeypatch):  # noqa: F811
    lp, pp, tok = servers
    calls = []
    monkeypatch.setattr(D, "intraday_quotes", _fetch(calls))
    _phone_book()                                                          # 7203.T 200 股 + 1545.T 100 口
    code, body, hd = _req(lp, "GET", "/api/quotes?book=paper")
    js = json.loads(body)
    assert code == 200 and set(js["rows"]) == {"7203.T", "1545.T"} and hd.get("Cache-Control") == "no-store"
    assert js["rows"]["1545.T"]["n"] == 100 and js["rows"]["7203.T"]["n"] == 200
    assert _req(lp, "GET", "/api/quotes?book=paper", headers={"Host": "evil.example:80"})[0] == 421
    assert _ts(pp, "GET", "/api/quotes?book=paper", gated=False)[0] == 401      # 手机端口：不是你本人 → 不给
    _ident_setup(pp)
    code, txt, _ = _ts(pp, "GET", "/api/quotes?book=paper")
    assert code == 200 and json.loads(txt)["rows"]["7203.T"]["px"] == 2650.0
    assert len(calls) == 1                                                 # Mac 与手机共用缓存


def test_page_has_quote_slots_note_and_refresh():
    _pbook()
    h = panel.render("paper", "tok", now=AT)
    assert "<div class='qt small' data-q='7203.T'></div>" in h and "<div class='qt small' data-q='1655.T'></div>" in h
    assert "现价：Yahoo 1 分钟线（约晚 20 分钟）" in h and '"live": true' in h
    assert '"live": false' in panel.render("paper", "tok", now=dt.datetime(2026, 10, 6, 18, 0, tzinfo=JST))
    for s in ("/api/quotes?book=", "60000", "600000", "visibilitychange"):
        assert s in panel._JS


def test_quote_line_in_node(tmp_path):
    """每只持仓下面的现价一行（盘中 = 时刻；不是今天 = 日期 + 「最近一个交易日」；涨红跌绿的颜色跟 K 线一样）。没有 node 就跳过。"""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    from test_panel import _js_fn
    fns = "\n".join(_js_fn(panel._JS, n) for n in ("nd", "pxs", "pcs", "qText", "showQ"))
    js = """
class El { constructor(t){ this.tagName=String(t).toUpperCase(); this.children=[]; this._t=''; this.className=''; this.dataset={}; }
  appendChild(c){ this.children.push(c); return c; }
  set textContent(v){ this._t=String(v); this.children=[]; } get textContent(){ return this._t+this.children.map(c=>c.textContent).join(''); } }
const mk=t=>{ const e=new El('div'); e.dataset.q=t; return e; };
const QS=[mk('7203.T'), mk('1655.T'), mk('9999.T')], NOTE=new El('div');
const document={createElement:t=>new El(t), querySelectorAll:s=>QS};
const $=s=>s==='#qt-note' ? NOTE : null;
const yen=v=>'¥'+Math.round(v).toLocaleString('ja-JP');
__FNS__
showQ({ok:true, src:'Yahoo 1 分钟线（约晚 20 分钟）', live:true, asof:'2026-10-06T10:00+09:00', rows:{
  '7203.T':{px:2650, at:'2026-10-06T09:40+09:00', today:true, kind:'stock', n:100, value:265000, chg_pct:1.92, pl_pct:6.0},
  '1655.T':{px:707, at:'2026-10-03T15:24+09:00', today:false, kind:'core', n:1130, value:798910, chg_pct:-0.5, pl_pct:null}}});
const out={a:QS[0].textContent, ac:QS[0].children[0].className, b:QS[1].textContent, bc:QS[1].children[0].className,
           c:QS[2].textContent, note:NOTE.textContent};
showQ({ok:false}); out.gone=QS[0].textContent; out.note2=NOTE.textContent;
showQ({ok:true, src:'Yahoo', live:false, asof:'2026-10-06T18:00+09:00', rows:{}}); out.none=QS[0].textContent;
console.log(JSON.stringify(out));
""".replace("__FNS__", fns)
    f = tmp_path / "q.js"
    f.write_text(js, encoding="utf-8")
    p = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    o = json.loads(p.stdout)
    assert o["a"] == "现价 ¥2,650（09:40） · 比昨收 +1.92% · 市值约 ¥265,000（100 股） · 比买入价 +6.00%" and o["ac"] == "up"
    assert o["b"] == "现价 ¥707.0（10/03 15:24，最近一个交易日） · 比昨收 -0.50% · 市值约 ¥798,910（1,130 口）" and o["bc"] == "down"
    assert o["c"] == "现价取不到（Yahoo 没有这只的分钟线）"
    assert o["note"] == "现价：Yahoo 1 分钟线（约晚 20 分钟），盘中每 1 分钟刷新；10:00 取"
    assert o["gone"] == "" and o["note2"] == o["note"]                     # 接口出错：不显示错的价，说明一行留着上一次的
    assert o["none"] == "现价暂时取不到（Yahoo 没回应：会自动再取）"            # 一只也没取到 = Yahoo 没回应
