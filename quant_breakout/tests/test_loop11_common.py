"""第十一个研究循环的共用部分（scripts/loop11_common.py）：成交日的对应、每笔持仓的参数表、种类标签、效率比、以往突破的周期、配对统计。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop11_common as C  # noqa: E402

from qbreak import exit_rules as EXR  # noqa: E402
from qbreak.config import StrategyParams  # noqa: E402


def test_fill_dates_next_trading_day():
    days = pd.DatetimeIndex(["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"])
    got = C.fill_dates(days, pd.to_datetime(["2026-09-28", "2026-09-30", "2026-09-26", "2026-10-01"]))
    assert got == ["2026-09-29", "2026-10-01", "2026-09-28", ""]


def test_build_params_td_only_non_base_and_shared_objects():
    px = EXR.apply(StrategyParams(), "X6")
    menu = {"low": {"k": 2.0, "mh": 60}, "high": {"k": 4.0, "mh": 90}, "mid": {"k": 3.0, "mh": 60}}
    td = C.build_params_td(px, ["A.T", "B.T", "C.T", "D.T", "E.T"], ["2026-10-01", "2026-10-01", "2026-10-02", "", "2026-10-03"],
                           ["low", "mid", "high", "low", "na"], menu)
    assert set(td) == {("A.T", "2026-10-01"), ("C.T", "2026-10-02")}                    # mid = B3、没有成交日、na → 不放
    assert td[("A.T", "2026-10-01")].exit_chandelier_k == 2.0 and td[("A.T", "2026-10-01")].max_hold_days == 60
    assert td[("C.T", "2026-10-02")].exit_chandelier_k == 4.0 and td[("C.T", "2026-10-02")].max_hold_days == 90
    assert not td[("C.T", "2026-10-02")].exit_on_macd_dead_cross                         # 其余照 X6
    td2 = C.build_params_td(px, ["A.T", "B.T"], ["2026-10-01", "2026-10-02"], ["low", "low"], menu)
    assert td2[("A.T", "2026-10-01")] is td2[("B.T", "2026-10-02")]


def test_spec_labels_round_trip():
    s = {"k": 2.5, "mh": 40}
    lab = C.spec_label(s)
    assert lab == "k2.5_mh40" and C.parse_spec_label(lab) == s and C.spec_of(lab, {}) == s
    assert C.spec_of("whatever", {}) == C.BASE_SPEC and C.is_base(C.spec_of("k3_mh60", {}))


def test_terciles_and_labels():
    x = np.array([1, 2, 3, 4, 5, 6, np.nan], float)
    lo, hi = C.tercile_cuts(x)
    assert lo < hi
    lab = C.label3([1.0, 3.5, 6.0, np.nan, lo, hi], lo, hi)
    assert list(lab) == ["low", "mid", "high", "na", "low", "high"]


def test_efficiency_ratio():
    c = np.arange(300, dtype=float)                                                      # 一直涨 → 1
    assert abs(C.efficiency_ratio(c, 299, 250) - 1.0) < 1e-12
    z = np.array([10.0, 11.0] * 150)                                                     # 来回 → 0〜很小
    assert C.efficiency_ratio(z, 299, 250) < 0.01
    assert np.isnan(C.efficiency_ratio(c, 100, 250))


def test_past_cycle_uses_only_finished_windows():
    n = 400
    c = np.ones(n)
    e = np.zeros(n, bool)
    for p, peak in ((10, 5), (100, 20), (200, 40)):                                     # 三次以往的突破：第 5 / 20 / 40 天到顶
        e[p] = True
        c[p + peak] = 2.0
    e[350] = True                                                                        # 窗口还没过完的不算
    assert C.past_cycle(c, e, 300, horizon=60, min_n=3) == 20.0
    assert np.isnan(C.past_cycle(c, e, 250, horizon=60, min_n=3))                         # 200 的窗口没过完 → 只有 2 个
    assert C.past_cycle(c, e, 300, horizon=60, lookback=250, min_n=2) == 30.0             # 只看最近 250 根


def test_pair_stats():
    st = C.pair_stats([1.0, -1.0, 2.0, np.nan], [0.5, 0.2, 2.0, 1.0], [True, True, False, True])
    assert st["n"] == 3 and st["changed"] == 2
    assert abs(st["dwin"] - (100.0 - 200 / 3)) < 1e-2 and abs(st["dmean"] - (2.7 / 3 - 2.0 / 3)) < 1e-3
    assert C.pair_stats([np.nan], [np.nan], [True])["n"] == 0
