"""收盘规划 / 次日开盘成交：回测引擎与实盘流水线（run_once + PaperBroker）逐日一致。

V4（scripts/verify_all.py）用真实数据对照不含核心仓位的现行配置；这里用确定的合成数据，
连同核心指数仓位、熊市清空、多笔同日入场、排队卖出腾出的名额与资金一起对照。
"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

import qbreak.trader as trader_mod
from conftest import make_indicator_frame
from qbreak.brokers import PaperBroker
from qbreak.config import BacktestConfig, DataConfig, ExecConfig, RiskConfig, SizingConfig, StrategyParams
from qbreak.core import CORE_COST
from qbreak.engine import run_backtest
from qbreak.trader import run_once

P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0,
                   stop_loss_pct=7.0)


def _bt(market: str, cash: float, pct: float, n: int, slip: float | None = None) -> BacktestConfig:
    bt = BacktestConfig.for_market(market, 5)
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions = cash, pct, n
    bt.sizing.max_position_pct = max(bt.sizing.max_position_pct, pct)
    if slip is not None:
        bt.exec_cfg.slippage_pct = slip
    return bt


# ─────────────────────────── 引擎：股数在信号日收盘定 ───────────────────────────
def test_shares_sized_at_signal_close_not_next_open():
    """100 万 × 34% = 34 万；信号日收盘 1700 → 200 股。开盘 1710 时按开盘价会变成 100 股（旧行为）。"""
    rows = [(1700.0, 1702.0, 1698.0, 1700.0, 1e6)] * 30 + [(1710.0, 1720.0, 1705.0, 1712.0, 1e6)] * 10
    ind = {"A.T": make_indicator_frame(rows, entries=[29])}
    r = run_backtest(ind, P, _bt("JP", 1_000_000, 0.34, 3, slip=0.0))
    assert r.trades.iloc[0]["shares"] == 200 and r.trades.iloc[0]["entry_px"] == pytest.approx(1710.0)


def test_same_day_entries_share_the_estimated_cash():
    """三个信号同日：各 50% → 第一笔 50 万，第二笔只剩约 49.5 万（缓冲 1%），第三笔没钱 → 不排队。"""
    flat = [(1000.0, 1001.0, 999.0, 1000.0, 1e6)] * 40
    ind = {t: make_indicator_frame(flat, entries=[29]) for t in ("A.T", "B.T", "C.T")}
    r = run_backtest(ind, P, _bt("JP", 1_000_000, 0.5, 3, slip=0.0))
    got = dict(zip(r.trades["ticker"], r.trades["shares"]))
    assert got == {"A.T": 500, "B.T": 400}                          # 49.5 万 / 1000 → 400 股（100 股单元）
    assert r.skipped["cash"] + r.skipped["lot"] >= 1


def test_queued_exit_frees_slot_and_cash_for_next_open():
    """上限 2 只：持有 A（当天收盘死叉 → 明天开盘卖）+ 空位 1；B、C 同日信号 → 规划 2 笔（A 的名额与资金可用）。"""
    flat = [(1000.0, 1001.0, 999.0, 1000.0, 1e6)] * 40
    ind = {"A.T": make_indicator_frame(flat, entries=[10], deads=[29]),
           "B.T": make_indicator_frame(flat, entries=[29]),
           "C.T": make_indicator_frame(flat, entries=[29])}
    r = run_backtest(ind, P, _bt("JP", 1_000_000, 0.45, 2, slip=0.0))
    t = r.trades.set_index("ticker")
    assert t.loc["A.T", "reason"] == "dead_cross"
    assert {"B.T", "C.T"} <= set(t.index)                            # 两笔都在 A 卖出的同一个开盘买入
    assert t.loc["B.T", "entry_date"] == t.loc["C.T", "entry_date"] == t.loc["A.T", "exit_date"]


# ─────────────────────────── 实盘 = 回测（合成数据，含核心仓位）───────────────────────────
def _synthetic(market: str, seed: int, n: int = 200):
    rng = np.random.default_rng(seed)
    names = ["A", "B", "C", "D", "E", "F"]
    suf = ".T" if market == "JP" else ""
    idx = pd.bdate_range("2025-01-06", periods=n)
    base = 1500.0 if market == "JP" else 80.0
    ind = {}
    for k, nm in enumerate(names):
        r = rng.normal(0.0004, 0.018, n)
        c = base * (1 + 0.3 * k) * np.exp(np.cumsum(r))
        o = c * np.exp(rng.normal(0, 0.006, n))
        h, lo = np.maximum(o, c) * 1.004, np.minimum(o, c) * 0.996
        df = pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": 1e6}, index=idx)
        ent = rng.random(n) < 0.035
        ent[:60] = False
        dead = rng.random(n) < 0.04
        df["entry"], df["dead_cross"] = ent, dead
        df["atr"], df["climax"] = c * 0.02, False
        df["range_pct"], df["vol_ratio"] = 8.0, 2.0
        ind[nm + suf] = df
    cr = rng.normal(0.0003, 0.011, n)
    cc = (6800.0 if market == "JP" else 550.0) * np.exp(np.cumsum(cr))
    co = cc * np.exp(rng.normal(0, 0.003, n))
    core = pd.DataFrame({"Open": co, "High": np.maximum(co, cc) * 1.002, "Low": np.minimum(co, cc) * 0.998,
                         "Close": cc, "Volume": 1e9, "entry": False, "dead_cross": False, "atr": np.nan,
                         "climax": False, "range_pct": np.nan, "vol_ratio": np.nan}, index=idx)
    bear = np.zeros(n, bool)
    bear[130:150] = True                                              # 中间一段熊市：核心仓位清空
    return ind, core, bear


@pytest.mark.parametrize("market,cash,pct,npos", [("JP", 1_000_000, 0.34, 3), ("US", 6_336.37, 0.125, 8)])
def test_live_pipeline_equals_engine_with_core(monkeypatch, market, cash, pct, npos):
    ind, core_df, bear = _synthetic(market, seed=7 if market == "JP" else 11)
    core_t = "CORE.T" if market == "JP" else "CORE"
    ind_all = {**ind, core_t: core_df}
    bt = _bt(market, cash, pct, npos)
    ccfg = {"ticker": core_t, "buffer_pct": 0.0, "band_pct": 10.0, **CORE_COST[market]}
    start = ind_all[core_t].index[60]
    eng = run_backtest(ind_all, P, bt, start=start, core=ccfg, core_bear=bear)

    cur = {"d": None}
    monkeypatch.setattr(trader_mod, "load_universe",
                        lambda tickers, cfg=None, use_cache=True: {t: ind_all[t].loc[:cur["d"]] for t in tickers
                                                                  if t in ind_all})
    monkeypatch.setattr(trader_mod, "compute_indicators", lambda df, p, ic=None: df)
    ex = bt.exec_cfg
    broker = PaperBroker(initial_cash=cash, exec_cfg=ex, market=market)
    risk = RiskConfig(daily_max_loss_pct=100, max_drawdown_pct=100, max_consecutive_losses=0,
                      max_new_positions_per_day=npos, max_order_value=1e12, max_positions=npos, require_arm=False)
    sizing = SizingConfig(initial_cash=cash, position_pct=pct, max_positions=npos,
                          max_position_pct=bt.sizing.max_position_pct)
    dates = ind_all[core_t].index
    eq_live = {}
    for k in range(60, len(dates)):
        d = dates[k]
        cur["d"] = d
        run_once(list(ind), broker, P, risk, sizing, DataConfig(provider="csv", years=5, min_bars=10),
                 market=market, today=d.date(), exec_cfg=ex, allow_stale=True,
                 core={**ccfg, "bear": bool(bear[k])})
        eq_live[d] = broker.equity()
    le = pd.Series(eq_live)
    diff = np.abs(le.values - eng.equity.reindex(le.index).values)
    assert np.nanmax(diff) < 1e-6 * cash, (np.nanmax(diff), le.index[int(np.nanargmax(diff))])
    st = broker.state
    live_tr = pd.DataFrame(st["closed_trades"])
    eng_tr = eng.trades[eng.trades["reason"] != "end"]
    assert len(live_tr) == len(eng_tr) > 3
    assert list(live_tr.sort_values(["entry_date", "ticker"])["shares"]) == \
        list(eng_tr.assign(entry_date=eng_tr["entry_date"].dt.strftime("%Y-%m-%d"))
             .sort_values(["entry_date", "ticker"])["shares"])
    assert st.get("core_trades"), "核心仓位应有减仓记录（入场腾资金 / 熊市清空）"
    assert eng.extra["core"]["trades"] > 5
    # 熊市区间结束时核心仓位为 0（清空），牛市恢复后重新买回
    assert core_t in broker.positions()


def test_paper_broker_fill_order_and_lot_reduction():
    """成交顺序：个股卖 → 核心卖 → 个股买（现金不够按单元减）→ 核心买（买不起的部分放弃）。"""
    ex = ExecConfig(market="JP", commission_pct=0.0, slippage_pct=0.0, max_entry_gap_pct=3.0)
    b = PaperBroker(initial_cash=0.0, exec_cfg=ex, market="JP")
    b.state["positions"] = {"X.T": {"qty": 100, "avg_px": 1000.0, "peak": 1000.0, "stop_px": 0.0,
                                    "entry_date": "2026-01-01", "hold_bars": 1, "last_bar": "2026-01-05"},
                            "CORE.T": {"qty": 50, "avg_px": 7000.0, "peak": 7000.0, "stop_px": 0.0,
                                       "entry_date": "2026-01-01", "hold_bars": 1, "last_bar": "2026-01-05"}}
    b.set_prices({"X.T": 1000.0, "CORE.T": 7000.0, "Y.T": 2000.0})
    bar = "2026-01-05"
    b.buy("CORE.T", 10, client_id="c-buy", ref_px=7000.0, bar=bar, extra={"core": True, "lot": 1, "cost": {}})
    b.buy("Y.T", 300, client_id="y-buy", ref_px=2000.0, bar=bar, extra={"lot": 100, "cap": 3, "excl": ["CORE.T"]})
    b.sell("CORE.T", 40, client_id="c-sell", ref_px=7000.0, bar=bar, extra={"core": True, "cost": {}})
    b.sell("X.T", 100, client_id="x-sell", ref_px=1000.0, bar=bar)
    out = b.fill_pending({"X.T": 1000.0, "CORE.T": 7000.0, "Y.T": 2050.0}, "2026-01-06")
    seq = [(o.side, o.ticker, o.status, o.filled_qty) for o in out]
    # 卖出 10 万 + 28 万 = 38 万现金；Y 300 股 ×2050 = 61.5 万 → 减到 100 股（20.5 万）；剩 17.5 万买核心 10 口 = 7 万
    assert seq == [("SELL", "X.T", "FILLED", 100), ("SELL", "CORE.T", "FILLED", 40),
                   ("BUY", "Y.T", "FILLED", 100), ("BUY", "CORE.T", "FILLED", 10)]
    assert b.cash() == pytest.approx(380_000 - 205_000 - 70_000)
    assert [t["ticker"] for t in b.state["closed_trades"]] == ["X.T"]           # 核心减仓不进策略成交记录
    assert [t["ticker"] for t in b.state["core_trades"]] == ["CORE.T"]
    assert b.state["closed_trades"][0]["exit_date"] == "2026-01-06"             # 日期 = 成交 K 线日


def test_sim_tier_switch_and_core_cfg(isolated_home):
    """sim-tier 只改 sim.json 的市场段；_core_cfg 按代码取成本（SPYM 买卖都收费），熊市时 bear=True。"""
    import argparse
    import json

    import run
    from qbreak.core import SPYM_COST
    (isolated_home / "sim.json").write_text(json.dumps({
        "start": "2026-09-24", "end": "2026-12-24", "markets": ["JP", "US"],
        "jp": {"initial_cash": 1_000_000, "position_pct": 0.34, "max_positions": 3},
        "us": {"initial_cash": 6336.37, "position_pct": 0.2, "max_positions": 5}}), encoding="utf-8")
    assert run.cmd_sim_tier(argparse.Namespace(tier="aggressive", markets="JP,US")) == 0
    cfg = json.loads((isolated_home / "sim.json").read_text(encoding="utf-8"))
    assert (cfg["jp"]["position_pct"], cfg["jp"]["max_positions"], cfg["jp"]["tier"]) == (0.25, 4, "aggressive")
    assert cfg["us"]["breakout"] is False and cfg["us"]["core"]["ticker"] == "SPYM"
    assert cfg["us"]["initial_cash"] == 6336.37                                # 其他字段不动
    c = run._core_cfg("US", cfg["us"]["core"], {"state": "bear"})
    assert c["bear"] is True and c["buy_fee_pct"] == SPYM_COST["buy_fee_pct"] == 0.495
    assert run._core_cfg("JP", cfg["jp"]["core"], {"state": "bull"})["bear"] is False
    assert run._core_cfg("JP", {"enabled": False}, None) is None
    assert run.cmd_sim_tier(argparse.Namespace(tier="safe", markets="JP")) == 0
    cfg = json.loads((isolated_home / "sim.json").read_text(encoding="utf-8"))
    assert cfg["jp"]["core"]["enabled"] is False and cfg["us"]["tier"] == "aggressive"
