"""scripts/model_switch_study.py：事先写定的常数、个股层的月结果、共同决定月、上限 / 固定模型、输出（合成数据）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import model_switch_study as S  # noqa: E402


def test_constants():
    assert S.METHODS == ("KNN", "HMM", "MOM1", "MOM3", "MOM12", "TAB") and len(S.METHODS) * len(S.MENUS) == 12
    assert np.isclose(S.P_MAX, 0.05 / 12) and S.T_MIN == 2.0 and S.MIN_SHIFT == 12
    assert (S.KNN_K, S.KNN_MIN, S.MAP_MIN, S.Z_MIN, S.HMM_MIN) == (12, 24, 12, 36, 60)
    assert S.MENUS["K"]["base"] == "Q" and S.MENUS["K"]["lag"] == 0 and S.K_MODELS == ("A", "Q", "B", "C", "D", "E", "F", "G")
    assert S.MENUS["S"]["base"] == "base" and S.MENUS["S"]["lag"] == 5 and S.S_MODELS == ("tight", "base", "wide")
    assert S.MENUS["K"]["eras"]["P"] == ("1996-01", "2006-09") and S.MENUS["S"]["eras"]["J"] == ("2017-01", "2026-09")
    assert S.K_START == "1996-01" and S.POOL_ERA == {"Zx": "Z", "W": "E", "Jx": "J"}


def test_stock_menu_uses_only_complete_signals():
    T = pd.DataFrame({"date": pd.to_datetime(["2010-01-05", "2010-01-20", "2010-02-03", "2010-02-10"]),
                      "tight": [1.0, 3.0, 2.0, np.nan], "base": [2.0, 4.0, 1.0, 9.0], "wide": [0.0, 2.0, 5.0, 9.0]})
    P = S.stock_menu(T, pd.period_range("2009-12", "2010-03", freq="M"))
    assert np.isnan(P.iloc[0]).all() and np.isnan(P.iloc[3]).all()
    assert list(P.loc[pd.Period("2010-01", "M")]) == [2.0, 3.0, 1.0] and list(P.loc[pd.Period("2010-02", "M")]) == [2.0, 1.0, 5.0]


def test_common_window_oracle_fixed():
    idx = pd.period_range("2000-01", periods=6, freq="M")
    P = pd.DataFrame({"a": [1.0, 2.0, 3.0, np.nan, 1.0, 0.0], "b": [0.0, 4.0, 1.0, np.nan, 3.0, 2.0]}, index=idx)
    PK = {"X": pd.Series(["a"] * 6, index=idx, dtype=object), "Y": pd.Series([None, "b", "b", "b", "b", "b"], index=idx, dtype=object)}
    ts = S.common_window(PK, P, None)
    assert ts == [idx[1], idx[3], idx[4]]                                              # idx[2] 的下一个月全 NaN；idx[5] 没有下一个月
    assert S.common_window(PK, P, "2000-05") == [idx[3], idx[4]]
    assert np.isclose(S.oracle(P, ts), np.mean([3 - 2, 3 - 2, 2 - 1]))
    fb = S.fixed_best(P, ts, {"E1": ("2000-01", "2000-03"), "E2": ("2000-04", "2000-12")})
    assert fb["E1"]["best"] == "a" and fb["E2"]["best"] == "b"


def test_render_smoke():
    m = {"n": 3, "g": 0.1, "t": 2.5, "eras": {}, "h": 0.05, "p": 0.001, "c": [True, True, True, True], "pass": True, "share": {"Q": 60.0, "A": 40.0}}

    def menu(name):
        eras = {k: 0.1 for k in S.MENUS[name]["eras"]}
        return {"window": ["1996-01", "2026-09"], "n_dec": 3, "oracle": 1.0, "fixed": {"P": {"best": "Q", "mean": {}}},
                "now": {k: "Q" for k in S.METHODS}, "methods": {k: {**m, "eras": eras} for k in S.METHODS}}

    md = S.render({"code": "abc", "K": menu("K"), "S": menu("S"), "passed": ["K KNN"]})
    assert md.startswith("# 按当前局势判断用哪个模型") and "K KNN" in md and md.rstrip().endswith("非投资建议。")
