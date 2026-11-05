"""第八个研究循环第 1 轮 VRP / VRN（scripts/loop8_r01_vrp.py，2026-10-04 登记）：登记的常数、STOXX 文件解析与拼接、IV 对齐（不偷看、最多回看 5 天）、
已实现方差与 VRP 的公式、月度比例只在月末之后变、信息检查的样本、横展开的平移与「比例全 1 → Δ = 0」、判定的接线。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop8_r01_vrp as V  # noqa: E402
import research_loop8 as L8  # noqa: E402


def test_registered_constants_and_judgment():
    assert (V.ROUND, V.IDS, V.FAMILY, V.POSTHOC, V.RV_N, V.IV_TOL_DAYS, V.THRESH) == (1, ("VRN",), "期权·波动风险溢价", False, 22, 5, 0.0)
    assert V.KEEP == pytest.approx(2 / 3) and V.FAMILY in L8.SOURCES
    assert tuple(V.MARKETS) == ("US", "EU", "AU", "IN", "BR") and V.CROSS == ("US", "EU", "AU", "IN") and tuple(V.DESC) == ("NDX",)
    assert (V.WINDOW_B, V.POST, V.LIT_END, V.H_SHORT, V.SEED_INFO, V.SEED_B, V.PLACEBO_N, V.SHIFT_GAP) == (
        ("2009-01-01", "2026-09-30"), "2012-01-01", "2007-12-31", 21, 20261010, 20261011, 400, 250)
    ra, s1, s2 = inspect.getsource(V.run_all), inspect.getsource(V.stage_one), inspect.getsource(V.stage_two)
    assert "if not A[\"judge\"][\"ok\"]:" in ra and "RL8.FAIL_INFO" in ra and "R7.FOUND if (a[\"ok\"] and b[\"judge\"][\"ok\"])" in ra
    assert "R6.stage1(cand, base, posthoc=None)" in s1 and "P2.vtx_over(M[\"ratio_t\"])" in s1
    assert "R7.judge(real, plac)" in s2 and "shift_ks(n_min)" in s2
    ic = inspect.getsource(V.info_check)
    assert "RL8.info_judge(ics, post, boot, sign=+1)" in ic and "RL8.joint_bootstrap(S, seed=SEED_INFO)" in ic


def test_parse_stoxx_files():
    v = V.parse_v2tx("Date;Symbol;Indexvalue\n04.01.1999;V2TX;18.2033\n05.01.1999;V2TX;29.6912\nbad;line\n")
    assert v.index.tolist() == [pd.Timestamp("1999-01-04"), pd.Timestamp("1999-01-05")] and v.iloc[1] == pytest.approx(29.6912)
    txt = ("Price Indices - EURO Currency\nDate    ;Blue-Chip;Blue-Chip;Broad\n        ;  Europe ;Euro-Zone;Europe\n        ;  SX5P   ;  SX5E   ;SXXP\n"
           "31.12.1986;775.00 ;  900.82 ;   82.76\n02.01.1987;770.00 ;  895.50 ;   82.00;\n25.03.2016;0.00 ;  0.00 ;   0.00;\n")
    s = V.parse_sx5e(txt)
    assert s.tolist() == pytest.approx([900.82, 895.50]) and s.index[0] == pd.Timestamp("1986-12-31")                # 休市日的 0 去掉


def test_splice_scales_new_by_overlap_median():
    idx = pd.bdate_range("2005-01-03", periods=800)
    base = pd.Series(np.linspace(100, 200, 800), index=idx)
    old, new = base.iloc[:600], (base * 1.01).iloc[300:]
    s, st = V.splice(old, new)
    assert st["overlap_days"] == 300 and st["ratio_median"] == pytest.approx(1.01, abs=1e-6)
    assert s.index.equals(idx) and s.iloc[:600].equals(old) and s.iloc[-1] == pytest.approx(200.0)
    with pytest.raises(RuntimeError):
        V.splice(old, new.iloc[-250:])                                         # 没有足够的重叠


def test_align_iv_no_lookahead_and_tolerance():
    iv = pd.Series([20.0, 30.0], index=pd.to_datetime(["2024-01-02", "2024-01-10"]))
    idx = pd.to_datetime(["2024-01-02", "2024-01-05", "2024-01-08", "2024-01-09", "2024-01-10"])
    a = V.align_iv(iv, idx)
    assert a.iloc[0] == 20.0 and a.iloc[1] == 20.0 and np.isnan(a.iloc[2]) and np.isnan(a.iloc[3]) and a.iloc[4] == 30.0   # 1-08 已超过 5 天


def test_realized_var_and_vrp_formula():
    idx = pd.bdate_range("2024-01-01", periods=40)
    r = np.r_[0.0, np.full(39, 0.01)]
    c = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
    rv = V.realized_var(c)
    assert rv.iloc[:22].isna().all() and rv.iloc[22] == pytest.approx(252 * 0.0001)
    iv = pd.Series(20.0, index=idx)
    v = V.vrp(c, iv)
    assert v["vrp"].iloc[30] == pytest.approx(0.04 - 0.0252) and list(v.columns) == ["iv", "rv", "vrp"]


def test_ratio_vrn_changes_only_after_month_ends():
    idx = pd.bdate_range("2024-01-01", "2024-04-10")
    c = pd.Series(100.0, index=idx)
    v = pd.Series(0.01, index=idx)
    v.loc["2024-01-31"] = -0.02                                                # 1 月末 ≤ 0
    v.loc["2024-02-15"] = -0.05                                                # 月中 ≤ 0 → 不算
    v.loc["2024-02-29"] = np.nan                                               # 2 月末算不了 → 1
    r = V.ratio_vrn(c, v)
    assert (r[r.index < "2024-01-31"] == 1.0).all()
    assert r.loc["2024-01-31"] == pytest.approx(2 / 3) and np.allclose(r[(r.index > "2024-01-31") & (r.index < "2024-02-29")], 2 / 3)
    assert (r[(r.index >= "2024-02-29")] == 1.0).all()                         # 3 月末 0.01 → 1；4 月还没结束
    assert r.index.equals(c.index)


def test_samples_use_month_ends_and_forward_returns():
    idx = pd.bdate_range("2020-01-01", "2021-12-31")
    c = pd.Series(np.exp(np.arange(len(idx)) * 0.001), index=idx)
    v = pd.Series(np.arange(len(idx), dtype=float), index=idx)
    s = V.samples(c, v, h=21)
    assert s.index.isin(L8.month_ends_done(c)).all() and np.allclose(s["y"], 0.021)
    assert s.index[-1] < pd.Timestamp("2021-12-01")                            # 最后几个月不够 21 天 → 不进样本


def test_cross_deltas_zero_with_ones_and_shift_ks():
    idx = pd.bdate_range("2006-01-02", "2026-09-30")
    g = np.random.default_rng(3)
    closes = {m: pd.Series(100 * np.exp(np.cumsum(g.normal(0.0003, 0.01, len(idx)))), index=idx) for m in ("A", "B")}
    bulls = {m: c > c.rolling(250, min_periods=250).mean() for m, c in closes.items()}   # 测试用的牛（检测器的配置在临时目录里没有）
    ones = {m: pd.Series(1.0, index=idx) for m in closes}
    for k in (None, 777):
        d = V.deltas(closes, ones, bulls, k)
        assert all(abs(x) < 1e-12 for v in d.values() for x in v)
    half = {m: pd.Series(np.where(np.arange(len(idx)) % 50 < 10, 2 / 3, 1.0), index=idx) for m in closes}
    assert V.deltas(closes, half, bulls, None) != V.deltas(closes, half, bulls, 501)
    ks = V.shift_ks(4000)
    assert len(ks) == 400 and min(ks) >= 250 and max(ks) <= 3750 and ks == V.shift_ks(4000)
    with pytest.raises(ValueError):
        V.shift_ks(400)
