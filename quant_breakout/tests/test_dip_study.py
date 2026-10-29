"""scripts/dip_explore.py / dip_study.py：信号只用当天为止、交易不重叠、R1 的卖出（收盘回到 5 日线之上的下一开盘）、判定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dip_explore as X                                                      # noqa: E402
import dip_study as S                                                        # noqa: E402


def _ix(c):
    d = pd.bdate_range("2020-01-01", periods=len(c))
    c = pd.Series(c, index=d, dtype=float)
    return pd.DataFrame({"Open": c.shift(1).fillna(c.iloc[0]), "High": c, "Low": c, "Close": c}, index=d)


def test_signals_no_lookahead():
    r = np.random.default_rng(3)
    c = 100 * np.cumprod(1 + r.normal(0.0005, 0.01, 400))
    ix = _ix(c)
    s1 = X.signals(ix)
    c2 = c.copy()
    c2[300:] *= 0.8
    s2 = X.signals(_ix(c2))
    for k in s1:
        assert (s1[k].iloc[:300].fillna(False) == s2[k].iloc[:300].fillna(False)).all(), k


def test_trades_exit_rule_and_no_overlap():
    c = [100.0] * 210 + [99, 97, 95, 96, 98, 101, 102, 103, 104, 105, 106, 107]
    ix = _ix(c)
    sig = pd.Series(False, index=ix.index)
    sig.iloc[212] = True                                                      # 连跌后
    sig.iloc[213] = True                                                      # 持仓中的新信号 → 忽略
    T = X.trades(ix, sig, "D2")
    assert len(T) == 1 and T["entry"].iloc[0] == ix.index[213]
    ma5 = ix["Close"].rolling(5).mean()
    k = next(i for i in range(213, len(ix)) if ix["Close"].iloc[i] > ma5.iloc[i])
    assert T["exit"].iloc[0] == ix.index[k + 1]                              # 收盘 > 5 日线的下一开盘卖
    T5 = X.trades(ix, sig, "D3")
    assert T5["exit"].iloc[0] == ix.index[213 + 5]


def test_fails():
    ok = {"P": {"n": 100, "win": 60.0, "mean": 0.3, "t": 2.5}, "E": {"n": 50, "mean": 0.1}, "H": {"n": 20, "mean": 0.2}}
    assert S.fails(ok) == []
    bad = {**ok, "P": {"n": 100, "win": 60.0, "mean": 0.3, "t": 1.9}}
    assert len(S.fails(bad)) == 1
    bad2 = {**ok, "H": {"n": 20, "mean": -0.1}}
    assert len(S.fails(bad2)) == 1
