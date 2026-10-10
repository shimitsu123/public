"""scripts/stack_study.py（牛熊分界 × 风险层 × 深跌加仓）：60 天窗口、D0 / D1 / D2 的持有条件与比例、事先写定的判定、事件后的账户统计。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import stack_study as SS                                                     # noqa: E402


def test_constants():
    assert (SS.DD_THR, SS.HOLD, SS.SLICE, SS.DIV_1321) == (-15.0, 60, 0.25, 1.8)
    assert (SS.MIN_GAIN, SS.MAX_DD_WORSE, SS.D0_TOL, SS.JUDGE) == (0.02, 2.0, 0.001, ("E", "J"))


def test_window_mask_and_dd_series():
    days = pd.bdate_range("2020-01-01", periods=200)
    w = SS.window_mask(days, [days[10]])
    assert w.iloc[10:70].all() and not w.iloc[9] and not w.iloc[70] and w.sum() == 60
    w2 = SS.window_mask(days, [pd.Timestamp("2020-02-01")])                 # 星期六 → 从下一个交易日算
    k = int(days.searchsorted(pd.Timestamp("2020-02-01")))
    assert days[k] == pd.Timestamp("2020-02-03") and w2.iloc[k] and not w2.iloc[k - 1] and w2.sum() == 60
    ub = pd.Series(np.arange(len(days)) >= 40, index=days)                  # 第 40 天起美股熊
    b0, x0 = SS.dd_series(days, [days[10]], ub, "D0")
    assert b0.all()
    b1, x1 = SS.dd_series(days, [days[10]], ub, "D1")
    assert (~b1).sum() == 30 and not (~b1).iloc[39] and (~b1).iloc[40] and x1.iloc[40] == 0.25 and x1.iloc[39] == 1.0
    b2, _ = SS.dd_series(days, [days[10]], ub, "D2")
    assert (~b2).sum() == 60


def test_verdict():
    base = {"cagr": 10.0, "dd": -30.0, "calmar": 0.30}
    acct = {"E": {"V0": base, "D1": {"cagr": 11.0, "dd": -31.0, "calmar": 0.33}},
            "J": {"V0": base, "D1": {"cagr": 11.0, "dd": -31.5, "calmar": 0.32}}}
    assert SS.verdict(acct, "D1")["label"] == "提议"
    acct["J"]["D1"] = {"cagr": 11.0, "dd": -32.5, "calmar": 0.34}           # 回撤深了 2.5 pp
    assert SS.verdict(acct, "D1")["label"] == "不通过"
    acct["J"]["D1"] = {"cagr": 11.0, "dd": -30.0, "calmar": 0.315}          # Calmar 只 +0.015
    assert SS.verdict(acct, "D1")["label"] == "不通过"


def test_ep_stats():
    days = pd.bdate_range("2020-01-01", periods=300)
    eq = pd.Series(100.0, index=days)
    eq.iloc[20:50] = 90.0
    eq.iloc[50:] = 110.0
    r = SS.ep_stats(eq, [days[10], days[250]])
    assert len(r) == 1 and r[0]["r60"] == 10.0 and r[0]["low"] == -10.0   # 离结尾不够 120 天的事件不算


def test_engine_cls_is_mixengine():
    import candle_portfolio as CP
    E = SS.engine_cls()
    assert issubclass(E, CP.MixEngine) and E.DD_EXPO is None
