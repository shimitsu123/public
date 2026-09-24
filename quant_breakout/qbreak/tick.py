"""tick.py — 東証の呼値（よびね / tick size）と単元株。

为什么需要：指値（limit order）价格必须落在合法的呼値上，否则券商直接拒单。
原版 README 让你「限价 = 现价 × 1.005」，7203 现价 2,987 → 3,001.9 这种价格
在 3,000 円超的价格带（呼値 5 円）上是非法的，实盘会报错。

注意：
  • 下表为 2024 年以来生效的内容，请对照 JPX「呼値の単位」页面核对。
  • JPX 已公告 2027-03-01 起改为按个股流动性（STR 指标）决定呼値单位，
    届时需要按券商/JPX 提供的对照表更新 TICK_TOPIX100 / TICK_OTHERS。
  • TOPIX100 成分股名单每年换，`TOPIX100_CODES` 只放了少量示例；
    不确定时用 `others` 档（更粗的呼値）总是合法的（价格一定落在合法格点上）。
"""
from __future__ import annotations

import math

# (上限价格, 呼値单位)；价格 <= 上限 时适用
TICK_OTHERS: list[tuple[float, float]] = [
    (3_000, 1), (5_000, 5), (30_000, 10), (50_000, 50), (300_000, 100),
    (500_000, 500), (3_000_000, 1_000), (5_000_000, 5_000),
    (30_000_000, 10_000), (50_000_000, 50_000), (float("inf"), 100_000),
]
TICK_TOPIX100: list[tuple[float, float]] = [
    (1_000, 0.1), (3_000, 0.5), (10_000, 1), (30_000, 5), (100_000, 10),
    (300_000, 50), (1_000_000, 100), (3_000_000, 500), (10_000_000, 1_000),
    (30_000_000, 5_000), (float("inf"), 10_000),
]

# 仅示例，实盘前请按 JPX 最新 TOPIX100 构成名单补全；留空也不会出错（退回粗档）
TOPIX100_CODES: set[str] = set()


def tick_size(price: float, code: str | None = None) -> float:
    table = TICK_TOPIX100 if code and code.split(".")[0] in TOPIX100_CODES else TICK_OTHERS
    for cap, unit in table:
        if price <= cap:
            return float(unit)
    return float(table[-1][1])


def round_to_tick(price: float, code: str | None = None, side: str = "BUY") -> float:
    """把价格对齐到合法呼値。买单向下取整、卖单向上取整（对自己不利的方向），
    保证「不会因为四舍五入而多付/少收」，同时价格一定合法。"""
    if price <= 0:
        raise ValueError(f"价格必须为正: {price}")
    unit = tick_size(price, code)
    n = price / unit
    n = math.floor(n) if side.upper() == "BUY" else math.ceil(n)
    out = n * unit
    # 跨价格带时（如 2,999.6 向上取整到 3,000）单位会变，再校验一次
    if tick_size(out, code) != unit:
        unit2 = tick_size(out, code)
        n2 = math.floor(out / unit2) if side.upper() == "BUY" else math.ceil(out / unit2)
        out = n2 * unit2
    return round(out, 4)


# 単元株数（売買単位）：東証内国株原则 100 株；ETF/REIT 常见 1 或 10。
DEFAULT_LOT_JP = 100
DEFAULT_LOT_US = 1
LOT_OVERRIDE: dict[str, int] = {
    # "1306.T": 10,   # 例：TOPIX 連動型上場投信
    # "1570.T": 1,
}


def lot_size(ticker: str, market: str) -> int:
    if ticker in LOT_OVERRIDE:
        return LOT_OVERRIDE[ticker]
    return DEFAULT_LOT_JP if market.upper() == "JP" else DEFAULT_LOT_US


# ══════════════════════════ 値幅制限（ストップ高 / ストップ安）══════════════════════════
# JPX「制限値幅」表：基準値段（前日終値）→ 上下の制限値幅（円）。上段から「未満」で判定。
_JP_LIMITS = [
    (100, 30), (200, 50), (500, 80), (700, 100), (1_000, 150), (1_500, 300), (2_000, 400),
    (3_000, 500), (5_000, 700), (7_000, 1_000), (10_000, 1_500), (15_000, 3_000), (20_000, 4_000),
    (30_000, 5_000), (50_000, 7_000), (70_000, 10_000), (100_000, 15_000), (150_000, 30_000),
    (200_000, 40_000), (300_000, 50_000), (500_000, 70_000), (700_000, 100_000), (1_000_000, 150_000),
    (1_500_000, 300_000), (2_000_000, 400_000), (3_000_000, 500_000), (5_000_000, 700_000),
    (7_000_000, 1_000_000), (10_000_000, 1_500_000), (15_000_000, 3_000_000), (20_000_000, 4_000_000),
    (30_000_000, 5_000_000), (50_000_000, 7_000_000),
]


def price_limit_jp(base: float) -> float:
    """前日終値 base に対する制限値幅（円）。"""
    for upper, width in _JP_LIMITS:
        if base < upper:
            return float(width)
    return 10_000_000.0


def limit_lock(prev_close: float, high: float, low: float, close: float, market: str) -> str | None:
    """その日一日中ストップ高 / ストップ安に張り付いていたか（寄付で約定できない日）。
    日足だけでは板は見えないので「値幅がほぼゼロ」かつ「前日比が制限値幅の 8 割以上」で判定。
    日本株以外は None（米国株に値幅制限はない。サーキットブレーカーは別物）。"""
    if market.upper() != "JP" or not prev_close or prev_close <= 0 or not all(
            x == x and x > 0 for x in (high, low, close)):
        return None
    if (high - low) > prev_close * 0.005:
        return None
    w = price_limit_jp(prev_close)
    if close <= prev_close - 0.8 * w:
        return "down"
    if close >= prev_close + 0.8 * w:
        return "up"
    return None
