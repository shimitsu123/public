"""B・N・F 的逻辑（scripts/bnf_study.py 登记检验）：25 日线乖离、卖出判定、业种中位数（出遅れ）、四个候选的成立条件、卖法参数、
判定规则（通过 / 只在他的年代成立 / 不通过）、逐笔（同一只票不重叠、最多 5 天）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bnf_study as B                                                        # noqa: E402


def test_dev25_uses_only_past_and_today():
    c = pd.Series(np.r_[np.full(30, 100.0), 70.0])
    d = B.dev25(c)
    assert d.iloc[:24].isna().all() and abs(d.iloc[29]) < 1e-12
    assert abs(d.iloc[30] - (70 / ((24 * 100 + 70) / 25) - 1)) < 1e-12                  # 均线含当天
    c2 = pd.concat([c, pd.Series([200.0])], ignore_index=True)
    assert abs(B.dev25(c2).iloc[30] - d.iloc[30]) < 1e-12                               # 之后的数据不影响之前


def test_exit_signal_threshold():
    d = pd.Series([np.nan, -0.25, -0.1000001, -0.10, 0.02])
    assert list(B.exit_signal(d)) == [False, False, False, True, True]


def test_sector_median_needs_three_members():
    R = pd.DataFrame({"A": [0.01, 0.03], "B": [0.02, -0.01], "C": [0.05, 0.00], "D": [0.10, 0.10], "E": [0.2, 0.2]})
    S = B.sector_median(R, {"A": "x", "B": "x", "C": "x", "D": "y", "E": "y"})
    assert list(S["A"]) == [0.02, 0.0] and list(S["C"]) == [0.02, 0.0]
    assert S["D"].isna().all()                                                          # 业种里只有 2 只 → 不算


def test_candidate_masks():
    dev = np.array([-0.35, -0.25, -0.21, -0.19, np.nan])
    panic = np.array([True, False, True, True, True])
    sm = np.array([0.02, 0.005, 0.012, 0.03, 0.03])
    own = np.array([-0.01, -0.02, 0.001, -0.01, -0.01])
    assert list(B.cand_mask("B20", dev, panic, sm, own)) == [True, True, True, False, False]
    assert list(B.cand_mask("B30", dev, panic, sm, own)) == [True, False, False, False, False]
    assert list(B.cand_mask("BP", dev, panic, sm, own)) == [True, False, True, False, False]
    assert list(B.cand_mask("BL", dev, panic, sm, own)) == [True, False, False, False, False]   # 第 2 天业种没反弹、第 3 天自己涨了


def test_bnf_params():
    from qbreak.config import StrategyParams
    pp = B.bnf_params(StrategyParams())
    assert (pp.stop_loss_pct, pp.max_hold_days, pp.take_profit_pct, pp.trailing_stop_pct) == (10.0, 5, 0.0, 0.0)
    assert pp.exit_on_macd_dead_cross and not pp.exit_on_climax and not pp.exit_before_earnings


def _acct(z=0.20, e=0.30, j=0.40, dd=-20.0):
    return {"Z": {"calmar": z, "dd": dd}, "E": {"calmar": e, "dd": dd}, "J": {"calmar": j, "dd": dd}}


def test_verdict_rules():
    tr = {k: {"n": 40, "mean": 0.5} for k in B.ERAS}
    base = _acct()
    assert B.verdict(tr, {"lo": 0.1}, _acct(0.21, 0.33, 0.43), base) == ("通过", [])
    lab, f = B.verdict(tr, {"lo": -0.1}, _acct(0.21, 0.33, 0.43), base)
    assert lab == "只在他的年代成立" and any("95% 下限" in x for x in f)
    lab, f = B.verdict(tr, {"lo": 0.1}, _acct(0.21, 0.31, 0.43), base)                   # E 只高 0.01
    assert lab == "只在他的年代成立" and any(x.startswith("b E Calmar") for x in f)
    lab, f = B.verdict(tr, {"lo": 0.1}, _acct(0.19, 0.33, 0.43), base)                   # Z 账户比现行低
    assert lab == "不通过" and "b Z Calmar 低于现行" in f
    tr2 = {**tr, "J": {"n": 12, "mean": 2.0}}
    lab, f = B.verdict(tr2, {"lo": 0.1}, _acct(0.21, 0.33, 0.43), base)
    assert lab == "只在他的年代成立" and any("只有 12 笔" in x for x in f)
    tr4 = {**tr, "Z": {"n": 12, "mean": 1.5}}                                        # Z 笔数不够 → 够不上「只在他的年代成立」
    assert B.verdict(tr4, {"lo": 0.1}, _acct(0.21, 0.33, 0.43), base)[0] == "不通过"
    tr3 = {**tr, "Z": {"n": 40, "mean": -0.1}}
    assert B.verdict(tr3, {"lo": 0.1}, _acct(0.21, 0.33, 0.43), base)[0] == "不通过"
    lab, f = B.verdict(tr, {"lo": 0.1}, _acct(0.21, 0.33, 0.43, dd=-23.0), base)         # 回撤深 3 pp
    assert lab == "只在他的年代成立" and any("回撤" in x for x in f)


def test_solo_trades_do_not_overlap_and_hold_at_most_five_days():
    from qbreak.config import StrategyParams
    from qbreak.strategy import compute_indicators
    import sell_confirm as SCF
    n = 160
    idx = pd.bdate_range("2021-01-04", periods=n)
    c = np.full(n, 1000.0)
    c[100:106] = [900, 820, 760, 740, 745, 760]                                         # 急跌 → 25 日线乖离 ≤ −20%
    c[106:] = 780.0
    df = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6}, index=idx)
    p = StrategyParams()
    fa = {"A.T": compute_indicators(df, p)}
    dev = B.dev25(fa["A.T"]["Close"])
    m = {"A.T": B.cand_mask("B20", dev.to_numpy(float), np.zeros(n, bool), np.full(n, np.nan), np.full(n, np.nan))}
    assert m["A.T"].sum() >= 2                                                          # 连续几天都成立
    ex = {"A.T": B.exit_signal(dev)}
    bt = SCF.bt_single()
    T = B.solo_trades(fa, m, ex, B.bnf_params(p), bt, 0.0, idx[0], idx[-1])
    assert len(T) >= 1 and (T["hold"] <= 5).all()
    ds = list(pd.to_datetime(T["date"]))
    assert ds == sorted(ds) and len(set(ds)) == len(ds)
