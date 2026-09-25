"""fees.py — 手续费的唯一实现：回测引擎、模拟盘、实盘规划、核心 ETF 仓位共用同一套计算。

FeeSchedule：按一笔约定金额收费
  tiers : ((约定金额上限, 手续费), ...)，按上限升序；约定金额 ≤ 某档上限 → 收该档的定额手续费
  超过最后一档（或没有 tiers）→ 按比例 pct%，再套 min / max（0 = 不设）
核心 ETF 的成本字典用 buy_ / sell_ 前缀：buy_fee_pct / buy_fee_min / buy_fee_max / buy_fee_tiers（卖出同理）。
"""
from __future__ import annotations

import math
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


# ══════════════════════════ 券商费用表 ══════════════════════════
# 回测 / 模拟盘 / 实盘规划都按 sim.json 市场段的 "broker" 取这里（没写就用 DEFAULT_BROKER）。
# markets：个股（ExecConfig 的 commission_* / fx_spread_pct）；etf：核心指数 ETF 的成本字典（见上方 side_fee 的键）。
BROKERS: dict[str, dict] = {
    "rakuten": {
        "label": "楽天証券",
        "checked": "2026-09-24",
        "note": "国内株ゼロコース（需同意 SOR・R クロス）；米国株 0.495%（上限 22 美元）；换汇 25 銭/USD（157 円时 ≈0.16%）；"
                "VOO 为买付手数料無料 ETF（卖出照收）",
        "markets": {"JP": {"commission_pct": 0.0},
                    "US": {"commission_pct": 0.495, "commission_max": 22.0, "fx_spread_pct": 0.16}},
        "etf": {"1329.T": {"buy_fee_pct": 0.0, "sell_fee_pct": 0.0, "slip_pct": 0.03, "lot": 1},
                "VOO": {"buy_fee_pct": 0.0, "sell_fee_pct": 0.495, "sell_fee_max": 22.0, "slip_pct": 0.01, "lot": 1},
                "SPYM": {"buy_fee_pct": 0.495, "buy_fee_max": 22.0, "sell_fee_pct": 0.495, "sell_fee_max": 22.0,
                         "slip_pct": 0.02, "lot": 1}},
    },
}
# 立花証券ｅ支店 国内株式 現物（税込、報告書等電子交付）：https://www.e-shiten.jp/TorihikiRule/cost/（2026-09-25 核对）
# ETF / REIT「株式と同様にお取扱い」。ｅ支店不做美股（米国株は対面口座のみ），所以没有 US 市场、没有换汇。
TACHIBANA_KOBETSU = ((100_000, 77.0), (200_000, 99.0), (500_000, 187.0), (1_000_000, 341.0), (1_500_000, 407.0),
                     (3_000_000, 473.0), (6_000_000, 814.0), (10_000_000, 869.0), (float("inf"), 1100.0))
TACHIBANA_TEIGAKU = ((120_000, 0.0), (200_000, 176.0), (500_000, 253.0), (1_000_000, 506.0), (2_000_000, 759.0),
                     (3_000_000, 1012.0))                      # 1 日约定合计；300 万以上每 100 万 +253 円


def tachibana_teigaku(day_total: float) -> float:
    """立花 定額コース：按 1 日约定代金合计收费（300 万円以上每增 100 万円 +253 円，1,000 万円 = 2,783 円）。"""
    x = abs(float(day_total))
    if x <= 0:
        return 0.0
    for cap, fee in TACHIBANA_TEIGAKU:
        if x <= cap:
            return fee
    return 1012.0 + 253.0 * math.ceil((x - 3_000_000) / 1_000_000)


BROKERS["tachibana"] = {
    "label": "立花証券ｅ支店",
    "checked": "2026-09-25",
    "note": "個別コース（1 注文ごと）；ETF 与股票同表；新开户前 60 营业日现物手续费 0 円（未计入）；"
            "定額コース见 tachibana_teigaku()；不做美股、无换汇",
    "markets": {"JP": {"commission_tiers": TACHIBANA_KOBETSU}},
    "etf": {t: {"buy_fee_tiers": TACHIBANA_KOBETSU, "sell_fee_tiers": TACHIBANA_KOBETSU, "slip_pct": sl, "lot": lot}
            for t, sl, lot in (("1329.T", 0.03, 1), ("1655.T", 0.02, 10), ("2558.T", 0.03, 1))},
}
DEFAULT_BROKER = {"JP": "tachibana", "US": "rakuten"}   # 日本 = 立花（2026-09-25 起，Mac 上可 API 全自动）；美股个股只有楽天能做
_SLIP = {"JP": 0.10, "US": 0.05}                     # 个股单边滑点 %（与券商无关）
_ETF_SLIP = {"JP": 0.03, "US": 0.02}                 # 没登记的 ETF：滑点按市场默认


def broker_of(market: str, mc: dict | None = None) -> str:
    """市场段写了 broker 就用它，否则用默认。"""
    b = (mc or {}).get("broker") or DEFAULT_BROKER[market.upper()]
    if b not in BROKERS:
        raise KeyError(f"未知券商 {b}，可选 {sorted(BROKERS)}")
    return b


def market_fees(broker: str, market: str) -> dict:
    """个股的 ExecConfig 参数（手续费 / 换汇 / 滑点）。券商不做该市场时报错，不静默套用别家的费率。"""
    m = market.upper()
    f = BROKERS[broker]["markets"].get(m)
    if f is None:
        raise KeyError(f"{BROKERS[broker]['label']} 不做 {m} 市场的个股")
    return {"slippage_pct": _SLIP[m], **f}


def etf_cost(broker: str, ticker: str, market: str) -> dict:
    """核心 ETF 的成本字典：登记过的按代码取，否则按该券商该市场的个股费率 + 市场默认滑点。"""
    b = BROKERS[broker]
    if ticker in b["etf"]:
        return dict(b["etf"][ticker])
    f = market_fees(broker, market)
    out = {"slip_pct": _ETF_SLIP[market.upper()], "lot": 1}
    for s in ("buy", "sell"):
        out.update({f"{s}_fee_pct": f.get("commission_pct", 0.0), f"{s}_fee_min": f.get("commission_min", 0.0),
                    f"{s}_fee_max": f.get("commission_max", 0.0), f"{s}_fee_tiers": f.get("commission_tiers", ())})
    return out
