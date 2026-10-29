"""「持仓反映今天成交」（live_ops.held_now；2026-10-16）二次复核的回归测试（F1〜F13）：盘中固定口数的预计与执行器同一套凑钱、
今天买进 / 卖光的票在对账之后照常可写、核心 ETF 调仓按投影、立花快照前后都有成交时不报假的不一致（也不把真的不一致藏起来）、
周末 / 收盘后的文字不写「今天」、刷新不冲掉成交日的寄付成交、liveu.sh broker --notify 与面板同一个判断。执行器（live_unified）不改。"""
import datetime as dt
import json
import re
from types import SimpleNamespace

from qbreak import broker_snapshot as BS
from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import names as NM
from qbreak import panel, paths
from qbreak.calendar_jp import JST

from test_held_now import _b1016, _o, _tbook
from test_panel_held_now import AT, _book, _book_stocks, _text, _write

SAT = dt.datetime(2026, 10, 17, 10, 0, tzinfo=JST)                     # 周六（成交日 10/16 周五）
FRI1030 = dt.datetime(2026, 10, 16, 10, 30, tzinfo=JST)               # 成交日盘中
FRI1540 = dt.datetime(2026, 10, 16, 15, 40, tzinfo=JST)               # 成交日收盘后
FRI10 = dt.datetime(2026, 10, 16, 10, 0, tzinfo=JST)


def _snap(d: dict, tag: str = "tachibana") -> None:
    (paths.out_dir() / f"broker_snapshot_{tag}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _b1016r() -> dict:
    """_b1016 + 真实账本里规则那几个数（1545 规则目标 0、1482 规则目标 679 / 规则 100% 0 / 固定口数调到 655）。"""
    b = _b1016()
    b["core_rule"].update({"units100": {"1482.T": 679, "1545.T": 0}, "rule100": {"1482.T": 0}, "fix_applied": {"1482.T": 655},
                           "decided_on": "2026-10-15", "pct": 100.0, "applied": 100.0})
    b["manual"]["core"] = ["1545.T", "1482.T", "1655.T", "2845.T"]
    return b


# ────────── F1：盘中改固定口数的预计 = 执行器 now_phase（凑钱按账本口数、今天有单的 ETF 不拿来凑钱）──────────
def test_corefix_preview_matches_the_executor_intraday():
    from test_core_etf_restore import _morning, _paper2, _w
    from test_manual_now import _at, _quote
    pxq = {"A.T": 1000.0, "B.T": 1500.0, "1545.T": 700.0, "1482.T": 1000.0}
    r = _paper2()
    _morning(r, 8)
    assert int(r.eng.st.core_units["1545.T"]) > 0
    _w(r.tag, "M-fix-100", kind="corefix", ticker="1482.T", units=100)
    r.now["t"] = _at(r, 10, 0)
    r.ux.now_phase(_quote(pxq))
    d = r.ux.book["state"]["last_date"]
    now1 = [(o.ticker, o.side, o.qty, o.status) for o in r.ux.orders if o.decided_on == d and o.phase == "now"]
    assert ("1482.T", "BUY", 100, "FILLED") in now1 and any(x[0] == "1545.T" and x[3] == "FILLED" for x in now1)
    t2 = _at(r, 10, 30)
    r.ux.save(force=True)
    b = json.loads((paths.state_dir() / f"live_unified_{r.tag}.json").read_text(encoding="utf-8"))
    pv = MO.corefix_preview(b, r.tag, {"kind": "corefix", "ticker": "1482.T", "units": 300}, t2)
    pre_sells = [(m["t"], m["qty"]) for m in pv["plan"]["moves"] if m["side"] == "SELL"]
    pre_buys = [(m["t"], m["qty"]) for m in pv["plan"]["moves"] if m["side"] == "BUY"]
    n0 = len(r.ux.orders)
    _w(r.tag, "M-fix-300", kind="corefix", ticker="1482.T", units=300)
    r.now["t"] = t2
    r.ux.now_phase(_quote(pxq))
    new = [(o.ticker, o.side, o.qty) for o in r.ux.orders[n0:] if o.status not in ("CANCELLED", "SKIPPED")]
    assert pre_sells == [(t, q) for t, s, q in new if s == "SELL"] == []          # 预计与执行器都不卖 1545（今天已经有单）
    assert pre_buys == [(t, q) for t, s, q in new if s == "BUY"], (pv["text"], new)
    assert "1545.T" in pv["plan"].get("busy", ()) and "不拿来凑钱" in pv["text"]


def test_corefix_preview_intraday_does_not_sell_a_core_bought_today_for_funding():
    for t in ("1545.T", "1655.T"):
        pv = MO.corefix_preview(_b1016(), "paper", {"kind": "corefix", "ticker": t, "units": 1000 if t == "1545.T" else 100}, FRI1030)
        assert not [m for m in pv["plan"]["moves"] if m["side"] == "SELL"], pv["text"]   # 1482 账本 0 口（今天买的）不拿来卖
        assert "现金只够约" in pv["text"] and "下一次决策照它调" in pv["text"]
    assert NM.label("1545.T") + " 今天已经有执行器的单 → 不拿来凑钱" in pv["text"]


# ────────── F2：今天买进的个股 —— 收盘后写的卖出（对账之后执行）照常；盘中写的才挡 ──────────
def test_sell_of_a_stock_bought_today_is_allowed_after_close():
    from test_manual_now import PX, _at, _morning, _paper, _quote, _req
    r = _paper("paper_r5")
    _morning(r, until=14)
    _req(r, kind="buy", ticker="B.T", unit="rule")
    r.now["t"] = _at(r, 10, 0)
    assert r.ux.now_phase(_quote(PX))["placed"] >= 1
    r.ux.save(force=True)
    book = json.loads((paths.state_dir() / "book_paper_r5.json").read_text(encoding="utf-8"))
    late = _at(r, 15, 40)
    for rec in ({"kind": "sell", "ticker": "B.T"}, {"kind": "trim", "ticker": "B.T", "pct": 5.0},
                {"kind": "adjust", "ticker": "B.T", "unit": "shares", "value": 200}):
        assert MO.check(rec, book, r.tag, now=late) is None, rec
    why = MO.check({"kind": "sell", "ticker": "B.T"}, book, r.tag, now=_at(r, 10, 30))
    assert why and "今天盘中执行器不再动它" in why and "收盘后（15:25 起）再写" in why
    _req(r, kind="sell", ticker="B.T", id="M-sell-B-1540")                # 收盘后写的 → 第二天早上对账之后照常卖
    _morning(r)
    it = r.ux.book["manual"]["items"]["M-sell-B-1540"]
    d = r.ux.book["state"]["last_date"]
    assert it.get("status") != "rejected"
    assert any(o.side == "SELL" for o in r.ux.orders if o.ticker == "B.T" and o.decided_on == d)


# ────────── F3：今天卖光的核心 ETF —— 往上调仓不说「不用再点」──────────
def test_core_sold_out_today_adjust_up_points_to_corefix():
    b = _b1016r()
    b["core_rule"]["units100"]["1545.T"] = 4110
    for now in (FRI1540, SAT):
        try:
            MO.core_rec({"kind": "adjust", "ticker": "1545.T", "unit": "shares", "value": 2000}, b, "paper", now=now)
            raise AssertionError("adjust up of a core sold out today should be refused")
        except ValueError as e:
            msg = str(e)
        assert "要买回用「固定口数…」或「闲置资金比例」" in msg and "不用再点" not in msg, msg
        for rec in ({"kind": "sell", "ticker": "1545.T"}, {"kind": "adjust", "ticker": "1545.T", "unit": "shares", "value": 0}):
            w = MO.today_why(b, "1545.T", rec["kind"], "paper", now, rec)
            assert w and "不用再点" in w, (rec, w)


# ────────── F4：规则止损今天卖光的个股 —— 收盘后 / 周末写的买入不说「已经持有」──────────
def _b_stop() -> dict:
    st = {"last_date": "2026-10-15", "cash_jpy": 500000.0,
          "pos": {"7203.T": {"ticker": "7203.T", "market": "JP", "shares": 300, "entry_px": 2800.0, "entry_date": "2026-09-01",
                             "stop_px": 2600.0, "peak": 3000.0, "last_close": 2650.0, "hold": 20, "armed": False, "entry_fx": 1.0}},
          "pending_exit": {"7203.T": "stop"}, "core_units": {}, "core_last": {},
          "history": [["2026-10-15", 1295000.0, 500000.0, 0.0, 150.0]], "trades": [], "core_trades": [], "plan": {}, "core_plan": {}}
    o = {"cid": "U2026-10-15-SELL-7203.T", "ticker": "7203.T", "side": "SELL", "kind": "stock", "qty": 300, "sent_qty": 300,
         "filled_qty": 300, "filled_px": 2640.0, "status": "FILLED", "reason": "stop", "phase": "morning", "limit": None,
         "ref_px": 2650.0, "decided_on": "2026-10-15"}
    return {"state": st, "orders": [o], "broker": "PaperBroker", "core_rule": {},
            "manual": {"items": {}, "core_fix": {}, "core_pct": 100.0, "max_positions": 4, "core": []}}


def test_buy_back_of_a_stock_sold_out_today():
    rec = {"kind": "buy", "ticker": "7203.T", "unit": "shares", "value": 100}
    for now in (FRI1540, SAT):
        assert MO.check(rec, _b_stop(), "paper", now=now) is None
        w = MO.check({"kind": "adjust", "ticker": "7203.T", "unit": "shares", "value": 100}, _b_stop(), "paper", now=now)
        assert w and "要买回用「买入」" in w and "已经持有" not in w
    w = MO.check(rec, _b_stop(), "paper", now=FRI10)
    assert w and "对账之后（收盘后 15:25 起写）才能再买" in w and "已经持有" not in w, w


# ────────── F5：今天买进的核心 ETF 减仓 / 调仓按投影的口数 ──────────
def test_core_trim_of_a_core_bought_today_uses_the_projection():
    for now in (FRI1540, SAT):
        r = MO.core_rec({"kind": "trim", "ticker": "1482.T", "pct": 50.0}, _b1016r(), "paper", now=now)   # 固定 655、今天买进 650
        assert r["kind"] == "corefix" and r["units"] == 328, r
        b2 = _b1016r()
        b2["manual"]["core_fix"] = {}
        b2["core_rule"].pop("fix_applied")
        b2["orders"][1]["reason"] = "核心 ETF 调整"
        b2["orders"][1]["phase"] = "open"
        r = MO.core_rec({"kind": "trim", "ticker": "1482.T", "pct": 10.0}, b2, "paper", now=now)
        assert r["kind"] == "core" and r["target"] == 65 and r["pct"] > 0, r
        c = MO.core_info(b2, "1482.T", LO.held_now(b2, "paper", now=now))
        assert c["cur"] == 650, c


# ────────── F6 / F10：同一只快照前后都有成交 → 只拿快照之前的比，不报假的不一致 ──────────
def test_broker_card_fills_before_and_after_the_snapshot():
    b = _tbook([_o("1482.T", "BUY", status="SENT", qty=100, filled=0, px=0.0, kind="core", ref_px=1483.0,
                   cid="U2026-10-15-BUY-1482.T", broker_id="111", order_date="20261016"),
                _o("1482.T", "BUY", status="FILLED", qty=200, filled=200, px=1490.0, kind="core", phase="now",
                   reason="core_fix", cid="U2026-10-15-BUY-1482.T-N130005", sent_at="2026-10-16T13:00:05+09:00",
                   broker_id="222", order_date="20261016")],
               core={"1482.T": 0})
    _snap({"at": "2026-10-16 11:35:00", "source": "liveu.sh broker", "positions": [{"ticker": "1482.T", "qty": 100, "avg_px": 1484.0}],
           "buying_power": 300000.0, "fills_at": "2026-10-16 11:35:00",
           "fills": [{"cid": "U2026-10-15-BUY-1482.T", "ticker": "1482.T", "side": "BUY", "kind": "core", "qty": 100,
                      "filled_qty": 100, "avg_px": 1484.0, "status": "約定", "final": ""}]})
    now = dt.datetime(2026, 10, 16, 13, 30, tzinfo=JST)
    pj = LO.held_now(b, "tachibana", now=now)
    assert pj["core_units"]["1482.T"] == 300
    h = panel._broker_card("tachibana", now, pj)
    t = _text(h)
    assert "card warn" not in h and "不一致" not in t, t
    assert NM.label("1482.T") + " 立花 100 / 账本 100 ✓" in t and "又成交了，下一次刷新才看得到" in t, t


# ────────── F7：周末的名额 / 现金说明写成交那天，不写「今天」──────────
def test_saturday_slot_labels_name_the_fill_day(capsys, monkeypatch):
    import run
    from qbreak import calendar_jp as CJ
    b = _book_stocks()
    s = MO.slots(b, "paper", now=SAT, with_today=True)
    assert panel._slots_today(s) == "（含 10/16（周五）已成交）", s
    b["manual"]["blocks"] = {"6758.T": {"id": "M20261016-1", "since": "2026-10-16", "until": None}}
    u = panel._unblock_confirm(b, "paper", ["6758.T"], "这只", [], now=SAT)
    assert "含 10/16（周五）已成交" in u and "含今天已成交" not in u, u
    monkeypatch.setattr(CJ, "now_jst", lambda: SAT)
    monkeypatch.setattr(LO, "now_jst", lambda: SAT)
    assert run.main(["manual", "list", "--broker", "paper"]) == 0
    out = capsys.readouterr().out
    assert "（含 10/16（周五）已成交）" in out and "含今天已成交" not in out, out


# ────────── F8：持仓页「仓位占比」卡也写明是对账前的预计 ──────────
def test_alloc_card_says_it_includes_fills_before_reconcile():
    _book()
    h = panel.render("paper", "t" * 40, AT)
    i = h.index("id='alloc'")
    t = _text(h[i:h.index("</section>", i)])
    assert "已成交" in t and "对账" in t, t


# ────────── F9：成交日之后（周末 / 周一早上的运行没做）刷新快照 → 不冲掉成交日的寄付成交 ──────────
class _FB:
    """周一 / 周六读到的立花：7203 周五寄付卖光、6758 周五 10:00 买进 100 股。"""
    spec = None

    def positions(self):
        return {"6758.T": SimpleNamespace(qty=100, avg_px=3000.0)}

    def cash(self):
        return 450_000.0

    def open_orders(self):
        return []

    def order_status(self, bid, od):
        return {}


def _b_fri() -> dict:
    return _tbook([_o("7203.T", "SELL", status="SENT", qty=100, filled=0, px=0.0, cid="U2026-10-15-SELL-7203.T",
                      broker_id="111", order_date="20261016", sent_at="2026-10-16T07:41:00+09:00"),
                   _o("6758.T", "BUY", status="FILLED", qty=100, filled=100, px=3000.0, phase="now", reason="manual_buy",
                      cid="U2026-10-15-BUY-6758.T-N100000", broker_id="222", order_date="20261016",
                      sent_at="2026-10-16T10:00:00+09:00")],
                  pos={"7203.T": {"shares": 100, "entry_px": 2400.0, "last_close": 2500.0, "entry_date": "2026-09-01"}})


def test_refresh_after_the_fill_day_keeps_its_open_fills(monkeypatch):
    for when in (SAT, dt.datetime(2026, 10, 19, 11, 35, tzinfo=JST)):     # 周六手动「看立花那边」/ 周一 07:40 没跑、11:35 的定时刷新
        b = _b_fri()
        _snap({"at": "2026-10-16 15:45:00", "source": "liveu.sh broker", "positions": [{"ticker": "6758.T", "qty": 100}],
               "buying_power": 450_000.0, "fills_at": "2026-10-16 15:45:00", "fills_day": "2026-10-16",
               "fills": [{"cid": "U2026-10-15-SELL-7203.T", "ticker": "7203.T", "side": "SELL", "kind": "stock", "qty": 100,
                          "filled_qty": 100, "avg_px": 2510.0, "status": "約定", "final": "FILLED"}]})
        pj0 = LO.held_now(b, "tachibana", now=when)
        assert "7203.T" not in pj0["pos"]
        monkeypatch.setattr(BS, "_now", lambda when=when: when)
        BS.refresh(_FB(), "tachibana", b)
        pj1 = LO.held_now(b, "tachibana", now=when)
        assert sorted(pj1["pos"]) == sorted(pj0["pos"]) and round(pj1["cash"]) == round(pj0["cash"]), (pj0["note"], pj1["note"])
        s = BS.load("tachibana")
        assert s.get("fills_day") == "2026-10-16" and any(f.get("cid") == "U2026-10-15-SELL-7203.T" and f.get("filled_qty") == 100
                                                          for f in s["fills"]), s["fills"]
        assert BS.fills_lines(s)                                           # 合并进来的行也能打印（不因缺字段崩）


# ────────── F11：快照里的成交是确定的、立花和账本 + 成交仍对不上 → 照样标红 ──────────
def test_broker_card_real_mismatch_on_a_ticker_traded_today_warns():
    b = _tbook([_o("7203.T", "SELL", status="SENT", qty=100, filled=0, px=0.0, reason="manual_trim", cid="U2026-10-15-SELL-7203.T",
                   broker_id="111", order_date="20261016")],
               pos={"7203.T": {"shares": 300, "entry_px": 2400.0, "last_close": 2500.0, "entry_date": "2026-09-01"}})
    s = {"at": "2026-10-16 11:35:00", "source": "liveu.sh broker", "positions": [], "buying_power": 1_250_000.0,
         "fills_at": "2026-10-16 11:35:00",
         "fills": [{"cid": "U2026-10-15-SELL-7203.T", "ticker": "7203.T", "side": "SELL", "kind": "stock", "qty": 100,
                    "filled_qty": 100, "avg_px": 2500.0, "status": "約定", "final": ""}]}
    s["compare"] = BS.compare(b, [])
    _snap(s)
    now = dt.datetime(2026, 10, 16, 12, 0, tzinfo=JST)
    pj = LO.held_now(b, "tachibana", now=now)
    assert pj["pos"]["7203.T"]["shares"] == 200 and pj["fills"][0]["src"] == "snapshot"
    h = panel._broker_card("tachibana", now, pj)
    assert "card warn" in h and "下一次早上的核对会停下" in _text(h)       # 账本 300 − 100 = 200 对立花 0：网站上另卖了 200 股


# ────────── F12：周末的立花卡不写「今天」、收盘后不写「还在等成交」──────────
def test_saturday_broker_card_and_after_close_pending_text():
    b = _tbook([_o("6758.T", "SELL", qty=200, filled=200, px=3000.0, phase="now", cid="U2026-10-15-SELL-6758.T-N100000",
                   sent_at="2026-10-16T10:00:00+09:00")],
               pos={"6758.T": {"shares": 200, "entry_px": 2900.0, "last_close": 3000.0, "entry_date": "2026-09-01"}})
    for at, positions in (("2026-10-16 15:45:00", []), ("2026-10-16 07:41:05", [{"ticker": "6758.T", "qty": 200}])):
        _snap({"at": at, "source": "x", "positions": positions, "buying_power": 1.0})
        pj = LO.held_now(b, "tachibana", now=SAT, snap={})
        assert pj["day_word"] == "10/16（周五）"
        t = _text(panel._broker_card("tachibana", SAT, pj))
        assert "今天" not in t.split("只读的快照")[0], t
    assert LO.hn_pending_text("今天", True) == LO.HN_PENDING
    p = LO.hn_pending_text("10/16（周五）", False)
    assert "已经收盘" in p and "还在等成交" not in p and p.startswith("10/16（周五）")
    b = _tbook([_o("7203.T", "BUY", status="SENT", qty=100, filled=0, ref_px=2500.0)])
    pj = LO.held_now(b, "paper", now=FRI1540, snap={})
    assert LO.HN_PENDING not in (pj.get("note") or "")


# ────────── F13：liveu.sh broker --notify 与面板同一个判断（正常的成交日不报「不一致」）──────────
class _FBn:
    spec = None

    def __init__(self, held: dict):
        self.held = held

    def positions(self):
        return {t: SimpleNamespace(qty=q, avg_px=2500.0) for t, q in self.held.items()}

    def cash(self):
        return 750_000.0

    def open_orders(self):
        return []

    def order_status(self, bid, od):
        return {"filled_qty": 100, "avg_px": 2500.0, "status": "約定", "final": "FILLED"}

    def logout(self):
        return None


def test_broker_notify_uses_the_same_compare_as_the_card(capsys, monkeypatch):
    import run
    from qbreak import calendar_jp as CJ
    from qbreak import notify
    now = dt.datetime(2026, 10, 16, 11, 35, tzinfo=JST)
    monkeypatch.setattr(CJ, "now_jst", lambda: now)
    monkeypatch.setattr(LO, "now_jst", lambda: now)
    monkeypatch.setattr(BS, "_now", lambda: now)
    monkeypatch.setattr(run, "_query_lock", lambda *a, **k: SimpleNamespace(release=lambda: None))
    sent = []
    monkeypatch.setattr(notify, "send", lambda title, body, **kw: sent.append((title, body, kw)))
    a = SimpleNamespace(broker="tachibana", demo=False, dry_run=False, notify=True, lock_wait=1)
    for held, rc, lvl in (({}, 0, "info"), ({"7203.T": 100}, 1, "warn")):     # 寄付卖光 100 股：立花 0 = 一致；立花还有 100 = 真的不一致
        b = _tbook([_o("7203.T", "SELL", status="SENT", qty=100, cid="U2026-10-15-SELL-7203.T", broker_id="111",
                       order_date="20261016", sent_at="2026-10-16T07:41:00+09:00")],
                   pos={"7203.T": {"shares": 100, "entry_px": 2400.0, "last_close": 2500.0, "entry_date": "2026-09-01"}})
        _write(b, "tachibana")
        monkeypatch.setattr(run, "_cancel_broker", lambda *a_, held=held: _FBn(held))
        sent.clear()
        assert run.cmd_live_broker(a) == rc
        out = capsys.readouterr().out
        assert ("不一致" in out) == (rc == 1), out
        assert len(sent) == 1 and sent[0][2]["level"] == lvl and ("不一致" in sent[0][1]) == (rc == 1), sent
        assert sent[0][0].startswith("qbreak 立花：今天的成交")
    assert re.search(NM.label("7203.T") + r".*立花 100", out) or "7203" in out
