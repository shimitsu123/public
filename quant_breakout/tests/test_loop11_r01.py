"""第十一个研究循环第 1 轮（scripts/loop11_r01_cycle.py）：VOK 学参数的规则、逐年前推的截止日、常量。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop11_r01_cycle as R  # noqa: E402


def test_round_constants():
    assert R.ROUND == 1 and R.IDS == ("ULC", "ERK", "VOK")
    assert R.TIGHT == {"k": 2.0, "mh": 60} and R.WIDE == {"k": 4.0, "mh": 90} and R.OPTIONS["base"] == {"k": 3.0, "mh": 60}
    assert R.MENUS["ULC"] == {"short": R.TIGHT, "long": R.WIDE} and R.MENUS["ERK"] == {"low": R.TIGHT, "high": R.WIDE}
    assert all(not v for v in R.POSTHOC.values()) and set(R.KINDS.values()) == {"label"}
    assert (R.MIN_TRAIN, R.WF_GAP_DAYS, R.ER_N, R.ULC_N, R.ULC_K, R.ULC_MIN) == (20, 120, 250, 500, 3.0, 3)


def test_choose_prefers_win_among_not_lower_mean():
    n = 30
    base = np.r_[np.full(15, 1.0), np.full(15, -0.5)]                          # 胜率 50%、每笔 +0.25
    tight = np.r_[np.full(20, 0.4), np.full(10, -0.3)]                         # 胜率 67%、每笔 +0.167 < B3 → 不合格
    wide = np.r_[np.full(18, 0.8), np.full(12, -0.6)]                          # 胜率 60%、每笔 +0.24 < B3 → 不合格
    assert R.choose({"tight": tight, "base": base, "wide": wide}) == "base"
    wide2 = np.r_[np.full(18, 1.0), np.full(12, -0.5)]                         # 胜率 60%、每笔 +0.4 ≥ B3 → 选它
    assert R.choose({"tight": tight, "base": base, "wide": wide2}) == "wide"
    assert R.choose({"tight": tight[:10], "base": base[:10], "wide": wide2[:10]}) == "base"   # 不够 20 笔
    same = {"tight": base.copy(), "base": base.copy(), "wide": base.copy()}
    assert R.choose(same) == "base"                                            # 平手 → B3
    assert n == len(base)


def test_learn_and_apply_map():
    T = pd.DataFrame({"label": ["low"] * 25 + ["high"] * 5, "net_tight": [0.5] * 30,
                      "net_base": [0.4] * 20 + [-0.1] * 10, "net_wide": [-1.0] * 30})            # low：tight 胜率 100% > B3 80%、每笔也不低
    mp = R.learn_map(T)
    assert mp == {"low": "tight", "mid": "base", "high": "base"}               # high 只有 5 笔 → B3；mid 没有 → B3
    assert R.apply_map(["low", "high", "na", "mid"], mp) == ["tight", "base", "base", "base"]


def test_wf_cut():
    assert R.wf_cut("2010-07-15") == pd.Timestamp("2009-09-03")               # 2010-01-01 − 120 天


def test_registered_cuts():
    assert R.CUTS == {"ULC": (17.5, 25.5), "ERK": (0.0248, 0.0582), "VOK": (0.0164, 0.0203)}
    assert list(R.labels_of("ULC", [10.0, 20.0, 30.0, float("nan")])) == ["short", "mid", "long", "na"]
    assert list(R.labels_of("VOK", [0.0164, 0.018, 0.0203])) == ["low", "mid", "high"]
