"""第五个研究循环第 1 轮 CSH / SMO / RSM（scripts/loop5_r01_layer.py，2026-10-03 登记）：登记值与第五个循环的规则、美国状态的时点（美国日期 + 1 天才可用）、
CSH 倍数、SMO 的窗口（252 天、离场后 2 天才算、≥ 10 笔）、RSM 的相对涨幅、信号日取值、接线与命令行。"""
import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop5_r01_layer as T  # noqa: E402
import research_loop5 as R5  # noqa: E402


def test_registered_constants_and_loop5_rules():
    assert (T.ROUND, T.POSTHOC, T.KIND, T.M_UP, T.M_DOWN, T.LOOKBACK, T.MIN_N, T.KNOWN_LAG, T.CORE) == (1, False, "size_time", 1.36, 0.5, 252, 10, 2, "1545.T")
    assert T.M_UP == pytest.approx(R5.M_CAP) and set(T.IDS) <= {"CSH", "SMO", "RSM"}
    assert all(T.FAMILY[k].startswith(R5.FAMILY_PREFIX) for k in T.IDS)
    assert not set(T.IDS) & R5.previous_ids(ROOT / "var")
    st = R5.load_state(ROOT / "var")
    if not st:
        pytest.skip("第五个研究循环还没有登记")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R5.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND} for k in T.IDS], R5.previous_ids(ROOT / "var"))


def test_us_known_uses_only_earlier_calendar_days():
    us = pd.Series([0.0, 1.0, 0.0], index=pd.to_datetime(["2024-01-08", "2024-01-09", "2024-01-10"]))
    jp = pd.to_datetime(["2024-01-05", "2024-01-09", "2024-01-10", "2024-01-11"])
    k = T.us_known(us, jp)
    assert np.isnan(k.iloc[0])                                                 # 之前没有美国收盘
    assert k.loc["2024-01-09"] == 0.0                                          # 1/9 的 JP 收盘只知道美国 1/8
    assert k.loc["2024-01-10"] == 1.0 and k.loc["2024-01-11"] == 0.0           # 美国 1/9 → JP 1/10 才可用


def test_csh_mult():
    b = pd.Series([1.0, 0.0, np.nan, 1.0], index=pd.bdate_range("2024-01-01", periods=4))
    assert T.csh_mult(b).tolist() == [1.36, 1.0, 1.0, 1.36]


def test_smo_state_window_lag_and_min_n():
    n = 600
    ep = np.array([10, 100, 300, 300, 590] + [400] * 9, float)
    xs = np.array([1.0, -1.0, 2.0, np.nan, 5.0] + [-0.5] * 9)
    mean, cnt = T.smo_state(ep, xs, n)
    assert cnt[11] == 0 and cnt[12] == 1 and mean[12] == pytest.approx(1.0)  # 离场 10 → 第 12 天才算
    assert cnt[102] == 2 and mean[102] == pytest.approx(0.0)
    assert cnt[263] == 2 and cnt[264] == 1                                   # 第 12 天加进来的那笔在 12 + 252 = 264 天掉出窗口
    assert cnt[402] == 1 + 9 and mean[402] == pytest.approx((2.0 - 4.5) / 10)   # NaN 的那笔不算；第 102 天加进来的已经掉出
    m = T.smo_mult(mean, cnt, pd.RangeIndex(n))
    assert m[402] == 0.5 and m[302] == 1.0 and m[0] == 1.0                   # 够 10 笔且 ≤ 0 → 减；不够 10 笔 → 不变
    mean2, cnt2 = T.smo_state(np.array([5.0] * 10), np.array([0.3] * 10), 20)
    assert T.smo_mult(mean2, cnt2, pd.RangeIndex(20))[7] == 1.36


def test_rsm_mult_relative_momentum():
    d = pd.bdate_range("2020-01-01", periods=300)
    jp = pd.Series(np.linspace(100, 200, 300), index=d)
    us = pd.Series(np.linspace(100, 150, 300), index=d)
    m = T.rsm_mult(jp, us, d)
    assert (m.iloc[:252] == 1.0).all() and (m.iloc[252:] == 1.36).all()      # 日経涨得多 → 加
    m2 = T.rsm_mult(us, jp, d)
    assert (m2.iloc[252:] == 0.5).all()                                       # 纳指涨得多 → 减


def test_at_dates_signal_day_value():
    m = pd.Series([1.0, 1.36, 0.5], index=pd.to_datetime(["2024-01-04", "2024-01-05", "2024-01-09"]))
    assert T.at_dates(m, ["2024-01-03", "2024-01-05", "2024-01-08", "2024-01-09"]).tolist() == [1.0, 1.36, 1.36, 0.5]
    assert T.at_dates(m, ["2024-01-08", "2024-01-08", "2024-01-05"]).tolist() == [1.36, 1.36, 1.36]       # 同一天几个信号


def test_wiring_and_cli():
    r = inspect.getsource(T.runs)
    assert "R5.sizing_kw(R5.M_CAP, day_mult=R5.fill_day(M[k], days))" in r
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and "rc = L2.run(W, e, **kw)" in s1 and "R5.stage1(cand[k], base, trade=os_[k], posthoc=None)" in s1
    w = inspect.getsource(T.wiring)
    assert "pd.Series(1.0, index=M[\"days\"])" in w and "all(v > 0 for v in n.values())" in w
    s2 = inspect.getsource(T.stage_two)
    assert "R5.size_shift_ks(len(M[\"days\"]))" in s2 and "R5.stage2(stat, vals)" in s2 and 'if not s1["ok"]' in s2
    assert "R5.shift_mult(M[k], ks[int(seed)])" in inspect.getsource(T._placebo_one)
    with pytest.raises(SystemExit):
        T.main(["--nope"])
