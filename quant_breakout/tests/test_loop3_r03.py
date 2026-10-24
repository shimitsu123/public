"""第三个研究循环第 3 轮 FXX（scripts/loop3_r03_yenexit.py，2026-10-02 登记）：登记值、东证交易日上的对齐、急升开始日、
触发的票只有日本个股、单笔模拟的触发、离场钩子还在、ID 没用过、命令行。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop3_r03_yenexit as T  # noqa: E402
import research_loop3 as R3  # noqa: E402


def test_registered_constants():
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC, T.KIND, T.REASON) == (3, ("FXX",), "个股层·日元急升离场", False, "stock", "pre_earnings")
    assert T.KIND in R3.KINDS and T.FAMILY not in R3.BANNED
    assert not set(T.IDS) & R3.previous_ids(ROOT / "var")                    # 第一 / 第二个循环没用过


def test_tse_state_carries_us_dates_forward():
    us = pd.Series([False, True, True, False], index=pd.to_datetime(["2024-07-03", "2024-07-05", "2024-07-08", "2024-07-10"]))
    days = pd.to_datetime(["2024-07-04", "2024-07-05", "2024-07-08", "2024-07-09", "2024-07-10", "2024-07-11"])
    assert list(T.tse_state(us, days)) == [False, True, True, True, False, False]
    early = pd.to_datetime(["2024-07-01", "2024-07-02"])
    assert list(T.tse_state(us, early)) == [False, False]                     # 更早没有值 = 不是


def test_onsets_are_off_to_on_transitions():
    days = pd.bdate_range("2024-01-01", periods=8)
    s = pd.Series([True, True, False, True, True, False, False, True], index=days)
    assert list(T.onsets(s, days)) == [days[0], days[3], days[7]]            # 第一天就是「是」也算开始
    assert len(T.onsets(pd.Series(False, index=days), days)) == 0


def test_exit_tick_only_japanese_stocks():
    od = pd.to_datetime(["2024-08-01"])
    tick = T.exit_tick(["7203.T", "2845.T", "1545.T", "AAPL", "6758.T"], od)
    assert set(tick) == {"7203.T", "6758.T"} and tick["7203.T"] == frozenset(od)
    assert T.exit_tick(["7203.T"], pd.DatetimeIndex([])) == {}


def test_fxx_flags_from_entry_bar_on():
    idx = pd.bdate_range("2024-01-01", periods=6)
    od = [idx[1], idx[4]]
    assert list(T.fxx_flags(idx, 2, od)) == [False, False, False, False, True, False]
    assert list(T.fxx_flags(idx, 1, od)) == [False, True, False, False, True, False]   # 买入当天就是开始日 → 第二天开盘卖
    assert not T.fxx_flags(idx, 9, od).any()


def test_engine_hook_still_there():
    import inspect
    import candle_portfolio as CP
    assert hasattr(CP.MixEngine, "EXIT_TICK") and "pre_earnings" in inspect.getsource(CP.MixEngine._tick_exit)
    src = inspect.getsource(CP.make_runner)
    assert "exit_tick: dict | None = None" in src and "MixEngine.EXIT_TICK = exit_tick or None" in src


def test_wiring_and_cli():
    import inspect
    src = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in src and "exit_tick=tick" in src and "posthoc=None" in src and "trade=os_" in src
    wsrc = inspect.getsource(T.wiring)
    assert "days[-1] + pd.Timedelta(days=3650)" in wsrc and "exit_tick(names, days)" in wsrc
    with pytest.raises(SystemExit):
        T.main(["--stage2"])
    assert np.isfinite(len(T.CORE))
