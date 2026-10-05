"""只描述（scripts/loop11_cycle_describe.py）：一格的统计、「最好的卖法」、三个年代稳不稳。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop11_cycle_describe as R  # noqa: E402


def _frame(n, era, sector, tight, base, wide, cycle=20.0):
    return pd.DataFrame({"era": [era] * n, "sector": [sector] * n, "size": ["mid"] * n, "vol": ["low"] * n, "cycle": [cycle] * n,
                         "net_tight": tight, "net_base": base, "net_wide": wide})


def test_constants_reuse_registered_cuts():
    assert set(R.OPTIONS) == {"tight", "base", "wide"} and R.SIZE_CUTS == (9.1557, 9.5445) and R.VOL_CUTS == (0.0164, 0.0203)
    assert R.MIN_N == 10


def test_cell_best_and_small_sample():
    df = _frame(12, "Z", "cyc", np.full(12, 1.0), np.full(12, 2.0), np.r_[np.full(11, 3.0), np.nan])
    c = R.cell(df)
    assert c["n"] == 12 and c["n_trade"] == 11 and c["cycle_med"] == 20.0     # 有一个算不了 → 三套都只用 11 笔
    assert c["best"] == "wide" and c["wide"] == {"win": 100.0, "mean": 3.0}
    assert R.cell(df.iloc[:9])["best"] is None                                 # < 10 笔 → 不判
    tie = _frame(10, "Z", "cyc", np.full(10, 1.0), np.full(10, 1.0), np.full(10, 1.0))
    assert R.cell(tie)["best"] == "base"                                       # 平手 → B3


def test_stable_and_summarize():
    assert R.stable(["wide", "wide", "wide"]) == "wide" and R.stable(["wide", "base", "wide"]) == "年代间换"
    assert R.stable(["wide", None, "wide"]) == "样本不够"
    df = pd.concat([_frame(10, e, "def", np.full(10, 1.0), np.full(10, 0.5), np.full(10, 0.0)) for e in ("Z", "E", "J")], ignore_index=True)
    res = R.summarize(df)
    assert res["sector"]["def"]["stable"] == "tight" and res["sector"]["cyc"]["stable"] == "样本不够"
    assert res["all"]["all"]["n"] == 30
