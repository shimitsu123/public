"""scripts/halloween_study.py：5〜10 月的比例、只有核心的回测（前一天收盘的状态决定当天持仓、调整扣成本）、判定、引擎的 core_expo。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import halloween_study as S                                                  # noqa: E402

from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402


def test_season_expo():
    d = pd.DatetimeIndex(["2020-04-30", "2020-05-01", "2020-10-30", "2020-11-02"])
    assert list(S.season_expo(d, 0.5)) == [1.0, 0.5, 0.5, 1.0]


def test_core_only_uses_previous_close_and_costs():
    d = pd.bdate_range("2020-04-27", periods=6)                                # 4/27〜5/4
    close = pd.Series([100.0, 110, 121, 121, 133.1, 133.1], index=d)
    bear = pd.Series(False, index=d)
    eq = S.core_only(close, bear, S.season_expo(d, 0.0))
    # 4/28 的持仓 = 4/27 收盘的状态（4 月 → 1）；5/1 起 0（决策日在 5 月的下一天）
    assert abs(eq.iloc[1] / eq.iloc[0] - 1.10) < 1e-3
    assert abs(eq.iloc[4] / eq.iloc[3] - 1.10) < 1e-9                          # 5/1 的持仓 = 4/30 收盘（4 月）的决定
    assert abs(eq.iloc[5] / eq.iloc[4] - (1 - S.SWITCH_COST / 100)) < 1e-12   # 5/4 起不持有，只扣一次调整成本
    bear2 = pd.Series([False, True, True, True, True, True], index=d)
    eq2 = S.core_only(close, bear2, S.season_expo(d, 1.0))
    assert abs(eq2.iloc[2] / eq2.iloc[1] - (1 - S.SWITCH_COST / 100)) < 1e-12  # 4/28 收盘转熊 → 4/29 起空仓（只扣调整成本）
    assert abs(eq2.iloc[5] - eq2.iloc[2]) < 1e-12


def test_p_fails():
    base = {"P": {"calmar": 0.30, "dd": -30.0}, "P1": {"calmar": 0.3}, "P2": {"calmar": 0.3}}
    ok = {"P": {"calmar": 0.36, "dd": -25.0}, "P1": {"calmar": 0.35}, "P2": {"calmar": 0.31}}
    assert S.p_fails(ok, base) == []
    assert len(S.p_fails({**ok, "P2": {"calmar": 0.29}}, base)) == 1


def test_engine_core_expo_halves_core_in_summer():
    D = pd.bdate_range("2026-04-27", periods=10)
    df = pd.DataFrame({"Open": 1000.0, "High": 1000.0, "Low": 1000.0, "Close": 1000.0, "Volume": 1e9}, index=D)
    df = df.assign(entry=False, dead_cross=False, climax=False, atr=np.nan)
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), core={"1655.T": 1.0},
                        core_index={"1655.T": "US"}, band_pct=10.0)
    EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
    P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0, stop_loss_pct=50.0)
    ue = CP.MixEngine({"1655.T": df}, cfg, {"JP": P, "US": P}, EX, {"1655.T": etf_cost("tachibana", "1655.T", "JP")},
                      bear={"US": pd.Series(False, index=D), "JP": pd.Series(False, index=D)}, core_expo={"US": S.season_expo(D, 0.5)})
    ue.prime(0)
    v = []
    for i in range(len(D)):
        ue.step(i)
        v.append(int(ue.st.core_units.get("1655.T", 0)) * 1000)
    assert v[1] > 900_000                                                     # 4 月：全部
    assert 400_000 < v[-1] < 600_000                                          # 5 月：一半
