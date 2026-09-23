"""risk.py — 实盘/模拟盘风控（リスク管理）。回测不用，实盘必须有。

原版最关键的 bug：当日亏损熔断（サーキットブレーカー）拿「今天第一次运行时的权益」
当基准，而程序设计上每天只跑一次 —— 基准恰好等于当前权益，亏损恒为 0.00%，
熔断永远不会触发。这里改成用**上一交易日收盘权益**做基准，并持久化。

四道闸：
  1. 当日亏损熔断      → 当日只平不开
  2. 总回撤 HALT       → 写 var/HALT 文件，需人工删除才恢复
  3. 连续亏损 HALT     → 同上
  4. 单笔/单日笔数上限 → 拒绝超限订单
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from . import paths
from .config import RiskConfig
from .utils import read_json, setup_logging, write_json

log = setup_logging("risk")


@dataclass
class RiskState:
    prev_close_equity: float = 0.0
    prev_session_date: str = ""
    peak_equity: float = 0.0
    consecutive_losses: int = 0
    opened_today: int = 0
    today: str = ""
    halted_reason: str = ""

    @classmethod
    def load(cls, path=None) -> "RiskState":
        d = read_json(path or (paths.state_dir() / "risk_state.json"), {})
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def save(self, path=None) -> None:
        write_json(path or (paths.state_dir() / "risk_state.json"), self.__dict__)


@dataclass
class RiskDecision:
    allow_open: bool
    halted: bool
    reasons: list[str] = field(default_factory=list)
    daily_loss_pct: float = 0.0
    drawdown_pct: float = 0.0

    def __str__(self):
        head = "HALT" if self.halted else ("只平不开" if not self.allow_open else "正常")
        return f"[风控:{head}] 当日 {self.daily_loss_pct:+.2f}%  回撤 {self.drawdown_pct:+.2f}%" + \
               (f"  原因: {'; '.join(self.reasons)}" if self.reasons else "")


class RiskManager:
    """每个市场一份状态（peak_equity 等不能跨市场混用：¥100 万和 $6,000 放一起会误判 -99% 回撤）。
    自动触发的 HALT 写 var/HALT_<market>；人工的全局 var/HALT 仍然拦所有市场。"""

    def __init__(self, cfg: RiskConfig, state_path=None, market: str = ""):
        self.cfg = cfg.validate()
        self.market = market.upper()
        name = f"risk_state_{self.market}.json" if self.market else "risk_state.json"
        self.path = state_path or (paths.state_dir() / name)
        self.st = RiskState.load(self.path)

    def halt_file(self):
        return paths.home() / (f"HALT_{self.market}" if self.market else "HALT")

    # ── 会话开始：确定当日基准 ──
    def begin(self, equity: float, today: dt.date | None = None) -> RiskDecision:
        today = today or dt.date.today()
        ts = today.isoformat()
        if self.st.today != ts:                       # 新的一天
            self.st.today = ts
            self.st.opened_today = 0
            if not self.st.prev_close_equity:         # 第一次运行：用当前权益初始化
                self.st.prev_close_equity = equity
                self.st.prev_session_date = ts
        self.st.peak_equity = max(self.st.peak_equity or equity, equity)

        base = self.st.prev_close_equity or equity
        daily = (equity - base) / base * 100 if base else 0.0
        ddp = (equity - self.st.peak_equity) / self.st.peak_equity * 100 if self.st.peak_equity else 0.0

        reasons: list[str] = []
        halted = False
        for hf in {paths.halt_file(), self.halt_file()}:
            if hf.exists():
                halted = True
                reasons.append(f"存在 HALT 文件（{hf}），删除后才会恢复")
        if self.st.halted_reason:
            halted = True
            reasons.append(f"历史 HALT: {self.st.halted_reason}")
        if self.cfg.max_drawdown_pct and ddp <= -abs(self.cfg.max_drawdown_pct):
            halted = True
            self._trip(f"总回撤 {ddp:.2f}% 触及上限 {self.cfg.max_drawdown_pct}%")
            reasons.append(self.st.halted_reason)
        if (self.cfg.max_consecutive_losses
                and self.st.consecutive_losses >= self.cfg.max_consecutive_losses):
            halted = True
            self._trip(f"连续亏损 {self.st.consecutive_losses} 笔")
            reasons.append(self.st.halted_reason)

        allow = not halted
        if allow and daily <= -abs(self.cfg.daily_max_loss_pct):
            allow = False
            reasons.append(f"当日亏损 {daily:.2f}% ≥ 熔断线 {self.cfg.daily_max_loss_pct}% → 今日只平不开")
        self.st.save(self.path)
        return RiskDecision(allow_open=allow, halted=halted, reasons=reasons,
                            daily_loss_pct=daily, drawdown_pct=ddp)

    def _trip(self, reason: str) -> None:
        self.st.halted_reason = reason
        self.halt_file().write_text(
            f"{dt.datetime.now().isoformat()}\n{reason}\n"
            "删除本文件即可解除停机。解除前请先弄清楚发生了什么。\n", encoding="utf-8")
        log.error("★★★ 触发 HALT：%s", reason)

    # ── 单笔订单检查 ──
    def check_order(self, notional: float, n_positions: int) -> tuple[bool, str]:
        if notional > self.cfg.max_order_value:
            return False, f"单笔金额 {notional:,.0f} > 上限 {self.cfg.max_order_value:,.0f}"
        if n_positions >= self.cfg.max_positions:
            return False, f"持仓数已达上限 {self.cfg.max_positions}"
        if (self.cfg.max_new_positions_per_day
                and self.st.opened_today >= self.cfg.max_new_positions_per_day):
            return False, f"今日新开仓已达上限 {self.cfg.max_new_positions_per_day}"
        return True, ""

    def on_open(self) -> None:
        self.st.opened_today += 1
        self.st.save(self.path)

    def on_trade_closed(self, pnl: float) -> None:
        self.st.consecutive_losses = self.st.consecutive_losses + 1 if pnl <= 0 else 0
        self.st.save(self.path)

    # ── 会话结束：把今天的收盘权益存成明天的基准 ──
    def end(self, equity: float, today: dt.date | None = None) -> None:
        today = today or dt.date.today()
        self.st.prev_close_equity = equity
        self.st.prev_session_date = today.isoformat()
        self.st.peak_equity = max(self.st.peak_equity or equity, equity)
        self.st.save(self.path)

    def reset_halt(self) -> None:
        self.st.halted_reason = ""
        self.st.consecutive_losses = 0
        self.st.save(self.path)
        for hf in {paths.halt_file(), self.halt_file()}:
            if hf.exists():
                hf.unlink()
        log.warning("HALT 已人工解除")
