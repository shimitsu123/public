"""qbreak/tankan.py 的売上高计划（cost_sales_study）：代码、旧分类拼接、按公布时间取最新计划、实绩中位只用已公布的、价格转嫁、東証业种映射。"""
import numpy as np
import pandas as pd

from qbreak import tankan as TK


def _fetch(code):
    k = int(code[-5])
    ind = code[5:9]
    years = range(2000, 2021)
    if ind == "1140":                                                          # 旧分类只到 2009 年度
        return pd.Series({y: 100.0 + k for y in years if y <= 2009})
    if ind == "1149":
        return pd.Series({y: 200.0 + k for y in years if y >= 2010})
    if ind == "1160":
        base = {y: float(y - 2000) for y in years}                             # 实绩 = 年度 − 2000
        return pd.Series(base if k == 0 else {y: 50.0 + k for y in years})
    return pd.Series(dtype=float)


def test_sales_code_and_splice():
    assert TK.sales_code("1150", 4) == "TK99G1150102CFY41000"
    S = TK.load_sales(_fetch)
    assert set(S) == {0, 2, 3, 4, 5} and "1140" not in S[4].columns
    assert S[4].loc[2009, "1149"] == 104.0 and S[4].loc[2010, "1149"] == 204.0   # 2009 年度以前用旧分类


def test_sales_strength_latest_survey_and_history():
    S = TK.load_sales(_fetch)
    months = pd.DatetimeIndex(["2015-03-31", "2015-04-30", "2015-06-30", "2015-07-31", "2015-10-31", "2015-12-31"])
    X = TK.sales_strength(S, months)
    # 2015-03 末：年度 2014、最新 = 12 月调查（k = 2 → 52）；实绩可用到 2013 年度（2014-07-05 之后）→ 过去 10 个 2004〜2013 → 中位 8.5
    assert np.isclose(X.loc["2015-03-31", "1160"], 52.0 - 8.5)
    assert np.isclose(X.loc["2015-04-30", "1160"], 55.0 - 8.5)                 # 年度 2015 的 3 月调查；2014 年度实绩要到 7/5
    assert np.isclose(X.loc["2015-06-30", "1160"], 55.0 - 8.5)
    assert np.isclose(X.loc["2015-07-31", "1160"], 54.0 - 9.5)                 # 6 月调查；2014 年度实绩已可用 → 2005〜2014
    assert np.isclose(X.loc["2015-10-31", "1160"], 53.0 - 9.5) and np.isclose(X.loc["2015-12-31", "1160"], 52.0 - 9.5)
    few = TK.sales_strength(S, pd.DatetimeIndex(["2003-05-31"]))
    assert np.isnan(few.loc["2003-05-31", "1160"])                              # 实绩不到 5 个年度 → 缺值


def test_pass_through_uses_release_date_and_to_tse():
    q = pd.DatetimeIndex(["2020-03-31", "2020-06-30"])
    T = {"sell": pd.DataFrame({"1160": [10.0, 20.0]}, index=q), "buy": pd.DataFrame({"1160": [5.0, 30.0]}, index=q)}
    P = TK.pass_through(T, pd.DatetimeIndex(["2020-04-30", "2020-06-30", "2020-07-31"]))
    assert P.loc["2020-04-30", "1160"] == 5.0 and P.loc["2020-06-30", "1160"] == 5.0 and P.loc["2020-07-31", "1160"] == -10.0
    X = pd.DataFrame({"2081": [1.0], "2082": [3.0], "2040": [2.0]}, index=pd.DatetimeIndex(["2020-01-31"]))
    G = TK.to_tse(X, ["サービス業", "陸運業", "銀行業"])
    assert G.loc["2020-01-31", "サービス業"] == 2.0 and G.loc["2020-01-31", "陸運業"] == 2.0 and "銀行業" not in G.columns
