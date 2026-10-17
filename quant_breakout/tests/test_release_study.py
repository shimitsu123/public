"""scripts/release_study.py（压力释放预警）：压力分位只用过去、事件的 60 天冷却、命中率与对照、探索的挑选规则、判定、跨市场按段重抽。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import release_study as RS                                                   # noqa: E402


def test_constants_and_candidate_count():
    assert (RS.RUNUP_D, RS.MA_D, RS.PCT_W, RS.PCT_MIN, RS.H_FWD, RS.DROP, RS.REFRACT) == (500, 250, 2520, 1260, 60, -10.0, 60)
    assert (RS.MIN_EXPLORE_N, RS.MAX_PICK, RS.MAX_PER_FAMILY, RS.MIN_N, RS.LIFT_BASE, RS.LIFT_REF, RS.MKT_SHARE) == (10, 5, 2, 5, 10.0, 5.0, 60.0)
    assert RS.EXPLORE == {"US": ("^GSPC", "1950-01-01", "1999-12-31"), "JP": ("^N225", "1970-01-01", "1999-12-31")}
    C = RS.candidates()
    fam = pd.Series([c["family"] for c in C.values()]).value_counts().to_dict()
    assert fam == {"A": 18, "C": 18, "ref": 11, "B": 6, "D": 2}
    assert all(C[c["ref"]]["family"] == "ref" for c in C.values() if c.get("ref"))


def test_pressure_uses_only_past(monkeypatch):
    monkeypatch.setattr(RS, "PCT_W", 60)
    monkeypatch.setattr(RS, "PCT_MIN", 30)
    monkeypatch.setattr(RS, "RUNUP_D", 20)
    monkeypatch.setattr(RS, "MA_D", 10)
    days = pd.bdate_range("2000-01-03", periods=300)
    c = pd.Series(np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.01, 300))), index=days)
    P = RS.pressure(c)
    c2 = c.copy()
    c2.iloc[201:] *= 3
    assert np.allclose(RS.pressure(c2).iloc[:201].fillna(-1), P.iloc[:201].fillna(-1))
    assert P.dropna().between(0, 100).all() and P.isna().iloc[:40].all()


def test_events_refractory():
    idx = pd.bdate_range("2000-01-03", periods=200)
    cond = pd.Series(False, index=idx)
    cond.iloc[[10, 11, 12, 50, 130]] = True
    assert list(RS.events(cond)) == [idx[10], idx[130]]                     # 50 离 12 不到 60 天 → 不算新事件


def test_stats_score_pick_and_verdict():
    idx = pd.bdate_range("2000-01-03", periods=100)
    f = pd.DataFrame({"y60": [1.0] * 30 + [0.0] * 70, "y20": 0.0, "ret60": 1.0}, index=idx)
    s = RS.stats(f, idx[[0, 1, 50]])
    assert s["n"] == 3 and s["hit"] == 66.7 and s["base"] == 30.0
    C = {"A1": {"family": "A", "ref": "R1"}, "A2": {"family": "A", "ref": "R1"}, "A3": {"family": "A", "ref": "R1"},
         "D1": {"family": "D", "ref": None}, "R1": {"family": "ref"}}
    mk = lambda hit, n=12, base=30.0: {"n": n, "hit": hit, "base": base}             # noqa: E731
    res = {m: {"A1": mk(60), "A2": mk(55), "A3": mk(50), "D1": mk(45), "R1": mk(40)} for m in ("US", "JP")}
    assert RS.score(res, "A1", C) == 20.0 and RS.score(res, "D1", C) == 15.0
    assert RS.pick(res, C) == ["A1", "A2", "D1"]                             # 每类最多 2 个
    res["JP"]["A1"] = mk(60, n=9)
    assert "A1" not in RS.pick(res, C)                                       # 日本不到 10 个事件
    home = {m: {"A1": {"n": 6, "hit": 50.0, "base": 30.0}, "R1": {"n": 20, "hit": 40.0, "base": 30.0}} for m in ("US", "JP")}
    good = {"pooled": {"diff": 8.0, "lo": 1.0, "hi": 15.0}, "share": 70.0}
    assert RS.verdict(home, good, "A1", C)["label"] == "通过"
    assert RS.verdict(home, {**good, "share": 50.0}, "A1", C)["label"] == "不通过"
    home["US"]["A1"]["hit"] = 43.0                                           # 只比对照高 3 pp
    assert RS.verdict(home, good, "A1", C)["label"] == "不通过"


def test_pooled_diff_reproducible():
    rows = [{"date": f"20{i:02d}-01-10", "kind": "cand", "y": 1.0 if i % 2 else 0.0} for i in range(10)]
    rows += [{"date": f"20{i:02d}-06-10", "kind": "ref", "y": 0.0} for i in range(10)]
    a, b = RS.pooled_diff(rows, n_boot=300), RS.pooled_diff(rows, n_boot=300)
    assert a == b and a["diff"] == 50.0 and a["lo"] <= 50.0 <= a["hi"]
    assert RS.pooled_diff([])["diff"] is None
