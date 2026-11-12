"""第四个研究循环第 8 轮 SSN（scripts/loop4_r08_season.py，2026-10-03 登记）：登记值与第四个循环的规则、业种月收益（等权、成员 ≥ 3 只）、
季节分（只用以前年份的同一个日历月份、≥ 10 年）、最低三分之一、票的被挡表（没有业种不挡）、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop4_r08_season as T  # noqa: E402
import research_loop4 as R4  # noqa: E402


def test_registered_constants_and_loop4_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.MIN_YEARS, T.MIN_MEMBERS) == (8, ("SSN",), False, "stock", 10, 3) and T.LOW_Q == pytest.approx(1 / 3)
    assert T.FAMILY == {"SSN": "选股·季节性"} and all(f.startswith(R4.FAMILY_PREFIX) for f in T.FAMILY.values())
    assert not set(T.IDS) & R4.previous_ids(ROOT / "var")
    st = R4.load_state(ROOT / "var")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R4.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND} for k in T.IDS], R4.previous_ids(ROOT / "var"))


def test_sector_monthly_needs_three_members():
    m = pd.period_range("2020-01", periods=2, freq="M")
    R = pd.DataFrame({"A": [0.01, 0.02], "B": [0.03, np.nan], "C": [0.05, 0.04], "D": [0.10, 0.10]}, index=m)
    S = T.sector_monthly(R, {"A": "x", "B": "x", "C": "x", "D": "y"})
    assert S["x"].iloc[0] == pytest.approx(0.03) and np.isnan(S["x"].iloc[1])   # 第二个月只有 2 只 → 不算
    assert S["y"].isna().all()                                                  # 只有 1 只的业种 → 不算


def test_season_score_uses_only_past_same_month():
    idx = pd.period_range("2000-01", "2012-12", freq="M")
    S = pd.DataFrame({"x": np.where(idx.month == 6, 0.05, 0.0), "y": np.where(idx.month == 6, -0.05, 0.01)}, index=idx)
    sc = T.season_score(S)
    t = pd.Period("2010-05", "M")                                               # 行 t → 打的是 6 月（t+1）的分：2000〜2009 的 6 月 = 10 年
    assert sc.loc[t, "x"] == pytest.approx(0.05) and sc.loc[t, "y"] == pytest.approx(-0.05)
    assert sc.loc[pd.Period("2009-05", "M")].isna().all()                       # 只有 9 年 → 不算
    S2 = S.copy()
    S2.loc[pd.Period("2010-06", "M"), "x"] = 9.9                                # 当年 6 月的值不能用在 2010-05 那一行
    assert T.season_score(S2).loc[t, "x"] == pytest.approx(0.05)


def test_bottom_third_and_ticker_block():
    m = pd.period_range("2021-01", periods=1, freq="M")
    P = pd.DataFrame({"x": [0.1], "y": [0.5], "z": [0.9], "w": [np.nan]}, index=m)
    B = T.bottom_third(P)
    assert list(B.iloc[0]) == [True, False, False, False]
    tb = T.ticker_block(B, ["A.T", "B.T", "C.T"], {"A.T": "x", "B.T": "z"})
    assert list(tb.iloc[0]) == [True, False, False]                             # 没有业种 → 不挡


def test_union_monthly_combines_eras():
    i1 = pd.bdate_range("2000-01-03", "2001-12-28")
    i2 = pd.bdate_range("2001-06-01", "2003-12-30")
    f1 = {"A.T": pd.DataFrame({"Close": np.linspace(100, 200, len(i1))}, index=i1)}
    f2 = {"A.T": pd.DataFrame({"Close": np.linspace(300, 400, len(i2))}, index=i2), "B.T": pd.DataFrame({"Close": np.ones(len(i2))}, index=i2)}
    months = pd.period_range("2000-01", "2003-12", freq="M")
    R = T.union_monthly([f1, f2], months)
    assert R["A.T"].loc[pd.Period("2000-06", "M")] == pytest.approx(T.RM.monthly_ret(f1["A.T"]["Close"]).loc[pd.Period("2000-06", "M")])
    assert R["A.T"].loc[pd.Period("2003-06", "M")] == pytest.approx(T.RM.monthly_ret(f2["A.T"]["Close"]).loc[pd.Period("2003-06", "M")])   # 后面的年代补上
    assert R["A.T"].loc[pd.Period("2001-08", "M")] == pytest.approx(T.RM.monthly_ret(f1["A.T"]["Close"]).loc[pd.Period("2001-08", "M")])   # 重叠 → 先出现的优先
    assert R["B.T"].loc[pd.Period("2000-06", "M")] != R["B.T"].loc[pd.Period("2000-06", "M")]                                               # 没有 → NaN


def test_wiring_and_cli():
    r = inspect.getsource(T.runs)
    assert '"SSN": {"em_tick": RM.em_tick_of(G[e], W["ctx"][e]["days"])}' in r
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **over)" in s1 and "R4.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    i = inspect.getsource(T.inputs)
    assert 'union_monthly([SM[e]["fa"] for e in L2.ERAS], months)' in i
    w = inspect.getsource(T.wiring)
    assert 'L2.run(W, "J", em_tick={})' in w and "n > 0" in w
    with pytest.raises(SystemExit):
        T.main(["--nope"])
