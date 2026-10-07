"""manual_orders.py — 手动指令：页面（qbreak/panel.py）或命令行（run.py manual）上点「卖出 / 调仓 / 买入 / 闲置资金比例」，
执行器（qbreak/live_unified.py）下单。页面只把指令追加到数据目录的 manual/requests_<账本>.jsonl；下单的永远是执行器，
闸门与平时相同（HALT / ARM / 持仓核对 / 单笔上限 / 资格检查），所以手动操作不会让第二天的持仓核对停下。

指令（kind）：
  sell     卖出一只个股的全部；之后 block_days 个交易日不自动买回（默认 20；0 = 不限制；-1 = 一直，直到 unblock）
  trim     把一只个股减到总权益的 pct %（命令行用；只能减）
  adjust   调仓（unit = shares 股数 / yen 金额 / pct 占总权益 %，value = 目标；单元向下取整）：少于现在 → 卖出多的部分；
           多于现在 → 加仓（只加已经持有的票；单只最多占总权益 34%；资格检查 / 立花能不能买 / 不买回 / 决算前 / 新仓倍数 0 的不加；
           只做一次）。加仓后成本按股数加权平均，止损 / 峰值 / 持有天数不变。
  buy      买入一只还没拿的个股（unit = rule 按规则的仓位〔默认〕/ shares / yen / pct）：与规则的新仓同一套闸门
           （占名额〔最多 4 只〕、不能买核心 ETF、单只上限 34%、资格检查 / 立花能不能买 / 不买回 / 决算前 / 新仓倍数 0）；只做一次；
           买入后与规则的持仓一样（止损按 ATR、规则离场）。
  core     闲置资金（核心 ETF）比例：规则的目标额 × pct %（100 = 照规则；0 = 留现金）。从下一次决策起一直有效
  unblock  解除「不自动买回」
  cancel   撤回一条还没下的指令（target = 指令 id）；已经发到交易所的单要在立花网站 / App 上撤
「赢家加仓」研究没有通过、没触发信号的票没有回测验证：加仓 / 买入都是用户自己的决定，会让账户和云端模拟盘不一致。

什么时候下单（2026-10-07 用户：「当天买入卖出的话在交易时间段就直接进行买入卖出 在交易时间之前的话就等交易时间的时候进行交易」）：
  盘中（09:00〜11:30、12:30〜15:25）点的 → 马上下单：面板叫执行器跑 --phase now（约 1〜3 分钟）；限价单按现价，
      买入的限价不超过决策日收盘 ×1.03（与寄付相同）；钱不够先卖核心 ETF（今天开盘有单的不动）。
  开盘前点的 → 今天开盘：07:40 的运行之前 → 那次运行一起下寄付单；之后、08:55 之前的卖出 → 重试加进今天的寄付单；
      其余 → 09:00 开盘后马上下（--phase now）。午休（11:30〜12:30）点的 → 12:30 后场开盘后。
  收盘后（15:25 起）/ 休市日点的 → 下一个交易日早上的运行（开盘的寄付单）。
  今天开盘已经有执行器的单的票（规则 / 手动），盘中不再下第二笔 → 明天早上的运行处理（明天开盘）。
状态：pending 等下单 → placed 已下单（盘中的单当场成交或挂着）→ done 完成（第二天早上对账时记进账本）；
      rejected 没执行（理由）/ cancelled 已撤回 / superseded 规则也要卖（按规则的单）。
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
SESSION = ((dt.time(9, 0), dt.time(11, 30)), (dt.time(12, 30), dt.time(15, 25)))   # 盘中马上下单的时间（前場 / 後場；15:25 起是收盘竞价）
RETRY_S = 600                           # 盘中没下成的指令（取不到现价等）：过多久再试
LABEL = {"sell": "卖出全部", "trim": "减仓", "adjust": "调仓", "buy": "买入", "core": "闲置资金比例", "unblock": "解除不买回",
         "cancel": "撤回指令"}
STATUS = {"pending": "等下单", "placed": "已下单", "done": "完成", "rejected": "没执行", "cancelled": "已撤回",
          "superseded": "按规则的单卖"}
REASON_TEXT = {"manual": "手动卖出", "manual_trim": "手动减仓", "manual_add": "手动加仓", "manual_buy": "手动买入",
               "manual_fund": "为手动买入先卖核心 ETF"}
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
    if kind == "core" and req.get("ticker"):              # 持有的核心 ETF 的卖出 / 调仓（换算成比例；票与目标口数只用来显示）
        t = str(req.get("ticker") or "").strip().upper()
        if "." not in t:
            t += ".T"
        if not _TICKER.match(t):
            raise ValueError(f"代码 {t} 不对（东证 4 位代码，例 1545 或 1545.T）")
        out["ticker"] = t
        try:
            tg = int(req.get("target", 0))
        except (TypeError, ValueError):
            raise ValueError("目标口数要是整数") from None
        if not 0 <= tg <= 10_000_000:
            raise ValueError("目标口数要在 0〜10,000,000 之间")
        out["target"] = tg
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
    if k == "core" and r.get("ticker"):
        tg = int(r.get("target") or 0)
        return (f"卖出全部 {r['ticker']}" if tg <= 0 else f"调仓 {r['ticker']} → 约 {tg:,} 口") + f"（闲置资金比例 {float(r['pct']):g}%）"
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
        return f"现在约占权益 {now:.1f}%，已经到单只上限 {cap_pct:g}%：不能再加"
    nxt = (cur + lot) * px / eq * 100 if eq > 0 else 0.0
    return f"现在约占权益 {now:.1f}%，再加 {lot:,} 股就约占 {nxt:.1f}%，超过单只上限 {cap_pct:g}%：不能再加"


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


def _exit_text(why: str) -> str:
    """卖出理由的中文（MACD 死叉 / 止损 / 手动卖出…；qbreak/holding_view.EXIT_TEXT）。"""
    try:
        from .holding_view import EXIT_TEXT
    except Exception:                                       # noqa: BLE001
        EXIT_TEXT = {}
    return EXIT_TEXT.get(str(why)) or REASON_TEXT.get(str(why)) or str(why)


def cancelled(waiting: list[dict]) -> set:
    """指令文件里执行器还没读的撤回指向的指令 id（页面：这些不再算「在处理」、不再给撤回按钮）。"""
    return {r.get("target") for r in waiting if r.get("kind") == "cancel"}


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


def core_info(book: dict | None, t: str) -> dict | None:
    """一只核心 ETF 的调仓用数字：{"cur" 现在口数, "u100" 规则目标（闲置资金比例 100% 时；最近一次决策算的）, "px", "lot", "eq",
    "pct" 现在的比例, "selling" 规则这次在卖它}；不是核心 ETF / 执行器还没算过 → None。"""
    st = (book or {}).get("state") or {}
    cr = (book or {}).get("core_rule") or {}
    if t not in core_tickers(book or {}) or t not in (cr.get("units100") or {}):
        return None
    hist = st.get("history") or []
    px = float((cr.get("px") or {}).get(t) or (st.get("core_last") or {}).get(t) or 0)
    plan = (st.get("core_plan") or {}).get(t) or []
    cur = int((st.get("core_units") or {}).get(t, 0))
    u100 = int((cr.get("units100") or {}).get(t, 0))
    return {"cur": cur, "u100": u100, "px": px, "lot": max(1, int((cr.get("lot") or {}).get(t) or 1)),
            "eq": float(hist[-1][1]) if hist else 0.0, "pct": float(((book or {}).get("manual") or {}).get("core_pct", 100.0)),
            "selling": u100 <= 0 or (len(plan) == 2 and plan[0] == "SELL" and int(plan[1]) >= cur > 0)}


def core_effects(book: dict | None, pct: float, skip: str | None = None) -> list[tuple[str, int, int]]:
    """闲置资金比例改成 pct 时，各只核心 ETF（skip 以外）现在的口数 → 新比例下的目标口数（只列会变的）：[(票, 现在, 目标)]。
    比例对全部核心 ETF 一起生效（规则同时拿两只以上时，调一只另一只也跟着变）。"""
    st = (book or {}).get("state") or {}
    cr = (book or {}).get("core_rule") or {}
    out = []
    for t, n100 in sorted((cr.get("units100") or {}).items()):
        cur, lot = int((st.get("core_units") or {}).get(t, 0)), max(1, int((cr.get("lot") or {}).get(t) or 1))
        tg = int(math.floor(int(n100) * float(pct) / 100 / lot + 1e-9)) * lot
        if t != skip and tg != cur and (cur > 0 or tg > 0):
            out.append((t, cur, tg))
    return out


def core_pct_for(tg: int, u100: int, lot: int) -> float:
    """目标口数 → 闲置资金比例（%，两位小数）：取「规则目标 × 比例」按单元向下取整后正好是 tg 的最小比例（直接四舍五入可能少一个单元）。"""
    if u100 <= 0:
        return 0.0
    p = math.ceil(tg / u100 * 10000 - 1e-9) / 100
    if int(math.floor(u100 * p / 100 / lot + 1e-9)) * lot != tg:
        p = round(tg / u100 * 100, 2)
    return p


def core_rec(rec: dict, book: dict | None) -> dict | None:
    """持有的核心 ETF 的卖出全部 / 减仓 / 调仓 → 「闲置资金比例」指令（规则每天把核心 ETF 调回「目标额 × 比例」，
    只改这一次的单留不住）。比例 = 目标口数 ÷ 规则目标（比例 100% 时的口数）；对全部核心 ETF 一起生效。
    不是核心 ETF → None；调不了 → ValueError（说明）。"""
    t, k = rec.get("ticker"), rec.get("kind")
    if k not in POS_KINDS or not t or t not in core_tickers(book or {}):
        return None
    c = core_info(book, t)
    if c is None or c["cur"] <= 0:
        raise ValueError(f"现在没有 {t}（或执行器还没算过它的目标额：下一次运行之后再调）")
    if c["selling"]:
        raise ValueError(f"规则这次在卖 {t}（熊市 / 换了 ETF）：开盘卖出，不用调")
    if c["px"] <= 0:
        raise ValueError(f"账本里没有 {t} 的收盘价（执行器跑过一次之后再调）")
    if k == "sell":
        tg = 0
    elif k == "trim":
        tg = int(math.floor(c["eq"] * float(rec["pct"]) / 100 / c["px"] / c["lot"] + 1e-9)) * c["lot"] if c["eq"] > 0 else 0
        if tg >= c["cur"]:
            raise ValueError(f"{t} 现在约占权益 {c['cur'] * c['px'] / c['eq'] * 100:.1f}%，目标 {float(rec['pct']):g}% 不低于现在："
                             "减仓只能减不能加（要加用「调仓」）")
    else:
        tg = target_shares(rec["unit"], rec["value"], c["eq"], c["px"], c["lot"])
    tg = min(tg, c["u100"])
    out = {"kind": "core", "pct": core_pct_for(tg, c["u100"], c["lot"]), "ticker": t, "target": tg,
           "source": rec.get("source") or "cli"}
    if rec.get("note"):
        out["note"] = rec["note"]
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
                return f"{t} 已经持有：要加仓用「调仓」"
            if t in core_tickers(book):
                return f"{t} 是核心 ETF：不能手动买（用「闲置资金比例」调）"
            if t in (st.get("plan") or {}):
                return f"{t} 已经排在开盘买入（规则的信号），不用再点"
        else:
            if t not in pos:
                return f"执行器的账本里没有 {t} 这只持仓（核心 ETF 用「闲置资金比例」调）"
            why = (st.get("pending_exit") or {}).get(t)
            if why:
                return f"{t} 已经在卖出全部（{_exit_text(why)}），不用再点"
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
            return (f"个股名额已满（拿着 {s['held']} 只 + 排定买入 {s['buys']} 只，上限 {s['max']} 只）：要买先卖出一只"
                    "（卖出先处理，再处理买入）")
    if k == "trim":
        cur = position_pct(st).get(t)
        if cur is not None and rec["pct"] >= cur:
            return f"{t} 现在约占权益 {cur:.1f}%，目标 {rec['pct']:g}% 不低于现在：减仓只能减不能加（要加用「调仓」）"
    if k == "adjust":
        a = adjust_plan(rec, st, float(man.get("cap_pct") or CAP_PCT))
        if a["px"] <= 0 or a["eq"] <= 0:
            return f"账本里没有 {t} 的收盘价 / 总权益（执行器跑过一次之后再调）"
        if a["want"] == a["cur"]:
            return f"{t} 现在 {a['cur']:,} 股，目标 {fmt_target(rec)} 换算也是 {a['want']:,} 股：不用调"
        if a["want"] > a["cur"] and a["delta"] <= 0:
            return f"{t} {cap_text(a['cur'], a['px'], a['eq'], a['cap_pct'], LOT)}"
    if k == "core":
        cur = float(man.get("core_pct", 100.0))
        late = [r for r in waiting if r.get("kind") == "core" and r["id"] not in cancelled(waiting)]
        if late:
            cur = float(late[-1]["pct"])
        if abs(float(rec["pct"]) - cur) < 0.005:
            return (f"{t} 换算成闲置资金比例还是 {cur:g}%：不用调" if t else f"闲置资金比例现在就是 {cur:g}%：不用改")
    if k == "unblock" and t not in (man.get("blocks") or {}):
        return f"{t} 没有「不自动买回」的设定"
    if k == "cancel":
        it = items.get(rec["target"])
        if it is None:
            if rec["target"] in cancelled(waiting):
                return f"指令 {rec['target']} 已经在撤回中"
            if any(r["id"] == rec["target"] for r in waiting):
                return None
            return f"没有指令 {rec['target']}"
        if it.get("status") not in ACTIVE:
            return f"指令 {rec['target']} 已经是「{status_text(it)}」，撤不了"
        if it.get("cancel_req"):
            return f"指令 {rec['target']} 已经在撤回中"
        if it.get("now") and it.get("status") == "placed":
            return NOW_NO_CANCEL
    return None


NOW_NO_CANCEL = "盘中的单已经发到交易所，撤不了（要撤在立花网站 / App 上撤）"
RULE_TEXT = "盘中点的马上下单；开盘前、午休点的等开盘；收盘后点的等下一个交易日开盘"


def timing(now: dt.datetime) -> tuple[str, dt.date]:
    """现在点下去什么时候下单：("now", 今天) 盘中 → 马上；("open", 今天) 开盘前 → 今天开盘；("lunch", 今天) 午休 → 12:30 后场开盘；
    ("next", 下一个交易日) 收盘后（15:25 起）/ 休市日 → 下一个交易日开盘。"""
    d, t = now.date(), now.time()
    if is_trading_day(d):
        if t < SESSION[0][0]:
            return "open", d
        if any(a <= t < b for a, b in SESSION):
            return "now", d
        if t < SESSION[1][0]:
            return "lunch", d
    return "next", next_trading_day(d)


def when_text(now: dt.datetime) -> str:
    """一句话：马上（盘中）/ 今天 09:00 开盘 / 12:30 后场开盘 / 10/08 开盘。"""
    mode, d = timing(now)
    return {"now": "马上（盘中）", "open": "今天 09:00 开盘", "lunch": "12:30 后场开盘"}.get(mode) or f"{d:%m/%d} 开盘"


def next_window(now: dt.datetime) -> tuple[dt.date, bool]:
    """现在点下去哪一天下单：(日期, 是不是今天)。交易日 15:25 之前 → 今天；之后 / 休市日 → 下一个交易日。"""
    mode, d = timing(now)
    return d, mode != "next"


def due(tag: str, book: dict | None, now: dt.datetime | None = None) -> bool:
    """今天开盘之前还来得及寄付（交易日、08:55 之前）、而且有要变成寄付单的手动指令（还没读的卖出 / 减仓 / 调仓 / 撤回，或读了还在等的；
    等 09:00 开盘的买入 / 加仓不算）→ 早上的运行已经完成时，重试（08:35 / 页面）要再跑一次，把它加进今天开盘的单。"""
    now = now or now_jst()
    if not is_trading_day(now.date()) or now.time() >= CUTOFF:
        return False
    if any(r["kind"] in POS_KINDS + ("cancel",) for r in unseen(tag, book)):
        return True
    items = ((book or {}).get("manual") or {}).get("items") or {}
    return any((it.get("status") == "pending" and it.get("kind") in POS_KINDS and not it.get("wait"))
               or (it.get("status") == "placed" and it.get("cancel_req")) for it in items.values())


def now_due(tag: str, book: dict | None, now: dt.datetime | None = None) -> bool:
    """盘中（timing = now）、今天早上的运行已经完成、有要马上下的手动指令（执行器还没读的买卖，或读了还在等的；
    「明天再处理」的、RETRY_S 秒内试过的不算；HALT 时不算）→ 面板叫执行器跑一次 --phase now。"""
    now = now or now_jst()
    if timing(now)[0] != "now" or paths.halt_file().exists():
        return False
    st = (book or {}).get("state") or {}
    if str(st.get("last_date") or "") < prev_trading_day(now.date()).isoformat():
        return False                                        # 今天早上的运行还没完成（它会先处理这些指令）
    if any(r["kind"] in ORDER_KINDS + ("core",) for r in unseen(tag, book)):
        return True
    today = now.date().isoformat()
    cr = (book or {}).get("core_rule") or {}
    if cr and cr.get("decided_on") == st.get("last_date") and cr.get("defer") != today:
        want = float(((book or {}).get("manual") or {}).get("core_pct", 100.0))
        if abs(want - float(cr.get("applied", cr.get("pct", want)))) > 1e-9:
            try:
                age = (now - dt.datetime.fromisoformat(str(cr["tried"]))).total_seconds() if cr.get("tried") else None
            except (TypeError, ValueError):
                age = None
            if age is None or age >= RETRY_S:
                return True
    for it in (((book or {}).get("manual") or {}).get("items") or {}).values():
        if it.get("status") != "pending" or it.get("kind") not in ORDER_KINDS or it.get("hold") == today:
            continue
        try:
            age = (now - dt.datetime.fromisoformat(str(it["tried"]))).total_seconds() if it.get("tried") else None
        except (TypeError, ValueError):
            age = None
        if age is None or age >= RETRY_S:
            return True
    return False


def status_text(it: dict) -> str:
    """指令的状态（页面 / 日志）：盘中的单分「盘中已成交 / 盘中已下单」；明天再处理的写「明天开盘」。"""
    s = it.get("status")
    if s == "placed" and it.get("now"):
        return "盘中已成交" if it.get("fill") else "盘中已下单"
    if s == "pending" and it.get("hold"):
        return "明天开盘"
    return STATUS.get(s, str(s))


def entry_why(eng, t: str, i: int) -> str | None:
    """买入 / 加仓的闸门（与规则的新仓相同）：资格检查 / 手动卖出后不买回（entry_gate_fn）、决算前（entry_block_fn）、新仓倍数 0。"""
    why = eng.entry_gate_fn(t, i) if eng.entry_gate_fn is not None else None
    if not why and eng.entry_block_fn is not None:
        why = eng.entry_block_fn(t, i)
    if not why and float(eng._entry_mult(t, i)) <= 0:
        why = "规则现在不开新仓（新仓倍数是 0）"
    return why


def buy_size(eng, it: dict, eq: float, px: float, lot: int, em: float) -> tuple[int, str]:
    """买入的股数（单元向下取整，还没按上限 / 现金截）与说明：按规则的仓位 = 权益 × position_pct × 新仓倍数（≤ 单只上限；
    与统一决策的新仓同一个算法，价格含滑点）；或目标（股数 / 金额 / 占权益 %）。"""
    cfg = eng.cfg
    if it.get("unit", "rule") == "rule":
        budget = min(eq * cfg.position_pct * min(1.0, em), eq * cfg.max_position_pct)
        pxs = px * (1 + eng.slip["JP"])
        return (int(math.floor(budget / pxs / lot)) * lot,
                f"按规则的仓位（权益 ×{cfg.position_pct * 100:g}%" + (f" × 新仓倍数 {em:g}" if em < 1 else "") + "）")
    return target_shares(it["unit"], it["value"], eq, px, lot), f"目标 {fmt_target(it)}"


def _when(it: dict, bar: str) -> str:
    """成交说明里的「盘中 / 开盘」：盘中下的单（now）在下单那天成交 → 盘中；没成交、改到之后的开盘卖的 → 开盘。"""
    return "盘中" if it.get("now") and str(it.get("fill_day") or "") == str(bar) else "开盘"


def _wait_text(now: dt.datetime, fill_day: dt.date) -> str:
    """开盘前的补单不做的买入 / 加仓：成交日就是今天 → 09:00 开盘后马上下（盘中的运行）；否则 → 那天早上的运行（开盘的寄付单）。"""
    if now.date() == fill_day:
        return "09:00 开盘后马上下单（盘中）"
    return f"{fill_day:%m/%d} 早上的运行下单（开盘买）"


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
        new = [r for r in read_all(self.tag) if r["id"] not in items]
        dropped = {r.get("target") for r in new if r["kind"] == "cancel"}   # 执行器读到之前就被撤回的（比例 / 解除是读到就生效的）
        for r in new:
            it = {**r, "status": "pending"}
            items[r["id"]] = it
            k = r["kind"]
            if k in ("core", "unblock") and r["id"] in dropped:
                it.update(status="cancelled", msg="执行器读到之前就撤回了")
            elif k == "core":
                self.m["core_pct"] = float(r["pct"])
                it.update(status="done", msg=f"闲置资金比例设为 {r['pct']:g}%"
                          + (f"（{r['ticker']} 约 {int(r.get('target') or 0):,} 口）" if r.get("ticker") else ""))
            elif k == "unblock":
                gone = self.m["blocks"].pop(r["ticker"], None)
                it.update(status="done" if gone else "rejected",
                          msg=f"{r['ticker']} 解除「不自动买回」" if gone else f"{r['ticker']} 本来就没有「不自动买回」")
            elif k == "cancel":
                tg = items.get(r["target"])
                if tg is not None and tg.get("status") == "pending":
                    tg.update(status="cancelled", msg=f"已撤回（{r['id']}）")
                    for f in ("wait", "hold", "tried"):
                        tg.pop(f, None)
                    it.update(status="done", msg=f"撤回 {r['target']}")
                elif tg is not None and tg.get("status") == "cancelled" and r["target"] in dropped:
                    it.update(status="done", msg=f"撤回 {r['target']}")
                elif tg is not None and tg.get("status") == "placed" and tg.get("now"):
                    it.update(status="rejected", msg=f"{r['target']}：{NOW_NO_CANCEL}")
                elif tg is not None and tg.get("status") == "placed" and not tg.get("cancel_req"):
                    tg["cancel_req"] = r["id"]
                    it.update(status="done", msg=f"撤回 {r['target']}：之后不再下（已经发到交易所的要在立花网站 / App 上撤）")
                else:
                    it.update(status="rejected", msg=f"{r['target']} 不是还没完成的指令，撤不了")
            else:
                it["msg"] = "等执行器下单"
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
        """第 i 根 K 线收盘后的决策之前（deciding = True）或同一决策补单之前（False）：等着的 sell / trim / adjust / buy → 开盘的寄付单。
        补跑的旧 K 线（成交日已经过了）不处理；HALT 时不动；成交日 08:55 之后寄付来不及 → 留着，开盘后由盘中的运行（now_phase）下。
        加仓 / 买入只在 deciding（统一决策要先给它留钱、买入还占名额）；同一决策补单时留着（wait），09:00 开盘后由盘中的运行下。
        先处理卖出 / 减仓 / 调仓，再处理买入（同一次决策里先卖出一只、空出的名额给买入）。返回 [(级别, 说明)]。"""
        todo = sorted(self.pending(ORDER_KINDS), key=lambda x: (x["kind"] == "buy", x.get("at", "")))
        if not todo:
            return []
        now = self.clock()
        if now.date() > fill_day:
            return []
        if now.date() == fill_day and now.time() >= CUTOFF:
            return [("info", f"手动指令 {len(todo)} 条：过了 {CUTOFF:%H:%M}，寄付来不及 → 开盘后马上下（盘中）")]
        if halted:
            return [("warn", f"手动指令 {len(todo)} 条没处理：HALT 生效中（解除之后才处理）")]
        st, out = eng.st, []
        decided = eng.gidx[i].date()
        for it in todo:
            t = it["ticker"]
            ps = st.pos.get(t)
            rule = st.pending_exit.get(t)
            for f in ("wait", "hold", "tried"):
                it.pop(f, None)
            if it["kind"] == "buy":
                if ps is not None:
                    it.update(status="rejected", msg="已经持有：要加仓用「调仓」")
                elif not deciding:
                    it.update(wait=True, msg=_wait_text(now, fill_day))
                else:
                    self._buy(eng, i, it, decided, fill_day)
                lvl = "warn" if it["status"] == "rejected" else "info"
                out.append((lvl, f"手动指令 {it['id']}：{t} {it['msg']}"))
                continue
            if ps is None:
                it.update(status="rejected", msg="执行器的账本里没有这只持仓（已经卖掉了？）")
            elif rule == "manual":
                it.update(status="rejected", msg="已经在卖出全部，不用再点")
            elif rule:
                it.update(status="superseded", decided_on=str(decided), fill_day=str(fill_day),
                          msg=f"规则也要卖出全部（{rule}），按规则的单卖")
                if it["kind"] == "sell":
                    self._set_block(t, int(it.get("block_days", BLOCK_DEFAULT)), decided, it["id"])
            elif t in self.m["trims"] or t in self.m["adds"]:
                it["msg"] = "同一只票的上一笔手动单还没成交完：成交后再处理"
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
        """卖出全部（sell）/ 减到 pct %（trim）/ 减到 target 股（adjust 的减仓方向）→ 开盘的寄付成行卖单。"""
        t, st = it["ticker"], eng.st
        sell_all, n_sell = it["kind"] == "sell", None
        eq, px, lot = self._numbers(eng, i, t)
        if not sell_all:
            if target is None:
                target = int(math.floor(eq * float(it["pct"]) / 100 / px / lot)) * lot if px > 0 and eq > 0 else 0
            n_sell = int(ps.shares) - max(0, target)
            if n_sell <= 0:
                it.update(status="rejected", msg=f"现在 {ps.shares:,} 股约占权益 {ps.shares * px / eq * 100:.1f}%，不高于目标：不用减")
                return
            sell_all = target <= 0
        if sell_all:
            st.pending_exit[t] = "manual"
            if it["kind"] == "sell":
                self._set_block(t, int(it.get("block_days", BLOCK_DEFAULT)), decided, it["id"])
            it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(ps.shares), side="SELL",
                      msg=f"{fill_day:%m/%d} 开盘卖出全部 {ps.shares:,} 股")
        else:
            self.m["trims"][t] = {"id": it["id"], "shares": int(n_sell), "target": int(target), "decided_on": str(decided)}
            new_pct = target * px / eq * 100 if eq > 0 else 0.0
            it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(n_sell), side="SELL",
                      msg=f"{fill_day:%m/%d} 开盘卖出 {n_sell:,} 股（{ps.shares:,} → {target:,} 股，约占权益 {new_pct:.1f}%）")

    def _adjust(self, eng, i: int, it: dict, ps, decided: dt.date, fill_day: dt.date, deciding: bool) -> None:
        """调仓：按第 i 天收盘与权益把目标换成股数 → 少于现在 → 卖出多的部分；多于现在 → 加仓（闸门见模块说明）；一样 → 不用调。"""
        t = it["ticker"]
        eq, px, lot = self._numbers(eng, i, t)
        cur = int(ps.shares)
        want = target_shares(it["unit"], it["value"], eq, px, lot)
        if want == cur:
            it.update(status="rejected", msg=f"现在 {cur:,} 股，目标 {fmt_target(it)} 换算也是 {want:,} 股：不用调")
            return
        if want < cur:
            self._place(eng, i, it, ps, decided, fill_day, target=want)
            return
        if not deciding:
            it.update(wait=True, msg=_wait_text(self.clock(), fill_day))
            return
        self._add(eng, i, it, ps, decided, fill_day, want)

    def _add(self, eng, i: int, it: dict, ps, decided: dt.date, fill_day: dt.date, want: int) -> None:
        t, st, cfg = it["ticker"], eng.st, eng.cfg
        eq, px, lot = self._numbers(eng, i, t)
        cur = int(ps.shares)
        why = entry_why(eng, t, i)
        if why:
            it.update(status="rejected", decided_on=str(decided), msg=f"不加仓：{why}")
            return
        if not (px > 0 and eq > 0):
            it.update(status="rejected", decided_on=str(decided), msg="没有收盘价 / 总权益，算不了")
            return
        cap_pct = float(cfg.max_position_pct) * 100
        cap = int(math.floor(eq * float(cfg.max_position_pct) / px / lot + 1e-9)) * lot
        add = (min(want, cap) - cur) // lot * lot
        notes = []
        if want > cap:
            notes.append(f"超过单只上限 {cap_pct:g}%，截到 {cap:,} 股")
        if add <= 0:
            it.update(status="rejected", decided_on=str(decided), msg=f"现在 {cur:,} 股：{cap_text(cur, px, eq, cap_pct, lot)}")
            return
        room = eng.add_room(t, i)
        if room < add:
            notes.append(f"现金只够 {room:,} 股")
            add = room
        if add <= 0:
            it.update(status="rejected", decided_on=str(decided), msg="现金 + 核心 ETF 不够买 1 个单元：不加")
            return
        gap = eng.ex["JP"].max_entry_gap_pct                # 执行器只做东证
        from .tick import round_to_tick
        lim = round_to_tick(px * (1 + gap / 100), t, "BUY")
        st.add_plan[t] = [px, int(add), str(decided), it["id"]]
        self.m["adds"][t] = {"id": it["id"], "shares": int(add), "target": cur + int(add), "decided_on": str(decided),
                             "limit": lim}
        it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(add), side="BUY", limit=lim,
                  msg=f"{fill_day:%m/%d} 开盘买入 {add:,} 股（限价 ¥{lim:,g}；{cur:,} → {cur + add:,} 股，"
                      f"约占权益 {(cur + add) * px / eq * 100:.1f}%）" + "".join(f"；{n}" for n in notes))

    def _buy(self, eng, i: int, it: dict, decided: dt.date, fill_day: dt.date) -> None:
        """手动买入（新开仓）：与规则的新仓同一套闸门（资格检查 / 决算前 / 新仓倍数 0 / 名额），按规则的仓位或目标定股数
        （单只上限 34%、现金 + 核心 ETF 能凑出的钱），放进统一决策的 plan（开盘的寄付指値；统一决策先给它留钱）。"""
        t, st, cfg = it["ticker"], eng.st, eng.cfg

        def no(msg: str) -> None:
            it.update(status="rejected", decided_on=str(decided), msg=msg)
        j = eng.col.get(t)
        if t in eng.core_set:
            return no("核心 ETF 不能手动买（用「闲置资金比例」调）")
        if j is None or not eng.A.has[i, j]:
            return no(f"没有 {t} 在 {decided} 的行情（不在股票池？停牌？）：不买")
        if t in st.plan:
            return no("已经排在开盘买入（规则的信号）：不用再点")
        why = entry_why(eng, t, i)
        if why:
            return no(f"不买：{why}")
        n_after = len(st.pos) - sum(1 for x in st.pending_exit if x in st.pos)
        if n_after + len(st.plan) >= cfg.max_positions:
            return no(f"个股名额已满（拿着 {n_after} 只" + (f" + 排定买入 {len(st.plan)} 只" if st.plan else "")
                      + f"，上限 {cfg.max_positions} 只）：要买先卖出一只")
        eq, px, lot = self._numbers(eng, i, t)
        if not (px > 0 and eq > 0):
            return no("没有收盘价 / 总权益，算不了")
        em = float(eng._entry_mult(t, i))
        want, basis = buy_size(eng, it, eq, px, lot, em)
        cap_pct = float(cfg.max_position_pct) * 100
        cap = int(math.floor(eq * float(cfg.max_position_pct) / px / lot + 1e-9)) * lot
        notes = []
        if want > cap:
            notes.append(f"超过单只上限 {cap_pct:g}%，截到 {cap:,} 股")
            want = cap
        if want <= 0:
            return no(f"{basis}不够买 1 个单元（{lot:,} 股 ≈ ¥{lot * px:,.0f}）：不买")
        room = eng.add_room(t, i)
        if room < want:
            notes.append(f"现金只够 {room:,} 股")
            want = room
        if want <= 0:
            return no("现金 + 核心 ETF 不够买 1 个单元：不买")
        gap = eng.ex["JP"].max_entry_gap_pct
        from .tick import round_to_tick
        lim = round_to_tick(px * (1 + gap / 100), t, "BUY")
        st.plan[t] = [px, int(want), str(decided)]
        self.m["buys"][t] = {"id": it["id"], "shares": int(want), "decided_on": str(decided), "limit": lim}
        sig = bool(eng.A.entry[i, j])
        it.update(status="placed", decided_on=str(decided), fill_day=str(fill_day), shares=int(want), side="BUY", limit=lim,
                  msg=f"{fill_day:%m/%d} 开盘买入 {want:,} 股（限价 ¥{lim:,g}；约 ¥{want * px:,.0f}，约占权益 {want * px / eq * 100:.1f}%；"
                      f"{basis}）" + "".join(f"；{n}" for n in notes) + ("" if sig else "；★ 没有买入信号：是你自己的决定"))

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
        """执行器对账时每笔手动单（reason manual / manual_trim / manual_add / manual_buy）的结果（qty = 0：没成交；why = 单的说明）。
        bar = 成交日；盘中下的单（item 的 now，成交日同一天）写「盘中」，否则写「开盘」。"""
        fill = {"qty": int(qty), "px": round(float(px), 2)}
        if reason in ("manual_add", "manual_buy"):
            add = reason == "manual_add"
            x = self.m["adds" if add else "buys"].pop(ticker, None)
            if not x:
                return
            it = self.m["items"].get(x["id"]) or {}
            when = _when(it, bar)
            late = "；撤回来不及：交易所的单已经成交" if it.get("cancel_req") else ""
            done = "加仓完成" if add else "新仓，之后按规则止损 / 离场"
            if qty <= 0 and it.get("cancel_req"):
                it.update(status="cancelled", done_on=bar, msg=f"已撤回（{it['cancel_req']}）：{bar} 没有买")
            elif qty <= 0:
                it.update(status="rejected", done_on=bar,
                          msg=f"{bar} {when}没买到{('（' + why + '）') if why else ''} → 只做一次，要{'加' if add else '买'}请再点一次")
            elif qty < int(x["shares"]):
                it.update(status="done", done_on=bar, fill=fill,
                          msg=f"{bar} {when}买入 {qty:,} 股 @ ¥{px:,.2f}（计划 {int(x['shares']):,} 股，只成交一部分；{done}）{late}")
            else:
                it.update(status="done", done_on=bar, fill=fill, msg=f"{bar} {when}买入 {qty:,} 股 @ ¥{px:,.2f}（{done}）{late}")
            return
        if reason == "manual_trim":
            x = self.m["trims"].get(ticker)
            if not x:
                return
            it = self.m["items"].get(x["id"]) or {}
            when = _when(it, bar)
            if qty <= 0:
                it["msg"] = f"{bar} {when}没成交 → 下一开盘再卖"
                return
            left = int(x["shares"]) - int(qty)
            if left > 0 and ticker in st.pos:
                x["shares"] = left                          # 部分成交：剩下的下一次再卖
                it["msg"] = f"{bar} {when}卖出 {qty:,} 股 @ ¥{px:,.2f}，还差 {left:,} 股（下一开盘再卖）"
                return
            self.m["trims"].pop(ticker, None)
            it.update(status="done", done_on=bar, fill=fill, msg=f"{bar} {when}卖出 {qty:,} 股 @ ¥{px:,.2f}（减仓完成）")
            return
        for it in self._active_for(ticker):
            if (self.m["trims"].get(ticker) or {}).get("id") == it["id"] or (self.m["adds"].get(ticker) or {}).get("id") == it["id"]:
                continue
            when = _when(it, bar)
            if ticker not in st.pos:
                it.update(status="done", done_on=bar, fill=fill, msg=f"{bar} {when}卖出 {qty:,} 股 @ ¥{px:,.2f}（全部卖出）"
                          + ("；撤回来不及：交易所的单已经成交" if it.get("cancel_req") else ""))
            elif qty > 0:
                it["msg"] = f"{bar} {when}只成交 {qty:,} 股 @ ¥{px:,.2f}，剩下的下一开盘再卖"
            else:
                it["msg"] = f"{bar} {when}没成交 → 下一开盘再卖"

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
                        it.update(status="rejected", msg=f"这笔{'加仓' if what == '加' else '买入'}没有成交记录 → 结束"
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
                "fill_day", "done_on", "fill", "shares", "side", "limit", "source", "note", "cancel_req", "wait", "now", "hold")
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
        out.append(f"- 闲置资金比例：手动设为规则目标额的 {float(sm['core_pct']):g}%（改回 100% 就照规则）")
    for t, b in (sm.get("blocks") or {}).items():
        out.append(f"- {t}：不自动买回（{'一直，直到解除' if b.get('until') is None else '到 ' + str(b['until'])}）")
    for it in sm.get("items") or []:
        if it.get("status") in ACTIVE or (today and str(it.get("done_on") or "") >= today) \
                or (today and str(it.get("at") or "")[:10] >= today):
            out.append(f"- 手动 {describe(it)}：{status_text(it)}" + (f"（{it['msg']}）" if it.get("msg") else ""))
    return out


__all__ = ["KINDS", "POS_KINDS", "ORDER_KINDS", "UNITS", "BUY_UNITS", "BLOCK_DEFAULT", "CAP_PCT", "MAX_POS", "SESSION", "Manual",
           "append", "read_all", "unseen", "cancelled", "normalize", "check", "slots", "core_tickers", "core_info", "core_rec", "core_pct_for", "core_effects", "timing", "when_text",
           "next_window", "due",
           "RULE_TEXT", "NOW_NO_CANCEL",
           "now_due", "status_text", "entry_why", "buy_size", "requests_path", "position_pct", "target_shares", "adjust_plan",
           "cap_text", "fmt_target", "describe", "active", "lines", "LABEL", "STATUS", "REASON_TEXT"]
