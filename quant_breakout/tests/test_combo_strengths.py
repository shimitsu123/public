"""各方法长处的等权组合 ENB（scripts/combo_strengths_study.py，2026-10-04 登记）：登记的成分与不收的理由、对齐只用前一个美国日（不偷看）、
T13 的「另一个大市场」、11 个成分 = 登记过的函数原样、组合 = 等权平均、组合 vs 成分的描述、判定用的函数。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import combo_strengths_study as C  # noqa: E402
import loop7_r01_vctx as P1  # noqa: E402
import loop7_r02_voltarget as P2  # noqa: E402
import loop7_r03_volshock as P3  # noqa: E402
from qbreak import timing as T  # noqa: E402
from qbreak.bullbear import BEAR  # noqa: E402


def _mk(seed=1, n=4200):
    idx = pd.bdate_range("1990-01-01", periods=n)
    r = np.random.default_rng(seed).normal(0.0004, 0.011, n)
    for a in (900, 1800, 2600, 3500):
        r[a:a + 30] -= 0.012                                                    # 几次急跌
    return pd.Series(100 * np.exp(np.cumsum(r)), index=idx)


def _f(idx, seed=2):
    g = np.random.default_rng(seed)
    n = len(idx)
    baa = pd.Series(2.0 + np.cumsum(g.normal(0, 0.02, n)), index=idx)
    f = pd.DataFrame({"fx": np.nan, "vix": 15 + 20 * (np.sin(np.arange(n) / 90) > 0.8) + g.normal(0, 1, n), "baa": baa,
                      "curve": np.sin(np.arange(n) / 400), "un": 5 + np.sin(np.arange(n) / 300), "un_ma12": 5.0}, index=idx)
    f["baa_ma250"] = f["baa"].rolling(250, min_periods=200).mean()
    f["baa_d20"] = f["baa"] - f["baa"].shift(20)
    f["other_below"] = pd.Series(np.sin(np.arange(n) / 120) > 0.3, index=idx)
    return f


def test_registered_constants_and_judgment():
    assert C.COMPONENTS == ("T4", "T5", "T6", "T7", "T8", "T10", "T12", "T13", "VCX", "VTX", "VSX")
    assert set(C.EXCLUDED) == {"T1", "T2", "T3", "T9", "T11", "T14", "T15", "A0 / C_rel", "K4", "NDR / NDB / ZSP", "汇率 / 债券类"}
    assert not set(C.COMPONENTS) & set(C.EXCLUDED)
    assert (C.IDS, C.POSTHOC, C.OUT, C.MACRO) == (("ENB",), True, "combo_strengths_study", ("VIXCLS", "BAA10Y", "DGS10", "DGS3MO", "UNRATE"))
    s1, s2, ra = inspect.getsource(C.stage_one), inspect.getsource(C.stage_two), inspect.getsource(C.run_all)
    assert "R6.stage1(cand, base, posthoc=unseen)" in s1 and "P2.vtx_over(M[\"ratio_t\"])" in s1 and "P2.old_core(W, M[\"ratio_us\"])" in s1
    assert "R7.judge(real, plac)" in s2 and "R7.shift_ks(sc[\"n_min\"])" in s2
    assert "R7.FOUND if (a[\"ok\"] and jd[\"ok\"])" in ra


def test_asof_prev_uses_only_earlier_days():
    s = pd.Series([1.0, 2.0, np.nan, 4.0], index=pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09"]))
    idx = pd.to_datetime(["2020-01-07", "2020-01-08", "2020-01-09", "2020-01-10", "2020-01-13"])
    assert C.asof_prev(s, idx, 1).tolist() == [1.0, 2.0, 2.0, 4.0, 4.0]          # d 日只用到 d − 1 天为止（缺值用之前的）
    assert C.asof_prev(s, idx, 0).tolist() == [2.0, 2.0, 4.0, 4.0, 4.0]
    assert np.isnan(C.asof_prev(s, pd.to_datetime(["2020-01-06"]), 1).iloc[0])  # 之前没有值 → 空


def test_frame_for_us_same_day_others_previous_day():
    idx = pd.bdate_range("2021-01-04", periods=6)
    f_us = pd.DataFrame({"vix": np.arange(6, dtype=float), "baa": np.arange(6, dtype=float) * 10}, index=idx)
    sp = pd.Series([0, 1, 1, 0, 0, 1], index=idx, dtype=float)
    nk = pd.Series([1, 0, 0, 1, 1, 0], index=idx, dtype=float)
    us = C.frame_for("US", idx, f_us, sp, nk)
    de = C.frame_for("DE", idx, f_us, sp, nk)
    assert us["vix"].tolist() == f_us["vix"].tolist() and us["other_below"].tolist() == [True, False, False, True, True, False]
    assert np.isnan(de["vix"].iloc[0]) and de["vix"].iloc[1:].tolist() == f_us["vix"].iloc[:-1].tolist()   # 前一个美国日
    assert de["other_below"].tolist() == [False, False, True, True, False, False]                       # S&P 前一天
    mon = pd.DatetimeIndex(["2021-01-11"])                                                               # 星期一 → 用上星期五
    assert C.frame_for("DE", mon, f_us, sp, nk)["vix"].iloc[0] == 4.0


def test_components_are_the_registered_functions():
    c = _mk()
    f = _f(c.index)
    comp = C.components(c, f)
    assert list(comp.columns) == list(C.COMPONENTS) and comp.index.equals(c.index)
    assert comp.notna().all().all() and ((comp >= 0) & (comp <= 1)).all().all()
    nb = lambda st: (np.asarray(st) != BEAR).astype(float)                                                # noqa: E731
    assert np.array_equal(comp["T4"].to_numpy(), (~T.t4_stress_exit(c, f)).to_numpy().astype(float))
    assert np.array_equal(comp["T5"].to_numpy(), (~T.t5_momentum(c, f)).to_numpy().astype(float))
    assert np.array_equal(comp["T6"].to_numpy(), (~T.t6_majority(c, f)).to_numpy().astype(float))
    for k, fn in (("T7", T.s7_dual_speed), ("T8", T.s8_credit_fast_exit), ("T12", T.s12_fast_credit), ("T13", T.s13_fast_global)):
        assert np.array_equal(comp[k].to_numpy(), nb(fn(c, f))), k
    assert np.array_equal(comp["T10"].to_numpy(), T.t10_half_expo(c, f).to_numpy())
    sig = P1.signal(c)["signal"].reindex(c.index).fillna(False).to_numpy(bool)
    assert np.allclose(comp["VCX"].to_numpy(), np.where(sig, 2 / 3, 1.0))
    assert comp["VTX"].equals(P2.market_ratio(c).reindex(c.index).astype(float).rename("VTX"))
    assert comp["VSX"].equals(P3.shock_ratio(c).reindex(c.index).astype(float).rename("VSX"))
    for k in ("T4", "T6", "T7", "T8", "T10", "T12", "T13", "VCX", "VTX", "VSX"):                           # 合成数据上每个成分都会减仓
        assert (comp[k] < 1).any(), k
    other = f.copy()
    other["other_below"] = False
    assert (C.components(c, other)["T13"] == 1).sum() >= (comp["T13"] == 1).sum()                         # 另一个市场不确认 → T13 少离场


def test_ensemble_is_equal_weight_mean():
    idx = pd.bdate_range("2020-01-01", periods=3)
    comp = pd.DataFrame({k: [1.0, 0.0, 1.0] for k in C.COMPONENTS}, index=idx)
    comp.loc[idx[2], "VSX"] = np.nan                                                                     # 缺值当 1
    comp.loc[idx[0], "T7"] = 0.0
    r = C.ensemble(comp)
    assert r.tolist() == pytest.approx([10 / 11, 0.0, 1.0])
    one = pd.DataFrame({k: [1.0] for k in C.COMPONENTS}, index=idx[:1])
    assert C.ensemble(one).tolist() == [1.0]
    assert C.T_RULES + C.VOL_RULES == C.COMPONENTS


def test_ensemble_bull_mask_only_changes_non_bull_days():
    idx = pd.bdate_range("2020-01-01", periods=4)
    comp = pd.DataFrame({k: [0.0, 0.0, 0.0, 0.0] for k in C.COMPONENTS}, index=idx)
    comp["VSX"] = [0.5, 0.5, 0.5, 0.5]
    bull = pd.Series([True, False, True, False], index=idx)
    r0, r1 = C.ensemble(comp), C.ensemble(comp, bull)
    assert r1[bull].tolist() == r0[bull].tolist() == pytest.approx([0.5 / 11] * 2)        # 牛的日子不变（候选本身不受影响）
    assert r1[~bull].tolist() == pytest.approx([(8 + 0.5) / 11] * 2)                      # 不是牛：T 规则记 1、波动类照原样
    assert C.ensemble(comp, pd.Series(True, index=idx)).equals(r0)


def test_below_ma_definition():
    c = _mk(3, 600)
    b = C.below_ma(c)
    ma = c.rolling(250).mean()
    assert b.iloc[:249].isna().all()
    assert (b.iloc[249:] == (c < ma).iloc[249:].astype(float)).all()


def test_combo_gain_description():
    keys = ["A", "B", "C"]
    real = {"A": [0.03, 0, 0], "B": [-0.01, 0, 0], "C": [0.0, 0, 0]}
    comp = {"X": {"A": [0.01, 0, 0], "B": [0.0, 0, 0], "C": [0.02, 0, 0]}, "Y": {"A": [0.03, 0, 0], "B": [-0.04, 0, 0], "C": [-0.01, 0, 0]}}
    g = C.combo_gain({k: real[k] for k in keys}, comp)
    assert g["ensemble"] == pytest.approx(0.02 / 3) and g["component_pooled"]["X"] == pytest.approx(0.01)
    assert g["component_pooled"]["Y"] == pytest.approx(-0.02 / 3) and g["component_positive"] == {"X": 2, "Y": 1}
    assert g["gain"] == pytest.approx(0.02 / 3 - (0.01 - 0.02 / 3) / 2)
    assert g["markets_beat_component_mean"] == 2                       # A：0.03 > 0.02 是；B：−0.01 > −0.02 是；C：0.0 > 0.005 否
    assert -1.0 <= g["mean_pairwise_corr"] <= 1.0
