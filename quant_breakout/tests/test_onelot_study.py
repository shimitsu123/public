"""scripts/onelot_study.py 的纯函数：判定 P1〜P6、多买到的交易、买入时占权益、常数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import onelot_study as S  # noqa: E402


def _a(c, h1, h2, dd):
    return {"calmar": c, "h1": h1, "h2": h2, "dd": dd}


def test_constants():
    assert S.VARIANTS == {"L50": 0.50, "L34": 0.34, "L100": 1.00} and S.PRIMARY == "L50" and S.CAPITALS == (800_000, 1_200_000)
    assert (S.CAL_UP, S.HALF_TOL, S.DD_TOL, S.ERA_TOL, S.MIN_EXTRA) == (0.03, 0.02, 2.0, 0.02, 5)


def test_judge():
    B = _a(0.676, 0.689, 0.896, -29.6)
    good = S.judge(_a(0.71, 0.68, 0.90, -31.0), B, {8e5: (0.7, 0.6), 1.2e6: (0.7, 0.7)}, np.array([1.0] * 5),
                   {"Z": 1.17, "E": 0.65}, {"Z": 1.186, "E": 0.664})
    assert good["pass"]
    assert not S.judge(_a(0.70, 0.68, 0.90, -31.0), B, {8e5: (0.7, 0.6)}, np.ones(5), {"Z": 1.2, "E": 0.7}, {"Z": 1.186, "E": 0.664})["checks"]["P1"]
    r = S.judge(_a(0.71, 0.66, 0.90, -32.0), B, {8e5: (0.5, 0.6)}, np.array([1.0, -6.0, 1, 1, 1]), {"Z": 1.1, "E": 0.7}, {"Z": 1.186, "E": 0.664})
    assert r["checks"] == {"P1": True, "P2": False, "P3": False, "P4": False, "P5": False, "P6": False}
    assert not S.judge(_a(0.71, 0.68, 0.90, -31.0), B, {8e5: (0.7, 0.6)}, np.ones(4), {"Z": 1.2, "E": 0.7}, {"Z": 1.186, "E": 0.664})["checks"]["P5"]


def test_extra_and_weight():
    base = pd.DataFrame({"ticker": ["A", "B"], "entry_date": ["2020-01-06", "2020-02-03"], "shares": [100, 100], "entry_px": [1000.0, 2000.0],
                         "pnl": [1000.0, -2000.0]})
    cand = pd.concat([base, pd.DataFrame({"ticker": ["C"], "entry_date": ["2020-03-02"], "shares": [100], "entry_px": [5000.0], "pnl": [5000.0]})])
    ex = S.extra_trades(cand, base)
    assert list(ex["ticker"]) == ["C"] and np.allclose(S.net_pct(ex), [1.0])
    hist = pd.Series([1_000_000.0, 990_000.0, 1_100_000.0], index=pd.to_datetime(["2020-02-27", "2020-02-28", "2020-03-02"]))
    assert np.allclose(S.weight_pct(ex, hist), [500_000 / 990_000 * 100])              # 买入日前一天收盘后的权益
