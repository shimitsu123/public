"""本机操作面板（qbreak/panel.py）：只接受本机、要令牌、只写手动指令；交易日 07:45〜08:50 早上的运行完成后叫执行器重试。"""
import datetime as dt
import http.client
import json
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
    assert trg.check() == ["paper"] and calls == [("paper", "retry")]     # 07:45〜08:50：加进今天开盘的寄付单
    assert trg.check() == []                                    # 3 分钟之内不重复
    trg.last.clear()
    now["t"] = dt.datetime(2026, 10, 6, 8, 55, tzinfo=JST)      # 过了 08:50、还没开盘：等 09:00
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
    assert not ok and "不能再加" in msg                         # 已经约占 52%，单只上限 34%
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
    assert "data-act='adj'" in html and "data-px='1000'" in html and "单只上限 <span id='adj-cap'>34</span>%" in html and "调仓…</button>" in html
    assert "一次最少 100 股" in html and "id='adj-bar'" in html and "id='adj-lab'" in html     # 调仓条按单元分格
    assert "data-t='6758.T' data-kind='stock'" in html and "data-t='1545.T' data-kind='core'" in html
    assert "现在没拿" in html and "data-t='1482.T' data-kind='core'" in html
    assert "data-act='tf'" not in html and "data-act='sub'" not in html                # 没有整页一排的切换：每张图自己的（脚本画）
    assert "kBar(box, 'ktop', 'ktf', TFS" in html and "kBar(box, 'kbot', 'ksub', SUBS" in html     # 上边沿 日K / 周K / 月K、下边沿 量 / MACD / DMI
    assert "</script><b>x" not in html and "对冲版美国国债&lt;/script&gt;" in html
    assert "日K <b class='up'>往上走</b> · 涨势整齐" in html and "周K <b class='muted'>横着走</b>" in html
    assert "月K <b class='down'>往下走</b> · 跌势整齐" in html and '"上升": "往上走"' in html     # 图下的说法也从 kline.py 来（CFG.kp）
    assert '"when": "今天 09:00 开盘"' in html and "addWhen" not in html
    assert "chart-data" not in html and "红色空心 = 涨" in html       # K 线数据不内嵌，打开时才取（/api/chart）
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


def _sm(rows=None):
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps(
        {"suggest": {"asof": "2026-10-05", "rows": SG_ROWS if rows is None else rows}}, ensure_ascii=False), encoding="utf-8")


def test_render_suggestions_with_buy_buttons_and_gates():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    _sm()
    html = panel.render("paper", "t" * 40, AT)
    assert "建议的股票（规则的候选，3 只）" in html and "个股名额：空 3 个（拿着 1 + 排定买入 0，上限 4 只）" in html
    assert ("<h3 class='sgh'>今天出了买入信号（1 只）</h3>" in html and "<h3 class='sgh'>快要出买入信号（1 只）</h3>" in html
            and "<h3 class='sgh'>观察中（1 只）</h3>" in html)
    assert html.count("data-act='buy'") == 2                                # 8035 被硬闸门挡：没有按钮
    assert "data-t='6501.T'" in html and "data-sig='1'" in html and "data-rule='200'" in html and "data-limit='3605'" in html
    assert "不能买：JPX 市場区分「プロ」：不买" in html and "顶部风险：RSI72" in html
    assert "★ 规则现在不开这只的新仓（新仓倍数 0）：执行器会挡" in html and "真突破" in html
    assert html.count("<details class='kl' open>") == 2 and "<details class='kl'><summary>" in html     # 观察中的 K 线默认收起
    assert "按规则约 200 股 · 约 ¥700,000 · 约占权益 70.0%" in html
    full = {t: {"shares": 100, "entry_px": 1000.0, "entry_date": "2026-09-01", "stop_px": 900.0, "last_close": 1000.0}
            for t in ("7203.T", "6758.T", "6861.T", "6098.T")}
    _book(pos=full, manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    html = panel.render("paper", "t" * 40, AT)
    assert "data-act='buy'" not in html and "个股名额已满（4 / 4 只）：先卖出一只" in html
    _sm([])
    assert "今天没有出信号 / 快要出信号 / 观察中的票" in panel.render("paper", "t" * 40, AT)


def test_render_watch_rows_show_how_far_from_a_buy_signal():
    _book(manual={"cap_pct": 34.0, "max_positions": 4, "items": {}})
    rows = [dict(r) for r in SG_ROWS]
    rows[2]["near"] = {"where": "below_up", "days": 2, "miss": [], "vol": 0.8}
    rows[2]["near_text"] = "离买入信号：MACD 约 2 天后金叉（按最近一天的变化估）；金叉那天量要 > 1.5 倍（今天 0.8 倍）"
    _sm(rows)
    html = panel.render("paper", "t" * 40, AT)
    assert ("<div class='small near'>离买入信号：MACD 约 2 天后金叉（按最近一天的变化估）；金叉那天量要 &gt; 1.5 倍（今天 0.8 倍）</div>"
            in html)
    assert html.count("按离买入信号的远近排（越上面越可能先出信号；只是估算）") == 1   # 只有带 near 的组（旧的汇总没有 → 不写）


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
    assert html.count("data-act='cancel'") == 2 and "有一条买入指令在处理（见「手动指令」）" in html


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
    """页面里的脚本整段能被 JavaScript 解析（Python 字符串里的 \\n 转义写错会让整页的按钮和走势图都不工作）。没有 node 就跳过。"""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("没有 node")
    _book()
    for mode in ("local", "remote"):
        html = panel.render("paper", "t" * 40, AT, mode=mode, device={"name": "x"}, phone={"port": 8766, "url": None, "devices": []})
        f = tmp_path / f"{mode}.js"
        f.write_text(html.split("<script>")[-1].split("</script>")[0], encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[-500:]


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
                                            "adjCap", "adjBar"))
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
    assert "没有预测力" in J                                                                   # 研究结论在「怎么看这张图」里说一次
