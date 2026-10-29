"""第十一个研究循环第 5 轮（scripts/loop11_r05_gates.py）：标记 = 第十个循环的闸门同一个条件、只收紧、常量。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop11_r01_cycle as R1  # noqa: E402
import loop11_r05_gates as R  # noqa: E402


def test_round_constants():
    assert R.ROUND == 5 and R.IDS == ("HWT", "X2T", "JRT") and all(R.POSTHOC.values())
    assert R.MENU == {"flag": R1.TIGHT} and set(R.FAMILY.values()) == {"卖法·选股闸门改收紧"}


def test_flags_match_loop10_gates():
    X = pd.DataFrame({"date": pd.to_datetime(["2020-04-30", "2020-05-01", "2020-11-02", "2020-10-30"]),
                      "x2": [0.1, -0.2, np.nan, 0.0]})
    assert list(R.labels_of("HWT", X, None)) == ["base", "flag", "base", "flag"]
    assert list(R.labels_of("X2T", X, None)) == ["base", "flag", "base", "flag"]   # x2 ≤ 0；缺值 → B3
    days = pd.Series([False, True, False], index=pd.to_datetime(["2020-04-30", "2020-05-01", "2020-10-01"]))
    assert list(R.labels_of("JRT", X, days)) == ["base", "flag", "base", "base"]   # 之前最后一个值
