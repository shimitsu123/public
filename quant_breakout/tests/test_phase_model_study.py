"""按局面选模型（scripts/phase_model_study.py 登记检验）：局面优先级与刚转牛窗口、真实局面标签、模型收益与配比（之和 ≤ 1）、
学习只用过去 + 最少天数 → Q 的做法、月末映射按月生效、M2 映射、近 36 个月学习、安慰剂（平移 / 随机映射）、局面统计。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import core_switch_study as CS                                               # noqa: E402
import phase_model_study as PM                                               # noqa: E402


def test_constants():
    assert PM.ASSETS == ("1545.T", "1655.T", "2845.T", "1540.T", "1321.T", "2238.T")
    assert tuple(PM.ACTIONS) == ("a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8") and PM.PHASES == ("up", "bear", "down", "bull")
    assert (PM.FRESH_N, PM.THREAT_PCT, PM.MIN_DAYS, PM.MIN_DAYS_ROLL, PM.ROLL_MONTHS) == (60, 80.0, 120, 60, 36)
    assert (PM.FWD_N, PM.UP_PCT, PM.DOWN_PCT, PM.PLACEBO_SEEDS, PM.SHIFT_MIN, PM.BASE) == (20, 5.0, -5.0, 20, 250, "Q")
    assert PM.DEFAULT_MAP == {"up": "a1", "bear": "a7", "down": "a1", "bull": "a1"}
    assert PM.HAND_MAP == {"up": "a6", "bear": "a7", "down": "a7", "bull": "a1"}
    for ws in PM.ACTIONS.values():
        assert sum(ws.values()) <= 1 + 1e-9 and all(t in PM.ASSETS for t in ws)


def test_fresh_bull_and_phase_priority():
    d = pd.bdate_range("2020-01-01", periods=300)
    bear = pd.Series(False, index=d)
    bear.iloc[50:100] = True                                                  # 第 100 天翻牛
    f = PM.fresh_bull(bear)
    assert not f.iloc[:100].any() and f.iloc[100:160].all() and not f.iloc[160:].any()
    dip = pd.Series(False, index=d)
    dip.iloc[60:70] = True                                                    # 熊市里的深跌窗口 → 预计大涨（优先于熊）
    threat = pd.Series(False, index=d)
    threat.iloc[200:210] = True
    threat.iloc[55:58] = True                                                 # 熊市里的威胁高 → 仍是熊市
    ph = PM.phase_series(bear, dip, f, threat)
    assert (ph.iloc[60:70] == "up").all() and (ph.iloc[50:60] == "bear").all() and (ph.iloc[70:100] == "bear").all()
    assert (ph.iloc[100:160] == "up").all() and (ph.iloc[200:210] == "down").all() and (ph.iloc[160:200] == "bull").all()
    assert (ph.iloc[55:58] == "bear").all()


def test_realized_phase():
    d = pd.bdate_range("2020-01-01", periods=10)
    bear = pd.Series([False] * 5 + [True] * 5, index=d)
    fwd = pd.Series([6.0, -6.0, 1.0, np.nan, 4.9, 5.0, -5.0, 0.0, np.nan, np.nan], index=d)
    r = PM.realized_phase(bear, fwd)
    assert list(r) == ["up", "down", "bull", "bull", "bull", "up", "down", "bear", "bear", "bear"]


def test_action_returns_and_weights():
    d = pd.bdate_range("2020-01-01", periods=4)
    R = pd.DataFrame(np.nan, index=d, columns=list(PM.ASSETS))
    R["1545.T"] = 0.01
    R["1540.T"] = [np.nan, 0.02, 0.02, 0.02]                                  # 第 0 天不可用 → 当现金
    R["2238.T"] = -0.01
    AR = PM.action_returns(R)
    assert abs(AR["a1"].iloc[0] - 0.01) < 1e-12 and abs(AR["a7"].iloc[0]) < 1e-12 and abs(AR["a8"].iloc[0] + 0.01) < 1e-12
    assert abs(AR["a4"].iloc[0] - 0.008) < 1e-12 and abs(AR["a4"].iloc[1] - 0.012) < 1e-12
    assert abs(AR["a5"].iloc[0] - 0.005) < 1e-12 and abs(AR["a6"].iloc[0] - 0.0075) < 1e-12
    ch = pd.Series(["a1", "a4", "a7", "a6"], index=d)
    W = PM.weights_of(ch)
    assert W.iloc[0]["1545.T"] == 1.0 and W.iloc[1]["1540.T"] == 0.2 and W.iloc[2].sum() == 0 and W.iloc[3]["1321.T"] == 0.25
    assert (W.sum(axis=1) <= 1 + 1e-9).all()


def test_learn_map_min_days_and_no_lookahead():
    d = pd.bdate_range("2015-01-01", periods=600)
    rng = np.random.default_rng(0)
    AR = pd.DataFrame(rng.normal(0, 0.01, (600, 8)), index=d, columns=list(PM.ACTIONS))
    AR["a7"] = 0.0
    ph = pd.Series(np.where(np.arange(600) % 2 == 0, "bull", "down"), index=d, dtype=object)
    AR.loc[ph == "bull", "a3"] += 0.02                                        # 普通牛市里 a3 最好
    AR.loc[ph == "down", :] -= 0.01                                           # 预计大跌里全都亏 → 现金（0）最好
    mp = PM.learn_map(AR, ph, d[-1])
    assert mp["bull"] == "a3" and mp["down"] == "a7" and mp["up"] == "a1" and mp["bear"] == "a7"   # up / bear 没有历史 → Q 的做法
    early = PM.learn_map(AR, ph, d[100])                                      # 每个局面只 50 天 < 120 → 全部 Q 的做法
    assert early == PM.DEFAULT_MAP
    AR2 = AR.copy()
    AR2.iloc[400:] = 0.5                                                      # 改未来
    assert PM.learn_map(AR2, ph, d[399]) == PM.learn_map(AR, ph, d[399])
    ch, maps = PM.walk_forward(AR, ph)
    me = CS.month_ends(d)
    assert set(ch.unique()) <= set(PM.ACTIONS) and (ch.loc[:me[0]] == "a1").all()
    last = maps[me[-1]]
    assert last["bull"] == "a3"
    ch3, _ = PM.walk_forward(AR, ph, roll_months=PM.ROLL_MONTHS)
    assert len(ch3) == len(ch)


def test_choice_by_map_month_boundary():
    d = pd.bdate_range("2020-01-01", "2020-03-31")
    ph = pd.Series("bull", index=d, dtype=object)
    me = CS.month_ends(d)
    maps = {me[0]: {"up": "a1", "bear": "a7", "down": "a1", "bull": "a2"}, me[1]: {"up": "a1", "bear": "a7", "down": "a1", "bull": "a3"}}
    ch = PM.choice_by_map(ph, maps)
    assert (ch.loc[:me[0]] == "a1").all() and (ch.loc[me[0] + pd.Timedelta(days=1):me[1]] == "a2").all() and (ch.loc[me[1] + pd.Timedelta(days=1):] == "a3").all()


def test_baseline_choice_ignores_phase():
    d = pd.bdate_range("2020-01-01", periods=6)
    bear = pd.Series([False, True, True, False, False, True], index=d)
    assert list(PM.baseline_choice(bear, "a1")) == ["a1", "a7", "a7", "a1", "a1", "a7"]
    assert list(PM.baseline_choice(bear, "a2")) == ["a2", "a7", "a7", "a2", "a2", "a7"]


def test_fixed_random_shift_and_stats():
    d = pd.bdate_range("2018-01-01", periods=900)
    ph = pd.Series(np.where(np.arange(900) % 4 == 0, "up", np.where(np.arange(900) % 4 == 1, "bear", "bull")), index=d, dtype=object)
    ch = PM.fixed_choice(ph, PM.HAND_MAP)
    assert (ch[ph == "up"] == "a6").all() and (ch[ph == "bear"] == "a7").all() and (ch[ph == "bull"] == "a1").all()
    s = PM.shifted_phase(ph, 1)
    assert sorted(s.unique()) == sorted(ph.unique()) and (s == ph).mean() < 0.9 and s.value_counts().sort_index().equals(ph.value_counts().sort_index())
    m1, m2 = PM.random_map(3), PM.random_map(3)
    assert m1 == m2 and set(m1) == set(PM.PHASES) and set(m1.values()) <= set(PM.ACTIONS)
    close = pd.Series(np.cumprod(1 + np.where(ph.to_numpy() == "up", 0.01, 0.0)), index=d)
    st = PM.phase_stats(ph, close, str(d[0].date()), None)
    assert st["up"]["days"] == 225 and st["all"]["days"] == 900 and st["up"]["r20"] is not None


def test_verdict_reuse():
    seg = lambda c, dd: {"cagr": 10.0, "dd": dd, "calmar": c}                 # noqa: E731
    RP = {"Q": {"P": seg(0.30, -40.0), "P1": seg(0.2, -40.0), "P2": seg(0.4, -30.0)},
          "M2": {"P": seg(0.36, -39.0), "P1": seg(0.25, -39.0), "P2": seg(0.45, -30.0)}}
    ACCT = {e: {"Q": seg(0.50, -30.0), "M2": seg(0.53, -29.0)} for e in ("Z", "E", "J")}
    assert CS.verdict("M2", RP, ACCT, 0.33, 0.52)[0] == "提议"
    assert CS.verdict("M2", RP, ACCT, 0.33, 0.53)[0] == "不通过"
