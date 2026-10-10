"""「卖出判定」横展开（scripts/sell_common.py、scripts/sell_explore.py）：指标算法、只用当天为止的数据、变换方式、入选规则、判定准度的算法。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak.config import StrategyParams
from qbreak.strategy import compute_indicators

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sell_common as SC                                                     # noqa: E402
import sell_explore as SX                                                    # noqa: E402


def _frame(n=400, seed=3):
    rng = np.random.default_rng(seed)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, n)))
    o = c * (1 + rng.normal(0, 0.006, n))
    df = pd.DataFrame({"Open": o, "High": np.maximum(o, c) * (1 + rng.random(n) * 0.01), "Low": np.minimum(o, c) * (1 - rng.random(n) * 0.01),
                       "Close": c, "Volume": rng.integers(50_000, 500_000, n).astype(float)}, index=pd.bdate_range("2020-01-01", periods=n))
    return compute_indicators(df, StrategyParams())


def test_indicators_basic_shapes():
    up = np.arange(1, 41, dtype=float)
    k, d = SC.stoch(up + 0.5, up - 0.5, up)
    assert np.nanmax(np.abs(k[20:] - k[-1])) < 1e-9 and k[-1] > 90            # 一路涨 → %K 贴近上方且稳定
    pdi, mdi = SC.dmi(up + 0.5, up - 0.5, up)
    assert (pdi[20:] > mdi[20:]).all()
    assert SC.cross_down([2, 1], [1.5, 1.5]).tolist() == [False, True]
    assert SC.cross_down([np.nan, 1], [1.5, 1.5]).tolist() == [False, False]
    # V 形：先跌后涨 → SAR 翻到下方（上升）；再跌 → 翻到上方（sar_flip 那一天）
    x = np.r_[np.linspace(100, 80, 15), np.linspace(80, 110, 20), np.linspace(110, 90, 15)]
    _, trend = SC.psar(x + 1, x - 1)
    assert trend[30] and not trend[-1] and trend[1:15].sum() == 0
    hb = SC.heikin_bear(np.r_[10.0, 9, 8], np.r_[10.5, 9.5, 8.5], np.r_[8.5, 7.5, 6.5], np.r_[9.0, 8, 7])
    assert hb.tolist() == [False, True, True]                                  # 第一根 HA 开 = (开 + 收) / 2 = HA 收 → 不算阴线


def test_candle_signals_hand_made():
    rows = [(100, 101, 99, 100)] * 30 + [(100, 106, 100, 105), (106, 107, 99, 99.5), (99.5, 100, 98, 99)]
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=pd.bdate_range("2021-01-01", periods=len(rows)), dtype=float)
    df["macd"], df["macd_sig"], df["dead_cross"] = 0.0, 0.0, False
    S = SC.signals(df)
    assert S["engulf_bear"][31] and not S["engulf_bear"][30]                 # 阴线实体 106→99.5 包住前一天阳线 100→105
    assert bool(S["below_prev_low"][31])                                     # 99.5 < 前一天最低 100
    assert S["bear_candle"][31] and not S["bear_candle"][30]
    assert S["bb_fall"][31]                                                  # 第 30 天收在上轨之外、第 31 天回到之内
    assert set(SC.SIGNALS) <= set(S)


def test_signals_use_only_data_up_to_today():
    df = _frame()
    full = SC.signals(df)
    for k in (150, 233, 399):
        part = SC.signals(df.iloc[:k])
        for name in SC.SIGNALS:
            assert np.array_equal(part[name], full[name][:k]), (name, k)


def test_exit_transform_modes():
    df = _frame()
    fr = {"A.T": df}
    S = SC.signals(df)
    assert SC.exit_transform(fr, None) is fr
    assert np.array_equal(SC.exit_transform(fr, "_neutral")["A.T"]["dead_cross"].to_numpy(), df["dead_cross"].to_numpy())
    cache = {}
    r1 = SC.exit_transform(fr, "R1", cache)["A.T"]["dead_cross"].to_numpy()
    assert np.array_equal(r1, S["kd_dead"]) and "A.T" in cache
    a1 = SC.exit_transform(fr, "A1", cache)["A.T"]["dead_cross"].to_numpy()
    assert np.array_equal(a1, S["dead_cross"] | S["rsi70_down"])
    c1 = SC.exit_transform(fr, "C1", cache)["A.T"]["dead_cross"].to_numpy()
    assert np.array_equal(c1, S["dead_cross"] & S["rsi_lt50"])
    assert np.array_equal(df["dead_cross"].to_numpy(), S["dead_cross"])      # 原表不动
    assert {v["fam"] for v in SC.VARIANTS.values()} == {"R", "A", "C"} and len(SC.VARIANTS) == 15


def _s(win, mean=0.6, calmar=0.3, dd=-30.0, hw=(42.0, 42.0)):
    return {"win": win, "mean": mean, "calmar": calmar, "dd": dd, "halves_win": list(hw)}


def test_qualifies_and_pick():
    base = {"E": _s(42.0), "J": _s(42.0)}
    good = {"E": _s(47.0, 0.7, 0.30, -31.0, (46, 48)), "J": _s(46.5, 0.65, 0.295, -30.5, (45, 47))}
    assert SX.qualifies(good, base) == []
    bad = {"E": _s(45.0, 0.5, 0.28, -33.0, (40, 50)), "J": _s(47.0, 0.7, 0.3, -30.0, (41, 50))}
    f = SX.qualifies(bad, base)
    assert "E 胜率没高 4 pp" in f and "E 每笔不如现行" in f and "E Calmar 低 0.01 以上" in f and "E 回撤深 2 pp 以上" in f
    assert "半段胜率低于现行 2 个" in f
    res = {"R1": good, "R2": {e: {**v, "win": v["win"] + 1} for e, v in good.items()},
           "R3": {e: {**v, "win": v["win"] + 2} for e, v in good.items()}, "A1": good, "C1": bad}
    assert SX.pick(res, base) == ["R3", "R2", "A1"]                          # R 族最多 2 个；C1 不入选


def test_judge_accuracy_first_fire_and_forward():
    n = 40
    c = np.r_[np.full(10, 100.0), np.linspace(100, 120, 10), np.linspace(120, 100, 20)]
    df = pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1, "Close": c}, index=pd.bdate_range("2022-01-03", periods=n))
    df["macd"], df["macd_sig"] = 0.0, 0.0
    dead = np.zeros(n, bool)
    dead[21] = True
    df["dead_cross"] = dead
    tr = pd.DataFrame({"ticker": ["A.T"], "entry_date": [df.index[10]], "exit_date": [df.index[22]], "exit_px": [c[22]]})
    acc = SX.judge_accuracy({"A.T": df}, tr, {}, 0.0, names=["dead_cross", "bear_candle"])
    d = acc["dead_cross"]
    assert d["trades"] == 1 and d["fire_pct"] == 100.0 and d["n"] == 1
    assert d["right_pct"] == 100.0                                           # 第 22 天开盘卖、10 天后更低 → 卖对
    assert d["fwd_mean"] == pytest.approx((c[32] / c[22] - 1) * 100, abs=0.01) and d["vs_exit_mean"] == 0.0
    assert acc["bear_candle"]["fire_pct"] == 0.0                              # 开 = 收，没有阴线
    assert acc["_every_day"]["n"] == 12                                       # 第 10〜21 天（实际卖出前一天为止）
