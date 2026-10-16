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


def how_text(o, paper: bool = False) -> str:
    """这笔单的下法（面板「今天的单」/ 命令行）：寄付成行 / 寄付指値 / 开盘后 / 盘中 / 错过寄付后当日限价。
    模拟账户（D3；2026-10-15）：开盘后的买单写「开盘后（09:25 前后按开盘价）」—— 不是立花的当日限り指値，是面板 09:25 前后按 1 分钟线的开盘价撮合。"""
    ph = _g(o, "phase") or "morning"
    if ph == "now":
        return "盘中"
    if ph == "late":
        return "错过寄付 → 当日限价"
    if ph == "open" or _g(o, "status") == "DEFERRED":
        return "开盘后（09:25 前后按开盘价）" if paper else "开盘后（当日限り指値）"
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


def model_same(o, srcs) -> bool:
    """凑钱的卖单没成交、买单因此不下 / 少买 —— 这是规则自己的结果（与模型相同，不是 ★ 交易 的问题）吗（复核 tests F2，2026-10-16：
    规则的卖单开盘跌停没成交、规则的买单钱不够，以前写成「要撤 → 不会下」并推 ★ 交易、09:30 自检不通过）：
    买单与这些卖单都是规则的单（不是手动指令 / 固定口数 / 为它凑钱 / 闲置资金比例），卖单是行情原因没成交（没成交 / 失效），不是你撤的、不是被拒。"""
    srcs = list(srcs or [])
    return bool(srcs) and all(_g(x, "reason") not in MANUAL_REASONS + ("manual_fund",) and str(_g(x, "src") or "rule") == "rule"
                              for x in [o, *srcs]) and all(_g(x, "status") in ("UNFILLED", "EXPIRED") for x in srcs)


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
        same = model_same(o, srcs) and len(srcs) == len(gone)
        if act == "skip" and same:                         # 规则的卖单行情原因没成交、规则的买单钱不够：与模型相同（不推 ★ 交易）
            note = (f"{st} → 不下（现在能用的钱约 ¥{max(free, 0):,.0f}，买 {lot:,} {u}要约 ¥{need(o, lot):,.0f}）—— 与模型相同")
        elif act == "skip":
            note = (f"{st} → 不会下（现在能用的钱约 ¥{max(free, 0):,.0f}，按参考价买 {lot:,} {u}要约 ¥{need(o, lot):,.0f}）")
        elif act == "reduce":
            note = f"{st} → 按现在能用的钱（约 ¥{max(free, 0):,.0f}）减到 {q:,} {u}（原计划 {n0:,} {u}；{when}）"
        else:
            note = f"{st}；现在能用的钱够（约 ¥{max(free, 0):,.0f}）：照常（{when}）"
        if act != "skip":
            pool -= need(o, q if act == "reduce" else n0)
        out.append({"o": o, "act": act, "qty": int(q if act != "skip" else 0), "was": n0, "srcs": srcs, "note": note[:300],
                    "free": round(free, 2), "model": same})
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
        qty_txt = f"{int(r['was']):,} {_unit(o)}"            # 先算好数量文字（Python 3.10 / 3.11 不允许 f-string 里嵌套同种引号）
        what = f"买 {_labq(_g(o, 'ticker'), qty_txt)}"
        if r["act"] == "keep" or r.get("model"):          # 与模型相同的不下 / 照常：info（不推 ★ 交易）
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


# ══════════════════════════ 同一组（一起下的买单和卖单）：整组撤单（2026-10-16）══════════════════════════
# 2026-10-16 用户：「如果一起下的买单和卖单的话要可以一起进行撤单 而不是一个个撤单」—— 07:40 照固定口数排了「卖 1545（寄付，凑钱）+
# 买 1482（等开盘后）」，08:04 先撤了买单、14 秒后又点卖单的撤单：两次。现在按单的用途认「同一组」（不加新字段，今天已有的账本也认得）：
#   E1 拆成两笔的单（立花核心单的余数 cid + "-2"）；E2 早上的固定口数：core_fix 的买单 ↔ fix_fund 的卖单（phase 不是 now，两两相连）；
#   E3 盘中的固定口数：core_fix 的买单 ↔ core_rule.fix_fund[票].cids 与 fund_src 里 fix_fund 的卖单；E4 盘中的手动买入 / 加仓 ↔ fund_src 里
#   manual_fund 的卖单；E5 手动买入「从持仓平摊凑」/「全部换成」同一次写的个股卖出。
# 不算成员：规则的单、照闲置资金比例调的核心单（含「全部换成」比例 0% 的 ETF 卖单）、单独下的手动卖出、早上覆盖整个决策的 fund_src、
# 以前决策的单、没有 src 的旧账本。整组撤单：先撤买单，没有任何买单还可能花钱（成交过 / 还挂着 / 状态不明 / 你确认之后才出现）才撤卖单。
GROUP_POLLS = 10                                     # 整组撤单里买单的撤单：立花最多查 10 次（每次 1 秒）
GROUP_NEUTRAL = ("CANCELLED", "SKIPPED", "REJECTED", "EXPIRED", "UNFILLED", "MISSED", "RESOLVED")   # 这些状态 + 没成交 = 不再花钱
GROUP_OPEN = ("PLANNED", "DEFERRED", "BLOCKED", "SENDING", "SENT", "PARTIAL", "ERROR")             # 还没结束的单


def _grp_capable(o) -> bool:
    """这笔单能不能是「同一组」的成员（规则的单、照比例调的核心单、旧账本的核心单不能）。"""
    core = (_g(o, "kind") or "stock") == "core"
    r = str(_g(o, "reason") or "")
    if _g(o, "side") == "BUY":
        return (core and src_of(o) == "core_fix") or r in ("manual_buy", "manual_add")
    return (core and src_of(o) == "fix_fund") or r in ("manual_fund", "manual", "manual_trim")


def _grp_key(o) -> tuple:
    """成员的顺序：买单在前；同一方向里在交易所 / 已成交的在前；再按 cid。"""
    return (0 if _g(o, "side") == "BUY" else 1, 0 if _g(o, "status") in AT_EXCH + ("FILLED",) else 1, str(_g(o, "cid")))


def groups(orders, book: dict | None) -> dict[str, list[str]]:
    """当前决策里一起下的单 → {cid: 同一组的成员 cid（买单在前）}（只放成员 ≥ 2 的；纯函数、只读；ExecOrder / dict 都行）。
    面板（按钮与「同一组还有」）、手动指令的检查、撤单引擎、命令行的预览共用。"""
    b = book or {}
    by = {}
    for o in orders or []:
        if _in_current(o, b):
            by[str(_g(o, "cid"))] = o
    if len(by) < 2:
        return {}
    parent = {c: c for c in by}

    def find(c: str) -> str:
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c

    def link(x: str, y: str) -> None:
        x, y = str(x), str(y)
        if x in by and y in by and x != y:
            parent[find(x)] = find(y)

    def ph(o) -> str:
        return _g(o, "phase") or "morning"

    def core(o) -> bool:
        return (_g(o, "kind") or "stock") == "core"
    for c, o in by.items():                                # E1 拆成两笔的单
        if c.endswith("-2") and c[:-2] in by and _grp_capable(o) and _grp_capable(by[c[:-2]]):
            link(c, c[:-2])
    eb = [c for c, o in by.items() if _g(o, "side") == "BUY" and core(o) and ph(o) != "now" and src_of(o) == "core_fix"]
    es = [c for c, o in by.items() if _g(o, "side") == "SELL" and core(o) and ph(o) != "now" and src_of(o) == "fix_fund"]
    for x in eb:                                           # E2 早上的固定口数：凑钱的卖单分不出为哪只 → 两两相连
        for y in es:
            link(x, y)
    ff = (b.get("core_rule") or {}).get("fix_fund") or {}
    for c, o in by.items():
        if _g(o, "side") != "BUY" or ph(o) != "now":
            continue
        fs = [str(x) for x in (_g(o, "fund_src") or [])]
        if core(o) and src_of(o) == "core_fix":            # E3 盘中的固定口数
            f = ff.get(_g(o, "ticker")) if isinstance(ff, dict) else None
            for s in ((f or {}).get("cids") or []) if isinstance(f, dict) else []:
                if str(s) in by and _g(by[str(s)], "side") == "SELL":
                    link(c, s)
            for s in fs:
                if s in by and _g(by[s], "side") == "SELL" and _g(by[s], "reason") == "fix_fund":
                    link(c, s)
        if _g(o, "reason") in ("manual_buy", "manual_add"):   # E4 盘中的手动买入 / 加仓
            for s in fs:
                if s in by and _g(by[s], "side") == "SELL" and _g(by[s], "reason") == "manual_fund":
                    link(c, s)
    items = [x for x in (((b.get("manual") or {}).get("items")) or {}).values() if isinstance(x, dict)]
    if items:                                              # E5 手动买入「平摊凑」/「全部换成」同一次写的个股卖出
        from .manual_orders import fund_companions
        sells = None
        for c, o in by.items():
            if _g(o, "side") != "BUY" or _g(o, "reason") not in ("manual_buy", "manual_add"):
                continue
            it_b = _manual_item(b, o)
            if not it_b or it_b.get("fund") not in ("split", "all"):
                continue
            ids = {r.get("id") for r in fund_companions(it_b, items)}
            if sells is None:
                sells = [(s, _manual_item(b, x)) for s, x in by.items()
                         if _g(x, "side") == "SELL" and _g(x, "reason") in ("manual", "manual_trim")]
            for s, it_s in sells:
                if it_s and it_s.get("id") in ids:
                    link(c, s)
    comp: dict[str, list[str]] = {}
    for c in by:
        comp.setdefault(find(c), []).append(c)
    out = {}
    for cs in comp.values():
        if len(cs) < 2:
            continue
        ms = sorted(cs, key=lambda c: _grp_key(by[c]))
        for c in cs:
            out[c] = list(ms)
    return out


_group_map = groups                                  # cancel_core 的参数也叫 groups


def group_of(o, orders, book: dict | None) -> list:
    """这笔单所在的一组（成员：ExecOrder / dict，买单在前）；不在一组里 → [o]。"""
    g = groups(orders, book).get(str(_g(o, "cid")))
    if not g:
        return [o]
    by = {str(_g(x, "cid")): x for x in orders}
    return [by[c] for c in g if c in by]


def fund_linked(mem, orders, book: dict | None) -> list:
    """不是这一组的成员、靠这一组卖单的钱、已经发出（在交易所 / 状态不明 / 成交过）的买单（复核 6 2026-10-16：以前整组撤单不管它们，
    卖单撤了、它们还挂在交易所，确认框和推送都不提）。整组撤单把它们当成这一组的买单：一起撤（先撤买单），撤不了 / 已经成交 → 卖单不撤
    （与「一起撤买单」legacy_plan 的 exch 一样）。还没发出的（deps_of）不算：撤了卖单按现在的钱重算（fund_cascade）。"""
    mids = {str(_g(x, "cid")) for x in mem}
    sells = {str(_g(x, "cid")) for x in mem if _g(x, "side") == "SELL"}
    out = []
    for x in orders or []:
        if (str(_g(x, "cid")) in mids or _g(x, "side") != "BUY" or _g(x, "status") in DEP_OPEN or not _in_current(x, book)
                or not sells & {str(y) for y in (_g(x, "fund_src") or [])}):
            continue
        q, _n, full = _fq(x)
        if _g(x, "status") in AT_EXCH + ("ERROR",) or q > 0 or full:
            out.append(x)
    return out


def group_members(o, orders, book: dict | None) -> list:
    """整组撤单的范围（成员 + fund_linked；确认框、按钮、check、撤单引擎、命令行预览同一个）；不在一组里 → [o]。"""
    mem = group_of(o, orders, book)
    return mem + fund_linked(mem, orders, book) if len(mem) > 1 else mem


def grp_why(o, book: dict | None, now: dt.datetime, paper: bool) -> str | None:
    """整组撤单里这笔现在能不能撤：= cancel_why；被挡、还没发到交易所（BLOCKED、没有注文番号）的当成计划（今天 15:30 之前在本地撤掉，
    执行器不再重试）。面板的按钮、group_prune、check 与撤单引擎共用。"""
    if _g(o, "status") == "BLOCKED" and not _g(o, "broker_id"):
        d = dict(o) if isinstance(o, dict) else asdict(o)
        d["status"] = "PLANNED"
        return cancel_why(d, book, now, paper)
    return cancel_why(o, book, now, paper)


def _ord_txt(o) -> str:
    """「买 1482 对冲版美国 7〜10 年国债：679 口」（代码带名字、口 / 股）。"""
    n = int(_g(o, "sent_qty") or _g(o, "qty") or 0)
    q_ = f"{n:,} {_unit(o)}"
    return _side(o) + " " + _labq(_g(o, "ticker"), q_)


def _fq(x) -> tuple[int, int, bool]:
    """(已成交, 发出的, 全部成交了吗)：FILLED / 撤单时已经全部成交 / 成交数 ≥ 发出的 = 全部成交（复核 2 2026-10-16：部分成交不再算全部成交）。"""
    n = int(_g(x, "sent_qty") or _g(x, "qty") or 0)
    q = int(_g(x, "filled_qty") or 0)
    full = _g(x, "status") == "FILLED" or "撤单时已经全部成交" in str(_g(x, "note") or "") or (n > 0 and q >= n)
    return (max(q, n) if full else q), n, full


def _spends(x, scope: set, pend: set, now: dt.datetime | None, fill, pre: bool = False) -> tuple[str, str] | None:
    """整组撤单的闸门：这笔买单还可能花钱吗 →（代码, 理由）/ None。filled（成交过，含部分成交）/ unknown（发送中 / 结果不明）/
    pending（撤单立花还没确认：这次运行发的 pend，或不在这次范围里、之前撤过还在取消中）/ live（没撤掉、还挂着 / 执行器还会发）/
    new（不在这次范围里、执行器还会发：你确认之后才出现的；pre = 确认框的预判 → 「现在撤不了」）。
    复核 2（2026-10-16）：先看成交，再看状态不明，再看还挂着 / 取消中，最后才看「不在范围里」（以前状态不明的也说成「你确认之后才出现的」）。"""
    s = _g(x, "status")
    lab = _lab(_g(x, "ticker"))
    q, _n, full = _fq(x)
    if q > 0 or full:
        return "filled", f"买 {lab} 已经成交 {q:,} {_unit(x)}"
    if s in ("SENDING", "ERROR"):
        return "unknown", f"买 {lab} 状态不明（发送中 / 结果不明）"
    c = str(_g(x, "cid"))
    inn = c in scope
    if s in CANCELLABLE and GONE in str(_g(x, "note") or ""):   # 撤单时立花回已经失效 / 被拒、没成交：不再花钱（复核 5 2026-10-16）
        return None
    if s in CANCELLABLE:
        if c in pend or (not inn and ACCEPTED in str(_g(x, "note") or "")):
            return "pending", f"买 {lab} 的撤单立花还没确认（取消中）"
        if FAILED in str(_g(x, "note") or ""):            # 之前的撤单立花回「取消失敗」（复核 3 2026-10-16：说明里不再留「撤单已受理」）
            return "live", f"买 {lab} 的撤单没成功（立花：取消失敗，还挂着）"
        return "live", (f"买 {lab} 没撤掉（还挂着）" if inn else f"买 {lab} 还挂在交易所（不在这次整组撤单里）")
    if s in GROUP_NEUTRAL:
        return None
    if s == "BLOCKED" and not blocked_retry(x, now, fill):
        return None                                        # 被挡、今天不会再发：不花钱
    if s in UNSENT or s == "BLOCKED":
        if inn:
            return "live", f"买 {lab} 没撤掉（执行器还会发）"
        return "new", (f"买 {lab} 现在撤不了（执行器还会发）" if pre else f"买 {lab} 是你确认之后才出现的、没一起撤")
    return None


ACCEPTED = "撤单已受理"                                # 撤单受理了、立花还在处理时写进单的说明（_cancel_one）
FAILED = "撤单没成功"                                  # 立花回「取消失敗」（单还挂着）时写进单的说明（_cancel_one；复核 3 2026-10-16）
GONE = "立花那边已经结束"                              # 撤单时立花回「已经失效 / 被拒」（单不在交易所了）时写进单的说明（_cancel_one；复核 5 2026-10-16）
DEPK = "撤买单（卖单不撤）"                             # 确认框「一起撤买单」在同一组的买单还可能花钱时的按钮文字（data-depk；复核 2 2026-10-16）


def _cancelling(r: dict | None) -> bool:
    """立花的注文状态是「取消中」（sOrderStatusCode 6 / 状态名称 取消中）。复核 2（2026-10-16）：以前只看名称里有没有「取消」，
    「取消失敗」（撤单没成功、单还挂着）也被当成已受理。"""
    r = r or {}
    return str(r.get("status_code") or "").strip() == "6" or str(r.get("status") or "").strip() == "取消中"


def _solo_spends(x, now: dt.datetime | None, fill) -> tuple[str, str] | None:
    """只撤同一组里的一笔卖单（不是整组撤单）时的闸门：同一组的这笔买单还可能花钱吗 →（代码, 理由）/ None。
    filled（成交过）/ pending（撤单立花还没确认）/ live（还挂在交易所）/ unknown（发送中 / 结果不明）。还没发出的（计划 / 等开盘后 / 被挡）
    不算：发的时候执行器按那时的现金 / 余力重算（fund_cascade），少了这笔卖出也不会透支（复核 2026-10-16）。"""
    s = _g(x, "status")
    lab = _lab(_g(x, "ticker"))
    q, _n, full = _fq(x)
    if q > 0 or full:
        return "filled", f"买 {lab} 已经成交 {q:,} {_unit(x)}"
    if s in CANCELLABLE and GONE in str(_g(x, "note") or ""):   # 撤单时立花回已经失效 / 被拒、没成交：不再花钱
        return None
    if s in CANCELLABLE:
        if ACCEPTED in str(_g(x, "note") or ""):
            return "pending", f"买 {lab} 的撤单立花还没确认（取消中）"
        if FAILED in str(_g(x, "note") or ""):
            return "live", f"买 {lab} 的撤单没成功（立花：取消失敗，还挂着）"
        return "live", f"买 {lab} 还挂在交易所（没撤）"
    if s in ("SENDING", "ERROR"):
        return "unknown", f"买 {lab} 状态不明（发送中 / 结果不明）"
    return None


def _xtra_spends(x, book: dict | None, now: dt.datetime | None, paper: bool, fill) -> tuple[str, str] | None:
    """「一起撤买单」（deps=cancel）里同一组、不靠这笔卖出的钱的买单（执行器不为它发撤单）还可能花钱吗（legacy_plan 与 _group_job 共用；
    复核 4 2026-10-16）= _solo_spends，但撤单已受理（取消中）、现在能查的 → pending：执行器等它（约 1 分钟只查一次状态、不再发撤单），
    立花确认撤掉了（没成交）才撤卖单，最多 10 分钟 / 收盘前 3 分钟为止（以前当成「还挂着」马上留下卖单、指令就此结束，确认框却写「买单撤掉了才撤」）。
    现在查不了（模拟账户 / grp_why）→ live。"""
    r = _solo_spends(x, now, fill)
    if r and r[0] == "pending" and (paper or (now is not None and grp_why(x, book, now, paper) is not None)):
        return "live", r[1].replace("（取消中）", "（取消中，现在查不了）")
    return r


def _solo_holds(o, orders, book: dict | None, now: dt.datetime | None, G=None) -> list[tuple[str, str, str]]:
    """solo_holds 带上买单的 cid →[(cid, 代码, 理由)]（确认框按代码写建议、引擎按代码给命令行的提示）。"""
    if _g(o, "side") != "SELL":
        return []
    G = groups(orders, book) if G is None else G
    by = {str(_g(x, "cid")): x for x in orders}
    out = []
    for c in G.get(str(_g(o, "cid"))) or []:
        x = by.get(c)
        if x is not None and _g(x, "side") == "BUY":
            r = _solo_spends(x, now, fill_day_of(book))
            if r:
                out.append((c,) + r)
    return out


def solo_holds(o, orders, book: dict | None, now: dt.datetime | None, G=None) -> list[tuple[str, str]]:
    """只撤这笔卖单（同一组里、不是整组撤单）会不会被闸门挡下：同一组里还可能花钱的买单 → [(代码, 理由)]（不是卖单 / 不在一组里 → []）。
    撤单引擎（deps 没写 keep 的单笔卖单）与面板（「只撤这笔卖单」的确认框）共用。"""
    return [(k, t) for _c, k, t in _solo_holds(o, orders, book, now, G)]


def _pre_gate(mem, scope: set, asked: set, now: dt.datetime | None, fill) -> list[tuple[str, str, str]]:
    """确认框的闸门预判（只读）：整组撤单撤完能撤的之后，这一组里还会花钱的买单 → [(cid, 代码, 理由)]。在这次范围里 / 已经在撤的买单
    只算已经成交（含部分成交）/ 状态不明的（撤了也挡）；不在范围里的按 _spends（还挂着 / 执行器还会发）。"""
    out = []
    handled = set(scope) | set(asked)
    for x in mem:
        if _g(x, "side") != "BUY":
            continue
        r = _spends(x, handled, set(), now, fill, pre=True)
        if r is None or (str(_g(x, "cid")) in handled and r[0] not in ("filled", "unknown")):
            continue
        out.append((str(_g(x, "cid")),) + r)
    return out


def group_view(o, orders, book: dict | None, now: dt.datetime, paper: bool, asked=(), *, cli: bool = False) -> dict:
    """这一组现在能怎么撤（只读；面板的按钮 data-grp、确认框 group_lines、命令行预览共用；复核 2 2026-10-16）→
    {mem, can（同一组里现在能一起撤的其他单）, ok（给「整组撤单」按钮的：闸门预判挡下卖单时为空）, gate（_pre_gate）, blocked, solo, scope}。
    blocked：这一组有买单撤了也还会花钱（已经成交 / 部分成交 / 状态不明 / 撤不了还挂着），整组撤单不会撤任何卖单 → 不给整组撤单（solo）：
    确认框写「只撤这一笔」，与执行器实际做的一样（以前给「整组撤单（N 笔）」、执行器一笔卖单都不撤）。
    cli（命令行 cancel <cid> --group 的预览；复核 3 2026-10-16）：照执行器 groups={cid: None} 的范围 —— 这一组现在能撤的全部 + 点的这一笔，
    不看 asked（命令行照样撤已经在单笔撤的）、不限 GROUP_MAX 笔。"""
    from .manual_orders import _CID, GROUP_MAX
    asked = set() if cli else {str(c) for c in asked or ()}
    gm = group_of(o, orders, book)
    me = str(_g(o, "cid"))
    if len(gm) < 2:
        return {"mem": gm, "can": [], "ok": [], "gate": [], "blocked": False, "solo": True, "scope": {me}, "linked": set()}
    xl = fund_linked(gm, orders, book)                      # 靠这一组卖单的钱、已经发出的买单：也在范围里（group_members；复核 6）
    mem = gm + xl
    lk = {str(_g(x, "cid")) for x in xl}
    can = [str(_g(x, "cid")) for x in mem if str(_g(x, "cid")) != me and str(_g(x, "cid")) not in asked
           and grp_why(x, book, now, paper) is None and (cli or _CID.match(str(_g(x, "cid"))))]
    if len(can) > GROUP_MAX - 1 and not cli:
        can = []
    scope = set(can) | ({me} if me not in asked and grp_why(o, book, now, paper) is None else set())
    gate = _pre_gate(mem, scope, asked, now, fill_day_of(book))
    blocked = bool(gate) and any(_g(x, "side") == "SELL" and str(_g(x, "cid")) in scope for x in mem)
    ok = [] if blocked else can
    return {"mem": mem, "can": can, "ok": ok, "gate": gate, "blocked": blocked, "solo": not ok, "scope": scope, "linked": lk}


def legacy_plan(o, orders, book: dict | None, now: dt.datetime, paper: bool, asked=(), G=None) -> dict:
    """「一起撤买单」（单笔卖单的 deps=cancel，不是整组撤单：_group_job 的 legacy）执行器会怎么做（只读预判；确认框 group_lines、面板的
    data-depk / data-depw / data-depx 与执行器同一个范围；复核 3 2026-10-16）→
    {"dep": 靠这笔卖出的钱、还没发出的买单（本地撤）, "exch": 靠这笔卖出的钱、在交易所、现在能撤的买单（执行器也发撤单）,
     "ask": 靠它的钱 / 同一组、已经在撤（等执行器）的买单, "keep": [(cid, 代码, 理由)], "src": 靠这笔卖出的钱的买单（fund_src）}。
    keep = 执行器撤完能撤的之后还会花钱、执行器自己改变不了的买单（已经成交 / 状态不明 / 还挂着现在撤不了 / 同一组不靠它的钱、还挂着）：
    有 → 卖单一定不撤（确认框的主按钮写「撤买单（卖单不撤）」）；没有、但有 exch / ask → 执行器先撤这些买单，立花确认撤掉了（没成交）才撤卖单
    （主按钮仍叫「一起撤买单」，确认框写清；以前一律写「撤买单（卖单不撤）」，执行器却在同一次运行里把卖单也撤了）。
    复核 4（2026-10-16）：已撤、但成交过一部分的买单也算花了钱（keep；以前跳过已撤的，确认框写「→ 撤」、执行器留下卖单）；同一组、不靠它的钱、
    撤单已受理（取消中）的买单进 ask（执行器等它：_xtra_spends；以前进 keep，执行器又不等）。"""
    c = str(_g(o, "cid"))
    asked = {str(x) for x in asked or ()}
    fill = fill_day_of(book)
    G = groups(orders, book) if G is None else G
    by = {str(_g(x, "cid")): x for x in orders}
    src = [x for x in orders if _g(x, "side") == "BUY" and _in_current(x, book) and c in [str(y) for y in (_g(x, "fund_src") or [])]]
    sids = {str(_g(x, "cid")) for x in src}
    dep = [str(_g(x, "cid")) for x in deps_of(o, orders)]
    extra = [by[m] for m in G.get(c) or [] if m in by and _g(by[m], "side") == "BUY" and m not in sids]
    scope = sids | {c}
    exch, ask, keep = [], [], []
    for x in src + extra:
        xc = str(_g(x, "cid"))
        if xc in dep or (_g(x, "status") == "CANCELLED" and not _fq(x)[0]):   # 已撤、成交过一部分的：下面按已经成交挡（复核 4）
            continue
        lab = _lab(_g(x, "ticker"))
        if xc in asked or (xc in sids and grp_why(x, book, now, paper) is None):
            (ask if xc in asked else exch).append(xc)      # 执行器会撤（单笔撤单在前 / 「一起撤买单」也发撤单）：只有已经成交 / 状态不明的挡
            r = _spends(x, scope | {xc}, set(), now, fill, pre=True)
            if r and r[0] in ("filled", "unknown"):
                keep.append((xc,) + r)
            continue
        if xc in sids:                                     # 靠它的钱、执行器撤不了的（已成交 / 状态不明 / 还挂着、现在撤不了）
            r = _spends(x, scope, set(), now, fill, pre=True)
            if r and r[0] == "live":
                r = ("live", f"买 {lab} 还挂着、现在撤不了（{grp_why(x, book, now, paper) or '撤不了'}）")
        else:                                              # 同一组、不靠它的钱（执行器不发撤单，只看它还会不会花钱）
            r = _xtra_spends(x, book, now, paper, fill)
            if r and r[0] == "pending":                    # 撤单已受理（取消中）：执行器等立花确认撤掉了（没成交）才撤卖单（复核 4）
                ask.append(xc)
                continue
        if r:
            keep.append((xc,) + r)
    return {"dep": dep, "exch": exch, "ask": ask, "keep": keep, "src": sorted(sids)}


def still_sells(x, now: dt.datetime | None, fill: dt.date | None = None) -> bool:
    """同一组的这笔卖单「照常卖」吗（确认框「只撤这笔买单（卖 X 照常卖）」只列这些；简化 2026-10-16）：还开着、立花那边没失效 / 被拒、
    撤单没受理、不是不会再发的「被挡」。"""
    if _g(x, "side") != "SELL" or _g(x, "status") not in GROUP_OPEN:
        return False
    n = str(_g(x, "note") or "")
    if _g(x, "status") in CANCELLABLE and (GONE in n or ACCEPTED in n):
        return False
    return not (_g(x, "status") == "BLOCKED" and not blocked_retry(x, now, fill))


def gone_word(x) -> str:
    """撤单时立花回的终态（_cancel_one 写进说明的 GONE）：「被拒」/「失效」。"""
    return "被拒" if f"{GONE}（被拒" in str(_g(x, "note") or "") else "失效"


def _st_txt(x) -> str:
    """确认框里一笔单的状态：「已下单（等成交）」「部分成交，已成交 1,000/4,110 口」「已下单（等成交），撤单已受理（取消中）」。"""
    s = _g(x, "status")
    t = STATUS_TEXT.get(s, str(s))
    gone = s in CANCELLABLE and GONE in str(_g(x, "note") or "")
    if gone:                                               # 撤单时立花回已经失效 / 被拒：不写「已下单（等成交）」（复核 5）
        t = "立花那边已经" + gone_word(x) + "（撤单时查到）"
    q, n, _full = _fq(x)
    if 0 < q < n:
        t += f"，已成交 {q:,}/{n:,} {_unit(x)}"
    if gone:
        return t
    if s in CANCELLABLE and ACCEPTED in str(_g(x, "note") or ""):
        t += "，撤单已受理（取消中）"
    elif s in CANCELLABLE and FAILED in str(_g(x, "note") or ""):
        t += "，撤单没成功（取消失敗）"
    return t


def _hold_star(c: str, code: str, text: str, x, book, now, paper, asked: set, what: str) -> str:
    """只撤这笔卖单、同一组的买单还可能花钱：确认框的 ★ 一行（按代码写建议；复核 2 2026-10-16：买单已经成交时不再叫你「等买单撤掉」，
    买单在撤单中 / 取消中时不再说「还挂在交易所（没撤）」）。what：按钮叫什么（「只撤这笔卖单」/「只撤卖单」）。"""
    lab = _lab(_g(x, "ticker")) if x is not None else ""
    risk = "买单万一成交，钱不从这笔卖出来（现金比计划少；买单发出时已经按那时的钱下，不会透支）"
    if code == "filled":
        return f"★ 同一组的{text}：{what} = 这笔卖出的钱不来了，现金比计划少（买单是按发出时的钱成交的，不会透支）"
    if code == "unknown":
        return (f"★ 同一组的{text}：先在立花网站 / 手机网站的注文一覧核对买 {lab}；{what} = {risk}" if not paper else
                f"★ 同一组的{text}：{what} = {risk}")
    if code == "pending":
        return f"★ 同一组的{text}：{what} = {risk}。稳妥做法：等买单撤掉（取消完了）之后再撤卖单"
    if c in asked:
        return f"★ 同一组的买 {lab} 撤单中（等执行器）：{what} = {risk}。稳妥做法：等买单撤掉之后再撤卖单"
    why = grp_why(x, book, now, paper) if x is not None else "撤不了"
    if why is None:
        return f"★ 同一组的{text}：{what} = {risk}。稳妥做法：先撤买 {lab}（它那一行的「撤单」），撤掉之后再撤卖单"
    return f"★ 同一组的{text}（现在撤不了：{why}）：{what} = {risk}。稳妥做法：等买单结束（成交 / 失效）之后再决定"


def group_lines(o, orders, book: dict | None, now: dt.datetime, paper: bool, tag: str | None = None, asked=(), *,
                solo: bool | None = None, fix_t: str | None = None, cli: bool = False) -> list[str]:
    """整组撤单的确认框 / 命令行预览（只读）：怎么撤、每一笔会怎样、不是成员却受影响的买单、固定口数还有效、「全部换成」的说明。
    solo（None = 按 group_view：同一组的其他单现在不能一起撤，或闸门预判整组撤单一笔卖单都不会撤）：写「只撤这一笔」，
    卖单在同一组的买单还可能花钱时按买单的情况加 ★（_hold_star）；这笔卖单有靠它的钱、执行器还没发出的买单（deps_of：确认框的
    「一起撤买单」/「只撤卖单」）→ 不写「只撤这一笔」，逐笔写两个按钮各会怎样（复核 2 2026-10-16）。solo=False：整组撤单，闸门预判挡下
    卖单时卖单写「不撤（…）」。cli（命令行 cancel <cid> --group 的预览 = cancel-plan；复核 3 2026-10-16）：solo=False + 执行器 --group 的范围
    （group_view cli；以前按面板的「只撤这一笔」写，与 --group 实际做的相反）。部分成交的单写「撤剩下的」+ 已成交 / 发出的。
    「一起撤买单」的范围照 legacy_plan（复核 3）：靠这笔卖出的钱、在交易所的买单也写成一起撤（以前写「不跟着撤」，执行器却撤了）；
    执行器撤完之后还有买单会花钱（keep）才叫「撤买单（卖单不撤）」，不然写「买单撤掉了（没成交）才撤卖单」；不在一组里、但「一起撤买单」
    也撤在交易所的买单 / 会留下卖单的，也写这几行。
    fix_t：确认框里「（整组）撤单并恢复按规则」恢复的是哪只固定口数的 ETF（只有它的那一行指向这个按钮；别的固定 ETF 指向「持仓」里的
    「恢复按规则」；没给 → 都指向「持仓」）。"""
    import re
    from .manual_orders import GROUP_MAX
    asked = set() if cli else {str(c) for c in asked or ()}
    v = group_view(o, orders, book, now, paper, asked, cli=cli)
    mem = v["mem"]
    me = str(_g(o, "cid"))
    solo = False if cli else (v["solo"] if solo is None else bool(solo))
    gate = v["gate"]
    gtxt = "；".join(t for _c, _k, t in gate)
    blocked = v["blocked"]
    sell = _g(o, "side") == "SELL"
    me_ok = me not in asked and grp_why(o, book, now, paper) is None
    dx = deps_of(o, orders) if solo and sell and me_ok else []
    dids = {str(_g(x, "cid")) for x in dx}
    lp = legacy_plan(o, orders, book, now, paper, asked) if dx else None
    exch = list(lp["exch"]) if lp else []
    keep = list(lp["keep"]) if lp else []
    cond = bool(lp and not keep and (lp["exch"] or lp["ask"]))   # 「一起撤买单」：买单撤掉了（没成交）才撤卖单
    if len(mem) < 2 and not (lp and (exch or lp["ask"] or keep)):
        return []
    if cli and not v["scope"]:                             # 命令行预览：没有能撤的单 → 只写这一句（复核 6 2026-10-16：以前照样写「先撤买单…」）
        return ["这一组没有能撤的单（" + "；".join(_ord_txt(x) + "：" + _st_txt(x) for x in mem)
                + "）：--group 什么都不会撤"]
    k1 = DEPK if keep else "一起撤买单"
    sopen = any(_g(x, "side") == "SELL" and str(_g(x, "cid")) in v["scope"] for x in mem)   # 这次范围里有卖单（「卖单因此不撤」只在有时写）
    if solo and dx and len(mem) < 2:
        out = ["这笔卖单：靠这笔卖出的钱的买单看下面（两个按钮不一样）"]
    elif solo and dx:
        out = ["这笔卖单：同一组（一起下的）其他单现在不能一起撤（" + (gtxt if blocked else "已经成交 / 已撤 / 撤单中 / 撤不了")
               + "）；靠这笔卖出的钱" + ("的买单" if exch else "、执行器还没发出的买单") + "看下面（两个按钮不一样）"]
    elif solo and blocked:
        out = ["只撤这一笔：" + gtxt + " → 这一组不能整组撤（这样的买单撤了也还会花钱，卖单不能跟着撤）"]
    elif solo:
        out = ["只撤这一笔：同一组（一起下的）其他单现在不能一起撤（已经成交 / 已撤 / 撤单中 / 撤不了），撤的只是这一笔"]
    elif blocked:
        out = ["整组撤单：" + gtxt + " → 这一组的卖单都不撤（撤了买的钱不够），只撤还能撤的买单"]
    else:
        out = ["整组撤单：先撤买单，确认买单撤掉了（没成交）再撤卖单；买单已经成交 / 撤不掉 → 卖单不撤（不然钱不够）"]
    if len(mem) > GROUP_MAX and not cli:
        out.insert(0, f"这一组超过 {GROUP_MAX} 笔：请一笔笔撤，或在 Mac 对话里说「整组撤单」")
    first = gate[0][2] if gate else ""

    def exch_line(x) -> str:                               # 靠这笔卖出的钱、在交易所的买单：「一起撤买单」也发撤单（legacy_plan）
        q_, _n, _f = _fq(x)
        return ("· 靠这笔卖出的钱、在交易所：" + _ord_txt(x) + "（" + _st_txt(x) + "）—— 「" + k1 + "」→ "
                + ("撤剩下的" if q_ > 0 else "一起撤") + "（发撤单）；「只撤卖单」→ 不撤")
    scope, dead = set(), set()
    for x in mem:
        c, s = str(_g(x, "cid")), _g(x, "status")
        w = _ord_txt(x) + ("（靠这一组卖单的钱买的，不是一起下的）" if c in v["linked"] else "")
        q, n, full = _fq(x)
        part = f"已成交 {q:,}/{n:,} {_unit(x)}" if 0 < q < n else ""
        if s == "CANCELLED":
            m = re.search(r"你撤了单（(\d\d:\d\d)", str(_g(x, "note") or ""))
            out.append(("· 已撤（" + m.group(1) + "）：" if m else "· 已撤：") + w + ("（" + part + "）" if part else ""))
        elif full:
            out.append("· 已成交：" + w + (" —— 不能撤；卖单因此不撤" if _g(x, "side") == "BUY" and not solo and sopen else
                                          " —— 不能撤" if _g(x, "side") == "BUY" else ""))
        elif s in CANCELLABLE and GONE in str(_g(x, "note") or ""):   # 撤单时立花回已经失效 / 被拒：单不在交易所了（买卖一样；简化 2026-10-16）
            out.append("· 立花那边已经" + gone_word(x) + "（" + (part or "没成交") + "）：" + w + " —— 不用撤")
        elif c in asked or (lp and c in lp["ask"]):        # 「一起撤买单」要等的、之前撤过还在取消中的同一组买单也写「撤单中」（复核 4）
            out.append("· 撤单中：" + w + ("（" + part + "）" if part else ""))
        elif c in dids:                                    # 也是靠这笔卖出的钱、还没发出的：下面「靠这笔卖出的钱」那一行写（复核 3：以前写两次、说法相反）
            continue
        elif c in exch:
            out.append(exch_line(x))
        elif s not in GROUP_OPEN and q > 0:                # 已失效 / 被拒、成交了一部分
            out.append("· " + STATUS_TEXT.get(s, str(s)) + "（" + part + "）：" + w)
        else:
            why = grp_why(x, book, now, paper)
            st = _st_txt(x)
            if solo and c != me:
                out.append(("· 不跟着撤：" + w + "（" + st + "）") if why is None else ("· 撤不了：" + w + " —— " + why))
            elif why is not None:
                out.append("· 撤不了：" + w + " —— " + why)
            elif not solo and blocked and _g(x, "side") == "SELL":
                out.append("· 不撤（" + first + "）：" + w + "（" + st + "）")
            elif dx and c == me:                           # 两个按钮对这笔卖单不一样（复核 3：以前一律写「撤（这一笔）」，「撤买单（卖单不撤）」并不撤它）
                rest = "撤剩下的" if q > 0 else "撤"
                out.append("· 这一笔：" + w + "（" + st + "）—— 「" + k1 + "」→ "
                           + ("不撤" if keep else "买单撤掉了（没成交）才" + rest if cond else rest) + "；「只撤卖单」→ " + rest)
                scope.add(c)
                dead.add(c)
            else:
                out.append("· " + ("撤剩下的" if q > 0 else "撤") + ("（这一笔）" if solo else "") + "：" + w + "（" + st + "）")
                scope.add(c)
                if _g(x, "side") == "SELL":
                    dead.add(c)
    hold = _solo_holds(o, orders, book, now) if solo and sell and me in scope else []
    by = {str(_g(x, "cid")): x for x in orders}
    what = "只撤卖单" if dx else "只撤这笔卖单"
    mids = {str(_g(x, "cid")) for x in mem}
    rows = _fund_rows(orders, book, now, paper, tag, scope, dead)   # 不是成员、靠这组卖单的钱的买单：撤了之后会怎样
    if dx:                                                 # 「一起撤买单」/「只撤卖单」各会怎样（与引擎：deps=cancel → 以前的「一起撤买单」、keep → 重算）
        for b in dx:
            r = rows.get(str(_g(b, "cid")))
            u = _unit(b)
            w2 = ("按现在的钱重算" if r is None else "不会下" if r["act"] == "skip"
                  else f"减到 {int(r['qty']):,} {u}" if r["act"] == "reduce" else "照常（钱够）")
            out.append("· 靠这笔卖出的钱：" + _ord_txt(b) + "（" + STATUS_TEXT.get(_g(b, "status"), str(_g(b, "status"))) + "）—— 「"
                       + k1 + "」→ 一起撤（执行器不再发）；「只撤卖单」→ " + w2)
        for xc in exch + lp["ask"]:                        # 不是成员、靠这笔卖出的钱、在交易所 / 已经在撤的买单
            x = by.get(xc)
            if x is None or xc in mids:
                continue
            out.append(exch_line(x) if xc in exch else "· 靠这笔卖出的钱、撤单中：" + _ord_txt(x))
        if keep:
            pre = "同一组的" if all(k[0] in mids for k in keep) else ""
            out.append("★ 「" + DEPK + "」：靠它的钱的买单撤掉，这笔卖单不撤（" + pre + "；".join(t for _c, _k, t in keep)
                       + "：撤了买的钱不够）；要撤这笔卖单 → 「只撤卖单」")
        elif cond:
            ws = [_ord_txt(by[x]) + ("（撤单中）" if x in lp["ask"] else "") for x in exch + lp["ask"] if x in by]
            out.append("★ 「一起撤买单」：先撤买单（" + "、".join(ws) + "），确认买单撤掉了（没成交）才撤这笔卖单；买单成交了 / 撤不掉"
                       + ("" if paper else " / 立花 10 分钟还没确认") + " → 这笔卖单不撤（会推送 ★）")
    for c, k, t in hold:                                   # 只撤这笔卖单、同一组的买单还可能花钱：按买单的情况说清楚（引擎的闸门在 deps 不是 keep 时会挡下）
        out.append(_hold_star(c, k, t, by.get(c), book, now, paper, asked, what))
    for c, r in rows.items():
        if c in mids or c in dids or c in exch or r["act"] == "keep":
            continue
        out.append("· 不跟着撤：买 " + _labq(_g(r["o"], "ticker"), f"{int(r['was']):,} {_unit(r['o'])}") + " —— " + str(r["note"]))
    fx = _core_fix_of(book, tag)
    btn = ("撤买单并恢复按规则" if keep else "撤单并恢复按规则") if solo else "整组撤单并恢复按规则"   # 确认框里实际有的那个按钮（复核 3：卖单不撤时按钮叫「撤买单…」）
    for t in dict.fromkeys(_g(x, "ticker") for x in mem if _g(x, "side") == "BUY" and _g(x, "ticker") in fx):
        how = ("「" + btn + "」") if fix_t and t == fix_t and not cli else ("「持仓」里 " + _lab(t) + " 下面点「恢复按规则」")
        out.append(f"固定口数 {_lab(t)} {int(fx[t]):,} 口还有效：撤了，下一次决策（{next_decision_text(now)}）还会再排；"
                   "不要再排 → " + how)
    if any(_g(x, "side") == "BUY" and (_manual_item(book or {}, x) or {}).get("fund") == "all" for x in mem
           if _g(x, "reason") in ("manual_buy", "manual_add")):
        out.append("「全部换成」的整批：核心 ETF 的卖单（闲置资金比例 0%）不在这一组里、不跟着撤；要恢复比例在 Mac 对话里说")
    return out


def _fund_rows(orders, book: dict | None, now: dt.datetime, paper: bool, tag: str | None, scope: set, dead: set) -> dict:
    """撤掉 scope 之后，靠撤掉的卖单（dead）的钱、还没发出的买单会怎样（fund_cascade 预览；只读）→ {cid: 结果}；算不成 → {}。"""
    import copy
    try:
        cp = copy.deepcopy(list(orders))
        cur = [x for x in cp if _in_current(x, book)]
        for x in cur:
            if str(_g(x, "cid")) in scope:
                _set(x, status="CANCELLED")
        cash = cash_hi(book, tag) - _reserve_of(book, paper)
        return {str(_g(r["o"], "cid")): r for r in fund_cascade(cur, cash=cash, now=now, apply=False, dead=dead,
                                                                 fill=fill_day_of(book), queued=paper, book=book)}
    except Exception:                                      # noqa: BLE001  只是说明
        return {}


def lone_lines(o, orders, book: dict | None, now: dt.datetime, paper: bool, tag: str | None = None) -> list[str]:
    """不在一组里的单的命令行预览（cancel-plan；复核 6 2026-10-16）：现在能不能撤；卖单 → 靠这笔卖出的钱的买单撤了之后会怎样（还没发出的：
    按现在的钱重算 照常 / 减股 / 不会下，与执行器撤单之后的 fund_cascade 同一个；在交易所的：不跟着撤）。cancel <cid> 与 --group 做的一样。"""
    why = cancel_why(o, book or {}, now, paper)
    if why:
        return ["这笔单不在一组里、现在撤不了：" + why]
    out = ["这笔单不在一组里：撤单就是撤这一笔"]
    if _g(o, "side") != "SELL":
        return out
    c = str(_g(o, "cid"))
    dx = deps_of(o, orders)
    rows = _fund_rows(orders, book, now, paper, tag, {c}, {c}) if dx else {}
    for b in dx:
        r = rows.get(str(_g(b, "cid")))
        u = _unit(b)
        w = ("按现在的钱重算" if r is None else "不会下" if r["act"] == "skip"
             else f"减到 {int(r['qty']):,} {u}" if r["act"] == "reduce" else "照常（钱够）")
        out.append("· 靠这笔卖出的钱：" + _ord_txt(b) + "（" + _st_txt(b) + "）—— 撤了之后 → " + w + ("（" + r["note"] + "）" if r else ""))
    for x in fund_linked([o], orders, book):
        out.append("· 靠这笔卖出的钱、已经发出：" + _ord_txt(x) + "（" + _st_txt(x) + "）—— 不跟着撤（要撤就另撤这笔买单）")
    if dx:
        out.append("要靠它的钱的买单一起撤：面板确认框的「一起撤买单」（命令行 cancel 只撤这一笔卖单）")
    return out


def next_decision_text(now: dt.datetime) -> str:
    """下一次决策（交易日 07:40）是哪天 →「MM/DD 07:40」（panel._next_decision 同一个算法）。"""
    d0 = now.date()
    d1 = d0 if is_trading_day(d0) and now.time() < dt.time(7, 40) else next_trading_day(d0)
    return f"{d1:%m/%d} 07:40"


def fix_pending_when(book: dict | None, now: dt.datetime, tag: str | None = None) -> tuple[dict, str]:
    """还没照它调的固定口数（manual_orders.corefix_pending：含执行器还没读的）与什么时候照它下单（corefix_fill 的一句话）→ ({票: 口数}, 文字)；
    撤单提示 / 交易页「固定口数仍有效」用：没照它调过的今天开盘后 / 盘中就下，不是「下一次决策还会再排」（复核 UI F2，2026-10-16）。"""
    try:
        from . import manual_orders as MO
        pend = MO.corefix_pending(book, tag, now)
        return pend, (MO.corefix_fill(now, book, tag)["text"] if pend else "")
    except Exception:                                      # noqa: BLE001  只是说明
        return {}, ""


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
    if r == "fix_fund":                                     # 盘中为固定口数凑钱的卖单（D1；2026-10-15）
        return (f"{head}；这是盘中为手动固定口数凑钱的核心 ETF 卖单：撤了就不再为这次固定口数凑钱，固定的那只按手上的钱少买"
                f"（固定口数仍有效 → {nd} 的决策还会再排）")
    if kind == "core":
        fx = _core_fix_of(book, tag)
        d = ((book or {}).get("state") or {}).get("last_date")
        mine = [x for x in (book or {}).get("orders") or [] if x.get("decided_on") == d]
        pend, when = fix_pending_when(book, now, tag)       # 还没照它调的固定口数（D1）：今天开盘后 / 盘中就照它下，不等下一次决策（复核 UI F2）
        if t in fx:
            if t in pend:
                return (f"{head}；{_lab(t)} 手动固定 {int(fx[t]):,} 口还没照它调：{when}照它下单（撤这笔单不会取消固定口数；"
                        f"不想要 → 「持仓」里 {_lab(t)} 下面点「恢复按规则」）")
            return (f"{head}；{_lab(t)} 手动固定 {int(fx[t]):,} 口仍有效 → {nd} 的决策还会再排同样的单"
                    f"（不想要 → 「持仓」里 {_lab(t)} 下面点「恢复按规则」）")
        drv = [x.get("ticker") for x in mine if x.get("kind") == "core" and x.get("side") == "BUY" and x.get("ticker") in fx]
        if side == "SELL" and drv:
            fl = "、".join(f"{_lab(x)} {int(fx[x]):,} 口" for x in dict.fromkeys(drv))
            if any(x in pend for x in drv):
                return (f"{head}；这笔卖出是为手动固定（{fl}）凑钱：固定口数还没照它调 → {when}照它下单（钱不够先卖不固定的核心 ETF；"
                        f"不想要 → 「持仓」里那只 ETF 下面点「恢复按规则」）")
            return (f"{head}；这笔卖出是为手动固定（{fl}）凑钱：固定口数仍有效 → {nd} 的决策还会再排同样的换仓"
                    f"（不想要 → 「持仓」里那只 ETF 下面点「恢复按规则」）")
        if r == "manual_core":
            return f"{head}；照闲置资金比例调的单：比例不变 → {nd} 的决策照比例再算目标，可能再买 / 再卖"
        return f"{head}；核心 ETF 的单：{nd} 的决策照规则 / 闲置资金比例重新算目标，可能再买 / 再卖（要少拿用「闲置资金比例」）"
    if side == "SELL":
        return f"{head}；规则明天还要卖就会再下（与「没成交」同一处理）"
    return f"{head}；撤掉的个股买单不再买（信号只在那天开盘有效）"


# ══════════════════════════ 核心 ETF 单的来源（D7；2026-10-15）══════════════════════════
# 2026-10-15 事故：07:41 的推送写「规则拿 1545、不拿 1482」，同时要全卖 1545 —— 那组换仓其实来自你 10/14 19:21 写的「固定 1482 678 口」，
# 单的 reason 一律「核心 ETF 调整」，看不出来（很可能是 08:05 撤单的诱因）。执行器排单时在单上记来源（src）与一句话（src_txt：排单那一刻的
# 固定口数 / 比例与你写的时刻），日志 / 推送、交易页、撤单确认框照它写。reason 不改（对账、盘中的路按它认单）；旧账本没有 src → 照旧显示。
CORE_SRC = ("rule", "core_fix", "fix_fund", "manual_core")
SRC_WORD_CORE = {"rule": "规则再平衡", "core_fix": "照你写的固定口数", "fix_fund": "为你写的固定口数凑钱",
                 "manual_core": "照你写的闲置资金比例"}


def src_of(o) -> str:
    """核心单的来源：执行器记的 src；盘中的单（reason = core_fix / fix_fund / manual_core）照 reason；旧账本 / 个股 → ""。"""
    s = str(_g(o, "src") or "")
    if s in CORE_SRC:
        return s
    r = str(_g(o, "reason") or "")
    return r if r in CORE_SRC else ""


def _tsj(v) -> dt.datetime | None:
    """ISO 时刻 → 带 JST 时区的 datetime（读不了 → None）。"""
    from .calendar_jp import JST
    try:
        t = dt.datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None
    return t.astimezone(JST) if t.tzinfo else t.replace(tzinfo=JST)


def _at(d: dt.date, t: dt.time) -> dt.datetime:
    from .calendar_jp import JST
    return dt.datetime.combine(d, t, tzinfo=JST)


def wrote(at) -> str:
    """指令写的时刻 →「10/14 19:21 写」（读不了 → ""）。"""
    t = _tsj(at)
    return f"{t:%m/%d %H:%M} 写" if t else ""


def _last_item(book: dict | None, kind: str, t: str | None = None) -> dict | None:
    """账本里最近一条读到、生效了的固定口数 / 比例指令（撤回 / 作废 / 没执行的不算）。"""
    items = ((book or {}).get("manual") or {}).get("items") or {}
    c = [it for it in items.values() if isinstance(it, dict) and it.get("kind") == kind and not it.get("clear")
         and (t is None or it.get("ticker") == t) and it.get("status") in ("done", "pending")]
    return max(c, key=lambda x: str(x.get("at") or ""), default=None)


def fix_name(t, u) -> str:
    """「固定 1482 对冲版美国 7〜10 年国债 678 口」。"""
    return f"固定 {_lab(t)} {int(u):,} 口"


def _fix_quote(book: dict | None, t: str, u, tail: str = "") -> str:
    """「『固定 1482 … 678 口』<tail>（10/14 19:21 写）」（tail：「凑钱」「调」这类动词放在写的时刻前面，与 D7 的例句同一个语序）。"""
    it = _last_item(book, "corefix", t)
    w = wrote(it.get("at")) if it else ""
    return f"『{fix_name(t, u)}』{tail}" + (f"（{w}）" if w else "")


def src_note(src: str, book: dict | None, t: str | None = None, fixed=None) -> str:
    """来源 → 一句话（排单那一刻；存在单的 src_txt 上）：
    rule →「规则再平衡」；core_fix →「照你的『固定 1482 … 678 口』调（10/14 19:21 写）」；
    fix_fund →「为你的『固定 1482 … 678 口』凑钱（10/14 19:21 写）」（fixed：为哪几只固定的凑钱；没给 = 全部固定的；
    几只 →「为你的『固定 A』（… 写）、『固定 B』（… 写）凑钱」）；
    manual_core →「照你写的闲置资金比例 50%（10/14 19:21 写）」。"""
    fx = {}
    for x, u in ((((book or {}).get("manual") or {}).get("core_fix")) or {}).items():
        try:
            fx[str(x)] = int(u)
        except (TypeError, ValueError):
            continue
    if src == "rule":
        return SRC_WORD_CORE["rule"]
    if src == "core_fix":
        return f"照你的{_fix_quote(book, t, fx[t], '调')}" if t in fx else SRC_WORD_CORE["core_fix"]
    if src == "fix_fund":
        xs = [x for x in (fixed if fixed is not None else sorted(fx)) if x in fx]
        if not xs:
            return SRC_WORD_CORE["fix_fund"]
        xs = list(dict.fromkeys(xs))
        if len(xs) == 1:
            return f"为你的{_fix_quote(book, xs[0], fx[xs[0]], '凑钱')}"
        return "为你的" + "、".join(_fix_quote(book, x, fx[x]) for x in xs) + "凑钱"
    if src == "manual_core":
        try:
            pct = float((((book or {}).get("manual") or {}).get("core_pct")) or 100.0)
        except (TypeError, ValueError):
            pct = 100.0
        it = _last_item(book, "core")
        w = wrote(it.get("at")) if it else ""
        return f"照你写的闲置资金比例 {pct:g}%" + (f"（{w}）" if w else "")
    return ""


def src_line(o) -> str:
    """单上记的来源的一句话（没有 → ""：旧账本照旧）。"""
    return str(_g(o, "src_txt") or "") if src_of(o) else ""


# ══════════════════════════ 今天会发生什么：一个判断（outlook；D5，2026-10-15）══════════════════════════
# 2026-10-15 事故：面板写「不会下单（预计）」、09:30 自检推「✓ 通过 · 开盘后再下 1」、执行器的汇总照旧写 07:40 的「开盘后按始値检查、减股再下」，
# 各算一套。现在「每笔单 / 每条等着的指令今天会不会下、什么时候、为什么」只在这里判断（纯函数，只读）：面板的交易页（角标、「不会下单」）、
# /api/status、09:30 自检、执行器的汇总推送、撤单推送、面板的「今天该下但没有执行路径」与 15:25 之后的汇总都调它。
OUT_WORD = {"will": "会下", "done": "结束", "wont": "今天不会下", "later": "之后才下"}
WONT_NOTE = ("不会下", "钱没来", "与模型不同", "买不起")      # 「不下」（SKIPPED）的说明里有这些 → 今天不会下（不是规则自己的正常结果）
NOW_SUPERSEDED = "被盘中的新单取代"                  # 等开盘后的买单：盘中已经为同一只下了单（复核 R2，2026-10-16）
OK_NOTE = ("与模型相同", "被新的固定口数取代", "手动指令已撤回", "一起撤", "不是错误", "已撤回", "分钟后再试", NOW_SUPERSEDED)
OPEN_AT = {"tachibana": dt.time(9, 5), "paper": dt.time(9, 25)}   # 等开盘后的买单什么时候下（立花 09:05 / 09:20；模拟账户 09:25 前后的开盘撮合）
PAPER_OPEN_END = dt.time(11, 30)                     # 模拟账户当天的开盘撮合到这之前（之后 → 下一次早上的运行照旧撮合）
TRADE_HEAD = "★ 交易"                               # 交易问题的推送标题开头（level = warn；经济威胁提醒不用它）
NO_PATH_S = 600                                      # 过了该下的时刻这么久还没有执行路径 →「今天该下但没有执行路径」（U4）
CHIP = {"fund": "不会下单（预计）", "halt": "不会下单（HALT）", "closed": "已收盘", "blocked": "不会再发", "open_missed": "不会下单",
        "paused": "暂停中"}


def skip_wont(o) -> bool:
    """「不下」（SKIPPED）是「今天不会下」（凑钱的卖单没了 / 钱没来 / 余力不够 / 错过寄付与模型不同）吗；
    与模型相同的不下（资格、跳空…）、被取代、撤回、一会儿再试 → 不是。"""
    n = str(_g(o, "note") or "")
    if any(x in n for x in OK_NOTE):
        return False
    return any(x in n for x in WONT_NOTE)


def asked_cids(book: dict | None, waiting=()) -> set:
    """已经写了撤单（还没处理完）的单的 cid：指令文件里还没读的（被撤销的撤回不算）+ 账本里 pending 的撤单指令（job_cids：整组撤单的
    主单 + grp + 在等的；「一起撤买单」靠这笔卖出的钱、还没发出的买单）。执行器发单前的保护（_cancel_asked）与 outlook 用。"""
    from . import manual_orders as MO
    waiting = [r for r in waiting or [] if isinstance(r, dict)]
    void = MO.voided(waiting)
    items = ((book or {}).get("manual") or {}).get("items") or {}
    orders = [x for x in (book or {}).get("orders") or [] if isinstance(x, dict)]
    out = set()                                            # 整组撤单（grp；2026-10-16）：同一组的每一笔都算「撤单中」
    for r in waiting:
        if r.get("kind") == "cancel_order" and r.get("id") not in void:
            out.update(job_cids(r, orders))
    for it in items.values():                              # 还在等立花确认的撤单（grp_wait）也算（MO.handling_cids）
        if isinstance(it, dict) and it.get("kind") == "cancel_order" and it.get("status") == "pending":
            out.update(job_cids(it, orders))
    return out


def legacy_rec(r: dict | None) -> bool:
    """这条撤单指令是以前的「一起撤买单」吗（一笔卖单的 deps=cancel、没有 grp；在等立花确认的记 grp_legacy）。"""
    from .manual_orders import _CID
    r = r or {}
    m = _CID.match(str(r.get("cid") or ""))
    return bool(r.get("grp_legacy") or (r.get("deps") == "cancel" and not r.get("grp") and m and m.group(2) == "SELL"))


def job_cids(r: dict | None, orders) -> list[str]:
    """一条还在处理的撤单指令要撤 / 在等的单 = MO.handling_cids + 「一起撤买单」靠这笔卖出的钱、执行器还没发出的买单（deps_of：撤单的运行会在本地
    一起撤掉）。复核 6（2026-10-16）：以前不算这些买单 —— 09:05 / 09:20 的运行拿着锁时你点了「一起撤买单」，执行器照样把等开盘后的买单发出去；
    面板也写「同一组撤单中：等它结束再撤」。执行器发单前的保护、面板的「撤单中」、cancel_jobs 同一个。"""
    from . import manual_orders as MO
    out = MO.handling_cids(r)
    if legacy_rec(r):
        c = str((r or {}).get("cid") or "")
        s = next((x for x in orders or [] if str(_g(x, "cid")) == c), None)
        if s is not None and _g(s, "side") == "SELL":
            out += [d for d in (str(_g(x, "cid")) for x in deps_of(s, orders)) if d not in out]
    return out


# 同一组同时只有一个撤单（2026-10-16 简化：以前几条撤单指令同时处理同一组，合并 / 交接越补越多，还是会先撤卖单）。
# 一条撤单指令盖着的单（cancel_scope）：它要撤的（主单 + 整组撤单的 grp + 还在等的成员）+ 这些单所在的一组 + 范围里卖单靠它的钱的买单（fund_src）。
# 还在处理的撤单（cancel_jobs：执行器还没读的 + 账本里 pending 的）盖着的单：别的撤单一律先拒绝（cancel_conflict：check、面板的按钮、
# 执行器、命令行与预览同一个判断），等它结束再撤；面板那几行不给「撤单」。
def cancel_scope(r: dict | None, orders, book: dict | None, G=None) -> set:
    """一条撤单指令（或面板一行 {"cid": …}）盖着的单 → {cid}（只读）。"""
    from . import manual_orders as MO
    r = r or {}
    G = groups(orders, book) if G is None else G
    base = set(MO.cancel_cids(r)) | {str(c) for c in list(r.get("grp_all") or []) + list(r.get("grp_wait") or [])}
    out = set(base)
    for c in base:
        out.update(G.get(c) or [])
    by = {str(_g(x, "cid")): x for x in orders or []}
    sells = {c for c in out if c in by and _g(by[c], "side") == "SELL"}
    for x in orders or []:
        if _g(x, "side") == "BUY" and _in_current(x, book) and sells & {str(y) for y in (_g(x, "fund_src") or [])}:
            out.add(str(_g(x, "cid")))
    return out


def _job_who(r: dict) -> str:
    """撤单指令是哪一条：「卖 1545 纳斯达克 100 的「一起撤买单」」/「买 1482 … 这一组的整组撤单」/「卖 1545 … 的撤单」。"""
    from .manual_orders import _CID
    m = _CID.match(str(r.get("cid") or ""))
    w = (("买 " if m.group(2) == "BUY" else "卖 ") + _lab(m.group(3))) if m else "一笔单"
    if legacy_rec(r):
        return w + " 的「一起撤买单」"
    return w + (" 这一组的整组撤单" if r.get("grp") or r.get("grp_wait") else " 的撤单")


def _job_state(r: dict) -> str:
    """撤单指令现在在做什么：「等执行器」/「等立花确认买单的撤单，最长到 09:40」（最多 10 分钟、收盘前 3 分钟为止）。"""
    if not r.get("grp_wait"):
        return "等执行器"
    t0 = _tsj(r.get("grp_wait0")) or _tsj(r.get("recheck_at"))
    if t0 is None:
        return "等立花确认买单的撤单"
    return f"等立花确认买单的撤单，最长到 {wait_end(t0):%H:%M}"


def wait_end(t0: dt.datetime) -> dt.datetime:
    """整组撤单从 t0 开始等立花确认买单的撤单，最多等到什么时候（10 分钟、收盘前 3 分钟为止）。"""
    from .manual_orders import GROUP_LAST_S, GROUP_WAIT_MAX_S
    return min(t0 + dt.timedelta(seconds=GROUP_WAIT_MAX_S), _at(t0.date(), CLOSE_T) - dt.timedelta(seconds=GROUP_LAST_S))


def cancel_jobs(book: dict | None, waiting=(), now: dt.datetime | None = None, G=None) -> list[dict]:
    """还在处理的撤单 → [{id, cid, at, scope, targets, who, state}]（写的先后；只读）：账本里 pending 的撤单指令（过了收盘还在等的不算：
    执行器不吵地结束它）+ 指令文件里执行器还没读的（被撤销的撤回不算）。targets = 它要撤 / 在等的单（MO.handling_cids）。"""
    from . import manual_orders as MO
    b = book or {}
    orders = [x for x in b.get("orders") or [] if isinstance(x, dict)]
    G = groups(orders, b) if G is None else G
    recs = [it for it in ((b.get("manual") or {}).get("items") or {}).values()
            if isinstance(it, dict) and it.get("kind") == "cancel_order" and it.get("status") == "pending"
            and not (now is not None and MO.grp_wait_stale(it, now))]
    w = [r for r in waiting or [] if isinstance(r, dict)]
    void = MO.voided(w)
    have = {it.get("id") for it in recs}
    recs += [r for r in w if r.get("kind") == "cancel_order" and r.get("id") not in void and r.get("id") not in have]
    return sorted((_job(r, orders, b, G) for r in recs), key=lambda j: j["at"])


def _job(r: dict, orders, book: dict | None, G) -> dict:
    """一条撤单指令 → cancel_jobs 的一项。"""
    return {"id": r.get("id"), "cid": str(r.get("cid") or ""), "at": str(r.get("at") or ""), "scope": cancel_scope(r, orders, book, G),
            "targets": set(job_cids(r, orders)), "who": _job_who(r), "state": _job_state(r)}


def cancel_conflict(r: dict, book: dict | None, jobs, G=None) -> str | None:
    """这条撤单（或面板一行 {"cid": …}）现在能不能写 / 做：盖着的单和还在处理的撤单（jobs）有重叠 → 理由（不然 None）。
    要撤的单本身已经在撤 →「… 的单 … 已经在撤（那一条，它在做什么）」；只是同一组 →「同一组正在撤单（…）：等它结束再撤」。"""
    from . import manual_orders as MO
    if not jobs:
        return None
    b = book or {}
    orders = [x for x in b.get("orders") or [] if isinstance(x, dict)]
    G = groups(orders, b) if G is None else G
    sc = cancel_scope(r, orders, b, G)
    mine = MO.cancel_cids(r)
    for j in jobs:
        if j.get("id") is not None and j.get("id") == (r or {}).get("id"):
            continue
        hit = next((c for c in mine if c in j["targets"]), None)
        if hit is not None:
            m = MO._CID.match(hit)
            return f"{_lab(m.group(3)) if m else ''} 的单 {hit} 已经在撤（{j['who']}，{j['state']}）".lstrip()
        ov = sc & j["scope"]
        if ov:
            rel = "同一组" if any(set(G.get(c) or ()) & ov for c in mine) else "有关的单（凑钱的卖单 / 靠它的钱的买单）"
            return f"{rel}正在撤单（{j['who']}，{j['state']}）：等它结束再撤"
    return None


def _fund_why(x: dict, asked: set, unit: str) -> tuple[str, list]:
    """unfunded_buys 的说明 →（一句话, 没了的卖单）：旧账本（没有 fund_src）的「不会下单（预计）」。"""
    gone = [g for g in x["gone"] if g.get("status") == "CANCELLED" or str(g.get("cid")) in asked]
    src = ("资金来源的卖单已撤（" + "、".join("卖 " + _labq(g.get('ticker'), f"{int(g.get('sent_qty') or g.get('qty') or 0):,} "
                                                          f"{_unit(g)}") for g in gone) + "）；") if gone else ""
    return (f"{src}开盘时能用的钱最多约 ¥{x['cash'] + x['sells']:,.0f}，按跌停价买 {x['lot']:,} {unit}也要约 "
            f"¥{x['need']:,.0f}：开盘后这笔下不成（执行器会放弃）"), gone


def instr_due(at, today: dt.date) -> dt.datetime | None:
    """一条手动指令今天最晚该在什么时刻下（09:30 自检 G24 与 outlook 共用）：写于开盘前 / 前几天 → 今天 09:00 开盘；盘中写的 → 写的时刻；
    午休写的 → 12:30；收盘后 / 休市日写的 → 下一个交易日 09:00（在今天之后 → None）。读不了 → None。"""
    from . import manual_orders as MO
    w = _tsj(at)
    if w is None:
        return None
    mode, d = MO.timing(w)
    t = w if mode == "now" else _at(d, MO.SESSION[1][0] if mode == "lunch" else MO.SESSION[0][0])
    if t.date() < today:
        t = _at(today, MO.SESSION[0][0])
    return t if t.date() == today else None


def _instr_row(r: dict, book: dict | None, now: dt.datetime, tag: str | None, halt: bool, paused: bool, seen: bool) -> dict | None:
    """一条等着的手动指令（seen：执行器读过、账本里 pending；否则指令文件里还没读）→ outlook 的一行；撤回 / 撤单 / 撤销撤回本身 → None。"""
    from . import manual_orders as MO
    k = r.get("kind")
    if k in ("cancel", "cancel_order", "uncancel"):
        return None
    today = now.date()
    paper = str(tag or "").startswith("paper")
    mode, d = MO.timing(now)
    nxt = d if mode == "next" else next_trading_day(today)
    row = {"ref": str(r.get("id")), "kind": "instr", "ikind": k, "ticker": r.get("ticker"), "side": r.get("side"),
           "qty": r.get("shares") or r.get("units"), "unit": "口" if k in ("core", "corefix") else "股", "state": "will",
           "act_at": None, "reason": "", "chip": None, "cls": "", "what": MO.describe(r), "at": r.get("at"), "src": "", "src_txt": "",
           "gone": [], "seen": seen}
    try:
        wt = (MO.msg_text(r, now) if seen and r.get("msg") else "") or MO.wait_text(r, now, book, tag)
    except Exception:                                      # noqa: BLE001  只是说明
        wt = ""

    def put(state: str, at: dt.datetime | None, reason: str, cls: str = "") -> dict:
        if state == "will" and at is not None and at.date() > today:
            state = "later"
        row.update(state=state, act_at=at, reason=reason or wt, cls=cls)
        return row
    if halt and k in MO.ORDER_KINDS + ("core", "corefix"):
        return put("later", None, MO.halt_text(r), "halt")
    if k == "unblock":
        return put("later", None, MO.next_decision(now))
    if MO.allin_member(r):
        fd = MO.allin_fill(now, book, tag)
        return put("will", _at(fd, MO.SESSION[0][0]), f"{MO.allin_when(now, book, tag)}整批")
    if k == "corefix":
        cf = MO.corefix_fill(now, book, tag)
        if cf["mode"] == "behind":
            return put("will", None, wt) if paper else put("later", _at(nxt, MO.SESSION[0][0]), wt)
        if cf["intraday"]:
            due_ = instr_due(r.get("at"), today) or (now if cf["mode"] == "now" else
                                                      _at(today, MO.SESSION[1][0] if cf["mode"] == "lunch" else MO.SESSION[0][0]))
            return put("wont", due_, "面板自动下单今天暂停了：修好之后在 Mac 对话里说「再试一次」", "paused") if (
                paused and cf["mode"] == "now") else put("will", due_, wt)
        return put("will", _at(cf["day"], MO.SESSION[0][0]), wt)
    if k not in MO.ORDER_KINDS + ("core",):
        return put("later", None, wt)
    if r.get("hold") == today.isoformat():
        return put("later", _at(nxt, MO.SESSION[0][0]), wt)
    if r.get("wait"):
        return put("will", None, wt)                       # 等上一笔成交 / 等凑钱的卖单：路径是执行器自己（不判断时刻）
    rd = MO.rolled_over(r, now) if seen else None
    if rd is not None:
        return put("later", _at(rd, MO.SESSION[0][0]), MO.rolled_text(r, now) or wt)
    if mode == "next":                                     # 收盘后 / 休市日：下一个交易日开盘
        return put("later", _at(d, MO.SESSION[0][0]), wt)
    if MO.morning_behind(book, now):                       # 今天早上的运行还没完成：模拟账户面板补跑；立花 08:55 之后不自动补跑
        if not paper and now.time() >= MO.CUTOFF:
            return put("later", _at(nxt, MO.SESSION[0][0]), wt)
        return put("will", None, wt)
    late_open = mode == "open" and now.time() >= MO.CUTOFF   # 寄付截止之后：开盘后由盘中的路下（与 MO.when_for 同一个口径）
    if (k in MO.ORDER_KINDS and r.get("ticker") and (mode in ("now", "lunch") or late_open)
            and MO.busy_today(book, r.get("ticker"), now)):
        return put("later", _at(nxt, MO.SESSION[0][0]), wt)
    due_ = instr_due(r.get("at"), today) or (now if mode == "now" else
                                              _at(today, MO.SESSION[1][0] if mode == "lunch" else MO.SESSION[0][0]))
    if paused and mode == "now":
        return put("wont", due_, "面板自动下单今天暂停了：修好之后在 Mac 对话里说「再试一次」", "paused")
    return put("will", due_, wt)


def _order_row(o: dict, *, now, paper, tag, halt, asked, casc, unf, f) -> dict:
    """当前决策的一笔单 → outlook 的一行（判断顺序：结束了的 → 不下 / 被拒 / 错过 → 撤单中 → 立花收盘后 → HALT → 被挡不再试 →
    凑钱的卖单没了 / 开盘时一定买不起 → 立花开盘后的补单没跑成 → 状态不明 → 会下）。"""
    cid, s = str(o.get("cid")), o.get("status")
    today = now.date()
    row = {"ref": cid, "kind": "order", "ticker": o.get("ticker"), "side": o.get("side"), "okind": o.get("kind") or "stock",
           "qty": int(o.get("sent_qty") or o.get("qty") or 0), "unit": _unit(o), "status": s, "state": "will", "act_at": None,
           "reason": "", "chip": None, "cls": "", "src": src_of(o), "src_txt": src_line(o), "gone": [],
           "manual": o.get("reason") in MANUAL_REASONS, "phase": o.get("phase") or "morning"}
    ph = row["phase"]
    day = (_tsj(o.get("sent_at")) or now).date() if ph == "now" else f
    note = str(o.get("note") or "")

    def put(state: str, reason: str = "", cls: str = "", chip: str | None = None, **kw) -> dict:
        row.update(state=state, reason=reason, cls=cls, chip=chip if chip is not None else CHIP.get(cls) if state == "wont" else None, **kw)
        return row
    if s in ("FILLED", "RESOLVED", "CANCELLED", "UNFILLED", "EXPIRED"):
        return put("done", note)
    if s == "SKIPPED":
        return put("wont", note, "skip", chip="") if skip_wont(o) else put("done", note)
    if s in ("REJECTED", "MISSED"):
        return put("wont", note or STATUS_TEXT.get(s, s), "reject" if s == "REJECTED" else "missed", chip="")
    if cid in asked:
        return put("done", "撤单中", "asked", chip="撤单中")
    if not paper and tag and day is not None and (day < today or (day == today and now.time() >= CLOSE_T)):
        unsent = s not in AT_EXCH
        return put("wont" if unsent else "done", f"成交日 {day:%m/%d} 的交易所已经收盘：" + ("这笔没下" if unsent else "没成交的部分已失效")
                   + "，明早对账记账（之后什么都不会再发生）", "closed", chip="已收盘")
    from .live_unified import HALT_WAIT
    if paper and s == "DEFERRED" and note.startswith(HALT_WAIT):     # 开盘撮合时被 HALT 挡下（D3）
        return put("wont", "开盘撮合时 HALT 生效中：这笔没下（11:30 之前解除后可以再跑一次 bash scripts/liveu.sh run --broker paper "
                           "--phase open，否则明早对账记为没买）", "halt")
    if halt and s in ("PLANNED", "DEFERRED", "BLOCKED"):  # 模拟账户的「等开盘后」：09:25 前后的开盘撮合按同样的闸门（D3）
        return put("wont", "HALT 生效中：还没发出的单不下" + ("（开盘撮合在 09:25 前后：那之前解除才会下）" if paper
                                                     else "（开盘后的补单在 09:05 / 09:20：那之前解除才会下）"), "halt")
    if s in ("PLANNED", "BLOCKED") and not blocked_retry(o, now, f) and not (s == "PLANNED" and ph == "now"):
        return put("wont", (note + "：" if note else "") + "今天不会再发", "blocked")
    if cid in casc and casc[cid]["act"] == "skip":       # 执行器记的凑钱卖单没了：按现在能用的钱重算（与撤单那一刻的级联同一个函数）
        return put("wont", casc[cid]["note"], "fund", gone=list(casc[cid]["srcs"]))
    if cid in unf:                                       # 旧账本（没有 fund_src）：开盘时一定买不起一单元
        why, gone = _fund_why(unf[cid], asked, row["unit"])
        return put("wont", why, "fund", gone=gone)
    if not paper and s == "DEFERRED" and f is not None and (today > f or (today == f and now.time() >= LATE_UNTIL)):
        return put("wont", "开盘后的补单（09:05 / 09:20）没跑成：今天不会再下", "open_missed")
    if s in ("SENDING", "ERROR"):
        return put("will", "状态不明：可能已被受理（去注文一覧核对；登记之前执行器不再发别的单）", "unknown")
    return put("will", casc[cid]["note"] if cid in casc else note)


def _act_at(row: dict, o: dict, now: dt.datetime, paper: bool, f: dt.date | None) -> dt.datetime | None:
    """会下的单什么时候下：盘中的 = 发出的时刻；在交易所的 = 发出的时刻（没有 → 成交日 09:00）；等开盘后的 = 立花 09:05 / 模拟账户 09:25
    （模拟账户 11:30 之后还没撮合 → 下一次早上的运行）；计划 / 被挡的早上的单 = 成交日 09:00。"""
    s, today = o.get("status"), now.date()
    if row["phase"] == "now" or s in AT_EXCH + ("ERROR",):
        return _tsj(o.get("sent_at")) or (_at(f, OPEN_T) if f else None)
    if f is None:
        return None
    if s == "DEFERRED":
        if paper and (today > f or (today == f and now.time() >= PAPER_OPEN_END)):
            nd = today if today > f and is_trading_day(today) and now.time() < dt.time(7, 40) else next_trading_day(today)
            return _at(nd, dt.time(7, 40))
        return _at(f, OPEN_AT["paper" if paper else "tachibana"])
    return _at(f, OPEN_T)


def outlook(book: dict | None, waiting=(), now: dt.datetime | None = None, *, tag: str | None = None, halt: bool | None = None,
            paused: bool = False, cash: float | None = None, asked=None, instr: bool = True) -> dict:
    """今天会发生什么（D5；纯函数、只读）：当前决策的每笔单 + 每条等着的手动指令 → 一行
    {ref（cid / 指令 id）, kind（order / instr）, ticker, side, qty, unit, state, act_at（什么时候下）, reason, chip（交易页的状态；None = 照单的状态）, cls}：
      state：will（会下 / 已下、在交易所）| done（结束：成交 / 撤了 / 撤单中 / 规则自己的不下…）| wont（今天不会下：凑钱的卖单没了、钱不够、
             被拒、错过、HALT、立花收盘后 / 补单没跑成、面板自动下单暂停…）| later（之后某天：收盘后写的、明天开盘、HALT 解除后…）。
    还没发出的买单：执行器记了凑钱的卖单（fund_src）→ 按 fund_cascade 的预览（资金按来源分组、按单的先后累计扣减）；旧账本 → unfunded_buys
    的保守估计。被挡的单 08:55 之前还会再发（blocked_retry）→ 算「会下」；状态不明的单单独给理由（cls = unknown）。
    waiting：指令文件里还没读的（MO.unseen）；halt：None = 看 HALT 文件；paused：面板自动下单今天暂停；cash：开盘时能用的钱
    （None = cash_hi）；asked：当成「撤单中」的 cid（None = 从 waiting / 账本里的撤单指令算；() = 不算 —— 撤单推送「撤之前」那一次）；
    instr=False：只看单。→ {"rows": [...], "orders": {cid: 行}, "items": {指令 id: 行}, "asked": set, "n": {state: 笔数}}。"""
    from . import paths
    now = now or now_jst()
    b = book or {}
    st = b.get("state") or {}
    d = st.get("last_date")
    cur = [o for o in b.get("orders") or [] if isinstance(o, dict) and o.get("decided_on") == d]
    paper = str(tag or "").startswith("paper") or str(b.get("broker") or "").startswith("Paper")
    halt = paths.halt_file().exists() if halt is None else bool(halt)
    waiting = [r for r in waiting or [] if isinstance(r, dict)]
    asked = asked_cids(b, waiting) if asked is None else {str(x) for x in asked}
    f = fill_day_of(b)
    try:
        cash_ = cash_hi(b, tag) if cash is None else float(cash)
    except (TypeError, ValueError):
        cash_ = 0.0
    try:                                                    # 旧账本（没有 fund_src）：开盘时一定买不起一单元的买单
        unf = unfunded_buys(b, asked, cash=cash_)
    except (TypeError, ValueError, KeyError):
        unf = {}
    unf = {c: x for c, x in unf.items() if not any(str(o.get("cid")) == c and o.get("fund_src") for o in cur)}
    casc = {}
    if any(o.get("side") == "BUY" and o.get("fund_src") and o.get("status") in DEP_OPEN for o in cur):
        try:                                                # 执行器记的凑钱卖单：撤单那一刻 / 开盘时的重算的预览（同一个函数）
            casc = {str(_g(r["o"], "cid")): r for r in fund_cascade(
                cur, cash=cash_ - _reserve_of(b, paper), now=now, book=b, dead=asked, apply=False, fill=f, queued=paper)}
        except (TypeError, ValueError, KeyError):
            casc = {}
    rows, orders = [], {}
    po = b.get("paper_open") or {}
    stop = str(po.get("stop") or "") if paper and d and po.get("decided_on") == d and f is not None and now.date() == f else ""
    for o in cur:
        row = _order_row(o, now=now, paper=paper, tag=tag, halt=halt, asked=asked, casc=casc, unf=unf, f=f)
        if row["state"] == "will":
            row["act_at"] = _act_at(row, o, now, paper, f)
            if stop and (o.get("status") == "DEFERRED"
                         or (o.get("status") == "SENT" and (o.get("phase") or "morning") == "morning")):
                nd = next_trading_day(now.date())        # 今天的开盘撮合不做（公司行为 / 开盘价超出制限値幅）→ 明早的运行按日线撮合
                row.update(state="later", act_at=_at(nd, dt.time(7, 40)),   # （复核 F3，2026-10-16：以前还写「今天 09:25」，面板误推「没有执行路径」）
                           reason=f"今天不做开盘撮合（{stop}）：{nd:%m/%d} 07:40 的运行按今天的正式开盘价撮合")
            elif row["act_at"] is not None and row["act_at"].date() > now.date():
                row["state"] = "later"
                if paper and o.get("status") == "DEFERRED":    # 今天的开盘撮合过了 11:30 还没下：不再写 07:40 存下的旧说明
                    row["reason"] = (f"今天的开盘撮合（09:25〜11:30）没下成 → {row['act_at']:%m/%d %H:%M} 的运行按那天的开盘价照旧撮合"
                                     "（钱够才买）")
        rows.append(row)
        orders[row["ref"]] = row
    items = {}
    if instr:
        from . import manual_orders as MO
        void = MO.voided(waiting)
        gone_ids = MO.cancelled(waiting)
        its = ((b.get("manual") or {}).get("items") or {})
        recs = [(it, True) for it in its.values() if isinstance(it, dict) and it.get("status") == "pending" and not it.get("cancel_req")]
        recs += [(r, False) for r in waiting if r.get("id") not in void]
        for r, seen in recs:
            if r.get("id") in gone_ids:
                continue
            try:
                x = _instr_row(r, b, now, tag, halt, paused, seen)
            except Exception:                              # noqa: BLE001  一条读不了的指令：不下结论
                x = None
            if x is not None:
                rows.append(x)
                items[x["ref"]] = x
        unread_fix = {r.get("ticker") for r, seen in recs if not seen and r.get("kind") == "corefix"}
        try:                                               # 读了、还没照它调的固定口数（corefix_pending；D1）：没有指令行 → 补一行
            pend = MO.corefix_pending(b, None, now)
        except Exception:                                  # noqa: BLE001
            pend = {}
        for t, u in pend.items():
            if t in unread_fix:
                continue
            it = _last_item(b, "corefix", t) or {"id": f"fix:{t}", "kind": "corefix", "ticker": t, "units": u, "clear": u is None}
            x = _instr_row({**it, "status": "pending", "msg": ""}, b, now, tag, halt, paused, True)
            if x is not None:
                x.update(ref=f"fix:{t}", what=(fix_name(t, u) if u is not None else f"{_lab(t)} 恢复按规则") + "（还没照它调）")
                rows.append(x)
                items[x["ref"]] = x
    n = {k: sum(1 for x in rows if x["state"] == k) for k in OUT_WORD}
    return {"rows": rows, "orders": orders, "items": items, "asked": asked, "n": n}


def row_text(row: dict) -> str:
    """outlook 的一行 →「买 1482 对冲版美国 7〜10 年国债：678 口：<原因>」/ 指令「固定 ETF 口数 …（M…）：<原因>」（代码带名字）。"""
    from .names import annotate
    if row.get("kind") == "order":
        q_ = f"{int(row.get('qty') or 0):,} {row.get('unit') or '股'}"      # 嵌套 f-string 不用同一种引号（3.10 / 3.11 不认）
        head = f"{'买' if row.get('side') == 'BUY' else '卖'} {_labq(row.get('ticker'), q_)}"
        if row.get("src_txt"):
            head += f"（{row['src_txt']}）"
    else:
        head = f"{row.get('what') or row.get('ref')}（{row.get('ref')}）"
    r = str(row.get("reason") or "")
    return head + (f"：{annotate(r)}" if r else "")


def act_text(row: dict, now: dt.datetime) -> str:
    """act_at →「今天 09:05」/「10/16 09:00」（没有 → ""）。"""
    t = row.get("act_at")
    if not isinstance(t, dt.datetime):
        return ""
    return f"今天 {t:%H:%M}" if t.date() == now.date() else f"{t:%m/%d %H:%M}"


def trade_key(row: dict, now: dt.datetime, what: str = "") -> str:
    """★ 交易 推送的去重键（notify_seen.first）：哪一类 + 哪一笔 + 哪天下 —— 不含金额 / 股数 / 名字 / 原因的文字
    （同一笔的说明里的数字变了、名字补上了，不算新的原因）。"""
    t = row.get("act_at")
    day = t.date().isoformat() if isinstance(t, dt.datetime) else now.date().isoformat()
    return f"{TRADE_HEAD}|{what}|{row.get('cls') or row.get('state')}|{row.get('ref')}|{day}"


def new_wont(before: dict | None, after: dict, skip=()) -> list[dict]:
    """撤单前后各算一次 outlook：之后新出现的「今天不会下」（skip 里的 —— 撤的那几笔自己、撤单推送已经写了的 —— 不算）。"""
    old = {r["ref"] for r in (before or {}).get("rows") or [] if r["state"] == "wont"}
    skip = {str(x) for x in skip or ()}
    return [r for r in after.get("rows") or [] if r["state"] == "wont" and r["ref"] not in old and r["ref"] not in skip]


def not_today(ol: dict, now: dt.datetime) -> list[dict]:
    """15:25 之后的汇总（M3 / M18）：今天没下成 / 不会下的全部 —— 今天不会下的单与指令（HALT 的不算：解除后照原样）、
    今天该下却还等着的指令（改到之后某天的）、还没发出的今天的单。"""
    out = []
    for r in ol.get("rows") or []:
        if r["cls"] == "halt":
            continue
        if r["state"] == "wont":
            out.append(r)
        elif r["kind"] == "instr" and r["state"] in ("later", "will") and instr_due(r.get("at"), now.date()) is not None:
            out.append(r)
        elif r["kind"] == "order" and r["state"] in ("will", "later") and r.get("status") in ("PLANNED", "DEFERRED", "BLOCKED"):
            out.append(r)
    return out


# ══════════════════════════ B1 撤单 ══════════════════════════
def _in_current(o, book: dict | None) -> bool:
    """这笔单是账本当前决策的吗（cancel_why 与「同一组」同一个判断）。"""
    return _g(o, "decided_on") == ((book or {}).get("state") or {}).get("last_date")


def cancel_why(o, book: dict, now: dt.datetime, paper: bool) -> str | None:
    """这笔单现在能不能撤：能 → None；不能 → 理由。面板（显示「撤单」按钮）、手动指令的检查、执行器共用。
    执行器自己还没发到交易所的单（PLANNED / DEFERRED：计划 / 等开盘后）也能撤 = 执行器不再发（D2；2026-10-15：以前撤了凑钱的卖单，
    等开盘后的买单撤不了）：成交日当天、立花在收盘（15:30）之前。"""
    st = _g(o, "status")
    unsent = st in UNSENT
    if st not in CANCELLABLE and not unsent:
        return f"状态是「{STATUS_TEXT.get(st, st)}」：只撤还挂着的单（已下单 / 部分成交）或执行器还没发出的单（计划 / 等开盘后）"
    if not unsent and GONE in str(_g(o, "note") or ""):   # 撤单时立花回已经失效 / 被拒：单不在交易所了（不给「撤单」；简化 2026-10-16）
        return f"立花那边已经{gone_word(o)}（撤单时查到），不用撤"
    if not _in_current(o, book):
        return "不是当前决策的单（已经对账过了）"
    f = fill_day_of(book)
    if f != now.date():
        return f"不是今天的单（成交日 {f}）"
    if unsent:
        if now.time() >= CLOSE_T:                          # 两种账本同一个截止（面板 15:30 之后不再叫 --phase cancel：cancel_due）
            if paper and st == "DEFERRED":                 # 模拟账户：明早的运行按今天的开盘价照旧撮合（复核 promise F1，2026-10-16：
                return ("已经收盘（15:30）：模拟账户等开盘后的买单明早的运行按今天的开盘价照旧撮合（钱够才买），现在撤不了"   # 以前面板接受、
                        "（明早对账之后不想拿着：写手动卖出）")                            # 却没有路去撤，第二天照样成交）
            return "已经收盘（15:30）：这笔今天不会再发了，不用撤"
        return None
    if paper:
        if (_g(o, "phase") or "morning") != "morning":
            return "模拟账户：盘中 / 开盘后的单当场成交了，撤不了"
        if now.time() >= OPEN_T:
            return "模拟账户：寄付单已经在 09:00 开盘（今天 09:25 前后按开盘价撮合；D3），撤不了"
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


def _cancel_one(o, b, paper: bool, now: dt.datetime, source: str, polls: int, resend: bool = True,
                blocked: bool = False) -> tuple[str, str]:
    """撤一笔 → ("done" | "pending" | "failed" | "skipped", 说明)。成功：o.status = CANCELLED（立花：filled_qty / filled_px 记撤单时的成交）。
    执行器还没发出的单（PLANNED / DEFERRED）：不连券商，记 CANCELLED = 执行器不再发（D2；2026-10-15）。
    blocked（整组撤单；2026-10-16）：被挡、还没发到交易所（BLOCKED、没有注文番号）的也在本地撤（执行器不再重试）。
    resend=False（立花，整组撤单的复查）：撤单已经受理过 → 不再发撤单、只查状态；还没到终态 → "pending"（说明不改）。"""
    n = int(_g(o, "sent_qty") or _g(o, "qty") or 0)
    who = f"，{source}" if source else ""
    if blocked and _g(o, "status") == "BLOCKED" and not _g(o, "broker_id"):
        _set(o, status="CANCELLED", fund_src=[],
             note=f"你撤了单（{now:%H:%M}{who}）：被挡、还没发到交易所，执行器不再重试"[:300])
        return "done", _g(o, "note")
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
    ok = not resend                                        # 复查：撤单已经受理过（不再发）
    if resend:
        try:
            ok = bool(b.cancel_order(o.broker_id, o.order_date))
        except Exception as e:                             # noqa: BLE001  适配器本身不抛；抛了也当没撤成，下面再查一次状态
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
    code = str((r or {}).get("status_code") or "").strip()   # 应答里没有状态名称（只有 sOrderStatusCode）时按代码补（复核 3 2026-10-16）
    name = str((r or {}).get("status") or "") or {"6": "取消中", "8": "取消失敗"}.get(code, "") or fin
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
    if r is not None and not fin and (code == "8" or "失敗" in name):   # 撤单在立花那边没成功（取消失敗）、单还挂着：不说「已受理」（复核 2）；
        if q:                                              # 复核 3（2026-10-16）：也认状态码 8（应答里没有名称时）；说明改写（以前留着第一次的
            o.status, o.filled_qty, o.filled_px = "PARTIAL", int(q), float(px)   # 「撤单已受理」→ 整组撤单一直当它取消中、等 10 分钟、每分钟推 ★）
        old = str(o.note or "")
        keep = "" if (ACCEPTED in old or old.startswith(FAILED)) else old
        o.note = (f"{FAILED}（{now:%H:%M}{who}；立花：{name}）：单还挂着 → 在{SITE}撤，或稍后再试"
                  + (f"；原先：{keep}" if keep else ""))[:300]
        return "failed", f"{FAILED}（立花：{name}）：单还挂着 → 在{SITE}撤，或稍后再试"
    if ok and not fin:                                     # 撤单受理了、但单还没到终态（取消中 / 正在撮合）：状态不改成「已撤单」
        if q:                                              # （撤单可能失败：那时单还挂着；明天早上的对账按实际成交记）
            o.status, o.filled_qty, o.filled_px = "PARTIAL", int(q), float(px)
        if not resend:                                     # 复查还没到终态：说明不改（第一次撤的时候已经写了）
            return "pending", "撤单已受理，立花还在处理" + (f"（{name}）" if name else "")
        o.note = (f"你撤了单（{now:%H:%M}{who}）：撤单已受理，立花还在处理"
                  + (f"（{name}）" if name else "") + (f"，查状态失败：{err}" if err and r is None else "")
                  + "；过一会儿在面板 / 立花网站看是否撤掉（还挂着可以再撤）；明天早上的对账按实际成交记")[:300]
        return "pending", o.note
    if not ok and r is not None and not fin and _cancelling(r):   # 立花不受理这次撤单，因为单已经在取消中（之前撤过 / 在立花网站撤的）：
        name = name or "取消中"                            # 不是「撤单失败」（复核 2026-10-16：以前报 ★ 没撤成、整组撤单把卖单留下、退出码 1）；
        if q:                                              # 只认「取消中」（代码 6 / 名称）：「取消失敗」= 单还挂着，照旧报撤单失败（复核 2）
            o.status, o.filled_qty, o.filled_px = "PARTIAL", int(q), float(px)
        if ACCEPTED not in str(o.note or ""):
            o.note = (f"你撤了单（{now:%H:%M}{who}）：{ACCEPTED}（立花那边已经在{name}：之前撤过 / 在立花网站撤的）；"
                      "过一会儿在面板 / 立花网站看是否撤掉；明天早上的对账按实际成交记")[:300]
        return "pending", f"{ACCEPTED}（之前已经撤过），立花还在处理（{name}）"
    if fin in ("EXPIRED", "REJECTED"):                     # 立花不受理撤单、单已经失效 / 被拒（寄付指値没成交 → 全部失効…）：状态不改（对账照旧），
        word = "失效" if fin == "EXPIRED" else "被拒"       # 成交记下、说明里记 GONE（整组撤单的闸门不再当它「还挂着」；复核 5 2026-10-16：
        if q:                                              # 以前汇总行同一笔买单既说「已经失效」又说「没撤掉（还挂着）」，卖单也不撤）
            o.filled_qty, o.filled_px = int(q), float(px)
        got = f"已成交 {q:,}/{n:,} {_unit(o)}，其余{word}" if q else "没成交"
        if GONE not in str(o.note or ""):
            old = str(o.note or "")
            keep = "" if (ACCEPTED in old or old.startswith(FAILED)) else old   # 以前的「撤单已受理 / 没成功」不再留（单已经不在交易所）
            o.note = (f"{now:%H:%M} 撤单时{GONE}（{word}：{name}）：{got}；明天早上的对账按实际成交记"
                      + (f"；原先：{keep}" if keep else ""))[:300]
        return "skipped", f"立花那边已经{word}（{name}）：{got}，不用撤（明天早上照常对账）"
    return "failed", ("撤单失败（立花没受理" + (f"；查状态也失败：{err}" if err else "") + "）：单可能还挂着 → "
                      "在立花网站 / 手机网站（https://kabuka.e-shiten.jp/mfds_smp.php）撤，或稍后再试")


SITE = "立花网站 / 手机网站（https://kabuka.e-shiten.jp/mfds_smp.php）"


def _broker_arg(tag: str | None, paper: bool) -> str:
    """提示里 liveu.sh 的 --broker：paper / tachibana [--demo] [--dry-run]（账本标签 tachibana_demo_dryrun 之类）。"""
    if paper:
        return "paper"
    t = str(tag or "tachibana")
    return "tachibana" + (" --demo" if "_demo" in t else "") + (" --dry-run" if "_dryrun" in t else "")


def _hold_why(o, hold, orders, book: dict | None, now: dt.datetime, paper: bool, tag: str | None) -> str:
    """单笔撤一组里的卖单被闸门挡下的说明（cancel_core；复核 2 2026-10-16）：写实际的 cid 与 --broker；整组撤只在每一笔挡的买单都还挂着 /
    取消中、现在能撤时才提（买单已经成交 / 状态不明 / 撤不了：整组撤单也一笔卖单都不会撤）；立花取消中 / 状态不明 → 叫你在立花网站核对。"""
    by = {str(_g(x, "cid")): x for x in orders}
    cmd = f"bash scripts/liveu.sh cancel {_g(o, 'cid')}"
    b = _broker_arg(tag, paper)
    why = ("同一组的" + "；".join(t for _c, _k, t in hold) + "：卖单不撤（撤了买的钱不够）。真要只撤这笔卖单 → 面板选「只撤这笔卖单」"
           f"（命令行加 --solo：{cmd} --solo --broker {b}）")
    if all(k in ("live", "pending") and by.get(c) is not None and grp_why(by[c], book, now, paper) is None for c, k, _t in hold):
        why += f"；或整组撤（{cmd} --group --broker {b}：先撤买单、确认没成交再撤卖单）"
    if not paper and any(k in ("pending", "unknown") for _c, k, _t in hold):
        why += "；买单撤没撤掉 / 成没成交在" + SITE + "核对"
    return why


def _grp_finish(res: dict, by: dict, now: dt.datetime, fill) -> None:
    """整组撤单的汇总行收尾（cancel_core 最后，单笔撤单都处理完之后；复核 2 2026-10-16）：同一组里不在这次范围里、还开着的卖单写出来
    （「都撤了」只说这次撤的那几笔，不让人以为整组都撤了）；只撤了一部分 / 不等了 / 一笔都没撤成 → ★ 交易 推送。
    立花那边已经失效 / 被拒的卖单不算还开着（简化 2026-10-16）。"""
    for g in (res.get("grp") or {}).values():
        if g.get("legacy"):
            continue
        sc = set(g.get("scope") or [])
        oth = []
        for c in g.get("members") or []:
            x = by.get(c)
            if x is None or c in sc or _g(x, "side") != "SELL" or _g(x, "status") not in GROUP_OPEN:
                continue
            if (_g(x, "status") == "BLOCKED" and not blocked_retry(x, now, fill)) or GONE in str(_g(x, "note") or ""):
                continue
            oth.append(_ord_txt(x) + "（" + _st_txt(x) + "）")
        if oth:
            g["line"] += "；同一组另有 " + "、".join(oth) + " 不在这次整组撤单里"
        if g.get("state") in ("part", "gaveup", "none"):
            res["events"].append(("warn", g["line"]))


def cancel_core(orders: list, book: dict, get_broker, cids=None, *, paper: bool, now: dt.datetime, source: str = "",
                polls: int = POLLS, deps=None, cash=None, need=None, lot_of=None, tag: str | None = None,
                reserve: float = 0.0, queued: bool | None = None, groups=None, waits=None) -> dict:
    """撤单的核心（执行器 / 不建引擎的 cancel_book 共用）。orders：ExecOrder 列表（原地改）；get_broker()：要撤交易所的单时才取券商
    （没有要撤的 / 只撤执行器还没发出的单就不连券商）；cids=None → 今天全部还挂着的执行器单（只撤交易所里的：停并撤单的口径；买单在前，
    不设闸门 —— 紧急「全撤」，立花现物的买单只按发出那一刻的余力下，不会透支）。
    撤了凑钱的卖单（D2；2026-10-15）：deps（{cid: "cancel" | "keep"} 或一个值）="cancel" → 靠它的钱的买单一起撤
    （2026-10-16 起与整组撤单同一个引擎：先撤买单，买单已经成交 / 撤不掉 → 卖单不撤；立花买单的撤单还没确认 → 一样等）；其余（"keep" / 没写）→
    fund_cascade 按现在能用的钱重算（照常 / 减股 / 不下 + ★ 交易 提醒）。盘中为手动买入凑钱的核心卖单（fund_wait）被撤 → 那条买入默认也撤回
    （M16；deps="keep" 时留着、按现金重新算）。
    整组撤单（2026-10-16 用户：一起下的买单和卖单一起撤）：groups = {主单 cid: 你确认过的同一组其他单 | None（命令行 --group = 现在能撤的全部）}，
    waits = {主单 cid: {"wait": [撤单还没确认的买单], "since": 开始等的时刻, "all": [成员], "legacy": 以前的「一起撤买单」}}（还在等的指令）。
    成员在这次运行开头算一次（本地撤单会清空 fund_src）。先撤买单（交易所里的在前），没有任何买单还可能花钱（_spends）才撤卖单；立花买单的撤单
    还没确认 → 卖单先不撤（wait：约 1 分钟后再查，最多 10 分钟、收盘前 3 分钟为止 → gaveup）。
    复核（2026-10-16）：单笔撤一笔在一组里的卖单（deps 不是 keep）、同一组的买单还可能花钱（solo_holds）→ 不撤（面板「只撤这笔卖单」/ 命令行
    --solo 写 deps=keep 才撤）。同一组同时只有一个撤单（简化 2026-10-16）：别的撤单在 cancel_book / check 就先拒绝（cancel_conflict），
    这里不再合并 / 交接；只有命令行 cancel <B> <S> --group 点了同一组的几笔 → 跑一次（一行汇总，点名的都在范围里）。
    cash：重算用的钱（数或函数；没给 → 模拟账户 = 模拟券商的现金 − 排队的寄付买单，立花 = 券商余力 − 出金预留 reserve，没连券商 → cash_hi）。
    返回 {"done", "pending", "failed", "skipped": [{cid, ticker, side, qty, why, kind, hint}], "events": [(级别, 文字)],
    "by_cid": {cid: (结果, 说明)}, "fund": [cascade_rows], "grp": {主单: {state, n, members, wait, since, kept, line, legacy}},
    "held": [闸门留下的卖单]}。"""
    from .manual_orders import GROUP_WAIT_MAX_S
    res = {"done": [], "pending": [], "failed": [], "skipped": [], "events": [], "by_cid": {}, "fund": [], "grp": {}, "held": []}
    by = {o.cid: o for o in orders}
    gsel = dict(groups or {})
    gw = dict(waits or {})
    mode = deps if isinstance(deps, dict) else {}

    def m_of(c):
        return mode.get(c) if isinstance(deps, dict) else deps

    def skip_rec(c, o, why):
        rec = {"cid": c, "ticker": _g(o, "ticker") if o else "", "side": _g(o, "side") if o else "",
               "qty": int(_g(o, "sent_qty") or _g(o, "qty") or 0) if o else 0, "why": why,
               "kind": (_g(o, "kind") or "stock") if o else ""}
        res["skipped"].append(rec)
        res["by_cid"][c] = ("skipped", why)
    targets, jobs = [], []
    named: dict = {}                                       # 命令行 cancel <B> <S> --group：并进同一组那一项的点名的单
    G0 = _group_map(orders, book) if cids is not None else {}   # 成员只在运行开头算一次（本地撤单会清空 fund_src）
    if cids is None:
        targets = [o for o in orders if o.status in CANCELLABLE and cancel_why(o, book, now, paper) is None]
        if not targets:
            res["note"] = "今天没有还挂着的执行器单（不用撤）"
    else:
        for c in dict.fromkeys(str(x) for x in cids):
            o = by.get(c)
            if c in gsel and gsel[c] is None and c not in G0 and c not in gw:   # 命令行 --group、这笔不在一组里：就是撤这一笔（与不带 --group
                gsel.pop(c)                                #   一样写，不说「整组撤单」；复核 6 2026-10-16）
            if c in gsel or c in gw:                       # 整组撤单：主单本身不先查（复查时主单可能已经撤了），只要在账本里
                if o is None:
                    skip_rec(c, None, "账本里没有这笔单（已经对账过了 / cid 写错？）")
                    continue
                lg = bool((gw.get(c) or {}).get("legacy"))
                hit = None if lg else next((b for b, l_ in jobs if not l_ and c in (G0.get(b) or [b])), None)
                if hit is None:
                    jobs.append((c, lg))
                    continue
                ca, cb = gsel.get(c, []), gsel.get(hit, [])   # 同一组点了几笔（命令行）：跑一次，范围合起来
                gsel[hit] = None if (ca is None or cb is None) else list(dict.fromkeys(list(cb) + [c] + list(ca)))
                named.setdefault(hit, []).append(c)
                continue
            why = "账本里没有这笔单（已经对账过了 / cid 写错？）" if o is None else cancel_why(o, book, now, paper)
            if why:
                skip_rec(c, o, why)
                continue
            if o.side == "SELL" and m_of(c) == "cancel":    # 以前的「一起撤买单」：同一个引擎（先撤买单、闸门），保留以前的写法
                jobs.append((c, True))
                continue
            targets.append(o)
    targets.sort(key=lambda o: 0 if o.side == "BUY" else 1)   # 买单在前（稳定排序）
    fill = fill_day_of(book)
    hints = {o.cid: cancel_hint(o, book, now, tag) for o in targets}       # 撤之前算（状态还没改）
    holder: dict = {}

    def broker():
        if "b" not in holder:
            holder["b"] = get_broker()
        return holder["b"]
    if any(o.status in CANCELLABLE for o in targets):
        broker()
    word = {"done": "撤掉了 —— ", "pending": "撤单已受理 —— "}

    def record(kind, x, why, hint=None, ev=None, lvl=None):
        n_ = int(_g(x, "sent_qty") or _g(x, "qty") or 0)
        rec = {"cid": x.cid, "ticker": x.ticker, "side": x.side, "qty": n_, "why": why, "kind": x.kind or "stock"}
        if hint is not None:
            rec["hint"] = hint
        if kind in ("done", "pending"):
            w = _withdraw_manual(book, x, now)
            if w:
                rec["why"] = f"{why}；{w}"
        res[kind].append(rec)
        res["by_cid"][x.cid] = (kind, rec["why"])
        gx = kind == "skipped" and GONE in str(x.note or "")   # 立花那边已经失效 / 被拒：不用撤（不是没撤成）；失效前成交过 → 照样 warn
        gone_ = gx and not _fq(x)[0]
        if ev is None:
            ev = f"撤单 {_ord_txt(x)}（{x.cid}）：" + ("不用撤 —— " if gx else word.get(kind, "没撤 —— ")) + rec["why"]
        res["events"].append((lvl or ("info" if kind in ("done", "pending") or gone_ else "warn"), ev))
        return rec

    def m16(o, m):
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
    pend: set = set()                                      # 这次运行里撤单还没确认的买单（单笔撤的也算：整组撤单的闸门等它）
    seen: set = set()

    def single(o):
        if o.cid in res["by_cid"] or o.status == "CANCELLED":
            return
        if cids is not None and o.side == "SELL" and m_of(o.cid) != "keep" and o.cid in G0:
            hold = _solo_holds(o, orders, book, now, G0)   # 单笔撤一组里的卖单、同一组的买单还可能花钱：不撤（复核 2026-10-16）
            if hold:
                why = _hold_why(o, hold, orders, book, now, paper, tag)
                skip_rec(o.cid, o, why)
                res["held"].append(o.cid)
                res["events"].append(("warn", f"{TRADE_HEAD}：{_ord_txt(o)}（{o.cid}）没撤 —— {why}"))
                return
        kind, why = _cancel_one(o, holder.get("b"), paper, now, source, polls)
        record(kind, o, why, hints[o.cid])
        if kind == "pending" and o.side == "BUY":
            pend.add(o.cid)
        if kind in ("done", "pending") and o.side == "SELL":
            m16(o, m_of(o.cid))
    for o in targets:                                      # 顺序（复核 2 2026-10-16）：单笔的买单 → 整组撤单（先买后卖）→ 单笔的卖单
        if o.side == "BUY":                                # （单笔撤卖单的闸门看得到同一次运行里买单撤没撤掉）
            single(o)
    for a, legacy in jobs:
        _group_job(a, legacy, orders, by, book, G0, gsel, gw, res, record, m16, broker, holder, pend, seen,
                   paper=paper, now=now, source=source, polls=polls, tag=tag, fill=fill, wait_max=GROUP_WAIT_MAX_S,
                   named=named.get(a) or [])
    for o in targets:
        if o.side != "BUY":
            single(o)
    _grp_finish(res, by, now, fill)
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


def _legacy_mem(a, orders, by, book, gw) -> list:
    """以前的「一起撤买单」的成员：卖单 + fund_src 里有它的买单 + 还在等的指令记下的成员（复查时第一次本地撤掉的买单 fund_src 已经清空）。"""
    mem = [by[a]] + [y for y in orders if y.side == "BUY" and _in_current(y, book) and a in [str(c) for c in (y.fund_src or [])]]
    for c in (gw.get(a) or {}).get("all") or []:
        x = by.get(str(c))
        if x is not None and x not in mem:
            mem.append(x)
    return mem


def _blk_pre(reasons, legacy: bool, gm, scope) -> str:
    """留下卖单的说明里挡它的买单前面写什么（复核 4 2026-10-16；与确认框 group_lines 的 ★ 一致）：都是同一组的成员 →「同一组的」；
    以前的「一起撤买单」里都是靠这笔卖出的钱的 →「靠它的钱的」；混着 → 不加（以前一律写「同一组的」，不在一组里的也这么写）。"""
    cs = [c for c, _k, _t in reasons]
    gm = set(gm or [])
    if not cs or all(c in gm for c in cs):
        return "同一组的"
    if all((c in scope) if legacy else (c not in gm) for c in cs):   # 整组撤单里靠这一组卖单的钱的买单（fund_linked；复核 6）也写「靠它的钱的」
        return "靠它的钱的"
    return ""


def _group_job(a, legacy, orders, by, book, G0, gsel, gw, res, record, m16, broker, holder, pend, seen, *, paper, now, source,
               polls, tag, fill, wait_max, named=()) -> None:
    """整组撤单的一组（cancel_core 用）：A 先撤买单 → B 闸门（_spends）→ C 没有买单还可能花钱才撤卖单 → D 不然卖单一笔都不撤。
    legacy：以前的「一起撤买单」（卖单 + 靠它的钱的买单；说明照旧写；同一组里不靠 fund_src 的买单也进闸门；立花买单的撤单还没确认 → 一样等）。
    复核 4（2026-10-16）：legacy 里同一组、不靠它的钱的买单（extra）撤单已受理（之前单笔撤的、还在取消中）→ 也等（只查状态、
    不发新的撤单；记进这一组的 members / wait，复查时照样只查），立花确认撤掉了（没成交）才撤卖单（与确认框 legacy_plan 的 ask 一致）；
    范围里你要撤的买单已经成交 → 写一行「已经成交、撤不了」、汇总不说「都撤了」；legacy 里靠它的钱、已经成交的买单不再推「已经发到交易所，
    没一起撤」（卖单那条 ★ 已经写了理由）；留下卖单的说明只在挡它的买单都在同一组时写「同一组的」（不然「靠它的钱的」/ 不加）。
    简化（2026-10-16）：立花那边已经失效 / 被拒（GONE）的单买卖一样：没成交 → 不用撤（不算没撤成、不推 ★）；失效前成交过 → 按已经成交写。
    named：命令行 cancel <B> <S> --group 并进这一项的点名的单（也在范围里：撤不了的写一行、不说「都撤了」）。"""
    from .manual_orders import GROUP_LAST_S
    o0 = by[a]
    w0 = gw.get(a) or {}
    extra = []
    if legacy:
        mem0 = _legacy_mem(a, orders, by, book, gw)
        dep = {x.cid for x in deps_of(o0, orders)}

        def own(y) -> bool:                                # 卖单本身 / 靠它的钱的买单（本地撤掉的 fund_src 已经清空：已撤的也算）
            return y.side == "SELL" or y.status == "CANCELLED" or a in [str(c) for c in (y.fund_src or [])]
        mem = [y for y in mem0 if own(y)]
        scope = {x.cid for x in mem}
        xs = (list(G0.get(a) or []) + [y.cid for y in mem0 if not own(y)]   # 同一组、不靠它的钱的买单（+ 上次在等的）
              + [str(c) for c in w0.get("wait") or []])
        extra = [by[c] for c in dict.fromkeys(xs) if c in by and by[c].side == "BUY" and c not in scope]
    else:
        cs = list(G0.get(a) or [a])
        if len(cs) > 1:                                    # 靠这一组卖单的钱、已经发出的买单也在这一组里（fund_linked；复核 6 2026-10-16）
            cs += [x.cid for x in fund_linked([by[c] for c in cs if c in by], orders, book) if x.cid not in cs]
        conf = gsel.get(a, [])
        nm = [str(c) for c in named or () if str(c) in by]
        for c in list(w0.get("all") or []) + (list(conf) if conf else []) + nm:   # 还在等的成员 + 你确认过的（还在账本里的）
            if str(c) in by and str(c) not in cs:
                cs.append(str(c))
        mem = sorted([by[c] for c in cs if c in by], key=_grp_key)
        dep = set()
        if conf is None:                                   # 命令行 --group：现在能撤的全部 + 你点名的（已成交 / 撤不了的写一行、不说「都撤了」）
            scope = {x.cid for x in mem if grp_why(x, book, now, paper) is None} | {a} | set(nm)
        else:
            scope = ({str(c) for c in conf} | {a}) & {x.cid for x in mem}
    wait_in = {str(c) for c in w0.get("wait") or []}
    since = _tsj(w0.get("since")) or now
    gp = max(int(polls), GROUP_POLLS)
    miss: list[tuple[str, str]] = []                      # 没撤的 → [(cid, 说明)]（汇总行用）
    gone: list[str] = []                                   # 撤的时候立花那边已经失效 / 被拒、没成交的买单（不用撤、不花钱；复核 5）
    bad = False                                            # 有单被拒（grp_why）/ 撤单失败（「一笔都没撤成」要有这个）
    sl = _lab(o0.ticker)
    for x in sorted([y for y in mem if y.side == "BUY"], key=lambda y: 0 if y.status in AT_EXCH else 1):   # A. 买单
        if x.cid in res["by_cid"] or x.cid in seen or x.status == "CANCELLED":
            continue
        if legacy and x.cid in dep:                        # 以前的写法：还没发出的买单在本地撤
            h = cancel_hint(x, book, now, tag)
            x.status, x.fund_src = "CANCELLED", []
            x.note = f"你撤了单（{now:%H:%M}{'，' + source if source else ''}）：和凑钱的卖单 {sl} 一起撤，执行器不再发"[:300]
            seen.add(x.cid)
            record("done", x, x.note, h, lvl="info")
            continue
        recheck = False
        if x.cid in wait_in and x.status in CANCELLABLE and grp_why(x, book, now, paper) is None:   # 复查：撤单已经受理过
            h = cancel_hint(x, book, now, tag)
            kx, wx = _cancel_one(x, broker(), paper, now, source, gp, resend=False)
            recheck = True
        elif x.cid in scope and grp_why(x, book, now, paper) is None:
            h = cancel_hint(x, book, now, tag)             # 复核 2（2026-10-16）：照样发撤单（之前撤过的：立花回「取消中」→ 撤单已受理；
            kx, wx = _cancel_one(x, broker() if x.status in CANCELLABLE else holder.get("b"), paper, now, source, gp,   # 之前的撤单没成功 → 这次再撤）
                                 blocked=True)
        else:
            qx, _nx, fullx = _fq(x)
            gx = x.status in CANCELLABLE and GONE in str(x.note or "")   # 之前撤的时候立花那边已经失效 / 被拒（单不在交易所了）
            done_x = fullx or (qx > 0 and (x.status not in GROUP_OPEN or gx))   # 已经成交（全部 / 失效前成交了一部分）
            if gx and not qx:                              # 没成交：不花钱、不用撤（范围里的写进汇总）
                if x.cid in scope or x.cid in wait_in:
                    seen.add(x.cid)
                    gone.append(x.cid)
            elif legacy and done_x:                          # 靠它的钱、已经成交：撤不了，下面的闸门留下卖单、卖单那条 ★ 写理由
                seen.add(x.cid)                            # （复核 4 2026-10-16：不再另推「已经发到交易所，没一起撤」）
                record("skipped", x, f"已经成交 {qx:,} {_unit(x)}，撤不了（不用撤）", lvl="info")
            elif legacy and x.status in CANCELLABLE:       # 已经发到交易所、现在撤不了（以前的写法）
                why_x = grp_why(x, book, now, paper) or "撤不了"
                what = f"{_ord_txt(x)}（{x.cid}）"
                seen.add(x.cid)
                rec = {"cid": x.cid, "ticker": x.ticker, "side": x.side, "qty": int(x.sent_qty or x.qty), "kind": x.kind or "stock",
                       "why": f"已经发到交易所，没一起撤：{why_x}"}
                res["skipped"].append(rec)
                res["by_cid"][x.cid] = ("skipped", why_x)
                res["events"].append(("warn", f"{TRADE_HEAD}：{what}：已经发到交易所，没一起撤 —— {why_x}"))
            elif not legacy and x.cid in scope and done_x:   # 你要撤的买单已经成交（命令行 cancel <已成交的买单> --group / 确认之后成交的）：
                seen.add(x.cid)                            # 写一行、汇总不说「都撤了」（复核 4 2026-10-16）
                record("skipped", x, f"已经成交 {qx:,} {_unit(x)}，撤不了（不用撤；明天早上照常对账）")
                miss.append((x.cid, f"买 {_lab(x.ticker)} 已经成交 {qx:,} {_unit(x)}，撤不了"))
            elif not legacy and (x.cid in scope or x.cid in wait_in) and x.status in GROUP_OPEN and not int(x.filled_qty or 0):
                why_x = grp_why(x, book, now, paper)       # 范围里的买单现在撤不了（不是今天的单 / 已经收盘…）：写出来
                if why_x:
                    seen.add(x.cid)
                    record("skipped", x, why_x)
                    miss.append((x.cid, f"买 {_lab(x.ticker)} 撤不了：{why_x}"))
                    bad = True
            continue
        seen.add(x.cid)
        if kx == "failed":
            bad = True
        dead = kx == "skipped" and GONE in str(x.note or "") and not _fq(x)[0]   # 立花那边已经失效 / 被拒、没成交：不花钱、不用撤（复核 5）
        if dead:
            gone.append(x.cid)
        elif kx == "skipped" and not legacy:               # 撤的时候已经全部成交 / dry-run / 失效前成交过：汇总写出来（复核 4）
            miss.append((x.cid, f"买 {_lab(x.ticker)} 没撤：{wx}"))
        if kx == "pending":
            pend.add(x.cid)
            if recheck:                                    # 复查还在等：只记在这一组的 wait 里（不推送）
                continue
        ev = None
        if legacy:
            ev = (f"撤单 {_ord_txt(x)}（{x.cid}）（和凑钱的卖单 {sl} 一起撤）："
                  + {"done": "撤掉了 —— ", "pending": "撤单已受理 —— "}.get(kx, "不用撤 —— " if dead else "★ 没撤 —— ") + wx)
        record(kx, x, wx, h, ev=ev, lvl="info" if dead else None)
    for x in extra:                                        # legacy：同一组、不靠它的钱、撤单已受理（取消中）的买单 → 只查状态（不发新的撤单；
        if (paper or x.cid in res["by_cid"] or x.cid in seen or x.cid in pend or x.status not in CANCELLABLE   # 这次运行刚撤过的不再查）
                or ACCEPTED not in str(x.note or "") or grp_why(x, book, now, paper) is not None):
            continue
        h = cancel_hint(x, book, now, tag)
        kx, wx = _cancel_one(x, broker(), paper, now, source, gp, resend=False)
        seen.add(x.cid)
        if kx == "pending":
            pend.add(x.cid)
            continue
        bad = bad or kx == "failed"
        record(kx, x, wx, h)
    reasons = []                                           # B. 闸门：这一组里还可能花钱的买单 → [(cid, 代码, 理由)]
    wl: list[str] = []                                     # 撤单立花还没确认的买单（等的时候复查它们）
    for x in mem:
        if x.side == "BUY":
            r = _spends(x, scope, pend, now, fill)
            if r:
                reasons.append((x.cid,) + r)
                if r[0] == "pending":
                    wl.append(x.cid)
    for x in extra:                                        # 以前的「一起撤买单」：同一组里不靠 fund_src 的买单（没一起撤）还可能花钱 → 也挡；
        r = _xtra_spends(x, book, now, paper, fill)        # 撤单立花还没确认 → 等（复核 4：以前当成还挂着、马上留下卖单）
        if r:
            reasons.append((x.cid,) + r)
            if r[0] == "pending":
                wl.append(x.cid)
    sells = sorted([y for y in mem if y.side == "SELL" and y.cid in scope], key=lambda y: 0 if y.status in AT_EXCH else 1)

    def gone_s(y) -> None:                                 # 卖单在立花那边已经失效 / 被拒：没成交 → 不用撤；失效前成交过 → 按已经成交写
        q_ = _fq(y)[0]
        if q_:
            miss.append((y.cid, f"卖 {_lab(y.ticker)} 已经成交 {q_:,} {_unit(y)}（其余立花那边已经{gone_word(y)}）"))
        else:
            gone.append(y.cid)
    for y in sells:                                        # 之前撤的时候已经知道的（简化 2026-10-16：以前当成「撤不了」、推 ★）
        if (y.cid not in res["by_cid"] and y.cid not in seen and y.status in CANCELLABLE and GONE in str(y.note or "")):
            seen.add(y.cid)
            record("skipped", y, f"立花那边已经{gone_word(y)}（撤单时查到），不用撤")
            gone_s(y)
    open_s = [y for y in sells if y.status in GROUP_OPEN and y.cid not in res["by_cid"] and y.cid not in seen]
    state = None
    late = False
    kept: list[str] = []
    spend_s: set = set()                                   # 撤单已受理、立花还在处理的卖单（不是「没撤」；复核 2026-10-16）
    rtxt = "；".join(t for _c, _k, t in reasons)
    rcodes = {k for _c, k, _t in reasons}
    gated = bool(reasons) and bool(open_s)                 # 闸门只护这次范围里还开着的卖单（复核 3 2026-10-16：范围里没有卖单时，同一组别的买单
    if not gated:                                          # 已经成交不再让「都撤了」变成「只撤了一部分」、也不为没有卖单的范围等 10 分钟）
        # C. 没有买单还可能花钱（或这次范围里没有开着的卖单）：撤卖单
        for y in sells:
            if y.cid in res["by_cid"] or y.cid in seen or y.status == "CANCELLED":
                continue
            if y.status not in GROUP_OPEN:
                q = int(y.filled_qty or 0)
                if y.status == "FILLED":
                    q = max(q, int(y.sent_qty or y.qty or 0))
                if q > 0:
                    miss.append((y.cid, f"卖 {_lab(y.ticker)} 已经成交 {q:,} {_unit(y)}"))
                continue
            seen.add(y.cid)
            why = grp_why(y, book, now, paper)
            if why:
                record("skipped", y, why)
                miss.append((y.cid, f"卖 {_lab(y.ticker)} 撤不了：{why}"))
                bad = True
                continue
            h = cancel_hint(y, book, now, tag)
            ky, wy = _cancel_one(y, broker() if y.status in CANCELLABLE else holder.get("b"), paper, now, source, polls, blocked=True)
            record(ky, y, wy, h)
            if ky in ("done", "pending"):
                m16(y, "cancel")
                if ky == "pending":
                    spend_s.add(y.cid)
            elif ky == "skipped" and GONE in str(y.note or ""):   # 立花那边已经失效 / 被拒（复核 6：以前算「没撤」、推 ★ 只撤了一部分）
                gone_s(y)
            else:
                miss.append((y.cid, f"卖 {_lab(y.ticker)} 没撤：{wy}"))
                bad = bad or ky == "failed"
    else:                                                  # D. 有买单还可能花钱：卖单一笔都不撤
        if rcodes == {"pending"}:                           # 立花还没确认买单的撤单：等（最多 10 分钟；收盘前 3 分钟起不再等 —— 15:30 之后没人收尾）
            last = _at(now.date(), CLOSE_T) - dt.timedelta(seconds=GROUP_LAST_S)
            if since + dt.timedelta(seconds=wait_max) <= now:
                state = "gaveup"
            elif now >= last:
                state, late = "gaveup", True
            else:
                state = "wait"
        pre = _blk_pre(reasons, legacy, G0.get(a), scope)   # 「同一组的」只在挡它的都是同一组的买单时写（复核 4）
        held = pre + rtxt + "：卖单不撤（撤了买的钱不够）"
        gu = ""                                            # 不等了：卖单那条 ★ 也写去立花网站看（legacy 的汇总行不进推送事件；复核 4）
        if state == "gaveup":
            held = pre + rtxt + "：" + ("快收盘了（15:30）不再等" if late else "等了 " + str(wait_max // 60) + " 分钟") + " → 卖单没撤"
            gu = "。请在" + SITE + "看买单撤掉没有；撤掉了再点卖单的「撤单」"
        elif legacy and not paper and rcodes & {"live", "unknown"}:
            held += "；还挂着 / 状态不明的买单在" + SITE + "核对、撤"
        for y in open_s:
            kept.append(y.cid)
            if state == "wait":
                continue
            seen.add(y.cid)
            n_ = int(y.sent_qty or y.qty)
            res["skipped"].append({"cid": y.cid, "ticker": y.ticker, "side": y.side, "qty": n_, "why": held, "kind": y.kind or "stock"})
            res["by_cid"][y.cid] = ("skipped", held)
            res["held"].append(y.cid)
            if legacy:
                res["events"].append(("warn", f"{TRADE_HEAD}：{_ord_txt(y)}（{y.cid}）没撤 —— {held}{gu}"))
    site = SITE
    xw = [c for c in wl if c in {x.cid for x in extra}]   # 等的是同一组、不靠它的钱的买单（legacy；复核 4）→ 写明是哪几笔
    tail_wait = (("买单已发撤单、立花还没确认" if not xw else
                  "、".join("买 " + _lab(by[c].ticker) for c in wl) + " 的撤单立花还没确认")
                 + " → 卖单先不撤，约 1 分钟后再查（" + f"{since:%H:%M}" + " 起，最多等 " + str(wait_max // 60) + " 分钟）")
    tail_gu = (("买单的撤单立花还没确认、快收盘了（15:30）不再等" if late else "买单的撤单立花 " + str(wait_max // 60) + " 分钟还没确认")
               + " → 卖单没撤。请在" + site + "看买单撤掉没有；撤掉了再点卖单的「撤单」"
               + ("（15:30 收盘后今天没成交的单都失效）" if late else ""))
    members = [x.cid for x in mem]                         # 这条指令要撤的单（legacy：卖单 + 靠它的钱的买单）
    wl = wl if state == "wait" else []                     # legacy 等的同一组、不靠它的钱的买单也在里面（复查时只查、不发撤单）
    if legacy:                                             # 以前的「一起撤买单」：只在等 / 不等了时记一组（cancel_book 要它保持 pending / 结束）
        if state in ("wait", "gaveup"):
            head = "卖 " + sl + " 和靠它的钱的买单一起撤"
            res["grp"][a] = {"state": state, "n": len(mem), "members": members, "wait": wl,
                             "since": since.isoformat(timespec="seconds"),
                             "kept": kept, "line": head + "：" + tail_wait if state == "wait" else "★ " + head + "：" + tail_gu,
                             "legacy": True}
        return
    ncan = sum(1 for x in mem if x.cid in scope and (x.status == "CANCELLED" or x.cid in pend or x.cid in spend_s))
    left = [x for x in mem if x.cid in scope and x.status in GROUP_OPEN and x.cid not in pend and x.cid not in spend_s
            and GONE not in str(x.note or "")]
    fcid = {c for c, k, _t in reasons if k == "filled"} if gated else set()   # 已经成交的买单：闸门那一句已经写了，不重复（复核 4）
    gtxt = "；".join(_side(by[c]) + " " + _lab(by[c].ticker) + " 立花那边已经" + gone_word(by[c]) + "（没成交），不用撤"
                    for c in dict.fromkeys(gone))         # 不花钱、不用撤：不算没撤成（买卖一样；简化 2026-10-16）
    why_all = "；".join([t for c, t in miss if c not in fcid] + ([rtxt + "：卖单不撤（撤了买的钱不够）"] if gated else [])
                       + ([gtxt] if gtxt else []))
    pend_b = {x.cid for x in mem if x.cid in scope and x.side == "BUY" and x.cid in pend}   # 范围里没有卖单时：买单的撤单已受理、还没确认
    if state is None:
        if not miss and not left:                          # 只按这次范围里的单判（复核 3：范围外已成交的买单不算）
            state = "all"
        elif ncan == 0:                                    # 一笔都没撤（也没发撤单）：不说「只撤了一部分」（复核 2 2026-10-16）
            state = "none"
        else:
            state = "part"
    n = len(mem)
    k = sum(1 for x in mem if x.cid in scope)              # 这次整组撤单的笔数（= 确认框「整组撤单（N 笔）」；同一组还有别的 → 写明几笔里的几笔）
    head = "整组撤单（" + (f"{n} 笔" if k >= n else f"同一组 {n} 笔里的 {k} 笔") + "：" + _side(o0) + " " + sl + " 这一组）"
    acc = [w for w, ids in (("买单", pend_b), ("卖单", spend_s)) if ids]
    tail_site = (("（还挂着 / 状态不明的单在" + site + "核对、撤）")
                 if not paper and (bad or (gated and rcodes & {"live", "unknown"})) else "")
    if state == "all" and gone and not ncan:               # 范围里的单都已经在立花那边失效 / 被拒：没有要撤的
        line = head + "：不用撤 —— " + gtxt
    elif state == "all":
        line = head + (("：都发了撤单（" + "和".join(acc) + "的撤单已受理、立花还在处理：过一会儿在面板 / 立花网站看是否撤掉）") if acc
                       else "：都撤了") + (f"（{gtxt}）" if gtxt else "")
    elif state == "wait":
        line = head + "：" + tail_wait
    elif state == "gaveup":
        line = "★ " + head + "：" + tail_gu
    elif state == "part":
        line = "★ " + head + "：只撤了一部分 —— " + (why_all or "有单没撤") + tail_site
    else:
        line = "★ " + head + "：一笔都没撤成 —— " + (why_all or "有单没撤") + tail_site
    res["grp"][a] = {"state": state, "n": n, "members": members, "wait": wl, "since": since.isoformat(timespec="seconds"),
                     "kept": kept, "line": line, "legacy": False, "scope": sorted(scope & set(members))}   # ★ 交易 推送：_grp_finish


def cancel_text(res: dict) -> list[str]:
    """撤单结果的几行（命令行 / 通知）：「撤掉了：卖 1545 纳斯达克 100 4,110 口（U…）—— …」（代码 + 名字、口 / 股；2026-10-15）。"""
    out = [g.get("line") for g in (res.get("grp") or {}).values() if g.get("line")]   # 整组撤单的汇总行在最前面（2026-10-16）
    out += list(res.get("refused") or [])                 # 同一组已经有撤单在处理：没做的那几条（简化 2026-10-16）
    for k, head in (("done", "撤掉了"), ("pending", "撤单已受理（立花还在处理）"), ("failed", "★ 没撤成"), ("skipped", "没撤")):
        for r in res.get(k) or []:
            q = int(r.get("qty") or 0)
            what = " ".join(x for x in ({"BUY": "买", "SELL": "卖"}.get(r.get("side"), ""), _lab(r.get("ticker")),
                                        f"{q:,} {'口' if r.get('kind') == 'core' else '股'}" if q else "") if x)
            h = "不用撤" if k == "skipped" and str(r.get("why") or "").startswith("立花那边已经") else head   # 立花那边已经失效 / 被拒
            out.append(f"{h}：{what}（{r['cid']}）—— {r['why']}")
    for r in res.get("fund") or []:                       # 靠撤掉的卖单的钱的买单：重算的结果（D2；2026-10-15）
        u = "口" if r.get("kind") == "core" else "股"
        qty_txt = f"{int(r.get('was') or 0):,} {u}"          # 先算好数量文字（Python 3.10 / 3.11 不允许 f-string 里嵌套同种引号）
        out.append(("★ " if r.get("act") != "keep" else "") + f"买 {_labq(r.get('ticker'), qty_txt)}：{r.get('note')}")
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


GRP_KEYS = ("grp_wait", "grp_wait0", "recheck_at", "grp_legacy")   # 撤单指令结束时去掉的「等」字段


def cancel_book(path, get_broker, cids=None, *, paper: bool, tag: str | None = None, requests: bool = False,
                clock=None, source: str = "", polls: int = POLLS, groups=None, deps=None) -> dict:
    """不建引擎的撤单（run.py live-u --cancel / --phase cancel）：读账本 → 撤 → 存账本（存之前先备份）。
    requests=True（--phase cancel，面板叫）：读手动指令文件里的「撤单」指令（kind cancel_order），撤完把结果记进那条指令。
    整组撤单（grp；2026-10-16）：买单的撤单立花还没确认 → 指令保持 pending、记 grp_wait / recheck_at（约 1 分钟后再查，最多 10 分钟、
    收盘前 3 分钟为止）；以前的「一起撤买单」（deps=cancel）也一样等（grp_legacy）。已经过了那天收盘还在等的 → 不吵地结束（今天没成交的单
    都已失效；复核 2026-10-16）。groups：命令行 --group（{cid: None}）；deps：命令行 --solo（"keep" = 只撤这笔卖单）。
    同一组同时只有一个撤单（简化 2026-10-16）：一条撤单盖着的单（cancel_scope）和还在处理的撤单（在等的 / 先写的 / 面板还没读的）重叠 →
    这条不做（指令记 rejected + 理由；命令行那一笔记「没撤」），等那一条结束再撤。
    返回 cancel_core 的结果 + "items"（处理了的撤单指令 [(id, 状态, 说明)]）+ "refused"（没做的撤单指令的说明）。"""
    from . import manual_orders as MO
    from .book_backup import backup
    from .live_unified import ExecOrder, _np
    clock = clock or now_jst
    now = clock()
    book = read_json(path, {}) or {}
    msgs: list[tuple[str, str]] = []
    items: list[dict] = []
    stale: list[dict] = []
    waits: dict = {}
    refused: list[tuple[dict, str]] = []                   # 同一组已经有撤单在处理：这条先不做（同一组同时只有一个撤单；简化 2026-10-16）
    cli_skip: list[dict] = []
    if requests and tag:
        man = MO.Manual(book, tag, clock)
        msgs = man.ingest(only=("cancel_order",))
        allp = man.pending(("cancel_order",))
        stale = [it for it in allp if MO.grp_wait_stale(it, now)]   # 等到收盘之后：不再等
        live = [it for it in allp if it not in stale]
        due = [it for it in live if MO._recheck_due(it, now)]
        o0 = [x for x in book.get("orders") or [] if isinstance(x, dict)]
        G = _group_map(o0, book)
        run = [_job(it, o0, book, G) for it in live if it not in due]   # 还没到复查时刻的：原封不动、照样盖着
        for it in sorted(due, key=lambda x: (0 if x.get("grp_wait") else 1, str(x.get("at") or ""))):   # 在等的先（它先写的）
            why = cancel_conflict(it, book, run, G)
            if why:
                refused.append((it, why))
                continue
            items.append(it)
            run.append(_job(it, o0, book, G))
            if not it.get("grp_wait"):
                run[-1]["state"] = "执行器正在撤"
        cids = [str(it.get("cid") or "") for it in items]
        groups = {str(it.get("cid") or ""): list(it.get("grp") or []) for it in items if it.get("grp")}
        waits = {str(it.get("cid") or ""): {"wait": list(it.get("grp_wait") or []), "since": it.get("grp_wait0"),
                                            "all": list(it.get("grp_all") or []), "legacy": bool(it.get("grp_legacy"))}
                 for it in items if it.get("grp_wait")}
    elif tag and cids:                                     # 命令行：面板写的撤单还在处理 / 还没读、盖着这一笔 → 这一笔先不撤
        try:
            jobs = cancel_jobs(book, MO.unseen(tag, book), now)
        except Exception:                                  # noqa: BLE001  读不了指令文件：照旧撤（引擎的闸门还在）
            jobs = []
        if groups:                                         # 命令行 --group 再跑同一条命令：还在等立花确认买单撤单的那一条（账本里 pending）接着做 ——
            pend = {str(it.get("cid") or ""): it for it in ((book.get("manual") or {}).get("items") or {}).values()   # 只查状态、不再发撤单，
                    if isinstance(it, dict) and it.get("kind") == "cancel_order" and it.get("status") == "pending"   # 从开始等的时刻算 10 分钟
                    and it.get("grp_wait") and not MO.grp_wait_stale(it, now)}                                     # （复核 6 2026-10-16）
            items = list({id(it): it for it in (pend.get(str(c)) for c in cids) if it is not None}.values())
            if items:
                o0 = [x for x in book.get("orders") or [] if isinstance(x, dict)]
                cover: set = set()
                for it in items:
                    cover |= cancel_scope(it, o0, book)
                ids = {it.get("id") for it in items}
                jobs = [j for j in jobs if j.get("id") not in ids]
                cids = [c for c in cids if str(c) not in cover]   # 那一条盖着的单：是它的一部分（不另撤、不算冲突）
                groups = {c: v for c, v in groups.items() if c in cids}
        if jobs:
            by0 = {str(o.get("cid")): o for o in book.get("orders") or [] if isinstance(o, dict)}
            keep = []
            for c in dict.fromkeys(str(x) for x in cids):
                why = cancel_conflict({"cid": c}, book, jobs)
                if not why:
                    keep.append(c)
                    continue
                o = by0.get(c) or {}
                cli_skip.append({"cid": c, "ticker": o.get("ticker") or "", "side": o.get("side") or "",
                                 "qty": int(o.get("sent_qty") or o.get("qty") or 0), "why": why, "kind": o.get("kind") or "stock"})
            cids = keep
            groups = {c: v for c, v in (groups or {}).items() if c in keep}
        if items:
            cids = [str(it.get("cid") or "") for it in items] + list(cids)
            groups = {**{str(it.get("cid") or ""): list(it.get("grp") or []) for it in items if it.get("grp")}, **(groups or {})}
            waits = {str(it.get("cid") or ""): {"wait": list(it.get("grp_wait") or []), "since": it.get("grp_wait0"),
                                                "all": list(it.get("grp_all") or []), "legacy": bool(it.get("grp_legacy"))}
                     for it in items}
    orders = [ExecOrder.from_dict(o) for o in book.get("orders") or []]
    if (requests and not items) or (cli_skip and not cids):
        res = {"done": [], "pending": [], "failed": [], "skipped": [], "events": [], "by_cid": {}, "fund": [], "grp": {}, "held": [],
               "note": "" if cli_skip or refused else "没有要处理的撤单指令"}
    else:
        dps = {str(it.get("cid") or ""): it.get("deps") for it in items if it.get("deps")} if items else deps
        res = cancel_core(orders, book, get_broker, cids, paper=paper, now=now, source=source, polls=polls, deps=dps, tag=tag,
                          reserve=_reserve_of(book, paper), groups=groups or None, waits=waits or None)
    for r in cli_skip:
        res["skipped"].append(r)
        res["by_cid"][r["cid"]] = ("skipped", r["why"])
        res["events"].append(("info", f"撤单 {_ord_txt(r)}（{r['cid']}）：这次不撤 —— {r['why']}"))
    res["refused"] = []
    done_items = []
    stamp0 = now.isoformat(timespec="seconds")
    gr = res.get("grp") or {}
    for it, why in refused:                                # 同一组已经有撤单在处理：这条不做（不合并、不交接）
        for f in GRP_KEYS:
            it.pop(f, None)
        msg = f"{now:%m/%d %H:%M} 没做：{why}"
        it.update(status="rejected", done_on=now.date().isoformat(), msg=msg[:300])
        done_items.append((it["id"], "rejected", it["msg"]))
        res["refused"].append(f"撤单指令 {it.get('id')}（{_job_who(it)}）没做 —— {why}")
        res["events"].append(("info", res["refused"][-1]))
    for it in items:
        c = str(it.get("cid") or "")
        g = gr.get(c)
        if g is not None and not (it.get("grp") or it.get("grp_wait") or g.get("legacy")):
            g = None
        if g is not None and g["state"] == "wait":         # 立花还没确认买单的撤单：保持 pending，约 1 分钟后再查
            it.update(grp_wait=list(g["wait"]), grp_all=list(g["members"]), msg=g["line"][:300],
                      recheck_at=(now + dt.timedelta(seconds=MO.GROUP_RECHECK_S)).isoformat(timespec="seconds"))
            if g.get("legacy"):
                it["grp_legacy"] = True
            it.setdefault("grp_wait0", stamp0)
            done_items.append((it["id"], "pending", it["msg"]))
            continue
        if g is not None:
            for f in GRP_KEYS:
                it.pop(f, None)
            it.update(status="rejected" if g["state"] == "none" else "done", done_on=now.date().isoformat(), msg=g["line"][:300])
            done_items.append((it["id"], it["status"], it["msg"]))
            continue
        kind, why = res["by_cid"].get(c, ("skipped", "没处理"))
        for f in GRP_KEYS:
            it.pop(f, None)
        it.update(status="done" if kind in ("done", "pending") else "rejected", done_on=now.date().isoformat(), msg=why[:300])
        done_items.append((it["id"], it["status"], it["msg"]))
    mine = {str(it.get("cid") or "") for it in items}
    for c, g in gr.items():                                # 命令行 --group 在等立花确认买单的撤单：记成一条撤单指令（和面板的一样：面板约 1 分钟后
        if requests or c in mine or g.get("state") != "wait" or g.get("legacy"):   # 自动再查、再跑同一条命令也接着查；从开始等的时刻算
            continue                                       # 10 分钟，到了给立花网站的链接；复核 6 2026-10-16：以前每次重跑都从头算、永远不超时）
        o = next((x for x in orders if x.cid == c), None)
        its = book.setdefault("manual", {}).setdefault("items", {})
        rid, n = f"M{now:%Y%m%d-%H%M%S}-cancel_order-cli", 2
        while rid in its:
            rid, n = f"M{now:%Y%m%d-%H%M%S}-cancel_order-cli-{n}", n + 1
        its[rid] = {"kind": "cancel_order", "cid": c, "ticker": o.ticker if o else "", "deps": "cancel",
                    "grp": [x for x in g.get("scope") or [] if x != c], "at": stamp0, "id": rid, "status": "pending", "source": "命令行",
                    "grp_wait": list(g["wait"]), "grp_all": list(g["members"]), "grp_wait0": g.get("since") or stamp0, "msg": g["line"][:300],
                    "recheck_at": (now + dt.timedelta(seconds=MO.GROUP_RECHECK_S)).isoformat(timespec="seconds")}
        done_items.append((rid, "pending", g["line"][:300]))
    for it in stale:                                       # 过了收盘还在等：不吵地结束（不推送；今天没成交的单都已失效）
        t0 = _tsj(it.get("grp_wait0")) or _tsj(it.get("recheck_at"))
        since = f"{t0:%m/%d %H:%M} 起" if t0 else ""
        msg = (f"已收盘（15:30）：整组撤单停在等立花确认买单的撤单（{since}）→ 卖单没撤；今天没成交的单都已失效，买单撤没撤掉看明早的对账"
               "（立花网站的注文一覧也能看）").replace("（）", "")
        for f in GRP_KEYS:
            it.pop(f, None)
        it.update(status="done", done_on=now.date().isoformat(), msg=msg[:300])
        done_items.append((it["id"], "done", it["msg"]))
    if stale and not items:
        sid = {it.get("id") for it in stale}
        res["note"] = "；".join(m for i_, _s, m in done_items if i_ in sid)
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
           "GROUP_POLLS", "GROUP_NEUTRAL", "groups", "group_of", "fund_linked", "group_members", "lone_lines", "legacy_rec", "job_cids",
           "wait_end", "grp_why", "group_view", "group_lines", "ACCEPTED", "DEPK", "FAILED", "GONE", "gone_word", "still_sells", "legacy_plan", "cancel_scope", "cancel_jobs", "cancel_conflict",
           "solo_holds",
           "CORE_SRC", "src_of", "src_note", "src_line", "wrote", "fix_name", "OUT_WORD", "TRADE_HEAD", "NO_PATH_S", "skip_wont",
           "asked_cids", "instr_due", "outlook", "row_text", "act_text", "trade_key", "new_wont", "not_today",
           "fill_day_of", "how_text", "unknown_candidates", "unknown_text", "resolve_draft", "reconcile_report", "adopt", "save_book"]
