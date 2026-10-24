"""scripts/jq_vs_yf_study.py 的纯函数。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import jq_vs_yf_study as S  # noqa: E402


def test_overlap():
    o = S.overlap({("A", "1"), ("B", "2")}, {("A", "1"), ("C", "3")})
    assert (o["both"], o["only_a"], o["only_b"], o["agree_pct"]) == (1, 1, 1, 33.3)
    assert S.overlap(set(), set())["agree_pct"] is None
