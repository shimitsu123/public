"""base.py — 券商适配层抽象（ブローカーアダプター / broker adapter）。

paper_trader 只依赖这里的接口，换券商不用改交易逻辑。
与原版相比新增：
  • Position 是显式结构，peak / stop_px / entry_date 都会被持久化
    （原版把 peak 存在 broker 状态字典里却从不落盘，跟踪止损的"最高价"每天都被重置）
  • sync()：实盘必须能从券商侧回读真实持仓，而不是相信本地记账
  • 每个 Order 都有 client_id，用于幂等（同一根 K 线重复运行不会重复下单）
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any


class BrokerError(RuntimeError):
    pass


@dataclass
class Position:
    ticker: str
    qty: int = 0
    avg_px: float = 0.0
    peak: float = 0.0          # 入场后的最高价，用于跟踪止损；**必须持久化**
    stop_px: float = 0.0       # 入场时确定的止损价（ATR 模式下每只不同）
    entry_date: str = ""
    hold_bars: int = 0         # 已持有的交易日数（按实际处理过的 K 线累加）
    last_bar: str = ""         # 最近一次被处理的 K 线日期，用于幂等

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Position":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Order:
    ticker: str
    side: str                  # BUY / SELL
    qty: int
    price: float               # 限价或参考价
    ts: str
    status: str = "FILLED"     # FILLED / SENT / REJECTED / BLOCKED / PARTIAL / ERROR
    filled_qty: int = 0
    filled_px: float = 0.0
    client_id: str = ""
    broker_id: str = ""
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in ("FILLED", "SENT", "PARTIAL")

    def to_dict(self) -> dict:
        return asdict(self)


def state_tag(broker) -> str:
    """本地状态文件的后缀：模拟盘（PaperBroker）沿用原文件名，其他券商各记各的（_manual / _tachibana / _rakutenrss），
    同一个数据目录里模拟盘与实盘的持仓簿、幂等记录、流水、风控基准、自动 HALT 互不干扰。"""
    kind = type(broker).__name__.lower().replace("broker", "") if broker is not None else "paper"
    return "" if kind in ("paper", "") else f"_{kind}"


class BaseBroker(ABC):
    market: str = "JP"

    @abstractmethod
    def get_price(self, ticker: str) -> float: ...
    @abstractmethod
    def buy(self, ticker: str, qty: int, limit: float | None = None,
            client_id: str = "", ref_px: float | None = None, bar: str = "") -> Order:
        """bar 非空 = 收盘后下单、次日开盘成交（寄付 / opening order）。
        ref_px = 信号日收盘价，用于次日开盘跳空过大时放弃。"""
    @abstractmethod
    def sell(self, ticker: str, qty: int, limit: float | None = None,
             client_id: str = "", ref_px: float | None = None, bar: str = "") -> Order: ...
    @abstractmethod
    def positions(self) -> dict[str, Position]: ...
    @abstractmethod
    def cash(self) -> float: ...

    def sync(self) -> None:
        """从券商侧回读真实持仓/余力。模拟盘是空操作。"""

    def update_position(self, pos: Position) -> None:
        """把 peak / hold_bars 等本地跟踪字段写回并落盘。"""

    def equity(self) -> float:
        total = self.cash()
        for t, p in self.positions().items():
            try:
                px = self.get_price(t)
            except Exception:              # noqa: BLE001  取不到价就用成本价，绝不让权益计算崩掉
                px = p.avg_px
            total += p.qty * px
        return total

    def has_client_id(self, client_id: str) -> bool:
        """幂等检查：该 client_id 是否已经下过单。"""
        return False
