"""scripts/candle_study.py 与 scripts/candle_portfolio.py：押し目仓位满 N 天卖（不看死叉）、指値碰到才买（成交价 = min(开盘, 指値)）、
另外的卖出列、门槛 R / E、逐笔统计、指値的逐笔近似。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import candle_study as S                                                     # noqa: E402

from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402

D8 = pd.bdate_range("2026-01-05", periods=16)
EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0, stop_loss_pct=50.0)


def _bars(px, low=None, entry_on=(), dead_on=()):
    px = np.asarray(px, float)
    df = pd.DataFrame({"Open": px, "High": px * 1.01, "Low": px * 0.99 if low is None else np.asarray(low, float), "Close": px,
                       "Volume": 1e6}, index=D8)
    df["entry"] = df.index.isin(pd.DatetimeIndex(entry_on))
    df["dead_cross"] = df.index.isin(pd.DatetimeIndex(dead_on))
    df["climax"] = False
    df["atr"] = px * 0.02
    return df


def _run(ind, pb, hold=3, limit_k=0.0, use_dead=False):
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), core={}, core_index={})
    old = (CP.MixEngine.PB, CP.MixEngine.HOLD_PB, CP.MixEngine.LIMIT_K, CP.MixEngine.PB_USE_DEAD)
    CP.MixEngine.PB, CP.MixEngine.HOLD_PB, CP.MixEngine.LIMIT_K, CP.MixEngine.PB_USE_DEAD = pb, hold, limit_k, use_dead
    try:
        ue = CP.MixEngine(ind, cfg, {"JP": P, "US": P}, EX, {})
        ue.run()
    finally:
        CP.MixEngine.PB, CP.MixEngine.HOLD_PB, CP.MixEngine.LIMIT_K, CP.MixEngine.PB_USE_DEAD = old
    return ue


def test_pullback_position_exits_after_n_days_and_ignores_dead_cross():
    ind = {"1111.T": _bars([1000.0] * 16, entry_on=[D8[1]], dead_on=[D8[3]]),
           "2222.T": _bars([1000.0] * 16, entry_on=[D8[1]], dead_on=[D8[3]])}
    ue = _run(ind, {"1111.T": {D8[1]}}, hold=5)
    tr = {t["ticker"]: t for t in ue.st.trades}
    assert tr["2222.T"]["exit_date"] == str(D8[4].date())                         # 突破仓位：D3 死叉 → D4 开盘卖
    assert tr["1111.T"]["entry_date"] == str(D8[2].date()) and tr["1111.T"]["exit_date"] == str(D8[7].date())   # 押し目：持有 5 天
    ue2 = _run({"1111.T": _bars([1000.0] * 16, entry_on=[D8[1]], dead_on=[D8[3]])}, {"1111.T": {D8[1]}}, hold=5, use_dead=True)
    assert ue2.st.trades[0]["exit_date"] == str(D8[4].date())                    # 另外的卖出列打开 → 按它卖


def test_limit_entry_fills_only_when_low_touches():
    px = [1000.0] * 16
    low_hit = [990.0] * 16
    low_hit[2] = 990.0                                                             # 指値 = 1000 − 0.3 × 20 = 994 → 碰到
    ue = _run({"1111.T": _bars(px, low=low_hit, entry_on=[D8[1]])}, {"1111.T": {D8[1]}}, hold=3, limit_k=0.3)
    t = (ue.st.trades or [{"entry_px": p.entry_px} for p in ue.st.pos.values()])[0]
    assert abs(t["entry_px"] / (1 + EX["JP"].slippage_pct / 100) - 994.0) < 1e-6
    low_miss = [999.0] * 16
    ue2 = _run({"1111.T": _bars(px, low=low_miss, entry_on=[D8[1]])}, {"1111.T": {D8[1]}}, hold=3, limit_k=0.3)
    assert not ue2.st.trades and not ue2.st.pos and ue2.skipped.get("limit_miss") == 1


def test_gates_r_and_e():
    core = {"all": {"calmar": 0.42}}
    cur0 = {"all": {"calmar": 0.37}}
    assert S.r_fails({"all": {"calmar": 0.42}}, core, cur0) == [] and S.r_fails({"all": {"calmar": 0.41}}, core, cur0)
    assert S.e_fails({"n": 10, "mean": 0.5, "pf": 1.2}) == []
    assert len(S.e_fails({"n": 10, "mean": -0.1, "pf": 0.9})) == 2 and S.e_fails({"n": 0})


def test_trade_stats_and_limit_adjust():
    days = pd.bdate_range("2022-01-03", periods=30)
    T = pd.DataFrame({"ticker": ["A", "A"], "sig_date": [days[20], days[25]], "entry_date": [days[21], days[26]],
                      "net": [2.0, -1.0], "ret_pct": [2.2, -0.8], "exit_px": [102.2, 99.2], "hold_days": [10, 10]})
    s = S.tstat(T)
    assert s["n"] == 2 and s["win"] == 50.0 and s["pf"] == 2.0
    assert S.tstat(T, "2022-01-01", str(days[23].date()))["n"] == 1
    L = np.full((30, 1), 99.0)
    L[21, 0], L[26, 0] = 98.0, 99.9                                            # 指値 = 100 − 0.3 × ATR(2) = 99.4
    Pn = {"O": np.full((30, 1), 100.0), "H": np.full((30, 1), 101.0), "C": np.full((30, 1), 100.0), "L": L}
    out = S.limit_adjust(T, Pn, days, ["A"], 0.3, 0.001)
    assert len(out) == 1 and out["sig_date"].iloc[0] == days[20]                # 第二笔最低 99.9 碰不到 → 删掉
    fill = 100.0 - 0.3 * 2.0
    assert abs(out["net"].iloc[0] - ((102.2 / (fill * 1.001) - 1) * 100 - 0.2)) < 1e-9
