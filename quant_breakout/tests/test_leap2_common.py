"""「选股本身的质的飞跃」的共用判定（scripts/leap2_common.py）：S1〜S5 逐项生效、缺值不算通过、扩大池的构成。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leap2_common as L  # noqa: E402

BASE = {"Z": {"win": 53.3, "mean": 0.78, "n": 45, "calmar": 0.979, "dd": -8.75},
        "E": {"win": 44.0, "mean": 0.93, "n": 68, "calmar": 0.298, "dd": -28.81},
        "J": {"win": 42.0, "mean": 0.61, "n": 81, "calmar": 0.389, "dd": -35.58}}
PQ = {w: {"win": 55.0, "mean": 1.5} for w in L.WINDOWS}


def _good():
    return {w: {"win": b["win"] + 9, "mean": b["mean"] + 1.2, "n": int(b["n"] * 0.4), "calmar": b["calmar"] - 0.01, "dd": b["dd"] - 1.0}
            for w, b in BASE.items()}


def test_passes_only_when_every_condition_holds():
    assert L.s_fails(_good(), BASE, {w: {"win": 50.0, "mean": 1.0} for w in L.WINDOWS}) == []
    for w, key, val, tag in (("Z", "win", 61.0, "S1 Z"), ("E", "mean", 1.9, "S2 E"), ("J", "n", 24, "S3 J"),
                             ("E", "calmar", 0.277, "S4 E Calmar"), ("J", "dd", -37.7, "S4 J 回撤")):
        c = _good()
        c[w][key] = val
        f = L.s_fails(c, BASE, {x: {"win": 50.0, "mean": 1.0} for x in L.WINDOWS})
        assert any(x.startswith(tag) for x in f), (tag, f)
    f = L.s_fails(_good(), BASE, {**{w: {"win": 50.0, "mean": 1.0} for w in L.WINDOWS}, "Z": {"win": 63.0, "mean": 1.0}})
    assert any(x.startswith("S5 Z 胜率") for x in f) and not any(x.startswith("S5 Z 每笔") for x in f)
    f = L.s_fails(_good(), BASE, {**{w: {"win": 50.0, "mean": 1.0} for w in L.WINDOWS}, "J": {"win": 40.0, "mean": 1.9}})
    assert any(x.startswith("S5 J 每笔") for x in f)


def test_missing_values_fail():
    c = _good()
    c["E"]["win"] = None
    assert any(x.startswith("S1 E") for x in L.s_fails(c, BASE, PQ))
    assert any(x.startswith("S5 Z") for x in L.s_fails(_good(), BASE, {}))


def test_improve_is_weaker_than_leap():
    c = {w: {"win": b["win"] + 4.5, "mean": b["mean"] + 0.6, "n": int(b["n"] * 0.5), "calmar": b["calmar"], "dd": b["dd"]} for w, b in BASE.items()}
    assert L.improve_fails(c, BASE) == [] and L.s_fails(c, BASE, PQ)
    c["Z"]["calmar"] = 0.9
    assert L.improve_fails(c, BASE) == ["Z 组合变差"]


def test_uw_names_is_n225_plus_t500x():
    from qbreak import wide_universe as WU
    from qbreak.config import universe
    fp = Path(__file__).resolve().parents[1] / "var" / WU.FILE                    # 测试在临时 QBREAK_HOME 下 → 直接读仓库里冻结的那份
    n = L.uw_names(fp)
    n225 = list(universe("JP", "broad"))
    assert n[:len(n225)] == n225 and len(set(n)) == len(n)
    assert set(n) - set(n225) == set(WU.tickers(WU.load(fp), "T500x")) - set(n225) and len(n) > 400
