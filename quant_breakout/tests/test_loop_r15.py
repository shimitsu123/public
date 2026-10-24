"""研究循环第 15 轮 FJE（scripts/loop_r15_fxeunion.py，2026-10-01 登记）：登记值、两个「对冲中」取或、拆分、接法、循环平移。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_r15_fxeunion as U  # noqa: E402


def test_registered_constants():
    assert (U.ROUND, U.IDS, U.OLD) == (15, ("FJE",), ("1987-01-01", "2000-12-31"))
    assert (U.SHIFT_FROM, U.SHIFT_GAP, U.SEED0) == ("2000-01-03", 250, 20261015)


def test_union_is_either_state_with_forward_fill():
    fxh = pd.Series([True, False], index=pd.to_datetime(["2020-01-06", "2020-01-08"]))
    jbh = pd.Series([False, True, False], index=pd.to_datetime(["2020-01-06", "2020-01-09", "2020-01-13"]))
    u = U.union_state(fxh, jbh)
    got = {d.strftime("%m-%d"): bool(v) for d, v in u.items()}
    assert got == {"01-06": True, "01-08": False, "01-09": True, "01-13": False}
    p = U.parts(fxh, jbh, pd.bdate_range("2020-01-06", "2020-01-13"))
    assert int(p["fxh_only"].sum()) == 2 and int(p["jbh_only"].sum()) == 2 and int(p["both"].sum()) == 0


def test_fje_override_uses_round4_wiring():
    fr = pd.DataFrame({"Close": [1.0]}, index=[pd.Timestamp("2020-01-06")])
    s = pd.Series([True], index=[pd.Timestamp("2020-01-06")])
    W = {"kw": {"Z": {"extra_core": {"1545.T": fr}}}, "bear": {"US": ~s}}
    o = U.fje_over(W, s, fr)
    assert o["cfg_over"]["core_mode"] == "follow" and set(o["extra_core"]) == {"1545.T", "2845.T"}
    assert o["extra_bear"]["US_UH"].tolist() == [True] and o["extra_bear"]["US_HG"].tolist() == [False]


def test_shift_placebo_keeps_days_and_is_reproducible():
    idx = pd.bdate_range("1999-06-01", "2026-10-30")
    s = pd.Series((np.arange(len(idx)) % 200) < 45, index=idx)
    a, b = U.shifted(s, 13), U.shifted(s, 13)
    assert a.equals(b) and int(a.sum()) == int(U.shift_domain(s).sum())
    w = U.shift_domain(s)
    ks = [U.shift_k(x, len(w)) for x in range(400)]
    assert min(ks) >= 250 and max(ks) <= len(w) - 250 and len(set(ks)) > 300


def test_fxe_is_round11_majority_state():
    import loop_r11_fxensemble as X
    idx = pd.bdate_range("2020-01-01", periods=120)
    rng = np.random.default_rng(4)
    fx = pd.Series(110 * np.exp(np.cumsum(rng.normal(0, 0.012, len(idx)))), index=idx)
    W = {"inp": {"dexjp": fx}}
    import loop_r13_jpbearhedge as J
    J_state = J.state_series
    try:
        J.state_series = lambda W: pd.Series(False, index=idx)                             # 只看 FXE 这一半
        fxe, jbh, uni = U.states(W)
    finally:
        J.state_series = J_state
    assert fxe.equals(X.ensemble_state(fx)) and uni.tolist() == fxe.reindex(uni.index).ffill().fillna(False).tolist()
