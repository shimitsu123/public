"""股票池复核（scripts/universe_recheck.py）：临时数据目录不共用研究的中间结果、只认复核开始之后写出的输出、研究总图的依赖分类。"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import universe_recheck as R                                                 # noqa: E402


def _fake_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    (repo / "var" / "cache" / "sub").mkdir(parents=True)
    (repo / "var" / "out").mkdir()
    (repo / "var" / "sim.json").write_text("{}", encoding="utf-8")
    (repo / "var" / "out" / "x.json").write_text(json.dumps({"passed": ["A"]}), encoding="utf-8")
    (repo / "var" / "cache" / "7203.T_21y.csv").write_text("d", encoding="utf-8")
    (repo / "var" / "cache" / "candle_panels.npz").write_text("p", encoding="utf-8")
    (repo / "var" / "cache" / "study_ckpt.pkl").write_text("k", encoding="utf-8")
    return repo


def test_setup_links_cache_but_not_study_intermediates(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(R, "REPO", repo)
    base = tmp_path / "urc"
    R.setup(base, ("old",))
    h = base / "old" / "home"
    assert (h / R.MARK).exists() and (h / "sim.json").exists() and (h / "out" / "x.json").exists()
    c = h / "cache"
    assert (c / "7203.T_21y.csv").is_symlink() and (c / "sub").is_symlink()
    assert not (c / "candle_panels.npz").exists() and not (c / "study_ckpt.pkl").exists()


def test_load_out_only_after_setup(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    monkeypatch.setattr(R, "REPO", repo)
    base = tmp_path / "urc"
    R.setup(base, ("new",))
    fp = base / "new" / "home" / "out" / "x.json"
    old = time.time() - 3600
    os.utime(fp, (old, old))                                                  # 复制过来的旧输出 → 不算
    assert R.load_out(base, "new", "x") is None
    time.sleep(0.01)
    fp.write_text(json.dumps({"passed": []}), encoding="utf-8")               # 复核里重跑写出的 → 算
    assert R.load_out(base, "new", "x") == {"passed": []}
    assert R._pick({"passed": [], "fails": [1, 2], "other": 1}) == {"passed": [], "fails": 2}


def test_classify_registry_covers_every_entry():
    rows = R.classify_registry()
    reg = json.loads((R.REPO / "var" / "research_registry.json").read_text(encoding="utf-8"))
    assert len(rows) == len(reg)
    kinds = {"日経225 股票池", "扩大池（冻结）/ 全市场", "全市场（本来就含航空 / 陆运）", "美股池", "指数 / 行业 / 宏观（不看个股池）", "没有脚本（配置 / 工程）"}
    assert {r["dep"] for r in rows} <= kinds
    dep = {r["dep"] for r in rows if "scripts/exit_mode_check.py" in r["script"].split(";")}
    assert dep == {"日経225 股票池"}
    assert {r["dep"] for r in rows if r["script"] == "scripts/threat_intl_study.py"} == {"指数 / 行业 / 宏观（不看个股池）"}


def test_conclusion_compare_ignores_numbers():
    a = {"verdict": {"D1": {"label": "不通过", "E": {"d_calmar": 0.001, "d_dd": 0.47}}}}
    b = {"verdict": {"D1": {"label": "不通过", "E": {"d_calmar": 0.002, "d_dd": 0.46}}}}
    assert R.same_kind(a, b) == "same" and R.same_kind(None, a) is None
    assert R.same_kind({"proposal": "W2", "passed": ["V3"]}, {"proposal": "W2", "passed": []}) == "passed"
    ca = {"decision": {"per": {"1000000|2": []}, "best": "1000000|2"}}
    cb = {"decision": {"per": {"1000000|2": ["主窗口"]}, "best": "1000000|4|U2"}}
    assert R.same_kind(ca, cb) == "changed"
    assert R.same_kind({"decision": {"H3": True, "H3_diff": 2.8}}, {"decision": {"H3": True, "H3_diff": 1.1}}) == "same"


def test_pick_search_pools_and_k_candidates():
    d = {"pools": {"P1": {"real": 2, "top": [{"rule": "vr1 ≥ 2/3 分位（2.184） ∧ b_n225 ≤ 中位数（0.7803）"}]}},
         "K2": {"leap_fails": ["S1 Z 胜率 56.5%"], "improve_fails": []}}
    p = R._pick(d)
    assert p["pools"]["P1"] == {"real": 2, "top": ["vr1 ≥ 2/3 分位 ∧ b_n225 ≤ 中位数"]}
    assert p["verdict"]["K2"]["label"] == "飞跃 ✗ / 改进 ✓"
    assert "过筛选 2 个" in R._short(p)


def test_details_only_lists_flipped_candidates():
    out = R._details({"fails": {"V1": ["x"], "V3": []}}, {"fails": {"V1": ["y"], "V3": ["z"]}})
    assert len(out) == 1 and "V3" in out[0] and "old 全部过" in out[0] and "z" in out[0]
    cap = R._details({"decision": {"per": {"2": [], "U2": ["g"]}}}, {"decision": {"per": {"2": ["h"], "U2": []}}})
    assert len(cap) == 2
    sig = R._details({"decision": {"per": {"E1": {"pass": False, "fails": ["q"]}}}}, {"decision": {"per": {"E1": {"pass": True, "fails": []}}}})
    assert len(sig) == 1 and "new 全部过" in sig[0]


def test_write_report_counts_follow_results(tmp_path, monkeypatch):
    repo = _fake_repo(tmp_path)
    reg = [{"line": 1, "date": "2026-09-01", "domain": "个股", "verdict": "不通过", "title": "x", "script": ""}]
    (repo / "var" / "research_registry.json").write_text(json.dumps(reg), encoding="utf-8")
    monkeypatch.setattr(R, "REPO", repo)
    monkeypatch.setattr(R, "SCRIPTS", ["x"])
    monkeypatch.setattr(R, "EXTRA", [])
    monkeypatch.setattr(R, "WAVE2", [])
    base = tmp_path / "urc"
    R.setup(base, ("old", "new"))
    time.sleep(0.01)
    for m, v in (("old", ["A"]), ("new", [])):
        (base / m / "home" / "out" / "x.json").write_text(json.dumps({"proposal": "W2", "passed": v}), encoding="utf-8")
    notes = tmp_path / "notes.md"
    notes.write_text("读法一句。", encoding="utf-8")
    out = R.write_report(base, notes)
    md = (repo / "var" / "out" / "universe_recheck.md").read_text(encoding="utf-8")
    assert [r["kind"] for r in out["rows"] if r["script"] == "x"] == ["passed"]
    assert "两边都跑出来的 1 项里，0 项结论完全相同；1 项决定不变" in md and "全部 1 条研究" in md
    assert "## 四 读法" in md and "读法一句。" in md and md.rstrip().endswith("非投资建议。")


def test_only_w_modes_turn_w2_off():
    assert [m for m in ("old", "new", "newus", "oldw", "neww") if R.w2_off(m)] == ["oldw", "neww"]   # "new" 以 w 结尾，但要开 W2
