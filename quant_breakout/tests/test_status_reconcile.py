"""手动指令的状态与对账之后的说明（2026-10-14 缺口 G7 / G8 / G11 / G16 / G17 / G22 / G26）：
① G7 手动单没发出（被拒 / 被挡）：卖出留着、说明写「MM/DD 没发出（原因）→ 下一次决策再下」，重下时更新成交日；
   买入被拒 → 对账时结束（没下成）；09:30 自检列出被拒的手动单、同一条连续 2 天没发出标 ★（HALT 不算）；
② G8「全部换成 X」留到开盘后的买入被放弃 / 没下成 → 当天结束、warn「卖单已成交 / 已发出，X 没买」；
③ G11 状态不明的单登记为没成交（--resolve 0 股）= 没成交：卖出「下一开盘再卖」；
④ G16 盘中的手动卖单 15:30 失效之后可以撤回（明天不再卖）；挂着 / 全部成交 / 买入的说明不再互相矛盾；
⑤ G17 手动买入作废 → warn + 日报「★ 手动买入作废 N 条」，手动指令的几行在持仓说明之前（推送正文 600 字截断）；
⑥ G22 手动卖出 / 减仓之后只剩零股 → 指令结束（不再每天建「零股：这笔不下」的单）；
⑦ G26 卖单没卖掉 → 日报「仍是待卖」那一行，连续 2 天以上「★ X 连续 N 天没卖掉」。"""
import datetime as dt
import json

from qbreak import live_ops, panel, paths, watchdog
from qbreak import manual_orders as MO
from qbreak.brokers.tachibana_sim import SimExchange
from qbreak.calendar_jp import JST
from qbreak.live_unified import daily_text, unsold_long, unsold_today, voided_today

from test_allin_exec import _allin, _ev, _orders
from test_intraday_buy_gaps import _no_open_phase_day
from test_manual_buy import _buy
from test_manual_orders import TAG, _NoSellOnce, _Run, _sell_req


def _refusing(left: dict):
    """立花拒绝新注文的模拟交易所：left = {(票, BUY / SELL): 还要拒绝几次}（例：売付可能数量不足 —— 网站上另有挂单）。"""
    class _Refuse(SimExchange):
        def _new_order(self, p):
            s = self.spec
            key = (f"{p.get(s.f_code)}.T", "BUY" if p.get(s.f_side) == s.side_buy else "SELL")
            if left.get(key, 0) > 0:
                left[key] -= 1
                return self._err("991099", "テスト：受け付けません")
            return super()._new_order(p)
    return _Refuse


def _no_sell(n: int = 99):
    """A.T 的卖单前 n 次挂着不成交（寄付で約定せず / 盘中的指値没触及；收盘时失效）。"""
    class _Stuck(SimExchange):
        left = n

        def _fill(self, o, op):
            if o["side"] == "SELL" and o["ticker"] == "A.T" and self.left > 0:
                self.left -= 1
                return
            super()._fill(o, op)
    return _Stuck


def _texts(r):
    sm = r.ux.summary()
    return sm, daily_text(sm, r.eng.st, None, False, 1_000_000)


# ────────── ① G7：手动单没发出 ──────────
def test_g7_rejected_manual_sell_stays_pending_and_says_when_it_was_not_sent():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True, exchange_cls=_refusing({("A.T", "SELL"): 2}))
    r.until(14)
    rec = _sell_req(r)
    r.day()                                                    # 第 15 根的决策：卖单被立花拒绝
    it = r.item(rec["id"])
    f1 = it["fill_day"]
    assert it["status"] == "placed" and r.eng.st.pending_exit.get("A.T") == "manual"
    assert it["unsent"]["n"] == 1 and it["unsent"]["last"] == f1
    assert it["msg"].startswith(f"{MO.mmdd(f1)} 没发出（立花没受理：") and "テスト" in it["msg"]
    assert it["msg"].endswith("→ 下一次决策再下") and MO.status_text(it) == "没发出，等再下"
    r.day()                                                    # 对账（同一个成交日不重复算）→ 第 16 根的决策：又被拒
    it = r.item(rec["id"])
    assert it["unsent"]["n"] == 2 and it["unsent"]["last"] > f1 and it["fill_day"] == f1
    r.day()                                                    # 第 17 根的决策：受理 → 说明写重下的成交日
    it = r.item(rec["id"])
    assert "unsent" not in it and it["status"] == "placed" and it["fill_day"] > f1
    assert it["msg"].startswith(f"{MO.mmdd(it['fill_day'])} 开盘再卖 ") and "（上次：" in it["msg"] and "没发出" in it["msg"]
    assert MO.status_text(it) != "没发出，等再下"
    r.day()
    assert r.item(rec["id"])["status"] == "done" and "A.T" not in r.eng.st.pos


def test_g7_halt_blocked_manual_sell_does_not_count_as_a_streak():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True, exchange_cls=_refusing({("A.T", "SELL"): 1}))
    r.until(14)
    rec = _sell_req(r)
    r.day()
    assert r.item(rec["id"])["unsent"]["n"] == 1
    m = r.ux.manual
    it = r.item(rec["id"])
    m.on_not_sent("A.T", "manual", "2099-01-05", "HALT 生效中", halt=True)
    assert it["unsent"]["n"] == 1 and it["unsent"]["halt"] and it["msg"].endswith("→ HALT 解除后的决策再下")


def test_g7_g17_rejected_manual_buy_is_voided_with_a_warning_and_a_daily_line():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True, exchange_cls=_refusing({("B.T", "BUY"): 1}))
    r.until(14)
    rec = _buy(r, id="M-rej-buy")
    r.day()                                                    # 第 15 根的决策：B.T 寄付买单被立花拒绝
    it = r.item(rec["id"])
    assert it["status"] == "placed" and "没发出（立花没受理：" in it["msg"] and "不再重下" in it["msg"]
    assert MO.status_text(it) == "没发出（只做一次）"
    r.day()                                                    # 对账：被拒不是系统原因 → 只做一次，结束（作废）
    it = r.item(rec["id"])
    bar = str(r.eng.gidx[16].date())
    assert it["status"] == "rejected" and it["void_on"] == bar and "unsent" not in it
    assert it["msg"].startswith(f"{bar} 开盘没下成（立花没受理：") and "只做一次" in it["msg"]
    assert "B.T" not in r.eng.st.pos and not r.ux.manual.m["buys"]
    ev = [e for e in _ev(r) if e["msg"].startswith("★ 手动买入 B 作废")]
    assert len(ev) == 1 and ev[0]["level"] == "warn"
    sm, (_, short, body) = _texts(r)
    assert [x["id"] for x in voided_today(sm)] == [rec["id"]] and "｜★ 手动买入作废 1 条" in short
    ls = body.splitlines()
    i_man = next(i for i, x in enumerate(ls) if x.startswith("- 手动 买入 B"))
    i_pos = next(i for i, x in enumerate(ls) if x.startswith("- 持仓："))
    assert i_man < i_pos                                       # 手动指令的结果在持仓说明之前（600 字截断）
    r.day()
    sm, (_, short, _b) = _texts(r)
    assert not voided_today(sm) and "手动买入作废" not in short   # 第二天不再算
    assert len([e for e in _ev(r) if e["msg"].startswith("★ 手动买入 B 作废")]) == 1


def _wd_book(it: dict, **o_kw):
    o = {"cid": "U2026-10-05-SELL-7203.T", "ticker": "7203.T", "side": "SELL", "kind": "stock", "qty": 100,
         "decided_on": "2026-10-05", "status": "REJECTED", "reason": "manual", "phase": "morning",
         "note": "売付可能数量が不足しています", **o_kw}
    (paths.state_dir() / "live_unified_tachibana.json").write_text(json.dumps(
        {"state": {"last_date": "2026-10-05"}, "orders": [o], "manual": {"items": {it["id"]: it}}}, ensure_ascii=False),
        encoding="utf-8")


def test_g7_watchdog_lists_rejected_manual_orders_and_flags_two_days():
    now = dt.datetime(2026, 10, 6, 9, 30, tzinfo=JST)
    it = {"id": "M-s", "kind": "sell", "ticker": "7203.T", "status": "placed", "at": "2026-10-02T06:00:00+09:00",
          "unsent": {"n": 2, "last": "2026-10-06", "why": "立花没受理：売付可能数量が不足しています", "halt": False}}
    _wd_book(it)
    rs = watchdog.evaluate("tachibana", now)["reasons"]
    assert any(x.startswith("决策 2026-10-05 有 1 笔手动指令的单没发出：") for x in rs)
    star = [x for x in rs if x.startswith("★ 手动指令 M-s（")]
    assert len(star) == 1 and "连续 2 个交易日没发出（立花没受理：売付可能数量が不足しています）" in star[0]
    _wd_book({**it, "unsent": {**it["unsent"], "n": 1}})
    rs = watchdog.evaluate("tachibana", now)["reasons"]
    assert rs and not any(x.startswith("★ 手动指令") for x in rs)
    _wd_book(it, status="BLOCKED", note="存在 HALT 文件 /x/HALT")   # HALT 挡下的：不是问题
    rs = watchdog.evaluate("tachibana", now)["reasons"]
    assert not any("手动指令" in x for x in rs)


# ────────── ② G8：「全部换成 X」开盘后没买 ──────────
def test_g8_allin_buy_given_up_after_the_open_ends_the_same_day_with_a_warning():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _allin(r, r.at(r.k - 1, 6).isoformat())
    r.day()                                                    # 第 15 根的决策：卖单寄付、B.T 留到开盘后
    xo = next(o for o in _orders(r, "B.T", "BUY") if o.decided_on == r.eng.st.last_date)
    assert xo.status == "DEFERRED"
    d = r.eng.st.last_date
    r.ux._gate_buy = lambda o: "测试：不下" if o.ticker == "B.T" else None
    k = r.k
    r.exch.open(k)
    r.now["t"] = dt.datetime.combine(r.eng.gidx[k].date(), dt.time(9, 5), tzinfo=JST)
    r.ux.open_phase()                                          # 09:05：开盘后补单放弃 B.T
    it = r.item("M-all-buy")
    assert xo.status == "SKIPPED" and it["status"] == "rejected" and it["void_on"] == d
    assert it["msg"].startswith("「全部换成 B」卖单已发出，B 没买（测试：不下）：钱留现金，闲置资金 ETF 仍停买")
    assert "B.T" not in r.ux.manual.m["buys"]
    ev = [e for e in _ev(r) if e["msg"].startswith("★ 「全部换成 B」卖单")]
    assert len(ev) == 1 and ev[0]["level"] == "warn"
    sm = r.ux.summary()
    assert [x["id"] for x in voided_today(sm)] == ["M-all-buy"]
    r.exch.close_day()                                         # 收盘 → 第二天 07:40 的早上运行（对账不重复提醒）
    r.exch.set_day(k + 1)
    r.now["t"] = r.at(k)
    r.ux.morning([k])
    r.k += 1
    assert len([e for e in _ev(r) if e["msg"].startswith("★ 「全部换成 B」卖单")]) == 1
    sm, (_, short, _b) = _texts(r)
    assert not voided_today(sm) and "B.T" not in r.eng.st.pos and r.ux.manual.core_pct == 0.0


def test_g8_allin_buy_missed_because_the_open_phase_did_not_run():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _allin(r, r.at(r.k - 1, 6).isoformat())
    r.day()
    _no_open_phase_day(r)                                      # 09:05 / 09:20 没跑：对账时 MISSED
    it = r.item("M-all-buy")
    bar = str(r.eng.gidx[r.k - 1].date())
    assert it["status"] == "rejected" and it["void_on"] == bar
    assert it["msg"].startswith("「全部换成 B」卖单已成交，B 没买（开盘后补单没有运行") and "钱留现金，闲置资金 ETF 仍停买" in it["msg"]
    assert any(e["level"] == "warn" and e["msg"].startswith("★ 「全部换成 B」卖单已成交") for e in _ev(r))
    sm, (_, short, _b) = _texts(r)
    assert "｜★ 手动买入作废 1 条" in short


def test_g8_paper_allin_buy_given_up_at_the_open_says_sold():
    from test_manual_now import _morning, _paper
    from test_manual_buy import _write
    r = _paper("g8")
    _morning(r, until=14)
    at = "2026-01-01T06:00:00+09:00"
    _write({"kind": "core", "pct": 0, "fund_for": "B.T", "batch": "all", "source": "test", "id": "M-all-core", "at": at,
            "prev_pct": 100}, "g8")
    _write({"kind": "buy", "ticker": "B.T", "unit": "shares", "value": 100_000, "fund": "all", "source": "test",
            "id": "M-all-buy", "at": at}, "g8")
    _morning(r)                                                # 决策：卖单排队、B.T 留到开盘后
    assert r.ux.book["manual"]["items"]["M-all-buy"]["status"] == "placed"
    r.ux._gate_buy = lambda o: "测试：不下" if o.ticker == "B.T" else None
    _morning(r)                                                # 开盘撮合（卖单成交）→ 开盘后放弃 B.T → 当天结束
    it = r.ux.book["manual"]["items"]["M-all-buy"]
    assert it["status"] == "rejected" and it["void_on"] == r.eng.st.last_date
    assert it["msg"].startswith("「全部换成 B」卖单已成交，B 没买（测试：不下）")
    sm = r.ux.summary()
    assert [x["id"] for x in voided_today(sm)] == ["M-all-buy"]


# ────────── ③ G11：状态不明的单登记为没成交 ──────────
def test_g11_resolved_zero_is_treated_as_not_filled():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True, exchange_cls=_NoSellOnce)
    r.until(14)
    rec = _sell_req(r)
    r.day()
    o = next(x for x in r.ux.orders if x.ticker == "A.T" and x.side == "SELL")
    o.status, o.filled_qty = "RESOLVED", 0                     # 你在立花的注文一覧核对过：没成交（--resolve 0 股）
    r.item(rec["id"])["msg"] = "盘中卖出 200 股：下单结果不明，去立花核对"
    r.day()
    it = r.item(rec["id"])
    bar = str(r.eng.gidx[16].date())
    assert it["status"] == "placed" and "不明" not in it["msg"] and r.eng.st.pending_exit.get("A.T") == "manual"
    assert any(e["msg"] == "卖 A 状态不明的单登记为没成交 → 仍是待卖，今天再下" for e in _ev(r))
    hist = [x for h in r.ux.book["history"] for x in h["orders"] if x["cid"] == o.cid]
    assert hist and hist[0]["status"] == "RESOLVED"
    assert r.ux.book["unsold"]["A.T"]["why"] == "状态不明的单登记为没成交"
    assert any(x.ticker == "A.T" and x.side == "SELL" and x.decided_on == bar for x in r.ux.orders)   # 今天再下
    r.day()
    assert r.item(rec["id"])["status"] == "done"


def test_g11_on_fill_text_for_a_resolved_sell():
    m = MO.Manual.__new__(MO.Manual)
    m.m = {"items": {"M-x": {"id": "M-x", "kind": "sell", "ticker": "7203.T", "status": "placed", "fill_day": "2026-10-06"}},
           "trims": {}, "adds": {}, "buys": {}, "blocks": {}}
    st = type("S", (), {"pos": {"7203.T": object()}})()
    m.on_fill("7203.T", "manual", 0, 0.0, "2026-10-06", st, why="登记为没成交")
    assert m.m["items"]["M-x"]["msg"] == "2026-10-06 开盘的单登记为没成交 → 下一开盘再卖"


# ────────── ④ G16：盘中卖单 15:30 失效之后撤回 ──────────
def test_g16_now_cancel_why_by_time_side_and_fill():
    it = {"id": "M-now-sell-1", "kind": "sell", "ticker": "7203.T", "status": "placed", "now": True, "fill_day": "2026-10-06",
          "side": "SELL", "shares": 200}
    at = lambda h, m, d=6: dt.datetime(2026, 10, d, h, m, tzinfo=JST)     # noqa: E731
    assert MO.now_cancel_why(it, at(14, 0)) == MO.NOW_NO_CANCEL         # 还挂在交易所：用「撤单」
    assert MO.now_cancel_why(it, at(15, 31)) is None                    # 15:30 失效：可以撤回（明天不再卖）
    assert MO.now_cancel_why(it, at(7, 40, 7)) is None                  # 第二天早上对账之前也行
    assert MO.now_cancel_why({**it, "side": "BUY"}, at(15, 31)) == MO.NOW_BUY_LAPSED
    assert MO.now_cancel_why({**it, "fill": {"qty": 200}}, at(15, 31)) == MO.NOW_FILLED_NO_CANCEL
    assert MO.now_cancel_why({**it, "now": False}, at(15, 31)) is None
    book = {"state": {"last_date": "2026-10-05", "pos": {"7203.T": {"shares": 200}}}, "manual": {"items": {"M-now-sell-1": it}}}
    rec = MO.normalize({"kind": "cancel", "target": "M-now-sell-1"})
    assert MO.check(rec, book, now=at(14, 0)) == MO.NOW_NO_CANCEL
    assert MO.check(rec, book, now=at(15, 40)) is None


def _session_unfilled(r, hh=10, mm=0):
    """成交日（第 r.k 根）盘中下手动单、不等约定（挂着）：开盘撮合 → 09:05 开盘后补单 → hh:mm now_phase。"""
    k = r.k
    r.exch.open(k)
    r.now["t"] = dt.datetime.combine(r.eng.gidx[k].date(), dt.time(9, 5), tzinfo=JST)
    r.ux.open_phase()
    r.now["t"] = dt.datetime.combine(r.eng.gidx[k].date(), dt.time(hh, mm), tzinfo=JST)
    return r.ux.now_phase(r.quote)


def test_g16_expired_intraday_sell_can_be_withdrawn_and_is_not_sold_again():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True, exchange_cls=_no_sell())
    r.until(13)
    rec = _sell_req(r)
    res = _session_unfilled(r)
    it = r.item(rec["id"])
    assert res["placed"] == 1 and it["status"] == "placed" and it["now"] and not it.get("fill")
    book = json.loads((paths.state_dir() / "book.json").read_text(encoding="utf-8"))
    day = r.eng.gidx[r.k].date()
    t14, t1540 = (dt.datetime.combine(day, dt.time(h, m), tzinfo=JST) for h, m in ((14, 0), (15, 40)))
    ok, msg, _ = MO.cancel_request(TAG, book, rec["id"], now=t14)
    assert not ok and MO.NOW_NO_CANCEL in msg                      # 还挂着：用「撤单」
    o = next(x for x in r.ux.orders if x.ticker == "A.T" and x.side == "SELL" and x.phase == "now")
    why = live_ops.cancel_why(o, book, t1540, paper=False)
    assert why.startswith("已经收盘（15:30）") and f"不想再卖就在「交易」点开「另有 …」，在「手动指令」里撤回 {rec['id']}" in why
    ok, msg, _ = MO.cancel_request(TAG, book, rec["id"], now=t1540)
    assert ok, msg
    k = r.k                                                        # 收盘 → 第二天 07:40：读撤回 → 对账 → 撤 → 不再卖
    r.exch.close_day()
    r.exch.set_day(k + 1)
    r.now["t"] = r.at(k)
    r.ux.morning([k])
    r.k += 1
    it = r.item(rec["id"])
    assert it["status"] == "cancelled" and it["msg"].endswith(f"{day:%m/%d} 盘中的单已失效，之后不再卖")   # 按下单那天写（不写「明天」）
    assert "A.T" in r.eng.st.pos and "A.T" not in r.eng.st.pending_exit and "A.T" not in r.ux.manual.m["blocks"]
    assert not [x for x in r.ux.orders if x.ticker == "A.T" and x.side == "SELL"]
    assert "unsold" not in r.ux.book


def test_g16_panel_offers_withdrawal_only_after_the_close():
    it = {"id": "M-now-sell-1", "kind": "sell", "ticker": "7203.T", "status": "placed", "now": True, "fill_day": "2026-10-06",
          "side": "SELL", "shares": 200, "at": "2026-10-06T10:00:00+09:00", "msg": "盘中已下单"}
    st = {"last_date": "2026-10-05", "cash_jpy": 500_000.0, "history": [["2026-10-05", 1_000_000.0, 0, 0, 150]],
          "pos": {"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0,
                             "last_close": 2600.0}}, "pending_exit": {"7203.T": "manual"}, "core_units": {}}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(
        {"state": st, "orders": [], "manual": {"items": {"M-now-sell-1": it}, "blocks": {}, "trims": {}, "adds": {}, "buys": {}}},
        ensure_ascii=False), encoding="utf-8")
    h = panel.render("paper", "t" * 40, dt.datetime(2026, 10, 6, 14, 0, tzinfo=JST))
    assert "data-id='M-now-sell-1'" not in h
    h = panel.render("paper", "t" * 40, dt.datetime(2026, 10, 6, 15, 40, tzinfo=JST))
    assert "data-id='M-now-sell-1' data-placed='2'" in h


# ────────── ⑥ G22：只剩零股 → 指令结束 ──────────
def test_g22_manual_sell_leaving_only_odd_shares_finishes():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True)
    r.until(13)
    r.eng.st.pos["A.T"].shares += 50                            # 拆股 / 合并之后多出 50 股（单元未满）
    r.exch.pos["A.T"] += 50
    rec = _sell_req(r)
    r.day()                                                    # 卖整数手（零股不发、记 odd_lots）
    r.day()                                                    # 成交 → 只剩 50 股零股 → 指令结束
    it = r.item(rec["id"])
    assert r.eng.st.pos["A.T"].shares == 50 and "A.T" not in r.eng.st.pending_exit
    assert it["status"] == "done" and it["msg"].endswith("剩 50 股零股：API 卖不了，请在立花网站卖后说一声登记（adopt）")
    assert it["fill"]["qty"] > 0 and "卖出" in it["msg"]
    assert any("手动卖出这条指令结束" in e["msg"] for e in _ev(r))
    assert r.ux.book["odd_lots"]["A.T"]["shares"] == 50
    r.day()
    assert not [o for o in r.ux.orders if o.ticker == "A.T" and o.side == "SELL"]   # 不再每天建「零股：这笔不下」的单
    assert "A.T" not in (r.ux.book.get("unsold") or {})


def test_g22_trim_leaving_only_odd_shares_finishes():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True)
    r.until(13)
    r.eng.st.pos["A.T"].shares += 50
    r.exch.pos["A.T"] += 50
    rec = _sell_req(r, kind="trim", pct=15.0)                 # 250 股 → 100 股：要减 150 股 = 整数手 100 + 零股 50
    r.day()
    assert r.ux.book["manual"]["trims"]["A.T"]["shares"] == 150
    r.day()
    it = r.item(rec["id"])
    assert r.eng.st.pos["A.T"].shares == 150 and it["status"] == "done" and "剩 50 股零股" in it["msg"]
    assert "A.T" not in r.ux.manual.m["trims"]
    r.day()
    assert not [o for o in r.ux.orders if o.ticker == "A.T" and o.side == "SELL"]
    assert r.eng.st.pos["A.T"].shares == 150


# ────────── ⑦ G26：卖单没卖掉 ──────────
def test_g26_unsold_rule_sell_shows_in_the_daily_and_flags_two_days():
    r = _Run([1000.0] * 30, entry=(10,), dead=(15,), bear_all=True, exchange_cls=_no_sell(2))
    r.until(15)
    assert r.eng.st.pending_exit.get("A.T")
    r.day()                                                    # 第 16 根开盘没卖掉
    sm, (_, short, body) = _texts(r)
    u = unsold_today(sm)["A.T"]
    assert u["n"] == 1 and not unsold_long(sm) and "没卖掉" not in short
    assert "- ★ 卖 A 没卖掉（" in body and "→ 仍是待卖，今天再下" in body and "连续" not in body
    since = u["since"]
    r.day()                                                    # 第 17 根又没卖掉
    sm, (_, short, body) = _texts(r)
    assert unsold_today(sm)["A.T"]["n"] == 2 and unsold_long(sm) == ["A.T"]
    assert "｜★ A 连续 2 天没卖掉" in short
    assert f"（连续 2 天没卖掉，{since[5:].replace('-', '/')} 起）" in body
    r.day()                                                    # 第 18 根卖掉 → 记录去掉
    sm, (_, short, body) = _texts(r)
    assert "A.T" not in r.eng.st.pos and "unsold" not in r.ux.book and "没卖掉" not in short + body
