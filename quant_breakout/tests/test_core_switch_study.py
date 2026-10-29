"""核心层「按状态选模型」（scripts/core_switch_study.py 登记检验）：晚卖守卫、月末状态只用过去、各模型的配比（之和 ≤ 1、不可用 → 现金）、
S1 的优先级、S4 的全叠加、只有核心的净值（前一天定的配比、换手成本）、S2 只用过去 36 个月、上限 / 随机 / 平移安慰剂、判定、
通用编码（split + 自己的键 + 比例 × 资产数）进引擎 = 单资产核心的直接设定。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import core_switch_study as CS                                               # noqa: E402

from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.fees import etf_cost                                             # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402


def _states(n=40, start="2020-01-01", **cols):
    d = pd.bdate_range(start, periods=n)
    S = pd.DataFrame(index=d)
    for c in ("bear", "guard", "yen", "gold_up", "rs_ndx", "summer", "dip"):
        S[c] = bool(cols.get(c, False))
    S["gold_ok"] = bool(cols.get("gold_ok", True))
    return S


def test_constants():
    assert CS.ASSETS == ("1655.T", "1545.T", "2563.T", "2845.T", "1540.T", "1321.T")
    assert tuple(CS.MODELS) == ("A", "Q", "B", "C", "D", "E", "F", "G") and tuple(CS.CANDS) == ("S1", "S2", "S3", "S4")
    assert (CS.GUARD_DD, CS.GUARD_N, CS.GOLD_W, CS.GOLD_MONTHS, CS.SEASON_W, CS.RS_N, CS.DIP_W) == (-15.0, 250, 0.20, 10, 0.5, 252, 0.25)
    assert (CS.SEL_MONTHS, CS.SEL_MIN, CS.SWITCH_COST, CS.PLACEBO_SEEDS, CS.SHIFT_MIN) == (36, 24, 0.1, 20, 250)
    assert (CS.CAL_UP_P, CS.CAL_UP, CS.DD_TOL, CS.Z_TOL, CS.HARD_TOL, CS.BASE) == (0.05, 0.02, 2.0, 0.02, 0.001, "Q")
    assert CS.P_WIN["P"] == ("1987-01-01", "2006-01-01") and CS.PLACEBO_FAMILY == {"S1": "P2", "S2": "P1", "S3": "P1", "S4": "P2"}


def test_guard_bear_skips_late_exit_only():
    d = pd.bdate_range("2019-01-01", periods=700)
    px = pd.Series(100.0, index=d)
    px.iloc[300:320] = np.linspace(100, 80, 20)                               # 急跌 20%
    px.iloc[320:400] = 80.0
    px.iloc[400:] = 100.0
    bear = pd.Series(False, index=d)
    bear.iloc[320:400] = True                                                 # T0 在 −20% 时才翻熊 → 守卫：这一段不卖
    g = CS.guard_bear(px, bear)
    assert not g.iloc[320:400].any() and not g.iloc[400:].any()
    bear2 = pd.Series(False, index=d)
    bear2.iloc[305:400] = True                                                # 在 −5% 时翻熊 → 照常
    g2 = CS.guard_bear(px, bear2)
    assert g2.iloc[305:400].all() and not g2.iloc[:305].any()
    bear3 = pd.Series(False, index=d)
    bear3.iloc[100:150] = True                                                # 250 天历史不够 → 不守卫
    assert CS.guard_bear(px, bear3).iloc[100:150].all()


def test_next_month_flag_and_gold_up_no_lookahead():
    d = pd.bdate_range("2020-01-01", "2021-12-31")
    g = pd.Series(np.linspace(100, 200, len(d)), index=d)                      # 一路涨
    f = CS.gold_up_flag(g, d)
    me = CS.month_ends(d)
    assert not f.loc[:me[9]].any()                                            # 前 10 个月末平均没定 → False
    assert f.loc[me[10] + pd.Timedelta(days=1):].all()                        # 之后每个月都 > 平均
    g2 = g.copy()
    g2.loc[me[15] + pd.Timedelta(days=1):] = 1.0                              # 改未来
    f2 = CS.gold_up_flag(g2, d)
    assert (f2.loc[:me[15]] == f.loc[:me[15]]).all()                          # 之前的不变
    assert not f2.loc[me[16] + pd.Timedelta(days=1):].any()
    assert not CS.gold_up_flag(pd.Series(dtype=float), d).any()


def test_rs_flag_next_month_only_with_history():
    d = pd.bdate_range("2019-01-01", periods=600)
    ndx = pd.Series(np.linspace(100, 300, 600), index=d)
    spx = pd.Series(np.linspace(100, 150, 600), index=d)
    f = CS.rs_flag(ndx, spx, d)
    me = CS.month_ends(d)
    first_ok = next(m for m in me if int(d.get_loc(m)) >= 252)
    assert not f.loc[:first_ok].any() and f.loc[first_ok + pd.Timedelta(days=1):].all()


def test_model_weights_rules():
    for m in CS.MODELS:
        S = _states(bear=False, yen=True, gold_up=True, summer=True, dip=True, rs_ndx=True)
        W = CS.model_weights(m, S)
        assert (W.sum(axis=1) <= 1 + 1e-9).all() and (W >= 0).all().all()
    S = _states(bear=False, gold_up=True)
    assert CS.model_weights("B", S).iloc[0].to_dict() == {"1655.T": 0.8, "1545.T": 0, "2563.T": 0, "2845.T": 0, "1540.T": 0.2, "1321.T": 0}
    S = _states(bear=False, gold_ok=False)
    assert CS.model_weights("B", S).iloc[0]["1655.T"] == 1.0 and CS.model_weights("B", S).iloc[0]["1540.T"] == 0
    S = _states(bear=True, dip=True)
    w = CS.model_weights("E", S).iloc[0]
    assert w["1321.T"] == 0.25 and w.sum() == 0.25
    S = _states(bear=False, dip=True)
    w = CS.model_weights("E", S).iloc[0]
    assert w["1655.T"] == 0.75 and w["1321.T"] == 0.25
    S = _states(bear=False, yen=True)
    assert CS.model_weights("C", S).iloc[0]["2563.T"] == 1.0 and CS.model_weights("C", S).iloc[0]["1655.T"] == 0
    S = _states(bear=False, summer=True)
    assert CS.model_weights("D", S).iloc[0]["1655.T"] == 0.5
    S = _states(bear=False, rs_ndx=True)
    assert CS.model_weights("F", S).iloc[0]["1545.T"] == 1.0 and CS.model_weights("Q", S).iloc[0]["1545.T"] == 1.0
    S = _states(bear=True, guard=False)                                       # T0 熊但守卫说不卖
    assert CS.model_weights("G", S).iloc[0]["1655.T"] == 1.0 and CS.model_weights("A", S).iloc[0].sum() == 0
    S = _states(bear=True, guard=True)
    assert CS.model_weights("G", S).iloc[0].sum() == 0


def test_s1_priority_branches():
    def w(**k):
        return CS.model_weights("S1", _states(**k)).iloc[0]
    x = w(dip=True, yen=True, gold_up=True)                                   # dip 最先
    assert x["1321.T"] == 0.25 and x["1655.T"] == 0.75
    assert w(bear=True, guard=True, yen=True).sum() == 0                      # 熊 → 现金
    assert w(bear=True, guard=False, yen=True)["2563.T"] == 1.0              # 守卫后不是熊 → 往下走：yen → 对冲
    assert w(yen=True, gold_up=True)["2563.T"] == 1.0                        # yen 优先于黄金
    x = w(gold_up=True, summer=True)
    assert x["1655.T"] == 0.8 and x["1540.T"] == 0.2                          # 黄金优先于季节
    assert w(summer=True)["1655.T"] == 0.5
    assert w()["1655.T"] == 1.0 and w(rs_ndx=True)["1545.T"] == 1.0
    assert w(rs_ndx=True, yen=True)["2845.T"] == 1.0                          # 指数按 F 选，对冲版跟着换
    W = CS.model_weights("S1", _states(n=5, summer=True))
    assert W.attrs["branches"]["summer"] == 5 and sum(W.attrs["branches"].values()) == 5


def test_s4_all_overlays_and_blend():
    x = CS.model_weights("S4", _states(yen=True, gold_up=True, summer=True, dip=True, rs_ndx=True)).iloc[0]
    assert abs(x["2845.T"] - (0.5 - 0.1) * 0.75) < 1e-9 and abs(x["1540.T"] - 0.1) < 1e-9 and x["1321.T"] == 0.25
    assert x.sum() <= 1 + 1e-9
    x = CS.model_weights("S4", _states(bear=True, guard=True, dip=True)).iloc[0]
    assert x["1321.T"] == 0.25 and x.sum() == 0.25
    S = _states(bear=False)
    WM = {m: CS.model_weights(m, S) for m in CS.MODELS}
    B = CS.blend_weights(WM)
    assert abs(B.iloc[0]["1655.T"] - 6.8 / 8) < 1e-9 and abs(B.iloc[0]["1545.T"] - 1 / 8) < 1e-9   # B 常配黄金：1655 0.8 + 黄金 0.2
    assert abs(B.iloc[0]["1540.T"] - 0.2 / 8) < 1e-9 and abs(B.iloc[0].sum() - 1.0) < 1e-9


def test_core_sim_next_day_and_cost():
    d = pd.bdate_range("2020-01-01", periods=5)
    R = pd.DataFrame({"1655.T": [0.0, 0.10, 0.0, 0.0, 0.0], "1545.T": [0.0, 0.0, 0.0, 0.20, 0.0]}, index=d)
    for a in CS.ASSETS:
        if a not in R:
            R[a] = np.nan
    W = pd.DataFrame(0.0, index=d, columns=list(CS.ASSETS))
    W.loc[d[0], "1655.T"] = 1.0                                               # 第 0 天收盘决定 → 第 1 天吃到 +10%
    W.loc[d[1], "1655.T"] = 1.0
    W.loc[d[2], "1545.T"] = 1.0                                               # 第 2 天换 → 第 3 天吃到 +20%，第 3 天扣 2 × 0.1%
    W.loc[d[3], "1545.T"] = 1.0
    eq = CS.core_sim(W, R)
    assert abs(eq.iloc[1] / eq.iloc[0] - (1.10 - 0.001)) < 1e-12
    assert abs(eq.iloc[2] / eq.iloc[1] - 1.0) < 1e-12
    assert abs(eq.iloc[3] / eq.iloc[2] - (1.20 - 0.002)) < 1e-12
    W2 = W.copy()
    W2["1540.T"] = 0.5                                                        # 不可用的资产 → 当现金、不算换手
    assert (CS.core_sim(W2, R) == eq).all()


def test_trailing_choice_uses_only_past():
    d = pd.bdate_range("2015-01-01", "2019-12-31")
    rng = np.random.default_rng(0)
    EQ = {m: pd.Series(np.cumprod(1 + rng.normal(0.0003 * (k + 1), 0.01, len(d))), index=d) for k, m in enumerate(CS.MODELS)}
    ch = CS.trailing_choice(EQ, d)
    me = CS.month_ends(d)
    assert (ch.loc[:me[CS.SEL_MIN - 1]] == "A").all() and set(ch.unique()) <= set(CS.MODELS)
    EQ2 = {m: e.copy() for m, e in EQ.items()}
    for m in EQ2:
        EQ2[m].loc[me[40] + pd.Timedelta(days=1):] = 1.0                      # 改未来
    ch2 = CS.trailing_choice(EQ2, d)
    assert (ch2.loc[:me[40]] == ch.loc[:me[40]]).all()


def test_oracle_random_and_shift():
    d = pd.bdate_range("2018-01-01", "2019-12-31")
    EQ = {m: pd.Series(1.0, index=d) for m in CS.MODELS}
    me = CS.month_ends(d)
    EQ["D"].loc[me[3] + pd.Timedelta(days=1):] = 2.0                          # 第 4 个月 D 涨 → 月末 3 事后选 D
    o = CS.oracle_choice(EQ, d)
    assert (o.loc[me[3] + pd.Timedelta(days=1):me[4]] == "D").all() and (o.loc[:me[3]] == "A").all()
    r1, r2 = CS.random_choice(d, 3), CS.random_choice(d, 3)
    assert (r1 == r2).all() and set(r1.unique()) <= set(CS.MODELS) and not (r1 == CS.random_choice(d, 4)).all()
    S = _states(n=800)
    S["bear"] = np.arange(800) % 100 < 30
    S["guard"] = S["bear"] & (np.arange(800) % 100 >= 10)
    S["yen"] = np.arange(800) % 7 == 0
    S2 = CS.shifted_states(S, 1)
    assert (S2["bear"] == S["bear"]).all() and (S2["guard"] <= S["bear"]).all() and S2["yen"].sum() == S["yen"].sum()
    assert not (S2["yen"] == S["yen"]).all()


def test_verdict():
    seg = lambda c, dd: {"cagr": 10.0, "dd": dd, "calmar": c}                 # noqa: E731
    RP = {"Q": {"P": seg(0.30, -40.0), "P1": seg(0.2, -40.0), "P2": seg(0.4, -30.0)},
          "S1": {"P": seg(0.36, -39.0), "P1": seg(0.25, -39.0), "P2": seg(0.45, -30.0)}}
    ACCT = {e: {"Q": seg(0.50, -30.0), "S1": seg(0.53, -29.0)} for e in ("Z", "E", "J")}
    lab, f = CS.verdict("S1", RP, ACCT, 0.33, 0.52)
    assert lab == "提议" and not f
    assert CS.verdict("S1", RP, ACCT, 0.37, 0.52)[0] == "不通过"                # P ≤ 安慰剂 95 分位
    RP["S1"]["P1"] = seg(0.19, -39.0)
    assert any("1987〜1996" in x for x in CS.verdict("S1", RP, ACCT, 0.33, 0.52)[1])
    RP["S1"]["P1"] = seg(0.25, -39.0)
    ACCT["J"]["S1"] = seg(0.51, -30.0)                                        # J 只 +0.01
    assert any("J Calmar" in x for x in CS.verdict("S1", RP, ACCT, 0.33, 0.50)[1])
    ACCT["J"]["S1"] = seg(0.53, -32.5)                                        # J 回撤深 2.5 pp
    assert any("J 回撤" in x for x in CS.verdict("S1", RP, ACCT, 0.33, 0.52)[1])


def test_encode_equals_single_core_engine():
    """通用编码（6 个核心资产、自己的键、比例 × 6）里只让 X 为 1 → 与「core = {X: 1}」的直接设定同样的核心持仓。"""
    D = pd.bdate_range("2026-01-05", periods=30)
    rng = np.random.default_rng(1)
    f = lambda p0, s: pd.DataFrame({"Open": p0 * np.cumprod(1 + rng.normal(0, 0.01, len(D)))}, index=D).assign(   # noqa: E731
        High=lambda x: x.Open, Low=lambda x: x.Open, Close=lambda x: x.Open, Volume=1e9, entry=False, dead_cross=False, climax=False, atr=np.nan)
    tick = ["X.T", "Y.T", "Z.T", "U.T", "V.T", "W.T"]
    ind = {t: f(1000.0 * (k + 1), k) for k, t in enumerate(tick)}
    EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
    P = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=True, max_hold_days=0, stop_loss_pct=50.0)
    cost = {t: etf_cost("tachibana", t, "JP") for t in tick}
    bear_us = pd.Series([False] * 20 + [True] * 10, index=D)                  # 第 20 天起熊 → 目标 0

    def units(eng):
        eng.prime(0)
        v = []
        for i in range(len(D)):
            eng.step(i)
            v.append({t: int(eng.st.core_units.get(t, 0)) for t in tick})
        return v
    cfg1 = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",),
                         core={"X.T": 1.0}, core_index={"X.T": "US"}, core_mode="split")
    v1 = units(CP.MixEngine(ind, cfg1, {"JP": P, "US": P}, EX, cost, bear={"US": bear_us, "JP": pd.Series(False, index=D)}))
    W = pd.DataFrame(0.0, index=D, columns=tick)
    W["X.T"] = (~bear_us).astype(float)
    cfg_over, bear, expo = CS.encode(W)
    assert cfg_over["core"] == {t: 1.0 for t in tick} and bear["CS:X.T"].iloc[25] and not bear["CS:X.T"].iloc[5]
    assert expo["CS:X.T"].iloc[5] == 6.0
    Eng = CS.engine_cls()
    old_eb = CP.MixEngine.EXTRA_BEAR
    CP.MixEngine.EXTRA_BEAR, Eng.EXPO = bear, expo
    try:
        cfg2 = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), **cfg_over)
        v2 = units(Eng(ind, cfg2, {"JP": P, "US": P}, EX, cost, bear={"US": bear_us, "JP": pd.Series(False, index=D)}))
    finally:
        CP.MixEngine.EXTRA_BEAR, Eng.EXPO = old_eb, {}
    assert v1[5]["X.T"] > 0 and v1 == v2
    assert all(v2[i][t] == 0 for i in range(len(D)) for t in tick[1:])
    assert v2[25]["X.T"] == 0
