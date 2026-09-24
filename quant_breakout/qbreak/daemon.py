"""daemon.py — 盘中常驻守护进程（デーモン / daemon）。macOS 用 launchd 开机自启。

为什么是「日线信号 + 盘中守护」而不是「盘中重算信号」
  当前策略的信号定义在**收盘价**上，回测也是按收盘价验证的。
  盘中每分钟重算 MACD 金叉，会得到一堆盘中出现、收盘消失的假信号 ——
  而这种行为**无法用现有回测验证**。想做真正的日内策略是另一个项目
  （分钟级数据源 + 日内回测框架 + 全新信号定义）。
  所以守护进程盘中只做三件在日线框架内说得通、且真正有价值的事：

    ① 止损/跟踪止损/止盈的**盘中执行**（把回测里 intraday 模式变成现实）
    ② **逆指値の維持**：把止损挂到券商侧 —— Mac 休眠、断网、程序崩溃都不影响它
    ③ 成交核对、熔断监控、异常告警

  收盘后（默认 15:40）跑一次和模拟盘完全相同的日线流程，产生次日寄付单。

生命周期
    closed          → 睡到下一个开市时刻（不空转、不浪费 API 配额）
    pre   08:50     → 开市前对账：持仓、余力、逆指値是否都还在
    morning/afternoon → 每 poll_interval_s 轮询一次
    lunch           → 低频心跳
    closing_auction → 15:25 最后一次风控检查
    post  15:40     → 日线信号 → 次日寄付单 → 日终对账 → risk.end()

崩溃与休眠
    所有状态都在磁盘上；launchd 的 KeepAlive 会把进程拉起来，
    重启后 `_reconcile()` 会把本地记录和券商侧持仓对齐，并补挂缺失的逆指値。
"""
from __future__ import annotations

import datetime as dt
import signal
import threading
from dataclasses import dataclass, field

import numpy as np

from . import notify, paths
from .brokers.base import BaseBroker, Position, state_tag
from .calendar_jp import now_jst, seconds_until_next_event, session_of
from .config import DataConfig, ExecConfig, RiskConfig, SizingConfig, StrategyParams
from .risk import RiskManager
from .trader import OrderGuard, PositionBook, run_once
from .utils import read_json, setup_logging, write_json

log = setup_logging("daemon")

_SESSION_CN = {"closed": "休市 —— 睡到下一个开市时刻", "pre": "开市前", "morning": "前場",
               "lunch": "午休", "afternoon": "後場", "closing_auction": "收盘集合竞价",
               "post": "收盘后"}


@dataclass
class DaemonConfig:
    poll_interval_s: int = 60          # 盘中轮询间隔。日线策略不需要更快；越快越容易被限流
    lunch_interval_s: int = 300
    premarket_at: dt.time = dt.time(8, 50)
    eod_at: dt.time = dt.time(15, 40)  # 收盘 15:30 + 缓冲；日线数据也需要时间更新
    protective_stop: bool = True       # 把止损挂到券商侧（强烈建议开）
    trail_update_threshold: float = 0.5  # 跟踪止损上移超过该 % 才改挂，避免频繁撤改
    max_round_trips_per_day: int = 1
    # 現物の差金決済：同一銘柄・同一営業日・同一資金は「買→売」1 往復まで。
    # 2 往復目は券商侧で拒否されるので、こちら側でも止める。
    heartbeat_s: int = 120
    quote_fail_alert: int = 5          # 连续取价失败多少轮后告警


@dataclass
class DaemonState:
    date: str = ""
    premarket_done: bool = False
    eod_done: bool = False
    round_trips: dict = field(default_factory=dict)   # ticker -> 当日已完成往复数
    sold_today: list = field(default_factory=list)
    last_heartbeat: str = ""

    @classmethod
    def load(cls) -> "DaemonState":
        d = read_json(paths.state_dir() / "daemon_state.json", {}) or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def save(self) -> None:
        write_json(paths.state_dir() / "daemon_state.json", self.__dict__)

    def roll(self, today: str) -> None:
        if self.date != today:
            self.date, self.premarket_done, self.eod_done = today, False, False
            self.round_trips, self.sold_today = {}, []
            self.save()


class Daemon:
    def __init__(self, universe: list[str], broker: BaseBroker, params: StrategyParams,
                 risk_cfg: RiskConfig, sizing: SizingConfig, data_cfg: DataConfig,
                 exec_cfg: ExecConfig, cfg: DaemonConfig | None = None,
                 dry_run: bool = False, market: str = "JP",
                 fallback_quotes: bool = False,
                 entry_hook=None, corp_actions=None, core_ticker: str | None = None):
        self.universe = universe
        self.core_ticker = core_ticker         # 核心指数 ETF：不做个股止损 / 逆指値，由日终流程按目标份额调整
        self.broker = broker
        self.p = params.validate()
        self.corp_actions = corp_actions       # 除息 / 拆股数据源
        self.entry_hook = entry_hook           # (date) -> (市场倍数, {票: 倍数}, 事件拦截, 强制离场, 核心仓位, 财报日)
        self.risk_cfg = risk_cfg.validate()
        self.sizing = sizing.validate()
        self.data_cfg = data_cfg.validate()
        self.ex = exec_cfg.validate()
        self.cfg = cfg or DaemonConfig()
        self.dry_run = dry_run
        self.market = market
        self.fallback_quotes = fallback_quotes
        self.st = DaemonState.load()
        self.book = PositionBook.for_broker(broker)
        self.guard = OrderGuard.for_broker(broker)
        self.rm = RiskManager(self.risk_cfg, market=market, tag=state_tag(broker))
        self._stop = threading.Event()
        self._quote_fails = 0
        self._last_session = ""

    # ────────────────────── 生命周期 ──────────────────────
    def install_signal_handlers(self) -> None:
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: self.request_stop())

    def request_stop(self) -> None:
        log.info("收到停止信号，完成本轮后退出")
        self._stop.set()

    def run_forever(self, max_loops: int | None = None) -> None:
        """max_loops 仅供测试使用。"""
        log.info("守护进程启动：股票池 %d 只，轮询 %ds，逆指値 %s，dry_run=%s",
                 len(self.universe), self.cfg.poll_interval_s,
                 "开" if self.cfg.protective_stop else "关", self.dry_run)
        notify.send("守护进程启动", f"股票池 {len(self.universe)} 只 / dry_run={self.dry_run}")
        loops = 0
        try:
            while not self._stop.is_set():
                sleep_s = self.tick()
                loops += 1
                if max_loops is not None and loops >= max_loops:
                    break
                self._stop.wait(max(sleep_s, 1.0))
        except Exception as e:                       # noqa: BLE001
            log.exception("守护进程异常退出: %s", e)
            notify.send("★ 守护进程异常退出", str(e), "error")
            raise
        finally:
            if hasattr(self.broker, "logout"):
                self.broker.logout()
            log.info("守护进程已停止")

    def tick(self, now: dt.datetime | None = None) -> float:
        """跑一轮，返回建议睡眠秒数。所有分支都必须返回，不能抛异常到上层。"""
        now = now or now_jst()
        self.st.roll(str(now.date()))
        self._heartbeat(now)
        sess = session_of(now)
        if sess != self._last_session:               # 只在状态切换时打日志，避免刷屏
            log.info("[%s] %s", now.strftime("%m-%d %H:%M"), _SESSION_CN.get(sess, sess))
            self._last_session = sess

        try:
            if sess == "closed":
                return min(seconds_until_next_event(now), 3600.0)

            if sess == "pre":
                if now.time() >= self.cfg.premarket_at and not self.st.premarket_done:
                    self._premarket()
                return min(seconds_until_next_event(now), 300.0)

            if sess == "lunch":
                return min(self.cfg.lunch_interval_s, seconds_until_next_event(now))

            if sess in ("morning", "afternoon", "closing_auction"):
                self._intraday(now)
                return float(self.cfg.poll_interval_s)

            # post
            if now.time() >= self.cfg.eod_at and not self.st.eod_done:
                self._end_of_day(now)
            return min(seconds_until_next_event(now), 900.0)
        except Exception as e:                       # noqa: BLE001
            log.exception("本轮出错（已捕获，不影响后续）: %s", e)
            notify.send("守护进程本轮出错", str(e), "warn")
            return float(self.cfg.poll_interval_s)

    # ────────────────────── 各阶段 ──────────────────────
    def _heartbeat(self, now: dt.datetime) -> None:
        hb = paths.home() / "heartbeat.json"
        write_json(hb, {"ts": now.isoformat(), "session": session_of(now),
                        "pid": __import__("os").getpid(), "dry_run": self.dry_run})
        self.st.last_heartbeat = now.isoformat()

    def _premarket(self) -> None:
        log.info("── 开市前对账 ──")
        self._reconcile()
        if self.cfg.protective_stop:
            self._sync_protective_stops()
        self.st.premarket_done = True
        self.st.save()

    def _reconcile(self):
        """把本地跟踪记录和券商侧持仓对齐。崩溃重启、Mac 休眠醒来后都要跑。"""
        self.broker.sync()
        pos = self.book.merge(self.broker.positions())
        for t, p in pos.items():
            if not p.peak:
                p.peak = p.avg_px
            if not p.stop_px and t != self.core_ticker:
                p.stop_px = p.avg_px * (1 - self.p.stop_loss_pct / 100)
            self.book.update(p)
        self.book.save()
        log.info("持仓 %s  现金 %.0f", {t: p.qty for t, p in pos.items()},
                 _safe(self.broker.cash))
        return pos

    def _intraday(self, now: dt.datetime) -> None:
        pos = self.book.merge(self.broker.positions())
        if not pos:
            self._quote_fails = 0
            return
        prices = self._quotes(list(pos))
        if not prices:
            self._quote_fails += 1
            if self._quote_fails == self.cfg.quote_fail_alert:
                notify.send("★ 连续取不到实时价", f"已连续 {self._quote_fails} 轮，请检查 API 连接",
                            "error")
            return
        self._quote_fails = 0

        equity = _safe(self.broker.equity)
        dec = self.rm.begin(equity, now.date())
        if dec.halted:
            log.error("%s", dec)
            return

        for t, p in list(pos.items()):
            px = prices.get(t)
            if not px or t == self.core_ticker:
                continue
            if px > p.peak:                       # 用实时价更新峰值，跟踪止损才跟得上
                p.peak = px
                self.book.update(p)
            reason = self._exit_check(p, px)
            if reason:
                self._exit_now(t, p, px, reason, now)
        self.book.save()

        if self.cfg.protective_stop:
            self._sync_protective_stops()

    def _exit_check(self, p: Position, px: float) -> str | None:
        stop_px = p.stop_px or p.avg_px * (1 - self.p.stop_loss_pct / 100)
        trail_px = p.peak * (1 - self.p.trailing_stop_pct / 100) if self.p.trailing_stop_pct else -np.inf
        if self.p.trailing_arm_pct and p.peak < p.avg_px * (1 + self.p.trailing_arm_pct / 100):
            trail_px = -np.inf
        tp_px = p.avg_px * (1 + self.p.take_profit_pct / 100) if self.p.take_profit_pct else np.inf
        # 盘中只处理价格类出场；死叉/超时/时间止损是收盘价概念，留给 EOD
        if px <= stop_px:
            return f"stop(止损 {stop_px:.1f})"
        if px <= trail_px:
            return f"trail(跟踪止损 {trail_px:.1f} 峰值 {p.peak:.1f})"
        if px >= tp_px:
            return f"take_profit(止盈 {tp_px:.1f})"
        return None

    def _exit_now(self, t: str, p: Position, px: float, reason: str,
                  now: dt.datetime) -> None:
        cid = f"{now.date()}-{t}-SELL-intraday"
        if self.guard.seen(cid):
            return
        if self.dry_run:
            log.info("[DRY-RUN] 本应卖出 %s x%d @%.1f %s", t, p.qty, px, reason)
            self.guard.mark(cid, "dry-run")
            return
        # 先撤掉挂着的逆指値，否则会出现"重复卖出"
        sid = self.book.book.get(t, {}).get("stop_order_id")
        if sid and hasattr(self.broker, "cancel"):
            self.broker.cancel(sid)
            self.book.book.get(t, {}).pop("stop_order_id", None)
        o = self.broker.sell(t, p.qty, client_id=cid)
        if o.ok:
            self.guard.mark(cid, f"{o.status} {reason}")
            self.st.sold_today.append(t)
            self.st.round_trips[t] = self.st.round_trips.get(t, 0) + 1
            self.st.save()
            self.book.drop(t)
            fill_px = o.filled_px or px
            pnl = (fill_px - p.avg_px) * (o.filled_qty or o.qty)
            self.rm.on_trade_closed(pnl)
            notify.send(f"卖出 {t}",
                        f"{reason}\n数量 {o.filled_qty}/{o.qty} @ {fill_px:.1f}  损益 {pnl:+,.0f}")
        log.info("SELL %s x%d %s → %s", t, p.qty, reason, o.status)

    def _sync_protective_stops(self) -> None:
        """逆指値の維持。Mac が寝ても、プロセスが落ちても、この注文だけは生きている。"""
        if self.dry_run or not hasattr(self.broker, "place_protective_stop"):
            return
        for t, p in self.broker.positions().items():
            if t == self.core_ticker:
                continue
            ann = self.book.book.setdefault(t, {})
            base = ann.get("stop_px") or p.stop_px or p.avg_px * (1 - self.p.stop_loss_pct / 100)
            peak = float(ann.get("peak") or p.avg_px)
            trail = peak * (1 - self.p.trailing_stop_pct / 100) if self.p.trailing_stop_pct else 0.0
            want = max(float(base), trail)
            if want <= 0:
                continue
            cur = float(ann.get("stop_order_px") or 0)
            if cur and (want - cur) / cur * 100 < self.cfg.trail_update_threshold:
                continue                              # 变动太小，不值得撤改
            if ann.get("stop_order_id") and hasattr(self.broker, "cancel"):
                self.broker.cancel(ann["stop_order_id"])
            cid = f"{self.st.date}-{t}-STOP-{int(want)}"
            o = self.broker.place_protective_stop(t, p.qty, want, client_id=cid)
            if o.ok:
                ann.update({"stop_order_id": cid, "stop_order_px": want})
                log.info("逆指値 %s → %.1f", t, want)
        self.book.save()

    def _index_close(self):
        """基准指数收盘序列（相对强度过滤）；取不到时返回 None → 过滤自动跳过。"""
        if self.p.min_rs_pct <= -900:
            return None
        from .config import BENCHMARK
        from .data import load_universe
        try:
            idx = load_universe([BENCHMARK[self.market]], self.data_cfg).get(BENCHMARK[self.market])
            return idx["Close"] if idx is not None else None
        except Exception as e:                                # noqa: BLE001
            log.warning("指数数据不可用，相对强度过滤跳过: %s", e)
            return None

    def _end_of_day(self, now: dt.datetime) -> None:
        log.info("── 收盘后日线流程 ──")
        scale, tmult, block, force, core, earnings = 1.0, None, None, None, None, None
        if self.entry_hook is not None:
            try:
                got = self.entry_hook(now.date())
                scale, tmult, block = got[:3]
                force = got[3] if len(got) > 3 else None
                core = got[4] if len(got) > 4 else None
                earnings = got[5] if len(got) > 5 else None
            except Exception as e:                            # noqa: BLE001
                log.warning("宏观层 / 状态层计算失败，按 ×1 处理: %s", e)
        res = run_once(self.universe, self.broker, self.p, self.risk_cfg, self.sizing,
                       self.data_cfg, market=self.market, dry_run=self.dry_run,
                       today=now.date(), exec_cfg=self.ex,
                       protective_stop=self.cfg.protective_stop,
                       index_close=self._index_close(), entry_scale=scale,
                       ticker_mult=tmult, entry_block=block, corp_actions=self.corp_actions,
                       force_exit_all=force, core=core, earnings=earnings)
        log.info("\n%s", res.summary())
        self.st.eod_done = True
        self.st.save()
        notify.send(f"{now.date()} 日终汇总", res.summary())

    # ────────────────────── 工具 ──────────────────────
    def _quotes(self, tickers: list[str]) -> dict[str, float]:
        if hasattr(self.broker, "quotes"):
            return self.broker.quotes(tickers)
        out = {}
        for t in tickers:
            try:
                out[t] = self.broker.get_price(t)
            except Exception:                        # noqa: BLE001, PERF203
                pass
        if not out and self.fallback_quotes:
            # 模拟盘演练用：yfinance 分钟线（東証は 15~20 分遅延）
            from .data import realtime_quotes
            out = realtime_quotes(tickers)
            if out:
                log.debug("使用 yfinance 延迟报价（仅演练）")
                if hasattr(self.broker, "set_prices"):
                    self.broker.set_prices(out)
        return out

    def can_open(self, ticker: str) -> tuple[bool, str]:
        """差金決済チェック：同一銘柄は当日 1 往復まで。"""
        if ticker in self.st.sold_today:
            return False, "当日已卖出，再买入属差金決済（現物）"
        if self.st.round_trips.get(ticker, 0) >= self.cfg.max_round_trips_per_day:
            return False, f"当日往复已达 {self.cfg.max_round_trips_per_day} 次"
        return True, ""


def _safe(fn, default: float = 0.0) -> float:
    try:
        return float(fn())
    except Exception:                                # noqa: BLE001
        return default
