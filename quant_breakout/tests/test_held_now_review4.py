"""「持仓反映今天成交」（live_ops.held_now；2026-10-16）四次复核的回归测试（H1〜H5）：
H1 今天已经全部成交的手动卖出 / 减仓 / 买入，收盘后 / 周末写同一只的新指令不再被「没处理完」挡（check / fund_all / fund_holdings；部分成交照挡）；
H2 liveu.sh manual 的核心 ETF 卖出预计按含今天已成交的口数、今天有成交的不估（面板同一个判断 MO.est_skip）；
H3 交易页：对账之后才执行的时段（收盘后 / 周末 / 下一个交易日 07:40 之前）持仓与现金按投影，与 today_why 一致；
H4 立花对照：上一份快照留下来的成交行不算「快照那一刻知道的」→ 说不准（soft），不报「不一致」；
H5 没有已知的成交时，结果不明的在途单照样算说不准。执行器（live_unified）不改。"""
import datetime as dt
import json
from types import SimpleNamespace

from qbreak import broker_snapshot as BS
from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import paths
from qbreak import trade_room as TR
from qbreak.calendar_jp import JST

from test_held_now import _b1016, _o, _tbook
from test_manual_now import PX, _at, _item, _morning, _paper, _quote, _req


def _book(r) -> dict:
    r.ux.save(force=True)
    return json.loads((paths.state_dir() / f"book_{r.tag}.json").read_text(encoding="utf-8"))


# ────────── H1：今天已经全部成交的手动指令，对账之后执行的新指令不再被它挡 ──────────
def test_filled_trim_does_not_block_instructions_written_after_close():
    r = _paper("paper_h1a")
    _morning(r, until=14)
    _req(r, kind="trim", ticker="A.T", pct=12.0)                            # 200 → 100 股，10:00 盘中全部成交
    r.now["t"] = _at(r, 10, 0)
    assert r.ux.now_phase(_quote(PX))["placed"] == 1
    book = _book(r)
    t1030, t1540, nxt = _at(r, 10, 30), _at(r, 15, 40), _at(r, 7, 0, days=1)
    assert "没处理完" in (MO.check({"kind": "sell", "ticker": "A.T"}, book, r.tag, now=t1030) or "")   # 当天对账前执行：照挡
    assert "A.T" in MO.fund_holdings(book, r.tag, now=t1030)["busy"]
    for T in (t1540, nxt):                                                 # 收盘后 / 第二天 07:40 之前：对账之后执行 → 不挡
        assert MO.check({"kind": "sell", "ticker": "A.T"}, book, r.tag, now=T) is None
        fa = MO.fund_all(book, r.tag, "C.T", now=T)
        assert fa["blocked"] is None and [(t, n) for t, n, _p in fa["sells"]] == [("A.T", 100)]   # 股数 = 减仓之后剩下的
        assert "A.T" not in MO.fund_holdings(book, r.tag, now=T)["busy"]
        ra = TR.room(r.tag, book, T, sm={}, halt=False, arm="file", running=False)["per_ticker"]["A.T"]
        assert ra["held"] == 100 and not any("没处理完" in w for w in ra["sell"]["why"]), ra["sell"]["why"]   # 交易页同一个判断
    ok, msg, _ = MO.cancel_request(r.tag, book, "M-trim-A", now=t1540)
    assert not ok and "明天早上" not in msg and "收盘后" in msg and "不用等它" in msg
    _req(r, kind="sell", ticker="A.T", block_days=0, id="M-sell-A2")         # 收盘后写的卖出：第二天早上对账（减仓完成）之后卖剩下的 100 股
    _morning(r)
    assert _item(r, "M-trim-A")["status"] == "done" and _item(r, "M-sell-A2")["status"] == "placed"
    assert [(o.side, o.qty) for o in r.ux.orders if o.ticker == "A.T" and o.reason == "manual"] == [("SELL", 100)]


def test_filled_sell_and_buy_do_not_block_after_close():
    r = _paper("paper_h1b")
    _morning(r, until=14)
    _req(r, kind="sell", ticker="A.T", block_days=0)
    _req(r, kind="buy", ticker="B.T", unit="shares", value=100)
    r.now["t"] = _at(r, 10, 0)
    r.ux.now_phase(_quote(PX))
    book = _book(r)
    assert "对账之后" in (MO.check({"kind": "buy", "ticker": "A.T"}, book, r.tag, now=_at(r, 10, 30)) or "")
    for T in (_at(r, 15, 40), _at(r, 15, 40) + dt.timedelta(days=1)):
        why = MO.check({"kind": "buy", "ticker": "A.T", "unit": "shares", "value": 100}, book, r.tag, now=T) or ""
        assert "没处理完" not in why, why                                   # 卖光的再买：对账时卖出先完成
        assert "B.T" not in MO.fund_holdings(book, r.tag, now=T)["busy"]   # 今天买进的：对账之后能拿来凑
        assert MO.check({"kind": "sell", "ticker": "B.T"}, book, r.tag, now=T) is None


def _trim_tbook(filled: int) -> dict:
    BS_snap = {"at": "2026-10-16 15:45:00", "fills_at": "2026-10-16 15:45:00", "fills_day": "2026-10-16", "positions": [],
               "fills": [{"cid": "U2026-10-15-SELL-7203.T-0", "filled_qty": filled, "avg_px": 2510.0}], "compare": []}
    paths.out_dir().mkdir(parents=True, exist_ok=True)
    (paths.out_dir() / "broker_snapshot_tachibana.json").write_text(json.dumps(BS_snap), encoding="utf-8")
    b = _tbook([_o(side="SELL", status="SENT", qty=100, reason="manual_trim", ref_px=2500.0)],
               pos={"7203.T": {"shares": 300, "entry_px": 2400.0, "last_close": 2500.0, "entry_date": "2026-09-01"}})
    b["manual"] = {"items": {"M-trim-7203": {"id": "M-trim-7203", "kind": "trim", "ticker": "7203.T", "pct": 50.0, "status": "placed",
                                             "decided_on": "2026-10-15", "shares": 100, "at": "2026-10-15T20:00:00+09:00"}},
                   "trims": {"7203.T": {"id": "M-trim-7203", "shares": 100, "target": 200, "decided_on": "2026-10-15"}},
                   "core_pct": 100.0}
    return b


def test_tachibana_trim_partial_still_blocks_full_does_not():
    sat = dt.datetime(2026, 10, 17, 10, 0, tzinfo=JST)
    b = _trim_tbook(100)
    assert MO.check({"kind": "sell", "ticker": "7203.T"}, b, "tachibana", now=sat) is None
    b = _trim_tbook(50)                                                    # 只成交了一部分：对账之后还要再卖 → 照挡
    assert "没处理完" in (MO.check({"kind": "sell", "ticker": "7203.T"}, b, "tachibana", now=sat) or "")
    assert "7203.T" in MO.fund_holdings(b, "tachibana", now=sat)["busy"]


# ────────── H2：命令行的核心 ETF 卖出预计按投影、今天有成交的不估 ──────────
def test_cli_core_trim_estimate_uses_the_projection(capsys, monkeypatch):
    import run
    from qbreak import calendar_jp as CJ
    from test_manual_core import _pbook
    _pbook(orders=[{"cid": "U2026-10-05-SELL-1655.T", "ticker": "1655.T", "side": "SELL", "kind": "core", "qty": 210, "sent_qty": 210,
                    "decided_on": "2026-10-05", "reason": "核心 ETF 调整", "phase": "morning", "status": "FILLED",
                    "filled_qty": 210, "filled_px": 700.0}])                # 早上开盘已照规则卖了 210 口：账本 1,130、投影 920
    now = dt.datetime(2026, 10, 6, 15, 40, tzinfo=JST)
    monkeypatch.setattr(CJ, "now_jst", lambda: now)
    assert MO.est_skip(LO.held_now(json.loads((paths.state_dir() / "live_unified_paper.json").read_text(encoding="utf-8")),
                                   "paper", now=now), "1655.T")
    assert run.main(["manual", "trim", "1655", "--pct", "5", "--broker", "paper"]) == 0
    out = capsys.readouterr().out
    assert "1,060" not in out and "742,000" not in out, out               # 以前：按账本 1,130 口算卖 1,060 口
    assert "今天已有成交（对账前）：成本 / 口数" in out and "预计收益对账之后再看" in out, out


# ────────── H3：交易页在对账之后执行的时段按投影 ──────────
def test_trade_room_after_settle_window_uses_the_projection():
    b = _b1016()
    mon = dt.datetime(2026, 10, 19, 7, 0, tzinfo=JST)                      # 周一 07:40 对账之前
    rm = TR.room("paper", b, mon, sm={}, halt=False, arm="file", waiting=[], running=False)
    r82 = rm["per_ticker"]["1482.T"]
    assert r82["held"] == 650 and r82["sell"]["n"] == 1, r82["sell"]["why"]
    assert MO.today_why(b, "1482.T", "sell", "paper", now=mon) is None     # 写入检查同一个结论
    assert "1545.T" not in rm["per_ticker"]                                # 周五卖光：不再按账本的 4,110 口算
    assert rm["overall"]["sell_left"]["n"] == 1 and "（含 10/16（周五）已成交）" in rm["overall"]["sell_left"]["why"]
    assert rm["money"]["cash"] > 9_000                                     # 现金含周五的卖出所得（账本只有 ¥191）
    sat = dt.datetime(2026, 10, 17, 10, 0, tzinfo=JST)
    r82 = TR.room("paper", b, sat, sm={}, halt=False, arm="file", waiting=[], running=False)["per_ticker"]["1482.T"]
    assert r82["sell"]["short"] == "休市日" and r82["sell"]["why"][0].startswith("今天休市")


# ────────── H4 / H5：立花对照卡 ──────────
class _FB:
    def __init__(self, held, status):
        self.held, self.status = held, status

    def positions(self):
        return {t: SimpleNamespace(qty=q, avg_px=2990.0) for t, q in self.held.items()}

    def cash(self):
        return 500_000.0

    def open_orders(self):
        return []

    def order_status(self, bid, od):
        if isinstance(self.status, Exception):
            raise self.status
        return self.status


def test_kept_snapshot_row_is_unsure_not_a_mismatch(monkeypatch):
    book = {"broker": "TachibanaBroker", "state": {"last_date": "2026-10-15", "cash_jpy": 1_000_000.0, "pos": {}, "core_units": {},
                                                   "history": [["2026-10-15", 1_000_000.0]], "pending_exit": {}},
            "orders": [{"cid": "U2026-10-15-BUY-7203.T", "ticker": "7203.T", "side": "BUY", "kind": "stock", "qty": 100, "sent_qty": 100,
                        "status": "SENT", "filled_qty": 0, "limit": 3000.0, "decided_on": "2026-10-15", "order_date": "20261016",
                        "sent_at": "2026-10-16T09:05:10+09:00", "broker_id": "B1", "phase": "open"}]}
    monkeypatch.setattr(BS, "_now", lambda: dt.datetime(2026, 10, 16, 11, 35, tzinfo=JST))
    BS.refresh(_FB({"7203.T": 50}, {"filled_qty": 50, "avg_px": 2990.0, "status": "一部約定"}), "tachibana", book)
    monkeypatch.setattr(BS, "_now", lambda: dt.datetime(2026, 10, 16, 15, 45, tzinfo=JST))
    snap = BS.refresh(_FB({"7203.T": 100}, TimeoutError("x")), "tachibana", book)    # 15:45 这笔读不了：留 11:35 的 50 股
    assert snap["fills"][0].get("kept_from") and snap["fills"][0]["filled_qty"] == 50
    pj = LO.held_now(book, "tachibana", now=dt.datetime(2026, 10, 16, 15, 50, tzinfo=JST), snap=snap)
    assert pj["fills"][0]["at"].startswith("2026-10-16 11:35")             # 成交时刻 = 那一行读到的时刻
    cm = LO.broker_compare(snap, pj)
    assert not cm["bad"] and [r["ticker"] for r in cm["soft"]] == ["7203.T"]


def test_errored_pending_order_is_unsure_without_other_fills(monkeypatch):
    book = {"broker": "TachibanaBroker",
            "state": {"last_date": "2026-10-15", "cash_jpy": 1e6, "core_units": {"1545.T": 100}, "history": [["2026-10-15", 1.3e6]],
                      "pos": {"7203.T": {"shares": 100, "entry_px": 3000, "last_close": 3000}}},
            "orders": [{"cid": "U2026-10-15-SELL-7203.T", "ticker": "7203.T", "side": "SELL", "kind": "stock", "qty": 100, "sent_qty": 100,
                        "status": "SENT", "filled_qty": 0, "decided_on": "2026-10-15", "order_date": "20261016",
                        "sent_at": "2026-10-16T07:41:00+09:00", "broker_id": "B1", "phase": "morning"}]}
    monkeypatch.setattr(BS, "_now", lambda: dt.datetime(2026, 10, 16, 11, 35, tzinfo=JST))
    snap = BS.refresh(_FB({"1545.T": 100}, TimeoutError("x")), "tachibana", book)   # 寄付の卖单读不了、立花已经没有 7203
    pj = LO.held_now(book, "tachibana", now=dt.datetime(2026, 10, 16, 11, 40, tzinfo=JST), snap=snap)
    assert not pj["has"]
    cm = LO.broker_compare(snap, pj)
    assert not cm["bad"] and [r["ticker"] for r in cm["soft"]] == ["7203.T"]
