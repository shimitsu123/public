"""第二个研究循环第 20 轮 TPX（scripts/loop2_r20_notp.py，2026-10-02 登记）：登记值、只关掉止盈（其余参数相同）、
只给日本个股、引擎的 _p 用 params_t、单笔模拟两边同一个买入、账户交易的计数、接法、命令行。"""
import json
import sys
from dataclasses import fields
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop2_r20_notp as T  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.TP_OFF) == (20, ("TPX",), "个股层·止盈", False, 0.0)
    live = json.loads((ROOT / "var" / "best_params.json").read_text(encoding="utf-8"))
    assert live["take_profit_pct"] == 25.0                                  # 现行 +25%（登记时）


def test_tp_off_changes_only_take_profit():
    from qbreak.config import StrategyParams
    p = StrategyParams()
    q = T.tp_off(p)
    diff = [f.name for f in fields(StrategyParams) if getattr(p, f.name) != getattr(q, f.name)]
    assert diff == ["take_profit_pct"] and q.take_profit_pct == 0.0


def test_params_t_only_jp_stocks():
    pt = T.params_t(["7203.T", "1655.T", "US_UH", "285A.T"], "P")
    assert pt == {"7203.T": "P", "285A.T": "P"}


def test_engine_p_uses_params_t():
    import inspect
    import candle_portfolio as CP
    assert "MixEngine.PARAMS_T.get(t) or super()._p(t)" in inspect.getsource(CP.MixEngine._p)


def test_take_profit_zero_means_off_in_both_engines():
    import inspect
    from qbreak import engine, unified
    assert "if p.take_profit_pct else np.inf" in inspect.getsource(unified.UnifiedEngine._check_exits)
    assert "take_profit_pct" in inspect.getsource(engine.run_backtest)


def test_trade_counts():
    tr = pd.DataFrame({
        "ticker": ["7203.T", "7203.T", "1655.T", "US_UH", "6758.T"],
        "entry_date": ["2019-05-07", "2019-05-13", "2019-05-07", "2019-05-07", "2018-05-08"],
        "reason": ["take_profit", "chandelier", "take_profit", "core", "take_profit"]})
    assert len(T.jp_stock_trades(tr, "2019-01-01", "2019-12-31")) == 2
    assert T.tp_exits(tr, "2019-01-01", "2019-12-31") == 1                  # 核心与窗口外的不算


def test_trade_pair_same_entry_both_sides(monkeypatch):
    from qbreak import exit_forward as XF
    calls = []

    def fake_one(t, f, p, bt, d, end):
        calls.append(p)
        return {"entry_date": "2019-05-08", "exit_date": "2019-06-01" if p == "P1" else "2019-05-20",
                "reason": "take_profit" if p == "P0" and len(calls) == 2 else "dead_cross", "ret_pct": 10.0 if p == "P1" else 25.0}
    monkeypatch.setattr(XF, "_one", fake_one)
    monkeypatch.setattr(XF, "chandelier_flags", lambda f, k, px: np.zeros(len(f), bool))

    class _Ex:
        slippage_pct = 0.1

    class _Bt:
        exec_cfg = _Ex()
    idx = pd.bdate_range("2019-05-01", periods=30)
    df = pd.DataFrame({"Open": 100.0, "Close": 100.0, "entry": False, "dead_cross": False}, index=idx)
    x = T.trade_pair("7203.T", df, idx[4], "P0", "P1", _Bt(), 20)
    assert calls == ["P0", "P0", "P1"] and x == {"x6": 25.0, "tpx": 10.0, "changed": True, "tp": True}


def test_wiring_and_cli():
    import inspect
    src = inspect.getsource(T.stage_one)
    assert "params_t=params_t(W[\"ctx\"][e][\"names\"], p1)" in src and "rb = L2.run(W, e)" in src
    with pytest.raises(SystemExit):
        T.main(["--stage2"])
    with pytest.raises(SystemExit):
        T.main(["--scale", "--wiring"])
