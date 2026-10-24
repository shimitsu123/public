"""scan.py — 候补队列：把整个股票池按「距离入场条件还有多远」排序。

这不是收益预测，是**条件就绪度**排序：四个入场条件（横盘 / 金叉 / 0 轴附近 / 放量）
各自量化成 0~1 的接近度，再叠加可负担性（1 単元买不买得起）与流动性。
排在前面的 = 最可能在接下来几天触发信号的票，也就是"以后要交易的顺序"的最佳估计。

状态：
  triggered  今天已触发（次日寄付买入）
  imminent   横盘 + 0 轴附近成立，MACD 距离金叉 < 0.15%，量比 ≥ 1.0
  watch      横盘 + 0 轴附近成立
  far        其余

「真突破」标签（只作展示，不改交易）：信号当天收盘 > 过去 range_n 日最高价（不含当天；compute_indicators 的 breakout 列）。
2026-09-26 事先登记的研究（var/out/signal_study.md）：真突破的信号胜率更高，但每笔期望的差异不显著、只买真突破组合更差。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import StrategyParams
from .tick import lot_size

# 用户偏好（美股）：单价 <100 美元、20 日均成交额 ≥ 1000 万美元、20 日均量 ≥ 50 万股、
# 60 日年化波动 ≤ 80%、20 日内单日最大跌幅 ≤ 25%、60 日最大回撤 ≤ 50%
US_PREF = dict(max_price=100.0, min_turnover=1e7, min_volume=5e5,
               max_vol60=80.0, max_drop20=25.0, max_dd60=50.0)


def _pref_flags(df: pd.DataFrame, market: str) -> tuple[bool, str]:
    if market != "US" or len(df) < 70:
        return True, ""
    c, v = df["Close"], df["Volume"]
    px = float(c.iloc[-1])
    turnover = float((c * v).tail(20).mean())
    volume = float(v.tail(20).mean())
    r = c.pct_change().tail(60)
    vol60 = float(r.std() * np.sqrt(252) * 100)
    drop20 = float(-c.pct_change().tail(20).min() * 100)
    w = c.tail(60)
    dd60 = float(-(w / w.cummax() - 1).min() * 100)
    bad = []
    if px >= US_PREF["max_price"]:
        bad.append(f"单价{px:.0f}≥100")
    if turnover < US_PREF["min_turnover"]:
        bad.append("成交额<1000万")
    if volume < US_PREF["min_volume"]:
        bad.append("成交量<50万")
    if vol60 > US_PREF["max_vol60"]:
        bad.append(f"波动{vol60:.0f}%")
    if drop20 > US_PREF["max_drop20"]:
        bad.append(f"单日跌{drop20:.0f}%")
    if dd60 > US_PREF["max_dd60"]:
        bad.append(f"回撤{dd60:.0f}%")
    return (not bad), "；".join(bad)


def breakout_fields(r: pd.Series) -> dict:
    """一行指标 → 「真突破」标签用的两个字段（只作展示）：
    breakout = 收盘 > 过去 range_n 日最高价（不含当天）；to_box_top_pct = 距箱顶 %（正 = 还差多少，负 = 已在箱顶之上）。"""
    close = float(r["Close"])
    box_top = float(r["box_top"]) if pd.notna(r["box_top"]) else np.nan
    to_top = (box_top / close - 1) * 100 if np.isfinite(box_top) and np.isfinite(close) and close > 0 else np.nan
    return {"breakout": bool(r["breakout"]) if pd.notna(r["breakout"]) else False,
            "to_box_top_pct": round(to_top, 1) if np.isfinite(to_top) else None}


def tag_breakouts(todo: dict, ind: dict[str, pd.DataFrame]) -> dict:
    """「今天要做的事」的个股买单加上「真突破」字段（按信号日那一行）；卖单、核心 ETF、换汇不动。就地修改并返回。"""
    for m in ("JP", "US"):
        for o in todo.get(m) or []:
            df = ind.get(o.get("ticker"))
            d = o.get("signal_date")
            if o.get("side") != "BUY" or not d or df is None or "breakout" not in df.columns:
                continue
            ts = pd.Timestamp(d)
            if ts in df.index:
                o.update(breakout_fields(df.loc[ts]))
    return todo


def scan(ind: dict[str, pd.DataFrame], p: StrategyParams, market: str,
         budget: float, top: int = 15) -> pd.DataFrame:
    """ind: {ticker: compute_indicators 结果}。budget: 单笔预算（用于可负担性）。"""
    rows = []
    for t, df in ind.items():
        if len(df) < p.warmup_bars + 2:
            continue
        r, r1 = df.iloc[-1], df.iloc[-2]
        close = float(r["Close"])
        if not np.isfinite(close) or close <= 0:
            continue
        range_pct = float(r["range_pct"]) if np.isfinite(r["range_pct"]) else np.nan
        is_range = bool(r["is_range"])
        near_zero = bool(r["near_zero"])
        gap = float((r["macd"] - r["macd_sig"]) / close * 100)        # <0 = 还在信号线下方
        hist_up = bool(r["macd_hist"] > r1["macd_hist"])
        vol_ratio = float(r["vol_ratio"]) if np.isfinite(r["vol_ratio"]) else 0.0
        bo = breakout_fields(r)                                   # 真突破标签 + 距箱顶 %（只作展示）
        lot = lot_size(t, market)
        affordable = close * lot <= budget
        pref_ok, pref_why = _pref_flags(df, market)
        # 顶部/出货风险标记（进场过滤是否打开都显示，方便人工判断）
        top_flags = []
        ext = float(r.get("ext_ma20_pct", np.nan))
        rsi_v = float(r.get("rsi", np.nan))
        dd_n = float(r.get("dist_days", np.nan))
        ush = float(r.get("upper_shadow_ratio", np.nan))
        rs = float(r.get("rs_pct", np.nan))
        if np.isfinite(ext) and ext > 8:
            top_flags.append(f"离20日线+{ext:.0f}%")
        if np.isfinite(rsi_v) and rsi_v > 70:
            top_flags.append(f"RSI{rsi_v:.0f}")
        if np.isfinite(dd_n) and dd_n >= 6:                 # 与日本株过滤线（≥6 不进场）一致
            top_flags.append(f"出货日{int(dd_n)}")
        if np.isfinite(ush) and ush > 3:
            top_flags.append("长上影")
        if np.isfinite(rs) and rs < 0:
            top_flags.append(f"落后指数{rs:.0f}%")

        # 各条件接近度（0~1）
        s_range = 1.0 if is_range else float(np.clip(1 - (range_pct - p.range_x_pct) / p.range_x_pct, 0, 1)) if np.isfinite(range_pct) else 0.0
        s_zero = 1.0 if near_zero else float(np.clip(1 - (abs(float(r["macd"])) / close * 100 - p.macd_zero_band_pct) / p.macd_zero_band_pct, 0, 1))
        if gap > 0:
            s_cross = 0.6 if bool(r["golden_cross"]) else 0.3       # 已在上方：刚金叉最好，否则错过
        else:
            s_cross = float(np.clip(1 - abs(gap) / 0.5, 0, 1)) * (1.0 if hist_up else 0.7)
        s_vol = float(np.clip(vol_ratio / p.vol_mult, 0, 1))
        score = 100 * (0.30 * s_range + 0.25 * s_zero + 0.30 * s_cross + 0.15 * s_vol)
        if not affordable:
            score *= 0.5

        if bool(r["entry"]):
            status = "triggered"
        elif is_range and near_zero and gap < 0 and abs(gap) < 0.15 and vol_ratio >= 1.0:
            status = "imminent"
        elif is_range and near_zero:
            status = "watch"
        else:
            status = "far"
        rows.append(dict(ticker=t, status=status, score=round(score, 1), close=round(close, 2),
                         range_pct=round(range_pct, 1) if np.isfinite(range_pct) else None,
                         macd_gap_pct=round(gap, 3), hist_up=hist_up,
                         vol_ratio=round(vol_ratio, 2),
                         to_box_top_pct=bo["to_box_top_pct"], breakout=bo["breakout"],
                         lot_cost=round(close * lot, 0), affordable=affordable,
                         pref_ok=pref_ok, pref_note=pref_why,
                         top_risk="；".join(top_flags), rsi=round(rsi_v, 0) if np.isfinite(rsi_v) else None,
                         rs_pct=round(rs, 1) if np.isfinite(rs) else None))
    if not rows:
        return pd.DataFrame()
    order = {"triggered": 0, "imminent": 1, "watch": 2, "far": 3}
    df = pd.DataFrame(rows)
    df["_o"] = df["status"].map(order)
    df = df.sort_values(["_o", "score"], ascending=[True, False]).drop(columns="_o")
    return df.head(top).reset_index(drop=True)
