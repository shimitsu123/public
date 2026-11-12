"""scripts/bsh_common.py / bsh_explore.py（买点 / 卖点 / 持有时间 横展开）：买点变换（MACD 零轴上下、跟进确认往后挪一天、第一次 / 重复信号）、
离场判定（与现行同顺序；赢家放宽后不看死叉、换慢出场、吊灯、20 日线、假突破、死叉两天确认、前几天不看死叉）、探索的入选规则与挑选。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bsh_common as BC  # noqa: E402
import bsh_explore as BX  # noqa: E402


def _frame(entry, close, macd=None):
    idx = pd.bdate_range("2024-01-01", periods=len(entry))
    return pd.DataFrame({"entry": entry, "Close": close, "macd": macd if macd is not None else np.zeros(len(entry))}, index=idx)


def test_entry_transform_macd_sign_and_follow_and_repeat():
    df = _frame([False, True, False, True, False, False], [10, 11, 12, 11, 10, 10], macd=[0, 0.5, 0, -0.2, 0, 0])
    fr = {"A": df}
    assert list(BC.entry_transform(fr, "macd_pos")["A"]["entry"]) == [False, True, False, False, False, False]
    assert list(BC.entry_transform(fr, "macd_neg")["A"]["entry"]) == [False, False, False, True, False, False]
    f = BC.entry_transform(fr, "follow")["A"]["entry"].tolist()
    assert f == [False, False, True, False, False, False]                       # 第 1 天的信号：第 2 天收盘 12 > 11 → 第 2 天成为信号日；第 3 天的：10 < 11 → 不买
    assert BC.entry_transform(fr, None) is fr
    rep = BC.entry_transform(fr, "repeat")["A"]["entry"].tolist()
    first = BC.entry_transform(fr, "first")["A"]["entry"].tolist()
    assert first == [False, True, False, False, False, False] and rep == [False, False, False, True, False, False]
    far = _frame([True] + [False] * 25 + [True], [10.0] * 27)
    assert BC.entry_transform({"A": far}, "first")["A"]["entry"].tolist()[-1]    # 相隔 26 天 → 又算第一次


def _s(**k):
    s = {"hold": 5, "entry_px": 100.0, "peak": 105.0, "c": 103.0, "climax": False, "dead": False, "dead_prev": False, "below": False,
         "ma20": np.nan, "low10": np.nan, "atr": 2.0, "sig_low": np.nan, "exit_climax": True, "climax_gain": 5.0, "use_dead": True,
         "max_hold": 60, "ts_days": 0, "ts_min": 0.0}
    s.update(k)
    return s


def test_exit_reason_current_order_and_relax():
    assert BC.exit_reason({}, _s(dead=True)) == "dead_cross"
    assert BC.exit_reason({}, _s(dead=True, climax=True, c=106.0)) == "climax"                 # 放量阴线在前
    assert BC.exit_reason({}, _s(hold=60)) == "max_hold"
    X1 = BC.VARIANTS["X1"]["exit"]
    assert BC.exit_reason(X1, _s(dead=True, peak=109.9)) == "dead_cross"                         # 还没到过 +10%
    assert BC.exit_reason(X1, _s(dead=True, peak=110.0)) is None                                 # 到过 +10% → 不看死叉
    assert BC.exit_reason(X1, _s(dead=True, peak=110.0, hold=60)) == "max_hold"
    X4 = BC.VARIANTS["X4"]["exit"]
    assert BC.exit_reason(X4, _s(peak=112.0, c=104.0, ma20=105.0)) == "w_ma20"
    assert BC.exit_reason(X4, _s(peak=112.0, c=106.0, ma20=105.0, dead=True)) is None
    X5 = BC.VARIANTS["X5"]["exit"]
    assert BC.exit_reason(X5, _s(peak=112.0, c=99.0, low10=100.0)) == "w_low10"


def test_exit_reason_replacements_fail_confirm_grace():
    X6 = BC.VARIANTS["X6"]["exit"]
    assert BC.exit_reason(X6, _s(peak=110.0, atr=2.0, c=103.9, dead=True)) == "chandelier"       # 110 − 3×2 = 104
    assert BC.exit_reason(X6, _s(peak=110.0, atr=2.0, c=104.1, dead=True)) is None               # 死叉不再用
    X7 = BC.VARIANTS["X7"]["exit"]
    assert BC.exit_reason(X7, _s(c=99.0, ma20=100.0)) == "ma20" and BC.exit_reason(X7, _s(dead=True, ma20=90.0)) is None
    X8 = BC.VARIANTS["X8"]["exit"]
    assert BC.exit_reason(X8, _s(hold=3, c=97.0, sig_low=98.0)) == "fail"
    assert BC.exit_reason(X8, _s(hold=11, c=97.0, sig_low=98.0)) is None                          # 10 天以后不再看
    assert BC.exit_reason(X8, _s(hold=11, c=97.0, sig_low=98.0, dead=True)) == "dead_cross"
    X9 = BC.VARIANTS["X9"]["exit"]
    assert BC.exit_reason(X9, _s(dead=True)) is None
    assert BC.exit_reason(X9, _s(dead_prev=True, below=True)) == "dead_cross2"
    assert BC.exit_reason(X9, _s(dead_prev=True, below=False)) is None                           # 第二天又回到信号线上
    H3 = BC.VARIANTS["H3"]["exit"]
    assert BC.exit_reason(H3, _s(hold=2, dead=True)) is None
    assert BC.exit_reason(H3, _s(hold=4, below=True)) == "dead_cross"                            # 宽限期里死叉、第 4 天还在下面 → 卖
    assert BC.exit_reason(H3, _s(hold=5, below=True)) is None                                    # 第 5 天起只看新的死叉
    assert BC.exit_reason(H3, _s(hold=5, dead=True)) == "dead_cross"
    XC = BC.VARIANTS["XC"]["exit"]
    assert BC.exit_reason(XC, _s(hold=2, c=97.0, sig_low=98.0)) == "fail"
    assert BC.exit_reason(XC, _s(peak=111.0, dead=True)) is None


def _sum(cal, dd=-30.0, mean=0.6, halves=(0.3, 0.3)):
    return {"calmar": cal, "dd": dd, "mean": mean, "halves": list(halves)}


def test_qualifies_and_pick():
    base = {"E": _sum(0.285), "J": _sum(0.388)}
    good = {"E": _sum(0.33, halves=(0.31, 0.31)), "J": _sum(0.43, halves=(0.31, 0.29))}
    assert BX.qualifies(good, base) == []                                                        # 一个半段低于现行：允许
    bad = {"E": _sum(0.33, mean=0.5), "J": _sum(0.40, dd=-33.0, halves=(0.2, 0.2))}
    f = BX.qualifies(bad, base)
    assert any("每笔" in x for x in f) and any("J Calmar" in x for x in f) and any("回撤" in x for x in f) and any("半段" in x for x in f)
    res = {k: good for k in ("X1", "X2", "X3", "X4", "B1", "B2", "H1")}
    res["X1"] = {"E": _sum(0.40, halves=(0.4, 0.4)), "J": _sum(0.50, halves=(0.4, 0.4))}
    res["B2"] = {"E": _sum(0.34, halves=(0.4, 0.4)), "J": _sum(0.44, halves=(0.4, 0.4))}
    out = BX.pick(res, base)
    assert out[0] == "X1" and len(out) == 5
    assert sum(BC.VARIANTS[k]["fam"] == "X" for k in out) <= 3 and not ({"B1", "B2"} <= set(out))
