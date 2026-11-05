"""scripts/fxhedge_study.py：对冲版的利差、月利率下个月起才用、日元走强判定只用当天为止、只有核心的持仓切换、引擎的 UH / HG 切换。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import fxhedge_study as S                                                    # noqa: E402

from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402


def test_hedged_index_carry_and_monthly_lag():
    d = pd.bdate_range("2020-01-01", "2020-03-31")
    spx = pd.Series(100.0, index=d)
    us = pd.Series(2.52, index=d)                                             # 2.52%
    jp = pd.Series([0.0, 25.2], index=pd.DatetimeIndex(["2020-01-01", "2020-02-01"]))   # 2 月的月平均 → 3 月起才用
    h = S.hedged_index(spx, us, jp)
    feb = h.loc["2020-02-03":"2020-02-28"]
    assert (feb.pct_change().dropna() < 0).all()                               # 2 月：日本 0% − 美国 2.52% → 每天 −0.01%
    mar = h.loc["2020-03-03":"2020-03-31"]
    assert (mar.pct_change().dropna() > 0).all()                               # 3 月：25.2% − 2.52% > 0


def test_yen_strong_no_lookahead():
    fx = pd.Series(np.r_[np.full(250, 150.0), np.linspace(150, 120, 50)], index=pd.bdate_range("2020-01-01", periods=300))
    ys = S.yen_strong(fx)
    assert not ys.iloc[:250].any() and ys.iloc[-1]
    fx2 = fx.copy()
    fx2.iloc[280:] = 200.0
    assert (S.yen_strong(fx2).iloc[:280] == ys.iloc[:280]).all()


def test_core_only_switches():
    d = pd.bdate_range("2020-01-01", periods=6)
    unh = pd.Series([100.0, 110, 121, 121, 121, 121], index=d)
    hed = pd.Series([100.0, 100, 100, 110, 121, 121], index=d)
    bear = pd.Series(False, index=d)
    use = pd.Series([False, True, True, True, True, True], index=d)            # 第 1 天收盘起用对冲
    eq = S.core_only(unh, hed, bear, use)
    assert abs(eq.iloc[1] / eq.iloc[0] - (1.10 - 0.001)) < 1e-9               # 第 1 天：不对冲（第 0 天的决定）+ 进场成本
    assert abs(eq.iloc[3] / eq.iloc[2] - 1.10) < 1e-9                          # 第 3 天：对冲版 +10%


def test_engine_hedge_switch():
    D = pd.bdate_range("2026-01-05", periods=12)
    f = lambda px: pd.DataFrame({"Open": px, "High": px, "Low": px, "Close": px, "Volume": 1e9}, index=D).assign(   # noqa: E731
        entry=False, dead_cross=False, climax=False, atr=np.nan)
    ind = {"1655.T": f(1000.0), S.HEDGED: f(2000.0)}
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), **S.CFG["F1"])
    EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
    P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0, stop_loss_pct=50.0)
    old = CP.MixEngine.YEN_STRONG
    CP.MixEngine.YEN_STRONG = pd.Series([False] * 6 + [True] * 6, index=D)
    try:
        ue = CP.MixEngine(ind, cfg, {"JP": P, "US": P}, EX, {t: etf_cost("tachibana", t, "JP") for t in ind},
                          bear={"US": pd.Series(False, index=D), "JP": pd.Series(False, index=D)})
        ue.prime(0)
        v = []
        for i in range(len(D)):
            ue.step(i)
            v.append({t: int(ue.st.core_units.get(t, 0)) for t in ind})
    finally:
        CP.MixEngine.YEN_STRONG = old
    assert v[3]["1655.T"] > 0 and v[3][S.HEDGED] == 0
    assert v[9]["1655.T"] == 0 and v[9][S.HEDGED] > 0
