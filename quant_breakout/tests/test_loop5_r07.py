"""第五个研究循环第 7 轮 X2F（scripts/loop5_r07_x2f.py，2026-10-03 登记）：登记值与第五个循环的规则、倍数用第 4 轮已测的三分位与
「越高越好」、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop5_r07_x2f as T  # noqa: E402
import research_loop5 as R5  # noqa: E402


def test_registered_constants_and_loop5_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.FEAT, T.KIND) == (7, ("X2F",), False, {"X2F": "x2"}, {"X2F": "size_trade"})
    assert all(T.FAMILY[k].startswith(R5.FAMILY_PREFIX) for k in T.IDS) and not set(T.IDS) & R5.previous_ids(ROOT / "var")
    assert "FIP" in R5.previous_ids(ROOT / "var")                             # 第三个循环用过 → 本轮不登记 FIP（见脚本开头）
    st = R5.load_state(ROOT / "var")
    if not st:
        pytest.skip("第五个研究循环还没有登记")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R5.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND[k]} for k in T.IDS], R5.previous_ids(ROOT / "var"))


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
    with pytest.raises(SystemExit):
        T.main(["--nope"])
