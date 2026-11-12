"""第三个研究循环第 10 轮 RMO / FIP（scripts/loop3_r10_resmom.py，2026-10-02 登记）：登记值、月收益、残差动量的方向与历史不够时 NaN、
路径连续性 ID 的方向、横截面中位数挡一半（NaN 不挡）、信号日用前一个月的值、em_tick 只给下一个月的交易日、接线与命令行。"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop3_r10_resmom as T  # noqa: E402
import research_loop3 as R3  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.REG_M, T.REG_MIN, T.FORM_M) == (10, ("RMO", "FIP"), False, "stock", 36, 24, 11)
    assert T.FAMILY == {"RMO": "选股·动量质量", "FIP": "选股·动量质量"}
    assert T.KIND in R3.KINDS and not set(T.IDS) & R3.previous_ids(ROOT / "var")
    st = json.loads((ROOT / "var" / "research_loop3.json").read_text(encoding="utf-8"))
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:                                                                  # 结果已记进状态文件
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        used = {a["id"] for r in st.get("rounds") or [] for a in r.get("approaches") or []}
        assert not set(T.IDS) & used and R3.family_counts(st).get("选股·动量质量", 0) + 2 <= R3.FAMILY_CAP
        assert R3.used(st) + len(T.IDS) <= R3.CAP


def _months(n, start="2015-01"):
    return pd.period_range(start, periods=n, freq="M")


def test_monthly_ret_uses_month_end_close():
    idx = pd.to_datetime(["2024-01-30", "2024-01-31", "2024-02-28", "2024-02-29", "2024-03-29"])
    r = T.monthly_ret(pd.Series([10.0, 11.0, 12.0, 13.2, 6.6], index=idx))
    assert list(r.index.astype(str)) == ["2024-01", "2024-02", "2024-03"]
    assert np.isnan(r.iloc[0]) and r.iloc[1] == pytest.approx(0.2) and r.iloc[2] == pytest.approx(-0.5)


def test_resid_mom_sign_and_history():
    rng = np.random.default_rng(1)
    m = _months(48)
    rm = pd.Series(rng.normal(0.005, 0.04, 48), index=m)
    noise = rng.normal(0, 0.01, 48)
    up = 1.2 * rm + noise
    up.iloc[-12:-1] += 0.03                                                   # 形成期（t−11〜t−1）每月多 +3%
    dn = 1.2 * rm + noise
    dn.iloc[-12:-1] -= 0.03
    a, b = T.resid_mom(up, rm), T.resid_mom(dn, rm)
    assert a.iloc[-1] > 2 and b.iloc[-1] < -2
    assert a.iloc[:T.REG_MIN - 1].isna().all()                                 # 回归不到 24 个月 → NaN
    short = up.copy()
    short.iloc[-5] = np.nan                                                   # 形成期缺一个月 → NaN
    assert np.isnan(T.resid_mom(short, rm).iloc[-1])


def test_info_discreteness_continuous_vs_jumpy():
    idx = pd.bdate_range("2023-01-02", "2024-12-31")
    smooth = pd.Series(100 * np.cumprod(np.full(len(idx), 1.001)), index=idx)     # 每天小涨
    r = np.full(len(idx), -0.001)
    r[::40] = 0.08                                                            # 几次跳涨、其余小跌，合计仍上涨
    jumpy = pd.Series(100 * np.cumprod(1 + r), index=idx)
    months = pd.period_range("2023-01", "2024-12", freq="M")
    a, b = T.info_discreteness(smooth, months), T.info_discreteness(jumpy, months)
    assert a.iloc[-1] == pytest.approx(-1.0, abs=0.06)                        # 连续：几乎全是上涨日 → ID ≈ −1
    assert b.iloc[-1] > 0.8 and np.isnan(a.iloc[5])                           # 跳涨：下跌日多 → ID 大；不满 11 个月 → NaN


def test_blocked_half_and_gate_uses_previous_month():
    m = _months(2, "2024-01")
    S = pd.DataFrame({"A.T": [3.0, 1.0], "B.T": [1.0, 2.0], "C.T": [2.0, np.nan], "D.T": [0.0, 3.0]}, index=m)
    br = T.blocked_months(S, "RMO")
    assert list(br.iloc[0]) == [False, True, False, True]                     # 中位数 1.5：低于的挡
    assert list(br.iloc[1]) == [True, False, False, False]                    # NaN 不挡；中位数 2 本身不挡
    bf = T.blocked_months(S, "FIP")
    assert list(bf.iloc[0]) == [True, False, True, False]
    g = T.gate_of(br, ["A.T", "B.T", "B.T", "Z.T"], ["2024-02-01", "2024-02-28", "2024-01-31", "2024-02-05"])
    assert list(g) == [False, True, False, False]                             # 2 月的信号用 1 月的行；1 月的信号用 12 月（没有）→ 不挡


def test_em_tick_only_next_month_days():
    m = _months(2, "2024-01")
    B = pd.DataFrame({"A.T": [True, False], "B.T": [False, False]}, index=m)
    days = pd.bdate_range("2024-01-29", "2024-03-05")
    tick = T.em_tick_of(B, days)
    assert set(tick) == {("A.T", d) for d in days if d.month == 2} and set(tick.values()) == {0.0}


def test_wiring_and_cli():
    import inspect
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **over)" in s1 and "R3.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    r = inspect.getsource(T.runs)
    assert "em_tick_of(G[e][k], days)" in r
    w = inspect.getsource(T.wiring)
    assert "G[\"J\"][k] & False" in w and "all(v > 0 for v in n.values())" in w
    with pytest.raises(SystemExit):
        T.main(["--nope"])
    with pytest.raises(SystemExit):
        T.main(["--scale", "--wiring"])
