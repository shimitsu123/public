"""paper.py — 模拟券商（ペーパートレード）。状态原子写入 JSON，进程被杀也不会写坏。"""
from __future__ import annotations

import time

from .. import paths
from ..config import ExecConfig
from ..utils import read_json, setup_logging, write_json
from .base import BaseBroker, Order, Position

log = setup_logging("broker.paper")

# 模拟盘的成交假设是「次日寄付（开盘）」，所以约定时刻就是各市场的开盘时间
OPEN_TIME = {"JP": "09:00 JST", "US": "09:30 ET"}


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class PaperBroker(BaseBroker):
    def __init__(self, state_file=None, initial_cash: float = 1_000_000,
                 exec_cfg: ExecConfig | None = None, market: str = "JP",
                 defer_to_next_open: bool = True):
        # defer_to_next_open：收盘后下的单在**次日开盘**成交，与回测引擎一致。
        # 原版模拟盘直接按当日收盘价成交，于是模拟盘和回测天生对不上，
        # 第3阶段"对照回测验证"这一步就失去了意义。
        self.defer = defer_to_next_open
        self.market = market
        self.ex = (exec_cfg or ExecConfig.for_market(market)).validate()
        self.path = state_file or (paths.state_dir() / f"paper_state_{market}.json")
        st = read_json(self.path)
        if st is None:
            st = {"cash": float(initial_cash), "positions": {}, "orders": [],
                  "closed_trades": [], "realized_pnl": 0.0, "pending": []}
            write_json(self.path, st)
        st.setdefault("pending", [])
        self.state = st
        self._prices: dict[str, float] = {}
        self._ids = {o.get("client_id") for o in self.state["orders"] if o.get("client_id")}

    # ── 价格由外部注入（收盘价或实时价）──
    def set_prices(self, prices: dict[str, float]) -> None:
        self._prices.update({k: float(v) for k, v in prices.items() if v and v > 0})

    def get_price(self, ticker: str) -> float:
        px = self._prices.get(ticker)
        if px is None:
            p = self.positions().get(ticker)
            if p is not None and p.avg_px:
                return p.avg_px          # 退回成本价，equity() 不会因为一只票取不到价就崩
            raise KeyError(f"没有 {ticker} 的价格")
        return px

    def cash(self) -> float:
        return float(self.state["cash"])

    def positions(self) -> dict[str, Position]:
        return {t: Position.from_dict({"ticker": t, **d})
                for t, d in self.state["positions"].items()}

    def has_client_id(self, client_id: str) -> bool:
        return bool(client_id) and client_id in self._ids

    def update_position(self, pos: Position) -> None:
        if pos.ticker in self.state["positions"]:
            d = pos.to_dict()
            d.pop("ticker")
            self.state["positions"][pos.ticker].update(d)
            self._save()

    def _save(self) -> None:
        write_json(self.path, self.state)

    def _log(self, o: Order) -> Order:
        self.state["orders"].append(o.to_dict())
        if o.client_id:
            self._ids.add(o.client_id)
        self._save()
        log.info("ORDER %s %s x%d @%.2f [%s] %s", o.side, o.ticker, o.qty,
                 o.filled_px or o.price, o.status, o.note)
        return o

    # ── 次日开盘成交队列 ──
    def queue(self, ticker: str, side: str, qty: int, ref_px: float, bar: str,
              client_id: str) -> Order:
        self.state["pending"].append({"ticker": ticker, "side": side, "qty": int(qty),
                                      "ref_px": float(ref_px), "bar": bar,
                                      "client_id": client_id})
        self._ids.add(client_id)
        self._save()
        return Order(ticker, side, qty, ref_px, _now(), "SENT", client_id=client_id,
                     note="已排队，次日开盘成交")

    def fill_pending(self, opens: dict[str, float], bar: str,
                     max_gap_pct: float | None = None) -> list[Order]:
        """用当日开盘价撮合昨日排队的订单；当日没排上的（停牌/跳空过大）作废，
        与回测引擎"信号只在 T+1 有效"的规则一致。"""
        out, keep = [], []
        gap = self.ex.max_entry_gap_pct if max_gap_pct is None else max_gap_pct
        for o in self.state["pending"]:
            if o["bar"] == bar:                      # 今天刚排的，留到明天
                keep.append(o)
                continue
            px = opens.get(o["ticker"])
            if px is None or px <= 0:
                out.append(Order(o["ticker"], o["side"], o["qty"], 0, _now(), "REJECTED",
                                 client_id=o["client_id"], note="次日无开盘价（停牌），作废"))
                continue
            if (o["side"] == "BUY" and gap and o["ref_px"]
                    and px > o["ref_px"] * (1 + gap / 100)):
                out.append(Order(o["ticker"], o["side"], o["qty"], px, _now(), "REJECTED",
                                 client_id=o["client_id"],
                                 note=f"开盘跳空 {px / o['ref_px'] - 1:+.1%} 超过 {gap}%，放弃"))
                continue
            self._prices[o["ticker"]] = px
            f = self._fill_now(o["ticker"], o["side"], o["qty"], o["client_id"] + "-f")
            f.extra.update({"fill_date": bar, "fill_time": OPEN_TIME.get(self.market, "09:00"),
                            "queued_bar": o["bar"], "ref_px": o["ref_px"]})
            if self.state["orders"] and self.state["orders"][-1].get("client_id") == f.client_id:
                self.state["orders"][-1]["extra"] = f.extra       # 落盘也带上
                self._save()
            out.append(f)
        self.state["pending"] = keep
        self._save()
        return out

    def pending(self) -> list[dict]:
        return list(self.state["pending"])

    def _fill_now(self, ticker: str, side: str, qty: int, client_id: str) -> Order:
        return (self._buy_now(ticker, qty, client_id) if side == "BUY"
                else self._sell_now(ticker, qty, client_id))

    def buy(self, ticker: str, qty: int, limit: float | None = None,
            client_id: str = "", ref_px: float | None = None, bar: str = "") -> Order:
        if self.defer and bar:
            if self.has_client_id(client_id):
                return Order(ticker, "BUY", qty, limit or 0, _now(), "REJECTED",
                             client_id=client_id, note="重复的 client_id（幂等拦截）")
            return self.queue(ticker, "BUY", qty, ref_px or self.get_price(ticker),
                              bar, client_id)
        return self._buy_now(ticker, qty, client_id, limit)

    def sell(self, ticker: str, qty: int, limit: float | None = None,
             client_id: str = "", ref_px: float | None = None, bar: str = "") -> Order:
        if self.defer and bar:
            if self.has_client_id(client_id):
                return Order(ticker, "SELL", qty, limit or 0, _now(), "REJECTED",
                             client_id=client_id, note="重复的 client_id（幂等拦截）")
            return self.queue(ticker, "SELL", qty, ref_px or self.get_price(ticker),
                              bar, client_id)
        return self._sell_now(ticker, qty, client_id, limit)

    def _buy_now(self, ticker: str, qty: int, client_id: str = "",
                 limit: float | None = None) -> Order:
        if self.has_client_id(client_id):
            return Order(ticker, "BUY", qty, limit or 0, _now(), "REJECTED",
                         client_id=client_id, note="重复的 client_id（幂等拦截）")
        if qty <= 0:
            return self._log(Order(ticker, "BUY", qty, 0, _now(), "REJECTED",
                                   client_id=client_id, note="数量为 0"))
        px = self.get_price(ticker) * (1 + self.ex.slippage_pct / 100)
        cost = px * qty + self.ex.fee(px * qty)
        if cost > self.cash():
            return self._log(Order(ticker, "BUY", qty, px, _now(), "REJECTED",
                                   client_id=client_id,
                                   note=f"资金不足 需要{cost:,.0f} 现有{self.cash():,.0f}"))
        self.state["cash"] -= cost
        d = self.state["positions"].setdefault(
            ticker, {"qty": 0, "avg_px": 0.0, "peak": px, "stop_px": 0.0,
                     "entry_date": _now()[:10], "hold_bars": 0, "last_bar": ""})
        d["avg_px"] = (d["avg_px"] * d["qty"] + px * qty) / (d["qty"] + qty)
        d["qty"] += qty
        d["peak"] = max(d.get("peak", 0.0), px)
        return self._log(Order(ticker, "BUY", qty, px, _now(), "FILLED",
                               filled_qty=qty, filled_px=px, client_id=client_id))

    def _sell_now(self, ticker: str, qty: int, client_id: str = "",
                  limit: float | None = None) -> Order:
        if self.has_client_id(client_id):
            return Order(ticker, "SELL", qty, limit or 0, _now(), "REJECTED",
                         client_id=client_id, note="重复的 client_id（幂等拦截）")
        d = self.state["positions"].get(ticker)
        if not d or d["qty"] < qty or qty <= 0:
            return self._log(Order(ticker, "SELL", qty, 0, _now(), "REJECTED",
                                   client_id=client_id, note="持仓不足"))
        px = self.get_price(ticker) * (1 - self.ex.slippage_pct / 100)
        proceeds = px * qty - self.ex.fee(px * qty)
        self.state["cash"] += proceeds
        avg, entry_date = d["avg_px"], d.get("entry_date", "")
        pnl = (px - avg) * qty - self.ex.fee(px * qty) - self.ex.fee(avg * qty)
        d["qty"] -= qty
        if d["qty"] == 0:
            self.state["positions"].pop(ticker)
        self.state["realized_pnl"] = float(self.state.get("realized_pnl", 0.0)) + pnl
        self.state["closed_trades"].append(
            {"ticker": ticker, "entry_date": entry_date, "exit_date": _now()[:10],
             "entry_px": round(avg, 4), "exit_px": round(px, 4), "shares": qty,
             "pnl": round(pnl, 2), "ret_pct": round((px / avg - 1) * 100, 3) if avg else 0.0})
        return self._log(Order(ticker, "SELL", qty, px, _now(), "FILLED", filled_qty=qty,
                               filled_px=px, client_id=client_id, note=f"pnl={pnl:,.0f}",
                               extra={"pnl": round(pnl, 2)}))
