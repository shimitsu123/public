"""2026-10-14 复核修正（第二轮，事后）：
ARM  没 ARM 挡下的单不当成 HALT（说明、连续没发出的天数、没卖掉的记录、09:30 自检都照常）；
G5   盘中凑钱的核心 ETF 卖单受理了、还没成交 → 买入等它成交再下（以前马上作废、核心照样卖了）；
G7   开盘没下成重新排队之后不再留着上一次的「没发出」；
G20  HALT 中面板开盘前不叫 --retry；当前决策有状态不明的单 → 面板不叫执行器（撤单除外）、模拟账户不补跑；
G9   模拟账户补跑 = 照常的运行（不加 --retry）；
G16  15:30 失效的盘中单按下单那天写（不写「今天 / 明天」）；
G3   盘中前面有一笔状态不明 → 剩下的指令写「先登记」，不写「明天开盘处理」。"""
import datetime as dt
import json

from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak import run_status as RS
from qbreak import watchdog as WD
from qbreak.brokers import tachibana as tb
from qbreak.brokers.tachibana_sim import SimExchange
from qbreak.calendar_jp import JST

from test_manual_buy import _buy
from test_manual_orders import TAG, _Run, _sell_req
from test_not_placed_safety import _Net
from test_panel import _book
from test_panel_notify_gaps import _clock, _paper_agent, _Proc


def _saved() -> dict:
    return json.loads((paths.state_dir() / "book.json").read_text(encoding="utf-8"))


# ────────── ARM：没 ARM ≠ HALT ──────────
def test_arm_block_is_not_called_halt_and_counts_as_unsent():
    r = _Run([1000.0] * 40, entry=(10,), bear_all=True)
    r.until(14)
    r.b.require_arm = True                                     # 立花本番要 ARM 文件；没有 → 适配器挡下（说明里有「…或建 HALT」字样）
    rec = _sell_req(r)
    for _ in range(3):
        r.day()
    assert not paths.halt_file().exists()
    it = r.item(rec["id"])
    assert "HALT 生效中" not in it["msg"] and "HALT 解除后" not in it["msg"]
    u = it.get("unsent") or {}
    assert int(u.get("n") or 0) == 3 and not u.get("halt")     # 以前当成 HALT：一天都不算
    o = next(x for x in r.ux.orders if x.ticker == "A.T" and x.side == "SELL")
    assert o.status == "BLOCKED" and not r.ux._halt_note(o) and not RS.is_halt(o.__dict__)
    assert int(((r.ux.book.get("unsold") or {}).get("A.T") or {}).get("n") or 0) >= 2   # G26 照常记没卖掉
    exp = str(r.eng.gidx[r.k - 1].date())
    out = WD._manual_unsent(_saved(), exp, r.at(r.k - 1).date(), True)
    assert out and out[0].startswith(f"决策 {exp} 有 1 笔手动指令的单没发出")
    assert any("连续 3 个交易日没发出" in s for s in out)


def test_halt_note_only_matches_the_halt_marker():
    from qbreak.live_unified import HALT_WAIT, ExecOrder, UnifiedExecutor
    halt = lambda note: UnifiedExecutor._halt_note(ExecOrder(cid="c", ticker="A.T", side="SELL", kind="stock", qty=100,   # noqa: E731
                                                             decided_on="2026-10-05", status="BLOCKED", note=note))
    assert halt(f"{RS.HALT_NOTE}（x）") and halt(f"{HALT_WAIT}（{RS.HALT_NOTE}）")
    assert not halt("没有 ARM 文件：要停用 = 删掉它或建 HALT") and not halt("行情没更新")


# ────────── G5：凑钱的核心卖单没成交 → 等成交再买 ──────────
class _CoreSellWaits(SimExchange):
    """盘中（当日限り）的核心 ETF 1655 卖单受理了但不当场成交（挂着）。"""

    def _new_order(self, p):
        s = self.spec
        if p.get(s.f_condition) == s.cond_normal and p.get(s.f_code) == "1655" and p.get(s.f_side) == s.side_sell:
            ph = self.phase
            self.phase = "x"
            try:
                return super()._new_order(p)
            finally:
                self.phase = ph
        return super()._new_order(p)


def _again(r, hh: int, mm: int) -> dict:
    """同一个成交日稍后再跑一次盘中的手动指令（面板 10 分钟后再叫）。"""
    r.now["t"] = dt.datetime.combine(r.eng.gidx[r.k].date(), dt.time(hh, mm), tzinfo=JST)
    old = tb._sleep, r.b.confirm_timeout_s
    tb._sleep, r.b.confirm_timeout_s = (lambda s: None), 5.0
    try:
        return r.ux.now_phase(r.quote)
    finally:
        tb._sleep, r.b.confirm_timeout_s = old


def test_intraday_buy_waits_for_the_funding_core_sell_to_fill():
    r = _Run([1000.0] * 30, exchange_cls=_CoreSellWaits, entry=(10,))
    r.until(14)
    _buy(r, id="M-c")
    r.session(10, 0)
    it = r.item("M-c")
    core = [o for o in r.ux.orders if o.ticker == "1655.T" and o.phase == "now"]
    assert core and core[0].status in ("SENT", "PARTIAL") and int(core[0].filled_qty or 0) == 0
    assert it["status"] == "pending" and "还没成交：等成交之后再买" in it["msg"], it["msg"]   # 以前：rejected「现金 + 核心 ETF 不够」
    assert it.get("fund_wait") == [core[0].cid]
    n_core = len(core)
    _again(r, 10, 11)                                          # 还没成交：再等，不再卖一次核心
    it = r.item("M-c")
    assert it["status"] == "pending" and "还没成交" in it["msg"]
    assert len([o for o in r.ux.orders if o.ticker == "1655.T" and o.phase == "now"]) == n_core
    so = next(o for o in r.exch.orders.values() if o["ticker"] == "1655.T" and o["side"] == "SELL" and o["status"] == "1")
    r.exch._fill(so, float(r.eng.A.open[r.k, r.eng.col["1655.T"]]))   # 卖单成交了 → 钱进余力
    _again(r, 10, 22)
    it = r.item("M-c")
    assert it["status"] == "placed" and "fund_wait" not in it, it
    assert any(o.ticker == "B.T" and o.side == "BUY" and o.phase == "now" and o.status in ("SENT", "FILLED", "PARTIAL")
               for o in r.ux.orders)
    assert len([o for o in r.ux.orders if o.ticker == "1655.T" and o.phase == "now"]) == n_core


# ────────── G7：重新排队之后不留上一次的「没发出」 ──────────
def test_requeue_drops_the_previous_unsent_mark():
    r = _Run([1000.0] * 30, entry=(10,))
    r.until(14)
    _buy(r, id="M-q")
    r.ux._breaker = lambda k, todo: "异常熔断：测试"
    r.day()
    del r.ux._breaker
    r.ux.blocked = None
    r.day()
    x = r.item("M-q")
    assert x["status"] == "placed"
    assert MO.status_text(x) != "没发出，等再下" and not (x.get("unsent") or {}).get("last")
    assert set(x.get("unsent") or {}) <= {"n"}


# ────────── G20：HALT / 状态不明时面板不叫执行器 ──────────
def test_trigger_does_not_spawn_retries_while_halted(monkeypatch):
    now, step = _clock(monkeypatch, dt.datetime(2026, 10, 6, 7, 45, tzinfo=JST))
    calls = []
    trg = panel.Trigger(run=lambda tag, mode="retry": calls.append(mode) or _Proc(0), clock=lambda: now["t"],
                        mono=lambda: now["m"], notify=lambda *a: None)
    halted = {"cid": "U2026-10-05-SELL-7203.T", "ticker": "7203.T", "side": "SELL", "decided_on": "2026-10-05",
              "status": "BLOCKED", "qty": 100, "note": f"{RS.HALT_NOTE}（不下单）"}
    bk = _book(last="2026-10-05", orders=[halted])
    MO.append("paper", {"kind": "sell", "ticker": "7203"})
    paths.halt_file().write_text("test", encoding="utf-8")
    assert not MO.due("paper", bk, now["t"])
    for _ in range(int(70 * 60 / 30)):                         # 07:45〜08:55：以前每 3 分钟叫一次什么都不做的 --retry
        trg.check()
        step(30)
    assert calls == []
    paths.halt_file().unlink()                                 # 对照：没有 HALT 照常叫
    now["t"] = dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST)
    assert MO.due("paper", bk, now["t"]) and trg.check() == ["paper"] and calls == ["retry"]


def test_trigger_does_not_spawn_while_an_order_is_unknown(monkeypatch):
    now, step = _clock(monkeypatch, dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST))
    calls = []
    trg = panel.Trigger(run=lambda tag, mode="retry": calls.append(mode) or _Proc(0), clock=lambda: now["t"],
                        mono=lambda: now["m"], notify=lambda *a: None)
    unk = {"cid": "U2026-10-05-BUY-6758.T", "ticker": "6758.T", "side": "BUY", "decided_on": "2026-10-05", "status": "ERROR",
           "qty": 100, "note": "发送途中断开"}
    _book(last="2026-10-05", orders=[unk])
    MO.append("paper", {"kind": "sell", "ticker": "7203"})
    assert trg.check() == []                                   # 开盘前：执行器登记之前每次都停下 → 不叫（以前连叫 3 次 → 暂停 + 通知）
    now["t"] = dt.datetime(2026, 10, 6, 10, 0, tzinfo=JST)
    MO.append("paper", {"kind": "sell", "ticker": "7203"}, clock=lambda: now["t"])
    for _ in range(20):                                        # 盘中也一样
        step(30)
        assert trg.check() == []
    assert calls == [] and "paper" not in trg.paused
    _book(last="2026-10-05", orders=[{**unk, "status": "SENT"}])   # 对照：登记了 → 照常叫
    step(60)
    assert trg.check() == ["paper"] and calls == ["now"]


def test_paper_catch_up_skips_unknown_orders_and_runs_normally(monkeypatch):
    now, step = _clock(monkeypatch, dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST))
    calls = []
    trg = panel.Trigger(run=lambda tag, mode="retry": calls.append(mode) or _Proc(0), clock=lambda: now["t"],
                        mono=lambda: now["m"], notify=lambda *a: None)
    _paper_agent()
    unk = {"cid": "U2026-10-02-BUY-6758.T", "ticker": "6758.T", "side": "BUY", "decided_on": "2026-10-02", "status": "SENDING",
           "qty": 100, "note": ""}
    _book(last="2026-10-02", orders=[unk])                     # 07:40 没跑完，而且有一笔状态不明：补跑也会停下
    for _ in range(10):
        trg.check()
        step(30)
    assert calls == []
    _book(last="2026-10-02")                                   # 对照：没有状态不明的单 → 补跑
    for _ in range(6):
        trg.check()
        step(30)
    assert calls == ["catchup"]


def test_catch_up_is_a_normal_run_not_a_retry():
    a = panel.Trigger._argv("paper", "catchup")
    assert a[-3:] == ["run", "--broker", "paper"] and "--retry" not in a
    assert panel.Trigger._argv("paper", "retry")[-1] == "--retry"
    assert panel.Trigger._argv("tachibana", "now")[-4:] == ["--broker", "tachibana", "--phase", "now"]
    assert panel.Trigger._argv("tachibana_demo", "cancel")[-3:] == ["--phase", "cancel", "--demo"]


# ────────── G16：失效的盘中单按下单那天写 ──────────
def test_lapsed_intraday_orders_are_described_by_their_day(monkeypatch):
    it = {"id": "M-now-sell-1", "kind": "sell", "ticker": "7203.T", "status": "placed", "now": True, "fill_day": "2026-10-06",
          "side": "SELL", "shares": 200, "at": "2026-10-06T10:00:00+09:00", "msg": "盘中已下单，等成交（今天有效）"}
    at = lambda h, m, d=6: dt.datetime(2026, 10, d, h, m, tzinfo=JST)     # noqa: E731
    assert MO.status_text(it, at(14, 0)) == "盘中已下单" and MO.msg_text(it, at(14, 0)) == it["msg"]   # 还挂着：照旧
    for t in (at(15, 40), at(7, 0, 7)):                        # 收盘后 / 第二天早上对账之前
        assert MO.status_text(it, t) == "盘中的单已失效"
        m = MO.msg_text(it, t)
        assert m.startswith("10/06 盘中的卖单已在 15:30 失效") and "下一次开盘再卖" in m and "今天" not in m and "明天" not in m
    part = {**it, "fill": {"qty": 100}}
    assert MO.status_text(part, at(7, 0, 7)) == "盘中部分成交，其余已失效" and "（成交 100 / 200 股）" in MO.msg_text(part, at(7, 0, 7))
    buy = {**it, "kind": "buy", "side": "BUY"}
    assert "没成交的部分不会再买" in MO.msg_text(buy, at(15, 40))
    assert MO.msg_text({**it, "cancel_req": "M-x"}, at(15, 40)) == it["msg"]   # 已经撤回：照撤回的说明
    w = MO.now_sell_withdrawn(it)
    assert w.startswith("10/06 盘中的单已在 15:30 失效：撤回之后下一次开盘不再卖") and "10/06 已经成交的部分照记" in w
    assert "明天" not in MO.NOW_SELL_WITHDRAWN and "明天" not in MO.NOW_BUY_LAPSED
    st = {"last_date": "2026-10-05", "cash_jpy": 500_000.0, "history": [["2026-10-05", 1_000_000.0, 0, 0, 150]],
          "pos": {"7203.T": {"shares": 200, "entry_px": 2500.0, "entry_date": "2026-09-01", "stop_px": 2325.0,
                             "last_close": 2600.0}}, "pending_exit": {"7203.T": "manual"}, "core_units": {}}
    (paths.state_dir() / "live_unified_paper.json").write_text(json.dumps(
        {"state": st, "orders": [], "manual": {"items": {"M-now-sell-1": it}, "blocks": {}, "trims": {}, "adds": {}, "buys": {}}},
        ensure_ascii=False), encoding="utf-8")
    h = panel.render("paper", "t" * 40, at(7, 0, 7))
    assert "data-wtxt='10/06 盘中的单已在 15:30 失效" in h and "盘中的单已失效" in h


# ────────── G3：前面有一笔状态不明 → 先登记 ──────────
def test_intraday_unknown_tells_to_register_not_tomorrow(monkeypatch):
    monkeypatch.setattr(tb, "_sleep", lambda s: None)
    r = _Run([1000.0] * 40, exchange_cls=_Net, entry=(10,), bear_all=True)
    r.until(13)
    _sell_req(r)
    buy = _sell_req(r, t="B.T", kind="buy", unit="shares", value=100)
    r.exch.mode = "on"
    r.session(10, 0)
    it = r.item(buy["id"])
    assert it["status"] == "pending" and it["msg"].endswith(MO.UNK_LATER) and "明天开盘处理" not in it["msg"]
    assert MO.status_text(it) == "等登记状态不明的单"
    assert MO.status_text({**it, "msg": "取不到现价 → 明天开盘处理"}) == "明天开盘"
