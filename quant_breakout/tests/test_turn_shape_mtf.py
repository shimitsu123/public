"""scripts/turn_shape_mtf.py（2026-10-05 登记）：登记值、周 / 月线尺度的起涨 / 起跌点标注、K 线 → 样本行、样本日（看得到之后 h 根）、
放大门槛的判定（放大倍数 1 时与原研究相同）、组内门槛、分组与簇。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import turn_shape_mtf as M  # noqa: E402
import turn_shape_study as S  # noqa: E402


def test_registered_constants():
    assert M.SCALES == {"W": {"freq": "W", "ext": 8, "h": 26, "sig_n": 52, "h_ret": 65, "cluster": "Q"},
                        "M": {"freq": "M", "ext": 6, "h": 12, "sig_n": 24, "h_ret": 126, "cluster": "H"}}
    assert M.BAR_DAYS == {"W": 5, "M": 21}
    assert M.m_bounds("W") == (0.18, 0.72) and M.m_bounds("M") == (0.25, 1.0)
    assert M.scale_factor("W") == 3.25 and M.scale_factor("M") == 6.3


def test_swing_labels_on_bars():
    n = 140
    t = np.arange(n)
    wig = 1 + 0.01 * np.sin(t * 1.3)                                          # 一点波动（σ > 0）
    C = np.r_[np.linspace(100, 60, 70), np.linspace(60, 150, 70)][:, None] * wig[:, None]
    L = M.swing_labels(C, ext=8, h=26, sig_n=52, m_lo=0.18, m_hi=0.72)
    k0 = int(np.nanargmin(C[:, 0]))
    assert L["RS"][k0, 0] and not L["FS"][k0, 0] and 0.18 <= L["M"][k0, 0] <= 0.72
    assert not L["RS"][-5:, 0].any()                                          # 之后不够 h 根 → 不标
    C2 = np.r_[np.linspace(60, 150, 70), np.linspace(150, 60, 70)][:, None] * wig[:, None]
    L2 = M.swing_labels(C2, ext=8, h=26, sig_n=52, m_lo=0.18, m_hi=0.72)
    assert L2["FS"][int(np.nanargmax(C2[:, 0])), 0]
    assert not L2["FS"][:52, 0].any()                                         # σ 要 52 根


def test_take_bar_and_bar_end_rows():
    arr = np.arange(12.0).reshape(4, 3)                                       # 4 根 K 线 × 3 只
    pos = np.array([-1, 0, 0, 1, 2, 3])
    v = M.take_bar(arr, pos, np.array([0, 1, 3, 5]), np.array([0, 1, 2, 0]))
    assert np.isnan(v[0]) and v[1:].tolist() == [1.0, 5.0, 9.0]
    days = pd.bdate_range("2017-09-25", periods=60)
    cdays = pd.DatetimeIndex([d for d in days if d.weekday() == 4])            # 每周五完成
    rows = M.bar_end_rows(days, cdays, len(cdays), h=3, h_ret=5)
    got = days[rows]
    assert all(d.weekday() == 4 for d in got) and got[0] >= pd.Timestamp(S.START)
    assert got[-1] == cdays[len(cdays) - 1 - 3]                               # 之后还要 3 根
    assert np.searchsorted(days, got[-1]) + 5 + 1 <= len(days) - 1


def test_judge_scaled_equals_original_at_scale_one():
    top, bot, base = {"R20x": 1.6}, {"R20x": -0.2}, {"R20x": 0.9}
    yrs = {2022: {"n": 10, "R20x": 1.0}, 2023: {"n": 10, "R20x": 0.5}, 2024: {"n": 10, "R20x": -0.1}, 2025: {"n": 10, "R20x": 2.0}, 2026: {"n": 5, "R20x": 0.3}}
    args = (1, 0.62, 0.60, top, bot, (0.004, 0.028), base, yrs, {"top": 0.8, "bottom": 0.1})
    assert M.judge_scaled(*args, scale=1.0) == S.judge(*args)
    j = M.judge_scaled(*args, scale=3.25)                                     # 差 1.8 pp < 3.25 → G3 不过
    assert not j["gates"]["G3"] and not j["gates"]["G4"] and j["tier"] == "没有用"
    y4 = {y: v for y, v in yrs.items() if y < 2026}                           # 4 年里 3 年对 → G5 过（最多一年不对）
    assert M.judge_scaled(1, 0.62, 0.60, top, bot, (0.004, 0.028), base, y4, {"top": 0.8, "bottom": 0.1}, scale=1.0)["gates"]["G5"]


def test_cell_scaled_threshold_and_groups():
    rng = np.random.default_rng(5)
    days = np.repeat(pd.bdate_range("2022-01-07", periods=40, freq="W-FRI").to_numpy(), 100)
    n = len(days)
    sc = rng.normal(size=n)
    r = 0.01 * sc + rng.normal(0, 0.01, n)                                    # 最像 − 最不像 ≈ 3.5 pp
    D = pd.DataFrame({"date": pd.to_datetime(days), "R20": r, "RS": (sc > 1.5).astype(float), "FS": (sc < -1.5).astype(float), "M": 0.3,
                      "lo10": sc < 0, "hi10": sc > 0})
    D["clu"] = M.cluster_of(D["date"], "Q")
    a = M.cell_scaled(D, {"rise": sc, "fall": sc}, np.ones(n, bool), info_pp=1.0)
    b = M.cell_scaled(D, {"rise": sc, "fall": sc}, np.ones(n, bool), info_pp=6.3)
    assert a["rise"]["info"] and not b["rise"]["info"] and 1.0 < a["rise"]["spread_pp"] < 6.3
    g = M.group_codes(np.array([1, 1, 1, 4, 5, 3, 2, 7]), np.array([300, 300, 100, 500, 500, 500, 500, 500]),
                      np.array([2e7, 5e6, 2e7, 1e9, 1e3, 1e8, 1e3, 1e3]))
    assert g.tolist() == ["A", "B", "C", "D", "D", "E", "F", "F"]
    d = pd.Series(pd.to_datetime(["2022-03-31", "2022-04-01", "2022-07-01"]))
    assert M.cluster_of(d, "Q").tolist() == ["2022Q1", "2022Q2", "2022Q3"] and M.cluster_of(d, "H").tolist() == ["2022H1", "2022H1", "2022H2"]
