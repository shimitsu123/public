"""scripts/state_model_diag.py（事后诊断，只描述）：信号日的找法、现行交易的拆分（过滤 / 没做 / 照做 / 新增）、随机去掉同样多笔与
业种标签置换的分位、秩相关的置换 p、分数按驱动组拆开（合计 = 1）、按分位判定过滤（业种不在横截面 → 照做）、持有期累计和。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import state_model_diag as DG  # noqa: E402


def test_signal_pos_is_last_signal_before_fill():
    idx = pd.bdate_range("2024-01-01", periods=10)
    en = np.zeros(10, bool)
    en[[2, 5]] = True
    assert DG.signal_pos(idx, en, idx[6]) == 5                                  # 第 5 天的信号 → 第 6 天成交
    assert DG.signal_pos(idx, en, idx[5]) == 2                                  # 成交日当天的信号不算（还没发生）
    assert DG.signal_pos(idx, en, idx[1]) is None


def test_split_trades_classifies_base_and_added():
    d = pd.to_datetime(["2024-01-05", "2024-02-05", "2024-03-05", "2024-04-05"])
    base = pd.DataFrame({"ticker": ["A", "B", "C", "D"], "entry_date": d, "net": [1.0, -2.0, 3.0, -4.0]})
    cand = pd.DataFrame({"ticker": ["A", "C", "E"], "entry_date": [d[0], d[2], pd.Timestamp("2024-04-06")], "net": [1.0, 3.0, 5.0]})
    sp = DG.split_trades(base, cand, [False, True, False, False])
    assert list(sp["过滤"]["ticker"]) == ["B"]
    assert list(sp["没做"]["ticker"]) == ["D"]                                   # 没被过滤、候选里却没有（组合路径变了）
    assert list(sp["照做"]["ticker"]) == ["A", "C"]
    assert list(sp["新增"]["ticker"]) == ["E"]
    assert len(sp["过滤却做了"]) == 0
    s = DG.stats(sp["照做"])
    assert s["n"] == 2 and s["win"] == 100.0 and s["mean"] == 2.0 and s["sum"] == 4.0
    assert DG.stats(sp["过滤"].iloc[:0])["n"] == 0


def test_pct_rank_and_perm_rank():
    assert DG.pct_rank(np.array([1.0, 2.0, 3.0, 4.0]), 2.5) == 50.0
    assert DG.pct_rank(np.array([1.0, 2.0, 2.0, 3.0]), 2.0) == 50.0             # 并列算一半
    net = np.array([-5.0, -4.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    worst = np.array([True, True, False, False, False, False, False, False])
    r = DG.perm_rank(net, worst, n_iter=500, seed=1)
    assert r["k"] == 2 and r["win"] == 100.0 and r["mean_pct"] > 95            # 去掉最差的 2 笔 → 在随机里几乎最好
    r2 = DG.perm_rank(net, worst, n_iter=500, seed=1)
    assert r == r2                                                              # 固定种子 → 可重现
    assert DG.perm_rank(net, np.zeros(8, bool))["k"] == 0


def test_spearman_perm():
    x = np.arange(20, dtype=float)
    r = DG.spearman_perm(x, x * 2 + 1, n_iter=999, seed=0)
    assert abs(r["rho"] - 1.0) < 1e-12 and r["p"] <= 0.002
    r2 = DG.spearman_perm(x, -x, n_iter=999, seed=0)
    assert abs(r2["rho"] + 1.0) < 1e-12 and r2["p"] <= 0.002                    # 双侧
    assert DG.spearman_perm([1.0, np.nan, 2.0], [1.0, 2.0, 3.0])["rho"] is None


def test_group_share_sums_to_one():
    names = ["OIL_up_D", "OIL_dn_D", "STEEL_up_D", "SALES_up", "CUS_dn"]
    rng = np.random.default_rng(0)
    Fi = rng.normal(size=(12, 5))
    Fi[3, 2] = np.nan                                                           # 有缺值的行不算
    sh = DG.group_share(Fi, np.array([0.5, -0.2, 0.3, 0.1, 0.4]), names)
    assert abs(sum(sh.values()) - 1.0) < 1e-9
    assert sh["NONFER"] == 0.0 and sh["FX"] == 0.0


def test_flags_from_uses_rank_cut_and_permutation():
    me = pd.to_datetime(["2024-01-31", "2024-01-31", "2024-02-29", "2024-02-29"])
    R = pd.DataFrame({"a": [0.2, 0.9], "b": [0.5, 0.1], "c": [0.9, 0.5]}, index=pd.to_datetime(["2024-01-31", "2024-02-29"]))
    f = DG.flags_from(R, me, ["a", "銀行業", "b", "c"], 1 / 3)
    assert list(f) == [True, False, True, False]                                # 业种不在横截面 → 照做
    fp = DG.flags_from(R, me, ["a", "銀行業", "b", "c"], 1 / 3, perm=[2, 0, 1])  # a 用 c 的、b 用 a 的、c 用 b 的
    assert list(fp) == [False, False, False, True]
    fp2 = DG.flags_from(R, me, ["a", "b", "c", "c"], 1 / 3, perm=[1, 2, 0])
    assert list(fp2) == [False, False, False, False]
    assert list(DG.flags_from(R, pd.to_datetime(["2023-12-31"]), ["a"], 1 / 3)) == [False]   # 没有分位的月份 → 照做


def test_perm_industry_reports_percentiles():
    me = pd.to_datetime(["2024-01-31"] * 6)
    R = pd.DataFrame({"a": [0.1], "b": [0.5], "c": [0.9]}, index=pd.to_datetime(["2024-01-31"]))
    ind = ["a", "a", "b", "b", "c", "c"]
    net = np.array([-5.0, -4.0, 1.0, 1.0, 2.0, 2.0])
    actual = DG.flags_from(R, me, ind, 1 / 3)
    r = DG.perm_industry(net, R, me, ind, 1 / 3, actual, n_iter=300, seed=0)
    assert r["win"] == 100.0 and r["mean_pct"] > 60                            # 挡掉的正好是最差的业种
    assert r["n"] == 300


def test_seg_sum_is_increment_over_half_open_interval():
    idx = pd.bdate_range("2024-01-01", periods=5)
    cum = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=idx).cumsum()             # 1, 3, 6, 10, 15
    assert DG.seg_sum(cum, idx[1], idx[3]) == 7.0                               # (第 1 天, 第 3 天] = 3 + 4
    assert DG.seg_sum(cum, idx[1], idx[4] + pd.Timedelta(days=1)) == 12.0      # 周六（不是交易日）→ 取之前最近的
    assert DG.tercile(0.2) == "低 1/3" and DG.tercile(0.5) == "中 1/3" and DG.tercile(0.9) == "高 1/3" and DG.tercile(float("nan")) is None
