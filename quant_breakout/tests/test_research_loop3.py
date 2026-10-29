"""第三个研究循环（scripts/research_loop3.py，2026-10-02 登记）：登记值、第一关同第二个循环、第二关的类别、资产置换类的随机平移、
以前的 ID 不能再用、家族上限、状态文件。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_loop as RL  # noqa: E402
import research_loop2 as R2  # noqa: E402
import research_loop3 as R3  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_registered_constants():
    assert (R3.CAP, R3.SUM_MIN, R3.ERA_TOL, R3.DD_TOL, R3.PLACEBO_N) == (20, 0.03, 0.02, 2.0, 400)
    assert (R3.FOUND, R3.FAIL1, R3.FAIL2) == (RL.FOUND, RL.FAIL1, RL.FAIL2)
    assert (R3.STATE_FILE, R3.FAMILY_CAP, R3.BANNED, R3.KINDS) == ("research_loop3.json", 3, ("汇率对冲",), ("signal", "asset", "stock"))
    assert (R3.SHIFT_GAP, R3.ASSET_SEED, R3.PREREQ_TOL) == (250, 20261003, 0.0005)
    assert R3.stage1 is R2.stage1 and R3.stage2 is RL.stage2


def test_shift_ks_deterministic_and_in_range():
    ks = R3.shift_ks(6000)
    assert len(ks) == 400 and ks == R3.shift_ks(6000) and all(250 <= k <= 5750 for k in ks)
    assert ks[:3] == [int(np.random.default_rng([20261003, s]).integers(250, 5751)) for s in range(3)]
    assert len(set(ks)) > 300
    with pytest.raises(ValueError):
        R3.shift_ks(500)


def test_asset_shift_rolls_returns_and_keeps_level():
    idx = pd.bdate_range("2020-01-01", periods=6)
    c = pd.Series([100.0, 110.0, 99.0, 99.0, 108.9, 108.9], index=idx)      # 收益 +10%、−10%、0、+10%、0
    s = R3.asset_shift(c, 1)
    r = s.pct_change().fillna(0.0).round(10).tolist()
    assert r == [0.0, 0.0, 0.1, -0.1, 0.0, 0.1]                               # 往后挪一天；第一天的收益当 0
    assert s.iloc[-1] == pytest.approx(108.9)                                 # 缺省：最后一天的价格水平不变
    s2 = R3.asset_shift(c, 2, ref_date=idx[2])
    assert s2.loc[idx[2]] == pytest.approx(99.0)
    assert R3.asset_shift(c, 0).round(8).tolist() == c.tolist()              # 不挪 = 原样
    assert R3.asset_shift(c, 3).pct_change().fillna(0.0).round(10).tolist() == [0.0, 0.1, 0.0, 0.0, 0.1, -0.1]


def _rnd(k, items):
    return {"round": k, "date": "2026-10-02", "title": f"第 {k} 轮",
            "approaches": [{"id": f"Q{k}{i}", "verdict": v, "sum": 0.01, "family": f, "posthoc": p, "kind": kd}
                           for i, (v, f, p, kd) in enumerate(items)]}


def test_new_approach_checks_kind_previous_ids_family():
    st = {"cap": 20, "status": "running", "rounds": []}
    prev = {"TBJ", "NVU"}
    st = R3.add_round(st, _rnd(1, [(R3.FAIL1, "核心·熊市资产置换", True, "asset")]), prev)
    with pytest.raises(ValueError):
        R3.add_round(st, _rnd(2, [(R3.FAIL1, "离场", False, "")]), prev)                       # 没写第二关的类别
    with pytest.raises(ValueError):
        R3.add_round(st, _rnd(2, [(R3.FAIL1, "离场", False, "timing")]), prev)                 # 类别不在列表里
    bad = _rnd(2, [(R3.FAIL1, "离场", False, "stock")])
    bad["approaches"][0]["id"] = "TBJ"
    with pytest.raises(ValueError):
        R3.add_round(st, bad, prev)                                                            # 以前用过的 ID
    with pytest.raises(ValueError):
        R3.add_round(st, _rnd(2, [(R3.FAIL1, "汇率对冲", False, "signal")]), prev)              # 不再加的家族
    st = R3.add_round(st, _rnd(2, [(R3.FAIL1, "核心·熊市资产置换", True, "asset"), (R3.FAIL1, "核心·熊市资产置换", True, "asset")]), prev)
    with pytest.raises(ValueError):
        R3.add_round(st, _rnd(3, [(R3.FAIL1, "核心·熊市资产置换", True, "asset")]), prev)       # 同一家族第 4 个
    assert R3.used(st) == 3 and R3.family_counts(st) == {"核心·熊市资产置换": 3}


def test_previous_ids_cover_loops_one_and_two():
    ids = R3.previous_ids(ROOT / "var")
    assert {"TBJ", "TBU", "NVU", "EBX", "TPX", "FJE"} <= ids


def test_status_text_names_loop3():
    assert "第三个研究循环" in R3.status_text({})
    st = {"start": "2026-10-02", "registered": "x", "cap": 20, "baseline": {}, "rounds": []}
    assert R3.status_text(st).startswith("第三个研究循环")


def test_registered_state_file_is_consistent():
    st = R3.load_state(ROOT / "var")
    if not st:
        pytest.skip("第三个研究循环还没有登记")
    assert st["cap"] == R3.CAP and st["family_cap"] == R3.FAMILY_CAP and st["banned_families"] == list(R3.BANNED)
    assert st["kinds"] == list(R3.KINDS) and st["prereq_ok"] and set(st["baseline"]) >= set(R3.ERAS) and R3.used(st) <= R3.CAP
    assert [r["round"] for r in st.get("rounds") or []] == list(range(1, len(st.get("rounds") or []) + 1))
    assert all(a.get("family") and isinstance(a.get("posthoc"), bool) and a.get("kind") in R3.KINDS
               for r in st.get("rounds") or [] for a in r["approaches"])
    fc = R3.family_counts(st)
    assert all(v <= R3.FAMILY_CAP for v in fc.values()) and not any(k in R3.BANNED for k in fc)
