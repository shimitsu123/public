"""第七个研究循环（scripts/research_loop7.py，2026-10-04 登记）：登记的常数、横展开第二关的纯函数（平移、净值、Calmar、两半、判定）、
做法的检查（家族 / kind / ID / 上限）、登记的先决条件与状态文件。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_loop7 as R7  # noqa: E402


def test_registered_constants():
    assert (R7.CAP, R7.FAMILY_CAP, R7.PLACEBO_N, R7.LOOP_SEED, R7.SHIFT_GAP) == (10, 3, 400, 20261007, 250)
    assert R7.WINDOW == ("1998-01-01", "2026-09-30") and R7.DATA_START_MAX == "1996-06-30" and R7.COST == 0.1
    assert R7.SHARE_MIN == pytest.approx(2 / 3) and R7.FP_SEG3 == "3b2e8757be7b4a74" and R7.FAMILY_PREFIX == "核心"
    assert list(R7.MARKETS) == ["JP", "DE", "GB", "FR", "CH", "NL", "ES", "BE", "AT", "AU", "HK", "SG", "CA", "BR", "MX", "MY", "ID"]
    assert R7.SOURCE == {"US": ("^GSPC", "美国 S&P 500（规则来源，只描述）")} and "US" not in R7.MARKETS
    assert "research_loop6.json" in R7.PREV_FILES


def test_shift_ks_deterministic_and_in_range():
    ks = R7.shift_ks(6980)
    assert len(ks) == 400 and min(ks) >= 250 and max(ks) <= 6980 - 250
    assert ks[:3] == [int(np.random.default_rng([20261007, 0, s]).integers(250, 6980 - 250 + 1)) for s in range(3)]
    with pytest.raises(ValueError):
        R7.shift_ks(400)


def test_shifted_only_inside_window():
    idx = pd.bdate_range("1997-12-25", "1998-01-09")
    s = pd.Series([True, False, False, False, False, True, False, False, False, False, False, False], index=idx)
    out = R7.shifted(s, 1, ("1998-01-01", "1998-01-09"))
    w = idx >= pd.Timestamp("1998-01-01")
    assert out[~w].tolist() == s[~w].tolist()
    assert out[w].tolist() == np.roll(s[w].to_numpy(), 1).tolist()
    assert R7.shifted(s, None).equals(s)


def test_nav_lag_and_cost():
    idx = pd.bdate_range("2020-01-01", periods=4)
    c = pd.Series([100.0, 110.0, 99.0, 99.0], index=idx)
    e = pd.Series([1.0, 1.0, 0.5, 0.5], index=idx)
    nv = R7.nav(c, e, cost=0.1)
    k = 0.001
    assert nv.iloc[0] == pytest.approx(1.0)                                     # 第一天还没持仓
    assert nv.iloc[1] == pytest.approx((1 + 0.10) * (1 - k))                     # 第一天收盘决定 → 第二天起 100%（买进扣 0.1%）
    assert nv.iloc[2] == pytest.approx(nv.iloc[1] * (1 + (99 / 110 - 1)))
    assert nv.iloc[3] == pytest.approx(nv.iloc[2] * (1 - 0.5 * k))              # 第三天收盘减到 0.5 → 第四天生效


def test_calmar_and_halves():
    idx = pd.bdate_range("2000-01-03", periods=600)
    v = np.ones(600)
    v[:300] = np.linspace(1.0, 1.2, 300)
    v[300:400] = np.linspace(1.2, 0.9, 100)
    v[400:] = np.linspace(0.9, 1.5, 200)
    nv = pd.Series(v, index=idx)
    yrs = (idx[-1] - idx[0]).days / 365.25
    assert R7.calmar(nv, str(idx[0].date()), str(idx[-1].date())) == pytest.approx((1.5 ** (1 / yrs) - 1) / 0.25)
    assert R7.calmar(nv.iloc[:100], "2000-01-01", "2030-01-01") is None        # 不够 250 天
    assert R7.calmar(pd.Series(np.linspace(1, 2, 300), index=idx[:300]), "2000-01-01", "2030-01-01") is None   # 没有回撤
    (a1, b1), (a2, b2) = R7.halves(idx)
    assert (a1, b1, a2, b2) == (str(idx[0].date()), str(idx[299].date()), str(idx[300].date()), str(idx[-1].date()))


def test_judge_rules():
    real = {f"m{i}": [0.05, 0.02, 0.03] for i in range(12)} | {f"n{i}": [-0.01, 0.01, -0.01] for i in range(5)}
    pooled = np.mean([v[0] for v in real.values()])
    ok = R7.judge(real, [pooled - 0.001] * 400)
    assert ok["ok"] and ok["C1"] and ok["C2"] and ok["C3"] and ok["positive"] == 12 and ok["need"] == 12 and ok["ge_stat"] == 0
    assert not R7.judge(real, [pooled] * 400)["C1"]                            # 严格大于（相等 = 不过）
    real2 = dict(real)
    real2["m0"] = [-0.2, 0.02, 0.03]                                            # 只剩 11 个为正
    assert not R7.judge(real2, [-1.0] * 400)["C2"]
    real3 = {k: [v[0], -0.5, v[2]] for k, v in real.items()}                    # 前一半为负
    assert not R7.judge(real3, [-1.0] * 400)["C3"]
    assert not R7.judge(real, [None] + [-1.0] * 399)["ok"]                      # 有算不出的 = 不过
    assert not R7.judge({**real, "x": [None, 0.1, 0.1]}, [-1.0] * 400)["ok"]


def test_check_new_approaches_and_add_round():
    st = {"status": "running", "cap": 10, "rounds": []}
    good = {"id": "ZZX", "family": "核心·波动率", "posthoc": True, "kind": "cross"}
    R7.check_new_approaches(st, [good], prev=set())
    for bad, msg in (({**good, "family": "选股·x"}, "核心层"), ({**good, "kind": "signal"}, "横展开"), ({**good, "posthoc": None}, "事后"),
                     ({**good, "id": "VCT"}, "用过")):
        with pytest.raises(ValueError, match=msg):
            R7.check_new_approaches(st, [bad], prev={"VCT"})
    three = [{**good, "id": f"Z{i}X"} for i in range(4)]
    with pytest.raises(ValueError, match="超过"):
        R7.check_new_approaches(st, three, prev=set())
    st2 = R7.add_round(st, {"round": 1, "approaches": [{**good, "verdict": R7.FAIL2}]}, prev=set())
    assert R7.used(st2) == 1 and R7.derive_status(st2) == "running"
    with pytest.raises(ValueError, match="用过"):
        R7.add_round(st2, {"round": 2, "approaches": [{**good, "verdict": R7.FAIL2}]}, prev=set())


def test_init_state_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(R7.RL, "rules_fingerprint", lambda home=None: "zzz")
    with pytest.raises(ValueError, match="不登记"):
        R7.init_state(tmp_path)
    monkeypatch.setattr(R7.RL, "rules_fingerprint", lambda home=None: R7.FP_SEG3)
    st = R7.init_state(tmp_path)
    assert st["status"] == "running" and st["cap"] == 10 and st["markets"] == list(R7.MARKETS) and st["kinds"] == ["cross"]
    assert R7.init_state(tmp_path) == st                                       # 已存在就不动
    assert "第七个研究循环" in R7.status_text(st) and "还没有登记" in R7.status_text({})


def test_registered_state_file_if_present():
    st = R7.load_state(ROOT / "var")
    if not st:
        pytest.skip("还没有登记")
    assert st["fingerprint"] == R7.FP_SEG3 and st["window"] == list(R7.WINDOW) and st["markets"] == list(R7.MARKETS)
    assert st["cap"] == R7.CAP and st["family_cap"] == R7.FAMILY_CAP and st["seed"] == R7.LOOP_SEED
