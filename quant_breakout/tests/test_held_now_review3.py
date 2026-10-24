"""「持仓反映今天成交」（live_ops.held_now；2026-10-16）三次复核的回归测试（G1〜G5）：立花只在快照里显示成交的手动买入，
对账之后执行的卖出 / 调仓不再被挡；盘中固定口数的预览不再叫用户等一张已经全部成交的单；周末的「照比例」那一行写成交日；
立花对照卡把快照之后撤单记下的部分成交算成快照之后；liveu.sh broker 拿到锁之后再读账本。执行器（live_unified）不改。"""
import datetime as dt
import json
from types import SimpleNamespace

from qbreak import broker_snapshot as BS
from qbreak import live_ops as LO
from qbreak import manual_orders as MO
from qbreak import panel, paths
from qbreak.calendar_jp import JST

from test_held_now import _o, _tbook
from test_panel_held_now import _text, _write

SAT = dt.datetime(2026, 10, 17, 10, 0, tzinfo=JST)                     # 周六（成交日 10/16 周五）
FRI13 = dt.datetime(2026, 10, 16, 13, 0, tzinfo=JST)                  # 成交日盘中（午后）


def _snap(d: dict, tag: str = "tachibana") -> None:
    paths.out_dir().mkdir(parents=True, exist_ok=True)
    (paths.out_dir() / f"broker_snapshot_{tag}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


# ────────── G1：立花今天手动买入、只在快照里显示成交 → 周末写卖出 / 调仓不挡（部分成交仍挡）──────────
def _buy_book() -> dict:
    b = _tbook([_o(status="SENT", qty=100, filled=0, reason="manual_buy", ref_px=2500.0)])   # 立花：寄付单对账前整天 SENT
    b["manual"] = {"items": {"M-buy-7203": {"id": "M-buy-7203", "kind": "buy", "ticker": "7203.T", "status": "placed",
                                            "unit": "rule", "decided_on": "2026-10-15", "at": "2026-10-15T20:00:00+09:00"}},
                   "core_pct": 100.0, "buys": {"7203.T": {"decided_on": "2026-10-15"}}}
    return b


def test_tachibana_snapshot_filled_manual_buy_does_not_block_weekend_sell():
    for filled, ok in ((100, True), (50, False)):
        _snap({"at": "2026-10-16 15:45:00", "fills_at": "2026-10-16 15:45:00", "fills_day": "2026-10-16", "positions": [],
               "fills": [{"cid": "U2026-10-15-BUY-7203.T-0", "filled_qty": filled, "avg_px": 2490.0}], "compare": []})
        b = _buy_book()
        assert LO.held_now(b, "tachibana", now=SAT)["new"] == ["7203.T"]
        sell = MO.check({"kind": "sell", "ticker": "7203.T"}, b, "tachibana", now=SAT)
        adj = MO.check({"kind": "adjust", "ticker": "7203.T", "unit": "shares", "value": 0}, b, "tachibana", now=SAT)
        if ok:
            assert sell is None and adj is None, (sell, adj)
        else:                                                              # 部分成交：买入还没处理完 → 仍挡
            assert sell and "没处理完" in sell and adj and "没处理完" in adj


# ────────── G2：盘中固定口数 / 恢复按规则：快照显示已经全部成交的单不叫用户「先等它成交」──────────
def _core_book(filled: int) -> dict:
    _snap({"at": "2026-10-16 11:35:00", "fills_at": "2026-10-16 11:35:00", "fills_day": "2026-10-16", "positions": [],
           "fills": [{"cid": "U2026-10-15-BUY-1482.T-0", "filled_qty": filled, "avg_px": 1484.0}], "compare": []})
    b = _tbook([_o(t="1482.T", side="BUY", status="SENT", qty=650, kind="core", phase="morning", broker_id="B1",
                   order_date="20261016", limit=1512.0, ref_px=1483.0)], core={"1482.T": 0, "1545.T": 4110})
    b["state"]["cash_jpy"] = 2_000_000.0
    b["core_rule"] = {"px": {"1482.T": 1483.0, "1545.T": 236.4}, "lot": {"1482.T": 1, "1545.T": 10},
                      "units100": {"1482.T": 650, "1545.T": 4110}, "rule100": {"1482.T": 650}, "applied": 100.0}
    b["manual"] = {"items": {}, "core_pct": 100.0, "core_fix": {}, "core": ["1482.T", "1545.T"]}
    return b


def test_intraday_corefix_preview_does_not_wait_for_a_snapshot_filled_order():
    b = _core_book(650)
    pv = MO.corefix_preview(b, "tachibana", {"kind": "corefix", "ticker": "1482.T", "units": 700}, FRI13)
    assert "现在 650 口 → 固定 700 口（买入 50 口）" in pv["text"]
    assert "已经在交易所" not in pv["text"] and "一会儿再试" not in pv["text"], pv["text"]
    assert "买 650 口 已成交（快照，对账前的预计）→ 已算进现在的口数" in pv["text"]
    b = _core_book(300)                                                    # 部分成交：还剩的照旧先等（fix_prep 同一个判断）
    pv = MO.corefix_preview(b, "tachibana", {"kind": "corefix", "ticker": "1482.T", "units": 700}, FRI13)
    assert "买 650 口（已成交 300 口，还剩 350 口） 已经在交易所 → 先等它成交" in pv["text"], pv["text"]


def test_intraday_clear_text_does_not_call_a_filled_order_still_open():
    b = _core_book(650)
    b["manual"]["core_fix"] = {"1482.T": 700}
    t = MO.corefix_clear_text(b, "1482.T", "tachibana", FRI13)
    assert "还挂着" not in t and "已成交（快照，对账前的预计）→ 已算进现在的口数" in t, t
    b = _core_book(300)
    b["manual"]["core_fix"] = {"1482.T": 700}
    t = MO.corefix_clear_text(b, "1482.T", "tachibana", FRI13)
    assert "（已成交 300 口，还剩 350 口） 还挂着" in t, t


# ────────── G3：周末 / 对账前的「照比例」那一行写成交日，口数已含成交 ──────────
def test_intraday_ratio_line_names_the_fill_day():
    from test_manual_core import _pbook
    _pbook(orders=[{"cid": "U2026-10-05-SELL-1655.T-N100000", "ticker": "1655.T", "side": "SELL", "kind": "core", "qty": 130,
                    "decided_on": "2026-10-05", "reason": "manual_core", "phase": "now", "status": "FILLED",
                    "filled_qty": 130, "filled_px": 700.0}])
    h = panel.render("paper", "tok", now=dt.datetime(2026, 10, 7, 6, 0, tzinfo=JST))   # 成交日 10/6 的第二天、07:40 对账之前
    assert "10/6（周二）盘中已照比例卖出 130 口（已成交）：上面的口数已含（对账前）；今天 07:40 对账后正式记账" in h, \
        [x for x in _text(h).split("  ") if "照比例" in x]
    assert "今天盘中已照比例" not in h


# ────────── G4：立花对照卡：快照记 0 成交、之后撤单记下部分成交 → 算快照之后，不报「不一致」──────────
def test_cancel_after_partial_fill_post_snapshot_is_late_not_mismatch():
    b = _tbook([_o("7203.T", "SELL", status="CANCELLED", qty=100, filled=50, px=2500.0, phase="now", reason="manual_trim",
                   cid="U2026-10-15-SELL-7203.T-N110000", sent_at="2026-10-16T11:00:00+09:00", broker_id="9", order_date="20261016")],
               pos={"7203.T": {"shares": 300, "entry_px": 2400.0, "last_close": 2500.0, "entry_date": "2026-09-01"}})
    s = {"at": "2026-10-16 11:35:00", "source": "liveu.sh broker", "positions": [{"ticker": "7203.T", "qty": 300}],
         "buying_power": 1.0, "fills_at": "2026-10-16 11:35:00", "fills_day": "2026-10-16",
         "fills": [{"cid": "U2026-10-15-SELL-7203.T-N110000", "ticker": "7203.T", "side": "SELL", "kind": "stock", "qty": 100,
                    "filled_qty": 0, "avg_px": 0.0, "status": "注文中", "final": ""}]}
    s["compare"] = BS.compare(b, s["positions"])
    _snap(s)
    now = dt.datetime(2026, 10, 16, 14, 30, tzinfo=JST)
    pj = LO.held_now(b, "tachibana", now=now)
    assert pj["pos"]["7203.T"]["shares"] == 250
    cm = LO.broker_compare(BS.load("tachibana"), pj)
    assert not cm["bad"] and not cm["soft"] and cm["late"] == {"7203.T"}
    assert "card warn" not in panel._broker_card("tachibana", now, pj)
    s["positions"] = [{"ticker": "7203.T", "qty": 200}]                    # 真的不一致（立花比快照前的账本少 100）照样报
    _snap(s)
    cm = LO.broker_compare(BS.load("tachibana"), pj)
    assert [r["ticker"] for r in cm["bad"]] == ["7203.T"]


# ────────── G5：liveu.sh broker 在执行器跑着时等锁 → 锁放开后按对账之后的账本写快照 ──────────
class _FB0:
    spec = None

    def positions(self):
        return {}

    def cash(self):
        return 750_000.0

    def open_orders(self):
        return []

    def order_status(self, bid, od):
        return {"filled_qty": 100, "avg_px": 2500.0, "status": "約定", "final": "FILLED"}

    def logout(self):
        return None


def test_live_broker_reads_the_ledger_after_the_lock(capsys, monkeypatch):
    import run
    from qbreak import calendar_jp as CJ
    now = dt.datetime(2026, 10, 19, 7, 45, tzinfo=JST)                    # 周一：执行器 07:40 正在对账
    monkeypatch.setattr(CJ, "now_jst", lambda: now)
    monkeypatch.setattr(LO, "now_jst", lambda: now)
    monkeypatch.setattr(BS, "_now", lambda: now)
    old = _tbook([_o("7203.T", "SELL", status="SENT", qty=100, cid="U2026-10-15-SELL-7203.T", broker_id="111",
                     order_date="20261016", sent_at="2026-10-16T07:41:00+09:00")],
                 pos={"7203.T": {"shares": 100, "entry_px": 2400.0, "last_close": 2500.0, "entry_date": "2026-09-01"}})
    _write(old, "tachibana")
    new = _tbook([])                                                       # 执行器对过账：周五卖光的 100 股已经记了
    new["state"].update(last_date="2026-10-16", history=[["2026-10-16", 1_000_000.0, 750_000.0, 0, 150]], cash_jpy=750_000.0)

    def lock(*a, **k):
        _write(new, "tachibana")                                           # 等锁的时候执行器写完了账本
        return SimpleNamespace(release=lambda: None)
    monkeypatch.setattr(run, "_query_lock", lock)
    monkeypatch.setattr(run, "_cancel_broker", lambda *a_: _FB0())
    a = SimpleNamespace(broker="tachibana", demo=False, dry_run=False, notify=False, lock_wait=1)
    assert run.cmd_live_broker(a) == 0
    out = capsys.readouterr().out
    s = BS.load("tachibana")
    assert s["fills_day"] == "2026-10-19" and not [r for r in s["compare"] if r.get("diff")], s["compare"]
    assert "不一致" not in out, out
    pj = LO.held_now(new, "tachibana", now=now)
    assert "card warn" not in panel._broker_card("tachibana", now, pj)
