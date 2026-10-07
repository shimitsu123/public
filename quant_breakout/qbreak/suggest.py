"""suggest.py — 操作面板的「建议的股票」= 规则的候选（2026-10-06 用户：「根据趋势等等建议的股票也要加到里面 可以一键买的
趋势也要能看到」）。只展示 + 给手动买入（qbreak/manual_orders.py 的 buy）用；不是收益预测，也不是 Claude 的建议。

三类（与日报的候补队列、qbreak/scan.py 同一个定义）：
  triggered  今天收盘出了买入信号（规则明天开盘买；买不了的写出是哪道闸门 / 名额 / 钱）
  imminent   即将触发：横盘 + MACD 0 轴附近 + 离金叉不到收盘价的 0.15% + 量比 ≥ 1
  watch      观察：横盘 + MACD 0 轴附近（按条件就绪度取前几只）
排序 = 状态 → 条件就绪度（0〜100）。拿着的票、核心 ETF 不列。每只附：
  rule  规则怎么处理（planned 已安排 / manual 手动买入已安排 / blocked 信号成立但不买 + 理由 / none 还没触发，规则不会买）
  buy   手动买入：block = 硬闸门（资格检查 / 立花能不能买 / 不在交易股票池 / 手动卖出后不买回）→ 页面不让点；
        warn = 现在会被挡、下一次决策可能变的（新仓倍数 0 / 决算前）；按规则的仓位估算（股数、金额、限价 = 收盘 ×1.03）
  trend 日K / 周K / 月K 的趋势标签（qbreak/kline.py；执行器再用长一点的行情补）
执行器下单前还会在下一次决策里按当时的收盘、权益、名额、闸门再查一遍（这里只是预览）。
"""
from __future__ import annotations

import math

import pandas as pd

from .calendar_jp import next_trading_day
from .tick import round_to_tick
from .unified import market_of

STATUS = {"triggered": "今天收盘出了买入信号", "imminent": "快要出买入信号（MACD 快要金叉、成交量不低）",
          "watch": "观察中（横着走、MACD 在 0 附近）"}                    # 2026-10-07：通俗说法（页面、日志）
RULE = {"planned": "规则已安排买入", "manual": "手动买入已安排", "blocked": "信号成立但规则不买", "none": "还没触发：规则不会买"}
MAX_ROWS = 12
N_WATCH = 6
NEED = {"Close", "entry", "range_pct", "is_range", "near_zero", "macd", "macd_sig", "macd_hist", "golden_cross", "vol_ratio",
        "box_top", "breakout"}                               # 条件就绪度要的列（核心 ETF 的 K 线没有这些 → 不列）


def _f(x, nd: int = 2):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if math.isfinite(v) else None


def rule_shares(eng, t: str, i: int, em: float) -> int:
    """按规则的仓位能买几股（与统一决策的新仓同一算法：min(权益 × position_pct × min(1, 倍数), 权益 × max_position_pct)
    ÷（收盘 × (1 + 滑点)），单元向下取整；不看现金 —— 现金不够时执行器按「现金 + 核心 ETF」减）。"""
    cfg = eng.cfg
    eq = float(eng.equity(i))
    px = float(eng._px_close(t, i)) * (1 + eng.slip["JP"])
    lot = int(eng.lots[eng.col[t]])
    if not (px > 0 and eq > 0) or em <= 0:
        return 0
    budget = min(eq * cfg.position_pct * min(1.0, em), eq * cfg.max_position_pct)
    return max(0, int(math.floor(budget / px / lot)) * lot)


def _why_not(eng, t: str, i: int, em: float, gate: str | None, earn: str | None) -> str:
    """信号成立、规则却没排买入的理由（与统一决策的检查同一个顺序）。"""
    st, cfg = eng.st, eng.cfg
    if gate:
        return f"资格检查：{gate}"
    if em <= 0:
        return "新仓倍数 0（宏观 / 判断层 / 关联搭配 C / TBF 里有一层说现在不开这只的新仓）"
    if earn:
        return earn
    n_after = len(st.pos) - sum(1 for x in st.pending_exit if x in st.pos)
    if n_after + len([x for x in st.plan if x != t]) >= cfg.max_positions or len(st.pos) >= cfg.max_positions:
        return f"个股名额已满（上限 {cfg.max_positions} 只）"
    return "钱不够买 1 个单元（按仓位 / 现金 + 核心 ETF 算）"


def build(ind: dict, eng, i: int, params, pool: list[str] | None = None, names: dict | None = None,
          manual: dict | None = None, max_rows: int = MAX_ROWS, n_watch: int = N_WATCH) -> dict:
    """第 i 根 K 线收盘后的决策之后（plan 已经排好）：规则的候选 → {"asof", "fill_day", "rows", "counts"}。
    ind：{代码: compute_indicators 的结果}；pool：交易股票池（默认 = 引擎里的东证个股）；names：代码 → 公司名；
    manual：执行器账本的 manual（看哪些是手动买入）。"""
    from .scan import scan
    from .sectors import sector_cn
    st, A, cfg = eng.st, eng.A, eng.cfg
    bar = eng.gidx[i]
    asof = str(bar.date())
    fill = next_trading_day(bar.date())
    pool = [t for t in (pool if pool is not None else A.tickers)
            if market_of(t) == "JP" and t not in eng.core_set and t in ind and t in eng.col]
    frames = {}
    for t in pool:
        df = ind[t]
        if not NEED <= set(df.columns):
            continue
        if len(df) and df.index[-1] > bar:
            df = df.loc[:bar]
        if len(df) and df.index[-1] == bar:                   # 今天没有 K 线（停牌等）的票不列
            frames[t] = df
    eq = float(eng.equity(i))
    sc = scan(frames, params, "JP", eq * cfg.position_pct, top=len(frames)) if frames else pd.DataFrame()
    rows = sc.to_dict("records") if len(sc) else []
    held = set(st.pos)
    counts = {k: sum(1 for r in rows if r["status"] == k) for k in STATUS}
    pick = [r for r in rows if r["status"] in ("triggered", "imminent") and r["ticker"] not in held]
    pick += [r for r in rows if r["status"] == "watch" and r["ticker"] not in held][:n_watch]
    pick = pick[:max_rows]
    buys = ((manual or {}).get("buys") or {})
    gap = eng.ex["JP"].max_entry_gap_pct
    out = []
    for r in pick:
        t = r["ticker"]
        j = eng.col[t]
        px = float(A.close[i, j])
        lot = int(eng.lots[j])
        em = float(eng._entry_mult(t, i))
        gate = eng.entry_gate_fn(t, i) if eng.entry_gate_fn is not None else None
        earn = None
        if not gate and em > 0 and eng.entry_block_fn is not None and r["status"] in ("triggered", "imminent", "watch"):
            try:
                earn = eng.entry_block_fn(t, i)
            except Exception:                                  # noqa: BLE001  展示用：取不到就不写
                earn = None
        sig = bool(A.entry[i, j])
        if t in st.plan and (buys.get(t) or {}).get("decided_on") == asof:
            p = st.plan[t]
            rule = {"state": "manual", "text": f"手动买入已安排：{fill} 开盘寄付指値买 {int(p[1]):,} 股"
                                               f"（限价 ¥{round_to_tick(float(p[0]) * (1 + gap / 100), t, 'BUY'):,g}）"}
        elif t in st.plan:
            p = st.plan[t]
            rule = {"state": "planned", "text": f"规则已安排：{fill} 开盘寄付指値买 {int(p[1]):,} 股"
                                                f"（限价 ¥{round_to_tick(float(p[0]) * (1 + gap / 100), t, 'BUY'):,g}）"}
        elif sig:
            rule = {"state": "blocked", "text": "信号成立但规则不买：" + _why_not(eng, t, i, em, gate, earn)}
        else:
            rule = {"state": "none", "text": "还没触发买入信号：规则不会买（手动买入是你自己的决定，没有回测验证）"}
        warn = []
        if not gate and em <= 0:
            warn.append("规则现在不开这只的新仓（新仓倍数 0）：执行器会挡")
        if not gate and earn:
            warn.append(f"{earn}：执行器会挡")
        out.append({
            "ticker": t, "code": t.split(".")[0], "name": (names or {}).get(t.split(".")[0]),
            "sector": sector_cn(t, "JP"), "status": r["status"], "status_text": STATUS.get(r["status"], r["status"]),
            "signal": sig, "score": _f(r.get("score"), 1), "close": _f(px), "range_pct": _f(r.get("range_pct"), 1),
            "macd_gap_pct": _f(r.get("macd_gap_pct"), 3), "vol_ratio": _f(r.get("vol_ratio")),
            "to_box_top_pct": _f(r.get("to_box_top_pct"), 1), "breakout": bool(r.get("breakout")),
            "top_risk": r.get("top_risk") or "", "rsi": _f(r.get("rsi"), 0), "rule": rule,
            "buy": {"block": gate, "warn": warn, "em": _f(em, 3), "lot": lot, "px": _f(px),
                    "limit": round_to_tick(px * (1 + gap / 100), t, "BUY") if px > 0 else None,
                    "rule_shares": rule_shares(eng, t, i, em if em > 0 else 1.0),
                    "planned": t in st.plan},
        })
    return {"asof": asof, "fill_day": fill.isoformat(), "equity": round(eq), "rows": out, "counts": counts,
            "max_positions": int(cfg.max_positions), "position_pct": float(cfg.position_pct),
            "cap_pct": round(float(cfg.max_position_pct) * 100, 2),
            "note": "规则的候选（条件就绪度排序），不是收益预测，也不是建议；手动买入是你自己的决定。"}


def lines(sg: dict | None) -> list[str]:
    """日志用：建议的股票（今天出了买入信号的 + 快要出信号的）一行一只（说法按 STATUS，旧的汇总也是新说法）。"""
    out = []
    for r in (sg or {}).get("rows") or []:
        if r.get("status") not in ("triggered", "imminent"):
            continue
        nm = f" {r['name']}" if r.get("name") else ""
        out.append(f"- 候选 {r['ticker']}{nm}：{STATUS.get(str(r.get('status')), r.get('status_text'))}；{(r.get('rule') or {}).get('text') or ''}")
    return out


__all__ = ["build", "lines", "rule_shares", "STATUS", "RULE", "MAX_ROWS"]
