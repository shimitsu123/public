"""本机操作面板（qbreak/panel.py）：只接受本机、要令牌、只写手动指令；交易日 07:45〜08:55 早上的决策做了之后叫执行器重试。"""
import datetime as dt
import http.client
import json
import logging
import os
import threading
from http.server import ThreadingHTTPServer

import pytest

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST


def _book(tag="paper", last="2026-10-05", pos=None, orders=None, manual=None):
    st = {"last_date": last, "cash_jpy": 500_000.0, "history": [[last, 1_000_000.0, 0, 0, 150]],
          "pos": pos if pos is not None else {"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01",
                                                         "stop_px": 2325.0, "last_close": 2600.0}},
          "pending_exit": {}, "core_units": {"1545.T": 100}}
    b = {"state": st, "orders": orders or []}
    if manual:
        b["manual"] = manual
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


AT = dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST)


@pytest.fixture()
def server():
    tok = panel.token()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), panel.make_handler(1, tok))
    port = srv.server_address[1]
    srv.RequestHandlerClass = panel.make_handler(port, tok, clock=lambda: AT)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield port, tok
    srv.shutdown()
    srv.server_close()


def _req(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": f"127.0.0.1:{port}"}
    h.update(headers or {})
    data = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    out = r.status, r.read().decode("utf-8"), dict(r.getheaders())
    c.close()
    return out


def _nofetch(ts):
    return {}


def _submit_ok(body, now=AT, source="panel"):
    """固定口数 / 恢复按规则要先「确认下单」（2026-10-15）：第一次 → need_confirm（什么都没写），带上服务器给的 token 再交一次 = 点了「确认下单」。
    别的指令照旧一次就写。测试里不联网取现价。"""
    ok, msg, rec = panel.submit(body, now, source=source, fetch=_nofetch)
    if not ok and (rec or {}).get("need_confirm"):
        return panel.submit({**body, "confirm": rec["confirm"]["token"]}, now, source=source, fetch=_nofetch)
    return ok, msg, rec


def test_token_is_private_and_stable():
    t = panel.token()
    p = paths.home() / panel.TOKEN_FILE
    assert len(t) >= 32 and oct(os.stat(p).st_mode & 0o777) == "0o600" and panel.token() == t


def test_page_needs_local_host_and_carries_no_broker_secrets(server):
    port, tok = server
    _book()
    code, html, hd = _req(port, "GET", "/?book=paper")
    assert code == 200 and "qbreak 操作面板" in html and tok in html and "卖出全部" in html and "调仓…" in html
    assert hd.get("X-Frame-Options") == "DENY" and "frame-ancestors 'none'" in hd.get("Content-Security-Policy", "")
    assert _req(port, "GET", "/", headers={"Host": "evil.example:80"})[0] == 421          # DNS rebinding
    assert _req(port, "GET", "/etc/passwd")[0] == 404


def test_post_requires_token_origin_json_and_size(server):
    port, tok = server
    _book()
    ok_h = {"X-Qbreak-Token": tok, "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"}
    body = {"book": "paper", "kind": "sell", "ticker": "7203", "block_days": 20}
    assert _req(port, "POST", "/api/request", body, {**ok_h, "X-Qbreak-Token": "x" * 40})[0] == 403
    assert _req(port, "POST", "/api/request", body, {**ok_h, "Origin": "https://evil.example"})[0] == 403
    assert _req(port, "POST", "/api/request", body, {**ok_h, "Content-Type": "text/plain"})[0] == 415
    assert _req(port, "POST", "/api/request", b"x" * 5000, ok_h)[0] == 413
    assert _req(port, "POST", "/api/request", body, {**ok_h, "Host": "evil.example"})[0] == 421
    assert not MO.read_all("paper")                                                        # 上面这些都没写进去
    code, txt, _ = _req(port, "POST", "/api/request", body, ok_h)
    j = json.loads(txt)
    assert code == 200 and j["ok"] and "今天 09:00 开盘卖出" in j["msg"]                   # 开盘前点的：等开盘
    r = MO.read_all("paper")
    assert len(r) == 1 and r[0]["ticker"] == "7203.T" and r[0]["source"] == "panel"
    code, txt, _ = _req(port, "POST", "/api/request", body, ok_h)                           # 同一只票再点：挡住
    assert code == 400 and "没处理完" in json.loads(txt)["msg"]
    code, txt, _ = _req(port, "POST", "/api/request", {**body, "ticker": "6758"}, ok_h)
    assert code == 400 and "没有 6758.T" in json.loads(txt)["msg"]


def test_submit_messages_and_halt_note():
    _book()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "trim", "ticker": "7203", "pct": 10}, AT)
    assert ok and rec["pct"] == 10.0 and "减到约 10%" in msg
    ok, msg, _ = panel.submit({"book": "tachibana", "kind": "core", "pct": 40}, dt.datetime(2026, 10, 6, 9, 30, tzinfo=JST))
    assert ok and "马上（盘中）照新比例调" in msg                                          # 闲置资金比例：盘中写的也马上调核心 ETF
    assert panel.submit({"book": "../etc", "kind": "core", "pct": 40})[0] is False
    paths.halt_file().write_text("x", encoding="utf-8")
    _book("tachibana")
    ok, msg, _ = panel.submit({"book": "tachibana", "kind": "sell", "ticker": "7203"}, dt.datetime(2026, 10, 6, 9, 30, tzinfo=JST))
    assert ok and "马上（盘中）卖出" in msg and "HALT 生效中" in msg                    # 盘中点的：马上（HALT 解除之后才处理）
    _book("tachibana_demo")
    ok, msg, _ = panel.submit({"book": "tachibana_demo", "kind": "sell", "ticker": "7203"}, dt.datetime(2026, 10, 6, 15, 40, tzinfo=JST))
    assert ok and "10/07 开盘卖出" in msg                                                # 收盘后点的：下一个交易日开盘


def test_trigger_runs_retry_in_the_morning_and_now_in_the_session(monkeypatch):
    calls = []
    now = {"t": dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST)}
    import qbreak.calendar_jp as CJ
    monkeypatch.setattr(CJ, "now_jst", lambda: now["t"])      # expected_last_bar 看真实时钟：真实日期 = 10-06 收盘后会算成 10-06 → 固定成假时钟
    trg = panel.Trigger(run=lambda tag, mode="retry": calls.append((tag, mode)), clock=lambda: now["t"])
    _book(last="2026-10-02")                                   # 早上的运行还没处理 10-05 → 不叫（它自己会读到指令）
    MO.append("paper", {"kind": "sell", "ticker": "7203"})
    assert trg.check() == [] and calls == []
    _book(last="2026-10-05")
    assert trg.check() == ["paper"] and calls == [("paper", "retry")]     # 07:45〜08:55：加进今天开盘的寄付单
    assert trg.check() == []                                    # 3 分钟之内不重复
    trg.last.clear()
    now["t"] = dt.datetime(2026, 10, 6, 8, 55, tzinfo=JST)      # 过了 08:55（寄付截止）、还没开盘：等 09:00
    assert trg.check() == []
    now["t"] = dt.datetime(2026, 10, 6, 9, 30, tzinfo=JST)      # 盘中：马上下（--phase now）
    assert trg.check() == ["paper"] and calls[-1] == ("paper", "now")
    assert trg.check() == []                                    # 1 分钟之内不重复
    trg.last.clear()
    for hh, mm in ((12, 0), (15, 30)):                          # 午休 / 收盘后：不叫
        now["t"] = dt.datetime(2026, 10, 6, hh, mm, tzinfo=JST)
        assert trg.check() == []
    now["t"] = dt.datetime(2026, 10, 6, 13, 0, tzinfo=JST)
    paths.halt_file().write_text("x", encoding="utf-8")         # HALT：盘中也不叫
    assert trg.check() == []
    paths.halt_file().unlink()
    now["t"] = dt.datetime(2026, 10, 10, 10, 0, tzinfo=JST)     # 周六
    assert trg.check() == []
    assert len(calls) == 2


def test_due_ignores_core_only_and_handled_requests():
    b = _book()
    MO.append("paper", {"kind": "core", "pct": 50})
    assert not MO.due("paper", b, AT)
    rec = MO.append("paper", {"kind": "sell", "ticker": "7203"})
    assert MO.due("paper", b, AT) and not MO.due("paper", b, dt.datetime(2026, 10, 6, 8, 55, tzinfo=JST))
    b["manual"] = {"items": {r["id"]: {**r, "status": "placed"} for r in MO.read_all("paper")}}
    assert not MO.due("paper", b, AT)
    b["manual"]["items"][rec["id"]]["cancel_req"] = "M20261006-081000-cancel"
    assert MO.due("paper", b, AT)


def test_render_shows_reasons_trend_and_hides_buttons_for_pending_exit():
    _book(pos={"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0},
               "6758.T": {"shares": 100, "entry_px": 3000.0, "entry_date": "2026-09-10", "stop_px": 2790.0, "last_close": 3100.0}},
          manual={"core_pct": 60.0, "blocks": {"9984.T": {"until": "2026-11-04"}}, "items": {}})
    b = json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8"))
    b["state"]["pending_exit"] = {"6758.T": "dead_cross"}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b), encoding="utf-8")
    hv = {"bar_date": "2026-10-05", "holdings": [
        {"ticker": "7203.T", "name": "トヨタ自動車", "shares": 200, "entry_date": "2026-09-01", "entry_px": 2500.0,
         "why": {"signal_date": "2026-08-29", "items": [{"key": "volume", "text": "放量：成交量是 20 日平均的 2.10 倍", "ok": True}],
                 "ok": True, "vol_ratio": 2.1, "golden_cross": True, "range_pct": 9.5, "range_n": 60},
         "trend": {"label": "up", "text": "收盘 ¥2,600：20 日线 …", "ret_pct": 4.0}},
        {"ticker": "6758.T", "shares": 100, "error": "x"}], "core": []}
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"holding_view": hv, "fill_day": "2026-10-06"}), encoding="utf-8")
    html = panel.render("paper", "t" * 40, AT)
    assert "トヨタ自動車" in html and "上涨中" in html and "成交量是 20 日平均的 2.10 倍" in html
    assert html.count("2.10 倍") == 1 and "其他规则读数" not in html            # 一句话里说了的读数，明细里不重复
    assert html.count("卖出全部</button>") == 1 and "已排定开盘卖（MACD 死叉）" in html
    assert "规则目标额的 <b>60%</b>" in html and "9984.T" in html and "解除" in html
    assert "模拟账户：手动操作后会和云端模拟盘不一致" in html and "现在点买卖 → <b>今天 09:00 开盘</b>下单" in html
    assert html.count("非投资建议") == 1


def test_submit_adjust_messages_and_due():
    _book(pos={"6758.T": {"shares": 200, "entry_px": 900.0, "entry_date": "2026-09-01", "stop_px": 850.0, "last_close": 1000.0},
               "7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0, "last_close": 2600.0}})
    ok, msg, rec = panel.submit({"book": "paper", "kind": "adjust", "ticker": "6758", "unit": "yen", "value": 100_000}, AT)
    assert ok and rec["unit"] == "yen" and "已写：6758.T 卖 100 股（→ 100 股）→ 今天 09:00 开盘卖出" in msg
    MO.append("paper", {"kind": "cancel", "target": rec["id"]})
    b = json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8"))
    b["manual"] = {"items": {rec["id"]: {**rec, "status": "cancelled"}}}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b), encoding="utf-8")
    ok, msg, rec2 = panel.submit({"book": "paper", "kind": "adjust", "ticker": "6758", "unit": "pct", "value": 30}, AT)
    assert ok and "已写：6758.T 加 100 股（→ 300 股）→ 今天 09:00 开盘买入" in msg   # 07:40 的决策已经做了 → 开盘后盘中买
    ok, msg, _ = panel.submit({"book": "paper", "kind": "adjust", "ticker": "7203", "unit": "shares", "value": 400}, AT)
    assert ok and "已写：7203.T 加" in msg                     # 已经约占 52%：2026-10-12 起手动加仓不设单只上限（到总权益）
    b = json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8"))
    only_wait = {"state": b["state"], "manual": {"items": {rec2["id"]: {**rec2, "status": "pending", "wait": True}}}}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(only_wait), encoding="utf-8")
    MO.requests_path("paper").write_text(json.dumps(rec2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert not MO.due("paper", only_wait, AT)                   # 等下一次决策的加仓：不叫重试


TR = {"D": {"label": "上升", "align": "多头排列"}, "W": {"label": "震荡", "align": ""}, "M": {"label": "下降", "align": "空头排列"}}


def _kfile(tickers: dict) -> None:
    (paths.out_dir() / "charts_paper.json").write_text(json.dumps({"asof": "2026-10-05", "tickers": tickers}, ensure_ascii=False),
                                                       encoding="utf-8")


def test_render_adjust_buttons_and_kline():
    _book(pos={"6758.T": {"shares": 200, "entry_px": 900.0, "entry_date": "2026-09-01", "stop_px": 850.0, "last_close": 1000.0}},
          manual={"cap_pct": 34.0, "items": {}})
    kl = {"asof": "2026-10-05", "file": "charts_paper.json", "trend": {"6758.T": TR, "1545.T": TR},
          "items": {"6758.T": {"kind": "stock"}, "1545.T": {"kind": "core", "name": "纳斯达克 100（1545）"},
                    "1482.T": {"kind": "core", "name": "对冲版美国国债</script><b>x"}}}
    hv = {"bar_date": "2026-10-05", "holdings": [{"ticker": "6758.T", "shares": 200, "error": "x"}],
          "core": [{"ticker": "1545.T", "name": "纳斯达克 100（1545）", "units": 100, "why": "闲置资金规则"}]}
    _kfile({"6758.T": {"kind": "stock", "tf": {}}})
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"holding_view": hv, "kline": kl}), encoding="utf-8")
    html = panel.render("paper", "t" * 40, AT)
    assert "data-act='adj'" in html and "data-px='1000'" in html and "最多加到总权益（钱不够从持仓平摊凑）" in html and "调仓…</button>" in html
    assert "一次最少 100 股" in html and "id='adj-bar'" in html and "id='adj-lab'" in html     # 调仓条按单元分格
    assert "data-t='6758.T' data-kind='stock'" in html and "data-t='1545.T' data-kind='core'" in html
    assert "现在没拿" in html and "data-t='1482.T' data-kind='core'" in html
    assert "data-act='tf'" not in html and "data-act='sub'" not in html                # 没有整页一排的切换：每张图自己的（脚本画）
    assert "kBar(box, 'ktop', 'ktf', TFS" in panel._JS and "kBar(box, 'kbot', 'ksub', SUBS" in panel._JS     # 上边沿 日K / 周K / 月K、下边沿 量 / MACD / DMI
    assert "</script><b>x" not in html and "对冲版美国国债&lt;/script&gt;" in html
    assert "日K <b class='up'>往上走</b> · 涨势整齐" in html and "周K <b class='muted'>横着走</b>" in html
    assert "月K <b class='down'>往下走</b> · 跌势整齐" in html and '"上升": "往上走"' in html     # 图下的说法也从 kline.py 来（CFG.kp）
    assert '"when": "今天 09:00 开盘"' in html and "addWhen" not in html
    assert "chart-data" not in html                                     # K 线数据不内嵌，打开时才取（/api/chart）
    assert "红色空心 = 涨" not in panel._JS and "红色空心 = 涨" in _card(html, "khelp")   # 说明整页一份（服务器画；2026-10-15）
    (paths.out_dir() / "charts_paper.json").unlink()
    html = panel.render("paper", "t" * 40, AT)                  # 还没有 K 线文件：占位文字、没有周期切换
    assert "K 线在执行器下一次运行之后显示" in html and "data-act='tf'" not in html and "data-act='sub'" not in html


SG_ROWS = [
    {"ticker": "6501.T", "code": "6501", "name": "日立", "sector": "電気機器", "status": "triggered", "status_text": "今天收盘出了买入信号",
     "signal": True, "score": 88.5, "close": 3500.0, "vol_ratio": 1.4, "range_pct": 9.1, "to_box_top_pct": -0.5, "breakout": True,
     "top_risk": "RSI72", "trend": TR, "rule": {"state": "blocked", "text": "信号成立但规则不买：个股名额已满（上限 4 只）"},
     "buy": {"block": None, "warn": [], "lot": 100, "px": 3500.0, "limit": 3605, "rule_shares": 200, "planned": False}},
    {"ticker": "8035.T", "code": "8035", "name": "東京エレクトロン", "status": "imminent", "status_text": "即将触发", "signal": False,
     "score": 70.0, "close": 30000.0, "rule": {"state": "none", "text": "还没触发买入信号：规则不会买"},
     "buy": {"block": "JPX 市場区分「プロ」：不买", "warn": [], "lot": 100, "px": 30000.0, "rule_shares": 0}},
    {"ticker": "9984.T", "code": "9984", "name": "ソフトバンクG", "status": "watch", "status_text": "观察中", "signal": False,
     "score": 50.0, "close": 9000.0, "rule": {"state": "none", "text": "还没触发买入信号：规则不会买"},
     "buy": {"block": None, "warn": ["规则现在不开这只的新仓（新仓倍数 0）：执行器会挡"], "lot": 100, "px": 9000.0, "limit": 9270,
             "rule_shares": 0}},
]


def _card(html: str, cid: str) -> str:
    """页面里 id = cid 的那张卡片（<section class='card' id='…'> 到它的 </section>）。"""
    i = html.index(f"<section class='card' id='{cid}'>")
    return html[i:html.index("</section>", i) + len("</section>")]


def _sm(rows=None):
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps(
        {"suggest": {"asof": "2026-10-05", "rows": SG_ROWS if rows is None else rows}}, ensure_ascii=False), encoding="utf-8")


def _sm_nowarn():
    """同 _sm()，但 9984 没有「执行器会挡」的警告（从持仓凑钱买会被拒的那种；2026-10-13）。"""
    _sm([dict(r, buy={**r["buy"], "warn": []}) for r in SG_ROWS])


def test_render_suggestions_with_buy_buttons_and_gates():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    _sm()
    html = panel.render("paper", "t" * 40, AT)
    sgc, ab = _card(html, "suggest"), _card(html, "autobuy")
    # 出了信号的 6501 在上面「规则接下来会自动买」里（2026-10-15 起建议的股票不重复列）：只数 = 这里列的
    assert "建议的股票（规则的候选，2 只）" in sgc and "上面「规则接下来会自动买」已列的 1 只不在这里重复" in sgc
    assert "个股名额：空 3 个（拿着 1 + 排定买入 0，上限 4 只）" in sgc
    assert "<b>6501</b>" not in sgc and "今天出了买入信号" not in sgc            # 空了的组（与它的分段按钮）不出现
    assert "<h3 class='sgh'>快要出买入信号（1 只）</h3>" in sgc and "<h3 class='sgh'>观察中（1 只）</h3>" in sgc
    assert sgc.count("data-act='buy'") == 1                                 # 8035 被硬闸门挡：没有按钮
    assert "data-t='6501.T'" in ab and "data-sig='1'" in ab and "data-rule='200'" in ab and "data-limit='3605'" in ab
    assert "不能买：JPX 市場区分「プロ」：不买" in sgc and "顶部风险：RSI72" in ab
    assert "★ 规则现在不开这只的新仓（新仓倍数 0）：执行器会挡" in sgc and "真突破" in ab
    assert sgc.count("<details class='kl' open>") == 1 and "<details class='kl'><summary>" in sgc     # 观察中的 K 线默认收起
    assert "按规则约 200 股 · 约 ¥700,000 · 约占权益 70.0%" in ab
    full = {t: {"shares": 100, "entry_px": 1000.0, "entry_date": "2026-09-01", "stop_px": 900.0, "last_close": 1000.0}
            for t in ("7203.T", "6758.T", "6861.T", "6098.T")}
    _book(pos=full, manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    html = panel.render("paper", "t" * 40, AT)
    assert "data-act='buy'" in html and "data-full='1'" in html and ">全部换成这只…<" in html     # 2026-10-13：名额满也给按钮，只能「其他全部卖出」
    assert "个股名额已满（4 / 4 只）：只能把其他持仓全部卖出来换这只" in html
    _sm([])
    assert "今天没有出信号 / 快要出信号 / 观察中的票" in panel.render("paper", "t" * 40, AT)


def test_render_watch_rows_show_how_far_from_a_buy_signal():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    rows = [dict(r) for r in SG_ROWS]
    rows[2]["near"] = {"where": "below_up", "days": 8, "miss": [], "vol": 0.8}   # 8 天：不在「规则接下来会自动买」（5 天以内）里
    rows[2]["near_text"] = "离买入信号：MACD 约 8 天后金叉（按最近一天的变化估）；金叉那天量要 > 1.5 倍（今天 0.8 倍）"
    _sm(rows)
    html = panel.render("paper", "t" * 40, AT)
    assert ("<div class='small near'>离买入信号：MACD 约 8 天后金叉（按最近一天的变化估）；金叉那天量要 &gt; 1.5 倍（今天 0.8 倍）</div>"
            in _card(html, "suggest")) and "9984" not in _card(html, "autobuy")
    assert html.count("按离 MACD 金叉的天数排（越上面越快金叉；只是估算）") == 1   # 只有带 near 的组（旧的汇总没有 → 不写）


def test_render_ranks_watch_rows_by_the_registered_probability(monkeypatch, tmp_path):
    """有比例表（研究判定 A）：快要出 + 观察中合成一组，按 闸门 → 历史比例 → near_key 排，每只写第几 + 历史比例（旧汇总也在渲染时补）。"""
    from qbreak import watch_prob as WP
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    rows = [dict(r) for r in SG_ROWS]
    rows[1] = {**rows[1], "buy": {**rows[1]["buy"], "block": None, "limit": 30900}, "macd_gap_pct": -0.05, "vol_ratio": 1.2,
               "near": {"where": "below_up", "days": 1, "miss": ["周线量比（0.8，要 ≥ 1）"], "vol": 1.2}}
    rows[2] = {**rows[2], "buy": {**rows[2]["buy"], "warn": []}, "macd_gap_pct": -0.3, "vol_ratio": 0.8,
               "near": {"where": "below_down", "days": None, "miss": [], "vol": 0.8}}
    extra = {"ticker": "6758.T", "code": "6758", "name": "ソニーG", "status": "watch", "signal": False, "score": 40.0, "close": 3000.0,
             "rule": {"state": "none", "text": ""}, "macd_gap_pct": 0.5, "vol_ratio": 0.5,
             "near": {"where": "above", "days": None, "miss": [], "vol": 0.5},
             "buy": {"block": None, "warn": [], "lot": 100, "px": 3000.0, "limit": 3090, "rule_shares": 100}}
    _sm(rows + [extra])
    t = WP.fit([("down_far", "m0", "v_lo", int(k < 9)) for k in range(100)] + [("up_d1", "m1", "v_hi", int(k < 4)) for k in range(100)]
               + [("above_far", "m0", "v_lo", 0) for _ in range(300)], extra={"show_pct": True})
    fp = tmp_path / "wp.json"
    fp.write_text(json.dumps(t), encoding="utf-8")
    monkeypatch.setattr(WP, "FILE", fp)
    html = panel.render("paper", "t" * 40, AT)
    sgc, ab = _card(html, "suggest"), _card(html, "autobuy")
    # 6501（出了信号）与 8035（约 1 天金叉）在上面「规则接下来会自动买」里，建议的股票不重复列（2026-10-15）
    assert "今天出了买入信号" not in sgc and "data-sgg" not in sgc            # 只剩一组：没有分段按钮
    assert "<h3 class='sgh'>观察中 · 2 只（按离 MACD 金叉的天数排）</h3>" in sgc and "快要出买入信号（1 只）" not in html
    i1, i2, i3 = html.index("<b>9984</b>"), html.index("<b>8035</b>"), html.index("<b>6758</b>")
    assert i2 < i1 < i3                                                    # 2026-10-11 起按离金叉：8035（约 1 天）→ 9984（往下走）→ 6758（已在线上）
    assert "<b>8035</b>" not in sgc and "<b>8035</b>" in ab
    assert "<span class='rk'>1</span><b>9984</b>" in sgc and "<span class='rk'>2</span><b>6758</b>" in sgc   # 名次按这里列的从 1 数（不跳号）
    assert "<span class='rk'" not in ab                                     # 自动买那张卡不带名次徽章
    assert "金叉约 1 天" in ab and "要先拐头" in sgc and "已在线上" in sgc
    assert "<span class='chip hot'>快要出</span>" in ab                       # 快要出的照样标出来（在自动买那张卡点开的一行里）
    p1 = WP.prob(t, "down_far", "m0", "v_lo")
    assert f"之后 10 个交易日内出买入信号：历史上约 <b>{p1['p'] * 100:.1f}%</b>（同样情况 100 次）" in html
    assert "越上面越快出现金叉（按最近一天的变化估算的天数" in html
    monkeypatch.setattr(WP, "FILE", tmp_path / "wp2.json")                 # 研究判定 B（只排序）：不写百分比
    (tmp_path / "wp2.json").write_text(json.dumps({**t, "show_pct": False}), encoding="utf-8")
    html = panel.render("paper", "t" * 40, AT)
    assert "历史上约" not in html and "按之后 10 个交易日内出买入信号的历史比例排" in html


def test_submit_buy_writes_instruction_and_checks():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}, "core": ["1545.T"]})
    _sm()
    ok, msg, rec = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501"}, AT)
    assert ok and rec["unit"] == "rule" and "已写：买入 6501.T（约 200 股）→ 今天 09:00 开盘买入" in msg
    assert "没有买入信号" not in msg
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "6501"}, AT)
    assert not ok and "没处理完" in msg
    ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": "8035"}, AT)
    assert not ok and "不能买：JPX" in msg
    for t, why in (("7203", "已经持有"), ("1545", "核心 ETF")):
        ok, msg, _ = panel.submit({"book": "paper", "kind": "buy", "ticker": t}, AT)
        assert not ok and why in msg
    ok, msg, rec = panel.submit({"book": "paper", "kind": "buy", "ticker": "9984", "unit": "shares", "value": 300}, AT)
    assert ok and rec["value"] == 300 and "买入 9984.T（300 股）" in msg and "没有买入信号" in msg
    html = panel.render("paper", "t" * 40, AT)
    assert html.count("data-act='cancel'") == 2 and "有一条买入指令在处理（见「手动指令」）" in _card(html, "suggest")


def test_chart_endpoint_serves_one_ticker(server):
    port, tok = server
    _book()
    big = {"kind": "stock", "tf": {"D": {"d": ["2026-10-05"] * 300, "c": [1.0] * 300}}}
    _kfile({"7203.T": big})
    code, body, hd = _req(port, "GET", "/api/chart?book=paper&t=7203.T")
    j = json.loads(body)
    assert code == 200 and j["ok"] and j["t"] == "7203.T" and j["data"]["kind"] == "stock" and j["asof"] == "2026-10-05"
    assert "Content-Encoding" not in hd and hd.get("Cache-Control") == "no-store"
    import gzip
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", "/api/chart?book=paper&t=7203.T", headers={"Host": f"127.0.0.1:{port}", "Accept-Encoding": "gzip"})
    r = c.getresponse()
    raw = r.read()
    assert r.getheader("Content-Encoding") == "gzip" and json.loads(gzip.decompress(raw))["data"] == big
    c.close()
    assert _req(port, "GET", "/api/chart?book=paper&t=9999.T")[0] == 404
    assert _req(port, "GET", "/api/chart?book=paper&t=../x")[0] == 400
    assert _req(port, "GET", "/api/chart?book=paper&t=7203.T", headers={"Host": "evil.example:80"})[0] == 421


def test_page_script_is_valid_javascript(tmp_path):
    """页面的脚本（qbreak/static/*.js，浏览器原生 ES 模块）每个都能按模块语法解析；页面只引用 main.js、配置是能解析的 JSON；
    每个 import 的名字对方模块都 export 了。没有 node 就跳过语法检查。"""
    import re
    import shutil
    import subprocess
    _book()
    for mode in ("local", "remote"):
        html = panel.render("paper", "t" * 40, AT, mode=mode, device={"name": "x"}, phone={"port": 8766, "url": None, "devices": []})
        assert html.count("<script>") == 1 and f"<script>{panel.BOOT_JS}</script>" in html     # 只有 boot.js 内联（CSP 用它的 sha256 放行）
        assert f"'{panel.BOOT_SHA}'" in panel.CSP and "'unsafe-inline'" not in panel.CSP.split("script-src")[1].split(";")[0]
        assert f"<script type='module' src='/static/main.js?v={panel.ASSET_V}'></script>" in html
        cfg = json.loads(html.split("<script type='application/json' id='qb-cfg'>")[1].split("</script>")[0])
        assert cfg["book"] == "paper" and "auth" in cfg
    files = {f.name: f.read_text(encoding="utf-8") for f in panel.STATIC_DIR.glob("*.js")}
    exports = {n: set(re.findall(r"^export (?:async )?(?:function|const|let) ([A-Za-z_$][\w$]*)", s, re.M))
               | set(re.findall(r"^export (?:const|let) [^;]*?,\s*([A-Za-z_$][\w$]*)\s*=", s, re.M)) for n, s in files.items()}
    for n, s in files.items():
        for names, mod in re.findall(r"^import \{([^}]*)\} from '\./([\w]+\.js)';", s, re.M):
            for x in (y.strip() for y in names.split(",")):
                assert mod in files and x in exports[mod], (n, x, mod)
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    for n, s in files.items():
        f = tmp_path / (n[:-3] + ".mjs")
        f.write_text(s, encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, (n, r.stderr[-500:])


def _js_fn(src: str, name: str) -> str:
    """从页面脚本里取出一个顶层函数的全文（按大括号配对；这些函数的字符串里没有大括号）。"""
    i = src.index(f"function {name}(")
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        depth += {"{": 1, "}": -1}.get(src[k], 0)
        if depth == 0:
            return src[i:k + 1]
    raise ValueError(name)


def test_kline_plain_text_and_lot_bar_in_node(tmp_path):
    """页面脚本里的通俗说明（小图「这一根」、现在的趋势、趋势线）与调仓条（按 100 股分格）在 node 里实际跑（假的最小 DOM）。没有 node 就跳过。"""
    import shutil
    import subprocess
    from qbreak import kline as KL
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    J = panel._JS
    fns = "\n".join(_js_fn(J, n) for n in ("nd", "pxs", "pcs", "vfmt", "sdate", "isLive", "liveAt", "kSubNow", "kTrend", "kTL", "ALOT", "UW",
                                            "capLab", "adjCap", "adjBar"))
    kp = json.dumps({"label": KL.PLAIN, "align": KL.ALIGN_PLAIN, "chan": KL.CHAN_PLAIN}, ensure_ascii=False)
    js = """
class El { constructor(t){ this.tagName=String(t).toUpperCase(); this.children=[]; this._t=''; this.className=''; this.style={}; this.attrs={};
  const s=this; this.classList={add(c){ s.className=(s.className ? s.className+' ' : '')+c; }}; }
  appendChild(c){ this.children.push(c); return c; }
  set textContent(v){ this._t=String(v); this.children=[]; } get textContent(){ return this._t+this.children.map(c=>c.textContent).join(''); }
  setAttribute(k,v){ this.attrs[k]=String(v); } }
const document={createElement:t=>new El(t), createTextNode:t=>{ const e=new El('#text'); e._t=String(t); return e; }};
const CFG={eq:5000000, cap:34, kp:__KP__}, KPL=CFG.kp, LOT=100, KU={D:'天', W:'周', M:'个月'}, KMA={D:'日', W:'周', M:'个月'};
const fmt=n=>Number(n).toLocaleString('ja-JP');
const R={max:'800', value:'600', attrs:{}, setAttribute(k,v){ this.attrs[k]=String(v); }};
const ELS={'#adj-range':R, '#adj-bar':new El('div'), '#adj-lab':new El('div'), '#adj-note':new El('div')};
const $=s=>ELS[s];
let ADJ=null;
__FNS__
const out={};
const bar=(shares, px, value)=>{ ADJ={shares:shares, px:px}; R.max=String(Math.max(1, Math.ceil(Math.max(adjCap(), shares, LOT)/LOT))*LOT); R.value=String(value);
  adjBar(); return {cls:ELS['#adj-bar'].children.map(i=>i.className||'_'), lab:ELS['#adj-lab'].children.map(s=>s.textContent),
                    note:ELS['#adj-note'].textContent, vt:R.attrs['aria-valuetext'], max:R.max}; };
out.add=bar(600, 1931, 800); out.cut=bar(600, 1931, 0); out.keep=bar(600, 1931, 600); out.over=bar(1000, 1931, 800);
out.many=bar(200, 10, 200); out.none=bar(100, 5000000, 100);
const t=(f)=>{ const e=new El('div'); f(e); return e.textContent; };
const DM={d:['2026-09-29','2026-09-30','2026-10-01'], dif:[-0.5,-0.2,0.3], dea:[0.1,0.0,0.1], mh:[-0.6,-0.2,0.2],
          pdi:[20,30,31], mdi:[25,12,11], adx:[26,28,27], v:[100,100,100]};
out.macd_last=t(e=>kSubNow(e, DM, 2, {kind:'stock'}, 'D', 'macd')); out.macd_mid=t(e=>kSubNow(e, DM, 1, {kind:'stock'}, 'D', 'macd'));
out.dmi=t(e=>kSubNow(e, DM, 1, {kind:'stock'}, 'D', 'dmi'));
const DV={d:Array.from({length:21}, (_, i)=>'2026-09-'+String(i+1).padStart(2,'0')), v:Array(20).fill(100).concat([250])};
out.vol=t(e=>kSubNow(e, DV, 20, {kind:'stock'}, 'D', 'v')); out.vol_w=t(e=>kSubNow(e, DV, 20, {kind:'core'}, 'W', 'v'));
out.trend_w=t(e=>kTrend(e, {label:'上升', align:'多头排列', above20:true, slope20_pct:0.52}, 'W'));
out.trend_flat=t(e=>kTrend(e, {label:'震荡', align:'', above20:false, slope20_pct:0}, 'D'));
out.tl=t(e=>kTL(e, {sup:{now:950, dist_pct:-5, slope_pct:0.12, touch:3}, res:{now:1100, dist_pct:10, slope_pct:0.01, touch:2},
                    chan:'对称三角', pos:33, eps:0.02}, 'D'));
out.tl_broken=t(e=>kTL(e, {sup:{now:1020, dist_pct:2, slope_pct:-0.5, touch:2}, res:{now:990, dist_pct:-1, slope_pct:0.3, touch:4},
                           chan:'扩散', pos:120, eps:0.4}, 'M'));
out.tl_one=t(e=>kTL(e, {res:{now:1100, dist_pct:10, slope_pct:0.2, touch:2}, eps:0.02}, 'W'));
console.log(JSON.stringify(out));
""".replace("__KP__", kp).replace("__FNS__", fns)
    f = tmp_path / "k.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([node, str(f)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-800:]
    o = json.loads(r.stdout)
    # 调仓条：一格 = 1 个单元（100 股）；留着的 / 要加的 / 要卖的 / 空着的
    assert o["add"]["cls"] == ["keep"] * 6 + ["add"] * 2 and o["add"]["max"] == "800"            # 单只上限 34% ≈ 800 股
    assert o["cut"]["cls"] == ["cut"] * 6 + ["_"] * 2 and o["keep"]["cls"] == ["keep"] * 6 + ["_"] * 2
    assert o["add"]["lab"][:3] == ["0", "100", "200"] and any("现在" in x for x in o["add"]["lab"])
    assert o["add"]["note"] == "一格 = 100 股 · 半透明 留着 · 实心 要加 · 红框 要卖 · 斜线 超过上限 · 最右边 = 单只上限 34%"
    assert o["add"]["vt"] == "目标 800 股（8 个单元）；现在 600 股"
    assert o["over"]["cls"] == ["keep"] * 8 + ["cut"] * 2 and "单只上限 34% ≈ 800 股（现在已超过，只能减）" in o["over"]["note"]  # 已经超过上限：只能减
    assert len(o["many"]["cls"]) == 50 and o["many"]["cls"][0] == "keep" and "一格 = 3,400 股（拖动按 100 股一步）" in o["many"]["note"]
    assert o["many"]["lab"][:2] == ["0", "170,000 股"] and "▲现在 200" in o["many"]["lab"]
    assert o["none"]["cls"] == ["keep"] and o["none"]["max"] == "100"                              # 1 个单元都超过上限
    # 小图「这一根」：金叉 / 死叉 / 变强变弱 / 0 线；DMI；量比（一句话）
    assert o["macd_last"] == "最新一根：金叉（快线刚往上穿过慢线）；在 0 线上面（偏涨）"
    assert o["macd_mid"] == "09/30：快线在慢线下面（跌的力量强），在变弱；在 0 线下面（偏跌）"
    assert o["dmi"] == "09/30：买方强；ADX 28.0（趋势明显），在变强"
    assert o["vol"] == "最新一根：成交 250 股，是前 20 天平均的 2.50 倍" and o["vol_w"] == "最新一根：成交 250 口，是前 20 周平均的 2.50 倍"
    # 现在的趋势（kline.py 的说法）
    assert o["trend_w"] == "现在的趋势：往上走（收盘在 20 周均价上面，20 周均价往上） · 涨势整齐"
    assert o["trend_flat"] == "现在的趋势：横着走（收盘在 20 日均价下面，20 日均价走平）"
    # 趋势线：一行（通道的说法 · 支撑 / 压力 离收盘多远，跌破 / 冲过）
    assert o["tl"] == "趋势线：下面的线往上、上面的线往下：越收越窄，快要选方向 · 支撑 ¥950.0（比收盘低 5%） · 压力 ¥1,100（比收盘高 10%）"
    assert o["tl_broken"] == "趋势线：两条线越张越开：上下波动越来越大 · 支撑 ¥1,020（已跌破） · 压力 ¥990.0（已冲过）"
    assert o["tl_one"] == "趋势线：只找到上面的一条 · 压力 ¥1,100（比收盘高 10%）"
    assert "没有预测力" not in J and "没有预测力" in panel._kline_help()     # 研究结论在整页一份的「怎么看 K 线图」里说一次（2026-10-15）


def _pane(html: str, tab: str) -> str:
    """一个标签页的全部内容（同一个标签可以有几段：按顺序拼起来）。"""
    out, k = [], 0
    while True:
        i = html.find(f"<div class='pane' data-tab='{tab}'>", k)
        if i < 0:
            return "".join(out)
        j = html.find("<div class='pane' data-tab=", i + 1)
        j = html.find("</main>", i) if j < 0 else j
        out.append(html[i:j])
        k = j


def test_one_kline_help_for_the_whole_page_and_no_number_table():
    """2026-10-15 用户：「去掉每个股票中的如何看这张图 整体留一个解释就行」「不需要最近十个月的数字的数据 看图就行」：
    整页只有一份收起的「怎么看 K 线图」（服务器画）；每张图不再画说明与数字表。同日用户「选股中的怎么看K线图要放到持仓中的K线的上面」：
    这一份在「持仓」的 K 线上面（持仓卡片之前），选股最上面只留一行「去看 ›」跳过去（app.js data-khelpgo）。"""
    _book(pos={"6758.T": {"shares": 200, "entry_px": 900.0, "entry_date": "2026-09-01", "stop_px": 850.0, "last_close": 1000.0}},
          manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    _sm()
    for mode in ("local", "remote"):
        html = panel.render("paper", "t" * 40, AT, mode=mode, device={"name": "x"}, phone={"port": 8766, "url": None, "devices": []})
        assert html.count("id='khelp'") == 1 and html.count("<summary>怎么看 K 线图</summary>") == 1
        assert "怎么看这张图" not in html and "的数字（表）" not in html
        hp = _card(html, "khelp")
        assert hp.startswith("<section class='card' id='khelp'><details class='khelp'><summary>怎么看 K 线图</summary><ul>")   # 默认收起
        hold, pick = _pane(html, "hold"), _pane(html, "pick")
        assert "id='khelp'" in hold and "id='khelp'" not in pick
        assert hold.index("id='khelp'") < hold.index("id='holdings'") < hold.index("data-t='6758.T' data-kind='stock'")   # 持仓的 K 线上面
        assert "data-kind=" not in hold[:hold.index("id='khelp'")]                     # 上面没有别的 K 线
        assert pick.count("怎么看 K 线图") == 1 and "data-khelpgo='1'" in pick and "<details" not in pick[:pick.index("data-khelpgo")]   # 选股：只一行指过去
        assert pick.index("data-khelpgo") < pick.index("id='autobuy'") < pick.index("id='suggest'")
        for x in ("红色空心 = 涨", "绿色实心 = 跌", "<i class='key m5'></i>5", "<i class='key m30'></i>30 日（周 / 个月）均价",
                  "▲买入 = 买入那一根", "▲信号 = 出买入信号那一根", "<i class='key dash stop'></i>止损线", "<i class='key dash tl'></i>趋势线",
                  "研究（2026-10-06）：对之后的涨跌没有预测力", "金叉，是规则买入的条件之一", "DMI = 买卖哪边强、趋势强不强（规则不用）",
                  "← →", "Home / End", "Esc", "图上都是过去的价格，不是预测"):
            assert x in hp, x
    J = (panel.STATIC_DIR / "kline.js").read_text(encoding="utf-8")
    for x in ("kHelp", "khelp", "怎么看这张图", "的数字（表）", "'table'", "'thead'", "'tbody'", "dataset.tbl", "dataset.help"):
        assert x not in J, x                                                # 每张图的说明 / 数字表（与它们的状态）都去掉
    assert "kTrend(nd('div','kexp',null,box), tr, tf)" in J and "kTL(nd('div','kexp',null,box), TL, tf)" in J   # 图下各自的一句话照旧
    assert "kSubKey(nd('div','kexp',null,box), P, tf, sub)" in J and "kSubNow(sn, D, N-1, P, tf, sub)" in J
    css = (panel.STATIC_DIR / "panel.css").read_text(encoding="utf-8")
    assert ".chart table" not in css and ".chart td" not in css and ".abxb .rk" not in css and ".kexp ul" not in css
    assert "details.khelp>summary" in css and ".khgo a{" in css
    A = (panel.STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "closest('[data-khelpgo]')" in A and "showTab('hold', true); d.open=true;" in A


def test_kline_help_stays_in_hold_pane_without_holdings():
    """没有持仓（也没有核心 ETF）：说明照样在「持仓」那个位置（持仓卡片之前），整页一份。"""
    _book(pos={}, manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    b = json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8"))
    b["state"]["core_units"] = {}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(b), encoding="utf-8")
    _sm()
    html = panel.render("paper", "t" * 40, AT)
    hold = _pane(html, "hold")
    assert html.count("id='khelp'") == 1 and hold.index("id='khelp'") < hold.index("id='holdings'")


def test_trade_badge_counts_what_the_trade_tab_shows():
    """「交易」标签的数字 = 卡片上还会做事的行：撤销撤回本身、被撤销的撤回不算（2026-10-15 用户：只有一条却标 3）；
    同日用户「撤单后 / 没有执行下单等等的话交易处的数字不显示」：撤回还没读 → 被撤回的那条与撤回本身都不算（以前算 2）。"""
    fix = {"id": "M1-corefix", "kind": "corefix", "ticker": "1482.T", "at": "2026-10-14T19:21:18+09:00"}
    can = {"id": "M2-cancel", "kind": "cancel", "target": "M1-corefix", "at": "2026-10-14T23:08:22+09:00"}
    unc = {"id": "M3-uncancel", "kind": "uncancel", "target": "M2-cancel", "at": "2026-10-14T23:32:14+09:00"}
    st = {"last_date": "2026-10-13", "pos": {}, "core_units": {}}
    book = {"state": st, "orders": []}
    assert panel._badges(book, st, {}, [fix, can, unc], AT).get("trade") == 1     # 固定口数 → 撤回 → 撤销撤回：只剩固定口数一条
    assert "trade" not in panel._badges(book, st, {}, [fix, can], AT)             # 撤回还没读：固定口数（撤回中）不会做事、撤回本身不算
    assert panel._trade_live(book, [fix, can], AT)["busy"] == 0                   # 都还没读的「指令 + 它的撤回」：没有要等的（2026-10-15 复核：
                                                                                    # 以前算 2 → 页面一直每 10 秒问、执行器读的时候整页刷新）
    assert "trade" not in panel._badges(book, st, {}, [], AT)
    book["manual"] = {"items": {"M1-corefix": {**fix, "status": "pending"}}}      # 执行器读了固定口数、撤回还没读
    assert "trade" not in panel._badges(book, st, {}, [can], AT)
    assert panel._trade_live(book, [can], AT)["busy"] == 1                        # 撤回指着执行器读过的指令：等它读撤回（页面照样问）
    assert panel._badges(book, st, {}, [], AT).get("trade") == 1
    book["manual"]["items"]["M1-corefix"]["cancel_req"] = "撤回"                    # 执行器读了撤回（撤回中）
    assert "trade" not in panel._badges(book, st, {}, [], AT)
    assert panel._trade_live(book, [], AT)["busy"] == 1                           # 撤回中：还在处理
    book["manual"]["items"]["M1-corefix"]["status"] = "cancelled"                 # 撤回完了：什么都不用等
    assert panel._trade_live(book, [], AT)["busy"] == 0


AT15 = dt.datetime(2026, 10, 15, 8, 15, tzinfo=JST)                              # 2026-10-15（四）08:15：成交日 = 今天


def _book1015(tag="paper", sell="CANCELLED", buy="DEFERRED", cash=192.0, items=None, fix=None, sell_cid="U2026-10-14-SELL-1545.T"):
    """2026-10-15 早上的真实状态（模拟账户）：你撤了 1545.T 的卖单（凑钱的），1482.T 的买单 678 口还在「等开盘后」，现金只有 192 円，
    固定口数 1482.T 678 口还有效。"""
    orders = [{"cid": sell_cid, "ticker": "1545.T", "side": "SELL", "kind": "core", "qty": 4110, "decided_on": "2026-10-14",
               "limit": None, "ref_px": 243.7, "phase": "morning", "status": sell, "sent_qty": 4110, "filled_qty": 0,
               "note": "你撤了单（08:05，面板的撤单指令）" if sell == "CANCELLED" else "已排队，次日开盘成交"},
              {"cid": "U2026-10-14-BUY-1482.T", "ticker": "1482.T", "side": "BUY", "kind": "core", "qty": 678, "decided_on": "2026-10-14",
               "limit": 1503.0, "ref_px": 1474.0, "phase": "open", "status": buy, "sent_qty": 0, "filled_qty": 0,
               "note": "开盘前余力 192 円 < 按限价预留 1,019,441 円 → 开盘后按始値检查、减股再下"}]
    st = {"last_date": "2026-10-14", "cash_jpy": cash, "history": [["2026-10-14", 1_001_799.0, cash, 0, 150]], "pos": {},
          "pending_exit": {}, "core_units": {"1545.T": 4110, "1482.T": 0}}
    b = {"state": st, "orders": orders, "core_rule": {"lot": {"1482.T": 1, "1545.T": 10}},
         "manual": {"items": items or {}, "core_fix": {"1482.T": 678} if fix is None else fix, "core_pct": 100.0}}
    (paths.state_dir() / f"live_unified_{tag}.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    return b


def _tabbtn(html: str, k: str) -> str:
    i = html.index(f"data-tabgo='{k}'")
    return html[i:html.index("</button>", i)]


def test_trade_badge_gone_when_funding_sell_cancelled_and_buy_cannot_be_paid():
    """2026-10-15 用户「撤单后 / 没有执行下单等等的话交易处的数字不显示」（真实状态）：凑钱的 1545.T 卖单撤了、现金 192 円 →
    1482.T 的 DEFERRED 买单开盘时连 1 口（跌停价约 1,174 円）都买不起 → 不算、写「不会下单（预计）」+ 原因；固定口数还在 → 提醒明天还会再排。"""
    from qbreak import live_ops as LO
    b = _book1015()
    assert set(LO.unfunded_buys(b)) == {"U2026-10-14-BUY-1482.T"}
    x = LO.unfunded_buys(b)["U2026-10-14-BUY-1482.T"]
    assert x["need"] == 1474.0 - 300 and x["lot"] == 1 and x["sells"] == 0 and [g["ticker"] for g in x["gone"]] == ["1545.T"]
    assert "trade" not in panel._badges(b, b["state"], {}, [], AT15, "paper")
    lv = panel._trade_live(b, [], AT15, "paper", halt=False)
    chip, why = lv["orders"]["U2026-10-14-BUY-1482.T"]
    assert chip == "不会下单（预计）" and "资金来源的卖单已撤（卖 1545.T 4,110 口）" in why and "¥192" in why and "¥1,174" in why
    assert "手动固定 678 口仍然有效" in lv["fix"]["U2026-10-14-BUY-1482.T"] and "10/16 07:40" in lv["fix"]["U2026-10-14-BUY-1482.T"]
    assert "「其他闲置资金 ETF（现在没拿）」里 1482.T 下面点「恢复按规则」" in lv["fix"]["U2026-10-14-BUY-1482.T"]
    html = panel.render("paper", "t" * 40, AT15)
    assert "class='badge'" not in _tabbtn(html, "trade")
    card = _card(html, "today")
    assert "<span class='chip'>不会下单（预计）</span>" in card and "资金来源的卖单已撤" in card and "手动固定 678 口仍然有效" in card
    assert "<span class='chip'>已撤单</span>" in card
    assert panel.status_json("paper")[1]["pending"] == 0
    b = _book1015(fix={})                                                     # 没有固定口数：不写那条提醒
    assert not panel._trade_live(b, [], AT15, "paper", halt=False)["fix"]


def test_trade_badge_keeps_fundable_deferred_buy_and_cancel_confirm_lists_it():
    """凑钱的卖单还在（模拟账户排队中）→ 1482.T 的 DEFERRED 买单开盘后能下 → 照算（卖 + 买 = 2）；
    卖单的「撤单」确认框写明撤了之后这笔买单下不成（data-deps）。"""
    b = _book1015(sell="SENT")
    assert panel._badges(b, b["state"], {}, [], AT15, "paper").get("trade") == 2
    assert not panel._trade_live(b, [], AT15, "paper", halt=False)["orders"]
    html = panel.render("paper", "t" * 40, AT15)
    assert "<i class='badge'>2</i>" in _tabbtn(html, "trade")
    card = _card(html, "today")
    assert "不会下单" not in card and "data-act='cancel-order' data-cid='U2026-10-14-SELL-1545.T'" in card
    assert "data-deps='撤掉之后，今天等这笔卖出的钱的买单预计下不成（开盘时现金不够一单元）：买 1482.T 678 口" in card
    J = (panel.STATIC_DIR / "trade.js").read_text(encoding="utf-8")
    assert "+(d.deps ? '\\n★ '+d.deps : '')" in J
    b = _book1015(sell="SENT", cash=2_000_000.0)                             # 现金本来就够：撤卖单也不影响买单 → 不写
    assert "data-deps" not in _card(panel.render("paper", "t" * 40, AT15), "today")
    st = panel.status_json("paper")[1]
    assert st["pending"] == 2 and st["busy"] == 0


def test_trade_badge_skips_orders_with_cancel_pending():
    """撤单指令还没处理（指令文件里还没读 / 账本里 pending）：那笔单「撤单中」不算；它是凑钱的卖单 → 买单也下不成、不算；撤单指令本身不算。"""
    b = _book1015(sell="SENT")
    co = {"id": "M3-cancel_order", "kind": "cancel_order", "cid": "U2026-10-14-SELL-1545.T", "ticker": "1545.T",
          "at": "2026-10-15T08:05:16+09:00"}
    assert "trade" not in panel._badges(b, b["state"], {}, [co], AT15, "paper")
    lv = panel._trade_live(b, [co], AT15, "paper", halt=False)
    assert lv["asked"] == {"U2026-10-14-SELL-1545.T"} and lv["busy"] == 1
    assert "资金来源的卖单已撤（卖 1545.T 4,110 口）" in lv["orders"]["U2026-10-14-BUY-1482.T"][1]
    b = _book1015(sell="SENT", items={"M3-cancel_order": {**co, "status": "pending"}})
    assert "trade" not in panel._badges(b, b["state"], {}, [], AT15, "paper")
    card = _card(panel.render("paper", "t" * 40, AT15), "today")
    assert "<span class='chip'>撤单中</span>" in card and "<span class='chip'>不会下单（预计）</span>" in card
    mb = _book1015(sell="SENT", items={"M3-cancel_order": {**co, "status": "pending"},           # 手动卖出的单在撤单中：指令也不算、写出来
                                       "M4-sell": {"id": "M4-sell", "kind": "sell", "ticker": "1545.T", "status": "placed",
                                                   "at": "2026-10-14T20:00:00+09:00"}})
    mb["orders"][0]["reason"] = "manual"
    lv = panel._trade_live(mb, [], AT15, "paper", halt=False)
    assert lv["n"] == 0 and lv["itxt"] == {"M4-sell": "（单在撤单中）"}


def test_trade_badge_under_halt():
    """HALT（立花）：还没发出的单（PLANNED / DEFERRED）不发 → 不算、写「不会下单（HALT）」；已经在交易所的（SENT）照算；
    手动指令照算（解除后照原样执行）。模拟账户的 DEFERRED 下一次运行照样撮合（_paper_open 不看 HALT）→ 照算。"""
    b = _book1015("tachibana", sell="SENT", cash=2_000_000.0,
                  items={"M5-sell": {"id": "M5-sell", "kind": "sell", "ticker": "7203.T", "status": "pending", "at": "2026-10-15T08:00:00+09:00"}})
    b["orders"].append({**b["orders"][1], "cid": "U2026-10-14-BUY-2845.T", "ticker": "2845.T", "status": "PLANNED", "ref_px": 3699.0})
    (paths.state_dir() / "live_unified_tachibana.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    assert panel._badges(b, b["state"], {}, [], AT15, "tachibana").get("trade") == 4   # 没有 HALT：卖 + 买 2 + 手动卖出
    paths.halt_file().write_text("测试", encoding="utf-8")
    try:
        assert panel._badges(b, b["state"], {}, [], AT15, "tachibana").get("trade") == 2   # 卖（在交易所）+ 手动卖出
        lv = panel._trade_live(b, [], AT15, "tachibana")
        assert lv["orders"]["U2026-10-14-BUY-1482.T"][0] == "不会下单（HALT）" and "09:05 / 09:20" in lv["orders"]["U2026-10-14-BUY-1482.T"][1]
        assert lv["orders"]["U2026-10-14-BUY-2845.T"][0] == "不会下单（HALT）"
        html = panel.render("tachibana", "t" * 40, AT15)
        assert "<i class='badge'>2</i>" in _tabbtn(html, "trade") and "不会下单（HALT）" in _card(html, "today")
        p = _book1015(sell="SENT", fix={})
        assert panel._badges(p, p["state"], {}, [], AT15, "paper").get("trade") == 2      # 模拟账户：DEFERRED 照算
    finally:
        paths.halt_file().unlink()


def test_trade_badge_tachibana_after_close():
    """立花：成交日 15:30 之后（成交日已过也一样）交易所那边什么都不会再发生 → 当前决策的单不算、写「已收盘」；模拟账户照算。"""
    b = _book1015("tachibana", sell="SENT", cash=2_000_000.0, fix={})
    late = AT15.replace(hour=16)
    assert panel._badges(b, b["state"], {}, [], AT15, "tachibana").get("trade") == 2
    assert "trade" not in panel._badges(b, b["state"], {}, [], late, "tachibana")
    lv = panel._trade_live(b, [], late, "tachibana", halt=False)
    assert lv["orders"]["U2026-10-14-SELL-1545.T"] == ("已收盘", "成交日 10/15 的交易所已经收盘：没成交的部分已失效，明早对账记账（之后什么都不会再发生）")
    assert "这笔没下" in lv["orders"]["U2026-10-14-BUY-1482.T"][1]
    assert "trade" not in panel._badges(b, b["state"], {}, [], AT15 + dt.timedelta(days=1), "tachibana")
    p = _book1015(sell="SENT", cash=2_000_000.0, fix={})
    assert panel._badges(p, p["state"], {}, [], late, "paper").get("trade") == 2


def test_trade_badge_skips_manual_orders_that_are_already_done():
    """2026-10-15 复核：手动卖出盘中成交了，指令还是「已下单」（明早对账才结束）→ 以前标签上一整天还是 1。现在单全部成交 → 指令不算、
    「手动指令」那一行写「已成交」；立花收盘后：手动买入的单失效了（只做一次）→ 不算，卖单没卖完的部分下一次开盘再卖 → 照算。"""
    items = {"M9-sell": {"id": "M9-sell", "kind": "sell", "ticker": "7203.T", "status": "placed", "at": "2026-10-15T09:30:00+09:00"},
             "M7-buy": {"id": "M7-buy", "kind": "buy", "ticker": "6758.T", "status": "placed", "at": "2026-10-15T09:31:00+09:00"}}
    def bk(sell_st, buy_st):
        o = {"decided_on": "2026-10-14", "phase": "now", "sent_at": "2026-10-15T09:30:05+09:00", "limit": 2500.0, "ref_px": 2500.0}
        st = {"last_date": "2026-10-14", "cash_jpy": 900_000.0, "pos": {"7203.T": {"shares": 100}}, "core_units": {}}
        return {"state": st, "manual": {"items": json.loads(json.dumps(items)), "buys": {"6758.T": {"id": "M7-buy"}}},
                "orders": [{**o, "cid": "N-SELL-7203.T", "ticker": "7203.T", "side": "SELL", "kind": "stock", "qty": 100, "reason": "manual",
                            "status": sell_st, "sent_qty": 100, "filled_qty": 100 if sell_st == "FILLED" else 0},
                           {**o, "cid": "N-BUY-6758.T", "ticker": "6758.T", "side": "BUY", "kind": "stock", "qty": 100, "reason": "manual_buy",
                            "status": buy_st, "sent_qty": 100, "filled_qty": 100 if buy_st == "FILLED" else 0}]}
    noon = AT15.replace(hour=11)
    lv = panel._trade_live(bk("FILLED", "FILLED"), [], noon, "paper", halt=False)
    assert lv["n"] == 0 and lv["busy"] == 0 and lv["items"] == {"M9-sell", "M7-buy"}
    assert lv["itxt"]["M9-sell"] == "（已成交：明早对账后这条指令结束）" == lv["itxt"]["M7-buy"]
    lv = panel._trade_live(bk("SENT", "UNFILLED"), [], noon, "paper", halt=False)
    assert lv["n"] == 2 and lv["itxt"] == {"M7-buy": "（单已失效：没成交的部分不会再买，明早对账后结束）"}   # 卖单还挂着：单 + 指令
    late = AT15.replace(hour=16)                                                # 立花 15:30 之后：两笔都「已收盘」
    lv = panel._trade_live(bk("SENT", "SENT"), [], late, "tachibana", halt=False)
    assert lv["orders"]["N-SELL-7203.T"][0] == lv["orders"]["N-BUY-6758.T"][0] == "已收盘"
    assert lv["n"] == 1 and "M9-sell" not in lv["items"] and "失效" in lv["itxt"]["M7-buy"]   # 卖出指令照算（明天开盘再卖），买入不算


def test_trade_badge_and_status_survive_unreadable_book_numbers(caplog, monkeypatch):
    """账本里有读不了的数（旧执行器写的 None 口数…）：「交易」的数字按以前的数法、/api/status 照样 200（2026-10-15 复核：以前 500 →
    页面的连接检查显示「连不上 Mac」）。"""
    b = _book1015(fix={"1482.T": None})
    w = [{"id": "M1-sell", "kind": "sell", "ticker": "7203.T", "at": "2026-10-15T08:00:00+09:00"}]
    with caplog.at_level(logging.WARNING, logger="qbreak"):
        lv = panel._trade_live(b, w, AT15, "paper", halt=False)
    assert lv["n"] == lv["busy"] == 1 and lv["orders"] == {} and "没算成" in caplog.text
    code, j = panel.status_json("paper")
    assert code == 200 and j["ok"] is True and "v" in j
    monkeypatch.setattr(panel, "_status_json", lambda tag: 1 / 0)
    code, j = panel.status_json("paper")
    assert code == 200 and j["ok"] is True and j["err"] == "ZeroDivisionError" and j["busy"] == 0 and j["v"] == panel.ASSET_V


def test_today_card_marks_the_old_note_of_a_buy_that_will_not_be_placed():
    """「不会下单（预计）」旁边执行器写的旧说明（「开盘后按始値检查、减股再下」）加上「原先：」（2026-10-15 复核：两句挨着像矛盾）。"""
    _book1015()
    card = _card(panel.render("paper", "t" * 40, AT15), "today")
    assert "<span class='chip'>不会下单（预计）</span>" in card and "原先：开盘前余力 192 円" in card
    _book1015(sell="SENT")
    card = _card(panel.render("paper", "t" * 40, AT15), "today")
    assert "原先：" not in card and "开盘前余力 192 円" in card


def _btn(html: str, act: str, t: str) -> str:
    i = html.find(f"data-act='{act}' data-t='{t}'")
    return "" if i < 0 else html[i:html.index("</button>", i)]


def test_corefix_card_shows_a_registered_change_and_the_buttons_after_it():
    """确认之后、执行器还没读：ETF 下面写「已登记：…」、按钮按登记之后的样子（恢复按规则登记了 → 不再给「恢复按规则」；
    2026-10-15 复核：以前页面上还是原来的按钮，像没写成、会再点一次）。撤回了 → 回到原来的样子。"""
    _book1015()                                                                   # 1482.T 手动固定 678 口（还没拿）
    kl = {"items": {"1482.T": {"kind": "core", "name": "1482.T"}, "1545.T": {"kind": "core", "name": "1545.T"}}}
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"kline": kl}), encoding="utf-8")   # 「其他闲置资金 ETF（现在没拿）」
    html = panel.render("paper", "t" * 40, AT15)
    assert "手动固定 678 口</b>" in html and _btn(html, "corefix-clear", "1482.T") and _btn(html, "corefix", "1482.T").endswith("固定口数…")
    rec = MO.append("paper", {"kind": "corefix", "ticker": "1482", "clear": True}, clock=lambda: AT15)
    html = panel.render("paper", "t" * 40, AT15)
    assert "已登记：恢复按规则</b>" in html and "在那之前还是手动固定 678 口" in html and "要撤回也在那里" in html
    assert not _btn(html, "corefix-clear", "1482.T") and _btn(html, "corefix", "1482.T").endswith("买入…")   # 恢复按规则之后没拿 → 买入…
    MO.append("paper", {"kind": "cancel", "target": rec["id"]}, clock=lambda: AT15 + dt.timedelta(minutes=1))
    html = panel.render("paper", "t" * 40, AT15)
    assert "已登记：" not in html and _btn(html, "corefix-clear", "1482.T")
    MO.append("paper", {"kind": "corefix", "ticker": "1545", "units": 100}, clock=lambda: AT15 + dt.timedelta(minutes=2))
    html = panel.render("paper", "t" * 40, AT15)
    assert "已登记：固定 100 口</b>" in html and _btn(html, "corefix", "1545.T").endswith("固定口数…")
    assert not _btn(html, "corefix-clear", "1545.T")                           # 只固定在还没读的指令里：要取消 → 撤回那条


def test_status_signature_changes_with_trade_count():
    """/api/status：pending = 「交易」的数字；数字变了 sig 一定变（HALT 建了 / 删了，账本别的地方没变）。"""
    _book1015("tachibana", sell="SENT", cash=2_000_000.0, fix={})
    s0 = panel.status_json("tachibana")[1]
    paths.halt_file().write_text("测试", encoding="utf-8")
    try:
        s1 = panel.status_json("tachibana")[1]
    finally:
        paths.halt_file().unlink()
    if s0["pending"] != s1["pending"]:                                       # 现在是成交日收盘之前（真实时钟）才会不同
        assert s0["sig"] != s1["sig"]
    A = (panel.STATIC_DIR / "conn.js").read_text(encoding="utf-8")         # 2026-10-15 起状态轮询在 conn.js（连接检查一起做）
    assert "+(st0.busy !== undefined ? st0.busy : st0.pending)" in A        # 轮询看还在处理的指令（busy），不是「交易」的数字
    assert "+(j.busy !== undefined ? j.busy : j.pending)" in A
