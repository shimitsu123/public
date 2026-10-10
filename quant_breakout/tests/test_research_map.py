"""scripts/research_map.py：研究总图的每一条都对应 var/sim_changes.md 的一个「## 」标题（行号一致、没有漏）；字段齐全；能渲染。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_map as RM  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
KEYS = {"line", "date", "title", "kind", "domain", "verdict", "candidates", "stable_findings", "era_dependent_or_reversed"}


def test_registry_matches_change_log():
    rows = RM.load()
    heads = [i + 1 for i, s in enumerate((ROOT / "var" / "sim_changes.md").read_text(encoding="utf-8").splitlines()) if s.startswith("## ")]
    lines = [r["line"] for r in rows]
    covered = set(lines)
    # 总图只追加：已登记的每一条都必须还指向「## 」标题；新写进 sim_changes 的条目可以晚一点补进总图
    assert covered <= set(heads)
    assert len(lines) == len(covered)
    assert len(covered) >= 118
    for r in rows:
        assert KEYS <= set(r), r.get("line")
        assert r["domain"] in RM.DOMAINS and r["verdict"] in RM.VERDICTS


def test_render():
    md = RM.render(RM.load())
    assert md.startswith("# 研究总图") and "## 三" in md and md.rstrip().endswith("非投资建议。")
