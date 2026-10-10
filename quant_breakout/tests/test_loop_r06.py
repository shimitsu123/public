"""研究循环第 6 轮 BXU（scripts/loop_r06_bearcash.py，2026-10-01 登记）：登记值、美元上升趋势、「熊且上升」键、引擎参数、133A 合成价、循环平移。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop_r06_bearcash as X  # noqa: E402


def test_registered_constants():
    assert (X.ROUND, X.IDS, X.MA_N, X.BX_KEY) == (6, ("BXU",), 200, "US_BX")
    assert (X.T133, X.T133_FEE, X.T133_REF, X.REF_DATE) == ("133A.T", 0.0975, 1073.75, "2026-08-31")
    assert (X.SHIFT_FROM, X.SHIFT_GAP, X.SEED0) == ("2000-01-03", 250, 20261006)


def test_usd_up_uses_sma_including_today_and_needs_full_window():
    idx = pd.bdate_range("2020-01-01", periods=8)
    fx = pd.Series([100.0, 101, 102, 101, 99, 98, 100, 103], index=idx)
    up = X.usd_up(fx, n=3)
    sma = fx.rolling(3).mean()
    assert up.tolist()[:2] == [False, False]                                       # 不满 3 个 → 不算上升
    assert up.iloc[2:].tolist() == (fx.iloc[2:] > sma.iloc[2:]).tolist()           # 含当天的平均
    assert X.usd_up(fx.where(fx.index != idx[3]), n=3).index.tolist() == [d for d in idx if d != idx[3]]   # 缺值丢掉、不向前填


def test_bx_bear_is_off_only_when_bear_and_up():
    bear = pd.Series([False, True, True, False], index=pd.to_datetime(["2020-01-06", "2020-01-08", "2020-01-10", "2020-01-14"]))
    up = pd.Series([True, False, True], index=pd.to_datetime(["2020-01-07", "2020-01-09", "2020-01-13"]))
    k = X.bx_bear(bear, up)
    on = ~k
    exp = {"2020-01-06": False, "2020-01-07": False, "2020-01-08": True, "2020-01-09": False, "2020-01-10": False,
           "2020-01-13": True, "2020-01-14": False}
    assert {d.strftime("%Y-%m-%d"): bool(v) for d, v in on.items()} == exp
    assert X.and_series(bear.iloc[0:0].astype(bool), up).sum() == 0                # 一边没有值 = False


def test_bxu_over_points_133a_to_its_own_key_and_keeps_1545():
    fr = pd.DataFrame({"Close": [1.0]}, index=[pd.Timestamp("2020-01-06")])
    W = {"kw": {"Z": {"extra_core": {"1545.T": fr}}}}
    s = pd.Series([True], index=[pd.Timestamp("2020-01-06")])
    o = X.bxu_over(W, s, s, fr)
    assert o["cfg_over"] == {"core": {"1545.T": 1.0, "133A.T": 1.0}, "core_index": {"1545.T": "US", "133A.T": "US_BX"},
                             "core_mode": "follow"}
    assert set(o["extra_core"]) == {"1545.T", "133A.T"} and set(o["extra_bear"]) == {"US_BX"}
    assert W["kw"]["Z"]["extra_core"] == {"1545.T": fr}                            # 不改 B0 的参数
    never = X.bxu_over(W, s, ~s, fr)["extra_bear"]["US_BX"]
    assert never.all()                                                              # 美元不上升 → 133A 永远不拿


def test_frame_133a_accrues_tbill_and_sets_level():
    days = pd.bdate_range("1999-12-01", "2026-09-30")
    inp = {"dtb3": pd.Series(5.0, index=days), "fx": pd.Series(100.0, index=days),
           "n225": pd.DataFrame({"Close": 1.0}, index=days)}
    f = X.frame_133a(inp)
    c = f["Close"]
    assert abs(float(c.asof(pd.Timestamp("2026-08-31"))) - 1073.75) < 1e-6
    a, b = float(c.asof(pd.Timestamp("2010-01-04"))), float(c.asof(pd.Timestamp("2011-01-04")))
    g = b / a - 1
    assert 0.049 < g < 0.052                                                        # 年 5%（360 天基准）扣 0.0975%
    assert c.index.min() >= pd.Timestamp("2000-01-01")


def test_shift_placebo_keeps_up_days_and_is_reproducible():
    idx = pd.bdate_range("1999-06-01", "2026-10-30")
    s = pd.Series((np.arange(len(idx)) % 300) < 140, index=idx)
    a, b = X.shifted(s, 7), X.shifted(s, 7)
    assert a.equals(b) and int(a.sum()) == int(X.shift_domain(s).sum())
    w = X.shift_domain(s)
    ks = [X.shift_k(x, len(w)) for x in range(400)]
    assert min(ks) >= 250 and max(ks) <= len(w) - 250 and len(set(ks)) > 300
    assert X.episodes(pd.Series([True, True, False, True])) == 2
