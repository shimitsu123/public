"""scripts/country_link_study.py：横截面回归 b、秩相关、之后 h 个月之和、年度 IC、两半、判定（合成数据）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import country_link_study as S  # noqa: E402


def test_constants():
    assert (S.K_DEEP, S.H_MAIN, S.H_LONG, S.NW_LAGS, S.T_PASS) == (3, 12, 24, 3, 2.0)
    assert S.SPLIT_A == pd.Period("2016-01", "M") and S.SPLIT_B == 2015 and (S.Y_FIRST, S.Y_LAST) == (2005, 2024)
    assert S.S17_KEEP == (1, 2, 4, 5, 6, 7, 8, 9) and (S.MIN_N33, S.MIN_N17) == (10, 8)


def _panel(n_t=6, n_i=12, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2010-01", periods=n_t, freq="M")
    cols = [f"I{k}" for k in range(n_i)]
    return idx, cols, rng


def test_fm_slopes_recovers_b():
    idx, cols, rng = _panel()
    F = pd.DataFrame(rng.normal(size=(len(idx), len(cols))), index=idx, columns=cols)
    R = pd.DataFrame(rng.normal(size=(len(idx), len(cols))), index=idx, columns=cols)
    for k in range(1, len(idx)):                                              # r_{t+1} = 2 × z(F_t) + 0.5 × z(r_t)
        f, r0 = F.iloc[k - 1].to_numpy(), R.iloc[k - 1].to_numpy()
        R.iloc[k] = 2 * S.zcs(f) + 0.5 * S.zcs(r0)
    b = S.fm_slopes(F, R, 10)
    assert len(b) == len(idx) - 1 and np.allclose(b.to_numpy(), 2.0)
    assert S.fm_slopes(F, R, 13).empty                                        # 业种不够
    F2 = F.copy()
    F2.iloc[0, :5] = np.nan
    assert idx[0] not in S.fm_slopes(F2, R, 10).index                         # 只剩 7 个 → 不算


def test_spearman_monthly_ic_and_fwd_sum():
    a = pd.Series([1.0, 2.0, 3.0, 4.0], index=list("abcd"))
    assert np.isclose(S.spearman(a, pd.Series([10.0, 20.0, 30.0, 40.0], index=list("abcd")), 3), 1.0)
    assert S.spearman(a, pd.Series([1.0, np.nan, np.nan, 2.0], index=list("abcd")), 3) is None
    assert S.spearman(a, pd.Series([1.0, 1.0, 1.0, 1.0], index=list("abcd")), 3) is None
    idx = pd.period_range("2010-01", periods=3, freq="M")
    F = pd.DataFrame([[1.0, 2.0, 3.0]] * 3, index=idx, columns=list("abc"))
    R = pd.DataFrame([[0.0, 0.0, 0.0], [3.0, 2.0, 1.0], [1.0, 2.0, 3.0]], index=idx, columns=list("abc"))
    ic = S.monthly_ic(F, R, 3)
    assert list(ic.index) == list(idx[:2]) and np.isclose(ic.iloc[0], -1.0) and np.isclose(ic.iloc[1], 1.0)
    fs = S.fwd_sum(R, idx[1], 2)
    assert list(fs) == [4.0, 4.0, 4.0] and S.fwd_sum(R, idx[2], 2).isna().all()


def test_annual_ic_window_starts_in_april():
    idx = pd.period_range("2010-01", "2012-12", freq="M")
    R = pd.DataFrame(0.0, index=idx, columns=list("abcd"))
    R.loc[pd.Period("2011-04", "M"):pd.Period("2012-03", "M")] = [1.0, 2.0, 3.0, 4.0]       # Y = 2010 的窗口
    R.loc[pd.Period("2011-01", "M")] = [9.0, -9.0, 9.0, -9.0]                                # 窗口外 → 不影响
    Sx = pd.DataFrame([[1.0, 2.0, 3.0, 4.0], [4.0, 3.0, 2.0, 1.0]], index=[2010, 2011], columns=list("abcd"))
    ic = S.annual_ic(Sx, R, 12, 4)
    assert list(ic.index) == [2010] and np.isclose(ic[2010], 1.0)              # 2011 的窗口到 2013-03 → 不完整 → 不算
    t = S.annual_tercile(Sx, R, 12, 3)
    assert t["n"] == 1 and np.isclose(t["spread"], 36.0) and t["hit"] == 100.0  # 12 × (4 − 1)


def test_halves_and_verdict():
    b = pd.Series([1.0, -1.0, 2.0], index=pd.PeriodIndex(["2015-11", "2015-12", "2016-01"], freq="M"))
    assert S.halves_a(b) == (1.0, 0.5)                                         # 结果月 2015-12 / 2016-01 / 2016-02
    ic = pd.Series([0.1, 0.3, -0.2], index=[2013, 2014, 2015])
    assert S.halves_b(ic) == (0.2, -0.2)
    good = {"mean": 0.1, "t": 2.1}
    assert S.verdict(good, 0.1, 0.2, 0.05)["label"] == "通过"
    assert not S.verdict({"mean": 0.1, "t": 1.9}, 0.1, 0.2, 0.05)["pass"]
    assert not S.verdict(good, 0.1, -0.2, 0.05)["pass"] and not S.verdict(good, 0.1, 0.2, -0.01)["pass"]
    assert not S.verdict({"mean": None, "t": None}, None, None, None)["pass"]
    assert S.mean_t(pd.Series(dtype=float), 0) == {"n": 0, "mean": None, "t": None}


def test_jp_month_end():
    d = pd.Series(1.0, index=pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-27", "2020-02-28"]))
    e = S.jp_month_end(d)
    assert list(e.index) == list(pd.period_range("2020-01", periods=2, freq="M"))
    assert list(e) == list(pd.to_datetime(["2020-01-31", "2020-02-28"]))
