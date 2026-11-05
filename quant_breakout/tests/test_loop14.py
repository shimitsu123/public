"""第十四个研究循环：登记清单（ID 没用过、家族 ≤ 3、事后判）+ A / B 轮特征的纯函数（不偷看、门槛）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop14_common as L14  # noqa: E402
import loop14_ra_price as RA  # noqa: E402
import loop14_rb_jq as RB  # noqa: E402
import research_loop14 as R14  # noqa: E402


def test_plan():
    R14.check_plan()
    assert [i for i, _, _ in R14.PLAN] == ["CNQ", "PRF", "GAP", "OVN", "AGR", "ISS", "PAY"] and R14.POSTHOC and R14.SEED == (20261024, 14)
    assert set(RA.IDS) | set(RB.IDS) == {i for i, _, _ in R14.PLAN} and L14.ROUTE["CNQ"] == "AB" and L14.ROUTE["PAY"] == "J"
    s = R14.stage1_all({e: {"calmar": 1.0, "dd": -10, "h1": 1, "h2": 1, "win": 50, "mean": 1, "n": 10} for e in "ZEJ"},
                       {e: {"calmar": 1.0, "dd": -10, "h1": 1, "h2": 1, "win": 50, "mean": 1, "n": 10} for e in "ZEJ"}, {})
    assert s["posthoc"] and not s["ok"]
    assert (RA.CNQ_N, RA.CNQ_MIN, RA.CNQ_Q, RA.PRF_FROM, RA.PRF_TO, RA.PRF_LOOK, RA.PRF_UP, RA.GAP_UP, RA.OVN_N, RA.OVN_Q) == (120, 80, 67, 60, 5, 120, 1.05, 1.01, 60, 80)
    assert (RB.AGR_MIN, RB.ISS_MIN, RB.ISS_MAX, RB.PAY_MIN, RB.GAP_DAYS, RB.FY_STALE, RB.PAY_STALE) == (0.20, 0.03, 0.40, 1.0, (300, 430), 400, 200)


def test_cut_and_at_least():
    cut = L14.era_cut({"E": [1.0, 2.0, 3.0, np.nan, 5.0], "J": [np.nan]}, 50)
    assert cut["E"] == 2.5 and np.isnan(cut["J"])
    assert list(L14.at_least([1.0, 3.0, np.nan], 2.5)) == [False, True, False] and not L14.at_least([9.0], np.nan).any()


def test_cnq_uses_window_and_aligned_dates():
    rng = np.random.default_rng(0)
    d = pd.bdate_range("2010-01-04", periods=300)
    nq = pd.Series(rng.normal(0, 0.01, 300), index=d)
    c = 100 * np.cumprod(1 + np.r_[0.0, nq.to_numpy()[1:]])                  # 个股日收益 = 纳指同一天的收益 → 相关 1
    assert np.isclose(RA.cnq(c, d, 250, nq), 1.0)
    c2 = c.copy()
    c2[251:] = c2[251:] * 3                                                  # 信号日之后的价格不影响
    assert np.isclose(RA.cnq(c2, d, 250, nq), RA.cnq(c, d, 250, nq))
    assert np.isnan(RA.cnq(c, d, 100, nq)) and np.isnan(RA.cnq(c, d, 250, nq.iloc[:180]))   # 不够 120 天 / 有效对 < 80


def test_prf():
    c = np.r_[np.linspace(100, 90, 130), 101.0, np.full(30, 100.0), 103.0]   # 第 130 天突破（> 之前 120 天最高）、之后没超过 101 × 1.05
    i = len(c) - 1
    assert RA.prf(c, i)
    c_ok = c.copy()
    c_ok[140] = 107.0                                                        # 之后到过 +5% 以上 → 不挡
    assert not RA.prf(c_ok, i)
    assert not RA.prf(np.linspace(100, 50, 200), 199)                        # 窗口里没有突破
    late = c.copy()
    late[i] = 10_000.0                                                        # 信号日当天的收盘不进「之后」
    assert RA.prf(late, i)


def test_gap_and_ovn():
    o = np.array([100.0, 102.0, 104.1])
    h = np.array([101.0, 103.0, 105.0])
    assert RA.gap(o, h, 2) is True and RA.gap(np.array([100.0, 102.0, 104.0]), np.array([101.0, 103.0, 105.0]), 2) is False
    assert not RA.gap(o, h, 0)
    n = 70
    c = np.full(n, 100.0)
    o2 = np.full(n, 100.0)
    o2[-1], c[-1] = 102.0, 101.0                                             # 最后一天：隔夜 +ln(1.02)、日中 ln(101/102)
    assert np.isclose(RA.ovn(o2, c, n - 1), np.log(1.02) - np.log(101 / 102))
    assert np.isnan(RA.ovn(o2, c, 30))


def _R():
    t = "1301.T"
    return pd.DataFrame({"ticker": [t, t, t, t], "date": pd.to_datetime(["2018-05-10", "2018-11-10", "2019-05-10", "2019-05-20"]),
                         "time": "", "per": ["FY", "2Q", "FY", "FY"], "fye": ["2018-03-31", "2019-03-31", "2019-03-31", "2019-03-31"],
                         "ta": [100.0, 110.0, 125.0, 999.0], "sh": [1000.0, 1000.0, 1050.0, 9999.0], "pay": [0.30, 1.20, 0.40, 0.40]})


def test_fy_growth_first_disclosure_and_gap():
    FG = RB.fy_growth(_R())
    assert len(FG) == 1 and np.isclose(FG["agr"].iloc[0], 0.25) and np.isclose(FG["iss"].iloc[0], 0.05)   # 同一决算期的订正不用
    R2 = _R()
    R2.loc[2, "date"] = pd.Timestamp("2019-12-01")                           # 相差 > 430 天 → 不算
    assert len(RB.fy_growth(R2)) == 0


def test_gates_asof():
    R = _R()
    FG = RB.fy_growth(R)
    tk = ["1301.T"] * 4
    dates = pd.to_datetime(["2019-05-10", "2019-05-13", "2018-12-01", "2021-01-01"])
    g = RB.gates(R, FG, tk, dates)
    assert list(g["AGR"]) == [False, True, False, False]                     # 开示当天不用；之后才用；太旧不挡
    assert list(g["ISS"]) == [False, True, False, False]
    assert list(g["PAY"]) == [True, False, True, False]                      # 2Q 短信的予想配当性向 120% → 挡；新的 FY 短信（40%）之后不挡
