"""第十一个研究循环（scripts/research_loop11.py：卖法，按股票种类 / 周期区分）：两条路线、V4〜V6、第二关（种类标签随机打乱）、ID / 家族规则。"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_loop10 as R10  # noqa: E402
import research_loop11 as R  # noqa: E402

BASE = {"Z": {"calmar": 1.194, "dd": -14.29, "h1": 1.422, "h2": 1.722, "n": 35, "win": 65.7, "mean": 6.0},
        "E": {"calmar": 0.627, "dd": -23.19, "h1": 0.215, "h2": 1.479, "n": 43, "win": 41.9, "mean": 1.29},
        "J": {"calmar": 0.676, "dd": -29.61, "h1": 0.722, "h2": 0.79, "n": 62, "win": 48.4, "mean": 3.06}}


def _cand(dcal=0.0, dwin=0.0, dmean=0.0, ddd=0.0, dh=0.0):
    out = {}
    for e, b in BASE.items():
        dc = dcal[e] if isinstance(dcal, dict) else dcal
        dw = dwin[e] if isinstance(dwin, dict) else dwin
        out[e] = {**b, "calmar": b["calmar"] + dc, "dd": b["dd"] + ddd, "h1": b["h1"] + dh, "h2": b["h2"] + dh,
                  "win": b["win"] + dw, "mean": b["mean"] + dmean}
    return out


def test_constants_copy_loops_9_and_10():
    assert (R.WIN_MIN, R.ERA_WIN_TOL, R.ERA_TOL, R.DD_TOL, R.HALF_TOL) == (2.0, 2.0, 0.02, 2.0, 0.02)
    assert (R.SUM_MIN_A, R.WIN_TOL_A) == (0.03, 2.0)
    assert (R.PLACEBO_N, R.PLACEBO_N_BOTH, R.SEED) == (400, 800, (20261005, 11))
    assert R.FP == R10.FP == "3b2e8757be7b4a74" and R.CAP == 20 and R.FAMILY_CAP == 3 and R.FAMILY_PREFIX == "卖法"
    assert R.PREV_FILES[-1] == "research_loop10.json" and R.KINDS == ("label",)


def test_route_b_and_a():
    rb = R.route_b(_cand(dcal=0.0, dwin=2.5, dmean=0.01), BASE)
    assert rb["B1"] and rb["B2"] and rb["B3"]
    assert not R.route_b(_cand(dwin=2.5, dmean=-0.01), BASE)["B1"]                    # 每笔降了
    assert not R.route_b(_cand(dwin={"Z": -2.5, "E": 5.0, "J": 5.0}), BASE)["B2"]     # 一个年代胜率降 > 2 pp
    assert not R.route_b(_cand(dcal={"Z": -0.03, "E": 0.02, "J": 0.02}, dwin=3.0), BASE)["B3"]
    ra = R.route_a(_cand(dcal=0.011, dwin=-1.9), BASE)
    assert ra["A1"] and ra["A2"] and ra["A3"] and abs(ra["sum"] - 0.033) < 1e-9
    assert not R.route_a(_cand(dcal=0.009), BASE)["A1"]                               # 合计 0.027 < 0.03
    assert not R.route_a(_cand(dcal=0.011, dwin=-2.1), BASE)["A3"]                    # 胜率降 > 2 pp
    assert not R.route_a(_cand(dcal={"Z": 0.08, "E": -0.021, "J": 0.0}), BASE)["A2"]  # 一个年代 < −0.02
    assert not R.route_a(_cand(dcal=0.02, ddd=-2.1), BASE)["A2"]                      # 回撤深 > 2 pp


def test_pool_ok_by_route():
    assert R.pool_ok({"changed": 5, "dwin": 0.1, "dmean": 0.0}, "B")
    assert not R.pool_ok({"changed": 5, "dwin": 0.0, "dmean": 0.1}, "B")
    assert R.pool_ok({"changed": 5, "dwin": -3.0, "dmean": 0.01}, "A")
    assert not R.pool_ok({"changed": 5, "dwin": 3.0, "dmean": 0.0}, "A")
    assert not R.pool_ok({"changed": 0, "dwin": 3.0, "dmean": 1.0}, "A") and not R.pool_ok(None, "B")


def test_stage1_routes_v4_v5_v6():
    good = {"W": {"changed": 9, "dwin": 1.0, "dmean": 0.2}, "Jx": {"changed": 9, "dwin": 0.5, "dmean": 0.1},
            "Zx": {"changed": 9, "dwin": -1.0, "dmean": -0.1}}
    c = _cand(dcal=0.011, dwin=2.5, dmean=0.05)
    s = R.stage1(c, BASE, good, posthoc=False)
    assert s["ok"] and s["ok_routes"] == ["A", "B"] and s["passed"] == 6
    s6 = R.stage1(c, BASE, good, posthoc=True)                                         # 事后 → Zx 反向 → 两条都不过
    assert not s6["ok"] and not s6["routes"]["A"]["V6"] and not s6["routes"]["B"]["V6"]
    bad_w = {**good, "W": {"changed": 9, "dwin": -1.0, "dmean": 0.2}}
    s4 = R.stage1(c, BASE, bad_w)                                                      # W 胜率反向 → 路线 B 的 V4 不过、路线 A 照过
    assert s4["ok_routes"] == ["A"] and not s4["routes"]["B"]["V4"]
    lens_ok = {"loeo": (c, BASE), "fwd": (c, BASE)}
    assert R.stage1(c, BASE, good, lenses=lens_ok)["ok"]
    lens_bad = {"loeo": (c, BASE), "fwd": (_cand(dwin=-3.0), BASE)}
    s5 = R.stage1(c, BASE, good, lenses=lens_bad)
    assert not s5["ok"] and not s5["routes"]["B"]["V5"]


def test_stage2_counts_and_routes():
    pl = [{"A": 0.01 * (i % 5), "B": 0.5 * (i % 7)} for i in range(400)]
    assert R.stage2({"A": 0.05, "B": 3.1}, pl, ["B"])["pass"]                          # 3.1 > 3.0
    assert not R.stage2({"A": 0.05, "B": 3.0}, pl, ["B"])["pass"]                      # 要严格大于
    assert not R.stage2({"A": 0.05, "B": 9.0}, pl, ["A", "B"])["pass"]                  # 两条都过要 800 次
    pl8 = pl + pl
    r = R.stage2({"A": 0.03, "B": 3.5}, pl8, ["A", "B"])
    assert r["pass"] and r["routes"]["B"]["pass"] and not r["routes"]["A"]["pass"]
    assert not R.stage2({"A": None, "B": 3.5}, pl, ["A"])["pass"]
    assert not R.stage2({"B": 3.5}, pl[:399] + [{"A": 0.0, "B": None}], ["B"])["pass"]
    assert R.placebo_n(["A"]) == 400 and R.placebo_n(["A", "B"]) == 800


def test_permute_labels_keeps_counts_and_is_seeded():
    lab = np.array(["low"] * 5 + ["mid"] * 3 + ["high"] * 2 + ["na"], dtype=object)
    a, b = R.permute_labels(lab, 7), R.permute_labels(lab, 7)
    assert list(a) == list(b) and sorted(a) == sorted(lab)
    assert any(list(R.permute_labels(lab, s)) != list(lab) for s in range(5))


def test_check_new_approaches_rules():
    st = {"rounds": []}
    ok = {"id": "TPC", "family": "卖法·个股以往突破的周期", "kind": "label", "posthoc": False, "verdict": R.FAIL1}
    R.check_new_approaches(st, [ok], prev={"MOM"})
    with pytest.raises(ValueError):
        R.check_new_approaches(st, [{**ok, "family": "选股·x"}], prev=set())
    with pytest.raises(ValueError):
        R.check_new_approaches(st, [{**ok, "id": "MOM"}], prev={"MOM"})
    with pytest.raises(ValueError):
        R.check_new_approaches(st, [{**ok, "id": "X6"}], prev=set())                   # 保留的名字
    with pytest.raises(ValueError):
        R.check_new_approaches(st, [{**ok, "kind": "stock"}], prev=set())
    fam = [{**ok, "id": f"Q{i}Z"} for i in range(4)]
    with pytest.raises(ValueError):
        R.check_new_approaches(st, fam, prev=set())                                    # 同一家族 4 个


def test_previous_ids_reads_loops_1_to_10(tmp_path):
    import json
    (tmp_path / "research_loop10.json").write_text(json.dumps({"rounds": [{"approaches": [{"id": "H5G", "id_in_code": "H52"}]}]}), encoding="utf-8")
    (tmp_path / "research_loop.json").write_text(json.dumps({"rounds": [{"approaches": [{"id": "UBG"}]}]}), encoding="utf-8")
    assert {"H5G", "H52", "UBG"} <= R.previous_ids(tmp_path)


def test_closest_and_status(tmp_path):
    st = {"cap": 20, "status": "running", "baseline": BASE, "success": {"n": 140, "win": 50.7, "mean": 3.25}, "rounds": [
        {"round": 1, "date": "2026-10-05", "title": "t", "approaches": [
            {"id": "AAA", "family": "卖法·a", "verdict": R.FAIL1, "dwin": 1.0, "sum": 0.01, "passed": 5},
            {"id": "BBB", "family": "卖法·b", "verdict": R.FAIL1, "dwin": 3.0, "sum": -0.1, "passed": 4},
            {"id": "CCC", "family": "卖法·c", "verdict": R.FAIL2, "dwin": 0.5, "sum": 0.0, "passed": 6}]}]}
    assert [x["id"] for x in R.closest(st)] == ["CCC", "AAA", "BBB"]
    assert "第十一个研究循环" in R.status_text(st) and R.derive_status(st) == "running"
