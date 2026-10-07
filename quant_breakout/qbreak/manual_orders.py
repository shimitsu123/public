"""manual_orders.py — 手动指令：页面上点「卖出 / 减仓 / 调闲置资金比例」→ 执行器在下一次能下寄付单的运行里下单
（2026-10-06 用户：「当持仓的时候可以在画面上点击卖出后 第二天或者当天就可以在立花自动交易 可以手动调节当前持仓股票百分比」）。

页面（qbreak/panel.py，只在本机 127.0.0.1）或命令行（run.py manual …）只把「指令」追加到数据目录的
manual/requests_<账本>.jsonl；真正下单的永远是执行器（qbreak/live_unified.py）：它在下一次能下寄付单的运行里把指令变成单，
经过与平时完全相同的闸门（HALT / ARM / 持仓核对 / 单笔上限 / 时间窗口）。所以手动卖出不会让第二天的持仓核对停下
（直接在立花网站上手动买卖才会）。

指令（kind）：
  sell     卖出一只个股的全部（寄付成行）；之后 block_days 个交易日不自动买回（默认 20；0 = 不限制；-1 = 一直不买回，直到 unblock）
  trim     把一只个股减到总权益的 pct %（按单元向下取整；只能减）；减到 0 股等于卖出全部（命令行 run.py manual trim 照旧可用）
  adjust   把一只个股调到目标持仓（2026-10-06 用户：「也可以调节现在个股的持仓和金额」）：unit = shares（股数）/ yen（金额 円）/
           pct（占总权益 %），value = 目标值；按执行器决策时的收盘与权益换成股数（单元向下取整）。
             目标 < 现在 → 减仓（与 trim 同一条路：寄付成行卖出多出来的股数；0 = 全部卖出）
             目标 > 现在 → 加仓（寄付指値，限价 = 决策日收盘 ×(1+跳空上限 3%)，与新仓同一条规则）。加仓的闸门（任何一道不过 → 不加）：
               只在「新收盘的决策」里做（统一决策先给它留钱，现金不够就同一个开盘先卖核心 ETF 补；同一决策的补单不做加仓 →
               等下一次决策）；加到最多单只占总权益 max_position_pct（34%）；资格检查 / 立花能不能买 / 手动卖出后不买回、
               决算前不进场、规则现在不开新仓（宏观 / 个股判断层倍数 0）的票不加；开盘比决策日收盘高 3% 以上 / ストップ高 → 不买；
               只做一次（没买成 → 这条指令结束，要加再点一次）。
             加仓后：成本 = 股数加权平均；止损 / 峰值 / 持有天数 / 跟踪止损是否已启动不变（离场规则照旧，不放宽）。
           「赢家加仓」研究没有通过（规则不会自己加仓）：加仓只是你的手动决定，会让账户和云端模拟盘不一致。
  buy      手动买入一只还没拿的个股（2026-10-06 用户：「根据趋势等等建议的股票也要加到里面 可以一键买的」；页面「建议的股票」=
           规则的候选：今天收盘出了买入信号 / 快要出信号 / 观察中）：unit = rule（按规则的仓位 = 权益 × position_pct × 新仓倍数，
           默认）/ shares / yen / pct，value = 目标。和规则的新仓走同一条路（统一决策的 plan）：
             只在「新收盘的决策」里做（统一决策先给它留钱、占一个名额；现金不够就同一个开盘先卖核心 ETF）；寄付指値 = 决策日收盘
             ×(1+跳空上限 3%)；开盘高于限价 / ストップ高 / 名额满 → 不买；只做一次（没买成 → 这条指令结束）。
             闸门（任何一道不过 → 不买）：资格检查 / 立花能不能买 / 手动卖出后不买回 / 决算前 / 新仓倍数 0（与规则的新仓相同）、
             已经持有（要加用 adjust）、核心 ETF（用 core）、个股名额满（max_positions 4 只）、单只上限 max_position_pct（34%）。
             买入后与规则的持仓完全一样：止损按 ATR、跟踪止损 / 离场信号照常。
           还没触发买入信号的票（快要出信号 / 观察中）规则不会买：手动买入是你自己的决定（没有回测验证），会让账户和云端模拟盘不一致。
  core     闲置资金（核心 ETF）比例：规则算出的目标额 × pct %（100 = 照规则；0 = 卖出、留现金）。一直有效，直到再改
  unblock  解除「不自动买回」
  cancel   撤回一条指令（target = 指令 id）：还没交给执行器的 → 马上撤；已经交给执行器的 → 之后不再重下
           （已经发到交易所的那一笔要撤，请在立花网站 / App 上撤；没撤的话开盘照常成交）
什么时候成交：执行器只在「成交日 08:55 之前」接手（寄付 = 开盘集合竞价；不在盘中下单）——
  卖出 / 减仓：成交日 08:55 之前点的 → 当天开盘卖（执行器 07:40 的运行；页面在 07:45〜08:45 之间点会马上叫执行器跑一次）；
  之后点的 → 下一个交易日开盘卖。加仓 / 买入：下一次「新收盘的决策」（每个交易日早上 07:40 的运行）之后的开盘 ——
  那天的早上运行之前点的 → 当天开盘；之后点的 → 下一个交易日开盘（add_window）。闲置资金比例从下一次决策起生效。
卖出所得：和规则卖出一样 —— 下一次决策里有新信号就买新票，没有就进闲置资金 ETF；想留现金就把闲置资金比例调低。
状态：pending 等执行器 → placed 已交给执行器（下一开盘的单）→ done 完成；rejected（理由）/ cancelled / superseded（规则也要卖）。
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re

from . import paths
from .calendar_jp import is_trading_day, next_trading_day, now_jst, prev_trading_day

KINDS = ("sell", "trim", "adjust", "buy", "core", "unblock", "cancel")
POS_KINDS = ("sell", "trim", "adjust")  # 针对一只持仓的指令
ORDER_KINDS = POS_KINDS + ("buy",)      # 会变成单的指令（同一只票同时只能有一条没处理完的）
UNITS = {"shares": "股", "yen": "円", "pct": "%"}
BUY_UNITS = {"rule": "按规则的仓位", **UNITS}
BLOCK_DEFAULT = 20                      # 手动卖出后多少个交易日不自动买回（默认）
BLOCK_MAX = 250
CAP_PCT = 34.0                          # 加仓上限：单只个股占总权益 %（执行器写进账本的 manual.cap_pct = 引擎的 max_position_pct；没有就用这个）
MAX_POS = 4                             # 个股名额（执行器写进账本的 manual.max_positions = 引擎的 max_positions；没有就用这个）
LOT = 100                               # 页面 / 命令行估算用的单元（东证个股 100 股；执行器按引擎的单元）
CUTOFF = dt.time(8, 55)                 # 寄付注文的最后时刻（与 live_unified.MORNING_CUTOFF 相同）
LABEL = {"sell": "卖出全部", "trim": "减仓", "adjust": "调整持仓", "buy": "买入", "core": "闲置资金比例", "unblock": "解除不买回",
         "cancel": "撤回指令"}
STATUS = {"pending": "等执行器", "placed": "已交给执行器", "done": "完成", "rejected": "没执行", "cancelled": "已撤回",
          "superseded": "规则也要卖（按规则的单）"}
REASON_TEXT = {"manual": "手动卖出", "manual_trim": "手动减仓", "manual_add": "手动加仓", "manual_buy": "手动买入"}
ACTIVE = ("pending", "placed")
_TICKER = re.compile(r"^[0-9][0-9A-Z]{3}\.T$")


def requests_path(tag: str):
    """指令文件（只追加）：<数据目录>/manual/requests_<账本标签>.jsonl —— 页面与命令行写，执行器读。"""
    return paths.sub("manual") / f"requests_{tag}.jsonl"


def normalize(req: dict) -> dict:
    """检查指令的格式（不看账本）：类型、代码、比例、天数。不合格 → ValueError（中文说明）。"""
    kind = str(req.get("kind") or "").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"不认识的指令 {kind!r}（可用：{'、'.join(KINDS)}）")
    out = {"kind": kind}
    if kind in ("sell", "trim", "adjust", "buy", "unblock"):
        t = str(req.get("ticker") or "").strip().upper()
        if t and "." not in t:
            t += ".T"
        if not _TICKER.match(t):
            raise ValueError(f"代码 {t or '—'} 不对（东证 4 位代码，例 7203 或 7203.T）")
        out["ticker"] = t
    if kind in ("trim", "core"):
        try:
            pct = float(req.get("pct"))
        except (TypeError, ValueError):
            raise ValueError("要给比例（%）") from None
        if not math.isfinite(pct) or not 0 <= pct <= 100:
            raise ValueError("比例要在 0〜100% 之间")
        out["pct"] = round(pct, 2)
    if kind == "adjust" or kind == "buy":
        unit = str(req.get("unit") or ("rule" if kind == "buy" else "")).strip().lower()
        if unit not in (BUY_UNITS if kind == "buy" else UNITS):
            raise ValueError("调整要给单位：shares（股数）/ yen（金额 円）/ pct（占总权益 %）" if kind == "adjust" else
                             "买入的单位：rule（按规则的仓位，默认）/ shares（股数）/ yen（金额 円）/ pct（占总权益 %）")
        out["unit"] = unit
        if unit != "rule":
            out["value"] = _target_value(unit, req.get("value"), positive=kind == "buy")
    if kind == "sell":
        bd = req.get("block_days", BLOCK_DEFAULT)
        try:
            bd = int(bd)
        except (TypeError, ValueError):
            raise ValueError("不买回的天数要是整数（0 = 不限制，-1 = 一直）") from None
        if not -1 <= bd <= BLOCK_MAX:
            raise ValueError(f"不买回的天数要在 -1〜{BLOCK_MAX} 之间")
        out["block_days"] = bd
    if kind == "cancel":
        tg = str(req.get("target") or "").strip()
        if not re.fullmatch(r"M[0-9A-Za-z\-]{6,60}", tg):
            raise ValueError("撤回要给指令 id（例 M20261006-081500-sell-7203）")
        out["target"] = tg
    note = " ".join(str(req.get("note") or "").split())
    if note:
        out["note"] = note[:200]
    out["source"] = re.sub(r"[^0-9A-Za-z_\-]", "", str(req.get("source") or "cli"))[:20] or "cli"
    return out


def _target_value(unit: str, raw, positive: bool = False):
    """调整 / 买入的目标值：shares → 整数股；yen → 整数円；pct → 0〜100（两位小数）。positive：买入要 > 0。"""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ValueError("要给目标值（股数 / 金额 円 / 占总权益 %）") from None
    if not math.isfinite(v) or v < 0:
        raise ValueError("目标值不能是负数")
    if positive and v <= 0:
        raise ValueError("买入的目标要大于 0（股数 / 金额 円 / 占总权益 %）")
    if unit == "shares":
        if v != int(v) or v > 10_000_000:
            raise ValueError("目标股数要是 0〜10,000,000 的整数")
        return int(v)
    if unit == "yen":
        if v > 1e10:
            raise ValueError("目标金额太大")
        return int(round(v))
    if v > 100:
        raise ValueError("比例要在 0〜100% 之间")
    return round(v, 2)


def append(tag: str, req: dict, clock=None) -> dict:
    """追加一条指令（先 normalize）；返回带 id / at 的记录。一行一条 JSON，O_APPEND 写入（同一台机器上多个写的人也不会互相覆盖）。"""
    rec = normalize(req)
    now = (clock or now_jst)()
    rec["at"] = now.isoformat(timespec="seconds")
    rec["id"] = f"M{now:%Y%m%d-%H%M%S}-{rec['kind']}" + (f"-{rec['ticker'].split('.')[0]}" if rec.get("ticker") else "")
    have = {r.get("id") for r in read_all(tag)}
    base, n = rec["id"], 2
    while rec["id"] in have:                                 # 同一秒的第二条
        rec["id"] = f"{base}-{n}"
        n += 1
    line = (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(requests_path(tag), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
    return rec


def read_all(tag: str) -> list[dict]:
    """全部指令（按写入顺序）；坏行跳过。"""
    p = requests_path(tag)
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("id") and r.get("kind") in KINDS:
            out.append(r)
    return out


def unseen(tag: str, book: dict | None) -> list[dict]:
    """指令文件里执行器还没读进账本的指令（页面显示「等执行器读」用）。"""
    have = set(((book or {}).get("manual") or {}).get("items") or {})
    return [r for r in read_all(tag) if r["id"] not in have]


def add_trading_days(d: dt.date, n: int) -> dt.date:
    x = d
    for _ in range(max(0, int(n))):
        x = next_trading_day(x)
    return x


def position_pct(state: dict) -> dict:
    """账本状态（dict）里每只个股占总权益的 %（按最近收盘 last_close；权益 = 历史最后一行）。"""
    hist = state.get("history") or []
    eq = float(hist[-1][1]) if hist else 0.0
    out = {}
    for t, p in (state.get("pos") or {}).items():
        px = float(p.get("last_close") or p.get("entry_px") or 0)
        out[t] = round(int(p.get("shares") or 0) * px / eq * 100, 2) if eq > 0 else None
    return out


def target_shares(unit: str, value, eq: float, px: float, lot: int = LOT) -> int:
    """调整的目标 → 股数（单元向下取整）：shares 直接用；yen = 金额 ÷ 价格；pct = 权益 × % ÷ 价格。"""
    v = float(value)
    if unit == "shares":
        raw = v
    elif px <= 0:
        return 0
    elif unit == "yen":
        raw = v / px
    else:
        raw = eq * v / 100 / px if eq > 0 else 0.0
    return max(0, int(math.floor(raw / lot + 1e-9)) * lot)


def fmt_target(r: dict) -> str:
    """调整 / 买入的目标值（带单位）：300 股 / ¥500,000 / 20% / 按规则的仓位。"""
    u, v = r.get("unit"), r.get("value")
    if u == "rule":
        return BUY_UNITS["rule"]
    if v is None:
        return "—"
    if u == "shares":
        return f"{int(v):,} 股"
    if u == "yen":
        return f"¥{float(v):,.0f}"
    return f"{float(v):g}%"


def describe(r: dict) -> str:
    """一条指令的一句话：卖出全部 7203.T / 减仓 7203.T 10% / 调整持仓 7203.T → 300 股 / 买入 7203.T（按规则的仓位）/
    闲置资金比例 80%。"""
    k = r.get("kind")
    s = LABEL.get(k, str(k)) + (f" {r['ticker']}" if r.get("ticker") else "")
    if k == "buy" and r.get("unit", "rule") == "rule":
        s += f"（{BUY_UNITS['rule']}）"
    elif k in ("adjust", "buy"):
        s += f" → {fmt_target(r)}"
    elif r.get("pct") is not None:
        s += f" {float(r['pct']):g}%"
    return s


def cap_text(cur: int, px: float, eq: float, cap_pct: float, lot: int = LOT) -> str:
    """加不了仓的理由（单只上限）：已经到上限，或者再加 1 个单元就超过上限。"""
    now = cur * px / eq * 100 if eq > 0 else 0.0
    if now >= cap_pct:
        return f"现在约占权益 {now:.1f}%，已经到单只上限 {cap_pct:g}%（规则的 max_position_pct）：不能再加"
    nxt = (cur + lot) * px / eq * 100 if eq > 0 else 0.0
    return (f"现在约占权益 {now:.1f}%；再加 1 个单元（{lot:,} 股，约 ¥{lot * px:,.0f}）就约占 {nxt:.1f}%，"
            f"超过单只上限 {cap_pct:g}%（规则的 max_position_pct）：不能再加")


def adjust_plan(rec: dict, state: dict, cap_pct: float = CAP_PCT, lot: int = LOT) -> dict:
    """按账本里的最近收盘与权益估算一条调整（页面 / 命令行的预览与检查；执行器下单前按决策时的收盘再算一次）：
    {"cur", "want"（目标换成的股数）, "target"（加仓时按上限截过）, "delta"（+ 买 / − 卖）, "px", "eq", "cur_pct", "new_pct",
     "capped"（被单只上限截了）, "cap_pct"}。"""
    pos = (state.get("pos") or {}).get(rec.get("ticker")) or {}
    hist = state.get("history") or []
    eq = float(hist[-1][1]) if hist else 0.0
    px = float(pos.get("last_close") or pos.get("entry_px") or 0)
    cur = int(pos.get("shares") or 0)
    want = target_shares(rec["unit"], rec["value"], eq, px, lot)
    tgt, capped = want, False
    if want > cur and eq > 0 and px > 0:
        cap = int(math.floor(eq * cap_pct / 100 / px / lot + 1e-9)) * lot
        if want > cap:
            tgt, capped = max(cap, cur), True
    pct = (lambda n: round(n * px / eq * 100, 2) if eq > 0 and px > 0 else None)
    return {"cur": cur, "want": want, "target": tgt, "delta": tgt - cur, "px": px, "eq": eq, "cur_pct": pct(cur),
            "new_pct": pct(tgt), "capped": capped, "cap_pct": cap_pct}


def _live(items: dict, waiting: list[dict], kinds) -> list[dict]:
    """还没处理完的指令（账本里 pending / placed 且没在撤回 + 指令文件里执行器还没读、也没被撤回的）。"""
    out = [it for it in items.values() if it.get("kind") in kinds and it.get("status") in ACTIVE and not it.get("cancel_req")]
    return out + [r for r in waiting if r.get("kind") in kinds
                  and not any(c.get("kind") == "cancel" and c.get("target") == r["id"] for c in waiting)]


def _to_zero(r: dict) -> bool:
    """卖出全部，或减仓 / 调整到 0（这只票的名额在同一次决策里空出来）。"""
    k = r.get("kind")
    return k == "sell" or (k == "trim" and float(r.get("pct") or 0) <= 0) or (
        k == "adjust" and r.get("unit") in UNITS and float(r.get("value") or 0) <= 0)


def core_tickers(book: dict) -> set:
    """核心 ETF（不能手动买，用闲置资金比例调）：执行器写进账本的 manual.core + 拿着的 + 闲置资金各方式里的 ETF。"""
    st = (book or {}).get("state") or {}
    out = set(((book or {}).get("manual") or {}).get("core") or []) | set(st.get("core_units") or {})
    try:
        from .idle_cash import NAMES
        out |= set(NAMES)
    except Exception:                                       # noqa: BLE001
        pass
    return out


def slots(book: dict, tag: str | None = None) -> dict:
    """个股名额的估算（页面 / 命令行；执行器在决策时按当时的持仓再算）：下一次决策时还拿着的（不算排在开盘卖出、
    有卖出全部 / 减到 0 指令的）+ 已经排定的买入（规则的计划 + 手动买入指令）→ {"held", "buys", "used", "max", "free"}。"""
    st = (book or {}).get("state") or {}
    man = (book or {}).get("manual") or {}
    waiting = unseen(tag, book) if tag else []
    live = _live(man.get("items") or {}, waiting, ORDER_KINDS)
    pos, pend = st.get("pos") or {}, st.get("pending_exit") or {}
    going = {r.get("ticker") for r in live if _to_zero(r)}
    held = [t for t in pos if t not in pend and t not in going]
    buys = ({t for t in (st.get("plan") or {}) if t not in pos}
            | {r.get("ticker") for r in live if r.get("kind") == "buy"})
    mx = int(man.get("max_positions") or MAX_POS)
    return {"held": len(held), "buys": len(buys), "used": len(held) + len(buys), "max": mx,
            "free": max(0, mx - len(held) - len(buys))}


def check(rec: dict, book: dict, tag: str | None = None, sm: dict | None = None) -> str | None:
    """下指令时对着执行器账本看一眼（页面 / 命令行用；执行器下单前还会按最新的收盘再查一次）：不行 → 理由；行 → None。
    tag：账本标签（给了就连指令文件里执行器还没读的指令一起看，避免同一只票点两次）。
    sm：执行器的汇总（给了就看「建议的股票」里这只票的资格检查：被挡的不让写）。"""
    st = (book or {}).get("state") or {}
    waiting = unseen(tag, book) if tag else []
    pos = st.get("pos") or {}
    man = (book or {}).get("manual") or {}
    items = man.get("items") or {}
    k = rec["kind"]
    t = rec.get("ticker")
    if k in ORDER_KINDS:
        if k == "buy":
            if t in pos:
                return f"{t} 已经持有：要加仓用「调整持仓」"
            if t in core_tickers(book):
                return f"{t} 是核心 ETF：不能手动买（用「闲置资金比例」调）"
            if t in (st.get("plan") or {}):
                return f"{t} 已经排在下一开盘买入（规则的买入信号），不用再点"
        else:
            if t not in pos:
                return f"执行器的账本里没有 {t} 这只持仓（核心 ETF 用「闲置资金比例」调）"
            why = (st.get("pending_exit") or {}).get(t)
            if why:
                return f"{t} 已经排在下一开盘卖出全部（{REASON_TEXT.get(why, why)}），不用再点"
        act = [r for r in _live(items, waiting, ORDER_KINDS) if r.get("ticker") == t]
        if act:
            return f"{t} 已经有一条没处理完的手动指令（{act[-1].get('id')}）：先撤回它，或等它完成"
    if k == "buy":
        row = next((r for r in ((sm or {}).get("suggest") or {}).get("rows") or [] if r.get("ticker") == t), None)
        hard = ((row or {}).get("buy") or {}).get("block")
        if hard:
            return f"{t} 不能买：{hard}"
        s = slots(book, tag)
        if s["free"] <= 0:
            return (f"个股名额已满：拿着 {s['held']} 只 + 排定买入 {s['buys']} 只 = {s['used']} 只（上限 {s['max']} 只）："
                    "要买先卖出一只（卖出 / 减到 0 的指令在同一次决策里先处理，再处理买入）")
    if k == "trim":
        cur = position_pct(st).get(t)
        if cur is not None and rec["pct"] >= cur:
            return f"{t} 现在约占权益 {cur:.1f}%，目标 {rec['pct']:g}% 不低于现在：减仓只能减不能加（要加用「调整持仓」）"
    if k == "adjust":
        a = adjust_plan(rec, st, float(man.get("cap_pct") or CAP_PCT))
        if a["px"] <= 0 or a["eq"] <= 0:
            return f"账本里没有 {t} 的收盘价 / 总权益（执行器跑过一次之后再调）"
        if a["want"] == a["cur"]:
            return (f"{t} 现在 {a['cur']:,} 股；目标 {fmt_target(rec)} 按最近收盘 ¥{a['px']:,.0f} 换算也是 {a['want']:,} 股"
                    f"（{LOT} 股单元向下取整）：不用调")
        if a["want"] > a["cur"] and a["delta"] <= 0:
            return f"{t} {cap_text(a['cur'], a['px'], a['eq'], a['cap_pct'], LOT)}"
    if k == "unblock" and t not in (man.get("blocks") or {}):
        return f"{t} 没有「不自动买回」的设定"
    if k == "cancel":
        it = items.get(rec["target"])
        if it is None:
            if any(r["id"] == rec["target"] for r in waiting):
                return None
            return f"没有指令 {rec['target']}"
        if it.get("status") not in ACTIVE:
            return f"指令 {rec['target']} 已经是「{STATUS.get(it.get('status'), it.get('status'))}」，撤不了"
        if it.get("cancel_req"):
            return f"指令 {rec['target']} 已经在撤回中"
    return None


def next_window(now: dt.datetime) -> tuple[dt.date, bool]:
    """现在点下去，最早哪个交易日的开盘执行：(日期, 是不是今天)。成交日 08:55 之前 → 当天；之后 → 下一个交易日。"""
    d = now.date()
    if is_trading_day(d) and now.time() < CUTOFF:
        return d, True
    return next_trading_day(d), False


def add_window(now: dt.datetime, last_date: str | None) -> tuple[dt.date, bool]:
    """加仓最早哪个交易日的开盘买：(日期, 是不是今天)。加仓只在「新收盘的决策」里做：next_window 的那个开盘的决策
    （它前一个交易日的收盘）执行器还没做（账本的决策日更早）→ 那个开盘；已经做了 → 再下一个交易日。"""
    d, today = next_window(now)
    if last_date and str(last_date) >= prev_trading_day(d).isoformat():
        return next_trading_day(d), False
    return d, today


def due(tag: str, book: dict | None, now: dt.datetime | None = None) -> bool:
    """今天开盘之前还来得及（交易日、08:55 之前）、而且有要变成单的手动指令（还没读的卖出 / 减仓 / 调整 / 撤回，或读了还在等的；
    等下一次决策的加仓不算）→ 早上的运行已经完成时，重试（08:35 / 页面）要再跑一次，把它加进今天开盘的单。"""
    now = now or now_jst()
    if not is_trading_day(now.date()) or now.time() >= CUTOFF:
        return False
    if any(r["kind"] in POS_KINDS + ("cancel",) for r in unseen(tag, book)):
        return True
    items = ((book or {}).get("manual") or {}).get("items") or {}
    return any((it.get("status") == "pending" and it.get("kind") in POS_KINDS and not it.get("wait"))
               or (it.get("status") == "placed" and it.get("cancel_req")) for it in items.values())


class Manual:
    """执行器里的手动指令：读指令文件 → 在下一次能下寄付单的运行里变成单 → 成交后记完成。状态都在执行器账本的 book["manual"]。"""

    def __init__(self, book: dict, tag: str, clock=None):
        self.book, self.tag, self.clock = book, tag, clock or now_jst
        m = book.setdefault("manual", {})
        m.setdefault("items", {})
        m.setdefault("blocks", {})
        m.setdefault("trims", {})
        m.setdefault("adds", {})
        m.setdefault("buys", {})
        m.setdefault("core_pct", 100.0)
        m["tag"] = tag
        self.m = m

    # ── 设定 ──
    @property
    def core_pct(self) -> float:
        return float(self.m.get("core_pct", 100.0))

    def block_reason(self, t: str, day) -> str | None:
        """t 在 day（决策用的 K 线日）还在「手动卖出后不自动买回」期内 → 理由。"""
        b = (self.m.get("blocks") or {}).get(t)
        if not b:
            return None
        until = b.get("until")
        d = day.date() if hasattr(day, "date") else day
        if until is None or str(d) <= str(until):
            return f"手动卖出后不自动买回（{'一直，直到解除' if until is None else f'到 {until}'}）"
        return None

    def _set_block(self, t: str, days: int, decided: dt.date, rid: str) -> None:
        if days == 0:
            return
        until = None if days < 0 else add_trading_days(decided, days).isoformat()
        self.m["blocks"][t] = {"until": until, "since": decided.isoformat(), "id": rid}

    def cancelling(self, t: str) -> bool:
        """t 有撤回中的手动指令（对账之后就撤）。"""
        return any(it.get("cancel_req") for it in self._active_for(t, ORDER_KINDS))

    def _active_for(self, t: str, kinds=POS_KINDS) -> list[dict]:
        return [it for it in self.m["items"].values()
                if it.get("ticker") == t and it.get("kind") in kinds and it.get("status") == "placed"]

    # ── 读指令 ──
    def ingest(self) -> list[tuple[str, str]]:
        """新指令 → items（pending）；core / unblock 当场生效；cancel：等执行器的马上撤，已交给执行器的记下「撤回中」
        （settle 在对账之后处理）。返回 [(级别, 说明)]。"""
        msgs = []
        items = self.m["items"]
        for r in read_all(self.tag):
            if r["id"] in items:
                continue
            it = {**r, "status": "pending"}
            items[r["id"]] = it
            k = r["kind"]
            if k == "core":
                self.m["core_pct"] = float(r["pct"])
                it.update(status="done", msg=f"闲置资金比例设为 {r['pct']:g}%（规则的目标额 × {r['pct']:g}%），从下一次决策起生效")
            elif k == "unblock":
                gone = self.m["blocks"].pop(r["ticker"], None)
                it.update(status="done" if gone else "rejected",
                          msg=f"{r['ticker']} 解除「不自动买回」" if gone else f"{r['ticker']} 本来就没有「不自动买回」")
            elif k == "cancel":
                tg = items.get(r["target"])
                if tg is not None and tg.get("status") == "pending":
                    tg.update(status="cancelled", msg=f"已撤回（{r['id']}）")
                    tg.pop("wait", None)
                    it.update(status="done", msg=f"撤回 {r['target']}")
                elif tg is not None and tg.get("status") == "placed" and not tg.get("cancel_req"):
                    tg["cancel_req"] = r["id"]
                    it.update(status="done", msg=f"撤回 {r['target']}：之后不再重下（已经发到交易所的那一笔要撤，请在立花网站 / App 上撤）")
                else:
                    it.update(status="rejected", msg=f"{r['target']} 不是「等执行器 / 已交给执行器」的指令，撤不了")
            else:
                it["msg"] = "等执行器在下一次能下寄付单的运行里处理"
            msgs.append(("info", f"手动指令 {r['id']}：{describe(r)} → {it['msg']}"))
        return msgs

    def pending(self, kinds=POS_KINDS) -> list[dict]:
        return sorted((it for it in self.m["items"].values() if it.get("status") == "pending" and it.get("kind") in kinds),
                      key=lambda x: x.get("at", ""))

    def has_work(self) -> bool:
        """还有要变成单的手动指令（等执行器的 sell / trim / adjust / buy）或要处理的撤回。"""
        return bool(self.pending(ORDER_KINDS)) or any(it.get("cancel_req") and it.get("status") == "placed"
                                                     for it in self.m["items"].values())

    # ── 变成单 ──
    def apply(self, eng, i: int, fill_day: dt.date, halted: bool = False, deciding: bool = True) -> list[tuple[str, str]]:
        """第 i 根 K 线收盘后的决策之前（deciding = True）或同一决策补单之前（False）：等着的 sell / trim / adjust / buy → 执行器的单。
        补跑的旧 K 线（成交日已经过了）不处理；成交日 08:55 之后、HALT 生效时也不动（下一次运行再看）。
        加仓 / 买入只在 deciding（统一决策要先给它留钱、买入还占名额）；同一决策补单时等下一次决策。
        先处理卖出 / 减仓 / 调整，再处理买入（同一次决策里先卖出一只、空出的名额给买入）。返回 [(级别, 说明)]。"""
        todo = sorted(self.pending(ORDER_KINDS), key=lambda x: (x["kind"] == "buy", x.get("at", "")))
        if not todo:
            return []
        now = self.clock()
        if now.date() > fill_day:
            return []
        if now.date() == fill_day and now.time() >= CUTOFF:
            return [("info", f"手动指令 {len(todo)} 条：已过 {fill_day} 的 {CUTOFF:%H:%M}，寄付来不及 → 下一个交易日早上的运行处理")]
        if halted:
            return [("warn", f"手动指令 {len(todo)} 条没处理：HALT 生效中（解除之后的下一次运行处理）")]
        st, out = eng.st, []
        decided = eng.gidx[i].date()
        for it in todo:
            t = it["ticker"]
            ps = st.pos.get(t)
            rule = st.pending_exit.get(t)
            it.pop("wait", None)
            if it["kind"] == "buy":
                if ps is not None:
                    it.update(status="rejected", msg="已经持有（规则在之前的开盘买进了？）：要加仓用「调整持仓」")
                elif not deciding:
                    nxt = next_trading_day(fill_day)
                    it.update(wait=True, msg=f"买入要和统一决策一起算（占名额；钱不够时同一个开盘先卖核心 ETF）：{fill_day} 收盘后的决策"
                                             f"（{nxt} 早上 07:40 的运行）处理 → {nxt} 开盘买")
                else:
                    self._buy(eng, i, it, decided, fill_day)
                lvl = "warn" if it["status"] == "rejected" else "info"
                out.append((lvl, f"手动指令 {it['id']}：{t} {it['msg']}"))
                continue
            if ps is None:
                it.update(status="rejected", msg="执行器的账本里没有这只持仓（已经卖掉了？）")
            elif rule == "manual":
                it.update(status="rejected", msg="已经排在开盘卖出全部（之前的手动卖出），不用再点")
            elif rule:
                it.update(status="superseded", decided_on=str(decided), fill_day=str(fill_day),
                          msg=f"规则也要在 {fill_day} 开盘卖出全部（{rule}）：按规则的单卖")
                if it["kind"] == "sell":
                    self._set_block(t, int(it.get("block_days", BLOCK_DEFAULT)), decided, it["id"])
            elif t in self.m["trims"] or t in self.m["adds"]:
                it["msg"] = "同一只票的手动减仓 / 加仓还没成交完：等它成交后再处理"
                out.append(("info", f"手动指令 {it['id']}：{t} {it['msg']}"))
                continue
            elif it["kind"] == "adjust":
                self._adjust(eng, i, it, ps, decided, fill_day, deciding)
                if it["status"] == "pending":
                    out.append(("info", f"手动指令 {it['id']}：{t} {it['msg']}"))
                    continue
            else:
                self._place(eng, i, it, ps, decided, fill_day)
            out.append(("warn" if it["status"] == "rejected" else "info", f"手动指令 {it['id']}：{t} {it['msg']}"))
        return out

    @staticmethod
    def _numbers(eng, i: int, t: str) -> tuple[float, float, int]:
        """(第 i 天收盘后的总权益, t 的收盘, t 的单元)。"""
        return float(eng.equity(i)), float(eng._px_close(t, i)), (int(eng.lots[eng.col[t]]) if t in eng.col else LOT)

    def _place(self, eng, i: int, it: dict, ps, decided: dt.date, fill_day: dt.date, target: int | None = None) -> None:
        """卖出全部（sell）/ 减到 pct %（trim）/ 减到 target 股（adjust 的减仓方向）。"""
        t, st = it["ticker"], eng.st
        sell_all, n_sell = it["kind"] == "sell", None
        eq, px, lot = self._numbers(eng, i, t)
        if not sell_all:
            if target is None:
                target = int(math.floor(eq * float(it["pct"]) / 100 / px / lot)) * lot if px > 0 and eq > 0 else 0
            n_sell = int(ps.shares) - max(0, target)
            if n_sell <= 0:
                it.update(status="rejected", msg=f"现在 {ps.shares:,} 股约占权益 {ps.shares * px / eq * 100:.1f}%，"
                                                 f"不高于目标{(' ' + format(it['pct'], 'g') + '%') if it.get('pct') is not None else ''}：不用减")
                return
            sell_all = target <= 0
        if sell_all:
            st.pending_exit[t] = "manual"
            if it["kind"] == "sell":
                self._set_block(t, int(it.get("block_days", BLOCK_DEFAULT)), decided, it["id"])
            it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(ps.shares), side="SELL",
                      msg=f"{fill_day} 开盘寄付成行卖出全部 {ps.shares:,} 股")
        else:
            self.m["trims"][t] = {"id": it["id"], "shares": int(n_sell), "target": int(target), "decided_on": str(decided)}
            new_pct = target * px / eq * 100 if eq > 0 else 0.0
            it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(n_sell), side="SELL",
                      msg=f"{fill_day} 开盘寄付成行卖出 {n_sell:,} 股（{ps.shares:,} → {target:,} 股，约占权益 {new_pct:.1f}%）")

    def _adjust(self, eng, i: int, it: dict, ps, decided: dt.date, fill_day: dt.date, deciding: bool) -> None:
        """调整持仓：按第 i 天收盘与权益把目标换成股数 → 少于现在 → 减仓；多于现在 → 加仓（闸门见模块说明）；一样 → 不用调。"""
        t = it["ticker"]
        eq, px, lot = self._numbers(eng, i, t)
        cur = int(ps.shares)
        want = target_shares(it["unit"], it["value"], eq, px, lot)
        if want == cur:
            it.update(status="rejected", msg=f"现在 {cur:,} 股；目标 {fmt_target(it)} 按 {decided} 收盘 ¥{px:,.0f} 换算也是"
                                             f" {want:,} 股（{lot} 股单元向下取整）：不用调")
            return
        if want < cur:
            self._place(eng, i, it, ps, decided, fill_day, target=want)
            return
        if not deciding:
            nxt = next_trading_day(fill_day)
            it.update(wait=True, msg=f"加仓要和统一决策一起算（钱不够时同一个开盘先卖核心 ETF 补）：{fill_day} 收盘后的决策"
                                     f"（{nxt} 早上 07:40 的运行）处理 → {nxt} 开盘买")
            return
        self._add(eng, i, it, ps, decided, fill_day, want)

    def _add(self, eng, i: int, it: dict, ps, decided: dt.date, fill_day: dt.date, want: int) -> None:
        t, st, cfg = it["ticker"], eng.st, eng.cfg
        eq, px, lot = self._numbers(eng, i, t)
        cur = int(ps.shares)
        why = eng.entry_gate_fn(t, i) if eng.entry_gate_fn is not None else None
        if not why and eng.entry_block_fn is not None:
            why = eng.entry_block_fn(t, i)
        if not why and eng._entry_mult(t, i) <= 0:
            why = "规则现在不开新仓（宏观 / 个股判断层的新仓倍数是 0）"
        if why:
            it.update(status="rejected", decided_on=str(decided), msg=f"不加仓：{why}（卖出 / 减仓照常可以）")
            return
        if not (px > 0 and eq > 0):
            it.update(status="rejected", decided_on=str(decided), msg="没有收盘价 / 总权益，算不了加仓")
            return
        cap_pct = float(cfg.max_position_pct) * 100
        cap = int(math.floor(eq * float(cfg.max_position_pct) / px / lot + 1e-9)) * lot
        add = (min(want, cap) - cur) // lot * lot
        notes = []
        if want > cap:
            notes.append(f"目标超过单只上限 {cap_pct:g}%，截到 {cap:,} 股")
        if add <= 0:
            it.update(status="rejected", decided_on=str(decided), msg=f"现在 {cur:,} 股：{cap_text(cur, px, eq, cap_pct, lot)}")
            return
        room = eng.add_room(t, i)
        if room < add:
            notes.append(f"现金 + 核心 ETF 只够 {room:,} 股（{add:,} → {room:,}）")
            add = room
        if add <= 0:
            it.update(status="rejected", decided_on=str(decided), msg="现金 + 核心 ETF 全部卖出也不够买 1 个单元：不加")
            return
        gap = eng.ex["JP"].max_entry_gap_pct                # 执行器只做东证
        from .tick import round_to_tick
        lim = round_to_tick(px * (1 + gap / 100), t, "BUY")
        st.add_plan[t] = [px, int(add), str(decided), it["id"]]
        self.m["adds"][t] = {"id": it["id"], "shares": int(add), "target": cur + int(add), "decided_on": str(decided),
                             "limit": lim}
        it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(add), side="BUY", limit=lim,
                  msg=f"{fill_day} 开盘寄付指値买入 {add:,} 股（限价 ¥{lim:,g} = {decided} 收盘 ¥{px:,g} ×{1 + gap / 100:g}；"
                      f"{cur:,} → {cur + add:,} 股，约占权益 {(cur + add) * px / eq * 100:.1f}%）"
                      + (f"；{'；'.join(notes)}" if notes else "")
                      + "；钱不够时同一个开盘先卖核心 ETF；开盘高于限价 / ストップ高 → 不买（这条指令就结束）")

    def _buy(self, eng, i: int, it: dict, decided: dt.date, fill_day: dt.date) -> None:
        """手动买入（新开仓）：与规则的新仓同一套闸门（资格检查 / 决算前 / 新仓倍数 0 / 名额），按规则的仓位或目标定股数
        （单只上限 34%、现金 + 核心 ETF 能凑出的钱），放进统一决策的 plan（下一开盘寄付指値；统一决策先给它留钱）。"""
        t, st, cfg = it["ticker"], eng.st, eng.cfg

        def no(msg: str) -> None:
            it.update(status="rejected", decided_on=str(decided), msg=msg)
        j = eng.col.get(t)
        if t in eng.core_set:
            return no("核心 ETF 不能手动买（用「闲置资金比例」调）")
        if j is None or not eng.A.has[i, j]:
            return no(f"执行器没有 {t} 在 {decided} 的行情（不在股票池？停牌？）：不买")
        if t in st.plan:
            return no(f"已经排在 {fill_day} 开盘买入（规则的买入信号）：不用再点")
        why = eng.entry_gate_fn(t, i) if eng.entry_gate_fn is not None else None
        if not why and eng.entry_block_fn is not None:
            why = eng.entry_block_fn(t, i)
        em = float(eng._entry_mult(t, i))
        if not why and em <= 0:
            why = "规则现在不开新仓（宏观 / 判断层 / 关联搭配 C / TBF 的新仓倍数是 0）"
        if why:
            return no(f"不买：{why}")
        n_after = len(st.pos) - sum(1 for x in st.pending_exit if x in st.pos)
        if n_after + len(st.plan) >= cfg.max_positions:
            return no(f"个股名额已满：拿着 {n_after} 只" + (f" + 排定买入 {len(st.plan)} 只" if st.plan else "")
                      + f"（上限 {cfg.max_positions} 只）→ 不买（要买先卖出一只；卖出指令在同一次决策里先处理）")
        eq, px, lot = self._numbers(eng, i, t)
        if not (px > 0 and eq > 0):
            return no("没有收盘价 / 总权益，算不了买入")
        pxs = px * (1 + eng.slip["JP"])
        if it.get("unit", "rule") == "rule":                 # 与统一决策的新仓同一个算法：权益 × 25% × 新仓倍数（≤ 单只上限）
            budget = min(eq * cfg.position_pct * min(1.0, em), eq * cfg.max_position_pct)
            want = int(math.floor(budget / pxs / lot)) * lot
            basis = f"按规则的仓位（权益 ×{cfg.position_pct * 100:g}%" + (f" × 新仓倍数 {em:g}" if em < 1 else "") + "）"
        else:
            want = target_shares(it["unit"], it["value"], eq, px, lot)
            basis = f"目标 {fmt_target(it)}"
        cap_pct = float(cfg.max_position_pct) * 100
        cap = int(math.floor(eq * float(cfg.max_position_pct) / px / lot + 1e-9)) * lot
        notes = []
        if want > cap:
            notes.append(f"超过单只上限 {cap_pct:g}%，截到 {cap:,} 股")
            want = cap
        if want <= 0:
            return no(f"{basis}按 {decided} 收盘 ¥{px:,g} 不够买 1 个单元（{lot:,} 股 ≈ ¥{lot * px:,.0f}）：不买")
        room = eng.add_room(t, i)
        if room < want:
            notes.append(f"现金 + 核心 ETF 只够 {room:,} 股（{want:,} → {room:,}）")
            want = room
        if want <= 0:
            return no("现金 + 核心 ETF 全部卖出也不够买 1 个单元：不买")
        gap = eng.ex["JP"].max_entry_gap_pct
        from .tick import round_to_tick
        lim = round_to_tick(px * (1 + gap / 100), t, "BUY")
        st.plan[t] = [px, int(want), str(decided)]
        self.m["buys"][t] = {"id": it["id"], "shares": int(want), "decided_on": str(decided), "limit": lim}
        sig = bool(eng.A.entry[i, j])
        it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(want), side="BUY", limit=lim,
                  msg=f"{fill_day} 开盘寄付指値买入 {want:,} 股（限价 ¥{lim:,g} = {decided} 收盘 ¥{px:,g} ×{1 + gap / 100:g}；"
                      f"约 ¥{want * px:,.0f}，约占权益 {want * px / eq * 100:.1f}%；{basis}）"
                      + (f"；{'；'.join(notes)}" if notes else "")
                      + ("；规则今天也有这只的买入信号" if sig else "；★ 这只今天没有买入信号（规则不会买）：是你自己的决定")
                      + "；钱不够时同一个开盘先卖核心 ETF；开盘高于限价 / ストップ高 / 名额满 → 不买（这条指令就结束）；"
                        "买入后按规则的止损 / 离场")

    def trim_orders(self, st) -> list[tuple[str, int, str]]:
        """这次决策要下的减仓卖单 [(票, 股数, 指令 id)]：规则已经要全部卖的票不下（按规则的单）。"""
        out = []
        for t, x in list(self.m["trims"].items()):
            ps = st.pos.get(t)
            if ps is None:
                self.m["trims"].pop(t, None)
                continue
            if t in st.pending_exit:
                continue
            n = min(int(x["shares"]), int(ps.shares))
            if n > 0:
                out.append((t, n, x["id"]))
        return out

    # ── 成交 → 完成 ──
    def on_fill(self, ticker: str, reason: str, qty: int, px: float, bar: str, st, why: str = "") -> None:
        """执行器对账时每笔手动单（reason manual / manual_trim / manual_add / manual_buy）的结果（qty = 0：没成交；why = 单的说明）。"""
        fill = {"qty": int(qty), "px": round(float(px), 2)}
        if reason in ("manual_add", "manual_buy"):
            add = reason == "manual_add"
            x = self.m["adds" if add else "buys"].pop(ticker, None)
            if not x:
                return
            it = self.m["items"].get(x["id"]) or {}
            late = "；撤回来不及：交易所的单已经成交" if it.get("cancel_req") else ""
            done = "加仓完成" if add else "新仓；之后按规则的止损 / 离场"
            if qty <= 0 and it.get("cancel_req"):
                it.update(status="cancelled", done_on=bar, msg=f"已撤回（{it['cancel_req']}）：{bar} 没有买")
            elif qty <= 0:
                it.update(status="rejected", done_on=bar,
                          msg=f"{bar} 开盘没买到{('（' + why + '）') if why else ''} → 这次不{'加' if add else '买'}"
                              f"（只做一次；要{'加' if add else '买'}请再点一次）")
            elif qty < int(x["shares"]):
                it.update(status="done", done_on=bar, fill=fill,
                          msg=f"{bar} 买入 {qty:,} 股 @ ¥{px:,.2f}（计划 {int(x['shares']):,} 股，只成交一部分；剩下的不再下；{done}）{late}")
            else:
                it.update(status="done", done_on=bar, fill=fill, msg=f"{bar} 买入 {qty:,} 股 @ ¥{px:,.2f}（{done}）{late}")
            return
        if reason == "manual_trim":
            x = self.m["trims"].get(ticker)
            if not x:
                return
            it = self.m["items"].get(x["id"]) or {}
            if qty <= 0:
                it["msg"] = f"{bar} 开盘没成交（ストップ安等）→ 下一开盘再卖"
                return
            left = int(x["shares"]) - int(qty)
            if left > 0 and ticker in st.pos:
                x["shares"] = left                          # 部分成交：剩下的下一次再卖
                it["msg"] = f"{bar} 开盘卖出 {qty:,} 股 @ ¥{px:,.2f}，还差 {left:,} 股（下一开盘再卖）"
                return
            self.m["trims"].pop(ticker, None)
            it.update(status="done", done_on=bar, fill=fill, msg=f"{bar} 开盘卖出 {qty:,} 股 @ ¥{px:,.2f}（减仓完成）")
            return
        for it in self._active_for(ticker):
            if (self.m["trims"].get(ticker) or {}).get("id") == it["id"] or (self.m["adds"].get(ticker) or {}).get("id") == it["id"]:
                continue
            if ticker not in st.pos:
                it.update(status="done", done_on=bar, fill=fill, msg=f"{bar} 开盘卖出 {qty:,} 股 @ ¥{px:,.2f}（全部卖出完成）"
                          + ("；撤回来不及：交易所的单已经成交" if it.get("cancel_req") else ""))
            elif qty > 0:
                it["msg"] = f"{bar} 开盘只成交 {qty:,} 股 @ ¥{px:,.2f}，剩下的下一开盘再卖"
            else:
                it["msg"] = f"{bar} 开盘没成交（ストップ安等）→ 下一开盘再卖"

    def settle(self, st, sent: set | None = None, sent_add: set | None = None) -> list[tuple[str, str]]:
        """对账之后（或没有新交易日时下单之前）：撤回中的指令 → 交易所那边没有在途的单就撤（之后不再重下）；
        持仓已经没了的 → 完成；对账过了还没结果的加仓 → 结束；过期的「不买回」去掉；只留最近 200 条记录。
        sent / sent_add = 这次决策里已经发到交易所的手动卖单 / 买单（加仓、买入）的票。"""
        out, sent, sent_add = [], set(sent or ()), set(sent_add or ())
        for key, plan, what in (("adds", st.add_plan, "加"), ("buys", st.plan, "买")):
            for t, x in list(self.m[key].items()):           # 对账已经过了（决策日早于账本的决策日）、却没有成交记录的加仓 / 买入
                if st.last_date and str(x.get("decided_on") or "") < str(st.last_date) and t not in plan:
                    self.m[key].pop(t, None)
                    it = self.m["items"].get(x["id"]) or {}
                    if it.get("status") == "placed":
                        it.update(status="rejected", msg=f"这笔{'加仓' if what == '加' else '买入'}没有下出去 / 没有成交记录 → 结束"
                                                         f"（要{what}请再点一次）")
        for it in self.m["items"].values():
            if it.get("status") != "placed" or it.get("kind") not in ORDER_KINDS:
                continue
            t = it.get("ticker")
            if it["kind"] == "buy":                          # 手动买入：交易所那边还没有这笔单（没发出 / 留到开盘后）→ 撤
                if (self.m["buys"].get(t) or {}).get("id") != it["id"] or not it.get("cancel_req") or t in sent_add:
                    continue
                self.m["buys"].pop(t, None)
                st.plan.pop(t, None)
                it.update(status="cancelled", msg=f"已撤回（{it['cancel_req']}）：这笔买入不下")
                out.append(("info", f"手动指令 {it['id']}：{t} {it['msg']}"))
                continue
            mine_trim = (self.m["trims"].get(t) or {}).get("id") == it["id"]
            mine_add = (self.m["adds"].get(t) or {}).get("id") == it["id"]
            if mine_add:
                if not it.get("cancel_req") or t in sent_add:
                    continue
                self.m["adds"].pop(t, None)
                st.add_plan.pop(t, None)
                it.update(status="cancelled", msg=f"已撤回（{it['cancel_req']}）：这笔加仓不下")
                out.append(("info", f"手动指令 {it['id']}：{t} {it['msg']}"))
                continue
            if t not in st.pos:
                if mine_trim:
                    self.m["trims"].pop(t, None)
                it.setdefault("done_on", st.last_date)
                it["status"] = "done"
                if it.get("cancel_req"):
                    it["msg"] = "撤回来不及：已经卖出了"
                continue
            if not it.get("cancel_req") or t in sent:
                continue
            if it["kind"] == "sell" or not mine_trim:
                if st.pending_exit.get(t) == "manual":
                    st.pending_exit.pop(t)
                b = self.m["blocks"].get(t)
                if b and b.get("id") == it["id"]:
                    self.m["blocks"].pop(t)
            if mine_trim:
                self.m["trims"].pop(t, None)
            it.update(status="cancelled", msg=f"已撤回（{it['cancel_req']}）：之后不再下这笔卖单")
            out.append(("info", f"手动指令 {it['id']}：{t} {it['msg']}"))
        today = self.clock().date().isoformat()
        for t, b in list(self.m["blocks"].items()):
            if b.get("until") is not None and str(b["until"]) < today:
                self.m["blocks"].pop(t)
        items = self.m["items"]
        if len(items) > 200:
            for k in sorted(items, key=lambda x: items[x].get("at", ""))[:len(items) - 200]:
                if items[k].get("status") not in ACTIVE:
                    items.pop(k)
        return out

    # ── 汇报 ──
    def summary(self) -> dict:
        items = sorted(self.m["items"].values(), key=lambda x: x.get("at", ""), reverse=True)
        keep = ("id", "at", "kind", "ticker", "pct", "unit", "value", "block_days", "target", "status", "msg", "decided_on",
                "fill_day", "done_on", "fill", "shares", "side", "limit", "source", "note", "cancel_req", "wait")
        return {"core_pct": self.core_pct, "blocks": dict(self.m["blocks"]), "trims": dict(self.m["trims"]),
                "adds": dict(self.m["adds"]), "buys": dict(self.m["buys"]), "cap_pct": self.m.get("cap_pct"),
                "max_positions": self.m.get("max_positions"),
                "items": [{k: v for k, v in it.items() if k in keep} for it in items[:30]],
                "active": sum(1 for it in items if it.get("status") in ACTIVE)}


def active(sm: dict | None) -> bool:
    """有手动操作在影响账户（闲置资金比例不是 100%、有「不买回」、有没完成的指令、做过卖出 / 减仓 / 加仓 / 买入）→ 与云端模拟盘不同是预期的。"""
    sm = sm or {}
    return (float(sm.get("core_pct", 100.0)) != 100.0 or bool(sm.get("blocks")) or bool(sm.get("trims"))
            or bool(sm.get("adds")) or bool(sm.get("buys")) or bool(sm.get("active"))
            or any(it.get("status") == "done" and it.get("kind") in ORDER_KINDS for it in sm.get("items") or []))


def lines(sm: dict | None, today: str | None = None) -> list[str]:
    """日志 / 通知用：手动指令的几行（没有就空）。today = 这一天完成的也列出来。"""
    sm = sm or {}
    out = []
    if float(sm.get("core_pct", 100.0)) != 100.0:
        out.append(f"- 闲置资金比例：手动设为规则目标额的 {float(sm['core_pct']):g}%（页面上改回 100% 就照规则）")
    for t, b in (sm.get("blocks") or {}).items():
        out.append(f"- {t}：手动卖出后不自动买回（{'一直，直到解除' if b.get('until') is None else '到 ' + str(b['until'])}）")
    for it in sm.get("items") or []:
        if it.get("status") in ACTIVE or (today and str(it.get("done_on") or "") >= today) \
                or (today and str(it.get("at") or "")[:10] >= today):
            out.append(f"- 手动指令 {it.get('id')}：{describe(it)}"
                       f" → {STATUS.get(it.get('status'), it.get('status'))}：{it.get('msg') or ''}")
    return out


__all__ = ["KINDS", "POS_KINDS", "ORDER_KINDS", "UNITS", "BUY_UNITS", "BLOCK_DEFAULT", "CAP_PCT", "MAX_POS", "Manual", "append",
           "read_all", "unseen", "normalize", "check", "slots", "core_tickers", "next_window", "add_window", "due", "requests_path",
           "position_pct", "target_shares", "adjust_plan", "cap_text", "fmt_target", "describe", "active", "lines", "LABEL", "STATUS",
           "REASON_TEXT"]
