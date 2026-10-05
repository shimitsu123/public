"""scripts/research_meta_stats.py：正态尾巴、BH、π0、符号检验、文字里的统计量提取、分节、第二关的经验 p。"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_meta_stats as M  # noqa: E402


def test_constants():
    assert (M.FDR_Q, M.LAMBDA, M.OUT) == (0.10, 0.5, "research_meta_stats")


def test_normal_helpers():
    assert math.isclose(M.p_two(1.96), 0.05, abs_tol=1e-3) and math.isclose(M.p_two(-2.576), 0.01, abs_tol=1e-3)
    for p in (0.5, 0.05, 0.01, 0.001):
        assert math.isclose(M.p_two(M.z_from_p(p)), p, rel_tol=1e-6)
    assert M.z_from_p(1.0) < 1e-6 and M.z_from_p(0.0) > 7
    assert M.num("−1.5") == -1.5 and M.num("+2") == 2.0


def test_bh_matches_textbook_example():
    p = [0.01, 0.04, 0.03, 0.20]
    adj, keep = M.bh(p, q=0.05)
    assert np.allclose(adj, [0.04, 0.0533333, 0.0533333, 0.20], atol=1e-6)        # 0.01×4/1、min(0.04×4/3, 0.03×4/2)
    assert keep == [True, False, False, False]
    assert M.bh([]) == ([], [])
    adj2, keep2 = M.bh([0.001] * 5 + [0.9] * 5, q=0.10)
    assert sum(keep2) == 5 and max(adj2) <= 1.0


def test_storey_pi0_and_tails():
    assert M.storey_pi0([0.9, 0.8, 0.1, 0.6]) == 1.0                                # 3 ÷ (0.5 × 4) → 上限 1
    assert M.storey_pi0([0.01, 0.02, 0.7, 0.04]) == 0.5
    assert M.storey_pi0([]) is None
    t = M.tail_share([0.0, 2.0, -3.0, 4.0])
    assert t["n"] == 4 and t["gt1.96"] == 75.0 and t["gt2.58"] == 50.0 and t["gt3.29"] == 25.0


def test_sign_test_and_binomial():
    assert math.isclose(M.sign_test([1] * 6), 2 / 64)
    assert M.sign_test([1, -1, 1, -1, 0, 0]) == 1.0 and M.sign_test([0, 0]) is None
    assert math.isclose(M.sign_test([1, 1, 1, 1, 1, -1]), 2 * 7 / 64)
    assert math.isclose(M.binom_upper(0, 5, 0.3), 1.0) and math.isclose(M.binom_upper(2, 2, 0.5), 0.25)


def test_paren_span():
    s = "甲（t 2.0，p 0.01）乙 p 0.2"
    assert M.paren_span(s, s.index("t 2")) == (1, s.index("）"))
    assert M.paren_span(s, s.rindex("p 0.2")) is None
    assert M.paren_span("（a）b", 3) is None


def test_extract_t_p_ci():
    rows = M.extract("胜率 +3%（t 2.51，对照经验 p 0.005，两半 +1 / +2）、另 −2.26（p 0.043）")
    kinds = sorted(r["kind"] for r in rows)
    assert kinds == ["p", "t"]                                                     # 括号里已经有 t 的 p 不算
    t = [r for r in rows if r["kind"] == "t"][0]
    assert t["z"] == 2.51 and math.isclose(t["p"], M.p_two(2.51))
    p = [r for r in rows if r["kind"] == "p"][0]
    assert p["val"] == "0.043" and math.isclose(p["z"], M.z_from_p(0.043))
    two = M.extract("鉄鋼（t +7.71 / +10.34，命中率 56.6%）")
    assert [r["kind"] for r in two] == ["t", "t_extra"] and [r["z"] for r in two] == [7.71, 10.34]
    assert M.extract("对照 t 95% 分位 1.83") == []                                 # 「t 95」不是 t 值
    assert M.extract("对照的经验 p < 0.05") == []                                  # 门槛不算
    eq = M.extract("合并 IC +0.089（联合区块自助法单侧 p = 0.070 ≤ 0.10）")
    assert len(eq) == 1 and math.isclose(eq[0]["p"], 0.14)                         # 单侧 → 双侧
    wrong = M.extract("方向相反；单侧 p = 0.741")
    assert math.isclose(wrong[0]["p"], 0.518)
    zero = M.extract("置换 p 0")
    assert zero[0]["p"] == 1e-4
    ci = M.extract("把胜率提高 7.2 pp（95% 区间 +0.7〜+13.6，统计上成立）")
    assert len(ci) == 1 and ci[0]["kind"] == "ci" and math.isclose(ci[0]["z"], 7.15 / (12.9 / 3.92))
    auc = M.extract("AUC 0.622（95% 区间 0.398〜0.801，太宽）")
    assert math.isclose(auc[0]["z"], (0.5995 - 0.5) / (0.403 / 3.92))              # AUC → 以 0.5 为零点
    assert M.extract("95% 区间 +1.0〜−1.0") == []                                  # 上下反了 → 不算
    for r in rows + ci:
        assert set(r) == {"kind", "z", "p", "val", "ctx", "key"}


def test_sections_and_part_a_dedupe():
    md = "前言\n## 研究一\n另见：差 +1.0 pp（t 3.0）\n## 研究二\n回顾：差 +1.0 pp（t 3.0）\n别的 p 0.5\n"
    sec = M.sections(md)
    assert [(s[0], s[1]) for s in sec] == [("（开头）", 1), ("研究一", 2), ("研究二", 4)]
    a = M.part_a(md)
    assert a["by_kind"]["t"] == 1 and a["by_kind"]["p"] == 1                       # 同一个值 + 前面 10 个字相同 → 一次
    t = [r for r in a["rows"] if r["kind"] == "t"][0]
    assert t["section"] == "研究一" and t["line"] == 3
    assert a["tails"]["n"] == 2 and 0 <= a["n_bh"] <= 2


def test_loop_rows_parts_b_c(tmp_path):
    loop = {"rounds": [{"approaches": [
        {"id": "AAA", "verdict": "不过", "d": {"Z": 0.1, "E": 0.2, "J": 0.3}, "stage2": {"ge_stat": 0, "n": 400}},
        {"id": "BBB", "verdict": "不过", "d": {"Z": -0.1, "E": 0.2, "J": None}},
        {"id": "CCC", "verdict": "不过", "d": {"Z": -0.1, "E": -0.2, "J": -0.3},
         "era_dwin": {"Z": 1.0, "E": 2.0, "J": 3.0}, "pools": {"W": {"dwin": 1.0}, "Jx": {"dwin": 2.0}, "Zx": {"dwin": 0.5}}}]}]}
    (tmp_path / "research_loop11.json").write_text(json.dumps(loop), encoding="utf-8")
    loop7 = {"rounds": [{"candidates": [{"id": "VVV", "verdict": "不过", "d": None, "stage2": {"ge_stat": 34, "n": 17}}]}]}
    (tmp_path / "research_loop7.json").write_text(json.dumps(loop7), encoding="utf-8")
    rows = M.loop_rows(tmp_path)
    by = {r["id"]: r for r in rows}
    assert by["AAA"]["loop"] == 11 and math.isclose(by["AAA"]["stage2_p"], 1 / 401)
    assert math.isclose(by["VVV"]["stage2_p"], 35 / 401)                           # n 17 = 市场数 → 400 次
    assert by["BBB"]["d"] == {"Z": -0.1, "E": 0.2} and by["CCC"]["six_signs"] == [1] * 6
    b = M.part_b(rows)
    assert b["by_k"][3]["n"] == 2 and b["by_k"][3]["all_pos"] == 1 and b["by_k"][3]["all_neg"] == 1
    assert b["by_k"][2]["n"] == 1 and b["six"][0]["id"] == "CCC" and math.isclose(b["six"][0]["p"], 0.0312, abs_tol=1e-4)
    c = M.part_c(rows)
    assert [r["id"] for r in c["rows"]] == ["AAA", "VVV"] and c["rows"][0]["bh"]
