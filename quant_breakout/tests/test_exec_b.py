"""执行器：立花实盘缺口 B 组（2026-10-09「做〔77〕B」；只改工程，B13 是用户同意的执行补救）。
① B7 开盘后补单：取价整个失败 → 单全部保留、09:20 再试；还没寄り付き → 09:05 保留、09:20 放弃并记入差异；
② B13 早上错过寄付：个股卖单开盘后当日限价卖、买单 / 核心 ETF 今天不下；08:55 之前照旧寄付；
③ LU-21 早上持仓核对不一致 → 盘中 / 开盘后 / 晚到的早上运行都不下，直到下一次核对一致；
④ LU-22 成交日当天生效的拆股：寄付单按拆股后的股数 / 价格，第二天的公司行为同步不再调第二次；
⑤ LU-15 寄付单发出前拿立花的前日終値核对收盘：差 > 3% → 买单不下、卖单只提醒；
⑥ C-11 异常熔断；⑦ C-14 零股；⑧ B11 实盘起始本金；⑨ B4 账本备份 / 读坏不新开 / 恢复。"""
import datetime as dt
import itertools
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from qbreak import book_backup, paths
from qbreak.brokers.tachibana import TachibanaBroker
from qbreak.brokers.tachibana_sim import SimExchange
from qbreak.calendar_jp import JST, next_trading_day
from qbreak.corpactions import FakeActions
from qbreak.live_unified import (LATE_BUY_NOTE, LATE_SELL_NOTE, NO_OPEN_FINAL, NO_OPEN_WAIT, QUOTE_FAIL, UnifiedExecutor,
                                 _MemPaper, daily_text, flows, invested_jpy, late_pending, register_flow, rehearse,
                                 start_capital)
from qbreak.tick import round_to_tick

from test_live_unified import NEW, _frame, _maker, _synth

_SEQ = itertools.count()


def _setup(a_close=None, a_open=None, entry=(10,), dead=(), b_entry=(), bear_all=False, n=30, exchange_cls=SimExchange,
           cash=None, check_clock=False, clock=None, before=None):
    """A.T（规则的信号可调）/ B.T（1,500 円平盘）/ 核心 1655.T（700 円）；真实的立花适配器 + 模拟交易所。"""
    a = _frame(a_close or [1000.0] * n, a_open, entry=entry, dead=dead)
    b = _frame([1500.0] * n, entry=b_entry)
    core = _frame([700.0] * n)
    core["entry"] = False
    make = _maker({"A.T": a, "B.T": b, "1655.T": core}, pd.Series(bool(bear_all), index=core.index))
    eng = make()
    exch = exchange_cls(eng, cash=eng.st.cash_jpy if cash is None else cash)
    br = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=False, confirm_timeout_s=0.0)
    book = paths.state_dir() / f"book_{next(_SEQ)}.json"           # 同一个测试里建两套也互不干扰
    if before is not None:
        before(book)
    ux = UnifiedExecutor(eng, br, book, paper=False, check_clock=check_clock, clock=clock)
    lo = int(eng.gidx.searchsorted(core.index[5]))
    eng.prime(lo)
    return SimpleNamespace(eng=eng, exch=exch, b=br, ux=ux, k=lo, book=book, make=make)


def _days(r, until: int, open_phase=True) -> None:
    """第 r.k … until-1 天：开盘撮合 → 开盘后补单 → 收盘 → 收盘后的决策（下一交易日的单）。"""
    for k in range(r.k, until):
        r.exch.open(k)
        if open_phase:
            r.ux.open_phase()
        r.exch.close_day()
        r.exch.set_day(k + 1)
        r.ux.run_bar(k)
    r.k = until


def _new(r, hh: int, mm: int, check_clock=True, day=None) -> UnifiedExecutor:
    """新进程（同一账本、同一券商、同一引擎）：成交日（当前决策的下一交易日）hh:mm。"""
    d = day or next_trading_day(r.eng.gidx[r.k - 1].date())
    return UnifiedExecutor(r.eng, r.b, r.book, paper=False, check_clock=check_clock,
                           clock=lambda: dt.datetime.combine(d, dt.time(hh, mm), tzinfo=JST))


def _orders(ux, ticker=None, side=None):
    return [o for o in ux._active() if (ticker is None or o.ticker == ticker) and (side is None or o.side == side)]


# ────────── ① B7 开盘后补单：取价失败 / 还没寄り付き ──────────
class _PriceDown(SimExchange):
    """取价这一路整个失败（PRICE 虚拟 URL 出错 / 开盘高峰被限流）；REQUEST 那一路是好的。"""
    down = False

    def _price(self, p):
        if self.down:
            return {"p_errno": "99", "p_err": "サービス一時停止中"}
        return super()._price(p)


class _NoOpen(SimExchange):
    """这几只还没寄り付き（特別気配）：现在值 / 始値是空的。"""
    late: set = set()

    def _price(self, p):
        res = super()._price(p)
        s = self.spec
        for row in res.get(s.r_price_list) or []:
            if f"{row.get(s.r_price_code)}.T" in self.late:
                row.update({s.r_price: "", s.r_open: ""})
        return res


def _deferred_core(exchange_cls):
    """第一天：100 万全买 1655（限价 ×1.02 预留放不下）→ 余数留到开盘后（DEFERRED）。"""
    r = _setup(entry=(), exchange_cls=exchange_cls)
    _days(r, r.k + 1)
    d = [o for o in r.ux._active() if o.status == "DEFERRED"]
    assert d and d[0].ticker == "1655.T"
    r.exch.open(r.k)
    return r, d[0]


def test_quote_failure_keeps_every_deferred_order_and_marks_the_run_incomplete():
    r, o = _deferred_core(_PriceDown)
    n0 = r.exch.calls.get(NEW, 0)
    r.exch.down = True
    ux = _new(r, 9, 5, check_clock=False)
    ux.open_phase(final=False)
    o2 = next(x for x in ux.orders if x.cid == o.cid)
    assert o2.status == "DEFERRED" and o2.note.startswith(QUOTE_FAIL) and r.exch.calls.get(NEW, 0) == n0
    assert "09:20 再试" in ux.incomplete and ux.summary()["incomplete"] == ux.incomplete
    assert any(e["level"] == "warn" and QUOTE_FAIL in e["msg"] for e in ux.book["events"])
    ux2 = _new(r, 9, 20, check_clock=False)
    ux2.open_phase(final=True)                                # 09:20 也失败：仍然保留（没有下一次定时运行）
    assert "09:20 的重试也没取到" in ux2.incomplete
    _, short, body = daily_text(ux2.summary(), r.eng.st, None, False, 1_000_000)
    assert "｜★ 没做完" in short and "这次没做完" in body
    r.exch.down = False
    ux3 = _new(r, 9, 40, check_clock=False)
    ux3.open_phase(final=True)                                # 手动再跑一次：取到了 → 照常下
    o3 = next(x for x in ux3.orders if x.cid == o.cid)
    assert o3.status in ("SENT", "FILLED", "PARTIAL") and r.exch.calls[NEW] == n0 + 1 and ux3.incomplete is None


def test_deferred_order_left_by_a_quote_failure_is_missed_with_the_real_reason():
    r, o = _deferred_core(_PriceDown)
    r.exch.down = True
    r.ux.open_phase(final=True)
    r.exch.down = False
    r.exch.close_day()
    r.exch.set_day(r.k + 1)
    r.ux.run_bar(r.k)
    h = [x for x in r.ux.book["history"][-1]["orders"] if x["cid"] == o.cid][0]
    assert h["status"] == "MISSED" and h["note"].startswith(QUOTE_FAIL) and "与模拟盘出现差异" in h["note"]


def test_not_opened_yet_waits_at_0905_and_gives_up_at_0920_as_a_divergence():
    r, o = _deferred_core(_NoOpen)
    r.exch.late = {"1655.T"}
    ux = _new(r, 9, 5, check_clock=False)
    ux.open_phase(final=False)
    o1 = next(x for x in ux.orders if x.cid == o.cid)
    assert o1.status == "DEFERRED" and o1.note == NO_OPEN_WAIT and ux.incomplete is None
    assert any(NO_OPEN_WAIT in e["msg"] for e in ux.book["events"])
    ux2 = _new(r, 9, 20, check_clock=False)
    ux2.open_phase(final=True)
    o2 = next(x for x in ux2.orders if x.cid == o.cid)
    assert o2.status == "SKIPPED" and o2.note == NO_OPEN_FINAL and "休市" not in o2.note
    assert ux2.stats["model_diff"] == 1 and ux2.diffs and ux2.diffs[0]["ticker"] == "1655.T"


def test_rehearsal_mode_keeps_the_old_no_open_rule():
    """演练 / 测试一天只跑一次开盘后（final=None）：没有始値 = 那天没有 K 线 → 放弃，模型也不买（不记差异）。"""
    r, o = _deferred_core(_NoOpen)
    r.exch.late = {"1655.T"}
    r.ux.open_phase()
    o1 = next(x for x in r.ux.orders if x.cid == o.cid)
    assert o1.status == "SKIPPED" and "模型也不买" in o1.note and r.ux.stats["model_diff"] == 0


# ────────── ② B13 早上错过寄付 ──────────
def _late_case(hh, mm, market_open=True):
    """A.T 第 10 天进场、第 15 天死叉；B.T 第 15 天出买入信号 → 第 15 天收盘的决策：卖 A.T、买 B.T。
    早上的运行在成交日 hh:mm 才跑（Mac 睡着了）；market_open：交易所已经开盘（模拟交易所在第 16 天的交易时间里）。"""
    r = _setup(entry=(10,), dead=(15,), b_entry=(15,), bear_all=True)
    _days(r, 15)
    assert "A.T" in r.eng.st.pos
    r.exch.open(15)
    r.ux.open_phase()
    r.exch.close_day()
    r.exch.set_day(16)
    if market_open:
        r.exch.open(16)
    f = next_trading_day(r.eng.gidx[15].date())
    ux = UnifiedExecutor(r.eng, r.b, r.book, paper=False, check_clock=True,
                         clock=lambda: dt.datetime.combine(f, dt.time(hh, mm), tzinfo=JST))
    ux.morning([15])
    return r, ux, f


def test_late_morning_sells_with_a_day_limit_and_skips_buys():
    r, ux, _ = _late_case(9, 10)
    s = _orders(ux, "A.T", "SELL")[0]
    assert s.phase == "late" and s.status in ("SENT", "FILLED") and s.note.startswith(LATE_SELL_NOTE)
    sent = [o for o in r.exch.orders.values() if o["ticker"] == "A.T" and o["side"] == "SELL"][-1]
    assert sent["cond"] == r.exch.spec.cond_normal                       # 当日限り（不是寄付）
    assert sent["lim"] == round_to_tick(1000.0 * 0.995, "A.T", "SELL")     # 现价 −0.5%
    bb = _orders(ux, "B.T", "BUY")[0]
    assert bb.status == "SKIPPED" and bb.note == LATE_BUY_NOTE
    assert ux.stats["model_diff"] >= 1 and any(x["ticker"] == "B.T" and x["phase"] == "late" for x in ux.diffs)
    assert not any(o["ticker"] == "B.T" for o in r.exch.orders.values())
    assert any("早上错过寄付" in e["msg"] for e in ux.book["events"]) and not ux.blocked
    _, short, body = daily_text(ux.summary(), r.eng.st, None, False, 1_000_000)     # 通知看得到与模型的差异（EXE-4）
    assert "★ 与模型不同 1 笔" in short and "- ★ 与模型不同：买 B.T" in body and LATE_BUY_NOTE in body
    _, short_p, _ = daily_text(ux.summary(), r.eng.st, None, True, 1_000_000)
    assert "与模型不同" not in short_p                                               # 模拟账户不加


def test_late_sell_before_the_open_waits_for_the_0905_run():
    r, ux, f = _late_case(8, 56, market_open=False)
    s = _orders(ux, "A.T", "SELL")[0]
    assert s.status == "BLOCKED" and s.phase == "late" and "取不到现价" in s.note and not s.broker_id
    assert late_pending(ux.book) and not any(o["side"] == "SELL" and o["ticker"] == "A.T" and o["day"] == r.exch._day(16)
                                             for o in r.exch.orders.values())
    r.exch.open(16)
    ux2 = UnifiedExecutor(r.eng, r.b, r.book, paper=False, check_clock=True,
                          clock=lambda: dt.datetime.combine(f, dt.time(9, 5), tzinfo=JST))
    ux2.open_phase(final=False)
    s2 = _orders(ux2, "A.T", "SELL")[0]
    assert s2.status in ("SENT", "FILLED") and s2.broker_id and not late_pending(ux2.book)


def test_before_the_cutoff_the_morning_orders_are_opening_orders_as_before():
    r, ux, _ = _late_case(8, 50, market_open=False)
    s = _orders(ux, "A.T", "SELL")[0]
    assert s.phase == "morning" and s.status == "SENT"
    sent = [o for o in r.exch.orders.values() if o["ticker"] == "A.T" and o["side"] == "SELL"][-1]
    assert sent["cond"] == r.exch.spec.cond_opening
    assert _orders(ux, "B.T", "BUY")[0].status in ("SENT", "DEFERRED") and ux.stats["model_diff"] == 0


def test_after_the_close_the_late_rule_does_not_apply():
    _, ux, _ = _late_case(15, 30)
    assert all(o.status == "BLOCKED" and "寄付注文来不及" in o.note for o in ux._active())


# ────────── ③ LU-21 早上持仓核对不一致 ──────────
def test_morning_mismatch_blocks_the_late_retry_and_is_cleared_by_a_clean_check():
    r = _setup(entry=(10,), bear_all=True)
    _days(r, 10)
    r.exch.open(10)
    r.ux.open_phase()
    r.exch.close_day()
    r.exch.set_day(11)
    r.exch.pos["B.T"] = 100                                   # 有人在立花网站上买了一只执行器管的票
    f = next_trading_day(r.eng.gidx[10].date())
    ux = UnifiedExecutor(r.eng, r.b, r.book, paper=False, check_clock=True,
                         clock=lambda: dt.datetime.combine(f, dt.time(7, 40), tzinfo=JST))
    ux.run_bar(10)
    mm = ux.book["broker_mismatch"]
    assert mm["date"] == f.isoformat() and "持仓与券商不一致" in mm["text"]
    a = _orders(ux, "A.T", "BUY")[0]
    assert a.status == "BLOCKED"
    r.exch.open(11)
    late = UnifiedExecutor(r.eng, r.b, r.book, paper=False, check_clock=True,
                           clock=lambda: dt.datetime.combine(f, dt.time(9, 10), tzinfo=JST))
    late.morning([])                                          # 09:00 以后不再核对持仓：按早上记下的结果挡（不会变成「错过寄付」的处理）
    a2 = _orders(late, "A.T", "BUY")[0]
    assert a2.status == "BLOCKED" and "持仓与券商不一致" in a2.note and r.exch.calls.get(NEW, 0) == 0
    del r.exch.pos["B.T"]
    late.check_positions()                                    # 下一次核对一致 → 清掉
    assert "broker_mismatch" not in late.book


def test_morning_mismatch_keeps_deferred_buys_at_the_open():
    r, o = _deferred_core(SimExchange)
    f = next_trading_day(r.eng.gidx[r.k - 1].date())
    r.ux.book["broker_mismatch"] = {"date": f.isoformat(), "text": "持仓与券商不一致：B.T 状态 0 股 / 券商 100 股"}
    r.ux.save()
    n0 = r.exch.calls.get(NEW, 0)
    ux = UnifiedExecutor(r.eng, r.b, r.book, paper=False, check_clock=False,
                         clock=lambda: dt.datetime.combine(f, dt.time(9, 5), tzinfo=JST))
    ux.open_phase(final=False)
    assert next(x for x in ux.orders if x.cid == o.cid).status == "DEFERRED" and r.exch.calls.get(NEW, 0) == n0
    assert any("持仓与券商不一致" in e["msg"] for e in ux.book["events"])
    ux2 = UnifiedExecutor(r.eng, r.b, r.book, paper=False, check_clock=False,      # 别的日子记下的不算
                          clock=lambda: dt.datetime.combine(next_trading_day(f), dt.time(9, 5), tzinfo=JST))
    assert ux2._mismatch_today() is None


def test_morning_mismatch_holds_intraday_manual_orders_until_tomorrow():
    from test_manual_now import PX, _at, _morning, _paper, _quote, _req
    r = _paper("mm")
    _morning(r, until=14)
    assert "A.T" in r.eng.st.pos
    rq = _req(r, kind="sell", ticker="A.T")
    r.now["t"] = _at(r, 10, 0)
    today = r.now["t"].date()
    r.ux.book["broker_mismatch"] = {"date": today.isoformat(), "text": "持仓与券商不一致：B.T 状态 0 股 / 券商 100 股"}
    n0 = len(r.ux.orders)
    out = r.ux.now_phase(_quote(PX))
    it = r.ux.book["manual"]["items"][rq["id"]]
    assert out["later"] == 1 and out["placed"] == 0 and len(r.ux.orders) == n0
    assert it.get("hold") == today.isoformat() and "持仓核对不一致" in it["msg"] and "持仓与券商不一致" in r.ux.blocked


# ────────── ④ LU-22 成交日当天生效的拆股 ──────────
def test_split_effective_on_the_fill_day_adjusts_the_opening_order_once():
    base = _setup(entry=(10,), bear_all=True)
    _days(base, 11)
    o0 = _orders(base.ux, "A.T", "BUY")[0]
    q0, l0 = o0.qty, o0.limit
    r = _setup(entry=(10,), bear_all=True)
    _days(r, 10)
    f = next_trading_day(r.eng.gidx[10].date()).isoformat()
    r.ux.corp_provider = FakeActions({"A.T": [{"date": f, "dividend": 0.0, "split": 2.0}]})
    _days(r, 11)
    o = _orders(r.ux, "A.T", "BUY")[0]
    assert o.qty == int(q0 * 2 / 100) * 100 and o.limit == round_to_tick(l0 / 2, "A.T", "BUY")
    assert any("拆股 / 合并 1:2 生效" in e["msg"] for e in r.ux.book["events"])
    assert [s["cid"] for s in r.ux.book["split_pre"]] == [o.cid]
    q1, l1 = o.qty, o.limit
    r.ux.on_corp_action("A.T", f, 0.0, 2.0, 0.8)              # 第二天早上的公司行为同步：这笔已经按拆股后下了 → 不再调
    assert (o.qty, o.limit) == (q1, l1) and r.ux.book["splits"][-1]["ticker"] == "A.T"


def _split_day(adjusted: bool | None, k=2.0):
    """第 10 天收盘后的决策、成交日当天 A.T 拆股 1:k。adjusted=True：这次早上的行情已经按拆股调整过（Yahoo 把过去的收盘整段 ÷k）；
    None：没有上一次决策记下的收盘（判断不了）。"""
    r = _setup(entry=(10,), bear_all=True)
    _days(r, 10)
    f = next_trading_day(r.eng.gidx[10].date()).isoformat()
    r.ux.corp_provider = FakeActions({"A.T": [{"date": f, "dividend": 0.0, "split": k}]})
    if adjusted:
        j = r.eng.col["A.T"]
        for a in ("open", "high", "low", "close"):
            getattr(r.eng.A, a)[:, j] /= k
    if adjusted is None:
        r.ux.book.pop("closes_seen", None)
    _days(r, 11)
    return r, f


def test_split_on_the_fill_day_with_prices_already_adjusted_is_not_scaled_twice():
    """Yahoo 已经按拆股调整了过去的收盘（引擎的股数 / 限价已经是拆股后的）→ 照引擎的单，不再 ×k / ÷k。"""
    base = _setup(entry=(10,), bear_all=True)
    _days(base, 11)
    l0 = _orders(base.ux, "A.T", "BUY")[0].limit
    r, f = _split_day(adjusted=True)
    o = _orders(r.ux, "A.T", "BUY")[0]
    assert o.limit == round_to_tick(l0 / 2, "A.T", "BUY") and o.status in ("SENT", "DEFERRED")   # 不是 l0 / 4
    assert any("行情已经按拆股调整过" in e["msg"] for e in r.ux.book["events"])
    assert [s["cid"] for s in r.ux.book["split_pre"]] == [o.cid]               # 第二天的公司行为同步也不再调
    q1, l1 = o.qty, o.limit
    r.ux.on_corp_action("A.T", f, 0.0, 2.0, 0.8)
    assert (o.qty, o.limit) == (q1, l1)


def test_split_on_the_fill_day_reverse_split_keeps_the_limit_cap():
    """合并（k < 1）且行情已经调整：限价不 ×(1/k)（不能把「收盘 ×1.03」的上限去掉）。"""
    r, _ = _split_day(adjusted=True, k=0.5)
    o = _orders(r.ux, "A.T", "BUY")[0]
    c = float(r.eng.A.close[10, r.eng.col["A.T"]])
    assert o.limit <= c * 1.03 + 1e-9


def test_split_on_the_fill_day_without_a_reference_skips_the_buy():
    r, _ = _split_day(adjusted=None)
    o = _orders(r.ux, "A.T", "BUY")[0]
    assert o.status == "SKIPPED" and "判断不了" in o.note and r.ux.stats["model_diff"] >= 1
    assert not any(x["ticker"] == "A.T" for x in r.exch.orders.values())


def test_split_adjusted_order_retried_after_a_block_keeps_its_split_context():
    """第一次运行被挡（HALT）时按拆股调过的单：重试时股数不够一手 → SKIPPED（不再天天 BLOCKED）、LU-15 不比。"""
    r = _setup(entry=(10,), bear_all=True)
    _days(r, 10)
    f = next_trading_day(r.eng.gidx[10].date()).isoformat()
    r.ux.corp_provider = FakeActions({"A.T": [{"date": f, "dividend": 0.0, "split": 0.001}]})
    paths.halt_file().write_text("HALT\n", encoding="utf-8")
    _days(r, 11)
    o = _orders(r.ux, "A.T", "BUY")[0]
    assert o.status == "BLOCKED" and o.qty == 0
    paths.halt_file().unlink()
    ux2 = _new(r, 8, 35, check_clock=False)
    ux2.corp_provider = None
    ux2.place(10)
    o2 = _orders(ux2, "A.T", "BUY")[0]
    assert o2.status == "SKIPPED" and "不够一手" in o2.note


class _SendFail(SimExchange):
    """下一笔新规注文的请求出错：not_sent = 请求根本没发出（DNS 解析失败）；否则 = 可能已到达（超时）。"""
    fail: BaseException | None = None

    def get_json(self, url, payload):
        if self.fail is not None and payload.get(self.spec.f_clmid) == NEW:
            e, self.fail = self.fail, None
            raise e
        return super().get_json(url, payload)


def test_executor_retries_an_order_that_was_never_sent_and_stops_on_a_maybe_sent_one():
    """B2：请求根本没发出（DNS / 连接被拒）→ BLOCKED，这次运行不停、同一决策的下一次运行（08:35）重发；
    可能已到达（超时）→ ERROR（状态不明），下一次运行停下等人工（ExecutorError）。"""
    import socket
    import urllib.error
    from qbreak.live_unified import ExecutorError
    r = _setup(entry=(10,), bear_all=True, exchange_cls=_SendFail)
    _days(r, 10)
    r.exch.fail = urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided"))
    _days(r, 11)                                                      # 不抛
    o = _orders(r.ux, "A.T", "BUY")[0]
    assert o.status == "BLOCKED" and "没连上立花，没发单" in o.note and not o.broker_id
    ux2 = _new(r, 8, 35, check_clock=False)
    ux2.place(10)
    o2 = _orders(ux2, "A.T", "BUY")[0]
    assert o2.status == "SENT" and o2.broker_id
    r2 = _setup(entry=(10,), bear_all=True, exchange_cls=_SendFail)
    _days(r2, 10)
    r2.exch.fail = TimeoutError("timed out")
    _days(r2, 11)
    assert _orders(r2.ux, "A.T", "BUY")[0].status == "ERROR"
    with pytest.raises(ExecutorError, match="状态不明"):
        _days(r2, 12)


def test_no_corp_data_means_orders_as_before():
    r = _setup(entry=(10,), bear_all=True)
    r.ux.corp_provider = FakeActions({})
    _days(r, 11)
    assert "split_pre" not in r.ux.book and _orders(r.ux, "A.T", "BUY")[0].status in ("SENT", "DEFERRED")


# ────────── ⑤ LU-15 立花的前日終値 vs 决策用的收盘 ──────────
class _BadPrev(SimExchange):
    """立花那边的前日終値和行情不一样（例如 Yahoo 还没反映拆股）。"""
    bad: dict = {}

    def _price(self, p):
        res = super()._price(p)
        s = self.spec
        for row in res.get(s.r_price_list) or []:
            t = f"{row.get(s.r_price_code)}.T"
            if t in self.bad and row.get(s.r_prev_close):
                row[s.r_prev_close] = repr(float(row[s.r_prev_close]) * self.bad[t])
        return res


def test_prev_close_gap_blocks_the_buy_but_only_warns_on_a_sell():
    r = _setup(entry=(10,), dead=(15,), bear_all=True, exchange_cls=_BadPrev)
    r.exch.bad = {"A.T": 0.9}
    _days(r, 11)
    a = _orders(r.ux, "A.T", "BUY")[0]
    assert a.status == "BLOCKED" and "立花前日終値" in a.note and "差 10.0%" in a.note and r.exch.calls.get(NEW, 0) == 0
    r.exch.bad = {"A.T": 0.98}                                # 差 2%：照常（门槛 3%）
    ux = _new(r, 8, 35, check_clock=False)
    ux.morning([])
    assert _orders(ux, "A.T", "BUY")[0].status == "SENT"
    r.ux = ux
    _days(r, 16)
    assert "A.T" in r.eng.st.pos or _orders(r.ux, "A.T", "SELL")
    r2 = _setup(entry=(10,), dead=(15,), bear_all=True, exchange_cls=_BadPrev)
    _days(r2, 15)
    r2.exch.bad = {"A.T": 0.5}
    _days(r2, 16)
    s = _orders(r2.ux, "A.T", "SELL")[0]
    assert s.status == "SENT" and any("卖单照下" in e["msg"] for e in r2.ux.book["events"])


def test_prev_close_is_not_compared_on_the_demo():
    r = _setup(entry=(10,), bear_all=True, exchange_cls=_BadPrev)
    r.b.demo = True                                           # デモ是假价格：不比
    r.exch.bad = {"A.T": 0.5}
    _days(r, 11)
    assert _orders(r.ux, "A.T", "BUY")[0].status in ("SENT", "DEFERRED")


# ────────── ⑥ C-11 异常熔断 ──────────
def test_breaker_blocks_every_order_when_the_rule_orders_are_impossible(monkeypatch):
    r = _setup(entry=(10,), bear_all=True)
    _days(r, 10)
    eng = r.eng
    k = r.k - 1
    many = [{"side": "SELL", "ticker": "A.T", "qty": 100}] * 11       # (4 + 1) × 2 = 10 笔是上限
    assert "超过上限 10 笔" in r.ux._breaker(k, many)
    assert r.ux._breaker(k, many[:10]) is None
    big = [{"side": "BUY", "ticker": "A.T", "qty": 3000, "limit": 1030.0}]    # ¥309 万 > 权益 ¥100 万 × 2.2
    assert "× 2.2" in r.ux._breaker(k, big)
    manual = [{"side": "SELL", "ticker": "A.T", "qty": 100, "reason": "manual_trim"}] * 11
    assert r.ux._breaker(k, manual) is None                   # 手动指令另外算
    monkeypatch.setattr(eng, "todo", lambda i: {"JP": [{"side": "SELL", "ticker": t, "qty": 100} for t in ("A.T", "B.T")] * 6})
    ux = _new(r, 7, 40, check_clock=False)
    ux.morning([])
    assert ux.blocked.startswith("异常熔断") and r.exch.calls.get(NEW, 0) == 0
    assert all(o.status == "BLOCKED" and "异常熔断" in o.note for o in ux._active())
    assert any(e["level"] == "error" and "异常熔断" in e["msg"] for e in ux.book["events"])


@pytest.mark.parametrize("seed", [7, 23])
def test_breaker_never_fires_in_the_rehearsals(seed):
    make, start = _synth(seed)
    r = rehearse(make, start, kind="tachibana-sim")
    assert not any("异常熔断" in e["msg"] for e in r["ux"].book.get("events") or [])


# ────────── ⑦ C-14 零股 ──────────
def test_odd_lot_sell_sends_whole_lots_and_records_the_rest():
    r = _setup(entry=(10,), dead=(15,), bear_all=True)
    _days(r, 13)
    ps = r.eng.st.pos["A.T"]
    ps.shares += 50                                           # 拆股 / 合并之后多出 50 股（单元未满）
    r.exch.pos["A.T"] += 50
    _days(r, 16)
    s = _orders(r.ux, "A.T", "SELL")[0]
    assert s.sent_qty == s.qty - 50 and s.status == "SENT"
    sent = [o for o in r.exch.orders.values() if o["ticker"] == "A.T" and o["side"] == "SELL"][-1]
    assert sent["qty"] % 100 == 0
    ol = r.ux.book["odd_lots"]["A.T"]
    assert ol["shares"] == 50 and "端株手续费 0.55%" in ol["text"]
    _days(r, 17)                                              # 整数手成交；剩下 50 股仍是待卖 → 不发（天天重发也会被拒）
    assert r.eng.st.pos["A.T"].shares == 50
    s2 = _orders(r.ux, "A.T", "SELL")[0]
    assert s2.status == "SKIPPED" and s2.note.startswith("零股") and not s2.broker_id
    assert any("剩下 50 股不足一手" in e["msg"] for e in r.ux.book["events"])
    sm = r.ux.summary()
    _, short, body = daily_text(sm, r.eng.st, None, False, 1_000_000)
    assert "★ 零股 1 只要在立花网站卖" in short and "A.T 有 50 股不足一手" in body


def test_paper_account_never_splits_odd_lots():
    make, _ = _synth(7)
    eng = make()
    b = _MemPaper(state_file=paths.state_dir() / "p.json", initial_cash=1e6, exec_cfg=eng.ex["JP"], market="JP")
    ux = UnifiedExecutor(eng, b, paths.state_dir() / "pb.json", paper=True, check_clock=False)
    from qbreak.live_unified import ExecOrder
    t = next(iter(eng.col))
    assert ux._odd_lot(ExecOrder("c", t, "SELL", "stock", 150, "2026-01-01"), 150) == 0


def test_odd_lot_record_from_the_adapter_keeps_tachibanas_unit():
    """适配器按立花売買単位拆出的零股（引擎的一手不同）：记录里是立花的一手，第二天早上的清理也按它（ADP-3）。"""
    r = _setup(entry=(), bear_all=True)
    _days(r, r.k + 1)
    j = r.eng.col["1655.T"]
    r.eng.lots[j] = 1                                                   # 行情配置的一手是 1，立花的是 10
    r.eng.st.core_units["1655.T"] = 15
    r.ux._note_odd("1655.T", 5, 10)
    assert r.ux.book["odd_lots"]["1655.T"]["lot"] == 10
    r.ux._odd_cleanup()
    assert r.ux.book["odd_lots"]["1655.T"]["shares"] == 5                  # 引擎的一手 1 不会把它当成「没有零股」删掉
    r.eng.st.core_units["1655.T"] = 20
    r.ux._odd_cleanup()
    assert "odd_lots" not in r.ux.book


# ────────── ⑧ B11 实盘起始本金 ──────────
def test_first_cash_sync_sets_the_live_starting_capital_without_a_false_alarm():
    r = _setup(entry=(), bear_all=True, cash=300_000.0)
    _days(r, r.k + 1)
    assert r.ux.book["capital_jpy"] == 300_000.0 and r.ux.book["live_start"]["cash_jpy"] == 300_000.0
    assert not any("现金突然变化" in e["msg"] or "现金差" in e["msg"] for e in r.ux.book["events"])
    assert "cash_drift" not in r.ux.book and r.eng.st.cash_jpy == 300_000.0
    assert start_capital(r.ux.book, 1_000_000) == 300_000.0 and start_capital({}, 1_000_000) == 1_000_000.0
    _days(r, r.k + 1)
    cap = start_capital(r.ux.book, 1_000_000)
    _, short, body = daily_text(r.ux.summary(), r.eng.st, None, False, cap, invested=invested_jpy(cap, r.ux.book))
    eq = float(r.eng.st.history[-1][1])
    assert f"累计 {(eq / 300_000 - 1) * 100:+.2f}%" in short
    r.exch.cash += 200_000.0                                  # 之后的入金：照常提醒登记
    _days(r, r.k + 1)
    assert any("现金突然变化 +200,000 円" in e["msg"] for e in r.ux.book["events"])


def test_starting_capital_waits_for_the_first_funded_sync():
    """任务先装好、账户还没入金（买付可能額 ¥0）：不把起始本金定成 0；入金之后第一次核对才定，不误报「现金突然变化」。"""
    r = _setup(entry=(), bear_all=True, cash=0.0)
    _days(r, r.k + 2)
    assert "capital_jpy" not in r.ux.book and r.ux.book.get("live_start_wait") and r.eng.st.cash_jpy == 0.0
    r.exch.cash += 300_000.0
    _days(r, r.k + 1)
    assert r.ux.book["capital_jpy"] == 300_000.0 and "live_start_wait" not in r.ux.book
    assert start_capital(r.ux.book, 1_000_000) == 300_000.0
    assert not any("现金突然变化" in e["msg"] for e in r.ux.book["events"])


def test_deposit_registered_before_the_first_run_is_part_of_the_starting_capital():
    r = _setup(entry=(), bear_all=True, cash=300_000.0, before=lambda bk: register_flow(bk, 300_000, "开户入金"))
    _days(r, r.k + 1)
    assert flows(r.ux.book) == [] and invested_jpy(start_capital(r.ux.book, 1e6), r.ux.book) == 300_000.0
    assert any("算进起始本金" in e["msg"] for e in r.ux.book["events"])


def test_paper_account_keeps_the_sim_json_capital():
    make, start = _synth(7)
    r = rehearse(make, start, kind="paper")
    assert "capital_jpy" not in r["ux"].book


# ────────── ⑨ B4 账本备份 / 读坏不新开 / 恢复 ──────────
def _write_book(p, n=0):
    p.write_text(json.dumps({"state": {"last_date": "2026-10-08", "cash_jpy": 1000.0 + n}, "orders": []}), encoding="utf-8")


def _t(m, s=0):
    return dt.datetime(2026, 10, 9, 7, m, s, tzinfo=JST)


def test_backup_dedupes_and_keeps_the_newest():
    p = paths.state_dir() / "live_unified_tachibana.json"
    assert book_backup.backup(p) is None                       # 还没有账本
    _write_book(p)
    b1 = book_backup.backup(p, _t(40))
    assert b1.name == "live_unified_tachibana_20261009-074000.json"
    _write_book(p, 1)
    assert book_backup.backup(p, _t(40, 30)) is None          # 同一分钟不重复
    assert book_backup.backup(p, _t(41)) is not None
    assert book_backup.backup(p, _t(42)) is None              # 内容没变不重复
    for i in range(5):
        _write_book(p, 10 + i)
        book_backup.backup(p, _t(43 + i), keep=3)
    names = [x.name for x in book_backup.list_backups(p)]
    assert len(names) == 3 and names[0].endswith("074700.json")
    (paths.state_dir() / "live_unified_tachibana_demo.json").write_text("{}", encoding="utf-8")
    book_backup.backup(paths.state_dir() / "live_unified_tachibana_demo.json", _t(50))
    assert len(book_backup.list_backups(p)) == 3              # デモ的备份不混进本番
    p.write_text("{broken", encoding="utf-8")
    assert book_backup.backup(p, _t(55)) is None              # 读坏的账本不覆盖备份


def test_corrupt_or_missing_live_book_stops_instead_of_starting_over():
    p = paths.state_dir() / "live_unified_tachibana.json"
    assert book_backup.problem(p) is None                     # 第一次运行：没有账本、没有备份
    _write_book(p)
    assert book_backup.problem(p) is None
    book_backup.backup(p, _t(40))
    p.write_text('{"state": {"last_da', encoding="utf-8")
    why = book_backup.problem(p)
    assert "账本读不了" in why and ".corrupt." in why and "restore --broker tachibana --list" in why and not p.exists()
    assert "账本读不了" in book_backup.problem(p)             # 别的程序已经改了名：照样停下
    for c in paths.state_dir().glob("*.corrupt.*"):
        c.unlink()
    assert "不见了" in book_backup.problem(p)                 # 账本没了、但有备份：不新开
    assert str(paths.home()) not in why                       # 只有文件名，没有本机路径


def test_cli_refuses_a_corrupt_live_book(capsys):
    import run
    p = paths.state_dir() / "live_unified_tachibana.json"
    p.write_text("{oops", encoding="utf-8")
    assert run.main(["live-u", "--broker", "tachibana", "--flow=1000"]) == 3
    out = capsys.readouterr().out
    assert "账本读不了" in out and "不新开账本" in out
    assert not p.exists() and not list(paths.state_dir().glob("live_unified_tachibana.json"))   # 没有新开账本
    from qbreak import run_status as RS
    assert RS.read("tachibana")["ok"] is False


def test_cli_backs_up_before_each_run_and_restores(capsys):
    import run
    p = paths.state_dir() / "live_unified_tachibana.json"
    _write_book(p)
    assert run.main(["live-u", "--broker", "tachibana", "--flow=1000"]) == 0
    baks = book_backup.list_backups(p)
    assert len(baks) == 1 and json.loads(baks[0].read_text(encoding="utf-8"))["state"]["cash_jpy"] == 1000.0
    assert run.main(["live-restore", "--list"]) == 0
    out = capsys.readouterr().out
    assert baks[0].name in out and "决策日 2026-10-08" in out
    assert run.main(["live-restore", "../x.json"]) == 2       # 只认这个账本的备份文件名
    assert run.main(["live-restore", baks[0].name]) == 0
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "flows" not in d and "从备份恢复账本" in d["events"][-1]["msg"]
    assert len(book_backup.list_backups(p)) == 2              # 恢复前的账本另存了一份


def test_restore_keeps_the_current_book_and_rejects_bad_names():
    p = paths.state_dir() / "live_unified_tachibana.json"
    _write_book(p)
    b1 = book_backup.backup(p, _t(40))
    _write_book(p, 5)
    with pytest.raises(ValueError):
        book_backup.restore(p, "live_unified_tachibana_demo_20261009-074000.json")
    with pytest.raises(FileNotFoundError):
        book_backup.restore(p, "live_unified_tachibana_20261009-070000.json")
    r = book_backup.restore(p, b1.name, now=_t(41))
    assert r["from"] == b1.name and r["saved"] and json.loads(p.read_text(encoding="utf-8"))["state"]["cash_jpy"] == 1000.0
    saved = book_backup.backup_dir() / r["saved"]
    assert json.loads(saved.read_text(encoding="utf-8"))["state"]["cash_jpy"] == 1005.0


def test_resolve_backs_up_the_book_first():
    from qbreak.live_unified import resolve_order
    p = paths.state_dir() / "live_unified_tachibana.json"
    p.write_text(json.dumps({"state": {}, "orders": [{"cid": "X", "status": "ERROR"}]}), encoding="utf-8")
    resolve_order(p, "X", 0, 0.0)
    assert len(book_backup.list_backups(p)) == 1


def test_late_pending_only_counts_unsent_late_sells():
    d = "2026-10-08"
    o = {"decided_on": d, "side": "SELL", "kind": "stock", "status": "BLOCKED", "phase": "late", "note": "x"}
    b = {"state": {"last_date": d}, "orders": [o]}
    assert late_pending(b)
    assert not late_pending({**b, "orders": [{**o, "status": "SENT", "broker_id": "1"}]})
    assert not late_pending({**b, "orders": [{**o, "phase": "morning", "note": "存在 HALT 文件"}]})
    assert late_pending({**b, "orders": [{**o, "phase": "morning", "note": "已过成交日 x 的 08:55：寄付注文来不及"}]})
