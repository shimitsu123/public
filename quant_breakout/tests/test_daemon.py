"""守护进程测试：状态机、盘中止损、逆指値维护、差金決済、幂等、崩溃恢复。"""
import datetime as dt

import pytest

from qbreak import paths
from qbreak.brokers.base import BaseBroker, Order, Position
from qbreak.calendar_jp import JST
from qbreak.config import DataConfig, ExecConfig, RiskConfig, SizingConfig, StrategyParams
from qbreak.daemon import Daemon, DaemonConfig, DaemonState


class StubBroker(BaseBroker):
    """可完全控制的券商替身。"""
    market = "JP"

    def __init__(self, positions=None, prices=None, cash=1_000_000):
        self._pos = positions or {}
        self._px = prices or {}
        self._cash = cash
        self.orders: list[Order] = []
        self.stops: list[tuple] = []
        self.cancelled: list[str] = []
        self.synced = 0

    def get_price(self, t):
        if t not in self._px:
            raise KeyError(t)
        return self._px[t]

    def quotes(self, ts):
        return {t: self._px[t] for t in ts if t in self._px}

    def positions(self):
        return {t: Position(**{**p.to_dict(), "ticker": t}) for t, p in self._pos.items()}

    def cash(self):
        return self._cash

    def sync(self):
        self.synced += 1

    def update_position(self, pos):
        if pos.ticker in self._pos:
            self._pos[pos.ticker] = pos

    def buy(self, t, qty, limit=None, client_id="", ref_px=None, bar=""):
        o = Order(t, "BUY", qty, limit or 0, "now", "FILLED", qty, self._px.get(t, 0), client_id)
        self.orders.append(o)
        return o

    def sell(self, t, qty, limit=None, client_id="", ref_px=None, bar=""):
        o = Order(t, "SELL", qty, limit or 0, "now", "FILLED", qty, self._px.get(t, 0), client_id)
        self.orders.append(o)
        self._pos.pop(t, None)
        return o

    def place_protective_stop(self, t, qty, trigger, client_id=""):
        self.stops.append((t, qty, trigger, client_id))
        return Order(t, "SELL", qty, 0, "now", "SENT", client_id=client_id)

    def cancel(self, client_id):
        self.cancelled.append(client_id)
        return True


P = StrategyParams(stop_loss_pct=7.0, trailing_stop_pct=12.0, take_profit_pct=25.0,
                   exit_on_macd_dead_cross=False)
RISK = RiskConfig(daily_max_loss_pct=99.0, max_drawdown_pct=99.0, require_arm=False)
SIZING = SizingConfig(initial_cash=1_000_000)
DATA = DataConfig(provider="csv", years=2, min_bars=50)
EX = ExecConfig(market="JP", commission_pct=0.0, slippage_pct=0.0)


def _daemon(broker, **kw):
    cfg = DaemonConfig(**kw.pop("cfg", {}))
    d = Daemon(["7203.T"], broker, P, RISK, SIZING, DATA, EX, cfg=cfg, **kw)
    return d


def _pos(avg=1000.0, qty=100, peak=None, stop=None):
    return Position(ticker="7203.T", qty=qty, avg_px=avg, peak=peak or avg,
                    stop_px=stop or avg * 0.93, entry_date="2026-09-22", hold_bars=1)


MORNING = dt.datetime(2026, 9, 24, 10, 0, tzinfo=JST)
LUNCH = dt.datetime(2026, 9, 24, 12, 0, tzinfo=JST)
PRE = dt.datetime(2026, 9, 24, 8, 55, tzinfo=JST)
POST = dt.datetime(2026, 9, 24, 15, 45, tzinfo=JST)
HOLIDAY = dt.datetime(2026, 9, 27, 10, 0, tzinfo=JST)      # 日曜


# ────────── 状态机 ──────────
def test_closed_day_sleeps_long_and_does_nothing():
    b = StubBroker({"7203.T": _pos()}, {"7203.T": 500.0})   # 价格已跌破止损
    d = _daemon(b)
    s = d.tick(HOLIDAY)
    assert s > 3000 and not b.orders                        # 休市日绝不下单


def test_lunch_break_does_not_trade():
    b = StubBroker({"7203.T": _pos()}, {"7203.T": 500.0})
    d = _daemon(b)
    d.tick(LUNCH)
    assert not b.orders


def test_premarket_reconciles_once():
    b = StubBroker({"7203.T": _pos()}, {"7203.T": 1000.0})
    d = _daemon(b)
    d.tick(PRE)
    assert b.synced == 1 and d.st.premarket_done
    d.tick(PRE)
    assert b.synced == 1                                    # 不重复


def test_heartbeat_written_every_tick():
    d = _daemon(StubBroker())
    d.tick(MORNING)
    hb = paths.home() / "heartbeat.json"
    assert hb.exists() and "session" in hb.read_text(encoding="utf-8")


# ────────── 盘中出场 ──────────
def test_intraday_stop_loss_sells():
    b = StubBroker({"7203.T": _pos(avg=1000)}, {"7203.T": 920.0})   # 止损 930
    d = _daemon(b)
    d.tick(MORNING)
    assert len(b.orders) == 1 and b.orders[0].side == "SELL"


def test_intraday_take_profit_sells():
    b = StubBroker({"7203.T": _pos(avg=1000)}, {"7203.T": 1260.0})  # 止盈 1250
    d = _daemon(b)
    d.tick(MORNING)
    assert b.orders and b.orders[0].side == "SELL"


def test_trailing_stop_uses_live_peak():
    # 1200 は止盈(1250)に届かないので出場しない → 峰値だけ上がる
    b = StubBroker({"7203.T": _pos(avg=1000, peak=1000)}, {"7203.T": 1200.0})
    d = _daemon(b, cfg={"protective_stop": False})
    d.tick(MORNING)
    assert not b.orders
    b._px["7203.T"] = 1050.0                          # 1200×0.88 = 1056 → 跟踪止损触发
    d.tick(MORNING)
    assert b.orders and b.orders[0].side == "SELL"
    # 出场原因必须是跟踪止损（1056），不是固定止损（930）
    assert "trail" in (d._exit_check(_pos(avg=1000, peak=1200.0), 1050.0) or "")


def test_no_exit_when_price_in_range():
    b = StubBroker({"7203.T": _pos(avg=1000)}, {"7203.T": 1010.0})
    d = _daemon(b)
    d.tick(MORNING)
    assert not b.orders


def test_intraday_exit_is_idempotent():
    b = StubBroker({"7203.T": _pos(avg=1000)}, {"7203.T": 900.0})
    d = _daemon(b)
    d.tick(MORNING)
    b._pos["7203.T"] = _pos(avg=1000)                 # 模拟持仓未及时消失
    d.tick(MORNING)
    assert len(b.orders) == 1                         # 同一交易日不会卖两次


def test_dry_run_never_sends():
    b = StubBroker({"7203.T": _pos(avg=1000)}, {"7203.T": 900.0})
    d = _daemon(b, dry_run=True)
    d.tick(MORNING)
    assert not b.orders and not b.stops


# ────────── 逆指値 ──────────
def test_protective_stop_placed_and_raised_with_peak():
    b = StubBroker({"7203.T": _pos(avg=1000)}, {"7203.T": 1000.0})
    d = _daemon(b)
    d.tick(MORNING)
    assert b.stops and b.stops[-1][2] == pytest.approx(930.0)     # 固定止损
    b._px["7203.T"] = 1100.0                                      # 未到止盈 1250
    d.tick(MORNING)
    assert b.stops[-1][2] == pytest.approx(1100 * 0.88)           # 跟随峰值上移
    assert b.cancelled                                            # 旧单被撤掉


def test_protective_stop_not_rechurned_for_tiny_moves():
    b = StubBroker({"7203.T": _pos(avg=1000)}, {"7203.T": 1000.0})
    d = _daemon(b)
    d.tick(MORNING)
    n = len(b.stops)
    b._px["7203.T"] = 1001.0
    d.tick(MORNING)
    assert len(b.stops) == n                        # 变动 < 阈值 → 不撤不改


def test_intraday_exit_cancels_protective_stop_first():
    b = StubBroker({"7203.T": _pos(avg=1000)}, {"7203.T": 1000.0})
    d = _daemon(b)
    d.tick(MORNING)                                  # 先挂上逆指値
    b._px["7203.T"] = 900.0
    d.tick(MORNING)
    assert b.cancelled                               # 避免"重复卖出"
    assert any(o.side == "SELL" for o in b.orders)


# ────────── 差金決済 ──────────
def test_same_day_rebuy_blocked():
    b = StubBroker({"7203.T": _pos(avg=1000)}, {"7203.T": 900.0})
    d = _daemon(b)
    d.tick(MORNING)
    ok, why = d.can_open("7203.T")
    assert not ok and "差金決済" in why


def test_other_ticker_still_allowed():
    b = StubBroker({"7203.T": _pos(avg=1000)}, {"7203.T": 900.0})
    d = _daemon(b)
    d.tick(MORNING)
    assert d.can_open("6758.T")[0]                   # 乗り換え売買は可能


# ────────── 状态持久化 / 崩溃恢复 ──────────
def test_state_survives_restart():
    b = StubBroker({"7203.T": _pos(avg=1000)}, {"7203.T": 900.0})
    _daemon(b).tick(MORNING)
    st = DaemonState.load()
    assert "7203.T" in st.sold_today and st.round_trips["7203.T"] == 1


def test_new_day_resets_counters():
    d = _daemon(StubBroker())
    d.st.date = "2026-09-23"
    d.st.sold_today = ["7203.T"]
    d.st.eod_done = True
    d.tick(MORNING)                                  # 9/24
    assert d.st.sold_today == [] and not d.st.eod_done


def test_tick_never_raises_on_broker_failure():
    class Broken(StubBroker):
        def positions(self):
            raise RuntimeError("API 挂了")
    d = _daemon(Broken())
    assert d.tick(MORNING) > 0                       # 捕获后继续，不能让守护进程死掉


def test_quote_failure_does_not_sell_blindly():
    b = StubBroker({"7203.T": _pos(avg=1000)}, {})   # 取不到价
    d = _daemon(b)
    d.tick(MORNING)
    assert not b.orders                              # 没有价格就什么都不做
