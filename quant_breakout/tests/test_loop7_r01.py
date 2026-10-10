"""第七个研究循环第 1 轮 VCX（scripts/loop7_r01_vctx.py，2026-10-04 登记）：登记的常数、通用版信号 = qbreak/vct_forward 的同名函数
（中位数从数据第一天起）、仓位、账户第一关引用 VCT 的结果、ID 与家族、接线核对的写法。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import loop7_r01_vctx as P  # noqa: E402
import research_loop7 as R7  # noqa: E402
from qbreak import vct_forward as VF  # noqa: E402


def test_registered_constants():
    assert (P.ROUND, P.IDS, P.POSTHOC, P.KIND, P.FAMILY) == (1, ("VCX",), True, {"VCX": "cross"}, {"VCX": "核心·波动率"})
    assert P.KEEP == pytest.approx(2 / 3) and (P.SOURCE_ID, P.SOURCE_FILE) == ("VCT", "loop6_r09_volcash.json")
    st = R7.load_state(ROOT / "var")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == P.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(P.IDS)
    elif st:
        R7.check_new_approaches(st, [{"id": k, "family": P.FAMILY[k], "posthoc": P.POSTHOC, "kind": P.KIND[k]} for k in P.IDS],
                                R7.previous_ids(ROOT / "var"))


def test_signal_matches_vct_forward_functions():
    idx = pd.bdate_range("1990-01-01", "2026-09-30")
    r = np.random.default_rng(5).normal(0.0003, 0.012, len(idx))
    r[3000:3040] -= 0.01
    c = pd.Series(100 * np.exp(np.cumsum(r)), index=idx)
    s = P.signal(c)
    sg = VF.sigma(c)
    tg = VF.target(sg, start="1990-01-01")
    ratio = VF.exposure(sg, tg)
    assert np.allclose(s["vt_ratio"].to_numpy(), ratio.reindex(s.index).to_numpy())
    exp = (ratio.reindex(s.index) < 1 - 1e-12) & VF.trend_down(c).reindex(s.index)
    assert s["signal"].tolist() == exp.tolist() and s["signal"].any() and not s["signal"].all()
    cut = idx[5000]                                                             # 截到某一天再算 = 全历史里那一天
    assert bool(P.signal(c[c.index <= cut])["signal"].iloc[-1]) == bool(s.loc[cut, "signal"])


def test_expo():
    idx = pd.bdate_range("2020-01-01", periods=4)
    b = pd.Series([True, True, False, False], index=idx)
    s = pd.Series([True, False, True, False], index=idx)
    assert np.allclose(P.expo(b, s).to_numpy(), [2 / 3, 1, 0, 0])
    assert np.allclose(P.expo(b, pd.Series(False, index=idx)).to_numpy(), b.astype(float).to_numpy())


def test_account_stage1_reference():
    s1 = P.account_stage1(ROOT / "var" / "out")
    assert s1["ok"] is True and s1["sum"] == pytest.approx(0.354, abs=1e-9) and s1["source"].startswith("loop6_r09_volcash.json")


def test_wiring_and_run_source():
    w = inspect.getsource(P.wiring)
    assert "never_signal_zero_delta" in w and "account_stage1_ok" in w
    st2 = inspect.getsource(P.stage_two)
    assert "R7.shift_ks(sc[\"n_min\"])" in st2 and "R7.judge(real, plac)" in st2 and "list(R7.MARKETS)" in st2
    assert "R7.deltas" in inspect.getsource(P.run_k)
    for flag in ("--scale", "--wiring"):
        assert flag in inspect.getsource(P.main)
