"""第四个研究循环第 5 轮 CWX（scripts/loop4_r05_cwide.py，2026-10-03 登记）：登记值与第四个循环的规则、每个折的学习集（日経225 另外两个年代 +
不同时期的扩大池；不含考试年代、不含同一时期的池子）、S5 的池子不在那个折的学习集里、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop4_r05_cwide as T  # noqa: E402
import research_loop4 as R4  # noqa: E402


def test_registered_constants_and_loop4_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.POOLS) == (5, ("CWX",), False, "stock", ("W", "Jx"))
    assert T.FAMILY == {"CWX": "选股·学习样本"} and all(f.startswith(R4.FAMILY_PREFIX) for f in T.FAMILY.values())
    assert not set(T.IDS) & R4.previous_ids(ROOT / "var")
    st = R4.load_state(ROOT / "var")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R4.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND} for k in T.IDS], R4.previous_ids(ROOT / "var"))


def test_train_keys_exclude_exam_era_and_same_period_pool():
    assert T.train_keys("Z") == ["E", "J", "W", "Jx"]
    assert T.train_keys("E") == ["Z", "J", "Jx"]                             # E 折不用同一时期的 W
    assert T.train_keys("J") == ["Z", "E", "W"]                              # J 折不用同一时期的 Jx
    assert T.SAME_PERIOD == {"E": "W", "J": "Jx"}
    for s, fold in (("W", "E"), ("Jx", "J")):                                # S5 的池子不在那个折的学习集里
        assert s not in T.train_keys(fold) and fold not in T.train_keys(fold)


def test_wiring_and_cli():
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and 'rc = L2.run(W, e, fr=XS.frames(W, e, kp[e]["CWX"]))' in s1
    assert 'lenses={"loeo": (cand, base), "fwd": (fc, fb)}' in s1 and "posthoc=None" in s1
    k = inspect.getsource(T.keeps)
    assert 'CA.apply_c(CA.fit_c([W["D"][x] for x in L2.ERAS if x != e]), A)' in k
    assert 'XS.fit_c_y([DX[k] for k in train_keys(e)], "net")' in k and '"fwd_c": XS.keep_fwd(n225, A, "net"), "fwd_w": XS.keep_fwd(wide, A, "net")' in k
    w = inspect.getsource(T.wiring)
    assert 'XS.frames(W, "J", kp["J"]["C"])' in w and "sum(ndiff.values()) > 0" in w
    with pytest.raises(SystemExit):
        T.main(["--nope"])
