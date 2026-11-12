"""只描述的诊断 scripts/loop4_placebo_bar.py：随机挡 = research_loop4.random_signal_block 原样（种子与比例）、em_tick 的样子、汇总的分位与门槛 ÷ 上限。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop4_placebo_bar as T  # noqa: E402
import research_loop4 as R4  # noqa: E402


def test_constants():
    assert (T.P, T.N, T.CEILING) == (0.15, 400, 0.594)


def test_placebo_tick_uses_registered_random_block():
    A = pd.DataFrame({"ticker": [f"S{i}.T" for i in range(200)], "date": pd.bdate_range("2024-01-01", periods=200)})
    tk = T.placebo_tick(A, 7)
    g = R4.random_signal_block(200, 0.15, 7)
    assert len(tk) == int(g.sum()) and all(v == 0.0 for v in tk.values())
    assert set(tk) == {(f"S{i}.T", A["date"].iloc[i]) for i in np.flatnonzero(g)}
    assert tk == T.placebo_tick(A, 7) and tk != T.placebo_tick(A, 8)       # 同一个种子 = 同一个结果


def test_summarize():
    s = T.summarize([0.0, 0.01, 0.02, 0.05, 0.297], ceiling=0.594)
    assert s["max"] == pytest.approx(0.297) and s["bar_over_ceiling"] == pytest.approx(0.5)
    assert s["share_s1"] == pytest.approx(0.4) and s["p50"] == pytest.approx(0.02)
