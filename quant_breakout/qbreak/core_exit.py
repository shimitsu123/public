"""core_exit.py — 拿着的闲置资金 ETF「什么时候会自动卖」与离触发还有多远（只展示，不改交易）。

来由：2026-10-07 用户「现在成交的etf在什么情况下会自动卖出」→「把「自动卖出条件 + 离触发还有多远」（离转熊线 −11.4%、
确认 0/5 天、转熊后去现金还是 1482）直接显示在面板的 ETF 卡片上，Mac 和手机都能看到」。

这里不重新判定，只把 qbreak/unified.py _decide_core 的规则说出来、填上执行器算好的数字：
  ① 全部卖：这只 ETF 的开关（qbreak/idle_cash.py MODES[方式]["core_index"]）变成「不拿」→ 下一个东证开盘全部卖（寄付成行）。
     "US" / "JP" = 牛熊分界（var/bullbear.json 的 ma_band：连续 k 天收盘 < L 日均价 ×(1 − b) → 熊）；
     "BR:BD"（对冲版美债 1482，BCU）= 美股转牛（换回 1545）或 股债 63 天相关 ≥ 0（留现金）；别的开关只写方式名。
     不在现在这个方式里的 ETF（以前的方式留下的）→ 下一次决策全部卖。
  ② 卖完去哪：Q1B 的 1545 → 那时股债 63 天负相关 → 对冲版美债 1482，否则现金（qbreak/bond_refuge.py）；只跟牛熊的方式 → 现金。
  ③ 部分卖：规则要买新的日本个股（一只约 权益 × position_pct × 新仓倍数）、日元不够 → 同一个开盘先卖核心 ETF 补足
     （缺口 ×(1 + 开盘跳空上限 3%)，按单元向上取整）；新仓倍数 0 / 个股已满 / 现金够 → 不会。
  ④ 不会因为：它自己跌（核心 ETF 没有止损）、新仓倍数 / 风险报告 / 威胁指数（只管个股新仓）、汇率、立花「买不了」（只挡买）。
页面最上面三格（tiles）= 用户点名要看的三个数：离翻转线多远、已确认几天、翻转后去哪（1482 是：离转牛线、已确认、股债相关）。
数字：执行器的汇总 out/live_unified_<账本>.json（market = 牛熊读数、idle_cash = 方式与股债相关、new_pos = 新仓倍数与仓位），
交易日 07:40 的运行按前一天的收盘（美股 = 前一晚的收盘）算好；面板只读。没有的数字就不写（写「下一次运行之后显示」）。
"""
from __future__ import annotations

import math
import re

from . import idle_cash as IC
from . import paths
from .utils import read_json

IDX_NAME = {"US": "S&P500", "JP": "日経平均"}
CLOSE_JST = {"US": "美股收盘 = 日本时间早上 5〜6 点", "JP": "东证 15:30 收盘"}
TRACKS = {"1655.T": "US", "1321.T": "JP"}                 # 本身就是择时指数的 ETF（「指数单独跌」那句不用写）
NEAR = ("bull_near", "bull_to_bear", "bear_near", "bear_to_bull")
CORR_NEAR = -0.1                                          # 1482：股债相关 ≥ −0.1 = 快到 0（只是页面标红，不是规则）
POS_PCT, MAX_POS, GAP_PCT, BAND_PCT = 0.25, 4, 3.0, 10.0  # 汇总里没有时的缺省（= var/sim.json / ExecConfig 的现值）


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _md(d) -> str:
    s = str(d or "")
    return f"{s[5:7]}/{s[8:10]}" if len(s) >= 10 else (s or "—")


def _pt(v) -> str:
    v = _f(v)
    return "—" if v is None else (f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.2f}")


def _yen(v) -> str:
    v = _f(v)
    return "—" if v is None else f"¥{round(v, -3):,.0f}"


def _sg(v, nd: int = 1) -> str:
    """带符号（负号用 −）：-11.4 → 「−11.4」、0.404 → 「+0.40」（nd = 2）。"""
    v = _f(v)
    return "—" if v is None else f"{v:+.{nd}f}".replace("-", "−")


def _code(t: str) -> str:
    return str(t).split(".")[0]


def _det(bb: dict) -> tuple[int, float, int]:
    """牛熊分界的参数 (L, b, k)：读数里的 detector 文字（ma_band(L=250,b=0.03,k=5)）→ 没有就从均价与翻转线反推。"""
    s = str(bb.get("detector") or "")
    m_l, m_b, m_k = re.search(r"L=(\d+)", s), re.search(r"b=([0-9.]+)", s), re.search(r"k=(\d+)", s)
    L = int(m_l.group(1)) if m_l else 250
    b = float(m_b.group(1)) if m_b else None
    if b is None:
        ma, line = _f(bb.get("ma")), _f(bb.get("flip_line") or bb.get("level"))
        b = round(abs(1 - line / ma), 4) if ma and line else 0.03
    k = int(m_k.group(1)) if m_k else int(bb.get("confirm_need") or 5)
    return L, b, k


def market_row(bb: dict | None, m: str, flip_to: str, *, then: str = "下一个开盘全部卖（寄付成行）", label: str = "全部卖") -> dict:
    """牛熊分界的一条触发。flip_to = "bear"（牛市里拿着、等转熊）/ "bull"（熊市里拿着、等转牛）。
    返回 {"k", "text", "sub", "chips": [{"text", "tone": "bad" | "hot" | None, "dots": (已确认, 要几天)?}], "hot", "fired", 数字…}；
    hot = 快要触发 / 已经触发（页面标红）；fired = 已经翻过去了（这次决策就卖）。"""
    bb = bb or {}
    name, st = IDX_NAME.get(m, m), bb.get("state")
    L, b, k = _det(bb)
    word = "转熊" if flip_to == "bear" else "转牛"
    side = "下" if flip_to == "bear" else "上"
    out = {"k": label, "m": m, "flip_to": flip_to, "word": word, "side": side, "state": st, "L": L, "b": b, "need": k,
           "asof": bb.get("asof"), "since": bb.get("since"), "close": _f(bb.get("close")), "ma": _f(bb.get("ma")),
           "line": _f(bb.get("flip_line") or bb.get("level")), "dist": _f(bb.get("to_flip_pct")),
           "confirm": int(bb.get("confirm_days") or 0), "phase": bb.get("phase"), "chips": [], "hot": False, "fired": False}
    head = f"{name} 连续 {k} 天收在{word}线{side} → {then}"
    if st not in ("bull", "bear"):
        out.update(text=head, sub=f"{name} 的牛熊读数还没有（执行器下一次运行之后显示）")
        return out
    if (st == "bear") == (flip_to == "bear"):                 # 已经翻过去了：这次决策就卖
        out.update(text=f"{name} 已{word}（{out['since'] or '—'} 起）→ {then}", sub=bb.get("phase_label") or "", hot=True, fired=True)
        out["chips"].append({"text": f"已{word}", "tone": "bad"})
        return out
    n, dist = out["confirm"], out["dist"]
    hot = n >= 1 or out["phase"] in NEAR
    if n >= 1:
        out["chips"].append({"text": f"已在{word}线{side} {abs(dist or 0):.1f}%，再 {max(k - n, 1)} 天就{word}", "tone": "bad"})
    elif dist is not None:
        out["chips"].append({"text": f"离{word}线 {_sg(dist)}%", "tone": "bad" if hot else None})
    out["chips"].append({"text": f"已确认 {n} / {k} 天", "tone": "bad" if n >= 1 else None, "dots": (n, k)})
    mult = f"{1 - b:g}" if flip_to == "bear" else f"{1 + b:g}"
    out["formula"] = f"{word}线 {_pt(out['line'])} = {L} 日均价 {_pt(out['ma'])} × {mult}（线每天跟着均价动）"
    out["phase_txt"] = (f"{bb['phase_label']} · {out['since'] or '—'} 起{'牛' if st == 'bull' else '熊'}市"
                        if bb.get("phase_label") else "")
    sub = f"{name} {_pt(out['close'])} · {out['formula']}" + (f" · {out['phase_txt']}" if out["phase_txt"] else "")
    out.update(text=head, sub=sub, hot=hot)
    return out


def market_tiles(r: dict) -> list[dict]:
    """market_row → 最上面的两格：离翻转线多远、已确认几天（已经翻过去 → 「已转熊」「全部卖」）。读数没有 → []。"""
    if r.get("state") not in ("bull", "bear"):
        return []
    name, word, side = IDX_NAME.get(r["m"], r["m"]), r["word"], r["side"]
    if r["fired"]:
        return [{"label": name, "value": f"已{word}", "sub": f"{r.get('since') or '—'} 起", "tone": "bad"},
                {"label": "下一个开盘", "value": "全部卖", "sub": "寄付成行", "tone": "bad"}]
    n, k, dist = r["confirm"], r["need"], r["dist"]
    if n >= 1:
        first = {"label": f"已在{word}线{side}", "value": f"{abs(dist or 0):.1f}%", "sub": f"{name} {_pt(r['close'])}", "tone": "bad"}
    else:
        first = {"label": f"离{word}线", "value": f"{_sg(dist)}%" if dist is not None else "—",
                 "sub": f"{_pt(r['close'])} → {_pt(r['line'])}", "tone": "bad" if r["hot"] else None}
    return [first, {"label": "已确认", "value": f"{n} / {k} 天", "sub": f"再 {max(k - n, 1)} 天就{word}" if n >= 1 else "",
                    "dots": (n, k), "tone": "bad" if n >= 1 else None}]


def _bcu_after(br: dict | None) -> tuple[str, str, str, str]:
    """Q1B：美股转熊那天闲置资金去哪（按现在的股债相关；那天的判定才算数）→ (格子里的字, 一句话, 补充, 格子的补充)。"""
    br = br or {}
    on, cs = br.get("on"), _sg(br.get("corr"), 2)
    head = f"股债 {br.get('win', 63)} 天相关 {cs}（{_md(br.get('corr_date'))}）"
    if on is None:
        return "留现金", "留现金", "股债相关算不了（国债收益率没更新）→ 按不拿对冲版美债 1482", "股债相关算不了"
    if on:
        return "换 1482", "换对冲版美债 1482", f"{head} < 0：那天还是负相关就换 1482，变成 ≥ 0 就留现金", f"股债相关 {cs}"
    return ("留现金", "留现金", f"{head}，{br.get('since') or '—'} 起不是负相关；< 0 才换对冲版美债 1482", f"股债相关 {cs}")


def _jp_mult(sm: dict) -> tuple[float | None, str]:
    """日本个股的新仓倍数与压住它的层（run.py _new_pos_brief 的 [[层, 倍数], …]）→ (倍数, 「风险报告「避险」」/「宏观 ×0.5」)。"""
    jp = ((sm.get("new_pos") or {}).get("markets") or {}).get("JP") or {}
    why = []
    for w in jp.get("why") or []:
        n, v = (w[0], _f(w[1])) if isinstance(w, (list, tuple)) and len(w) == 2 else (str(w), None)
        why.append(n if not v else f"{n} ×{v:g}")
    return _f(jp.get("mult")), "、".join(why)


def partial_row(t: str, sm: dict, st: dict, *, px: float | None, lot: int, cur: int, fill_day=None) -> dict | None:
    """③ 部分卖：规则买新的日本个股、日元不够 → 先卖核心 ETF 补足。账户不做个股（汇总里没有 suggest / new_pos）→ None。"""
    np_ = sm.get("new_pos") or {}
    sg = sm.get("suggest") or {}
    if not np_ and not sg:
        return None
    pos_pct = _f(np_.get("position_pct")) or _f(sg.get("position_pct")) or POS_PCT
    max_pos = int(np_.get("max_positions") or sg.get("max_positions") or MAX_POS)
    gap = _f(np_.get("gap_pct"))
    gap = GAP_PCT if gap is None else gap
    mult, why = _jp_mult(sm)
    hist = st.get("history") or []
    eq = _f(hist[-1][1]) if hist else None
    cash = _f(st.get("cash_jpy")) or 0.0
    out = {"k": "部分卖", "chips": [], "hot": False, "fired": False, "units": None, "per": None}
    per = eq * pos_pct * (min(1.0, mult) if mult else 1.0) if eq else None
    need = max(0.0, per - cash) * (1 + gap / 100) if per else None
    if need and px and px > 0:
        lot = max(int(lot or 1), 1)
        out["units"] = min(int(cur), int(math.ceil(need / px / lot)) * lot)
    out["per"] = per
    est = (f"（一只新仓约 {_yen(per)}：约卖 {out['units']:,} 口）" if out["units"] else
           f"（一只新仓约 {_yen(per)}）" if per else "")
    out["text"] = f"规则要买新的日本个股、现金不够 → 同一个开盘先卖它补足{est}"
    plan = (st.get("core_plan") or {}).get(t) or []
    n_pos = len(st.get("pos") or {})
    if len(plan) == 2 and plan[0] == "SELL" and 0 < int(plan[1]) < cur:
        buys = sorted(st.get("plan") or {})
        adds = sorted(st.get("add_plan") or {})
        why_p = (f"给要买的个股腾钱：{'、'.join(_code(x) for x in buys)}" if buys else
                 "给手动加仓腾钱" if adds else "调回规则目标")
        out.update(sub=f"规则已排（{why_p}）", fired=True)
        out["chips"].append({"text": f"{_md(fill_day)} 开盘卖 {int(plan[1]):,} 口", "tone": "hot"})
    elif n_pos >= max_pos:
        out["sub"] = f"个股已满 {max_pos} 只：不会为新仓再卖（卖掉一只之后才会）"
    elif mult is not None and mult <= 0:
        out["sub"] = f"现在新仓倍数 0（{why or '规则现在不开新仓'}）：暂时不会"
    elif per is not None and cash >= per:
        out["sub"] = f"现在现金 {_yen(cash)} 够买一只：不用卖"
    elif mult is not None and mult < 1:
        out["sub"] = f"现在新仓倍数 ×{mult:g}（{why or '—'}）：出了买入信号就会，按倍数卖得少一些"
    elif mult is not None:
        out["sub"] = "现在新仓倍数 ×1：出了买入信号就会（候选见下面「建议的股票」）"
    else:
        out["sub"] = "新仓倍数在执行器下一次运行之后显示"
    return out


def _own(t: str) -> str:
    return str(IC.NAMES.get(t, t)).split("（")[0]


def _stats(m: str) -> dict:
    """var/bullbear.json 的样本外评估（2006 年以来）：数据目录（liveu.sh 同步的）→ 仓库里的。"""
    for base in (paths.home(), paths.PROJECT_ROOT / "var"):
        d = read_json(base / "bullbear.json", {}) or {}
        s = (d.get("test_2006_on") or {}).get(m)
        if s:
            return s
    return {}


def _row(k: str, text: str, sub: str = "", *, hot: bool = False, fired: bool = False, chips=None) -> dict:
    return {"k": k, "text": text, "sub": sub, "chips": list(chips or []), "hot": hot, "fired": fired}


def build(t: str, sm: dict | None, book: dict | None, *, px: float | None = None, lot: int = 1) -> dict | None:
    """一只拿着的核心 ETF → {"t", "name", "mode", "label", "key", "asof", "asof_md", "tiles": [...], "rows": [...], "never",
    "notes": [...], "hot"}；没拿着 → None。sm = 执行器的汇总（out/live_unified_<账本>.json）；book = 账本（state/live_unified_<账本>.json）。
    tiles：{"label", "value", "sub", "tone", "dots"?}；rows：{"k", "text", "sub", "chips", "hot", "fired"}（格子里有的数不再放 chips）。"""
    sm, book = sm or {}, book or {}
    st = book.get("state") or {}
    cur = int((st.get("core_units") or {}).get(t, 0) or 0)
    if cur <= 0:
        return None
    px = _f(px) or _f((st.get("core_last") or {}).get(t))
    ic = sm.get("idle_cash") or {}
    mode = ic.get("mode") or IC.mode_of(read_json(paths.home() / "sim.json", {}) or {})
    spec = IC.MODES.get(mode, IC.MODES["K0"])
    label = ic.get("label") or IC.LABELS.get(mode, mode)
    key = spec["core_index"].get(t)
    mk = sm.get("market") or {}
    tiles, rows, notes = [], [], []
    np_ = sm.get("new_pos") or {}
    band = _f(np_.get("band_pct"))
    band = BAND_PCT if band is None else band
    timing = None                                             # 哪个指数的牛熊决定它（时间线 / 历史那几句用）
    if key is None:                                           # 以前的方式留下的
        tiles.append({"label": "下一次决策", "value": "全部卖", "sub": "不在现在的方式里", "tone": "bad"})
        rows.append(_row("全部卖", f"已经不在现在的闲置资金方式里（{label}）→ 下一次决策全部卖", hot=True, fired=True))
    elif key in ("US", "JP"):
        timing = key
        r = market_row(mk.get(key), key, "bear")
        tiles += market_tiles(r)
        if tiles and not r["fired"]:                          # 格子里已经有了现价 → 线、离多远、确认几天：这里只写线怎么算
            r.update(chips=[], sub=r["formula"] + (f" · {r['phase_txt']}" if r["phase_txt"] else ""))
        elif tiles:
            r["chips"] = []
        rows.append(r)
        back = f"之后 {IDX_NAME[key]} 转回牛市 → 再买回 {_code(t)}"
        notes.append(f"转回牛市 = {IDX_NAME[key]} 连续 {r['need']} 天收在转牛线上（{r['L']} 日均价 × {1 + r['b']:g}）")
        if mode in IC.BOND_REFUGE and key == "US":
            short, long_, sub, tsub = _bcu_after(ic.get("bond_refuge") or {})
        else:
            short, long_, sub, tsub = "留现金", "留现金", "", ""
        if tiles:
            tiles.append({"label": "卖完" if r["fired"] else "转熊后", "value": short, "sub": tsub, "tone": None})
        rows.append(_row("卖完去哪", f"卖完：{long_}" if r["fired"] else f"现在转熊的话：{long_}", (sub + "。" if sub else "") + back))
    elif key == "BR:BD":                                      # 对冲版美债 1482：美股熊且股债负相关时才拿
        timing = "US"
        r = market_row(mk.get("US"), "US", "bull", then="卖它、换回纳斯达克 100（1545）")
        tiles += market_tiles(r)
        if tiles and not r["fired"]:
            r.update(chips=[], sub=r["formula"] + (f" · {r['phase_txt']}" if r["phase_txt"] else ""))
        elif tiles:
            r["chips"] = []
        rows.append(r)
        br = ic.get("bond_refuge") or {}
        c = _f(br.get("corr"))
        hot = br.get("on") is not True or (c is not None and c >= CORR_NEAR)
        tiles.append({"label": "股债相关", "value": _sg(c, 2) if c is not None else "算不了",
                      "sub": f"{br.get('win', 63)} 天；≥ 0 就卖", "tone": "bad" if hot else None})
        rows.append(_row("或", f"股债 {br.get('win', 63)} 天相关变成 ≥ 0 → 下一个开盘全部卖、留现金",
                         f"S&P500 与对冲版美国 7〜10 年国债的日收益相关（{_md(br.get('corr_date'))}；国债起避险作用才拿）",
                         hot=hot, fired=br.get("on") is False))
    else:                                                     # 别的方式自己的开关（趋势 / 轮动 / 对冲 …）
        rows.append(_row("全部卖", f"「{label}」的开关变成「不拿」→ 下一个开盘全部卖"))
        for m in sorted(IC.uses_market(mode)):
            timing = timing or m
            rows.append({**market_row(mk.get(m), m, "bear"), "k": "或"})
    pr = partial_row(t, sm, st, px=px, lot=lot, cur=cur, fill_day=sm.get("fill_day"))
    if pr:
        rows.append(pr)
    never = ["它自己跌多少都不卖（核心 ETF 没有止损）"]
    if key in ("US", "JP") and TRACKS.get(t) != key:
        never.append(f"{_own(t)} 单独跌（看的是 {IDX_NAME[key]}）")
    never.append("汇率涨跌、风险报告「避险」/ 威胁指数（只管个股新仓）")
    if timing:
        mrow = next((x for x in rows if x.get("m") == timing), None)
        k = mrow["need"] if mrow else 5
        up = key == "BR:BD"
        notes.append(f"翻转那天：{IDX_NAME[timing]} 第 {k} 天收在线{'上' if up else '下'}（{CLOSE_JST[timing]}）"
                     "→ 交易日 07:40 执行器决策 → 09:00 开盘寄付成行卖出（模拟账户按开盘价成交）")
        s = _stats(timing)
        lag = s.get("bull_lag_med" if up else "bear_lag_med")
        if lag is not None:
            notes.append(f"这条线翻得晚：2006 年以来（样本外）{IDX_NAME[timing]} 从{'低点' if up else '高点'}起中位数约 "
                         f"{float(lag):.0f} 个交易日才判{'牛' if up else '熊'}；误报 {int(s.get('false_alarms') or 0)} 次（卖了又买回）")
    notes.append(f"规则目标和实际持有差不超过权益的 {band:g}% 就不动：零星现金、价格波动不会让它来回买卖")
    notes.append("你自己点「卖出全部 / 调仓…」、改闲置资金比例，或手动买入 / 加仓个股钱不够时也会卖它（不算自动）；HALT 时什么单都不下")
    asof = next((x.get("asof") for x in rows if x.get("asof")), None) or st.get("last_date")
    hot = any(x.get("hot") for x in rows) or any(x.get("tone") == "bad" for x in tiles)
    return {"t": t, "name": IC.NAMES.get(t, t), "mode": mode, "label": label, "key": key, "asof": asof, "asof_md": _md(asof),
            "tiles": tiles, "rows": rows, "never": "不会因为：" + "；".join(never), "notes": notes, "hot": hot}


def lines(info: dict | None) -> list[str]:
    """文字版（日志 / 测试）：第一行三格「标签 值（补充）」，之后每行「标签：内容〔chips〕（补充）」，最后「不会因为」。"""
    if not info:
        return []
    out = []
    if info.get("tiles"):
        out.append(" · ".join(f"{x['label']} {x['value']}" + (f"（{x['sub']}）" if x.get("sub") else "") for x in info["tiles"]))
    for r in info["rows"]:
        chips = "、".join(c["text"] for c in r.get("chips") or [])
        out.append(f"{r['k']}：{r['text']}" + (f"〔{chips}〕" if chips else "") + (f"（{r['sub']}）" if r.get("sub") else ""))
    out.append(info["never"])
    return out


__all__ = ["IDX_NAME", "build", "market_row", "market_tiles", "partial_row", "lines"]
