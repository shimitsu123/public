"""scripts/deepdip_intl_check.py（DAX / FTSE 100 的历史核对）：事先写定的判定、按大跌段重抽、事件与前向记录同一套函数（最后一天不判）、门槛与模块一致。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import deepdip_intl_check as IC                                              # noqa: E402

from qbreak import deepdip_forward as DF                                     # noqa: E402


def _row(m, d, x60, r60):
    return {"market": m, "date": d, "x60": x60, "r60": r60}


def test_constants_match_forward_record():
    assert (IC.END, IC.EU, IC.MIN_N, IC.WIN_SHARE, IC.N_BOOT, IC.SEED) == ("2026-09-28", ("DE", "UK"), 5, 60.0, 5000, 20260929)
    assert DF.MARKETS["DE"]["thr"] == -14.0 and DF.MARKETS["UK"]["thr"] == -11.2
    assert IC.REF == {"JP": ("^N225", -15.0), "US": ("^GSPC", -12.0)}


def test_verdict_labels():
    ok = [_row("DE", f"20{i:02d}-01-01", 2.0, 3.0) for i in range(5)] + [_row("UK", f"20{i:02d}-06-01", 1.0, 1.0) for i in range(5)]
    assert IC.verdict(ok)["label"] == "方向一致" and IC.verdict(ok)["win"] == 100.0
    assert IC.verdict(ok[:4] + ok[5:])["label"] == "样本不足"                   # DAX 只有 4 个
    bad = [dict(r, x60=-1.0) for r in ok]
    assert IC.verdict(bad)["label"] == "不一致（欧洲不复现）"
    part = ok[:5] + [dict(r, x60=-0.5) for r in ok[5:]]                       # 合并 > 0 但 FTSE 100 平均 < 0
    assert IC.verdict(part)["label"] == "部分一致"
    lowwin = [dict(r, r60=-1.0) if i % 2 else r for i, r in enumerate(ok)]     # 涨的比例 50%
    assert IC.verdict(lowwin)["label"] == "部分一致"
    assert IC.verdict(ok + [_row("DE", "2026-09-01", None, None)])["n"]["DE"] == 5   # 没有 60 日结果的不算


def test_boot_ci_resamples_whole_episodes():
    rows = [_row("DE", "2008-10-06", 10.0, 10.0), _row("UK", "2008-10-08", 10.0, 10.0),   # 同一段
            _row("DE", "2011-08-08", -2.0, -2.0), _row("UK", "2016-06-24", 1.0, 1.0)]
    a, b = IC.boot_ci(rows, 2000, 1), IC.boot_ci(rows, 2000, 1)
    assert a == b and a["episodes"] == 3 and a["lo"] <= float(np.mean([10, 10, -2, 1])) <= a["hi"]
    assert IC.boot_ci([])["episodes"] == 0


def test_event_rows_same_functions_and_last_bar():
    days = pd.bdate_range("2010-01-01", "2026-12-31")
    c = pd.Series(np.linspace(100, 150, len(days)), index=days)
    c[days >= pd.Timestamp("2020-03-09")] *= 0.8
    rows = IC.event_rows("DE", c)
    assert [r["date"] for r in rows] == ["2020-03-09"]
    r = rows[0]
    assert r["r60"] == DF.fwd(c, "2020-03-09", 60) and r["base60"] == DF.base60(c, "2020-03-09")
    assert r["x60"] == round(r["r60"] - r["base60"], 2) and r["xe60"] == round(r["r60"] - IC.uncond60(c), 2)
    assert IC.event_rows("DE", c[c.index <= "2020-03-09"]) == []                # 数据最后一天不判
    IC.mark_same_time(rows, {"JP": [pd.Timestamp("2020-03-13")], "US": [pd.Timestamp("2019-01-01")]})
    assert rows[0]["same_time"] == ["JP"]
