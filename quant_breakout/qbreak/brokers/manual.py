"""manual.py — 半自动模式的「券商」：持仓由你手工登记，程序只算不发单。

用途：留在楽天（或任何没有 API 的券商），Mac 上跑信号与风控，
每天收到一张操作清单（买什么、几股、寄付指値多少、逆指値放哪），你在 App 里照抄。
成交后用 `run.py pos add/rm` 把真实持仓登记进来，跟踪止损才能接着算。

它永远不会真的下单：buy()/sell() 只返回 PROPOSED 状态的 Order。
"""
from __future__ import annotations

import time

from .. import paths
from ..utils import read_json, setup_logging, write_json
from .base import BaseBroker, Order, Position

log = setup_logging("broker.manual")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class ManualBroker(BaseBroker):
    market = "JP"

    def __init__(self, state_file=None, initial_cash: float = 1_000_000, market: str = "JP"):
        self.market = market
        self.path = state_file or (paths.state_dir() / "manual_positions.json")
        st = read_json(self.path)
        if st is None:
            st = {"cash": float(initial_cash), "positions": {}}
            write_json(self.path, st)
        self.state = st
        self._prices: dict[str, float] = {}

    # ── 人工登记 ──
    def add(self, ticker: str, qty: int, avg_px: float, entry_date: str = "") -> Position:
        d = self.state["positions"].setdefault(
            ticker, {"qty": 0, "avg_px": 0.0, "entry_date": entry_date or _now()[:10]})
        d["avg_px"] = (d["avg_px"] * d["qty"] + avg_px * qty) / (d["qty"] + qty)
        d["qty"] += qty
        self._save()
        log.info("登记买入 %s x%d @%.1f → 持有 %d", ticker, qty, avg_px, d["qty"])
        return Position.from_dict({"ticker": ticker, **d})

    def remove(self, ticker: str, qty: int | None = None) -> None:
        d = self.state["positions"].get(ticker)
        if not d:
            log.warning("%s 不在登记持仓里", ticker)
            return
        if qty is None or qty >= d["qty"]:
            self.state["positions"].pop(ticker)
        else:
            d["qty"] -= qty
        self._save()
        log.info("登记卖出 %s %s", ticker, "全部" if qty is None else f"x{qty}")

    def set_cash(self, cash: float) -> None:
        self.state["cash"] = float(cash)
        self._save()

    def _save(self) -> None:
        write_json(self.path, self.state)

    # ── BaseBroker 接口 ──
    def set_prices(self, prices: dict[str, float]) -> None:
        self._prices.update({k: float(v) for k, v in prices.items() if v and v > 0})

    def get_price(self, ticker: str) -> float:
        if ticker in self._prices:
            return self._prices[ticker]
        d = self.state["positions"].get(ticker)
        if d:
            return float(d["avg_px"])
        raise KeyError(ticker)

    def cash(self) -> float:
        return float(self.state["cash"])

    def positions(self) -> dict[str, Position]:
        return {t: Position.from_dict({"ticker": t, **d})
                for t, d in self.state["positions"].items() if d.get("qty", 0) > 0}

    def buy(self, ticker, qty, limit=None, client_id="", ref_px=None, bar=""):
        return Order(ticker, "BUY", qty, ref_px or self.get_price(ticker), _now(),
                     "PROPOSED", client_id=client_id, note="半自动：请人工下单")

    def sell(self, ticker, qty, limit=None, client_id="", ref_px=None, bar=""):
        return Order(ticker, "SELL", qty, ref_px or self.get_price(ticker), _now(),
                     "PROPOSED", client_id=client_id, note="半自动：请人工下单")

    def fill_pending(self, opens, bar, max_gap_pct=None, prev_bars=None):
        return []
