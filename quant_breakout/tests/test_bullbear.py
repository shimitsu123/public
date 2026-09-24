"""牛熊分界：事后标注、实时检测器、评估、合成反向、引擎的状态层。"""
import numpy as np
import pandas as pd

from conftest import make_indicator_frame
from qbreak.bullbear import (BEAR, BULL, Detector, boundary, current_regime, date_phases, dd_rally, evaluate,
                             hmm_filter, hmm_fit, ma_band, phase_table, synthetic_inverse)
from qbreak.config import BacktestConfig, StrategyParams
from qbreak.engine import run_backtest
from qbreak.regime import quant_regime_series


def _path(points, n_each=50):
    """按折线点生成价格：[(100), (130), (95), ...] 每段线性插值。"""
    xs = []
    for a, b in zip(points, points[1:]):
        xs += list(np.linspace(a, b, n_each, endpoint=False))
    xs.append(points[-1])
    return pd.Series(xs, index=pd.bdate_range("2000-01-03", periods=len(xs)))


def test_date_phases_exact_turning_points():
    c = _path([100, 150, 110, 140, 100, 130])                  # 150→110 = −26.7%（熊），110→140 = +27%（牛）
    tp, lab = date_phases(c)
    assert list(tp["kind"]) == ["trough", "peak", "trough", "peak", "trough"][:len(tp)]
    pk = tp[tp["kind"] == "peak"].iloc[0]
    assert abs(pk["close"] - 150) < 1e-9
    i_pk = int(pk["i"])
    assert lab.iloc[i_pk] == BULL and lab.iloc[i_pk + 1] == BEAR  # 高点当天属牛，次日起熊
    pt = phase_table(c)
    assert abs(pt.iloc[0]["depth_pct"] - (110 / 150 - 1) * 100) < 0.1


def test_small_dips_are_not_bears():
    c = _path([100, 120, 105, 125, 110, 130])                  # 每次回撤 < 20%
    tp, lab = date_phases(c)
    assert list(tp["kind"]) == ["trough"] and (lab.iloc[1:] == BULL).all()   # 起点是低点（属熊），之后全是牛


def test_ma_band_needs_k_consecutive_days_and_band():
    c = pd.Series([100.0] * 260 + [96.0] * 4 + [100.0] + [96.0] * 5, index=pd.bdate_range("2001-01-01", periods=270))
    st = ma_band(c, L=250, b=0.03, k=5)
    assert st[263] == BULL                                     # 连续 4 天不够
    assert st[-1] == BEAR                                      # 连续 5 天 < 均线×0.97 → 熊
    st2 = ma_band(c, L=250, b=0.05, k=5)
    assert st2[-1] == BULL                                     # 带宽 5% 时 96 仍在带内


def test_dd_rally_realtime_rule():
    c = _path([100, 120, 96, 118])                              # 120→96 = −20%，96→118 = +22.9%
    st = dd_rally(c, 0.2, 0.2)
    assert st[0] == BULL and BEAR in st and st[-1] == BULL


def test_hmm_filter_flags_high_vol_regime():
    rng = np.random.default_rng(0)
    r = np.r_[rng.normal(0.05, 0.6, 1500), rng.normal(-0.1, 2.0, 300), rng.normal(0.05, 0.6, 500)]
    prm = hmm_fit(r, iters=100)
    p = hmm_filter(r, prm)
    assert p[1600:1800].mean() > 0.7 and p[:1400].mean() < 0.3


def test_evaluate_metrics_and_boundary_levels():
    c = _path([100, 160, 100, 170], n_each=300)
    _, lab = date_phases(c)
    det = Detector("ma_band", {"L": 250, "b": 0.03, "k": 5})
    st = det.states(c)
    ev = evaluate(st, lab, c)
    assert 0 < ev["bal_acc"] <= 1 and ev["bear_phases"] == 1 and ev["missed_bears"] == 0
    cur = int(st[-1])
    b = boundary(c, det, cur, int(np.where(st != cur)[0][-1]) + 1)
    assert b["flip_to"] == ("bear" if cur == BULL else "bull") and b["level"] > 0
    rg = current_regime(c, "US", {"detector": det.to_dict()})
    assert rg["state"] in ("bull", "bear") and "level" in rg


def test_synthetic_inverse_moves_opposite():
    idx = pd.bdate_range("2020-01-01", periods=5)
    df = pd.DataFrame({"Open": [100, 101, 99, 98, 100.0], "High": [101, 102, 100, 99, 101.0],
                       "Low": [99, 100, 98, 97, 99.0], "Close": [100, 101, 99, 98, 100.0]}, index=idx)
    inv = synthetic_inverse(df, fee_pct=0.0)
    r_idx, r_inv = df["Close"].pct_change().iloc[1:], inv["Close"].pct_change().iloc[1:]
    assert np.allclose(r_inv.values, -r_idx.values)


def test_quant_regime_series_matches_rules():
    c = pd.Series(np.r_[np.linspace(100, 200, 300), np.linspace(200, 150, 60)], index=pd.bdate_range("2001-01-01", periods=360))
    s = quant_regime_series(pd.DataFrame({"Close": c}))
    assert s.iloc[250] == 1.0 and s.iloc[-1] == 0.0


def test_engine_regime_blocks_entries_and_forces_exit():
    rows = [(1000.0, 1002.0, 998.0, 1000.0, 1e6)] * 30 + [(1000.0, 1031.0, 999.0, 1030.0, 6e6)] \
        + [(1040.0, 1045.0, 1035.0, 1042.0, 2e6)] * 20
    ind = {"A.T": make_indicator_frame(rows, entries=[30])}
    bt = BacktestConfig.for_market("JP")
    p = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=False, max_hold_days=0)
    n = len(rows)
    base = run_backtest(ind, p, bt)
    assert len(base.trades) == 1                                 # 持有到最后
    bear_at_signal = np.zeros(n, dtype=bool); bear_at_signal[30:] = True
    blocked = run_backtest(ind, p, bt, regime=bear_at_signal)
    assert blocked.trades.empty and blocked.skipped["regime"] == 1
    flip = np.zeros(n, dtype=bool); flip[40:] = True            # 第 40 天收盘宣布熊市 → 第 41 天开盘卖
    forced = run_backtest(ind, p, bt, regime=flip, regime_exit=True)
    tr = forced.trades.iloc[0]
    assert tr["reason"] == "regime_bear" and str(tr["exit_date"].date()) == str(ind["A.T"].index[41].date())
