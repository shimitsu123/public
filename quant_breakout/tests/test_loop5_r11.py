"""第五个研究循环第 11 轮 DVS / WVS（scripts/loop5_r11_volume.py，2026-10-03 登记）：登记值与第五个循环的规则（最后 2 个做法、新家族、ID 没用过）、
倍数用第 4 / 7 轮已测的三分位与「越高越好」、面板里有这两项、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import combo_all_common as CA  # noqa: E402
import loop5_r04_hiind as R4H  # noqa: E402
import loop5_r11_volume as T  # noqa: E402
import research_loop5 as R5  # noqa: E402


def test_registered_constants_and_loop5_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.FEAT, T.KIND) == (11, ("DVS", "WVS"), False, {"DVS": "vr1", "WVS": "w5v"},
                                                         {"DVS": "size_trade", "WVS": "size_trade"})
    assert T.FAMILY == {"DVS": "仓位·量能", "WVS": "仓位·量能"} and all(T.FAMILY[k].startswith(R5.FAMILY_PREFIX) for k in T.IDS)
    assert not set(T.IDS) & R5.previous_ids(ROOT / "var") and all(f in CA.FEATURES for f in T.FEAT.values())
    st = R5.load_state(ROOT / "var")
    if not st:
        pytest.skip("第五个研究循环还没有登记")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        assert R5.left(st) == len(T.IDS)                                      # 最后 2 个做法
        R5.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND[k]} for k in T.IDS], R5.previous_ids(ROOT / "var"))


def test_tertile_mult_on_volume():
    X = pd.DataFrame({"vr1": [0.5, 1.0, 1.5, 2.0, 3.0, np.nan]})
    cuts = R4H.tertile_cuts([pd.DataFrame({"vr1": [0.8, 1.2, 1.6, 2.4, 3.6, 0.4]})], "vr1")
    m = R4H.high_good_mult(X, "vr1", cuts)
    assert m[0] == R4H.M_LO and m[-2] == R4H.M_HI and m[-1] == 1.0          # 低 → 0.5、高 → 1.36、算不出 → 不变
    assert (R4H.M_LO, R4H.M_HI) == (0.5, 1.36)


def test_wiring_and_cli():
    i = inspect.getsource(T.inputs)
    assert 'R4H.tertile_cuts([W["D"][x] for x in L2.ERAS if x != e], FEAT[k])' in i and 'R4H.high_good_mult(sig[e], FEAT[k], cuts[k][e])' in i
    assert 'R2V.csz_kw(M["sig"][e], M["mult"][k][e], days)' in inspect.getsource(T.runs)
    assert 'R4H.high_good_mult(X, FEAT[k], M["cuts"][k][fold])' in inspect.getsource(T.other_stocks)
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **kw)" in s1 and "R5.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert "R2V.csz_kw(S, np.ones(len(S)), days)" in w and "all(v > 0 for v in n.values())" in w
    assert 'R5.permute_mult(M["mult"][k][e], int(seed))' in inspect.getsource(T._placebo_one)
    assert "loop5_r11_volume.py" in inspect.getsource(T.git_head)
    with pytest.raises(SystemExit):
        T.main(["--nope"])
