"""第 13 轮诊断（scripts/leap_r13_oracle.py、leap_r13b_required.py）：按事后标签保留信号、按目标胜率抽信号。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leap_r13_oracle as O  # noqa: E402
import leap_r13b_required as R  # noqa: E402


def _fr():
    idx = pd.bdate_range("2020-01-06", periods=6)
    return {"A.T": pd.DataFrame({"entry": [True, False, True, False, True, False]}, index=idx),
            "B.T": pd.DataFrame({"entry": [False, True, False, True, False, True]}, index=idx)}


def test_oracle_keep_only_labeled_entries_passing_rule():
    fr = _fr()
    d = fr["A.T"].index
    label = {("A.T", d[0]): 3.0, ("A.T", d[2]): -1.0, ("B.T", d[1]): 0.5, ("B.T", d[2]): 9.0}   # B 在 d[2] 没有信号 → 不算
    k = O.oracle_keep(fr, label, lambda v: v > 0)
    assert k["A.T"].tolist() == [True, False, False, False, False, False]                          # d[4] 没有标签 → 不做
    assert k["B.T"].tolist() == [False, True, False, False, False, False]


def test_mix_keep_hits_target_win_rate_and_count():
    fr = _fr()
    d = fr["A.T"].index
    label = {("A.T", d[0]): 1.0, ("A.T", d[2]): 2.0, ("A.T", d[4]): -1.0, ("B.T", d[1]): -2.0, ("B.T", d[3]): -3.0, ("B.T", d[5]): 4.0}
    for seed in range(5):
        k = R.mix_keep(fr, label, 4, 0.5, seed)
        kept = [(t, d[i]) for t in k for i in np.flatnonzero(k[t])]
        assert len(kept) == 4 and sum(label[x] > 0 for x in kept) == 2
    k = R.mix_keep(fr, label, 4, 1.0, 0)                                                           # 只有 3 个赚钱的 → 全用、不配亏钱的
    kept = [(t, d[i]) for t in k for i in np.flatnonzero(k[t])]
    assert len(kept) == 3 and all(label[x] > 0 for x in kept)
    k = R.mix_keep(fr, label, 8, 0.75, 0)                                                          # 要 6 个赚钱的只有 3 个 → 3 + 1（胜率仍 75%）
    kept = [(t, d[i]) for t in k for i in np.flatnonzero(k[t])]
    assert len(kept) == 4 and sum(label[x] > 0 for x in kept) == 3
    a, b = R.mix_keep(fr, label, 4, 0.5, 1), R.mix_keep(fr, label, 4, 0.5, 1)
    assert all((a[t] == b[t]).all() for t in a)                                                    # 同一个种子 → 同一个结果
