"""第十二个研究循环（scripts/research_loop12.py）的判定函数：路线 J、池子、第二关、状态（ID / 家族 / 上限）。"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research_loop12 as R  # noqa: E402

B = {"calmar": 0.60, "dd": -29.0, "h1": 0.55, "h2": 0.80, "win": 45.0, "mean": 2.0, "n": 60}


def test_route_j():
    jx_good = {"gone_n": 30, "dwin": 1.0, "dmean": 0.2}
    c = {**B, "calmar": 0.64, "win": 47.5, "mean": 2.1}
    s = R.stage1_j(c, B, jx_good)
    assert s["routes"]["JA"]["ok"] and s["routes"]["JB"]["ok"] and s["ok_routes"] == ["JA", "JB"]
    assert not R.stage1_j({**c, "h1": 0.50}, B, jx_good)["ok"]                    # 前一半差 −0.05 → 两条都不过
    assert not R.stage1_j(c, B, {"gone_n": 0, "dwin": 1.0, "dmean": 0.2})["ok"]    # Jx 一个都没挡 → V4J 不过
    s2 = R.stage1_j({**B, "win": 47.5, "mean": 1.9}, B, jx_good)
    assert not s2["routes"]["JB"]["ok"]                                         # 每笔变差
    assert not R.stage1_j({**B, "dd": -32.0, "calmar": 0.7}, B, jx_good)["ok"]   # 回撤深 3 pp


def test_stage2_and_random_block():
    p = [{"JB": float(x)} for x in np.linspace(-3, 2, 400)]
    assert R.stage2({"JB": 2.5}, p, ["JB"])["pass"] and not R.stage2({"JB": 1.9}, p, ["JB"])["pass"]
    assert not R.stage2({"JB": 9}, p[:399], ["JB"])["pass"]                     # 次数不够
    g = R.random_block(1000, 0.1, 3)
    assert 60 < g.sum() < 140 and (g == R.random_block(1000, 0.1, 3)).all()


def test_add_round_checks():
    st = {"rounds": []}
    a = lambda i, f="选股·估值": {"id": i, "family": f}                         # noqa: E731
    R.add_round(st, {"round": 1, "approaches": [a("PBH"), a("PBQ"), a("PBX")]})
    with pytest.raises(ValueError):
        R.add_round(st, {"round": 2, "approaches": [a("PBZ")]})                  # 同一家族第 4 个
    with pytest.raises(ValueError):
        R.add_round(st, {"round": 2, "approaches": [a("TBF", "选股·其他")]})       # 用过的 ID
    with pytest.raises(ValueError):
        R.add_round(st, {"round": 2, "approaches": [a("ZZZ", "卖法")]})            # 家族名
