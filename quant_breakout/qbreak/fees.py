"""fees.py — 手续费的唯一实现：回测引擎、模拟盘、实盘规划、核心 ETF 仓位共用同一套计算。

FeeSchedule：按一笔约定金额收费
  tiers : ((约定金额上限, 手续费), ...)，按上限升序；约定金额 ≤ 某档上限 → 收该档的定额手续费
  超过最后一档（或没有 tiers）→ 按比例 pct%，再套 min / max（0 = 不设）
核心 ETF 的成本字典用 buy_ / sell_ 前缀：buy_fee_pct / buy_fee_min / buy_fee_max / buy_fee_tiers（卖出同理）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class FeeSchedule:
    pct: float = 0.0
    min: float = 0.0
    max: float = 0.0
    tiers: tuple = ()

    def __call__(self, notional: float) -> float:
        x = abs(float(notional))
        if x <= 0:
            return 0.0
        for cap, fee in self.tiers:
            if x <= cap:
                return float(fee)
        f = x * self.pct / 100
        if self.min:
            f = max(f, self.min)
        if self.max:
            f = min(f, self.max)
        return f


def side_fee(cost: dict | None, side: str) -> Callable[[float], float]:
    """成本字典 → 该方向（BUY / SELL）的手续费函数。"""
    c, s = cost or {}, ("buy" if side == "BUY" else "sell")
    return FeeSchedule(pct=float(c.get(f"{s}_fee_pct", 0.0) or 0.0),
                       min=float(c.get(f"{s}_fee_min", 0.0) or 0.0),
                       max=float(c.get(f"{s}_fee_max", 0.0) or 0.0),
                       tiers=tuple((float(a), float(b)) for a, b in (c.get(f"{s}_fee_tiers") or ())))
