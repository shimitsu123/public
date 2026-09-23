"""regime.py — 市场状态（レジーム）过滤：结合"当前市场情况"决定要不要开新仓、开多大。

两层，取更保守的一层：
  ① 量化层（客观）：指数 vs 200 日线、20 日年化波动、距 252 日高点回撤
       risk_on  : 站上 200 日线 且 波动 < 25% 且 回撤 > -8%     → 仓位 ×1.0
       neutral  : 其余                                           → 仓位 ×0.75
       risk_off : 跌破 200 日线 或 回撤 < -12% 或 波动 > 35%     → 不开新仓
  ② 判断层（主观，可选）：读取「市场风险报告」artifact 里的行动四选一
       避险 → 不开新仓；减仓观察 → ×0.5；观望 / 加仓观察 → 不加不减
     由 worker 每天早上写入 var/market_regime.json（见例行任务步骤）。

注意：这一层**不在回测里**。开启后模拟盘的结果会与回测系统性地不同，
这是有意为之——用户明确要求结合当前市场情况。日报里会标明当日采用的倍数与依据。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import paths
from .utils import read_json

ACTION_MULT = {"避险": 0.0, "减仓观察": 0.5, "观望": 1.0, "加仓观察": 1.0}


@dataclass
class Regime:
    market: str
    quant_label: str = "unknown"
    quant_mult: float = 1.0
    above_ma200: bool | None = None
    vol20_pct: float | None = None
    dd252_pct: float | None = None
    overlay_action: str = ""
    overlay_mult: float = 1.0
    overlay_as_of: str = ""
    crash_prob: float | None = None

    @property
    def mult(self) -> float:
        return min(self.quant_mult, self.overlay_mult)

    @property
    def label(self) -> str:
        return f"{self.quant_label}" + (f"｜报告:{self.overlay_action}" if self.overlay_action else "")

    def to_dict(self) -> dict:
        return {**self.__dict__, "mult": self.mult, "label": self.label}


def quant_regime(index_df: pd.DataFrame | None, market: str) -> Regime:
    r = Regime(market=market)
    if index_df is None or len(index_df) < 210:
        return r
    c = index_df["Close"].dropna()
    ma200 = float(c.rolling(200).mean().iloc[-1])
    last = float(c.iloc[-1])
    vol20 = float(c.pct_change().tail(20).std() * np.sqrt(252) * 100)
    hi252 = float(c.tail(252).max())
    dd = (last / hi252 - 1) * 100
    r.above_ma200, r.vol20_pct, r.dd252_pct = last > ma200, round(vol20, 1), round(dd, 1)
    if (not r.above_ma200) or dd < -12 or vol20 > 35:
        r.quant_label, r.quant_mult = "risk_off", 0.0
    elif r.above_ma200 and vol20 < 25 and dd > -8:
        r.quant_label, r.quant_mult = "risk_on", 1.0
    else:
        r.quant_label, r.quant_mult = "neutral", 0.75
    return r


def apply_overlay(r: Regime, max_age_days: int = 2) -> Regime:
    """读取 var/market_regime.json（worker 从「市场风险报告」提取）。过期则忽略。"""
    d = read_json(paths.home() / "market_regime.json", {}) or {}
    m = d.get(r.market) or {}
    as_of = str(d.get("as_of") or m.get("as_of") or "")
    if not m or not as_of:
        return r
    try:
        age = (dt.date.today() - dt.date.fromisoformat(as_of[:10])).days
    except ValueError:
        return r
    if age > max_age_days:
        return r
    action = str(m.get("action") or "").strip()
    if action in ACTION_MULT:
        r.overlay_action, r.overlay_mult, r.overlay_as_of = action, ACTION_MULT[action], as_of
    cp = m.get("crash_prob")
    if cp is not None:
        try:
            r.crash_prob = float(cp)
        except (TypeError, ValueError):
            pass
    return r
