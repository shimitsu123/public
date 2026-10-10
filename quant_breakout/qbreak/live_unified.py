"""live_unified.py — 一个账户方案（S0C2：日本个股 4×25% + 闲置资金 1655.T，立花 e支店）的实盘执行器。

和模拟盘用同一个推进器（qbreak/unified.py）：模拟盘按「开盘价 ± 滑点」撮合；执行器把**券商的实际成交**记进同一份状态。
收盘后的离场判断、统一决策（明天的单）都是同一段代码 —— 成交相同，实盘就与模拟盘 / 回测逐笔相同。

每个交易日（F = 成交日，D = 它的上一交易日）
  早上（F 的 06:30〜08:55，美股 D 收盘之后；Mac 定时任务 07:40）  run.py live-u --phase morning
    ① 对账：D 那天下的单 → 向券商查实际成交（数量 / 均价）→ 记进状态。顺序与引擎相同：个股卖 → 核心卖 → 个股买 → 核心买。
       卖单没成交（ストップ安張り付き等）→ 仍是「待卖」，今天再下；买单没成交 → 作废（信号只在次日开盘有效，与回测相同）
    ② 核对：券商持仓 = 状态持仓？不一致 → 今天不下单、报警。现金以券商的买付可能額为准（税、实际手续费、分红入账都在这里对齐）
    ③ 决策：D 收盘后的离场判断 + 统一决策（与模拟盘同一段代码）
    ④ 下单：卖单全部下 寄付成行。买单按「开盘前的买付余力」从前往后下 寄付指値（个股 = 信号日收盘 ×1.03，核心 = 收盘 ×1.02）。
       放不下的（要等开盘卖出的钱）连同排在它后面的买单一起留到开盘后，保持与模型相同的先后
  开盘后（F 的 09:05 前后）  run.py live-u --phase open
    ⑤ 留下的买单：用券商给的始値做同一条跳空过滤与名额检查，按当时的余力减到买得起，下当日限り指値（价格同上）
  盘中（F 的 09:00〜11:30、12:30〜15:25；页面点了手动指令时面板叫）  run.py live-u --phase now
    ⑥ 等着的手动指令马上下单（now_phase：先卖后买；单记在这次决策里，第二天早上的对账记进账本）

手动指令（qbreak/manual_orders.py；页面 / run.py manual 写，manual_tag 给了才读）：卖出全部 / 减仓 / 调仓（股数 / 金额 / % ，
  可加可减）/ 买入（新开仓）/ 闲置资金比例 / 不自动买回。开盘前：在「收盘离场判断之后、统一决策之前」变成开盘的寄付单（与规则的单
  同一条路：同样的闸门、同样的对账）；盘中：now_phase 马上下单。所以不会让持仓核对停下。加仓成交后并进原来的持仓（成本加权平均，
  止损 / 峰值 / 持有天数不变）；买入成交后就是普通持仓（止损按 ATR，规则离场）。

安全闸（任何一道不过 → 不下单，只记账、报警）：
  HALT 文件 / 行情没更新到应有的交易日 / 持仓与券商不一致 / 时间窗口不对 / 有状态不明的单 /
  （立花本番）账本是另一台 Mac 的（check_host：两台 Mac 同时跑会重复下单）/ 新代码的冒烟测试没过（run.py --block-reason）；
  （立花）还有 ARM 未解锁、第二暗証番号缺失、单笔金额上限（默认 = 权益 ×1.05，核心 ETF 一笔可到权益的 100%）。
发单类请求绝不自动重发：发单前先在账本记「发送中」再发。发送途中崩溃、或网络错误（可能已被受理）的单，下次看到就停下，
等人工在立花的注文一覧确认后登记（run.py live-u --resolve），不猜（注文一覧里的候选：unknown_candidates / liveu.sh unknown）。
撤单（cancel_orders；qbreak/live_ops.py）：只撤执行器自己今天还挂着的单，HALT 时也可以撤；撤掉的单记 CANCELLED，第二天照实际成交对账。

与模型（回测 / 模拟盘）的已知差异 —— 都来自真实下单的约束，演练（run.py live-u-rehearse）逐项统计：
  • 买单是限价：价格按呼値向下取整，开盘恰好落在取整前后之间时不成交；核心 ETF 开盘高于收盘 +2% 时不成交（模型照买）
  • 留到开盘后的买单：按「限价 × 股数 + 手续费 ≤ 余力」减股（模型按实际开盘价减）；实盘在盘中成交，价格 ≠ 开盘价
  • 开盘前下的买单不知道同一开盘的卖单能不能成交：卖单遇到ストップ安没成交时，个股会暂时多于 4 只（模型会放弃这笔买入）
"""
from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from . import manual_orders as MO
from . import paths
from .brokers.base import state_tag
from .brokers.paper import PaperBroker
from .calendar_jp import next_trading_day, now_jst, prev_trading_day
from .manual_orders import Manual
from .tick import round_to_tick
from .unified import UnifiedEngine, UState, market_of
from .utils import atomic_write_text, read_json, setup_logging

log = setup_logging("live_unified")

ACCEPTED = ("SENT", "FILLED", "PARTIAL")          # 券商已受理（可能已成交）
UNKNOWN = ("SENDING", "ERROR")                     # 状态不明：可能已被受理 → 不重发，等人工确认
MORNING_CUTOFF = dt.time(8, 55)                    # 寄付注文的最后时刻（留 5 分钟余量）
MANUAL_REASONS = ("manual", "manual_trim", "manual_add", "manual_buy")   # 手动指令变成的单（qbreak/manual_orders.py）
OPEN_FROM, OPEN_UNTIL = dt.time(9, 0), dt.time(15, 25)
NOW_BUY_BUF = MO.NOW_BUY_BUF                       # 盘中手动买单的限价：现价 +0.5%（可成交的限价；不超过决策日收盘 ×1.03；面板同一个数）
NO_QUOTE = "取不到现价，没下"                      # 立花适配器：盘中单这一刻取不到现价 → BLOCKED（不发成行；手动指令一会儿再试）
CUTOFF_TEXT = "寄付注文来不及"                     # _gate("morning") 的时间窗口原因里的字样（B13 据此认出「错过寄付」）
LATE_SELL_NOTE = "早上错过寄付 → 开盘后当日限价卖（2026-10-09 用户同意）"   # B13：规则的个股卖单（止损 / 离场 / 减仓 / 手动卖）
LATE_BUY_NOTE = "错过寄付：今天不买（与模型不同 → 记入差异）"
LATE_CORE_NOTE = "错过寄付：核心 ETF 今天不调（下一次决策重新算目标；与模型不同 → 记入差异）"
QUOTE_FAIL = "取价失败"                            # B7：开盘后补单取价整个失败（DEFERRED 全部保留，09:20 再试）
NO_OPEN_WAIT = "还没寄り付き（特別気配？）：09:20 再看"
NO_OPEN_FINAL = "到 09:20 还没有始値（特別気配 / 停牌）：今天不买（与模型不同 → 记入差异）"
PRECLOSE_MAX_PCT = 3.0                             # LU-15：Yahoo 收盘 vs 立花前日終値 差超过这个 % → 那只的寄付买单不下（卖单只提醒）
BREAKER_N, BREAKER_VALUE = 2, 2.2                  # C-11：规则单笔数 > (个股名额 + 核心 ETF 只数) × 2，或金额合计 > 权益 × 2.2 → 异常熔断


def _np(x):
    """json 默认转换：numpy 标量 → Python 数（np.int64 不是 int 的子类，不转会被写成字符串）。"""
    return x.item() if hasattr(x, "item") else str(x)


class ExecutorError(RuntimeError):
    """执行器不能安全地继续（例如有状态不明的单、查不到成交）：不改状态、不下单，交给人工。"""


class HostError(ExecutorError):
    """立花本番的账本是另一台 Mac 的（OPS-04，check_host）：不连券商（连上去会把另一台的会话踢掉）、不下单。"""


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
    phase: str = "morning"     # morning（开盘前的寄付单）/ open（开盘后的当日限り）/ now（盘中的手动指令）
    status: str = "PLANNED"    # PLANNED SENDING SENT FILLED PARTIAL UNFILLED DEFERRED MISSED SKIPPED BLOCKED REJECTED EXPIRED ERROR RESOLVED
    #                            EXPIRED：交易所 / 立花那边已经失效（当日限り到期、取消完了…）—— 不算受理中、也不是状态不明；已成交的部分按 filled_qty 对账
    #                            CANCELLED：你撤了单（cancel_orders / qbreak/live_ops.py）—— 不算受理中、也不是状态不明；第二天早上照立花的实际成交对账，
    #                                       没成交的部分与「没成交」同一处理（卖单：规则还要卖就再下；买单：不再买）
    sent_qty: int = 0
    broker_id: str = ""
    order_date: str = ""
    filled_qty: int = 0
    filled_px: float = 0.0
    note: str = ""
    sent_at: str = ""          # 发出（记「发送中」）的时刻：状态不明时按它找注文一覧里的候选（qbreak/live_ops.unknown_candidates）

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
                 auto_cap: bool = False, cap_mult: float = 1.05, persist: bool = True, pre_send=None,
                 manual_tag: str | None = None):
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
        self.pre_send = pre_send                            # (票, BUY/SELL, stock/core) -> 理由 | None：发买单前的资格检查（qbreak/eligibility.py）
        self.book = read_json(self.path, {}) or {}
        self.orders = [ExecOrder.from_dict(o) for o in self.book.get("orders", [])]
        self.events: list[dict] = []
        self.blocked: str | None = None
        self.stats = {k: 0 for k in ("fills", "unfilled_sell", "unfilled_buy", "model_diff", "deferred", "reduced",
                                     "limit_lowered", "skipped", "blocked", "cash_sync", "gate")}
        self._fills: dict[str, tuple[int, float]] = {}
        self._reconciled: list[dict] = []
        self.diffs: list[dict] = []                         # 模型会成交、实际没成交的买单（与模拟盘出现差异的起点）
        self.incomplete: str | None = None                  # 这次运行没做完（例如开盘后补单取价失败，单都保留）→ 运行状态 ok=False
        self.corp_provider = None                           # 公司行为数据（run.py 给立花）：成交日当天生效的拆股 → 寄付单按拆股后下（LU-22）
        self.manual = Manual(self.book, manual_tag, self.clock) if manual_tag else None   # 手动指令（演练 / 回放不读）
        if self.manual is not None:
            self._wire_manual()

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

    def resolve_cmd(self) -> str:
        """登记状态不明的单的命令（提示用）：经 liveu.sh（数据目录 ~/.qbreak/home）。直接跑 run.py 默认是模拟账户、仓库的 var/，
        立花的入口在那里会被拒绝。"""
        stem = Path(self.path).stem
        br = "paper" if self.paper else ("tachibana" + (" --demo" if "_demo" in stem else "")
                                         + (" --dry-run" if "_dryrun" in stem else ""))
        return f"bash scripts/liveu.sh --broker {br} --resolve <cid> --filled <股数> --px <均价>"

    def block(self, reason: str) -> None:
        """这次运行不下单（状态照常对账、决策）。多个原因用「；」连起来。"""
        self.blocked = f"{self.blocked}；{reason}" if self.blocked else reason
        self._event("error", f"不下单：{reason}")

    def _wire_manual(self) -> None:
        """手动指令接进引擎：闲置资金比例 → 核心目标额 × 比例；手动卖出后不自动买回 → 新仓的资格检查多一条。"""
        eng, man = self.eng, self.manual
        eng.core_scale = man.core_pct / 100
        man.m["cap_pct"] = round(float(eng.cfg.max_position_pct) * 100, 2)     # 页面的加仓 / 买入上限（单只占总权益 %）
        man.m["max_positions"] = int(eng.cfg.max_positions)                     # 页面的个股名额（买入要有空名额）
        man.m["core"] = sorted(eng.core_set)                                     # 核心 ETF（不能手动买，用闲置资金比例调）
        base = eng.entry_gate_fn

        def gate(t: str, i: int) -> str | None:
            return (base(t, i) if base is not None else None) or man.block_reason(t, eng.gidx[i])
        eng.entry_gate_fn = gate

    def _apply_manual(self, i: int, deciding: bool = True) -> None:
        """第 i 根 K 线的决策之前（deciding）或同一决策补单之前：等着的手动卖出 / 减仓 / 调整 → 执行器的单
        （成交日 = i 的下一交易日；HALT 时不动；加仓只在 deciding）。"""
        fill = next_trading_day(self.eng.gidx[i].date())
        halted = self.respect_halt and paths.halt_file().exists()
        for lvl, msg in self.manual.apply(self.eng, i, fill, halted=halted, deciding=deciding):
            self._event(lvl, msg)

    def _core_pending(self, today: dt.date | None = None) -> float | None:
        """闲置资金比例改了、核心 ETF 还没照新比例调过（today 给了：今天也没说「明天再调」）→ 新比例（%）；否则 None。"""
        cr = self.book.get("core_rule") or {}
        if self.manual is None:
            return None
        want = float(self.manual.core_pct)
        if not cr.get("units100"):                            # 执行器还没用新代码决策过（没有规则目标额）：上一次决策的比例 = 100%
            if today is None:                                 # 决策：比例改了 / 盘中的单没成交完 → 这次直接调到目标（不看再平衡带）
                return want if cr.get("redo") or abs(want - float(cr.get("applied", 100.0))) > 1e-9 else None
            st = self.eng.st                                  # 盘中：卖出全部（0%）照样卖；别的比例按估算的目标调（MO.core_u100_est）
            held = any(int(u) > 0 for u in st.core_units.values()) or bool(st.core_plan)
            return want if (held and abs(want - float(cr.get("applied", 100.0))) > 1e-9
                            and cr.get("defer") != today.isoformat()) else None
        if today is not None and (cr.get("decided_on") != self.eng.st.last_date or cr.get("defer") == today.isoformat()):
            return None
        if today is None and cr.get("redo"):                  # 盘中照新比例的单没成交完（对账时记下）→ 这次决策再照比例调
            return want
        return want if abs(want - float(cr.get("applied", cr.get("pct", want)))) > 1e-9 else None

    def _record_core(self, k: int, exact: bool = False) -> None:
        """决策之后：核心 ETF 的规则目标（闲置资金比例 100% 时的口数）、收盘、单元、这次用的比例（页面 / 盘中的 ETF 调仓换算用）。
        exact（这次照新比例直接调到目标）且有核心 ETF 的单 → 记下这些票：第二天对账时没全部成交（HALT / 没成交 / 没下）→ 下一次决策再照比例调。"""
        eng = self.eng
        pct = round(float(eng.core_scale) * 100, 2)
        cr = {"decided_on": eng.st.last_date, "pct": pct, "applied": pct,
              "units100": {t: int(n) for t, n in sorted(eng.core_t100.items())},
              "px": {t: round(float(eng._px_close(t, k)), 4) for t in sorted(eng.core_t100)},
              "lot": {t: int(eng.lots[eng.col[t]]) for t in sorted(eng.core_t100)}}
        if exact and eng.st.core_plan:
            cr.update(exact_on=eng.st.last_date, exact_plan=sorted(eng.st.core_plan))
        prev = self.book.get("core_rule") or {}
        if self.manual is not None and float(self.manual.core_pct) <= 0 and prev.get("units100") is not None:
            p100 = prev.get("units100") or {}               # 停买闲置资金 ETF 时：规则从「不拿」变成「拿」= 买入信号 → 只提醒，你确认才买
            new = [t for t, n in cr["units100"].items() if n > 0 and int(p100.get(t, 0)) <= 0]
            if new:
                sig = {"date": eng.st.last_date,
                       "items": [{"ticker": t, "units": int(cr["units100"][t]), "px": cr["px"].get(t),
                                  "yen": round(int(cr["units100"][t]) * float(cr["px"].get(t) or 0))} for t in new]}
                self.manual.m["core_signal"] = sig
                from .manual_orders import signal_text
                self._event("warn", f"★ 闲置资金 ETF 买入信号（{sig['date']} 收盘）：{signal_text(sig)}；你卖出后停着："
                                    "确认后才买（面板「确认买入」，或 liveu.sh manual core --pct 100）")
            else:                                           # 还没确认、规则又不拿信号里的那几只了 → 信号撤掉（继续停买）
                old = self.manual.m.get("core_signal") or {}
                if old and not any(int(cr["units100"].get(x.get("ticker"), 0)) > 0 for x in old.get("items") or []):
                    self.manual.m.pop("core_signal", None)
                    self._event("info", f"闲置资金 ETF 的买入信号（{old.get('date')} 收盘）没了：规则又不拿了，继续停买")
        self.book["core_rule"] = cr

    def _settle_manual(self) -> None:
        """撤回中的手动指令：这次决策里它的单还没发到交易所 → 撤（不再重下）；已经发出的等对账。"""
        d = self.eng.st.last_date
        out = ("PLANNED", "BLOCKED", "SKIPPED")
        sent = {o.ticker for o in self.orders if o.decided_on == d and o.side == "SELL" and o.kind == "stock"
                and o.reason in ("manual", "manual_trim") and o.status not in out}
        sent_add = {o.ticker for o in self.orders if o.decided_on == d and o.reason in ("manual_add", "manual_buy")
                    and o.status not in out + ("DEFERRED",)}            # 留到开盘后的加仓 / 买入还没发出：可以撤
        for lvl, msg in self.manual.settle(self.eng.st, sent, sent_add):
            self._event(lvl, msg)
        for o in self.orders:                                # 撤掉的手动单还没发出的 → 不再重试
            if o.decided_on == d and o.reason in MANUAL_REASONS and not self._manual_wanted(o) \
                    and (o.status in ("PLANNED", "BLOCKED") or (o.reason in ("manual_add", "manual_buy") and o.status == "DEFERRED")):
                o.status, o.note = "SKIPPED", "手动指令已撤回"

    def _manual_wanted(self, o: ExecOrder) -> bool:
        """这笔手动单之后还要不要再下（没撤回、还在待卖 / 减仓 / 加仓里）。"""
        st = self.eng.st
        if self.manual.cancelling(o.ticker):
            return False
        if o.reason == "manual_trim":
            return o.ticker in self.manual.m["trims"] and o.ticker not in st.pending_exit
        if o.reason == "manual_add":
            return o.ticker in st.add_plan and o.ticker in self.manual.m["adds"]
        if o.reason == "manual_buy":
            return o.ticker in st.plan and o.ticker in self.manual.m["buys"]
        return st.pending_exit.get(o.ticker) == "manual"

    def _manual_wanted_add(self, t: str) -> bool:
        return not self.manual.cancelling(t) and t in self.manual.m["adds"]

    def _manual_buy(self, t: str, d: str) -> bool:
        """计划里的这笔个股买入是不是这次决策的手动买入（不是规则的新仓）。"""
        return self.manual is not None and (self.manual.m["buys"].get(t) or {}).get("decided_on") == d

    def fill_day(self) -> dt.date | None:
        d = self.eng.st.last_date
        return next_trading_day(dt.date.fromisoformat(d)) if d else None

    def _gate(self, phase: str) -> str | None:
        if self.respect_halt and paths.halt_file().exists():
            seen = self.book.setdefault("halt_seen", [])          # 上线门槛「HALT 演练过一次」的证据（run.py live-gate）
            day = self.clock().date().isoformat()
            if day not in seen:
                seen.append(day)
                self.book["halt_seen"] = seen[-30:]
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

    def _late_window(self) -> bool:
        """B13：立花（非模拟账户）、成交日 08:55 之后、15:25 之前 —— 今天的寄付已经错过，但还在当天的交易时间里。"""
        if self.paper or not self.check_clock or not self.eng.st.last_date:
            return False
        now, f = self.clock(), self.fill_day()
        return now.date() == f and MORNING_CUTOFF <= now.time() < OPEN_UNTIL

    def _mismatch_today(self) -> str | None:
        """LU-21：今天早上的持仓核对（check_broker / check_positions）发现的不一致（账本 broker_mismatch，同一天才算）→ 原因；
        没有 → None。盘中 / 开盘后 / 早上晚到的单都按它挡住，直到下一次早上核对一致（清掉）。"""
        mm = self.book.get("broker_mismatch") or {}
        if mm.get("text") and mm.get("date") == self.clock().date().isoformat():
            return str(mm["text"])
        return None

    def _late_skip(self, o: ExecOrder) -> None:
        """B13：错过寄付时规则的买单（与核心 ETF 的卖单）今天不下：SKIPPED，记入与模型的差异。"""
        o.status = "SKIPPED"
        o.note = LATE_BUY_NOTE if o.side == "BUY" else LATE_CORE_NOTE
        self.stats["skipped"] += 1
        self.stats["model_diff"] += 1
        if o.side == "BUY":
            self.diffs.append({"bar": str(self.fill_day()), "ticker": o.ticker, "kind": o.kind, "phase": "late",
                               "open": None, "limit": o.limit, "ref_px": o.ref_px})
        self._event("warn", f"{o.side} {o.ticker} ×{o.qty}：{o.note}")

    def _send_late(self, o: ExecOrder) -> None:
        """B13：早上错过寄付的个股卖单 → 当日限价卖（与盘中的手动卖同一算法：适配器按现价 −0.5%、夹在値幅里）；
        这一刻取不到现价（开盘前 / 还没寄り付き）→ 适配器不发（不发成行），BLOCKED 留给 09:05 / 09:20 的开盘后运行再试。"""
        o.phase = "late"
        self._send(o, o.qty, bar="")
        if o.status == "BLOCKED" and str(o.note).startswith(NO_QUOTE):
            o.note = f"{LATE_SELL_NOTE}：{o.note}，09:05 / 09:20 的开盘后运行再试"
        elif o.status in ACCEPTED or o.status in UNKNOWN:
            o.note = f"{LATE_SELL_NOTE}；{o.note}".rstrip("；")[:300]
        self.save()

    def _late_sells(self) -> list[ExecOrder]:
        """开盘后运行（09:05 / 09:20）要补的 B13 卖单：当前决策里因为错过寄付（时间窗口）或那一刻取不到现价而没发出的个股卖单。"""
        if self.paper:
            return []
        return [o for o in self._active() if o.side == "SELL" and o.kind == "stock" and o.status == "BLOCKED"
                and not o.broker_id and (o.phase == "late" or CUTOFF_TEXT in str(o.note))]

    # ── LU-22：成交日当天生效的拆股 ──
    def _splits_today(self, tickers) -> dict[str, list[tuple[str, float]]]:
        """公司行为数据里 日期 ∈ (决策日, 成交日] 的拆股 / 合并 → {票: [(日期, 比例)]}。没有数据 / 取不到 / 模拟账户 → {}（照旧）。"""
        prov = self.corp_provider
        d, f = self.eng.st.last_date, self.fill_day()
        if prov is None or self.paper or not d or f is None:
            return {}
        from .corpactions import due
        out: dict[str, list[tuple[str, float]]] = {}
        for t in sorted(set(tickers)):
            try:
                acts = due(prov, t, d, f.isoformat())
            except Exception as e:                          # noqa: BLE001
                log.info("公司行为数据取不到（%s %s）：今天的单照旧", t, type(e).__name__)
                continue
            sp = [(str(a["date"]), float(a.get("split") or 0)) for a in acts
                  if float(a.get("split") or 0) > 0 and abs(float(a.get("split") or 0) - 1) > 1e-9]
            if sp:
                out[t] = sp
        return out

    def _remember_closes(self, k: int) -> None:
        """记下这次决策用的收盘（每个决策第一次运行时记一次，留最近 3 个决策日）：下一次决策遇到成交日当天生效的拆股时，
        拿它判断行情这期间是不是已经按拆股调整过（Yahoo 记下拆股后会把过去的收盘整段 ÷k）。只在立花账户。"""
        eng, d = self.eng, self.eng.st.last_date
        cs = dict(self.book.get("closes_seen") or {})
        if self.paper or not d or d in cs:
            return
        cs[d] = {t: round(float(eng.A.close[k, j]), 4) for t, j in eng.col.items() if eng.A.has[k, j]}
        self.book["closes_seen"] = {x: cs[x] for x in sorted(cs)[-3:]}

    def _split_basis(self, t: str, kk: float) -> str | None:
        """引擎的价格是拆股前（"pre"）还是已经按拆股调整过（"post"）：上一个决策日记下的收盘 vs 现在行情里同一天的收盘。
        比值 ≈ 1 → 还没调整（单是按拆股前的价格算的）；≈ 1/k → 已经调整；没有记录 / 对不上 → None（判断不了）。"""
        import pandas as pd
        eng, d = self.eng, self.eng.st.last_date
        cs = self.book.get("closes_seen") or {}
        prev = sorted(x for x in cs if x < str(d))
        if not prev or t not in eng.col:
            return None
        dd = prev[-1]
        then = float((cs.get(dd) or {}).get(t) or 0)
        i, j = int(eng.gidx.searchsorted(pd.Timestamp(dd))), eng.col[t]
        if then <= 0 or i >= len(eng.gidx) or eng.gidx[i].date().isoformat() != dd or not eng.A.has[i, j]:
            return None
        r = float(eng.A.close[i, j]) / then
        if abs(r - 1) <= 0.02:
            return "pre"
        if abs(r * kk - 1) <= 0.03:
            return "post"
        return None

    def _split_adjust(self, o: ExecOrder, acts: list[tuple[str, float]]) -> str | None:
        """成交日当天生效的拆股 / 合并（比例 k）：
          • 个股卖单：股数来自账本的持仓（拆股前）→ 总是 ×k（向下取整到 1 股；零股另有 C-14 处理）；
          • 个股买单 / 核心 ETF 的单：股数、限价是引擎按行情算的 → 先判断行情是不是已经按拆股调整过（_split_basis）：
            还没调整 → 股数 ×k（买单向下取整到一手）、价格 ÷k；已经调整 → 个股买单照引擎的单（不再调第二次）；
            判断不了 / 核心 ETF 的行情已经调整（目标口数和账本口数基准不同）→ 这笔不下（返回原因，记入与模型的差异）。
        调过 / 已经是拆股后的单记进 split_pre：第二天的公司行为同步（on_corp_action）不再调。"""
        k = 1.0
        for _, s in acts:
            k *= s
        t = o.ticker
        lot = int(self.eng.lots[self.eng.col[t]]) if t in self.eng.col else 1
        stock_sell = o.side == "SELL" and o.kind == "stock"
        basis = self._split_basis(t, k)
        when = f"今天（{acts[-1][0]}）拆股 / 合并 1:{k:g} 生效"
        if basis != "pre" and not stock_sell and not (basis == "post" and o.kind == "stock"):
            return (f"{when}，{'行情已经按拆股调整、核心 ETF 的目标口数和账本口数对不上' if basis == 'post' else '判断不了行情是不是已经按拆股调整'}"
                    " → 这笔不下（与模型不同 → 记入差异）")
        q0, l0 = int(o.qty), o.limit
        if basis == "pre" or stock_sell:
            o.qty = int(o.qty * k / lot + 1e-9) * lot if o.side == "BUY" else int(o.qty * k + 1e-6)
        if basis == "pre":
            o.ref_px = o.ref_px / k
            if o.limit:
                o.limit = round_to_tick(o.limit / k, t, o.side, lot=lot)
        pre = [s for s in self.book.get("split_pre") or []
               if s.get("date", "") >= str(dt.date.fromisoformat(acts[-1][0]) - dt.timedelta(days=10))]
        self.book["split_pre"] = pre + [{"ticker": t, "date": dd, "k": s, "cid": o.cid} for dd, s in acts]
        if basis == "post" and (o.qty, o.limit) == (q0, l0):
            self._event("warn", f"{o.side} {t}：{when}，行情已经按拆股调整过 → 照引擎的单下（不再调）")
        else:
            self._event("warn", f"{o.side} {t}：{when} → 按拆股后下单：{q0:,}→{o.qty:,} "
                                f"{'口' if o.kind == 'core' else '股'}" + (f"，限价 {l0:g}→{o.limit:g}" if l0 and l0 != o.limit else ""))
        return None

    # ── LU-15：下单前核对立花的前日終値 ──
    def _prev_closes(self, tickers) -> dict[str, float]:
        """立花本番：一次请求取这些票的前日終値（quote_detail 的 prev_close）。模拟账户 / デモ（假价格）/ 取不到 → {}（不比）。"""
        if self.paper or getattr(self.b, "demo", False) or not hasattr(self.b, "quote_detail"):
            return {}
        try:
            q = self.b.quote_detail(sorted(set(tickers))) or {}
        except Exception as e:                              # noqa: BLE001
            log.info("前日終値取不到（%s）：这次不核对", type(e).__name__)
            return {}
        return {t: float(v["prev_close"]) for t, v in q.items() if (v or {}).get("prev_close")}

    # ── C-11：单次运行的异常熔断 ──
    def _breaker(self, k: int, todo: list[dict]) -> str | None:
        """这次决策的规则单（不含手动指令）笔数 > (个股名额 + 核心 ETF 只数) × 2，或买卖金额合计（卖 = 收盘、买 = 限价）> 权益 × 2.2
        → 原因（这次全部不下）。规则本身：个股最多 4 只、每只每天最多一买一卖，所以正常运行不会出现；出现了多半是程序的错。"""
        eng, d = self.eng, self.eng.st.last_date
        rule = [x for x in todo if not (x.get("reason") in MANUAL_REASONS
                                        or (x["side"] == "BUY" and x["ticker"] not in eng.core_set and not x.get("reason")
                                            and self._manual_buy(x["ticker"], d)))]
        cap = (int(eng.cfg.max_positions) + len(eng.core_set)) * BREAKER_N
        eq = float(eng.equity(k))
        val = sum(int(x["qty"]) * float(x.get("limit") or eng._px_close(x["ticker"], k) or 0) for x in rule)
        if len(rule) > cap:
            return (f"异常熔断：这次决策的规则单 {len(rule)} 笔，超过上限 {cap} 笔（(个股名额 {int(eng.cfg.max_positions)} + "
                    f"核心 ETF {len(eng.core_set)}) × {BREAKER_N}）（正常运行不会出现，请看日志）")
        if math.isfinite(eq) and eq > 0 and val > eq * BREAKER_VALUE:
            return (f"异常熔断：这次决策的规则单金额合计 ¥{val:,.0f}，超过权益 ¥{eq:,.0f} × {BREAKER_VALUE:g}"
                    "（正常运行不会出现，请看日志）")
        return None

    # ── C-14：单元未满株（拆股 / 合并后多出的零股）──
    def _odd_lot(self, o: ExecOrder, qty: int) -> int:
        """立花的卖单里不足一手的部分（普通注文卖不掉）。模拟账户不拆（与模型相同）。"""
        if self.paper or o.side != "SELL" or o.ticker not in self.eng.col:
            return 0
        lot = int(self.eng.lots[self.eng.col[o.ticker]])
        return int(qty) % lot if lot > 1 else 0

    def _note_odd(self, t: str, n: int, lot: int | None = None) -> str:
        """零股记进账本 odd_lots（通知 / 日志 / 面板显示，你在立花网站卖完说一声，人工代下登记）。第一次 / 股数变了才记事件。"""
        lot = lot or (int(self.eng.lots[self.eng.col[t]]) if t in self.eng.col else 0)
        txt = (f"{t} 有 {int(n):,} 股不足一手（売買単位 {lot:,}）：单元未满株不能用 API 的普通注文卖 → 在立花网站卖"
               "（端株手续费 0.55%），卖完在 Mac 对话里说一声登记")
        ol = self.book.setdefault("odd_lots", {})
        if int((ol.get(t) or {}).get("shares") or 0) != int(n):
            self._event("warn", f"★ {txt}")
        ol[t] = {"shares": int(n), "lot": int(lot), "since": (ol.get(t) or {}).get("since") or self.clock().date().isoformat(),
                 "text": txt}
        return txt

    def _odd_cleanup(self) -> None:
        """零股记录：那只已经没有了 / 不再有零股 → 去掉。"""
        ol, st = self.book.get("odd_lots") or {}, self.eng.st
        for t in list(ol):
            n = int(st.pos[t].shares) if t in st.pos else int(st.core_units.get(t, 0) or 0)
            lot = max(int(self.eng.lots[self.eng.col[t]]) if t in self.eng.col else 1,
                      int((ol[t] or {}).get("lot") or 1))      # 适配器按立花売買単位拆出的零股：引擎的一手可能是 1
            if n <= 0 or lot <= 1 or n % lot == 0:
                ol.pop(t, None)
        if not ol:
            self.book.pop("odd_lots", None)

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

    def _bp_why(self) -> str:
        """T4：开盘后按余力减股 / 放弃时写原因。模型的余力不扣譲渡益税；最近几天有盈利卖出（预计代扣 ≥ ¥1,000）→ 写明「疑似
        譲渡益税预扣占了余力」（立花在约定日还是受渡日扣，上线头几次核对：MACOS 第 5 步），否则写「余力规则与模型相同」。只是说明，不改下单。"""
        if self.paper:
            return "余力规则与模型相同"
        try:
            from .tax_ytd import withheld_change
            fd = self.fill_day()
            tax = withheld_change(self.eng.st, str(fd - dt.timedelta(days=4)), str(fd))
        except Exception:                             # noqa: BLE001  只是说明文字
            tax = 0.0
        if tax >= 1000:
            return (f"疑似譲渡益税预扣占了余力（最近的盈利卖出预计代扣约 ¥{tax:,.0f}；模型不扣税）—— "
                    "这是与模型的差异，不是错误")
        return "余力规则与模型相同"

    def _fit_limit(self, o: ExecOrder, qty: int, bp: float) -> float:
        """开盘后补单的限价：原限价（信号日收盘 ×1.03 / 核心 ×1.02）占用的余力放得下就用它；放不下就降到余力能承受的
        最高呼値（股数按模型的开盘价规则已经减过，所以这个价 ≥ 开盘价：价格还在开盘价附近就能成交）。"""
        from .tick import tick_size
        lim = float(o.limit)
        if self._reserve(o, qty, lim) <= bp + 1e-9:
            return lim
        lot = int(self.eng.lots[self.eng.col[o.ticker]]) if o.ticker in self.eng.col else None   # 呼値表：一手 1 口的 ETF 2027-03 起用 O 表
        p = round_to_tick(max(bp / qty, 0.01), o.ticker, "BUY", lot=lot)
        while p > 0 and self._reserve(o, qty, p) > bp + 1e-9:
            p = round(p - tick_size(p, o.ticker, lot=lot), 4)
        return p

    def _paper_extra(self, o: ExecOrder) -> dict:
        eng = self.eng
        lot = int(eng.lots[eng.col[o.ticker]])
        if o.kind == "core":
            return {"core": True, "cost": dict(eng.core_cost[o.ticker]), "lot": lot}
        if o.side == "BUY" and o.reason == "manual_add":   # 手动加仓：已经持有的票，不占新名额
            return {"lot": lot}
        if o.side == "BUY":
            return {"lot": lot, "cap": int(eng.cfg.max_positions), "excl": sorted(eng.core_set)}
        return {}

    def _gate_buy(self, o: ExecOrder) -> str | None:
        """发买单前再确认一次这只票没被踢出 / 没被指定（执行器里的最新数据；卖单不查）。"""
        if o.side != "BUY" or self.pre_send is None:
            return None
        why = self.pre_send(o.ticker, o.side, o.kind)
        if why:
            self.stats["gate"] += 1
            self._event("warn", f"BUY {o.ticker} 不下：资格检查 —— {why}")
            return f"资格检查：{why}"
        return None

    def _send(self, o: ExecOrder, qty: int, bar: str) -> None:
        """bar 非空 = 寄付（开盘集合竞价）；空 = 盘中当日限り。先把「发送中」写进账本再发（崩溃后不会重发）。
        立花的卖单里不足一手的部分（C-14：拆股 / 合并后的零股）不发：整数手照常下，零股记进 odd_lots 并提醒你在立花网站卖。"""
        b = self.b
        odd = self._odd_lot(o, qty)
        if odd:
            txt = self._note_odd(o.ticker, odd)
            qty = int(qty) - odd
            if qty <= 0:                                    # 全是零股：这笔不发（天天重发也只会被拒）
                o.status, o.sent_qty, o.note = "SKIPPED", 0, f"零股：{txt}"[:300]
                self.stats["skipped"] += 1
                self.save()
                return
        o.status, o.sent_qty = "SENDING", int(qty)
        o.sent_at = self.clock().isoformat(timespec="seconds")
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
        o.status = r.status if r.status in ACCEPTED + ("BLOCKED", "REJECTED", "EXPIRED", "ERROR") else "ERROR"
        o.broker_id, o.order_date = str(r.broker_id or ""), str((r.extra or {}).get("order_date") or "")
        o.note = (r.note or "")[:300]
        odd2 = int((r.extra or {}).get("odd_lot") or 0)
        if odd2 and o.side == "SELL" and not self.paper:    # 立花銘柄マスタ的売買単位与行情配置不同：适配器拆出的零股（只发了整数手）
            o.sent_qty = max(0, int(qty) - odd2)
            self._note_odd(o.ticker, odd2, int((r.extra or {}).get("lot") or 0) or None)
        if self.paper and r.status in ("FILLED", "PARTIAL", "EXPIRED") and r.filled_qty > 0:
            self._fills[o.cid] = (int(r.filled_qty), float(r.filled_px))       # 模拟账户盘中单：立即成交
        if o.phase == "now" and r.filled_qty > 0:          # 盘中的手动单：成交记在单上（模拟账户第二天早上的对账从这里读）
            o.filled_qty, o.filled_px = int(r.filled_qty), float(r.filled_px)
        if o.status == "BLOCKED":
            self.stats["blocked"] += 1
        lvl = "info" if o.status in ACCEPTED else ("warn" if o.status in ("BLOCKED", "REJECTED", "EXPIRED") else "error")
        self._event(lvl, f"{o.side} {o.ticker} ×{qty}{f' 限价 {o.limit:g}' if o.limit and o.side == 'BUY' else ''}"
                         f"（{'寄付' if bar else ('盘中' if o.phase == 'now' else '开盘后')}）→ {o.status} {o.note}".rstrip())
        self.save()

    def place(self, k: int) -> list[ExecOrder]:
        """第 k 根 K 线收盘后的决策 → 下一个交易日开盘的单。卖单全下；买单在开盘前余力内从前往后下，其余留到开盘后。
        同一决策重复运行：已下过 / 已留到开盘后 / 状态不明的单不再下；BLOCKED（未发出）的会重试。
        立花（非模拟账户）另外：
          • B13 早上错过寄付（成交日 08:55〜15:25 才跑到这里）：个股卖单改当日限价卖（_send_late），买单 / 核心 ETF 的单今天不下
            （SKIPPED，记入差异）；今天早上的持仓核对不一致（LU-21）照样全部挡住；
          • C-11 异常熔断：规则单的笔数 / 金额超过规则可能的上限 → 全部不下；
          • LU-22 成交日当天生效的拆股：新建的单按拆股后的股数 / 价格；
          • LU-15 寄付单发出前拿立花的前日終値核对决策用的收盘：差 > 3% → 那只的买单不下（卖单只提醒）。"""
        eng, st, b = self.eng, self.eng.st, self.b
        d = st.last_date
        g = self._gate("morning")                           # 总是先看闸门（HALT 存在时记下演练的证据）
        late = bool(g) and CUTOFF_TEXT in str(g) and not self.blocked and self._late_window()
        if late:                                            # 时间窗口不再挡卖单；早上 09:00 之后不再核对持仓 → 按今天早上记下的核对结果挡
            g = None
            mm = self._mismatch_today()
            if mm:
                self.block(mm)
        if self.auto_cap and hasattr(b, "max_order_value"):
            b.max_order_value = round(eng.equity(k) * self.cap_mult)
        have = {o.cid: o for o in self.orders if o.decided_on == d}
        bp, deferring = None, False
        now_t = {o.ticker for o in self.orders if o.decided_on == d and o.phase == "now"}   # 盘中已经下过单的票：这次决策不再下
        todo = [x for x in eng.todo(k)["JP"] if x["ticker"] not in now_t]
        if self.manual is not None:                         # 手动减仓：卖单，排在规则的卖单之后、买单之前
            n_sell = sum(1 for x in todo if x["side"] == "SELL")
            todo[n_sell:n_sell] = [{"side": "SELL", "ticker": t, "qty": n, "reason": "manual_trim", "cid": f"U{d}-SELL-{t}-M"}
                                   for t, n, _ in self.manual.trim_orders(st)]
        if not self.paper and not (self.blocked or g) and todo:
            br = self._breaker(k, todo)
            if br:
                self.block(br)
        why = self.blocked or g
        fresh = [x["ticker"] for x in todo if x.get("cid", f"U{d}-{x['side']}-{x['ticker']}") not in have]
        splits = self._splits_today(fresh) if fresh else {}   # 被挡时也要算：单这时建好（BLOCKED），重试时不再新建
        split_cids = {s.get("cid") for s in self.book.get("split_pre") or []}   # 之前的运行已经按拆股调过的单（重试时）
        pcs: dict | None = None
        n_late = 0

        def prev_close(t: str) -> float | None:            # 立花的前日終値：要用时才取（一次请求取这次全部的票）
            nonlocal pcs
            if pcs is None:
                pcs = self._prev_closes(x["ticker"] for x in todo)
            return pcs.get(t)
        for x in todo:
            t, side = x["ticker"], x["side"]
            kind = "core" if t in eng.core_set else "stock"
            if side == "BUY" and kind == "stock" and not x.get("reason") and self._manual_buy(t, d):
                if self.manual.cancelling(t):
                    continue                                # 撤回中的手动买入：不下
                x = {**x, "reason": "manual_buy"}           # 手动买入：与规则的新仓同一笔计划，单的理由与 cid 分开记
            cid = x.get("cid") or (f"U{d}-BUY-{t}-M" if x.get("reason") in ("manual_add", "manual_buy") else f"U{d}-{side}-{t}")
            if x.get("reason") == "manual_add" and self.manual is not None and not self._manual_wanted_add(t):
                continue                                    # 撤回了的加仓：不下
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
                if t in splits:                             # LU-22：今天生效的拆股 → 按拆股后的股数 / 价格
                    sk = self._split_adjust(o, splits[t])
                    if sk:
                        o.status, o.note = "SKIPPED", sk
                        self.stats["skipped"] += 1
                        self.stats["model_diff"] += 1
                        self._event("warn", f"{side} {t} ×{o.qty}：{sk}")
                        continue
                    split_cids.add(o.cid)
            if why:
                o.status, o.note = "BLOCKED", why
                self.stats["blocked"] += 1
                continue
            if o.qty <= 0:                                  # 拆股 / 合并调整后不够一手（重试时也查：之前的运行调过的单）
                o.status, o.note = "SKIPPED", ("按拆股 / 合并后的股数不够一手：这笔不下" if o.cid in split_cids
                                               else "股数为 0：这笔不下")
                continue
            if late:                                        # B13：错过寄付 → 个股卖单当日限价卖；其余今天不下
                n_late += 1
                if side == "SELL" and kind == "stock":
                    self._send_late(o)
                else:
                    self._late_skip(o)
                continue
            if side == "BUY" and not o.limit:
                o.status, o.note = "SKIPPED", "没有收盘价，定不了限价"
                continue
            g = self._gate_buy(o)
            if g:
                o.status, o.note = "SKIPPED", g
                continue
            pc = prev_close(t) if o.cid not in split_cids else None  # LU-15：拆股当天的价格本来就对不上，不比
            c = float(eng._px_close(t, k) or 0)
            if pc and c > 0 and abs(pc / c - 1) * 100 > PRECLOSE_MAX_PCT:
                w = f"Yahoo 收盘 ¥{c:,g} 和立花前日終値 ¥{pc:,g} 差 {abs(pc / c - 1) * 100:.1f}%（拆股 / 数据错？）"
                if side == "BUY":
                    o.status, o.note = "BLOCKED", f"{w}：这只的买单不下"
                    self.stats["blocked"] += 1
                    self._event("warn", f"BUY {t} 不下：{w}")
                    continue
                self._event("warn", f"SELL {t}：{w} → 卖单照下")
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
        self._remember_closes(k)                            # LU-22：下一次决策判断行情有没有按拆股调整用
        if why:
            self._event("warn", f"{d} 的决策没有下单：{why}")
        elif n_late:
            self._event("warn", f"{d} 的决策：早上错过寄付（{self.clock():%H:%M}）→ 个股卖单改开盘后当日限价卖、买单与核心 ETF 今天不下"
                                "（2026-10-09 用户同意；与模型不同的记入差异）")
        self.save()
        return [o for o in self.orders if o.decided_on == d]

    def _place_deferred(self, get_open, locked: dict | None = None, no_open: str | None = None) -> None:
        """开盘后：留下的买单按实际始値做与模型相同的检查（没开盘价 / 跳空 / ストップ高 / 名额），再下单。
        实盘按「限价 × 股数 + 手续费 ≤ 当时余力」减股；模拟账户交给 PaperBroker 按实际成交价减（与引擎相同）。
        no_open：立花这时还没有始値的票（B7）——"wait"（09:05）保留 DEFERRED，09:20 再看；"final"（09:20 的重试）放弃，
        记入与模型的差异（模型按日线开盘价，晚开盘也照买）；None（模拟账户 / 演练：没有开盘价 = 那天没有 K 线）→ 放弃，模型也不买。"""
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
        waiting = []
        for o in act:
            g = self._gate_buy(o)
            if g:
                o.status, o.note = "SKIPPED", g
                continue
            op = get_open(o.ticker)
            if not op or op <= 0:
                if no_open == "wait":                         # 还没寄り付き：保留，09:20 再看（先占着名额与余力：保持与模型相同的先后）
                    o.note = NO_OPEN_WAIT
                    waiting.append(o.ticker)
                    npos += o.kind == "stock" and o.reason != "manual_add"
                    if bp is not None:
                        bp = max(0.0, bp - self._reserve(o, o.qty))
                elif no_open == "final":
                    skip(o, NO_OPEN_FINAL)
                    self.stats["model_diff"] += 1
                    self.diffs.append({"bar": str(self.fill_day()), "ticker": o.ticker, "kind": o.kind, "phase": "open",
                                       "open": None, "limit": o.limit, "ref_px": o.ref_px})
                else:
                    skip(o, "没有开盘价（停牌 / 特別気配で未寄付）—— 模型也不买")
                continue
            if o.kind == "stock":
                if gap and op > o.ref_px * (1 + gap / 100):
                    skip(o, f"开盘 {op:g} 比信号日收盘 {o.ref_px:g} 高 {op / o.ref_px - 1:+.1%}，超过 {gap:g}% —— 与模型相同")
                    continue
                if (locked or {}).get(o.ticker) == "up":
                    skip(o, "ストップ高張り付き —— 与模型相同")
                    continue
                if npos >= eng.cfg.max_positions and o.reason != "manual_add":
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
                    skip(o, f"余力 {bp:,.0f} 円按开盘价买不起 1 单元 —— {self._bp_why()}")
                    continue
                if qty < o.qty:
                    self.stats["reduced"] += 1
                    self._event("info", f"BUY {o.ticker}：余力 {bp:,.0f} 円，按开盘价 {op:g} 减到 {qty} 股（计划 {o.qty}）—— {self._bp_why()}")
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
                npos += o.kind == "stock" and o.reason != "manual_add"
                if bp is not None:
                    bp -= self._reserve(o, qty, lim)
        if waiting:
            self._event("info", f"BUY {'、'.join(waiting)}（开盘后）：{NO_OPEN_WAIT}（单保留）")

    def open_phase(self, final: bool | None = None) -> None:
        """实盘：开盘后（09:05 前后）下早上留下的买单。模拟账户不用调（_paper_open 里一起做）。
        手动指令：先读新的撤回（留到开盘后、还没发出的加仓买单这时还能撤）；新的卖出 / 调整等下一次早上的运行。
        立花（B7）：取价整个失败 → 一笔都不动（DEFERRED 全部保留）、记 warn、self.incomplete（运行状态 ok=False），09:20 照常再跑；
        个别票还没有始値：final=False（09:05）保留到 09:20 再看，final=True（09:20 的重试）放弃并记入差异；
        final=None（演练 / 测试：一天只跑一次开盘后）→ 没有始値 = 那天没有 K 线，放弃（模型也不买）。
        B13：早上错过寄付、还没发出的个股卖单在这里补成当日限价卖。LU-21：今天早上的持仓核对不一致 → 这里也不下。"""
        if self.manual is not None:
            for lvl, msg in self.manual.ingest():
                self._event(lvl, msg)
            self._settle_manual()
        g = self._gate("open")                              # 总是先看闸门（HALT 存在时记下演练的证据）
        why = self.blocked or g
        act = [o for o in self._active() if o.status == "DEFERRED"]
        late = self._late_sells()
        if not act and not late:
            self._event("info", "没有留到开盘后的买单")
            self.save()
            return
        why = why or self._mismatch_today()
        if why:
            self._event("warn", f"开盘后的{'买单' if act else '卖单'}这次不下（仍保留，可稍后再跑）：{why}")
            self.save()
            return
        if self.auto_cap and hasattr(self.b, "max_order_value"):
            # 09:05 / 09:20 是新进程（broker 的上限是 run.py 传入的默认值）→ 与 place / now_phase 一样按决策日的权益 ×1.05；
            # 权益只读账本状态与收盘价（不用 prime、不改状态）；算不出（没有价）→ 保留传入的上限
            eng, d = self.eng, self.eng.st.last_date
            k = int(eng.gidx.searchsorted(dt.datetime.fromisoformat(d))) if d else len(eng.gidx) - 1
            eq = float(eng.equity(min(k, len(eng.gidx) - 1)))
            if math.isfinite(eq) and eq > 0:
                self.b.max_order_value = round(eq * self.cap_mult)
        for o in late:                                      # B13：卖在买之前（卖出的钱今天的买单用不上，但次序与模型相同）
            self._send_late(o)
        if act:
            morning = [o.ticker for o in self._active() if o.side == "BUY" and o.phase == "morning" and o.status in ACCEPTED]
            try:
                q = self.b.quote_detail(sorted({o.ticker for o in act} | set(morning)), strict=True)
            except Exception as e:                          # noqa: BLE001  取价整个失败：不当成「没有开盘价」（那会把买单全部放弃）
                when = self.clock().strftime("%H:%M")
                self.incomplete = (f"{QUOTE_FAIL}（{when}）：开盘后的买单 {len(act)} 笔这次没下（都保留）"
                                   + ("；09:20 的重试也没取到 → 没有下一次定时运行了（明天早上记为没买、与模拟盘不同；"
                                      "也可以手动再跑 bash scripts/liveu.sh run --broker tachibana --phase open）" if final
                                      else "，09:20 再试"))
                for o in act:
                    o.note = f"{QUOTE_FAIL}（{when}）：{str(e)[:120]}"
                self._event("warn", f"{self.incomplete}：{type(e).__name__}: {str(e)[:200]}")
                self.save()
                return
            self._place_deferred(lambda t: (q.get(t) or {}).get("open"),
                                 no_open=None if final is None else ("final" if final else "wait"))
        self.save()

    # ── 盘中：手动指令马上下单 ──
    @staticmethod
    def _unsent_now(o: ExecOrder) -> bool:
        """盘中的单根本没到交易所（适配器 BLOCKED，例如这一刻取不到现价、不发成行；之后撤回的记成 SKIPPED）：不算「今天已经有单」，
        一会儿再试的手动指令可以再下（推到明天开盘的指令本来就不在待办里）。"""
        return o.phase == "now" and o.status in ("BLOCKED", "SKIPPED") and not o.broker_id

    def now_phase(self, quote) -> dict:
        """交易时间里（09:00〜11:30、12:30〜15:25）等着的手动指令马上下单（2026-10-07 用户：「当天买入卖出的话在交易时间段就直接
        进行买入卖出 在交易时间之前的话就等交易时间的时候进行交易」）。quote(票列表) → {票: 现在价}（立花：現在値；模拟账户：
        Yahoo 最新的 1 分钟线，约晚 20 分钟）。
        先卖（卖出全部 / 减仓 / 调仓往下）再买（买入 / 调仓往上）。单记在这次决策里（decided_on = 账本的决策日、成交日 = 今天），
        第二天早上的对账按实际成交记进账本（模拟账户当场成交，成交记在单上）；没成交的卖单 → 下一开盘再卖（与寄付卖单相同）。
        闸门与开盘的单相同：HALT、今天早上的运行已完成、没有状态不明的单、实盘：券商的股数 ≥ 账本；买入 / 加仓：资格检查 /
        立花能不能买 / 不买回 / 决算前 / 新仓倍数 0、名额、单只上限、单笔上限；买入限价 = min(现价 +0.5%, 决策日收盘 ×1.03)
        （现价高于收盘 ×1.03 → 不买，与开盘买入同一个上限）；钱不够 → 先卖核心 ETF（今天有单的核心不动），还不够就减股。
        今天已经有执行器的单的票（规则 / 手动，开盘或盘中）不下第二笔 → 明天早上的运行处理（明天开盘）。
        返回 {"placed", "later", "rejected", "retry"} 各几条 + "items"（每条指令的状态与说明）。"""
        out = {"placed": 0, "later": 0, "rejected": 0, "retry": 0, "items": []}
        man = self.manual
        if man is None:
            return out
        for lvl, msg in man.ingest():
            self._event(lvl, msg)
        self._settle_manual()
        now = self.clock()
        stamp, today = now.isoformat(timespec="seconds"), now.date()
        todo = [it for it in man.pending(MO.ORDER_KINDS) if it.get("hold") != today.isoformat()]   # 「明天开盘」的不再试
        core_want = self._core_pending(today)                 # 闲置资金比例改了：核心 ETF 也马上照新比例调
        if not todo and core_want is None:
            self.save()
            return out
        cr = self.book.setdefault("core_rule", {}) if core_want is not None else (self.book.get("core_rule") or {})
        core_it = ([None] + sorted((it for it in man.m["items"].values() if it.get("kind") == "core" and it.get("status") == "done"),
                                   key=lambda x: x.get("at", "")))[-1]          # 最新生效的闲置资金比例指令（同一时刻 → 后写的）
        eng, st, b = self.eng, self.eng.st, self.b
        d = st.last_date
        k = int(eng.gidx.searchsorted(dt.datetime.fromisoformat(d))) if d else len(eng.gidx)
        why = None
        if self.respect_halt and paths.halt_file().exists():
            why = "HALT 生效中，解除之后才处理"
        elif MO.timing(now)[0] != "now":
            why = "现在不是交易时间（09:00〜11:30、12:30〜15:25）"
        elif not d or d < prev_trading_day(today).isoformat():
            why = "今天早上的运行还没完成（它会先处理）"
        elif not (k < len(eng.gidx) and str(eng.gidx[k].date()) == d):
            why = f"行情里没有决策日 {d} 的 K 线"
        if why is None and self.blocked:                     # run.py --block-reason（例：新代码的冒烟测试没过）：盘中也不下，一会儿再试
            why = self.blocked
        if why:
            for it in todo:
                it.update(tried=stamp, msg=why)
            out["retry"] = len(todo)
            out["items"] = [{"id": it["id"], "ticker": it["ticker"], "status": MO.status_text(it), "msg": why} for it in todo]
            if core_want is not None:
                cr["tried"] = stamp
                out["retry"] += 1
                out["items"].append({"id": (core_it or {}).get("id", "core"), "ticker": f"闲置资金比例 {core_want:g}%",
                                     "status": "等", "msg": why})
            self._event("warn" if "HALT" in why else "info", f"手动指令 {out['retry']} 条这次没下：{why}")
            self.save()
            return out
        mm = self._mismatch_today()
        if mm:                                                # LU-21：今天早上的持仓核对不一致 → 盘中也不下（明天早上先核对持仓）
            self.block(mm)
            msg = f"今天早上的持仓核对不一致 → 明天开盘处理（明天早上先核对持仓；{mm}）"[:300]
            for it in todo:
                it.update(hold=today.isoformat(), tried=stamp, msg=msg)
            out["later"] = len(todo)
            out["items"] = [{"id": it["id"], "ticker": it["ticker"], "status": MO.status_text(it), "msg": msg} for it in todo]
            if core_want is not None:
                cr["defer"] = today.isoformat()
                out["later"] += 1
                out["items"].append({"id": (core_it or {}).get("id", "core"), "ticker": f"闲置资金比例 {core_want:g}%",
                                     "status": "明天开盘", "msg": msg})
            self.save()
            return out
        unknown = [o for o in self._active() if o.status in UNKNOWN]
        if unknown:
            raise ExecutorError("有状态不明的单（发送中断 / 网络错误，可能已被受理）："
                                + "；".join(f"{o.cid} {o.side} {o.ticker} ×{o.sent_qty}" for o in unknown)
                                + f"。请在立花的注文一覧确认，然后登记：{self.resolve_cmd()}（没成交填 0）")
        eng.prime(k + 1)
        if self.auto_cap and hasattr(b, "max_order_value"):
            b.max_order_value = round(eng.equity(k) * self.cap_mult)
        decided = eng.gidx[k].date()
        eq, cfg, gap = float(eng.equity(k)), eng.cfg, float(eng.ex["JP"].max_entry_gap_pct or 0)
        busy = {o.ticker for o in self._active() if not self._unsent_now(o)}   # 盘中没到交易所的单不算（一会儿再试）
        cores = sorted((t for t, u in st.core_units.items() if int(u) > 0 and t in eng.col),
                       key=lambda t: -int(st.core_units[t]) * float(eng._px_close(t, k)))
        core_moves = {}                                       # {票: (现在口数, 目标口数)}：目标 = 规则目标（比例 100%）× 新比例
        if core_want is not None:
            u100s = cr.get("units100")
            if not u100s:                                     # 没算过规则目标额：比例还是 100% → 现在的口数 + 今天开盘的单（与面板 MO.core_u100s 同一个估算）
                u100s = ({t: MO.core_u100_est(st.core_units.get(t, 0), st.core_plan.get(t)) for t in set(st.core_units) | set(st.core_plan)}
                         if abs(float(cr.get("applied", 100.0)) - 100.0) <= 1e-9 else
                         {t: 0 for t, u in st.core_units.items() if int(u) > 0})          # 比例已经改过（今天调过）→ 只会是卖出全部
            for t, n100 in sorted(u100s.items()):
                if t in eng.col:
                    lt = int(eng.lots[eng.col[t]])
                    cur = int(st.core_units.get(t, 0))
                    tgt = int(math.floor(int(n100) * core_want / 100 / lt + 1e-9)) * lt
                    if tgt != cur or t in busy:               # 今天已经有单的：账本的口数还没算进今天的成交 → 下一次决策再调
                        core_moves[t] = (cur, tgt)
        want_px = sorted({it["ticker"] for it in todo} | {t for t in cores if t not in busy} | {t for t in core_moves if t not in busy})
        try:
            px = {t: float(v) for t, v in (quote(want_px) or {}).items() if v and float(v) > 0}
        except Exception as e:                                # noqa: BLE001
            px = {}
            self._event("warn", f"取不到现价（{type(e).__name__}: {e}）")
        held = None if self.paper else {t: int(p.qty) for t, p in b.positions().items()}
        tag = f"N{now:%H%M%S}"

        def lot_of(t: str) -> int:
            return int(eng.lots[eng.col[t]]) if t in eng.col else MO.LOT

        def later(it: dict, msg: str) -> None:              # 今天不下 → 明天早上的运行（明天开盘）
            it.update(hold=today.isoformat(), tried=stamp, msg=f"{msg} → 明天开盘处理")
            out["later"] += 1

        def retry(it: dict, msg: str) -> None:              # 一会儿再试
            it.update(tried=stamp, msg=msg)
            out["retry"] += 1

        def no(it: dict, msg: str, status: str = "rejected") -> None:
            it.update(status=status, decided_on=d, msg=msg)
            for f in ("hold", "tried"):
                it.pop(f, None)
            out["rejected"] += 1

        def sent(o: ExecOrder, it: dict, what: str, n: int, notes: list[str]) -> bool:
            """发出之后：受理（含状态不明）→ 记进指令；BLOCKED → 明天开盘；REJECTED → 没执行。返回是否受理。"""
            busy.add(o.ticker)
            if o.status in ACCEPTED or o.status in UNKNOWN or (o.status == "EXPIRED" and int(o.filled_qty or 0) > 0):
                q = int(o.filled_qty or 0)
                if o.status in UNKNOWN:
                    m = f"盘中{what} {n:,} 股：下单结果不明，请在立花的注文一覧确认"
                elif o.status == "EXPIRED":                 # 成交了一部分、其余在交易所那边失效了
                    m = f"盘中{what}：成交 {q:,} / {n:,} 股 @ ¥{float(o.filled_px):,.2f}，其余已失效（{o.note}）"
                elif q >= n:
                    m = f"盘中{what} {n:,} 股 @ ¥{float(o.filled_px):,.2f}" + ("（模拟：约 20 分钟前的价）" if self.paper else "")
                elif q > 0:
                    m = f"盘中{what}：成交 {q:,} / {n:,} 股 @ ¥{float(o.filled_px):,.2f}，其余挂着（今天有效）"
                else:
                    m = f"盘中{what} {n:,} 股：已下单，等成交（今天有效）"
                it.update(status="placed", now=True, decided_on=d, fill_day=today.isoformat(), shares=int(n),
                          side=o.side, msg=m + "".join(f"；{x}" for x in notes))
                if q > 0:
                    it["fill"] = {"qty": q, "px": round(float(o.filled_px), 2)}
                if o.side == "BUY":
                    it["limit"] = o.limit
                for f in ("hold", "tried", "wait"):
                    it.pop(f, None)
                out["placed"] += 1
                return True
            if o.status == "BLOCKED" and str(o.note).startswith(NO_QUOTE):     # 立花那边这一刻取不到现价：一会儿再试（不发成行）
                o.status, o.note = "SKIPPED", f"{o.note}：{MO.RETRY_S // 60} 分钟后再试（下一次是新的一笔）"
                retry(it, f"{NO_QUOTE}（不发成行单），{MO.RETRY_S // 60} 分钟后再试")
            elif o.status == "BLOCKED":
                later(it, f"没下（{o.note or '被挡'}）")
            elif o.status == "EXPIRED":
                no(it, f"下了单，但在立花那边已失效、没成交：{o.note or o.status}")
            else:
                no(it, f"立花没受理：{o.note or o.status}")
            return False

        def cash_now() -> float:
            """现在能用来买的钱：券商的余力 − 今天开盘还没下 / 还没撮合的买单要占的（留给它们）× (1 − 现金缓冲)。"""
            res = sum(self._reserve(o, o.qty) for o in self._active() if o.side == "BUY"
                      and (o.status == "DEFERRED" or (self.paper and o.phase == "morning" and o.status in ACCEPTED)))
            return (float(b.cash()) - res) * (1 - float(cfg.cash_buffer_pct) / 100)

        def fund(short: float) -> list[str]:
            """钱不够：卖核心 ETF 补 short 円（今天有单的核心不动；按现价）。返回说明。"""
            notes = []
            for c in cores:
                if short <= 0:
                    break
                u, pc = int(st.core_units.get(c, 0)), px.get(c)
                if held is not None:
                    u = min(u, held.get(c, 0))
                if c in busy or u <= 0 or not pc:
                    continue
                lot_c, net = lot_of(c), pc * (1 - float(eng.c_slip[c]))
                n = min(u, int(math.ceil(short / max(net * 0.995, 1e-9) / lot_c)) * lot_c)
                if n <= 0:
                    continue
                o = ExecOrder(f"U{d}-SELL-{c}-{tag}", c, "SELL", "core", n, d, ref_px=pc, reason="manual_fund", phase="now")
                if self.paper:
                    b.set_prices({c: pc})
                self.orders.append(o)
                self._send(o, n, bar="")
                busy.add(c)
                if o.status in ACCEPTED:
                    notes.append(f"先卖核心 ETF {c} {n:,} 口")
                    short -= n * net - float(eng.c_fee[c]["SELL"](n * net))
            return notes

        buys = []
        for it in todo:                                       # ① 卖：卖出全部 / 减仓 / 调仓往下（调仓往上放到 ②）
            t, kind = it["ticker"], it["kind"]
            it.pop("wait", None)
            if kind == "buy":
                buys.append(it)
                continue
            ps, rule = st.pos.get(t), st.pending_exit.get(t)
            if ps is None:
                if t in st.plan or t in busy:
                    later(it, "今天开盘刚买，账本明天早上才记上")
                else:
                    no(it, "执行器的账本里没有这只持仓（已经卖掉了？）")
                continue
            if rule == "manual":
                no(it, "已经在卖出全部，不用再点")
                continue
            if rule:
                no(it, f"规则也要卖出全部（{rule}），按规则的单卖", status="superseded")
                if kind == "sell":
                    man._set_block(t, int(it.get("block_days", MO.BLOCK_DEFAULT)), decided, it["id"])
                continue
            if t in busy or t in man.m["trims"] or t in man.m["adds"]:
                later(it, "这只今天已经有执行器的单")
                continue
            p = px.get(t)
            if not p:
                retry(it, f"取不到现价，{MO.RETRY_S // 60} 分钟后再试")
                continue
            cur, lot = int(ps.shares), lot_of(t)
            if kind == "sell":
                target = 0
            elif kind == "trim":
                target = int(math.floor(eq * float(it["pct"]) / 100 / p / lot)) * lot
            else:
                target = MO.target_shares(it["unit"], it["value"], eq, p, lot)
                if target == cur:
                    no(it, f"现在 {cur:,} 股，目标 {MO.fmt_target(it)} 换算也是 {target:,} 股：不用调")
                    continue
                if target > cur:
                    buys.append(it)
                    continue
            n = cur - max(0, target)
            if n <= 0:
                no(it, f"现在 {cur:,} 股约占权益 {cur * p / eq * 100:.1f}%，不高于目标：不用减")
                continue
            if held is not None and held.get(t, 0) < cur:
                later(it, f"立花那边 {t} 只有 {held.get(t, 0):,} 股（账本 {cur:,} 股）")
                continue
            full = target <= 0
            if full:
                st.pending_exit[t] = "manual"                 # 没成交 → 第二天早上的对账照常「仍是待卖」→ 下一开盘再卖
            else:
                man.m["trims"][t] = {"id": it["id"], "shares": int(n), "target": int(target), "decided_on": d, "now": True}
            o = ExecOrder(f"U{d}-SELL-{t}-{tag}", t, "SELL", "stock", n, d, ref_px=p,
                          reason="manual" if full else "manual_trim", phase="now")
            if self.paper:
                b.set_prices({t: p})
            self.orders.append(o)
            self._send(o, n, bar="")
            notes = [] if full else [f"{cur:,} → {target:,} 股"]
            if sent(o, it, "卖出", n, notes):
                if full and kind == "sell":
                    man._set_block(t, int(it.get("block_days", MO.BLOCK_DEFAULT)), decided, it["id"])
            elif full:
                st.pending_exit.pop(t, None)
            else:
                man.m["trims"].pop(t, None)
        core_done, core_wait, core_retry = [], [], []
        core_today = {o.ticker for o in self._active() if o.reason == "manual_core" and not self._unsent_now(o)}   # 今天已经照比例调过一次的 ETF

        def core_side(side: str) -> None:
            """闲置资金比例改了：核心 ETF 照新比例调（卖在个股买入之前、买在个股买入之后；目标 = 规则目标（比例 100%）× 新比例）。"""
            for t, (cur, tgt) in core_moves.items():
                if (tgt < cur) != (side == "SELL"):                 # 卖的在卖的那一轮、买的（和今天已经有单的）在买的那一轮
                    continue
                if t in core_today:
                    core_wait.append(f"{t} 今天已经调过一次")
                    continue
                if t in busy:
                    core_wait.append(f"{t} 今天已经有执行器的单")
                    continue
                p = px.get(t)
                if not p:
                    core_retry.append(f"{t} 取不到现价")
                    continue
                lt = lot_of(t)
                if side == "SELL":
                    n = cur - tgt if held is None else min(cur - tgt, held.get(t, 0))
                    if n <= 0:
                        core_wait.append(f"{t} 立花那边没有这么多口")
                        continue
                    o = ExecOrder(f"U{d}-SELL-{t}-{tag}", t, "SELL", "core", n, d, ref_px=p, reason="manual_core", phase="now")
                else:
                    gw = eng.core_gate_fn(t) if eng.core_gate_fn is not None else None
                    if gw:
                        core_done.append(f"{t} 不买（{gw}）：那份留现金")
                        continue
                    lim = round_to_tick(p * (1 + NOW_BUY_BUF), t, "BUY", lot=lt)     # 一手 1 口的 ETF：2027-03-01 起用 O 表
                    unit_px = p * (1 + float(eng.c_slip[t])) if self.paper else lim
                    fee = eng.c_fee[t]["BUY"]
                    n, avail = tgt - cur, cash_now()
                    while n > 0 and n * unit_px + fee(n * unit_px) > avail:
                        n -= lt
                    if n <= 0:
                        core_done.append(f"{t} 现金不够 1 个单元：没买")
                        continue
                    o = ExecOrder(f"U{d}-BUY-{t}-{tag}", t, "BUY", "core", n, d, limit=lim, ref_px=p, reason="manual_core",
                                  phase="now")
                if self.paper:
                    b.set_prices({t: p})
                self.orders.append(o)
                self._send(o, n, bar="")
                busy.add(t)
                what, q = ("卖出" if side == "SELL" else "买入"), int(o.filled_qty or 0)
                if o.status in UNKNOWN:
                    core_done.append(f"盘中{what} {t} {n:,} 口：下单结果不明，请在立花的注文一覧确认")
                elif o.status in ACCEPTED:
                    core_done.append(f"盘中{what} {t} {n:,} 口 @ ¥{float(o.filled_px):,.2f}" if q >= n else
                                     f"盘中{what} {t}：成交 {q:,} / {n:,} 口，其余挂着（今天有效）" if q > 0 else
                                     f"盘中{what} {t} {n:,} 口：已下单，等成交（今天有效）")
                elif o.status == "BLOCKED" and str(o.note).startswith(NO_QUOTE):
                    o.status, o.note = "SKIPPED", f"{o.note}：{MO.RETRY_S // 60} 分钟后再试（下一次是新的一笔）"
                    core_retry.append(f"{t} 取不到现价")
                elif o.status == "BLOCKED":
                    core_wait.append(f"{t} 没下（{o.note or '被挡'}）")
                elif o.status == "EXPIRED":
                    core_done.append(f"盘中{what} {t}：成交 {q:,} / {n:,} 口，其余已失效（{o.note}）" if q > 0 else
                                     f"{t} 下了单，但在立花那边已失效、没成交：{o.note}")
                else:
                    core_done.append(f"{t} 立花没受理：{o.note or o.status}")
        core_side("SELL")                                     # 比例调低：先卖核心，腾出的现金个股买入也能用
        n_used = (len(st.pos) - sum(1 for x in st.pending_exit if x in st.pos) + sum(1 for x in st.plan if x not in st.pos)
                  + len({o.ticker for o in self._active() if o.phase == "now" and o.reason == "manual_buy"
                         and (o.status in ACCEPTED or o.status in UNKNOWN)}))
        for it in buys:                                       # ② 买：买入 / 调仓往上
            t, add = it["ticker"], it["kind"] == "adjust"
            ps, j = st.pos.get(t), eng.col.get(t)
            if not add and t in eng.core_set:
                no(it, "核心 ETF 不能手动买（用「闲置资金比例」调）")
            elif not add and ps is not None:
                no(it, "已经持有：要加仓用「调仓」")
            elif not add and t in st.plan:
                no(it, "已经排在今天开盘买入（规则的信号）：不用再点")
            elif t in busy:
                later(it, "这只今天已经有执行器的单")
            elif j is None or not eng.A.has[k, j]:
                no(it, f"没有 {t} 在 {d} 的行情（不在股票池？停牌？）：不买")
            elif MO.entry_why(eng, t, k):
                no(it, f"{'不加仓' if add else '不买'}：{MO.entry_why(eng, t, k)}")
            elif not add and n_used >= cfg.max_positions:
                no(it, f"个股名额已满（上限 {cfg.max_positions} 只）：要买先卖出一只")
            elif not px.get(t):
                retry(it, f"取不到现价，{MO.RETRY_S // 60} 分钟后再试")
            if it["status"] != "pending" or it.get("tried") == stamp:
                continue
            p, c, lot = px[t], float(eng._px_close(t, k)), lot_of(t)
            top = round_to_tick(c * (1 + gap / 100), t, "BUY")
            if p > top:
                no(it, f"现价 ¥{p:,g} 比 {d} 收盘 ¥{c:,g} 高 {p / c - 1:+.1%}，超过 {gap:g}%：不买（与开盘买入同一个上限；只做一次）")
                continue
            cap_pct = float(cfg.max_position_pct) * 100
            cap = int(math.floor(eq * float(cfg.max_position_pct) / p / lot + 1e-9)) * lot
            notes = []
            if add:
                cur = int(ps.shares)
                want = MO.target_shares(it["unit"], it["value"], eq, p, lot)
                if want > cap:
                    notes.append(f"截到单只上限 {cap_pct:g}%")
                qty = (min(want, cap) - cur) // lot * lot
                if qty <= 0:
                    no(it, f"现在 {cur:,} 股：{MO.cap_text(cur, p, eq, cap_pct, lot)}")
                    continue
            else:
                qty, basis = MO.buy_size(eng, it, eq, p, lot, float(eng._entry_mult(t, k)))
                if qty > cap:
                    notes.append(f"截到单只上限 {cap_pct:g}%")
                    qty = cap
                if qty <= 0:
                    no(it, f"{basis}不够买 1 个单元（{lot:,} 股 ≈ ¥{lot * p:,.0f}）：不买")
                    continue
            lim = top if self.paper else min(top, round_to_tick(p * (1 + NOW_BUY_BUF), t, "BUY"))
            unit_px = p * (1 + float(eng.slip["JP"])) if self.paper else lim     # 模拟账户按现价 + 滑点成交；实盘按限价占余力
            fee = eng.fees["JP"]

            def need(q: int) -> float:
                return q * unit_px + fee(q * unit_px)
            avail = cash_now()
            if need(qty) > avail:                             # 卖核心补：按缓冲之前的金额算（卖出所得也要先扣缓冲）
                notes += fund((need(qty) - avail) / max(1e-9, 1 - float(cfg.cash_buffer_pct) / 100))
                avail = cash_now()
            q0 = qty
            while qty > 0 and need(qty) > avail:
                qty -= lot
            if 0 < qty < q0:
                notes.append(f"现金只够 {qty:,} 股")
            if qty <= 0:
                no(it, f"现金 + 核心 ETF 不够买 1 个单元：不{'加' if add else '买'}")
                continue
            o = ExecOrder(f"U{d}-BUY-{t}-{tag}", t, "BUY", "stock", qty, d, limit=lim, ref_px=c,
                          reason="manual_add" if add else "manual_buy", phase="now")
            g = self._gate_buy(o)
            if g:
                no(it, f"不买：{g}")
                continue
            key = "adds" if add else "buys"
            man.m[key][t] = {"id": it["id"], "shares": int(qty), "decided_on": d, "limit": lim, "now": True}
            if add:
                man.m[key][t]["target"] = int(ps.shares) + int(qty)
            if self.paper:
                b.set_prices({t: p})
            self.orders.append(o)
            self._send(o, qty, bar="")
            if not add and not bool(eng.A.entry[k, j]):
                notes.append("★ 没有买入信号：是你自己的决定")
            if sent(o, it, "加仓买入" if add else "买入", qty, notes):
                n_used += not add
            else:
                man.m[key].pop(t, None)
        core_side("BUY")                                      # 比例调高：个股买完再用剩下的现金买核心
        for it in todo:
            lvl = "warn" if it["status"] == "rejected" else "info"
            self._event(lvl, f"手动指令 {it['id']}：{it['ticker']} {MO.status_text(it)}：{it.get('msg') or ''}")
        out["items"] = [{"id": it["id"], "ticker": it["ticker"], "status": MO.status_text(it), "msg": it.get("msg") or ""}
                        for it in todo]
        if core_want is not None:                             # 闲置资金比例：记下调到哪了（没调完的 → 一会儿再试 / 下一次决策照新比例）
            if core_retry:
                cr["tried"] = stamp
                cs, cm = "等", "；".join(core_done + core_retry) + f"：{MO.RETRY_S // 60} 分钟后再试"
                out["retry"] += 1
            elif core_wait:
                cr["defer"] = today.isoformat()
                cs, cm = "明天开盘", "；".join(core_done + core_wait) + " → 下一次决策照新比例调（明天开盘）"
                out["later"] += 1
            else:
                cr["applied"] = core_want
                cr.pop("tried", None)
                cs, cm = ("盘中已调" if core_done else "完成"), "；".join(core_done) or "现在的口数已经是新比例的目标"
            lab = "停买闲置资金 ETF（比例 0%）" if core_want <= 0 else f"闲置资金比例设为 {core_want:g}%"
            if core_it is not None:
                core_it["msg"] = f"{lab}：{cm}"
            self._event("info", f"{lab}：{cm}")
            out["items"].append({"id": (core_it or {}).get("id", "core"), "ticker": f"闲置资金比例 {core_want:g}%", "status": cs,
                                 "msg": cm})
        self.save()
        return out

    # ── 撤单 / 状态不明的单的候选（qbreak/live_ops.py；缺口盘点 B1 / B2）──
    def cancel_orders(self, cids: list[str] | None = None, source: str = "") -> dict:
        """撤执行器自己今天的、还挂着的单（SENT / PARTIAL；立花：有注文番号）。cids=None → 全部这种单。撤完用 order_status 再确认 →
        CANCELLED + 撤单时的成交股数（第二天早上照实际成交对账）；已经全部成交的不改、说明。模拟账户：只撤还在排队、开盘之前的寄付单。
        HALT 时也可以撤（撤单只会减少风险）。改账本之前先备份。返回 qbreak/live_ops.cancel_core 的结果。"""
        from .live_ops import cancel_core
        if self.persist:
            from .book_backup import backup
            backup(self.path, force=True)
        res = cancel_core(self.orders, self.book, lambda: self.b, cids, paper=self.paper, now=self.clock(), source=source)
        for lvl, msg in res["events"]:
            self._event(lvl, msg)
        self.save()
        return res

    def unknown_candidates(self) -> list[dict]:
        """当前决策里状态不明的单（SENDING / ERROR）在券商注文一覧里的候选（只读；qbreak/live_ops.unknown_candidates）。
        没有状态不明的单 → []（不连券商）；模拟账户 / 没有注文一覧的券商 → []。"""
        from .live_ops import unknown_candidates
        unk = [o for o in self._active() if o.status in UNKNOWN]
        if not unk or self.paper or not hasattr(self.b, "open_orders"):
            return []
        return unknown_candidates(unk, self.orders, self.b, today=self.clock().date())

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
            for o in self._active():                          # 盘中的手动单：模拟账户当场成交，成交记在单上（那个进程的 _fills 已经没了）
                if o.phase == "now" and o.cid not in f and o.status in ("FILLED", "PARTIAL") and o.filled_qty > 0:
                    f[o.cid] = (int(o.filled_qty), float(o.filled_px))
            return f
        out = {}
        for o in self._active():
            if o.status == "RESOLVED":
                out[o.cid] = (int(o.filled_qty), float(o.filled_px))
            elif (o.status in ACCEPTED or o.status in ("EXPIRED", "CANCELLED")) and o.broker_id:   # 已失效 / 撤掉的单也可能成交过一部分
                try:
                    r = self.b.order_status(o.broker_id, o.order_date)
                except Exception as e:                      # noqa: BLE001
                    raise ExecutorError(f"查不到 {o.side} {o.ticker}（注文番号 {o.broker_id}）的成交：{e}；"
                                        "状态没有改动，稍后重跑") from None
                out[o.cid] = (int(r["filled_qty"]), float(r["avg_px"]))
                fin = r.get("final") or ""
                if fin in ("REJECTED", "EXPIRED", "CANCELLED") and int(r["filled_qty"]) < int(o.sent_qty or o.qty):
                    names = getattr(getattr(self.b, "spec", None), "status_names", None) or {}   # 终态：立花的状态名称记进 note
                    o.note = f"立花：{r.get('status') or names.get(str(r.get('status_code')), '') or fin}（sOrderStatusCode={r.get('status_code')}）"
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
            elif o.status in ("EXPIRED", "CANCELLED") and q >= (o.sent_qty or o.qty) > 0:   # 撤单之前已经全部成交
                o.status = "FILLED"
            elif o.status == "DEFERRED":                     # 开盘后的补单没有跑（09:05 的 --phase open）→ 这笔没买，与模型不同
                why_ = (str(o.note) if str(o.note).startswith((QUOTE_FAIL, NO_OPEN_WAIT))   # 跑了但没下成（取价失败 / 一直没寄り付き）
                        else "开盘后补单没有运行（--phase open）")
                o.status, o.note = "MISSED", f"{why_}，没买 —— 与模拟盘出现差异"
                self.stats["model_diff"] += not self.paper
                self._event("error", f"BUY {o.ticker} ×{o.qty}：{o.note}")
            if q <= 0:
                if o.reason in ("manual_add", "manual_buy") and self.manual is not None:   # 手动加仓 / 买入只做一次：没买成 → 指令结束
                    self.manual.on_fill(o.ticker, o.reason, 0, 0.0, str(eng.gidx[k].date()), st,
                                        why=o.note or o.status)
                lapsed = (o.status in ("UNFILLED", "CANCELLED")                # 你撤了单 = 没成交（同一处理）
                          or (o.status == "EXPIRED" and o.phase != "now"))      # 盘中手动单失效：当场已经处理（同 REJECTED）
                if o.side == "SELL" and lapsed:
                    self.stats["unfilled_sell"] += 1
                    again = self.manual is None or o.reason not in ("manual", "manual_trim") or self._manual_wanted(o)
                    self._event("warn", f"SELL {o.ticker} 没成交（{o.note or '寄付で約定せず'}）→ "
                                        + ("仍是待卖，今天再下" if again else "手动指令已撤回，不再下"))
                    if self.manual is not None and o.reason in ("manual", "manual_trim"):
                        self.manual.on_fill(o.ticker, o.reason, 0, 0.0, str(eng.gidx[k].date()), st)
                elif o.side == "BUY" and lapsed:
                    self.stats["unfilled_buy"] += 1
                    j = eng.col.get(o.ticker)
                    op = float(eng.A.open[k, j]) if j is not None and eng.A.has[k, j] else None
                    would = op is not None and (o.kind == "core" or not gap or op <= o.ref_px * (1 + gap / 100))
                    if not self.paper and o.phase != "now" and would and eng._locked(k, j) != "up":   # 模拟账户就是模型本身；盘中的手动单不比
                        self.stats["model_diff"] += 1
                        self.diffs.append({"bar": str(eng.gidx[k].date()), "ticker": o.ticker, "kind": o.kind,
                                           "phase": o.phase, "open": op, "limit": o.limit, "ref_px": o.ref_px})
                        self._event("warn", f"BUY {o.ticker} " + ("你撤了单（没成交），" if o.status == "CANCELLED" else "没成交，")
                                    + f"但模型会买（开盘 {op:g}，限价 {o.limit:g}）→ 与模拟盘出现差异")
                continue
            self.stats["fills"] += 1
            if o.side == "SELL" and o.kind == "stock":
                ps = st.pos.get(o.ticker)
                if ps is None:
                    self._event("error", f"SELL {o.ticker} 成交 {q} 股，但状态里没有这只持仓")
                    continue
                full = q >= ps.shares
                if o.reason == "manual_trim":                 # 手动减仓：只卖一部分，剩下的照常持有（不是待卖）
                    eng.sell_fill(o.ticker, min(int(q), ps.shares), px, k, "manual_trim", part_note="")
                    if full:
                        st.pending_exit.pop(o.ticker, None)
                else:
                    why = st.pending_exit.get(o.ticker) or o.reason or "exit"
                    eng.sell_fill(o.ticker, min(int(q), ps.shares), px, k, why)
                    if full:
                        st.pending_exit.pop(o.ticker, None)
                    else:
                        rest = int(st.pos[o.ticker].shares) if o.ticker in st.pos else 0   # sell_fill 之后剩下的
                        oddn = int(((self.book.get("odd_lots") or {}).get(o.ticker) or {}).get("shares") or 0)
                        self._event("warn", f"SELL {o.ticker} 部分成交 {q}/{q + rest} 股 → 剩下的仍是待卖"
                                    + (f"（剩下 {rest:,} 股不足一手：在立花网站卖）" if oddn and rest == oddn else ""))
                if self.manual is not None and o.reason in ("manual", "manual_trim"):
                    self.manual.on_fill(o.ticker, o.reason, int(q), float(px), str(eng.gidx[k].date()), st)
            elif o.kind == "core":
                eng._core_trade(o.ticker, o.side, int(q), k, px=px)
            elif o.reason == "manual_add":                     # 手动加仓：并进原来的持仓（成本加权平均；止损 / 峰值不变）
                if o.ticker not in st.pos:
                    self._event("warn", f"BUY {o.ticker}（手动加仓）成交 {q} 股，但原来的持仓已经没了 → 按新仓记")
                eng.add_fill(o.ticker, int(q), px, k)
                if self.manual is not None:
                    self.manual.on_fill(o.ticker, "manual_add", int(q), float(px), str(eng.gidx[k].date()), st)
            else:
                if o.ticker in st.pos:
                    self._event("error", f"BUY {o.ticker} 成交，但状态里已有这只持仓（不重复记）")
                    continue
                eng._open(o.ticker, "JP", int(q), px, k)
                if o.reason == "manual_buy" and self.manual is not None:     # 手动买入：之后就是普通持仓（规则的止损 / 离场）
                    self.manual.on_fill(o.ticker, "manual_buy", int(q), float(px), str(eng.gidx[k].date()), st)
            self._reconciled.append({"bar": str(eng.gidx[k].date()), "side": o.side, "ticker": o.ticker,
                                     "qty": int(q), "px": round(float(px), 4), "kind": o.kind, "reason": o.reason})
        mc: dict[str, list[ExecOrder]] = {}
        for o in act:
            if o.reason == "manual_core":
                mc.setdefault(o.ticker, []).append(o)
        for t, os_ in mc.items():                           # 盘中照新比例的单（按票看）：到了交易所的都成交完了吗
            sent = [o for o in os_ if not self._unsent_now(o)]   # 那一刻取不到现价没发出、之后重下成交了的 → 不算没成交
            if self.book.get("core_rule") and (not sent or any(o.filled_qty < (o.sent_qty or o.qty) for o in sent)):
                self.book["core_rule"]["redo"] = True         # 没成交完 / 一笔都没到交易所 → 这次决策核心 ETF 直接调到目标（不看再平衡带）
        cr = self.book.get("core_rule") or {}
        if cr.get("exact_on") and cr["exact_on"] == st.last_date:   # 照新比例直接调的那次决策：核心 ETF 的单都成交了吗
            done = {o.ticker for o in act if o.kind == "core" and o.filled_qty >= (o.sent_qty or o.qty) > 0}
            if set(cr.get("exact_plan") or []) - done:
                cr["redo"] = True                             # HALT / 没成交 / 没下 → 这次决策再照比例调（不看再平衡带）
        for t in list(st.pending_exit):
            if t not in st.pos:
                st.pending_exit.pop(t)
        if self.book.get("odd_lots"):
            self._odd_cleanup()
        st.plan.clear()
        st.core_plan.clear()
        st.add_plan.clear()
        if act:
            self.book.setdefault("history", []).append({"fill_bar": str(eng.gidx[k].date()),
                                                        "orders": [asdict(o) for o in act]})
        self.orders = [o for o in self.orders if o not in act]
        if self.manual is not None:                         # 撤回中的手动指令：这时候已经没有在途的单 → 撤；持仓没了的 → 完成
            for lvl, msg in self.manual.settle(st, set()):
                self._event(lvl, msg)

    def _position_diff(self) -> tuple[list[str], list[str]]:
        """券商持仓 vs 状态持仓（执行器管的票：状态里的持仓、核心 ETF、股票池里的票）→（不一致的文字，执行器不管的持仓的文字）。
        刚拆股、券商还没反映的不算不一致（记一条 warn）。"""
        eng, st = self.eng, self.eng.st
        self._last_held = self.b.positions()
        held = {t: int(p.qty) for t, p in self._last_held.items() if int(p.qty) > 0}
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
        return bad, [f"{t} {held[t]:,} 股" for t in sorted(set(held) - managed)]

    def _block_mismatch(self, bad: list[str]) -> None:
        """不一致 → 这次不下单，并记进账本 broker_mismatch（LU-21：同一天的盘中 / 开盘后 / 晚到的早上运行照样挡住）；
        一致 → 清掉（下一次早上核对一致之后才恢复）。"""
        if bad:
            txt = "持仓与券商不一致：" + "；".join(bad) + "（人工交易？状态不明的单？公司行为？）请核对后再跑"
            now = self.clock()
            self.book["broker_mismatch"] = {"date": now.date().isoformat(), "at": now.isoformat(timespec="seconds"), "text": txt}
            self.block(txt)
        else:
            self.book.pop("broker_mismatch", None)

    def check_positions(self) -> None:
        """只核对持仓（同一决策补单之前：08:35 的重试是新进程，07:40 的不一致不会带过来）。不同步现金：
        开盘前已经发出的买单占着买付可能額，这时候再同步会把现金算错。执行器不管的持仓 07:40 已经提醒过，这里不再提。"""
        self._block_mismatch(self._position_diff()[0])

    def check_broker(self, k: int | None = None) -> None:
        """券商持仓 = 状态持仓？不一致 → 这次不下单（_position_diff）。
        现金：买付可能額 − 状态现金 ≥ 1 円 → 记下；实盘以券商为准（税、实际手续费、分红入账）。
        实盘账本的第一次现金同步（还没有任何一天的权益记录，B11）：买付可能額（+ 已有持仓按第 k 天收盘的市值）就是起始本金
        （账本 capital_jpy；收益与页面「起始」用它，不用 sim.json 的 capital），这一次不提醒「现金突然变化」。"""
        st, b = self.eng.st, self.b
        bad, foreign = self._position_diff()
        if foreign:
            self._event("warn", "账户里有执行器不管的持仓（不影响下单）：" + "、".join(foreign))
        self._block_mismatch(bad)
        cash = float(b.cash())
        if not self.paper:                                     # UX-07：「立花那边实际是什么」快照（持仓 + 余力；只展示）
            try:
                from . import broker_snapshot as BS
                BS.record_check(Path(self.path).stem.replace("live_unified_", "", 1), getattr(self, "_last_held", {}) or {},
                                cash, {"state": st.to_dict()})
            except Exception as e:                             # noqa: BLE001  快照只是展示
                log.warning("立花快照没写成（不影响运行）：%s", e)
        if (self.sync_cash and not self.paper and "capital_jpy" not in self.book
                and not any(float(h[1] or 0) > 0 for h in st.history or [])):
            self._start_capital(cash, k)                   # 还没入金（买付可能額 0、没有持仓）→ 起始本金等第一次有钱的核对再定
            return
        drift = cash - st.cash_jpy
        if abs(drift) >= 1.0:
            tax = self._tax_pending() if self.sync_cash else 0.0
            why, lvl = self._drift_why(drift, tax)
            self._event(lvl if self.sync_cash else "error",
                        f"现金差 {drift:+,.0f} 円（券商买付可能額 {cash:,.0f} / 模型 {st.cash_jpy:,.0f}）"
                        + ("→ 以券商为准" if self.sync_cash else "") + (f"：{why}" if why and self.sync_cash else ""))
            self.book.setdefault("cash_drift", []).append([st.last_date, round(drift, 2)])
            self.book["cash_drift"] = self.book["cash_drift"][-250:]
            if self.sync_cash:
                self._match_flows(drift, tax)
                if abs(tax) >= 100 and abs(drift + tax) <= max(1_000.0, 0.15 * abs(tax)):
                    self._tax_seen()                           # 这次的现金差就是这笔税：记下，之后的早上不再拿它解释
                st.cash_jpy = cash
                self.stats["cash_sync"] += 1

    def _reserve_now(self) -> float:
        """这次决策要预留的出金（円）：登记了预留、还没到账的出金合计；登记超过 RESERVE_DAYS 天还没对上到账 → 解除（记 released）并提醒。"""
        today = self.clock().date()
        for f in reserves(self.book):
            try:
                age = (today - dt.date.fromisoformat(str(f.get("date"))[:10])).days
            except ValueError:
                age = 0
            if age > RESERVE_DAYS:
                f["reserve_released"] = today.isoformat()
                self._event("warn", f"出金预留 {f['jpy']:+,.0f} 円（{f.get('date')} 登记）{RESERVE_DAYS} 天还没对上到账 → 解除预留"
                                    "（金额写错？已经到账但金额不同？在 Mac 对话里说一声；需要的话重新登记）")
        hold = reserve_jpy(self.book)
        if hold > 0:
            self._event("info", f"出金预留 ¥{hold:,.0f}：这次决策按扣掉它的现金 / 权益算（个股仓位相应变小、闲置资金 ETF 不买回；"
                                "现金不够照规则先卖核心 ETF）；出金到账后自动解除")
        return hold

    def _tax_now(self) -> tuple[str, float]:
        """（今年，到今天为止的预计累计代扣）。"""
        from .tax_ytd import ytd
        today = self.clock().date()
        return str(today.year), float(ytd(self.eng.st, today.year, upto=today.isoformat())["withheld"])

    def _tax_pending(self) -> float:
        """还没在现金差里见到的预计譲渡益税变化（円；正 = 多扣、负 = 还付）= 今年的预计累计代扣 − 账本记下的「已经见到的」
        （账本 tax_seen：{year, w, since}）。模型现金不扣税 → 券商现金比模型少约这么多；见到一次之后就不再算（模型现金同步成券商的）。
        挂了 7 天还没见到（例如券商不在约定日 / 受渡日扣、或算法与券商不同）→ 当作已经见到，不再拿来解释（只影响提醒的文字）。"""
        try:
            year, w = self._tax_now()
        except Exception:                                      # noqa: BLE001
            return 0.0
        seen = self.book.get("tax_seen") or {}
        w0 = float(seen.get("w") or 0) if str(seen.get("year")) == year else 0.0
        pend = w - w0
        if abs(pend) < 1:
            return 0.0
        since = str(seen.get("pending_since") or "") if str(seen.get("year")) == year else ""
        today = self.clock().date()
        if not since:
            self.book["tax_seen"] = {"year": year, "w": w0, "pending_since": today.isoformat()}
        elif (today - dt.date.fromisoformat(since)).days > 7:
            self._tax_seen()
            return 0.0
        return pend

    def _tax_seen(self) -> None:
        try:
            year, w = self._tax_now()
        except Exception:                                      # noqa: BLE001
            return
        self.book["tax_seen"] = {"year": year, "w": round(w, 2)}

    @staticmethod
    def _drift_why(drift: float, tax: float) -> tuple[str, str]:
        """UX-08 / T3：现金差能不能解释 →（说明，级别）。≈ −预计代扣 → 譲渡益税（info）；< ¥1,000 → 手续费 / 取整 / 利息（info）；
        其他 → warn（入出金 / 分红到账 / 别的）。只影响提醒的级别与文字，现金照旧以券商为准。"""
        if abs(tax) >= 100 and abs(drift + tax) <= max(1_000.0, 0.15 * abs(tax)):
            return (f"≈ 预计{'譲渡益税代扣' if tax > 0 else '譲渡益税还付'} ¥{abs(tax):,.0f}（模型不扣税；以取引報告書为准）", "info")
        if abs(drift) < 1_000:
            return "小额差（手续费 / 取整 / 利息等）", "info"
        pre = f"其中预计譲渡益税{'代扣' if tax > 0 else '还付'} ¥{abs(tax):,.0f}，其余 {drift + tax:+,.0f} 円" if abs(tax) >= 100 else ""
        return (pre + "：" if pre else "") + "可能是入出金、分红到账或费用差", "warn"

    def _start_capital(self, cash: float, k: int | None) -> None:
        """B11：实盘账本第一次核对 → 起始本金 = 券商的买付可能額 + 已有持仓的市值；之前登记的入出金算进起始本金（不再另加）。"""
        st = self.eng.st
        old = float(st.cash_jpy)
        st.cash_jpy = cash
        cap = float(self.eng.equity(k)) if k is not None else cash
        if not math.isfinite(cap) or cap <= 0:
            cap = cash
        if cap <= 0:                                           # 账户里还没有钱（先装好任务、后入金）：不定起始本金（不记 0），现金照券商
            if not self.book.get("live_start_wait"):
                self._event("info", "实盘账本第一次核对：买付可能額 ¥0、没有持仓 → 起始本金等入金后第一次核对再定（之后的入金不用登记）")
            self.book["live_start_wait"] = self.clock().date().isoformat()
            return
        self.book.pop("live_start_wait", None)
        self.book["capital_jpy"] = round(cap, 2)
        self.book["live_start"] = {"date": self.clock().date().isoformat(), "cash_jpy": round(cash, 2), "capital_jpy": round(cap, 2)}
        pre = [f for f in flows(self.book) if not f.get("seen_after")]
        for f in pre:
            f["in_start"] = True                               # 第一次核对之前登记的入金已经在买付可能額里：不再加进投入本金
        self._event("info", f"起始本金 ¥{cap:,.0f}：实盘账本第一次核对，按券商的买付可能額 ¥{cash:,.0f}"
                            + (f" + 持仓市值 ¥{cap - cash:,.0f}" if abs(cap - cash) >= 1 else "")
                            + f" 开始（sim.json 的 ¥{old:,.0f} 只是模拟盘的本金）"
                            + (f"；之前登记的入出金 {sum(float(f.get('jpy') or 0) for f in pre):+,.0f} 円算进起始本金" if pre else ""))

    def _match_flows(self, drift: float, tax: float = 0.0) -> None:
        """实盘的现金差里有没有入金 / 出金（run.py live-u --flow 登记）：还没到账的登记（合计，或其中一笔）≈ 这次的现金差 → 记下
        「在哪个决策日之后到账」（seen_after；收益计算按它扣掉）；对不上、而且现金突然变化很大（≥ ¥50,000 且 ≥ 权益 2%）→ 提醒。
        只影响收益的显示与提醒，不影响下单（仓位本来就按券商的买付可能額算）。"""
        pend = [f for f in flows(self.book) if not f.get("seen_after")]
        hit = match_flow(pend, drift)
        if not hit and abs(tax) >= 100:                   # 同一天还有譲渡益税：扣掉再对；对上了 = 这笔税也见到了
            hit = match_flow(pend, drift + tax)
            if hit:
                self._tax_seen()
        if hit:
            for f in hit:
                f["seen_after"] = self.eng.st.last_date or ""
            self._event("info", f"登记过的入出金 {sum(float(f['jpy']) for f in hit):+,.0f} 円已到账（收益计算里扣掉）")
            return
        hist = self.eng.st.history or []
        eq = float(hist[-1][1]) if hist else abs(float(self.eng.st.cash_jpy))
        rest = drift + tax                                     # T3：先扣掉预计的譲渡益税（代扣 / 还付），剩下的才拿去比对入出金
        if abs(rest) < max(50_000.0, 0.02 * eq):
            return
        if pend:
            self._event("warn", f"现金突然变化 {drift:+,.0f} 円，和登记过还没到账的入出金 "
                                f"{sum(float(f.get('jpy') or 0) for f in pend):+,.0f} 円对不上（金额写错？还没到账？）")
        else:
            self._event("warn", f"现金突然变化 {drift:+,.0f} 円"
                                + (f"（其中预计譲渡益税{'代扣' if tax > 0 else '还付'} ¥{abs(tax):,.0f}，不是入出金就不用登记）" if abs(tax) >= 100 else "")
                                + f"：如果是入金 / 出金，请登记（只影响收益的计算、不影响下单）："
                                f"bash scripts/liveu.sh flow {rest:+.0f} --broker tachibana")

    def on_corp_action(self, t: str, date: str, dividend: float, split: float, div_net: float) -> None:
        """公司行为同步：模拟券商的持仓 / 排队单，与执行器账本里还没成交的单（拆股：股数 ×k、价格 ÷k）。"""
        if self.paper and hasattr(self.b, "apply_corporate_action"):
            self.b.apply_corporate_action(t, date, dividend=dividend, split=split, div_net=div_net)
        k = float(split or 0)
        if k > 0 and abs(k - 1) > 1e-9:
            done = {s.get("cid") for s in self.book.get("split_pre") or []        # 成交日当天已经按拆股后下的单（LU-22）：不再调第二次
                    if s.get("ticker") == t and s.get("date") == date}
            for o in self.orders:
                if o.ticker == t and o.cid not in done:
                    o.qty = int(o.qty * k + 1e-6)
                    o.ref_px = o.ref_px / k
                    if o.limit:
                        o.limit = round_to_tick(o.limit / k, t, o.side,
                                                lot=int(self.eng.lots[self.eng.col[t]]) if t in self.eng.col else None)
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
                                + f"。请在立花的注文一覧确认，然后登记：{self.resolve_cmd()}（没成交填 0）")
        if corp is not None:
            corp(k)
        if self.paper:
            self._paper_open(k)
        self._reconcile(k, self._collect_fills())
        self.check_broker(k)
        if place and self.manual is not None:              # 手动卖出 / 减仓：收盘离场判断之后、统一决策之前变成单
            self.eng.pre_decide_fn = self._apply_manual
        exact = self._core_pending() is not None            # 改了闲置资金比例、还没照新比例调过 → 这次核心 ETF 直接调到目标
        self.eng.core_exact = exact
        self.eng.cash_hold = 0.0 if self.paper else self._reserve_now()   # 出金预留（〔77〕C LU-19）：到账前按扣掉它决策
        try:
            self.eng.close_phase(k)
        finally:
            self.eng.pre_decide_fn = None
            self.eng.core_exact = False
            self.eng.cash_hold = 0.0
        self._record_core(k, exact)
        if place:
            self.place(k)

    def morning(self, idxs: list[int], corp=None) -> None:
        """实盘 / 模拟账户的早上：处理新收盘的交易日（通常 1 天）。实盘只能给今天的开盘下单 → 只在最后一天下单；
        中间错过的开盘（执行器没运行）等于没成交。没有新交易日 → 只补下当前决策里还没下的单。"""
        eng = self.eng
        if self.manual is not None:                         # 页面 / 命令行写的新指令（闲置资金比例从这次决策起生效）
            for lvl, msg in self.manual.ingest():
                self._event(lvl, msg)
            eng.core_scale = self.manual.core_pct / 100
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
                # 08:35 的重试是新进程：07:40 的「持仓不一致」不会带过来 → 开盘前再查一次持仓，不能绕过。
                # 09:00 以后不查（今天的单可能已成交，券商持仓本来就和账本不同；寄付单 08:55 之后也被时间闸挡住）——
                # 但成交日之前（决策做好、成交日在后面的休市日 / 周末）整天都查：那几天不会有新成交，寄付单的时间闸也不挡；
                # 模拟账户第二天早上才撮合，不查；
                # 已经因为别的原因不下单（例如行情没更新：账本还停在前一天、券商已有昨天的成交）→ 不查，免得多一条误报的「不一致」
                now, f = self.clock(), self.fill_day()
                if not self.paper and not self.blocked and (now.time() < dt.time(9, 0) or (f is not None and now.date() < f)):
                    self.check_positions()
                if self.manual is not None:                 # 同一决策补单：撤回中的先处理，再把新的手动卖出 / 减仓加进这次的单（加仓等下一次决策）
                    self._settle_manual()
                    self._apply_manual(k, deciding=False)
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
                "odd_lots": dict(self.book.get("odd_lots") or {}), "incomplete": self.incomplete,
                "manual": self.manual.summary() if self.manual is not None else None,
                "events": (self.book.get("events") or [])[-30:] + self.events}


def resolve_order(path, cid: str, filled: int, px: float) -> dict:
    """人工确认状态不明的单（在立花的注文一覧 / 約定照会看过之后）：登记实际成交股数与均价（没成交填 0）。
    只改账本里这一笔，下次早上的对账按登记的成交记进状态。改之前先备份账本（qbreak/book_backup.py）。"""
    from .book_backup import backup
    backup(path)
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
EARLY_TEXT = "上线初期：实盘从空仓开始，持仓和模拟盘不同是预期的"


def compare_with_sim(st: UState, sim: UState | None, live: bool = False, manual: dict | None = None,
                     book: dict | None = None) -> dict:
    """执行器账户 vs 模拟盘账户：同一决策日时逐项比较（个股股数、1655 口数、现金、权益）；不是同一天就不比（例如云端当天还没入库）。
    live=True（立花实盘）：本金、税、实际手续费与成交价都和 ¥100 万的模拟盘不同，金额一定对不上 → 只比「拿的是不是同样的票」
    （个股与核心 ETF 的品种），金额与权益差只写出来、不算不一致。
    manual = 执行器的手动指令汇总（qbreak/manual_orders.py）：有手动操作时不一致的文字后面注明「是预期的」。
    book = 实盘账本（LU-12）：上线初期（还从没和模拟盘拿过同样的票）不同只是因为实盘从空仓开始 → early = True、文字写明是预期的，
    通知不升 warn（early_reason 判断；第一次拿的票相同之后照常）。"""
    out = {"exec_date": st.last_date, "sim_date": sim.last_date if sim else None, "comparable": False, "same": None}
    out = _compare(st, sim, live, out)
    if live and out.get("comparable") and not out.get("same"):
        why = early_reason(st, sim, book)
        if why is not None:
            out["early"] = True
            out["text"] = f"{EARLY_TEXT}（{why}）"
        else:
            rw = reserve_reason(st, sim, book)
            if rw is not None:                              # 出金预留：实盘少拿的票是钱少了造成的（预期的差异，不算不一致）
                out["explained"] = "出金预留"
                out["text"] = f"与云端模拟盘拿的票不同，是出金预留造成的（预期）：{rw}"
    from .manual_orders import active as manual_active
    if manual_active(manual) and out.get("comparable") and not out.get("same"):
        out["manual"] = True                                # 有手动操作：与云端不同是预期的（上线门槛的「连续一致」照常中断）
        out["text"] += "（有手动操作 —— 手动卖出 / 减仓 / 加仓 / 闲置资金比例 / 不买回 —— 与云端不同是预期的）"
    return out


def early_reason(st: UState, sim: UState | None, book: dict | None) -> str | None:
    """LU-12：立花实盘与模拟盘拿的票不同，是不是只因为「上线初期、实盘从空仓开始」→ 说明文字；不是 → None（照常算不一致）。
    都要满足：① 这个账本以前（今天之前）从没和模拟盘拿过同样的票（第一次相同之后照常）；② 实盘拿的票模拟盘都有（实盘多出来的 = 真的不同）；
    ③ 模拟盘有、实盘没有的个股都是实盘第一个决策日（history 的第一天）或更早买进的（上线前的持仓；之后的买卖实盘也照同一决策下单）；
    ④ 模拟盘有、实盘没有的核心 ETF 只在第一个决策日算预期（第一笔核心 ETF 的买单第二天开盘才成交）。"""
    if sim is None or book is None:                       # 没给账本（不知道以前比过没有）→ 不当上线初期
        return None
    if any(h.get("comparable") and h.get("same") and h.get("date") != st.last_date
           for h in book.get("compare_history") or []):
        return None
    names = lambda s: (set(s.pos), {t for t, u in s.core_units.items() if int(u)})      # noqa: E731
    (lp, lc), (sp, sc) = names(st), names(sim)
    if (lp - sp) or (lc - sc):
        return None
    first = str(st.history[0][0])[:10] if st.history else str(st.last_date or "")
    late = [t for t in sorted(sp - lp) if str(getattr(sim.pos[t], "entry_date", "") or "")[:10] > first]
    if late or ((sc - lc) and str(st.last_date) != first):
        return None
    parts = []
    if sp - lp:
        parts.append(f"模拟盘上线前就拿着、实盘没有的个股 {len(sp - lp)} 只：{'、'.join(sorted(sp - lp))}（模拟盘卖掉之后就一致）")
    if sc - lc:
        parts.append(f"核心 ETF {'、'.join(sorted(sc - lc))} 实盘第一笔明天开盘才成交")
    return "；".join(parts) or "实盘还没有持仓"


def reserve_reason(st: UState, sim: UState | None, book: dict | None, days: int = 5) -> str | None:
    """出金预留期间（或出金到账 / 预留解除后 days 天内）实盘与模拟盘拿的票不同，是不是只因为实盘的钱少了 → 说明文字；不是 → None。
    要满足：有预留中的出金（或刚结束的）；实盘拿的票模拟盘都有（实盘多出来的 = 真的不同），即实盘只是少拿了几只 / 少拿了核心 ETF。
    出金金额只在本机账本里（不进仓库）：模拟盘不知道，所以只能在这里把差异标成预期的。"""
    if sim is None or not book:
        return None
    active = reserves(book)
    recent = []
    if not active:
        try:
            today = dt.date.fromisoformat(str(st.last_date)[:10])
        except ValueError:
            return None
        for f in flows(book):
            if not f.get("reserve"):
                continue
            end = str(f.get("seen_after") or f.get("reserve_released") or "")[:10]
            try:
                if end and (today - dt.date.fromisoformat(end)).days <= days:
                    recent.append(f)
            except ValueError:
                continue
        if not recent:
            return None
    lp, lc = set(st.pos), {t for t, u in st.core_units.items() if int(u)}
    sp, sc = set(sim.pos), {t for t, u in sim.core_units.items() if int(u)}
    if (lp - sp) or (lc - sc):
        return None
    miss = sorted((sp - lp) | (sc - lc))
    amt = sum(-float(f.get("jpy") or 0) for f in (active or recent))
    return (f"{'预留中' if active else '刚出金'} ¥{amt:,.0f}，实盘少拿了 {'、'.join(miss) or '—'}"
            "（钱少了一手买不起 / 闲置资金 ETF 不买回）")


def compare_bad(cmp: dict | None) -> bool:
    """与云端比较的结果要不要算「不对」（通知升 warn）：能比、不一致、又不是上线初期（LU-12）/ 出金预留造成的（〔77〕C LU-19）。"""
    return bool(cmp and cmp.get("comparable") and not cmp.get("same") and not cmp.get("early") and not cmp.get("explained"))


def _compare(st: UState, sim: UState | None, live: bool, out: dict) -> dict:
    pos = lambda s: {t: int(p.shares) for t, p in s.pos.items()}                     # noqa: E731
    core = lambda s: {t: int(u) for t, u in s.core_units.items() if int(u)}          # noqa: E731
    eq = lambda s: float(s.history[-1][1]) if s.history else None                    # noqa: E731
    if sim is None or not sim.last_date or st.last_date != sim.last_date:
        out["text"] = (f"模拟盘停在 {(sim.last_date if sim else None) or '—'}、执行器在 {st.last_date or '—'}："
                       "不是同一天，这次不比（云端当天的例行任务可能还没入库）")
        return out
    diff = eq(st) - eq(sim) if eq(st) is not None and eq(sim) is not None else None
    if live:
        a, b = (sorted(pos(st)), sorted(core(st))), (sorted(pos(sim)), sorted(core(sim)))
        same = a == b
        out.update(comparable=True, same=same, equity_diff_jpy=diff, mode="holdings")
        if same:
            out["text"] = "与云端模拟盘拿的是同样的票（个股、核心 ETF 的品种；金额按各自的本金，不比）"
        else:
            parts = []
            if a[0] != b[0]:
                parts.append(f"个股 {'、'.join(a[0]) or '无'} vs 模拟盘 {'、'.join(b[0]) or '无'}")
            if a[1] != b[1]:
                parts.append(f"核心 ETF {'、'.join(a[1]) or '无'} vs 模拟盘 {'、'.join(b[1]) or '无'}")
            out["text"] = "★ 与云端模拟盘拿的票不同：" + "；".join(parts) + "（看日志：没成交 / 被挡 / 人工交易？）"
        return out
    same = pos(st) == pos(sim) and core(st) == core(sim) and abs(st.cash_jpy - sim.cash_jpy) < 1.0
    out.update(comparable=True, same=same, equity_diff_jpy=diff)
    if same:
        out["text"] = "与云端模拟盘一致（个股、核心 ETF、现金、权益）"
    else:
        parts = []
        if pos(st) != pos(sim):
            parts.append(f"个股 {pos(st) or '无'} vs {pos(sim) or '无'}")
        if core(st) != core(sim):
            parts.append(f"核心 ETF {core(st) or '无'} vs {core(sim) or '无'}")
        parts.append(f"现金差 {st.cash_jpy - sim.cash_jpy:+,.0f} 円")
        if diff is not None:
            parts.append(f"权益差 {diff:+,.0f} 円")
        out["text"] = "★ 与云端模拟盘不一致：" + "；".join(parts)
    return out


def _qty_txt(o: dict) -> str:
    return f"{int(o.get('sent_qty') or o['qty']):,} {'口' if o.get('kind') == 'core' else '股'}"


def ic_text(ic: dict | None) -> str:
    """闲置资金一句话：现在拿什么 + 读数（K2〜K4：月末收盘 vs 10 个月均线；K6：12 个月涨跌）。"""
    ic = ic or {}
    t = str(ic.get("text") or "—")
    if ic.get("sma") is not None and ic.get("close") is not None:
        t += (f"（{ic.get('month_end')} 月末收盘 ¥{float(ic['close']):,.2f} {'>' if float(ic['close']) > float(ic['sma']) else '≤'} "
              f"{ic.get('months', 10)} 个月均线 ¥{float(ic['sma']):,.2f}）")
    elif ic.get("ret12"):
        t += "（12 个月：" + "、".join(f"{k} {float(v):+.1f}%" for k, v in ic["ret12"].items()) + "）"
    fh = ic.get("fx_hedge")
    if fh:                                                  # FJE 日元走强判定（Q1H；qbreak/fx_hedge.py）
        src = str(fh.get("source") or "")
        t += f"（日元走强判定：{fh.get('text') or '—'}" + ("" if src == "云端" else f"；★ {src}") + "）"
        if fh.get("errors"):
            t += "；★ " + "；".join(f"{k}：{v}" for k, v in fh["errors"].items())
    br = ic.get("bond_refuge")
    if br:                                                  # BCU 股债相关判定（Q1HB；qbreak/bond_refuge.py）
        src = str(br.get("source") or "")
        t += f"（股债相关判定：{br.get('text') or '—'}" + ("" if src == "云端" else f"；★ {src}") + "）"
        if br.get("errors"):
            t += "；★ " + "；".join(f"{k}：{v}" for k, v in br["errors"].items())
    return t


def fj_text(fj: dict) -> str:
    """前向记录判断层的一行（执行器日志 / 页面）。"""
    if not fj.get("applied"):
        return f"- ★ 前向记录判断层没生效：{fj.get('why') or '—'}"
    h = fj.get("halved") or []
    return (f"- 前向记录判断层（{fj.get('as_of')}）：市场 {fj.get('points')} 分 → 日本个股新仓 ×{fj.get('mult')}（与原有各层取小）；"
            + (f"个股减半 {len(h)} 只：{'、'.join(h[:8])}" if h else "没有个股减半"))


# ══════════════════ 数据依赖的提醒（C-08 / C-09 / LU-03；只提醒，照旧按原规则下单）══════════════════
YF_FIX = ("在 Mac 对话里说「升级 yfinance」→ Claude 运行 ~/.qbreak/venv/bin/python -m pip install -U yfinance"
          "（或你自己在终端运行 bash scripts/mac_setup.sh --upgrade-yfinance）；Yahoo 本身断了的话等它恢复，下一次运行会自动用新行情")
INPUT_LAYERS = (("fwd_judgment", "前向记录判断层"), ("combo_c", "关联搭配 C"), ("tbf", "TBF"))


def trading_days_behind(old, new) -> int | None:
    """old（数据的日子）比 new（应有的日子）落后几个交易日：old ≥ new → 0；读不出 → None；最多数到 60。"""
    try:
        a, b = dt.date.fromisoformat(str(old)[:10]), dt.date.fromisoformat(str(new)[:10])
    except ValueError:
        return None
    n = 0
    while b > a and n < 60:
        b = prev_trading_day(b)
        n += 1
    return n


def stale_inputs(sm: dict, sim_last: str | None = None) -> dict | None:
    """C-08：判断层的输入（云端算好、liveu.sh 同步过来的前向记录判断层 / 关联搭配 C / TBF 三个文件）日期不对 / 没有文件，
    或云端模拟盘（--compare-sim 的状态）比执行器的决策日落后 ≥ 1 个交易日 → {"days": N | None, "why": [...], "short", "text"}；
    都正常 → None。文件标着关闭、日期却是对的（云端自己关的）不算。只提醒：这几层今天不生效、照旧按原规则下单
    （「云端停摆时只卖不买」属于交易规则，要用户另外决定，这里不做）。"""
    d = sm.get("decided_on")
    why, days = [], []
    for key, name in INPUT_LAYERS:
        b = sm.get(key) or {}
        if not b.get("enabled") or b.get("applied"):
            continue
        asof = b.get("as_of")
        if not asof:
            why.append(f"{name}（没有文件）")
            days.append(None)
            continue
        n = trading_days_behind(asof, b.get("bar_date") or d)
        if n:
            why.append(f"{name}（文件是 {asof} 的）")
            days.append(n)
    n = trading_days_behind(sim_last, d) if sim_last and d else None
    if n:
        why.append(f"云端模拟盘停在 {sim_last}")
        days.append(n)
    if not why:
        return None
    known = [x for x in days if x]
    k = max(known) if known else None
    head = f"判断层的输入 {k} 天没更新" if k else "判断层的输入没更新"
    return {"days": k, "why": why, "short": head,
            "text": f"{head}：{'、'.join(why)} → 这几层今天不生效，照旧按原规则下单（例行任务没跑 / 没推上来？"
                    "在 Mac 对话里说「例行任务今天跑了吗」）"}


def data_problem(why: list[str] | None) -> dict | None:
    """C-09：这次的行情有问题（连不上 Yahoo / 日本行情落后 / 持仓或指数的行情落后）→ {"why": [...], "fix": 修法}；没有 → None。
    不改用 J-Quants 代替（数据源不同会让决策和模拟盘不同，属于规则，要用户另外决定）。"""
    why = [str(x) for x in why or [] if x]
    return {"why": why, "fix": YF_FIX} if why else None


def lag_exit_lines(lag: dict | None) -> list[str]:
    """LU-03：行情落后的持仓 {代码: 行情只到的日子} → 「X 今天的离场判断被跳过（行情只到 …）」（引擎缺那一天的 K 线就不检查离场）。"""
    return [f"{t} 今天的离场判断被跳过（行情只到 {d}）：止损 / 离场要等行情补上之后的下一次运行"
            for t, d in sorted((lag or {}).items())]


def model_diff_orders(orders) -> list[dict]:
    """没下的单里与模型不同的（早上错过寄付 / 到 09:20 还没寄り付き / 拆股当天判断不了行情…：note 里写着「与模型不同」）。
    实盘的通知升 warn、加 ★（不然只有第二天的「★ 与云端不一致」才看得出）。"""
    return [o for o in orders or [] if o.get("status") == "SKIPPED" and "与模型不同" in str(o.get("note") or "")]


def daily_text(sm: dict, st: UState, cmp: dict | None, paper: bool, capital: float,
               invested: float | None = None, flows_day: float = 0.0) -> tuple[str, str, str]:
    """(标题, 通知用的一行, 日志正文)。每个数字带单位。invested = 起始本金 + 登记过的入出金（累计收益按它算）；
    flows_day = 最近一个交易日之内登记的入出金（当日损益里扣掉，入金不算赚、出金不算亏）。"""
    hist = st.history or []
    eq = float(hist[-1][1]) if hist else float(sm.get("equity_jpy") or capital)
    chg = (eq - float(hist[-2][1]) if len(hist) > 1 else 0.0) - float(flows_day or 0.0)
    base = float(invested if invested is not None else capital)
    ret = (eq / base - 1) * 100 if base else 0.0
    title = f"qbreak {'模拟操盘' if paper else '立花实盘'} {sm.get('decided_on') or ''}"
    orders = [o for o in sm.get("orders") or [] if o.get("status") not in ("SKIPPED",) and o.get("phase") != "now"]
    short = f"权益 ¥{eq:,.0f}（当日 {chg:+,.0f} 円，累计 {ret:+.2f}%）｜下一开盘的单 {len(orders)} 笔"
    if cmp and cmp.get("comparable"):
        short += (("｜与云端一致" if cmp.get("mode") != "holdings" else "｜与云端同样的票") if cmp.get("same")
                  else "｜上线初期：持仓与云端不同（预期）" if cmp.get("early")
                  else "｜出金预留：持仓与云端不同（预期）" if cmp.get("explained") else "｜★ 与云端不一致")
    if sm.get("blocked"):
        short += "｜★ 没下单"
    from .run_status import actionable, bad_orders, bad_text, uncovered
    # 适配器挡下 / 立花拒绝 / 状态不明的单（不经过 ux.block）；HALT 挡下的不算（HALT 生效中不下单是预期的）
    bad = actionable(uncovered(bad_orders(sm.get("orders")), sm.get("blocked")))
    if bad:
        short += f"｜★ 没下 {len(bad)} 笔（{bad_text(bad)}）"
    md = [] if paper else model_diff_orders(sm.get("orders"))
    if md:
        short += f"｜★ 与模型不同 {len(md)} 笔（没下）"
    if sm.get("notices"):
        short += "｜★ 立花通知"
    if sm.get("incomplete"):                                # 这次没做完（例如开盘后补单取价失败，单都保留）
        short += "｜★ 没做完"
    ol = sm.get("odd_lots") or {}
    if ol:
        short += f"｜★ 零股 {len(ol)} 只要在立花网站卖"
    el = sm.get("eligibility") or {}
    if el.get("needs_user"):
        short += "｜★ 资格检查要确认"
    ds = sm.get("delist") or {}
    if ds.get("needs_user"):
        short += "｜★ 退市时间表要看"
    fj = sm.get("fwd_judgment") or {}
    if fj.get("enabled") and not fj.get("applied"):
        short += "｜★ 判断层没生效"
    cc = sm.get("combo_c") or {}
    if cc.get("enabled") and not cc.get("applied"):
        short += "｜★ 关联搭配 C 没生效"
    tb = sm.get("tbf") or {}
    if tb.get("enabled") and not tb.get("applied"):
        short += "｜★ TBF 没生效"
    si, dp, lx = sm.get("stale_inputs") or {}, sm.get("data_problem") or {}, sm.get("lag_exits") or {}
    if si:
        short += f"｜★ {si.get('short') or '判断层的输入没更新'}"
    if dp:
        short += "｜★ 行情有问题（看修法）"
    if lx:
        short += f"｜★ {'、'.join(sorted(lx))} 的离场判断今天跳过"
    mn = sm.get("manual") or {}
    if mn.get("active"):
        short += f"｜手动指令 {int(mn['active'])} 条在处理"
    if mn.get("core_pause") and (mn.get("core_signal") or {}).get("date") == sm.get("decided_on"):
        short += "｜★ 闲置资金 ETF 买入信号：确认后才买"         # 你卖出 ETF 后停着：规则从「不拿」变成「拿」（只提醒）
    lines = [f"- 决策日 {sm.get('decided_on') or '—'} → 成交日 {sm.get('fill_day') or '—'}；权益 ¥{eq:,.0f}"
             f"（当日 {chg:+,.0f} 円，累计 {ret:+.2f}%）；现金 ¥{float(st.cash_jpy):,.0f}"]
    if invested is not None and abs(float(invested) - float(capital)) >= 1.0:
        lines.append(f"- 投入本金 ¥{float(invested):,.0f}（起始 ¥{float(capital):,.0f}，登记的入出金 {float(invested) - float(capital):+,.0f} 円）"
                     + (f"；当日损益已扣掉入出金 {float(flows_day):+,.0f} 円" if flows_day else ""))
    for n in sm.get("notices") or []:                       # 立花的通知（例如 API 新版本的发布日）
        lines.append(f"- ★ {n}")
    if sm.get("incomplete"):
        lines.append(f"- ★ 这次没做完：{sm['incomplete']}")
    for o in md:                                            # 与模型不同的没下的单（B13 错过寄付 / B7 到 09:20 没寄り付き 等）
        lines.append(f"- ★ 与模型不同：{'买' if o.get('side') == 'BUY' else '卖'} {o.get('ticker')} {_qty_txt(o)}：{o.get('note')}")
    if dp:                                                  # 行情有问题：原因 + 修法（C-09）
        lines.append(f"- ★ 行情：{'；'.join(dp.get('why') or [])}。修法：{dp.get('fix') or YF_FIX}")
    for ln in lag_exit_lines(lx):                           # 行情落后的持仓：今天的离场判断被跳过（LU-03）
        lines.append(f"- ★ {ln}")
    if si:                                                  # 判断层的输入没更新（C-08）
        lines.append(f"- ★ {si.get('text')}")
    for t, v in sorted(ol.items()):                         # 单元未满株：普通注文卖不掉，要在立花网站卖（C-14）
        lines.append(f"- ★ {(v or {}).get('text') or f'{t} 有零股：在立花网站卖'}")
    held = [f"{t} {int(p.shares):,} 股（成本 ¥{float(p.entry_px):,.2f}，止损 ¥{float(p.stop_px):,.2f}）" for t, p in st.pos.items()]
    held += [f"{t} {int(u):,} 口" for t, u in st.core_units.items() if int(u)]
    lines.append("- 持仓：" + ("；".join(held) if held else "无（全部现金）"))
    from .holding_view import lines as hv_lines
    lines += hv_lines(sm.get("holding_view"))               # 每只持仓：为什么持有 · 现在趋势如何（只展示）
    from .manual_orders import REASON_TEXT, lines as manual_lines
    for r in sm.get("reconciled") or []:
        unit = "口" if r.get("kind") == "core" else "股"
        lines.append(f"- 已成交（{r['bar']} 开盘）：{'买' if r['side'] == 'BUY' else '卖'} {r['ticker']} {int(r['qty']):,} {unit} @ ¥{float(r['px']):,.2f}"
                     + (f"（{REASON_TEXT[r['reason']]}）" if r.get("reason") in REASON_TEXT else ""))
    for o in sm.get("orders") or []:
        now_ = o.get("phase") == "now"                       # 盘中的手动单（now_phase）
        how = ("盘中" if now_ else "寄付成行") if o["side"] == "SELL" else (
            f"{'盘中' if now_ else ('寄付' if o.get('phase') == 'morning' and o.get('status') != 'DEFERRED' else '开盘后')}"
            f"指値 ≤ ¥{float(o['limit']):,.0f}")
        lines.append(f"- {'盘中' if now_ else '下一开盘'}：{'卖' if o['side'] == 'SELL' else '买'} {o['ticker']} {_qty_txt(o)}（{how}"
                     + (f"，{REASON_TEXT[o['reason']]}" if o.get("reason") in REASON_TEXT else "") + f"）→ {o['status']}"
                     + (f"：{o['note']}" if o.get("note") else ""))
    if not orders:
        lines.append("- 下一开盘：没有单")
    lines += manual_lines(sm.get("manual"), today=sm.get("decided_on"))
    for m, bb in (sm.get("market") or {}).items():        # 牛熊：现在处于哪个阶段（只展示）
        if bb and bb.get("phase_label"):
            lines.append(f"- 牛熊（{ {'JP': '日経平均', 'US': 'S&P500'}.get(m, m)}）：{bb['phase_label']}：{bb.get('phase_text', '')}")
    if fj.get("enabled"):                                   # 前向记录判断层（云端算好的 fwd_judgment.json）
        lines.append(fj_text(fj))
    if cc.get("enabled"):                                   # 关联搭配 C（云端算好的 combo_c.json）
        from .combo_c import text as cc_text
        lines.append(cc_text(cc))
    if tb.get("enabled"):                                   # TBF 像起跌点就不买（云端算好的 tbf.json）
        from .tbf import text as tbf_text
        lines.append(tbf_text(tb))
    if sm.get("exit_mode") and sm["exit_mode"] != "DC":        # 个股的离场方式（var/sim.json exits）
        from .exit_rules import LABELS
        lines.append(f"- 个股离场：{LABELS.get(sm['exit_mode'], sm['exit_mode'])}（止损 / 跟踪 / 止盈 / 最长持有照旧）")
    ic = sm.get("idle_cash") or {}
    if ic.get("mode") and ic["mode"] != "K0":                 # 闲置资金的方式（var/sim.json idle_cash）
        lines.append(f"- 闲置资金：{ic.get('label') or ic['mode']}；现在：{ic_text(ic)}")
    if cmp:
        lines.append(f"- {cmp['text']}")
    if sm.get("blocked"):
        lines.append(f"- ★ 没有下单：{sm['blocked']}")
    for n in el.get("needs_user") or []:                    # 下单前资格检查：被踢出 / 被指定 / 名单不一致 / 数据过期
        lines.append(f"- ★ {n}")
    if el and not el.get("needs_user"):
        lines.append(f"- {el.get('text') or '资格检查：—'}")
    for n in ds.get("needs_user") or []:                    # 股票池更新时间表：持仓将上場廃止 / 已去掉、补入要确认
        lines.append(f"- ★ {n}")
    if ds.get("error"):
        lines.append(f"- ★ 股票池更新时间表这次没更新：{ds['error']}（上一次的表照常生效）")
    elif ds.get("text") and not ds.get("needs_user"):
        lines.append(f"- {ds['text']}")
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


# ══════════════════════════ 实盘的运行保障：锁、入出金、远程停止、重试 ══════════════════════════
def lock_held(path) -> bool:
    """有别的进程拿着这份账本的运行锁（RunLock）→ True（执行器正在运行）。只试一下共享锁、马上放开；
    锁文件不存在 / 没有 fcntl / 打不开 → False。不建文件、不等。"""
    try:
        import fcntl
        f = open(path, "r", encoding="utf-8")
    except (ImportError, OSError):
        return False
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError:
        return True
    else:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return False
    finally:
        f.close()


class RunLock:
    """同一个账本同一时间只允许一个执行器进程（07:40 早上 / 08:35 重试 / 09:05 开盘后 / 09:20 重试 / --resolve / --flow）。
    Mac 睡眠醒来时 launchd 会把错过的几个定时任务同时启动 → 没有锁就会两个进程同时读写账本（后写的覆盖先写的）。
    fcntl.flock 独占锁：进程结束（含崩溃）时操作系统自动释放，不会留下「死锁文件」。等不到 → ExecutorError（这次不运行）。"""

    def __init__(self, path, wait_s: float = 1200.0, poll_s: float = 5.0, sleep=None, mono=None):
        import time as _t
        self.path, self.wait_s, self.poll_s = path, float(wait_s), float(poll_s)
        self._sleep, self._mono = sleep or _t.sleep, mono or _t.monotonic
        self._f = None

    def acquire(self) -> "RunLock":
        import os
        try:
            import fcntl
        except ImportError:                                   # Windows：执行器只在 Mac / Linux 上跑，这里不加锁
            log.warning("没有 fcntl：执行器不加运行锁")
            return self
        from pathlib import Path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        f = open(self.path, "a+", encoding="utf-8")
        t0 = self._mono()
        while True:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if self._mono() - t0 >= self.wait_s:
                    f.seek(0)
                    holder = f.read().strip() or "?"
                    f.close()
                    raise ExecutorError(f"另一个执行器还在运行（{holder}），等了 {self.wait_s / 60:.0f} 分钟仍没结束 → 这次不运行"
                                        "（状态没有改动；在 Mac 对话里问「执行器为什么没跑完」）") from None
                self._sleep(self.poll_s)
        f.seek(0)
        f.truncate()
        f.write(f"pid {os.getpid()} 从 {now_jst():%Y-%m-%d %H:%M:%S JST}\n")
        f.flush()
        self._f = f
        return self

    def release(self) -> None:
        if self._f is None:
            return
        try:
            import fcntl
            fcntl.flock(self._f.fileno(), fcntl.LOCK_UN)
        finally:
            self._f.close()
            self._f = None

    def __enter__(self) -> "RunLock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()


def flows(book: dict) -> list[dict]:
    """登记过的入金（+）/ 出金（−）：[{"date", "jpy", "note", "at", "seen_after"?}]（seen_after = 在哪个决策日之后的现金同步里到账）。
    实盘账本第一次核对之前登记的（in_start：已经含在起始本金里，B11）不算。"""
    return [f for f in (book or {}).get("flows") or [] if isinstance(f, dict) and not f.get("in_start")]


RESERVE_DAYS = 14                          # 出金预留：登记后这么多天还没对上到账 → 解除并提醒


def reserves(book: dict | None) -> list[dict]:
    """还在预留中的出金（〔77〕C LU-19）：登记时选了预留、还没到账、没解除的。"""
    return [f for f in flows(book or {}) if f.get("reserve") and not f.get("seen_after") and not f.get("reserve_released")
            and float(f.get("jpy") or 0) < 0]


def reserve_jpy(book: dict | None) -> float:
    return sum(-float(f.get("jpy") or 0) for f in reserves(book))


def start_capital(book: dict | None, default: float) -> float:
    """起始本金：实盘账本第一次核对时的买付可能額（+ 持仓市值；账本 capital_jpy，B11）；没有（模拟账户 / 还没核对过）→ default
    （sim.json 的 capital_jpy）。只影响收益的显示，不影响下单。"""
    try:
        v = float((book or {}).get("capital_jpy") or 0)
    except (TypeError, ValueError):
        v = 0.0
    return v if v > 0 else float(default)


def _flow_tol(jpy) -> float:
    """登记的金额与现金差算「对上」的容差：¥5,000 或金额的 3%（当天的手续费、税、分红入账会混在现金差里）。"""
    return max(5000.0, 0.03 * abs(float(jpy or 0)))


def match_flow(pending: list[dict], drift: float) -> list[dict]:
    """还没到账的登记里，哪几笔 ≈ 这次的现金差：先看全部合计，再看单笔（新的优先）。对不上 → []。"""
    if not pending:
        return []
    tot = sum(float(f.get("jpy") or 0) for f in pending)
    if abs(drift - tot) <= _flow_tol(tot):
        return list(pending)
    for f in reversed(pending):
        if abs(drift - float(f.get("jpy") or 0)) <= _flow_tol(f.get("jpy")):
            return [f]
    return []


def flow_reflected(f: dict, asof: str | None) -> bool:
    """这笔入出金是否已经含在决策日 asof 的权益里：对上了现金差的（seen_after）→ seen_after 之后的决策日才含；
    还没对上的 → 按登记的日期（≤ asof 就算含）。asof 为空 = 全部算。"""
    if asof is None:
        return True
    sa = f.get("seen_after")
    if sa:
        return str(sa) < str(asof)
    return str(f.get("date") or "") <= str(asof)


def invested_jpy(capital: float, book: dict, asof: str | None = None) -> float:
    """投入本金 = 起始本金 + 已经含在 asof 那天权益里的入出金（累计收益按它算）。"""
    return float(capital) + sum(float(f.get("jpy") or 0) for f in flows(book) if flow_reflected(f, asof))


def flows_in_change(book: dict, prev: str | None, last: str | None) -> float:
    """权益从决策日 prev 到 last 的变化里含的入出金（当日损益里扣掉：入金不算赚、出金不算亏）。"""
    if not last:
        return 0.0
    return sum(float(f.get("jpy") or 0) for f in flows(book)
               if flow_reflected(f, last) and not (prev and flow_reflected(f, prev)))


def register_flow(path, jpy: float, note: str = "", day: str | None = None, reserve: bool = False) -> dict:
    """登记一笔入金（正）/ 出金（负）。只影响收益的显示与「现金突然变化」的提醒；下单本来就按券商的买付可能額，不受影响。
    如果最近几次早上的现金同步里已经出现过对得上的现金差（先到账、后登记），直接记为在那次到账。
    reserve=True（只用于出金；〔77〕C LU-19，2026-10-10 用户「加出金预留」）：到账之前，执行器每次决策都把这笔钱当作已经出金
    （个股仓位按扣掉它的权益算、闲置资金 ETF 不买回、现金不够照规则先卖核心 ETF）；出金到账（现金差对上）后自动解除，
    登记 14 天后还没对上也解除并提醒。"""
    if not jpy or abs(float(jpy)) < 1:
        raise ValueError("入出金金额要 ≥ 1 円（入金写正数、出金写负数）")
    if reserve and float(jpy) > 0:
        raise ValueError("预留只用于出金（写负数）：入金不用预留")
    if day is not None:
        day = dt.date.fromisoformat(str(day)).isoformat()              # 日期写错直接报错，不存进账本
    book = read_json(path, {}) or {}
    rec = {"date": day or now_jst().date().isoformat(), "jpy": round(float(jpy), 2), "note": str(note or "")[:200],
           "at": now_jst().isoformat(timespec="seconds")}
    if reserve:
        rec["reserve"] = True
    used = {str(f.get("seen_after")) for f in flows(book) if f.get("seen_after")}
    for d, x in reversed((book.get("cash_drift") or [])[-5:]):
        if d and str(d) not in used and abs(float(x) - rec["jpy"]) <= _flow_tol(rec["jpy"]):
            rec["seen_after"] = str(d)
            break
    book.setdefault("flows", []).append(rec)
    book.setdefault("events", []).append({"at": rec["at"], "level": "info",
                                          "msg": (f"登记{'入金' if rec['jpy'] > 0 else '出金'} {rec['jpy']:+,.0f} 円（{rec['date']}）{rec['note']}".rstrip()
                                                  + ("；出金预留：到账前的决策按扣掉它算" if reserve and not rec.get("seen_after") else ""))})
    atomic_write_text(path, json.dumps(book, ensure_ascii=False, indent=1, default=_np))
    return rec


REMOTE_HALT_MARK = ".remote_halt_applied"


def parse_remote_halt(text: str | None) -> dict | None:
    """仓库里的 var/HALT_REMOTE（云端对话里用户说「停」时 Claude 提交推送）：每行「键: 值」，至少有 id；没有 id 就用全文当 id。"""
    if not text or not text.strip():
        return None
    kv = {}
    for ln in text.splitlines():
        if ":" in ln:
            k, v = ln.split(":", 1)
            kv[k.strip().lower()] = v.strip()
    import hashlib
    rid = kv.get("id") or hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:12]    # 没写 id：用内容的稳定摘要
    return {"id": rid, "reason": kv.get("reason") or kv.get("原因") or ""}


def apply_remote_halt(text: str | None, home=None) -> str | None:
    """Mac 的执行器每次运行前看一眼远程停止：没处理过的 id → 建本地 HALT 文件（买卖都不下、持仓不动）并记下这个 id；
    同一个 id 不会再触发（所以在 Mac 上明确说「恢复下单，删除 HALT」之后不会被同一条远程停止又停住）。
    返回给人看的一句话；没有新的远程停止 → None。已经发到交易所的单不会被撤（要撤：面板「今天的单」的「撤单」/
    bash scripts/liveu.sh cancel，或立花网站 / 手机网站）。"""
    from pathlib import Path
    r = parse_remote_halt(text)
    if r is None:
        return None
    base = Path(home) if home is not None else paths.home()
    mark = base / REMOTE_HALT_MARK
    if mark.exists() and mark.read_text(encoding="utf-8").strip() == r["id"]:
        return None
    halt = base / "HALT"
    msg = f"远程停止（云端对话）{now_jst():%Y-%m-%d %H:%M JST}：{r['reason'] or '用户说停'}（id {r['id']}）"
    if not halt.exists():
        atomic_write_text(halt, msg + "\n恢复：在 Mac 对话里明确说「恢复下单，删除 HALT」\n")
    atomic_write_text(mark, r["id"] + "\n")
    return msg


def morning_done(book: dict, expected_bar: str) -> bool:
    """08:35 的重试用：今天早上的运行是否已经完成（账本已经处理到应有的决策日、而且这个决策没有 PLANNED / BLOCKED 的单）。
    完成了就什么都不做 —— 绝不在同一个早上换一份输入再决策一次（那样可能多下单）。"""
    st = (book or {}).get("state") or {}
    if st.get("last_date") != expected_bar:
        return False
    return not any(o.get("decided_on") == expected_bar and o.get("status") in ("PLANNED", "BLOCKED")
                   for o in (book or {}).get("orders") or [])


def late_pending(book: dict) -> bool:
    """09:20 的开盘后重试用（B13）：当前决策里还有早上错过寄付、还没发出的个股卖单吗（时间窗口挡下的，或开盘后那一刻取不到现价的）。"""
    d = ((book or {}).get("state") or {}).get("last_date")
    return any(o.get("decided_on") == d and o.get("side") == "SELL" and o.get("kind") == "stock" and o.get("status") == "BLOCKED"
               and not o.get("broker_id") and (o.get("phase") == "late" or CUTOFF_TEXT in str(o.get("note") or ""))
               for o in (book or {}).get("orders") or [])


def open_pending(book: dict) -> bool:
    """09:20 的开盘后重试用：当前决策里还有留到开盘后、还没下的买单（DEFERRED）吗？没有 → 什么都不做（09:05 已经处理过 / 今天没有）。"""
    d = ((book or {}).get("state") or {}).get("last_date")
    return any(o.get("decided_on") == d and o.get("status") == "DEFERRED" for o in (book or {}).get("orders") or [])


def record_compare(book: dict, cmp: dict | None) -> None:
    """每天与云端比较的结果（上线门槛「连续 10 个交易日一致」用；run.py live-gate 读）。同一个决策日只记最后一次。"""
    if not cmp or not cmp.get("exec_date"):
        return
    h = [x for x in book.get("compare_history") or [] if x.get("date") != cmp["exec_date"]]
    h.append({"date": cmp["exec_date"], "comparable": bool(cmp.get("comparable")), "same": cmp.get("same"),
              "mode": cmp.get("mode") or "exact", **({"early": True} if cmp.get("early") else {}),
              **({"explained": cmp["explained"]} if cmp.get("explained") else {})})
    book["compare_history"] = sorted(h, key=lambda x: x["date"])[-250:]


# ══════════════════════════ 两台 Mac（OPS-04 / 立花实盘缺口 B14）══════════════════════════
HOST_KEY = "host"                                  # 立花本番的账本属于哪台 Mac（标识的摘要，不是主机名）


IOREG = "/usr/sbin/ioreg"   # 绝对路径：定时任务（launchd）的 PATH 不一定带 /usr/sbin，终端里的带


def host_id(run=None, *, ioreg: str = IOREG, platform: str | None = None,
            machine_id: str = "/etc/machine-id") -> str:
    """这台机器的标识（只存摘要：sha1 的前 8 位；主机名 / 硬件 UUID 的原文不进账本、日志）。
    macOS：硬件 UUID（ioreg 的 IOPlatformUUID，换网络、改电脑名都不变）；先用绝对路径 /usr/sbin/ioreg（定时任务、面板、终端
    看到的 PATH 不一样，不能让同一台 Mac 因为 PATH 得出两个标识），没有这个文件才按 PATH 找；macOS 上 ioreg 读不出 → "?"
    （不判定；不退回主机名：主机名会随网络（DHCP）变，会把同一台 Mac 认成另一台、停掉执行器）。
    其他系统：/etc/machine-id；读不到 → 主机名（socket.gethostname()）；连主机名都没有 → "?"（不判定）。"""
    import hashlib
    import re as _re
    import shutil
    import socket
    import subprocess
    import sys
    darwin = (platform or sys.platform) == "darwin"
    exe = ioreg if Path(ioreg).exists() else (shutil.which("ioreg") or ioreg)
    raw = ""
    try:
        r = (run or subprocess.run)([exe, "-rd1", "-c", "IOPlatformExpertDevice"], capture_output=True, text=True, timeout=10)
        m = _re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', r.stdout or "") if r.returncode == 0 else None
        raw = f"uuid:{m.group(1)}" if m else ""
    except (OSError, ValueError, subprocess.SubprocessError):
        raw = ""
    if not raw and darwin:
        return "?"
    if not raw:
        try:
            mid = Path(machine_id).read_text(encoding="utf-8").strip()
            raw = f"mid:{mid}" if mid else ""
        except OSError:
            raw = ""
    if not raw:
        try:
            raw = f"host:{socket.gethostname()}" if socket.gethostname() else ""
        except OSError:
            raw = ""
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8] if raw else "?"


def check_host(book: dict, hid: str | None = None, clock=None) -> str | None:
    """立花本番的账本属于哪台 Mac：没记过 → 记下这台（book["host"]，下一次存账本时写进去）、返回 None；一样 → None；
    不一样 → 原因（执行器停下：两台 Mac 同时跑同一个账户会重复下单，立花那边挡不住）。这台的标识读不出（"?"）→ 不判定。"""
    hid = hid or host_id()
    old = str((book or {}).get(HOST_KEY) or "")
    if hid == "?" or old == hid:
        return None
    if not old:
        book[HOST_KEY] = hid
        book["host_since"] = (clock or now_jst)().date().isoformat()
        return None
    return (f"这个账本是另一台 Mac 的（账本记的机器标识 {old}，这台 {hid}；只记了摘要）：两台 Mac 同时跑同一个立花账户会重复下单。"
            "换 Mac 照 MACOS.md「换 Mac」做：先在旧 Mac 上 HALT 并卸载立花的定时任务，确认旧 Mac 不再运行之后，"
            "在 Mac 对话里明确说「换 Mac，账本归这台」→ bash scripts/liveu.sh adopt-host --broker tachibana")


def adopt_host(path, hid: str | None = None, clock=None) -> dict:
    """换 Mac（用户在对话里明确说了）：账本的机器标识改成这台。先备份账本（qbreak/book_backup.py）；不连券商、不下单。
    → {"old", "new", "changed"}；没有账本 → FileNotFoundError。"""
    from .book_backup import backup
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    book = read_json(p, {}) or {}
    hid = hid or host_id()
    if hid == "?":
        raise ValueError("这台机器的标识读不出（macOS：/usr/sbin/ioreg 读不出硬件 UUID；其他系统：machine-id / 主机名都没有）：不用换，执行器在这里不判定机器")
    old = str(book.get(HOST_KEY) or "")
    if old == hid:
        return {"old": old, "new": hid, "changed": False}
    backup(p)
    now = (clock or now_jst)()
    book[HOST_KEY], book["host_since"] = hid, now.date().isoformat()
    ev = (book.get("events") or []) + [{"at": now.isoformat(timespec="seconds"), "level": "warn",
                                        "msg": f"换 Mac：账本的机器标识 {old or '（没记过）'} → {hid}（用户在对话里确认）"}]
    book["events"] = ev[-500:]
    atomic_write_text(p, json.dumps(book, ensure_ascii=False, indent=1, default=_np))
    return {"old": old, "new": hid, "changed": True}
