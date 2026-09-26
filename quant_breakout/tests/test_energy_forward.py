"""scripts/energy_forward.py：月末状态（当月最后一个记录日、没记录的月份 = 不满足）、信号日的新仓系数（前向期之前 1 倍）、判定时点与判定。"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import energy_forward as EF                                                   # noqa: E402


def _T(rows):
    T = pd.DataFrame(rows, columns=["date", "on"])
    T["date"] = pd.to_datetime(T["date"])
    return T


def test_monthly_states_last_record_and_gap_month():
    T = _T([("2026-09-28", False), ("2026-09-30", True), ("2026-10-05", True), ("2026-10-30", False), ("2026-12-01", True)])
    S = EF.monthly_states(T)
    assert list(S.index.strftime("%Y-%m-%d")) == ["2026-09-30", "2026-10-31", "2026-11-30", "2026-12-31"]
    assert list(S) == [True, False, False, True]                               # 11 月没有记录 → 不满足


def test_signal_factor_uses_previous_month_end_and_start():
    S = pd.Series([True, False], index=pd.DatetimeIndex(["2026-09-30", "2026-10-31"]))
    d = pd.DatetimeIndex(["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-30", "2026-11-02"])
    f = EF.signal_factor(S, d)
    assert list(f) == [1.0, 0.5, 0.5, 0.5, 1.0]                                # 9 月末满足 → 10 月的信号日减半；10 月末不满足 → 11 月照常
    early = EF.signal_factor(pd.Series([True], index=pd.DatetimeIndex(["2026-08-31"])), pd.DatetimeIndex(["2026-09-25", "2026-09-28"]))
    assert list(early) == [1.0, 0.5]                                           # 前向期（2026-09-28）之前一律 1 倍
    assert list(EF.signal_factor(pd.Series(dtype=bool), d)) == [1.0] * 5


def test_decide_forward_stages_and_rules():
    b, good = {"cagr": 10.0, "dd": -20.0, "calmar": 0.5}, {"cagr": 12.0, "dd": -19.0, "calmar": 0.63}
    assert EF.decide_forward(b, good, 100, "2028-01-01")["stage"] is None       # 3 年之前只报告进度
    v = EF.decide_forward(b, good, 100, "2029-10-01")
    assert v["stage"] == "3 年" and v["verdict"].startswith("前向成立")
    assert EF.decide_forward(b, good, 30, "2029-10-01")["verdict"] == "暴露不够，继续记录"
    bad = EF.decide_forward(b, {"cagr": 9.0, "dd": -23.0, "calmar": 0.39}, 100, "2031-10-01")
    assert bad["stage"] == "5 年" and "建议停止记录" in bad["verdict"] and len(bad["fails"]) == 2


def test_completeness_counts_missing_trading_days():
    T = _T([("2026-09-28", True), ("2026-09-30", True), ("2026-10-03", False)])  # 10-03 是周六（多出来的不算错）
    c = EF.completeness(T, "2026-10-02")
    assert c["expected"] == 5 and c["recorded"] == 2 and c["missing"] == ["2026-09-29", "2026-10-01", "2026-10-02"]
    assert EF.completeness(_T([]), "2026-09-28")["missing"] == ["2026-09-28"]
