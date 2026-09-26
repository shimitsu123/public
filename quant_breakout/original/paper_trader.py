"""
paper_trader.py — 第3阶段：每日收盘后自动运行的模拟盘（ペーパートレード / paper trading）。

流程（每交易日 15:30 JST 之后跑一次；美股则 06:30 JST）：
  1. 拉取股票池最新日线 → 计算信号（与回测同一函数）
  2. 风控检查：当日亏损熔断（サーキットブレーカー）/ 持仓上限 / 单笔金额上限
  3. 先处理卖出（止损/跟踪/死叉/超时），再处理买入
  4. 全部动作写入 log 与 paper_state.json

运行：python paper_trader.py [JP|US] [--live]   （--live 切换到 RakutenRSSBroker，仅 JP）
定时：Windows 任务计划程序 / cron，每日一次即可（日线策略不需要盘中轮询）
"""
import sys
import json
import logging
import datetime as dt
from config import (DEFAULT_PARAMS, DEFAULT_RISK, StrategyParams, RiskConfig,
                    UNIVERSE_JP, UNIVERSE_US)
from data import load_ohlcv
from strategy import compute_indicators
from broker import PaperBroker, BaseBroker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.FileHandler("trader.log", encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("trader")
DAILY_FILE = "daily_anchor.json"     # 记录每日开盘时权益，用于计算当日亏损


def load_params(path="best_params.json") -> StrategyParams:
    """optimize.py 得出的稳健参数写到 best_params.json 即自动生效；否则用默认。"""
    try:
        with open(path, encoding="utf-8") as f:
            return StrategyParams(**json.load(f))
    except FileNotFoundError:
        return DEFAULT_PARAMS


def daily_loss_pct(broker: BaseBroker) -> float:
    """当日亏损 % = (今日起始权益 − 当前权益)/起始权益。起始权益每天第一次运行时锚定。"""
    today = dt.date.today().isoformat()
    try:
        with open(DAILY_FILE, encoding="utf-8") as f:
            anchor = json.load(f)
    except FileNotFoundError:
        anchor = {}
    if anchor.get("date") != today:
        anchor = {"date": today, "equity": broker.equity()}
        with open(DAILY_FILE, "w", encoding="utf-8") as f:
            json.dump(anchor, f)
    return (anchor["equity"] - broker.equity()) / anchor["equity"] * 100


def run_once(universe: list[str], broker: BaseBroker, p: StrategyParams, risk: RiskConfig,
             lot: int, years: int = 2):
    # ── 1. 数据与信号 ──
    ind = {}
    for t in universe:
        try:
            ind[t] = compute_indicators(load_ohlcv(t, years, use_cache=False), p)
        except Exception as e:  # noqa: BLE001
            log.error("数据失败 %s: %s", t, e)
    if not ind:
        log.error("无数据，退出"); return
    last_prices = {t: float(df["Close"].iloc[-1]) for t, df in ind.items()}
    if hasattr(broker, "set_prices"):
        broker.set_prices(last_prices)

    # ── 2. 风控 ──
    loss = daily_loss_pct(broker)
    halted = loss >= risk.daily_max_loss_pct
    if halted:
        log.warning("★ 熔断：当日亏损 %.2f%% ≥ %.2f%%，今日禁止开仓（仍执行卖出）", loss, risk.daily_max_loss_pct)

    # ── 3. 卖出判断 ──
    for t, pos in list(broker.positions().items()):
        if t not in ind:
            continue
        row = ind[t].iloc[-1]
        px = last_prices[t]
        pos.setdefault("peak", pos["avg_px"])
        pos["peak"] = max(pos["peak"], float(row["High"]))
        hold = (dt.date.today() - dt.date.fromisoformat(pos.get("entry_date", dt.date.today().isoformat()))).days
        reason = None
        if px <= pos["avg_px"] * (1 - p.stop_loss_pct / 100):                       reason = "stop"
        elif p.trailing_stop_pct and px <= pos["peak"] * (1 - p.trailing_stop_pct / 100): reason = "trail"
        elif p.take_profit_pct and px >= pos["avg_px"] * (1 + p.take_profit_pct / 100): reason = "take_profit"
        elif p.exit_on_macd_dead_cross and bool(row["dead_cross"]):                  reason = "dead_cross"
        elif p.max_hold_days and hold >= p.max_hold_days * 1.45:                     reason = "max_hold"  # 自然日≈交易日×1.45
        if reason:
            o = broker.sell(t, pos["qty"])
            log.info("SELL %s qty=%d px=%.1f reason=%s status=%s", t, pos["qty"], o.price, reason, o.status)

    # ── 4. 买入判断 ──
    if not halted:
        eq = broker.equity()
        for t, df in ind.items():
            if not bool(df["entry"].iloc[-1]) or t in broker.positions():
                continue
            if len(broker.positions()) >= risk.max_positions:
                log.info("持仓已满，跳过 %s", t); break
            px = last_prices[t]
            budget = min(eq * risk.position_pct, broker.cash(), risk.max_order_value)
            qty = int(budget // (px * lot)) * lot
            if qty <= 0:
                log.info("资金不足买 1 手 %s (px=%.0f)", t, px); continue
            o = broker.buy(t, qty)
            snap = df.iloc[-1]
            log.info("BUY %s qty=%d px=%.1f range=%.1f%% macd=%.2f volx=%.2f status=%s",
                     t, qty, o.price, snap["range_pct"], snap["macd"],
                     snap["Volume"] / snap["vol_ma"], o.status)

    log.info("完成：权益 %.0f  现金 %.0f  持仓 %s", broker.equity(), broker.cash(),
             {k: v["qty"] for k, v in broker.positions().items()})


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    market = (args[0] if args else "JP").upper()
    live = "--live" in sys.argv
    universe = UNIVERSE_JP if market == "JP" else UNIVERSE_US
    lot = 100 if market == "JP" else 1
    if live:
        if market != "JP":
            raise SystemExit("楽天 RSS 不支持美股，--live 仅限 JP")
        from broker import RakutenRSSBroker
        broker = RakutenRSSBroker(require_arm=DEFAULT_RISK.require_arm)
    else:
        broker = PaperBroker(commission_pct=0.055 if market == "JP" else 0.1)
    run_once(universe, broker, load_params(), DEFAULT_RISK, lot)
