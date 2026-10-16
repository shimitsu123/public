"""trade_room.py — 「今天还能买几次 / 卖几次 / 还能做几次股票交易」（D6；2026-10-15 用户要求 3）。

立花不限每天下单的次数（2026-09-26 核对，MACOS.md §9）：限制来自差金決済与执行器的规则。这里把它们按顺序合起来（取最严：
任何一条说今天不行 → 0），给面板「交易」页顶部的小卡、持仓卡片的小标记、/api/trade_room、`manual list` 用：
  ① 交易所时段：前場 09:00〜11:30、後場 12:30〜15:30；15:25〜15:30 是收盘竞价（执行器盘中的路只到 15:25）→ 15:25 之后 / 休市日今天 0 次。
  ② 差金決済（立花 e支店「差金決済取引・日計り取引」页，2026-10-15 核对：
     https://www.e-shiten.jp/TorihikiRule/rule/sakin_hibakari.html ）—— 现物交易里同一只、同一天、同一笔钱：
       例 1：买 → 卖之后再买 → 要另有前受金（这次卖出所得不能拿来再买）；
       例 2：拿着的 卖 → 买之后再卖 → 要另有前受金，或持股 ≥ 合计卖出股数；
       例 3：换别的股票不受限。
     按今天这只票的执行器的单（成交过的 / 还在交易所的，按发出的先后）判断；要另外的钱时写需要多少。
  ③ 执行器的规则：同一只当天只下一笔（MO.busy_today，D4：成交过的照算）→「下一笔 MM/DD 开盘」；个股名额（最多 4 只，含排定的买入）；
     手动卖出后不买回（到哪天）；资格检查 / 立花能不能买 / 决算前 / 新仓倍数 0（执行汇总里候选的 buy.block / warn）；
     现价比收盘高 3% 以上不买（与开盘买入同一个上限）；核心 ETF 不能用「买入」（用固定口数 / 闲置资金比例）。
  ④ 钱：现在能用的现金（与执行器 now_phase 的 cash_now 同一个式子：(券商的余力 − 今天还没下 / 还没撮合的买单要占的 − 出金预留)
     × (1 − 现金缓冲)）够几手；加上可以凑钱卖的核心 ETF（今天没有执行器的单、不是正要照固定口数调的）够几手。
  ⑤ HALT / 立花没解锁（ARM）/ 状态不明的单 / 今天的持仓核对不一致 / 今天早上的运行没完成（立花 08:55 之后）→ 全部 0；
     面板盘中自动下单暂停只写一句（写新的指令就恢复，不算 0）。
只读、不下单、不取价：现价由调用方给（面板 = 现价缓存里有的；没有 → 账本里的收盘估）。不写建议：不说该买哪只，候选只数「能不能」。
"""
from __future__ import annotations

import datetime as dt
import math

from . import live_ops as LO
from . import manual_orders as MO
from . import names as NM
from . import paths
from .calendar_jp import is_trading_day, next_trading_day, now_jst
from .utils import read_json

SAKIN_URL = "https://www.e-shiten.jp/TorihikiRule/rule/sakin_hibakari.html"   # 立花 e支店「差金決済取引・日計り取引」（2026-10-15 核对）
NOTE = "券商不限次数；限制来自差金決済与执行器规则"            # 卡片的说明（立花不限每天下单次数：MACOS.md §9，2026-09-26 核对）
AM = (dt.time(9, 0), dt.time(11, 30))                          # 前場
PM = (dt.time(12, 30), dt.time(15, 30))                        # 後場（15:25〜15:30 是收盘竞价：执行器盘中的路到 15:25 为止，MO.SESSION）
PHASE_TEXT = {"holiday": "休市日", "pre": "开盘前", "am": "盘中（前场）", "lunch": "午休", "pm": "盘中（后场）",
              "closing": "收盘竞价（15:25〜15:30）", "after": "收盘后"}
UNKNOWN = ("SENDING", "ERROR")                                 # 状态不明的单（live_unified.UNKNOWN）
GAP_PCT = 3.0                                                  # 个股买入：现价比收盘高这么多就不买（引擎 max_entry_gap_pct；汇总 new_pos.gap_pct 有就用它）
FIX_ADD_MAX = 1.001                                            # 固定口数最多到总权益（MO.check 的 corefix 同一条）
OK, NG = "✓", "✗"


def phase(now: dt.datetime) -> str:
    """现在的时段：holiday / pre（开盘前）/ am / lunch / pm / closing（15:25〜15:30）/ after（15:30 之后）。"""
    if not is_trading_day(now.date()):
        return "holiday"
    t = now.time()
    if t < AM[0]:
        return "pre"
    if t < AM[1]:
        return "am"
    if t < PM[0]:
        return "lunch"
    if t < MO.SESSION[1][1]:
        return "pm"
    return "closing" if t < PM[1] else "after"


def market(now: dt.datetime, book: dict | None = None) -> dict:
    """时段 + 现在写的指令什么时候下（MO.when_for）+ 下一个能交易的时刻 → {"phase", "text", "today"（今天还能交易）, "when", "next",
    "next_text", "line"（一行说明）}。"""
    ph = phase(now)
    d = now.date()
    if ph in ("am", "pm"):
        nxt, nt = now, "现在（盘中）"
    elif ph == "pre":
        nxt = dt.datetime.combine(d, AM[0], tzinfo=now.tzinfo)
        nt = "今天 09:00 开盘"
    elif ph == "lunch":
        nxt = dt.datetime.combine(d, PM[0], tzinfo=now.tzinfo)
        nt = "今天 12:30 后场开盘"
    else:
        nd = next_trading_day(d)
        nxt = dt.datetime.combine(nd, AM[0], tzinfo=now.tzinfo)
        nt = f"{nd:%m/%d} 09:00 开盘"
    when = MO.when_for(now, book)
    today = ph in ("pre", "am", "lunch", "pm")
    line = f"{PHASE_TEXT[ph]}：现在写的买卖 → {when}下单" + ("" if ph in ("am", "pm") else f"；下一个能交易的时刻 {nt}")
    if ph == "closing":
        line += "（15:25 起是收盘竞价：执行器盘中的路到 15:25 为止）"
    return {"phase": ph, "text": PHASE_TEXT[ph], "today": today, "when": when, "next": nxt.isoformat(timespec="minutes"),
            "next_text": nt, "line": line}


# ───────────────────────── ② 差金決済 ─────────────────────────
def _live_today(o: dict) -> bool:
    """这笔单算「今天做过 / 在做」的买卖（差金決済按它）：成交过（含部分）或还在交易所（发送中 / 已下单 / 部分成交）。"""
    return int(o.get("filled_qty") or 0) > 0 or o.get("status") in LO.AT_EXCH


def _qty_of(o: dict) -> int:
    """这笔单算多少股：还在交易所的按下单的股数（可能全部成交），结束了的按成交的股数。"""
    if o.get("status") in LO.AT_EXCH:
        return int(o.get("sent_qty") or o.get("qty") or 0)
    return int(o.get("filled_qty") or 0)


def _px_of(o: dict) -> float:
    return float(o.get("filled_px") or 0) or float(o.get("limit") or 0) or float(o.get("ref_px") or 0)


def sakin(orders, held0: int = 0) -> dict:
    """差金決済（同一只、同一天；立花 e支店 2026-10-15 核对，见文件头）：orders = 今天这只票的执行器的单（dict），held0 = 今天开盘前拿着的股数
    （账本的持仓：当天的成交第二天早上对账才记进去）→
    {"seq": "BS…"（成交过 / 在交易所的单按发出的先后，连续同方向算一次）, "bought", "sold"（股）, "sold_jpy"（卖出所得：成交价 × 股数）,
     "buy": {"rule": 1 | None, "why"}（例 1：买 → 卖之后再买要另有前受金，这次卖出所得不能用）,
     "sell": {"rule": 2 | None, "free": 不另付钱最多还能卖几股 | None, "why"}（例 2：拿着的 卖 → 买之后再卖 → 要另有前受金或持股 ≥ 合计卖出股数）}。
    纯函数（只看给它的单）；执行器「同一只当天只下一笔」一般先挡住第二笔，这里把交易所的规则单独写出来（换别的票不受限：例 3）。"""
    live = sorted((o for o in orders or [] if isinstance(o, dict) and _live_today(o)), key=lambda o: str(o.get("sent_at") or ""))
    seq = ""
    for o in live:
        s = "B" if o.get("side") == "BUY" else "S"
        if not seq.endswith(s):
            seq += s
    bought = sum(_qty_of(o) for o in live if o.get("side") == "BUY")
    sold = sum(_qty_of(o) for o in live if o.get("side") == "SELL")
    sold_jpy = sum(_qty_of(o) * _px_of(o) for o in live if o.get("side") == "SELL")
    out = {"seq": seq, "bought": bought, "sold": sold, "sold_jpy": round(sold_jpy),
           "buy": {"rule": None, "why": None}, "sell": {"rule": None, "free": None, "why": None}}
    if "BS" in seq:                                        # 例 1：买 → 卖之后再买
        out["buy"] = {"rule": 1, "why": (f"差金決済（例 1）：今天已经买 → 卖过这只，再买要另有前受金"
                                         f"（这次卖出所得约 ¥{sold_jpy:,.0f} 不能拿来再买）")}
    if "SB" in seq and int(held0) > 0:                     # 例 2：拿着的 卖 → 买之后再卖
        free = max(0, int(held0) - sold)
        out["sell"] = {"rule": 2, "free": free,
                       "why": ("差金決済（例 2）：今天已经卖 → 买过这只，再卖要另有前受金，或持股 ≥ 合计卖出股数"
                               f"（不另付钱最多再卖 {free:,} 股）")}
    return out


# ───────────────────────── ④ 钱 ─────────────────────────
def _broker_cash(book: dict | None, tag: str | None, now: dt.datetime) -> float:
    """券商那边现在的现金 / 余力（执行器 cash_now 的 b.cash()）：模拟账户 = 模拟券商文件的现金（盘中的成交当场记进去）；
    立花 = 今天的余力快照（broker_snapshot）；都没有 → 账本现金。"""
    v = float(((book or {}).get("state") or {}).get("cash_jpy") or 0)
    if not tag:
        return v
    try:
        if str(tag).startswith("paper"):
            bj = read_json(paths.state_dir() / f"live_unified_{tag}_broker.json", None)
            if isinstance(bj, dict) and bj.get("cash") is not None:
                return float(bj["cash"])
        else:
            snap = read_json(paths.out_dir() / f"broker_snapshot_{tag}.json", {}) or {}
            if str(snap.get("at") or "")[:10] == now.date().isoformat() and snap.get("buying_power") is not None:
                return float(snap["buying_power"])
    except (TypeError, ValueError, OSError):
        pass
    return v


def cash_now(book: dict | None, tag: str | None, now: dt.datetime, cash: float | None = None) -> dict:
    """现在能用来买的钱（与执行器 now_phase 的 cash_now 同一个式子）：(券商的余力 − 今天开盘还没下 / 还没撮合的买单要占的 − 出金预留)
    × (1 − 现金缓冲)。孤儿（凑钱的卖单没了）不留钱（D4）。开盘时一定下不成的买单（LO.unfunded_buys）执行器照样留钱 → 这里也留，
    另外记在 "unf"（审查 UI F7，2026-10-16：以前这里不留，交易室比执行器多算了能用的钱）。
    cash：券商的余力（None = _broker_cash）→ {"base", "res"（留给还没下的买单的）, "unf"（其中一定下不成的）, "reserve"（出金预留）,
    "buf_pct", "cash"}。"""
    b = book or {}
    st = b.get("state") or {}
    paper = str(tag or "").startswith("paper") or str(b.get("broker") or "").startswith("Paper")
    base = _broker_cash(b, tag, now) if cash is None else float(cash)
    d = st.get("last_date")
    cur = [o for o in b.get("orders") or [] if isinstance(o, dict) and o.get("decided_on") == d]
    res = unf_v = 0.0
    if LO.fill_day_of(b) == now.date():
        try:
            unf = LO.unfunded_buys(b, cash=base)
        except (TypeError, ValueError, KeyError):
            unf = {}
        for o in cur:
            if o.get("side") != "BUY":
                continue
            if (o.get("status") == "DEFERRED" and not LO.orphan(o, cur, now, now.date())) or \
                    (paper and o.get("phase") == "morning" and o.get("status") == "SENT"):
                v = float(o.get("limit") or 0) * int(o.get("qty") or 0) or LO._need_est(o, int(o.get("qty") or 0))
                res += v + MO.fee_jp(v)
                if str(o.get("cid")) in unf:
                    unf_v += v + MO.fee_jp(v)
    rsv = LO._reserve_of(b, paper)
    buf = MO.CASH_BUF_PCT
    return {"base": round(base), "res": round(res), "unf": round(unf_v), "reserve": round(rsv), "buf_pct": buf,
            "cash": max(0.0, (base - res - rsv) * (1 - buf / 100))}


def lots(money: float, px: float, lot: int, pad: float = MO.NOW_BUY_BUF) -> int:
    """money 円够买几个单元（价格 ×(1 + 0.5%) 的限价 + 手续费；与盘中买入占余力的口径相同）。"""
    if px <= 0 or lot <= 0 or money <= 0:
        return 0
    unit = lot * px * (1 + pad)
    k = int(money // unit)
    while k > 0 and k * unit + MO.fee_jp(k * unit) > money + 1e-9:
        k -= 1
    return k


def lot_cost(px: float, lot: int, pad: float = MO.NOW_BUY_BUF) -> float:
    """一个单元大约要多少钱（限价 + 手续费）。"""
    v = lot * px * (1 + pad)
    return v + MO.fee_jp(v)


def fundable(book: dict | None, now: dt.datetime, px_of, skip=()) -> tuple[float, list]:
    """可以凑钱卖的核心 ETF（执行器 fund_src 同一口径）：拿着的、今天没有执行器的单的（busy_today）、不在 skip 里的（要买的这只 / 正要照
    固定口数调的）→ (卖出所得扣手续费、再扣现金缓冲之后的合计, [票])。取不到价格的不算。"""
    st = (book or {}).get("state") or {}
    val, used = 0.0, []
    for c, u in sorted((st.get("core_units") or {}).items()):
        u = int(u or 0)
        if u <= 0 or c in skip or MO.busy_today(book, c, now):
            continue
        p = px_of(c)
        if p <= 0:
            continue
        net = u * p * (1 - MO._etf_slip(c))
        val += (net - MO.fee_jp(net)) * (1 - MO.CASH_BUF_PCT / 100)
        used.append(c)
    return val, used


# ───────────────────────── 每一只 ─────────────────────────
def _side(via: str = "") -> dict:
    return {"n": 1, "max_qty": 0, "why": [], "short": "", "next": "", "via": via}


def _no(s: dict, why: str, short: str, nxt: str = "") -> None:
    """这一边今天 0 次：第一条挡住的原因当小标记（规则按 ① → ⑤ 的顺序查）；原因都留着。"""
    if s["n"]:
        s["short"], s["next"] = short, nxt
    s["n"] = 0
    s["why"].append(why)


def _note(s: dict, why: str) -> None:
    s["why"].append(why)


def _qpx(quotes: dict | None, t: str) -> float:
    q = (quotes or {}).get(t)
    if isinstance(q, dict):
        q = q.get("px")
    try:
        return float(q or 0)
    except (TypeError, ValueError):
        return 0.0


def _gates(tag: str, book: dict, now: dt.datetime, halt: bool, arm: str | None, ph: str, running: bool | None = None) -> tuple[list, list]:
    """⑤ 全部挡住的（→ [(原因, 小标记)]）与只写一句的（→ [原因]）。running：执行器正在运行（拿着运行锁；None = 看锁）。"""
    st = book.get("state") or {}
    paper = str(tag).startswith("paper")
    g, notes = [], []
    if halt:
        g.append(("HALT 生效中：执行器不下单（解除之后才处理；解除只在 Mac 上、你明确说）", "HALT"))
    if "dryrun" in str(tag):
        g.append(("dry-run 的账本：只算不发单", "只看"))
    elif not paper and arm in ("off", "bad"):
        g.append(("立花还没解锁（没有 ARM，或内容不是 ARMED）：单会被挡住，不会真的发出去", "没解锁"))
    d = st.get("last_date")
    unk = [o for o in book.get("orders") or [] if isinstance(o, dict) and o.get("decided_on") == d and o.get("status") in UNKNOWN]
    if any(o.get("status") == "SENDING" for o in unk):
        if running is None:
            from .live_unified import lock_held
            running = lock_held(paths.state_dir() / f"live_unified_{tag}.lock")
        if running:                                        # 执行器正在运行：SENDING 是正在发的单（发之前先存账本）→ 不是状态不明（与面板同一口径）
            snd = [o for o in unk if o.get("status") == "SENDING"]
            unk = [o for o in unk if o.get("status") != "SENDING"]
            notes.append("执行器正在运行（发送中：" + "、".join(LO._labq(o.get("ticker"), f"{int(o.get('qty') or 0):,} {'口' if o.get('kind') == 'core' else '股'}")
                                                        for o in snd)
                         + "）：跑完之后数会变")
    if unk:
        g.append(("有状态不明的单（" + "、".join(LO._labq(o.get("ticker"), f"{int(o.get('sent_qty') or o.get('qty') or 0):,}"
                                                       f" {'口' if o.get('kind') == 'core' else '股'}") for o in unk)
                  + "）：先核对、登记，登记之前执行器不下单", "状态不明的单"))
    mm = book.get("broker_mismatch") or {}
    if mm.get("text") and mm.get("date") == now.date().isoformat():
        g.append((f"今天早上的持仓核对不一致（{NM.annotate(str(mm['text']))[:160]}）：下一次早上核对一致之前不下单", "持仓不一致"))
    if ph in ("pre", "am", "lunch", "pm") and now.time() >= MO.RUN_AT and MO.morning_behind(book, now):
        # 写法与面板顶部的「★ 今天早上的运行还没完成」分开（那条有自己的条件：停用了的模拟账户不吵）；这里只说对「今天还能做几次」的影响
        nd, ld = next_trading_day(now.date()), d or "—"
        if not paper and now.time() >= MO.CUTOFF:
            g.append((f"早上的决策还没做到今天（上次决策 {ld}；立花不自动补跑：你说再跑才补）→ 补跑之后才下；没补跑 → {nd:%m/%d} 开盘",
                      "早上没跑完"))
        else:
            notes.append(f"早上的决策还没做到今天（上次决策 {ld}）："
                         + ("手动指令等补跑之后才下（装着定时任务的模拟账户面板自动补跑）" if paper else "08:55 之前完成 → 照常")
                         + f"；没补跑 → {nd:%m/%d} 开盘")
    if ph == "pre" and now.time() < MO.RUN_AT:
        notes.append(f"今天 {MO.RUN_AT:%H:%M} 的决策还没跑：规则的开盘单（新仓、核心 ETF 的买卖、名额）会照它变")
    return g, notes


def room(tag: str, book: dict | None, now: dt.datetime | None = None, quotes: dict | None = None, waiting: list | None = None, *,
         sm: dict | None = None, halt: bool | None = None, paused: bool | str = False, cash: float | None = None,
         arm: str | None = None, cands: list | None = None, running: bool | None = None) -> dict:
    """今天还能买几次 / 卖几次（见文件头 ① → ⑤）。
    quotes：{票: 现价} 或 {票: {"px": …}}（没有 → 账本里的收盘）；waiting：指令文件里执行器还没读的（None = MO.unseen）；
    sm：执行器的汇总（候选 = suggest.rows、新仓倍数、资格检查）；halt：None = 看 HALT 文件；paused：面板盘中自动下单今天暂停（原因文字）；
    cash：券商的余力（None = 模拟券商的现金 / 立花今天的余力快照 / 账本现金）；arm：None = paths.arm_state()；
    cands：候选（suggest 的行或代码；None = sm 里的 suggest.rows）；running：执行器正在运行（None = 看运行锁；只在有 SENDING 的单时看）。
    → {"tag", "asof", "market", "per_ticker": {票: {"t", "label", "kind": stock | core, "held", "cand", "buy": {n, max_qty, why[], short, next, via},
       "sell": {…}, "sakin", "chip"}}, "overall": {"buy_left" | "sell_left" | "trades_left": {"n", "why"}}, "headline", "note",
       "gates", "notes", "money", "slots", "cands", "sakin_url"}。"""
    now = now or now_jst()
    b = book or {}
    st = b.get("state") or {}
    sm = sm or {}
    man = b.get("manual") or {}
    paper = str(tag).startswith("paper")
    waiting = MO.unseen(tag, b) if waiting is None else [r for r in waiting if isinstance(r, dict)]
    halt = paths.halt_file().exists() if halt is None else bool(halt)
    arm = paths.arm_state() if arm is None else arm
    mk = market(now, b)
    ph = mk["phase"]
    nd_txt = f"下一笔 {next_trading_day(now.date()):%m/%d} 开盘"          # 同一只当天只下一笔 → 下一个交易日开盘
    gates, notes = _gates(tag, b, now, halt, arm, ph, running)
    if paused:
        notes.append("面板盘中自动下单今天暂停" + (f"（{paused}）" if isinstance(paused, str) and paused else "")
                     + "：写新的指令会恢复自动叫执行器（或在 Mac 上说「再试一次」）")
    # 今天已成交的买卖（对账前的投影）：现在写的在成交日当天对账之前执行（pre_reconcile）→ held0、sakin、现金仍按账本 / 券商
    #（执行器当天按账本、差金決済用开盘前的持仓；只改文字）；对账之后才执行（收盘后 / 周末 / 下一个交易日 07:40 之前）→ 持仓、现金、
    # 能凑钱的核心 ETF 按投影（= 执行器那时对过账的账本），当天的单不再算差金決済（四次复核：周一 07:00 以前说周五买进的 1482 今天不能卖）
    try:
        pjr = LO.held_now(b, tag, now=now)
    except Exception:                                      # noqa: BLE001  只是文字：算不了就当没有
        pjr = {"by_ticker": {}, "new": [], "sold_out": [], "day_word": "今天"}
    proj = bool(pjr.get("has")) and isinstance(pjr.get("book"), dict) and not MO.pre_reconcile(pjr, now)
    led_b = b                                              # 账本本身（_placed_filled 比账本与投影）
    if proj:
        b = pjr["book"]
        st = b.get("state") or {}
    pos = st.get("pos") or {}
    cores_held = {t: int(u or 0) for t, u in (st.get("core_units") or {}).items() if int(u or 0) > 0}
    hn_by, hn_new, hn_gone = pjr.get("by_ticker") or {}, set(pjr.get("new") or []), set(pjr.get("sold_out") or [])
    hn_dw = pjr.get("day_word") or "今天"                  # 周末 / 早上的运行之前：「10/16（周五）」（2026-10-16 复核）

    def hn_mark(s: dict, t: str, held: int) -> None:      # 卖这一边的第一个原因：今天买进（对账前不算持仓）/ 今天已卖出全部
        x = hn_by.get(t) or {}
        if held <= 0 and t in hn_new and x.get("text"):
            _no(s, x["text"], f"{hn_dw}买进")
        elif t in hn_gone and x.get("text"):
            _no(s, x["text"], f"{hn_dw}已卖出")
    pend = st.get("pending_exit") or {}
    hist = st.get("history") or []
    eq = float(hist[-1][1]) if hist else 0.0
    cr = b.get("core_rule") or {}
    gone = MO.cancelled(waiting)
    live_items = MO._live(man.get("items") or {}, waiting, MO.ORDER_KINDS)
    if proj:                                               # 今天已全部成交、对账时就完成的指令不再算「在处理」（MO.check 同一个判断；四次复核）
        live_items = MO._settled_later(live_items, led_b, pjr, now)
    instr = {}
    for r in live_items:
        instr.setdefault(r.get("ticker"), r)
    core_instr = [r for r in waiting if r.get("kind") in ("core", "corefix") and r.get("id") not in gone and not r.get("fund_for")]
    allin = MO.allin_busy_text(MO.live_allin(tag, b))
    blocks = man.get("blocks") or {}
    lift = MO.lifting(tag, b)
    try:
        fix_pend = MO.corefix_pending(b, tag, now)
    except Exception:                                      # noqa: BLE001  估算用：读不了就当没有
        fix_pend = {}
    fixed = MO.core_fixed(b, tag)
    plan_live = MO.live_plan(b)
    sl = MO.slots(b, tag, now=now)                        # 名额含今天已成交（2026-10-16 复核）
    el = sm.get("eligibility") or {}
    el_block = {str(x.get("code")): str(x.get("why") or "") for x in el.get("blocked") or [] if isinstance(x, dict)}
    el_core = {str(x.get("code")): str(x.get("why") or "") for x in el.get("core") or [] if isinstance(x, dict)}
    tb = el.get("tachibana") or {}
    tb_stock = {} if paper else {str(x.get("code")): str(x.get("why") or "") for x in tb.get("stock") or [] if isinstance(x, dict)}
    tb_core = {} if paper else {str(x.get("code")): str(x.get("why") or "") for x in tb.get("core") or [] if isinstance(x, dict)}
    npos = sm.get("new_pos") or {}
    mult = ((npos.get("markets") or {}).get("JP") or {}).get("mult")
    gap = float(npos.get("gap_pct") or GAP_PCT)
    rows = {str(r.get("ticker")): r for r in ((sm.get("suggest") or {}).get("rows") or []) if isinstance(r, dict) and r.get("ticker")}
    held_block = {str(k): str(v) for k, v in ((sm.get("suggest") or {}).get("held_block") or {}).items() if v}   # 持仓的「决算前」（UI F6）
    today_ok = mk["today"]
    intraday = ph in ("am", "pm")
    d = st.get("last_date")
    cur_orders = [o for o in b.get("orders") or [] if isinstance(o, dict) and o.get("decided_on") == d] \
        if LO.fill_day_of(b) == now.date() and not proj else []   # 按投影时当天的成交已经在持仓里（不重复算）

    def close_of(t: str) -> float:
        if t in pos:
            return float(pos[t].get("last_close") or pos[t].get("entry_px") or 0)
        c = (cr.get("px") or {}).get(t) or (st.get("core_last") or {}).get(t)
        if c:
            return float(c)
        r = rows.get(t)
        return float((r or {}).get("close") or ((r or {}).get("buy") or {}).get("px") or 0)

    def px_of(t: str) -> float:
        return _qpx(quotes, t) or close_of(t)

    def code_of(t: str) -> str:
        return NM.code(t)

    money = cash_now(b, tag, now, cash)
    cash_ = money["cash"]
    if money.get("unf"):                                   # UI F7（2026-10-16）：执行器照样给它留钱 → 说清楚为什么能用的钱少了
        notes.append(f"今天开盘还没下的买单里约 ¥{money['unf']:,} 开盘时一定下不成，执行器照样给它们留着这笔钱（撤掉那些买单就能用）")
    skip_fix = set(fix_pend)                               # 正要照固定口数调的核心 ETF：不拿来凑（执行器 fund_src 的 fix_want）
    f_all, f_used = fundable(b, now, px_of, skip_fix)

    def session(s: dict) -> None:                           # ① 交易所时段
        if ph == "holiday":
            _no(s, f"今天休市：下一个能交易的时刻 {mk['next_text']}", "休市日", mk["next_text"])
        elif ph == "after":
            _no(s, f"已收盘（15:30 之后今天不能再交易）：下一个能交易的时刻 {mk['next_text']}", "已收盘", mk["next_text"])
        elif ph == "closing":
            _no(s, f"15:25 起是收盘竞价：执行器盘中的路到 15:25 为止，今天不再下 → {mk['next_text']}", "收盘竞价", mk["next_text"])

    def busy(t: str) -> bool:
        return MO.busy_today(b, t, now)

    def gate_all(s: dict) -> None:                          # ⑤
        for why, short in gates:
            _no(s, why, short)

    out: dict = {}

    def add_row(t: str, kind: str, held: int, cand: bool = False) -> dict:
        x = hn_by.get(t) or {}
        r = {"t": t, "label": NM.label(t), "kind": kind, "held": held, "cand": cand, "px": round(px_of(t), 2) or None,
             "buy": _side(), "sell": _side(),
             "held_now": {"buy": int(x.get("buy") or 0), "sell": int(x.get("sell") or 0), "net": int(x.get("net") or 0)}}
        out[t] = r
        return r

    # 持仓个股、今天有单的个股
    order_t = {o.get("ticker") for o in cur_orders if _live_today(o) or LO.busy(o, cur_orders, now, now.date())}
    stock_t = list(pos) + sorted(t for t in order_t if t and t not in pos and o_kind(cur_orders, t) == "stock")
    core_t = list(cores_held) + sorted(t for t in set(order_t) | set(fixed) | set(fix_pend)
                                       if t and t not in cores_held and (o_kind(cur_orders, t) == "core" or t in fixed or t in fix_pend))
    for t in stock_t:
        held0 = int((pos.get(t) or {}).get("shares") or 0)
        r = add_row(t, "stock", held0)
        sk = sakin([o for o in cur_orders if o.get("ticker") == t], held0)
        r["sakin"] = sk
        px, lot = px_of(t), MO.LOT
        s, bb = r["sell"], r["buy"]
        s["via"] = "「卖出全部」/「调仓…」" if held0 > 0 else ""
        bb["via"] = "「调仓…」（加仓）" if held0 > 0 else "「买入…」"
        # 卖
        session(s)                                         # 时段先（休市 / 已收盘），再「今天买进 / 已卖出」
        hn_mark(s, t, held0)
        if sk["sell"]["why"]:
            _note(s, sk["sell"]["why"])
        left = max(0, held0 - sk["sold"])                  # 不另付钱还能卖的（例 2：持股 ≥ 合计卖出股数）
        if held0 <= 0 and t not in hn_new:
            _no(s, "没拿着（今天买进的第二天早上对账之后才算持仓）", "没拿着")
        elif t in pend:
            _no(s, ("已在卖出（手动）" if pend[t] == "manual" else f"已排定开盘卖（{MO._exit_text(pend[t])}）") + "：不用再卖", "已在卖")
        elif t in instr:
            _no(s, f"已经有一条没处理完的手动指令（{instr[t].get('id')}）：先撤回它，或等它完成", "有指令在处理")
        if busy(t):
            _no(s, f"今天已经有执行器的单：同一只当天只下一笔 → {nd_txt}", "今天已有单", nd_txt)
        if left <= 0 < held0:
            if sk["sell"]["rule"] == 2 and sk["bought"] > 0:   # 例 2：开盘前拿着的已经卖完、今天买回的再卖 → 要另有前受金
                need = sk["bought"] * px
                if cash_ < need:
                    _no(s, f"差金決済（例 2）：今天买回的 {sk['bought']:,} 股再卖要另有前受金约 ¥{need:,.0f}"
                           f"（现在能用的现金 ¥{cash_:,.0f}）", "差金決済")
                left = sk["bought"]
            else:
                _no(s, "今天已经卖完", "已卖完")
        s["max_qty"] = left if s["n"] else 0
        gate_all(s)
        # 买（加仓 / 今天有单的没拿着的票）
        session(bb)
        if sk["buy"]["why"]:
            _note(bb, sk["buy"]["why"] + f"：再买 1 个单元（{lot:,} 股）约 ¥{lot_cost(px, lot):,.0f} 全部要来自别的钱")
        if t in pend:
            _no(bb, "已在卖出：不加仓", "已在卖")
        elif t in instr:
            _no(bb, f"已经有一条没处理完的手动指令（{instr[t].get('id')}）：先撤回它，或等它完成", "有指令在处理")
        if busy(t):
            _no(bb, f"今天已经有执行器的单：同一只当天只下一笔 → {nd_txt}", "今天已有单", nd_txt)
        if allin:
            _no(bb, allin, "全部换成在等")
        _stock_gates(bb, t, code_of(t), mult, el_block, tb_stock, blocks, lift, rows.get(t), px if intraday and _qpx(quotes, t) else 0,
                     close_of(t), gap)
        if held_block.get(t) and not any("决算" in x or "決算" in x for x in bb["why"]):
            _no(bb, f"{held_block[t]}：加仓也会被挡（执行器 entry_why 同一个闸门）", "决算前")   # 持仓不在候选行里（UI F6；2026-10-16）
        room_t = cash_ - (sk["sold_jpy"] if sk["buy"]["rule"] == 1 else 0)
        _money(bb, room_t, f_all, px, lot, eq, held0, "股")
        gate_all(bb)
    for t in core_t:
        held0 = cores_held.get(t, 0)
        r = add_row(t, "core", held0)
        sk = sakin([o for o in cur_orders if o.get("ticker") == t], held0)
        r["sakin"] = sk
        px, lot = px_of(t), MO.core_lot(b, t)
        s, bb = r["sell"], r["buy"]
        s["via"] = "「固定口数…」（0 口 = 全部卖出）" if t in fixed else "「卖出全部」/「调仓…」（换算成闲置资金比例）"
        bb["via"] = "「固定口数…」/「买入…」（核心 ETF 不能用个股的「买入」：用固定口数或闲置资金比例）"
        for x in (s, bb):
            session(x)
        hn_mark(s, t, held0)
        if sk["sell"]["why"]:
            _note(s, sk["sell"]["why"].replace("股", "口"))
        if sk["buy"]["why"]:
            _note(bb, sk["buy"]["why"])
        left = max(0, held0 - sk["sold"])
        if held0 <= 0 and t not in hn_new:
            _no(s, "没拿着", "没拿着")
        mine = [y for y in core_instr if y.get("kind") == "core" or y.get("ticker") == t]
        for x in (s, bb):
            if mine:
                _no(x, f"有一条闲置资金比例 / 固定口数的指令还没被执行器读（{mine[-1].get('id')}）：先等它处理（或撤回）", "有指令在处理")
            elif t in instr:
                _no(x, f"已经有一条没处理完的手动指令（{instr[t].get('id')}）：先撤回它，或等它完成", "有指令在处理")
            if busy(t):
                _no(x, f"今天已经有执行器的单：同一只当天只下一笔 → {nd_txt}", "今天已有单", nd_txt)
            if allin:
                _no(x, allin, "全部换成在等")
        if t in fix_pend:
            u = fix_pend[t]
            _note(s, f"固定口数{'恢复按规则' if u is None else f' {int(u):,} 口'}还没照它调：执行器会先照它调")
            _note(bb, f"固定口数{'恢复按规则' if u is None else f' {int(u):,} 口'}还没照它调：执行器会先照它调")
        why_c = el_core.get(code_of(t)) or tb_core.get(code_of(t))
        if why_c:
            _no(bb, f"不买：{why_c}", "资格检查")
        q = _qpx(quotes, t)
        c = close_of(t)
        if intraday and q > 0 and c > 0 and q > c * MO.CORE_BUY_LIMIT:
            _note(bb, f"现价 ¥{q:,g} 比收盘 ¥{c:,g} 高 {q / c - 1:+.1%}：盘中核心 ETF 的买单限价 ≤ 收盘 ×{MO.CORE_BUY_LIMIT:g}，"
                      "这个价下不了（一会儿再试）")
        s["max_qty"] = left if s["n"] else 0
        gate_all(s)
        f_c, _u = fundable(b, now, px_of, skip_fix | set(fixed) | {t})   # 给固定口数凑钱：固定的不卖（D1）
        _money(bb, cash_, f_c, px, lot, eq, held0, "口", cap=FIX_ADD_MAX)
        gate_all(bb)
    # 候选（没拿着的个股）：只数能不能（不是建议）
    cl = list(rows.values()) if cands is None else [rows.get(x, {"ticker": x}) if isinstance(x, str) else x for x in cands]
    cand_rows, all_core, la_t = [], MO.core_tickers(b), {x.get("ticker") for x in MO.live_allin(tag, b)}
    for row in cl:
        t = str((row or {}).get("ticker") or "")
        if not t or t in out or t in pos or t in all_core:
            continue
        r = add_row(t, "stock", 0, cand=True)
        bb, s = r["buy"], r["sell"]
        _no(s, "没拿着", "没拿着")
        bb["via"] = "「买入…」"
        session(bb)
        if t in instr:
            _no(bb, f"已经写了买入（{instr[t].get('id')}）：等它处理", "已写买入")
        elif t in plan_live:
            _no(bb, "已经排在今天开盘买入（规则的信号）", "已排开盘买")
        if busy(t):
            _no(bb, f"今天已经有执行器的单：同一只当天只下一笔 → {nd_txt}", "今天已有单", nd_txt)
        if allin and t not in la_t:
            _no(bb, allin, "全部换成在等")
        _stock_gates(bb, t, code_of(t), mult, el_block, tb_stock, blocks, lift, row, _qpx(quotes, t) if intraday else 0, close_of(t), gap)
        if sl["free"] <= 0:
            _no(bb, f"个股名额已满（拿着 {sl['held']} 只 + 排定买入 {sl['buys']} 只，上限 {sl['max']} 只）：要买先卖出一只", "名额已满")
        lot = int(((row or {}).get("buy") or {}).get("lot") or MO.LOT)
        _money(bb, cash_, f_all, px_of(t), lot, eq, 0, "股")
        gate_all(bb)
        cand_rows.append(r)
    for r in out.values():
        r["both"] = bool(r["buy"]["n"] and r["sell"]["n"])
        r["chip"] = chip(r)
    # overall：卖 = 拿着的、今天还能卖的只数；买 = 还能买的新股只数（名额与钱都够）+ 拿着的还能加仓的只数；共 = 两者之和
    #（同一只既能买又能卖 → 只算一次：执行器同一只当天只下一笔）
    held_rows = [r for r in out.values() if r["held"] > 0]
    sells = [r for r in held_rows if r["sell"]["n"]]
    adds = [r for r in held_rows if r["buy"]["n"]]
    ok_c = sorted((r for r in cand_rows if r["buy"]["n"]), key=lambda r: (lot_cost(r["px"] or 0, MO.LOT), r["t"]))
    gate_txt = "；".join(w for w, _s in gates)
    stop = (not today_ok) or bool(gate_txt) or (mult is not None and float(mult) <= 0)
    pool, new = cash_ + f_all, 0
    for r in ok_c:                                        # 钱是共用的：按一个单元便宜的先数（只是数，不是建议）
        if new >= sl["free"]:
            break
        cst = lot_cost(r["px"] or 0, int(((rows.get(r["t"]) or {}).get("buy") or {}).get("lot") or MO.LOT))
        if 0 < cst <= pool:
            pool -= cst
            new += 1
    if not cand_rows and not stop and pool > 0:            # 没有候选的价格：新股只数名额（钱够几只要看买哪只；不猜）
        new = sl["free"]
    groups: dict = {}
    for r in cand_rows:
        if not r["buy"]["n"]:
            k = r["buy"]["short"] or "不能买"
            groups[k] = groups.get(k, 0) + 1
    g_txt = "、".join(f"{k} {n} 只" for k, n in sorted(groups.items(), key=lambda kv: -kv[1]))
    b_n, s_n = new + len(adds), len(sells)
    one = sum(1 for r in held_rows if r["both"])
    k_n = b_n + s_n - one
    if not today_ok:
        why_b = why_s = f"{mk['text']}：今天 0 次（下一个能交易的时刻 {mk['next_text']}）"
    elif gate_txt:
        why_b = why_s = gate_txt
    else:
        why_b = (f"新股 {new} 只（个股名额空 {sl['free']} 个 / 上限 {sl['max']} 只；"
                 + (f"候选 {len(cand_rows)} 只里名额与钱都够的 {new} 只" + (f"，其余：{g_txt}" if g_txt else "") if cand_rows
                    else "没有候选的价格：只数名额，钱够几只要看买哪只" if new else "新仓倍数 0：规则现在不开新仓" if stop else "钱不够")
                 + f"）+ 拿着的还能加仓 {len(adds)} 只"
                 + _miss([r for r in held_rows if not r["buy"]["n"]], "buy")
                 + f"；钱：现在能用的现金 ¥{cash_:,.0f} + 能卖来凑钱的核心 ETF 约 ¥{f_all:,.0f}（钱是共用的：买了一只，别的就少了）")
        shown = ({r["t"] for r in held_rows} - hn_gone) | hn_new   # 拿着的只数含今天已成交（与「持仓」角标同一个数；2026-10-16 复核）；
        #                                                             held0 / sakin 仍按开盘前的持仓（差金決済）
        why_s = (f"拿着的 {len(shown)} 只" + (f"（{pjr.get('head') or LO.hn_head(hn_dw)}）" if proj or shown != {r["t"] for r in held_rows} else "")
                 + f"里今天还能卖 {s_n} 只" + _miss([r for r in out.values() if r["t"] in shown and not r["sell"]["n"]], "sell"))
    why_k = (f"买 {b_n} + 卖 {s_n}" + (f" − 既能买又能卖的 {one} 只（同一只当天执行器只下一笔：只算一次）" if one else "")
             + "；换别的股票不受差金決済限制（例 3）")
    headline = f"今天还能：买 {b_n} 次 · 卖 {s_n} 次 · 共 {k_n} 次"
    return {"tag": tag, "asof": now.isoformat(timespec="minutes"), "market": mk, "per_ticker": out,
            "overall": {"buy_left": {"n": b_n, "why": why_b, "new": new, "adds": len(adds)},
                        "sell_left": {"n": s_n, "why": why_s},
                        "trades_left": {"n": k_n, "why": why_k}},
            "headline": headline, "note": NOTE, "gates": [w for w, _s in gates], "notes": notes,
            "money": {**{k: v for k, v in money.items() if k != "cash"}, "cash": round(cash_), "fundable": round(f_all),
                      "fund_from": [NM.label(x) for x in f_used]},
            "slots": sl, "cands": {"n": len(cand_rows), "ok": len(ok_c), "groups": groups}, "sakin_url": SAKIN_URL}


def o_kind(orders: list, t: str) -> str:
    """今天这只票的单是个股还是核心 ETF（没有 → stock）。"""
    return next((str(o.get("kind") or "stock") for o in orders if o.get("ticker") == t), "stock")


def _stock_gates(s: dict, t: str, code: str, mult, el_block: dict, tb_stock: dict, blocks: dict, lift: set, row: dict | None,
                 q: float, close: float, gap: float) -> None:
    """③ 个股买入 / 加仓的闸门（与执行器 now_phase 的 entry_why / 现价上限 / 立花能不能买同一组；数字来自执行器的汇总）。"""
    rb = (row or {}).get("buy") or {}
    hard = rb.get("block")
    if hard and (rb.get("block_kind") == "manual" or str(hard).startswith("手动卖出后不")) and (t in lift or t not in blocks):
        hard = None                                        # 不买回已经在解除 / 已经没了（MO.check 同一条）
    bl = blocks.get(t)
    if bl and t not in lift:
        r = MO.rebuy_day(bl.get("until"))
        _no(s, f"手动卖出后不买回：{MO.block_text(bl)}（要提前买：先在{MO.BLOCK_WHERE}点「解除」/「恢复按规则」）",
            "不买回" + (f"到 {r:%m/%d}" if r else ""), f"{r:%m/%d} 开盘" if r else "")
    elif hard:
        _no(s, f"不能买：{hard}", "资格检查")
    for w in rb.get("warn") or []:
        if str(w).endswith("会被挡"):
            _no(s, str(w)[:-len("：会被挡")] if str(w).endswith("：会被挡") else str(w),
                "新仓倍数 0" if "新仓倍数 0" in str(w) else "决算前" if "決算" in str(w) or "决算" in str(w) else "会被挡")
    if mult is not None and float(mult) <= 0 and not any("新仓倍数 0" in x for x in s["why"]):
        _no(s, "规则现在不开新仓（新仓倍数 0）：手动买入 / 加仓也会被挡", "新仓倍数 0")
    w = el_block.get(code)
    if w and not hard:
        _no(s, f"资格检查：{w}", "资格检查")
    w = tb_stock.get(code)
    if w:
        _no(s, f"立花买不了：{w}", "立花买不了")
    if q > 0 and close > 0 and q > close * (1 + gap / 100):
        _no(s, f"现价 ¥{q:,g} 比收盘 ¥{close:,g} 高 {q / close - 1:+.1%}，超过 {gap:g}%：盘中不买（与开盘买入同一个上限）", "涨太多")


def _money(s: dict, cash: float, fund: float, px: float, lot: int, eq: float, held: int, unit: str, cap: float | None = None) -> None:
    """④ 钱：现金够几个单元、加上能卖来凑钱的核心 ETF 够几个单元；最多到总权益（手动买入 / 加仓的上限，MO.MANUAL_CAP_PCT）。"""
    if px <= 0:
        _no(s, "没有价格（执行器下一次运行之后才有）：算不了", "没有价格")
        return
    k1, k2 = lots(cash, px, lot), lots(cash + max(0.0, fund), px, lot)
    top = int(math.floor(eq * (cap or MO.MANUAL_CAP_PCT / 100) / px / lot + 1e-9)) * lot - int(held) if eq > 0 else k2 * lot
    mx = max(0, min(k2 * lot, top))
    if k2 <= 0:
        _no(s, f"现在能用的现金 ¥{cash:,.0f}" + (f" + 能卖来凑钱的核心 ETF 约 ¥{fund:,.0f}" if fund > 0 else "")
            + f" 不够买 1 个单元（{lot:,} {unit} ≈ ¥{lot_cost(px, lot):,.0f}）", "钱不够")
        return
    if mx <= 0:
        _no(s, "已经到总权益的上限：不能再加", "到上限")
        return
    s["max_qty"] = mx if s["n"] else 0
    _note(s, f"现金够 {k1 * lot:,} {unit}" + (f"，加上卖核心 ETF 凑钱最多 {k2 * lot:,} {unit}" if k2 > k1 else "")
          + f"（1 个单元 {lot:,} {unit} ≈ ¥{lot_cost(px, lot):,.0f}）")


def _miss(rows: list, side: str) -> str:
    """不能的那几只：「；不能：7203 トヨタ自動車（今天已有单）…」（代码带名字）。"""
    xs = [f"{r['label']}（{r[side]['short'] or '不能'}）" for r in rows]
    return ("；不能：" + "、".join(xs)) if xs else ""


def chip(r: dict) -> str:
    """持仓卡片的小标记：「今天还能卖 ✓ / 买 ✗（钱不够）」（两边都 ✓：同一只当天只下一笔 → 写「二选一」）。"""
    s, b = r["sell"], r["buy"]
    sv = OK if s["n"] else f"{NG}（{s['short'] or '不能'}）"
    bv = OK if b["n"] else f"{NG}（{b['short'] or '不能'}）"
    return f"今天还能卖 {sv} / 买 {bv}" + ("（二选一：同一只当天只下一笔）" if s["n"] and b["n"] else "")


def lines(rm: dict, limit: int = 40) -> list[str]:
    """命令行 / 日志用的几行（manual list 的末尾）：标题、时段、每只（代码带名字）、为什么是这个数。"""
    out = [rm["headline"] + f"（{rm['note']}）", "  " + rm["market"]["line"]]
    for w in rm.get("gates") or []:
        out.append(f"  ★ {w}")
    for w in rm.get("notes") or []:
        out.append(f"  · {w}")
    ov = rm["overall"]
    out.append(f"  买 {ov['buy_left']['n']}：{ov['buy_left']['why']}")
    out.append(f"  卖 {ov['sell_left']['n']}：{ov['sell_left']['why']}")
    out.append(f"  共 {ov['trades_left']['n']}：{ov['trades_left']['why']}")
    n = 0
    for r in rm["per_ticker"].values():
        if r.get("cand"):
            continue
        n += 1
        if n > limit:
            out.append("  …")
            break
        out.append(f"  - {r['label']}：{r['chip']}")
        for side, w in (("sell", "卖"), ("buy", "买")):
            x = r[side]
            if not x["n"] and x["why"]:
                out.append(f"      {w}：{x['why'][0]}" + (f"（{x['next']}）" if x.get("next") and x["next"] not in x["why"][0] else ""))
    c = rm.get("cands") or {}
    if c.get("n"):
        g = "、".join(f"{k} {v} 只" for k, v in sorted((c.get("groups") or {}).items(), key=lambda kv: -kv[1]))
        out.append(f"  选股页的候选 {c['n']} 只：名额与钱都够的 {c['ok']} 只" + (f"；不能：{g}" if g else "")
                   + "（只是数，不是建议；买不买是你的决定）")
    out.append(f"  差金決済：{SAKIN_URL}（2026-10-15 核对）")
    return out


__all__ = ["room", "market", "phase", "sakin", "cash_now", "lots", "lot_cost", "fundable", "chip", "lines", "NOTE", "SAKIN_URL"]
