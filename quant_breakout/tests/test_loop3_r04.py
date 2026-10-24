"""第三个研究循环第 4 轮 ZSP（scripts/loop3_r04_zonespx.py，2026-10-02 登记）：登记值、警戒区 = 0% 线连续 5 天在下面且分界不是熊、
接法 = NSX 原样（警戒区全 False = B1 的两个键）、ID 没用过、命令行。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop3_r04_zonespx as T  # noqa: E402
import research_loop3 as R3  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.KIND) == (4, ("ZSP",), "核心·指数选择", True, "signal")
    assert T.ZONE == {"L": 250, "b": 0.0, "k": 5}
    import json
    d = json.loads((ROOT / "var" / "bullbear.json").read_text(encoding="utf-8"))["detector"]   # 测试在临时 QBREAK_HOME 下 → 直接读仓库的
    assert d["kind"] == "ma_band" and (d["params"]["L"], d["params"]["k"]) == (T.ZONE["L"], T.ZONE["k"]) and d["params"]["b"] == 0.03
    assert T.KIND in R3.KINDS and not set(T.IDS) & R3.previous_ids(ROOT / "var")


def test_zone_bear_needs_k_closes_below_the_line():
    idx = pd.bdate_range("2020-01-01", periods=16)
    px = pd.Series([10, 10, 10, 10, 10, 9.9, 9.9, 9.9, 9.9, 9.9, 9.9, 10.5, 10.5, 10.5, 10.5, 10.5], index=idx, dtype=float)
    z = T.zone_bear(px, {"L": 5, "b": 0.0, "k": 3})
    assert not z.iloc[:7].any() and z.iloc[7]                                # 第 3 天收在 5 日线下面才算
    assert z.iloc[12] and not z.iloc[13]                                     # 连续 3 天在上面才结束


def test_zone_state_excludes_b1_bear():
    idx = pd.bdate_range("2020-01-01", periods=5)
    zb = pd.Series([False, True, True, True, False], index=idx)
    ub = pd.Series([False, False, True, False, False], index=idx)
    assert list(T.zone_state(zb, ub)) == [False, True, False, True, False]


def test_never_zone_keeps_b1_keys():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=6)
    bear = pd.Series([False, True, False, False, True, False], index=idx)
    uni = pd.Series([True, False, False, True, False, False], index=idx)
    k = T.NS.nsx_keys(bear, uni, pd.Series(False, index=idx))
    assert list(k[Y.UH_KEY].reindex(idx)) == list(Y.or_series(bear, uni).reindex(idx))
    assert list(k[Y.HG_KEY].reindex(idx)) == list(Y.or_series(bear, ~uni).reindex(idx))
    assert k[T.NS.SU_KEY].reindex(idx).all() and k[T.NS.SH_KEY].reindex(idx).all()   # S&P 两只永远是熊（不拿）


def test_wiring_and_cli():
    import inspect
    src = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in src and "posthoc=unseen" in src and "NS.nsx_over(W, sw, uni" in src
    wsrc = inspect.getsource(T.wiring)
    assert "pd.Series(False, index=sw.index)" in wsrc and "n_spx > 0" in wsrc
    with pytest.raises(SystemExit):
        T.main(["--nope"])
    assert np.isfinite(T.ZONE["L"])


def test_placebo_zone_keeps_days_and_stays_on_bull_days():
    idx = pd.bdate_range("2000-01-03", periods=900)
    rng = np.random.default_rng(7)
    bear = pd.Series(False, index=idx)
    bear.iloc[100:180] = True                                                 # 一段熊市
    zb = pd.Series(False, index=idx)
    for a, n in ((50, 8), (300, 15), (600, 5)):
        zb.iloc[a:a + n] = True
    zb.iloc[120:130] = True                                                   # 熊市里的 0% 熊不算警戒区
    real = T.zone_state(zb, bear)
    for seed in (0, 1, 399):
        p = T.placebo_zone(zb, bear, seed, a="2000-01-03", b=str(idx[-1].date()))
        assert int(p.sum()) == int(real.sum()) == 28                         # 天数不变
        assert not (p & bear.reindex(p.index).to_numpy(bool)).any()           # 只落在牛市的日子里
        assert p.equals(T.placebo_zone(zb, bear, seed, a="2000-01-03", b=str(idx[-1].date())))   # 同一个种子 = 同一个结果
    pos = np.flatnonzero(~bear.to_numpy(bool))
    k = R3.shift_ks(len(pos))[5]
    assert list(T.placebo_zone(zb, bear, 5, a="2000-01-03", b=str(idx[-1].date())).to_numpy()[pos]) == list(np.roll(real.to_numpy()[pos], k))
    assert rng is not None


def test_stage_two_reuses_registered_pieces():
    import inspect
    src = inspect.getsource(T.stage_two)
    assert 'R3.stage2(stat, vals)' in src and 'if not s1["ok"]' in src and "NS.nsx_over(W, sw, uni, hspx)" in src
    assert "R3.shift_ks(len(pos), seeds=[seed])[0]" in inspect.getsource(T.placebo_zone)
