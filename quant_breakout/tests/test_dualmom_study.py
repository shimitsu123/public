"""scripts/dualmom_study.py 与 candle_portfolio.MixEngine 的双动量核心：两边都牛拿强的、一边牛拿那边、都熊现金；强弱只在月末用当时为止的数据。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import dualmom_study as S                                                    # noqa: E402

from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402

D = pd.bdate_range("2026-01-05", periods=24)
EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0, stop_loss_pct=50.0)


def _flat(px):
    df = pd.DataFrame({"Open": px, "High": px, "Low": px, "Close": px, "Volume": 1e9}, index=D)
    return df.assign(entry=False, dead_cross=False, climax=False, atr=np.nan)


def test_dual_momentum_core_targets():
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), **S.CFG)
    ind = {"1655.T": _flat(1000.0), S.JP_ETF: _flat(2000.0)}
    cc = {t: etf_cost("tachibana", t, "JP") for t in ind}
    bear = {"US": pd.Series([False] * 17 + [True] * 7, index=D), "JP": pd.Series([False] * 11 + [True] * 13, index=D)}
    old = CP.MixEngine.PREF_US
    CP.MixEngine.PREF_US = pd.Series([True, False], index=[D[0], D[5]])     # 第 5 天月末判定：日本强
    try:
        ue = CP.MixEngine(ind, cfg, {"JP": P, "US": P}, EX, cc, bear=bear)
        ue.prime(0)
        v = []
        for i in range(len(D)):
            ue.step(i)
            v.append({t: int(ue.st.core_units.get(t, 0)) for t in ind})
    finally:
        CP.MixEngine.PREF_US = old
    assert all(v[i]["1655.T"] > 0 and v[i][S.JP_ETF] == 0 for i in range(1, 6))     # 都牛、美股强
    assert all(v[i]["1655.T"] == 0 and v[i][S.JP_ETF] > 0 for i in range(6, 12))     # 都牛、日本强
    assert all(v[i]["1655.T"] > 0 and v[i][S.JP_ETF] == 0 for i in range(12, 18))    # 日本熊 → 美股
    assert all(v[i]["1655.T"] == 0 and v[i][S.JP_ETF] == 0 for i in range(18, 24))   # 都熊 → 现金


def test_pref_us_month_end_only_and_no_lookahead():
    d = pd.bdate_range("2025-01-01", "2025-06-30")
    us = pd.Series(np.linspace(100, 130, len(d)), index=d)
    jp = pd.Series(np.linspace(100, 110, len(d)), index=d)
    s = S.pref_us(us, jp, 20)
    me = d.to_series().groupby(d.to_period("M")).max()
    assert set(s.index) <= set(me) and s.all()                                # 只有月末；美股涨得多 → True
    jp2 = jp.copy()
    jp2.loc["2025-05-15":] *= 2.0
    s2 = S.pref_us(us, jp2, 20)
    assert (s2[s2.index < pd.Timestamp("2025-05-15")] == s[s.index < pd.Timestamp("2025-05-15")]).all()
    assert not s2[s2.index >= pd.Timestamp("2025-05-30")].iloc[0]             # 5 月末日本强
