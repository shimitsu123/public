"""core.py — 核心指数仓位（コア・サテライト）：闲置资金在牛市持有指数 ETF，熊市持现金。

  日本：1329.T（iShares Core 日経225 ETF，1 口约 6,800 円，ゼロコース手续费 0）
  美股：VOO（乐天「买付手数料無料」ETF，卖出 0.495% 上限 $22）或 SPYM（单价 <$100，买卖都 0.495%）
回测用 ETF 的复权价；ETF 上市前（1329 为 2009-01 前）用指数日收益 + 估计股息率拼接。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CORE_ETF = {"JP": "1329.T", "US": "VOO"}
CORE_COST = {  # 回测 / 模拟盘的成交成本（乐天，2026-09-24 官方页面核对）
    "JP": {"buy_fee_pct": 0.0, "sell_fee_pct": 0.0, "slip_pct": 0.03, "lot": 1},
    "US": {"buy_fee_pct": 0.0, "sell_fee_pct": 0.495, "sell_fee_max": 22.0, "slip_pct": 0.01, "lot": 1},
}
SPYM_COST = {"buy_fee_pct": 0.495, "buy_fee_max": 22.0, "sell_fee_pct": 0.495, "sell_fee_max": 22.0, "slip_pct": 0.02, "lot": 1}
COST_BY_TICKER = {"1329.T": CORE_COST["JP"], "VOO": CORE_COST["US"], "SPYM": SPYM_COST}


def core_cost(ticker: str, market: str) -> dict:
    """核心 ETF 的成交成本：登记过的按代码取（VOO 买入免费 / SPYM 买卖都收费），否则按市场默认。"""
    return dict(COST_BY_TICKER.get(ticker) or CORE_COST[market.upper()])


# 资金配置三档（scripts/allocation_study.py，2026-09-24，引擎「收盘规划」版；同一选择规则在不同回撤上限下的结果）
# 20 年 = 2006-10～2026-09，5 年 = 2021-09～；个股部分有幸存者偏差（偏乐观），指数部分没有
TIERS = {
    "safe": {"label": "安全（事先登记的约束：20 年回撤 ≥−30%、5 年 ≥−20%）",
             "JP": {"position_pct": 0.34, "max_positions": 3, "breakout": True, "core": {"enabled": False},
                    "halt_dd_pct": 30.0, "bt": "突破 3×34%：20 年 2.83%/年 回撤 −18.3%；5 年 4.02% / −9.0%"},
             "US": {"position_pct": 0.20, "max_positions": 5, "breakout": True, "core": {"enabled": False},
                    "halt_dd_pct": 30.0, "bt": "突破 5×20%：20 年 1.62%/年 回撤 −18.0%；5 年 2.67% / −11.5%"}},
    "aggressive": {"label": "进取（20 年回撤 ≥−35%、5 年 ≥−30%；Calmar 两市场最高，日本与 3×34% 并列）",
                   "JP": {"position_pct": 0.25, "max_positions": 4, "breakout": True,
                          "core": {"enabled": True, "ticker": "1329.T", "timing": True, "band_pct": 10.0},
                          "halt_dd_pct": 45.0,
                          "bt": "突破 4×25% + 闲置资金 1329（熊市清空）：20 年 8.77%/年 回撤 −32.5%；5 年 17.4% / −25.7%"},
                   "US": {"position_pct": 0.20, "max_positions": 5, "breakout": False,
                          "core": {"enabled": True, "ticker": "SPYM", "timing": True, "band_pct": 10.0},
                          "halt_dd_pct": 45.0,
                          "bt": "只持 SPYM + 牛熊择时（不做个股）：20 年 8.30%/年 回撤 −33.4%；5 年 10.6% / −18.7%"}},
    "max": {"label": "最大收益（不设回撤上限；历史回撤约 −55%～−61%）",
            "JP": {"position_pct": 0.34, "max_positions": 3, "breakout": True,
                   "core": {"enabled": True, "ticker": "1329.T", "timing": False, "band_pct": 10.0},
                   "halt_dd_pct": 70.0,
                   "bt": "突破 3×34% + 闲置资金一直持 1329：20 年 11.58%/年 回撤 −61.2%；5 年 21.9% / −25.0%"},
            "US": {"position_pct": 0.20, "max_positions": 5, "breakout": False,
                   "core": {"enabled": True, "ticker": "SPYM", "timing": False, "band_pct": 10.0},
                   "halt_dd_pct": 70.0,
                   "bt": "只持 SPYM（买入持有）：20 年 11.27%/年 回撤 −54.5%；5 年 13.1% / −24.3%"}},
}


def core_frame(etf: pd.DataFrame, index_df: pd.DataFrame | None = None, div_yield_pct: float = 0.0) -> pd.DataFrame:
    """引擎可用的核心仓位 K 线（entry/dead_cross 全 False）。etf 之前的日子用 index 日收益 + 股息率/252 拼接。"""
    e = etf[["Open", "High", "Low", "Close", "Volume"]].copy()
    if index_df is not None and len(index_df) and index_df.index[0] < e.index[0]:
        first = e.index[0]
        ix = index_df[index_df.index <= first][["Open", "High", "Low", "Close"]].astype(float)
        if len(ix) > 1 and ix.index[-1] == first:
            r = ix["Close"].pct_change().fillna(0) + div_yield_pct / 100 / 252
            tr = pd.Series(np.cumprod(1 + r.values), index=ix.index)      # 含估计股息的总收益指数
            c = tr / tr.iloc[-1] * float(e["Close"].iloc[0])             # 在 ETF 首日与其收盘价对齐
            ratio = (c / ix["Close"]).iloc[:-1]
            pre = ix.iloc[:-1]
            syn = pd.DataFrame({"Open": pre["Open"] * ratio, "High": pre["High"] * ratio, "Low": pre["Low"] * ratio,
                                "Close": c.iloc[:-1], "Volume": 1e9}, index=pre.index)
            e = pd.concat([syn, e])
    e["entry"] = False
    e["dead_cross"] = False
    e["climax"] = False
    e["atr"] = np.nan
    e.index.name = "Date"
    return e


def core_orders(equity: float, stock_value: float, reserve: float, cash_est: float, units: int,
                price: float, bear: bool, *, buffer_pct: float = 0.0, band_pct: float = 10.0,
                lot: int = 1, sell_net=None, margin_pct: float = 3.0) -> tuple[int, int]:
    """收盘时决定核心 ETF 次日开盘的 (卖出份额, 买入份额)。回测引擎与实盘 run_once 共用这一个函数。
    equity      含核心仓位的总权益（收盘价计）
    stock_value 次日开盘后仍持有的个股市值（不含已排队卖出的）
    reserve     计划买入个股的预计成本（收盘价 ×(1+滑点) + 手续费）
    cash_est    现金 + 已排队卖出个股的预计净额（尚未扣除 reserve）
    units/price 现有核心份额 / 核心 ETF 收盘价
    规则：目标 = floor((权益×(1−buffer%) − 个股 − reserve) / 价)，熊市目标 = 0；
      偏离超过 band% × 权益才调整（清仓不受 band 限制，避免小额来回付手续费）；
      计划买入的现金缺口 (reserve − cash_est) 由卖出核心补足，并按 margin_pct 预留开盘跳空余量
      （个股只在开盘 ≤ 信号日收盘 ×(1+跳空上限) 时成交，所以缺口最多放大这么多）。
    sell_net(u)：卖出 u 份的预计净额（扣滑点、手续费）；None = u × price。"""
    if price <= 0 or not np.isfinite(price):
        return 0, 0
    tgt_val = equity * (1 - buffer_pct / 100) - stock_value - reserve
    tgt = 0 if bear else int(np.floor(max(0.0, tgt_val) / price / lot)) * lot
    band = band_pct / 100 * equity
    sell = buy = 0
    if tgt < units and (tgt == 0 or (units - tgt) * price > band):
        sell = units - tgt
    elif tgt > units and (tgt - units) * price > band:
        buy = tgt - units
    short = reserve - cash_est
    if short > 0 and units > 0:
        need = short * (1 + margin_pct / 100)
        net = sell_net or (lambda u: u * price)
        u = min(units, int(np.ceil(need / price / lot)) * lot)
        while u < units and net(u) < need:
            u += lot
        sell, buy = max(sell, u), 0
    return int(sell), int(buy)
