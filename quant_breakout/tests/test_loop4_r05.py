"""第四个研究循环第 5 轮 W2T / VTZ（scripts/loop4_r05_weakvol.py，2026-10-03 登记）：登记值与第四个循环的规则、弱市的判定（日経在 200 日线下；
缺值不算）、只在弱市且量不够时挡（缺值不挡、牛市一笔不挡）、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop4_r05_weakvol as T  # noqa: E402
import research_loop4 as R4  # noqa: E402


def test_registered_constants_and_loop4_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.W2T_MIN, T.VTZ_MIN) == (5, ("W2T", "VTZ"), False, "stock", 1.5, 2.0)
    assert T.FAMILY == {"W2T": "选股·门槛随市况", "VTZ": "选股·门槛随市况"} and all(f.startswith(R4.FAMILY_PREFIX) for f in T.FAMILY.values())
    assert not set(T.IDS) & R4.previous_ids(ROOT / "var")
    st = R4.load_state(ROOT / "var")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R4.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND} for k in T.IDS], R4.previous_ids(ROOT / "var"))


def test_weak_and_gates():
    X = pd.DataFrame({"n225_ma200": [-0.05, -0.05, 0.02, np.nan, -0.01, -0.01],
                      "w5v": [1.2, 1.6, 1.2, 1.2, np.nan, 1.49],
                      "vr1": [1.5, 2.5, 1.0, 1.0, 1.9, np.nan]})
    assert list(T.weak(X)) == [True, True, False, False, True, True]
    g = T.gates(X)
    assert list(g["W2T"]) == [True, False, False, False, False, True]     # 弱市且周线量比 < 1.5；牛市 / 日経缺值 / 量缺值 → 不挡
    assert list(g["VTZ"]) == [True, False, False, False, True, False]     # 弱市且突破日量比 < 2.0


def test_runs_wiring_and_cli():
    assert T.runs({"J": {"W2T": {("A.T", pd.Timestamp("2024-01-04")): 0.0}, "VTZ": {}}}, "J") == {
        "W2T": {"em_tick": {("A.T", pd.Timestamp("2024-01-04")): 0.0}}, "VTZ": {"em_tick": {}}}
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **over)" in s1 and "R4.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert 'empty = {"J": {k: {} for k in IDS}}' in w and "all(v > 0 for v in n.values())" in w
    o = inspect.getsource(T.other_stocks)
    assert "X = D[s][CA.apply_c(R1[fold], D[s])]" in o and "gs = gates(X)" in o
    with pytest.raises(SystemExit):
        T.main(["--nope"])
