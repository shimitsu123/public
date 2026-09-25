"""live_unified.py — 一个账户方案（S0C2：日本个股 4×25% + 闲置资金 1655.T，立花 e支店）的实盘执行器。

和模拟盘用同一个推进器（qbreak/unified.py）：模拟盘按「开盘价 ± 滑点」撮合；执行器把**券商的实际成交**记进同一份状态。
收盘后的离场判断、统一决策（明天的单）都是同一段代码 —— 成交相同，实盘就与模拟盘 / 回测逐笔相同。

每个交易日（F = 成交日，D = 它的上一交易日）
  早上（F 的 06:30〜08:55，美股 D 收盘之后；例行任务 07:30）  run.py live-u --phase morning
    ① 对账：D 那天下的单 → 向券商查实际成交（数量 / 均价）→ 记进状态。顺序与引擎相同：个股卖 → 核心卖 → 个股买 → 核心买。
       卖单没成交（ストップ安張り付き等）→ 仍是「待卖」，今天再下；买单没成交 → 作废（信号只在次日开盘有效，与回测相同）
    ② 核对：券商持仓 = 状态持仓？不一致 → 今天不下单、报警。现金以券商的买付可能額为准（税、实际手续费、分红入账都在这里对齐）
    ③ 决策：D 收盘后的离场判断 + 统一决策（与模拟盘同一段代码）
    ④ 下单：卖单全部下 寄付成行。买单按「开盘前的买付余力」从前往后下 寄付指値（个股 = 信号日收盘 ×1.03，核心 = 收盘 ×1.02）。
       放不下的（要等开盘卖出的钱）连同排在它后面的买单一起留到开盘后，保持与模型相同的先后
  开盘后（F 的 09:05 前后）  run.py live-u --phase open
    ⑤ 留下的买单：用券商给的始値做同一条跳空过滤与名额检查，按当时的余力减到买得起，下当日限り指値（价格同上）

安全闸（任何一道不过 → 不下单，只记账、报警）：
  HALT 文件 / 行情没更新到应有的交易日 / 持仓与券商不一致 / 时间窗口不对 / 有状态不明的单；
  （立花）还有 ARM 未解锁、第二暗証番号缺失、单笔金额上限（默认 = 权益 ×1.05，核心 ETF 一笔可到权益的 100%）。
发单类请求绝不自动重发：发单前先在账本记「发送中」再发。发送途中崩溃、或网络错误（可能已被受理）的单，下次看到就停下，
等人工在立花的注文一覧确认后登记（run.py live-u --resolve），不猜。

与模型（回测 / 模拟盘）的已知差异 —— 都来自真实下单的约束，演练（run.py live-u-rehearse）逐项统计：
  • 买单是限价：价格按呼値向下取整，开盘恰好落在取整前后之间时不成交；核心 ETF 开盘高于收盘 +2% 时不成交（模型照买）
  • 留到开盘后的买单：按「限价 × 股数 + 手续费 ≤ 余力」减股（模型按实际开盘价减）；实盘在盘中成交，价格 ≠ 开盘价
  • 开盘前下的买单不知道同一开盘的卖单能不能成交：卖单遇到ストップ安没成交时，个股会暂时多于 4 只（模型会放弃这笔买入）
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass

from . import paths
from .brokers.base import state_tag
from .brokers.paper import PaperBroker
from .calendar_jp import next_trading_day, now_jst
from .tick import round_to_tick
from .unified import UnifiedEngine, UState, market_of
from .utils import atomic_write_text, read_json, setup_logging

log = setup_logging("live_unified")

ACCEPTED = ("SENT", "FILLED", "PARTIAL")          # 券商已受理（可能已成交）
UNKNOWN = ("SENDING", "ERROR")                     # 状态不明：可能已被受理 → 不重发，等人工确认
MORNING_CUTOFF = dt.time(8, 55)                    # 寄付注文的最后时刻（留 5 分钟余量）
OPEN_FROM, OPEN_UNTIL = dt.time(9, 0), dt.time(15, 25)


def _np(x):
    """json 默认转换：numpy 标量 → Python 数（np.int64 不是 int 的子类，不转会被写成字符串）。"""
    return x.item() if hasattr(x, "item") else str(x)


class ExecutorError(RuntimeError):
    """执行器不能安全地继续（例如有状态不明的单、查不到成交）：不改状态、不下单，交给人工。"""


@dataclass
class ExecOrder:
    cid: str
    ticker: str
    side: str                  # BUY / SELL
    kind: str                  # stock / core
    qty: int                   # 模型计划的股数
    decided_on: str            # 决策所用的 K 线日 D（成交日 = D 的下一交易日）
    limit: float | None = None
    ref_px: float = 0.0        # 个股买单：信号日收盘（跳空过滤用）；其他：D 的收盘
    reason: str = ""
    phase: str = "morning"     # morning（开盘前的寄付单）/ open（开盘后的当日限り）
    status: str = "PLANNED"    # PLANNED SENDING SENT FILLED PARTIAL UNFILLED DEFERRED MISSED SKIPPED BLOCKED REJECTED ERROR RESOLVED
    sent_qty: int = 0
    broker_id: str = ""
    order_date: str = ""
    filled_qty: int = 0
    filled_px: float = 0.0
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "ExecOrder":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def book_path(broker) -> "paths.Path":
    """执行器账本：每种券商一个（var/state/live_unified_paper.json / _tachibana.json），模拟与实盘互不干扰。"""
    tag = state_tag(broker).lstrip("_") or "paper"
    return paths.state_dir() / f"live_unified_{tag}.json"


def load_state(path, capital: float) -> UState:
    """账本里的模型状态；还没有账本 → 以 capital 円现金开始。"""
    raw = (read_json(path, {}) or {}).get("state")
    return UState.from_dict(raw) if raw else UState(cash_jpy=float(capital))


class UnifiedExecutor:
    """eng：用账本里的状态建好的 UnifiedEngine（行情要包含到最新收盘）；broker：PaperBroker（模拟账户）或 TachibanaBroker。
    paper=True 时第 k 天的开盘由这里用 K 线撮合（PaperBroker 的规则与引擎逐条相同）；实盘的开盘在交易所，第二天早上查成交。"""

    def __init__(self, eng: UnifiedEngine, broker, path=None, *, paper: bool | None = None,
                 respect_halt: bool = True, check_clock: bool = True, clock=None, sync_cash: bool | None = None,
                 auto_cap: bool = False, cap_mult: float = 1.05, persist: bool = True):
        if "US" in eng.cfg.stock_markets or any(market_of(t) != "JP" for t in eng.cfg.core):
            raise ValueError("执行器只做东证（立花 e支店没有美股）：stock_markets 只能是 JP，核心 ETF 只能是东证上市的")
        self.eng, self.b = eng, broker
        self.paper = isinstance(broker, PaperBroker) if paper is None else paper
        self.path = path or book_path(broker)
        self.respect_halt, self.check_clock = respect_halt, check_clock
        self.clock = clock or now_jst
        self.sync_cash = (not self.paper) if sync_cash is None else sync_cash
        self.auto_cap, self.cap_mult = auto_cap, cap_mult
        self.persist = persist                              # False：演练回放只在内存里记账（最后一次性保存）
        self.book = read_json(self.path, {}) or {}
        self.orders = [ExecOrder.from_dict(o) for o in self.book.get("orders", [])]
        self.events: list[dict] = []
        self.blocked: str | None = None
        self.stats = {k: 0 for k in ("fills", "unfilled_sell", "unfilled_buy", "model_diff", "deferred", "reduced",
                                     "limit_lowered", "skipped", "blocked", "cash_sync")}
        self._fills: dict[str, tuple[int, float]] = {}
        self._reconciled: list[dict] = []
        self.diffs: list[dict] = []                         # 模型会成交、实际没成交的买单（与模拟盘出现差异的起点）

    # ── 账本 ──
    def _active(self) -> list[ExecOrder]:
        d = self.eng.st.last_date
        return [o for o in self.orders if o.decided_on == d]

    def save(self, force: bool = False) -> None:
        ev = (self.book.get("events") or []) + self.events
        self.book["events"], self.events = ev[-500:], []
        self.book["history"] = (self.book.get("history") or [])[-250:]
        if not (self.persist or force):
            return
        self.book.update({"version": 1, "broker": type(self.b).__name__, "updated": self.clock().isoformat(timespec="seconds"),
                          "state": self.eng.st.to_dict(), "orders": [asdict(o) for o in self.orders]})
        atomic_write_text(self.path, json.dumps(self.book, ensure_ascii=False, indent=1, default=_np))

    def _event(self, level: str, msg: str) -> None:
        self.events.append({"at": self.clock().isoformat(timespec="seconds"), "level": level, "msg": msg})
        {"info": log.info, "warn": log.warning, "error": log.error}[level](msg)

    def block(self, reason: str) -> None:
        """这次运行不下单（状态照常对账、决策）。多个原因用「；」连起来。"""
        self.blocked = f"{self.blocked}；{reason}" if self.blocked else reason
        self._event("error", f"不下单：{reason}")

    def fill_day(self) -> dt.date | None:
        d = self.eng.st.last_date
        return next_trading_day(dt.date.fromisoformat(d)) if d else None

    def _gate(self, phase: str) -> str | None:
        if self.respect_halt and paths.halt_file().exists():
            return f"存在 HALT 文件（{paths.halt_file()}）"
        if not self.check_clock or not self.eng.st.last_date:
            return None
        now, f = self.clock(), self.fill_day()
        if phase == "morning" and (now.date() > f or (now.date() == f and now.time() >= MORNING_CUTOFF)):
            return f"已过成交日 {f} 的 {MORNING_CUTOFF:%H:%M}：寄付注文来不及（待卖的明天再下；也可以人工处理）"
        if phase == "open":
            if now.date() != f:
                return f"今天不是成交日（成交日 {f}）"
            if not OPEN_FROM <= now.time() < OPEN_UNTIL:
                return f"开盘后的买单只在 {OPEN_FROM:%H:%M}〜{OPEN_UNTIL:%H:%M} 下"
        return None

    # ── 下单 ──
    def _fee(self, o: ExecOrder):
        return self.eng.c_fee[o.ticker]["BUY" if o.side == "BUY" else "SELL"] if o.kind == "core" else self.eng.fees["JP"]

    def _reserve(self, o: ExecOrder, qty: int, limit: float | None = None) -> float:
        """买单占用的余力 = 限价 × 股数 + 手续费（券商按指値预留）。"""
        v = float(limit if limit is not None else (o.limit or 0)) * qty
        return v + self._fee(o)(v)

    def _fit_qty(self, o: ExecOrder, bp: float) -> int:
        """按原限价预留时，余力 bp 放得下的最大股数（整单元）。"""
        lot = int(self.eng.lots[self.eng.col[o.ticker]])
        q = int(o.qty)
        while q > 0 and self._reserve(o, q) > bp + 1e-9:
            q -= lot
        return max(q, 0)

    def _fit_limit(self, o: ExecOrder, qty: int, bp: float) -> float:
        """开盘后补单的限价：原限价（信号日收盘 ×1.03 / 核心 ×1.02）占用的余力放得下就用它；放不下就降到余力能承受的
        最高呼値（股数按模型的开盘价规则已经减过，所以这个价 ≥ 开盘价：价格还在开盘价附近就能成交）。"""
        from .tick import tick_size
        lim = float(o.limit)
        if self._reserve(o, qty, lim) <= bp + 1e-9:
            return lim
        p = round_to_tick(max(bp / qty, 0.01), o.ticker, "BUY")
        while p > 0 and self._reserve(o, qty, p) > bp + 1e-9:
            p = round(p - tick_size(p, o.ticker), 4)
        return p

    def _paper_extra(self, o: ExecOrder) -> dict:
        eng = self.eng
        lot = int(eng.lots[eng.col[o.ticker]])
        if o.kind == "core":
            return {"core": True, "cost": dict(eng.core_cost[o.ticker]), "lot": lot}
        if o.side == "BUY":
            return {"lot": lot, "cap": int(eng.cfg.max_positions), "excl": sorted(eng.core_set)}
        return {}

    def _send(self, o: ExecOrder, qty: int, bar: str) -> None:
        """bar 非空 = 寄付（开盘集合竞价）；空 = 盘中当日限り。先把「发送中」写进账本再发（崩溃后不会重发）。"""
        b = self.b
        o.status, o.sent_qty = "SENDING", int(qty)
        self.save()
        kw = {"extra": self._paper_extra(o)} if getattr(b, "supports_order_extra", False) else {}
        fn = b.buy if o.side == "BUY" else b.sell
        try:
            r = fn(o.ticker, int(qty), limit=o.limit if o.side == "BUY" else None, client_id=o.cid,
                   ref_px=o.ref_px, bar=bar, **kw)
        except Exception as e:                          # noqa: BLE001  适配器本身不该抛；抛了就按状态不明处理
            o.status, o.note = "ERROR", f"状态不明（{type(e).__name__}）：{e}"[:300]
            self._event("error", f"{o.side} {o.ticker} ×{qty}：{o.note}")
            self.save()
            return
        o.status = r.status if r.status in ACCEPTED + ("BLOCKED", "REJECTED", "ERROR") else "ERROR"
        o.broker_id, o.order_date = str(r.broker_id or ""), str((r.extra or {}).get("order_date") or "")
        o.note = (r.note or "")[:300]
        if self.paper and r.status in ("FILLED", "PARTIAL") and r.filled_qty > 0:
            self._fills[o.cid] = (int(r.filled_qty), float(r.filled_px))       # 模拟账户盘中单：立即成交
        if o.status == "BLOCKED":
            self.stats["blocked"] += 1
        lvl = "info" if o.status in ACCEPTED else ("warn" if o.status in ("BLOCKED", "REJECTED") else "error")
        self._event(lvl, f"{o.side} {o.ticker} ×{qty}{f' 限价 {o.limit:g}' if o.limit and o.side == 'BUY' else ''}"
                         f"（{'寄付' if bar else '盘中'}）→ {o.status} {o.note}".rstrip())
        self.save()

    def place(self, k: int) -> list[ExecOrder]:
        """第 k 根 K 线收盘后的决策 → 下一个交易日开盘的单。卖单全下；买单在开盘前余力内从前往后下，其余留到开盘后。
        同一决策重复运行：已下过 / 已留到开盘后 / 状态不明的单不再下；BLOCKED（未发出）的会重试。"""
        eng, st, b = self.eng, self.eng.st, self.b
        d = st.last_date
        why = self.blocked or self._gate("morning")
        if self.auto_cap and hasattr(b, "max_order_value"):
            b.max_order_value = round(eng.equity(k) * self.cap_mult)
        have = {o.cid: o for o in self.orders if o.decided_on == d}
        bp, deferring = None, False
        for x in eng.todo(k)["JP"]:
            t, side = x["ticker"], x["side"]
            kind = "core" if t in eng.core_set else "stock"
            cid = f"U{d}-{side}-{t}"
            o = have.get(cid)
            if o is not None and o.status not in ("PLANNED", "BLOCKED"):
                deferring = deferring or (side == "BUY" and o.status == "DEFERRED")
                continue
            if o is None:
                ref = float(x["signal_close"]) if side == "BUY" and kind == "stock" else float(eng._px_close(t, k))
                o = ExecOrder(cid, t, side, kind, int(x["qty"]), d, limit=x.get("limit") if side == "BUY" else None,
                              ref_px=ref, reason=x.get("reason") or ("entry" if side == "BUY" else ""))
                self.orders.append(o)
                have[cid] = o
            if why:
                o.status, o.note = "BLOCKED", why
                self.stats["blocked"] += 1
                continue
            if side == "BUY" and not o.limit:
                o.status, o.note = "SKIPPED", "没有收盘价，定不了限价"
                continue
            if side == "SELL":
                self._send(o, o.qty, bar=d)
                continue
            if bp is None:
                bp = float(b.cash())
            need = self._reserve(o, o.qty)
            if not deferring and need > bp + 1e-9 and kind == "core" and not self.paper:
                fit = self._fit_qty(o, bp)                  # 实盘：核心买单能放进开盘前余力的部分先下寄付，只把余数留到开盘后
                if 0 < fit < o.qty:
                    rest = ExecOrder(cid + "-2", t, side, kind, o.qty - fit, d, limit=o.limit, ref_px=o.ref_px,
                                     reason=o.reason, phase="open", status="DEFERRED",
                                     note=f"开盘前余力只够 {fit} 口（限价 ×1.02 预留）→ 余下 {o.qty - fit} 口开盘后再下")
                    o.qty, need = fit, self._reserve(o, fit)
                    self.orders.append(rest)
                    have[rest.cid] = rest
                    self.stats["deferred"] += 1
            if deferring or need > bp + 1e-9:
                o.status, o.phase = "DEFERRED", "open"
                o.note = ("排在前面的买单留到开盘后 → 这笔也留到开盘后（保持与模型相同的先后）" if deferring else
                          f"开盘前余力 {bp:,.0f} 円 < 按限价预留 {need:,.0f} 円 → 开盘后按始値检查、减股再下")
                deferring = True
                self.stats["deferred"] += 1
                continue
            self._send(o, o.qty, bar=d)
            if o.status in ACCEPTED:
                bp -= need
        if why:
            self._event("warn", f"{d} 的决策没有下单：{why}")
        self.save()
        return [o for o in self.orders if o.decided_on == d]

    def _place_deferred(self, get_open, locked: dict | None = None) -> None:
        """开盘后：留下的买单按实际始値做与模型相同的检查（没开盘价 / 跳空 / ストップ高 / 名额），再下单。
        实盘按「限价 × 股数 + 手续费 ≤ 当时余力」减股；模拟账户交给 PaperBroker 按实际成交价减（与引擎相同）。"""
        eng, st, b = self.eng, self.eng.st, self.b
        act = [o for o in self._active() if o.status == "DEFERRED"]
        if not act:
            return
        gap = eng.ex["JP"].max_entry_gap_pct
        mine = set(st.pos) | {o.ticker for o in self._active() if o.side == "BUY" and o.kind == "stock"}
        held = {t for t, p in b.positions().items() if int(p.qty) > 0 and t in mine and t not in eng.core_set}
        npos = len(held)
        if not self.paper:                                    # 实盘：早上的寄付买单，股票还没开盘（特別気配で未寄付）→ 之后可能成交，先占名额
            npos += len({o.ticker for o in self._active() if o.side == "BUY" and o.kind == "stock" and o.phase == "morning"
                         and o.status in ("SENT", "PARTIAL") and o.ticker not in held and not get_open(o.ticker)})
        bp = None if self.paper else float(b.cash())

        def skip(o: ExecOrder, why: str) -> None:
            o.status, o.note = "SKIPPED", why
            self.stats["skipped"] += 1
            self._event("info", f"BUY {o.ticker}（开盘后）放弃：{why}")
        for o in act:
            op = get_open(o.ticker)
            if not op or op <= 0:
                skip(o, "没有开盘价（停牌 / 特別気配で未寄付）—— 模型也不买")
                continue
            if o.kind == "stock":
                if gap and op > o.ref_px * (1 + gap / 100):
                    skip(o, f"开盘 {op:g} 比信号日收盘 {o.ref_px:g} 高 {op / o.ref_px - 1:+.1%}，超过 {gap:g}% —— 与模型相同")
                    continue
                if (locked or {}).get(o.ticker) == "up":
                    skip(o, "ストップ高張り付き —— 与模型相同")
                    continue
                if npos >= eng.cfg.max_positions:
                    skip(o, f"个股已有 {npos} 只（开盘的卖单没成交）—— 与模型相同")
                    continue
            qty, lim = o.qty, o.limit
            if bp is not None:                                # 实盘：先按模型的规则（开盘价 + 滑点）减股，再把限价放进余力
                lot = int(eng.lots[eng.col[o.ticker]])
                px = op * (1 + (eng.c_slip[o.ticker] if o.kind == "core" else eng.slip["JP"]))
                fee = self._fee(o)
                while qty > 0 and px * qty + fee(px * qty) > bp + 1e-9:
                    qty -= lot
                if qty <= 0:
                    skip(o, f"余力 {bp:,.0f} 円按开盘价买不起 1 单元 —— 与模型相同")
                    continue
                if qty < o.qty:
                    self.stats["reduced"] += 1
                    self._event("info", f"BUY {o.ticker}：余力 {bp:,.0f} 円，按开盘价 {op:g} 减到 {qty} 股（计划 {o.qty}）—— 与模型相同")
                lim = self._fit_limit(o, qty, bp)
                if lim < float(o.limit):
                    self.stats["limit_lowered"] += 1
                    self._event("info", f"BUY {o.ticker}：限价 {o.limit:g} 占用的余力放不下 → 降到 {lim:g}（开盘 {op:g}）")
                    o.note = f"限价 {o.limit:g}→{lim:g}（余力）"
                    o.limit = lim
            else:
                b.set_prices({o.ticker: float(op)})
            o.phase = "open"
            self._send(o, qty, bar="")
            if o.status in ACCEPTED:
                npos += o.kind == "stock"
                if bp is not None:
                    bp -= self._reserve(o, qty, lim)

    def open_phase(self) -> None:
        """实盘：开盘后（09:05 前后）下早上留下的买单。模拟账户不用调（_paper_open 里一起做）。"""
        why = self.blocked or self._gate("open")
        act = [o for o in self._active() if o.status == "DEFERRED"]
        if not act:
            self._event("info", "没有留到开盘后的买单")
            self.save()
            return
        if why:
            self._event("warn", f"开盘后的买单这次不下（仍保留，可稍后再跑）：{why}")
            self.save()
            return
        morning = [o.ticker for o in self._active() if o.side == "BUY" and o.phase == "morning" and o.status in ACCEPTED]
        q = self.b.quote_detail(sorted({o.ticker for o in act} | set(morning)))
        self._place_deferred(lambda t: (q.get(t) or {}).get("open"))
        self.save()

    # ── 成交 → 状态 ──
    def _paper_open(self, k: int) -> None:
        """模拟账户：用第 k 天的开盘价撮合前一天排队的寄付单（PaperBroker 的规则与引擎逐条相同），再下开盘后的买单；
        当天没成交的单作废（与真实券商相同）。"""
        eng, b = self.eng, self.b
        act = self._active()
        tick = sorted({o.ticker for o in act if o.ticker in eng.col})
        opens = {t: float(eng.A.open[k, eng.col[t]]) for t in tick if eng.A.has[k, eng.col[t]]}
        locked = {}
        for t in tick:
            v = eng._locked(k, eng.col[t])
            if v:
                locked[t] = v
        by = {o.cid: o for o in act}
        if act:
            for r in b.fill_pending(opens, str(eng.gidx[k].date()), max_gap_pct=eng.ex["JP"].max_entry_gap_pct,
                                    locked=locked):
                cid = r.client_id[:-2] if r.client_id.endswith("-f") else r.client_id
                if r.status == "FILLED" and r.filled_qty > 0:
                    self._fills[cid] = (int(r.filled_qty), float(r.filled_px))
                elif cid in by:
                    by[cid].note = (r.note or "")[:300]
        b.expire_pending()
        self._place_deferred(opens.get, locked)

    def _collect_fills(self) -> dict[str, tuple[int, float]]:
        if self.paper:
            f, self._fills = self._fills, {}
            return f
        out = {}
        for o in self._active():
            if o.status == "RESOLVED":
                out[o.cid] = (int(o.filled_qty), float(o.filled_px))
            elif o.status in ACCEPTED and o.broker_id:
                try:
                    r = self.b.order_status(o.broker_id, o.order_date)
                except Exception as e:                      # noqa: BLE001
                    raise ExecutorError(f"查不到 {o.side} {o.ticker}（注文番号 {o.broker_id}）的成交：{e}；"
                                        "状态没有改动，稍后重跑") from None
                out[o.cid] = (int(r["filled_qty"]), float(r["avg_px"]))
        return out

    def _reconcile(self, k: int, fills: dict[str, tuple[int, float]]) -> None:
        """把第 k 天开盘（及开盘后）的实际成交记进状态，顺序与引擎的开盘撮合相同。"""
        eng, st = self.eng, self.eng.st
        eng.begin_day(k)
        act = self._active()
        gap = eng.ex["JP"].max_entry_gap_pct
        for n in sorted(range(len(act)), key=lambda n: (act[n].side == "BUY", act[n].kind == "core", n)):
            o = act[n]
            q, px = fills.get(o.cid, (0, 0.0))
            o.filled_qty, o.filled_px = int(q), float(px)
            if o.status in ACCEPTED:
                o.status = "FILLED" if q >= (o.sent_qty or o.qty) else ("PARTIAL" if q > 0 else "UNFILLED")
            elif o.status == "DEFERRED":                     # 开盘后的补单没有跑（09:05 的 --phase open）→ 这笔没买，与模型不同
                o.status, o.note = "MISSED", "开盘后补单没有运行（--phase open），没买 —— 与模拟盘出现差异"
                self.stats["model_diff"] += not self.paper
                self._event("error", f"BUY {o.ticker} ×{o.qty}：{o.note}")
            if q <= 0:
                if o.side == "SELL" and o.status == "UNFILLED":
                    self.stats["unfilled_sell"] += 1
                    self._event("warn", f"SELL {o.ticker} 没成交（{o.note or '寄付で約定せず'}）→ 仍是待卖，今天再下")
                elif o.side == "BUY" and o.status == "UNFILLED":
                    self.stats["unfilled_buy"] += 1
                    j = eng.col.get(o.ticker)
                    op = float(eng.A.open[k, j]) if j is not None and eng.A.has[k, j] else None
                    would = op is not None and (o.kind == "core" or not gap or op <= o.ref_px * (1 + gap / 100))
                    if not self.paper and would and eng._locked(k, j) != "up":      # 模拟账户就是模型本身，不用比
                        self.stats["model_diff"] += 1
                        self.diffs.append({"bar": str(eng.gidx[k].date()), "ticker": o.ticker, "kind": o.kind,
                                           "phase": o.phase, "open": op, "limit": o.limit, "ref_px": o.ref_px})
                        self._event("warn", f"BUY {o.ticker} 没成交，但模型会买（开盘 {op:g}，限价 {o.limit:g}）→ 与模拟盘出现差异")
                continue
            self.stats["fills"] += 1
            if o.side == "SELL" and o.kind == "stock":
                ps = st.pos.get(o.ticker)
                if ps is None:
                    self._event("error", f"SELL {o.ticker} 成交 {q} 股，但状态里没有这只持仓")
                    continue
                full = q >= ps.shares
                eng.sell_fill(o.ticker, min(int(q), ps.shares), px, k, st.pending_exit.get(o.ticker) or o.reason or "exit")
                if full:
                    st.pending_exit.pop(o.ticker, None)
                else:
                    self._event("warn", f"SELL {o.ticker} 部分成交 {q}/{ps.shares} 股 → 剩下的仍是待卖")
            elif o.kind == "core":
                eng._core_trade(o.ticker, o.side, int(q), k, px=px)
            else:
                if o.ticker in st.pos:
                    self._event("error", f"BUY {o.ticker} 成交，但状态里已有这只持仓（不重复记）")
                    continue
                eng._open(o.ticker, "JP", int(q), px, k)
            self._reconciled.append({"bar": str(eng.gidx[k].date()), "side": o.side, "ticker": o.ticker,
                                     "qty": int(q), "px": round(float(px), 4), "kind": o.kind})
        for t in list(st.pending_exit):
            if t not in st.pos:
                st.pending_exit.pop(t)
        st.plan.clear()
        st.core_plan.clear()
        if act:
            self.book.setdefault("history", []).append({"fill_bar": str(eng.gidx[k].date()),
                                                        "orders": [asdict(o) for o in act]})
        self.orders = [o for o in self.orders if o not in act]

    def check_broker(self) -> None:
        """券商持仓 = 状态持仓？（执行器管的票：状态里的持仓、核心 ETF、股票池里的票）不一致 → 这次不下单。
        现金：买付可能額 − 状态现金 ≥ 1 円 → 记下；实盘以券商为准（税、实际手续费、分红入账）。"""
        eng, st, b = self.eng, self.eng.st, self.b
        held = {t: int(p.qty) for t, p in b.positions().items() if int(p.qty) > 0}
        exp = {t: int(p.shares) for t, p in st.pos.items()}
        for t, u in st.core_units.items():
            if int(u):
                exp[t] = exp.get(t, 0) + int(u)
        managed = set(exp) | set(eng.col)
        splits = {s["ticker"]: float(s["k"]) for s in self.book.get("splits", [])}
        bad = []
        for t in sorted(set(exp) | (set(held) & managed)):
            e, h = exp.get(t, 0), held.get(t, 0)
            if e == h:
                continue
            k = splits.get(t)
            if k and abs(h * k - e) < 1:
                self._event("warn", f"{t}：刚拆股 1:{k:g}，券商那边还没反映（状态 {e:,} 股 / 券商 {h:,} 股），暂不当作不一致")
                continue
            bad.append(f"{t} 状态 {e:,} 股 / 券商 {h:,} 股")
        foreign = sorted(set(held) - managed)
        if foreign:
            self._event("warn", "账户里有执行器不管的持仓（不影响下单）：" + "、".join(f"{t} {held[t]:,} 股" for t in foreign))
        if bad:
            self.block("持仓与券商不一致：" + "；".join(bad) + "（人工交易？状态不明的单？公司行为？）请核对后再跑")
        cash = float(b.cash())
        drift = cash - st.cash_jpy
        if abs(drift) >= 1.0:
            self._event("warn" if self.sync_cash else "error",
                        f"现金差 {drift:+,.0f} 円（券商买付可能額 {cash:,.0f} / 模型 {st.cash_jpy:,.0f}）"
                        + ("→ 以券商为准" if self.sync_cash else ""))
            self.book.setdefault("cash_drift", []).append([st.last_date, round(drift, 2)])
            self.book["cash_drift"] = self.book["cash_drift"][-250:]
            if self.sync_cash:
                st.cash_jpy = cash
                self.stats["cash_sync"] += 1

    def on_corp_action(self, t: str, date: str, dividend: float, split: float, div_net: float) -> None:
        """公司行为同步：模拟券商的持仓 / 排队单，与执行器账本里还没成交的单（拆股：股数 ×k、价格 ÷k）。"""
        if self.paper and hasattr(self.b, "apply_corporate_action"):
            self.b.apply_corporate_action(t, date, dividend=dividend, split=split, div_net=div_net)
        k = float(split or 0)
        if k > 0 and abs(k - 1) > 1e-9:
            for o in self.orders:
                if o.ticker == t:
                    o.qty = int(o.qty * k + 1e-6)
                    o.ref_px = o.ref_px / k
                    if o.limit:
                        o.limit = round_to_tick(o.limit / k, t, o.side)
            sp = [s for s in self.book.get("splits", []) if s.get("date", "") >= str(dt.date.fromisoformat(date)
                                                                                     - dt.timedelta(days=10))]
            self.book["splits"] = sp + [{"ticker": t, "date": date, "k": k}]

    # ── 一天 ──
    def run_bar(self, k: int, place: bool = True, corp=None) -> None:
        """第 k 根 K 线（已收盘）：[公司行为] → [模拟账户：第 k 天开盘撮合] → 对账 → 核对 → 收盘决策 → [下单]。"""
        unknown = [o for o in self._active() if o.status in UNKNOWN]
        if unknown:
            raise ExecutorError("有状态不明的单（发送中断 / 网络错误，可能已被受理）："
                                + "；".join(f"{o.cid} {o.side} {o.ticker} ×{o.sent_qty}" for o in unknown)
                                + "。请在立花的注文一覧确认，然后登记：run.py live-u --resolve <cid> --filled <股数> --px <均价>"
                                  "（没成交填 0）")
        if corp is not None:
            corp(k)
        if self.paper:
            self._paper_open(k)
        self._reconcile(k, self._collect_fills())
        self.check_broker()
        self.eng.close_phase(k)
        if place:
            self.place(k)

    def morning(self, idxs: list[int], corp=None) -> None:
        """实盘 / 模拟账户的早上：处理新收盘的交易日（通常 1 天）。实盘只能给今天的开盘下单 → 只在最后一天下单；
        中间错过的开盘（执行器没运行）等于没成交。没有新交易日 → 只补下当前决策里还没下的单。"""
        eng = self.eng
        if idxs:
            eng.prime(idxs[0])
            if not self.paper and len(idxs) > 1:
                self._event("warn", f"执行器有 {len(idxs) - 1} 个开盘没有运行（{eng.gidx[idxs[0]].date()} 之后），那几天没有下单")
            for n, k in enumerate(idxs):
                self.run_bar(k, place=self.paper or n == len(idxs) - 1, corp=corp)
        elif eng.st.last_date:
            k = int(eng.gidx.searchsorted(dt.datetime.fromisoformat(eng.st.last_date)))
            if k < len(eng.gidx) and str(eng.gidx[k].date()) == eng.st.last_date:
                eng.prime(k + 1)
                self.place(k)
        self.save()

    # ── 汇报 ──
    def summary(self) -> dict:
        eng, st = self.eng, self.eng.st
        k = int(eng.gidx.searchsorted(dt.datetime.fromisoformat(st.last_date))) if st.last_date else len(eng.gidx) - 1
        k = min(k, len(eng.gidx) - 1)
        f = self.fill_day()
        return {"broker": type(self.b).__name__, "decided_on": st.last_date, "fill_day": f.isoformat() if f else None,
                "equity_jpy": round(eng.equity(k)), "cash_jpy": round(st.cash_jpy),
                "positions": {t: {"shares": p.shares, "entry_px": round(p.entry_px, 2), "entry_date": p.entry_date,
                                  "stop_px": round(p.stop_px, 2)} for t, p in st.pos.items()},
                "core_units": {t: int(u) for t, u in st.core_units.items() if int(u)},
                "pending_exit": dict(st.pending_exit), "reconciled": list(self._reconciled),
                "orders": [asdict(o) for o in self.orders if o.decided_on == st.last_date],
                "blocked": self.blocked, "stats": dict(self.stats),
                "events": (self.book.get("events") or [])[-30:] + self.events}


def resolve_order(path, cid: str, filled: int, px: float) -> dict:
    """人工确认状态不明的单（在立花的注文一覧 / 約定照会看过之后）：登记实际成交股数与均价（没成交填 0）。
    只改账本里这一笔，下次早上的对账按登记的成交记进状态。"""
    book = read_json(path, {}) or {}
    for o in book.get("orders", []):
        if o.get("cid") == cid:
            o.update(status="RESOLVED", filled_qty=int(filled), filled_px=float(px),
                     note=f"人工确认 {now_jst():%Y-%m-%d %H:%M}：成交 {int(filled)} 股 @ {float(px):g}")
            book.setdefault("events", []).append({"at": now_jst().isoformat(timespec="seconds"), "level": "warn",
                                                  "msg": f"{cid}：{o['note']}"})
            atomic_write_text(path, json.dumps(book, ensure_ascii=False, indent=1, default=_np))
            return o
    raise KeyError(f"账本里没有 {cid}（当前的单：{[o.get('cid') for o in book.get('orders', [])]}）")


# ══════════════════════════ 演练：执行器 + 模拟账户 vs 回测引擎 ══════════════════════════
class _MemPaper(PaperBroker):
    """演练回放用：只在内存里记账（几千笔单每笔都整份写盘太慢）。"""

    def _save(self) -> None:
        pass


def rehearse(make_engine, start, end=None, kind: str = "paper", workdir=None, exchange_cls=None, before_bar=None) -> dict:
    """同一套行情走两遍：① 引擎直接回测（模拟盘的撮合）② 执行器 + 模拟账户逐日「早上对账 → 决策 → 下单 → 开盘 → 开盘后补单」。
    kind="paper"：PaperBroker（成交规则与引擎逐条相同 → 应该逐笔一致，验证执行器的记账与下单流程）；
    kind="tachibana-sim"：真实的立花适配器 + 模拟交易所（限价取整、1655 的 +2% 限价、按限价减股、开盘前不知道卖单能否成交
    这些真实约束都在 → 差异就是实盘相对模型会出现的差异）。make_engine() 每次返回一个全新状态的 UnifiedEngine。
    测试用：exchange_cls 换模拟交易所（例如部分成交）；before_bar(k, ux, exch) 在每天早上的对账之前调用（例如改券商侧的现金）。"""
    import tempfile
    from pathlib import Path

    import pandas as pd
    ref = make_engine().run(start=start, end=end)
    eng = make_engine()
    lo = 0 if start is None else int(eng.gidx.searchsorted(pd.Timestamp(start), side="left"))
    hi = len(eng.gidx) if end is None else int(eng.gidx.searchsorted(pd.Timestamp(end), side="right"))
    wd = Path(workdir or tempfile.mkdtemp(prefix="qbreak_rehearse_"))
    exch = None
    if kind == "paper":
        b = _MemPaper(state_file=wd / "paper.json", initial_cash=eng.st.cash_jpy, exec_cfg=eng.ex["JP"], market="JP")
    elif kind == "tachibana-sim":
        from .brokers import tachibana as tb
        from .brokers.tachibana import TachibanaBroker
        from .brokers.tachibana_sim import SimExchange
        tb._sleep = lambda s: None                                  # 模拟交易所即时撮合，不用等
        exch = (exchange_cls or SimExchange)(eng, cash=eng.st.cash_jpy)
        b = TachibanaBroker(transport=exch, spec=exch.spec, creds=exch.creds(), require_arm=False, confirm_timeout_s=0.0)
    else:
        raise ValueError(f"未知演练方式 {kind}（paper / tachibana-sim）")
    ux = UnifiedExecutor(eng, b, wd / f"book_{kind}.json", paper=exch is None, respect_halt=False, check_clock=False,
                         persist=False, auto_cap=True)
    eng.prime(lo)
    for k in range(lo, hi):
        if exch is not None:
            exch.open(k)                                            # 第 k 天开盘：撮合寄付单
            ux.open_phase()                                         # 开盘后：留下的买单
            exch.close_day()
            exch.set_day(k + 1)                                     # 之后（第 k 天收盘后 / 次日早上）下的单属于下一交易日
        if before_bar is not None:
            before_bar(k, ux, exch)
        ux.run_bar(k)                                               # 早上：对账 → 核对 → 决策 → 下单
    ux.save(force=True)
    res = eng.result(lo, hi)
    diff = (res.equity - ref.equity).abs()
    cols = ["ticker", "entry_date", "exit_date", "shares", "reason"]
    same_trades = res.trades[cols].reset_index(drop=True).equals(ref.trades[cols].reset_index(drop=True))
    errors = [e["msg"] for e in ux.book.get("events", []) if e["level"] == "error"]
    return {"kind": kind, "engine": ref, "executor": res, "stats": dict(ux.stats), "max_abs_diff": float(diff.max()),
            "final_diff": float(res.equity.iloc[-1] - ref.equity.iloc[-1]), "same_trades": bool(same_trades),
            "same_core": res.state.core_trades == ref.state.core_trades, "errors": errors[-20:], "diffs": ux.diffs,
            "calls": dict(getattr(exch, "calls", {}) or {}), "book": str(wd / f"book_{kind}.json"),
            "ux": ux, "exchange": exch}


# ══════════════════════════ 汇报：与模拟盘比较、通知、日志 ══════════════════════════
def compare_with_sim(st: UState, sim: UState | None) -> dict:
    """执行器账户 vs 模拟盘账户：同一决策日时逐项比较（个股股数、1655 口数、现金、权益）；不是同一天就不比（例如云端当天还没入库）。"""
    pos = lambda s: {t: int(p.shares) for t, p in s.pos.items()}                     # noqa: E731
    core = lambda s: {t: int(u) for t, u in s.core_units.items() if int(u)}          # noqa: E731
    eq = lambda s: float(s.history[-1][1]) if s.history else None                    # noqa: E731
    out = {"exec_date": st.last_date, "sim_date": sim.last_date if sim else None, "comparable": False, "same": None}
    if sim is None or not sim.last_date or st.last_date != sim.last_date:
        out["text"] = (f"模拟盘停在 {(sim.last_date if sim else None) or '—'}、执行器在 {st.last_date or '—'}："
                       "不是同一天，这次不比（云端当天的例行任务可能还没入库）")
        return out
    diff = eq(st) - eq(sim) if eq(st) is not None and eq(sim) is not None else None
    same = pos(st) == pos(sim) and core(st) == core(sim) and abs(st.cash_jpy - sim.cash_jpy) < 1.0
    out.update(comparable=True, same=same, equity_diff_jpy=diff)
    if same:
        out["text"] = "与云端模拟盘一致（个股、1655、现金、权益）"
    else:
        parts = []
        if pos(st) != pos(sim):
            parts.append(f"个股 {pos(st) or '无'} vs {pos(sim) or '无'}")
        if core(st) != core(sim):
            parts.append(f"1655 {core(st) or '无'} vs {core(sim) or '无'}")
        parts.append(f"现金差 {st.cash_jpy - sim.cash_jpy:+,.0f} 円")
        if diff is not None:
            parts.append(f"权益差 {diff:+,.0f} 円")
        out["text"] = "★ 与云端模拟盘不一致：" + "；".join(parts)
    return out


def _qty_txt(o: dict) -> str:
    return f"{int(o.get('sent_qty') or o['qty']):,} {'口' if o.get('kind') == 'core' else '股'}"


def daily_text(sm: dict, st: UState, cmp: dict | None, paper: bool, capital: float) -> tuple[str, str, str]:
    """(标题, 通知用的一行, 日志正文)。每个数字带单位。"""
    hist = st.history or []
    eq = float(hist[-1][1]) if hist else float(sm.get("equity_jpy") or capital)
    chg = eq - float(hist[-2][1]) if len(hist) > 1 else 0.0
    ret = (eq / capital - 1) * 100 if capital else 0.0
    title = f"qbreak {'模拟操盘' if paper else '立花实盘'} {sm.get('decided_on') or ''}"
    orders = [o for o in sm.get("orders") or [] if o.get("status") not in ("SKIPPED",)]
    short = f"权益 ¥{eq:,.0f}（当日 {chg:+,.0f} 円，累计 {ret:+.2f}%）｜下一开盘的单 {len(orders)} 笔"
    if cmp and cmp.get("comparable"):
        short += "｜与云端一致" if cmp.get("same") else "｜★ 与云端不一致"
    if sm.get("blocked"):
        short += "｜★ 没下单"
    lines = [f"- 决策日 {sm.get('decided_on') or '—'} → 成交日 {sm.get('fill_day') or '—'}；权益 ¥{eq:,.0f}"
             f"（当日 {chg:+,.0f} 円，累计 {ret:+.2f}%）；现金 ¥{float(st.cash_jpy):,.0f}"]
    held = [f"{t} {int(p.shares):,} 股（成本 ¥{float(p.entry_px):,.2f}，止损 ¥{float(p.stop_px):,.2f}）" for t, p in st.pos.items()]
    held += [f"{t} {int(u):,} 口" for t, u in st.core_units.items() if int(u)]
    lines.append("- 持仓：" + ("；".join(held) if held else "无（全部现金）"))
    for r in sm.get("reconciled") or []:
        unit = "口" if r.get("kind") == "core" else "股"
        lines.append(f"- 已成交（{r['bar']} 开盘）：{'买' if r['side'] == 'BUY' else '卖'} {r['ticker']} {int(r['qty']):,} {unit} @ ¥{float(r['px']):,.2f}")
    for o in sm.get("orders") or []:
        how = ("寄付成行" if o["side"] == "SELL" else
               f"{'寄付' if o.get('phase') == 'morning' and o.get('status') != 'DEFERRED' else '开盘后'}指値 ≤ ¥{float(o['limit']):,.0f}")
        lines.append(f"- 下一开盘：{'卖' if o['side'] == 'SELL' else '买'} {o['ticker']} {_qty_txt(o)}（{how}）→ {o['status']}"
                     + (f"：{o['note']}" if o.get("note") else ""))
    if not sm.get("orders"):
        lines.append("- 下一开盘：没有单")
    if cmp:
        lines.append(f"- {cmp['text']}")
    if sm.get("blocked"):
        lines.append(f"- ★ 没有下单：{sm['blocked']}")
    for e in [e for e in sm.get("events") or [] if e.get("level") == "error"][-5:]:
        lines.append(f"- ★ {e['msg']}")
    return title, short, "\n".join(lines)


def append_journal(path, when: str, title: str, body: str) -> None:
    """模拟操盘 / 实盘日志（markdown，按时间追加，一天一节）。"""
    from pathlib import Path
    p = Path(path)
    head = "" if p.exists() else "# 执行器日志（每个交易日早上一节；数字都带单位）\n"
    with p.open("a", encoding="utf-8") as f:
        f.write(f"{head}\n## {when}　{title}\n{body}\n")


def mac_notify(title: str, text: str) -> bool:
    """macOS 通知中心（osascript；参数经 argv 传入，不拼接脚本 → 引号、换行都安全）。其他系统返回 False。"""
    import subprocess
    import sys
    if sys.platform != "darwin":
        return False
    try:
        subprocess.run(["osascript", "-e", "on run argv", "-e",
                        "display notification (item 1 of argv) with title (item 2 of argv)", "-e", "end run",
                        text, title], timeout=15, capture_output=True, check=False)
        return True
    except Exception:                                    # noqa: BLE001
        return False
