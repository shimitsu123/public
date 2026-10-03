"""qbreak/demark.py（TD Sequential，Jason Perl《DeMark Indicators》第 1 章的推荐设定）：价格翻转、setup 9、打断、完美、countdown 13、
第 13 根的限定条件（延后）、相反 setup 取消、越过 TDST 取消、对称、只用当时已知的数据、周线。"""
import numpy as np
import pandas as pd

from qbreak import demark as DM

DIP = [30, 29, 28, 27, 26, 25, 24, 23]                                        # 先跌：之后第一次「收盘 > 4 根前」= 价格翻转


def _frame(closes, spread=0.5, start="2024-01-01"):
    c = np.asarray(closes, float)
    idx = pd.bdate_range(start, periods=len(c))
    return pd.DataFrame({"Open": c, "High": c + spread, "Low": c - spread, "Close": c}, index=idx)


def _up(n, s=23, step=2):
    return [s + step * (k + 1) for k in range(n)]


def test_sell_setup_needs_price_flip_and_nine_bars():
    s = DM.sequential(_frame(DIP + _up(30)))
    assert int(np.flatnonzero(s["sell_setup"].to_numpy() == 1)[0]) == 9      # 第 9 根：27 > 4 根前的 25、前一根 25 < 它 4 根前的 26
    assert list(np.flatnonzero(s["sell9"].to_numpy())) == [17]                # 一直涨：只完成一次，之后接着数 10、11…
    assert s["sell_setup"].iloc[20] == 12 and not s["buy9"].any() and not s["buy13"].any()
    assert s["sell_tdst"].iloc[17] == 25.0                                     # 9 根里最低的真实低点（第 9 根的前收盘 25）


def test_sell_countdown_13_on_steady_rise():
    s = DM.sequential(_frame(DIP + _up(30)))
    assert list(np.flatnonzero(s["sell13"].to_numpy())) == [29]               # setup 第 9 根（17）本身是 countdown 1 → 第 13 个在 29
    assert (s["sell_cd"].iloc[17], s["sell_cd"].iloc[24], s["sell_cd"].iloc[29], s["sell_cd"].iloc[30]) == (1, 8, 13, 0)


def test_buy_side_is_symmetric():
    up = DIP + _up(30)
    s = DM.sequential(_frame([100 - v for v in up]))
    t = DM.sequential(_frame(up))
    assert list(np.flatnonzero(s["buy9"].to_numpy())) == list(np.flatnonzero(t["sell9"].to_numpy())) == [17]
    assert list(np.flatnonzero(s["buy13"].to_numpy())) == list(np.flatnonzero(t["sell13"].to_numpy())) == [29]


def test_interruption_resets_setup():
    c = DIP + [25, 27, 29, 31, 24] + _up(15, s=31)                           # setup 第 4 根（24 不大于 4 根前的 25）被打断
    s = DM.sequential(_frame(c))
    assert s["sell_setup"].iloc[12] == 0 and not s["sell9"].iloc[17]
    assert list(np.flatnonzero(s["sell9"].to_numpy())) == [21]                # 13 根起新的翻转 → 21 完成


def test_perfection_flag():
    f = _frame(DIP + _up(30))
    assert DM.sequential(f)["sell_perfect"].iloc[17]                          # 一直涨：第 8、9 根的高点 ≥ 第 6、7 根
    g = f.copy()
    g.iloc[14, g.columns.get_loc("High")] += 10                                # 第 6、7 根拉出长上影 → 第 8、9 根不再更高
    g.iloc[15, g.columns.get_loc("High")] += 10
    s = DM.sequential(g)
    assert s["sell9"].iloc[17] and not s["sell_perfect"].iloc[17]


def test_deferred_13_needs_bar8_close():
    c = DIP + _up(17) + [50, 45, 40, 43, 46, 49, 52, 55, 56, 58, 60]           # countdown 8 在 24（收盘 57）；回落后再数到 12；33 的高点 56.5 < 57 → 延后
    s = DM.sequential(_frame(c))
    assert s["sell_cd"].iloc[24] == 8 and s["sell_cd"].iloc[32] == 12
    assert not s["sell13"].iloc[33] and s["sell_cd"].iloc[33] == 12
    assert list(np.flatnonzero(s["sell13"].to_numpy())) == [34]


def test_opposite_setup_cancels_countdown():
    c = DIP + _up(10) + [45 - 1.5 * (k + 1) for k in range(12)]               # 卖 countdown 数到 2 之后一路跌 → 买 setup 完成
    s = DM.sequential(_frame(c))
    b9 = np.flatnonzero(s["buy9"].to_numpy())
    assert len(b9) == 1 and s["sell_cd"].iloc[b9[0] - 1] > 0 and s["sell_cd"].iloc[b9[0]] == 0
    assert not s["sell13"].any() and s["buy_cd"].iloc[b9[0]] >= 1


def test_tdst_violation_cancels():
    c = DIP + _up(11) + [10, 10, 10.5, 11]                                    # 卖 setup 之后整根跌到 TDST（25）以下
    s = DM.sequential(_frame(c))
    assert s["sell_cd"].iloc[18] > 0 and s["sell_cd"].iloc[19] > 0           # 19：暴跌那一根的真实高点含前收盘 → 还没取消
    assert s["sell_cd"].iloc[20] == 0 and not s["sell13"].any()               # 20：真实高点 10.5 < 25 → 取消


def test_no_lookahead():
    c = list(np.cumsum(np.random.default_rng(3).normal(0, 1, 400)) + 100)
    f = _frame(c)
    full = DM.sequential(f)
    assert full["sell13"].any() or full["buy13"].any()
    for cut in (150, 260, 399):
        assert DM.sequential(f.iloc[:cut]).equals(full.iloc[:cut])           # 第 i 根的状态只用到 i 和之前


def test_weekly_resample_and_events():
    idx = pd.bdate_range("2024-01-01", "2024-01-19")
    f = pd.DataFrame({"Open": np.arange(len(idx)) + 1.0, "High": np.arange(len(idx)) + 2.0, "Low": np.arange(len(idx)) + 0.5,
                      "Close": np.arange(len(idx)) + 1.5}, index=idx)
    w = DM.weekly(f)
    assert list(w.index.strftime("%m-%d")) == ["01-05", "01-12", "01-19"]
    assert w.iloc[0].tolist() == [1.0, 6.0, 0.5, 5.5]
    assert list(DM.event_days(_frame(DIP + _up(30))).strftime("%Y-%m-%d")) == ["2024-02-09"]


def test_setup_tdst_persists_until_next_setup():
    s = DM.sequential(_frame(DIP + _up(30)))
    v = s["sell_setup_tdst"].to_numpy()
    assert np.isnan(v[:17]).all() and (v[17:] == 25.0).all()                # 完成那一根起一直是 25（之后没有新的卖 setup）
    assert np.isnan(s["buy_setup_tdst"].to_numpy()).all()
