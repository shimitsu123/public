"""「规则接下来会自动买」每一行可以点开（2026-10-14 用户：「选股中的估计 5 个交易日内可能出现信号的股票也要可以能看到 K 线，
也可以有买入的 button 等等」）：收起时 = 原来的一行摘要；点开 = 「建议的股票」里同一只同一行（_suggest_row：买入… / 不能买的理由、
规则的买价、K 线 · 现价），默认收起；同一只票在两张卡里各一份，元素不带 id。"""
import re
from collections import Counter

from qbreak import panel

from test_panel import AT, _book, _card, _sm

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


def test_near_and_triggered_rows_expand_to_the_same_suggest_row(monkeypatch):
    _setup(monkeypatch=monkeypatch)
    html = panel.render("paper", "t" * 40, AT)
    ab, sg = _card(html, "autobuy"), _card(html, "suggest")
    assert "点一行展开：K 线 · 现价、买入…" in ab
    for t in ("1925.T", "6501.T", "8306.T"):                                # 默认收起：一行摘要在 summary 里
        assert f"<details class='abx' data-t='{t}'><summary>" in ab
    assert "<details class='abx' open" not in ab and "9008" not in ab        # 资格检查挡的不列（与以前一样）
    one = _abx(ab, "1925.T")
    s = one[:one.index("</summary>")]
    assert "约 2 天" in s and "<b>1925</b> 大和ハウス" in s and "<span class='chip" in s
    assert "历史出信号 9%" in s and "还差 1 个条件" in s and "data-act='buy'" not in s   # 摘要里没有按钮（点开才有）
    # 点开的内容 = 建议的股票里同一只（只差 K 线默认打开）
    for t in ("1925.T", "6501.T", "8306.T"):
        a, b = _row(ab, t, "autobuy"), _row(sg, t, "suggest")
        assert a.replace("<details class='kl' open>", "<details class='kl'>") == b.replace("<details class='kl' open>", "<details class='kl'>"), t
        assert a.endswith(f"<details class='kl' open><summary>K 线 · 现价</summary><div class='qt small' data-sq='{t}'></div>")
    btn = re.search(r"<button class='btn primary' data-act='buy' data-t='1925\.T'[^>]*>买入…</button>", one)
    assert btn and btn.group(0) in sg                                       # 按钮与数据属性一模一样（同一个买入框）
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
    ab, sg = _card(html, "autobuy"), _card(html, "suggest")
    one = _abx(ab, "1925.T")
    assert "名额满" in one[:one.index("</summary>")]
    assert "data-full='1'" in one and ">全部换成这只…<" in one and "个股名额已满（4 / 4 只）" in one
    assert _row(ab, "1925.T", "autobuy").replace(" open>", ">") == _row(sg, "1925.T", "suggest").replace(" open>", ">")
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
    assert html.count("<div class='chart' data-t='1925.T'") == 2 and html.count("data-sq='1925.T'") == 2


def test_quotes_and_kline_scripts_cover_both_cards():
    js = panel._JS
    assert "#autobuy details.abx[open] details.kl[open] .chart[data-t], #suggest details.kl[open] .chart[data-t]" in js   # 点开的行也取现价
    assert "e.target.closest('#suggest, #autobuy')" in js                    # 点开就取（不用等下一次刷新）
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
