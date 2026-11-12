"""第九个研究循环第 2 轮（scripts/loop9_r02_marketday.py）的纯函数。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import loop9_r02_marketday as R  # noqa: E402


def test_big_up_days_threshold():
    c = pd.Series([100.0, 101.6, 101.0, 102.4], index=pd.bdate_range("2020-01-06", periods=4))
    assert list(R.big_up_days(c)) == [False, True, False, False]           # +1.6% 算；−0.6%、+1.39% 不算


def test_prev_close_gate_uses_strictly_earlier_us_day():
    us = pd.Series([True, False, True], index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]))
    jp = pd.DatetimeIndex(pd.to_datetime(["2020-01-02", "2020-01-06", "2020-01-07"]))
    # 1/2：之前没有美国收盘 → 不成立；1/6：用 1/3（False）；1/7：用 1/6（True）
    assert list(R.prev_close_gate(us, jp)) == [False, False, True]


def test_align_dispatches_by_market():
    days = pd.bdate_range("2020-01-06", periods=3)
    jp = pd.Series([False, True, False], index=days)
    assert list(R.align(("jp", jp), days)) == [False, True, False]
    us = pd.Series([True, False, True], index=days)
    assert list(R.align(("us", us), days)) == [False, True, False]
    assert R.align(("us", us.iloc[:0]), days).sum() == 0                   # 没有美国数据 → 不挡


def test_render_shared_table_has_all_checks():
    import loop9_common as C9
    acct = {"cagr": 10.0, "dd": -20.0, "calmar": 0.5, "h1": 0.4, "h2": 0.6, "n": 10, "mean": 1.0, "win": 50.0}
    s1 = {"sum": 0.01, "d": {e: 0.0 for e in C9.ERAS}, "h1": 0.0, "h2": 0.0, "ok": False,
          **{x: True for x in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")},
          "success": {"base": {"win": 50.0, "mean": 1.0}, "cand": {"win": 51.0, "mean": 1.1}}}
    other = {x: {"gone_n": 1, "n": 10, "gone_win": 0.0, "gone_mean": -1.0, "dwin": 1.0, "dmean": 0.1} for x in ("W", "Jx")}
    res = {"ids": ["AAA"], "code": "abc", "dirty": False, "drift": {e: 0.0 for e in C9.ERAS},
           "base": {e: acct for e in C9.ERAS}, "cand": {"AAA": {e: acct for e in C9.ERAS}},
           "scale": {e: {"AAA": {"signals_blocked": 1, "trades_blocked": 0}} for e in C9.ERAS},
           "gate_days_pct": {"AAA": {e: 10.0 for e in C9.ERAS}}, "stage1": {"AAA": s1}, "other": {"AAA": other}, "seconds": 1}
    md = C9.render(res, "# t")
    assert md.startswith("# t") and "S8 ✓" in md and "第一关不过" in md and "非投资建议" in md
