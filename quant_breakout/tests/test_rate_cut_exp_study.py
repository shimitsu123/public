"""「加息中新仓倍率不变、以后降息预期强 → 减仓」（scripts/rate_cut_exp_study.py 登记检验）：信号对齐（2 年国债 − 政策金利，月平均）、
条件（E ≤ θ、缺值 = 不满足、加息中一律不变）、开始变强的月（之前 12 个月都没有）与持续月数、判定 D1〜D5（含「账户期间没触发 → 不适用」）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rate_cut_exp_study as R                                               # noqa: E402


def _m(start, vals):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="ME"), dtype=float)


def test_constants():
    assert R.HIKE_D == 0.1 and R.THETAS == (-0.25, -0.50) and R.SPLIT == "2000-12-31" and R.ACCT0 == "2006-09-30" and R.EP_GAP == 12
    assert R.CANDS == {"J25": ("BOJ", -0.25), "J50": ("BOJ", -0.50), "F25": ("FED", -0.25), "F50": ("FED", -0.50)}
    assert (R.D_MIN, R.D5_UP, R.D5_TOL, R.MAX_ON, R.MIN_FOREIGN, R.MIN_MONTHS, R.SEEDS) == (0.02, 0.02, 0.01, 50.0, 5, 120, 30)


def test_signals_are_monthly_average_spreads_and_hiking_is_d12():
    days = pd.bdate_range("2000-01-03", "2002-12-31")
    y2 = pd.Series(np.where(days < pd.Timestamp("2001-07-01"), 6.0, 3.0), index=days)
    dff = pd.Series(np.where(days < pd.Timestamp("2001-01-01"), 6.5, 4.0), index=days)
    f = R.fed_signal(y2, dff)
    assert abs(f["e1"].loc["2000-06-30"] - (-0.5)) < 1e-9 and abs(f["e1"].loc["2001-03-31"] - 2.0) < 1e-9 and abs(f["e1"].loc["2002-06-30"] + 1.0) < 1e-9
    assert not f["hike"].loc["2000-12-31"] and not f["hike"].loc["2001-12-31"]                             # 2000 年内没有 12 个月前的值 / 降息
    call = _m("1999-01-31", [1.0] * 12 + [1.5] * 24)
    pol_d12 = _m("2000-01-31", [0.5] * 12 + [0.0] * 12)
    b = R.boj_signal(y2, call, pol_d12)
    assert abs(b["e1"].loc["2000-06-30"] - 4.5) < 1e-9 and b["hike"].loc["2000-06-30"] and not b["hike"].loc["2001-06-30"]
    assert b["e1"].index[0] == pd.Timestamp("2000-01-31")                                                  # 两边都有值的月起


def test_condition_hiking_clause_and_missing_values():
    e = _m("2000-01-31", [-0.6, -0.3, -0.1, np.nan, -0.6, -0.26])
    hk = _m("2000-01-31", [False, True, False, False, False, np.nan]).astype(object)
    hk = hk.where(hk.notna(), np.nan)
    hiking = pd.Series([False, True, False, False, False, False], index=e.index)
    assert R.cond_of(e, hiking, -0.25).tolist() == [True, False, False, False, True, True]                  # 加息中不变；缺值 = 不满足
    assert R.cond_of(e, hiking, -0.50).tolist() == [True, False, False, False, True, False]
    assert R.cond_of(e, None, -0.25).tolist() == [True, True, False, False, True, True]                     # U1：不看加息
    short = pd.Series([True], index=[e.index[1]])
    assert R.cond_of(e, short, -0.25).tolist() == [True, False, False, False, True, True]                  # 加息中缺值 = 不在加息中
    gap = e.drop(e.index[2])
    assert len(R.cond_of(gap, None, -0.25)) == 6                                                            # 缺月补成连续月末


def test_episode_starts_and_run_lengths():
    v = [False] * 14 + [True] * 3 + [False] * 5 + [True] * 2 + [False] * 12 + [True]
    c = pd.Series(v, index=pd.date_range("2000-01-31", periods=len(v), freq="ME"))
    st = R.episode_starts(c)
    assert [t.strftime("%Y-%m") for t in st] == ["2001-03", "2003-01"]                                     # 2001-11 那段之前 12 个月里有满足 → 不算
    assert R.run_lengths(c) == [("2001-03", 3), ("2001-11", 2), ("2003-01", 1)]
    early = pd.Series([True] + [False] * 13 + [True], index=pd.date_range("2000-01-31", periods=15, freq="ME"))
    assert [t.strftime("%Y-%m") for t in R.episode_starts(early)] == ["2001-03"]                             # 序列开头不足 12 个月不算


def _x(delta, q95, on=10.0, h1=0.03, h2=0.03):
    return {"n": 300, "delta": delta, "on_share": on, "placebo": {"q95": q95, "vals": [0.0, 0.0, 0.0]},
            "halves": {"h1": {"delta": h1}, "h2": {"delta": h2}}}


def test_decide_all_paths():
    good_m, bad_m = {"n": 200, "delta": 0.02, "placebo": {"vals": [0.0, 0.0, 0.0]}}, {"n": 200, "delta": -0.02, "placebo": {"vals": [0.0, 0.0, 0.0]}}
    horiz = {-0.25: {"US": good_m, "DE": good_m, "GB": good_m, "FR": good_m, "CA": good_m, "AU": bad_m, "JP": bad_m, "XX": {**good_m, "n": 60}},
             -0.50: {"US": good_m, "DE": bad_m, "GB": bad_m, "FR": good_m, "CA": good_m}}
    us = {-0.25: _x(0.03, 0.01), -0.50: _x(0.03, 0.01, h1=0.01)}
    nk = {"J25": _x(0.03, 0.02), "J50": _x(0.03, 0.02), "F25": _x(0.03, 0.02), "F50": _x(0.01, 0.0)}
    acct = {"J25": None, "J50": {"D5": True}, "F25": {"D5": True}, "F50": {"D5": False}}
    d = R.decide(nk, us, horiz, acct)
    assert d["J25"]["pass14"] and d["J25"]["D5"] is None and d["J25"]["verdict"].startswith("提议做前向记录")
    assert d["J25"]["h"] == {"n_foreign": 6, "share_pos": 83.0, "mean": 0.013, "pooled_q95": 0.0}
    assert d["F25"]["verdict"] == "提议（要用户确认）"
    assert not d["J50"]["D2"] and not d["J50"]["D4"] and d["J50"]["verdict"] == "不通过"                     # 美国 H1 只 +0.01、横向 3 / 5
    assert not d["F50"]["D1"] and d["F50"]["verdict"] == "不通过"
    nk2 = {**nk, "F25": _x(0.03, 0.05)}
    assert not R.decide(nk2, us, horiz, acct)["F25"]["D1"]                                                   # 没超过安慰剂
    nk3 = {**nk, "F25": _x(0.03, 0.02, on=60.0)}
    assert not R.decide(nk3, us, horiz, acct)["F25"]["D3"]                                                   # 变相长期减半
