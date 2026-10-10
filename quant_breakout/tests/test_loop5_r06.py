"""第五个研究循环第 6 轮 DYV / LTR（scripts/loop5_r06_valrev.py，2026-10-03 登记）：登记值与第五个循环的规则、
「过去 730 天的信号」三分位（只用之前的、不够 30 个 → 不算）、两个方向的倍数、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop5_r06_valrev as T  # noqa: E402
import research_loop5 as R5  # noqa: E402


def test_registered_constants_and_loop5_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.M_LO, T.M_HI, T.PAST_DAYS, T.PAST_MIN) == (6, ("DYV", "LTR"), False, 0.5, 1.36, 730, 30)
    assert T.FEAT == {"DYV": "dy", "LTR": "r3y"} and T.HIGH_GOOD == {"DYV": True, "LTR": False}
    assert T.KIND == {"DYV": "size_trade", "LTR": "size_trade"}
    assert all(T.FAMILY[k].startswith(R5.FAMILY_PREFIX) for k in T.IDS) and not set(T.IDS) & R5.previous_ids(ROOT / "var")
    st = R5.load_state(ROOT / "var")
    if not st:
        pytest.skip("第五个研究循环还没有登记")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R5.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND[k]} for k in T.IDS], R5.previous_ids(ROOT / "var"))


def test_past_cuts_only_before_and_min_count():
    rd = pd.bdate_range("2020-01-01", periods=60)
    rv = np.arange(60, dtype=float)
    c = T.past_cuts(rd, rv, [rd[29], rd[30], rd[59], pd.Timestamp("2025-01-01")])
    assert np.isnan(c[0]).all()                                                # 之前只有 29 个 → 不算
    assert c[1] == pytest.approx([np.quantile(np.arange(30), 1 / 3), np.quantile(np.arange(30), 2 / 3)])   # 当天的不算
    assert c[2] == pytest.approx([np.quantile(np.arange(59), 1 / 3), np.quantile(np.arange(59), 2 / 3)])
    assert np.isnan(c[3]).all()                                                # 730 天以内没有 → 不算
    rv2 = rv.copy()
    rv2[:40] = np.nan
    assert np.isnan(T.past_cuts(rd, rv2, [rd[59]])[0]).all()                   # NaN 不算数


def test_rank_mult_both_directions():
    cuts = np.array([[1.0, 2.0]] * 5 + [[np.nan, np.nan]])
    v = [0.5, 1.0, 1.5, 2.0, np.nan, 3.0]
    assert T.rank_mult(v, cuts, True).tolist() == [0.5, 0.5, 1.0, 1.36, 1.0, 1.0]
    assert T.rank_mult(v, cuts, False).tolist() == [1.36, 1.36, 1.0, 0.5, 1.0, 1.0]
    assert T.rank_mult([1.0], np.array([[1.0, 1.0]]), True).tolist() == [1.36]


def test_wiring_and_cli():
    assert 'R2V.csz_kw(M["sig"][e], M["mult"][k][e], days)' in inspect.getsource(T.runs)
    assert 'past_cuts(ref["date"], ref[f].to_numpy(float), X["date"])' in inspect.getsource(T.mult_for)
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **kw)" in s1 and "R5.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert "R2V.csz_kw(S, np.ones(len(S)), days)" in w and "all(v > 0 for v in n.values())" in w
    assert 'R5.permute_mult(M["mult"][k][e], int(seed))' in inspect.getsource(T._placebo_one)
    with pytest.raises(SystemExit):
        T.main(["--nope"])
