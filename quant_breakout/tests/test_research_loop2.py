"""第二个研究循环（scripts/research_loop2.py、scripts/loop2_common.py，2026-10-02 登记）：登记值、S7 事后组合、家族上限、状态、B1 的接法。"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_common as L2  # noqa: E402
import research_loop as RL  # noqa: E402
import research_loop2 as R2  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _acct(cal, dd=-20.0):
    return {e: {"calmar": c, "dd": dd, "h1": c, "h2": c} for e, c in zip(R2.ERAS, cal)}


def test_registered_constants_same_as_loop1_plus_loop2_rules():
    assert (R2.CAP, R2.SUM_MIN, R2.ERA_TOL, R2.DD_TOL, R2.PLACEBO_N) == (20, 0.03, 0.02, 2.0, 400)
    assert (R2.FOUND, R2.FAIL1, R2.FAIL2) == (RL.FOUND, RL.FAIL1, RL.FAIL2)
    assert (R2.STATE_FILE, R2.FAMILY_CAP, R2.BANNED) == ("research_loop2.json", 3, ("汇率对冲",))
    assert R2.B0_REG == {"Z": 0.949, "E": 0.566, "J": 0.660} and R2.B1_REF == {"Z": 0.979, "E": 0.749, "J": 0.741}
    assert L2.J_END == "2026-09-30" and L2.MERGE_KEYS == ("cfg_over", "extra_core", "extra_bear")


def test_stage1_adds_posthoc_s7():
    base, cand = _acct([0.98, 0.75, 0.74]), _acct([1.00, 0.77, 0.76])
    r = R2.stage1(cand, base)
    assert r["ok"] and r["S7"] and not r["posthoc"]["applies"]                            # 不是事后组合 = 不适用
    assert R2.stage1(cand, base, posthoc=0.01)["ok"]
    for bad in (0.0, -0.01, float("nan")):
        r = R2.stage1(cand, base, posthoc=bad)
        assert not r["S7"] and not r["ok"] and r["posthoc"]["applies"]                    # 没看过的数据上不同方向 / 算不出 = 不过
    assert not R2.stage1(_acct([0.98, 0.76, 0.75]), base, posthoc=0.5)["ok"]              # S1 不过时 S7 救不了


def _rnd(k, items):
    return {"round": k, "date": "2026-10-02", "title": f"第 {k} 轮",
            "approaches": [{"id": f"A{k}{i}", "verdict": v, "sum": 0.01, "family": f, "posthoc": p} for i, (v, f, p) in enumerate(items)]}


def test_family_cap_banned_and_posthoc_flag():
    st = {"cap": 20, "status": "running", "rounds": []}
    st = R2.add_round(st, _rnd(1, [(R2.FAIL1, "离场", False), (R2.FAIL1, "离场", False)]))
    st = R2.add_round(st, _rnd(2, [(R2.FAIL2, "离场", True)]))
    assert R2.family_counts(st) == {"离场": 3} and R2.used(st) == 3
    with pytest.raises(ValueError):
        R2.add_round(st, _rnd(3, [(R2.FAIL1, "离场", False)]))                             # 第 4 个同一家族
    with pytest.raises(ValueError):
        R2.add_round(st, _rnd(3, [(R2.FAIL1, "汇率对冲", False)]))                          # 不再加的家族
    with pytest.raises(ValueError):
        R2.add_round(st, _rnd(3, [(R2.FAIL1, "", False)]))                                  # 没写家族
    with pytest.raises(ValueError):
        R2.add_round(st, {"round": 3, "approaches": [{"id": "x", "verdict": R2.FAIL1, "family": "仓位"}]})   # 没标 posthoc
    with pytest.raises(ValueError):
        R2.add_round(st, _rnd(4, [(R2.FAIL1, "仓位", False)]))                              # 轮次号要接着来（第一个循环的规则）
    st = R2.add_round(st, _rnd(3, [(R2.FAIL1, "仓位", False)]))
    assert "家族用量" in R2.status_text({**st, "start": "2026-10-02", "baseline": {}}) and "离场 3" in R2.status_text(st)


def test_closest_ranks_stage2_then_passed_then_sum():
    st = {"rounds": [{"round": 1, "approaches": [{"id": "a", "verdict": R2.FAIL1, "sum": 0.10, "passed": 4},
                                                 {"id": "b", "verdict": R2.FAIL2, "sum": 0.05, "passed": 7},
                                                 {"id": "c", "verdict": R2.FAIL1, "sum": 0.20, "passed": 5},
                                                 {"id": "d", "verdict": R2.FAIL1, "sum": -0.3, "passed": 5}]}]}
    assert [x["id"] for x in R2.closest(st)] == ["b", "c", "d"]


def test_merge_over_keeps_b1_core_and_adds_candidate():
    b1 = {"cfg_over": {"core": {"1545.T": 1.0, "2845.T": 1.0}, "core_mode": "follow"}, "extra_core": {"1545.T": 1, "2845.T": 2},
          "extra_bear": {"US_UH": 1, "US_HG": 2}}
    m = L2.merge_over(b1, {"cfg_over": {"max_positions": 3}, "extra_bear": {"X": 9}, "em_scale": "s"})
    assert m["cfg_over"] == {"core": {"1545.T": 1.0, "2845.T": 1.0}, "core_mode": "follow", "max_positions": 3}
    assert m["extra_bear"] == {"US_UH": 1, "US_HG": 2, "X": 9} and m["extra_core"] == b1["extra_core"] and m["em_scale"] == "s"
    m2 = L2.merge_over(b1, {"cfg_over": {"core_mode": "split"}})
    assert m2["cfg_over"]["core_mode"] == "split" and b1["cfg_over"]["core_mode"] == "follow"                # 原来的不改


def test_b1_over_is_round15_wiring():
    import loop_r15_fxeunion as U
    fr = pd.DataFrame({"Close": [1.0]}, index=[pd.Timestamp("2020-01-06")])
    s = pd.Series([True], index=[pd.Timestamp("2020-01-06")])
    W = {"kw": {"Z": {"extra_core": {"1545.T": fr}}}, "bear": {"US": ~s}, "inp": {}}
    got = U.fje_over(W, s, fr)
    assert got["cfg_over"]["core_mode"] == "follow" and set(got["extra_core"]) == {"1545.T", "2845.T"}


def test_registered_state_file_is_consistent():
    st = R2.load_state(ROOT / "var")
    if not st:
        pytest.skip("第二个研究循环还没有登记")
    assert st["cap"] == R2.CAP and st["family_cap"] == R2.FAMILY_CAP and st["banned_families"] == list(R2.BANNED)
    assert st["prereq_ok"] and set(st["baseline"]) >= set(R2.ERAS) and R2.used(st) <= R2.CAP
    assert [r["round"] for r in st.get("rounds") or []] == list(range(1, len(st.get("rounds") or []) + 1))
    assert all(a.get("family") and isinstance(a.get("posthoc"), bool) for r in st.get("rounds") or [] for a in r["approaches"])
    fc = R2.family_counts(st)
    assert all(v <= R2.FAMILY_CAP for v in fc.values()) and not any(k in R2.BANNED for k in fc)
