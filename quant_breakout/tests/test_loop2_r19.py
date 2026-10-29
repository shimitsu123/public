"""第二个研究循环第 19 轮 EBX（scripts/loop2_r19_earnexit.py，2026-10-02 登记）：登记值 = 实盘常数、开示日口径、
触发成交日 = 实盘同一个数日子的函数（逐日暴力算法核对，含黄金周与周六开示）、触发收盘日映射、单笔模拟的旗标、
EBG 只描述的信号判定、账户交易的计数、引擎钩子（只有一个 _check_exits、缺省关、会触发）、命令行。"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import loop2_r19_earnexit as T  # noqa: E402

TS = pd.Timestamp


def test_registered_constants_match_live_code():
    import inspect
    from qbreak import trader
    assert (T.ROUND, T.IDS, T.FAMILY, T.POSTHOC) == (19, ("EBX",), "个股层·决算日程", False)
    assert T.EXIT_E == 1 and "earnings_in_days <= 1" in inspect.getsource(trader.exit_reason)
    live = json.loads((ROOT / "var" / "best_params.json").read_text(encoding="utf-8"))
    assert T.BLACKOUT == live["earnings_blackout_days"] == 2 and live["exit_before_earnings"] is False


def test_disclosure_dates_first_per_period_only_fs():
    F = pd.DataFrame({
        "DiscDate": ["2019-08-01", "2019-08-01", "2019-08-20", "2019-10-01", "2020-05-12", "2024-11-12"],
        "Code": ["72030", "72030", "72030", "72030", "72030", "285A0"],
        "DocType": ["1QFinancialStatements_Consolidated_JP", "1QFinancialStatements_NonConsolidated_JP",
                    "1QFinancialStatements_Consolidated_JP",                       # 订正（同一期、更晚）→ 不算
                    "EarnForecastRevision",                                        # 予想修正 → 不是決算短信
                    "FYFinancialStatements_Consolidated_JP", "2QFinancialStatements_Consolidated_IFRS"],
        "CurPerType": ["1Q", "1Q", "1Q", "", "FY", "2Q"],
        "CurFYEn": ["2020-03-31", "2020-03-31", "2020-03-31", "2020-03-31", "2020-03-31", "2025-03-31"]})
    d = T.disclosure_dates(F)
    assert list(d["7203.T"]) == [TS("2019-08-01"), TS("2020-05-12")]
    assert list(d["285A.T"]) == [TS("2024-11-12")]
    assert T.data_from(d) == TS("2019-08-01")


def _cal_days(a: str, b: str) -> pd.DatetimeIndex:
    from qbreak.calendar_jp import is_trading_day
    return pd.DatetimeIndex([d for d in pd.date_range(a, b) if is_trading_day(d.date())])


DISC = pd.DatetimeIndex(["2019-05-08", "2019-05-10", "2019-05-18"])       # 黄金周之后的周三、周五；周六开示


@pytest.mark.parametrize("n", [1, 2])
def test_trigger_fills_equal_daily_live_rule_across_golden_week(n):
    from qbreak.events import trading_days_until
    days = _cal_days("2019-04-10", "2019-05-31")
    brute = []
    for f in days:                                                          # 逐日：f 当天或之后第一个开示日、实盘同一个函数
        k = int(DISC.searchsorted(f))
        if k < len(DISC) and trading_days_until(DISC[k].date(), f.date(), "JP") <= n:
            brute.append(f)
    assert list(T.trigger_fills(DISC, days, n)) == brute


def test_trigger_fills_values_and_since():
    days = _cal_days("2019-04-10", "2019-05-31")
    assert list(T.trigger_fills(DISC, days, 1)) == [TS(x) for x in ("2019-05-07", "2019-05-08", "2019-05-09", "2019-05-10",
                                                                    "2019-05-16", "2019-05-17")]
    two = T.trigger_fills(DISC, days, 2)
    assert TS("2019-04-26") in two                                          # 中间是 10 连休，实际只隔 2 个交易日
    assert TS("2019-04-26") not in T.trigger_fills(DISC, days, 2, since=TS("2019-05-01"))   # 数据开始之前 → 不算


def test_exit_tick_is_previous_trading_day():
    days = _cal_days("2019-04-10", "2019-05-31")
    tick = T.exit_tick(days, {"7203.T": pd.DatetimeIndex(["2019-05-07", "2019-05-13"]), "6758.T": pd.DatetimeIndex([days[0]])})
    assert tick == {"7203.T": frozenset([TS("2019-04-26"), TS("2019-05-10")])}   # 第一天没有前一天 → 跳过；空的票不留


def test_ebx_flags_from_entry_bar_on():
    idx = _cal_days("2019-04-22", "2019-05-20")
    fills = T.trigger_fills(DISC, idx, 1)
    f = T.ebx_flags(idx, int(idx.get_loc(TS("2019-04-26"))), fills)
    assert list(idx[f]) == [TS(x) for x in ("2019-04-26", "2019-05-07", "2019-05-08", "2019-05-09", "2019-05-15", "2019-05-16")]
    g = T.ebx_flags(idx, int(idx.get_loc(TS("2019-05-10"))), fills)           # 5/10（开示日）开盘买 → 拿着过开示，下一次是 5/18 之前
    assert list(idx[g]) == [TS("2019-05-15"), TS("2019-05-16")]
    assert not T.ebx_flags(idx, 0, pd.DatetimeIndex([])).any()


def test_signal_hit_uses_next_trading_day_and_since():
    disc = {"7203.T": DISC}
    tk = ["7203.T", "7203.T", "7203.T", "7203.T", "9999.T"]
    sd = ["2019-04-25", "2019-05-08", "2019-05-10", "2019-05-14", "2019-05-08"]
    assert list(T.signal_hit(tk, sd, disc, 2, None)) == [True, True, False, True, False]
    assert list(T.signal_hit(tk, sd, disc, 2, TS("2019-05-01"))) == [False, True, False, True, False]


def test_trade_counts():
    tr = pd.DataFrame({
        "ticker": ["7203.T", "7203.T", "1655.T", "US_UH", "6758.T", "7203.T"],
        "entry_date": ["2019-05-07", "2019-05-13", "2019-05-07", "2019-05-07", "2019-05-08", "2018-05-07"],
        "exit_date": ["2019-05-20", "2019-05-14", "2019-05-09", "2019-05-09", "2019-05-31", "2018-05-20"],
        "reason": ["x6", "pre_earnings", "core", "core", "end", "x6"],
        "pnl": [1000.0, -500.0, 10.0, 10.0, 0.0, 5.0], "shares": [100, 100, 10, 10, 100, 100], "entry_px": [100.0] * 6})
    f2 = {"7203.T": pd.DatetimeIndex(["2019-05-07", "2018-05-07"]), "6758.T": pd.DatetimeIndex(["2019-05-08"])}
    assert T.entries_on(tr, f2, "2019-01-01", "2019-12-31") == {"entries": 3, "on": 2}
    tick = {"7203.T": frozenset([TS("2019-05-10"), TS("2019-05-14")]), "6758.T": frozenset([TS("2019-05-30")])}
    assert T.held_through(tr, tick, "2019-01-01", "2019-12-31") == 2          # 7203（5/7〜5/20 拿着过 5/10）、6758（未平仓、5/30）；5/13 买 5/14 卖 → 不算
    assert T.pre_exits(tr, "2019-01-01", "2019-12-31") == 1


def test_engine_hook_single_check_exits_and_default_off():
    import inspect
    import candle_portfolio as CP
    src = inspect.getsource(CP.MixEngine)
    assert src.count("def _check_exits") == 1 and "self._tick_exit(i, xt)" in src and "self._opp_exit(i, ox)" in src
    assert CP.MixEngine.EXIT_TICK is None


class _Pos:
    def __init__(self, market):
        self.market = market


class _St:
    def __init__(self):
        self.pos = {"7203.T": _Pos("JP"), "6758.T": _Pos("JP"), "AAPL": _Pos("US")}
        self.pending_exit = {"6758.T": "x6"}


def test_tick_exit_marks_only_held_jp_on_listed_days():
    import candle_portfolio as CP
    eng = CP.MixEngine.__new__(CP.MixEngine)                                 # 只测这个方法：不跑完整引擎
    eng.gidx = pd.DatetimeIndex(["2019-05-09", "2019-05-10"])
    eng.st = _St()
    xt = {"7203.T": frozenset([TS("2019-05-10")]), "6758.T": frozenset([TS("2019-05-09")]), "AAPL": frozenset([TS("2019-05-09")])}
    eng._tick_exit(0, xt)
    assert eng.st.pending_exit == {"6758.T": "x6"}                           # 6758 已排队（不改原因）、AAPL 不是日本股、7203 不是这一天
    eng._tick_exit(1, xt)
    assert eng.st.pending_exit == {"6758.T": "x6", "7203.T": "pre_earnings"}


def test_run_passes_and_resets_exit_tick():
    import inspect
    import candle_portfolio as CP
    src = inspect.getsource(CP.make_runner)
    assert "exit_tick: dict | None = None" in src and "MixEngine.EXIT_TICK = exit_tick or None" in src
    assert src.count("MixEngine.EXIT_TICK = None") == 1


def test_wiring_and_cli():
    import inspect
    src = inspect.getsource(T.stage_one)
    assert "L2.run(W, e, exit_tick=tick)" in src and "rb = L2.run(W, e)" in src
    with pytest.raises(SystemExit):
        T.main(["--stage2"])
    with pytest.raises(SystemExit):
        T.main(["--scale", "--wiring"])
    assert np.array_equal(T.ebx_flags(pd.DatetimeIndex([]), 0, None), np.zeros(0, bool))
