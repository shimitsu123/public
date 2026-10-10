"""研究循环第 13 轮 JBH（scripts/loop_r13_jpbearhedge.py，2026-10-01 登记）：登记值、两个状态的合并、日元牛 = USD/JPY 熊、接法、循环平移。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import equity_idle_study as EI  # noqa: E402
import loop_r13_jpbearhedge as J  # noqa: E402


def test_registered_constants():
    assert (J.ROUND, J.IDS, J.OLD) == (13, ("JBH",), ("1987-01-01", "2000-12-31"))
    assert (J.SHIFT_FROM, J.SHIFT_GAP, J.SEED0) == ("2000-01-03", 250, 20261013)


def test_and_series_needs_both_and_forward_fills_each_side():
    jp = pd.Series([False, True, True], index=pd.to_datetime(["2020-01-06", "2020-01-07", "2020-01-10"]))
    fx = pd.Series([True, False], index=pd.to_datetime(["2020-01-06", "2020-01-09"]))
    s = J.hedge_state(jp, fx)
    got = {d.strftime("%m-%d"): bool(v) for d, v in s.items()}
    assert got == {"01-06": False, "01-07": True, "01-09": False, "01-10": False}


def test_yen_bull_is_usdjpy_bear_of_the_current_detector():
    from qbreak import paths
    src = Path(__file__).resolve().parents[1] / "var" / "bullbear.json"                    # 现行牛熊分界（测试的 QBREAK_HOME 是临时目录）
    (paths.home() / "bullbear.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    idx = pd.bdate_range("2015-01-01", periods=700)
    fx = pd.Series(np.r_[np.linspace(100, 120, 350), np.linspace(120, 90, 350)], index=idx)
    fx.iloc[5] = np.nan                                                                     # FRED 的空值先去掉
    yb = J.yen_bull(fx)
    assert yb.equals(EI.t0_bear(fx.dropna()))
    assert not yb.iloc[:300].any() and yb.iloc[-1]                                          # 上升段不是日元牛、下跌到底是


def test_jbh_override_uses_round4_wiring():
    fr = pd.DataFrame({"Close": [1.0]}, index=[pd.Timestamp("2020-01-06")])
    s = pd.Series([True], index=[pd.Timestamp("2020-01-06")])
    W = {"kw": {"Z": {"extra_core": {"1545.T": fr}}}, "bear": {"US": ~s}}
    o = J.jbh_over(W, s, fr)
    assert o["cfg_over"]["core_mode"] == "follow" and set(o["extra_core"]) == {"1545.T", "2845.T"}


def test_shift_placebo_keeps_days_and_is_reproducible():
    idx = pd.bdate_range("1999-06-01", "2026-10-30")
    s = pd.Series((np.arange(len(idx)) % 300) < 40, index=idx)
    a, b = J.shifted(s, 9), J.shifted(s, 9)
    assert a.equals(b) and int(a.sum()) == int(J.shift_domain(s).sum())
    w = J.shift_domain(s)
    ks = [J.shift_k(x, len(w)) for x in range(400)]
    assert min(ks) >= 250 and max(ks) <= len(w) - 250 and len(set(ks)) > 300
