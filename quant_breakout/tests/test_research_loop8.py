"""第八个研究循环（新的独立信息来源）的规则代码（scripts/research_loop8.py，2026-10-04 登记）：信息检查的函数（月末、之后的收益、
秩相关、联合区块自助法、I1〜I3 判定）与状态文件（先决条件、来源 / 结论 / ID / 上限的检查）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_loop8 as L8  # noqa: E402


def test_registered_constants():
    assert (L8.CAP, L8.FAMILY_CAP, L8.H, L8.INFO_ALPHA, L8.BOOT_REPS, L8.BOOT_BLOCK) == (10, 3, 63, 0.10, 2000, 12)
    assert L8.FP == "3b2e8757be7b4a74" and L8.FAIL_INFO == "信息检查不过" and L8.VERDICTS[-1] == L8.FAIL_INFO
    assert L8.SOURCES == ("期权·波动风险溢价", "杠杆·融资余额", "资金流·投资部门别", "卖空·空売り比率")
    assert "research_loop7.json" in L8.PREV_FILES and "research_loop6.json" in L8.PREV_FILES


def test_month_ends_done_drops_unfinished_month():
    idx = pd.bdate_range("2024-01-01", "2024-03-15")
    c = pd.Series(np.arange(len(idx), dtype=float) + 1, index=idx)
    me = L8.month_ends_done(c)
    assert list(me) == [pd.Timestamp("2024-01-31"), pd.Timestamp("2024-02-29")]
    assert len(L8.month_ends_done(pd.Series(dtype=float))) == 0


def test_fwd_log_ret_starts_next_day():
    idx = pd.bdate_range("2024-01-01", periods=10)
    c = pd.Series(np.exp(np.arange(10) * 0.01), index=idx)
    f = L8.fwd_log_ret(c, pd.DatetimeIndex([idx[2], idx[7]]), h=3)
    assert f.iloc[0] == pytest.approx(0.03)                                   # 第 3 天收盘 → 第 6 天收盘（从下一天起 3 天）
    assert np.isnan(f.iloc[1])                                                # 不够 3 天 → 空


def test_spearman_and_pooled():
    x = np.arange(30.0)
    assert L8.spearman(x, x ** 3) == pytest.approx(1.0) and L8.spearman(x, -x) == pytest.approx(-1.0)
    assert L8.spearman(x[:20], x[:20]) is None                               # 不到 24 对
    assert L8.spearman(x, np.ones(30)) is None
    y = x.copy()
    y[5] = np.nan
    assert L8.spearman(x, y) == pytest.approx(1.0)
    assert L8.pooled({"a": 0.2, "b": None, "c": 0.0}) == pytest.approx(0.1) and L8.pooled({"a": None}) is None


def _samples(rho, n=240, seed=0, start="1995-01-31"):
    g = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="ME")
    x = g.normal(size=n)
    y = rho * x + np.sqrt(1 - rho ** 2) * g.normal(size=n)
    return pd.DataFrame({"x": x, "y": y}, index=idx)


def test_joint_bootstrap_centered_and_reproducible():
    S = {m: _samples(0.3, seed=i) for i, m in enumerate("ABC")}
    b1 = L8.joint_bootstrap(S, reps=300, seed=7)
    b2 = L8.joint_bootstrap(S, reps=300, seed=7)
    assert np.array_equal(b1, b2) and np.isfinite(b1).all()
    assert 0.2 < np.median(b1) < 0.4 and (b1 <= 0).mean() < 0.01
    S0 = {m: _samples(0.0, seed=10 + i) for i, m in enumerate("ABC")}
    b0 = L8.joint_bootstrap(S0, reps=300, seed=7)
    assert abs(np.median(b0)) < 0.1


def test_info_judge_rules():
    boot = np.full(100, 0.05)
    boot[:5] = -0.01                                                          # p = 0.05
    ok = L8.info_judge({"a": 0.1, "b": 0.05, "c": -0.02}, {"a": 0.02, "b": 0.01, "c": 0.0}, boot)
    assert ok["ok"] and ok["I1"] and ok["I2"] and ok["I3"] and ok["agree"] == 2 and ok["need"] == 2 and ok["p"] == pytest.approx(0.05)
    weak = L8.info_judge({"a": 0.1, "b": 0.05, "c": -0.02}, {"a": 0.02, "b": 0.01, "c": 0.0}, np.r_[np.full(80, 0.05), np.full(20, -0.01)])
    assert not weak["I1"] and not weak["ok"]                                  # p = 0.20 > 0.10
    split = L8.info_judge({"a": 0.1, "b": -0.05, "c": -0.02}, {"a": 0.1, "b": 0.1, "c": 0.1}, boot)
    assert not split["I2"]                                                    # 1 / 3 一致 < 2
    post = L8.info_judge({"a": 0.1, "b": 0.05, "c": 0.02}, {"a": -0.1, "b": -0.1, "c": 0.0}, boot)
    assert not post["I3"] and not post["ok"]
    neg = L8.info_judge({"a": -0.1, "b": -0.05}, {"a": -0.1, "b": -0.1}, -boot, sign=-1)
    assert neg["ok"]                                                          # 文献方向为负的来源
    one = L8.info_judge({"a": 0.1}, {"a": 0.1}, boot, halves=(0.05, 0.02))
    assert one["I2"] and not L8.info_judge({"a": 0.1}, {"a": 0.1}, boot, halves=(0.05, -0.02))["I2"]


def test_state_init_requires_fingerprint_and_round_checks(tmp_path, monkeypatch):
    import research_loop as RL
    monkeypatch.setattr(RL, "rules_fingerprint", lambda home=None: "deadbeef")
    with pytest.raises(ValueError):
        L8.init_state(tmp_path)
    monkeypatch.setattr(RL, "rules_fingerprint", lambda home=None: L8.FP)
    st = L8.init_state(tmp_path)
    assert st["status"] == "running" and st["cap"] == 10 and L8.load_state(tmp_path)["fingerprint"] == L8.FP
    a = {"id": "VRN", "family": "期权·波动风险溢价", "posthoc": False, "verdict": L8.FAIL_INFO}
    st2 = L8.add_round(st, {"round": 1, "approaches": [a]}, prev=set())
    assert L8.used(st2) == 1 and L8.derive_status(st2) == "running"
    with pytest.raises(ValueError):
        L8.add_round(st2, {"round": 2, "approaches": [{**a, "id": "VRN"}]}, prev=set())                 # ID 重复
    with pytest.raises(ValueError):
        L8.add_round(st2, {"round": 2, "approaches": [{**a, "id": "X1", "family": "核心·波动率"}]}, prev=set())   # 不是登记的来源
    with pytest.raises(ValueError):
        L8.add_round(st2, {"round": 2, "approaches": [{**a, "id": "X1", "verdict": "差不多"}]}, prev=set())
    with pytest.raises(ValueError):
        L8.add_round(st2, {"round": 2, "approaches": [{**a, "id": "VSX"}]}, prev={"VSX"})            # 以前的循环用过
    with pytest.raises(ValueError):
        L8.add_round(st2, {"round": 3, "approaches": [{**a, "id": "X1"}]}, prev=set())               # 轮次号不接着
    st3 = L8.add_round(st2, {"round": 2, "approaches": [{**a, "id": "X1"}, {**a, "id": "X2"}]}, prev=set())
    with pytest.raises(ValueError):
        L8.add_round(st3, {"round": 3, "approaches": [{**a, "id": "X3"}]}, prev=set())              # 同一来源 > 3
    found = L8.add_round(st2, {"round": 2, "approaches": [{**a, "id": "Y1", "family": "杠杆·融资余额", "verdict": L8.FOUND}]}, prev=set())
    assert L8.derive_status(found) == "found"
    assert "第八个研究循环" in L8.status_text(found)
