"""第七个研究循环第 2 轮 VTX（scripts/loop7_r02_voltarget.py，2026-10-04 登记）：登记的常数、ID 与家族、账户比例的对齐与持仓、
市场的比例 = vct_forward 的函数（= 第一个循环 VT20 的函数）、数值平移、横展开的 Δ 与 research_loop7 的同名函数一致、运行的写法。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import loop7_r01_vctx as P1  # noqa: E402
import loop7_r02_voltarget as P  # noqa: E402
import loop_r01_voltarget as VT  # noqa: E402
import loop6_r03_earlyreturn as N3  # noqa: E402
import research_loop7 as R7  # noqa: E402
from qbreak import vct_forward as VF  # noqa: E402


def _px(start="1986-01-01", end="2026-09-30", seed=7):
    idx = pd.bdate_range(start, end)
    r = np.random.default_rng(seed).normal(0.0003, 0.012, len(idx))
    r[2000:2060] *= 3.0                                                         # 一段高波动
    return pd.Series(100 * np.exp(np.cumsum(r)), index=idx)


def test_registered_constants():
    assert (P.ROUND, P.IDS, P.POSTHOC, P.KIND, P.FAMILY) == (2, ("VTX",), True, {"VTX": "cross"}, {"VTX": "核心·波动率"})
    assert P.OUT == "loop7_r02_voltarget"
    st = R7.load_state(ROOT / "var")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == P.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(P.IDS)
    elif st:
        R7.check_new_approaches(st, [{"id": k, "family": P.FAMILY[k], "posthoc": P.POSTHOC, "kind": P.KIND[k]} for k in P.IDS],
                                R7.previous_ids(ROOT / "var"))


def test_market_ratio_is_vt20():
    c = _px()
    x = P.market_ratio(c)
    sg = VF.sigma(c)
    assert np.allclose(x.to_numpy(), VF.exposure(sg, VF.target(sg, start=str(c.index[0].date()))).to_numpy())
    vt = VT.exposure(VT.sigma(c), VT.target(VT.sigma(c)))                       # 数据从 1986-01-01 起 → 与 VT20 的函数完全相同
    assert np.allclose(x.to_numpy(), vt.reindex(x.index).to_numpy())
    assert (x <= 1.0 + 1e-12).all() and (x < 1.0 - 1e-12).any() and (x > 0).all()
    assert np.allclose(P1.signal(c)["vt_ratio"].to_numpy(), x.reindex(P1.signal(c).index).to_numpy())   # 与第 1 轮 VCX 同一个比例
    cut = c.index[6000]
    assert P.market_ratio(c[c.index <= cut]).iloc[-1] == pytest.approx(x.loc[cut])     # 截到某一天再算 = 全历史里那一天


def test_as_of_matches_on_idx_and_fill():
    us = pd.Series([0.5, 1.0, 0.7], index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]))
    tse = pd.to_datetime(["2020-01-01", "2020-01-03", "2020-01-04", "2020-01-07"])
    assert P.as_of(us, tse).tolist() == [1.0, 1.0, 1.0, 0.7]
    b = pd.Series([True, False, True], index=us.index)
    assert (P.as_of(b.astype(float), tse, fill=0.0) > 0.5).tolist() == N3.on_idx(b, tse).tolist()


def test_core_weights_and_expo():
    idx = pd.bdate_range("1990-01-01", periods=4)
    bear = pd.Series([False, False, True, True], index=idx)
    on = pd.Series([True, False, True, False], index=idx)
    x = pd.Series([0.6, 1.0, 0.3, 0.3], index=idx)
    w = P.core_weights(bear, x, on)
    assert w["u"].tolist() == pytest.approx([0.6, 1.0, 0.0, 0.0]) and w["b"].tolist() == pytest.approx([0.0, 0.0, 1.0, 0.0])
    w1 = P.core_weights(bear, pd.Series(1.0, index=idx), on)
    import loop6_r07_volbond as V
    assert w1.equals(V.core_weights(bear, pd.Series(False, index=idx), on))     # 比例全 1 = B3 的持仓
    assert np.allclose(P.expo(~bear, x).to_numpy(), [0.6, 1.0, 0.0, 0.0])
    assert P.vtx_over(x)["core_expo"]["US"].equals(x) and list(P.vtx_over(x)) == ["core_expo"]


def test_shifted_num_only_inside_window():
    idx = pd.bdate_range("1997-12-25", "1998-01-09")
    s = pd.Series(np.linspace(0.1, 1.0, len(idx)), index=idx)
    out = P.shifted_num(s, 2, ("1998-01-01", "1998-01-09"))
    w = idx >= pd.Timestamp("1998-01-01")
    assert out[~w].tolist() == s[~w].tolist()
    assert np.allclose(out[w].to_numpy(), np.roll(s[w].to_numpy(), 2))
    assert P.shifted_num(s, None).equals(s)


def test_deltas_num_equals_research_loop7_for_two_level_ratio():
    """比例只取 2/3 与 1 时：数值平移的 Δ = research_loop7.deltas（布尔信号平移 + 第 1 轮的 expo）。"""
    c = _px("1990-01-01", "2026-09-30", seed=11)
    bull = c > c.rolling(250, min_periods=250).mean()                           # 测试用的牛（检测器的配置在测试的临时目录里没有）
    sig = P1.signal(c)["signal"]
    ratio = pd.Series(np.where(sig.to_numpy(bool), 2 / 3, 1.0), index=sig.index)
    spans = P.spans_of(c)
    for k in (None, 777):
        a = P.deltas_num({"m": c}, {"m": ratio}, {"m": bull}, k, {"m": spans})
        b = R7.deltas({"m": c}, P1.expo, {"m": sig}, {"m": bull}, k, spans)
        assert np.allclose(np.array(a["m"], float), np.array(b["m"], float), atol=1e-12)
    z = P.deltas_num({"m": c}, {"m": pd.Series(1.0, index=c.index)}, {"m": bull}, 1234, {"m": spans})
    assert all(abs(v) < 1e-12 for v in z["m"])                                  # 比例全 1 → Δ 全为 0（平移也是）


def test_run_and_wiring_source():
    w = inspect.getsource(P.wiring)
    for key in ("ones_same_as_b3", "old_core_b3_same", "no_other_core_expo", "markets_ones_zero_delta", "markets_ones_shift_zero_delta"):
        assert key in w
    s2 = inspect.getsource(P.stage_two)
    assert "R7.shift_ks(sc[\"n_min\"])" in s2 and "R7.judge(real, plac)" in s2 and "list(R7.MARKETS)" in s2
    s1 = inspect.getsource(P.stage_one)
    assert "R6.stage1(cand, base, posthoc=unseen)" in s1 and "L6.run(W, e, **ov)" in s1
    ra = inspect.getsource(P.run_all)
    assert "R7.FOUND if (a[\"ok\"] and jd[\"ok\"])" in ra
    assert "R7.deltas" not in inspect.getsource(P.run_k) and "deltas_num" in inspect.getsource(P.run_k)
    for flag in ("--scale", "--wiring"):
        assert flag in inspect.getsource(P.main)
