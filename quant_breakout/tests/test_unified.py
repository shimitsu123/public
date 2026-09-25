"""统一引擎（一个账户、日元 + 美元、日本株 + 美股 + 东证 ETF）：
① 退化情形与原引擎逐笔一致（只有日本 + 1329；只有美股且全用美元）；
② 换汇的时序：日元→美元在美股开盘前完成；美股卖出的美元先换回日元，日本新仓最早在换回后的下一个日本开盘；
③ 统一排名按执行成本：名额不够时日本株优先于要换汇的美股；
④ 核心 ETF 买入不会吃掉当天换汇要用的日元。"""
import numpy as np
import pandas as pd
import pytest

from qbreak.config import BacktestConfig, ExecConfig, StrategyParams
from qbreak.engine import run_backtest
from qbreak.fees import etf_cost
from qbreak.unified import UnifiedConfig, UnifiedEngine

from test_plan_alignment import _synthetic

P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0,
                   stop_loss_pct=7.0)
EX = {"JP": ExecConfig.for_market("JP", "rakuten"), "US": ExecConfig.for_market("US", "rakuten")}


def _cmp_trades(u, e):
    ut = u.trades[u.trades["reason"] != "end"].sort_values(["entry_date", "ticker"])
    et = e.trades[e.trades["reason"] != "end"].copy()
    et["entry_date"] = et["entry_date"].dt.strftime("%Y-%m-%d")
    et = et.sort_values(["entry_date", "ticker"])
    assert list(ut["ticker"]) == list(et["ticker"]) and len(ut) > 3
    assert list(ut["shares"]) == list(et["shares"])


@pytest.mark.parametrize("pct,npos", [(0.34, 3), (0.25, 4)])
def test_jp_only_with_1329_equals_single_market_engine(pct, npos):
    ind, core_df, bear = _synthetic("JP", seed=7)
    ind_all = {**ind, "1329.T": core_df}
    bt = BacktestConfig.for_market("JP", 5, "rakuten")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions = 1_000_000, pct, npos
    bt.sizing.max_position_pct = max(bt.sizing.max_position_pct, pct)
    cc = etf_cost("rakuten", "1329.T", "JP")
    start = core_df.index[60]
    eng = run_backtest(ind_all, P, bt, start=start,
                       core={"ticker": "1329.T", "buffer_pct": 0.0, "band_pct": 10.0, **cc}, core_bear=bear)
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=pct, max_positions=npos,
                        max_position_pct=bt.sizing.max_position_pct, stock_markets=("JP",),
                        core={"1329.T": 1.0}, core_index={"1329.T": "JP"})
    ue = UnifiedEngine(ind_all, cfg, {"JP": P, "US": P}, EX, {"1329.T": cc},
                       bear={"JP": pd.Series(bear, index=core_df.index)})
    res = ue.run(start=start)
    diff = np.abs(res.equity.values - eng.equity.reindex(res.equity.index).values)
    assert np.nanmax(diff) < 1e-6 * 1_000_000, np.nanmax(diff)
    _cmp_trades(res, eng)
    assert len(res.state.core_trades) == eng.extra["core"]["trades"]


def test_us_only_all_usd_equals_single_market_engine():
    """美股、全用美元（不换汇）：执行 / 离场规则与单市场引擎一致。"""
    ind, _, _ = _synthetic("US", seed=11)
    bt = BacktestConfig.for_market("US", 5, "rakuten")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions = 10_000, 0.2, 5
    start = next(iter(ind.values())).index[60]
    eng = run_backtest(ind, P, bt, start=start)
    cfg = UnifiedConfig(capital_jpy=0, position_pct=0.2, max_positions=5, max_position_pct=bt.sizing.max_position_pct,
                        stock_markets=("US",), core={}, core_index={}, usd_keep=True)
    from qbreak.unified import UState
    ue = UnifiedEngine(ind, cfg, {"JP": P, "US": P}, EX, {}, state=UState(cash_jpy=0.0, cash_usd=10_000.0))
    res = ue.run(start=start)
    diff = np.abs(res.equity.values - eng.equity.reindex(res.equity.index).values)
    assert np.nanmax(diff) < 1e-6 * 10_000, np.nanmax(diff)
    _cmp_trades(res, eng)
    assert not res.state.fx_trades


# ─────────────────────────── 换汇时序与统一排名（手工场景）───────────────────────────
def _bars(dates, px, entry_on=(), dead_on=()):
    idx = pd.DatetimeIndex(dates)
    df = pd.DataFrame({"Open": px, "High": np.array(px) * 1.01, "Low": np.array(px) * 0.99, "Close": px,
                       "Volume": 1e6}, index=idx)
    df["entry"] = df.index.isin(pd.DatetimeIndex(entry_on))
    df["dead_cross"] = df.index.isin(pd.DatetimeIndex(dead_on))
    df["atr"], df["climax"] = np.array(px) * 0.02, False
    return df


D = pd.bdate_range("2026-01-05", periods=8)
FX = pd.DataFrame({"Open": 150.0, "Close": 150.0}, index=D)


def test_us_buy_converts_yen_the_same_day_before_us_open():
    ind = {"AAA": _bars(D, [100.0] * 8, entry_on=[D[1]])}                  # 美股信号：D1 收盘
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("US",),
                        core={}, core_index={}, fx_on_jp_holidays=True)
    ue = UnifiedEngine(ind, cfg, {"JP": P, "US": P}, EX, {}, fx=FX)
    ue.run()
    fx0 = ue.st.fx_trades[0]
    assert fx0[0] == str(D[2].date()) and fx0[1] == "JPY>USD" and fx0[3] == 150.25     # TTS = 中值 + 25 銭
    buy = ue.st.trades or []
    pos_or_trade = ue.st.pos.get("AAA") or next(t for t in buy if t["ticker"] == "AAA")
    entry_date = pos_or_trade.entry_date if hasattr(pos_or_trade, "entry_date") else pos_or_trade["entry_date"]
    assert entry_date == str(D[2].date())                                   # 同一天：先换汇，当晚美股开盘买入
    sh = ue.st.pos["AAA"].shares if "AAA" in ue.st.pos else pos_or_trade["shares"]
    assert sh == int(1_000_000 * 0.25 / 150 // (100 * 1.0005))              # 预算 = 日元权益 × 25% ÷ 汇率


def test_us_sale_dollars_go_back_to_yen_before_a_jp_buy():
    """美股 D2 买入、D3 收盘死叉 → D4 美股开盘卖出（得美元）→ D5 换回日元；日本信号 D4 收盘 → D5 开盘时日元还没换回。"""
    us = _bars(D, [100.0] * 8, entry_on=[D[1]], dead_on=[D[3]])
    jp = _bars(D, [1000.0] * 8, entry_on=[D[4], D[5]])
    cfg = UnifiedConfig(capital_jpy=400_000, position_pct=0.9, max_positions=1, max_position_pct=0.95,
                        stock_markets=("JP", "US"), core={}, core_index={}, fx_on_jp_holidays=True)
    ue = UnifiedEngine({"AAA": us, "7777.T": jp}, cfg, {"JP": P, "US": P}, EX, {}, fx=FX)
    ue.run()
    dirs = [(d, k) for d, k, *_ in ue.st.fx_trades]
    assert (str(D[2].date()), "JPY>USD") in dirs and (str(D[5].date()), "USD>JPY") in dirs
    jp_tr = [t for t in ue.st.trades if t["ticker"] == "7777.T"]
    jp_entry = jp_tr[0]["entry_date"] if jp_tr else ue.st.pos["7777.T"].entry_date
    assert jp_entry == str(D[6].date())               # D5 开盘前日元不够（美元 D5 白天才换回）→ D5 收盘的信号 D6 买入


def test_ranking_prefers_jp_over_us_needing_fx_when_one_slot():
    jp = _bars(D, [1000.0] * 8, entry_on=[D[1]])
    us = _bars(D, [100.0] * 8, entry_on=[D[1]])
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=1, stock_markets=("JP", "US"),
                        core={}, core_index={}, fx_on_jp_holidays=True)
    ue = UnifiedEngine({"AAA": us, "7777.T": jp}, cfg, {"JP": P, "US": P}, EX, {}, fx=FX)
    ue.run()
    bought = {t["ticker"] for t in ue.st.trades}                 # run() 结束时按收盘价平仓（统计口径）
    assert bought == {"7777.T"} and not ue.st.fx_trades


def test_core_buy_leaves_yen_for_same_day_conversion():
    us = _bars(D, [100.0] * 8, entry_on=[D[2]])
    etf = _bars(D, [3000.0] * 8)
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.3, max_positions=2, stock_markets=("US",),
                        core={"1655.T": 1.0}, core_index={"1655.T": "US"}, fx_on_jp_holidays=True)
    cc = {"1655.T": etf_cost("rakuten", "1655.T", "JP")}
    ue = UnifiedEngine({"AAA": us, "1655.T": etf}, cfg, {"JP": P, "US": P}, EX, cc, fx=FX)
    ue.run()
    assert any(t["ticker"] == "AAA" for t in ue.st.trades)   # 核心 ETF 先买满、再卖出腾钱 → 换汇 → 美股买入都成立
    assert ue.st.cash_jpy >= 0 and ue.st.cash_usd >= 0
    assert any(k == "JPY>USD" for _, k, *_ in ue.st.fx_trades)
