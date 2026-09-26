"""券商层测试：持久化、幂等、ARM 闸门、呼値取整、约定核对、次日开盘成交。"""
import pytest

from qbreak import paths
from qbreak.brokers import PaperBroker
from qbreak.brokers.rakuten_rss import FakeExcelBridge, RakutenRSSBroker
from qbreak.config import ExecConfig
from qbreak.tick import round_to_tick, tick_size


# ────────── PaperBroker ──────────
def _paper(**kw):
    ex = ExecConfig(market="JP", commission_pct=0.0, slippage_pct=0.0)
    return PaperBroker(initial_cash=1_000_000, exec_cfg=ex, **kw)


def test_state_survives_restart():
    b = _paper(defer_to_next_open=False)
    b.set_prices({"A.T": 1000.0})
    b.buy("A.T", 100, client_id="c1")
    b2 = _paper(defer_to_next_open=False)
    assert b2.positions()["A.T"].qty == 100
    assert b2.cash() == pytest.approx(900_000)


def test_idempotent_client_id():
    b = _paper(defer_to_next_open=False)
    b.set_prices({"A.T": 1000.0})
    assert b.buy("A.T", 100, client_id="c1").status == "FILLED"
    assert b.buy("A.T", 100, client_id="c1").status == "REJECTED"
    assert b.positions()["A.T"].qty == 100


def test_peak_is_persisted():
    """原版把 peak 只放在内存里，跟踪止损每天被重置 —— 这里必须能跨进程保留。"""
    b = _paper(defer_to_next_open=False)
    b.set_prices({"A.T": 1000.0})
    b.buy("A.T", 100, client_id="c1")
    pos = b.positions()["A.T"]
    pos.peak = 1500.0
    b.update_position(pos)
    assert _paper(defer_to_next_open=False).positions()["A.T"].peak == 1500.0


def test_rejects_insufficient_cash_and_position():
    b = _paper(defer_to_next_open=False)
    b.set_prices({"A.T": 1000.0})
    assert b.buy("A.T", 10_000, client_id="a").status == "REJECTED"
    assert b.sell("A.T", 100, client_id="b").status == "REJECTED"
    assert b.cash() == 1_000_000


def test_equity_does_not_crash_without_price():
    b = _paper(defer_to_next_open=False)
    b.set_prices({"A.T": 1000.0})
    b.buy("A.T", 100, client_id="c1")
    b._prices.clear()                      # 模拟这只票今天取不到行情
    assert b.equity() == pytest.approx(1_000_000)   # 退回成本价，不抛 KeyError


def test_deferred_fill_at_next_open():
    b = _paper()
    b.set_prices({"A.T": 1000.0})
    o = b.buy("A.T", 100, client_id="c1", ref_px=1000.0, bar="2026-01-05")
    assert o.status == "SENT" and not b.positions()
    fills = b.fill_pending({"A.T": 1020.0}, "2026-01-06")
    assert fills[0].status == "FILLED"
    assert b.positions()["A.T"].avg_px == pytest.approx(1020.0)


def test_deferred_order_expires_on_big_gap():
    b = _paper()
    b.set_prices({"A.T": 1000.0})
    b.buy("A.T", 100, client_id="c1", ref_px=1000.0, bar="2026-01-05")
    fills = b.fill_pending({"A.T": 1200.0}, "2026-01-06", max_gap_pct=3.0)
    assert fills[0].status == "REJECTED" and not b.positions()


def test_corrupt_state_file_is_quarantined_not_silently_ignored():
    b = _paper(defer_to_next_open=False)
    b.path.write_text("{ broken", encoding="utf-8")
    _paper(defer_to_next_open=False)               # 不应抛异常
    assert list(b.path.parent.glob("*.corrupt.*"))


# ────────── RakutenRSSBroker ──────────
def _rss(**kw):
    bridge = FakeExcelBridge(quotes={"7203": 2987.0}, positions=[[7203, 300, 2400.0]],
                             cash=500_000)
    return RakutenRSSBroker(bridge=bridge, **kw), bridge


def test_arm_gate_blocks_orders():
    br, bridge = _rss()
    o = br.buy("7203.T", 100, client_id="c1")
    assert o.status == "BLOCKED" and "ARM" in o.note
    assert not bridge.sent                      # 一个字节都没发出去


def test_halt_file_blocks_orders():
    br, bridge = _rss()
    bridge.write("Ctrl", "ARM", "ARMED")
    paths.halt_file().write_text("test", encoding="utf-8")
    assert br.buy("7203.T", 100, client_id="c1").status == "BLOCKED"
    assert not bridge.sent


def test_limit_price_snaps_to_legal_tick():
    br, bridge = _rss(limit_buffer_pct=0.5)
    bridge.write("Ctrl", "ARM", "ARMED")
    o = br.buy("7203.T", 100, client_id="c1")
    # 2987×1.005 = 3001.9 属于 3000 円超价格带（呼値 5 円），必须落到合法格点
    assert o.price % tick_size(o.price) == 0
    assert o.price == 3000.0


def test_partial_and_unfilled_are_reported():
    br, bridge = _rss(confirm_timeout_s=0.5)
    bridge.write("Ctrl", "ARM", "ARMED")
    bridge.fill_ratio = 0.5
    o = br.buy("7203.T", 100, client_id="c1")
    assert o.status == "PARTIAL" and o.filled_qty == 50
    bridge.fill_ratio = 0.0
    o2 = br.buy("7203.T", 100, client_id="c2")
    assert o2.status == "SENT" and "未约定" in o2.note


def test_positions_and_cash_come_from_broker_side():
    br, _ = _rss()
    assert br.positions()["7203.T"].qty == 300
    assert br.cash() == 500_000


def test_opening_condition_when_placed_after_close():
    br, bridge = _rss()
    bridge.write("Ctrl", "ARM", "ARMED")
    br.buy("7203.T", 100, client_id="c1", bar="2026-01-05")
    assert bridge.sent[-1]["condition"] == "OPENING"


def test_protective_stop_payload():
    br, bridge = _rss()
    bridge.write("Ctrl", "ARM", "ARMED")
    br.place_protective_stop("7203.T", 100, 2777.7, client_id="s1")
    sent = bridge.sent[-1]
    assert sent["order_type"] == "STOP" and sent["trigger"] == round_to_tick(2777.7, "7203.T", "SELL")


def test_no_arm_required_mode():
    br, bridge = _rss(require_arm=False)
    assert br.buy("7203.T", 100, client_id="c1").status == "FILLED"


def test_dry_run_never_sends():
    br, bridge = _rss(dry_run=True, require_arm=False)
    assert br.buy("7203.T", 100, client_id="c1").status == "BLOCKED"
    assert not bridge.sent


def test_deferred_order_expires_when_a_session_was_skipped():
    """数据延迟一天再补成交 = 事后下单（前视），必须作废。"""
    b = _paper()
    b.set_prices({"A.T": 1000.0})
    b.buy("A.T", 100, client_id="c1", ref_px=1000.0, bar="2026-01-05")
    fills = b.fill_pending({"A.T": 1010.0}, "2026-01-07", prev_bars={"A.T": "2026-01-06"})
    assert fills[0].status == "REJECTED" and "数据延迟" in fills[0].note and not b.positions()
    b.buy("A.T", 100, client_id="c2", ref_px=1000.0, bar="2026-01-07")
    fills = b.fill_pending({"A.T": 1010.0}, "2026-01-08", prev_bars={"A.T": "2026-01-07"})
    assert fills[0].status == "FILLED"
