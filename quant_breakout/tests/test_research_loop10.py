"""第十个研究循环（scripts/research_loop10.py）：判定 V1〜V6、第二关、状态。"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_loop10 as R  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _acct(calmar, dd=-20.0, h1=0.5, h2=0.5, n=40, win=50.0, mean=3.0):
    return {"calmar": calmar, "dd": dd, "h1": h1, "h2": h2, "n": n, "win": win, "mean": mean}


BASE = {"Z": _acct(1.0, n=35, win=60.0, mean=6.0), "E": _acct(0.6, n=45, win=40.0, mean=1.0), "J": _acct(0.7, n=60, win=50.0, mean=3.0)}
GOOD_POOL = {"gone_n": 10, "n": 100, "dwin": 1.0, "dmean": 0.1}


def _cand(**over):
    c = {e: dict(v) for e, v in BASE.items()}
    for e, kv in over.items():
        c[e].update(kv)
    return c


def test_v1_needs_two_pp_pooled_and_mean_not_lower():
    up = _cand(Z={"win": 63.0}, E={"win": 42.0}, J={"win": 52.5})          # 合起来 +2.46 pp
    r = R.success_v1v2(up, BASE)
    assert r["V1"] and r["V2"] and abs(r["dwin"] - (35 * 3 + 45 * 2 + 60 * 2.5) / 140) < 1e-9
    small = _cand(J={"win": 52.0})                                            # 合起来 +0.86 pp
    assert not R.success_v1v2(small, BASE)["V1"]
    worse_mean = _cand(Z={"win": 63.0}, E={"win": 42.0}, J={"win": 52.5, "mean": 2.0})
    assert not R.success_v1v2(worse_mean, BASE)["V1"]


def test_v2_rejects_one_era_driven_gain():
    c = _cand(Z={"win": 57.5}, J={"win": 60.0})                               # Z −2.5 pp
    r = R.success_v1v2(c, BASE)
    assert r["V1"] and not r["V2"]


def test_v3_account_not_worse_rules():
    ok = _cand(Z={"calmar": 0.99}, E={"calmar": 0.61}, J={"calmar": 0.70})    # −0.01、+0.01、0 → 合计 0
    assert R.account_v3(ok, BASE)["V3"]
    assert not R.account_v3(_cand(Z={"calmar": 0.97}, E={"calmar": 0.65}), BASE)["V3"]        # Z −0.03 < −0.02
    assert not R.account_v3(_cand(Z={"calmar": 0.99}), BASE)["V3"]                             # 合计 −0.01 < 0
    assert not R.account_v3(_cand(E={"calmar": 0.62, "dd": -22.5}), BASE)["V3"]                # 回撤深 2.5 pp
    assert not R.account_v3(_cand(E={"calmar": 0.65, "h2": 0.47}), BASE)["V3"]                 # 后一半 −0.03
    assert not R.account_v3(_cand(J={"calmar": None}), BASE)["V3"]                             # 算不出 → 不过


def test_pool_ok_strict_win_and_mean():
    assert R.pool_ok(GOOD_POOL)
    assert not R.pool_ok({**GOOD_POOL, "dwin": 0.0})
    assert not R.pool_ok({**GOOD_POOL, "dmean": -0.01})
    assert not R.pool_ok({**GOOD_POOL, "gone_n": 0})
    assert not R.pool_ok(None)


def test_stage1_v6_only_for_posthoc_and_v5_lenses():
    c = _cand(Z={"win": 63.0, "calmar": 1.0}, E={"win": 42.0, "calmar": 0.6}, J={"win": 52.5, "calmar": 0.71})
    other = {"W": GOOD_POOL, "Jx": GOOD_POOL, "Zx": {**GOOD_POOL, "dwin": -1.0}}
    a = R.stage1(c, BASE, other, posthoc=False)
    assert a["ok"] and a["passed"] == 6 and a["V6"]                          # 不是事后 → V6 不适用（算过）
    b = R.stage1(c, BASE, other, posthoc=True)
    assert not b["ok"] and not b["V6"]                                       # 事后 → Zx 要同方向
    lens = R.stage1(c, BASE, other, lenses={"loeo": (c, BASE), "fwd": (BASE, BASE)})
    assert not lens["V5"]                                                    # 逐年前推那一种没过 V1
    assert not R.stage1(c, BASE, {"W": GOOD_POOL})["V4"]                      # 少一个池子 → 不过


def test_stage2_strictly_above_max_and_none_fails():
    assert R.stage2(5.0, [1.0, 4.9, -2.0])["pass"]
    assert not R.stage2(4.9, [1.0, 4.9])["pass"]
    assert not R.stage2(5.0, [1.0, None])["pass"]
    assert not R.stage2(None, [1.0])["pass"]
    s1 = {"ok": True}
    assert R.verdict(s1, {"pass": True}) == R.FOUND and R.verdict(s1, {"pass": False}) == R.FAIL2
    assert R.verdict({"ok": False}, None) == R.FAIL1


def test_seeds_are_deterministic_and_differ_from_loop9():
    import research_loop9 as R9
    a = R.random_signal_block(500, 0.2, 7)
    assert np.array_equal(a, R.random_signal_block(500, 0.2, 7))
    assert not np.array_equal(a, R9.random_signal_block(500, 0.2, 7))
    ks = R.shift_ks(1000, range(50))
    assert all(250 <= k <= 750 for k in ks) and ks == R.shift_ks(1000, range(50))
    with pytest.raises(ValueError):
        R.shift_ks(400, range(3))


def test_ids_cannot_repeat_previous_loops_and_family_cap():
    prev = R.previous_ids(ROOT / "var")
    assert {"MDD", "GPT", "FJE"} <= prev                                      # 第九个、第三个、第一个循环的 ID
    st = {"rounds": [], "status": "running", "cap": 20}
    a = {"family": "选股·测试", "posthoc": True, "kind": "date", "verdict": R.FAIL1}
    with pytest.raises(ValueError):
        R.check_new_approaches(st, [{**a, "id": "MDD"}], prev)
    with pytest.raises(ValueError):
        R.check_new_approaches(st, [{**a, "id": f"T{i}"} for i in range(4)], prev)
    with pytest.raises(ValueError):
        R.check_new_approaches(st, [{**a, "id": "TX1", "family": "核心·x"}], prev)
    st2 = R.add_round(st, {"round": 1, "approaches": [{**a, "id": "TX1", "dwin": 1.0, "sum": 0.0, "passed": 4}]}, prev)
    assert R.used(st2) == 1 and R.closest(st2)[0]["id"] == "TX1"


def test_status_text_and_prereq():
    assert "还没有登记" in R.status_text({})
    ref = {e: {"calmar": v} for e, v in (("Z", 1.194), ("E", 0.627), ("J", 0.676))}
    ok = R.prereq({e: {"calmar": ref[e]["calmar"] + 0.0004} for e in R.ERAS}, ref, R.FP)
    assert ok["ok"]
    assert not R.prereq({e: {"calmar": ref[e]["calmar"] + 0.001} for e in R.ERAS}, ref, R.FP)["ok"]
    assert not R.prereq(ref, ref, "x")["ok"]
