"""「质的飞跃」确认框架（scripts/leap_confirm.py）的纯函数：逐笔按买入日分窗口、过滤掩码、保留比例。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import leap_confirm as LF  # noqa: E402


def test_trade_stats_by_entry_date_and_net_of_fees():
    tr = pd.DataFrame({"entry_date": ["2001-02-01", "2004-03-01", "2006-12-01"], "pnl": [900.0, -500.0, 100.0],
                       "shares": [100, 100, 100], "entry_px": [1000.0, 1000.0, 1000.0]})
    s = LF.trade_stats(tr, "2001-01-04", "2006-09-30")
    assert s["n"] == 2 and np.isclose(s["mean"], (0.9 - 0.5) / 2) and s["win"] == 50.0
    assert LF.trade_stats(tr, "2006-10-01", None)["n"] == 1
    assert LF.trade_stats(tr.iloc[:0], "2001-01-04", None) == {"n": 0, "mean": None, "win": None}


def test_masks_and_keep_fraction():
    idx = pd.bdate_range("2020-01-01", periods=4)
    fr = {"A.T": pd.DataFrame({"entry": [True, False, True, True]}, index=idx), "B.T": pd.DataFrame({"entry": [True] * 4}, index=idx)}
    keep = {"A.T": np.array([True, True, False, True])}
    out = LF.with_mask(fr, keep)
    assert out["A.T"]["entry"].tolist() == [True, False, False, True] and out["B.T"]["entry"].all()
    assert np.isclose(LF.keep_frac(fr, keep), 6 / 7)
    assert not any(df["entry"].any() for df in LF.no_entries(fr).values())


def test_windows_follow_charter():
    w = LF._windows("Z")
    assert w["Z"] == ("2001-01-04", "2006-09-30") and w["Z1"][1] == "2003-12-31" and w["Z2"][0] == "2004-01-01"


def test_placebo_trades_takes_percentiles_of_win_mean_calmar(monkeypatch):
    idx = pd.bdate_range("2020-01-06", periods=20)
    fr = {"A.T": pd.DataFrame({"entry": [True] * 20}, index=idx)}
    calls = []

    def fake_run(ctx, run_fn, f, p, **kw):
        k = int(f["A.T"]["entry"].sum())
        calls.append((k, kw))
        return {"Z": {"win": float(k), "mean": k / 10, "calmar": None if k == 0 else 1.0}}

    monkeypatch.setattr(LF, "run", fake_run)
    out = LF.placebo_trades({"era": "Z"}, None, fr, None, 0.5, seeds=10, q=95, priority={"x": 1})
    ks = [k for k, _ in calls]
    assert len(calls) == 10 and all(kw == {"priority": {"x": 1}} for _, kw in calls)
    assert set(ks) <= {0, 5, 10, 15, 20} and len(set(ks)) > 1                          # 整周一起留或一起去
    assert np.isclose(out["win"], np.percentile(ks, 95)) and np.isclose(out["mean"], np.percentile(ks, 95) / 10)
    assert len(out["vals"]["calmar"]) == 10
