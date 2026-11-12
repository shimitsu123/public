"""跟着时代调整（scripts/adaptive_study.py；2026-09-26 事先登记）：选择只用选择日以前的权益、同分选现行、逐年名次、
真实切换只换那两列且只换那一段、业种期望只用之前已平仓的交易、跳过 / 排序、判定。"""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak.config import StrategyParams

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import adaptive_study as AD                                                   # noqa: E402

DAYS = pd.bdate_range("2006-10-02", "2013-12-31")


def _curve(rets: dict[int, float], noise: float = 0.0, seed: int = 0) -> pd.Series:
    """每年一个日收益率（{年: 日收益}），可加一点噪音（让回撤不为 0）。"""
    rng = np.random.default_rng(seed)
    r = np.array([rets.get(d.year, 0.0) for d in DAYS]) + rng.standard_normal(len(DAYS)) * noise
    return pd.Series(100 * np.cumprod(1 + r), index=DAYS)


def test_combos_grid_and_current_first():
    base = StrategyParams()
    C = AD.combos(base)
    keys = [k for k, _ in C]
    assert len(C) == 36 and len(set(keys)) == 36 and keys[0] == AD.key_of(base) == "60/15/12/26"
    assert all(p.macd_signal == base.macd_signal and p.stop_loss_pct == base.stop_loss_pct for _, p in C)  # 只改网格里的阈值
    with pytest.raises(ValueError):
        AD.combos(replace(base, range_n=55))


def test_period_starts():
    y = AD.period_starts(DAYS, "Y", "2011-10-01")
    assert [d.strftime("%Y-%m-%d") for d in y] == ["2012-01-02", "2013-01-01"]
    m = AD.period_starts(DAYS, "M", "2013-10-15")
    assert [d.strftime("%Y-%m-%d") for d in m] == ["2013-11-01", "2013-12-02"]


def test_select_uses_only_past_and_ties_go_to_current():
    E = pd.DataFrame({"cur": _curve({}, 0.002, 1), "b": _curve({y: 0.001 for y in range(2006, 2012)}, 0.002, 2),
                      "c": _curve({2012: 0.01, 2013: 0.01}, 0.002, 3)})                 # c 只在 2012 以后好
    s = pd.Timestamp("2012-01-02")
    assert AD.select(E, [s], 5, "calmar") == {s: "b"}
    later = E.copy()
    later.loc[later.index >= s, "b"] = 1.0                                   # 改掉选择日以后的 → 选择不变
    assert AD.select(later, [s], 5, "calmar") == {s: "b"}
    same = pd.DataFrame({"cur": E["b"], "x": E["b"]})
    assert AD.select(same, [s], 5, "calmar") == {s: "cur"} and AD.select(same, [s], 5, "rank") == {s: "cur"}


def test_rank_prefers_steady_over_one_lucky_year():
    steady = _curve({y: 0.0003 for y in range(2006, 2012)}, 0.002, 4)
    lucky = _curve({2007: -0.0001, 2008: -0.0001, 2009: -0.0001, 2010: -0.0001, 2011: 0.004}, 0.002, 5)  # 只有 2011 年大赚
    E = pd.DataFrame({"cur": _curve({}, 0.002, 6), "steady": steady, "lucky": lucky})
    s = pd.Timestamp("2012-01-02")
    assert AD.select(E, [s], 5, "calmar") == {s: "lucky"}                    # 5 年合起来看，一次好运气就能胜出
    assert AD.select(E, [s], 5, "rank") == {s: "steady"}                     # 逐年名次平均：稳的胜出


def _ind(n: int = 30):
    ix = pd.bdate_range("2011-12-20", periods=n)
    df = pd.DataFrame({"Close": np.arange(n, dtype=float) + 100, "entry": False, "dead_cross": False, "atr": 1.0}, index=ix)
    return {"1111.T": df, "2222.T": df.copy()}


def test_switched_replaces_two_columns_only_in_chosen_period():
    base = _ind()
    ix = base["1111.T"].index
    ones = (np.ones(len(ix), bool), np.ones(len(ix), bool))
    sig = {"cur": {t: (np.zeros(len(ix), bool), np.zeros(len(ix), bool)) for t in base}, "alt": {t: ones for t in base}}
    s1, s2 = ix[5], ix[15]
    out = AD.switched(base, sig, {s1: "alt", s2: "cur"}, "cur")
    d = out["1111.T"]
    m = (ix >= s1) & (ix < s2)
    assert d["entry"].tolist() == m.tolist() and d["dead_cross"].tolist() == m.tolist()  # 只在 [s1, s2) 换成 alt
    assert d["Close"].equals(base["1111.T"]["Close"]) and d["atr"].equals(base["1111.T"]["atr"])
    assert not base["1111.T"]["entry"].any()                                 # 不改原表
    last = AD.switched(base, sig, {s1: "cur", s2: "alt"}, "cur")["2222.T"]
    assert last["entry"].tolist() == (ix >= s2).tolist()                     # 最后一段到期末


def _trades():
    return pd.DataFrame({
        "ticker": ["1111.T"] * 12 + ["2222.T"] * 12 + ["3333.T"] * 12 + ["4444.T"],
        "sig_date": pd.to_datetime(["2012-06-01"] * 36 + ["2012-06-01"]),
        "exit_date": pd.to_datetime(["2012-07-01"] * 36 + ["2013-02-01"]),
        "net": [-2.0] * 12 + [1.0] * 12 + [3.0] * 12 + [-50.0]})


SEC = {"1111.T": "A", "2222.T": "B", "3333.T": "C", "4444.T": "A"}


def test_sector_tables_only_closed_trades_before_month():
    T = _trades()
    s = [pd.Timestamp("2012-07-02"), pd.Timestamp("2013-03-01"), pd.Timestamp("2015-07-01")]
    tabs = AD.sector_tables(T, SEC, s)
    assert tabs[s[0]] == {"A": -2.0, "B": 1.0, "C": 3.0}                     # 2013-02 才平仓的那笔还不知道
    assert tabs[s[1]]["A"] == pytest.approx((-2.0 * 12 - 50) / 13)
    assert tabs[s[2]] == {}                                                  # 超过 36 个月
    few = AD.sector_tables(T.iloc[:5], SEC, s[:1])
    assert few[s[0]] == {}                                                   # 不到 10 笔不排
    assert AD.cold({"A": -2.0, "B": 1.0, "C": 3.0}) == {"A"} and AD.cold({"A": 1.0, "B": 2.0}) == set()


def test_skip_cold_and_sector_prio():
    ind = _ind()
    ix = ind["1111.T"].index
    for t in ind:
        ind[t].loc[[ix[2], ix[20]], "entry"] = True                          # 2011-12 一个、2012-01 一个
    tabs = {pd.Timestamp("2012-01-02"): {"A": -2.0, "B": 1.0, "C": 3.0}}
    out, n = AD.skip_cold(ind, SEC, tabs)
    assert n == 1 and out["1111.T"]["entry"].tolist().count(True) == 1 and bool(out["1111.T"].loc[ix[2], "entry"])
    assert out["2222.T"] is ind["2222.T"]                                    # B 不冷，不动
    assert bool(ind["1111.T"].loc[ix[20], "entry"])                          # 不改原表
    pr = AD.sector_prio({**ind, "9999.T": ind["2222.T"]}, SEC, tabs)
    assert pr == {("1111.T", ix[20]): -2.0, ("2222.T", ix[20]): 1.0, ("9999.T", ix[20]): 1.0}  # 月初以前的信号不给分；没业种 = 中位数


def test_spearman_and_persistence():
    a = pd.Series({"x": 1.0, "y": 2.0, "z": 3.0, "u": 4.0, "v": 5.0})
    assert AD.spearman(a, a * 10) == 1.0 and AD.spearman(a, -a) == -1.0 and AD.spearman(a.iloc[:4], a.iloc[:4]) is None
    s = AD._summ({2012: 0.5, 2013: -0.1, 2014: None})
    assert s["mean"] == 0.2 and s["pos"] == 1 and s["n"] == 2


def _r(oos, h1, h2, cagr, dd):
    return {"oos": {"calmar": oos, "cagr": cagr, "dd": dd}, "h1": {"calmar": h1}, "h2": {"calmar": h2}}


def test_decide_rules():
    R = {"BASE": _r(0.40, 0.30, 0.50, 12.0, -30.0),
         "A1": _r(0.46, 0.31, 0.55, 12.5, -31.0),                            # 通过
         "A2": _r(0.44, 0.31, 0.55, 12.5, -31.0),                            # 只 +0.04 → 不通过
         "A3": _r(0.60, 0.25, 0.90, 14.0, -25.0),                            # 前半变差 → 不通过
         "A4": _r(0.50, 0.35, 0.60, 11.5, -23.0),                            # 年化低 → 不通过
         "A5": _r(0.50, 0.35, 0.60, 15.0, -32.5)}                            # 回撤深 2.5 pp → 不通过
    V = AD.decide(R)
    assert V["best"] == "A1" and not V["per"]["A1"]
    assert all(V["per"][k] for k in ("A2", "A3", "A4", "A5"))
