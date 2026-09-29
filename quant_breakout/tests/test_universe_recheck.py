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
