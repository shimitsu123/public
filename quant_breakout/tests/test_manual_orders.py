"""手动指令（qbreak/manual_orders.py）：页面 / 命令行只写指令，执行器在下一次能下寄付单的运行里下单。
① 指令的格式与对着账本的检查；② 执行器：卖出全部 → 下一开盘寄付成行、之后不自动买回；减仓；闲置资金比例；
③ HALT / 过了 08:55 → 留着；撤回（等执行器的 / 已交给执行器的）；规则同一天也要卖 → 按规则的单；④ 日志与比较的文字。"""
import datetime as dt
import json
import os

import pytest

from qbreak import paths
from qbreak import manual_orders as MO
from qbreak.brokers.tachibana import TachibanaBroker
from qbreak.brokers.tachibana_sim import SimExchange
from qbreak.calendar_jp import JST, next_trading_day
from qbreak.live_unified import UnifiedExecutor, compare_with_sim, daily_text
from qbreak.unified import UPos, UState

from test_live_unified import _scenario

TAG = "t"
NEW = "CLMKabuNewOrder"


# ────────── ① 指令的格式与检查 ──────────
def test_normalize_accepts_codes_and_rejects_bad_input():
    assert MO.normalize({"kind": "sell", "ticker": "7203"}) == {"kind": "sell", "ticker": "7203.T", "block_days": 20,
                                                                "source": "cli"}
    assert MO.normalize({"kind": "trim", "ticker": "130a.t", "pct": "12.345"})["pct"] == 12.35
    assert MO.normalize({"kind": "core", "pct": 0, "source": "page<script>"})["source"] == "pagescript"
    for bad, msg in [({"kind": "short", "ticker": "7203"}, "不认识"), ({"kind": "sell", "ticker": "AAPL"}, "代码"),
                     ({"kind": "trim", "ticker": "7203", "pct": 120}, "0〜100"), ({"kind": "core"}, "比例"),
                     ({"kind": "trim", "ticker": "7203", "pct": "nan"}, "0〜100"),
                     ({"kind": "sell", "ticker": "7203", "block_days": 999}, "天数"),
                     ({"kind": "cancel", "target": "x; rm -rf"}, "id")]:
        with pytest.raises(ValueError, match=msg):
            MO.normalize(bad)


def test_append_is_private_append_only_and_ids_are_unique():
    clk = lambda: dt.datetime(2026, 10, 6, 8, 0, tzinfo=JST)          # noqa: E731
    a = MO.append(TAG, {"kind": "sell", "ticker": "7203", "note": "  跌太多\n了 "}, clock=clk)
    b = MO.append(TAG, {"kind": "sell", "ticker": "7203"}, clock=clk)
    assert a["id"] == "M20261006-080000-sell-7203" and b["id"] == a["id"] + "-2" and a["note"] == "跌太多 了"
    assert [r["id"] for r in MO.read_all(TAG)] == [a["id"], b["id"]]
    assert oct(os.stat(MO.requests_path(TAG)).st_mode & 0o777) == "0o600"
    with open(MO.requests_path(TAG), "a", encoding="utf-8") as f:
        f.write("坏行\n{\"kind\": \"sell\"}\n")
    assert len(MO.read_all(TAG)) == 2


def test_check_against_the_book():
    book = {"state": {"pos": {"7203.T": {"shares": 300, "last_close": 1000.0, "entry_px": 900.0}},
                      "pending_exit": {}, "history": [["2026-10-05", 1_000_000.0]]},
            "manual": {"items": {"M20261006-080000-sell-7203": {"status": "done", "kind": "sell"}}, "blocks": {}}}
    n = MO.normalize
    assert MO.check(n({"kind": "sell", "ticker": "7203"}), book) is None
    assert "没有 6758.T" in MO.check(n({"kind": "sell", "ticker": "6758"}), book)
    assert "只能减不能加" in MO.check(n({"kind": "trim", "ticker": "7203", "pct": 30}), book)   # 现在 30%
    assert MO.check(n({"kind": "trim", "ticker": "7203", "pct": 10}), book) is None
    assert "没有「不自动买回」" in MO.check(n({"kind": "unblock", "ticker": "7203"}), book)
    assert "撤不了" in MO.check(n({"kind": "cancel", "target": "M20261006-080000-sell-7203"}), book)
    book["state"]["pending_exit"]["7203.T"] = "dead_cross"
    assert "已经排在下一开盘卖出" in MO.check(n({"kind": "sell", "ticker": "7203"}), book)
    book["state"]["pending_exit"] = {}
    MO.append(TAG, {"kind": "sell", "ticker": "7203"})                # 执行器还没读的同一只票
    assert "没处理完" in MO.check(n({"kind": "trim", "ticker": "7203", "pct": 5}), book, tag=TAG)


def test_next_window_cutoff_weekend_and_holiday():
    at = lambda *a: dt.datetime(*a, tzinfo=JST)                         # noqa: E731
    assert MO.next_window(at(2026, 10, 6, 8, 54)) == (dt.date(2026, 10, 6), True)
    assert MO.next_window(at(2026, 10, 6, 8, 55)) == (dt.date(2026, 10, 7), False)
    assert MO.next_window(at(2026, 10, 10, 10, 0)) == (dt.date(2026, 10, 13), False)   # 周六 → 周一是体育之日 → 周二
    assert MO.next_window(at(2026, 10, 12, 7, 0)) == (dt.date(2026, 10, 13), False)


# ────────── ② 执行器 ──────────
class _NoSellOnce(SimExchange):
    """第一次卖 A.T 开盘没成交（例如在立花网站上撤了，或ストップ安）。"""
    done = False

    def _fill(self, o, op):
        if o["side"] == "SELL" and o["ticker"] == "A.T" and not self.done:
            self.done = True
            o["status"] = "12"
            return
        super()._fill(o, op)


class _Run:
    """立花适配器 + 模拟交易所，逐日：开盘撮合 → 早上（时钟 = 成交日 07:40）读指令 → 对账 → 决策 → 下单。"""

    def __init__(self, a_close, exchange_cls=SimExchange, **kw):
        make, start = _scenario(a_close, **kw)
        self.eng = eng = make()
        self.exch = exchange_cls(eng, cash=eng.st.cash_jpy)
        self.b = TachibanaBroker(transport=self.exch, spec=self.exch.spec, creds=self.exch.creds(), require_arm=False,
                                 confirm_timeout_s=0.0)
        self.now = {"t": None}
        self.ux = UnifiedExecutor(eng, self.b, paths.state_dir() / "book.json", paper=False, check_clock=False,
                                  clock=lambda: self.now["t"], manual_tag=TAG, auto_cap=True)
        self.k = int(eng.gidx.searchsorted(start))
        eng.prime(self.k)

    def at(self, k: int, hh: int = 7, mm: int = 40) -> dt.datetime:
        """第 k 根 K 线收盘之后、成交日（下一交易日）hh:mm 的时刻。"""
        return dt.datetime.combine(next_trading_day(self.eng.gidx[k].date()), dt.time(hh, mm), tzinfo=JST)

    def day(self, hh: int = 7, mm: int = 40) -> None:
        k = self.k
        self.exch.open(k)
        self.now["t"] = dt.datetime.combine(self.eng.gidx[k].date(), dt.time(9, 5), tzinfo=JST)
        self.ux.open_phase()
        self.exch.close_day()
        self.exch.set_day(k + 1)
        self.now["t"] = self.at(k, hh, mm)
        self.ux.morning([k])
        self.k += 1

    def until(self, k: int, **kw) -> None:
        while self.k <= k:
            self.day(**kw)

    def ask(self, **req) -> dict:
        return MO.append(TAG, req, clock=lambda: self.at(self.k - 1, 6, 0))

    def item(self, rid: str) -> dict:
        return self.ux.book["manual"]["items"][rid]

    def sells(self, t: str = "A.T") -> list[dict]:
        return [o for h in self.ux.book["history"] for o in h["orders"] if o["ticker"] == t and o["side"] == "SELL"] \
            + [o.__dict__ for o in self.ux.orders if o.ticker == t and o.side == "SELL"]


def _sell_req(r, t="A.T", **kw):
    """测试里的票是 A.T（4 位代码的格式检查在 normalize；执行器读的是文件）：直接写一行指令。"""
    rec = {"kind": "sell", "ticker": t, "block_days": 20, "source": "test", **kw}
    rec.setdefault("id", f"M{r.at(r.k - 1, 6):%Y%m%d-%H%M%S}-{rec['kind']}-{t.split('.')[0]}")
    rec.setdefault("at", r.at(r.k - 1, 6).isoformat())
    with open(MO.requests_path(TAG), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def test_manual_sell_fills_next_open_and_blocks_rebuy():
    r = _Run([1000.0] * 40, entry=(10, 22), bear_all=True)
    r.until(14)
    assert "A.T" in r.eng.st.pos
    rq = r.ask(kind="sell", ticker="7203")                     # 不是持仓：执行器自己也查 → 没执行
    it = _sell_req(r)
    r.day()                                                    # 第 15 根：决策之前变成单
    assert r.item(it["id"])["status"] == "placed" and r.eng.st.pending_exit.get("A.T") == "manual"
    assert r.item(rq["id"])["status"] == "rejected"
    o = [x for x in r.ux.orders if x.ticker == "A.T"][0]
    assert o.side == "SELL" and o.status == "SENT" and o.reason == "manual"
    r.day()                                                    # 第 16 根开盘成交 → 早上对账
    assert "A.T" not in r.eng.st.pos and r.item(it["id"])["status"] == "done"
    assert r.eng.st.trades[-1]["reason"] == "manual" and not r.ux.blocked
    blk = r.ux.book["manual"]["blocks"]["A.T"]
    assert blk["until"] == str(MO.add_trading_days(r.eng.gidx[15].date(), 20))
    r.until(24)                                                # 第 22 根的买入信号被挡
    assert "A.T" not in r.eng.st.pos
    assert any(t == "A.T" and "手动卖出后不自动买回" in w for _, t, w in r.eng.gate_log)
    sm = r.ux.summary()["manual"]
    assert sm["blocks"]["A.T"]["id"] == it["id"] and sm["active"] == 0


def test_trim_sells_part_and_keeps_the_rest():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True)
    r.until(14)
    sh = r.eng.st.pos["A.T"].shares
    eq = r.eng.equity(14)
    rec = _sell_req(r, kind="trim", pct=15.0)                 # 200 股 ≈ 20% → 15%：按单元向下取整 = 100 股
    r.day()
    tgt = int(eq * 0.15 / 1000 // 100) * 100
    assert tgt == 100 and sh == 200
    assert r.item(rec["id"])["status"] == "placed" and r.ux.book["manual"]["trims"]["A.T"]["shares"] == sh - tgt
    o = [x for x in r.ux.orders if x.ticker == "A.T"][0]
    assert o.cid.endswith("-M") and o.reason == "manual_trim" and o.qty == sh - tgt and o.status == "SENT"
    r.day()
    assert r.eng.st.pos["A.T"].shares == tgt and "A.T" not in r.eng.st.pending_exit
    t = r.eng.st.trades[-1]
    assert t["reason"] == "manual_trim" and t["shares"] == sh - tgt
    assert r.item(rec["id"])["status"] == "done" and not r.ux.book["manual"]["trims"] and not r.ux.blocked
    assert r.exch.pos["A.T"] == tgt                             # 券商那边同样 → 第二天的持仓核对照常通过
    r.day()
    assert not r.ux.blocked


def test_trim_to_zero_is_a_full_sell_without_rebuy_block():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True)
    r.until(14)
    rec = _sell_req(r, kind="trim", pct=0.0)
    r.day()
    assert r.eng.st.pending_exit.get("A.T") == "manual" and not r.ux.book["manual"]["blocks"]
    r.day()
    assert "A.T" not in r.eng.st.pos and r.item(rec["id"])["status"] == "done"


def test_core_pct_scales_the_idle_cash_etf():
    r = _Run([1000.0] * 30, entry=())                          # 牛市：闲置资金全买 1655
    r.until(12)
    u0 = r.eng.st.core_units.get("1655.T", 0)
    assert u0 > 0
    MO.append(TAG, {"kind": "core", "pct": 0}, clock=lambda: r.at(r.k - 1, 6))
    r.day()                                                    # 这次决策：目标 0 → 卖出全部
    assert r.ux.book["manual"]["core_pct"] == 0.0 and r.eng.core_scale == 0.0
    assert r.eng.st.core_plan.get("1655.T") == ["SELL", u0]
    r.day()
    assert r.eng.st.core_units.get("1655.T", 0) == 0
    MO.append(TAG, {"kind": "core", "pct": 50}, clock=lambda: r.at(r.k - 1, 6))
    r.until(r.k + 1)
    u = r.eng.st.core_units.get("1655.T", 0)
    assert 0.4 * u0 < u < 0.6 * u0


def test_halt_and_cutoff_keep_requests_pending():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True)
    r.until(14)
    rec = _sell_req(r)
    paths.halt_file().write_text("stop", encoding="utf-8")
    r.day()
    assert r.item(rec["id"])["status"] == "pending" and "A.T" not in r.eng.st.pending_exit
    assert any("HALT 生效中" in e["msg"] for e in r.ux.book["events"])
    paths.halt_file().unlink()
    r.ux.blocked = None
    r.day(hh=9, mm=10)                                         # 过了成交日 08:55：寄付来不及 → 留到下一次
    assert r.item(rec["id"])["status"] == "pending"
    assert any("寄付来不及" in e["msg"] for e in r.ux.book["events"])
    r.day()
    assert r.item(rec["id"])["status"] == "placed"


def test_same_morning_retry_adds_the_manual_sell_without_redeciding():
    """07:40 的运行之后（同一个决策）点卖出：08:35 的重试只把这笔卖单加进去，别的单不动、不重复下。"""
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True)
    r.until(14)
    n0 = r.exch.calls.get(NEW, 0)
    _sell_req(r)
    r.now["t"] = r.at(r.k - 1, 8, 35)
    r.ux.morning([])
    assert r.eng.st.pending_exit.get("A.T") == "manual" and r.exch.calls[NEW] == n0 + 1
    r.ux.morning([])
    assert r.exch.calls[NEW] == n0 + 1
    r.day()
    assert "A.T" not in r.eng.st.pos


def test_rule_exit_same_day_supersedes_and_still_blocks():
    r = _Run([1000.0] * 30, entry=(10,), dead=(15,), bear_all=True)
    r.until(14)
    rec = _sell_req(r)
    r.day()
    it = r.item(rec["id"])
    assert it["status"] == "superseded" and r.eng.st.pending_exit["A.T"] == "dead_cross"
    assert "A.T" in r.ux.book["manual"]["blocks"]
    r.day()
    assert r.eng.st.trades[-1]["reason"] == "dead_cross"


def test_cancel_pending_and_placed():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True, exchange_cls=_NoSellOnce)
    r.until(13)
    a = _sell_req(r)
    MO.append(TAG, {"kind": "cancel", "target": a["id"]}, clock=lambda: r.at(r.k - 1, 6, 1))
    r.day()                                                    # 等执行器的 → 马上撤，不下单
    assert r.item(a["id"])["status"] == "cancelled" and "A.T" not in r.eng.st.pending_exit
    b = _sell_req(r, id="M-placed-sell-A")
    r.day()                                                    # 第 15 根：交给执行器，第 16 根开盘卖 —— 没成交（网站上撤了）
    assert r.item(b["id"])["status"] == "placed"
    MO.append(TAG, {"kind": "cancel", "target": b["id"]}, clock=lambda: r.at(r.k - 1, 10))
    r.day()                                                    # 对账：没成交 → 撤（不再重下）
    assert r.item(b["id"])["status"] == "cancelled" and "A.T" in r.eng.st.pos
    assert "A.T" not in r.eng.st.pending_exit and "A.T" not in r.ux.book["manual"]["blocks"]
    assert any("手动指令已撤回，不再下" in e["msg"] for e in r.ux.book["events"])
    r.until(r.k + 2)
    assert [o["status"] for o in r.sells()] == ["UNFILLED"] and not r.ux.blocked


def test_cancel_too_late_when_already_filled():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True)
    r.until(14)
    b = _sell_req(r)
    r.day()
    MO.append(TAG, {"kind": "cancel", "target": b["id"]}, clock=lambda: r.at(r.k - 1, 10))
    r.day()
    it = r.item(b["id"])
    assert it["status"] == "done" and "撤回来不及" in it["msg"] and "A.T" not in r.eng.st.pos


def test_paper_account_trim_then_sell_keeps_broker_in_sync():
    """模拟账户（PaperBroker，第二天早上按 K 线开盘撮合）走同一条路：减仓 → 卖出全部，每天的持仓核对都通过。"""
    from qbreak.live_unified import _MemPaper
    make, start = _scenario([1000.0] * 30, entry=(10,), bear_all=True)
    eng = make()
    b = _MemPaper(state_file=paths.state_dir() / "paper.json", initial_cash=eng.st.cash_jpy, exec_cfg=eng.ex["JP"], market="JP")
    now = {"t": None}
    ux = UnifiedExecutor(eng, b, paths.state_dir() / "book_p.json", paper=True, respect_halt=False, check_clock=False,
                         clock=lambda: now["t"], manual_tag="p")
    k0 = int(eng.gidx.searchsorted(start))
    eng.prime(k0)

    def day(k):
        now["t"] = dt.datetime.combine(next_trading_day(eng.gidx[k].date()), dt.time(7, 40), tzinfo=JST)
        ux.morning([k])
        assert not ux.blocked
        held = {t: int(p.qty) for t, p in b.positions().items()}
        assert held == {t: int(p.shares) for t, p in eng.st.pos.items()}
    for k in range(k0, 15):
        day(k)
    clk = lambda: now["t"]                                      # noqa: E731
    with open(MO.requests_path("p"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "trim", "ticker": "A.T", "pct": 15.0, "id": "M-trim-A", "at": "x"}) + "\n")
    day(15)
    day(16)
    assert eng.st.pos["A.T"].shares == 100 and eng.st.trades[-1]["reason"] == "manual_trim"
    with open(MO.requests_path("p"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "sell", "ticker": "A.T", "block_days": 0, "id": "M-sell-A", "at": "y"}) + "\n")
    day(17)
    day(18)
    assert "A.T" not in eng.st.pos and eng.st.trades[-1]["reason"] == "manual" and clk()
    assert [ux.book["manual"]["items"][i]["status"] for i in ("M-trim-A", "M-sell-A")] == ["done", "done"]
    assert not ux.book["manual"]["blocks"]                      # block_days = 0：不限制买回


def test_rehearsal_and_executors_without_tag_ignore_requests():
    r = _Run([1000.0] * 30, entry=(10,), bear_all=True)
    ux2 = UnifiedExecutor(r.eng, r.b, paths.state_dir() / "b2.json", paper=False, check_clock=False)
    assert ux2.manual is None and "manual" not in ux2.book


# ────────── ④ 文字 ──────────
def test_journal_lines_and_compare_note():
    sm = {"core_pct": 50.0, "blocks": {"7203.T": {"until": "2026-11-04"}}, "trims": {}, "active": 1,
          "items": [{"id": "M1", "kind": "sell", "ticker": "7203.T", "status": "placed", "msg": "2026-10-07 开盘寄付成行卖出全部 300 股"},
                    {"id": "M0", "kind": "core", "pct": 50.0, "status": "done", "at": "2026-09-01T08:00:00+09:00", "msg": "x"}]}
    ls = MO.lines(sm, today="2026-10-06")
    assert "规则目标额的 50%" in ls[0] and "到 2026-11-04" in ls[1] and "已交给执行器" in ls[2] and len(ls) == 3
    st = UState(cash_jpy=1.0, last_date="2026-10-06", history=[["2026-10-06", 1_000_000.0, 0, 0, 150]])
    sim = UState(cash_jpy=2.0, last_date="2026-10-06", history=[["2026-10-06", 1_000_000.0, 0, 0, 150]])
    st.pos["7203.T"] = UPos("7203.T", "JP", 100, 3000.0, "2026-10-01", 2800.0, 3000.0, 3000.0)
    c = compare_with_sim(st, sim, manual=sm)
    assert c["same"] is False and c.get("manual") and "是预期的" in c["text"]
    assert "是预期的" not in compare_with_sim(st, sim)["text"]
    sm2 = {"decided_on": "2026-10-06", "orders": [{"side": "SELL", "ticker": "7203.T", "kind": "stock", "qty": 300,
                                                   "status": "SENT", "reason": "manual"}], "events": [], "blocked": None,
           "reconciled": [{"bar": "2026-10-06", "side": "SELL", "ticker": "6758.T", "qty": 100, "px": 3000.0,
                           "kind": "stock", "reason": "manual_trim"}], "manual": sm}
    title, short, body = daily_text(sm2, st, None, True, 1_000_000)
    assert "（寄付成行，手动卖出）" in body and "（手动减仓）" in body and "手动指令 1 条在处理" in short
    assert "闲置资金比例：手动设为" in body
