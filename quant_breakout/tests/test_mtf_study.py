"""scripts/mtf_study.py：候选只改 entry / dead_cross 两列（C1 条件出场、C2 周线出场、C3 见顶离场、C4 规则过滤、C5 周线突破系统）、
规则缺值不过滤、验证期的挑选规则、R 门槛、每年收益、逐笔统计。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import mtf_study as S                                                        # noqa: E402

IDX = pd.bdate_range("2026-01-05", periods=6)


def _ind():
    return pd.DataFrame({"entry": [True, False, True, False, True, False], "dead_cross": [False, True, False, False, True, False],
                         "macd": [1.0, -1.0, -2.0, 0.5, -1.0, -3.0], "macd_sig": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}, index=IDX)


def _f():
    return pd.DataFrame({"W1": [1, 1, 0, np.nan, 1, 1], "W2": [1, 1, 1, 1, 0, 1], "W3": 1.0, "W4v": [0.2, 0.5, np.nan, 0.3, 0.3, 0.3],
                         "W5v": 1.0, "W6v": 1.0, "M1": [1, 0, np.nan, 1, 1, 0], "M2v": [0.1, -0.1, np.nan, 0.0, 0.2, 0.1],
                         "M3": 1.0, "M4v": 1.0, "M5v": 0.1,
                         "E_X1": [False, False, False, True, False, True], "E_X2": False, "E_X3": [True, False, False, False, False, False],
                         "E_X4": False, "E_X5": False, "E_X6": False, "E_B26": [True, True, False, True, False, True]}, index=IDX)


def test_c1_strong_uses_weekly_exit_else_daily_macd_state():
    out = S.variant(_ind(), _f(), "C1")
    # 强势（W1 且 W2）：第 0、1、5 天 → 用 E_X1；其余 → MACD 在信号线下
    assert out["dead_cross"].tolist() == [False, False, True, False, True, True]
    assert out["entry"].tolist() == _ind()["entry"].tolist()


def test_c2_c3_only_change_dead_cross():
    assert S.variant(_ind(), _f(), "C2")["dead_cross"].tolist() == _f()["E_X1"].tolist()
    c3 = S.variant(_ind(), _f(), "C3", top="X3")
    assert c3["dead_cross"].tolist() == [True, True, False, False, True, False] and c3["entry"].tolist() == _ind()["entry"].tolist()


def test_c4_rules_missing_values_do_not_filter():
    f = _f()
    assert S.rule_keep("E1", f).tolist() == [True, True, False, True, True, True]          # W1 缺值 → 保留
    assert S.rule_keep("E12", f).tolist() == [True, False, False, True, True, False]
    assert S.rule_keep("E8", f).tolist() == [True, False, True, False, True, True]          # M2v = 0 不算 > 0
    assert S.rule_keep("E4", f, 0.3).tolist() == [True, False, True, True, True, True]
    c4 = S.variant(_ind(), f, "C4", rule="E7")
    assert c4["entry"].tolist() == [True, False, True, False, True, False]                 # 第 2 天 M1 缺值 → 保留
    assert c4["dead_cross"].tolist() == _ind()["dead_cross"].tolist()


def test_c5_weekly_system_masked_by_membership():
    member = pd.Series([True, True, True, False, True, True], index=IDX)
    out = S.variant(_ind(), _f(), "C5", member=member, masked=True)
    assert out["entry"].tolist() == [True, False, False, False, False, False]              # B26 且 M1 == 1 且 成员
    assert out["dead_cross"].tolist() == _f()["E_X1"].tolist()
    un = S.variant(_ind(), _f(), "C5")
    assert un["entry"].tolist() == [True, False, False, True, False, False]


def _ts(n, win, mean):
    return {"n": n, "win": win, "mean": mean, "med": mean, "pf": 1.0, "hold": 10.0}


def test_pick_top_and_rule():
    base = _ts(100, 40.0, 1.0)
    rows = {"X1": _ts(90, 39.0, 2.0), "X2": _ts(90, 41.0, 1.5), "X3": _ts(90, 40.0, 1.5), "X4": _ts(0, None, None)}
    assert S.pick_top(rows, base) == "X2"                                                  # X1 胜率降了；X2 / X3 一样 → 编号小
    assert S.pick_top({"X5": _ts(90, 41.0, 0.9)}, base) is None
    r = {"E1": {"keep": 0.49, "kept": _ts(49, 50.0, 3.0), "filt": _ts(51, 30.0, -1.0)},
         "E2": {"keep": 0.6, "kept": _ts(60, 45.0, 1.5), "filt": _ts(40, 35.0, 0.5)},
         "E3": {"keep": 0.7, "kept": _ts(70, 45.0, 2.0), "filt": _ts(30, 46.0, 0.0)},
         "E10": {"keep": 0.8, "kept": _ts(80, 45.0, 1.8), "filt": _ts(20, 30.0, 0.8)}}
    assert S.pick_rule(r) == "E2"                                                          # E1 保留 < 50%；E3 胜率不高；E2 / E10 差一样 → 编号小
    assert S.pick_rule({"E3": r["E3"]}) is None


def _st(cal, dd, win):
    return {"all": {"cagr": 10.0, "dd": dd, "calmar": cal}, "win": win}


def test_r_gate():
    base = _st(0.40, -30.0, 42.0)
    assert S.r_fails(_st(0.40, -31.9, 40.0), base) == []
    f = S.r_fails(_st(0.39, -32.5, 39.9), base)
    assert len(f) == 3 and "Calmar" in f[0] and "回撤" in f[1] and "胜率" in f[2]


def test_yearly_and_trade_stats():
    eq = pd.Series([100.0, 110.0, 121.0, 108.9], index=pd.to_datetime(["2017-01-04", "2017-12-29", "2018-12-28", "2019-06-28"]))
    assert S.yearly(eq) == {"2017": 10.0, "2018": 10.0, "2019": -10.0}
    T = pd.DataFrame({"sig_date": pd.to_datetime(["2018-05-01", "2019-03-01", "2024-01-05"]), "net": [2.0, -1.0, 3.0], "hold_days": [5, 10, 15]})
    assert S.tstats(S.period(T, *S.VAL)) == {"n": 1, "win": 0.0, "mean": -1.0, "med": -1.0, "pf": 0.0, "hold": 10.0}
    s = S.tstats(T)
    assert s["n"] == 3 and s["pf"] == 5.0 and s["win"] == 66.67
    assert len(S.period(T, *S.HOLD)) == 1


def test_exit_labels_for_every_row_of_part_c():
    labs = ["现行"] + list(S.TOPS) + ["C1", "C2", "C5"]
    out = [S.exit_label(x) for x in labs]
    assert out[0].startswith("现行（") and out[1].startswith("现行 + X1") and out[-1].startswith("C5 ")
