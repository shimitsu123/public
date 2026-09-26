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
                        core={}, core_index={}, fx_on_jp_holidays=True, fx_spread_yen=0.25, fx_before_jp_open=False)
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
                        stock_markets=("JP", "US"), core={}, core_index={}, fx_on_jp_holidays=True,
                        fx_spread_yen=0.25, fx_before_jp_open=False)
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


def test_entry_priority_default_keeps_code_order_and_score_reorders():
    """同一天两个日本信号、只有一个名额：缺省按代码（小的先）；给了分数 → 分数高的先（研究用的钩子，缺省不改行为）。"""
    a, b = _bars(D, [1000.0] * 8, entry_on=[D[1]]), _bars(D, [1000.0] * 8, entry_on=[D[1]])
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=1, stock_markets=("JP",),
                        core={}, core_index={})

    def run(fn=None):
        ue = UnifiedEngine({"1111.T": a, "2222.T": b}, cfg, {"JP": P, "US": P}, EX, {})
        ue.entry_priority_fn = fn
        ue.run()
        return {t["ticker"] for t in ue.st.trades}, ue.skipped["full"]
    assert run() == ({"1111.T"}, 1)
    assert run(lambda t, i: {"1111.T": 0.1, "2222.T": 0.9}[t]) == ({"2222.T"}, 1)
    assert run(lambda t, i: {"1111.T": None, "2222.T": -5.0}[t]) == ({"2222.T"}, 1)      # 没有分数的排在后面
    assert run(lambda t, i: None) == ({"1111.T"}, 1)


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


def test_pre_open_conversion_lets_jp_buy_use_last_nights_dollars():
    """fx_before_jp_open：换汇窗口在 09:00 前 → D4 夜美股卖出的美元 D5 开盘前换回日元，D4 收盘的日本信号 D5 就能买入。"""
    us = _bars(D, [100.0] * 8, entry_on=[D[1]], dead_on=[D[3]])
    jp = _bars(D, [1000.0] * 8, entry_on=[D[4]])
    cfg = UnifiedConfig(capital_jpy=400_000, position_pct=0.9, max_positions=1, max_position_pct=0.95,
                        stock_markets=("JP", "US"), core={}, core_index={}, fx_on_jp_holidays=True,
                        fx_before_jp_open=True, fx_spread_yen=0.25)
    ue = UnifiedEngine({"AAA": us, "7777.T": jp}, cfg, {"JP": P, "US": P}, EX, {}, fx=FX)
    ue.run()
    jp_tr = [t for t in ue.st.trades if t["ticker"] == "7777.T"]
    assert jp_tr and jp_tr[0]["entry_date"] == str(D[5].date())
    back = [x for x in ue.st.fx_trades if x[1] == "USD>JPY" and x[0] == str(D[5].date())]
    assert back and back[0][3] == 149.75 and back[0][2] > 2000                     # 卖出所得全部换回；TTB = 中值 − 25 銭


def test_pending_plan_across_other_markets_holiday_keeps_its_money():
    """日本假日（只有美股开市）那天的决策：前一天定下、还没成交的日本买入计划先占住日元，不会把同一笔钱再分给新信号。"""
    jd = D.delete(2)                                          # D2 日本休市
    jp = _bars(jd, [1000.0] * 7, entry_on=[D[1]])
    jp2 = _bars(jd, [1000.0] * 7)
    us = _bars(D, [100.0] * 8, entry_on=[D[2]])                # 美股 D2 收盘信号
    cfg = UnifiedConfig(capital_jpy=300_000, position_pct=0.9, max_positions=2, max_position_pct=0.95,
                        stock_markets=("JP", "US"), core={}, core_index={}, fx_on_jp_holidays=True)
    ue = UnifiedEngine({"7777.T": jp, "8888.T": jp2, "AAA": us}, cfg, {"JP": P, "US": P}, EX, {}, fx=FX)
    ue.run()
    assert min(h[2] for h in ue.st.history) >= -1e-6 and min(h[3] for h in ue.st.history) >= -1e-6   # 现金从不为负
    jp_tr = [t for t in ue.st.trades if t["ticker"] == "7777.T"]
    assert jp_tr and jp_tr[0]["entry_date"] == str(D[3].date())                                   # 跨过假日照样成交


# ─────────────────────────── 模拟盘：除息 / 拆股（行情是复权价，持仓按真实价格记账）───────────────────────────
def _held_state(**kw):
    from qbreak.unified import UPos, UState
    pos = {"7777.T": UPos("7777.T", "JP", 100, 1000.0, "2026-01-06", 930.0, 1050.0, 1000.0, hold=2, armed=True)}
    return UState(cash_jpy=100_000.0, pos=pos, last_date=str(D[3].date()), **kw)


def test_apply_corp_action_split_dividend_idempotent():
    from qbreak.corpactions import DIV_NET
    from qbreak.unified import UPos, apply_corp_action
    st = _held_state(core_units={"1329.T": 73}, plan={"6666.T": [2000.0, 50, "2026-01-08"]})
    assert "100→200" in apply_corp_action(st, "7777.T", "2026-01-09", split=2.0, div_net=DIV_NET["JP"])
    p = st.pos["7777.T"]
    assert (p.shares, p.entry_px, p.stop_px, p.peak, p.last_close) == (200, 500.0, 465.0, 525.0, 500.0)
    assert apply_corp_action(st, "7777.T", "2026-01-09", split=2.0) is None           # 同一天只处理一次
    apply_corp_action(st, "7777.T", "2026-01-12", dividend=20.0, div_net=DIV_NET["JP"])
    assert st.cash_jpy == pytest.approx(100_000 + 20 * 200 * DIV_NET["JP"]) and (p.stop_px, p.peak) == (445.0, 505.0)
    apply_corp_action(st, "1329.T", "2026-01-12", dividend=100.0, div_net=DIV_NET["JP"])   # 核心 ETF 的分配金
    assert st.cash_jpy == pytest.approx(100_000 + (20 * 200 + 100 * 73) * DIV_NET["JP"])
    apply_corp_action(st, "6666.T", "2026-01-13", split=5.0)                             # 计划单：股数 ×5、信号价 ÷5
    assert st.plan["6666.T"][:2] == [400.0, 250]
    st.pos["AAA"] = UPos("AAA", "US", 10, 100.0, "2026-01-06", 93.0, 100.0, 100.0)
    apply_corp_action(st, "AAA", "2026-01-13", dividend=1.0, div_net=DIV_NET["US"])      # 美股分红进美元
    assert st.cash_usd == pytest.approx(10 * DIV_NET["US"])
    assert apply_corp_action(st, "9999.T", "2026-01-13", dividend=5.0) is None           # 没持有：什么都不做
    assert len(st.corp_log) == 5


def _split_engine(state):
    jp = _bars(D, [500.0] * 8)                               # 复权后的行情：拆股（D4）前的价格已被 yfinance 除以 2
    cfg = UnifiedConfig(capital_jpy=0, position_pct=0.25, max_positions=4, stock_markets=("JP",), core={}, core_index={})
    return UnifiedEngine({"7777.T": jp}, cfg, {"JP": P, "US": P}, EX, {}, state=state)


def test_sim_step_after_split_does_not_fake_a_stop():
    from qbreak.corpactions import FakeActions
    prov = FakeActions({"7777.T": [{"date": str(D[4].date()), "dividend": 0.0, "split": 2.0},
                                   {"date": str(D[2].date()), "dividend": 30.0, "split": 0.0}]})  # D2 在上次处理之前：不重复
    ue = _split_engine(_held_state())
    ue.prime(4)
    notes = ue.apply_corp_actions(4, prov)
    ue.step(4)
    assert len(notes) == 1 and "100→200" in notes[0]
    assert not ue.st.pending_exit and ue.st.pos["7777.T"].shares == 200
    assert ue.st.history[-1][1] == pytest.approx(100_000 + 200 * 500.0)                   # 权益没有凭空腰斩
    bad = _split_engine(_held_state())                                                     # 对照：不补拆股 → 假止损
    bad.prime(4)
    bad.step(4)
    assert bad.st.pending_exit.get("7777.T") == "stop" and bad.st.history[-1][1] == pytest.approx(150_000)


def test_sim_split_inferred_from_prices_when_actions_unavailable():
    class Down:
        def actions(self, ticker):
            raise ConnectionError("blocked")
    ue = _split_engine(_held_state())
    ue.prime(4)
    notes = ue.apply_corp_actions(4, Down())
    assert any("推断拆股 1:2" in n for n in notes) and ue.st.pos["7777.T"].shares == 200



def test_usd_kept_while_other_us_candidates_are_imminent():
    """美股 AAA D4 卖出得美元；另一只 BBB 在 D4 收盘「即将触发」→ usd_keep_imminent 时 D5 不换回日元。"""
    us = _bars(D, [100.0] * 8, entry_on=[D[1]], dead_on=[D[3]])
    bbb = _bars(D, [50.0] * 8)
    for c, v in (("macd", -0.01), ("macd_sig", 0.0), ("is_range", True), ("near_zero", True), ("vol_ratio", 1.2)):
        bbb[c] = v
    bbb.loc[bbb.index != D[4], "vol_ratio"] = 0.5                     # 只有 D4 满足「即将」
    from qbreak.unified import imminent_flags
    assert list(imminent_flags(bbb)) == [d == D[4] for d in D]
    runs = {}
    for keep in (False, True):
        cfg = UnifiedConfig(capital_jpy=400_000, position_pct=0.9, max_positions=1, max_position_pct=0.95,
                            stock_markets=("US",), core={}, core_index={}, fx_on_jp_holidays=True,
                            fx_spread_yen=0.25, fx_before_jp_open=False, usd_keep_imminent=keep)
        ue = UnifiedEngine({"AAA": us, "BBB": bbb}, cfg, {"JP": P, "US": P}, EX, {}, fx=FX)
        ue.run()
        runs[keep] = [(d, k) for d, k, *_ in ue.st.fx_trades]
    assert (str(D[5].date()), "USD>JPY") in runs[False]
    assert not any(k == "USD>JPY" and d == str(D[5].date()) for d, k in runs[True])
