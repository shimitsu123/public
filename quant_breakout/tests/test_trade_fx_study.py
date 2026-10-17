"""日本进出口贸易、贸易收支、日元对各国汇率 × 日経（scripts/trade_fx_study.py 登记检验）：3 个月同比与 12 个月收支比、M + 1、交叉汇率与日元强弱的符号、
条件（缺值 = 不满足）、同月相关、横向统计与判定（含 F 族族内门槛）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import trade_fx_study as T                                                   # noqa: E402


def _m(start, vals):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="ME"), dtype=float)


def test_constants():
    assert (T.LAG_TRADE, T.EXP_D, T.BAL_D, T.FX_D, T.Z_D, T.SPLIT) == (1, 10.0, 2.0, 5.0, 1.0, "2000-12-31")
    assert (T.D_MIN, T.MAX_ON, T.MIN_MONTHS, T.MIN_FOREIGN, T.SEEDS, T.N_FW) == (0.02, 50.0, 120, 5, 30, 200)
    assert len(T.CROSS) == 18 and T.CROSS["EUR"] == ("DEXJPUS", "*", "DEXUSEU") and T.CROSS["CNY"] == ("DEXJPUS", "/", "DEXCHUS")
    assert set(T.SINGLE) == {"T1", "T2", "T3", "F2", "F3"} and len(T.HZ_TRADE) == 21 and len(T.HZ_EER) == 18 and "JP" not in T.HZ_TRADE + T.HZ_EER
    assert "輸送用機器" in T.EXPORT_S33 and "小売業" in T.DOMESTIC_S33 and not set(T.EXPORT_S33) & set(T.DOMESTIC_S33)


def test_yoy3_balance_ratio_and_lag():
    x = _m("2000-01-31", [100.0] * 12 + [80.0] * 12)
    y = T.yoy3(x)
    assert abs(y.loc["2001-03-31"] - 100 * np.log(0.8)) < 1e-9 and np.isnan(y.loc["2000-12-31"])
    e, i = _m("2000-01-31", [100.0] * 24), _m("2000-01-31", [90.0] * 12 + [110.0] * 12)
    b = T.bal_ratio(e, i)
    assert abs(b.loc["2000-12-31"] - 10.0) < 1e-9 and abs(b.loc["2001-12-31"] + 10.0) < 1e-9
    bn = T.bal_ratio(e, net=e - i)
    assert abs(bn.loc["2001-06-30"] - b.loc["2001-06-30"]) < 1e-9
    lg = T.lag(b)
    assert np.isnan(lg.loc["2000-12-31"]) and abs(lg.loc["2001-01-31"] - 10.0) < 1e-9                      # m 月的值 m+1 月末才用


def test_cross_and_yen_strength_sign():
    days = pd.bdate_range("2019-01-01", "2020-12-31")
    jpus = pd.Series(np.where(days < pd.Timestamp("2020-01-01"), 100.0, 110.0), index=days)              # 日元对美元贬值 10%
    useu = pd.Series(1.2, index=days)
    chus = pd.Series(7.0, index=days)
    fx = {"DEXJPUS": jpus, "DEXUSEU": useu, "DEXCHUS": chus}
    eur, cny = T.cross(fx, "EUR"), T.cross(fx, "CNY")
    assert abs(eur.loc["2019-06-30"] - 120.0) < 1e-9 and abs(cny.loc["2019-06-30"] - 100 / 7) < 1e-9
    ys = T.yen_strength(T.cross(fx, "USD"))
    assert abs(ys.loc["2020-06-30"] + 10.0) < 1e-9                                                          # 日元弱 → 负
    assert T.flag(ys, ">", 5.0).sum() == 0 and T.flag(-ys, ">", 5.0).loc["2020-06-30"]
    z = _m("2000-01-31", [0.5, np.nan, 1.2])
    assert T.flag(z, ">=", 1.0).tolist() == [False, False, True]


def test_era_corr_and_fwd_sum():
    idx = pd.date_range("1985-01-31", periods=480, freq="ME")
    a = pd.Series(np.sin(np.arange(480)), index=idx)
    c = T.era_corr(a, a)
    assert c["〜1989"][0] == 1.0 and c["1990〜2012"][1] == 276 and c["2013〜"][0] == 1.0
    m = _m("2000-01-31", np.ones(30))
    assert T.fwd_sum(m, 12).loc["2000-01-31"] == 12.0 and np.isnan(T.fwd_sum(m, 12).iloc[-1])


def test_horizontal_stats_and_decision():
    g = {"n": 200, "delta": 0.01, "placebo": {"vals": [0.0, 0.0]}}
    bad = {"n": 200, "delta": -0.01, "placebo": {"vals": [0.0, 0.0]}}
    H = {"A": g, "B": g, "C": g, "D": g, "E": bad, "S": {**g, "n": 50}}
    hs = T.horiz_stats(H)
    assert hs == {"n": 5, "share_pos": 80.0, "mean": 0.006, "pooled_q95": 0.0, "ok": True}
    assert not T.horiz_stats({**H, "B": bad})["ok"]
    x = {"delta": 0.03, "on_share": 20.0, "halves": {"h1": {"delta": 0.01}, "h2": {"delta": 0.02}}}
    d = T.decide_rule(x, 0.025, hs, {"D5": True})
    assert d["pass14"] and d["D5"] is True and d["verdict"] == "提议（要用户确认）"
    assert T.decide_rule(x, 0.025, hs, None)["verdict"] == "不通过"                                          # 账户级没跑 / 不过
    assert not T.decide_rule(x, 0.035, hs, None)["D1"]
    assert not T.decide_rule({**x, "halves": {"h1": {"delta": -0.01}, "h2": {"delta": 0.02}}}, 0.0, hs, None)["D2"]
    assert not T.decide_rule({**x, "on_share": 55.0}, 0.0, hs, None)["D3"]
    assert not T.decide_rule(x, 0.0, {"ok": False}, None)["D4"]
