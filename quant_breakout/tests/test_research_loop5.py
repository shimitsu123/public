"""第五个研究循环（scripts/research_loop5.py，2026-10-03 登记）：登记值同第四个循环、家族必须是「仓位」、第一〜四个循环的 ID 不能再用、
加减仓的接法（position_pct = 25% × m_max、倍数 ÷ m_max）、三种第二关的随机对照（打乱 / 循环平移 / 配对重抽）、仓位版 S5、状态文件。"""
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
import research_loop5 as R5  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_registered_constants_same_as_loop4():
    assert (R5.CAP, R5.SUM_MIN, R5.ERA_TOL, R5.DD_TOL, R5.PLACEBO_N, R5.REPRO_TOL) == (R4.CAP, R4.SUM_MIN, R4.ERA_TOL, R4.DD_TOL, R4.PLACEBO_N, R4.REPRO_TOL)
    assert (R5.CAP, R5.SUM_MIN, R5.ERA_TOL, R5.DD_TOL, R5.PLACEBO_N) == (20, 0.03, 0.02, 2.0, 400)
    assert (R5.FOUND, R5.FAIL1, R5.FAIL2) == (RL.FOUND, RL.FAIL1, RL.FAIL2)
    assert (R5.STATE_FILE, R5.FAMILY_CAP, R5.BANNED, R5.KINDS) == ("research_loop5.json", 3, R4.BANNED, ("size_trade", "size_time", "struct"))
    assert (R5.FAMILY_PREFIX, R5.SIZE_SEED, R5.PREREQ_TOL, R5.DROP_FRAC, R5.SHIFT_GAP) == ("仓位", 20261005, 0.0005, 0.20, 250)
    assert (R5.BASE_PCT, R5.MAX_PCT) == (0.25, 0.34) and R5.M_CAP == pytest.approx(1.36)
    assert R5.stage1 is R2.stage1 and R5.stage2 is RL.stage2 and R5.verdict is RL.verdict
    assert R5.PREV_FILES == ("research_loop.json", "research_loop2.json", "research_loop3.json", "research_loop4.json")
    assert R5.WIRING_KEYS == ("cagr", "dd", "calmar", "n", "mean", "win", "h1", "h2") and R5.O0_REF == {"Z": 0.376, "E": 0.615, "J": 0.727}


def test_sizing_kw_reproduces_b1_and_scales_up_to_cap():
    days = pd.bdate_range("2024-01-01", periods=5)
    kw = R5.sizing_kw(1.0, days=days)
    assert kw["cfg_over"] == {"position_pct": 0.25} and (kw["em_mult"] == 1.0).all() and "em_tick" not in kw   # 倍数全为 1 = B1
    kw = R5.sizing_kw(1.36, days=days, tick_mult={("A.T", days[0]): 1.36, ("B.T", days[1]): 0.5})
    assert kw["cfg_over"]["position_pct"] == pytest.approx(0.34) and kw["em_mult"].iloc[0] == pytest.approx(1 / 1.36)
    eff = {k: kw["cfg_over"]["position_pct"] * kw["em_mult"].iloc[0] * v for k, v in kw["em_tick"].items()}
    assert eff[("A.T", days[0])] == pytest.approx(0.34) and eff[("B.T", days[1])] == pytest.approx(0.125)       # 有效仓位 = 25% × m
    assert kw["cfg_over"]["position_pct"] * kw["em_mult"].iloc[2] == pytest.approx(0.25)                         # 没给倍数的信号 = 25%
    dm = pd.Series([1.0, 1.2, 0.5, 0.0, 1.2], index=days)
    kw = R5.sizing_kw(1.2, day_mult=dm)
    assert (kw["cfg_over"]["position_pct"] * kw["em_mult"]).round(6).tolist() == [0.25, 0.3, 0.125, 0.0, 0.3]
    with pytest.raises(ValueError):
        R5.sizing_kw(1.5, days=days)                                                                              # 超过单只上限 34%
    with pytest.raises(ValueError):
        R5.sizing_kw(1.2, day_mult=pd.Series([1.3], index=days[:1]))                                             # 倍数超过 m_max
    with pytest.raises(ValueError):
        R5.sizing_kw(1.0)                                                                                         # 没给 days


def test_fill_day_and_ticks_from():
    days = pd.bdate_range("2024-01-01", periods=4)
    s = R5.fill_day(pd.Series([0.5, 1.2], index=[days[0], days[2]]), days)
    assert s.tolist() == [1.0, 0.5, 0.5, 1.2]                                                                     # 信号日收盘定 → 下一个交易日用
    tk = R5.ticks_from(["A.T", "B.T", "C.T"], [days[0], days[1], days[2]], [1.0, 1.36, 0.0])
    assert tk == {("B.T", days[1]): 1.36, ("C.T", days[2]): 0.0}                                                  # 只放 m ≠ 1 的


def test_permute_mult_same_multiset_and_seeded():
    m = np.array([1.0] * 60 + [1.36] * 30 + [0.5] * 10)
    a = R5.permute_mult(m, 3)
    assert sorted(a) == sorted(m) and (a == R5.permute_mult(m, 3)).all() and not (a == R5.permute_mult(m, 4)).all()
    assert (a == m[np.random.default_rng([20261005, 1, 3]).permutation(len(m))]).all()


def test_shift_mult_and_ks():
    idx = pd.bdate_range("2020-01-01", periods=6)
    m = pd.Series([1, 2, 3, 4, 5, 6], index=idx, dtype=float)
    assert R5.shift_mult(m, 2).tolist() == [5, 6, 1, 2, 3, 4] and R5.shift_mult(m, 0).equals(m) and (R5.shift_mult(m, 2).index == idx).all()
    ks = R5.size_shift_ks(2000, range(50))
    assert all(250 <= k <= 1750 for k in ks) and ks == R3.shift_ks(2000, range(50), base=20261005, gap=250)
    with pytest.raises(ValueError):
        R5.size_shift_ks(400, range(3))


def test_drop_mask_rate_seed_and_era():
    a = R5.drop_mask(20000, 5, 0)
    assert a.dtype == bool and abs(a.mean() - 0.2) < 0.02 and (a == R5.drop_mask(20000, 5, 0)).all()
    assert not (a == R5.drop_mask(20000, 6, 0)).all() and not (a == R5.drop_mask(20000, 5, 1)).all()
    assert (R5.drop_mask(10, 2, 1) == (np.random.default_rng([20261005, 2, 2, 1]).random(10) < 0.2)).all()


def test_stage2_struct_needs_all_positive_and_neighbors():
    assert R5.stage2_struct([0.01] * 400, True)["ok"]
    assert not R5.stage2_struct([0.01] * 399 + [0.0], True)["ok"]                                                 # 有一次不比 B1 好
    assert not R5.stage2_struct([0.01] * 399 + [None], True)["ok"]                                                # 有算不出的
    assert not R5.stage2_struct([0.01] * 399, True)["ok"]                                                         # 次数不够
    assert not R5.stage2_struct([0.01] * 400, False)["ok"]                                                        # 相邻参数值不过
    r = R5.stage2_struct([0.05, -0.01] + [0.02] * 398, True)
    assert r["min"] == pytest.approx(-0.01) and r["le0"] == 1 and not r["ok"]


def test_s5_sizing_first_order_effect():
    x = np.array([10.0, -5.0, 3.0, -2.0, np.nan])
    r = R5.s5_sizing(x, np.ones(5))
    assert r["n"] == 4 and r["dmean"] == pytest.approx(0.0) and r["dwin"] == pytest.approx(0.0)                    # 不改仓位 = 0
    r = R5.s5_sizing(x, np.full(5, 1.36))
    assert r["dmean"] == pytest.approx(0.36 * 1.5) and r["dwin"] == pytest.approx(0.0)                             # 统一加大：超额平均 > 0 → 正
    r = R5.s5_sizing(x, np.full(5, 0.5))
    assert r["dmean"] == pytest.approx(-0.5 * 1.5)                                                                 # 统一缩小：超额平均 > 0 → 负
    r = R5.s5_sizing(x, np.array([1.36, 0.5, 1.36, 0.5, 1.0]))
    assert r["dmean"] > 0 and r["dwin"] > 0                                                                        # 加给跑赢的、减给跑输的
    r = R5.s5_sizing(x, np.array([0.5, 1.36, 0.5, 1.36, 1.0]))
    assert r["dmean"] < 0 and r["dwin"] < 0
    assert R5.s5_sizing([np.nan], [1.0])["n"] == 0
    chk = RL.other_stocks_check({"W": R5.s5_sizing(x, np.full(5, 1.36)), "Jx": R5.s5_sizing(x, np.full(5, 0.5))})
    assert chk["applies"] and not chk["S5"]                                                                        # 一个池子反方向 → S5 不过


def _rnd(k, items):
    return {"round": k, "date": "2026-10-03", "title": f"第 {k} 轮",
            "approaches": [{"id": f"P{k}{i}", "verdict": v, "sum": 0.01, "family": f, "posthoc": p, "kind": kd}
                           for i, (v, f, p, kd) in enumerate(items)]}


def test_new_approach_checks_sizing_only():
    st = {"cap": 20, "status": "running", "rounds": []}
    prev = {"TBJ", "RMO", "STR", "SSN"}
    st = R5.add_round(st, _rnd(1, [(R5.FAIL1, "仓位·层间切分", False, "size_time")]), prev)
    with pytest.raises(ValueError):
        R5.add_round(st, _rnd(2, [(R5.FAIL1, "选股·基本面", False, "size_trade")]), prev)                         # 不是仓位
    with pytest.raises(ValueError):
        R5.add_round(st, _rnd(2, [(R5.FAIL1, "仓位·按信号", False, "stock")]), prev)                               # 第二关类别不是本循环的
    bad = _rnd(2, [(R5.FAIL1, "仓位·按信号", False, "size_trade")])
    bad["approaches"][0]["id"] = "STR"
    with pytest.raises(ValueError):
        R5.add_round(st, bad, prev)                                                                               # 第四个循环用过的 ID
    with pytest.raises(ValueError):
        R5.add_round(st, _rnd(2, [(R5.FAIL1, "仓位·按信号", None, "size_trade")]), prev)                           # 没标明是不是事后组合
    st = R5.add_round(st, _rnd(2, [(R5.FAIL1, "仓位·层间切分", False, "struct"), (R5.FAIL1, "仓位·层间切分", True, "size_time")]), prev)
    with pytest.raises(ValueError):
        R5.add_round(st, _rnd(3, [(R5.FAIL1, "仓位·层间切分", False, "size_time")]), prev)                         # 同一家族第 4 个
    assert R5.used(st) == 3 and R5.family_counts(st) == {"仓位·层间切分": 3}


def test_previous_ids_cover_loops_one_to_four():
    ids = R5.previous_ids(ROOT / "var")
    assert {"TBJ", "FJE", "TPX", "ZSP", "NZS", "RMO", "FIP"} <= ids
    if R4.load_state(ROOT / "var"):
        assert {"FBM", "STR", "SSN"} <= ids


def test_status_text_names_loop5():
    assert "第五个研究循环" in R5.status_text({})
    st = {"start": "2026-10-03", "registered": "x", "cap": 20, "baseline": {}, "rounds": []}
    assert R5.status_text(st).startswith("第五个研究循环")


def test_init_state_writes_once(tmp_path):
    res = {"baseline": {"Z": {"calmar": 0.979}}, "prereq_ok": True, "fingerprint": "abc"}
    st = R5.init_state(res, tmp_path)
    assert st["status"] == "running" and st["cap"] == 20 and st["family_prefix"] == "仓位" and st["rounds"] == []
    assert st["deadline"] is None and st["kinds"] == list(R5.KINDS) and st["baseline"] == res["baseline"]
    assert st["sizing"]["max_pct"] == 0.34 and st["sizing"]["base_pct"] == 0.25
    again = R5.init_state({"baseline": {}, "prereq_ok": False, "fingerprint": "zzz"}, tmp_path)
    assert again == st                                                                                            # 已存在就不动
    assert R5.load_state(tmp_path) == st


def test_cli_status_only_reads(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path))
    assert R5.main(["--status"]) == 0
    assert "还没有登记" in capsys.readouterr().out and not (tmp_path / R5.STATE_FILE).exists()


def test_registered_state_file_is_consistent():
    st = R5.load_state(ROOT / "var")
    if not st:
        pytest.skip("第五个研究循环还没有登记")
    assert st["cap"] == R5.CAP and st["family_cap"] == R5.FAMILY_CAP and st["family_prefix"] == R5.FAMILY_PREFIX
    assert st["kinds"] == list(R5.KINDS) and st["prereq_ok"] and set(st["baseline"]) >= set(R5.ERAS) and R5.used(st) <= R5.CAP
    assert [r["round"] for r in st.get("rounds") or []] == list(range(1, len(st.get("rounds") or []) + 1))
    assert all(str(a.get("family")).startswith(R5.FAMILY_PREFIX) and isinstance(a.get("posthoc"), bool) and a.get("kind") in R5.KINDS
               for r in st.get("rounds") or [] for a in r["approaches"])
    assert not {a["id"] for r in st.get("rounds") or [] for a in r["approaches"]} & R5.previous_ids(ROOT / "var")
    assert all(v <= R5.FAMILY_CAP for v in R5.family_counts(st).values())
