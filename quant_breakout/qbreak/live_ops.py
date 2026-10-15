"""live_ops.py — 实盘执行器的人工操作（立花实盘缺口盘点 B 组：B1 撤单、B2 状态不明的单的候选、B3 持仓核对 / 人工代下登记）。

B1 撤单（UnifiedExecutor.cancel_orders / cancel_book；命令 bash scripts/liveu.sh cancel | halt-cancel，面板「今天的单」的「撤单」）：
   只撤执行器自己今天的、还挂着的单（SENT / PARTIAL；立花：有注文番号）。撤完用 order_status 再确认 → 记 CANCELLED（不算受理中、
   不算状态不明）+ 已经成交的股数；第二天早上的对账照立花的实际成交记账（再查一次 order_status）：
     撤掉的卖单 = 没成交 → 规则明天还要卖就照常再下（与「没成交」同一处理）；撤掉的买单不再买（信号只在那天开盘有效）；
     手动指令的单被撤 → 那条指令也撤回（之后不再下；已经成交的部分照记）。
   HALT 时也可以撤（撤单只会减少风险）。模拟账户：只撤还在排队、成交日 09:00 开盘之前的寄付单（PaperBroker.cancel_pending）；
   盘中的手动单当场成交，撤不了。
B2 状态不明的单的候选（unknown_candidates，只读）：注文一覧（CLMOrderList）里同代码、同买卖、股数相同或更少的单 →
   按受付时刻接近排序；附上可以照抄的登记命令草稿（bash scripts/liveu.sh --broker tachibana --resolve …）。登记仍要你确认。
B3 持仓核对（reconcile_report，只读）与人工代下登记（adopt）：立花 API / Mac 出故障那天在立花网站照「今天的单」下了单 →
   第二天早上之前登记进账本（止损按引擎的新仓算法；先备份账本），执行器之后照常。
撤单（cancel / halt-cancel）、人工代下登记（adopt）只在你在对话里明确说时由 Claude 运行（与 --resolve 同级）。
"""
from __future__ import annotations

import datetime as dt
import json
import math
import time
from dataclasses import asdict
from pathlib import Path

from .calendar_jp import is_trading_day, next_trading_day, now_jst
from .utils import atomic_write_text, read_json, setup_logging

log = setup_logging("live_ops")

CANCELLABLE = ("SENT", "PARTIAL")                    # 还挂着的单（受理了、还没全部成交）
OPEN_T = dt.time(9, 0)                               # 模拟账户的寄付单在开盘撮合（之后撤不了）
CLOSE_T = dt.time(15, 30)                            # 交易所收盘：之后今天没成交的单都已失效（不用撤）
POLLS, POLL_S = 5, 1.0                               # 撤单之后再确认几次 / 间隔几秒（立花的取消是异步的：取消中 → 取消完了）
MANUAL_REASONS = ("manual", "manual_trim", "manual_add", "manual_buy")
STATUS_TEXT = {"PLANNED": "计划", "SENDING": "发送中", "SENT": "已下单（等成交）", "PARTIAL": "部分成交", "FILLED": "已成交",
               "UNFILLED": "没成交", "DEFERRED": "等开盘后", "MISSED": "没下（错过）", "SKIPPED": "不下", "BLOCKED": "被挡",
               "REJECTED": "被拒", "EXPIRED": "已失效", "ERROR": "状态不明", "RESOLVED": "已登记", "CANCELLED": "已撤单"}
CANCEL_HINT = "已经成交的部分撤不了；撤掉的卖单如果规则明天还要卖会再下；撤掉的个股买单不再买"
CANCEL_HINT_CORE = ("核心 ETF 的单：已经成交的部分撤不了；下一次决策照规则 / 闲置资金比例重新算目标，可能再买 / 再卖"
                    "（要少拿用「闲置资金比例」）")
RESOLVE_NOTE = ("Claude 只在你确认之后登记（与 --resolve 同级）；还挂着的单（等成交）等它成交 / 失效、或在立花网站撤掉之后再登记成交数")
SPLIT_KS = (2, 3, 4, 5, 10, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10)   # 常见的拆股 / 合并比例（持仓核对给可能原因用）


def _sleep(s: float) -> None:
    time.sleep(s)


def _g(o, k: str, d=None):
    """ExecOrder 或 dict 的字段。"""
    return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)


def _unit(o) -> str:
    return "口" if _g(o, "kind") == "core" else "股"


def _side(o) -> str:
    return "买" if _g(o, "side") == "BUY" else "卖"


def _lab(t) -> str:
    """给人看的票：「7203.T」→「7203 トヨタ自動車」（查不到名字只写代码；空 → 空。2026-10-15 用户：只写代码不知道是哪只）。
    cid、注文番号、登记命令草稿（adopt / --resolve）照旧只写代码。"""
    from .names import label
    return label(t) if t else ""


def _labq(t, s: str) -> str:
    """票后面紧跟数量：「1545 纳斯达克 100：4,110 口」（名字可能以数字结尾，直接接数量读不出哪个是口数；names.qty，2026-10-15 复核）。"""
    from .names import qty
    return qty(t, s) if t else s


def fill_day_of(book: dict | None) -> dt.date | None:
    """账本当前决策的成交日（决策日的下一个交易日）。"""
    d = ((book or {}).get("state") or {}).get("last_date")
    try:
        return next_trading_day(dt.date.fromisoformat(str(d))) if d else None
    except ValueError:
        return None


def how_text(o) -> str:
    """这笔单的下法（面板「今天的单」/ 命令行）：寄付成行 / 寄付指値 / 开盘后 / 盘中 / 错过寄付后当日限价。"""
    ph = _g(o, "phase") or "morning"
    if ph == "now":
        return "盘中"
    if ph == "late":
        return "错过寄付 → 当日限价"
    if ph == "open" or _g(o, "status") == "DEFERRED":
        return "开盘后（当日限り指値）"
    return "寄付指値" if _g(o, "side") == "BUY" else "寄付成行"


# ══════════════════════════ 还没发出的买单开盘时下不下得成（只读；面板「交易」的数字与「不会下单」）══════════════════════════
UNSENT = ("PLANNED", "DEFERRED")                     # 还没发到交易所（重试 / 开盘后补单时才下）
AT_EXCH = ("SENDING", "SENT", "PARTIAL")             # 已经发到（正在发到）交易所
LIVE = UNSENT + AT_EXCH


def px_band(px: float) -> tuple[float, float]:
    """前日終値 px → (跌停价, 涨停价)（JPX 制限値幅：开盘价出不了这个范围）。"""
    from .tick import price_limit_jp
    w = price_limit_jp(float(px))
    return max(float(px) - w, 0.0), float(px) + w


def cash_hi(book: dict | None, tag: str | None) -> float:
    """开盘时能用的现金的上限（unfunded_buys 用）：账本现金、模拟账户的券商现金、今天的券商快照的余力 取大（看不到的入金不算漏）。
    面板「交易」的「不会下单（预计）」与固定口数 / 恢复按规则的确认框、提交说明同一个数（2026-10-15 复核：以前只在面板里）。"""
    from . import paths
    v = [float(((book or {}).get("state") or {}).get("cash_jpy") or 0)]
    if tag:
        try:
            if tag.startswith("paper"):
                v.append(float((read_json(paths.state_dir() / f"live_unified_{tag}_broker.json", {}) or {}).get("cash") or 0))
            snap = read_json(paths.out_dir() / f"broker_snapshot_{tag}.json", {}) or {}
            if str(snap.get("at") or "")[:10] == now_jst().date().isoformat():
                v.append(float(snap.get("buying_power") or 0))
        except (TypeError, ValueError, OSError):
            pass
    return max(v)


def unfunded_buys(book: dict | None, asked=(), drop=(), cash: float | None = None) -> dict[str, dict]:
    """当前决策里还没发出的买单（DEFERRED / PLANNED）里，开盘时一定下不成的 → {cid: 说明用的数}（只读、纯函数；2026-10-15 用户
    「撤单后 / 没有执行下单等等的话交易处的数字不显示」：撤了凑钱的卖单、现金只有 192 円，1482.T 的买单还算「等开盘后」）。
    执行器开盘后补单（_place_deferred：立花按「开盘价 ×(1+滑点) + 手续费 ≤ 余力」、模拟账户 PaperBroker._buy_now 按同一条减到整单元）
    减到 0 → 不下（放弃 / 资金不足）。开盘价开盘前不知道 → 保守地估（只有一定下不成才算）：
      能用的钱的上限 = cash（默认账本现金；面板传入账本现金 / 券商余力取大）+ 登记了还没对上的入金
                       + 还会成交的卖单（没撤、没在撤单中：asked / drop 之外）按涨停价全部卖掉 + 已经成交的卖出按涨停价
      一单元的下限   = 单元（核心 ETF 按账本记的，没记 = 1；个股 100 股）× 跌停价（不算滑点、手续费）
    上限 < 下限 → 下不成。估不出（没有参考价）→ 不下结论（不列）。只是展示，不改执行器的行为。
    asked = 已经写了撤单的单的 cid；drop = 当成撤掉的卖单（撤单确认框「撤掉之后哪些买单下不成」）。"""
    st = (book or {}).get("state") or {}
    d = st.get("last_date")
    cur = [o for o in (book or {}).get("orders") or [] if o.get("decided_on") == d]
    if not any(o.get("side") == "BUY" and o.get("status") in UNSENT for o in cur):
        return {}
    off = {str(x) for x in asked} | {str(x) for x in drop}
    c0 = float(st.get("cash_jpy") or 0) if cash is None else float(cash)
    c0 += sum(float(f.get("jpy") or 0) for f in (book or {}).get("flows") or []          # 入金登记了、现金同步还没对上：券商那边可能已经能用
              if isinstance(f, dict) and float(f.get("jpy") or 0) > 0 and not f.get("seen_after") and not f.get("in_start"))
    sells, gone = 0.0, []
    for o in cur:
        if o.get("side") != "SELL":
            continue
        px = float(o.get("ref_px") or 0)
        if px <= 0:
            return {}                                       # 估不出这笔卖出的钱：不下结论
        live = o.get("status") in LIVE and str(o.get("cid")) not in off
        sells += (int(o.get("sent_qty") or o.get("qty") or 0) if live else int(o.get("filled_qty") or 0)) * px_band(px)[1]
        if not live and int(o.get("filled_qty") or 0) < int(o.get("sent_qty") or o.get("qty") or 0):
            gone.append(o)                                  # 撤了 / 在撤单中 / 没成交 / 没下的卖单（说明「资金来源的卖单已撤」用）
    lots = ((book or {}).get("core_rule") or {}).get("lot") or {}
    out = {}
    for o in cur:
        if o.get("side") != "BUY" or o.get("status") not in UNSENT:
            continue
        px = float(o.get("ref_px") or 0)
        lo = px_band(px)[0] if px > 0 else 0.0
        if o.get("kind") == "core":
            lot = int(lots.get(o.get("ticker")) or 1)
        else:
            from .tick import lot_size
            lot = lot_size(str(o.get("ticker")), "JP")
        need = lot * lo
        if need > 0 and c0 + sells < need - 1e-9:
            out[str(o.get("cid"))] = {"cash": c0, "sells": sells, "need": need, "lot": lot, "gone": gone}
    return out


# ══════════════════════════ 资金依赖（fund_src）：凑钱的卖单没成交 → 靠它的钱的买单当场重算（D2 / D4；2026-10-15）══════════════════════════
# 2026-10-15 事故：07:40 照「固定 1482 678 口」排了「卖 1545 4,110 口（寄付）→ 买 1482 678 口（现金不够 → 等开盘后）」，08:05 撤了卖单 →
# 买单成了孤儿（撤不了、仍写「开盘后再下」、模拟账户第二天早上被拒、不推送）。执行器排单时把凑钱的卖单记在买单的 fund_src 上；
# 卖单到了没成交的终态（撤单 / 被拒 / 失效 / 没成交 / 今天不会再试的没发出）→ fund_cascade 按实际现金重算这笔买单：
# 够 → 照常；够一部分 → 减股；不够一单元 → 不下（SKIPPED）+ ★ 交易 提醒。撤单那一刻（cancel_core）、发单结果（_send）、
# 开盘撮合 / 开盘后补单、对账都调它；面板的撤单确认框用 apply=False 预览同一个结果。旧账本没有 fund_src → 不推测（照旧）。
DEP_OPEN = ("PLANNED", "BLOCKED", "DEFERRED")        # 依赖单还没发到交易所：级联只动这些
SRC_WORD = {"CANCELLED": "已撤", "REJECTED": "被拒", "EXPIRED": "已失效", "UNFILLED": "没成交", "SKIPPED": "没下",
            "MISSED": "没下", "RESOLVED": "登记为没成交", "BLOCKED": "没发出", "PLANNED": "没发出"}
CUTOFF_T = dt.time(8, 55)                            # 寄付注文的最后时刻（live_unified.MORNING_CUTOFF）：之后早上被挡的单不再重试
LATE_UNTIL = dt.time(9, 30)                          # 立花早上错过寄付的个股卖单：09:05 / 09:20 的开盘后运行补发（之后不再试）
BUY_PAD, SELL_PAD = 0.005, 0.01                      # 估算：买按参考价 ×(1+0.5%)（滑点 + 手续费）；还会成交的卖单按参考价 ×(1−1%)
LIVE_SRC = ("SENDING", "SENT", "PARTIAL", "FILLED", "ERROR", "DEFERRED")


def _set(o, **kw) -> None:
    """ExecOrder 或 dict 都能改。"""
    for k, v in kw.items():
        if isinstance(o, dict):
            o[k] = v
        else:
            setattr(o, k, v)


def blocked_retry(o, now: dt.datetime | None, fill: dt.date | None = None) -> bool:
    """还没发出的单（PLANNED / BLOCKED）今天还会再发吗（D4；2026-10-15）：盘中的单（phase now）不会（一会儿再试的是新的一笔）；
    成交日之前 / 08:55 之前的早上的单会（08:35 的重试 / 面板的 --retry 再发）；立花早上错过寄付的个股卖单 09:05 / 09:20 的开盘后运行补成
    当日限价卖。其余（08:55 之后的被挡、成交日已过）不会。now=None → 当成还会（不下结论）。"""
    if (_g(o, "phase") or "morning") == "now":
        return False
    if now is None:
        return True
    if fill is not None:
        if now.date() < fill:
            return True
        if now.date() > fill:
            return False
    if now.time() < CUTOFF_T:
        return True
    from .live_unified import CUTOFF_TEXT
    return (_g(o, "side") == "SELL" and (_g(o, "kind") or "stock") == "stock" and _g(o, "status") == "BLOCKED"
            and not _g(o, "broker_id") and (_g(o, "phase") == "late" or CUTOFF_TEXT in str(_g(o, "note") or ""))
            and now.time() < LATE_UNTIL)


def src_done(o, now: dt.datetime | None, fill: dt.date | None = None) -> bool:
    """凑钱的卖单已经不会（全部）成交了 = 它的钱不会（全部）来：撤了 / 被拒 / 失效 / 没成交 / 没下 / 今天不会再发的没发出。
    还在交易所 / 发送中 / 状态不明 / 已成交 → 不算。"""
    s = _g(o, "status")
    if s in LIVE_SRC:
        return False
    if s in ("PLANNED", "BLOCKED"):
        return not blocked_retry(o, now, fill)
    return int(_g(o, "filled_qty") or 0) < int(_g(o, "sent_qty") or _g(o, "qty") or 0)


def _src_dead(s, cid: str, now, fill, dead) -> bool:
    """凑钱的卖单 cid（s = 账本里的那笔；找不到 → 当成不会来）没了吗；dead：另外当成「撤掉」的卖单（确认框预览）。"""
    if s is None:
        return True
    if str(cid) in dead:
        return int(_g(s, "filled_qty") or 0) < int(_g(s, "sent_qty") or _g(s, "qty") or 0)
    return src_done(s, now, fill)


def fund_srcs(o, orders) -> list:
    """买单 o 的凑钱卖单（账本里找得到的；旧账本没有 fund_src → []）。"""
    by = {str(_g(x, "cid")): x for x in orders}
    return [by[str(c)] for c in (_g(o, "fund_src") or []) if str(c) in by]


def orphan(o, orders, now: dt.datetime | None, fill: dt.date | None = None, dead=()) -> bool:
    """还没发出的买单（PLANNED / BLOCKED / DEFERRED）的凑钱卖单全部不会成交了（孤儿：开盘后要用的钱不会来）。旧账本（没有 fund_src）→ False。"""
    src = [str(c) for c in (_g(o, "fund_src") or [])]
    if _g(o, "side") != "BUY" or _g(o, "status") not in DEP_OPEN or not src:
        return False
    by = {str(_g(x, "cid")): x for x in orders}
    dead = {str(c) for c in dead or ()}
    return all(_src_dead(by.get(c), c, now, fill, dead) for c in src)


def busy(o, orders, now: dt.datetime | None, fill: dt.date | None = None) -> bool:
    """这笔单让它那只票算「今天已经有执行器的单」吗（D4；执行器 now_phase、手动指令的「什么时候下」、面板共用一处；2026-10-15）：
    成交过（含部分）/ 在交易所 / 发送中 / 状态不明 → 算；等开盘后的（DEFERRED）钱还会来 → 算，凑钱的卖单都没了（孤儿）→ 不算；
    计划 / 被挡的今天还会再发 → 算；撤了 / 不下 / 被拒 / 失效、今天不会再发的被挡、盘中没到交易所的 → 不算（撤单之后当天还能写新的指令马上下）。
    「同一只票当天执行器只下一笔」的规则不变（成交过的照算）。"""
    if int(_g(o, "filled_qty") or 0) > 0:
        return True
    s = _g(o, "status")
    if s in ("SENDING", "SENT", "PARTIAL", "FILLED", "ERROR"):
        return True
    if s == "DEFERRED":
        return not orphan(o, orders, now, fill)
    if s in ("PLANNED", "BLOCKED"):
        return blocked_retry(o, now, fill) and not orphan(o, orders, now, fill)
    return False


def src_text(srcs, dead=()) -> str:
    """「凑钱的卖单 卖 1545 纳斯达克 100：4,110 口 已撤（08:05）」（代码带名字；撤单的时刻从单的说明里取）。"""
    import re
    dead = {str(c) for c in dead or ()}
    parts = []
    for s in srcs:
        n = int(_g(s, "sent_qty") or _g(s, "qty") or 0)
        st = _g(s, "status")
        w = "要撤" if str(_g(s, "cid")) in dead and st in CANCELLABLE + UNSENT + ("BLOCKED",) else SRC_WORD.get(st, STATUS_TEXT.get(st, st))
        m = re.search(r"你撤了单（(\d\d:\d\d)", str(_g(s, "note") or ""))
        q = int(_g(s, "filled_qty") or 0)
        parts.append(f"{_side(s)} {_labq(_g(s, 'ticker'), f'{n:,} {_unit(s)}')} {w}" + (f"（{m.group(1)}）" if m else "")
                     + (f"（已成交 {q:,}）" if q else ""))
    return "凑钱的卖单 " + ("、".join(parts) if parts else "（账本里找不到）")


def _lot_est(o, book: dict | None) -> int:
    """一单元：核心 ETF 按账本记的（core_rule.lot，没记 = 1），个股按东证的売買単位。"""
    if (_g(o, "kind") or "stock") == "core":
        return int((((book or {}).get("core_rule") or {}).get("lot") or {}).get(_g(o, "ticker")) or 1)
    from .tick import lot_size
    return int(lot_size(str(_g(o, "ticker")), "JP"))


def _need_est(o, q: int) -> float:
    """买 q 股 / 口大约要的钱：参考价（个股 = 信号日收盘，核心 = 决策日收盘；没有 → 限价）×(1+0.5%)。"""
    px = float(_g(o, "ref_px") or 0) or float(_g(o, "limit") or 0)
    return px * int(q) * (1 + BUY_PAD)


def fund_cascade(orders, *, cash, now: dt.datetime | None, need=None, lot_of=None, book: dict | None = None,
                 partial: bool = True, reduce: bool = True, dead=(), queued: bool = False, apply: bool = True,
                 fill: dt.date | None = None, add_live: bool = True) -> list[dict]:
    """凑钱的卖单没了（任何一笔到了没成交的终态）的、还没发出的买单 → 按现在能用的钱重算（D2；2026-10-15）。
    能用的钱 = cash（券商余力 / 现金；可以是函数：有要重算的买单才取）− 模拟账户排队的寄付买单（queued）+ 还会成交的凑钱卖单按参考价 ×(1−1%)
    （按单的先后：前面还会下的、还没发出的买单先占）。每笔：够 → 照常；不够 → partial 时减到放得下的整单元（reduce=False：留给开盘时券商减），
    一单元也放不下 → 不下（SKIPPED）。apply：改单（状态 / 股数 / 说明；凑钱卖单里没了的从 fund_src 去掉）；False → 只预览（撤单确认框）。
    dead：另外当成「撤掉」的卖单 cid（预览）；add_live=False：还会成交的卖单的钱已经在 cash 里（模拟账户开盘撮合之后）。→ [{o, act: keep | reduce | skip, qty, was, srcs, note, free}]。"""
    dead = {str(c) for c in dead or ()}
    by = {str(_g(x, "cid")): x for x in orders}
    hit = {}
    for o in orders:
        src = [str(c) for c in (_g(o, "fund_src") or [])]
        if _g(o, "side") != "BUY" or _g(o, "status") not in DEP_OPEN or not src:
            continue
        gone = [c for c in src if _src_dead(by.get(c), c, now, fill, dead)]
        if gone:
            hit[id(o)] = (gone, [c for c in src if c not in gone])
    if not hit:
        return []
    need = need or _need_est
    lot_of = lot_of or (lambda o: _lot_est(o, book))
    pool = float(cash() if callable(cash) else cash)
    if queued:                                             # 模拟账户：排队的寄付买单开盘先撮合（PaperBroker 的现金还没扣它）
        pool -= sum(need(o, int(_g(o, "sent_qty") or _g(o, "qty") or 0)) for o in orders
                    if _g(o, "side") == "BUY" and _g(o, "status") == "SENT" and (_g(o, "phase") or "morning") == "morning")
    live = {}
    for o in orders:                                       # 还会成交的凑钱卖单：开盘卖出的钱（每笔只算一次）
        if not add_live or _g(o, "side") != "BUY" or _g(o, "status") not in DEP_OPEN:
            continue
        for c in _g(o, "fund_src") or []:
            s = by.get(str(c))
            if s is not None and str(c) not in dead and not src_done(s, now, fill) and _g(s, "status") != "FILLED":
                left = int(_g(s, "sent_qty") or _g(s, "qty") or 0) - int(_g(s, "filled_qty") or 0)
                live[str(c)] = max(0, left) * float(_g(s, "ref_px") or 0) * (1 - SELL_PAD)
    pool += sum(live.values())
    out = []
    for o in orders:
        if _g(o, "side") != "BUY" or _g(o, "status") not in DEP_OPEN:
            continue
        n0 = int(_g(o, "qty") or 0)
        if id(o) not in hit:
            if busy(o, orders, now, fill):                 # 别的还会下的买单（排在前面的先占钱）
                pool -= need(o, n0)
            continue
        gone, keep = hit[id(o)]
        srcs = [by[c] for c in gone if c in by]
        st = src_text(srcs, dead) + (f"（另有 {len(gone) - len(srcs)} 笔账本里找不到）" if len(srcs) < len(gone) else "")
        u = _unit(o)
        lot = max(1, int(lot_of(o) or 1))
        free = pool
        if n0 > 0 and need(o, n0) <= pool + 1e-9:
            act, q = "keep", n0
        else:
            q = (n0 // lot) * lot if partial else 0
            while q > 0 and need(o, q) > pool + 1e-9:
                q -= lot
            act = "skip" if q <= 0 else ("reduce" if reduce else "keep")
            if act == "keep":
                q = n0
        when = "开盘后下" if _g(o, "status") == "DEFERRED" else "照常下"
        if act == "skip":
            note = (f"{st} → 不会下（现在能用的钱约 ¥{max(free, 0):,.0f}，按参考价买 {lot:,} {u}要约 ¥{need(o, lot):,.0f}）")
        elif act == "reduce":
            note = f"{st} → 按现在能用的钱（约 ¥{max(free, 0):,.0f}）减到 {q:,} {u}（原计划 {n0:,} {u}；{when}）"
        else:
            note = f"{st}；现在能用的钱够（约 ¥{max(free, 0):,.0f}）：照常（{when}）"
        if act != "skip":
            pool -= need(o, q if act == "reduce" else n0)
        out.append({"o": o, "act": act, "qty": int(q if act != "skip" else 0), "was": n0, "srcs": srcs, "note": note[:300],
                    "free": round(free, 2)})
        if apply:
            if act == "skip":
                _set(o, status="SKIPPED", note=note[:300], fund_src=[])
            else:
                _set(o, note=note[:300], fund_src=list(keep), **({"qty": int(q)} if act == "reduce" else {}))
    return out


def cascade_events(res: list[dict]) -> list[tuple[str, str]]:
    """fund_cascade 的结果 → [(级别, 文字)]：不下 / 减股 = ★ 交易 warn（推送），照常 = info。"""
    ev = []
    for r in res:
        o = r["o"]
        what = f"买 {_labq(_g(o, 'ticker'), f'{int(r['was']):,} {_unit(o)}')}"
        if r["act"] == "keep":
            ev.append(("info", f"{what}：{r['note']}"))
        else:
            ev.append(("warn", f"★ 交易：{what}：{r['note']}"))
    return ev


def cascade_rows(res: list[dict]) -> list[dict]:
    """fund_cascade 的结果 → 可以存 / 显示的字典（不带单对象）。"""
    return [{"cid": str(_g(r["o"], "cid")), "ticker": _g(r["o"], "ticker"), "kind": _g(r["o"], "kind") or "stock", "act": r["act"],
             "qty": r["qty"], "was": r["was"], "note": r["note"]} for r in res]


def deps_of(o, orders) -> list:
    """撤这笔卖单会影响的买单：fund_src 里有它、还没发出的（执行器字段；旧账本 → []）。"""
    c = str(_g(o, "cid"))
    return [x for x in orders if _g(x, "side") == "BUY" and _g(x, "status") in DEP_OPEN
            and c in [str(y) for y in (_g(x, "fund_src") or [])]]


def next_decision_text(now: dt.datetime) -> str:
    """下一次决策（交易日 07:40）是哪天 →「MM/DD 07:40」（panel._next_decision 同一个算法）。"""
    d0 = now.date()
    d1 = d0 if is_trading_day(d0) and now.time() < dt.time(7, 40) else next_trading_day(d0)
    return f"{d1:%m/%d} 07:40"


def _core_fix_of(book: dict | None, tag: str | None = None) -> dict:
    """现在的固定口数（含还没读的 corefix：manual_orders.core_fixed；取不到 → 账本里的）。"""
    try:
        from .manual_orders import core_fixed
        return dict(core_fixed(book, tag) or {})
    except Exception:                                      # noqa: BLE001  只是说明
        return {t: int(u) for t, u in ((((book or {}).get("manual") or {}).get("core_fix")) or {}).items()}


def cancel_hint(o, book: dict | None, now: dt.datetime, tag: str | None = None) -> str:
    """撤这笔单之后会怎样（M5：按单的来源选；确认框 / 命令行 / 推送共用；2026-10-15）。以前一律写个股版「撤掉的卖单如果规则明天还要卖会再下」，
    固定口数排出的核心单撤了、固定口数仍有效 → 下一次决策会再排同样的单，提示却叫你改闲置资金比例（固定的 ETF 不跟比例）。"""
    s, t, side, kind = _g(o, "status"), _g(o, "ticker"), _g(o, "side"), (_g(o, "kind") or "stock")
    head = "还没发到交易所：撤了执行器就不再发" if s in UNSENT + ("BLOCKED",) else "已经成交的部分撤不了"
    nd = next_decision_text(now)
    r = _g(o, "reason") or ""
    if r in MANUAL_REASONS:
        return f"{head}；手动指令的单：那条指令也撤回（之后不再下；已经成交的部分照记）"
    if r == "manual_fund":
        return f"{head}；这是盘中为手动买入凑钱的核心 ETF 卖单：那条买入默认一起撤回（钱不够就不买）"
    if kind == "core":
        fx = _core_fix_of(book, tag)
        d = ((book or {}).get("state") or {}).get("last_date")
        mine = [x for x in (book or {}).get("orders") or [] if x.get("decided_on") == d]
        if t in fx:
            return (f"{head}；{_lab(t)} 手动固定 {int(fx[t]):,} 口仍有效 → {nd} 的决策还会再排同样的单"
                    f"（不想要 → 「持仓」里 {_lab(t)} 下面点「恢复按规则」）")
        drv = [x.get("ticker") for x in mine if x.get("kind") == "core" and x.get("side") == "BUY" and x.get("ticker") in fx]
        if side == "SELL" and drv:
            fl = "、".join(f"{_lab(x)} {int(fx[x]):,} 口" for x in dict.fromkeys(drv))
            return (f"{head}；这笔卖出是为手动固定（{fl}）凑钱：固定口数仍有效 → {nd} 的决策还会再排同样的换仓"
                    f"（不想要 → 「持仓」里那只 ETF 下面点「恢复按规则」）")
        if r == "manual_core":
            return f"{head}；照闲置资金比例调的单：比例不变 → {nd} 的决策照比例再算目标，可能再买 / 再卖"
        return f"{head}；核心 ETF 的单：{nd} 的决策照规则 / 闲置资金比例重新算目标，可能再买 / 再卖（要少拿用「闲置资金比例」）"
    if side == "SELL":
        return f"{head}；规则明天还要卖就会再下（与「没成交」同一处理）"
    return f"{head}；撤掉的个股买单不再买（信号只在那天开盘有效）"


# ══════════════════════════ B1 撤单 ══════════════════════════
def cancel_why(o, book: dict, now: dt.datetime, paper: bool) -> str | None:
    """这笔单现在能不能撤：能 → None；不能 → 理由。面板（显示「撤单」按钮）、手动指令的检查、执行器共用。
    执行器自己还没发到交易所的单（PLANNED / DEFERRED：计划 / 等开盘后）也能撤 = 执行器不再发（D2；2026-10-15：以前撤了凑钱的卖单，
    等开盘后的买单撤不了）：成交日当天、立花在收盘（15:30）之前。"""
    st = _g(o, "status")
    unsent = st in UNSENT
    if st not in CANCELLABLE and not unsent:
        return f"状态是「{STATUS_TEXT.get(st, st)}」：只撤还挂着的单（已下单 / 部分成交）或执行器还没发出的单（计划 / 等开盘后）"
    if _g(o, "decided_on") != ((book or {}).get("state") or {}).get("last_date"):
        return "不是当前决策的单（已经对账过了）"
    f = fill_day_of(book)
    if f != now.date():
        return f"不是今天的单（成交日 {f}）"
    if unsent:
        if not paper and now.time() >= CLOSE_T:
            return "已经收盘（15:30）：这笔今天不会再发了，不用撤"
        return None
    if paper:
        if (_g(o, "phase") or "morning") != "morning":
            return "模拟账户：盘中 / 开盘后的单当场成交了，撤不了"
        if now.time() >= OPEN_T:
            return "模拟账户：寄付单已经在 09:00 开盘撮合（第二天早上记账），撤不了"
        return None
    if not _g(o, "broker_id"):
        return "没有注文番号：撤不了（在立花网站的注文一覧核对）"
    if now.time() >= CLOSE_T:
        why = "已经收盘（15:30）：今天没成交的单都已失效，不用撤"
        it = _manual_item(book, o) if _g(o, "side") == "SELL" and _g(o, "reason") in ("manual", "manual_trim") else None
        if it is not None and not it.get("cancel_req"):        # 手动卖出没卖完的部分明天开盘会再卖：要停就撤回指令（G16；2026-10-14）
            why += f"；手动卖出没成交的部分明天开盘会再卖 → 不想再卖就在「手动指令」撤回 {it.get('id')}"
        return why
    return None


def _manual_item(book: dict, o) -> dict | None:
    """这笔手动单对应的手动指令（账本 manual.items）。"""
    m = (book or {}).get("manual") or {}
    items = m.get("items") or {}
    key = {"manual_trim": "trims", "manual_add": "adds", "manual_buy": "buys"}.get(_g(o, "reason"))
    t = _g(o, "ticker")
    if key:
        rid = ((m.get(key) or {}).get(t) or {}).get("id")
        return items.get(rid) if rid else None
    trim_id = ((m.get("trims") or {}).get(t) or {}).get("id")
    for it in items.values():
        if (it.get("ticker") == t and it.get("status") == "placed" and it.get("kind") in ("sell", "trim", "adjust")
                and it.get("id") != trim_id):
            return it
    return None


def _withdraw_manual(book: dict, o, now: dt.datetime) -> str | None:
    """手动指令的单被撤 → 那条指令也撤回（之后不再下；对账之后结束）。返回说明 / None。"""
    if _g(o, "reason") not in MANUAL_REASONS:
        return None
    it = _manual_item(book, o)
    if it is None or it.get("cancel_req"):
        return None
    it["cancel_req"] = f"撤单 {_g(o, 'cid')}"
    where = "执行器还没发出的单" if "还没发到交易所" in str(_g(o, "note") or "") or "执行器不再发" in str(_g(o, "note") or "") else "交易所的单"
    it["msg"] = f"{now:%m/%d %H:%M} 你撤了{where}：这条指令也撤回（之后不再下；已经成交的部分照记）"
    try:                                                   # 指令写的是什么（「卖出全部 7203 トヨタ自動車」；2026-10-15）
        from .manual_orders import describe
        what = describe(it)
    except Exception:                                      # noqa: BLE001  只是说明：取不到就只写 id
        what = ""
    return f"手动指令 {it.get('id')}" + (f"（{what}）" if what else "") + " 也撤回（之后不再下）"


def _cancel_one(o, b, paper: bool, now: dt.datetime, source: str, polls: int) -> tuple[str, str]:
    """撤一笔 → ("done" | "failed" | "skipped", 说明)。成功：o.status = CANCELLED（立花：filled_qty / filled_px 记撤单时的成交）。
    执行器还没发出的单（PLANNED / DEFERRED）：不连券商，记 CANCELLED = 执行器不再发（D2；2026-10-15）。"""
    n = int(_g(o, "sent_qty") or _g(o, "qty") or 0)
    who = f"，{source}" if source else ""
    if _g(o, "status") in UNSENT:
        _set(o, status="CANCELLED", fund_src=[],
             note=f"你撤了单（{now:%H:%M}{who}）：还没发到交易所，执行器不再发"[:300])
        return "done", _g(o, "note")
    if paper:
        fn = getattr(b, "cancel_pending", None)
        if fn is None or not fn(o.cid):
            return "failed", "模拟券商里没有这笔排队的单（已经撮合？）：没撤"
        o.status = "CANCELLED"
        o.note = f"你撤了单（{now:%H:%M}{who}）：还在排队，没成交，全部撤掉"[:300]
        return "done", o.note
    if getattr(b, "dry_run", False):
        return "skipped", "dry-run：不撤"
    ok = False
    try:
        ok = bool(b.cancel_order(o.broker_id, o.order_date))
    except Exception as e:                                 # noqa: BLE001  适配器本身不抛；抛了也当没撤成，下面再查一次状态
        log.warning("撤单出错 %s：%s", o.cid, type(e).__name__)
    r, err = None, ""
    for i in range(max(1, int(polls))):
        try:
            r = b.order_status(o.broker_id, o.order_date)
        except Exception as e:                             # noqa: BLE001
            r, err = None, f"{type(e).__name__}"
            break
        if not ok or r.get("final"):
            break
        if i < polls - 1:
            _sleep(POLL_S)
    fin = str((r or {}).get("final") or "")
    q = int((r or {}).get("filled_qty") or 0) if r else None
    px = float((r or {}).get("avg_px") or 0) if r else 0.0
    name = str((r or {}).get("status") or "") or fin
    if r is not None and (fin == "FILLED" or (q is not None and n > 0 and q >= n)):
        o.note = f"{o.note}；撤单时已经全部成交（{q:,}/{n:,}），撤不了".lstrip("；")[:300]
        return "skipped", f"已经全部成交（{q:,}/{n:,} {_unit(o)}），撤不了（不用撤；明天早上照常对账）"   # 不算撤单失败
    if fin == "CANCELLED" or (ok and fin in ("EXPIRED", "REJECTED")):   # 撤单受理、单到了终态（成交的比发出的少）
        o.status = "CANCELLED"
        if q is not None:
            o.filled_qty, o.filled_px = int(q), float(px if q else 0.0)
        got = (f"已成交 {o.filled_qty:,}/{n:,} {_unit(o)} @ ¥{o.filled_px:,.2f}，其余撤掉" if o.filled_qty
               else "没成交，全部撤掉")
        o.note = f"你撤了单（{now:%H:%M}{who}）：{got}"[:300]
        return "done", o.note
    if ok and not fin:                                     # 撤单受理了、但单还没到终态（取消中 / 正在撮合）：状态不改成「已撤单」
        if q:                                              # （撤单可能失败：那时单还挂着；明天早上的对账按实际成交记）
            o.status, o.filled_qty, o.filled_px = "PARTIAL", int(q), float(px)
        o.note = (f"你撤了单（{now:%H:%M}{who}）：撤单已受理，立花还在处理"
                  + (f"（{name}）" if name else "") + (f"，查状态失败：{err}" if err and r is None else "")
                  + "；过一会儿在面板 / 立花网站看是否撤掉（还挂着可以再撤）；明天早上的对账按实际成交记")[:300]
        return "pending", o.note
    if fin in ("EXPIRED", "REJECTED"):
        return "skipped", f"立花那边已经{'失效' if fin == 'EXPIRED' else '被拒'}（{name}）：不用撤（明天早上照常对账）"
    return "failed", ("撤单失败（立花没受理" + (f"；查状态也失败：{err}" if err else "") + "）：单可能还挂着 → "
                      "在立花网站 / 手机网站（https://kabuka.e-shiten.jp/mfds_smp.php）撤，或稍后再试")


def cancel_core(orders: list, book: dict, get_broker, cids=None, *, paper: bool, now: dt.datetime, source: str = "",
                polls: int = POLLS, deps=None, cash=None, need=None, lot_of=None, tag: str | None = None,
                reserve: float = 0.0, queued: bool | None = None) -> dict:
    """撤单的核心（执行器 / 不建引擎的 cancel_book 共用）。orders：ExecOrder 列表（原地改）；get_broker()：要撤交易所的单时才取券商
    （没有要撤的 / 只撤执行器还没发出的单就不连券商）；cids=None → 今天全部还挂着的执行器单（只撤交易所里的：停并撤单的口径）。
    撤了凑钱的卖单（D2；2026-10-15）：deps（{cid: "cancel" | "keep"} 或一个值）="cancel" → 靠它的钱、还没发出的买单一起撤
    （CANCELLED，手动指令也撤回）；其余（"keep" / 没写）→ fund_cascade 按现在能用的钱重算（照常 / 减股 / 不下 + ★ 交易 提醒）。
    盘中为手动买入凑钱的核心卖单（fund_wait）被撤 → 那条买入默认也撤回（M16；deps="keep" 时留着、按现金重新算）。
    cash：重算用的钱（数或函数；没给 → 模拟账户 = 模拟券商的现金 − 排队的寄付买单，立花 = 券商余力 − 出金预留 reserve，没连券商 → cash_hi）。
    返回 {"done", "pending", "failed", "skipped": [{cid, ticker, side, qty, why, kind, hint}], "events": [(级别, 文字)],
    "by_cid": {cid: (结果, 说明)}, "fund": [cascade_rows]}。"""
    res = {"done": [], "pending": [], "failed": [], "skipped": [], "events": [], "by_cid": {}, "fund": []}
    by = {o.cid: o for o in orders}
    targets = []
    if cids is None:
        targets = [o for o in orders if o.status in CANCELLABLE and cancel_why(o, book, now, paper) is None]
        if not targets:
            res["note"] = "今天没有还挂着的执行器单（不用撤）"
    else:
        for c in dict.fromkeys(str(x) for x in cids):
            o = by.get(c)
            why = "账本里没有这笔单（已经对账过了 / cid 写错？）" if o is None else cancel_why(o, book, now, paper)
            if why:
                rec = {"cid": c, "ticker": _g(o, "ticker") if o else "", "side": _g(o, "side") if o else "",
                       "qty": int(_g(o, "sent_qty") or _g(o, "qty") or 0) if o else 0, "why": why,
                       "kind": (_g(o, "kind") or "stock") if o else ""}
                res["skipped"].append(rec)
                res["by_cid"][c] = ("skipped", why)
                continue
            targets.append(o)
    hints = {o.cid: cancel_hint(o, book, now, tag) for o in targets}       # 撤之前算（状态还没改）
    holder: dict = {}

    def broker():
        if "b" not in holder:
            holder["b"] = get_broker()
        return holder["b"]
    if any(o.status in CANCELLABLE for o in targets):
        broker()
    mode = deps if isinstance(deps, dict) else {}
    fill = fill_day_of(book)
    for o in targets:
        kind, why = _cancel_one(o, holder.get("b"), paper, now, source, polls)
        n = int(o.sent_qty or o.qty)
        rec = {"cid": o.cid, "ticker": o.ticker, "side": o.side, "qty": n, "why": why, "kind": o.kind or "stock", "hint": hints[o.cid]}
        if kind in ("done", "pending"):
            w = _withdraw_manual(book, o, now)
            if w:
                rec["why"] = f"{why}；{w}"
        res[kind].append(rec)
        res["by_cid"][o.cid] = (kind, rec["why"])
        lvl = "info" if kind in ("done", "pending") else "warn"
        res["events"].append((lvl, f"撤单 {_side(o)} {_labq(o.ticker, f'{n:,} {_unit(o)}')}（{o.cid}）："
                                   + {"done": "撤掉了 —— ", "pending": "撤单已受理 —— "}.get(kind, "没撤 —— ") + rec["why"]))
        if kind not in ("done", "pending") or o.side != "SELL":
            continue
        m = mode.get(o.cid) if isinstance(deps, dict) else deps
        if m == "cancel":                                  # 你选了「一起撤买单」：靠它的钱、还没发出的买单一起撤（执行器不再发）
            for x in deps_of(o, orders):
                h = cancel_hint(x, book, now, tag)
                x.status, x.fund_src = "CANCELLED", []
                x.note = f"你撤了单（{now:%H:%M}{'，' + source if source else ''}）：和凑钱的卖单 {_lab(o.ticker)} 一起撤，执行器不再发"[:300]
                xr = {"cid": x.cid, "ticker": x.ticker, "side": x.side, "qty": int(x.qty), "why": x.note, "kind": x.kind or "stock",
                      "hint": h}
                w = _withdraw_manual(book, x, now)
                if w:
                    xr["why"] = f"{x.note}；{w}"
                res["done"].append(xr)
                res["by_cid"][x.cid] = ("done", xr["why"])
                res["events"].append(("info", f"撤单 买 {_labq(x.ticker, f'{int(x.qty):,} {_unit(x)}')}（{x.cid}）：撤掉了 —— {xr['why']}"))
        for it in (((book or {}).get("manual") or {}).get("items") or {}).values():   # 盘中为手动买入凑钱的核心卖单（M16）
            if o.cid not in [str(c) for c in it.get("fund_wait") or []] or it.get("status") != "pending":
                continue
            if m == "keep":                                # 你选了只撤卖单：买入留着，执行器下一次按现金重新算
                it.pop("fund_wait", None)
                it["msg"] = f"{now:%m/%d %H:%M} 凑钱的核心 ETF 卖单 {_lab(o.ticker)} 被你撤了：这条买入按现在的现金重新算（钱不够就不买）"
                continue
            it.update(status="cancelled", msg=f"{now:%m/%d %H:%M} 凑钱的核心 ETF 卖单 {_lab(o.ticker)} 被你撤了：这条买入也撤回（之后不再下）")
            for f in ("wait", "hold", "tried", "fund_wait"):
                it.pop(f, None)
            res["events"].append(("info", f"手动指令 {it.get('id')}（买 {_lab(it.get('ticker'))}）：凑钱的卖单被撤 → 也撤回"))
    if res["done"] or res["pending"]:
        q = paper if queued is None else queued

        def cash_now() -> float:
            if cash is not None:
                return float(cash() if callable(cash) else cash)
            if paper:
                return float(broker().cash())
            b_ = holder.get("b")
            if b_ is not None and hasattr(b_, "cash"):
                return float(b_.cash()) - float(reserve or 0)
            return cash_hi(book, tag) - float(reserve or 0)
        try:
            fr = fund_cascade(orders, cash=cash_now, now=now, need=need, lot_of=lot_of, book=book, partial=True,
                              queued=q, fill=fill)
        except Exception as e:                             # noqa: BLE001  重算失败不影响撤单本身：记下、09:05 / 开盘撮合再判断
            fr = []
            res["events"].append(("warn", f"★ 交易：撤单之后重算靠这笔卖出的钱的买单没算成（{type(e).__name__}：{e}）：开盘后补单时再判断"))
        res["fund"] = cascade_rows(fr)
        res["events"] += cascade_events(fr)
    return res


def cancel_text(res: dict) -> list[str]:
    """撤单结果的几行（命令行 / 通知）：「撤掉了：卖 1545 纳斯达克 100 4,110 口（U…）—— …」（代码 + 名字、口 / 股；2026-10-15）。"""
    out = []
    for k, head in (("done", "撤掉了"), ("pending", "撤单已受理（立花还在处理）"), ("failed", "★ 没撤成"), ("skipped", "没撤")):
        for r in res.get(k) or []:
            q = int(r.get("qty") or 0)
            what = " ".join(x for x in ({"BUY": "买", "SELL": "卖"}.get(r.get("side"), ""), _lab(r.get("ticker")),
                                        f"{q:,} {'口' if r.get('kind') == 'core' else '股'}" if q else "") if x)
            out.append(f"{head}：{what}（{r['cid']}）—— {r['why']}")
    for r in res.get("fund") or []:                       # 靠撤掉的卖单的钱的买单：重算的结果（D2；2026-10-15）
        u = "口" if r.get("kind") == "core" else "股"
        out.append(("★ " if r.get("act") != "keep" else "") + f"买 {_labq(r.get('ticker'), f'{int(r.get('was') or 0):,} {u}')}：{r.get('note')}")
    if res.get("note"):
        out.append(res["note"])
    return out


def _reserve_of(book: dict | None, paper: bool) -> float:
    """出金预留（立花：到账前不拿它买；模拟账户 0）。"""
    if paper:
        return 0.0
    try:
        from .live_unified import reserve_jpy
        return float(reserve_jpy(book) or 0)
    except Exception:                                      # noqa: BLE001
        return 0.0


def cancel_book(path, get_broker, cids=None, *, paper: bool, tag: str | None = None, requests: bool = False,
                clock=None, source: str = "", polls: int = POLLS) -> dict:
    """不建引擎的撤单（run.py live-u --cancel / --phase cancel）：读账本 → 撤 → 存账本（存之前先备份）。
    requests=True（--phase cancel，面板叫）：读手动指令文件里的「撤单」指令（kind cancel_order），撤完把结果记进那条指令。
    返回 cancel_core 的结果 + "items"（处理了的撤单指令 [(id, 状态, 说明)]）。"""
    from . import manual_orders as MO
    from .book_backup import backup
    from .live_unified import ExecOrder, _np
    clock = clock or now_jst
    now = clock()
    book = read_json(path, {}) or {}
    msgs: list[tuple[str, str]] = []
    items: list[dict] = []
    if requests and tag:
        man = MO.Manual(book, tag, clock)
        msgs = man.ingest(only=("cancel_order",))
        items = man.pending(("cancel_order",))
        cids = [str(it.get("cid") or "") for it in items]
    orders = [ExecOrder.from_dict(o) for o in book.get("orders") or []]
    if requests and not items:
        res = {"done": [], "pending": [], "failed": [], "skipped": [], "events": [], "by_cid": {}, "fund": [],
               "note": "没有要处理的撤单指令"}
    else:
        deps = {str(it.get("cid") or ""): it.get("deps") for it in items if it.get("deps")} if items else None
        res = cancel_core(orders, book, get_broker, cids, paper=paper, now=now, source=source, polls=polls, deps=deps, tag=tag,
                          reserve=_reserve_of(book, paper))
    done_items = []
    for it in items:
        kind, why = res["by_cid"].get(str(it.get("cid") or ""), ("skipped", "没处理"))
        it.update(status="done" if kind in ("done", "pending") else "rejected", done_on=now.date().isoformat(), msg=why[:300])
        done_items.append((it["id"], it["status"], it["msg"]))
    res["items"] = done_items
    if not (res["done"] or res["pending"] or res["failed"] or res["skipped"] or msgs or done_items):
        return res                                         # 什么都没变：不写账本
    backup(path, force=True)                               # 改账本之前先备份（qbreak/book_backup.py）
    stamp = now.isoformat(timespec="seconds")
    ev = list(book.get("events") or []) + [{"at": stamp, "level": lv, "msg": m} for lv, m in msgs + res["events"]]
    book["events"] = ev[-500:]
    book["orders"] = [asdict(o) for o in orders]
    book["updated"] = stamp
    atomic_write_text(path, json.dumps(book, ensure_ascii=False, indent=1, default=_np))
    return res


# ══════════════════════════ B2 状态不明的单的候选 ══════════════════════════
def _ts(v) -> dt.datetime | None:
    """受付时刻：ISO（账本的 sent_at）或立花的 YYYYMMDDHHMMSS → datetime（不带时区，按 JST 比较）；读不了 → None。"""
    s = str(v or "").strip()
    if not s:
        return None
    try:
        if s.isdigit() and len(s) >= 12:
            return dt.datetime.strptime(s[:14].ljust(14, "0"), "%Y%m%d%H%M%S")
        t = dt.datetime.fromisoformat(s)
        return t.replace(tzinfo=None)
    except ValueError:
        return None


def _num(v, cast=float, d=0):
    try:
        return cast(float(str(v).strip())) if str(v or "").strip() else d
    except (TypeError, ValueError):
        return d


def _sent_day(o) -> dt.date | None:
    """这笔单发出的营业日：立花受理应答的営業日（order_date，YYYYMMDD），没有就用发出时刻（sent_at）的日期。"""
    od = str(_g(o, "order_date") or "").strip()
    if od.isdigit() and len(od) == 8:
        try:
            return dt.datetime.strptime(od, "%Y%m%d").date()
        except ValueError:
            pass
    t0 = _ts(_g(o, "sent_at"))
    return t0.date() if t0 else None


def unknown_candidates(unknown: list, all_orders: list, broker, today: dt.date | None = None) -> list[dict]:
    """状态不明的单（SENDING / ERROR）→ 注文一覧（broker.open_orders(strict=True)：立花 CLMOrderList，今天）里的候选：
    同代码、同买卖、股数相同或更少（拆出零股时会少）；账本里别的单已经用了的注文番号不算。排序：注文番号 = 这笔记下的 → 股数相同 →
    受付时刻离这笔发出的时刻近 → 注文番号。只读（不下单、不改账本）。注文一覧读不了 → 抛出（调用方处理）。
    这笔单不是今天（JST）发的（执行器第二天早上才因它停下）→ 注文一覧里本来就没有它：不找候选，标 stale（发出的日期），
    文字让你去立花网站的注文約定照会查那一天的记录（不给「成交 0」的草稿）。受付时刻和发出日期不是同一天的行不算候选。
    返回 [{cid, ticker, side, qty, note, sent_at, stale, candidates: [{order_no, status, final, filled_qty, filled_px, qty, price, time}]}]。"""
    if not unknown:
        return []
    today = today or now_jst().date()
    spec = getattr(broker, "spec", None)
    rows = None
    used = {str(_g(o, "broker_id") or "") for o in all_orders if _g(o, "broker_id")}
    fstate = getattr(broker, "final_state", None)
    out = []
    for o in unknown:
        code, side = str(_g(o, "ticker") or "").split(".")[0], _g(o, "side")
        want = int(_g(o, "sent_qty") or _g(o, "qty") or 0)
        mine = str(_g(o, "broker_id") or "")
        t0 = _ts(_g(o, "sent_at"))
        day = _sent_day(o)
        base = {"cid": str(_g(o, "cid")), "ticker": str(_g(o, "ticker")), "side": side, "qty": want,
                "kind": _g(o, "kind") or "stock", "note": str(_g(o, "note") or "")[:200], "sent_at": str(_g(o, "sent_at") or "")}
        if day is not None and day != today:
            out.append({**base, "stale": day.isoformat(), "candidates": []})
            continue
        if rows is None:
            rows = broker.open_orders(strict=True) or []
        cands = []
        for r in rows:
            if spec is None or str(r.get(spec.r_list_code) or "").strip() != code:
                continue
            if str(r.get(spec.r_list_side) or "").strip() != (spec.side_buy if side == "BUY" else spec.side_sell):
                continue
            q = _num(r.get(spec.r_list_qty), int)
            no = str(r.get(spec.r_list_order_no) or "").strip()
            if q <= 0 or (want and q > want) or (no in used and no != mine):
                continue
            code_st = str(r.get(spec.r_list_status_code) or "").strip()
            tm = _ts(r.get(spec.r_list_time))
            if tm is not None and day is not None and tm.date() != day:
                continue                                    # 受付是别的日子的单：不是这笔
            fq = _num(r.get(spec.r_list_filled_qty), int)
            cands.append({"order_no": no, "qty": q, "price": _num(r.get(spec.r_list_price)),
                          "filled_qty": fq, "filled_px": _num(r.get(spec.r_list_filled_px)) if fq else 0.0,
                          "status": str(r.get(spec.r_list_status) or "") or (spec.status_names or {}).get(code_st, code_st),
                          "final": (fstate(code_st) if fstate else "") or "",
                          "time": tm.strftime("%m/%d %H:%M:%S") if tm else "",
                          "_k": (no != mine or not mine, q != want, tm is None or t0 is None,
                                 abs((tm - t0).total_seconds()) if tm and t0 else 0.0, no)})
        cands.sort(key=lambda c: c["_k"])
        for c in cands:
            c.pop("_k", None)
        out.append({**base, "candidates": cands[:5]})
    return out


def resolve_draft(c: dict, cid: str, broker_args: str = "tachibana") -> str:
    """一个候选 → 可以照抄的登记命令草稿（成交股数 / 均价按注文一覧；还挂着的单要等它结束再登记）。"""
    px = float(c.get("filled_px") or 0)
    return (f"bash scripts/liveu.sh --broker {broker_args} --resolve {cid} --filled {int(c.get('filled_qty') or 0)} "
            f"--px {px:g}")


def unknown_text(cands: list[dict] | None, broker_args: str = "tachibana", drafts: bool = True) -> list[str]:
    """状态不明的单与候选的几行（命令行 / 通知正文 / 面板）。"""
    out = []
    for u in cands or []:
        if u.get("error"):
            out.append(f"・注文一覧读不了：{u['error']}（去立花网站的注文一覧核对）")
            continue
        unit = "口" if u.get("kind") == "core" else "股"
        n_ = f"{int(u.get('qty') or 0):,} {unit}"
        out.append(f"・{u['cid']}：{'买' if u.get('side') == 'BUY' else '卖'} {_labq(u['ticker'], n_)}"
                   + (f"（{u['note']}）" if u.get("note") else ""))
        cs = u.get("candidates") or []
        if u.get("stale"):
            md = u["stale"][5:].replace("-", "/")
            out.append(f"  这笔单是 {md} 发的：API 的注文一覧只有今天的单（找不到不代表没受理）→ 在立花网站「注文約定照会」查 {md} 的记录"
                       "（受理了没有、成交多少股、均价），再登记"
                       + (f"：bash scripts/liveu.sh --broker {broker_args} --resolve {u['cid']} --filled <股数> --px <均价>"
                          if drafts else ""))
            continue
        if not cs:
            out.append("  注文一覧里没有同代码、同买卖的单 → 多半没受理（确认后登记成交 0："
                       + (f"bash scripts/liveu.sh --broker {broker_args} --resolve {u['cid']} --filled 0 --px 0" if drafts else "--filled 0")
                       + "）")
            continue
        for n, c in enumerate(cs, 1):
            live = not c.get("final")
            fill = (f"约定 {int(c['filled_qty']):,}/{int(c['qty']):,} {unit} @ ¥{float(c['filled_px']):,.2f}" if c.get("filled_qty")
                    else f"没约定（{int(c['qty']):,} {unit}）")
            out.append(f"  {n}. 注文番号 {c['order_no']}" + (f"  受付 {c['time']}" if c.get("time") else "")
                       + f"  {c.get('status') or '—'}  {fill}" + ("  ← 还挂着" if live else ""))
            if drafts:
                out.append("     登记草稿：" + resolve_draft(c, u["cid"], broker_args)
                           + ("（还挂着：等它成交 / 失效、或在立花网站撤掉之后再登记）" if live else ""))
    return out


# ══════════════════════════ B3 持仓核对 / 人工代下登记 ══════════════════════════
def _split_guess(book_q: int, broker_q: int) -> float | None:
    if book_q <= 0 or broker_q <= 0:
        return None
    r = broker_q / book_q
    for k in SPLIT_KS:
        if abs(r - k) < 1e-9:
            return k
    return None


def reconcile_report(book: dict, held: dict, managed=(), now: dt.datetime | None = None, broker_args: str = "tachibana") -> dict:
    """账本 vs 券商持仓（只读）：held = broker.positions()（{票: Position(qty, avg_px)}）；managed = 执行器管的票（股票池 + 核心 ETF）。
    返回 {"rows": [{ticker, kind, book_qty, book_cost, broker_qty, broker_cost, same, causes, draft}], "bad": 不一致的行,
    "foreign": [(票, 股数)]（执行器不管的持仓）, "splits", "orders"（当前决策的单）, "mismatch"（早上记下的不一致）, "lines"}。"""
    now = now or now_jst()
    st = (book or {}).get("state") or {}
    pos = st.get("pos") or {}
    core = {t: int(u) for t, u in (st.get("core_units") or {}).items() if int(u or 0)}
    exp: dict[str, tuple[int, float, str]] = {t: (int(p.get("shares") or 0), float(p.get("entry_px") or 0), "stock")
                                             for t, p in pos.items()}
    for t, u in core.items():
        exp[t] = (exp.get(t, (0, 0.0, "core"))[0] + u, 0.0, "core")
    h = {t: (int(getattr(p, "qty", 0) or 0), float(getattr(p, "avg_px", 0) or 0)) for t, p in (held or {}).items()
         if int(getattr(p, "qty", 0) or 0) > 0}
    mg = set(exp) | set(managed or ())
    d = st.get("last_date")
    orders = [o for o in (book or {}).get("orders") or [] if o.get("decided_on") == d]
    splits = list((book or {}).get("splits") or []) + [{**s, "pre": True} for s in (book or {}).get("split_pre") or []]
    f = fill_day_of(book)
    traded = f is not None and (now.date() > f or (now.date() == f and now.time() >= OPEN_T))   # 今天的单可能已经成交
    rows, bad = [], []
    for t in sorted(set(exp) | (set(h) & mg)):
        eq_, ec, kind = exp.get(t, (0, 0.0, "core" if t in core else "stock"))
        hq, hc = h.get(t, (0, 0.0))
        row = {"ticker": t, "kind": kind, "book_qty": eq_, "book_cost": round(ec, 2), "broker_qty": hq, "broker_cost": round(hc, 2),
               "same": eq_ == hq, "causes": [], "draft": "", "pending": False}
        if not row["same"]:
            mine = [o for o in orders if o.get("ticker") == t]
            unk = [o for o in mine if o.get("status") in ("SENDING", "ERROR")]
            act = [o for o in mine if o.get("status") in ("SENT", "PARTIAL", "FILLED")]
            buy_ = sum(int(o.get("sent_qty") or o.get("qty") or 0) for o in act if o.get("side") == "BUY")
            sell_ = sum(int(o.get("sent_qty") or o.get("qty") or 0) for o in act if o.get("side") == "SELL")
            if not unk and traded and act and -sell_ <= hq - eq_ <= buy_:
                row["pending"] = True                       # 差的部分正好可以是执行器今天的单成交了：明天早上的对账记上，不是不一致
                row["causes"].append("执行器今天的单成交了（" + "、".join(f"{o['cid']} {STATUS_TEXT.get(o.get('status'), o.get('status'))}"
                                                                         for o in act)
                                     + "）：账本明天早上对账时自动记上 → 不用登记、不会挡下单")
                rows.append(row)
                continue
            if unk:
                row["causes"].append("状态不明的单（" + "、".join(o["cid"] for o in unk) + "）可能已经成交：先 bash scripts/liveu.sh unknown "
                                     f"--broker {broker_args} 看候选")
            live = [o for o in mine if o.get("status") in ("SENT", "PARTIAL", "FILLED", "CANCELLED", "EXPIRED")]
            if live and traded:
                row["causes"].append("今天的单可能已经成交（账本明天早上对账之后才记上；今天开盘之后看本来就会不同）")
            k = _split_guess(eq_, hq)
            sp = [s for s in splits if s.get("ticker") == t]
            if k or sp:
                row["causes"].append("公司行为（拆股 / 合并" + (f" 1:{k:g}" if k else "") + "）？"
                                     + ("（账本里登记过：" + "、".join(f"{s.get('date')} 1:{float(s.get('k') or 0):g}" for s in sp) + "）"
                                        if sp else "（公司行为数据还没反映？）"))
            if not row["causes"] or not (unk or (live and traded)):
                row["causes"].append("人工交易（在立花网站 / 手机网站上自己买卖了）？")
            diff = hq - eq_
            if diff and not unk and not k and not (act and traded):   # 执行器今天的单也成交了一部分：差额里混着它的成交 → 不给草稿
                px = f"{hc:g}" if diff > 0 and eq_ == 0 and hc > 0 else "<均价>"
                row["draft"] = (f"bash scripts/liveu.sh adopt --broker {broker_args} {t.split('.')[0]} "
                                f"{'BUY' if diff > 0 else 'SELL'} {abs(diff)} {px}")
            bad.append(row)
        rows.append(row)
    foreign = [(t, q) for t, (q, _) in sorted(h.items()) if t not in mg]
    lines = [f"持仓核对（{now:%m/%d %H:%M} JST；只读：不下单、不改账本）：账本决策日 {d or '—'}"]
    if not rows:
        lines.append("  账本和券商都没有执行器管的持仓")
    for r in rows:
        u = "口" if r["kind"] == "core" else "股"
        cost_b = f"，成本 ¥{r['book_cost']:,.2f}" if r["book_cost"] else ""
        cost_h = f"，概算簿価 ¥{r['broker_cost']:,.2f}" if r["broker_cost"] else ""
        mark = "✓" if r["same"] else ("…" if r.get("pending") else "★")
        lines.append(f"  {mark} {_lab(r['ticker'])}：账本 {r['book_qty']:,} {u}{cost_b} ／ 券商 {r['broker_qty']:,} {u}{cost_h}")
        for c in r["causes"]:
            lines.append(f"      可能原因：{c}")
        if r["draft"]:
            lines.append(f"      登记草稿（确认是人工交易之后；均价用立花「約定照会」的实际成交价）：{r['draft']}")
    if foreign:
        lines.append("  执行器不管的持仓（不影响下单）：" + "、".join(_labq(t, f"{q:,} 股") for t, q in foreign))
    mm = (book or {}).get("broker_mismatch") or {}
    if mm.get("text"):
        lines.append(f"  早上记下的不一致（{mm.get('date')}）：{mm['text']}")
    for s in splits[-5:]:
        lines.append(f"  拆股登记：{_lab(s.get('ticker'))} {s.get('date')} 1:{float(s.get('k') or 0):g}"
                     + ("（成交日当天按拆股后下的单）" if s.get("pre") else ""))
    if orders:
        lines.append("  今天的单（当前决策）：")
        for o in orders:
            lim = f" 限价 ¥{float(o['limit']):,g}" if o.get("limit") and o.get("side") == "BUY" else ""
            n_ = f"{int(o.get('sent_qty') or o.get('qty') or 0):,} {'口' if o.get('kind') == 'core' else '股'}"
            lines.append(f"    {'买' if o.get('side') == 'BUY' else '卖'} {_labq(o.get('ticker'), n_)}"
                         f"（{how_text(o)}{lim}）→ {STATUS_TEXT.get(o.get('status'), o.get('status'))}")
    if bad:
        lines.append("  ★ 有不一致：执行器的下一次运行会挡住全部下单。确认原因之后：人工交易 → adopt 登记（Claude 只在你确认之后运行）；"
                     "状态不明的单 → 先登记那笔（--resolve）；拆股 → 等公司行为数据反映（或在 Mac 对话里说明）")
    elif any(r.get("pending") for r in rows):
        lines.append("  ✓ 没有要处理的不一致：差的部分是执行器今天的单成交了（明天早上对账记上）")
    else:
        lines.append("  ✓ 账本与券商一致（执行器管的票）")
    return {"rows": rows, "bad": bad, "foreign": foreign, "splits": splits, "orders": orders, "mismatch": mm or None,
            "lines": lines}


def adopt(eng, book: dict, ticker: str, side: str, qty: int, px: float, day: str | None = None, note: str = "",
          now: dt.datetime | None = None, separate: bool = False) -> dict:
    """人工代下登记（用户在立花网站上实际成交的单 → 账本；只在你明确说时由 Claude 运行）。eng：用账本状态建好的引擎（行情含成交日之前的
    K 线：新仓的止损按开仓前一根 K 线的 ATR，与引擎的新仓相同 —— UnifiedEngine._open）。改的是 eng.st 与 book（调用方存账本、之前备份）。
      SELL 个股：减持仓（全卖 → 清掉持仓与待卖；部分 → 减股数），成交记进交易记录；
      BUY 个股：新持仓（止损按引擎的新仓算法、entry_date = 成交日、峰值 = 均价；占名额，满了拒绝）；已经持有 → 并进原来的持仓
               （成本加权平均，止损 / 峰值不变，与手动加仓相同）；
      BUY / SELL 核心 ETF：改口数（成交记进核心 ETF 的记录）。
    现金按成交额 ± 手续费估算变动（与执行器记成交相同）；下一次早上的现金同步照常以券商的买付可能額为准对齐。
    拒绝（ValueError）：数量不是一手的整数倍（卖出账本记下的零股除外）、代码不在股票池也不是核心 ETF（执行器不管的票不用登记）、
    日期在未来 / 不是交易日、卖的比账本多、买个股时名额已满；执行器当前决策这只同方向有已发出 / 已成交的单（成交日起）——
    它的成交第二天早上对账自动记，除非 separate=True（你确认这是在立花网站另外下的单）。"""
    import pandas as pd
    now = now or now_jst()
    st = eng.st
    t = str(ticker or "").strip().upper()
    if t and "." not in t:
        t += ".T"
    side = str(side or "").strip().upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("买卖要写 BUY 或 SELL")
    try:
        qty, px = int(qty), float(px)
    except (TypeError, ValueError):
        raise ValueError("股数要是整数、均价要是数字") from None
    if qty <= 0 or not (math.isfinite(px) and px > 0):
        raise ValueError("股数、均价都要大于 0")
    d = dt.date.fromisoformat(str(day)) if day else now.date()
    if d > now.date():
        raise ValueError(f"日期 {d} 在未来：只登记已经成交的单")
    if not is_trading_day(d):
        raise ValueError(f"{d} 不是交易日：日期写错了？")
    core = t in eng.core_set or t in st.core_units
    held = t in st.pos
    if not (core or held or (t.endswith(".T") and t in eng.col)):
        raise ValueError(f"{_lab(t)} 不在股票池、也不是核心 ETF：执行器不管的票不用登记（持仓核对也不看它）")
    if t not in eng.col:
        raise ValueError(f"行情里没有 {_lab(t)}：登记不了（先在 Mac 对话里说明）")
    mine = [o for o in (book or {}).get("orders") or [] if o.get("decided_on") == st.last_date and o.get("ticker") == t
            and o.get("side") == side]
    unk = [o for o in mine if o.get("status") in ("SENDING", "ERROR")]
    if unk:
        raise ValueError(f"执行器今天这只有状态不明的单（{'、'.join(o['cid'] for o in unk)}）：先核对、登记那笔（--resolve；"
                         "bash scripts/liveu.sh unknown 看候选），别把执行器的成交当成人工代下重复登记")
    f = fill_day_of(book)
    act = [o for o in mine if o.get("status") in ("SENT", "PARTIAL", "FILLED")]
    if act and (f is None or d >= f) and not separate:
        raise ValueError("执行器今天这只同方向也有单（" + "、".join(f"{o['cid']} {o.get('status')}" for o in act) + "）：它的成交明天早上"
                         "对账时自动记，别当成人工代下重复登记。确认这是你在立花网站另外下的单 → 加 --separate 再登记")
    warn = ""
    live = [o for o in mine if o.get("status") in ("SENT", "PARTIAL", "FILLED", "RESOLVED", "CANCELLED", "EXPIRED")]
    if live:
        warn = ("执行器今天这只也有单（" + "、".join(f"{o['cid']} {o.get('status')}" for o in live) + "）：它的成交明天早上对账时"
                "自动记 —— 这次登记的只能是你自己在立花网站上另外下的单")
    lot = int(eng.lots[eng.col[t]])
    odd = 0
    if side == "SELL" and held:
        odd = int(st.pos[t].shares) % lot if lot > 1 else 0
    elif side == "SELL" and core:
        odd = int(st.core_units.get(t, 0)) % lot if lot > 1 else 0
    if lot > 1 and qty % lot and not (side == "SELL" and odd and qty % lot == odd):
        raise ValueError(f"{qty:,} 不是一手（{lot:,}）的整数倍" + (f"（卖零股只能卖账本记下的 {odd:,} 股）" if odd else ""))
    # 成交日在行情里的位置：那天的 K 线还没有（今天盘中）→ 用最后一根（成交日照写 d）
    i_ge = int(eng.gidx.searchsorted(pd.Timestamp(d), side="left"))
    i = min(i_ge, len(eng.gidx) - 1)
    eng.prime(i_ge)                                       # 每只票在成交日之前的最后一根 K 线（新仓的 ATR 止损用）
    unit = "口" if core else "股"
    before = {"shares": int(st.pos[t].shares) if held else int(st.core_units.get(t, 0) or 0)}
    if core:
        have = int(st.core_units.get(t, 0) or 0)
        if side == "SELL" and qty > have:
            raise ValueError(f"账本里 {_lab(t)} 只有 {have:,} 口，卖不了 {qty:,} 口")
        eng._core_trade(t, side, qty, i, px=px)
        if eng.st.core_trades:
            r = list(eng.st.core_trades[-1])
            r[0] = d.isoformat()
            eng.st.core_trades[-1] = tuple(r)
        what = f"核心 ETF {_lab(t)} {'买' if side == 'BUY' else '卖'} {qty:,} 口 @ ¥{px:,g}（{have:,} → {int(st.core_units.get(t, 0)):,} 口）"
    elif side == "SELL":
        if not held:
            raise ValueError(f"账本里没有 {_lab(t)} 的持仓：卖出不用登记（执行器不管？）")
        ps = st.pos[t]
        if qty > int(ps.shares):
            raise ValueError(f"账本里 {_lab(t)} 只有 {int(ps.shares):,} 股，卖不了 {qty:,} 股")
        full = qty >= int(ps.shares)
        eng.sell_fill(t, qty, px, i, "adopted", part_note="（人工代下，部分）")
        if st.trades:
            st.trades[-1]["exit_date"] = d.isoformat()
        if full:
            st.pending_exit.pop(t, None)
        what = f"卖 {_labq(t, f'{qty:,} 股')} @ ¥{px:,g}（{'全部卖出' if full else f'剩 {int(st.pos[t].shares):,} 股'}）"
    elif held:
        eng.add_fill(t, qty, px, i)
        what = f"买 {_labq(t, f'{qty:,} 股')} @ ¥{px:,g}（并进原来的持仓：{before['shares']:,} → {int(st.pos[t].shares):,} 股，止损不变）"
    else:
        n_pos = len(st.pos)
        if n_pos >= int(eng.cfg.max_positions):
            raise ValueError(f"个股名额已满（{n_pos} 只，上限 {int(eng.cfg.max_positions)} 只）：先登记卖出的那只")
        eng._open(t, "JP", qty, px, i)
        ps = st.pos[t]
        ps.entry_date, ps.peak, ps.last_close = d.isoformat(), float(px), float(px)
        st.plan.pop(t, None)
        what = (f"买 {_labq(t, f'{qty:,} 股')} @ ¥{px:,g}（新持仓：止损 ¥{float(ps.stop_px):,.2f}，按引擎的新仓算法；之后规则照常离场）")
    rec = {"at": now.isoformat(timespec="seconds"), "date": d.isoformat(), "ticker": t, "side": side, "qty": int(qty),
           "px": round(float(px), 4), "unit": unit, "note": " ".join(str(note or "").split())[:200], "text": what}
    if warn:
        rec["warn"] = warn
    book.setdefault("adopted", []).append(rec)
    book["adopted"] = book["adopted"][-200:]
    book.setdefault("events", []).append({"at": rec["at"], "level": "warn",
                                          "msg": f"人工代下登记（用户确认）：{d} {what}" + (f"；{rec['note']}" if rec["note"] else "")})
    book["events"] = book["events"][-500:]
    return rec


def save_book(path, book: dict, st=None, now: dt.datetime | None = None) -> None:
    """把（改过的）账本写回：st 给了 → 状态换成它。原子写入，格式与执行器相同。"""
    from .live_unified import _np
    if st is not None:
        book["state"] = st.to_dict()
    book["updated"] = (now or now_jst()).isoformat(timespec="seconds")
    atomic_write_text(Path(path), json.dumps(book, ensure_ascii=False, indent=1, default=_np))


__all__ = ["CANCELLABLE", "STATUS_TEXT", "CANCEL_HINT", "CANCEL_HINT_CORE", "RESOLVE_NOTE", "cancel_why", "cancel_core", "cancel_book", "cancel_text",
           "DEP_OPEN", "SRC_WORD", "blocked_retry", "src_done", "fund_srcs", "orphan", "busy", "src_text", "fund_cascade",
           "cascade_events", "cascade_rows", "deps_of", "next_decision_text", "cancel_hint",
           "fill_day_of", "how_text", "unknown_candidates", "unknown_text", "resolve_draft", "reconcile_report", "adopt", "save_book"]
