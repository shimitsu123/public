"""第五个研究循环第 8 轮 COR / WAV（scripts/loop5_r08_corwav.py，2026-10-03 登记）：登记值与第五个循环的规则、周收益的相关、
按自己最近 5 年的分位定倍数（下一个交易日起用）、5 日突破数、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop5_r08_corwav as T  # noqa: E402
import research_loop5 as R5  # noqa: E402


def test_registered_constants_and_loop5_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.M_LO, T.M_HI, T.COR_WIN, T.COR_MIN, T.REF_WIN, T.REF_MIN, T.WAVE_DAYS) == \
        (8, ("COR", "WAV"), False, 0.5, 1.36, 52, 40, 260, 104, 5)
    assert T.KIND == {"COR": "size_time", "WAV": "size_trade"} and T.CORE == "1545.T"
    assert all(T.FAMILY[k].startswith(R5.FAMILY_PREFIX) for k in T.IDS) and not set(T.IDS) & R5.previous_ids(ROOT / "var")
    st = R5.load_state(ROOT / "var")
    if not st:
        pytest.skip("第五个研究循环还没有登记")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R5.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND[k]} for k in T.IDS], R5.previous_ids(ROOT / "var"))


def test_weekly_corr():
    d = pd.bdate_range("2020-01-01", periods=400)
    rng = np.random.default_rng(0)
    a = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(d)))), index=d)
    r = T.weekly_corr(a, a * 2.0)                                           # 同一个走势 → 相关 1
    assert r.dropna().round(9).eq(1.0).all() and len(r.dropna()) > 0
    assert r.index.dayofweek.isin([4]).all()                                 # 周五
    b = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(d)))), index=d)
    assert abs(T.weekly_corr(a, b).dropna().iloc[-1]) < 0.5                  # 独立 → 相关小
    assert T.weekly_corr(a.iloc[:150], a.iloc[:150]).dropna().empty         # 不到 40 周 → 不算


def test_cor_mult_quantiles_and_lag():
    wk = pd.date_range("2010-01-01", periods=300, freq="W-FRI")
    rho = pd.Series(np.r_[np.linspace(0, 1, 299), np.nan], index=wk)
    rho.iloc[200] = -1.0                                                      # 远低于之前 → 低三分之一
    days = pd.bdate_range(wk[0], wk[-1] + pd.Timedelta(days=10))
    m = T.cor_mult(rho, days)
    assert m.loc[:wk[103]].eq(1.0).all()                                      # 不到 104 周 → 不变
    fri = wk[200]
    assert m.loc[fri] != 1.36 and m.loc[fri + pd.Timedelta(days=3)] == 1.36    # 周五的值从下周一起用
    assert m.loc[wk[150] + pd.Timedelta(days=3)] == 0.5                        # 一直上升 → 高三分之一
    assert m.loc[wk[-1] + pd.Timedelta(days=3)] == 1.0                         # 算不出 → 不变


def test_wave_series():
    days = pd.bdate_range("2021-01-04", periods=10)
    w = T.wave_series([days[0], days[0], days[2], days[7]], days)
    assert w.tolist() == [2, 2, 3, 3, 3, 1, 1, 1, 1, 1]                       # 5 个交易日的窗口（含当天）


def test_wiring_and_cli():
    r = inspect.getsource(T.runs)
    assert 'R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(M["COR"], days))' in r and 'R2V.csz_kw(M["sig"][e], M["WAV"][e], days)' in r
    i = inspect.getsource(T.inputs)
    assert 'weekly_corr(W["inp"]["n225"]["Close"], W["assets"][CORE]["Close"])' in i and "wav_mult_for(sig[e][\"date\"], ref, wave)" in i
    assert 'R6V.rank_mult(v, R6V.past_cuts(ref["date"], ref["wv"].to_numpy(float), dates), True)' in inspect.getsource(T.wav_mult_for)
    o = inspect.getsource(T.other_stocks)
    assert 'R1.at_dates(M["COR"], X["date"])' in o and 'wav_mult_for(X["date"], M["ref"], M["wave"])' in o
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **kw)" in s1 and "R5.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert "R2V.csz_kw(S, np.ones(len(S)), days)" in w and "pd.Series(1.0, index=M[\"days\"])" in w and "all(v > 0 for v in n.values())" in w
    p = inspect.getsource(T._placebo_one)
    assert 'R5.shift_mult(M["COR"], ks[int(seed)])' in p and 'R5.permute_mult(M["WAV"][e], int(seed))' in p
    with pytest.raises(SystemExit):
        T.main(["--nope"])
