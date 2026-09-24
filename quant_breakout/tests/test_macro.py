"""宏观因子层 / 板块倾斜 / 事件窗口 / 引擎倍数矩阵。"""
import datetime as dt
import json

import numpy as np
import pandas as pd

from conftest import make_indicator_frame
from qbreak import paths
from qbreak.calendar_us import is_trading_day as us_td, next_trading_day as us_next
from qbreak.config import BacktestConfig, StrategyParams
from qbreak.engine import run_backtest
from qbreak.macro import (MacroEvent, MacroFeatures, MacroOverlay, blocked_fill_dates, build_entry_mult,
                          features_at, features_frame, load_events, load_overlay, macro_mult, sector_mult,
                          ticker_mults)
from qbreak.sectors import SECTOR_JP, SECTOR_US, sector_of
from qbreak.universes import NIKKEI225, US_BROAD, nikkei225


def test_every_pool_ticker_has_a_sector():
    assert all(c in SECTOR_JP for c in NIKKEI225)
    assert all(t in SECTOR_US for t in US_BROAD)
    assert sector_of("8031.T", "JP") == "trading" and sector_of("9101.T", "JP") == "shipping"
    assert sector_of("NVDA", "US") == "semis" and sector_of("CVX", "US") == "energy"


def test_jp_pool_excludes_airlines_and_land_transport_but_keeps_shipping():
    u = nikkei225()
    assert "9201.T" not in u and "9202.T" not in u and "9001.T" not in u and "9064.T" not in u
    assert "9101.T" in u and "8031.T" in u
    assert len(nikkei225(exclude=False)) == 225


def test_macro_mult_thresholds_take_min():
    calm = MacroFeatures(brent=80, brent_chg20_pct=2, us10y=4.2, vix=14, usdjpy=150)
    assert macro_mult(calm, None, "JP") == (1.0, []) and macro_mult(calm, None, "US") == (1.0, [])
    hot = MacroFeatures(brent=103, brent_chg20_pct=4, us10y=5.11, vix=15.2, usdjpy=158.3)
    m_jp, fired_jp = macro_mult(hot, None, "JP")
    m_us, fired_us = macro_mult(hot, None, "US")
    assert m_jp == 0.75 and m_us == 0.75                     # 10Y≥5 两市场 0.75；Brent≥100 只压日本
    assert any("Brent" in s for s in fired_jp) and not any("Brent" in s for s in fired_us)
    panic = MacroFeatures(vix=31)
    assert macro_mult(panic, None, "US")[0] == 0.0 and macro_mult(panic, None, "JP")[0] == 0.5
    ov = MacroOverlay(as_of="2026-09-24", hy_oas_bp=345, breadth_pct=24, fed_hike_prob=70, jgb10y=3.1, boj_hike_prob=70)
    assert macro_mult(calm, ov, "US")[0] == 0.5              # HY 利差 ≥330 → 美股 0.5
    assert macro_mult(calm, ov, "JP")[0] == 0.75             # JGB ≥3.05 / BOJ 窗口 → 日本 0.75
    ov.stale = True
    assert macro_mult(calm, ov, "US")[0] == 1.0              # 过期的判断层不参与


def test_sector_tilt_rules():
    oil = MacroFeatures(brent=105, us10y=4.5)
    assert sector_mult("chemical", oil) == (0.5, "油价高位：chemical ×0.5")
    assert sector_mult("airline", oil)[0] == 0.0 and sector_mult("food", oil)[0] == 0.75
    assert sector_mult("energy", oil)[0] == 1.0 and "受益" in sector_mult("shipping", oil)[1]
    assert sector_mult("semis", oil)[0] == 1.0
    rates = MacroFeatures(brent=80, us10y=5.05)
    assert sector_mult("semis", rates)[0] == 0.5 and sector_mult("software_internet", rates)[0] == 0.5
    assert sector_mult("bank", rates)[0] == 1.0
    both = MacroFeatures(brent=105, us10y=5.3)
    assert sector_mult("chemical", both)[0] == 0.5 and sector_mult("semis", both)[0] == 0.5
    t = ticker_mults(["NVDA", "CVX", "LIN"], "US", both)
    assert t["NVDA"][0] == 0.5 and t["CVX"][0] == 1.0 and t["LIN"][0] == 0.5


def test_features_frame_and_lookup_no_lookahead():
    idx = pd.bdate_range("2026-01-01", periods=30)
    series = {"brent": pd.Series(np.linspace(80, 120, 30), index=idx), "vix": pd.Series(15.0, index=idx[::2])}
    f = features_frame(series)
    assert list(f.columns) == ["brent", "us10y", "vix", "usdjpy", "brent_chg20_pct"] or "brent_chg20_pct" in f.columns
    assert f["vix"].isna().sum() == 0                        # 缺日前向填充
    at = features_at(f, idx[25])
    assert at.date == str(idx[25].date()) and at.brent_chg20_pct is not None and at.us10y is None
    assert features_at(f, idx[0] - pd.Timedelta(days=5)).brent is None


def test_event_reaction_and_blocked_dates():
    fomc = MacroEvent(dt.date(2026, 10, 28), "FOMC", "US")
    boj = MacroEvent(dt.date(2026, 10, 30), "BOJ", "JP")
    nfp = MacroEvent(dt.date(2026, 10, 2), "NFP", "US")          # 周五 21:30 JST
    assert fomc.reaction_date("US") == dt.date(2026, 10, 28) and fomc.reaction_date("JP") == dt.date(2026, 10, 29)
    assert boj.reaction_date("JP") == dt.date(2026, 10, 30) and boj.reaction_date("US") == dt.date(2026, 10, 30)
    assert nfp.reaction_date("JP") == dt.date(2026, 10, 5)
    b_jp = blocked_fill_dates([fomc, boj, nfp], "JP")
    assert {d.isoformat() for d in b_jp} == {"2026-10-02", "2026-10-28", "2026-10-29", "2026-10-30"}
    b_us = blocked_fill_dates([fomc, boj, nfp], "US")
    assert {d.isoformat() for d in b_us} == {"2026-10-01", "2026-10-27", "2026-10-28", "2026-10-29"}
    assert fomc.exposed_sessions("JP") == [dt.date(2026, 10, 28)]      # 03:00 JST 发布，10/29 开盘已知
    assert nfp.exposed_sessions("US") == [dt.date(2026, 10, 1)]        # 盘前发布，10/2 开盘已知
    assert not us_td(dt.date(2026, 11, 26)) and us_next(dt.date(2026, 11, 25)) == dt.date(2026, 11, 27)


def test_load_events_reads_file_and_history():
    (paths.home() / "macro_events.json").write_text(json.dumps(
        {"events": [{"date": "2026-12-09", "kind": "FOMC"}, {"date": "2026-12-18", "kind": "BOJ"}, {"date": "bad"}]}))
    ev = load_events()
    assert [(e.date.isoformat(), e.kind, e.home) for e in ev] == [("2026-12-09", "FOMC", "US"), ("2026-12-18", "BOJ", "JP")]
    hist = load_events(include_history=True, nfp_heuristic_years=(2024, 2024))
    kinds = {e.kind for e in hist}
    assert {"FOMC", "BOJ", "NFP"} <= kinds and any(e.date == dt.date(2024, 9, 18) for e in hist)
    assert sum(1 for e in hist if e.kind == "NFP") == 12


def test_load_overlay_age_and_types():
    (paths.home() / "macro.json").write_text(json.dumps(
        {"as_of": "2026-09-24", "source": "早报", "fed_hike_prob": "70", "hy_oas_bp": 266, "breadth_pct": None}))
    ov = load_overlay(today=dt.date(2026, 9, 25))
    assert ov.fed_hike_prob == 70.0 and ov.hy_oas_bp == 266.0 and ov.breadth_pct is None and not ov.stale
    assert load_overlay(today=dt.date(2026, 9, 30)).stale
    (paths.home() / "macro.json").write_text("{}")
    assert load_overlay() is None


def _two_signal_frames():
    flat = [(1000.0, 1002.0, 998.0, 1000.0, 1e6)] * 80
    rows = flat + [(1000.0, 1031.0, 999.0, 1030.0, 6e6)] + [(1040.0, 1045.0, 1035.0, 1042.0, 2e6)] * 30
    return {"A": make_indicator_frame(rows, entries=[80]), "B": make_indicator_frame(rows, entries=[80])}


def test_engine_entry_mult_blocks_and_scales():
    ind = _two_signal_frames()
    bt = BacktestConfig.for_market("US")
    bt.sizing.initial_cash = 100_000                          # 让半仓仍能买到整数股
    p = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=False, max_hold_days=10)
    base = run_backtest(ind, p, bt)
    assert len(base.trades) == 2
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))
    M = np.ones((len(gidx), 2)); M[:, 1] = 0.0                # B 永远不开
    r = run_backtest(ind, p, bt, entry_mult=M)
    assert set(r.trades["ticker"]) == {"A"} and r.skipped["macro"] == 1
    M2 = np.ones((len(gidx), 2)) * 0.5
    half = run_backtest(ind, p, bt, entry_mult=M2)
    assert half.trades["shares"].iloc[0] * 2 <= base.trades["shares"].iloc[0] + 1
    try:
        run_backtest(ind, p, bt, entry_mult=np.ones((3, 2)))
        assert False, "形状错误应报错"
    except ValueError:
        pass


def test_build_entry_mult_uses_previous_day_and_events():
    ind = _two_signal_frames()
    gidx = pd.DatetimeIndex(sorted(set().union(*[df.index for df in ind.values()])))
    frame = pd.DataFrame({"brent": 105.0, "us10y": 4.0, "vix": 15.0, "usdjpy": 150.0, "brent_chg20_pct": 2.0}, index=gidx)
    frame.loc[gidx[10], "vix"] = 40.0                           # 第 10 天恐慌 → 第 11 天成交倍数 0（US）
    ev = [MacroEvent(gidx[20].date(), "FOMC", "US")]
    M, st = build_entry_mult(gidx, ["NVDA", "LIN"], "US", frame, events=ev)
    assert M[11].tolist() == [0.0, 0.0] and M[12].tolist() == [1.0, 0.5]   # LIN=chemical 油价高位 ×0.5
    assert M[20].tolist() == [0.0, 0.0] and st["event_days"] >= 1
    M_jp, _ = build_entry_mult(gidx, ["8031.T", "4188.T"], "JP", frame, use_events=False)
    assert M_jp[12].tolist() == [0.75, 0.375]                  # Brent≥100 → 日本 0.75；化学再 ×0.5
    frame["brent"] = 120.0                                     # Brent≥115 → 美股也 0.75
    M_us, _ = build_entry_mult(gidx, ["NVDA", "LIN"], "US", frame, use_events=False)
    assert M_us[12].tolist() == [0.75, 0.375]


# ────────── run_once：事件窗口按真实 K 线算成交日 ──────────
def test_run_once_callable_entry_block_uses_real_fill_date():
    from qbreak.brokers import PaperBroker
    from qbreak.config import DataConfig, ExecConfig, RiskConfig, SizingConfig
    from qbreak.trader import run_once
    T = "9999.T"
    flat = [(1000.0, 1002.0, 998.0, 1000.0, 1e6)] * 300
    sig = (1000.0, 1031.0, 999.0, 1030.0, 6e6)
    idx = pd.bdate_range(end=pd.Timestamp("2026-10-28"), periods=301)          # 信号日 = 周三 10/28
    df = pd.DataFrame(flat + [sig], columns=["Open", "High", "Low", "Close", "Volume"], index=idx)
    df.index.name = "Date"
    (paths.sub("csv") / f"{T}.csv").write_text(df.to_csv(), encoding="utf-8")
    P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=False)
    kw = dict(market="JP", today=dt.date(2026, 10, 28), exec_cfg=ExecConfig(market="JP", commission_pct=0, slippage_pct=0))
    seen = []
    def block(fill_d):
        seen.append(fill_d)
        return "FOMC 2026-10-28 发布前不开新仓" if fill_d == dt.date(2026, 10, 29) else None
    b = PaperBroker(initial_cash=1_000_000, exec_cfg=kw["exec_cfg"], market="JP")
    res = run_once([T], b, P, RiskConfig(require_arm=False, max_order_value=1e9),
                   SizingConfig(position_pct=0.5, max_position_pct=1.0),
                   DataConfig(provider="csv", years=2, min_bars=100), entry_block=block, **kw)
    assert seen == [dt.date(2026, 10, 29)] and res.fill_date == "2026-10-29"   # 10/28 收盘信号 → 10/29 寄付
    assert res.signals == [T] and not res.orders and any("宏观事件窗口" in x for x in res.blocked)
    b2 = PaperBroker(initial_cash=1_000_000, exec_cfg=kw["exec_cfg"], market="JP")
    res2 = run_once([T], b2, P, RiskConfig(require_arm=False, max_order_value=1e9),
                    SizingConfig(position_pct=0.5, max_position_pct=1.0),
                    DataConfig(provider="csv", years=2, min_bars=100), entry_block=lambda d: None,
                    ticker_mult={T: 0.5}, **kw)
    assert res2.orders and res2.orders[0]["side"] == "BUY" and res2.orders[0]["qty"] == 200   # 50%×0.5 预算 → 2 単元


# ────────── 利率 beta（US 的长久期判定）──────────
def test_rate_beta_rank_identifies_rate_sensitive_stock():
    from qbreak.macro import long_duration_set, rate_beta_rank
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2024-01-01", periods=400)
    dy = pd.Series(rng.normal(0, 0.05, 400), index=idx)                  # 10Y 日变动（百分点）
    y = 4.0 + dy.cumsum()
    noise = lambda: rng.normal(0, 0.01, 400)                               # noqa: E731
    closes = pd.DataFrame({
        "DUR": 100 * np.exp(np.cumsum(-0.3 * dy.values + noise())),       # 收益率上行 → 跌
        "VAL": 100 * np.exp(np.cumsum(+0.2 * dy.values + noise())),
        "MID": 100 * np.exp(np.cumsum(noise())),
    }, index=idx)
    rk = rate_beta_rank(closes, y, "US")
    assert rk.iloc[-1]["DUR"] < rk.iloc[-1]["MID"] < rk.iloc[-1]["VAL"]
    assert long_duration_set(closes, y, "US") == {"DUR"}


def test_sector_mult_uses_rate_beta_flag_when_given():
    f = MacroFeatures(brent=80, us10y=5.1)
    assert sector_mult("hardware", f, long_duration=True)[0] == 0.5          # 非半导体但利率敏感
    assert sector_mult("semis", f, long_duration=False)[0] == 1.0            # 半导体但不敏感
    assert sector_mult("semis", f)[0] == 0.5                                 # 不给 → 板块近似
    t = ticker_mults(["NVDA", "AAPL"], "US", f, long_duration={"AAPL"})
    assert t["NVDA"][0] == 1.0 and t["AAPL"][0] == 0.5
