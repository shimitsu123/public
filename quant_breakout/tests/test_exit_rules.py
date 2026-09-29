"""模拟盘的离场方式（qbreak/exit_rules.py + qbreak/unified.py）：吊灯止损 X6 / SAR 翻转 R4 与前向记录的定义（qbreak/exit_forward.py）
在同一天成立；只换「死叉」那一条；var/best_params 不受影响（run_backtest 不静默忽略）；指标表只在打开时才有 SAR 列。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qbreak import exit_forward as EF                                        # noqa: E402
from qbreak import exit_rules as EXR                                         # noqa: E402
from qbreak.config import StrategyParams                                     # noqa: E402
from qbreak.unified import UnifiedEngine                                      # noqa: E402

from test_live_unified import CC, CFG, EX, P, _frame                          # noqa: E402


def _ind(close, dead=(), sar=None):
    a = _frame(close, entry=(10,), dead=dead)
    if sar is not None:
        a["sar_flip"] = a.index.isin(a.index[list(sar)])
    core = _frame([700.0] * len(close))
    core["entry"] = False
    return {"A.T": a, "1655.T": core}, pd.Series(True, index=core.index)


def _run(ind, bear, p):
    e = UnifiedEngine(ind, CFG, {"JP": p, "US": p}, EX, CC, bear={"US": bear})
    r = e.run(ind["1655.T"].index[5])
    tr = r.trades[r.trades["ticker"] == "A.T"]
    return tr.iloc[0] if len(tr) else None


def test_modes_apply_and_default():
    assert set(EXR.MODES) == {"DC", "X6", "R4", "X6R4", "ALL"} and EXR.CHANDELIER_K == EF.CHANDELIER_K == 3.0
    x6 = EXR.apply(P, "X6")
    assert (x6.exit_on_macd_dead_cross, x6.exit_chandelier_k, x6.exit_sar_flip) == (False, 3.0, False)
    assert x6.stop_loss_pct == P.stop_loss_pct and x6.max_hold_days == P.max_hold_days                    # 其余不变
    assert EXR.mode_of({}) == "DC" and EXR.mode_of({"exits": {"JP": "R4"}}) == "R4" and EXR.mode_of({"exits": {"JP": "??"}}) == "DC"
    with pytest.raises(KeyError):
        EXR.apply(P, "nope")
    d = StrategyParams()
    assert d.exit_chandelier_k == 0.0 and d.exit_sar_flip is False                                          # 默认 = 原规则


def test_chandelier_exit_same_day_as_forward_definition():
    close = [1000.0] * 12 + [1030.0, 1060.0, 1080.0, 1100.0, 1000.0] + [1000.0] * 13
    ind, bear = _ind(close, dead=(22,))
    dc = _run(ind, bear, EXR.apply(P, "DC"))
    x6 = _run(ind, bear, EXR.apply(P, "X6"))
    idx = ind["A.T"].index
    assert dc["reason"] == "dead_cross" and pd.Timestamp(dc["exit_date"]) == idx[23]                   # 死叉第二天开盘卖
    assert x6["reason"] == "chandelier" and x6["entry_date"] == dc["entry_date"] and x6["entry_px"] == dc["entry_px"]
    k = int(idx.get_loc(pd.Timestamp(x6["entry_date"])))
    flags = EF.chandelier_flags(ind["A.T"], k, float(x6["entry_px"]))
    first = int(np.flatnonzero(flags)[0])
    assert pd.Timestamp(x6["exit_date"]) == idx[first + 1]                                                 # 前向记录的定义成立的第二天开盘


def test_sar_flip_exit_only_when_enabled():
    close = [1000.0] * 12 + [1020.0] * 18
    ind, bear = _ind(close, dead=(25,), sar=(15,))
    dc = _run(ind, bear, EXR.apply(P, "DC"))
    r4 = _run(ind, bear, EXR.apply(P, "R4"))
    both = _run(ind, bear, EXR.apply(P, "ALL"))
    idx = ind["A.T"].index
    assert dc["reason"] == "dead_cross" and pd.Timestamp(dc["exit_date"]) == idx[26]                   # SAR 列在但没打开 → 不看
    assert r4["reason"] == "sar_flip" and pd.Timestamp(r4["exit_date"]) == idx[16]
    assert both["reason"] == "sar_flip" and pd.Timestamp(both["exit_date"]) == idx[16]                 # ALL：哪个先到用哪个
    ind2, bear2 = _ind(close, dead=(14,), sar=(20,))
    assert _run(ind2, bear2, EXR.apply(P, "ALL"))["reason"] == "dead_cross"
    assert _run(ind2, bear2, EXR.apply(P, "R4"))["reason"] == "sar_flip"                                 # R4：死叉不算


def test_indicators_and_single_ticker_engine_guard():
    from qbreak.config import BacktestConfig
    from qbreak.engine import run_backtest
    from qbreak.strategy import compute_indicators
    from conftest import make_frame
    rng = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
    df = make_frame([(x, x * 1.01, x * 0.99, x, 1e6) for x in c])
    base = compute_indicators(df, StrategyParams())
    assert "sar_flip" not in base.columns
    on = compute_indicators(df, EXR.apply(StrategyParams(), "R4"))
    assert np.array_equal(on["sar_flip"].to_numpy(bool), EF.sar_flip(on))
    with pytest.raises(NotImplementedError):
        run_backtest({"X.T": base}, EXR.apply(StrategyParams(), "X6"), BacktestConfig())
