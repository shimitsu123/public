"""qbreak/tankan.py 的売上高计划（cost_sales_study）：代码、旧分类拼接、同一次调查比自己的标准化、按公布时间取最新一次（有值的那一次）、
修正率、价格转嫁、東証业种映射。"""
import numpy as np
import pandas as pd

from qbreak import tankan as TK

YEARS = range(2000, 2021)


def _fetch(code):
    k = int(code[-5])
    ind = code[5:9]
    if ind == "1140":                                                          # 旧分类只到 2009 年度
        return pd.Series({y: 100.0 + k for y in YEARS if y <= 2009})
    if ind == "1149":
        return pd.Series({y: 200.0 + k for y in YEARS if y >= 2010})
    if ind == "1160":
        if k == 4:
            return pd.Series({y: float(y - 2000) for y in YEARS if y != 2016})   # 2016 年度 6 月调查缺 → 退回 3 月调查
        return pd.Series({y: float(y - 2000) + 0.5 * k for y in YEARS})
    return pd.Series(dtype=float)


def test_codes_and_splice():
    assert TK.sales_code("1150", 4) == "TK99G1150102CFY41000" and TK.sales_rev_code("1150", 4) == "TK99G11501022FY41000"
    S = TK.load_sales(_fetch)
    assert set(S) == {0, 2, 3, 4, 5} and "1140" not in S[4].columns
    assert S[4].loc[2009, "1149"] == 104.0 and S[4].loc[2010, "1149"] == 204.0   # 2009 年度以前用旧分类


def test_vintage_z_same_survey_baseline():
    S = TK.load_sales(_fetch)
    V = TK.vintage_z(S)
    assert 0 not in V
    # 6 月调查、2015 年度：之前 10 个年度 2005〜2014 = 5..14 → 中位 9.5、MAD 2.5 → (15 − 9.5) / (1.4826 × 2.5)
    assert np.isclose(V[4].loc[2015, "1160"], 5.5 / (1.4826 * 2.5))
    assert np.isnan(V[4].loc[2004, "1160"])                                      # 之前只有 4 个年度 → 缺值
    const = TK.vintage_z({4: pd.DataFrame({"x": [1.0] * 8 + [3.0]}, index=range(2000, 2009))})[4]
    assert np.isclose(const.loc[2008, "x"], 2.0 / (1.4826 * 0.5))                # MAD = 0 → 用下限 0.5 个百分点


def test_latest_vintage_release_dates_and_fallback():
    S = TK.load_sales(_fetch)
    V = TK.vintage_z(S)
    months = pd.DatetimeIndex(["2015-03-31", "2015-04-30", "2015-07-31", "2015-10-31", "2015-12-31", "2016-07-31"])
    X = TK.latest_vintage(V, months)
    assert np.isclose(X.loc["2015-03-31", "1160"], V[2].loc[2014, "1160"])     # 1〜3 月末 → 上一年度的 12 月调查
    assert np.isclose(X.loc["2015-04-30", "1160"], V[5].loc[2015, "1160"])
    assert np.isclose(X.loc["2015-07-31", "1160"], V[4].loc[2015, "1160"])
    assert np.isclose(X.loc["2015-10-31", "1160"], V[3].loc[2015, "1160"])
    assert np.isclose(X.loc["2015-12-31", "1160"], V[2].loc[2015, "1160"])
    assert np.isclose(X.loc["2016-07-31", "1160"], V[5].loc[2016, "1160"])     # 6 月调查缺 → 退回当时已有的 3 月调查
    assert np.allclose(TK.sales_strength(S, months)["1160"], X["1160"], equal_nan=True)


def test_sales_revision_has_no_value_before_june_survey():
    R = TK.load_sales_rev(_fetch)
    assert set(R) == set(TK.REV_SURVEYS)
    X = TK.sales_revision(R, pd.DatetimeIndex(["2015-05-31", "2015-08-31"]))
    assert np.isnan(X.loc["2015-05-31", "1160"]) and np.isclose(X.loc["2015-08-31", "1160"], R[4].loc[2015, "1160"])


def test_pass_through_uses_release_date_and_to_tse():
    q = pd.DatetimeIndex(["2020-03-31", "2020-06-30"])
    T = {"sell": pd.DataFrame({"1160": [10.0, 20.0]}, index=q), "buy": pd.DataFrame({"1160": [5.0, 30.0]}, index=q)}
    P = TK.pass_through(T, pd.DatetimeIndex(["2020-04-30", "2020-06-30", "2020-07-31"]))
    assert P.loc["2020-04-30", "1160"] == 5.0 and P.loc["2020-06-30", "1160"] == 5.0 and P.loc["2020-07-31", "1160"] == -10.0
    X = pd.DataFrame({"2081": [1.0], "2082": [3.0], "2040": [2.0]}, index=pd.DatetimeIndex(["2020-01-31"]))
    G = TK.to_tse(X, ["サービス業", "海運業", "銀行業"])
    assert G.loc["2020-01-31", "サービス業"] == 2.0 and G.loc["2020-01-31", "海運業"] == 2.0 and "銀行業" not in G.columns
