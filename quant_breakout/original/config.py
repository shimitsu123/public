"""
config.py — 全部可调参数（パラメータ / parameters）集中在这里。
其他模块只 import 这个文件，不要在别处写死数字。
"""
from dataclasses import dataclass, field, asdict


@dataclass
class StrategyParams:
    """策略参数：每个字段后面的注释说明它的作用与调大/调小的影响。"""

    # ── 横盘（レンジ相場 / consolidation）判定 ──
    range_n: int = 60
    # 回看窗口 N 日。越大 → 要求横盘时间越长，信号越少但"蓄势"更充分。

    range_x_pct: float = 15.0
    # 允许振幅 X%：(N日最高 − N日最低) / N日最低 < X%。越小 → 横盘越"紧"，信号越少。

    # ── MACD ──
    macd_fast: int = 12   # 快线 EMA 周期。越小对价格越敏感。
    macd_slow: int = 26   # 慢线 EMA 周期。fast/slow 差距越大，信号越迟钝但更稳。
    macd_signal: int = 9  # 信号线 EMA 周期。越小金叉越早出现，假信号也越多。

    macd_zero_band_pct: float = 1.0
    # "0轴附近"的容忍带：|MACD| / 收盘价 < 该百分比 才算 0 轴附近。
    # 越小 → 只接受几乎贴 0 轴的金叉（真正的横盘末端）；越大 → 放宽。

    # ── 成交量（出来高 / volume）确认 ──
    vol_ma_n: int = 20        # 成交量均线周期。
    vol_mult: float = 1.5     # 当日成交量 > 均量 × vol_mult 才确认。越大 → 要求越强的放量。

    # ── 出场（決済 / exit）规则 ──
    stop_loss_pct: float = 7.0
    # 固定止损 %：入场价下跌该幅度立即平仓。横盘突破失败通常跌回箱体，7% 大致等于箱体半高。

    take_profit_pct: float = 25.0
    # 固定止盈 %。设为 0 表示不用固定止盈，只靠跟踪止损。

    trailing_stop_pct: float = 12.0
    # 跟踪止损 %：从入场后最高价回落该幅度平仓。用于"暴涨"后锁利。0 = 关闭。

    max_hold_days: int = 60
    # 最长持有天数，到期强制平仓，避免资金长期被占用。0 = 不限制。

    exit_on_macd_dead_cross: bool = True
    # 是否在 MACD 死叉（デッドクロス）时平仓。True 更保守。

    def to_dict(self):
        return asdict(self)


@dataclass
class BacktestConfig:
    initial_cash: float = 1_000_000      # 初始资金（日元或美元，视市场）
    position_pct: float = 0.20           # 单笔占总资金比例（20%）→ 同时最多约 5 只
    max_positions: int = 5               # 同时持仓上限
    commission_pct: float = 0.05         # 单边手续费 %（楽天 現物 超割 约 0.055%，美股 0.495%，自行改）
    slippage_pct: float = 0.10           # 滑点 %：按次日开盘价成交再加滑点，避免前视偏差
    lot_size: int = 100                  # 东证单位股数 100；美股填 1
    market: str = "JP"                   # "JP" 或 "US"
    years: int = 5                       # 回测年数


@dataclass
class RiskConfig:
    """模拟盘 / 实盘的风控（リスク管理 / risk management）参数。"""
    daily_max_loss_pct: float = 2.0      # 当日亏损达到总资产该 % → 熔断，停止当日所有开仓
    max_positions: int = 5
    position_pct: float = 0.20
    max_order_value: float = 300_000     # 单笔订单金额硬上限（防误单）
    require_arm: bool = True             # 实盘必须人工 ARM（解锁）才允许发单


# ── 股票池（銘柄ユニバース / universe）──
UNIVERSE_JP = [  # 东证主板流动性较好的示例，请按需替换
    "7203.T", "6758.T", "8035.T", "6857.T", "6146.T", "6501.T", "6702.T",
    "7011.T", "9984.T", "8306.T", "4063.T", "6981.T", "6367.T", "4568.T",
    "9433.T", "2914.T", "8058.T", "6098.T", "4519.T", "7741.T",
]
UNIVERSE_US = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "AMD", "MU",
    "ORCL", "CRM", "ADBE", "NFLX", "COST", "LLY", "UNH", "JPM", "XOM",
    "CAT", "DE",
]

DEFAULT_PARAMS = StrategyParams()
DEFAULT_BT = BacktestConfig()
DEFAULT_RISK = RiskConfig()
