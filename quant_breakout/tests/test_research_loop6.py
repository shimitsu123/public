"""第六个研究循环（scripts/research_loop6.py，2026-10-03 登记）：判定的数字同第二〜五个循环、家族必须是「核心」、第一〜五个循环的 ID 不能再用、
三种第二关的随机对照（信号平移 / 资产收益平移 / 组合按成分各自平移，种子固定）、状态文件只写一次、命令行只读。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_loop as RL  # noqa: E402
import research_loop2 as R2  # noqa: E402
import research_loop3 as R3  # noqa: E402
import research_loop5 as R5  # noqa: E402
import research_loop6 as R6  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_registered_constants_same_as_loop5():
    assert (R6.CAP, R6.SUM_MIN, R6.ERA_TOL, R6.DD_TOL, R6.PLACEBO_N, R6.REPRO_TOL) == (R5.CAP, R5.SUM_MIN, R5.ERA_TOL, R5.DD_TOL, R5.PLACEBO_N, R5.REPRO_TOL)
    assert (R6.CAP, R6.SUM_MIN, R6.ERA_TOL, R6.DD_TOL, R6.PLACEBO_N) == (20, 0.03, 0.02, 2.0, 400)
    assert (R6.FOUND, R6.FAIL1, R6.FAIL2) == (RL.FOUND, RL.FAIL1, RL.FAIL2)
    assert (R6.STATE_FILE, R6.FAMILY_CAP, R6.BANNED, R6.KINDS) == ("research_loop6.json", 3, R2.BANNED, ("signal", "asset", "combo"))
    assert (R6.FAMILY_PREFIX, R6.LOOP_SEED, R6.SHIFT_GAP, R6.SHIFT_FROM, R6.PREREQ_TOL) == ("核心", 20261006, 250, "2000-01-04", 0.0005)
    assert R6.stage1 is R2.stage1 and R6.stage2 is RL.stage2 and R6.verdict is RL.verdict and R6.asset_shift is R3.asset_shift
    assert R6.PREV_FILES == R5.PREV_FILES + ("research_loop5.json",)


def test_previous_ids_cover_loops_1_to_5():
    prev = R6.previous_ids(ROOT / "var")
    assert {"FJE", "NDRH", "VTU", "NVU", "TBJ", "TBU", "BAU", "ZSP", "RGX", "DVS", "WVS"} <= prev


def _st():
    return {"status": "running", "cap": 20, "rounds": []}


def test_check_new_approaches_rules():
    ok = {"id": "NEW1", "family": "核心·熊市避险资产", "posthoc": True, "kind": "asset"}
    R6.check_new_approaches(_st(), [ok], prev=set())
    with pytest.raises(ValueError):
        R6.check_new_approaches(_st(), [{**ok, "family": "仓位·量能"}], prev=set())              # 只做核心层
    with pytest.raises(ValueError):
        R6.check_new_approaches(_st(), [{**ok, "kind": "size_trade"}], prev=set())              # 第二关的类别
    with pytest.raises(ValueError):
        R6.check_new_approaches(_st(), [{**ok, "id": "TBJ"}], prev={"TBJ"})                     # 以前的 ID
    with pytest.raises(ValueError):
        R6.check_new_approaches(_st(), [{**ok, "posthoc": None}], prev=set())                   # 事后组合要标明
    with pytest.raises(ValueError):
        R6.check_new_approaches(_st(), [{**ok, "family": "汇率对冲"}], prev=set())               # 不再加的家族（也不是「核心」开头）
    with pytest.raises(ValueError):
        R6.check_new_approaches(_st(), [{**ok, "id": f"N{i}"} for i in range(4)], prev=set())   # 同一家族最多 3 个


def test_shift_ks_reproducible_and_in_range():
    a, b = R6.shift_ks(1000, 0, seeds=range(50)), R6.shift_ks(1000, 0, seeds=range(50))
    assert a == b and all(250 <= k <= 750 for k in a) and len(set(a)) > 10
    assert R6.shift_ks(1000, 1, seeds=range(50)) != a                                         # signal / asset 的种子不同
    assert a[0] == int(np.random.default_rng([20261006, 0, 0]).integers(250, 751))
    with pytest.raises(ValueError):
        R6.shift_ks(500, 0)


def test_combo_ks():
    c = R6.combo_ks(1000, 3, seeds=range(20))
    assert len(c) == 20 and all(len(x) == 3 and all(250 <= k <= 750 for k in x) for x in c) and c == R6.combo_ks(1000, 3, seeds=range(20))
    g = np.random.default_rng([20261006, 2, 0])
    assert c[0] == [int(g.integers(250, 751)) for _ in range(3)]


def test_shift_signal_and_asset_shift():
    d = pd.bdate_range("2020-01-01", periods=10)
    s = pd.Series([True, False, False, True, False, False, False, False, False, False], index=d)
    t = R6.shift_signal(s, 2)
    assert t.index.equals(d) and t.tolist() == [False, False, True, False, False, True, False, False, False, False]
    c = pd.Series(100 * np.cumprod(1 + np.linspace(-0.02, 0.03, 10)), index=d)
    x = R6.asset_shift(c, 3)
    assert x.index.equals(c.index) and x.iloc[-1] == pytest.approx(c.iloc[-1])                # 参考日（最后一天）的水平不变
    r, rx = c.pct_change().fillna(0).to_numpy(), x.pct_change().fillna(0).to_numpy()
    assert rx[4:] == pytest.approx(np.roll(r, 3)[4:])


def test_status_and_init_state(tmp_path):
    assert "还没有登记" in R6.status_text({})
    res = {"baseline": {"Z": {"calmar": 0.979, "dd": -14.71}}, "prereq_ok": True, "fingerprint": "x"}
    st = R6.init_state(res, home=tmp_path)
    assert st["status"] == "running" and st["kinds"] == ["signal", "asset", "combo"] and st["family_prefix"] == "核心"
    st2 = R6.init_state({"baseline": {}, "prereq_ok": False, "fingerprint": "y"}, home=tmp_path)    # 已存在就不动
    assert st2["fingerprint"] == "x"


def test_registered_state_if_present():
    st = R6.load_state(ROOT / "var")
    if not st:
        pytest.skip("第六个研究循环还没有登记")
    assert st["prereq_ok"] is True and st["cap"] == 20 and st["family_prefix"] == "核心"
    b5 = R5.load_state(ROOT / "var").get("baseline") or {}
    assert all(abs(st["baseline"][e]["calmar"] - b5[e]["calmar"]) <= R6.PREREQ_TOL for e in R6.ERAS)


def test_status_after_adoption(monkeypatch):
    st = {"start": "2026-10-03", "baseline": {}, "fingerprint": "aaa", "rounds": [], "cap": R6.CAP,
          "adopted": {"date": "2026-10-03", "candidate": "BCU", "change": "Q1H → Q1HB", "fingerprint_after": "bbb"}}
    monkeypatch.setattr(R6, "rules_fingerprint", lambda home=None: "bbb")
    monkeypatch.setattr(R2, "rules_fingerprint", lambda home=None: "bbb")
    t = R6.status_text(st)
    assert "采用：2026-10-03 用户「采用」BCU" in t and "已按「采用」改过" in t and "★" not in t
    monkeypatch.setattr(R6, "rules_fingerprint", lambda home=None: "ccc")
    monkeypatch.setattr(R2, "rules_fingerprint", lambda home=None: "ccc")
    assert "★ 与登记时不同" in R6.status_text(st)                                           # 采用之后又改了别的 → 照旧提示


def test_cli_status_is_read_only():
    assert R6.main(["--status"]) == 0


def _seg_state():
    r1 = {"round": 1, "date": "2026-10-03", "title": "t", "approaches": [
        {"id": "BCU", "family": "核心·熊市避险资产", "posthoc": True, "kind": "asset", "verdict": R6.FOUND, "sum": 0.25},
        {"id": "BCJ", "family": "核心·熊市避险资产", "posthoc": True, "kind": "asset", "verdict": R6.FAIL1, "sum": 0.01}]}
    return {"status": "found", "cap": 20, "rounds": [r1], "start": "2026-10-03", "fingerprint": "aaa",
            "adopted": {"date": "2026-10-03", "candidate": "BCU", "fingerprint_after": "bbb"},
            "segments": [{"seg": 2, "from_round": 2, "start": "2026-10-03", "registered": "x",
                          "baseline": {"Z": {"calmar": 1.162, "dd": -14.76}}, "fingerprint": "bbb", "cap": 20, "status": "running"}]}


def test_segment2_view_counts_and_ids():
    """第二段（用户「采用 并且继续」）：计数与家族用量从这一段重新算、轮次号接着编、第一段的 ID 不能再用、找到 → 这一段停。"""
    st = _seg_state()
    v = R6.view(st)
    assert v["rounds"] == [] and R6.used(v) == 0 and R6.left(v) == 20 and R6.derive_status(v) == "running"
    assert R6.earlier_ids(st) == {"BCU", "BCJ"} and R6.view({"rounds": []}) == {"rounds": []}
    ok = {"id": "NEW1", "family": "核心·熊市避险资产", "posthoc": True, "kind": "signal"}
    R6.check_new_approaches(st, [ok, {**ok, "id": "NEW2"}, {**ok, "id": "NEW3"}], prev=set())
    with pytest.raises(ValueError):
        R6.check_new_approaches(st, [{**ok, "id": "BCU"}], prev=set())
    rnd = {"round": 2, "date": "2026-10-04", "title": "t2", "approaches": [{**ok, "verdict": R6.FAIL1, "sum": -0.1}]}
    st2 = R6.add_round(st, rnd, prev=set())
    assert len(st2["rounds"]) == 2 and R6.used(R6.view(st2)) == 1 and st2["segments"][-1]["status"] == "running"
    with pytest.raises(ValueError):
        R6.add_round(st, {**rnd, "round": 3}, prev=set())
    found = R6.add_round(st, {**rnd, "approaches": [{**ok, "verdict": R6.FOUND, "sum": 0.3}]}, prev=set())
    assert found["status"] == "found" and found["segments"][-1]["status"] == "found"
    with pytest.raises(ValueError):
        R6.add_round(found, {**rnd, "round": 3, "approaches": [{**ok, "id": "NEW9", "verdict": R6.FAIL1}]}, prev=set())


def test_segment2_status_text(monkeypatch):
    st = _seg_state()
    monkeypatch.setattr(R6, "rules_fingerprint", lambda home=None: "bbb")
    t = R6.status_text(st)
    assert "第二段" in t and "做法 0 / 20" in t and "与第二段登记时相同" in t and "BCU 更好候选" in t
    monkeypatch.setattr(R6, "rules_fingerprint", lambda home=None: "ccc")
    assert "★ 与第二段登记时不同" in R6.status_text(st)


def test_init_segment2_once(tmp_path):
    st0 = {k: v for k, v in _seg_state().items() if k != "segments"}
    R6.save_state(st0, tmp_path)
    res = {"baseline": {"Z": {"calmar": 1.162}}, "prereq_ok": True, "fingerprint": "bbb"}
    st = R6.init_segment2(res, home=tmp_path)
    assert st["status"] == "running" and R6.segment(st)["from_round"] == 2 and R6.segment(st)["fingerprint"] == "bbb"
    st2 = R6.init_segment2({**res, "fingerprint": "zzz"}, home=tmp_path)                       # 已有第二段就不动
    assert len(st2["segments"]) == 1 and R6.segment(st2)["fingerprint"] == "bbb"


def test_b2_reference_and_common_wiring():
    import inspect
    import json
    import loop6_common as L6
    assert R6.B2_REF == {"Z": 1.162, "E": 0.808, "J": 0.749} and R6.SEG2_FROM == 2
    src = inspect.getsource(L6.bcu_over)
    assert "T.inputs(W)" in src and 'T2.tbh_over(W["bear"]["US"], M["on_b"], M["fb"])' in src
    assert 'W["b1"] = merge_over(W["b1"], ov)' in inspect.getsource(L6.load) and L6.run is L6.L2.run
    r1 = json.loads((ROOT / "var" / "out" / "loop6_r01_bondcorr.json").read_text(encoding="utf-8"))
    assert {e: r1["cand"]["BCU"][e]["calmar"] for e in R6.ERAS} == R6.B2_REF                 # 第 1 轮 BCU 的第一关账户


def test_registered_segment2_if_present():
    st = R6.load_state(ROOT / "var")
    sg = R6.segment(st)
    if not sg:
        pytest.skip("第二段还没有登记")
    assert sg["prereq_ok"] is True and sg["from_round"] == 2 and sg["cap"] == 20
    assert sg["fingerprint"] == (st.get("adopted") or {}).get("fingerprint_after")
    assert all(abs(sg["baseline"][e]["calmar"] - R6.B2_REF[e]) <= R6.PREREQ_TOL for e in R6.ERAS)
