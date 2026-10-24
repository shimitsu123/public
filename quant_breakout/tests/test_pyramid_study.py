"""赢家加仓 / 分批止盈（scripts/pyramid_study.py 登记检验）：研究引擎 —— 变体为空 = 现行；创新高加仓的时点 / 股数 / 现金 / 平均成本 / 保本止损；
回落后加仓；分批止盈的部分记录与剩余股数、保本；三级分批；无条件与随机日；逐笔合并；探索 / 确认的判定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import pyramid_study as PY                                                   # noqa: E402

from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.strategy import compute_indicators                              # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402

EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
PP = StrategyParams(max_distribution_days=6, max_upper_shadow_ratio=3.0, exit_on_macd_dead_cross=False, exit_chandelier_k=3.0)
CFG = UnifiedConfig(capital_jpy=10_000_000, position_pct=0.25, max_positions=4, max_position_pct=0.34, stock_markets=("JP",), core={}, core_index={})
N0 = 120                                                                     # 信号日（收盘）；成交 = 第 121 天开盘


def _frame(closes: list[float]) -> pd.DataFrame:
    c = np.asarray(closes, float)
    idx = pd.bdate_range("2021-01-04", periods=len(c))
    o = np.r_[c[0], c[:-1]]
    raw = pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.015, "Low": np.minimum(o, c) * 0.985, "Close": c, "Volume": 1e6}, index=idx)
    ind = compute_indicators(raw, StrategyParams())
    ind["entry"] = False
    ind.loc[idx[N0], "entry"] = True
    ind["dead_cross"] = False
    ind["climax"] = False
    return ind


def _rise(days: int, rate: float = 0.01, start: float = 1000.0) -> list[float]:
    return [start * (1 + rate) ** k for k in range(1, days + 1)]


def _run(ind: pd.DataFrame, V: dict | None, seed: int = 0):
    """V=None → 现行 MixEngine；否则研究引擎。返回 (engine, trades)。"""
    idx = ind.index
    if V is None:
        eng = CP.MixEngine({"A.T": ind}, CFG, {"JP": PP, "US": PP}, EX, {})
        eng.run(start=idx[100])
        return eng, [t for t in eng.st.trades if t["ticker"] == "A.T"]
    Eng = PY.engine_cls()
    Eng.V, Eng.SEED = V, seed
    try:
        eng = Eng({"A.T": ind}, CFG, {"JP": PP, "US": PP}, EX, {})
        eng.run(start=idx[100])
    finally:
        Eng.V, Eng.SEED = {}, 0
    return eng, [t for t in eng.st.trades if t["ticker"] == "A.T"]


def _snap(ind: pd.DataFrame, V: dict) -> dict:
    """逐日推进研究引擎，记下每天收盘后持仓的止损价。"""
    Eng = PY.engine_cls()
    Eng.V, Eng.SEED = V, 0
    try:
        eng = Eng({"A.T": ind}, CFG, {"JP": PP, "US": PP}, EX, {})
        lo = int(eng.gidx.searchsorted(ind.index[100]))
        eng.prime(lo)
        stop = []
        for i in range(lo, len(eng.gidx)):
            eng.step(i)
            ps = eng.st.pos.get("A.T")
            stop.append((str(eng.gidx[i].date()), float(ps.stop_px) if ps is not None else None))
    finally:
        Eng.V, Eng.SEED = {}, 0
    return {"stop": stop, "adds": list(eng.adds), "scales": list(eng.scales)}


def test_constants():
    assert (PY.ADD_FRAC, PY.ADD_MAXHOLD, PY.PULL_PCT, PY.RAND_LO, PY.RAND_HI, PY.ORACLE_MIN) == (0.5, 40, 3.0, 1, 30, 10.0)
    assert tuple(PY.VARIANTS) == ("A1", "A2", "A3", "S1", "S2", "S3") and tuple(PY.CONTROLS) == ("A0", "S0", "O1")
    assert (PY.EXP_TOL, PY.EXP_GAIN, PY.DD_TOL, PY.CONF_TOL, PY.CONF_GAIN, PY.MAX_FINAL, PY.HARD_TOL) == (0.01, 0.04, 2.0, 0.01, 0.02, 3, 0.001)
    assert PY.PLACEBO_OF == {"A1": "PA", "A2": "PA", "A3": "PA", "S1": "PS", "S2": "PS", "S3": "PS"} and PY.PLACEBO_SEEDS == 20
    assert PY.VARIANTS["S3"]["scale"]["levels"][0][0] == 10.0 and abs(PY.VARIANTS["S3"]["scale"]["levels"][1][1] - 1 / 3) < 1e-12


def test_empty_variant_equals_current():
    ind = _frame([1000.0] * (N0 + 1) + _rise(40))
    _, t0 = _run(ind, None)
    eng, t1 = _run(ind, {})
    assert t0 and t0 == t1 and not eng.adds and not eng.scales


def test_add_on_newhigh_shares_cash_cost_and_breakeven():
    ind = _frame([1000.0] * (N0 + 1) + _rise(40))
    idx = ind.index
    eng, tr = _run(ind, PY.VARIANTS["A1"]["add"] and {"add": PY.VARIANTS["A1"]["add"]})
    assert len(eng.adds) == 1
    fill = 1000.0 * (1 + EX["JP"].slippage_pct / 100)                        # 第 121 天开盘 = 第 120 天收盘 1000
    k = next(k for k in range(N0 + 1, len(idx)) if float(ind["Close"].iloc[k]) / fill - 1 >= 0.08)
    d, t, q, px = eng.adds[0]
    assert d == str(idx[k + 1].date()) and t == "A.T" and q == 1200                # 2,400 股（¥250 万 ÷ 1,001 一手取整）× 50% = 1,200
    assert abs(px - float(ind["Open"].iloc[k + 1]) * (1 + EX["JP"].slippage_pct / 100)) < 0.006      # 记录里四舍五入到 2 位
    assert len(tr) == 1 and tr[0]["shares"] == 3600                             # 2,400 + 1,200，一笔记录
    avg = (2400 * fill + 1200 * px) / 3600
    assert abs(tr[0]["entry_px"] - round(avg, 4)) < 1e-3
    assert eng.skipped["add_cash"] == 0 and eng.skipped["add_gap"] == 0
    # A2：加仓时止损提到原成本；A1 不动（逐日推进看引擎状态）
    for key, expect_be in (("A1", False), ("A2", True)):
        snap = _snap(ind, {"add": PY.VARIANTS[key]["add"]})
        d_add = snap["adds"][0][0]
        after = [v for d, v in snap["stop"] if d >= d_add and v is not None]
        assert after and ((min(after) >= fill - 1e-9) if expect_be else (max(after) < fill))


def test_add_after_pullback_only():
    mono = _frame([1000.0] * (N0 + 1) + _rise(40))
    e, _ = _run(mono, {"add": PY.VARIANTS["A3"]["add"]})
    assert not e.adds                                                          # 一路涨没有回落 → 不加
    seq = [1000.0] * (N0 + 1) + [1010, 1020, 1030, 1040, 1050, 1061, 1040, 1019, 1040, 1062] + [1062 * 1.01 ** k for k in range(1, 30)]
    ind = _frame(seq)
    e2, _ = _run(ind, {"add": PY.VARIANTS["A3"]["add"]})
    assert len(e2.adds) == 1 and e2.adds[0][0] == str(ind.index[N0 + 11].date())   # 第 130 天收盘 1062 创新高（回落后）→ 第 131 天开盘加


def test_scale_out_half_and_breakeven():
    ind = _frame([1000.0] * (N0 + 1) + _rise(40))
    idx = ind.index
    eng, tr = _run(ind, {"scale": PY.VARIANTS["S1"]["scale"]})
    fill = 1000.0 * (1 + EX["JP"].slippage_pct / 100)
    k = next(k for k in range(N0 + 1, len(idx)) if float(ind["Close"].iloc[k]) >= fill * 1.12)
    assert len(eng.scales) == 1 and eng.scales[0][0] == str(idx[k + 1].date()) and eng.scales[0][2] == 1200
    assert len(tr) == 2 and tr[0]["reason"].startswith("scale_out1") and tr[0]["shares"] == 1200 and tr[1]["shares"] == 1200
    assert tr[0]["entry_date"] == tr[1]["entry_date"]
    T = PY.agg_trades(tr)
    assert len(T) == 1 and T["n_rec"].iloc[0] == 2 and abs(T["pnl"].iloc[0] - (tr[0]["pnl"] + tr[1]["pnl"])) < 1e-6
    # S2：卖出后剩余股数的止损提到成本；S1 不动（逐日推进看引擎状态）
    for key, expect_be in (("S1", False), ("S2", True)):
        snap = _snap(ind, {"scale": PY.VARIANTS[key]["scale"]})
        d_sc = snap["scales"][0][0]
        after = [v for d, v in snap["stop"] if d >= d_sc and v is not None]
        assert after and ((min(after) >= fill - 1e-9) if expect_be else (max(after) < fill))


def test_scale_three_tranches():
    ind = _frame([1000.0] * (N0 + 1) + _rise(40))
    eng, tr = _run(ind, {"scale": PY.VARIANTS["S3"]["scale"]})
    assert len(eng.scales) == 2 and eng.scales[0][2] == 800 and eng.scales[1][2] == 800   # 2,400 × 1/3 = 800
    assert len(tr) == 3 and tr[2]["shares"] == 800


def test_day_and_random_kinds():
    ind = _frame([1000.0] * (N0 + 1) + [1000.0] * 40)                          # 不涨：只有无条件 / 随机日会动
    e, _ = _run(ind, {"add": PY.CONTROLS["A0"]["add"]})
    assert len(e.adds) == 1 and e.adds[0][0] == str(ind.index[N0 + 6].date())      # 持有第 5 天收盘 → 第 6 天开盘
    e2, tr2 = _run(ind, {"scale": PY.CONTROLS["S0"]["scale"]})
    assert len(e2.scales) == 1 and e2.scales[0][0] == str(ind.index[N0 + 11].date()) and tr2[0]["shares"] == 1200
    r1, _ = _run(ind, PY.PLACEBO["PA"], seed=3)
    r2, _ = _run(ind, PY.PLACEBO["PA"], seed=3)
    r3, _ = _run(ind, PY.PLACEBO["PA"], seed=4)
    assert r1.adds == r2.adds and len(r1.adds) == 1 and (r1.adds != r3.adds or True)
    day = int(ind.index.get_loc(pd.Timestamp(r1.adds[0][0]))) - (N0 + 1)
    assert 1 <= day <= PY.RAND_HI


def test_agg_and_stats():
    tr = [dict(ticker="A.T", entry_date="2021-01-05", exit_date="2021-01-20", entry_px=100.0, shares=100, pnl=500.0, hold_days=10, reason="scale_out1（部分成交）"),
          dict(ticker="A.T", entry_date="2021-01-05", exit_date="2021-02-01", entry_px=100.0, shares=100, pnl=-200.0, hold_days=18, reason="stop"),
          dict(ticker="B.T", entry_date="2021-01-06", exit_date="2021-01-15", entry_px=50.0, shares=200, pnl=-100.0, hold_days=7, reason="stop"),
          dict(ticker="C.T", entry_date="2021-03-01", exit_date="2021-03-31", entry_px=10.0, shares=100, pnl=10.0, hold_days=20, reason="end")]
    T = PY.agg_trades(tr)
    assert len(T) == 2
    a = T[T["ticker"] == "A.T"].iloc[0]
    assert a["pnl"] == 300.0 and a["cost"] == 20000.0 and abs(a["net_pct"] - 1.5) < 1e-9 and a["n_rec"] == 2 and a["hold"] == 18
    s = PY.trade_stats(T, "2021-01-01", "2021-12-31")
    assert s["n"] == 2 and s["multi"] == 1 and s["win"] == 50.0
    assert PY.trade_stats(T, "2021-01-06", None)["n"] == 1


def test_verdicts():
    seg = lambda c, dd: {"cagr": 10.0, "dd": dd, "calmar": c}                 # noqa: E731
    ACCT = {"E": {"现行": seg(0.30, -30.0), "A1": seg(0.33, -29.0)}, "J": {"现行": seg(0.40, -30.0), "A1": seg(0.42, -31.0)}}
    PL = {"PA": [0.0, 0.01, 0.02, -0.01, 0.03]}
    ok, f = PY.explore_verdict("A1", ACCT, PL)
    assert ok and not f and PY.gain_sum(ACCT, "A1", ("E", "J")) == 0.05
    ACCT["J"]["A1"] = seg(0.405, -31.0)                                        # 合计只 +0.035
    assert not PY.explore_verdict("A1", ACCT, PL)[0]
    ACCT["J"]["A1"] = seg(0.42, -32.5)                                         # J 回撤深 2.5 pp
    assert any("回撤" in x for x in PY.explore_verdict("A1", ACCT, PL)[1])
    ACCT["J"]["A1"] = seg(0.42, -31.0)
    assert not PY.explore_verdict("A1", ACCT, {"PA": [0.06, 0.07]})[0]          # ≤ 安慰剂 95 分位
    C = {"Z": {"现行": seg(1.0, -10.0), "A1": seg(1.02, -10.0)}, "W": {"现行": seg(0.3, -30.0), "A1": seg(0.31, -30.0)}}
    assert PY.confirm_verdict("A1", C)[0] == "确认"
    C["W"]["A1"] = seg(0.28, -30.0)
    assert PY.confirm_verdict("A1", C)[0] == "不通过"
