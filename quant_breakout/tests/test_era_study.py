"""scripts/era_study.py（时代主线）：排名只用跳过最近 1 个月之前的数据、选中的持有下一个月、缺数据的行业不参加、NW t 值、描述统计。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import era_study as E                                                        # noqa: E402


def _R(n=90, k=6, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2000-01-01", periods=n, freq="MS")
    return pd.DataFrame(rng.normal(0.5, 4, (n, k)), index=idx, columns=[f"I{j}" for j in range(k)])


def test_past_log_skips_latest_month_and_needs_full_window():
    R = _R()
    p = E.past_log(R, 12)
    L = np.log1p(R / 100) * 100
    t = 30
    assert np.isclose(p.iloc[t, 0], L.iloc[t - 11:t, 0].sum())                   # 第 t−11 … t−1 个月（不含第 t 个月）
    R2 = R.copy()
    R2.iloc[t, 0] = 99.0                                                         # 改第 t 个月 → 行 t 的分数不变
    assert np.isclose(E.past_log(R2, 12).iloc[t, 0], p.iloc[t, 0])
    R3 = R.copy()
    R3.iloc[t - 5, 1] = np.nan
    assert np.isnan(E.past_log(R3, 12).iloc[t, 1])                               # 窗口里缺一个月 → 不参加
    assert p.iloc[:11].isna().all().all() and p.iloc[11].notna().all()


def test_select_and_backtest_hold_next_month():
    idx = pd.date_range("2000-01-01", periods=4, freq="MS")
    R = pd.DataFrame({"A": [1.0, 2.0, 3.0, 4.0], "B": [10.0, 20.0, 30.0, 40.0], "C": [5.0, 5.0, np.nan, 5.0]}, index=idx)
    S = pd.DataFrame({"A": [3.0, 1.0, 1.0, 1.0], "B": [2.0, 2.0, 2.0, 2.0], "C": [1.0, 3.0, np.nan, 3.0]}, index=idx)
    sel = E.select_top(S, 2)
    assert sel.iloc[0].tolist() == [True, True, False] and sel.iloc[1].tolist() == [False, True, True]
    ret = E.backtest(R, sel)
    assert np.isnan(ret.iloc[0])                                                 # 第一个月没有上个月的选择
    assert ret.iloc[1] == (2.0 + 20.0) / 2                                       # 行 0 选 A、B → 持有第 1 个月
    assert ret.iloc[2] == 30.0                                                   # 行 1 选 B、C；C 第 2 个月缺 → 只算 B
    assert np.isclose(E.turnover(sel), 0.5)                                      # 每个月换掉 2 个里的 1 个


def test_scores_ranges_and_nw_t():
    R = _R(120)
    S = E.scores(R)
    er, en = S["ER"].dropna(how="all"), S["EN"].dropna(how="all")
    assert er.min().min() > 0 and er.max().max() <= 1 and en.min().min() >= -1 and en.max().max() <= 1
    assert S["E60"].iloc[:59].isna().all().all() and S["E60"].iloc[59].notna().all()
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(0.5, 1, 600))
    t = E.nw_t(x)
    assert 8 < t < 16                                                            # 均值 0.5、标准差 1、600 个月 → 约 12
    assert abs(E.nw_t(pd.Series(rng.normal(0, 1, 600)))) < 3
    s = E.seg_stats(pd.Series([1.0] * 12 + [-1.0] * 12 + [1.0] * 12, index=pd.date_range("2000-01-01", periods=36, freq="MS")))
    assert s["n"] == 36 and np.isclose(s["ann"], 4.0) and s["mdd"] == -12.0


def test_persistence_and_stay_top_detect_persistent_leaders():
    idx = pd.date_range("1950-01-01", periods=12 * 40, freq="MS")
    rng = np.random.default_rng(3)
    k = 30
    drift = np.linspace(-1, 1, k)                                                # 每个行业有固定的长期相对强弱 → 名次会持续
    Rel = pd.DataFrame(rng.normal(0, 3, (len(idx), k)) + drift, index=idx, columns=[f"I{j}" for j in range(k)])
    p = E.persistence(Rel, 5)
    assert p["all"] > 0.5 and p["n"] > 20
    st = E.stay_top(Rel)
    assert st[5]["stay"] > 2 * st[5]["random"]
    dec = E.decade_leaders(Rel)
    assert dec["1950s"]["top"][0][0] == "I29" or dec["1950s"]["top"][0][0] in {f"I{j}" for j in range(25, 30)}
