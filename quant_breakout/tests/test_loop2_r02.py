"""第二个研究循环第 2 轮 TBH（scripts/loop2_r02_bondrefuge.py，2026-10-02 登记）：登记值、平价债总收益、债券牛熊用模拟盘同一个检测器、
接法（债券从不是牛 = B1）、只有核心的持仓、费用表里的 1482。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop2_r02_bondrefuge as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.BOND_T, T.BD_KEY) == (2, ("TBH",), "核心·熊市避险资产", True, "1482.T", "US_BD")
    assert (T.TENOR, T.TRUST_FEE, T.BASIS, T.REF_DATE, T.REF_PX, T.BOND_START, T.OLD) == (
        8.5, 0.154, 0.6, "2026-08-31", 1537.0, "1986-01-01", ("1987-01-01", "2000-12-31"))


def test_par_bond_carry_and_duration():
    idx = pd.bdate_range("2020-01-01", periods=4)
    flat = T.par_bond_tr(pd.Series([4.0, 4.0, 4.0, 4.0], index=idx))
    dt = np.diff(idx.to_numpy()).astype("timedelta64[D]").astype(float) / 365.0
    assert np.allclose(flat.pct_change().dropna().to_numpy(), 0.04 * dt)                 # 收益率不变 → 只有票息
    up = T.par_bond_tr(pd.Series([4.68, 4.78], index=idx[:2]))
    r = float(up.iloc[-1] - 1) - 0.0468 / 365
    assert -0.0075 < r < -0.0065                                                        # +10 bp → 约 −0.7%（有效久期约 7 年，1482 是 6.96 年）


def test_trend_uses_the_sim_detector():
    import json
    det = json.loads((Path(__file__).resolve().parents[1] / "var" / "bullbear.json").read_text(encoding="utf-8"))["detector"]
    assert det == {"kind": "ma_band", "params": {"L": 250, "b": 0.03, "k": 5}}           # 模拟盘的美股牛熊分界同一组参数
    idx = pd.bdate_range("2000-01-03", periods=400)
    rise = pd.Series(np.linspace(100, 140, 400), index=idx)
    on = T.trend_on(rise, det)
    assert not on.iloc[:249].any() and on.iloc[260:].all()                              # 250 日线算出来之前 = 不拿
    fall = pd.concat([rise, pd.Series(np.linspace(139, 100, 120), index=pd.bdate_range(idx[-1] + pd.Timedelta(days=1), periods=120))])
    assert not T.trend_on(fall, det).iloc[-1]


def test_never_bull_bond_equals_b1_wiring():
    import loop_r04_yensurge as Y
    idx = pd.bdate_range("2020-01-01", periods=6)
    bear = pd.Series([False, True, True, False, True, True], index=idx)
    o = T.tbh_over(bear, pd.Series(False, index=idx), pd.DataFrame({"Close": [1.0]}, index=[idx[0]]))
    assert o["cfg_over"]["core_mode"] == "follow" and o["cfg_over"]["core_index"] == {"1545.T": Y.UH_KEY, "2845.T": Y.HG_KEY, "1482.T": "US_BD"}
    assert o["extra_bear"]["US_BD"].all() and set(o["extra_core"]) == {"1482.T"}       # 债券一直「熊」→ 1482 目标 0 = B1
    on = pd.Series([True, True, False, True, True, True], index=idx)
    o2 = T.tbh_over(bear, on, pd.DataFrame({"Close": [1.0]}, index=[idx[0]]))
    assert (~o2["extra_bear"]["US_BD"]).tolist() == [False, True, False, False, True, True]   # 美股熊且债券牛才拿
    assert T.held(bear, on, idx).tolist() == [False, True, False, False, True, True]
    assert T.segments(T.held(bear, on, idx)) == 2


def test_core_weights_three_states():
    idx = pd.bdate_range("2020-01-01", periods=4)
    w = T.core_weights(pd.Series([False, False, True, True], index=idx), pd.Series([False, True, False, False], index=idx),
                       pd.Series([True, True, True, False], index=idx))
    assert w.to_numpy().tolist() == [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]]            # 牛不对冲 / 牛对冲 / 熊且债券牛 / 熊 → 现金


def test_fee_table_has_1482():
    from qbreak.fees import etf_cost
    c = etf_cost("tachibana", "1482.T", "JP")
    assert c["lot"] == 1 and c["slip_pct"] == 0.05
