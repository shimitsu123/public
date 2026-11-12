"""scripts/lvs_event_study.py（2026-10-05 登记）：登记值、事件（t1 = 提出日之后第一个交易日、同票 20 日去重、前后够长）、
退市用最后收盘、分格（市值 × 过去 60 日收益五分位）与超额、周聚类区间、判定的方向（E3 往下）与档位。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lvs_event_study as S  # noqa: E402


def test_registered_constants():
    assert (S.START, S.H_SHORT, S.H_LONG, S.PRE, S.PAST, S.GAP, S.NQ) == ("2021-07-01", 20, 60, 20, 60, 20, 5)
    assert (S.HALF_END, S.HALF2_START, S.TRANSITION) == ("2023-12-29", "2024-01-04", "2026-05-01")
    assert (S.BOOT_N, S.SEED, S.BIG_PP) == (2000, 20261005, 1.0)
    assert {k: v[:2] for k, v in S.TYPES.items()} == {"E1": ("L1", 1), "E2": ("L2", 1), "E3": ("L3", -1)} and set(S.DESC) == {"E4", "E5"}


def test_dedupe_gap():
    assert S.dedupe(np.array([100, 105, 119, 120, 141, 160])).tolist() == [True, False, False, True, True, False]
    assert S.dedupe(np.array([])).tolist() == []


def _o(rows):
    o = pd.DataFrame(rows, columns=["ticker", "sub_date", "L1", "L2", "L3", "imp", "up", "lh_type", "buy_mkt", "rpt_date"])
    o["sub_date"] = pd.to_datetime(o["sub_date"])
    return o


def test_events_t1_after_sub_date_and_dedupe():
    days = pd.bdate_range("2021-06-01", periods=400)
    names = ["1111.T", "2222.T"]
    fri = next(i for i in range(100, 120) if days[i].weekday() == 4)
    o = _o([("1111.T", days[100], True, False, False, False, True, "2", True, "x"),                 # t1 = 下一个交易日
            ("1111.T", days[105], True, False, False, False, True, "2", True, "x"),                 # 5 日后再来一份 → 去掉
            ("1111.T", days[130], True, False, False, False, True, "2", True, "x"),                 # 30 日后 → 新事件
            ("2222.T", days[fri] + pd.Timedelta(days=1), True, False, False, False, True, "1", True, "x"),   # 周六提出 → t1 = 下周一
            ("3333.T", days[100], True, False, False, False, True, "2", True, "x"),                 # 不在面板 → 不算
            ("1111.T", days[380], True, False, False, False, True, "2", True, "x"),                 # 后面不够 60 日 → 不算
            ("1111.T", pd.Timestamp("2021-07-05"), True, False, False, False, True, "2", True, "x"),   # 前面不够 61 日 → 不算
            ("2222.T", pd.Timestamp("2021-06-15"), True, False, False, False, True, "2", True, "x")])  # START 以前 → 不算
    ev = S.events(o, days, names, "E1")
    assert ev["ticker"].tolist() == ["1111.T", "1111.T", "2222.T"]
    assert ev["k1"].tolist() == [101, 131, fri + 1] and ev["j"].tolist() == [0, 0, 1]
    assert (ev["t1"] > ev["sub_date"]).all() and ev["t1"].iloc[2].weekday() == 0
    assert len(S.events(o, days, names, "E3")) == 0
    e5 = S.events(o, days, names, "E5")
    assert e5["ticker"].tolist() == ["2222.T"]


def test_ffill_close_and_quintile():
    C = np.array([[np.nan, 10.0], [5.0, 11.0], [6.0, np.nan], [np.nan, np.nan]])
    F = S.ffill_close(C)
    assert np.isnan(F[0, 0]) and F[3, 0] == 6.0 and F[3, 1] == 11.0
    q = S.quintile(np.arange(10.0), np.ones(10, bool))
    assert q.tolist() == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
    q2 = S.quintile(np.arange(10.0), np.array([True] * 9 + [False]))
    assert q2[-1] == -1 and q2[:9].max() == 4


def _panel(T=120, N=50, seed=0):
    rng = np.random.default_rng(seed)
    C = np.cumprod(1 + rng.normal(0, 0.01, size=(T, N)), axis=0) * 100
    O = C * (1 + rng.normal(0, 0.002, size=(T, N)))
    MC = np.tile(np.linspace(1, 50, N), (T, 1))
    return O, C, MC


def test_abnormal_matches_manual_cell_mean():
    O, C, MC = _panel()
    k, H, j = 70, 20, 7
    Cff = S.ffill_close(C)
    ev = pd.DataFrame({"j": [j], "k1": [k], "ticker": ["x"]})
    r, ar, sq = S.abnormal(ev, O, C, Cff, MC, H)
    cell = S.day_cells(k, MC, C)
    rr = Cff[k + H - 1] / O[k] - 1
    m = cell == cell[j]
    assert np.isclose(r[0], rr[j]) and np.isclose(ar[0], rr[j] - rr[m].mean()) and sq[0] == cell[j] // S.NQ
    O2 = O.copy()
    O2[:, :] = O[:, :]
    C2 = C.copy()
    C2[k + 5:, j] = np.nan                                                    # t1 后第 5 天退市 → 用最后收盘
    r2, _, _ = S.abnormal(ev, O2, C2, S.ffill_close(C2), MC, H)
    assert np.isclose(r2[0], C[k + 4, j] / O[k, j] - 1)


def test_cells_known_at_t1_minus_1():
    O, C, MC = _panel()
    k = 80
    a = S.day_cells(k, MC, C)
    C2 = C.copy()
    C2[k:] *= np.linspace(0.5, 2.0, C.shape[1])                              # t1 当天及以后的价格变化不影响分格
    assert (S.day_cells(k, MC, C2) == a).all()


def test_boot_ci_and_stats():
    x = np.r_[np.full(50, 0.02), np.full(50, 0.04)]
    w = np.repeat(np.arange(20), 5).astype(str)
    st = S.stats(x, w)
    assert st["n"] == 100 and np.isclose(st["mean"], 3.0) and st["pos"] == 100.0 and st["ci"][0] <= 3.0 <= st["ci"][1]
    assert S.boot_ci(np.ones(5), np.arange(5)) == (None, None) and S.stats(np.array([np.nan]))["n"] == 0


def test_judge_direction_and_tiers():
    big = {"n": 500, "mean": 1.5, "median": 0.4, "pos": 52.0, "ci": [0.6, 2.4]}
    h = {"H1": {"n": 250, "mean": 1.2}, "H2": {"n": 250, "mean": 1.8}}
    j = S.judge("E1", big, {"n": 500, "mean": 2.0, "median": 0.5}, h)
    assert all(j["gates"].values()) and j["tier"].startswith("有信息而且够大")
    small = dict(big, mean=0.6, ci=[0.1, 1.1])
    assert S.judge("E1", small, {"n": 500, "mean": 0.8, "median": 0.5}, h)["tier"] == "有信息但不够大（只记录）"
    assert S.judge("E1", dict(big, ci=[-0.1, 2.0]), {"n": 500, "mean": 2.0}, h)["tier"] == "没有信息"
    assert S.judge("E1", big, {"n": 500, "mean": 2.0}, {"H1": {"n": 250, "mean": 1.2}, "H2": {"n": 250, "mean": -0.1}})["tier"] == "没有信息"
    neg = {"n": 400, "mean": -1.4, "median": -0.3, "pos": 45.0, "ci": [-2.2, -0.5]}
    jn = S.judge("E3", neg, {"n": 400, "mean": -2.0}, {"H1": {"n": 200, "mean": -1.0}, "H2": {"n": 200, "mean": -1.8}})
    assert all(jn["gates"].values()) and jn["s_lo"] == 0.5
    assert S.judge("E3", big, {"n": 500, "mean": 2.0}, h)["tier"] == "没有信息"
