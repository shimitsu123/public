"""判断底部 + 石油条件（scripts/bottom_oil_study.py 登记检验）：深跌段与 B0 / B1 / B2 的发信号、石油日状态 = 最近月末且缺值不亮、
真底距离与召回、合并统计与判定（五条全过才算更准确）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bottom_oil_study as B                                                # noqa: E402


def _close():
    """2004〜：先涨 300 天到 200，跌到 150（−25%），从最低反弹回 220，再横。"""
    days = pd.bdate_range("2003-01-01", periods=1400)
    v = np.concatenate([np.linspace(100, 200, 500), np.linspace(200, 150, 120), np.linspace(150, 220, 300), np.full(480, 220.0)])
    return pd.Series(v, index=days)


def test_constants():
    assert (B.DD_THR, B.REBOUND, B.LINE_THR, B.TROUGH_THR) == (-0.15, 0.08, -15.0, 0.15)
    assert (B.HS, B.H_HIT, B.FALSE_THR, B.NEAR, B.RECALL_H, B.SEEDS, B.SHIFT_MIN, B.GAIN_PP, B.COUNT_SHARE) == ((60, 120, 250), 120, -10.0, 60, 120, 30, 12, 5.0, 0.5)
    assert B.CANDS == ("B0", "B0m", "B1", "B1m", "B2") and B.EVAL0 == "2004-01-01"


def test_oil_daily_uses_latest_month_end_and_nan_is_off():
    m = pd.date_range("2005-01-31", periods=6, freq="ME")
    sig = pd.Series([-1.0, -9.0, np.nan, -9.0, 2.0, -9.0], index=m)
    days = pd.bdate_range("2005-01-01", "2005-07-15")
    o = B.oil_daily(sig, -5.0, days)
    assert not o.loc["2005-01-14"] and not o.loc["2005-02-15"] and o.loc["2005-03-01"] and not o.loc["2005-04-01"]     # 3 月缺值 → 不亮
    assert o.loc["2005-05-02"] and not o.loc["2005-06-01"] and o.loc["2005-07-01"]


def test_episode_and_signals():
    c = _close()
    eps = B.episodes(c)
    assert len(eps) == 1
    ep = eps[0]
    assert c.iloc[ep["s"]] <= c.iloc[:ep["s"] + 1].rolling(250).max().iloc[-1] * 0.85 + 1e-9 and c.iloc[ep["low_i"]] == 150.0
    assert c.iloc[ep["e"]] >= c.iloc[ep["e"] - 249:ep["e"] + 1].max() - 1e-9 and ep["e"] > ep["low_i"]                # 创 250 日新高结束
    s0 = B.sig_b0(c, eps)
    assert len(s0) == 1 and c.iloc[s0[0]["i"]] >= 150.0 * 1.08 and s0[0]["i"] > ep["low_i"]
    on = pd.Series(False, index=c.index)
    on.iloc[s0[0]["i"] + 40:] = True                                                                                  # 石油在反弹确认之后 40 天才亮
    s1 = B.sig_b0(c, eps, on)
    assert len(s1) == 1 and s1[0]["i"] == s0[0]["i"] + 40                                                             # B1 = 等到亮
    s2 = B.sig_b2(c, eps, on)
    assert s2[0]["i"] == s0[0]["i"] + 40
    never = pd.Series(False, index=c.index)
    assert B.sig_b0(c, eps, never) == [] and B.sig_b2(c, eps, never) == []
    tr = B.troughs(c)
    assert c.loc[tr[-1]] == 150.0 and tr[0] < pd.Timestamp(B.EVAL0)                                                   # 序列起点也算一个拐点，评估期外
    rows = B.metrics(c, s0, tr)
    assert len(rows) == 1 and rows[0]["lag"] > 0 and rows[0]["near"] and rows[0]["f120"] > 0 and rows[0]["false"] is False
    assert B.recall(c, s0, tr) == (1, 1) and B.recall(c, [], tr) == (0, 1)
    P = B.pooled(rows)
    assert P["n"] == 1 and P["hit120"] == 100.0 and P["false"] == 0.0 and P["near"] == 100.0


def _crash():
    """急跌：涨到 200 后 30 天跌到 120（−40%），再 200 天涨回 220。"""
    days = pd.bdate_range("2003-01-01", periods=1200)
    v = np.concatenate([np.linspace(100, 200, 500), np.linspace(200, 120, 30), np.linspace(120, 220, 200), np.full(470, 220.0)])
    return pd.Series(v, index=days)


def test_b0m_line_signal():
    c = _crash()
    s = B.sig_b0m(c)
    assert len(s) == 1
    dev = B.DF.line_dev(c)
    assert dev.iloc[s[0]["i"]] >= 0 and (dev.iloc[:s[0]["i"]] <= -15).any()


def test_decide_rules():
    P = {"B0": {"n": 100, "hit120": 70.0, "false": 25.0}, "B1": {"n": 60, "hit120": 76.0, "false": 24.0},
         "B0m": {"n": 80, "hit120": 68.0}, "B1m": {"n": 50, "hit120": 69.0}}
    ok, fails, info = B.decide(P, [0.0, 1.0, 2.0, 3.0, 4.0])
    assert ok and info["gain"] == 6.0 and info["checks"]["D4"]
    P2 = {**P, "B1": {"n": 40, "hit120": 76.0, "false": 24.0}}                                                       # 信号不到一半
    ok2, fails2, _ = B.decide(P2, [0.0, 1.0])
    assert not ok2 and any(f.startswith("D3") for f in fails2)
    P3 = {**P, "B1": {"n": 60, "hit120": 73.0, "false": 24.0}}                                                       # 只 +3 pp
    assert not B.decide(P3, [0.0])[0]
    P4 = {**P, "B1m": {"n": 50, "hit120": 60.0}}
    assert any(f.startswith("D5") for f in B.decide(P4, [0.0])[1])
    assert not B.decide(P, [7.0, 8.0, 9.0])[2]["checks"]["D4"]
