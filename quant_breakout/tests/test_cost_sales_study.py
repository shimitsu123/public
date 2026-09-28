"""scripts/cost_sales_study.py：成本压力大的判定、按键分上下半的月度差、S2 只在成本上升的月份、个股层 S4 / S5 的保留规则、检验汇总。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cost_sales_study as CS  # noqa: E402

COLS = list("abcdef")


def _m(rows, idx):
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx), columns=COLS, dtype=float)


def test_costly_top_third_and_positive():
    idx = ["2020-01-31", "2020-02-29"]
    D3 = _m([[3, 2, 1, 0, 0, 0], [-3, -2, -1, -1, -1, -1]], idx)
    I3 = _m([[1, 1, 1, 0, 0, 0], [0, 0, 0, 0, 0, -5]], idx)
    C = CS.costly(D3, I3)
    assert list(C.iloc[0]) == [True, True, False, False, False, False]
    assert not C.iloc[1].any()                                                  # 最高 1/3 但 ≤ 0 → 不算
    assert list(CS.bottom_third(D3).iloc[0]) == [False, False, False, True, True, True]


def test_split_spread_top_minus_bottom_half_drop_middle_and_min_n():
    idx = ["2020-01-31", "2020-02-29"]
    Y = _m([[10, 1, 5, 2, 7, 0], [1] * 6], idx)
    key = _m([[6, 1, 3, 2, 5, 4], [1, 2, 3, 4, 5, 6]], idx)
    sel = pd.DataFrame([[True] * 5 + [False], [True, True, True, False, False, False]], index=Y.index, columns=COLS)
    x = CS.split_spread(Y, sel, key, min_n=4)
    # 1 月：a..e 按 key 排序 b(1) d(2) c(3) e(5) a(6)，5 个 → 上半 e, a（7, 10）、下半 b, d（1, 2）
    assert np.isclose(x.loc["2020-01-31"], (7 + 10) / 2 - (1 + 2) / 2)
    assert "2020-02-29" not in x.index                                          # 只有 3 个 → 不算


def test_s1_s2_series_and_complement():
    idx = pd.date_range("2020-01-31", periods=3, freq="ME")
    D3 = _m([[5, 4, 0, 0, 0, 0], [5, 4, 0, 0, 0, 0], [-1, -1, -1, -1, -1, -1]], idx)
    I3 = _m([[0, 0, 3, 2, 0, 0], [0, 0, 3, 2, 0, 0], [0, 0, 0, 0, 0, 0]], idx)
    SALES = _m([[9, 1, 8, 2, 5, 5]] * 3, idx)
    Y = _m([[4, 0, 3, 1, 0, 0]] * 3, idx)
    x1 = CS.split_spread(Y, CS.costly(D3, I3), SALES, min_n=2)
    assert np.isclose(x1.iloc[0], 4.0 - 0.0)                                    # 成本大 = a, b（最高 1/3），a 销售强
    x2 = CS.s2_series(Y, D3, I3, SALES)
    assert len(x2) == 0                                                          # 销售好的 1/3 只有 2 个 < 4 → 不算
    up = ((D3 + I3).mean(axis=1) > 0)
    assert list(up) == [True, True, False]


def test_stock_keep_rules():
    days = pd.bdate_range("2020-02-03", "2020-02-28")
    fr = {t: pd.DataFrame({"Close": 1.0}, index=days) for t in ("A.T", "B.T", "C.T", "Z.T")}
    s33 = {"A.T": "a", "B.T": "c", "C.T": "e", "Z.T": "銀行業"}
    idx = pd.DatetimeIndex(["2020-01-31"])
    D3 = _m([[5, 0, 1, 0, 0, 0]], idx)
    I3 = _m([[0, 0, 4, 0, 0, 0]], idx)                                          # a 偏直接、c 偏间接，都是成本压力大的 1/3
    SALES = _m([[9, 5, 0, 5, 1, 5]], idx)                                       # c 销售最低 1/3
    k4 = CS.stock_keep(fr, s33, D3, I3, SALES, "S4")
    k5 = CS.stock_keep(fr, s33, D3, I3, SALES, "S5")
    assert (~k4["A.T"]).all() and (~k4["B.T"]).all() and k4["C.T"].all() and k4["Z.T"].all()
    assert k5["A.T"].all() and (~k5["B.T"]).all() and k5["C.T"].all()          # S5 只看销售：a 销售强 → 照做


def test_spread_test_and_effective():
    idx = pd.date_range("2006-10-31", periods=240, freq="ME")
    x = pd.Series(np.where(np.arange(240) % 5 == 0, -0.5, 1.0), index=idx)
    r = CS.spread_test(x, [pd.Series(np.random.default_rng(i).normal(0, 1, 240), index=idx) for i in range(50)])
    assert r["mean"] > 0 and r["t"] > 5 and r["H1"] > 0 and r["H2"] > 0 and r["hit"] > 55 and r["placebo_p"] < 0.05
    assert CS.effective(r) == []
    assert len(CS.effective({"mean": -0.1, "t": -1.0, "H1": 0.1, "H2": -0.1, "hit": 40.0, "placebo_p": 0.5})) == 4
