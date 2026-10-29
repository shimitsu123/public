"""scripts/ndx_study.py：只有核心的持仓（前一天收盘的状态、各自的牛熊、权重、调整成本）与引擎里另外的牛熊判定（EXTRA_BEAR）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import ndx_study as S                                                        # noqa: E402

from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402


def test_core_mix():
    d = pd.bdate_range("2020-01-01", periods=4)
    a = pd.Series([100.0, 110, 121, 133.1], index=d)
    b = pd.Series([100.0, 100, 100, 100], index=d)
    bull = pd.Series(False, index=d)
    eq = S.core_mix({"A": a, "B": b}, {"A": 0.5, "B": 0.5}, {"A": bull, "B": bull})
    assert abs(eq.iloc[1] - (1 + 0.05 - 0.001)) < 1e-12                        # 一半 +10%，进场扣 0.1% × 权重合计 1
    bear_b = pd.Series([True] * 4, index=d)
    eq2 = S.core_mix({"A": a, "B": b}, {"A": 0.5, "B": 0.5}, {"A": bull, "B": bear_b})
    assert abs(eq2.iloc[1] - (1 + 0.05 - 0.0005)) < 1e-12                     # B 熊 → 那一半现金


def test_engine_extra_bear():
    D = pd.bdate_range("2026-01-05", periods=10)
    df = pd.DataFrame({"Open": 1000.0, "High": 1000.0, "Low": 1000.0, "Close": 1000.0, "Volume": 1e9}, index=D)
    df = df.assign(entry=False, dead_cross=False, climax=False, atr=np.nan)
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), **S.CFG["N2"])
    EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
    P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0, stop_loss_pct=50.0)
    old = CP.MixEngine.EXTRA_BEAR
    CP.MixEngine.EXTRA_BEAR = {"NQ": pd.Series([False] * 5 + [True] * 5, index=D)}
    try:
        ue = CP.MixEngine({S.NQ: df}, cfg, {"JP": P, "US": P}, EX, {S.NQ: etf_cost("tachibana", S.NQ, "JP")},
                          bear={"US": pd.Series(False, index=D), "JP": pd.Series(False, index=D)})
        ue.prime(0)
        v = []
        for i in range(len(D)):
            ue.step(i)
            v.append(int(ue.st.core_units.get(S.NQ, 0)))
    finally:
        CP.MixEngine.EXTRA_BEAR = old
    assert v[3] > 0 and v[-1] == 0                                            # 第 4 天收盘纳指转熊 → 第 5 天卖
