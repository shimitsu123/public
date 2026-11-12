"""第七个研究循环第 3 轮 VSX（scripts/loop7_r03_volshock.py，2026-10-04 登记）：登记的常数、ID 与家族、冲击比例的算法
（σ20 vs 过去 250 天的实现波动，vct_forward.exposure 原样）、只用到当天为止、重叠的数法、运行的写法（复用第 2 轮已登记的纯函数）。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import loop7_r03_volshock as P  # noqa: E402
import research_loop7 as R7  # noqa: E402
from qbreak import vct_forward as VF  # noqa: E402


def _px(start="1990-01-01", end="2026-09-30", seed=3):
    idx = pd.bdate_range(start, end)
    r = np.random.default_rng(seed).normal(0.0003, 0.010, len(idx))
    r[3000:3030] *= 4.0                                                         # 一次波动冲击
    r[5000:6000] *= 2.0                                                         # 一段整体偏高、但平稳的高波动
    return pd.Series(100 * np.exp(np.cumsum(r)), index=idx)


def test_registered_constants():
    assert (P.ROUND, P.IDS, P.POSTHOC, P.KIND, P.FAMILY, P.WIN_LONG) == (3, ("VSX",), True, {"VSX": "cross"}, {"VSX": "核心·波动率"}, 250)
    assert P.OUT == "loop7_r03_volshock"
    st = R7.load_state(ROOT / "var")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == P.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(P.IDS)
    elif st:
        R7.check_new_approaches(st, [{"id": k, "family": P.FAMILY[k], "posthoc": P.POSTHOC, "kind": P.KIND[k]} for k in P.IDS],
                                R7.previous_ids(ROOT / "var"))


def test_sigma_long_and_shock_ratio():
    c = _px()
    sl = P.sigma_long(c)
    r = np.log(c).diff()
    i = 4000
    assert sl.iloc[i] == pytest.approx(r.iloc[i - 249:i + 1].std() * np.sqrt(252))
    assert sl.iloc[:250].isna().all() and not np.isnan(sl.iloc[250])
    x = P.shock_ratio(c)
    assert np.allclose(x.to_numpy(), VF.exposure(VF.sigma(c), sl).to_numpy())
    assert (x <= 1.0 + 1e-12).all() and (x > 0).all()
    assert x.iloc[3005:3030].min() < 0.5                                        # 冲击里减得多
    assert (x.iloc[5400:5950] < 1.0 - 1e-12).mean() < 0.5                       # 整体偏高但平稳的年代多半不减
    cut = c.index[3020]
    assert P.shock_ratio(c[c.index <= cut]).iloc[-1] == pytest.approx(x.loc[cut])   # 截到某一天再算 = 全历史里那一天


def test_overlap():
    idx = pd.bdate_range("2020-01-01", periods=6)
    bull = pd.Series([True, True, True, True, False, True], index=idx)
    a = pd.Series([0.5, 0.5, 1.0, 0.8, 0.5, 1.0], index=idx)
    b = pd.Series([0.7, 1.0, 0.6, 0.9, 0.5, 1.0], index=idx)
    assert P.overlap(bull, a, b) == pytest.approx(round(2 / 3 * 100, 1))
    assert P.overlap(bull, pd.Series(1.0, index=idx), b) is None


def test_run_and_wiring_source():
    w = inspect.getsource(P.wiring)
    for key in ("ones_same_as_b3", "old_core_ones_same", "no_other_core_expo", "markets_ones_zero_delta", "markets_ones_shift_zero_delta",
                "ratio_us_is_shock_ratio"):
        assert key in w
    s2 = inspect.getsource(P.stage_two)
    assert "R7.shift_ks(sc[\"n_min\"])" in s2 and "R7.judge(real, plac)" in s2 and "list(R7.MARKETS)" in s2
    s1 = inspect.getsource(P.stage_one)
    assert "R6.stage1(cand, base, posthoc=unseen)" in s1 and "L6.run(W, e, **ov)" in s1 and "P2.old_core(W, M[\"ratio_us\"])" in s1
    assert "R7.FOUND if (a[\"ok\"] and jd[\"ok\"])" in inspect.getsource(P.run_all)
    assert "P2.deltas_num" in inspect.getsource(P.run_k)
    assert "shock_ratio(c)" in inspect.getsource(P.market_inputs) and "shock_ratio(EI.ndx_tr(W[\"inp\"]))" in inspect.getsource(P.account_inputs)
    for flag in ("--scale", "--wiring"):
        assert flag in inspect.getsource(P.main)
