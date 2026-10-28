"""scripts/us_selection_study.py 的纯函数与动量账户（合成数据）。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import us_selection_study as U  # noqa: E402


def test_month_ends():
    d = pd.bdate_range("2020-01-01", "2020-03-31")
    me = U.month_ends(d)
    assert list(me.strftime("%Y-%m-%d")) == ["2020-01-31", "2020-02-28", "2020-03-31"]


def test_dedup_signals():
    f = np.zeros(60, bool)
    f[[0, 5, 30, 51, 52]] = True
    out = U.dedup_signals(f, gap=20)
    assert list(np.flatnonzero(out)) == [0, 30, 51]          # 5 在 0 的 20 日内；52 在 51 之后 1 日


def test_mom_score_skips_short_history_and_ranks():
    d = pd.bdate_range("2019-01-01", periods=300)
    up = pd.Series(np.linspace(10, 30, 300), index=d)
    flat = pd.Series(10.0, index=d)
    short = pd.Series(np.nan, index=d)
    short.iloc[-100:] = 50.0
    C = pd.DataFrame({"UP": up, "FLAT": flat, "SHORT": short})
    s = U.mom_score(C, d[-1])
    assert list(s.index) == ["UP", "FLAT"]
    assert abs(s["UP"] - (up.iloc[-22] / up.iloc[-253] - 1)) < 1e-12


def test_rakuten_fee_cap():
    assert U.rakuten_fee(1000, 0.495, 22) == 4.95
    assert U.rakuten_fee(10000, 0.495, 22) == 22


def test_read_rules():
    ok = {"E": {"excess": 0.5, "ci": (0.1, 0.9)}, "J": {"excess": 0.2, "ci": (-0.3, 0.7)}}
    assert U.read_u0(ok).startswith("U0 有用")
    bad = {"E": {"excess": -0.5, "ci": (-0.9, -0.1)}, "J": {"excess": -0.2, "ci": (-0.3, 0.1)}}
    assert U.read_u0(bad) == "U0 跑输指数"
    mix = {"E": {"excess": 0.5, "ci": (-0.1, 0.9)}, "J": {"excess": 0.2, "ci": (-0.3, 0.7)}}
    assert U.read_u0(mix) == "看不出 U0 比指数好"
    c0 = {"Z": 0.1, "E": 0.1, "J": 0.1}
    assert U.read_variant({"Z": 0.13, "E": 0.2, "J": 0.14}, c0) == "比 U0 更好"
    assert U.read_variant({"Z": 0.13, "E": 0.2, "J": 0.12}, c0) == "看不出更好"
    assert U.read_variant({"Z": 0.0, "E": 0.05, "J": -0.1}, c0) == "比 U0 差"


def test_boot_mean_brackets_mean():
    x = pd.Series(np.arange(40, dtype=float))
    g = pd.Series(np.repeat(np.arange(10), 4))
    lo, hi = U.boot_mean(x, g, reps=300)
    assert lo < x.mean() < hi


def test_run_momentum_holds_top_and_charges_fees():
    d = pd.bdate_range("2018-01-01", periods=420)
    rng = np.random.default_rng(0)
    cols = {}
    for k, g in enumerate([0.002, 0.001, 0.0005, 0.0, -0.0005, -0.001]):
        cols[f"S{k}"] = 50 * np.exp(np.cumsum(g + rng.normal(0, 0.001, len(d))))
    C = pd.DataFrame(cols, index=d)
    O = C.shift(1).fillna(C)
    fx = pd.Series(100.0, index=d)
    eq, tr, turn = U.run_momentum(C, O, fx, str(d[300].date()), 0.495, 22.0, 0.05, 0.03)
    assert len(eq) == 120 and turn > 0
    held = set(tr["ticker"])
    assert held <= {"S0", "S1", "S2", "S3"}                 # 只拿动量前 4
    eq0, *_ = U.run_momentum(C, O, fx, str(d[300].date()), 0.0, 0.0, 0.0, 0.0)
    assert eq0.iloc[-1] > eq.iloc[-1]                        # 成本让权益变低
    assert abs(eq.iloc[0] - U.CAPITAL) / U.CAPITAL < 0.01
