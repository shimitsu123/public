"""立花实盘缺口 B 组的人工操作（qbreak/live_ops.py；B1 撤单、B2 状态不明的单的候选、B3 持仓核对 / 人工代下登记）：
① 撤单：模拟交易所上撤还挂着的寄付单 → CANCELLED、第二天按「没成交」对账；部分成交后撤 → 成交的部分照记；已经全部成交 → 撤不了、不改；
   模拟账户撤排队单（开盘前）；HALT 时也能撤；面板的撤单指令 → 执行器撤（不建引擎）；手动指令的单被撤 → 指令也撤回；规则的卖单被撤 → 明天再下；
② 状态不明的单：注文一覧里找候选（股数相同的排前面 / 受付时刻近的排前面 / 没有候选）；运行状态与面板显示候选；
③ 持仓核对（可能原因、登记草稿）与人工代下登记（各分支、拒绝、备份、核对之后一致）；liveu.sh 子命令的参数。
全部用模拟交易所 / 假券商 / 临时数据目录：不联网、不调真的 security / launchctl。"""
import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak import run_status as RS
from qbreak.brokers.paper import PaperBroker
from qbreak.brokers.tachibana import TachibanaBroker
from qbreak.brokers.tachibana_sim import SimExchange
from qbreak.calendar_jp import JST, next_trading_day
from qbreak.config import StrategyParams
from qbreak.live_unified import ExecutorError, UnifiedExecutor
from qbreak.unified import UnifiedEngine

from test_live_unified import CC, CFG, EX, NEW, _frame, _maker

ROOT = Path(__file__).resolve().parent.parent
BOOK_T = "live_unified_tachibana.json"
TA, TB, TC = "7203.T", "6758.T", "8306.T"                     # 合成行情用东证代码的格式（手动指令 / 撤单指令按代码格式检查）


def _scenario(a_close, entry=(10,), dead=(), bear_all=False, n=30):
    """与 test_live_unified._scenario 相同，只是票用东证代码：TA 有信号、TB 平、核心 1655.T。"""
    a = _frame(a_close, entry=entry, dead=dead)
    b = _frame([1500.0] * n)
    core = _frame([700.0] * n)
    core["entry"] = False
    bear = pd.Series(bool(bear_all), index=core.index)
    return _maker({TA: a, TB: b, "1655.T": core}, bear), core.index[5]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(LO, "_sleep", lambda s: None)
    import qbreak.brokers.tachibana as TB
    monkeypatch.setattr(TB, "_sleep", lambda s: None)


def _at(d: dt.date, hh: int, mm: int = 0) -> dt.datetime:
    return dt.datetime.combine(d, dt.time(hh, mm), tzinfo=JST)


class _Timeout(SimExchange):
    """指定时刻起，下一笔新规注文：交易所受理了，但应答没回来（超时 → 适配器记「状态不明」）。"""
    fail = False

    def get_json(self, url, payload):
        r = super().get_json(url, payload)
        if self.fail and payload.get(self.spec.f_clmid) == NEW:
            self.fail = False
            raise TimeoutError("timed out")
        return r


class _NetDown(SimExchange):
    """下一笔新规注文没到交易所（连接中途断了：适配器分不清 → 状态不明）。"""
    fail = False

    def get_json(self, url, payload):
        if self.fail and payload.get(self.spec.f_clmid) == NEW:
            self.fail = False
            raise ConnectionError("回线断了")
        return super().get_json(url, payload)


def _rig(entry=(10,), dead=(), bear_all=True, upto=10, exch_cls=SimExchange, manual=None, before=None):
    """立花适配器 + 模拟交易所的执行器（账本在临时数据目录的 live_unified_tachibana.json），逐日跑到第 upto 天收盘后的决策。
    时钟 = 每个决策的成交日 07:40（早上的运行）。before(k, r)：第 k 天的早上运行之前调用。"""
    make, start = _scenario([1000.0] * 30, entry=entry, dead=dead, bear_all=bear_all)
    eng = make()
    exch = exch_cls(eng, cash=eng.st.cash_jpy)
    b = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=False, confirm_timeout_s=0.0)
    book = paths.state_dir() / BOOK_T
    lo = int(eng.gidx.searchsorted(start))
    now = {"t": _at(eng.gidx[lo].date(), 7, 40)}
    ux = UnifiedExecutor(eng, b, book, paper=False, check_clock=False, clock=lambda: now["t"], manual_tag=manual)
    r = SimpleNamespace(eng=eng, exch=exch, b=b, ux=ux, now=now, book=book, lo=lo)

    def day(k):
        exch.open(k)
        r.ux.open_phase()
        exch.close_day()
        exch.set_day(k + 1)
        now["t"] = _at(next_trading_day(eng.gidx[k].date()), 7, 40)
        if before is not None:
            before(k, r)
        r.ux.run_bar(k)
    r.day = day
    eng.prime(lo)
    for k in range(lo, upto + 1):
        day(k)
    r.f = r.ux.fill_day()
    return r


def _order(r, ticker=TA, side="BUY"):
    return [o for o in r.ux.orders if o.ticker == ticker and o.side == side and o.decided_on == r.eng.st.last_date][0]


def _xo(r, o):
    """模拟交易所里执行器那笔单。"""
    return r.exch.orders[o.broker_id]


# ══════════════════════════ ① 撤单 ══════════════════════════
def test_cancel_a_resting_opening_order_then_next_morning_counts_it_as_unfilled():
    r = _rig()
    o = _order(r)
    assert o.status == "SENT" and o.broker_id and o.sent_at                # 发出的时刻记在单上（状态不明时找候选用）
    r.now["t"] = _at(r.f, 8, 10)
    res = r.ux.cancel_orders()
    assert [x["cid"] for x in res["done"]] == [o.cid] and not res["failed"]
    assert o.status == "CANCELLED" and o.filled_qty == 0 and "你撤了单" in o.note and "全部撤掉" in o.note
    assert _xo(r, o)["status"] == "7"                                       # 交易所那边：取消完了
    saved = json.loads(r.book.read_text(encoding="utf-8"))
    assert [x["status"] for x in saved["orders"] if x["cid"] == o.cid] == ["CANCELLED"]
    assert any("撤单 买 7203.T" in e["msg"] for e in saved["events"])
    assert list((paths.state_dir() / "backup").glob("live_unified_tachibana_*.json"))   # 改账本之前先备份
    assert r.ux.cancel_orders()["note"].startswith("今天没有还挂着的执行器单")              # 再撤一次：没有要撤的了
    r.day(11)                                                               # 第二天早上：撤掉的买单 = 没成交，不再买
    assert TA not in r.eng.st.pos and not r.ux.blocked
    hist = [x for h in r.ux.book["history"] for x in h["orders"] if x["cid"] == o.cid]
    assert hist and hist[0]["status"] == "CANCELLED" and r.ux.stats["unfilled_buy"] == 1


def test_cancel_after_a_partial_fill_keeps_the_filled_part():
    r = _rig()
    o = _order(r)
    x = _xo(r, o)
    q0 = int(x["qty"])
    assert q0 >= 200
    x["qty"] = 100
    r.exch._fill(x, 1000.0)                                                 # 先成交 100 股（一部約定），其余还挂着
    x.update(qty=q0, status="1")
    r.now["t"] = _at(r.f, 10, 0)
    res = r.ux.cancel_orders([o.cid])
    assert res["done"] and o.status == "CANCELLED" and o.filled_qty == 100 and "已成交 100/" in o.note
    r.day(11)                                                               # 对账：成交的 100 股照记（与券商一致，不挡）
    assert int(r.eng.st.pos[TA].shares) == 100 and not r.ux.blocked


def test_fully_filled_order_is_not_cancelled_and_reconciles_normally():
    r = _rig()
    o = _order(r)
    r.exch.open(11)                                                         # 寄付已经全部成交
    r.now["t"] = _at(r.f, 10, 0)
    res = r.ux.cancel_orders()
    assert not res["done"] and not res["failed"] and "已经全部成交" in res["skipped"][0]["why"]   # 不算撤单失败（退出码 0、面板不退避）
    assert o.status == "SENT"                                               # 不改：第二天早上照常对账
    r.ux.open_phase()
    r.exch.close_day()
    r.exch.set_day(12)
    r.now["t"] = _at(next_trading_day(r.eng.gidx[11].date()), 7, 40)
    r.ux.run_bar(11)
    assert int(r.eng.st.pos[TA].shares) == int(o.qty) and not r.ux.blocked


class _SlowCancelBroker:
    """撤单受理了，但单一直没到终态（取消中）。"""
    dry_run = False

    def __init__(self, final="", filled=0):
        self.final, self.filled = final, filled

    def cancel_order(self, broker_id, order_date):
        return True

    def order_status(self, broker_id, order_date):
        return {"final": self.final, "filled_qty": self.filled, "avg_px": 1000.0 if self.filled else 0.0, "status": "取消中"}


def test_cancel_accepted_but_not_final_keeps_the_order_live():
    """撤单受理了、立花还没处理完（取消中 / 正在撮合）→ 不记「已撤单」（单可能还挂着；可以再查 / 再撤），明天早上照实际成交对账（OPSCMD-5）。"""
    from qbreak.live_unified import ExecOrder
    book = {"state": {"last_date": "2026-01-19"}, "orders": []}
    now = _at(dt.date(2026, 1, 20), 10, 0)
    o = ExecOrder("U2026-01-19-BUY-7203.T", TA, "BUY", "stock", 200, "2026-01-19", status="SENT", sent_qty=200,
                  broker_id="S1", order_date="20260120")
    res = LO.cancel_core([o], book, lambda: _SlowCancelBroker(), None, paper=False, now=now, polls=2)
    assert res["pending"] and not res["done"] and not res["failed"] and o.status == "SENT"
    assert "立花还在处理" in o.note and LO.cancel_why(o, book, now, False) is None              # 还能再撤
    assert any(ln.startswith("撤单已受理（立花还在处理）") for ln in LO.cancel_text(res))
    o2 = ExecOrder("U2026-01-19-SELL-7203.T", TA, "SELL", "stock", 200, "2026-01-19", status="SENT", sent_qty=200,
                   broker_id="S2", order_date="20260120")
    res = LO.cancel_core([o2], book, lambda: _SlowCancelBroker(final="CANCELLED", filled=100), None, paper=False, now=now)
    assert res["done"] and o2.status == "CANCELLED" and o2.filled_qty == 100


def test_cancel_is_allowed_while_halt_exists_and_only_today_and_before_close():
    r = _rig()
    o = _order(r)
    paths.halt_file().write_text("stop", encoding="utf-8")
    book = r.ux.book
    assert "收盘" in LO.cancel_why(o, book, _at(r.f, 15, 31), False)          # 收盘之后：已失效，不用撤
    assert "不是今天的单" in LO.cancel_why(o, book, _at(next_trading_day(r.f), 9, 0), False)
    r.now["t"] = _at(r.f, 9, 30)
    assert r.ux.cancel_orders()["done"] and o.status == "CANCELLED"         # HALT 时也能撤（撤单只会减少风险）
    assert "只撤还挂着的单" in LO.cancel_why(o, book, _at(r.f, 9, 30), False)


def test_cancelled_rule_sell_is_placed_again_next_day():
    r = _rig(entry=(5,), dead=(10,))
    o = _order(r, side="SELL")
    assert o.status == "SENT" and TA in r.eng.st.pending_exit
    r.now["t"] = _at(r.f, 8, 30)
    assert r.ux.cancel_orders()["done"]
    r.day(11)                                                               # 撤掉的卖单 = 没成交：规则还要卖 → 照常再下
    again = _order(r, side="SELL")
    assert again.cid != o.cid and again.status == "SENT" and TA in r.eng.st.pos
    assert r.ux.stats["unfilled_sell"] == 1


def test_cancelled_manual_sell_also_withdraws_the_instruction():
    def write(k, r):
        if k == 10:
            MO.append("tachibana", {"kind": "sell", "ticker": TA}, clock=lambda: r.now["t"])
            r.ux.open_phase()                                               # 执行器读到指令（开盘后运行也会读）
    r = _rig(entry=(5,), manual="tachibana", before=write)
    o = _order(r, side="SELL")
    assert o.reason == "manual" and o.status == "SENT"
    r.now["t"] = _at(r.f, 8, 30)
    res = r.ux.cancel_orders()
    assert "也撤回" in res["done"][0]["why"]
    it = [x for x in r.ux.book["manual"]["items"].values() if x.get("kind") == "sell"][0]
    assert it["cancel_req"] == f"撤单 {o.cid}"
    r.day(11)                                                               # 对账：没成交 → 指令撤回、不再下、不买回也解除
    assert it["status"] == "cancelled" and TA in r.eng.st.pos and TA not in r.eng.st.pending_exit
    assert not [x for x in r.ux.orders if x.ticker == TA and x.side == "SELL" and x.decided_on == r.eng.st.last_date]
    assert TA not in r.ux.book["manual"]["blocks"]


def test_paper_account_cancels_only_queued_opening_orders_before_the_open(tmp_path):
    make, start = _scenario([1000.0] * 30, entry=(10,), bear_all=True)
    eng = make()
    pb = PaperBroker(state_file=tmp_path / "pb.json", initial_cash=eng.st.cash_jpy, exec_cfg=EX["JP"], market="JP")
    now = {"t": _at(eng.gidx[0].date(), 7, 40)}
    ux = UnifiedExecutor(eng, pb, tmp_path / "book.json", paper=True, respect_halt=False, check_clock=False,
                         clock=lambda: now["t"])
    lo = int(eng.gidx.searchsorted(start))
    eng.prime(lo)
    for k in range(lo, 11):
        now["t"] = _at(next_trading_day(eng.gidx[k].date()), 7, 40)
        ux.run_bar(k)
    o = [x for x in ux.orders if x.ticker == TA and x.side == "BUY"][0]
    assert o.status == "SENT" and [q["client_id"] for q in pb.pending()] == [o.cid]
    f = ux.fill_day()
    assert "09:00" in LO.cancel_why(o, ux.book, _at(f, 9, 5), True)         # 开盘撮合之后撤不了
    now["t"] = _at(f, 8, 40)
    assert ux.cancel_orders()["done"] and o.status == "CANCELLED" and pb.pending() == []
    now["t"] = _at(next_trading_day(f), 7, 40)
    ux.run_bar(11)
    assert TA not in eng.st.pos and not ux.blocked


def test_panel_request_then_cancel_phase_cancels_without_building_an_engine(monkeypatch):
    r = _rig()
    o = _order(r)
    now = _at(r.f, 9, 10)
    monkeypatch.setattr(LO, "now_jst", lambda: now)
    monkeypatch.setattr(MO, "now_jst", lambda: now)
    html = panel.render("tachibana", "tok", now)
    assert "今天的单" in html and "data-act='cancel-order'" in html and f"data-cid='{o.cid}'" in html
    assert "核心 ETF 的单" in html and "可能再买 / 再卖" in html                        # 核心 ETF 撤了下一次决策会重新算（OPSCMD-6）
    assert "被挡 / 不下 / 没下" in html and "别再下" in html                          # 故障那天只照没下的行下单（OPSCMD-8）
    old_ = panel.render("tachibana", "tok", _at(next_trading_day(r.f), 8, 0))           # 第二天早上的运行还没跑：不是今天的单
    assert "上一次决策的单" in old_ and "不是今天" in old_ and "被挡 / 不下 / 没下" not in old_
    ok, msg, rec = panel.submit({"book": "tachibana", "kind": "cancel_order", "cid": o.cid}, now)
    assert ok and "执行器马上撤" in msg and rec["ticker"] == TA
    ok2, msg2, _ = panel.submit({"book": "tachibana", "kind": "cancel_order", "cid": o.cid}, now)
    assert not ok2 and "已经在撤" in msg2
    assert "撤单中" in panel.render("tachibana", "tok", now)
    assert MO.cancel_due("tachibana", json.loads(r.book.read_text(encoding="utf-8")), now)
    calls = []
    trg = panel.Trigger(run=lambda tag, mode="retry": calls.append((tag, mode)) or SimpleNamespace(poll=lambda: 0),
                        clock=lambda: _at(r.f, 11, 45), mono=lambda: 1000.0)
    assert trg.check() == ["tachibana"] and calls == [("tachibana", "cancel")]     # 午休也马上叫（撤单）
    res = LO.cancel_book(r.book, lambda: r.b, paper=False, tag="tachibana", requests=True, clock=lambda: now,
                         source="面板的撤单指令")
    assert res["done"] and res["items"] and res["items"][0][1] == "done"
    saved = json.loads(r.book.read_text(encoding="utf-8"))
    assert [x["status"] for x in saved["orders"] if x["cid"] == o.cid] == ["CANCELLED"]
    assert not MO.cancel_due("tachibana", saved, now)                       # 处理完了：面板不再叫
    assert _xo(r, o)["status"] == "7"


def test_cancel_request_for_an_order_that_cannot_be_cancelled_is_rejected():
    r = _rig()
    o = _order(r)
    now = _at(r.f, 16, 0)
    ok, msg, _ = panel.submit({"book": "tachibana", "kind": "cancel_order", "cid": o.cid}, now)
    assert not ok and "收盘" in msg
    with pytest.raises(ValueError, match="单号"):
        MO.normalize({"kind": "cancel_order", "cid": "not-a-cid"})
    assert MO.describe(MO.normalize({"kind": "cancel_order", "cid": o.cid})).startswith("撤单 7203.T（U")
    assert not MO.cancel_due("tachibana", {}, _at(r.f, 15, 40))


def test_run_py_cancel_and_halt_cancel(monkeypatch, capsys):
    import run
    from test_live_ops import _unified_home
    _unified_home()
    r = _rig()
    o = _order(r)
    now = _at(r.f, 8, 20)
    monkeypatch.setattr(LO, "now_jst", lambda: now)
    monkeypatch.setattr(MO, "now_jst", lambda: now)
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: r.b)
    assert run.main(["live-u", "--broker", "tachibana", "--phase", "cancel"]) == 0       # 没有撤单指令：不拿锁、不连券商
    assert "不用跑" in capsys.readouterr().out
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", "U2026-01-05-BUY-6758.T"]) == 0
    assert "账本里没有这笔单" in capsys.readouterr().out
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", "--halt-first"]) == 0
    out = capsys.readouterr().out
    assert paths.halt_file().exists() and "撤掉了" in out and o.cid in out
    saved = json.loads(r.book.read_text(encoding="utf-8"))
    assert [x["status"] for x in saved["orders"] if x["cid"] == o.cid] == ["CANCELLED"]


def test_halt_cancel_creates_halt_before_the_lock_and_book_check(monkeypatch, capsys):
    """「停并撤单」：执行器拿着运行锁 / 账本读不了时也先建 HALT，并说清这次没撤单（OPSCMD-1）。"""
    import run
    from qbreak.live_unified import RunLock
    from test_live_ops import _unified_home
    _unified_home()
    r = _rig()
    _order(r)
    lock = RunLock(r.book.with_suffix(".lock"), wait_s=0.0).acquire()
    try:
        assert run.main(["live-u", "--broker", "tachibana", "--cancel", "--halt-first", "--lock-wait", "0"]) == 3
    finally:
        lock.release()
    out = capsys.readouterr().out
    assert paths.halt_file().exists() and "HALT 已建" in out and "没有撤单" in out
    paths.halt_file().unlink()
    r.book.write_text("{坏了", encoding="utf-8")                # 账本读坏（有备份 / .corrupt）→ 停下，但 HALT 已经建好
    from qbreak import book_backup
    monkeypatch.setattr(book_backup, "problem", lambda book, args: "账本读不了（测试）")
    assert run.main(["live-u", "--broker", "tachibana", "--cancel", "--halt-first"]) == 3
    out = capsys.readouterr().out
    assert paths.halt_file().exists() and "没有撤单（账本读不了）" in out


# ══════════════════════════ ② 状态不明的单的候选 ══════════════════════════
def _unknown_rig(exch_cls=_Timeout):
    def boom(k, r):
        if k == 10:
            r.exch.fail = True
            r.exch.order_time = r.now["t"].strftime("%Y%m%d%H%M%S")
    return _rig(exch_cls=exch_cls, before=boom)


def test_unknown_order_candidates_from_the_order_list():
    r = _unknown_rig()
    o = _order(r)
    assert o.status == "ERROR" and "状态不明" in o.note
    real = [x for x in r.exch.orders.values() if x["ticker"] == TA][0]
    day = real["day"]
    base = dict(real, filled=0, px=0.0, status="1")
    r.exch.orders["S9000001"] = dict(base, no="S9000001", qty=100, at=day + "093000")       # 股数更少、时刻远：排后面
    r.exch.orders["S9000002"] = dict(base, no="S9000002", qty=int(real["qty"]) + 100)       # 股数更多：不算
    r.exch.orders["S9000003"] = dict(base, no="S9000003", side="SELL")                      # 买卖不同：不算
    c = r.ux.unknown_candidates()
    assert [u["cid"] for u in c] == [o.cid]
    nos = [x["order_no"] for x in c[0]["candidates"]]
    assert nos == [real["no"], "S9000001"]
    top = c[0]["candidates"][0]
    assert top["qty"] == int(real["qty"]) and top["filled_qty"] == 0 and top["final"] == "" and top["time"]
    txt = "\n".join(LO.unknown_text(c, "tachibana"))
    assert f"--resolve {o.cid} --filled 0 --px 0" in txt and "还挂着" in txt
    r.exch.open(11)                                                         # 开盘成交了：候选带成交数与均价
    c2 = r.ux.unknown_candidates()
    t2 = c2[0]["candidates"][0]
    assert t2["order_no"] == real["no"] and t2["filled_qty"] == int(real["qty"]) and t2["final"] == "FILLED"
    assert f"--filled {int(real['qty'])} --px {t2['filled_px']:g}" in "\n".join(LO.unknown_text(c2, "tachibana"))


def test_unknown_without_candidates_and_run_status_and_panel_show_them(monkeypatch):
    import run
    r = _unknown_rig(exch_cls=_NetDown)
    o = _order(r)
    assert o.status == "ERROR"
    c = r.ux.unknown_candidates()
    assert c[0]["candidates"] == [] and "多半没受理" in "\n".join(LO.unknown_text(c))
    with pytest.raises(ExecutorError):
        r.day(11)
    unk = run._unknown_for(r.ux, SimpleNamespace(broker="tachibana", demo=False, dry_run=False))
    assert unk and unk[0]["cid"] == o.cid
    assert unk[0]["stale"] == r.f.isoformat() and unk[0]["candidates"] == []   # 第二天早上：注文一覧里本来就没有昨天的单
    rec = RS.build(r.ux.book, phase="morning", ok=False, rc=3, error="执行器停下：有状态不明的单", unknown=unk)
    RS.write("tachibana", rec)
    assert rec["unknown"][0]["cid"] == o.cid
    html = panel.render("tachibana", "tok", _at(r.f, 8, 0))
    assert "注文一覧里的候选" in html and "注文約定照会" in html and "多半没受理" not in html
    monkeypatch.setattr(r.b, "open_orders", lambda strict=False: (_ for _ in ()).throw(RuntimeError("down")))
    r.now["t"] = _at(r.f, 9, 0)                                             # 同一天（才去读注文一覧）
    bad = run._unknown_for(r.ux, SimpleNamespace(broker="tachibana", demo=False, dry_run=False))
    assert bad and "RuntimeError" in bad[0]["error"]


def test_unknown_order_from_yesterday_gets_no_filled_zero_advice():
    """交易所受理了（还成交了）、应答丢了 → 第二天早上执行器停下：注文一覧只有今天的单，找不到不代表没受理 →
    不给「登记成交 0」的草稿，让人去注文約定照会查那一天（OPSCMD-2）。"""
    import run
    r = _unknown_rig()
    o = _order(r)
    with pytest.raises(ExecutorError):
        r.day(11)
    unk = run._unknown_for(r.ux, SimpleNamespace(broker="tachibana", demo=False, dry_run=False))
    assert unk[0]["cid"] == o.cid and unk[0]["stale"] == r.f.isoformat() and unk[0]["candidates"] == []
    for drafts in (True, False):
        txt = "\n".join(LO.unknown_text(unk, "tachibana", drafts=drafts))
        assert "--filled 0" not in txt and "多半没受理" not in txt and "注文約定照会" in txt
        assert f"{r.f:%m/%d}" in txt


def test_run_py_live_unknown_prints_candidates(monkeypatch, capsys):
    import run
    import qbreak.brokers.tachibana as TB
    r = _unknown_rig()
    monkeypatch.setattr(TB, "TachibanaBroker", lambda **kw: r.b)
    monkeypatch.setattr(LO, "now_jst", lambda: _at(r.f, 8, 10))           # 同一天（注文一覧里有这笔）
    assert run.main(["live-unknown", "--broker", "tachibana"]) == 0
    out = capsys.readouterr().out
    assert "状态不明的单 1 笔" in out and "登记草稿" in out and "Claude 只在你确认之后登记" in out
    _order(r).status = "RESOLVED"
    r.ux.save()
    assert run.main(["live-unknown", "--broker", "tachibana"]) == 0
    assert "没有状态不明的单" in capsys.readouterr().out


# ══════════════════════════ ③ 持仓核对 / 人工代下登记 ══════════════════════════
P2 = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0,
                    stop_loss_pct=7.0, atr_stop_mult=2.0)


def _adopt_engine(state=None, n=30):
    """人工代下登记用的引擎：TA / TB / TC 三只个股 + 核心 1655.T（ATR = 收盘 ×2%）。"""
    a = _frame([1000.0] * n)
    b = _frame([1500.0] * n)
    c = _frame([800.0] * n)
    core = _frame([700.0] * n)
    for df in (a, b, c, core):
        df["entry"] = False
    bear = pd.Series(True, index=core.index)
    return UnifiedEngine({TA: a, TB: b, TC: c, "1655.T": core}, CFG, {"JP": P2, "US": P2}, EX, CC,
                         bear={"US": bear}, state=state)


def test_adopt_buy_sell_core_and_rejections():
    eng = _adopt_engine()
    book: dict = {"orders": []}
    eng.st.last_date = str(eng.gidx[20].date())
    day = eng.gidx[21].date()
    now = _at(eng.gidx[25].date(), 18, 0)
    with pytest.raises(ValueError, match="股票池"):
        LO.adopt(eng, book, "9999", "BUY", 100, 1000, day.isoformat(), now=now)
    with pytest.raises(ValueError, match="一手"):
        LO.adopt(eng, book, TB, "BUY", 150, 1500, day.isoformat(), now=now)
    with pytest.raises(ValueError, match="未来"):
        LO.adopt(eng, book, TB, "BUY", 100, 1500, (now.date() + dt.timedelta(days=3)).isoformat(), now=now)
    with pytest.raises(ValueError, match="不是交易日"):
        LO.adopt(eng, book, TB, "BUY", 100, 1500, "2026-01-17", now=now)     # 土曜日
    rec = LO.adopt(eng, book, TB, "BUY", 200, 1510, day.isoformat(), note="API 故障日", now=now)
    ps = eng.st.pos[TB]
    assert ps.shares == 200 and ps.entry_date == day.isoformat() and ps.peak == 1510 and ps.entry_px == 1510
    assert ps.stop_px == pytest.approx(1510 - 1500 * 0.02 * 2.0)            # 引擎的新仓算法：前一根 K 线的 ATR × 倍数
    assert book["adopted"][-1]["ticker"] == TB and "人工代下登记（用户确认）" in book["events"][-1]["msg"]
    assert "API 故障日" in book["events"][-1]["msg"] and rec["side"] == "BUY"
    LO.adopt(eng, book, TB, "BUY", 100, 1540, day.isoformat(), now=now)   # 已经持有 → 并进原来的持仓（止损不变）
    assert eng.st.pos[TB].shares == 300 and eng.st.pos[TB].stop_px == ps.stop_px
    assert eng.st.pos[TB].entry_px == pytest.approx((1510 * 200 + 1540 * 100) / 300)
    with pytest.raises(ValueError, match="卖不了"):
        LO.adopt(eng, book, TB, "SELL", 400, 1500, day.isoformat(), now=now)
    LO.adopt(eng, book, TB, "SELL", 100, 1520, day.isoformat(), now=now)  # 部分卖出
    assert eng.st.pos[TB].shares == 200 and eng.st.trades[-1]["exit_date"] == day.isoformat()
    eng.st.pending_exit[TB] = "dead_cross"
    LO.adopt(eng, book, TB, "SELL", 200, 1520, day.isoformat(), now=now)  # 全部卖出：持仓与待卖都清掉
    assert TB not in eng.st.pos and TB not in eng.st.pending_exit
    LO.adopt(eng, book, "1655.T", "BUY", 30, 700, day.isoformat(), now=now)       # 核心 ETF（一手 10 口）：改口数
    LO.adopt(eng, book, "1655", "SELL", 10, 705, day.isoformat(), now=now)
    assert eng.st.core_units["1655.T"] == 20 and eng.st.core_trades[-1][0] == day.isoformat()
    with pytest.raises(ValueError, match="卖不了"):
        LO.adopt(eng, book, "1655", "SELL", 30, 705, day.isoformat(), now=now)
    for t, px in ((TA, 1000), (TB, 1500)):
        LO.adopt(eng, book, t, "BUY", 100, px, day.isoformat(), now=now)
    eng.st.pos["X1.T"] = eng.st.pos["X2.T"] = eng.st.pos[TA]             # 个股名额 4 只占满
    with pytest.raises(ValueError, match="名额已满"):
        LO.adopt(eng, book, TC, "BUY", 100, 800, day.isoformat(), now=now)
    assert TC not in eng.st.pos


def test_adopt_odd_lot_sell_and_refuses_when_the_executor_order_is_unknown():
    eng = _adopt_engine()
    eng.st.last_date = str(eng.gidx[20].date())
    day = eng.gidx[21].date().isoformat()
    now = _at(eng.gidx[25].date(), 18, 0)
    book: dict = {"orders": []}
    LO.adopt(eng, book, TA, "BUY", 200, 1000, day, now=now)
    eng.st.pos[TA].shares = 250                                           # 拆股后多出零股 50 股
    with pytest.raises(ValueError, match="零股只能卖账本记下的 50 股"):
        LO.adopt(eng, book, TA, "SELL", 30, 1000, day, now=now)
    LO.adopt(eng, book, TA, "SELL", 50, 1000, day, now=now)               # 在立花网站卖掉的零股：可以登记
    assert eng.st.pos[TA].shares == 200
    book["orders"] = [{"cid": f"U{eng.st.last_date}-SELL-7203.T", "decided_on": eng.st.last_date, "ticker": TA,
                       "side": "SELL", "status": "ERROR"}]
    with pytest.raises(ValueError, match="状态不明"):
        LO.adopt(eng, book, TA, "SELL", 200, 1000, day, now=now)
    book["orders"][0]["status"] = "SENT"
    with pytest.raises(ValueError, match="--separate"):                   # 执行器自己的单：成交明天早上对账自动记，不重复登记
        LO.adopt(eng, book, TA, "SELL", 100, 1000, day, now=now)
    rec = LO.adopt(eng, book, TA, "SELL", 100, 1000, day, now=now, separate=True)
    assert "另外下的单" in rec["warn"]


def test_reconcile_report_causes_and_drafts_then_consistent_after_adopt():
    r = _rig(entry=(5,), upto=10)
    st = r.ux.book["state"]
    held = r.b.positions()
    rep = LO.reconcile_report(r.ux.book, held, {TA, TB, "1655.T"}, now=_at(r.f, 8, 0))
    assert not rep["bad"] and "✓ 账本与券商一致" in "\n".join(rep["lines"])
    r.exch.pos[TB] = 100                                                  # 人在立花网站上买了 B.T
    r.exch.book_value[TB] = 150_500.0
    r.exch.pos["9984.T"] = 100                                               # 执行器不管的票
    r.exch.pos[TA] = int(st["pos"][TA]["shares"]) * 2                  # 像 1:2 的拆股
    rep = LO.reconcile_report(r.ux.book, r.b.positions(), {TA, TB, "1655.T"}, now=_at(r.f, 8, 0))
    lines = "\n".join(rep["lines"])
    bad = {x["ticker"]: x for x in rep["bad"]}
    assert set(bad) == {TA, TB} and rep["foreign"] == [("9984.T", 100)]
    assert any("公司行为" in c and "1:2" in c for c in bad[TA]["causes"]) and not bad[TA]["draft"]
    assert any("人工交易" in c for c in bad[TB]["causes"])
    assert bad[TB]["draft"] == "bash scripts/liveu.sh adopt --broker tachibana 6758 BUY 100 1505"
    assert "执行器不管的持仓" in lines and "★ 有不一致" in lines
    r.exch.pos[TA] = int(st["pos"][TA]["shares"])
    eng = r.eng
    LO.adopt(eng, r.ux.book, TB, "BUY", 100, 1505, r.f.isoformat(), now=_at(r.f, 18, 0))
    r.ux.book["state"] = eng.st.to_dict()
    rep = LO.reconcile_report(r.ux.book, r.b.positions(), {TA, TB, "1655.T"}, now=_at(r.f, 18, 0))
    assert not rep["bad"]


def test_reconcile_points_at_unknown_orders_and_todays_fills():
    book = {"state": {"last_date": "2026-01-19", "pos": {TA: {"shares": 100, "entry_px": 1000}}, "core_units": {}},
            "orders": [{"cid": "U2026-01-19-SELL-7203.T", "decided_on": "2026-01-19", "ticker": TA, "side": "SELL",
                        "status": "ERROR", "qty": 100}]}
    rep = LO.reconcile_report(book, {}, {TA}, now=_at(dt.date(2026, 1, 20), 10, 0))
    causes = rep["bad"][0]["causes"]
    assert any("状态不明" in c for c in causes) and not rep["bad"][0]["draft"]
    book["orders"][0]["status"] = "SENT"
    rep = LO.reconcile_report(book, {}, {TA}, now=_at(dt.date(2026, 1, 20), 10, 0))   # 执行器今天的卖单成交了：不是不一致
    lines = "\n".join(rep["lines"])
    assert not rep["bad"] and rep["rows"][0]["pending"] and not rep["rows"][0]["draft"]
    assert "不用登记" in lines and "会挡住全部下单" not in lines and "adopt" not in lines
    book["orders"][0]["status"] = "SENT"
    book["state"]["pos"][TA]["shares"] = 300                             # 差 300 股、执行器只卖 100：还是不一致，但不给草稿（混着它的成交）
    rep = LO.reconcile_report(book, {}, {TA}, now=_at(dt.date(2026, 1, 20), 10, 0))
    assert rep["bad"] and any("今天的单可能已经成交" in c for c in rep["bad"][0]["causes"]) and not rep["bad"][0]["draft"]


def test_run_py_live_adopt_backs_up_and_saves(monkeypatch, capsys):
    import run
    from qbreak.live_unified import load_state
    from test_live_ops import _unified_home
    _unified_home()
    r = _rig(entry=(5,), upto=10)
    shutil.rmtree(paths.state_dir() / "backup", ignore_errors=True)
    monkeypatch.setattr(run, "_netcheck", lambda: [])
    monkeypatch.setattr(run, "_unified_engine",
                        lambda a, cfg, state, provider: (_adopt_engine(state=load_state(r.book, 1_000_000)), None))
    monkeypatch.setattr(run, "_refresh_after_book_change", lambda tag: None)
    assert run.main(["live-adopt", "--broker", "paper", "7203", "BUY", "100", "1000"]) == 2
    assert run.main(["live-adopt", "--broker", "tachibana", "8306", "BUY", "150", "800", "--date", r.f.isoformat()]) == 2
    assert "没登记（账本没动）" in capsys.readouterr().out
    assert run.main(["live-adopt", "--broker", "tachibana", "8306", "buy", "100", "801", "--date", r.f.isoformat(),
                     "--note", "API 故障日照单下"]) == 0
    out = capsys.readouterr().out
    assert "已登记（人工代下）" in out and TC in out
    saved = json.loads(r.book.read_text(encoding="utf-8"))
    assert saved["state"]["pos"][TC]["shares"] == 100 and saved["adopted"][-1]["note"] == "API 故障日照单下"
    assert list((paths.state_dir() / "backup").glob("live_unified_tachibana_*.json"))


def test_run_py_live_reconcile_exit_code(monkeypatch, capsys):
    import run
    from test_live_ops import _unified_home
    _unified_home()
    r = _rig(entry=(5,), upto=10)
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: r.b)
    monkeypatch.setattr(run, "_managed_tickers", lambda b: {TA, TB, "1655.T"})
    assert run.main(["live-reconcile", "--broker", "tachibana"]) == 0
    assert "✓ 账本与券商一致" in capsys.readouterr().out
    r.exch.pos[TB] = 100
    assert run.main(["live-reconcile", "--broker", "tachibana"]) == 1
    assert "人工交易" in capsys.readouterr().out


def test_unknown_and_reconcile_wait_for_the_executor_lock(monkeypatch, capsys):
    """unknown / reconcile 也拿账本的运行锁：执行器在跑时登录立花会把它的会话踢掉（发单中途被切断）→ 等它结束；
    等不到 → 不登录立花、退出 3。"""
    import run
    import qbreak.brokers.tachibana as TB
    from qbreak.live_unified import RunLock
    r = _unknown_rig()
    made = []
    monkeypatch.setattr(TB, "TachibanaBroker", lambda **kw: made.append("tachibana") or r.b)
    monkeypatch.setattr(run, "_cancel_broker", lambda a, paper: made.append("cancel") or r.b)
    monkeypatch.setattr(LO, "now_jst", lambda: _at(r.f, 8, 10))
    held = RunLock(r.book.with_suffix(".lock"), wait_s=0).acquire()          # 执行器在跑
    try:
        assert run.main(["live-unknown", "--broker", "tachibana", "--lock-wait", "0"]) == 3
        assert run.main(["live-reconcile", "--broker", "tachibana", "--lock-wait", "0"]) == 3
        out = capsys.readouterr().out
        assert out.count("执行器在跑：等它结束") == 2 and "没登录立花" in out
        assert made == []                                                     # 没建适配器、没登录
    finally:
        held.release()
    assert run.main(["live-unknown", "--broker", "tachibana"]) == 0 and made == ["tachibana"]
    assert "执行器在跑" not in capsys.readouterr().out


# ══════════════════════════ liveu.sh 子命令 ══════════════════════════
@pytest.mark.skipif(not shutil.which("bash"), reason="需要 bash")
def test_liveu_subcommands_pass_the_right_arguments(tmp_path):
    b = tmp_path / "bin"
    b.mkdir()
    log = tmp_path / "calls.log"
    (b / "fakepy").write_text('#!/bin/sh\necho "py $*" >> "$CALLS"\nexit 0\n', encoding="utf-8")
    (b / "fakepy").chmod(0o755)
    (b / "git").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (b / "git").chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("QBREAK_", "XPC_"))}
    env.update({"PATH": f"{b}{os.pathsep}{os.environ['PATH']}", "HOME": str(tmp_path / "home"), "CALLS": str(log),
                "QBREAK_PYTHON": str(b / "fakepy"), "QBREAK_LIVEU_HOME": str(tmp_path / "lh"), "QBREAK_LIVEU_PULL": "0",
                "QBREAK_CAFFEINATED": "1", "QBREAK_LAUNCH_AGENTS": str(tmp_path / "agents"), "LC_ALL": "C.UTF-8"})

    def sh(*args) -> str:
        if log.exists():
            log.unlink()
        r = subprocess.run(["bash", "scripts/liveu.sh", *args], cwd=ROOT, env=env, capture_output=True, timeout=60)
        assert b"unbound variable" not in r.stderr, r.stderr
        return log.read_text(encoding="utf-8") if log.exists() else ""
    assert sh("cancel", "U2026-10-08-SELL-7203.T", "--broker", "tachibana").strip() == \
        "py run.py live-u --broker tachibana --cancel U2026-10-08-SELL-7203.T"
    assert sh("cancel").strip() == "py run.py live-u --cancel"
    assert sh("halt-cancel", "--broker", "tachibana").strip() == "py run.py live-u --broker tachibana --halt-first --cancel"
    assert sh("halt-cancel").strip() == "py run.py live-u --broker tachibana --halt-first --cancel"   # 没有账本：默认立花（真钱）
    st_ = tmp_path / "lh" / "state"
    st_.mkdir(parents=True, exist_ok=True)
    for f in ("live_unified_tachibana.json", "live_unified_paper.json"):
        (st_ / f).write_text("{}", encoding="utf-8")
    assert sh("halt-cancel").strip().splitlines() == [                      # 没写 --broker：有账本的都撤（立花在前；OPSCMD-7）
        "py run.py live-u --broker tachibana --halt-first --cancel", "py run.py live-u --broker paper --halt-first --cancel"]
    assert sh("unknown", "--broker", "tachibana").strip() == "py run.py live-unknown --broker tachibana"
    assert sh("reconcile").strip() == "py run.py live-reconcile"
    assert sh("adopt", "--broker", "tachibana", "7203", "BUY", "100", "2500").strip() == \
        "py run.py live-adopt --broker tachibana 7203 BUY 100 2500"
    calls = sh("run", "--broker", "tachibana", "--phase", "cancel")          # 面板叫的撤单：不 pull、不等云端，直接跑
    assert "live-u --notify --remote-halt" in calls and "--phase cancel" in calls and "unified_today" not in calls
