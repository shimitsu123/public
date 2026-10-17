"""第四个研究循环第 6 轮 CV3（scripts/loop4_r06_ccell3.py，2026-10-03 登记）：登记值与第四个循环的规则、格 3 用格 2 的规则（其余格与 apply_c 逐个相同；
格 2 没有规则 / 格 3 本来有规则 → 不动）、逐年前推两种（原样 / 扩到格 3）、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import combo_all_common as CA  # noqa: E402
import loop4_r06_ccell3 as T  # noqa: E402
import research_loop4 as R4  # noqa: E402


def test_registered_constants_and_loop4_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.SRC_CELL, T.DST_CELL) == (6, ("CV3",), False, "stock", 2, 3)
    assert T.FAMILY == {"CV3": "选股·C 的适用范围"} and all(f.startswith(R4.FAMILY_PREFIX) for f in T.FAMILY.values())
    assert not set(T.IDS) & R4.previous_ids(ROOT / "var")
    st = R4.load_state(ROOT / "var")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R4.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND} for k in T.IDS], R4.previous_ids(ROOT / "var"))


def _panel(seed, n=600):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({f: rng.normal(size=n) for f in CA.STOCK_FEATS})
    X["n225_ma200"] = np.where(np.arange(n) % 2 == 0, 0.05, -0.05)          # 偶数 = 200 日线上
    X["vix"] = np.where(np.arange(n) % 20 == 2, 25.0, 15.0)                  # 格 3（线上且 VIX ≥ 20）只有 1/20 → 学不出规则（< 60 笔）
    X["net"] = 2.0 * X[CA.STOCK_FEATS[0]] + rng.normal(size=n)
    return X


def test_apply_c3_uses_cell2_rule_only_in_cell3():
    tr = [_panel(1), _panel(2)]
    rules = CA.fit_c(tr)
    assert rules[2] is not None
    X = _panel(3, n=200)
    X["vix"] = np.where(np.arange(200) < 100, 15.0, 25.0)
    X["n225_ma200"] = 0.05                                                   # 前 100 个格 2、后 100 个格 3
    k0, k3 = CA.apply_c(rules, X), T.apply_c3(rules, X)
    cell = CA.cell_of(X)
    assert np.array_equal(k0[cell != 3], k3[cell != 3])                      # 格 3 以外逐个相同
    assert rules.get(3) is None
    assert np.array_equal(k3[cell == 3], CA.apply_v(rules[2], X[cell == 3])) and (~k3[cell == 3]).any() and k0[cell == 3].all()
    r2 = {**rules, 2: None}
    assert np.array_equal(T.apply_c3(r2, X), CA.apply_c(r2, X))              # 格 2 没有规则 → 不动


def test_keep_fwd3_ext_false_equals_plain_forward():
    tr = _panel(5, n=1200)
    tr["date"], tr["exit"], tr["ticker"] = pd.Timestamp("2005-01-04"), pd.Timestamp("2005-03-01"), [f"S{i}.T" for i in range(1200)]
    A = _panel(6, n=40).assign(date=[pd.Timestamp("2007-06-01")] * 40, ticker="Q.T")
    rule = T.XS.fit_c_y([T.XS.fwd_pool([tr], 2007)], "net")
    assert list(T.keep_fwd3([tr], A, False)) == list(CA.apply_c(rule, A))
    assert list(T.keep_fwd3([tr], A, True)) == list(T.apply_c3(rule, A))


def test_wiring_and_cli():
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and 'rc = L2.run(W, e, fr=XS.frames(W, e, kp[e]["CV3"]))' in s1
    assert 'lenses={"loeo": (cand, base), "fwd": (fc, fb)}' in s1 and "posthoc=None" in s1
    k = inspect.getsource(T.keeps)
    assert 'rules = CA.fit_c([W["D"][x] for x in L2.ERAS if x != e])' in k and '"CV3": apply_c3(rules, A)' in k
    o = inspect.getsource(T.other_stocks)
    assert "X = D[s][kc]" in o and "g = ~apply_c3(rules, X)" in o
    w = inspect.getsource(T.wiring)
    assert "same_outside_cell3" in w and 'XS.frames(W, "J", kp["J"]["C"])' in w
    with pytest.raises(SystemExit):
        T.main(["--nope"])
