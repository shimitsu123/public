"""「持仓反映今天成交」（live_ops.held_now；2026-10-16）复核的回归测试：周末 / 早上的运行之前也按投影、凑钱与名额看执行时那一刻、
今天买进的个股不再当候选、立花快照早于成交时不报假的不一致、现价的「比昨收」、时点文字的空格与「今天」、固定口数的 ETF 不写会自动卖。
数据：tests/test_held_now._b1016（10/16 盘中卖光 1545 4,110 口、买进 1482 650 口；账本 10/15 收盘）等。"""
import copy
import datetime as dt
import json
import re

from qbreak import core_exit as CX
from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import names as NM
from qbreak import panel, paths
from qbreak import trade_room as TR
from qbreak.calendar_jp import JST

from test_held_now import _b1016, _o, _tbook
from test_panel_held_now import AT, SETTLE, _book, _book_stocks, _text, _write

SAT = dt.datetime(2026, 10, 17, 12, 0, tzinfo=JST)                     # 周六
MON7 = dt.datetime(2026, 10, 19, 7, 0, tzinfo=JST)                     # 周一 07:40 之前
MON9 = dt.datetime(2026, 10, 19, 9, 0, tzinfo=JST)                     # 周一 早上的运行没做完（missed）
FRI10 = dt.datetime(2026, 10, 16, 10, 0, tzinfo=JST)                   # 成交日盘中
FRI1310 = dt.datetime(2026, 10, 16, 13, 10, tzinfo=JST)
FRI1540 = dt.datetime(2026, 10, 16, 15, 40, tzinfo=JST)                # 收盘后（timing next）


def _r100(b: dict, n: int) -> dict:
    b["core_rule"]["rule100"] = {"1482.T": n}
    return b


# ────────── F1：「恢复按规则」的说明在周末 / 07:40 之前也按今天已成交的口数 ──────────
def test_corefix_clear_text_weekend_and_before_the_morning_run():
    for now in (AT, SAT, MON7):
        txt = MO.corefix_clear_text(_r100(_b1016(), 0), "1482.T", "paper", now=now)
        assert "全部卖出 650 口" in txt and "不会买" not in txt, (now, txt)
    for now, head in ((SAT, "含 10/16（周五）已成交"), (MON7, "含 10/16（周五）已成交")):
        txt = MO.corefix_clear_text(_r100(_b1016(), 700), "1482.T", "paper", now=now)
        assert "规则现在 700 口（现在 650 口（" + head + "；账本 0 口））" in txt, txt
        assert "差 50 口在再平衡带" in txt and "买 700 口" not in txt and "含今天已成交" not in txt, txt
    txt = MO.corefix_clear_text(_r100(_b1016(), 700), "1482.T", "paper", now=AT)   # 周五收盘后：与周末同一个结论
    assert "差 50 口在再平衡带" in txt and "含今天已成交；账本 0 口" in txt


def test_corefix_clear_text_adds_only_the_unfilled_rest_of_open_orders():
    def bk(n):
        b = _r100(_b1016(), n)
        b["orders"].append({"cid": "U2026-10-15-BUY-1482.T-N100500", "ticker": "1482.T", "side": "BUY", "kind": "core", "qty": 10,
                            "sent_qty": 10, "filled_qty": 4, "filled_px": 1486.0, "status": "PARTIAL", "reason": "core_fix",
                            "phase": "now", "decided_on": "2026-10-15"})
        return b
    txt = MO.corefix_clear_text(bk(0), "1482.T", "paper", now=AT)   # 650 + 4（已成交，含在 held_now）+ 6（还挂着）= 660（不重复算那 4 口）
    assert "全部卖出 660 口" in txt, txt
    txt = MO.corefix_clear_text(bk(700), "1482.T", "paper", now=AT)
    assert "现在 654 口（含今天已成交；账本 0 口），今天的单成交后约 660 口" in txt and "差 40 口" in txt, txt


# ────────── F2：今天买进的个股不挡「全部换成」 ──────────
def test_allin_not_blocked_by_a_stock_bought_today_and_says_it_is_sold_too():
    _book_stocks()
    ok, msg, _r = panel.submit({"book": "paper", "kind": "buy", "ticker": "9984.T", "unit": "rule", "fund": {"mode": "all"}}, now=AT)
    assert ok, msg
    assert "今天买进的：" + NM.label("7203.T") + "（对账之后算持仓，执行时一起卖出）" in msg
    sells = [r for r in MO.read_all("paper") if r.get("kind") == "sell"]
    assert [r["ticker"] for r in sells] == ["6758.T"]                         # 7203 由执行时的 _allin_sweep 一起卖（不写空的卖出）


# ────────── F3：凑钱时今天有成交的票只在成交日当天（对账前执行）才不拿 ──────────
def test_fund_holdings_busy_depends_on_when_it_runs():
    b = _b1016()
    fh = MO.fund_holdings(b, "paper", now=SAT)
    assert not {"1482.T", "1545.T"} & set(fh["busy"]) and [(h["t"], h["cur"]) for h in fh["hold"]] == [("1482.T", 650)]
    sp = MO.fund_split(500_000, fh, skip="7203.T")
    assert sp and [r["t"] for r in sp["rows"]] == ["1482.T"]                   # 周六写的在周一对账之后执行：1482 能凑
    for now in (FRI10, FRI1310):
        assert "1482.T" in MO.fund_holdings(b, "paper", now=now)["busy"]     # 当天盘中：同一只今天不再下第二笔
    assert "1482.T" not in MO.fund_holdings(b, "paper", now=FRI1540)["busy"]
    b = _book_stocks()
    fh = MO.fund_holdings(b, "paper", now=AT)
    assert "7203.T" not in fh["busy"] and "6758.T" not in fh["busy"]          # 收盘后写的在对账之后执行：今天买进的也能凑（二次复核 F2）
    assert {"7203.T", "6758.T"} <= set(MO.fund_holdings(b, "paper", now=FRI10)["busy"])   # 当天盘中：今天有成交的不拿


# ────────── F4 / F8：今天买进的个股，「比昨收」= 决策那天的收盘 ──────────
def _quotes(monkeypatch, px=2530.0):
    monkeypatch.setattr(panel, "_QUOTE_CACHE", {})
    monkeypatch.setattr(panel, "_CHART_CACHE", {})

    def fetch(ts):
        return {t: {"px": px if t == "7203.T" else 1490.0 if t == "1482.T" else 3000.0, "at": "2026-10-16T10:00+09:00"} for t in ts}
    return panel.quotes_json("paper", now=FRI10, fetch=fetch)[1]["rows"]


def test_quotes_prev_close_for_a_stock_bought_today(monkeypatch):
    _book_stocks()
    r = _quotes(monkeypatch)["7203.T"]
    assert r["chg_pct"] is None and r["pl_pct"] == round((2530 / 2500 - 1) * 100, 2)   # 没有昨收：不拿成交价充数
    (paths.out_dir() / "charts_paper.json").write_text(json.dumps({"tickers": {"7203.T": {"tf": {"D": {
        "d": ["2026-10-14", "2026-10-15", "2026-10-16"], "c": [2400.0, 2450.0, 2999.0]}}}}}), encoding="utf-8")
    rows = _quotes(monkeypatch)
    r = rows["7203.T"]
    assert r["chg_pct"] == round((2530 / 2450 - 1) * 100, 2) and r["pl_pct"] == round((2530 / 2500 - 1) * 100, 2)
    assert rows["6758.T"]["chg_pct"] == round((3000 / 3050 - 1) * 100, 2)    # 账本里的照旧按 last_close
    (paths.out_dir() / "live_unified_paper.json").write_text(json.dumps({"suggest": {"rows": [
        {"ticker": "7203.T", "close": 2440.0}]}}), encoding="utf-8")
    assert _quotes(monkeypatch)["7203.T"]["chg_pct"] == round((2530 / 2440 - 1) * 100, 2)   # 汇总的那一行优先


# ────────── F5 / F13：立花的快照早于今天的成交 → 不报假的不一致 ──────────
def _tb_card(snap_at: str, positions: list) -> str:
    b = _tbook([_o("6758.T", "SELL", qty=200, filled=200, px=3000.0, phase="now", cid="U2026-10-15-SELL-6758.T-N100000")],
               pos={"6758.T": {"shares": 200, "entry_px": 2900.0, "last_close": 3000.0, "entry_date": "2026-09-01"}})
    (paths.out_dir() / "broker_snapshot_tachibana.json").write_text(json.dumps(
        {"at": snap_at, "source": "执行器核对", "positions": positions, "buying_power": 100000.0}), encoding="utf-8")
    now = dt.datetime(2026, 10, 16, 10, 30, tzinfo=JST)
    pj = LO.held_now(b, "tachibana", now=now, snap={})
    return panel._broker_card("tachibana", now, pj)


def test_broker_card_snapshot_before_the_fill_is_not_a_mismatch():
    h = _tb_card("2026-10-16 07:41:05", [{"ticker": "6758.T", "qty": 200}])
    t = _text(h)
    assert "card warn" not in h and "不一致" not in t and "下一次早上的核对会停下" not in t
    assert NM.label("6758.T") + " 立花 200 / 账本 200 ✓" in t and "快照之后今天又成交了，下一次刷新才看得到" in t
    assert "（账本含今天已成交）" not in t


def test_broker_card_snapshot_after_the_fill_uses_the_projection():
    h = _tb_card("2026-10-16 11:35:00", [])
    t = _text(h)
    assert "card warn" not in h and "不一致" not in t and "快照之后" not in t and "（账本含今天已成交）" in t
    # 10:00 盘中成交（单上记的、确定的）、11:35 的快照立花还是 200：账本 + 成交 = 0 对 200 → 真的不一致（早上的核对也会停）→ 标红
    # （2026-10-16 二次复核 F11：以前凡是今天成交过的票一律降成「对账之后再看」，把真的不一致藏起来了）
    h = _tb_card("2026-10-16 11:35:00", [{"ticker": "6758.T", "qty": 200}])
    t = _text(h)
    assert "card warn" in h and "下一次早上的核对会停下" in t and "（账本按含今天已成交算）" in t


def test_broker_card_ledger_mismatch_still_warns():
    h = _tb_card("2026-10-16 07:41:05", [{"ticker": "6758.T", "qty": 100}])   # 快照早于成交、账本 200 对立花 100：真的不一致
    assert "card warn" in h and "下一次早上的核对会停下" in _text(h)


# ────────── F6 / F12：manual list 的持仓行含今天已成交 ──────────
def test_manual_list_holdings_follow_the_projection(capsys, monkeypatch):
    import run
    from qbreak import calendar_jp as CJ
    for now, dw in ((AT, "今天"), (SAT, "10/16（周五）")):
        monkeypatch.setattr(CJ, "now_jst", lambda now=now: now)
        _book()
        assert run.main(["manual", "list", "--broker", "paper"]) == 0
        out = capsys.readouterr().out
        assert "核心 1545" not in out and "核心 " + NM.qty("1482.T", "650 口") + f"（{dw}买进，对账前）" in out, out
        assert "已成交（对账前）：1545 纳斯达克 100：" + dw + "已卖出全部 4,110 口" in out
        assert "今天已成交：" not in out
    monkeypatch.setattr(CJ, "now_jst", lambda: AT)
    _book_stocks()
    run.main(["manual", "list", "--broker", "paper"])
    out = capsys.readouterr().out
    assert NM.qty("6758.T", "200 股") in out and NM.qty("7203.T", "100 股") in out and "（今天买进，对账前）" in out
    assert NM.qty("6758.T", "400 股") not in out
    assert "个股名额：空 2 个（拿着 2 + 排定买入 0，上限 4 只）（含今天已成交）" in out


# ────────── F7：个股名额含今天已成交 ──────────
def _stk(t: str, n: int = 100) -> dict:
    return {"shares": n, "entry_px": 1000.0, "last_close": 1000.0, "entry_date": "2026-09-01", "stop_px": 900.0}


def test_slots_count_todays_fills():
    b = _tbook([_o("4507.T", "BUY", qty=100, filled=100, px=2900.0, phase="now", reason="manual_buy")])   # 账本没有个股、今天买进 4507
    s = MO.slots(b, "paper", now=FRI1310, with_today=True)
    assert (s["held"], s["free"], s["today"]) == (1, 3, True)
    b = _tbook([_o("6758.T", "BUY", qty=100, filled=100, px=3500.0, phase="now")], pos={"7203.T": _stk("7203.T"), "9984.T": _stk("9984.T")})
    s = MO.slots(b, "paper", now=FRI1310, with_today=True)
    assert (s["held"], s["free"]) == (3, 1)
    four = {t: _stk(t) for t in ("7203.T", "6758.T", "9984.T", "8306.T")}
    b = _tbook([_o("7203.T", "SELL", qty=100, filled=100, px=1000.0, phase="now")], pos=four)   # 今天卖光 7203
    s = MO.slots(b, "paper", now=FRI1310, with_today=True)                                     # 盘中写的马上执行：执行器还按账本算 4 只
    assert (s["held"], s["free"], s["today"]) == (4, 0, False)
    s = MO.slots(b, "paper", now=FRI1540, with_today=True)                                     # 收盘后写的：对账之后执行，7203 已经不在
    assert (s["held"], s["free"], s["today"]) == (3, 1, True)
    rec = MO.normalize({"kind": "buy", "ticker": "4502.T", "unit": "rule"})
    assert "名额已满" not in str(MO.check(rec, b, "paper", now=FRI1540) or "")
    assert "名额已满" in str(MO.check(rec, b, "paper", now=FRI1310) or "")
    b = _tbook([_o("4507.T", "BUY", qty=100, filled=100, px=2900.0, phase="open")])   # 规则的开盘计划买进的：不重复算进排定买入
    b["state"]["plan"] = {"4507.T": {"shares": 100}}
    s = MO.slots(b, "paper", now=FRI1310, with_today=True)
    assert (s["held"], s["buys"], s["free"]) == (1, 0, 3)


# ────────── F9：今天买进的个股不再当候选 ──────────
def _sg() -> dict:
    return {"asof": "2026-10-15", "fill_day": "2026-10-16", "rows": [
        {"ticker": "7203.T", "code": "7203", "name": "トヨタ自動車", "status": "triggered", "signal": True, "close": 2450.0,
         "buy": {"rule_shares": 100, "px": 2450.0, "lot": 100, "em": 1.0, "limit": 2524}, "rule": {"state": "none", "text": "信号成立"}},
        {"ticker": "6501.T", "code": "6501", "name": "日立製作所", "status": "watch", "close": 3100.0,
         "buy": {"rule_shares": 100, "px": 3100.0, "lot": 100, "em": 1.0, "limit": 3193}, "rule": {}}]}


def test_suggest_cards_mark_a_stock_bought_today():
    b = _book_stocks()
    c = panel._suggest_ctx(_sg(), b, "paper", marks={}, now=AT)
    assert c["bought"] == {"7203.T": "今天已买进 100 股（对账前）"}
    assert (c["slots"]["held"], c["slots"]["free"], c["slots"]["today"]) == (2, 2, True)
    h = panel._auto_buy_card(_sg(), b, "paper", 1_000_000.0, chart=lambda t, k: "", ctx=c)
    assert "data-act='buy' data-t='7203.T'" not in h and "今天已买进 100 股（对账前）" in _text(h)
    assert "个股名额空 2 个（上限 4 只）（含今天已成交）" in _text(h)
    h = panel._suggest_card(_sg(), b, "paper", set(), "马上", 1_000_000.0, 100.0, lambda t, k: "", ctx=c)
    assert "data-act='buy' data-t='6501.T'" in h and "（含今天已成交）" in _text(h)


# ────────── F10：解除「不买回」的确认框：今天已经卖光的不算「还没成交的卖出」 ──────────
def test_unblock_confirm_does_not_list_a_ticker_sold_out_today():
    b = _tbook([_o("7203.T", "SELL", qty=100, filled=100, px=1000.0, phase="now")], pos={"7203.T": _stk("7203.T")})
    b["manual"] = {"items": {}, "blocks": {"7203.T": {"id": "M20261016-1", "since": "2026-10-16", "until": None}}}
    h = panel._blocks_card(b, "paper", b["manual"]["blocks"], NM.label, now=AT)[0]
    assert "还没成交的卖出" not in h and "现在空 4 个，上限 4 只（含今天已成交）" in h
    b["orders"] = []                                                          # 没成交：照旧说还没成交的卖出
    assert "还没成交的卖出（" + NM.label("7203.T") + "）" in panel._blocks_card(b, "paper", b["manual"]["blocks"], NM.label, now=AT)[0]


# ────────── F11：交易页「拿着的 N 只」与持仓同一个数 ──────────
def test_trade_room_held_count_follows_the_projection():
    b = _book_stocks()
    b["state"]["pos"]["6758.T"]["shares"] = 400
    rm = TR.room("paper", b, FRI1310, sm={}, halt=False, arm="file", waiting=[])
    assert "拿着的 3 只（含今天已成交）里今天还能卖" in rm["overall"]["sell_left"]["why"], rm["overall"]["sell_left"]["why"]


# ────────── F14：持仓卡片里「今天买进…」那句只写一次 ──────────
def test_holdings_card_says_bought_today_once():
    b = _book_stocks()
    b["orders"].append({"cid": "U2026-10-15-BUY-1655.T", "ticker": "1655.T", "side": "BUY", "kind": "core", "qty": 10, "sent_qty": 10,
                        "filled_qty": 10, "filled_px": 870.0, "status": "FILLED", "reason": "核心 ETF 调整", "phase": "open",
                        "decided_on": "2026-10-15"})
    _write(b)
    h = panel.render("paper", "c" * 40, AT, mode="remote", device={"name": "iPhone", "created": "2026-10-06T08:00:00+09:00"})
    i = h.index("id='holdings'")
    card = _text(h[i:h.index("</section>", i)])
    assert card.count("7203 トヨタ自動車：今天买进 100 股 @ ¥2,500.00") == 1, card
    assert card.count("1655 S&P500：今天买进 10 口") == 1, card
    assert "对账之后才能卖出 / 调仓" not in card and "data-act='sell' data-t='7203.T'" in h   # 收盘后：对账之后执行 → 按钮照常（二次复核 F2）
    h = panel.render("paper", "c" * 40, FRI1310, mode="remote", device={"name": "iPhone", "created": "2026-10-06T08:00:00+09:00"})
    i = h.index("id='holdings'")
    card = _text(h[i:h.index("</section>", i)])
    assert "今天盘中执行器不再动它" in card and "data-act='sell' data-t='7203.T'" not in h   # 当天盘中：执行器今天不动它


# ────────── F15：周末的「今天」写成成交那天 ──────────
def test_saturday_labels_use_the_fill_day(capsys, monkeypatch):
    import shutil

    import run
    from qbreak import calendar_jp as CJ
    from qbreak import desktop_page as DP
    rm = TR.room("paper", _b1016(), SAT, sm={}, halt=False, arm="file", waiting=[])
    r82 = rm["per_ticker"]["1482.T"]                                        # 周末写的在对账之后执行 → 按投影（四次复核）：
    assert r82["held"] == 650 and r82["sell"]["short"] == "休市日" and "今天买进" not in r82["chip"]   # 1482 拿着、1545 已经没了
    assert "1545.T" not in rm["per_ticker"]
    _book_stocks()
    shutil.copy(paths.PROJECT_ROOT / "var" / "sim.json", paths.home() / "sim.json")
    monkeypatch.setattr(CJ, "now_jst", lambda: SAT)
    assert run.main(["live-u", "--broker", "paper", "--status"]) == 0
    out = capsys.readouterr().out
    assert "（含 10/16（周五）已成交；账本 ¥" in out and "（10/16（周五）买进，对账前）" in out
    assert "含今天已成交" not in out and "今天买进，对账前" not in out and "  今天已成交 " not in out
    monkeypatch.setattr(DP, "now_jst", lambda: SAT)
    t = _text(DP.render("paper", 1_000_000, "2026-09-28"))
    assert "10/16（周五）有成交（对账前）" in t and "今天有成交" not in t


# ────────── F16：时点文字后面不多空格 ──────────
def test_settle_words_have_no_stray_spaces():
    from qbreak import holding_view as HV
    b = _book_stocks()
    pj = LO.held_now(b, "paper", now=MON9)                                    # 早上的运行没做完 → 「下一次执行器运行」
    assert pj["missed"] and pj["when_sp"] == "下一次执行器运行"
    for x in pj["by_ticker"].values():
        assert "运行 对账" not in x["text"]
    hv = HV.overlay({"holdings": [], "core": []}, pj)
    later = [r.get("later") for r in hv["holdings"] if r.get("later")]
    assert later == ["止损价、趋势标签在下一次执行器运行的决策之后才有"]
    hv = HV.overlay({"holdings": [], "core": []}, LO.held_now(b, "paper", now=AT))
    assert [r.get("later") for r in hv["holdings"] if r.get("later")] == ["止损价、趋势标签在" + SETTLE + " 的决策之后才有"]
    why = MO.today_why(b, "7203.T", "buy", "paper", now=MON9)
    assert "下一次执行器运行对账之后才算持仓" in why and "运行 对账" not in why
    assert MO.today_why(b, "7203.T", "sell", "paper", now=MON9) is None       # 对账之后执行：卖出不挡（二次复核 F2）
    fa = MO.fund_all(_book(), "paper", "9984.T", now=MON9)
    assert any("（下一次执行器运行对账后正式记账）" in w for _t, w in fa["skip"])


# ────────── F17：损益卡片说清当日 / 累计是账本收盘的数 ──────────
def test_money_card_and_desktop_say_pnl_is_as_of_the_ledger_close(monkeypatch):
    from qbreak import desktop_page as DP
    b = _book()
    note = "当日 / 累计损益按账本（10/15 收盘）；今天已成交的在" + SETTLE + " 对账之后才算进来"
    h = panel._money_card("paper", b, AT, LO.held_now(b, "paper", now=AT))
    assert note in _text(h)
    assert note in _text(panel.render("paper", "t" * 40, AT))
    monkeypatch.setattr(DP, "now_jst", lambda: AT)
    assert note in _text(DP.render("paper", 1_000_000, "2026-09-28"))
    b0 = copy.deepcopy(b)
    b0["orders"] = []
    assert "当日 / 累计损益按账本" not in _text(panel._money_card("paper", b0, AT, LO.held_now(b0, "paper", now=AT)))


# ────────── F18：固定口数的 ETF 不写「会自动卖」 ──────────
def test_fixed_core_etf_exit_card_says_the_rule_will_not_sell_it():
    info = CX.build("1482.T", {}, LO.held_now(_b1016(), "paper", now=AT)["book"], fixed=650)
    assert info and info["tiles"] == [] and len(info["rows"]) == 1 and not info["hot"]
    assert info["rows"][0]["text"] == "手动固定 650 口：规则不会自动卖（不看美股牛熊 / 股债相关）"
    assert "「固定口数…」（0 口）或「恢复按规则」" in info["rows"][0]["sub"]
    assert set(info) >= {"t", "name", "mode", "label", "key", "asof", "asof_md", "tiles", "rows", "never", "never_tags", "notes", "hot"}
    _book()
    h = panel.render("paper", "t" * 40, AT)
    m = re.search(r"data-exit='1482\.T'(.*?)</details>", h, re.S)
    assert m, "1482 没有「什么时候会自动卖」"
    blk = _text(m.group(1))
    assert "手动固定 655 口：规则不会自动卖" in blk and "下个开盘全部卖" not in blk and "全部卖" not in blk.replace("不会自动卖", "")
