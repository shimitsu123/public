"""scripts/cost_sales_study.py：只算上涨部分的成本信号、成本压力大（含下限）、按秩分上下半（并列与中间不算）、S2 的月份与基准、
Holm、稳健性（去掉一个业种）、个股层 S4 / S5、只在有数据区间里错开。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cost_sales_study as CS  # noqa: E402

COLS = list("abcdef")


def _m(rows, idx):
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx), columns=COLS, dtype=float)


def test_pos_signals_only_count_rises():
    months = pd.date_range("2020-01-31", periods=8, freq="ME")
    P = pd.DataFrame({k: 100.0 for k in CS.TS.SHOCKS}, index=pd.date_range("2020-01-01", periods=8, freq="MS"))
    P["E"] = 100 * np.exp(np.arange(8) * 0.01)                                     # 能源每月 +1%
    P["S"] = 100 * np.exp(-np.arange(8) * 0.02)                                    # 钢铁每月 −2%
    ex = {"direct": {"E": {"a": 0.5}, "S": {"a": 0.5}, "N": {}, "F": {}}, "indirect": {"E": {"a": 0.1}, "S": {"a": 0.2}, "N": {}, "F": {}}}
    s = CS.pos_signals(P, ex, months, ["a"], 3)
    t = months[6]
    assert np.isclose(s["D3p"].loc[t, "a"], 0.5 * 3) and np.isclose(s["I3p"].loc[t, "a"], 0.1 * 3)    # 钢铁下跌不抵消
    assert np.isclose(s["D3"].loc[t, "a"], 0.5 * 3 - 0.5 * 6) and np.isclose(s["I3"].loc[t, "a"], 0.1 * 3 - 0.2 * 6)
    assert s["D3p"].iloc[:4].isna().all().all()                                    # 3 个月变化 + 发布滞后：头 4 个月没有值


def test_costly_floor_and_top_third():
    idx = ["2020-01-31", "2020-02-29"]
    D3p = _m([[3, 2, 1, 0, 0, 0], [0.05, 0.04, 0, 0, 0, 0]], idx)
    I3p = _m([[1, 1, 1, 0, 0, 0], [0.0, 0.0, 0, 0, 0, 0.01]], idx)
    C = CS.costly(D3p, I3p)
    assert list(C.iloc[0]) == [True, True, False, False, False, False]
    assert not C.iloc[1].any()                                                      # 最高 1/3 但不到 0.1 → 不算


def test_split_spread_rank_halves_ties_and_drop():
    idx = ["2020-01-31", "2020-02-29", "2020-03-31"]
    Y = _m([[10, 1, 5, 2, 7, 0], [1, 2, 3, 4, 5, 6], [4, 0, 9, 1, 0, 0]], idx)
    key = _m([[6, 1, 3, 2, 5, 4], [1, 1, 2, 2, 3, 3], [5, 1, 5, 1, 3, 3]], idx)
    sel = pd.DataFrame([[True] * 5 + [False], [True] * 6, [True] * 4 + [False] * 2], index=Y.index, columns=COLS)
    x = CS.split_spread(Y, sel, key, min_n=4)
    # 1 月：a..e 的秩 b1 d2 c3 e4 a5 → 中线 3：上半 e, a（7, 10）、下半 b, d（1, 2）、c 不算
    assert np.isclose(x.loc["2020-01-31"], (7 + 10) / 2 - (1 + 2) / 2)
    # 2 月：并列 (1,1)(2,2)(3,3) → 秩 1.5 / 3.5 / 5.5，中线 3.5：c, d 不算
    assert np.isclose(x.loc["2020-02-29"], (5 + 6) / 2 - (1 + 2) / 2)
    # 3 月：a, c 并列最高（9 与 4）、b, d 并列最低
    assert np.isclose(x.loc["2020-03-31"], (4 + 9) / 2 - (0 + 1) / 2)
    xd = CS.split_spread(Y, sel, key, min_n=4, drop="a")
    assert "2020-01-31" in xd.index and "2020-03-31" not in xd.index                # 去掉 a 后 3 月只剩 3 个 → 不算


def test_s1_s2_sets_and_indirect_share():
    idx = pd.date_range("2020-01-31", periods=2, freq="ME")
    D3p = _m([[5, 4, 0.05, 0, 0, 1], [5, 4, 0, 0, 0, 1]], idx)
    I3p = _m([[0, 0, 3, 2, 0, 0], [0, 0, 3, 2, 0, 0]], idx)
    D3 = _m([[1] * 6, [-1] * 6], idx)
    I3 = _m([[0] * 6, [0] * 6], idx)
    SALES = _m([[9, 1, 8, 2, np.nan, 5]] * 2, idx)
    C, Cc = CS.s1_sets(D3p, I3p, SALES)
    assert list(C.iloc[0]) == [True, True, False, False, False, False] and list(Cc.iloc[0]) == [False, False, True, True, False, True]
    S2, S2b = CS.s2_sets(D3p, I3p, D3, I3, SALES)
    assert list(S2b.iloc[0]) == [True, True, True, True, False, True] and not S2b.iloc[1].any()   # 2 月成本净值下降 → 不算
    assert list(S2.iloc[0]) == [True, False, True, False, False, True]                          # 销售前一半（秩百分位 > 0.5）：a 9、c 8、f 5
    sh = CS.indirect_share(D3p, I3p)
    assert np.isclose(sh.iloc[0, 2], 3 / 3.05) and np.isnan(sh.iloc[0, 4])


def test_spread_test_holm_effective_and_loo():
    idx = pd.date_range("2006-10-31", periods=240, freq="ME")
    x = pd.Series(np.where(np.arange(240) % 5 == 0, -0.5, 1.0), index=idx)
    r = CS.spread_test(x, [pd.Series(np.random.default_rng(i).normal(0, 1, 240), index=idx) for i in range(50)])
    assert r["mean"] > 0 and r["t"] > 5 and r["H1"] > 0 and r["H2"] > 0 and len(r["hits"]) == 3 and r["hit"] > 55 and r["placebo_p"] < 0.05
    assert CS.holm({"S1": 0.01, "S2": 0.04}) == {"S1": True, "S2": True}
    assert CS.holm({"S1": 0.03, "S2": 0.04}) == {"S1": False, "S2": False}          # 最小的也要 < 0.025
    assert CS.holm({"S1": None, "S2": 0.001}) == {"S2": True, "S1": False}
    assert CS.effective(r, 0.2, True) == []
    assert len(CS.effective({"mean": -0.1, "t": -1.0, "H1": 0.1, "H2": -0.1, "hit": 40.0, "placebo_p": 0.5}, -0.1, False)) == 5
    p = CS.paired(pd.Series([1.0] * 40, index=idx[:40]), pd.Series(np.linspace(0, 0.1, 40), index=idx[:40]))
    assert p["diff"] > 0.9 and p["n"] == 40


def test_skip_panel_s4_s5_and_stock_keep():
    idx = pd.DatetimeIndex(["2020-01-31"])
    D3p = _m([[5, 0, 1, 0, 0, 0]], idx)
    I3p = _m([[0, 0, 4, 0, 0, 0]], idx)                                             # a 偏直接、c 偏间接，都是成本压力大
    SALES = _m([[9, 5, 8, 5, 1, 5]], idx)                                           # a、c 在前 1/3
    s4, s5 = CS.skip_panel(D3p, I3p, SALES, "S4"), CS.skip_panel(D3p, I3p, SALES, "S5")
    assert list(s4.iloc[0]) == [True, False, False, False, False, False]           # 偏直接 → 销售再好也不做
    assert not s5.iloc[0].any()                                                     # 只看销售：都在前 1/3 → 照做
    SALES2 = _m([[9, 5, 1, 5, 1, 8]], idx)                                          # c 销售掉出前 1/3
    assert list(CS.skip_panel(D3p, I3p, SALES2, "S5").iloc[0]) == [False, False, True, False, False, False]
    days = pd.bdate_range("2020-02-03", "2020-02-28")
    fr = {t: pd.DataFrame({"Close": 1.0}, index=days) for t in ("A.T", "C.T", "Z.T")}
    k = CS.stock_keep(fr, {"A.T": "a", "C.T": "c", "Z.T": "銀行業"}, D3p, I3p, SALES2, "S4")
    assert (~k["A.T"]).all() and (~k["C.T"]).all() and k["Z.T"].all()


def test_valid_start_and_roll_block():
    idx = pd.date_range("1990-01-31", periods=10, freq="ME")
    S = pd.DataFrame({"a": [np.nan] * 4 + list(range(6)), "b": [np.nan] * 3 + list(range(7))}, index=idx, dtype=float)
    D = pd.DataFrame({"a": 1.0, "b": 1.0}, index=idx)
    vs = CS.valid_start(S, D, frac=1.0)
    assert vs == idx[4]
    R = CS.roll_block(S, 2, vs)
    assert R.iloc[:4].equals(S.iloc[:4]) and list(R["a"].iloc[4:]) == [4.0, 5.0, 0.0, 1.0, 2.0, 3.0]   # 只在有效区间里循环


def test_skip_panel_missing_sales_means_keep():
    idx = pd.DatetimeIndex(["2020-01-31"])
    D3p = _m([[0, 0, 1, 0, 0, 0]], idx)
    I3p = _m([[0, 0, 4, 0, 0, 0]], idx)                                             # 只有 c 成本压力大（偏间接）
    SALES = _m([[9, 5, np.nan, 5, 1, 8]], idx)                                      # c 的销售缺值 → 照做（登记文字「缺值照做」）
    assert not CS.skip_panel(D3p, I3p, SALES, "S4").iloc[0].any() and not CS.skip_panel(D3p, I3p, SALES, "S5").iloc[0].any()
