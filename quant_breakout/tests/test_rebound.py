"""专门的超跌反弹（scripts/rebound_study.py）：候选、反弹卖法的参数与卖出列（只用已完成 K 线）、大盘过滤、两部分资金的再平衡、入选与确认规则。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rebound_study as RB                                                  # noqa: E402
from qbreak.config import StrategyParams                                     # noqa: E402


def _daily(closes, start="2020-01-06"):
    days = pd.bdate_range(start, periods=len(closes))
    c = np.asarray(closes, float)
    return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": np.full(len(c), 1e6)}, index=days), days


def test_candidates_and_constants():
    c = RB.candidates()
    assert len(c) == 18 and len(set(c)) == 18 and RB.parts("E1M1XB") == ("E1", "M1", "XB")
    assert {k: (v["ev"], v["hold"]) for k, v in RB.ENTRIES.items()} == {"E1": ("N4", 20), "E2": ("N6", 20), "E3": ("N5", 60)}
    assert RB.MFILTERS == {"M0": None, "M1": -6.0} and RB.STOP_PCT == 15.0 and RB.W_DIP == 0.25


def test_dip_params():
    q = RB.dip_params(StrategyParams(), 20)
    assert (q.stop_loss_pct, q.take_profit_pct, q.trailing_stop_pct, q.max_hold_days) == (15.0, 0.0, 0.0, 20)
    assert q.exit_on_macd_dead_cross and not q.exit_on_climax and q.time_stop_days == 0


def test_exit_cols_use_completed_bars():
    c = np.r_[np.full(100, 100.0), np.full(10, 80.0), np.full(15, 101.0)]          # 跌到 80 再回到 101
    raw, days = _daily(c)
    xa = RB.exit_col(raw, days, raw.index, "XA", "W", 13)
    assert not xa.any()
    xb = RB.exit_col(raw, days, raw.index, "XB", "W", 13)
    assert not xb[:64].any() and xb[64]                                              # 第 13 周完成（第 64 天）之前没有线；平的时候收盘 = 线
    assert not xb[100:110].any()                                                     # 跌到 80 的两周：低于线（第 21 周完成那天的线含这一根 = 98.5）
    assert xb[110]                                                                   # 第 23 周周一收 101 ≥ 上一根已完成周线的线 (11×100 + 80 + 80) / 13 = 96.9
    xc = RB.exit_col(raw, days, raw.index, "XC", "W", 13)
    m25 = pd.Series(c).rolling(25).mean().to_numpy()
    assert np.array_equal(xc, np.isfinite(m25) & (c >= m25))


def test_index_filter():
    c = np.r_[np.full(100, 100.0), np.full(10, 90.0)]
    nk, days = _daily(c)
    st = RB.index_dev_state(nk)
    fri = days[104]                                                                  # 第 21 周周五完成（收 90）：乖离 −9.2%
    assert np.isclose(st.loc[fri], (90 / ((12 * 100 + 90) / 13) - 1) * 100) and st.loc[days[103]] > -1
    ok = RB.market_ok([days[103], fri, days[106]], st, -6.0)
    assert ok.tolist() == [True, False, False]
    assert RB.market_ok([days[0]], st, -6.0).tolist() == [True]                     # 没有值 → 不挡
    assert RB.market_ok([fri], st, None).tolist() == [True]


def test_blend_monthly_rebalance():
    idx = pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-04"])
    a = pd.Series([100.0, 110.0, 110.0, 121.0], index=idx)
    b = pd.Series([100.0, 100.0, 50.0, 50.0], index=idx)
    x = RB.blend(a, b, 0.25)
    assert np.isclose(x.iloc[1], 0.75 * 1.1 + 0.25)                                 # 1 月：各自漂移
    tot = 0.75 * 1.1 + 0.25                                                          # 2 月第一天先再平衡回 75 / 25
    assert np.isclose(x.iloc[2], tot * 0.75 + tot * 0.25 * 0.5)
    assert np.allclose(RB.blend(a, b, 0.0).to_numpy(), (a / 100).to_numpy())


def _t(n, win, mean):
    return {"n": n, "win": win, "mean": mean}


def test_qualifies_and_pick():
    base = {"E": _t(127, 42.5, 0.70), "J": _t(172, 42.4, 0.53), "J2": _t(1083, 38.3, 0.12)}
    good = {"E": _t(100, 55.0, 1.0), "J": _t(80, 52.0, 0.9), "J2": _t(400, 50.0, 0.8)}
    a0 = {"E": {"calmar": 0.285, "dd": -28.0}, "J": {"calmar": 0.388, "dd": -35.0}}
    a1 = {"E": {"calmar": 0.31, "dd": -29.0}, "J": {"calmar": 0.41, "dd": -36.0}}
    assert RB.qualifies(good, base, a1, a0) == []
    assert any("胜率" in f for f in RB.qualifies({**good, "J2": _t(400, 37.0, 0.8)}, base, a1, a0))
    assert any("Calmar" in f for f in RB.qualifies(good, base, {**a1, "J": {"calmar": 0.40, "dd": -36.0}}, a0))
    assert any("回撤" in f for f in RB.qualifies(good, base, {**a1, "E": {"calmar": 0.31, "dd": -31.0}}, a0))
    assert any("笔数" in f for f in RB.qualifies({**good, "E": _t(20, 60.0, 2.0)}, base, a1, a0))
    fails = {"E1M0XA": [], "E1M1XB": [], "E2M1XA": [], "E3M0XC": ["x"]}
    gain = {"E1M0XA": 0.05, "E1M1XB": 0.08, "E2M1XA": 0.03, "E3M0XC": 0.2}
    assert RB.pick(fails, gain) == ["E1M1XB", "E2M1XA"]                            # 同一种买点只取 1 个、最多 2 个


def test_confirm_verdict():
    base = {"win": 44.0, "mean": 1.0}
    pool = {"n": 500, "win": 55.0, "mean": 1.5, "lo": 0.3}
    per = {"Z": {"mean": 2.0}, "W": {"mean": 1.2}}
    z0, z1 = {"calmar": 1.3, "dd": -9.0}, {"calmar": 1.35, "dd": -10.0}
    assert RB.confirm_verdict(pool, per, base, z1, z0)["label"] == "通过"
    assert RB.confirm_verdict({**pool, "lo": -0.1}, per, base, z1, z0)["label"] == "方向一致"
    assert RB.confirm_verdict(pool, per, base, {"calmar": 1.2, "dd": -10.0}, z0)["label"] == "方向一致"
    assert RB.confirm_verdict(pool, {**per, "W": {"mean": -0.1}}, base, z1, z0)["label"] == "不通过"
    assert RB.confirm_verdict({**pool, "win": 40.0}, per, base, z1, z0)["label"] == "不通过"
