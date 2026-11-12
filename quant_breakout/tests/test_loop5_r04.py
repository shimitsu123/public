"""第五个研究循环第 4 轮 H52 / ISM（scripts/loop5_r04_hiind.py，2026-10-03 登记）：登记值与第五个循环的规则、学习样本的三分位、
「越高越好」的倍数（两头、算不出不动、分位相同不冲突）、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop5_r04_hiind as T  # noqa: E402
import research_loop5 as R5  # noqa: E402


def test_registered_constants_and_loop5_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.M_LO, T.M_HI) == (4, ("H52", "ISM"), False, 0.5, 1.36)
    assert T.FEAT == {"H52": "hi52", "ISM": "sec"} and T.KIND == {"H52": "size_trade", "ISM": "size_trade"}
    assert all(T.FAMILY[k].startswith(R5.FAMILY_PREFIX) for k in T.IDS) and not set(T.IDS) & R5.previous_ids(ROOT / "var")
    st = R5.load_state(ROOT / "var")
    if not st:
        pytest.skip("第五个研究循环还没有登记")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R5.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND[k]} for k in T.IDS], R5.previous_ids(ROOT / "var"))


def test_tertile_cuts_and_high_good_mult():
    tr = [pd.DataFrame({"hi52": [0.80, 0.90, np.nan, 1.00]}), pd.DataFrame({"hi52": [0.85, 0.95, 0.99]})]
    lo, hi = T.tertile_cuts(tr, "hi52")
    x = np.array([0.80, 0.90, 1.00, 0.85, 0.95, 0.99])
    assert (lo, hi) == (pytest.approx(np.quantile(x, 1 / 3)), pytest.approx(np.quantile(x, 2 / 3)))
    X = pd.DataFrame({"hi52": [0.70, lo, 0.92, hi, 1.00, np.nan]})
    assert T.high_good_mult(X, "hi52", (lo, hi)).tolist() == [0.5, 0.5, 1.0, 1.36, 1.36, 1.0]
    assert T.high_good_mult(X, "hi52", (np.nan, np.nan)).tolist() == [1.0] * 6
    assert T.high_good_mult(pd.DataFrame({"sec": [0.5]}), "sec", (0.5, 0.5)).tolist() == [1.36]   # 分位相同 → 算「高」，不冲突


def test_wiring_and_cli():
    assert 'R2V.csz_kw(M["sig"][e], M["mult"][k][e], days)' in inspect.getsource(T.runs)
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **kw)" in s1 and "R5.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert "R2V.csz_kw(S, np.ones(len(S)), days)" in w and "all(v > 0 for v in n.values())" in w
    assert 'R5.permute_mult(M["mult"][k][e], int(seed))' in inspect.getsource(T._placebo_one)
    with pytest.raises(SystemExit):
        T.main(["--nope"])
