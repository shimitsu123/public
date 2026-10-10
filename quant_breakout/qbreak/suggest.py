"""suggest.py — 操作面板的「建议的股票」= 规则的候选（2026-10-06 用户：「根据趋势等等建议的股票也要加到里面 可以一键买的
趋势也要能看到」）。只展示 + 给手动买入（qbreak/manual_orders.py 的 buy）用；不是收益预测，也不是 Claude 的建议。

三类（与日报的候补队列、qbreak/scan.py 同一个定义）：
  triggered  今天收盘出了买入信号（规则明天开盘买；买不了的写出是哪道闸门 / 名额 / 钱）
  imminent   即将触发：横盘 + MACD 0 轴附近 + 离金叉不到收盘价的 0.15% + 量比 ≥ 1
  watch      观察：横盘 + MACD 0 轴附近（按条件就绪度取前几只）
排序（只是排序与展示，不改交易；日报的候补队列照旧：状态 → 顺风 / 逆风 → 就绪度）：
  出了信号的在前；其余（快要出 + 观察中）合成一组（2026-10-07 用户「观察的股票要进行买入优先级排序 比如最上面的最大概率会买入」，
  登记研究 scripts/watch_prob_study.py 判定 A）：① 闸门（资格检查挡的放最后，新仓倍数 0 / 决算前的其次）→ ② 之后 10 个交易日内出买入信号的
  历史比例（qbreak/watch_prob.py：同样情况 = MACD 在哪 × 还差的条件数 × 今天的量比）高的先 → ③ near_key 的其余部分。
  没有比例表（var/watch_prob.json）→ 以前的顺序：快要出 → 观察中，组内 near_key = ① 闸门 → 今天就不满足、金叉那天多半也不满足的条件数
  （横盘 / 0 轴附近 / 周线量比 W2 / 出货日 …）→ MACD 估计几天后金叉（在信号线下往上靠的按天数；往下走的其次；已经在线上的最后）→
  今天的量比高的先 → 条件就绪度（0〜100）。
全部列出（2026-10-07 用户「建议的股票不限制个数」；以前最多 12 只、观察中最多 6 只）；拿着的票、核心 ETF 不列。每只附：
  rule  规则怎么处理（planned 已安排 / manual 手动买入已安排 / blocked 信号成立但不买 + 理由 / none 还没触发，规则不会买）
  buy   手动买入：block = 硬闸门（资格检查 / 立花能不能买 / 不在交易股票池 / 手动卖出后不买回）→ 页面不让点；
        warn = 现在会被挡、下一次决策可能变的（新仓倍数 0 / 决算前）；按规则的仓位估算（股数、金额、限价 = 收盘 ×1.03）
  trend 日K / 周K / 月K 的趋势标签（qbreak/kline.py；执行器再用长一点的行情补）
  near  离买入信号还差什么（proximity；只给「快要出」「观察中」）+ near_text 一句话
  prob  之后 10 个交易日内出买入信号的历史比例（watch_prob.for_row：p / n / y / h / cell / show；有比例表才有）
执行器下单前还会按当时的价格、权益、名额、闸门再查一遍（这里只是预览）。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import watch_prob as WP
from .calendar_jp import next_trading_day
from .tick import round_to_tick
from .unified import market_of

STATUS = {"triggered": "今天收盘出了买入信号", "imminent": "快要出买入信号（MACD 快要金叉、成交量不低）",
          "watch": "观察中（横着走、MACD 在 0 附近）"}                    # 2026-10-07：通俗说法（页面、日志）
RULE = {"planned": "规则已安排买入", "manual": "手动买入已安排", "blocked": "信号成立但规则不买", "none": "还没触发：规则不会买"}
NEED = {"Close", "entry", "range_pct", "is_range", "near_zero", "macd", "macd_sig", "macd_hist", "golden_cross", "vol_ratio",
        "box_top", "breakout"}                               # 条件就绪度要的列（核心 ETF 的 K 线没有这些 → 不列）


def _f(x, nd: int = 2):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if math.isfinite(v) else None


MAX_DAYS = 30                                                # 排序用：估出来超过 30 天 = 30 天
FAR_DAYS = 10                                                # 页面：线性外推 10 天以上不可靠 → 只写「还远」


def proximity(df: pd.DataFrame, p) -> dict:
    """离规则的买入信号还差什么（今天收盘为止；只用来排序和展示，不改交易）。
    where  below_up（MACD 在信号线下、往上靠）/ below_down（在线下、还在往下走）/ above（已经在线上：要先回落再金叉）/ unknown
    days   below_up 时估计再过几个交易日金叉：(MACD − 信号线) 按最近一天的变化线性外推（只是估算；最多 MAX_DAYS）
    miss   今天就不满足、金叉那天多半也不满足的条件（金叉那天的横盘看前一天的振幅 → 用今天的；W2 在同一周里不变）
    vol    今天的量比（金叉那天要 > vol_mult：当天的量预先不知道，只作参考）"""
    r, r1 = df.iloc[-1], df.iloc[-2]
    close = float(r["Close"])
    h, h1 = float(r["macd"] - r["macd_sig"]), float(r1["macd"] - r1["macd_sig"])
    days = None
    if not (np.isfinite(h) and np.isfinite(h1) and close > 0):
        where = "unknown"
    elif h > 0:
        where = "above"
    elif h - h1 > 0:
        where = "below_up"
        days = min(MAX_DAYS, int(math.floor(-h / (h - h1) + 1e-9)) + 1)      # 差 ≤ 0 → 第 days 天变成 > 0
    else:
        where = "below_down"
    miss = []
    rp = _f(r.get("range_pct"), 1)
    if rp is None or not rp < p.range_x_pct:
        miss.append(f"横盘（{p.range_n} 日振幅 {'—' if rp is None else f'{rp:g}%'}，要 < {p.range_x_pct:g}%）")
    if close > 0 and np.isfinite(float(r["macd"])) and not abs(float(r["macd"])) / close * 100 < p.macd_zero_band_pct:
        miss.append(f"MACD 离 0 轴（{abs(float(r['macd'])) / close * 100:.2f}%，要 < {p.macd_zero_band_pct:g}%）")
    w = _f(r.get("w5v"))
    if p.min_weekly_vol_ratio and w is not None and w < p.min_weekly_vol_ratio:
        miss.append(f"周线量比（{w:g}，要 ≥ {p.min_weekly_vol_ratio:g}）")
    dd = _f(r.get("dist_days"), 0)
    if p.max_distribution_days and dd is not None and dd >= p.max_distribution_days:
        miss.append(f"出货日（{p.distribution_lookback} 日内 {dd:g} 天，要 < {p.max_distribution_days}）")
    rv = _f(r.get("rsi"), 0)
    if p.max_rsi and rv is not None and rv > p.max_rsi:
        miss.append(f"RSI（{rv:g}，要 ≤ {p.max_rsi:g}）")
    ext = _f(r.get("ext_ma20_pct"), 1)
    if p.max_ext_ma20_pct and ext is not None and ext > p.max_ext_ma20_pct:
        miss.append(f"离 20 日线（+{ext:g}%，要 ≤ {p.max_ext_ma20_pct:g}%）")
    if p.min_rs_pct > -900 and "rs_ok" in df.columns and not bool(r["rs_ok"]):
        miss.append("相对强度（跑输指数）")
    return {"where": where, "days": days, "miss": miss, "vol": _f(r.get("vol_ratio"))}


def near_text(n: dict | None, p) -> str:
    """离买入信号的一句话（页面用）。"""
    n = n or {}
    w = n.get("where")
    a = {"below_up": f"MACD 约 {n.get('days')} 天后金叉（按最近一天的变化估）"
                     if (n.get("days") or 0) < FAR_DAYS else f"MACD 往上靠，但离金叉还远（估计 {FAR_DAYS} 天以上）",
         "below_down": "MACD 在信号线下、还在往下走（要先拐头）",
         "above": "MACD 已经在信号线上（要先回落再金叉）"}.get(w, "MACD 算不出来")
    parts = [a, f"金叉那天量要 > {p.vol_mult:g} 倍（今天 {n['vol']:g} 倍）" if n.get("vol") is not None
             else f"金叉那天量要 > {p.vol_mult:g} 倍"]
    if n.get("miss"):
        parts.append("还差：" + "、".join(n["miss"]))
    return "离买入信号：" + "；".join(parts)


def near_key(row: dict) -> tuple:
    """「快要出」「观察中」组里的顺序（小的在前）：闸门 → 还差的条件数 → 估计几天金叉 → 量比高的先 → 就绪度高的先。"""
    b, n = row.get("buy") or {}, row.get("near") or {}
    tier = 2 if b.get("block") else 1 if b.get("warn") else 0
    w = n.get("where")
    d = int(n.get("days") or MAX_DAYS) if w == "below_up" else {"below_down": MAX_DAYS + 1, "above": MAX_DAYS + 2}.get(w, MAX_DAYS + 3)
    return (tier, len(n.get("miss") or []), d, -float(row.get("vol_ratio") or 0), -float(row.get("score") or 0))


def order_key(row: dict, ranked: bool) -> tuple:
    """建议的股票的顺序（小的在前）。ranked（有比例表）：出了信号的在前，其余（快要出 + 观察中）一组：闸门 → 比例高的先 → near_key 其余；
    没有比例表：出了信号 → 快要出 → 观察中，组内 near_key。出了信号的组内保持原来的顺序（scan 的就绪度）。"""
    st = row.get("status")
    if st == "triggered":
        return (0,)
    nk = near_key(row)
    if ranked:
        p = (row.get("prob") or {}).get("p")
        return (1, nk[0], -float(p) if p is not None else 1.0) + nk[1:]
    return ({"imminent": 1, "watch": 2}.get(st, 9),) + nk


def rank(rows: list, table: dict | None = None) -> list:
    """给「快要出」「观察中」的行补上 prob（没有的话）并按 order_key 排（稳定排序）；table = None → 读 var/watch_prob.json。
    面板渲染时也用（执行器早上写的旧汇总没有 prob → 这里补，更新代码后不用等下一次运行）。"""
    tab = WP.load() if table is None else table
    for r in rows:
        if tab and "prob" not in r:
            pr = WP.for_row(r, tab)
            if pr:
                r["prob"] = pr
    return sorted(rows, key=lambda r: order_key(r, bool(tab)))


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
          manual: dict | None = None) -> dict:
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
    pick += [r for r in rows if r["status"] == "watch" and r["ticker"] not in held]          # 不限个数
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
            rule = {"state": "manual", "text": f"手动买入已安排：{fill:%m/%d} 开盘买 {int(p[1]):,} 股"
                                               f"（最高 ¥{round_to_tick(float(p[0]) * (1 + gap / 100), t, 'BUY'):,g}）"}
        elif t in st.plan:
            p = st.plan[t]
            rule = {"state": "planned", "text": f"规则已安排：{fill:%m/%d} 开盘买 {int(p[1]):,} 股"
                                                f"（最高 ¥{round_to_tick(float(p[0]) * (1 + gap / 100), t, 'BUY'):,g}）"}
        elif sig:
            rule = {"state": "blocked", "text": "信号成立但规则不买：" + _why_not(eng, t, i, em, gate, earn)}
        else:
            rule = {"state": "none", "text": "还没出买入信号：规则不会买"}
        warn = []
        if not gate and em <= 0:
            warn.append("规则现在不开这只的新仓（新仓倍数 0）：会被挡")
        if not gate and earn:
            warn.append(f"{earn}：会被挡")
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
        if r["status"] != "triggered":                       # 离买入信号还差什么（排序 + 页面一句话）
            out[-1]["near"] = proximity(frames[t], params)
            out[-1]["near_text"] = near_text(out[-1]["near"], params)
    tab = WP.load()                                            # 有比例表 → 快要出 + 观察中按历史比例排（研究判定 A）；没有 → 以前的顺序
    out = rank(out, tab or {})
    return {"asof": asof, "fill_day": fill.isoformat(), "equity": round(eq), "rows": out, "counts": counts,
            "ranked": bool(tab), "prob_h": int((tab or {}).get("h") or WP.H), "prob_pct": bool((tab or {}).get("show_pct", True)),
            "max_positions": int(cfg.max_positions), "position_pct": float(cfg.position_pct),
            "cap_pct": round(float(cfg.max_position_pct) * 100, 2),
            "note": ("规则的候选（快要出 + 观察中按之后 10 个交易日内出买入信号的历史比例排）" if tab else
                     "规则的候选（快要出 / 观察中按离买入信号的远近排序）") + "，不是收益预测，也不是建议；手动买入是你自己的决定。"}


def lines(sg: dict | None) -> list[str]:
    """日志用：建议的股票（今天出了买入信号的 + 快要出信号的）一行一只（说法按 STATUS，旧的汇总也是新说法）。"""
    out = []
    for r in (sg or {}).get("rows") or []:
        if r.get("status") not in ("triggered", "imminent"):
            continue
        nm = f" {r['name']}" if r.get("name") else ""
        out.append(f"- 候选 {r['ticker']}{nm}：{STATUS.get(str(r.get('status')), r.get('status_text'))}；{(r.get('rule') or {}).get('text') or ''}")
    return out


__all__ = ["build", "lines", "rule_shares", "proximity", "near_text", "near_key", "order_key", "rank", "MAX_DAYS", "FAR_DAYS", "STATUS", "RULE"]
