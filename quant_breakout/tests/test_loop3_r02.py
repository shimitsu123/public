"""第三个研究循环第 2 轮 FHU（scripts/loop3_r02_fjeust.py，2026-10-02 登记）：登记值、1482 的「熊」= 2845 的「熊」、
follow 模式下各一半、调仓带（为什么是一半）、1987〜2000 的持仓、ID 没用过、命令行。"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop3_r02_fjeust as T  # noqa: E402
import research_loop3 as R3  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.KIND, T.SHARE) == (2, ("FHU",), "核心·日元走强状态资产", True, "asset", 0.5)
    assert T.KIND in R3.KINDS and T.FAMILY not in R3.BANNED
    assert not set(T.IDS) & R3.previous_ids(ROOT / "var")                    # 第一 / 第二个循环没用过


def test_bond_bear_is_exactly_the_hedged_nasdaq_bear():
    import loop2_r02_bondrefuge as T2
    import loop_r04_yensurge as Y
    days = pd.bdate_range("2020-01-01", periods=6)
    bear = pd.Series([False, False, True, False, False, True], index=days)
    uni = pd.Series([True, False, True, True, False, False], index=days)
    fr = pd.DataFrame({"Close": 1.0}, index=days)
    ov = T.fhu_over(bear, uni, fr)
    b1 = Y.fxh_over({"kw": {"Z": {"extra_core": {}}}}, bear, uni, fr)
    assert list(ov["extra_bear"][T2.BD_KEY]) == list(b1["extra_bear"][Y.HG_KEY])   # 2845 拿的时候 1482 也拿
    assert list(ov["extra_bear"][T2.BD_KEY]) == [False, True, True, False, True, True]
    c = ov["cfg_over"]
    assert c["core"] == {"1545.T": 1.0, "2845.T": 1.0, "1482.T": 1.0} and c["core_mode"] == "follow"   # follow：两只「不是熊」→ 各一半
    assert c["core_index"] == {"1545.T": Y.UH_KEY, "2845.T": Y.HG_KEY, "1482.T": T2.BD_KEY} and set(ov["extra_core"]) == {"1482.T"}


def test_held_is_us_bull_and_hedging():
    days = pd.bdate_range("2020-01-01", periods=5)
    bear = pd.Series([False, True, False, False, True], index=days)
    uni = pd.Series([True, True, False, True, False], index=days)
    assert list(T.held(bear, uni, days)) == [True, False, False, True, False]


def test_band_explains_half_share():
    sim = json.loads((ROOT / "var" / "sim.json").read_text(encoding="utf-8"))
    bands = {v for v in _find(sim, "band_pct")}
    assert bands == {10.0}                                                   # 模拟盘的核心调仓带
    assert T.min_idle_to_buy(0.1, 10.0) >= 1.0                               # 各一成：闲置资金要超过总资产 → 永远买不进
    assert T.min_idle_to_buy(T.SHARE, 10.0) == pytest.approx(0.2)            # 一半：闲置资金 > 总资产 20% 就买得进


def _find(o, key):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                yield float(v)
            else:
                yield from _find(v, key)
    elif isinstance(o, list):
        for v in o:
            yield from _find(v, key)


def test_old_core_weights_half_in_hedge_state():
    idx = pd.bdate_range("1990-01-01", periods=4)
    bear = pd.Series([False, True, False, False], index=idx)
    hedge = pd.Series([False, True, True, False], index=idx)
    w = T.fhu_weights(bear, hedge, True)
    assert list(w["u"]) == [1.0, 0.0, 0.0, 1.0] and list(w["h"]) == [0.0, 0.0, 0.5, 0.0] and list(w["b"]) == [0.0, 0.0, 0.5, 0.0]
    w0 = T.fhu_weights(bear, hedge, False)
    assert list(w0["h"]) == [0.0, 0.0, 1.0, 0.0] and w0["b"].sum() == 0.0      # B1：对冲中全部对冲版纳指


def test_wiring_and_cli():
    import inspect
    src = inspect.getsource(T.stage_one)
    assert "fhu_over(W[\"bear\"][\"US\"], uni, fb)" in src and "rb = L2.run(W, e)" in src and "posthoc=unseen" in src
    wsrc = inspect.getsource(T.wiring)
    assert "pd.Series(False, index=uni.index)" in wsrc and "n_bond > 0" in wsrc
    with pytest.raises(SystemExit):
        T.main(["--stage2"])
