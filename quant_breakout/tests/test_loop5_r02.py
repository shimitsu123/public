"""第五个研究循环第 2 轮 VMS / CSZ（scripts/loop5_r02_volc.py，2026-10-03 登记）：登记值与第五个循环的规则、按市场波动的倍数（基准 = 过去的中位数、
上下限、样本不够 → 1）、C 分数的 2/3 分位与加大哪些信号（会买且分数高；没有规则的格子、被 C 挡的不动）、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop5_r02_volc as T  # noqa: E402
import research_loop5 as R5  # noqa: E402


def test_registered_constants_and_loop5_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.M_LO, T.M_HI, T.VOL_WIN, T.REF_WIN, T.REF_MIN) == (2, ("VMS", "CSZ"), False, 0.5, 1.36, 63, 1260, 504)
    assert T.HI_Q == pytest.approx(2 / 3) and T.KIND == {"VMS": "size_time", "CSZ": "size_trade"} and T.M_HI == pytest.approx(R5.M_CAP)
    assert all(T.FAMILY[k].startswith(R5.FAMILY_PREFIX) for k in T.IDS) and not set(T.IDS) & R5.previous_ids(ROOT / "var")
    st = R5.load_state(ROOT / "var")
    if not st:
        pytest.skip("第五个研究循环还没有登记")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R5.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND[k]} for k in T.IDS], R5.previous_ids(ROOT / "var"))


def test_vms_mult_relative_to_past_median():
    rng = np.random.default_rng(0)
    d = pd.bdate_range("2000-01-03", periods=2000)
    r = rng.normal(0, 0.01, 2000)
    r[1700:1763] *= 4.0                                                        # 一段动荡
    r[1900:] *= 0.25                                                           # 后来很平静
    close = pd.Series(100 * np.exp(np.cumsum(r)), index=d)
    m = T.vms_mult(close, d)
    assert (m.iloc[:63 + 503] == 1.0).all()                                    # 波动率的历史不够 504 个 → 不变
    assert 0.8 < m.iloc[1500] < 1.25                                           # 平常 ≈ 1
    assert m.iloc[1762] == pytest.approx(0.5)                                  # 动荡 → 下限
    assert m.iloc[-1] == pytest.approx(1.36)                                   # 平静 → 上限
    assert ((m >= 0.5) & (m <= 1.36)).all()


def _X(f1, bull=True, vix=15.0):
    return pd.DataFrame({"f1": f1, "n225_ma200": [0.05 if bull else -0.05] * len(f1), "vix": [vix] * len(f1)})


def test_c_hi_and_csz_mult():
    rules = {0: None, 1: None, 2: {"sel": {"f1": 1}, "cut": {"f1": (0.0, 1.0)}, "thr": -0.5}, 3: None}
    trains = [_X([2.0, 2.0, 0.5, -1.0, 0.5, 2.0]), _X([0.5, 0.5, -1.0])]
    hi = T.c_hi(trains, rules)
    s = np.array([1, 1, 0, -1, 0, 1, 0, 0, -1], float)
    assert hi[2] == pytest.approx(np.quantile(s, 2 / 3)) and hi[0] is None and hi[3] is None
    X = pd.concat([_X([2.0, 0.5, -1.0]), _X([2.0], vix=25.0)], ignore_index=True)
    m = T.csz_mult(X, rules, {0: None, 1: None, 2: 0.5, 3: None})
    assert m.tolist() == [1.36, 1.0, 1.0, 1.0]                                # 分数高 → 加；中间 → 不动；被 C 挡 → 不动；没有规则的格子 → 不动


def test_wiring_and_cli():
    r = inspect.getsource(T.runs)
    assert 'R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(M["VMS"], days))' in r and "csz_kw(S, m, days)" in r
    assert "R5.sizing_kw(R5.M_CAP, days=days, tick_mult=R5.ticks_from(S[\"ticker\"], S[\"date\"], m))" in inspect.getsource(T.csz_kw)
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **kw)" in s1 and "R5.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert "csz_kw(S, np.ones(len(S)), days)" in w and "all(v > 0 for v in n.values())" in w
    p = inspect.getsource(T._placebo_one)
    assert "R5.shift_mult(M[\"VMS\"], ks[int(seed)])" in p and "R5.permute_mult(m, int(seed))" in p
    with pytest.raises(SystemExit):
        T.main(["--nope"])
