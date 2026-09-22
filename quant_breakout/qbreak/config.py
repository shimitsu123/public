"""config.py — 全部可调参数集中在这里；其他模块不写死数字。

与原版的差异（改动原因见 REVIEW.md）：
  • 新增「真突破确认」「趋势过滤」「ATR 止损」「流动性过滤」「跳空过滤」等开关，
    默认值尽量贴近原版，方便先复现原结果、再逐项打开对比。
  • 手续费默认值按 2026-09 时点：日本株＝ゼロコース 0%，美股＝0.495% 上限 22 美元。
  • 所有 dataclass 都有 validate()，非法组合在启动时就报错，而不是回测跑完才发现。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


def _from_dict(cls, d: dict[str, Any], *, strict: bool = False):
    """按 dataclass 字段过滤，未知键报错或警告（原版 StrategyParams(**json) 遇到多余键直接崩）。"""
    names = {f.name for f in fields(cls)}
    unknown = set(d) - names
    if unknown:
        msg = f"{cls.__name__} 收到未知参数: {sorted(unknown)}"
        if strict:
            raise ConfigError(msg)
        print(f"[config] 警告 {msg}（已忽略）")
    return cls(**{k: v for k, v in d.items() if k in names})


# ══════════════════════════ 策略参数 ══════════════════════════
@dataclass
class StrategyParams:
    """入场 = ①横盘 ∧ ②MACD 金叉 ∧ ③0轴附近 ∧ ④放量 （∧ 可选过滤器）"""

    # ── ① 横盘（レンジ相場 / consolidation）──
    range_n: int = 60          # 回看窗口 N 日。↑ 要求横盘更久、信号更少、蓄势更充分
    range_x_pct: float = 15.0  # 允许振幅 X%：(N日最高−N日最低)/N日最低 < X%。↓ 箱体越紧

    # ── ② ③ MACD ──
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    macd_zero_band_pct: float = 1.0   # |MACD|/Close×100 < 该值 才算「0 轴附近」

    # ── ④ 放量（出来高 / volume）──
    vol_ma_n: int = 20
    vol_mult: float = 1.5

    # ── 可选过滤器（默认关闭＝复现原版；打开后建议重跑 walk-forward）──
    require_breakout: bool = False
    # 真突破确认：收盘价 > 过去 range_n 日最高（不含当日）。
    # 原版叫「横盘突破」，但四个条件里其实没有任何一条要求价格突破箱体上沿，
    # 抓到的是「突破前的蓄势」。打开这个开关才是字面意义的突破策略。

    breakout_buffer_pct: float = 0.0   # 突破幅度要求 %：Close > 箱顶 × (1+该值)

    trend_ma_n: int = 0
    # 长期趋势过滤：Close > SMA(trend_ma_n)。0=关闭。常用 200。突破策略在下降趋势里胜率显著更差。

    min_price: float = 0.0             # 最低股价过滤（避免低价股）
    min_turnover: float = 0.0          # 最低 20 日平均売買代金（Close×Volume）。0=关闭
    #   日本株建议 1e8（1 亿日元/日）以上，否则 100 股的滑点假设不成立

    # ── 出场（決済 / exit）──
    stop_loss_pct: float = 7.0
    atr_n: int = 14
    atr_stop_mult: float = 0.0
    # ATR 止损倍数：止损价 = 入场价 − ATR(atr_n) × 该倍数。>0 时覆盖 stop_loss_pct。
    # 固定 7% 对低波动大盘股太松、对高波动小盘股太紧；ATR 让止损随个股波动自适应。

    take_profit_pct: float = 25.0      # 0=关闭
    trailing_stop_pct: float = 12.0    # 0=关闭
    trailing_arm_pct: float = 0.0      # 浮盈超过该 % 后才启动跟踪止损。0=立即启动
    max_hold_days: int = 60            # 交易日；0=不限
    exit_on_macd_dead_cross: bool = True
    time_stop_days: int = 0
    time_stop_min_ret_pct: float = 0.0
    # 时间止损：持有满 time_stop_days 个交易日仍未达到 time_stop_min_ret_pct 浮盈则离场。
    # 0=关闭。作用是把"不涨不跌"的死钱释放出来。

    def __post_init__(self):
        """按字段声明强制类型。来自 JSON / numpy / 命令行的值可能是 float 或 np.float64，
        直接传给 pandas 的 rolling(60.0) 会报错 —— 在入口处一次性规整掉。"""
        for f in fields(self):
            v = getattr(self, f.name)
            if f.type in ("int", int) and not isinstance(v, bool):
                setattr(self, f.name, int(round(float(v))))
            elif f.type in ("float", float):
                setattr(self, f.name, float(v))
            elif f.type in ("bool", bool):
                setattr(self, f.name, bool(v))

    def validate(self) -> "StrategyParams":
        if self.range_n < 5:
            raise ConfigError("range_n 至少 5")
        if not 0 < self.range_x_pct <= 500:
            raise ConfigError("range_x_pct 必须在 (0,500]")
        if self.macd_fast >= self.macd_slow:
            raise ConfigError(f"macd_fast({self.macd_fast}) 必须 < macd_slow({self.macd_slow})")
        if min(self.macd_fast, self.macd_signal, self.vol_ma_n, self.atr_n) < 1:
            raise ConfigError("周期参数必须 ≥ 1")
        if self.stop_loss_pct <= 0 and self.atr_stop_mult <= 0:
            raise ConfigError("必须至少有一种止损：stop_loss_pct 或 atr_stop_mult")
        if self.take_profit_pct and self.take_profit_pct <= 0:
            raise ConfigError("take_profit_pct 不能为负")
        return self

    @property
    def warmup_bars(self) -> int:
        """指标预热所需最少 K 线数——数据不足这个数就不该产生任何信号。"""
        return int(max(self.range_n, self.vol_ma_n, self.trend_ma_n,
                       self.macd_slow + self.macd_signal, self.atr_n) + 2)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict, strict: bool = False) -> "StrategyParams":
        return _from_dict(cls, d, strict=strict).validate()

    @classmethod
    def load(cls, path: str | Path, strict: bool = False) -> "StrategyParams | None":
        p = Path(path)
        if not p.exists():
            return None
        return cls.from_dict(json.loads(p.read_text(encoding="utf-8")), strict=strict)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1),
                              encoding="utf-8")


# ══════════════════════════ 成交与费用 ══════════════════════════
@dataclass
class ExecConfig:
    """成交假设（約定前提 / execution assumptions）。回测偏悲观才有参考价值。"""
    market: str = "JP"
    commission_pct: float = 0.0
    # 日本株：楽天「ゼロコース」现货/信用手续费 0 円（需同意 SOR・R クロス）→ 默认 0。
    # 若你仍在「超割コース」等旧コース，改成 0.055 等实际值。
    commission_min: float = 0.0
    commission_max: float = 0.0        # 0=无上限；美股 22（美元）
    slippage_pct: float = 0.10         # 単边滑点 %
    max_entry_gap_pct: float = 3.0
    # T+1 开盘价比信号日收盘高出超过该 % 就放弃这笔（ストップ高／大幅ギャップアップ 追不进去）。
    # 原版无此限制，会把"隔夜跳空 15% 开盘"也当成能成交，严重高估收益。
    stop_fill_mode: str = "next_open"
    # 止损/跟踪止损/止盈的成交假设，**这是回测与实盘差距最大的一项**：
    #   "next_open" : 收盘价触发 → 次日开盘成交。一个每天只跑一次的程序只能做到这个。
    #   "intraday"  : 盘中触及止损价即成交。只有在你**真的**为每笔持仓挂了
    #                 逆指値（ぎゃくさしね / stop order）时才成立。
    # 原版默认按 intraday 计算却没有挂逆指値的实现 —— 回测收益被系统性高估。
    # 想用 intraday，就打开 trader 的 --protective-stop（会自动挂/改逆指値）。

    forbid_same_day_rebuy: bool = True
    # 现货（現物）同一营业日「买→卖→再买」用同一笔资金属于差金決済，原则禁止。
    # 日线策略几乎不会触发，但保留这道闸。

    def fee(self, notional: float) -> float:
        f = abs(notional) * self.commission_pct / 100
        if self.commission_min:
            f = max(f, self.commission_min)
        if self.commission_max:
            f = min(f, self.commission_max)
        return f

    def validate(self) -> "ExecConfig":
        if self.market.upper() not in ("JP", "US"):
            raise ConfigError("market 只支持 JP / US")
        if self.slippage_pct < 0 or self.commission_pct < 0:
            raise ConfigError("费用/滑点不能为负")
        if self.stop_fill_mode not in ("next_open", "intraday"):
            raise ConfigError("stop_fill_mode 只支持 next_open / intraday")
        return self

    @classmethod
    def for_market(cls, market: str) -> "ExecConfig":
        m = market.upper()
        if m == "JP":
            return cls(market="JP", commission_pct=0.0, slippage_pct=0.10).validate()
        # 美股：0.495%（税込）、最低 0 美元、上限 22 美元（2026-09 时点，实际以账户コース为准）
        return cls(market="US", commission_pct=0.495, commission_min=0.0,
                   commission_max=22.0, slippage_pct=0.05).validate()


# ══════════════════════════ 资金管理 ══════════════════════════
@dataclass
class SizingConfig:
    initial_cash: float = 1_000_000
    mode: str = "equity_pct"           # "equity_pct" | "risk_pct"
    position_pct: float = 0.20         # equity_pct 模式：单笔占权益比例
    risk_pct: float = 1.0
    # risk_pct 模式：单笔最大亏损 = 权益 × risk_pct%，据止损距离反推股数。
    # 突破策略的止损距离差异很大，按风险定量比按金额定量更合理。
    max_positions: int = 5
    max_position_pct: float = 0.30     # 单只上限（risk_pct 模式下的兜底）
    cash_buffer_pct: float = 1.0       # 预留现金比例，避免手续费导致余额不足被拒单

    def validate(self) -> "SizingConfig":
        if self.mode not in ("equity_pct", "risk_pct"):
            raise ConfigError("sizing.mode 只支持 equity_pct / risk_pct")
        if not 0 < self.position_pct <= 1:
            raise ConfigError("position_pct 必须在 (0,1]")
        if self.max_positions < 1:
            raise ConfigError("max_positions ≥ 1")
        return self


@dataclass
class BacktestConfig:
    years: int = 5
    exec_cfg: ExecConfig = field(default_factory=ExecConfig)
    sizing: SizingConfig = field(default_factory=SizingConfig)
    start: str | None = None           # "YYYY-MM-DD"，None=全部
    end: str | None = None

    @classmethod
    def for_market(cls, market: str, years: int = 5) -> "BacktestConfig":
        m = market.upper()
        ex = ExecConfig.for_market(m)
        sz = SizingConfig(initial_cash=1_000_000 if m == "JP" else 10_000)
        return cls(years=years, exec_cfg=ex, sizing=sz.validate())


# ══════════════════════════ 风控 ══════════════════════════
@dataclass
class RiskConfig:
    """模拟盘 / 实盘风控（リスク管理）。回测不需要这些，实盘必须有。"""
    daily_max_loss_pct: float = 2.0
    # 当日亏损达到「上一交易日收盘权益」的该 % → 当日熔断，只平不开。
    # 原版拿"今天第一次运行时的权益"当基准，而程序每天只跑一次，
    # 于是基准＝当前权益，亏损恒等于 0，熔断永远不会触发。

    max_drawdown_pct: float = 20.0
    # 从历史最高权益回撤超过该 % → 进入 HALT，需人工删除 var/HALT 文件才恢复。

    max_consecutive_losses: int = 6    # 连续亏损笔数达到该值 → HALT。0=关闭
    max_new_positions_per_day: int = 2 # 每日最多开几笔（避免某天信号扎堆全仓杀入）
    max_order_value: float = 300_000   # 单笔订单金额硬上限（防误单）
    max_positions: int = 5
    require_arm: bool = True           # 实盘必须人工 ARM 才允许发单
    stale_data_max_days: int = 1
    # 最新 K 线日期距今超过该天数（自然日）→ 拒绝交易。防止拿隔夜/隔周的旧数据下单。

    def validate(self) -> "RiskConfig":
        if self.daily_max_loss_pct <= 0:
            raise ConfigError("daily_max_loss_pct 必须 > 0")
        if self.max_order_value <= 0:
            raise ConfigError("max_order_value 必须 > 0")
        return self


@dataclass
class DataConfig:
    provider: str = "yfinance"         # "yfinance" | "csv"
    years: int = 5
    cache_ttl_hours: float = 12.0      # 缓存有效期；原版缓存永不过期，跑着跑着就用旧数据了
    allow_synthetic: bool = False
    # 原版默认 True：yfinance 一失败就静默生成假数据，回测报告照样打印漂亮数字。
    # 这里默认 False —— 宁可报错，也不要「看起来正常的假结果」。
    min_bars: int = 250
    max_daily_move_pct: float = 60.0   # 单日涨跌超过该 % 视为数据异常（未处理的拆股等）
    batch_size: int = 20               # yfinance 批量下载每批只数
    retry_attempts: int = 3            # 下载失败重试次数（指数退避）

    def validate(self) -> "DataConfig":
        if self.provider not in ("yfinance", "csv"):
            raise ConfigError("provider 只支持 yfinance / csv")
        if self.allow_synthetic:
            self.retry_attempts = 1     # 反正要退回合成数据，不必反复等待网络
        return self


# ══════════════════════════ 股票池 ══════════════════════════
UNIVERSE_JP = [
    "7203.T", "6758.T", "8035.T", "6857.T", "6146.T", "6501.T", "6702.T",
    "7011.T", "9984.T", "8306.T", "4063.T", "6981.T", "6367.T", "4568.T",
    "9433.T", "2914.T", "8058.T", "6098.T", "4519.T", "7741.T",
]
UNIVERSE_US = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "AMD", "MU",
    "ORCL", "CRM", "ADBE", "NFLX", "COST", "LLY", "UNH", "JPM", "XOM",
    "CAT", "DE",
]
BENCHMARK = {"JP": "^N225", "US": "^GSPC"}


def universe(market: str) -> list[str]:
    return list(UNIVERSE_JP if market.upper() == "JP" else UNIVERSE_US)


DEFAULT_PARAMS = StrategyParams()
