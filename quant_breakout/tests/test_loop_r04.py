"""研究循环第 4 轮 FXH / FXC（scripts/loop_r04_yensurge.py，2026-10-01 登记）：登记值、急升状态机、合并、引擎参数、循环平移。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_r04_yensurge as Y  # noqa: E402


def test_registered_constants():
    assert (Y.ROUND, Y.IDS, Y.CHG_N, Y.CHG_THR, Y.MA_N) == (4, ("FXH", "FXC"), 10, -0.03, 20)
    assert (Y.HEDGE_T, Y.HEDGE_FEE, Y.HEDGE_REF, Y.REF_DATE) == ("2845.T", 0.22, 2000.0, "2026-08-31")
    assert (Y.SHIFT_FROM, Y.SHIFT_GAP, Y.SEED0) == ("2000-01-03", 250, 20261004)


def test_surge_starts_on_10day_drop_and_ends_above_20day_mean():
    idx = pd.bdate_range("2020-01-01", periods=60)
    px = np.r_[np.full(30, 110.0), np.linspace(110, 104, 8), np.full(10, 104.0), np.linspace(104, 112, 12)]
    s = Y.surge_state(pd.Series(px, index=idx))
    first = int(np.argmax(s.to_numpy()))
    chg = pd.Series(px, index=idx) / pd.Series(px, index=idx).shift(10) - 1
    assert chg.iloc[first] <= -0.03 and (chg.iloc[:first].fillna(0) > -0.03).all()           # 第一次 ≤ −3% 那天开始
    ma = pd.Series(px, index=idx).rolling(20).mean()
    end = first + int(np.argmax(~s.to_numpy()[first:]))
    assert px[end] > ma.iloc[end] and (px[first:end] <= ma.iloc[first:end].to_numpy()).all()  # 第一次收在 20 日线之上那天结束
    assert Y.episodes(s) == 1 and not s.iloc[:20].any()


def test_or_series_and_overrides():
    a = pd.Series([False, True], index=pd.to_datetime(["2020-01-06", "2020-01-08"]))
    b = pd.Series([True, False], index=pd.to_datetime(["2020-01-07", "2020-01-09"]))
    assert Y.or_series(a, b).tolist() == [False, True, True, True]
    fr = pd.DataFrame({"Close": [1.0]}, index=[pd.Timestamp("2020-01-06")])
    W = {"kw": {"Z": {"extra_core": {"1545.T": fr}}}}
    bear = pd.Series([False], index=[pd.Timestamp("2020-01-06")])
    surge = pd.Series([True], index=[pd.Timestamp("2020-01-06")])
    h = Y.fxh_over(W, bear, surge, fr)
    assert h["cfg_over"]["core_mode"] == "follow" and set(h["extra_core"]) == {"1545.T", "2845.T"}
    assert h["extra_bear"]["US_UH"].tolist() == [True] and h["extra_bear"]["US_HG"].tolist() == [False]   # 急升中：1545 关、2845 开
    c = Y.fxc_over(bear, surge)
    assert c["cfg_over"]["core_index"] == {"1545.T": "US_FX"} and c["extra_bear"]["US_FX"].tolist() == [True]


def test_shift_keeps_surge_days():
    idx = pd.bdate_range("1999-06-01", "2026-10-30")
    s = pd.Series((np.arange(len(idx)) % 150) < 12, index=idx)
    a = Y.shifted(s, 9)
    assert a.equals(Y.shifted(s, 9)) and int(a.sum()) == int(Y.shift_domain(s).sum())
    ks = [Y.shift_k(x, len(Y.shift_domain(s))) for x in range(400)]
    assert min(ks) >= 250 and len(set(ks)) > 300
