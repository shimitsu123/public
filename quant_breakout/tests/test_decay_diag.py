"""scripts/decay_diag.py：逐笔的附加量（跳空、信号前涨幅、10 日最大有利 / 不利、同期日経与超额）、汇总、每年的市场环境。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import decay_diag as D  # noqa: E402


def _panel():
    days = pd.bdate_range("2020-01-01", periods=40)
    C = np.linspace(100, 139, 40)[:, None]
    P = {"C": C.copy(), "O": C - 0.5, "H": C + 1.0, "L": C - 1.0}
    N = pd.DataFrame({"Open": np.full(40, 1000.0), "Close": np.full(40, 1000.0)}, index=days)
    N.iloc[30:, 1] = 1010.0
    return P, days, N


def test_enrich_gap_pre20_mfe_and_market_excess():
    P, days, N = _panel()
    T = pd.DataFrame([{"ticker": "A.T", "sig_date": days[25], "entry_date": days[26], "exit_date": days[32], "entry_px": P["O"][26, 0],
                       "ret_pct": 5.0}])
    X = D.enrich(T, P, days, ["A.T"], N).iloc[0]
    assert np.isclose(X["gap"], (P["O"][26, 0] / P["C"][25, 0] - 1) * 100)
    assert np.isclose(X["pre20"], (P["C"][25, 0] / P["C"][5, 0] - 1) * 100)
    assert np.isclose(X["mfe10"], (P["H"][35, 0] / P["O"][26, 0] - 1) * 100)
    assert np.isclose(X["mae10"], (P["L"][26, 0] / P["O"][26, 0] - 1) * 100)
    assert np.isclose(X["mkt"], 1.0) and np.isclose(X["exc"], 4.0)                 # 日経 1000 → 1010


def test_stats_reasons_and_era():
    T = pd.DataFrame({"net": [2.0, -1.0, 3.0, -2.0], "reason": ["dead_cross", "stop", "take_profit", "gap_stop"],
                      "hold_days": [10, 3, 20, 2], "exc": [1.0, -1.0, 2.0, 0.5], "mkt": [1.0, 0.0, 1.0, -2.5]})
    s = D.stats(T)
    assert s["n"] == 4 and s["win"] == 50.0 and np.isclose(s["mean"], 0.5) and s["stop"] == 50.0 and s["tp"] == 25.0 and s["exc_win"] == 75.0
    assert D.era_of("2005-06-01") == "Z" and D.era_of("2006-10-01") == "E" and D.era_of("2016-11-15") is None and D.era_of("2020-01-06") == "J"


def test_yearly_context_survivor_excess_and_corr():
    days = pd.bdate_range("2019-01-01", "2020-12-31")
    rng = np.random.default_rng(0)
    m = rng.normal(0, 0.01, len(days))
    C = 100 * np.exp(np.cumsum(np.column_stack([m + rng.normal(0, 0.005, len(days)) for _ in range(5)]), axis=0))
    N = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(m))}, index=days)
    ctx = D.yearly_context(C, days, N)
    assert list(ctx.index) == [2019, 2020] and (ctx["corr"] > 0.5).all() and (ctx["n_names"] == 5).all()
    y = days.year == 2020
    ew = np.mean(C[y][-1] / C[y][0] - 1) * 100
    assert np.isclose(ctx.loc[2020, "surv"], round(ew - (N["Close"][y].iloc[-1] / N["Close"][y].iloc[0] - 1) * 100, 2), atol=0.01)
