"""〔77〕C：「立花那边实际是什么」快照 + 今天的成交（qbreak/broker_snapshot.py；只读）与现金差的拆分说明（UX-08 / T3）。"""
import datetime as dt
import json

from qbreak import broker_snapshot as BS
from qbreak import paths
from qbreak.brokers.base import Position
from qbreak.brokers.tachibana import TachibanaSpec
from qbreak.calendar_jp import JST
from qbreak.live_unified import UnifiedExecutor

SPEC = TachibanaSpec()
TODAY = dt.datetime.now(JST).date()


class FakeBroker:
    spec = SPEC

    def __init__(self):
        self.calls = []

    def positions(self):
        return {"7203.T": Position("7203.T", 200, 2400.0), "1545.T": Position("1545.T", 4110, 241.9),
                "9999.T": Position("9999.T", 100, 10.0)}

    def cash(self):
        return 12345.0

    def open_orders(self):
        return [{SPEC.r_list_code: "7203", SPEC.r_list_side: SPEC.side_buy, SPEC.r_list_qty: "100", SPEC.r_list_price: "0",
                 SPEC.r_list_filled_qty: "100", SPEC.r_list_filled_px: "3001", SPEC.r_list_status: "全部約定",
                 SPEC.r_list_order_no: "A0001", SPEC.r_list_time: TODAY.strftime("%Y%m%d") + "090001"}]

    def order_status(self, broker_id, order_date):
        self.calls.append(broker_id)
        if broker_id == "BAD":
            raise RuntimeError("x")
        return {"filled_qty": 100, "avg_px": 3001.0, "status": "全部約定", "final": "FILLED"}

    def quotes(self, tickers):
        return {t: 3010.0 for t in tickers}


def _book():
    d = TODAY.strftime("%Y%m%d")
    return {"state": {"pos": {"7203.T": {"shares": 100}}, "core_units": {"1545.T": 4110}},
            "orders": [{"cid": "c1", "ticker": "7203.T", "side": "BUY", "kind": "stock", "qty": 100, "sent_qty": 100,
                        "status": "SENT", "broker_id": "A0001", "order_date": d},
                       {"cid": "c2", "ticker": "6758.T", "side": "SELL", "kind": "stock", "qty": 100,
                        "status": "SENT", "broker_id": "BAD", "order_date": d},
                       {"cid": "old", "ticker": "6758.T", "side": "SELL", "kind": "stock", "qty": 100,
                        "status": "FILLED", "broker_id": "Z9", "order_date": "20200101"}]}


def test_refresh_writes_snapshot_with_compare_fills_and_quotes():
    br = FakeBroker()
    snap = BS.refresh(br, "tachibana", _book(), managed={"7203.T", "1545.T"})
    on_disk = json.loads(BS.path("tachibana").read_text(encoding="utf-8"))
    assert on_disk["buying_power"] == 12345 and on_disk["book"] == "tachibana"
    assert {r["ticker"]: r["diff"] for r in snap["compare"]} == {"7203.T": 100, "1545.T": 0, "9999.T": 100}
    assert snap["foreign"] == ["9999.T"]
    assert br.calls == ["A0001", "BAD"]                                    # 只查今天的单
    assert snap["orders"][0]["ticker"] == "7203.T" and snap["orders"][0]["side"] == "BUY"
    assert snap["quotes"]["7203.T"] == 3010.0
    lines = BS.fills_lines(snap)
    assert "成交 100/100 股 @ ¥3,001.0" in lines[0] and "读不了约定" in lines[1]
    assert any("7203.T" in ln for ln in BS.diff_lines(snap))
    assert "auth" not in json.dumps(on_disk).lower()                      # 不带认证类字段


def test_record_check_keeps_previous_orders_and_quotes():
    BS.refresh(FakeBroker(), "tachibana", _book())
    BS.record_check("tachibana", {"7203.T": Position("7203.T", 100, 2400.0)}, 999.0, _book())
    s = BS.load("tachibana")
    assert s["source"] == "执行器核对" and s["buying_power"] == 999
    assert s["orders"] and s["quotes"] and s["fills_at"]                   # 注文 / 成交 / 现价留着（带它们自己的时刻）
    assert [r["diff"] for r in s["compare"] if r["ticker"] == "7203.T"] == [0]
    assert paths.out_dir() in BS.path("x").parents


def test_drift_explained_by_estimated_tax_is_info():
    why, lvl = UnifiedExecutor._drift_why(-20315.0, 20315.0)
    assert lvl == "info" and "譲渡益税代扣" in why
    why, lvl = UnifiedExecutor._drift_why(-300.0, 0.0)
    assert lvl == "info" and "小额差" in why
    why, lvl = UnifiedExecutor._drift_why(-80000.0, 20315.0)
    assert lvl == "warn" and "其中预计譲渡益税代扣 ¥20,315" in why
    assert UnifiedExecutor._drift_why(50000.0, 0.0)[1] == "warn"


def test_tax_pending_counts_each_withholding_once_and_expires():
    """〔77〕C 审查：同一笔譲渡益税只在现金差里解释一次（以前最近 5 天每天早上都扣一次，会误报「现金突然变化，请登记入金」）。"""
    from types import SimpleNamespace

    class F:
        _tax_now = UnifiedExecutor._tax_now
        _tax_pending = UnifiedExecutor._tax_pending
        _tax_seen = UnifiedExecutor._tax_seen

    day = [dt.date(2026, 10, 6)]
    f = F()
    f.eng = SimpleNamespace(st=SimpleNamespace(trades=[{"ticker": "7203.T", "market": "JP", "exit_date": "2026-10-05",
                                                          "shares": 100, "exit_px": 4000, "pnl_jpy": 300000}], core_trades=[]))
    f.book = {}
    f.clock = lambda: dt.datetime.combine(day[0], dt.time(7, 40), JST)
    assert round(f._tax_pending()) == round(300000 * 0.20315)
    f._tax_seen()                                              # 这天的现金差对上了
    day[0] = dt.date(2026, 10, 7)
    assert f._tax_pending() == 0                                # 第二天不再拿它解释
    f.eng.st.trades.append({"ticker": "6758.T", "market": "JP", "exit_date": "2026-10-07", "shares": 100, "exit_px": 1,
                            "pnl_jpy": -100000})
    assert round(f._tax_pending()) == round(-100000 * 0.20315)  # 新的亏损 → 还付
    day[0] = dt.date(2026, 10, 20)                              # 挂了 7 天以上还没见到 → 当作已经见到
    assert f._tax_pending() == 0 and f.book["tax_seen"]["w"] == round(200000 * 0.20315, 2)


def test_withdrawal_reserve_register_release_and_expiry(tmp_path):
    """〔77〕C LU-19：登记出金时预留 → 到账前决策按扣掉它算；现金差对上（到账）自动解除；14 天还没对上也解除并提醒。入金不能预留。"""
    import pytest
    from types import SimpleNamespace
    from qbreak.live_unified import RESERVE_DAYS, register_flow, reserve_jpy, reserves
    bp = tmp_path / "live_unified_tachibana.json"
    bp.write_text(json.dumps({"state": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="只用于出金"):
        register_flow(bp, 100000, reserve=True)
    rec = register_flow(bp, -300000, "x", "2026-10-06", reserve=True)
    book = json.loads(bp.read_text(encoding="utf-8"))
    assert rec["reserve"] and reserve_jpy(book) == 300000 and len(reserves(book)) == 1

    class F:
        _reserve_now = UnifiedExecutor._reserve_now

        def __init__(self):
            self.events = []

        def _event(self, lvl, msg):
            self.events.append((lvl, msg))
    day = [dt.date(2026, 10, 8)]
    f = F()
    f.book = book
    f.clock = lambda: dt.datetime.combine(day[0], dt.time(7, 40), JST)
    assert f._reserve_now() == 300000 and "出金预留 ¥300,000" in f.events[-1][1]
    book["flows"][0]["seen_after"] = "2026-10-08"                       # 到账（现金差对上）→ 自动解除
    assert f._reserve_now() == 0 and reserve_jpy(book) == 0
    del book["flows"][0]["seen_after"]
    day[0] = dt.date(2026, 10, 6) + dt.timedelta(days=RESERVE_DAYS + 1)  # 14 天还没对上 → 解除并提醒
    assert f._reserve_now() == 0 and f.events[-1][0] == "warn" and book["flows"][0]["reserve_released"]


def test_reserve_explains_missing_holdings_vs_sim():
    """出金预留期间实盘少拿了几只（钱少了）→ 与云端比较标「预期」，不算不一致；实盘多拿了别的票 → 照常算不一致。"""
    from qbreak.live_unified import compare_bad, compare_with_sim
    from qbreak.unified import UPos, UState

    def st(pos, core):
        s = UState(cash_jpy=0.0, last_date="2026-10-08", history=[["2026-10-07", 1.0, 0, 0, 1], ["2026-10-08", 1.0, 0, 0, 1]])
        s.pos = {t: UPos(t, "JP", 100, 1.0, "2026-10-01", 0.9, 1.0, 1.0) for t in pos}
        s.core_units = dict(core)
        return s
    sim = st(["7203.T", "6758.T"], {"1545.T": 100})
    live = st(["7203.T"], {})
    book = {"flows": [{"date": "2026-10-07", "jpy": -300000.0, "reserve": True}],
            "compare_history": [{"date": "2026-10-01", "comparable": True, "same": True}]}
    c = compare_with_sim(live, sim, live=True, book=book)
    assert c["explained"] == "出金预留" and not compare_bad(c) and "6758.T" in c["text"]
    c2 = compare_with_sim(st(["7203.T", "9984.T"], {}), sim, live=True, book=book)      # 实盘多了 9984 → 真的不同
    assert compare_bad(c2) and not c2.get("explained")
    book["flows"][0]["seen_after"] = "2026-10-01"                                       # 早就到账了 → 不再解释
    assert compare_bad(compare_with_sim(live, sim, live=True, book=book))
