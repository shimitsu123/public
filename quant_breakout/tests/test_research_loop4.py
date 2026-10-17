"""第四个研究循环（scripts/research_loop4.py，2026-10-03 登记）：登记值同第三个循环、家族必须是「选股」、第一〜三个循环的 ID 不能再用、
选股类第二关的随机挡（每月同样多的票 / 逐个信号同样比例；种子固定）、状态文件。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_loop as RL  # noqa: E402
import research_loop2 as R2  # noqa: E402
import research_loop3 as R3  # noqa: E402
import research_loop4 as R4  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_registered_constants_same_as_loop3():
    assert (R4.CAP, R4.SUM_MIN, R4.ERA_TOL, R4.DD_TOL, R4.PLACEBO_N, R4.REPRO_TOL) == (R3.CAP, R3.SUM_MIN, R3.ERA_TOL, R3.DD_TOL, R3.PLACEBO_N, R3.REPRO_TOL)
    assert (R4.CAP, R4.SUM_MIN, R4.ERA_TOL, R4.DD_TOL, R4.PLACEBO_N) == (20, 0.03, 0.02, 2.0, 400)
    assert (R4.FOUND, R4.FAIL1, R4.FAIL2) == (RL.FOUND, RL.FAIL1, RL.FAIL2)
    assert (R4.STATE_FILE, R4.FAMILY_CAP, R4.BANNED, R4.KINDS) == ("research_loop4.json", 3, R3.BANNED, R3.KINDS)
    assert (R4.FAMILY_PREFIX, R4.STOCK_SEED, R4.PREREQ_TOL, R4.DEADLINE) == ("选股", 20261003, 0.0005, "2026-10-03 05:40 JST")
    assert R4.stage1 is R2.stage1 and R4.stage2 is RL.stage2 and R4.verdict is RL.verdict


def test_random_month_block_same_count_from_pool_and_deterministic():
    m = pd.period_range("2024-01", periods=3, freq="M")
    cols = [f"{k}.T" for k in range(10)]
    real = pd.DataFrame(False, index=m, columns=cols, dtype=object)
    real.iloc[0, [0, 1]] = True                                               # 1 月挡 2 只
    real.iloc[1, [3]] = True                                                  # 2 月挡 1 只
    real.iloc[1, 5:] = np.nan                                                 # 2 月只有 5 只在池子里
    a = R4.random_month_block(real, 7)
    assert a.equals(R4.random_month_block(real, 7))                           # 同一个种子 = 同一个结果
    assert list(a.sum(axis=1)) == [2, 1, 0]                                   # 每个月挡的个数与真实相同
    assert not a.iloc[1, 5:].any()                                            # 只从那个月在池子里的票里挑
    many = [R4.random_month_block(real, s).iloc[0] for s in range(40)]
    assert len({tuple(x) for x in many}) > 5                                  # 不同种子挑的不同


def test_random_signal_block_rate_and_seed():
    b = R4.random_signal_block(20000, 0.3, 3)
    assert b.dtype == bool and len(b) == 20000 and abs(b.mean() - 0.3) < 0.02
    assert (b == R4.random_signal_block(20000, 0.3, 3)).all() and not (b == R4.random_signal_block(20000, 0.3, 4)).all()
    assert not R4.random_signal_block(50, 0.0, 1).any() and R4.random_signal_block(50, 1.0, 1).all()
    assert (R4.random_signal_block(10, 0.5, 2) == (np.random.default_rng([20261003, 2]).random(10) < 0.5)).all()


def _rnd(k, items):
    return {"round": k, "date": "2026-10-03", "title": f"第 {k} 轮",
            "approaches": [{"id": f"S{k}{i}", "verdict": v, "sum": 0.01, "family": f, "posthoc": p, "kind": kd}
                           for i, (v, f, p, kd) in enumerate(items)]}


def test_new_approach_checks_stock_selection_only():
    st = {"cap": 20, "status": "running", "rounds": []}
    prev = {"TBJ", "RMO", "MXR"}
    st = R4.add_round(st, _rnd(1, [(R4.FAIL1, "选股·基本面", False, "stock")]), prev)
    with pytest.raises(ValueError):
        R4.add_round(st, _rnd(2, [(R4.FAIL1, "核心·熊市资产置换", False, "asset")]), prev)      # 不是选股
    with pytest.raises(ValueError):
        R4.add_round(st, _rnd(2, [(R4.FAIL1, "选股·基本面", False, "")]), prev)                 # 没写第二关的类别
    bad = _rnd(2, [(R4.FAIL1, "选股·基本面", False, "stock")])
    bad["approaches"][0]["id"] = "RMO"
    with pytest.raises(ValueError):
        R4.add_round(st, bad, prev)                                                            # 第三个循环用过的 ID
    with pytest.raises(ValueError):
        R4.add_round(st, _rnd(2, [(R4.FAIL1, "选股·基本面", None, "stock")]), prev)             # 没标明是不是事后组合
    st = R4.add_round(st, _rnd(2, [(R4.FAIL1, "选股·基本面", False, "stock"), (R4.FAIL1, "选股·基本面", True, "stock")]), prev)
    with pytest.raises(ValueError):
        R4.add_round(st, _rnd(3, [(R4.FAIL1, "选股·基本面", False, "stock")]), prev)            # 同一家族第 4 个
    assert R4.used(st) == 3 and R4.family_counts(st) == {"选股·基本面": 3}


def test_previous_ids_cover_loops_one_to_three():
    ids = R4.previous_ids(ROOT / "var")
    assert {"TBJ", "FJE", "TPX", "ZSP", "NZS", "RMO", "FIP"} <= ids


def test_status_text_names_loop4():
    assert "第四个研究循环" in R4.status_text({})
    st = {"start": "2026-10-03", "registered": "x", "cap": 20, "baseline": {}, "rounds": []}
    assert R4.status_text(st).startswith("第四个研究循环")


def test_init_state_writes_once(tmp_path):
    res = {"baseline": {"Z": {"calmar": 0.979}}, "prereq_ok": True, "fingerprint": "abc"}
    st = R4.init_state(res, tmp_path)
    assert st["status"] == "running" and st["cap"] == 20 and st["family_prefix"] == "选股" and st["rounds"] == []
    assert st["deadline"] == R4.DEADLINE and st["kinds"] == list(R4.KINDS) and st["baseline"] == res["baseline"]
    again = R4.init_state({"baseline": {}, "prereq_ok": False, "fingerprint": "zzz"}, tmp_path)
    assert again == st                                                       # 已存在就不动
    assert R4.load_state(tmp_path) == st


def test_cli_status_only_reads(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path))
    assert R4.main(["--status"]) == 0
    assert "还没有登记" in capsys.readouterr().out and not (tmp_path / R4.STATE_FILE).exists()


def test_registered_state_file_is_consistent():
    st = R4.load_state(ROOT / "var")
    if not st:
        pytest.skip("第四个研究循环还没有登记")
    assert st["cap"] == R4.CAP and st["family_cap"] == R4.FAMILY_CAP and st["family_prefix"] == R4.FAMILY_PREFIX
    assert st["kinds"] == list(R4.KINDS) and st["prereq_ok"] and set(st["baseline"]) >= set(R4.ERAS) and R4.used(st) <= R4.CAP
    assert [r["round"] for r in st.get("rounds") or []] == list(range(1, len(st.get("rounds") or []) + 1))
    assert all(str(a.get("family")).startswith(R4.FAMILY_PREFIX) and isinstance(a.get("posthoc"), bool) and a.get("kind") in R4.KINDS
               for r in st.get("rounds") or [] for a in r["approaches"])
    assert not {a["id"] for r in st.get("rounds") or [] for a in r["approaches"]} & R4.previous_ids(ROOT / "var")
    assert all(v <= R4.FAMILY_CAP for v in R4.family_counts(st).values())
