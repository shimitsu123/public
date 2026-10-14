"""「规则接下来会自动买」每一行可以点开（2026-10-14 用户：「选股中的估计 5 个交易日内可能出现信号的股票也要可以能看到 K 线，
也可以有买入的 button 等等」）：收起时 = 原来的一行摘要；点开 = 这只在「建议的股票」里会有的那一行（_suggest_row：买入… / 不能买的理由、
规则的买价、K 线 · 现价；不带名次徽章），默认收起。
2026-10-15 用户：「去掉估计五个交易日内和建议的股票中重复的股票」→ 自动买那张卡列的（_auto_pick，只算一次）建议的股票不再列：
选股页每只票只出现一次；建议的股票的只数 = 它列的，另写跳过了几只；名次从 1 数起不跳号。"""
import json
import re
import shutil
import subprocess
from collections import Counter

import pytest

from qbreak import panel
from qbreak import watch_prob as WP

from test_panel import AT, _book, _card, _js_fn, _sm

NEAR = {"ticker": "1925.T", "code": "1925", "name": "大和ハウス", "sector": "建設業", "status": "imminent", "signal": False,
        "score": 70.0, "close": 4000.0, "near": {"where": "below_up", "days": 2, "miss": ["量"]}, "prob": {"p": 0.09},
        "near_text": "离买入信号：MACD 约 2 天后金叉", "rule": {"state": "none", "text": "还没触发买入信号：规则不会买"},
        "buy": {"block": None, "warn": [], "lot": 100, "px": 4000.0, "limit": 4120, "rule_shares": 100, "em": 1.0}}
BLOCKED = {"ticker": "6501.T", "code": "6501", "name": "日立", "status": "watch", "signal": False, "close": 3500.0,
           "near": {"where": "below_up", "days": 3}, "rule": {"state": "none"},
           "buy": {"block": "手动卖出后不自动买回（到 2026-10-07）", "block_kind": "manual", "warn": [], "lot": 100, "px": 3500.0,
                   "limit": 3605, "em": 1.0, "rule_shares": 100}}
GATED = {"ticker": "9008.T", "code": "9008", "name": "京王", "status": "watch", "near": {"where": "below_up", "days": 2},
         "close": 5000.0, "buy": {"block": "JPX 指定", "lot": 100, "px": 5000.0}}
TRIG = {"ticker": "8306.T", "code": "8306", "name": "三菱UFJ", "status": "triggered", "signal": True, "close": 2000.0,
        "rule": {"state": "blocked", "text": "信号成立但规则不买：新仓倍数 0"},
        "buy": {"block": None, "warn": [], "lot": 100, "px": 2000.0, "limit": 2060, "rule_shares": 200, "em": 1.0}}
MARK = {"dir": "down", "level": "大", "net": -1.2, "sector": "建設業",
        "items": [{"time": "2026-10-05T10:00:00+09:00", "eff": -1.2, "labels": ["金利"], "title": "测试消息", "id": "n1"}]}


def _blk(until, bid):
    return {"until": until, "since": "2026-09-30", "id": bid}


def _setup(pos=None, monkeypatch=None):
    _book(pos=pos, manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "blocks": {"6501.T": _blk("2026-10-07", "M-h")}})
    _sm([TRIG, NEAR, BLOCKED, GATED])
    if monkeypatch is not None:
        monkeypatch.setattr(panel, "_news_marks", lambda tickers, now=None: {"1925.T": MARK} if "1925.T" in tickers else {})


def _row(card: str, t: str, kind: str) -> str:
    """一张卡片里 t 那一行（<div class='hv sg'> 到它的 K 线占位之前）。"""
    i = card.index(f"<div class='chart' data-t='{t}' data-kind='{kind}'>")
    return card[card.rindex("<div class='hv sg'>", 0, i):i]


def _abx(card: str, t: str) -> str:
    i = card.index(f"<details class='abx' data-t='{t}'>")
    j = card.find("<details class='abx'", i + 1)
    return card[i:j if j > 0 else len(card)]


def _sg_undeduped(monkeypatch) -> str:
    """不去重时的建议的股票（测试用：把自动买那张卡列的代码清空）—— 对比点开的一行与建议的股票里会有的那一行一样。"""
    orig = panel._auto_pick
    with monkeypatch.context() as m:
        m.setattr(panel, "_auto_pick", lambda *a, **k: {**orig(*a, **k), "tickers": set()})
        return _card(panel.render("paper", "t" * 40, AT), "suggest")


def _norm(row: str) -> str:
    return RK.sub("", row).replace("<details class='kl' open>", "<details class='kl'>")


def test_near_and_triggered_rows_expand_to_the_suggest_row_and_are_not_repeated(monkeypatch):
    _setup(monkeypatch=monkeypatch)
    html = panel.render("paper", "t" * 40, AT)
    ab, sg = _card(html, "autobuy"), _card(html, "suggest")
    assert "点一行展开：K 线 · 现价、买入…" in ab
    for t in ("1925.T", "6501.T", "8306.T"):                                # 建议的股票不再列（2026-10-15）
        assert f"data-t='{t}'" not in sg and f"data-sq='{t}'" not in sg, t
    assert "建议的股票（规则的候选，1 只）" in sg and "上面「规则接下来会自动买」已列的 3 只不在这里重复" in sg
    assert "<b>9008</b>" in sg                                              # 资格检查挡的：自动买那张卡不列 → 留在建议的股票
    for t in ("1925.T", "6501.T", "8306.T"):                                # 默认收起：一行摘要在 summary 里
        assert f"<details class='abx' data-t='{t}'><summary>" in ab
    assert "<details class='abx' open" not in ab and "9008" not in ab        # 资格检查挡的不列（与以前一样）
    one = _abx(ab, "1925.T")
    s = one[:one.index("</summary>")]
    assert "约 2 天" in s and "<b>1925</b> 大和ハウス" in s and "<span class='chip" in s
    assert "历史出信号 9%" in s and "还差 1 个条件" in s and "data-act='buy'" not in s   # 摘要里没有按钮（点开才有）
    # 点开的内容 = 去重之前建议的股票里同一只（只差 K 线默认打开）
    full = _sg_undeduped(monkeypatch)
    for t in ("1925.T", "6501.T", "8306.T"):
        a, b = _row(ab, t, "autobuy"), _row(full, t, "suggest")
        assert _norm(a) == _norm(b), t
        assert a.endswith(f"<details class='kl' open><summary>K 线 · 现价</summary><div class='qt small' data-sq='{t}'></div>")
    btn = re.search(r"<button class='btn primary' data-act='buy' data-t='1925\.T'[^>]*>买入…</button>", one)
    assert btn and btn.group(0) in full                                     # 按钮与数据属性一模一样（同一个买入框）
    for k in ("data-code='1925'", "data-px='4000'", "data-lot='100'", "data-rule='100'", "data-limit='4120'", "data-sig='0'"):
        assert k in btn.group(0), k
    assert "规则的买价：出信号那天的收盘 ×1.03" in one and "⚠ 消息：受损 大（1 条，估算 -1.2%）" in one
    blk = _abx(ab, "6501.T")
    assert "10/07 解除后" in blk[:blk.index("</summary>")]
    assert "手动卖出后不买回（可在「交易」解除）：到 2026-10-07" in blk and "data-act='buy'" not in blk   # 不能买：同样的理由、没有按钮
    tr = _abx(ab, "8306.T")
    assert "信号成立但规则不买：新仓倍数 0" in tr[:tr.index("</summary>")] and "data-act='buy' data-t='8306.T'" in tr
    assert "规则的买价：" in tr and "开盘、最高 <b>¥2,060</b>" in tr


def test_full_slots_and_planned_rows_use_the_same_logic(monkeypatch):
    full = {t: {"shares": 100, "entry_px": 1000.0, "entry_date": "2026-09-01", "stop_px": 900.0, "last_close": 1000.0}
            for t in ("7203.T", "6758.T", "6861.T", "6098.T")}
    _setup(pos=full, monkeypatch=monkeypatch)
    html = panel.render("paper", "t" * 40, AT)
    ab = _card(html, "autobuy")
    one = _abx(ab, "1925.T")
    assert "名额满" in one[:one.index("</summary>")]
    assert "data-full='1'" in one and ">全部换成这只…<" in one and "个股名额已满（4 / 4 只）" in one
    assert _norm(_row(ab, "1925.T", "autobuy")) == _norm(_row(_sg_undeduped(monkeypatch), "1925.T", "suggest"))
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    _sm([{**TRIG, "rule": {"state": "planned", "text": "规则已安排：10/07 开盘买 200 股"}}])
    ab = _card(panel.render("paper", "t" * 40, AT), "autobuy")
    tr = _abx(ab, "8306.T")
    assert "下个开盘" in tr and "已经排在开盘买入" in tr and "data-act='buy'" not in tr and "data-planned='1'" in tr


def test_no_duplicate_ids_and_chart_kinds(monkeypatch):
    _setup(monkeypatch=monkeypatch)
    html = panel.render("paper", "t" * 40, AT)
    ids = Counter(re.findall(r"\sid=['\"]([^'\"]+)['\"]", html))
    assert not [k for k, n in ids.items() if n > 1], ids                    # 同一只票在两张卡里：元素都不带 id
    ab = _card(html, "autobuy")
    assert " id=" not in ab.replace("<section class='card' id='autobuy'>", "")
    assert ab.count("data-kind='autobuy'") == 3 and "data-kind='suggest'" not in ab
    for t in ("1925.T", "6501.T", "8306.T", "9008.T"):                    # 选股页每只票只出现一次（2026-10-15）
        assert html.count(f"<div class='chart' data-t='{t}'") == 1, t
    assert html.count("data-sq='1925.T'") == 1 and html.count("<details class='abx' data-t='1925.T'>") == 1


def test_no_ticker_in_both_cards_and_the_set_is_computed_once(monkeypatch):
    """两张卡用同一份代码集（_auto_pick 只算一次）：自动买那张卡列的 = 建议的股票跳过的，加起来 = 全部候选。"""
    _setup(monkeypatch=monkeypatch)
    calls = []
    orig = panel._auto_pick
    monkeypatch.setattr(panel, "_auto_pick", lambda *a, **k: calls.append(1) or orig(*a, **k))
    html = panel.render("paper", "t" * 40, AT)
    assert len(calls) == 1
    ab, sg = _card(html, "autobuy"), _card(html, "suggest")
    in_ab = set(re.findall(r"<details class='abx' data-t='([^']+)'>", ab))
    in_sg = set(re.findall(r"<div class='chart' data-t='([^']+)' data-kind='suggest'>", sg))
    assert in_ab == {"1925.T", "6501.T", "8306.T"} and in_sg == {"9008.T"} and not in_ab & in_sg
    assert in_ab | in_sg == {"1925.T", "6501.T", "8306.T", "9008.T"}


def test_suggest_card_empty_after_dedupe_shows_one_line(monkeypatch):
    _setup(monkeypatch=monkeypatch)
    _sm([TRIG, NEAR])                                                       # 两只都在自动买那张卡里
    html = panel.render("paper", "t" * 40, AT)
    sg = _card(html, "suggest")
    assert "建议的股票（规则的候选，0 只）" in sg
    assert "候选 2 只都在上面「规则接下来会自动买」里（点开一行看 K 线、买入…），这里不重复" in sg
    assert "<div class='hv sg'>" not in sg and "data-sgg" not in sg and "已列的" not in sg and "data-act='buy'" not in sg
    _sm([GATED])                                                            # 自动买那张卡一只也没列：不写跳过的那一行
    sg = _card(panel.render("paper", "t" * 40, AT), "suggest")
    assert "建议的股票（规则的候选，1 只）" in sg and "已列的" not in sg and "<b>9008</b>" in sg


def test_quotes_and_kline_scripts_cover_both_cards():
    js = panel._JS
    assert "#autobuy details.abx[open] details.kl[open] .chart[data-t], #suggest details.kl[open] .chart[data-t]" in js   # 点开的行也取现价
    assert "if(d.tagName!=='DETAILS' || !d.closest('#suggest, #autobuy')) return;" in js   # 点开就取（不用等下一次刷新）
    assert "document.querySelectorAll('.qt[data-sq]')" in js                  # 现价写进同一只的每一处（不是只写第一处）
    assert "document.addEventListener('toggle', e=>{ if(e.target.tagName==='DETAILS' && e.target.open) e.target.querySelectorAll('.chart[data-t]')" in js
    assert "else if(!KD[b.dataset.t] && !b.closest('details:not([open])')){ if(IO) IO.unobserve(b); showK(b); }" in js   # 点开就取 K 线
    assert "if(a==='buy'){" in js and "BUY={t:d.t, px:+d.px" in js           # 买入框只读按钮自己的 data-*（两处一样）


def test_card_without_chart_or_ctx_still_renders():
    _setup()
    import json
    book = json.loads((panel.paths.state_dir() / "live_unified_paper.json").read_text())
    h = panel._auto_buy_card({"asof": "2026-10-05", "rows": [NEAR]}, book, "paper", 1_000_000)
    assert "<details class='abx' data-t='1925.T'>" in h and "data-kind='autobuy'" in h and "data-act='buy'" in h


RK = re.compile(r"<span class='rk'[^>]*>[^<]*</span>")
FAR = {"ticker": "7203.T", "code": "7203", "name": "トヨタ", "status": "watch", "signal": False, "close": 3000.0,
       "near": {"where": "below_up", "days": 9, "miss": []}, "rule": {"state": "none"},
       "buy": {"block": None, "warn": [], "lot": 100, "px": 3000.0, "limit": 3090, "rule_shares": 100, "em": 1.0}}
ABOVE = {**FAR, "ticker": "6758.T", "code": "6758", "name": "ソニーG", "near": {"where": "above", "days": None, "miss": []}}


def test_ranked_rows_have_no_badge_above_and_ranks_without_gaps_below(monkeypatch, tmp_path):
    """有比例表（生产里有 var/watch_prob.json）：自动买那张卡点开的行有历史比例 / 快要出，但不带名次徽章（那几只不在建议的股票里，
    名次指不到那边；2026-10-15）；建议的股票的名次按它列的从 1 数起、不跳号。"""
    _setup(monkeypatch=monkeypatch)
    _sm([TRIG, NEAR, BLOCKED, GATED, FAR, ABOVE])
    t = WP.fit([("down_far", "m0", "v_lo", int(k < 9)) for k in range(100)] + [("up_d1", "m1", "v_hi", int(k < 4)) for k in range(100)]
               + [("above_far", "m0", "v_lo", 0) for _ in range(300)], extra={"show_pct": True})
    fp = tmp_path / "wp.json"
    fp.write_text(json.dumps(t), encoding="utf-8")
    monkeypatch.setattr(WP, "FILE", fp)
    html = panel.render("paper", "t" * 40, AT)
    ab, sg = _card(html, "autobuy"), _card(html, "suggest")
    assert "<span class='rk'" not in ab and "观察中第" not in html          # 自动买那张卡：没有名次徽章
    full = _sg_undeduped(monkeypatch)
    for tk in ("1925.T", "6501.T"):
        a = _row(ab, tk, "autobuy")
        assert "<div class='small prob'>" in a, tk                          # 历史比例那一行照样在
        assert _norm(a) == _norm(_row(full, tk, "suggest")), tk             # 其余与建议的股票会有的那一行一样
    assert "<span class='chip hot'>快要出</span>" in _abx(ab, "1925.T") and "<div class='small prob'>" not in _abx(ab, "8306.T")
    ranks = [(int(n), c) for n, c in re.findall(r"<span class='rk'>(\d+)</span><b>(\d+)</b>", sg)]
    assert [n for n, _ in ranks] == [1, 2, 3] and {c for _, c in ranks} == {"9008", "7203", "6758"}   # 不跳号（去重前 1925 / 6501 也占名次）
    before = [int(n) for n in re.findall(r"<span class='rk'>(\d+)</span>", full)]
    assert before == [1, 2, 3, 4, 5]
    assert "建议的股票（规则的候选，3 只）" in sg and "已列的 3 只不在这里重复" in sg and "<h3 class='sgh'>观察中 · 3 只" in sg


def test_expanded_row_has_a_close_button_at_the_bottom(monkeypatch):
    _setup(monkeypatch=monkeypatch)
    ab = _card(panel.render("paper", "t" * 40, AT), "autobuy")
    for tk in ("1925.T", "6501.T", "8306.T"):
        one = _abx(ab, tk)
        assert one.count("data-abxclose") == 1, tk
        assert "<div class='abxe'><button type='button' class='btn' data-abxclose='1'>收起</button></div></div></details>" in one, tk
    js = panel._JS
    assert "const b=e.target.closest('[data-abxclose]'); if(!b) return;" in js and "const d=b.closest('details.abx'); if(!d) return;" in js
    assert "e.preventDefault(); d.open=false;" in js                        # 收起后把摘要滚到页头下面（在屏幕外时）


def test_panel_server_accepts_bursts_of_connections():
    """一下点开很多行：K 线 / 现价同时取（socketserver 默认只排 5 个连接，多了在 TCP 层被拒；2026-10-14 复核）。"""
    assert issubclass(panel._Srv, panel.ThreadingHTTPServer) and panel._Srv.request_queue_size >= 32 and panel._Srv.daemon_threads
    import inspect
    src = inspect.getsource(panel.serve)
    assert src.count("_Srv((\"127.0.0.1\"") == 2 and "ThreadingHTTPServer(" not in src       # 本机端口与手机端口都用它


def test_quotes_take_recent_first_and_explain_the_ones_over_the_limit(tmp_path):
    """点开超过 12 只：买入框 → 最近点开的 → 其余（页面顺序）取前 12 只；取不到的写一行说明（不留空、不留旧价）。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    js = panel._JS
    assert "CFG.sq_max" in js and panel.render  # noqa: B018
    fns = "\n".join(_js_fn(js, n) for n in ("sqAll", "sqWant", "sqOver"))
    src = """
function nd(tag, cls, text, par){ const e={tag, cls, text}; if(par) par.kids.push(e); return e; }
const OPEN = __OPEN__;
const QT = OPEN.concat(['2432.T']).map(t=>({dataset:{sq:t}, kids:[], set textContent(v){ this.kids=[]; this.txt=v; }}));
QT[0].dataset.over='1';
const document = {querySelectorAll: s => s.indexOf('.qt[data-sq]')===0 ? QT : OPEN.map(t=>({dataset:{t}}))};
let DLG = {open:true}; const $ = s => s==='#dlg-buy' ? DLG : null;
let BUY = {t:'7777.T'}; const SQMAX = 12; let RECENT = ['9531.T', '1111.T'];
__FNS__
const all = sqAll(), want = sqWant();
sqOver(all.slice(SQMAX), all.length);
console.log(JSON.stringify({all, want, qt: QT.map(e=>({t:e.dataset.sq, over:e.dataset.over||null, n:e.kids.length, txt:e.kids.length ? e.kids[0].text : null}))}));
""".replace("__FNS__", fns).replace("__OPEN__", json.dumps([f"{1000 + k}.T" for k in range(12)] + ["9531.T"]))
    f = tmp_path / "q.js"
    f.write_text(src, encoding="utf-8")
    p = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-800:]
    o = json.loads(p.stdout)
    assert o["all"][:2] == ["7777.T", "9531.T"] and "1111.T" not in o["all"]   # 买入框 → 最近点开的（收起了的不算）→ 其余
    assert o["want"] == o["all"][:12] and o["all"][12:] == ["1010.T", "1011.T"]
    over = {e["t"]: e for e in o["qt"]}
    for tk in ("1010.T", "1011.T"):
        assert over[tk]["over"] == "1" and over[tk]["txt"] == "现价一次最多取 12 只（现在打开了 14 只）：收起几行再看"
    assert over["1000.T"]["over"] is None and over["9531.T"]["over"] is None   # 以前超过、现在轮到了：说明去掉（等现价写进来）
    assert over["2432.T"]["over"] is None and over["2432.T"]["n"] == 0        # 没打开的不动
