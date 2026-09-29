"""scripts/deepdip_regime_posthoc.py（深跌加仓在牛 / 熊的事后描述）：事件日的牛熊状态向前取、分组统计、熊 − 牛 的差按大跌段整段重抽可重现。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import deepdip_regime_posthoc as RP                                          # noqa: E402


def test_state_on_uses_last_known_state():
    bear = pd.Series([False, True, True], index=pd.to_datetime(["2020-03-06", "2020-03-12", "2020-03-13"]))
    assert RP.state_on(bear, "2020-03-10") is False and RP.state_on(bear, "2020-03-12") is True
    assert RP.state_on(bear, "2020-03-01") is False


def test_summarize_and_diff_ci():
    rows = [{"date": f"20{i:02d}-01-01", "x60": 2.0, "xe60": 2.0, "r60": 3.0, "mae60": -5.0, "r120": 4.0, "r20": 1.0, "bear": True}
            for i in range(6)]
    rows += [{"date": f"19{i + 70:02d}-06-01", "x60": -1.0, "xe60": -1.0, "r60": -1.0, "mae60": -9.0, "r120": 0.0, "r20": 0.0, "bear": False}
             for i in range(4)]
    s = RP.summarize([r for r in rows if r["bear"]])
    assert s == {"n": 6, "x60": 2.0, "xe60": 2.0, "win": 100.0, "mae60": -5.0, "r120": 4.0, "r20": 1.0}
    assert RP.summarize([]) == {"n": 0}
    a, b = RP.diff_ci(rows, n_boot=500), RP.diff_ci(rows, n_boot=500)
    assert a == b and a["diff"] == 3.0 and a["episodes"] == 10 and a["lo"] <= 3.0 <= a["hi"]
    assert RP.diff_ci(rows[:7])["diff"] is None                              # 牛只有 1 个
    assert np.isclose(RP.diff_ci(rows, n_boot=200)["diff"], 3.0)
