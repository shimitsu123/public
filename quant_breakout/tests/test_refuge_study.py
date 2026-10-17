"""scripts/refuge_study.py 与 candle_portfolio.MixEngine 的「避险」核心（XR = 与美股牛熊相反）：
美股牛市全部 1655、熊市全部避险资产（前一天收盘判定 → 当天开盘换）；常配 20% 的比例；日元价格只用开盘前已知的美国收盘与汇率；熊市段的切分。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import refuge_study as R                                                     # noqa: E402

from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402

D = pd.bdate_range("2026-01-05", periods=20)
EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0, stop_loss_pct=50.0)
BEAR_US = pd.Series([False] * 8 + [True] * 6 + [False] * 6, index=D)          # 第 8〜13 天收盘判定为熊


def _flat(px):
    df = pd.DataFrame({"Open": px, "High": px, "Low": px, "Close": px, "Volume": 1e9}, index=D)
    return df.assign(entry=False, dead_cross=False, climax=False, atr=np.nan)


def _units(c):
    over = R.cfg_for(c)
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), **over)
    ind = {"1655.T": _flat(1000.0), R.GOLD: _flat(2000.0), R.BOND: _flat(1500.0)}
    ind = {t: df for t, df in ind.items() if t in cfg.core}
    cc = {t: etf_cost("tachibana", t, "JP") for t in ind}
    ue = CP.MixEngine(ind, cfg, {"JP": P, "US": P}, EX, cc, bear={"US": BEAR_US, "JP": pd.Series(False, index=D)})
    ue.prime(0)
    out = []
    for i in range(len(D)):
        ue.step(i)
        out.append({t: int(ue.st.core_units.get(t, 0)) * float(ind[t]["Close"].iloc[i]) for t in ind})
    return out


def test_cfg_for():
    g1, g2, g3 = R.cfg_for("G1"), R.cfg_for("G2"), R.cfg_for("G3")
    assert g1["core_index"] == {"1655.T": "US", R.GOLD: "XR"} and g1["core_mode"] == "follow"
    assert g2["core_index"] == {"1655.T": "US", R.BOND: "XR"} and set(g2["core"]) == {"1655.T", R.BOND}
    assert g3["core"] == {"1655.T": 0.8, R.GOLD: 0.2} and g3["core_mode"] == "split" and g3["core_index"][R.GOLD] == "US"


def test_bear_switches_core_to_refuge_and_back():
    v = _units("G1")
    for i in range(1, 9):                                                   # 牛市：全部 1655（第 1 天开盘买）
        assert v[i][R.GOLD] == 0 and v[i]["1655.T"] > 900_000
    for i in range(9, 15):                                                  # 第 8 天收盘转熊 → 第 9 天开盘换成黄金
        assert v[i]["1655.T"] == 0 and v[i][R.GOLD] > 900_000
    for i in range(15, 20):                                                 # 第 14 天收盘转牛 → 第 15 天开盘换回
        assert v[i][R.GOLD] == 0 and v[i]["1655.T"] > 900_000
    v2 = _units("G2")
    assert v2[10]["1655.T"] == 0 and v2[10][R.BOND] > 900_000 and v2[5][R.BOND] == 0


def test_constant_gold_share_and_cash_in_bear():
    v = _units("G3")
    tot = v[5]["1655.T"] + v[5][R.GOLD]
    assert tot > 900_000 and abs(v[5][R.GOLD] / tot - 0.2) < 0.01           # 牛市：80 / 20
    assert v[10]["1655.T"] == 0 and v[10][R.GOLD] == 0                      # 熊市：都卖、留现金


def test_jpy_frame_uses_previous_us_close_and_fx():
    us_days = pd.DatetimeIndex(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"])
    us = pd.DataFrame({"Open": [10.0, 11, 12, 13], "High": [10.0, 11, 12, 13], "Low": [10.0, 11, 12, 13],
                       "Close": [10.0, 11, 12, 13], "Volume": 1.0}, index=us_days)
    fx = pd.Series([100.0, 110, 120, 130], index=us_days)
    jp = pd.DatetimeIndex(["2026-01-06", "2026-01-07", "2026-01-09"])
    f = R.jpy_frame(us, fx, jp, 2.0)
    assert list(f["Open"]) == [10 * 100 / 2, 11 * 110 / 2, 13 * 130 / 2]      # d 日 = 前一个美国收盘 × 前一天的汇率 ÷ 2
    assert not f["entry"].any() and not f["dead_cross"].any()


def test_bear_runs_and_returns():
    bear = np.array([False, True, True, False, True, True, True])
    runs = R.bear_runs(bear)
    assert runs == [(2, 4), (5, 7)]                                         # 前一天判定 → 当天换；最后一段到末尾
    px = pd.Series([100.0, 100, 100, 110, 121, 100, 90])
    assert R.run_returns(px, runs) == [21.0, -10.0]
