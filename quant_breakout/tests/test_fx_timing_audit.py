"""事后审计 scripts/fx_timing_audit.py：修正口径只改汇率的时点（东证 d 日用 d 当天（含）以前最近的 Yahoo 值），美国收盘仍用 d 之前的；与原口径的差别。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import equity_idle_study as EI  # noqa: E402
import fx_timing_audit as A  # noqa: E402


def test_same_day_fx_vs_original_prev_fx(monkeypatch):
    days = pd.to_datetime(["2024-07-10", "2024-07-11", "2024-07-12"])
    us = pd.Series([100.0, 101.0, 102.0], index=pd.to_datetime(["2024-07-09", "2024-07-10", "2024-07-11"]))
    fx = pd.Series([160.0, 161.0, 158.0], index=days)                       # Yahoo：东证当天早上的值
    monkeypatch.delenv(EI.FX_ALIGN_ENV, raising=False)
    assert EI.on_jp(us, fx, days).equals(A.on_jp_same_day(us, fx, days))     # 2026-10-03 ㊼ ① 起：研究口径 = 修正口径
    monkeypatch.setenv(EI.FX_ALIGN_ENV, "prev")                              # 以前的口径（只为重现以前的结果）
    o = EI.on_jp(us, fx, days)
    f = A.on_jp_same_day(us, fx, days)
    assert o.loc["2024-07-12"] == 102.0 * 161.0                              # 原口径：美国 7-11 收盘 × 汇率用 d 之前（7-11 早上）
    assert f.loc["2024-07-12"] == 102.0 * 158.0                              # 修正口径：美国收盘相同 × 汇率用 d 当天（7-12 早上）
    assert f.loc["2024-07-10"] == 100.0 * 160.0 and np.isnan(o.get(pd.Timestamp("2024-07-10"), np.nan))
    assert A.on_jp_same_day(us, None, days).equals(EI.on_jp(us, None, days))  # 不换汇的（对冲版等）两种口径相同


def test_effects_and_events():
    acc = {e: {k: {"calmar": v} for k, v in zip(("B0", "B1", "B2", "CRW"), vals)}
           for e, vals in (("Z", (1.0, 1.1, 1.3, 1.2)), ("E", (0.5, 0.6, 0.7, 0.7)), ("J", (0.6, 0.5, 0.6, 0.7)))}
    ef = A.effects(acc)
    assert ef["FJE（B1 − B0）"] == {"Z": 0.1, "E": 0.1, "J": -0.1, "sum": 0.1}
    assert ef["CRW（CRW − B2）"]["sum"] == round(-0.1 + 0.0 + 0.1, 3)
    assert [d for d, _ in A.EVENTS] == ["2010-09-15", "2011-03-18", "2016-01-29", "2022-09-22", "2024-07-11"]
