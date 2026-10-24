"""
broker.py — 券商适配层（ブローカーアダプター / broker adapter）。

  PaperBroker        : 本地模拟成交，用于第3阶段（纸交易 / paper trading）
  RakutenRSSBroker   : 楽天証券 MARKETSPEED II RSS 适配器（第4阶段）
                       楽天没有个人 REST API，官方唯一自动化通道是 Excel RSS 插件，
                       Python 通过 xlwings 操作 Excel：读 RSS 函数取价、调用 VBA 发单。
                       仅 Windows + Excel + MarketSpeed II 登录状态下可用；RSS 不支持美股。

两者接口一致，paper_trader.py 只依赖抽象方法，切换券商只改一行。
"""
from __future__ import annotations
import json
import os
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict

log = logging.getLogger("broker")


@dataclass
class Order:
    ticker: str
    side: str          # "BUY" / "SELL"
    qty: int
    price: float       # 成交/参考价
    ts: str
    status: str = "FILLED"
    note: str = ""


class BaseBroker(ABC):
    @abstractmethod
    def get_price(self, ticker: str) -> float: ...
    @abstractmethod
    def buy(self, ticker: str, qty: int, limit: float | None = None) -> Order: ...
    @abstractmethod
    def sell(self, ticker: str, qty: int, limit: float | None = None) -> Order: ...
    @abstractmethod
    def positions(self) -> dict[str, dict]: ...
    @abstractmethod
    def cash(self) -> float: ...
    def equity(self) -> float:
        return self.cash() + sum(p["qty"] * self.get_price(t) for t, p in self.positions().items())


# ═══════════════════════ 模拟券商 ═══════════════════════
class PaperBroker(BaseBroker):
    """状态持久化到 json，重启不丢仓。价格由外部注入（收盘价或实时价）。"""

    def __init__(self, state_file="paper_state.json", initial_cash=1_000_000,
                 commission_pct=0.055, slippage_pct=0.1):
        self.state_file = state_file
        self.fee = commission_pct / 100
        self.slip = slippage_pct / 100
        self._prices: dict[str, float] = {}
        if os.path.exists(state_file):
            with open(state_file, encoding="utf-8") as f:
                self.state = json.load(f)
        else:
            self.state = {"cash": initial_cash, "positions": {}, "orders": []}
            self._save()

    def _save(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=1)

    def set_prices(self, prices: dict[str, float]):   # 外部喂最新价
        self._prices.update(prices)

    def get_price(self, ticker):
        return self._prices[ticker]

    def cash(self):
        return self.state["cash"]

    def positions(self):
        return self.state["positions"]

    def buy(self, ticker, qty, limit=None):
        px = self.get_price(ticker) * (1 + self.slip)
        cost = px * qty * (1 + self.fee)
        if cost > self.state["cash"]:
            return self._log(Order(ticker, "BUY", qty, px, _now(), "REJECTED", "cash不足"))
        self.state["cash"] -= cost
        pos = self.state["positions"].setdefault(ticker, {"qty": 0, "avg_px": 0.0, "peak": px,
                                                          "entry_date": _now()[:10]})
        pos["avg_px"] = (pos["avg_px"] * pos["qty"] + px * qty) / (pos["qty"] + qty)
        pos["qty"] += qty
        return self._log(Order(ticker, "BUY", qty, px, _now()))

    def sell(self, ticker, qty, limit=None):
        pos = self.state["positions"].get(ticker)
        if not pos or pos["qty"] < qty:
            return self._log(Order(ticker, "SELL", qty, 0, _now(), "REJECTED", "无持仓"))
        px = self.get_price(ticker) * (1 - self.slip)
        self.state["cash"] += px * qty * (1 - self.fee)
        pos["qty"] -= qty
        if pos["qty"] == 0:
            del self.state["positions"][ticker]
        return self._log(Order(ticker, "SELL", qty, px, _now(),
                               note=f"pnl={(px - pos['avg_px']) * qty:.0f}"))

    def _log(self, o: Order):
        self.state["orders"].append(asdict(o))
        self._save()
        log.info("ORDER %s", asdict(o))
        return o


# ═══════════════════════ 楽天 RSS 适配器 ═══════════════════════
class RakutenRSSBroker(BaseBroker):
    """
    前置条件（Windows）：
      1. 安装 MarketSpeed II，登录；安装 MARKETSPEED II RSS Excel 插件并在 Excel 中「接続」
      2. pip install xlwings
      3. 准备工作簿 rss_bridge.xlsm：
         - Sheet "Quote"：A 列填代码(如 7203)，B 列公式 =RssMarket(A2,"現在値")
         - Sheet "Order"：由 VBA 宏 PlaceOrder(code, side, qty, price) 调用 RSS 发注函数
           （函数名/参数以楽天官方「RSS 関数一覧 PDF」当期版本为准，会随年度更新）
      4. RSS 只覆盖国内株，不支持美股
    安全设计：require_arm=True 时，Excel 单元格 Order!ARM 必须由**人**手动填入 "ARMED"
    本类才会真正调用发单宏；Python 无法自己解锁。这是防误单的最后一道闸。
    """

    def __init__(self, workbook="rss_bridge.xlsm", require_arm=True):
        import xlwings as xw                       # 仅 Windows 可用
        self.wb = xw.Book(workbook)
        self.quote = self.wb.sheets["Quote"]
        self.order = self.wb.sheets["Order"]
        self.require_arm = require_arm

    def _code(self, ticker):                       # "7203.T" -> "7203"
        return ticker.split(".")[0]

    def get_price(self, ticker):
        codes = [str(int(c)) for c in self.quote.range("A2:A200").value if c]
        row = codes.index(self._code(ticker)) + 2
        for _ in range(10):                        # DDE 刷新有延迟，最多等 5 秒
            v = self.quote.range(f"B{row}").value
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
            time.sleep(0.5)
        raise RuntimeError(f"RSS 无报价: {ticker}")

    def _armed(self) -> bool:
        return (not self.require_arm) or str(self.order.range("ARM").value).strip() == "ARMED"

    def _place(self, ticker, side, qty, limit):
        if not self._armed():
            log.warning("未 ARM，拒绝发单 %s %s %s", side, ticker, qty)
            return Order(ticker, side, qty, limit or 0, _now(), "BLOCKED", "未ARM")
        macro = self.wb.macro("PlaceOrder")        # VBA: Function PlaceOrder(code, side, qty, price) As String
        result = macro(self._code(ticker), side, qty, limit or 0)
        return Order(ticker, side, qty, limit or self.get_price(ticker), _now(), "SENT", str(result))

    def buy(self, ticker, qty, limit=None):  return self._place(ticker, "BUY", qty, limit)
    def sell(self, ticker, qty, limit=None): return self._place(ticker, "SELL", qty, limit)

    def positions(self):
        # 建议 Sheet "Pos" 用 RSS 保有株関数拉取，这里读取为 {code: {qty, avg_px}}
        rows = self.wb.sheets["Pos"].range("A2:C200").value
        return {f"{int(r[0])}.T": {"qty": int(r[1]), "avg_px": float(r[2])} for r in rows if r and r[0]}

    def cash(self):
        return float(self.wb.sheets["Pos"].range("CASH").value)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")
