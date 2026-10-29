"""B・N・F 拆成每月（scripts/bnf_adapt_study.py 登记检验）：快速逐笔与引擎逐笔一致（跳空不买、止损 / 乖离 / 到期三种卖法、数据不够 → 没有）、
月表按平仓月入账（改下个月的价格不影响这个月那一列）、每月选参数只用过去的月份、记忆衰减真的偏向最近的月、滞回与最少笔数、
他的年代逐月路径与斜率、漂移外推与波动归一的取整、σ 只用上月底、build 的列与 PARAMS_TD 键、引擎逐笔不重叠、
研究引擎的 PARAMS_TD 钩子（每一笔持仓自己的持有天数 / 止损；缺省不变）、判定规则。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bnf_adapt_study as A                                                  # noqa: E402
import bnf_study as B                                                        # noqa: E402
import candle_portfolio as CP                                                # noqa: E402
import sell_confirm as SCF                                                   # noqa: E402

from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.strategy import compute_indicators                              # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402


def _frame(close, open_=None, start="2021-01-04"):
    close = np.asarray(close, float)
    open_ = close if open_ is None else np.asarray(open_, float)
    idx = pd.bdate_range(start, periods=len(close))
    df = pd.DataFrame({"Open": open_, "High": np.maximum(open_, close) * 1.005, "Low": np.minimum(open_, close) * 0.995,
                       "Close": close, "Volume": 1e6}, index=idx)
    return compute_indicators(df, StrategyParams())


def _crash_frame(seed=0):
    rng = np.random.default_rng(seed)
    n = 260
    c = 1000.0 * np.cumprod(1 + rng.normal(0, 0.01, n))
    c[120:128] *= np.linspace(1, 0.7, 8)                                                # 一段急跌 → 乖离 ≤ −20%
    c[128:] *= 0.7
    c[140:150] *= np.linspace(1, 1.25, 10)                                              # 反弹
    c[150:] *= 1.25
    o = c * (1 + rng.normal(0, 0.004, n))
    return _frame(c, o)


def test_fast_trades_match_engine_single_trade():
    """快速逐笔（fwd_rows + exit_net）与 sell_confirm.one_trade 在同一笔上的净收益一致（跳空、止损、乖离回、到期）。"""
    fa = {"A.T": _crash_frame(1), "B.T": _crash_frame(2)}
    D = {t: B.dev25(df["Close"]) for t, df in fa.items()}
    slip = ExecConfig.for_market("JP", "tachibana").slippage_pct / 100
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(SCF.NOTIONAL) * 2 / SCF.NOTIONAL * 100
    rows = A.fwd_rows(fa, D, slip)
    checked = 0
    for th in ((-20.0, -10.0, 5, 10.0), (-15.0, -5.0, 3, 5.0), (-20.0, 0.0, 20, 100.0), (-10.0, -2.5, 2, 7.5)):
        net = A.exit_net(rows, th[1], th[2], th[3], slip, rt)
        pp = A.bnf_params(StrategyParams(), th[2], th[3])
        for t, df in fa.items():
            dv = D[t].to_numpy(float) * 100
            sel = np.flatnonzero((rows["tick"] == t) & np.isfinite(rows["dev"]) & (rows["dev"] <= th[0]))
            for r in sel[:12]:
                pos = int(np.flatnonzero(df.index == rows["date"][r])[0])
                end = df.index[min(len(df) - 1, pos + 30)]
                with np.errstate(invalid="ignore"):
                    f0 = df.assign(entry=np.asarray(df.index == df.index[pos]), dead_cross=np.isfinite(dv) & (dv >= th[1]))
                x = SCF.one_trade(t, f0, df.index[pos], pp, bt, end)
                if x is None or x["reason"] == "end":
                    assert not np.isfinite(net[r]) or x is not None                  # 引擎没成交 / 没卖完 → 快速版也没有或不比较
                    continue
                assert np.isfinite(net[r]), (t, th, rows["date"][r])
                assert abs(net[r] - (float(x["ret_pct"]) - rt)) < 0.02, (t, th, rows["date"][r], net[r], x)
                checked += 1
    assert checked >= 20


def test_fast_trades_gap_skips_entry():
    c = np.full(60, 1000.0)
    c[30:36] = [900, 820, 760, 740, 745, 760]
    c[36:] = 780.0
    o = c.copy()
    o[33] = c[32] * 1.05                                                                # 第 33 天开盘跳空 5%：第 32 天的信号买不到
    fa = {"A.T": _frame(c, o)}
    D = {t: B.dev25(df["Close"]) for t, df in fa.items()}
    rows = A.fwd_rows(fa, D, 0.001)
    assert not np.isfinite(rows["entry"][32]) and np.isfinite(rows["entry"][31])
    net = A.exit_net(rows, -10.0, 5, 10.0, 0.001, 0.15)
    assert not np.isfinite(net[32]) and np.isfinite(net[31])


def _tables(rng, n_months=30, per_month=6):
    """人造的 S / C：每个月每个 θ 若干笔；月序号 0..n−1。"""
    months = np.arange(n_months)
    S = rng.normal(0, 1, (len(A.THETAS), n_months))
    C = np.full((len(A.THETAS), n_months), float(per_month))
    return months, S, C


def test_fit_uses_only_past_months_and_hysteresis():
    rng = np.random.default_rng(0)
    months, S, C = _tables(rng)
    k0 = A.T_INDEX[(-20.0, -10.0, 5, 10.0)]
    S[k0, :12] = 5.0                                                                    # 0〜11 月 θ0 明显最好
    path = A.walk_forward(months, S, C, 12, 20, start=0, win=12, ew=False)
    assert path[12] == k0
    S2 = S.copy()
    S2[:, 12:] = rng.normal(0, 1, (len(A.THETAS), 18)) + 50                             # 改动 12 月以后的数据
    S2[k0, 12:] = -100
    assert A.walk_forward(months, S2, C, 12, 12, start=0, win=12, ew=False)[12] == k0    # 12 月的选择不受 12 月及以后影响
    # 滞回：另一组只好一点点 → 不换
    k1 = A.T_INDEX[(-25.0, -10.0, 5, 10.0)]
    S[k1, :12] = 5.0 + A.HYST * 6 * 0.9                                                 # 每笔只高 0.9 × HYST
    assert A.fit_theta(S, C, np.arange(12), None, prev=k0) == k0
    S[k1, :12] = 5.0 + A.HYST * 6 * 1.5
    assert A.fit_theta(S, C, np.arange(12), None, prev=k0) == k1
    # 最少笔数：笔数不够 → 沿用
    C3 = np.full_like(C, 1.0)
    assert A.fit_theta(S, C3, np.arange(12), None, prev=k0) == k0
    assert A.fit_theta(S, C3, np.arange(12), None, prev=None) is None


def test_ew_weights_and_oracle():
    assert np.allclose(A.ew_weights(np.array([2, 1, 0]), half=1.0), [0.25, 0.5, 1.0])
    rng = np.random.default_rng(1)
    months, S, C = _tables(rng, 6, 12)
    k0 = A.T_INDEX[(-15.0, -5.0, 3, 5.0)]
    S[k0, 3] = 99.0
    orc = A.oracle_path(months, S, C, 3, 3, start=0)
    assert orc[3] == k0                                                                   # 上限用当月自己的数据（偷看，只描述）


def test_drift_and_vol_snap_to_grid():
    base = (-20.0, -10.0, 5, 10.0)
    slope = {"d_in": -0.5, "d_out": 0.25, "H": 0.5, "S": -0.5}
    assert A.drift_theta(base, slope, 0) == base
    th = A.drift_theta(base, slope, 10)                                                  # −25 / −7.5 / 10 天 / 5%
    assert th == (-25.0, -7.5, 10, 5.0) and th in A.T_INDEX
    th = A.drift_theta(base, slope, 200)                                                 # 超出网格 → 停在边上，且 d_out ≥ d_in + 5
    assert th[0] == -35.0 and th[3] == 5.0 and th[2] == 20 and th[1] >= th[0] + A.MIN_GAP and th in A.T_INDEX
    assert A.legal(-10.0, -15.0) == -5.0 and A.legal(-20.0, -10.0) == -10.0
    v = A.vol_theta(8.0, 2.5, 1.0, 5, 10.0)                                              # −20 / −7.5（−8 → 最近 −7.5）
    assert v == (-20.0, -7.5, 5, 10.0) and v in A.T_INDEX
    v = A.vol_theta(20.0, 2.5, 0.0, 5, 10.0)                                             # −50 → −35；d_out 0
    assert v == (-35.0, 0.0, 5, 10.0)
    assert A.snap(-13.0, A.GRID_IN) == -12.5 and A.snap(4, A.GRID_H) == 3


def test_sigma_uses_previous_month_end_only():
    idx = pd.bdate_range("2020-01-01", periods=600)
    rng = np.random.default_rng(3)
    D = {f"{i}.T": pd.Series(rng.normal(0, 0.05, 600), index=idx) for i in range(12)}
    s = A.sigma_by_month(D)
    m = A.mon("2021-06-15")
    assert m in s and abs(s[m] - 5.0) < 1.0
    D2 = {t: v.copy() for t, v in D.items()}
    for v in D2.values():
        v[v.index >= "2021-06-01"] *= 10                                                  # 6 月的数据变了 → 6 月用的 σ 不变
    assert A.sigma_by_month(D2)[m] == s[m]
    assert A.mon("2021-01-31") == 2021 * 12 and A.mon_str(2021 * 12 + 8) == "2021-09"


def test_build_frames_and_params_td():
    fa = {"A.T": _crash_frame(5)}
    D = {t: B.dev25(df["Close"]) for t, df in fa.items()}
    days = fa["A.T"].index
    th_a, th_b = (-20.0, -10.0, 5, 10.0), (-15.0, -5.0, 2, 20.0)
    ms = sorted({A.mon(d) for d in days})
    path = {m: A.T_INDEX[th_a if i % 2 == 0 else th_b] for i, m in enumerate(ms)}
    fr, td, prio = A.build(fa, D, days, path, StrategyParams())
    df = fr["A.T"]
    dv = D["A.T"].to_numpy(float) * 100
    for j in np.flatnonzero(df["entry"].to_numpy()):
        th = A.THETAS[path[A.mon(days[j])]]
        assert dv[j] <= th[0]
        key = ("A.T", str(days[j + 1].date()))
        assert td[key].max_hold_days == th[2] and td[key].stop_loss_pct == th[3]
        assert prio[("A.T", days[j])] == -dv[j]
    assert df["entry"].any() and df["dead_cross"].any()
    ent = np.flatnonzero(df["entry"].to_numpy())
    assert any(days[j].month != days[j + 1].month for j in ent)                        # 有信号在月末、次日成交跨月：仍按信号月的 θ


D8 = pd.bdate_range("2026-01-05", periods=16)
EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}
P0 = StrategyParams(take_profit_pct=0, trailing_stop_pct=0, exit_on_macd_dead_cross=False, max_hold_days=6, stop_loss_pct=50.0)


def _bars(px, entry_on=()):
    px = np.asarray(px, float)
    df = pd.DataFrame({"Open": px, "High": px * 1.01, "Low": px * 0.99, "Close": px, "Volume": 1e6}, index=D8)
    df["entry"] = df.index.isin(pd.DatetimeIndex(entry_on))
    df["dead_cross"] = False
    df["climax"] = False
    df["atr"] = px * 0.02
    return df


def _run(ind, td):
    cfg = UnifiedConfig(capital_jpy=1_000_000, position_pct=0.25, max_positions=4, stock_markets=("JP",), core={}, core_index={})
    old = CP.MixEngine.PARAMS_TD
    CP.MixEngine.PARAMS_TD = td
    try:
        ue = CP.MixEngine(ind, cfg, {"JP": P0, "US": P0}, EX, {})
        ue.run()
    finally:
        CP.MixEngine.PARAMS_TD = old
    return pd.DataFrame(ue.st.trades)


def test_params_td_gives_each_entry_its_own_hold_and_stop():
    ind = {"1111.T": _bars([1000.0] * 16, entry_on=[D8[1], D8[8]]),
           "2222.T": _bars([1000.0] * 4 + [900.0] * 12, entry_on=[D8[1]])}
    tr0 = _run(ind, {})                                                                  # 缺省：都按 P0（6 天；止损 50% 不触发）
    assert set(tr0["ticker"]) == {"1111.T", "2222.T"}
    a0 = tr0[tr0["ticker"] == "1111.T"].sort_values("entry_date")
    assert list(a0["hold_days"]) == [6, 6] and list(a0["reason"]) == ["max_hold", "max_hold"]
    assert tr0[tr0["ticker"] == "2222.T"]["reason"].iloc[0] == "max_hold"
    td = {("1111.T", str(D8[2].date())): A.bnf_params(StrategyParams(), 2, 10.0),
          ("2222.T", str(D8[2].date())): A.bnf_params(StrategyParams(), 6, 5.0)}
    tr = _run(ind, td)
    a = tr[tr["ticker"] == "1111.T"].sort_values("entry_date")
    assert list(a["hold_days"]) == [2, 6]                                               # 第一笔按自己的 2 天，第二笔（没登记）按缺省
    td[("1111.T", str(D8[9].date()))] = A.bnf_params(StrategyParams(), 3, 10.0)
    a = _run(ind, td)
    assert list(a[a["ticker"] == "1111.T"].sort_values("entry_date")["hold_days"]) == [2, 3]   # 同一只票两笔各自的参数
    b = tr[tr["ticker"] == "2222.T"].iloc[0]
    assert b["reason"] == "stop" and b["hold_days"] < 6                                 # 止损 5%：跌 10% 那天收盘触发
    assert CP.MixEngine.PARAMS_TD == {}


def _acct(z=0.20, e=0.30, j=0.40, dd=-20.0):
    return {"Z": {"calmar": z, "dd": dd}, "E": {"calmar": e, "dd": dd}, "J": {"calmar": j, "dd": dd}}


def test_verdict_rules():
    tr = {k: {"n": 40, "mean": 0.5} for k in A.ERAS}
    base, a1 = _acct(), _acct(0.25, 0.31, 0.415)
    assert A.verdict("A3", tr, {"lo": 0.1}, _acct(0.10, 0.33, 0.43), base, a1) == ("通过", [])
    assert A.verdict("A1", tr, {"lo": 0.1}, _acct(0.10, 0.33, 0.43), base, a1) == ("通过", [])
    lab, f = A.verdict("A3", tr, {"lo": 0.1}, _acct(0.10, 0.33, 0.421), base, a1)          # J 过了 b（≥ 0.42），比 A1 只高 0.006
    assert lab == "不通过" and f == ["c J Calmar 0.421 < A1 0.415 + 0.01"]
    lab, f = A.verdict("A1", tr, {"lo": 0.1}, _acct(0.10, 0.33, 0.421), base, a1)
    assert lab == "通过"                                                                  # A1 不看 c
    lab, f = A.verdict("A4", tr, {"lo": 0.1}, _acct(0.10, 0.33, 0.419), base, a1)          # J 差 b
    assert lab == "不通过" and any(x.startswith("b J Calmar") for x in f)
    lab, f = A.verdict("A2", tr, {"lo": -0.1}, _acct(0.10, 0.33, 0.43), base, a1)
    assert lab == "不通过" and any("95% 下限" in x for x in f)
    lab, f = A.verdict("A2", tr, {"lo": 0.1}, _acct(0.10, 0.33, 0.43, dd=-23.0), base, a1)
    assert lab == "不通过" and any("回撤" in x for x in f)
    tr2 = {**tr, "E": {"n": 12, "mean": 2.0}}
    assert A.verdict("A5", tr2, {"lo": 0.1}, _acct(0.10, 0.33, 0.43), base, a1)[0] == "不通过"
    tr3 = {**tr, "Z": {"n": 5, "mean": -3.0}}                                            # Z 不判定
    assert A.verdict("A5", tr3, {"lo": 0.1}, _acct(-1.0, 0.33, 0.43), base, a1)[0] == "通过"


def test_month_table_and_theta_grid():
    assert all(o >= i + A.MIN_GAP for i, o, _, _ in A.THETAS) and len(A.THETAS) == len(set(A.THETAS))
    fa = {"A.T": _crash_frame(7)}
    D = {t: B.dev25(df["Close"]) for t, df in fa.items()}
    rows = A.fwd_rows(fa, D, 0.001)
    months, S, C = A.month_table(rows, 0.001, 0.15)
    k = A.T_INDEX[(-20.0, -10.0, 5, 10.0)]
    net = A.exit_net(rows, -10.0, 5, 10.0, 0.001, 0.15)
    m = np.isfinite(net) & (rows["dev"] <= -20.0)
    assert C[k].sum() == m.sum() and abs(S[k].sum() - net[m].sum()) < 1e-9
    assert A.path_summary({0: k, 1: k, 2: A.T_INDEX[(-25.0, -10.0, 5, 10.0)]}, 0, 2)["changes"] == 1


def test_walk_forward_ew_prefers_recent_months():
    rng = np.random.default_rng(0)
    n = 40
    months = np.arange(n)
    S = rng.normal(0, 0.01, (len(A.THETAS), n))
    C = np.full((len(A.THETAS), n), 6.0)
    k_old, k_new = A.T_INDEX[(-20.0, -10.0, 5, 10.0)], A.T_INDEX[(-15.0, -5.0, 3, 5.0)]
    m = 37
    S[k_old, m - 36:m - 12] = 6.0 * 3.0                                                 # 旧的 24 个月 θ_old 每笔 +3、最近 12 个月 0
    S[k_new, m - 12:m] = 6.0 * 3.0                                                      # 最近 12 个月 θ_new 每笔 +3、旧的 0
    S[k_old, m - 12:m] = 0.0
    S[k_new, m - 36:m - 12] = 0.0
    plain = A.walk_forward(months, S, C, m, m, start=k_old, win=36, ew=False)[m]
    ew = A.walk_forward(months, S, C, m, m, start=k_old, win=36, ew=True)[m]
    assert plain == k_old and ew == k_new                                               # 不加权：2.0 vs 1.0 → θ_old；衰减（半衰期 12）：1.28 vs 1.72 → θ_new


def test_month_table_bins_by_exit_month_and_ignores_next_month_prices():
    n = 60
    idx = pd.bdate_range("2021-01-04", periods=n)
    c = np.full(n, 1000.0)
    c[35:41] = [900, 820, 760, 740, 745, 760]                                          # 2 月下旬急跌 → 信号在 2 月底、卖出在 3 月
    c[41:] = 780.0
    fa = {"A.T": _frame(c, start="2021-01-04")}
    D = {t: B.dev25(df["Close"]) for t, df in fa.items()}
    rows = A.fwd_rows(fa, D, 0.001)
    months, S, C = A.month_table(rows, 0.001, 0.15)
    k = A.T_INDEX[(-20.0, -10.0, 5, 10.0)]
    sig = np.flatnonzero(np.isfinite(rows["dev"]) & (rows["dev"] <= -20.0))
    assert len(sig) >= 2 and all(idx[i].month == 2 for i in sig)
    feb, mar = A.mon("2021-02-01") - months[0], A.mon("2021-03-01") - months[0]
    assert C[k, feb] == 0 and C[k, mar] == len(sig)                                     # 信号在 2 月，都记在卖出的 3 月
    c2 = c.copy()
    c2[idx >= pd.Timestamp("2021-03-01")] *= 1.3                                        # 3 月的价格全改
    rows2 = A.fwd_rows({"A.T": _frame(c2, start="2021-01-04")}, {"A.T": B.dev25(_frame(c2, start="2021-01-04")["Close"])}, 0.001)
    months2, S2, C2 = A.month_table(rows2, 0.001, 0.15)
    assert np.array_equal(S[:, :mar], S2[:, :mar]) and np.array_equal(C[:, :mar], C2[:, :mar])   # 3 月以前的列一个数都不变
    assert not np.allclose(S[k, mar], S2[k, mar])


def test_exit_net_nan_when_data_ends_before_exit_fill():
    c = np.full(40, 1000.0)
    c[30:36] = [900, 820, 760, 740, 745, 760]
    c[36:] = 780.0
    fa = {"A.T": _frame(c)}
    D = {t: B.dev25(df["Close"]) for t, df in fa.items()}
    rows = A.fwd_rows(fa, D, 0.001)
    assert rows["dev"][32] <= -20.0
    assert not np.isfinite(A.exit_net(rows, 0.0, 20, 100.0, 0.001, 0.15)[32])           # 20 天到期的卖出在数据之外
    net, k = A.exit_net(rows, 0.0, 2, 100.0, 0.001, 0.15, with_k=True)
    assert np.isfinite(net[32]) and k[32] == 1 and rows["Xm"][32, 1] == A.mon(pd.bdate_range("2021-01-04", periods=40)[35])
    assert rows["Xm"][37, 1] == -1 and not np.isfinite(A.exit_net(rows, 0.0, 2, 100.0, 0.001, 0.15)[37])


def test_slope_insample_vol_and_drift_composition():
    ms = list(range(100, 112))
    path = {m: A.T_INDEX[(-10.0 if i < 6 else -20.0, 0.0, 5, 10.0)] for i, m in enumerate(ms)}
    sl = A.slope_of(path)
    assert abs(sl["d_in"] - (-180.0 / 143.0)) < 1e-9 and sl["d_out"] == 0.0 and sl["H"] == 0.0 and sl["S"] == 0.0   # 6 / 6 的台阶
    assert A.slope_of({m: path[m] for m in ms[:11]}) == {"d_in": 0.0, "d_out": 0.0, "H": 0.0, "S": 0.0}            # 不够 12 个月 → 0
    rng = np.random.default_rng(2)
    months, S, C = _tables(rng, 30, 6)
    k0 = A.T_INDEX[(-20.0, -10.0, 5, 10.0)]
    S[k0, 20] = 60.0                                                                    # 20 月这一列很好
    ins = A.theta_path_insample(months, S, C, 20, 21, win=12, hyst=0.0)
    assert ins[20] == k0 and ins[21] == k0                                              # 样本内路径含当月（≤ m）
    wf = A.walk_forward(months, S, C, 20, 21, start=0, win=12, ew=False)
    assert wf[20] != k0 and wf[21] == k0                                                # walk-forward 只用 < m
    sig = {m: 8.0 for m in range(20, 30)}
    kv, obj = A.fit_vol(months, S, C, sig, 20, 29)
    assert kv in {(ki, ko, H, s) for ki in A.K_IN for ko in A.K_OUT for H in A.GRID_H for s in A.GRID_S} and np.isfinite(obj)
    vp = A.vol_path(sig, kv, 18, 29, start=0)
    assert vp[18] == 0 and vp[19] == 0 and all(vp[m] == A.T_INDEX[A.vol_theta(8.0, *kv)] for m in range(20, 30))
    # A2：从 Z 最后一个月的 θ 出发，斜率 × 月数
    base = A.THETAS[k0]
    th = A.drift_theta(base, {"d_in": -0.25, "d_out": 0.0, "H": 0.0, "S": 0.0}, 10)
    assert th == (-22.5, -10.0, 5, 10.0)


def test_solo_trades_non_overlapping_and_month_theta():
    fa = {"A.T": _crash_frame(1), "B.T": _crash_frame(2)}
    D = {t: B.dev25(df["Close"]) for t, df in fa.items()}
    days = fa["A.T"].index
    ms = sorted({A.mon(d) for d in days})
    th_a, th_b = (-20.0, -10.0, 5, 10.0), (-15.0, -5.0, 2, 20.0)
    path = {m: A.T_INDEX[th_a if i % 2 == 0 else th_b] for i, m in enumerate(ms)}
    fr, td, prio = A.build(fa, D, days, path, StrategyParams())
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(SCF.NOTIONAL) * 2 / SCF.NOTIONAL * 100
    T = A.solo_trades(fr, path, A.bnf_params(StrategyParams()), bt, rt, days[0], days[-1])
    assert len(T) >= 2 and set(T.columns) >= {"ticker", "date", "exit_date", "net", "hold", "reason"}
    for t, g in T.groupby("ticker"):
        g = g.sort_values("date")
        ex = pd.to_datetime(g["exit_date"]).to_numpy()
        dt = pd.to_datetime(g["date"]).to_numpy()
        assert (dt[1:] >= ex[:-1]).all()                                                # 上一笔卖出之前的信号不算
        for _, r in g.iterrows():
            H = A.THETAS[path[A.mon(r["date"])]][2]
            assert r["hold"] <= H                                                       # 持有天数按信号月的 θ
    # 每一笔都是 build 的 entry 列里的信号
    for _, r in T.iterrows():
        assert fr[r["ticker"]].loc[r["date"], "entry"]


def test_solo_trades_drop_positions_still_open_at_window_end():
    n = 80
    idx = pd.bdate_range("2021-01-04", periods=n)
    c = np.full(n, 1000.0)
    c[35:41] = [900, 820, 760, 740, 745, 760]                                          # 2 月下旬急跌
    c[41:50] = 780.0
    c[50:] = 960.0                                                                      # 3 月中旬才回到 −10% 以内
    fa = {"A.T": _frame(c, start="2021-01-04")}
    D = {t: B.dev25(df["Close"]) for t, df in fa.items()}
    k = A.T_INDEX[(-20.0, 0.0, 20, 100.0)]                                             # 20 天到期、不止损 → 只有乖离卖出 / 到期
    feb = A.mon("2021-02-01")
    bt = SCF.bt_single()
    rt = bt.exec_cfg.fee(SCF.NOTIONAL) * 2 / SCF.NOTIONAL * 100
    fr_full, _, _ = A.build(fa, D, idx, {feb: k, feb + 1: k}, StrategyParams())
    T_full = A.solo_trades(fr_full, {feb: k, feb + 1: k}, A.bnf_params(StrategyParams()), bt, rt, idx[0], idx[-1])
    assert len(T_full) >= 1 and T_full["reason"].iloc[0] in ("dead_cross", "max_hold")
    fr_feb, _, _ = A.build(fa, D, idx, {feb: k}, StrategyParams())
    b_end = pd.Timestamp("2021-02-26")
    T_feb = A.solo_trades(fr_feb, {feb: k}, A.bnf_params(StrategyParams()), bt, rt, idx[0], b_end)
    assert len(T_feb) == 0                                                              # 窗口末（2/26）还没平仓 → 不计
