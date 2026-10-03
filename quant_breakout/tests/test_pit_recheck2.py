"""时点名单复核（scripts/pit_recheck2.py，事后核对）：候选来自 w2mtf 的目录、开天眼标签只保留有标签且赚钱的信号、四条读法按事先写定的规则判。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pit_recheck2 as PR2                                                   # noqa: E402
import w2mtf_study as W                                                      # noqa: E402


def _pool(cur, q05, med, q95, o1=None, bar=None, cands=None):
    res = {PR2.CUR: {"calmar": cur}, PR2.NOW2: {"calmar": cur - 0.03}, PR2.O1: {"calmar": o1}}
    for k, v in (cands or {}).items():
        res[k] = {"calmar": v}
    return {"res": res, "placebo": {"q05": q05, "median": med, "q95": q95}, "bar": bar}


def test_candidates_and_pools():
    assert set(PR2.CANDS) <= set(W.VARIANTS) and W.VARIANTS["d1.5·W20/1·M0"] == {"kind": "and", "d": 1.5, "n": 20, "t": 1.0, "m": 0}
    assert W.VARIANTS["d2·W20/1·M0"]["d"] == 2.0 and PR2.SEEDS == 30 and PR2.GAIN == 0.02
    assert [p for e, p in PR2.POOLS if e == "J"] == ["today", "pit", "U1", "U2"] and set(PR2.POOL_ZH) == {"today", "pit", "U1", "U2"}


def test_oracle_keep_only_labelled_winners():
    idx = pd.bdate_range("2020-01-01", periods=5)
    fr = {"A": pd.DataFrame({"entry": [True, True, False, True, True]}, index=idx)}
    label = {("A", idx[0]): 1.5, ("A", idx[1]): -0.2, ("A", idx[3]): 0.0}     # idx[4] 没有标签
    k = PR2.oracle_keep(fr, label, lambda v: v > 0)
    assert k["A"].tolist() == [True, False, False, False, False]


def test_rules_pre_written():
    out = {"E/pit": _pool(0.31, 0.19, 0.25, 0.30, o1=0.35, bar=0.41, cands={"d1.5·W20/1·M0": 0.315, "d2·W20/1·M0": 0.34}),
           "J/pit": _pool(0.40, 0.34, 0.39, 0.44, cands={"d1.5·W20/1·M0": 0.41, "d2·W20/1·M0": 0.41}),
           "J/U1": _pool(0.30, 0.25, 0.29, 0.33, o1=0.60, bar=0.40),
           "J/U2": _pool(0.28, 0.20, 0.26, 0.27)}
    assert PR2.rule_r1(out)[0] and "不变" in PR2.rule_r1(out)[1]
    assert PR2.rule_r2(out)[0] == "不变（只等于随机）"                          # 中、中、高 → 中 ≥ 2
    ok, txt = PR2.rule_r3(out)
    assert ok and "没有优化方向" in txt                                        # 第二个候选 E +0.03 但 J 只 +0.01 → 不算
    out4 = dict(out)
    out4["J/pit"] = _pool(0.40, 0.34, 0.39, 0.44, cands={"d1.5·W20/1·M0": 0.41, "d2·W20/1·M0": 0.43})
    ok4, txt4 = PR2.rule_r3(out4)
    assert not ok4 and "有差别" in txt4 and "突破日 ≥ 2 倍" in txt4             # E +0.03、J +0.03 → 有差别
    out2 = dict(out)
    out2["E/pit"] = _pool(0.31, 0.19, 0.25, 0.32, o1=0.42, bar=0.41, cands={"d1.5·W20/1·M0": 0.315, "d2·W20/1·M0": 0.32})
    assert not PR2.rule_r1(out2)[0] and "变弱" in PR2.rule_r1(out2)[1]
    assert not PR2.rule_r4(out2)[0] and "要改" in PR2.rule_r4(out2)[1]
    assert PR2.rule_r4(out)[0]
    out3 = dict(out)
    out3["J/U1"] = _pool(0.36, 0.25, 0.29, 0.33, o1=0.60, bar=0.40)
    out3["J/U2"] = _pool(0.30, 0.20, 0.26, 0.27)
    assert PR2.rule_r2(out3)[0] == "时点池上反而成立"                             # 中、高、高
    assert PR2.gains(out, "d2·W20/1·M0") == {"E": 0.03, "J": 0.01}
