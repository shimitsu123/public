"""scripts/b4_weakness_diag.py 的纯函数：盈亏拆分（加起来 = 权益变化）、回撤段、贡献、读法。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import b4_weakness_diag as D  # noqa: E402


def _rec():
    d = pd.bdate_range("2020-01-06", periods=4)
    return [
        (d[0], 1000.0, 0.0, 100.0, {}, {"1545.T": (10.0, 50.0)}, 1500.0),
        (d[1], 500.0, 0.0, 100.0, {"7203.T": (100.0, 5.0, "JP")}, {"1545.T": (10.0, 55.0)}, 1550.0),
        (d[2], 500.0, 0.0, 100.0, {"7203.T": (100.0, 6.0, "JP")}, {"1545.T": (10.0, 52.0)}, 1620.0),
        (d[3], 1090.0, 0.0, 100.0, {}, {"1545.T": (10.0, 53.0)}, 1620.0),
    ]


def test_split_pnl_adds_up():
    P = D.split_pnl(_rec())
    assert np.allclose(P["check"], 0)
    assert np.isclose(P["core_pnl"].iloc[1], 50) and np.isclose(P["stock_pnl"].iloc[1], 0)       # 第一天的个股是今天买的 → 不算
    assert np.isclose(P["stock_pnl"].iloc[2], 100) and np.isclose(P["core_pnl"].iloc[2], -30)
    assert np.isclose(P["stock_pnl"].iloc[3], 0) and np.isclose(P["core_pnl"].iloc[3], 10)        # 今天卖掉的按前一天收盘 → 差进「其余」
    tot = P[["stock_pnl", "core_pnl", "other_pnl"]].sum(axis=1).iloc[1:]
    assert np.allclose(tot, P["eq"].diff().iloc[1:])


def test_dd_episodes():
    eq = pd.Series([100, 110, 90, 95, 120, 100, 60, 130, 125], index=pd.bdate_range("2020-01-06", periods=9), dtype=float)
    eps = D.dd_episodes(eq, 10, 5)
    assert [round(x[2], 1) for x in eps] == [-50.0, -18.2]
    assert eps[0][0] == eq.index[4] and eps[0][1] == eq.index[6]
    assert D.dd_episodes(eq, 60, 5) == []


def test_contrib_and_episode_split():
    P = D.split_pnl(_rec())
    c = D.contrib(P)
    assert c["core"]["pp"] > 0 and c["stock"]["pp"] > 0 and abs(c["total_pp"] - sum(c[k]["pp"] for k in ("stock", "core", "other"))) < 1e-9
    x = D.episode_split(P, P.index[1], P.index[2], pd.Series([False, True], index=[P.index[0], P.index[2]]))
    assert np.isclose(x["core_pp"], -30 / 1550 * 100) and np.isclose(x["stock_pp"], 100 / 1550 * 100)
    assert x["core_share"] == 100.0 and x["bear_days_pct"] == 100.0


def test_readings_rules():
    def era(core_share, stock_pp, core_pp, give, share, lot, n):
        return {"episodes": [{"core_share": core_share}], "contrib": {"stock": {"pp": stock_pp}, "core": {"pp": core_pp}},
                "trades": {"n": n, "by_reason": {"dead_cross": {"n": int(n * share / 100), "giveback_mean": give}, "stop": {"n": n - int(n * share / 100), "giveback_mean": 0.0}}},
                "skipped": {"lot": lot}}
    res = {"eras": {"Z": era(80, 1, 30, 6, 60, 50, 20), "E": era(70, 2, 30, 6, 60, 50, 20), "J": era(10, 20, 30, 1, 60, 5, 20)}}
    R = D.readings(res)
    assert R["R1"]["ok"] and R["R3"]["ok"] and R["R4"]["ok"] and not R["R2"]["ok"]
    assert R["order"] == ["R1", "R3", "R4"]
    assert D.SIGNAL_EXITS == ("dead_cross", "chandelier", "sar_flip", "climax") and D.R1_SHARE == 60.0
