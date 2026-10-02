"""第二个研究循环第 3 轮 TBJ（scripts/loop2_r03_jgbrefuge.py，2026-10-02 登记）：登记值、阶梯总收益、晚一天、接法、费用表的 2561。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r02_bondrefuge as T2  # noqa: E402
import loop2_r03_jgbrefuge as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.JGB_T, T.JG_KEY) == (3, ("TBJ",), "核心·熊市避险资产", True, "2561.T", "US_JG")
    assert (T.LADDER, T.TRUST_FEE, T.REF_DATE, T.REF_PX, T.OLD) == ((5, 10, 20), 0.066, "2026-08-31", 1979.0, ("1987-01-01", "2000-12-31"))


def test_ladder_is_equal_weight_of_par_bonds():
    idx = pd.bdate_range("2020-01-01", periods=5)
    cur = pd.DataFrame({"5Y": [1.0, 1.1, 1.0, 0.9, 1.0], "10Y": [2.0, 2.0, 2.1, 2.0, 1.9], "20Y": [3.0, 3.1, 3.2, 3.0, 3.0]}, index=idx)
    got = T.ladder_tr(cur).pct_change().dropna()
    want = pd.concat([T2.par_bond_tr(cur[f"{t}Y"], float(t)).pct_change() for t in (5, 10, 20)], axis=1).dropna().mean(axis=1)
    assert np.allclose(got.to_numpy(), want.loc[got.index].to_numpy())
    cur2 = cur.copy(); cur2.loc[idx[2], "20Y"] = np.nan                                  # 有一个期限缺值的日子不算
    assert idx[2] not in T.ladder_tr(cur2).index


def test_close_is_previous_day_and_scaled():
    days = pd.bdate_range("2026-08-27", periods=4)                                       # 8/27 8/28 8/31 9/1
    tr = pd.Series([1.0, 1.1, 1.2, 1.3], index=days)
    c = T.jgb_close({"n225": pd.DataFrame({"Close": 1.0}, index=days)}, tr)
    assert c.index[0] == days[1] and np.isclose(c.loc[pd.Timestamp("2026-08-31")], T.REF_PX)   # 8/31 的值 = 8/28 的总收益，定在 ¥1,979
    assert np.isclose(c.iloc[-1] / c.loc[pd.Timestamp("2026-08-31")], 1.2 / 1.1)


def test_never_bull_jgb_equals_b1_wiring():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=6)
    bear = pd.Series([False, True, True, False, True, True], index=idx)
    o = T.tbj_over(bear, pd.Series(False, index=idx), pd.DataFrame({"Close": [1.0]}, index=[idx[0]]))
    assert o["cfg_over"]["core_mode"] == "follow" and o["cfg_over"]["core_index"] == {"1545.T": Y.UH_KEY, "2845.T": Y.HG_KEY, "2561.T": "US_JG"}
    assert o["extra_bear"]["US_JG"].all() and set(o["extra_core"]) == {"2561.T"}
    on = pd.Series([True, True, False, True, True, True], index=idx)
    o2 = T.tbj_over(bear, on, pd.DataFrame({"Close": [1.0]}, index=[idx[0]]))
    assert (~o2["extra_bear"]["US_JG"]).tolist() == [False, True, False, False, True, True]


def test_fee_table_has_2561():
    from qbreak.fees import etf_cost
    c = etf_cost("tachibana", "2561.T", "JP")
    assert c["lot"] == 1 and c["slip_pct"] == 0.10
