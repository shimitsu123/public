"""第五个研究循环第 3 轮 BTS / DSP（scripts/loop5_r03_betadisp.py，2026-10-03 登记）：登记值与第五个循环的规则、β 的三分位与倍数（两头、算不出不动）、
横截面离散度（各票自己的交易日、当天只数够才算）、离散度倍数（与过去比、样本不够 → 1）、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop5_r03_betadisp as T  # noqa: E402
import research_loop5 as R5  # noqa: E402


def test_registered_constants_and_loop5_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.M_LO, T.M_HI, T.BETA) == (3, ("BTS", "DSP"), False, 0.5, 1.36, "b_n225")
    assert (T.DISP_WIN, T.REF_WIN, T.REF_MIN, T.MIN_STOCKS) == (20, 1260, 504, 50) and T.KIND == {"BTS": "size_trade", "DSP": "size_time"}
    assert all(T.FAMILY[k].startswith(R5.FAMILY_PREFIX) for k in T.IDS) and not set(T.IDS) & R5.previous_ids(ROOT / "var")
    st = R5.load_state(ROOT / "var")
    if not st:
        pytest.skip("第五个研究循环还没有登记")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R5.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND[k]} for k in T.IDS], R5.previous_ids(ROOT / "var"))


def test_beta_cuts_and_bab_mult():
    tr = [pd.DataFrame({"b_n225": [0.2, 0.5, 0.8, np.nan]}), pd.DataFrame({"b_n225": [1.1, 1.4, 0.6]})]
    lo, hi = T.beta_cuts(tr)
    b = np.array([0.2, 0.5, 0.8, 1.1, 1.4, 0.6])
    assert (lo, hi) == (pytest.approx(np.quantile(b, 1 / 3)), pytest.approx(np.quantile(b, 2 / 3)))
    X = pd.DataFrame({"b_n225": [0.1, lo, 0.7, hi, 2.0, np.nan]})
    assert T.bab_mult(X, (lo, hi)).tolist() == [1.36, 1.36, 1.0, 0.5, 0.5, 1.0]
    assert T.bab_mult(X, (np.nan, np.nan)).tolist() == [1.0] * 6


def test_dispersion_uses_own_days_and_min_stocks():
    d = pd.bdate_range("2020-01-01", periods=30)
    closes = {f"S{i}": pd.Series(100 * (1 + 0.01 * i) ** np.arange(30), index=d) for i in range(60)}
    disp = T.dispersion(closes, d)
    assert disp.iloc[:20].isna().all() and disp.iloc[20:].notna().all()        # 前 20 天没有 20 日涨跌
    r = np.array([(1 + 0.01 * i) ** 20 - 1 for i in range(60)])
    assert disp.iloc[25] == pytest.approx(np.std(r, ddof=1))
    few = {k: v for k, v in list(closes.items())[:40]}
    assert T.dispersion(few, d).isna().all()                                   # 不到 50 只 → 不算


def test_dsp_mult_relative_to_past():
    rng = np.random.default_rng(3)
    d = pd.bdate_range("2000-01-03", periods=1800)
    disp = pd.Series(0.07 + rng.normal(0, 0.005, 1800), index=d)
    disp.iloc[1700] = 0.20
    disp.iloc[1710] = 0.01
    m = T.dsp_mult(disp)
    assert (m.iloc[:503] == 1.0).all()                                         # 历史不够 504 个 → 不变
    assert m.iloc[1700] == 0.5 and m.iloc[1710] == 1.36
    assert set(np.unique(m.to_numpy())) <= {0.5, 1.0, 1.36}
    disp2 = disp.copy()
    disp2.iloc[1750:] = np.nan
    assert (T.dsp_mult(disp2).iloc[1750:] == 1.0).all()                        # 算不出 → 不变


def test_wiring_and_cli():
    r = inspect.getsource(T.runs)
    assert "R2V.csz_kw(S, m, days)" in r and 'R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(M["DSP"], days))' in r
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **kw)" in s1 and "R5.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert "R2V.csz_kw(S, np.ones(len(S)), days)" in w and "all(v > 0 for v in n.values())" in w
    p = inspect.getsource(T._placebo_one)
    assert 'R5.shift_mult(M["DSP"], ks[int(seed)])' in p and "R5.permute_mult(m, int(seed))" in p
    with pytest.raises(SystemExit):
        T.main(["--nope"])
