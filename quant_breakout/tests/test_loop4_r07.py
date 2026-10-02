"""第四个研究循环第 7 轮 PDL（scripts/loop4_r07_delay.py，2026-10-03 登记）：登记值与第四个循环的规则、周收益、价格延迟 D1（反应慢 → 大；
只对当周反应 → ≈ 0）、月末窗口（周五 ≤ 月末、不够 40 周 → NaN）、横截面最低三分之一、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop4_r07_delay as T  # noqa: E402
import research_loop4 as R4  # noqa: E402


def test_registered_constants_and_loop4_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.WIN_W, T.MIN_W, T.LAGS) == (7, ("PDL",), False, "stock", 52, 40, 4) and T.LOW_Q == pytest.approx(1 / 3)
    assert T.FAMILY == {"PDL": "选股·信息扩散"} and all(f.startswith(R4.FAMILY_PREFIX) for f in T.FAMILY.values())
    assert not set(T.IDS) & R4.previous_ids(ROOT / "var")
    st = R4.load_state(ROOT / "var")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R4.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND} for k in T.IDS], R4.previous_ids(ROOT / "var"))


def test_weekly_ret():
    idx = pd.bdate_range("2024-01-01", periods=10)                          # 1/1（一）〜1/12（五）
    w = T.weekly_ret(pd.Series(np.arange(100.0, 110.0), index=idx))
    assert w.index[-1] == pd.Timestamp("2024-01-12") and w.iloc[-1] == pytest.approx(109 / 104 - 1)


def test_delay_d1_fast_vs_slow():
    rng = np.random.default_rng(1)
    m = rng.normal(0, 0.02, 300)
    M = np.column_stack([np.r_[np.zeros(k), m[:len(m) - k]] for k in range(5)])
    fast = 1.0 * M[:, 0] + rng.normal(0, 0.005, 300)
    slow = 0.3 * M[:, 0] + 0.5 * M[:, 1] + 0.3 * M[:, 2] + rng.normal(0, 0.005, 300)
    assert T.delay_d1(fast, M) < 0.02 and T.delay_d1(slow, M) > 0.5
    assert np.isnan(T.delay_d1(np.zeros(300), M))                          # 没有波动 → R² 算不出


def test_delay_monthly_window_and_bottom_third():
    rng = np.random.default_rng(2)
    widx = pd.date_range("2020-01-03", periods=120, freq="W-FRI")
    rm = pd.Series(rng.normal(0, 0.02, 120), index=widx)
    ri = 0.2 * rm + 0.6 * rm.shift(1).fillna(0) + pd.Series(rng.normal(0, 0.003, 120), index=widx)
    months = pd.period_range("2020-03", "2022-03", freq="M")
    d = T.delay_monthly(ri, rm, months)
    assert np.isnan(d.loc[pd.Period("2020-06", "M")])                     # 到 2020-06 还不到 40 周 → NaN
    assert d.loc[pd.Period("2021-06", "M")] > 0.5                          # 主要对上周的市场反应 → 延迟大
    P = pd.DataFrame({"A": [0.1, 0.5], "B": [0.2, np.nan], "C": [0.9, 0.1]}, index=pd.period_range("2021-01", periods=2, freq="M"))
    B = T.bottom_third(P)
    assert list(B.iloc[0]) == [True, False, False] and list(B.iloc[1]) == [False, False, True]   # 最低的三分之一；NaN 不挡


def test_runs_wiring_and_cli():
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **over)" in s1 and "R4.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    r = inspect.getsource(T.runs)
    assert '"PDL": {"em_tick": RM.em_tick_of(G[e], W["ctx"][e]["days"])}' in r
    w = inspect.getsource(T.wiring)
    assert 'L2.run(W, "J", em_tick={})' in w and "n > 0" in w
    with pytest.raises(SystemExit):
        T.main(["--nope"])
