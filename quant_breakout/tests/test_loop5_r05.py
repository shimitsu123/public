"""第五个研究循环第 5 轮 IVL / HAL（scripts/loop5_r05_ivolcal.py，2026-10-03 登记）：登记值与第五个循环的规则、特质波动的合成、
「越低越好」的倍数（两头、算不出不动）、季节倍数、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop5_r05_ivolcal as T  # noqa: E402
import research_loop5 as R5  # noqa: E402


def test_registered_constants_and_loop5_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.M_LO, T.M_HI, T.WINTER) == (5, ("IVL", "HAL"), False, 0.5, 1.36, (11, 12, 1, 2, 3, 4))
    assert T.KIND == {"IVL": "size_trade", "HAL": "size_time"}
    assert all(T.FAMILY[k].startswith(R5.FAMILY_PREFIX) for k in T.IDS) and not set(T.IDS) & R5.previous_ids(ROOT / "var")
    st = R5.load_state(ROOT / "var")
    if not st:
        pytest.skip("第五个研究循环还没有登记")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R5.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND[k]} for k in T.IDS], R5.previous_ids(ROOT / "var"))


def test_with_ivol():
    X = pd.DataFrame({"vol60": [0.2, 0.2, 0.3, np.nan], "corr60": [0.0, 0.6, 1.2, 0.5], "a": [1, 2, 3, 4]})
    Y = T.with_ivol(X)
    assert Y["ivol"].iloc[0] == pytest.approx(0.2) and Y["ivol"].iloc[1] == pytest.approx(0.16) and Y["ivol"].iloc[2] == pytest.approx(0.0)
    assert np.isnan(Y["ivol"].iloc[3]) and (Y["a"] == X["a"]).all()


def test_low_good_mult():
    X = pd.DataFrame({"ivol": [0.10, 0.15, 0.17, 0.20, 0.30, np.nan]})
    assert T.low_good_mult(X, "ivol", (0.15, 0.20)).tolist() == [1.36, 1.36, 1.0, 0.5, 0.5, 1.0]
    assert T.low_good_mult(X, "ivol", (np.nan, np.nan)).tolist() == [1.0] * 6
    assert T.low_good_mult(pd.DataFrame({"ivol": [0.2]}), "ivol", (0.2, 0.2)).tolist() == [1.36]


def test_hal_mult():
    d = pd.to_datetime(["2024-10-31", "2024-11-01", "2025-04-30", "2025-05-01"])
    assert T.hal_mult(d).tolist() == [0.5, 1.36, 1.36, 0.5]


def test_wiring_and_cli():
    r = inspect.getsource(T.runs)
    assert 'R2V.csz_kw(M["sig"][e], M["IVL"][e], days)' in r and 'R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(M["HAL"], days))' in r
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **kw)" in s1 and "R5.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert "R2V.csz_kw(S, np.ones(len(S)), days)" in w and "all(v > 0 for v in n.values())" in w
    p = inspect.getsource(T._placebo_one)
    assert 'R5.shift_mult(M["HAL"], ks[int(seed)])' in p and 'R5.permute_mult(M["IVL"][e], int(seed))' in p
    with pytest.raises(SystemExit):
        T.main(["--nope"])
