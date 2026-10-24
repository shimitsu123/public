"""「质的飞跃」循环的共用判定（scripts/leap_common.py）：各条件逐项生效、探索不准碰 Z 年代。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leap_common as L  # noqa: E402


def _w(calmar, dd=-30.0, halves=(0.3, 0.3), mean=0.8, win=44.0, n=100):
    return {"calmar": calmar, "dd": dd, "halves": list(halves), "mean": mean, "win": win, "n": n}


def _all(**kw):
    return {w: _w(**kw) for w in ("Z", "E", "J")}


def test_leap_passes_only_when_every_condition_holds():
    base, core = _all(calmar=0.30), _all(calmar=0.25)
    good = {"Z": _w(0.36, halves=(0.31, 0.31), mean=1.4, win=46, n=60), "E": _w(0.41, halves=(0.31, 0.31), mean=1.4, win=46, n=60),
            "J": _w(0.41, halves=(0.31, 0.31), mean=1.4, win=46, n=60)}
    pq = {"Z": 0.33, "E": 0.33, "J": 0.33}
    assert L.leap_fails(good, base, core, pq) == []
    bad = {**good, "E": _w(0.39, halves=(0.31, 0.31), mean=1.4, win=46, n=60)}          # E 只高 0.09
    assert any(f.startswith("L1 E Calmar") for f in L.leap_fails(bad, base, core, pq))
    few = {**good, "J": _w(0.41, halves=(0.31, 0.31), mean=1.4, win=46, n=49)}          # 笔数不到一半
    assert any(f.startswith("L3 J 笔数") for f in L.leap_fails(few, base, core, pq))
    lowwin = {**good, "Z": _w(0.36, halves=(0.31, 0.31), mean=1.4, win=43.9, n=60)}
    assert any(f.startswith("L3 Z 胜率") for f in L.leap_fails(lowwin, base, core, pq))
    half = {**good, "Z": _w(0.36, halves=(0.29, 0.31), mean=1.4, win=46, n=60)}
    assert any("半段1" in f for f in L.leap_fails(half, base, core, pq))
    deep = {**good, "E": _w(0.41, dd=-32.5, halves=(0.31, 0.31), mean=1.4, win=46, n=60)}
    assert any("回撤" in f for f in L.leap_fails(deep, base, core, pq))
    assert any(f.startswith("L2") for f in L.leap_fails(good, base, _all(calmar=0.40), pq))
    assert any(f.startswith("L4") for f in L.leap_fails(good, base, core, {**pq, "J": 0.45}))
    assert any(f.startswith("L1 Z") for f in L.leap_fails(good, base, core, pq) + L.leap_fails({**good, "Z": _w(0.34)}, base, core, pq))


def test_missing_values_fail_instead_of_passing():
    base, core = _all(calmar=0.30), _all(calmar=0.25)
    c = {"Z": _w(None), "E": _w(0.5), "J": _w(0.5)}
    assert any(f.startswith("L1 Z Calmar") for f in L.leap_fails(c, base, core, {"Z": 0.1, "E": 0.1, "J": 0.1}))


def test_normal_improvement_rule():
    base = _all(calmar=0.30)
    assert L.normal_fails({"Z": _w(0.30), "E": _w(0.35), "J": _w(0.30)}, base, {"E": 0.34}) == []
    assert L.normal_fails({"Z": _w(0.29), "E": _w(0.35), "J": _w(0.30)}, base, {"E": 0.34}) == ["Z Calmar 比现行差"]


def test_explore_guard_blocks_z_era():
    L.assert_explore_dates(["2006-10-02", "2020-01-06"])
    with pytest.raises(ValueError):
        L.assert_explore_dates(["2006-09-29", "2020-01-06"])
