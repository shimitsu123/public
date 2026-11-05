"""研究循环第 10 轮 RFH（scripts/loop_r10_riskoffhedge.py，2026-10-01 登记）：登记值、50 日线、「避险中」的合并、引擎参数、循环平移。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_r10_riskoffhedge as H  # noqa: E402


def test_registered_constants():
    assert (H.ROUND, H.IDS, H.FX_MA, H.EQ_MA) == (10, ("RFH",), 50, 50)
    assert (H.SHIFT_FROM, H.SHIFT_GAP, H.SEED0) == ("2000-01-03", 250, 20261010)


def test_below_ma_includes_today_and_needs_full_window():
    idx = pd.bdate_range("2020-01-01", periods=6)
    s = pd.Series([10.0, 11, 12, 9, 13, 8], index=idx)
    b = H.below_ma(s, 3)
    ma = s.rolling(3).mean()
    assert b.tolist()[:2] == [False, False]
    assert b.iloc[2:].tolist() == (s.iloc[2:] < ma.iloc[2:]).tolist()


def test_riskoff_needs_both_and_forward_fills_each_side():
    fx = pd.Series([100.0] * 3 + [90.0, 90.0], index=pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09", "2020-01-13"]))
    spx = pd.Series([50.0] * 3 + [40.0], index=pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-08", "2020-01-10"]))
    st = H.riskoff_state(fx, spx, fx_n=3, eq_n=3)
    got = {d.strftime("%m-%d"): bool(v) for d, v in st.items()}
    assert got == {"01-06": False, "01-07": False, "01-08": False, "01-09": False, "01-10": True, "01-13": True}


def test_rfh_override_uses_round4_wiring():
    fr = pd.DataFrame({"Close": [1.0]}, index=[pd.Timestamp("2020-01-06")])
    W = {"kw": {"Z": {"extra_core": {"1545.T": fr}}}}
    s = pd.Series([True], index=[pd.Timestamp("2020-01-06")])
    o = H.rfh_over(W, ~s, s, fr)
    assert o["cfg_over"]["core_mode"] == "follow" and set(o["extra_core"]) == {"1545.T", "2845.T"}


def test_shift_placebo_keeps_days_and_is_reproducible():
    idx = pd.bdate_range("1999-06-01", "2026-10-30")
    s = pd.Series((np.arange(len(idx)) % 90) < 20, index=idx)
    a, b = H.shifted(s, 2), H.shifted(s, 2)
    assert a.equals(b) and int(a.sum()) == int(H.shift_domain(s).sum())
    w = H.shift_domain(s)
    ks = [H.shift_k(x, len(w)) for x in range(400)]
    assert min(ks) >= 250 and max(ks) <= len(w) - 250 and len(set(ks)) > 300
