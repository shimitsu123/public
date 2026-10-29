"""卖出判定的确认（scripts/sell_confirm.py）：逐信号配对、比较与区间、卖对率逐笔版与探索的合计一致、判定规则。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from conftest import make_indicator_frame
from qbreak.config import BacktestConfig, StrategyParams

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sell_common as SC                                                     # noqa: E402
import sell_confirm as SCF                                                   # noqa: E402
import sell_explore as SX                                                    # noqa: E402

FLAT = (100.0, 101.0, 99.0, 100.0, 1e6)
RISE = [FLAT] * 5 + [FLAT, (100, 103, 99, 102, 1e6), (102, 106, 101, 105, 1e6), (105, 110, 104, 109, 1e6),
                     (109, 115, 108, 114, 1e6), (114, 120, 113, 118, 1e6), (118, 119, 110, 111, 1e6), (111, 112, 110, 111, 1e6)] + [FLAT] * 3


def _bt():
    bt = BacktestConfig.for_market("JP", 5, "tachibana")
    bt.sizing.initial_cash, bt.sizing.position_pct, bt.sizing.max_positions, bt.sizing.max_position_pct = 1e10, 1.0, 1, 1.0
    bt.exec_cfg.slippage_pct = 0.0
    return bt


def _p():
    return StrategyParams(stop_loss_pct=7, take_profit_pct=0, trailing_stop_pct=0, max_hold_days=60, exit_on_macd_dead_cross=True)


def _frame(rows, entries, deads):
    df = make_indicator_frame(rows, entries=entries, deads=deads)
    df["macd"], df["macd_sig"] = 0.0, 0.0
    return df


def test_paired_only_changes_exit(monkeypatch):
    df = _frame(RISE, {5}, {11})                                             # 现行：第 11 天死叉 → 第 12 天开盘 111 卖（+11%）
    S = SC.signals(df)
    early = np.zeros(len(df), bool)
    early[8] = True                                                          # 变体：第 8 天就成立 → 第 9 天开盘 109 卖（+9%）
    S["_t_early"] = early
    monkeypatch.setitem(SC.VARIANTS, "T1", {"fam": "A", "zh": "测试", "sig": "_t_early", "mode": "or"})
    P = SCF.paired({"A.T": df}, pd.DataFrame({"ticker": ["A.T", "A.T", "B.T"], "date": [df.index[5], df.index[-1], df.index[5]]}),
                   _p(), _bt(), 0.1, ["T1"], {"A.T": S})
    assert len(P) == 1                                                       # 最后一根 K 线的信号、没行情的票 → 没有
    r = P.iloc[0]
    assert r["net"] == pytest.approx(11.0 - 0.1) and r["net_T1"] == pytest.approx(9.0 - 0.1)
    assert r["hold"] == 6 and r["hold_T1"] == 3


def test_paired_drops_unclosed():
    rows = [FLAT] * 5 + [FLAT, (100, 103, 99, 102, 1e6)] + [FLAT] * 3        # 买入后一直不卖 → 期末未平仓 → 不算
    df = _frame(rows, {5}, set())
    P = SCF.paired({"A.T": df}, pd.DataFrame({"ticker": ["A.T"], "date": [df.index[5]]}), _p(), _bt(), 0.1, ["A1"], {})
    assert len(P) == 0


def _pairs(n=300, d=(-2.0, 3.0), seed=0):
    rng = np.random.default_rng(seed)
    cur = rng.normal(0.6, 5, n)
    var = cur + rng.normal(*d, n)
    dates = pd.to_datetime("2003-01-01") + pd.to_timedelta(rng.integers(0, 1500, n), unit="D")
    return pd.DataFrame({"date": dates, "net": cur, "hold": 11, "net_A1": var, "hold_A1": 6})


def test_compare_and_ci():
    P = _pairs()
    x = SCF.compare(P, "A1")
    assert x["n"] == 300 and x["dmean"] == pytest.approx(P["net_A1"].mean() - P["net"].mean())
    assert x["dmean_lo"] < x["dmean"] < x["dmean_hi"] and x["dwin_lo"] <= x["dwin"] <= x["dwin_hi"]
    assert x["dmean_hi"] < 0                                                 # 每笔平均少 2 pp → 区间都在 0 以下
    assert SCF.compare(P, "A2") == {"n": 0}
    assert "dwin_lo" not in SCF.compare(P, "A1", ci=False)


def test_decide_rules():
    def c(dwin_lo, davg, dmean, dmean_lo=-1.0):
        return {"n": 100, "dwin_lo": dwin_lo, "davg_win": davg, "dmean": dmean, "dmean_lo": dmean_lo}
    acc = {"dead_cross": {"right_pct": 47.0}, "_every_day": {"right_pct": 48.5}}
    V = SCF.decide({"A1": c(0.5, -1.0, -0.2), "A2": c(1.0, -2.0, -0.4), "A3": c(-0.5, -1.0, -0.1)}, acc, {"lo": 0.4})
    assert V["trade_off"] and V["per_variant"]["A3"] == {"H1": False, "H2": True, "exception": False}
    assert V["H3"] and V["H4"] and V["H3_diff"] == pytest.approx(-1.5)
    V2 = SCF.decide({"A1": c(0.5, -1.0, 0.1), "A2": c(1.0, 0.5, -0.4), "A3": c(2.0, -1.0, 0.8, 0.2)},
                    {"dead_cross": {"right_pct": 40.0}, "_every_day": {"right_pct": 48.0}}, {"lo": -0.1})
    assert not V2["trade_off"] and V2["exception"] == ["A3"] and not V2["H3"] and not V2["H4"]


def test_accuracy_rows_match_explore_aggregate():
    rng = np.random.default_rng(5)
    n = 300
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n)))
    o = c * (1 + rng.normal(0, 0.005, n))
    df = pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.01, "Low": np.minimum(o, c) * 0.99, "Close": c},
                      index=pd.bdate_range("2004-01-01", periods=n))
    df["macd"] = pd.Series(c).ewm(span=12).mean().to_numpy() - pd.Series(c).ewm(span=26).mean().to_numpy()
    df["macd_sig"] = pd.Series(df["macd"].to_numpy()).ewm(span=9).mean().to_numpy()
    df["dead_cross"] = SC.cross_down(df["macd"], df["macd_sig"])
    tr = pd.DataFrame({"ticker": ["A.T"] * 4, "date": df.index[[30, 90, 150, 210]], "entry_date": df.index[[31, 91, 151, 211]],
                       "exit_date": df.index[[45, 110, 160, 240]], "exit_px": c[[45, 110, 160, 240]]})
    names = ["dead_cross", "ha_bear2", "rsi70_down"]
    A, every = SCF.accuracy_rows({"A.T": df}, tr, {}, 0.0005, names)
    s = SCF.accuracy_summary(A, every, names)
    ref = SX.judge_accuracy({"A.T": df}, tr, {}, 0.0005, names=names)
    for k in [*names, "_every_day"]:
        assert s[k]["n"] == ref[k]["n"]
        if ref[k]["right_pct"] is not None:
            assert s[k]["right_pct"] == pytest.approx(ref[k]["right_pct"], abs=0.051)
            assert s[k]["fwd_mean"] == pytest.approx(ref[k]["fwd_mean"], abs=0.006)
    h = SCF.boot_h4(pd.concat([A] * 5, ignore_index=True).assign(date=pd.date_range("2004-01-01", periods=20, freq="MS")))
    assert h["n"] >= 10 and h["lo"] <= h["diff"] <= h["hi"]


def test_registered_constants():
    assert SCF.TESTED == ("A1", "A2", "A3") and (SCF.BOOT_N, SCF.SEED, SCF.H3_TOL) == (2000, 20260928, 3.0)
    assert SCF.W_WIN == ("2006-10-01", "2016-09-30") and SX.LOOK == 60 and SX.FWD == 10
