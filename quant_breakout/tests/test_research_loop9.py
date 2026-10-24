"""第九个研究循环（选股成功率）的判定与状态（scripts/research_loop9.py；事先写定的纯函数）。"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_loop9 as R9  # noqa: E402


def _acct(cz, ce, cj, dd=-20.0, h=(0.5, 0.5), n=(30, 40, 60), win=(60.0, 40.0, 50.0), mean=(5.0, 1.0, 3.0)):
    out = {}
    for k, (e, c) in enumerate(zip(R9.ERAS, (cz, ce, cj))):
        out[e] = {"calmar": c, "dd": dd, "h1": h[0], "h2": h[1], "n": n[k], "win": win[k], "mean": mean[k]}
    return out


def test_pooled_trades_weights_by_count():
    p = R9.pooled_trades(_acct(1, 1, 1, n=(10, 30, 60), win=(70.0, 40.0, 50.0), mean=(6.0, 1.0, 2.0)))
    assert p["n"] == 100
    assert abs(p["win"] - (700 + 1200 + 3000) / 100) < 1e-9
    assert abs(p["mean"] - (60 + 30 + 120) / 100) < 1e-9
    assert R9.pooled_trades({e: {"n": 0} for e in R9.ERAS}) == {"n": 0, "win": None, "mean": None}


def test_success_check_needs_both_win_and_mean_not_lower():
    base = _acct(1, 1, 1)
    better = _acct(1, 1, 1, win=(61.0, 41.0, 51.0), mean=(5.1, 1.1, 3.1))
    worse_mean = _acct(1, 1, 1, win=(61.0, 41.0, 51.0), mean=(4.0, 1.0, 3.0))
    assert R9.success_check(better, base)["S8"]
    assert not R9.success_check(worse_mean, base)["S8"]
    assert R9.success_check(base, base)["S8"]                              # 不变 = 不降
    bad = _acct(1, 1, 1)
    bad["J"]["win"] = None
    assert not R9.success_check(bad, base)["S8"]


def test_stage1_adds_s8_to_loop2_checks():
    base = _acct(1.0, 0.6, 0.7)
    up = _acct(1.02, 0.62, 0.72, win=(61.0, 41.0, 51.0), mean=(5.1, 1.1, 3.1))
    r = R9.stage1(up, base)
    assert r["S1"] and r["S8"] and r["ok"] and r["passed"] == 8
    lower_win = _acct(1.02, 0.62, 0.72, win=(59.0, 40.0, 50.0))
    r2 = R9.stage1(lower_win, base)
    assert r2["S1"] and not r2["S8"] and not r2["ok"] and r2["passed"] == 7


def test_random_signal_block_is_seeded_and_uses_loop9_seed():
    a, b = R9.random_signal_block(500, 0.3, 7), R9.random_signal_block(500, 0.3, 7)
    assert np.array_equal(a, b)
    assert 0.2 < a.mean() < 0.4
    assert not np.array_equal(a, R9.random_signal_block(500, 0.3, 8))
    assert np.array_equal(a, np.random.default_rng([20261004, 7]).random(500) < 0.3)


def test_prereq_requires_fingerprint_and_b3():
    ref = {e: {"calmar": v} for e, v in zip(R9.ERAS, (1.194, 0.627, 0.676))}
    same = {e: {"calmar": v + 0.0004} for e, v in zip(R9.ERAS, (1.194, 0.627, 0.676))}
    assert R9.prereq(same, ref, R9.FP)["ok"]
    assert not R9.prereq(same, ref, "x" * 16)["ok"]
    off = dict(same)
    off["E"] = {"calmar": 0.6290}
    assert not R9.prereq(off, ref, R9.FP)["ok"]


def _a(i, fam="选股·测试", verdict=R9.FAIL1, kind="stock", posthoc=False):
    return {"id": i, "family": fam, "verdict": verdict, "kind": kind, "posthoc": posthoc}


def test_add_round_checks(tmp_path):
    st = {"cap": 20, "status": "running", "rounds": []}
    st = R9.add_round(st, {"round": 1, "approaches": [_a("AA1"), _a("AA2")]}, prev=set())
    assert R9.used(st) == 2
    with pytest.raises(ValueError):                                          # 轮次号要接着来
        R9.add_round(st, {"round": 3, "approaches": [_a("AA3")]}, prev=set())
    with pytest.raises(ValueError):                                          # 家族要以「选股」开头
        R9.add_round(st, {"round": 2, "approaches": [_a("AA3", fam="核心·测试")]}, prev=set())
    with pytest.raises(ValueError):                                          # 同一家族 ≤ 3
        R9.add_round(st, {"round": 2, "approaches": [_a("AA3"), _a("AA4")]}, prev=set())
    with pytest.raises(ValueError):                                          # ID 不重用（以前的循环）
        R9.add_round(st, {"round": 2, "approaches": [_a("VRN", fam="选股·别的")]}, prev={"VRN"})
    with pytest.raises(ValueError):                                          # ID 不重用（本循环）
        R9.add_round(st, {"round": 2, "approaches": [_a("AA1", fam="选股·别的")]}, prev=set())
    with pytest.raises(ValueError):                                          # 第二关类别要写
        R9.add_round(st, {"round": 2, "approaches": [_a("AA5", fam="选股·别的", kind="asset")]}, prev=set())
    with pytest.raises(ValueError):                                          # 事后要写明
        R9.add_round(st, {"round": 2, "approaches": [{**_a("AA5", fam="选股·别的"), "posthoc": None}]}, prev=set())
    st2 = R9.add_round(st, {"round": 2, "approaches": [_a("AA5", fam="选股·别的", verdict=R9.FOUND)]}, prev=set())
    assert R9.derive_status(st2) == "found"
    with pytest.raises(ValueError):                                          # 找到之后不能再加
        R9.add_round(st2, {"round": 3, "approaches": [_a("AA6", fam="选股·再别的")]}, prev=set())


def test_previous_ids_reads_loops_1_to_8(tmp_path):
    (tmp_path / "research_loop.json").write_text(json.dumps({"rounds": [{"approaches": [{"id": "VT20"}]}]}), encoding="utf-8")
    (tmp_path / "research_loop8.json").write_text(json.dumps({"rounds": [{"approaches": [{"id": "SSR"}]}]}), encoding="utf-8")
    assert R9.previous_ids(tmp_path) == {"VT20", "SSR"}


def test_real_previous_ids_cover_known_approaches():
    ids = R9.previous_ids(Path(__file__).resolve().parents[1] / "var")
    for i in ("FJE", "TPX", "RMO", "FBM", "SSN", "BCU", "VSX", "SSR"):
        assert i in ids


def test_init_state_refuses_without_prereq(tmp_path):
    res = {"prereq_ok": False, "prereq": {"fingerprint": R9.FP}, "baseline": {}, "success": {}}
    with pytest.raises(ValueError):
        R9.init_state(res, home=tmp_path)
    assert not (tmp_path / R9.STATE_FILE).exists()
    ok = {**res, "prereq_ok": True}
    st = R9.init_state(ok, home=tmp_path)
    assert st["status"] == "running" and st["cap"] == 20 and st["rounds"] == []
    assert R9.init_state({**ok, "baseline": {"x": 1}}, home=tmp_path)["baseline"] == {}   # 已存在就不动


def test_closest_orders_by_stage_then_checks_then_sum():
    st = {"rounds": [{"round": 1, "approaches": [
        {"id": "A", "verdict": R9.FAIL1, "passed": 7, "sum": 0.10},
        {"id": "B", "verdict": R9.FAIL2, "passed": 8, "sum": 0.05},
        {"id": "C", "verdict": R9.FAIL1, "passed": 7, "sum": 0.20},
        {"id": "D", "verdict": R9.FAIL1, "passed": 5, "sum": 0.50}]}]}
    assert [x["id"] for x in R9.closest(st)] == ["B", "C", "A"]


def test_shift_ks_range_and_seed():
    ks = R9.shift_ks(1000, range(50))
    assert all(250 <= k <= 750 for k in ks)
    assert ks == R9.shift_ks(1000, range(50))
    assert ks[3] == int(np.random.default_rng([20261004, 3]).integers(250, 751))
    with pytest.raises(ValueError):
        R9.shift_ks(400)


def test_shift_days_is_circular():
    on = np.array([True, False, False, False])
    assert list(R9.shift_days(on, 1)) == [False, True, False, False]
    assert list(R9.shift_days(on, 4)) == list(on)


def test_gate_from_days_maps_signal_dates():
    import pandas as pd
    import loop9_common as C9
    days = pd.bdate_range("2020-01-06", periods=5)
    S = pd.DataFrame({"ticker": ["A", "B", "C"], "date": [days[1], days[3], pd.Timestamp("2020-02-01")]})
    g = C9.gate_from_days(S, days, [False, True, False, False, False])
    assert list(g) == [True, False, False]                                   # 不在交易日里的信号日不挡
