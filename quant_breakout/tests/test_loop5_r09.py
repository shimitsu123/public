"""第五个研究循环第 9 轮 RSK（scripts/loop5_r09_risk.py，2026-10-03 登记）：登记值与第五个循环的规则、学习样本的中位数、
「中位数 ÷ 这只」的倍数（上下限、算不出不动）、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop5_r09_risk as T  # noqa: E402
import research_loop5 as R5  # noqa: E402


def test_registered_constants_and_loop5_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.M_LO, T.M_HI, T.FEAT, T.KIND) == (9, ("RSK",), False, 0.5, 1.36, {"RSK": "atrp"}, {"RSK": "size_trade"})
    assert all(T.FAMILY[k].startswith(R5.FAMILY_PREFIX) for k in T.IDS) and not set(T.IDS) & R5.previous_ids(ROOT / "var")
    st = R5.load_state(ROOT / "var")
    if not st:
        pytest.skip("第五个研究循环还没有登记")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R5.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND[k]} for k in T.IDS], R5.previous_ids(ROOT / "var"))


def test_median_ref_and_risk_mult():
    tr = [pd.DataFrame({"atrp": [0.01, 0.02, np.nan, -1.0]}), pd.DataFrame({"atrp": [0.03, 0.04, 0.0]})]
    assert T.median_ref(tr, "atrp") == pytest.approx(0.025)                  # 只用 > 0 的有限值
    X = pd.DataFrame({"atrp": [0.025, 0.05, 0.10, 0.02, 0.01, np.nan, 0.0]})
    m = T.risk_mult(X, "atrp", 0.025)
    assert m.tolist() == pytest.approx([1.0, 0.5, 0.5, 1.25, 1.36, 1.0, 1.0])   # 中位数 → 1；两倍 → 0.5；截在 0.5〜1.36；算不出 → 1
    assert T.risk_mult(X, "atrp", np.nan).tolist() == [1.0] * 7
    assert T.median_ref([], "atrp") != T.median_ref([], "atrp")              # NaN


def test_wiring_and_cli():
    i = inspect.getsource(T.inputs)
    assert 'median_ref([W["D"][x] for x in L2.ERAS if x != e], FEAT[k])' in i and 'risk_mult(sig[e], FEAT[k], ref[k][e])' in i
    assert 'R2V.csz_kw(M["sig"][e], M["mult"][k][e], days)' in inspect.getsource(T.runs)
    assert 'risk_mult(X, FEAT[k], M["cuts"][k][fold])' in inspect.getsource(T.other_stocks)
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **kw)" in s1 and "R5.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert "R2V.csz_kw(S, np.ones(len(S)), days)" in w and "all(v > 0 for v in n.values())" in w
    assert 'R5.permute_mult(M["mult"][k][e], int(seed))' in inspect.getsource(T._placebo_one)
    with pytest.raises(SystemExit):
        T.main(["--nope"])
