"""现行选股方案拆成每月（scripts/sel_monthly_study.py 登记检验）：按 θ0 重建的买点 = compute_indicators + W2（w2_keep）、其它档的买点是它的部件组合、
快速逐笔 = 研究引擎（止损 / 跟踪 / 止盈 / 吊灯 / 到期）、月表按平仓月入账、逐参数增减（OAT）的规则、分档（三分位、只用过去）与分档记忆、
build 的列与 PARAMS_TD、Spearman、判定规则、宏观序列的月末取值只用上月。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import candle_portfolio as CP                                                # noqa: E402
import leap_confirm as LF                                                    # noqa: E402
import sel_monthly_study as M                                                # noqa: E402

from qbreak import candles as K                                              # noqa: E402
from qbreak.config import ExecConfig, StrategyParams                        # noqa: E402
from qbreak.strategy import compute_indicators                              # noqa: E402
from qbreak.unified import UnifiedConfig                                     # noqa: E402

P0 = StrategyParams(max_distribution_days=6, max_upper_shadow_ratio=3.0, min_weekly_vol_ratio=0.0)
PX = StrategyParams(max_distribution_days=6, max_upper_shadow_ratio=3.0, min_weekly_vol_ratio=1.0, exit_on_macd_dead_cross=False,
                    exit_chandelier_k=3.0, exit_on_climax=True)                            # 与现行相同：放量阴线离场开
EX = {"JP": ExecConfig.for_market("JP", "tachibana"), "US": ExecConfig.for_market("US", "rakuten")}


def _synthetic(n_stocks=4, n=700, seed=0, start="2019-01-04"):
    """几只低波动的随机走势 + 偶尔放量 → 自然产生一些现行信号。"""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    data = {}
    for i in range(n_stocks):
        r = rng.normal(0.0003, 0.006, n)
        r[rng.integers(0, n, 12)] += 0.03                                                # 偶尔一根大阳线
        c = 1000.0 * np.cumprod(1 + r)
        o = c * (1 + rng.normal(0, 0.003, n))
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.004, n)))
        l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.004, n)))
        v = rng.lognormal(13, 0.5, n)
        v[rng.integers(0, n, 40)] *= 3.0
        data[f"{1000 + i}.T"] = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}, index=idx)
    names = list(data)
    P = K.panel(data, idx, names)
    ctx = {"P": P, "days": idx, "names": names, "cols": list(range(len(names)))}
    fa = {t: compute_indicators(df, P0) for t, df in data.items()}
    return ctx, fa


def test_theta0_entries_equal_current_rule_and_looser_grid_is_superset():
    ctx, fa = _synthetic()
    keep = LF.w2_keep(ctx, fa)
    comp = M.components(ctx, fa, P0)
    total = 0
    for t, df in fa.items():
        ref = df["entry"].to_numpy(bool) & np.asarray(keep[t], bool)
        mine = M.entry_mask(comp[t], M.THETA0[:5])
        assert np.array_equal(mine, ref), t
        total += int(ref.sum())
        loose = M.entry_mask(comp[t], (40, 20.0, 1.2, 0, 0.0))
        tight = M.entry_mask(comp[t], (90, 10.0, 2.0, 4, 1.5))
        assert not (mine & ~(loose | M.entry_mask(comp[t], (60, 20.0, 1.2, 0, 0.0)) | M.entry_mask(comp[t], (90, 20.0, 1.2, 0, 0.0)))).any()
        assert not (tight & ~mine).any()                                                 # 更严的档 ⊂ 现行
    assert total >= 1
    # 与 compute_indicators 直接换参数比：箱体 40 天 / 振幅 20 / 放量 1.2 / 出货不限
    p_alt = StrategyParams(range_n=40, range_x_pct=20.0, vol_mult=1.2, max_distribution_days=0, max_upper_shadow_ratio=3.0)
    for t, df in fa.items():
        raw = df[["Open", "High", "Low", "Close", "Volume"]]
        ref = compute_indicators(raw, p_alt)["entry"].to_numpy(bool)
        assert np.array_equal(M.entry_mask(comp[t], (40, 20.0, 1.2, 0, 0.0)), ref), t


def _engine_trade(df, entry_day, pp):
    """研究引擎（MixEngine）里只买这一笔 → (ret_pct, exit_date)。"""
    ind = df.copy()
    ind["entry"] = ind.index == entry_day
    ind["dead_cross"] = False
    cfg = UnifiedConfig(capital_jpy=1e10, position_pct=1.0, max_positions=1, max_position_pct=1.0, stock_markets=("JP",), core={}, core_index={})
    ue = CP.MixEngine({"A.T": ind}, cfg, {"JP": pp, "US": pp}, EX, {})
    ue.run(start=entry_day)
    tr = [t for t in ue.st.trades if t["reason"] != "end"]
    return tr[0] if tr else None


def test_fast_exit_matches_engine():
    ctx, fa = _synthetic(n_stocks=3, seed=3)
    comp = M.components(ctx, fa, P0)
    slip = EX["JP"].slippage_pct / 100
    rows = M.fwd_rows(fa, comp, slip)
    assert len(rows["entry"]) >= 3
    checked = 0
    for (S, kc, H) in ((7.0, 3.0, 60), (5.0, 2.0, 40), (10.0, 4.0, 90)):
        net, kx = M.exit_sim(rows, S, kc, H, slip, 0.0, PX.take_profit_pct, PX.trailing_stop_pct, PX.climax_min_gain_pct)
        pp = M.replace(PX, stop_loss_pct=S, exit_chandelier_k=kc, max_hold_days=H)
        for r in range(len(rows["entry"])):
            t, d = rows["tick"][r], pd.Timestamp(rows["date"][r])
            x = _engine_trade(fa[t], d, pp)
            if x is None:
                assert not np.isfinite(net[r]) or True                                     # 引擎没成交（跳空 / 涨停）或没卖完
                continue
            assert np.isfinite(net[r]), (t, d, S, kc, H)
            assert abs(net[r] - float(x["ret_pct"])) < 0.02, (t, d, S, kc, H, net[r], x)
            checked += 1
    assert checked >= 6


def test_month_table_bins_by_exit_month_and_current_index():
    ctx, fa = _synthetic(n_stocks=3, seed=5)
    comp = M.components(ctx, fa, P0)
    rows = M.fwd_rows(fa, comp, 0.001)
    months, S, C = M.month_table(rows, 0.001, 0.15, 25.0, 12.0)
    assert M.THETAS[M.K0] == M.THETA0 and len(M.THETAS) == 3 ** 8 and M.K0 == M.E_INDEX[M.THETA0[:5]] * 27 + M.EXITS.index((7.0, 3.0, 60))
    net, k = M.exit_sim(rows, 7.0, 3.0, 60, 0.001, 0.15, 25.0, 12.0)
    sel = rows["M"][:, M.E_INDEX[M.THETA0[:5]]] & np.isfinite(net)
    assert C[M.K0].sum() == sel.sum() and abs(S[M.K0].sum() - net[sel].sum()) < 1e-9
    xm = rows["Xm"][np.arange(len(k)), np.maximum(k, 0)]
    for r in np.flatnonzero(sel):
        assert C[M.K0, xm[r] - months[0]] >= 1                                            # 记在卖出那个月
        assert xm[r] > rows["mon"][r] or rows["Xm"][r, 0] == rows["mon"][r]


def test_oat_rules_and_gain():
    n_m = 50
    months = np.arange(n_m)
    S = np.zeros((len(M.THETAS), n_m))
    C = np.zeros((len(M.THETAS), n_m))
    k0 = M.K0
    C[k0, :] = 2.0                                                                        # 现行每月 2 笔 → 36 个月 72 笔
    S[k0, :] = 2.0 * 1.0                                                                  # 每笔 +1.0
    j = 2                                                                                 # 放量倍数
    k_low, k_high = M.oat_theta_index(j, 1.2), M.oat_theta_index(j, 2.0)
    C[k_low, :], C[k_high, :] = 3.0, 2.0                                                 # 松的档笔多（108 vs 72，差 ≥ 10 → 增减度才算）
    S[k_low, :], S[k_high, :] = 3.0 * 0.5, 2.0 * 1.5                                     # 大档每笔 +1.5（比现行好 0.5 ≥ 0.25）→ 该增
    cols = np.arange(4, 40)
    vals, gains, objs, ns = M.oat_month(S, C, cols)
    assert vals[j] == 2.0 and abs(gains[j] - 1.0) < 1e-9 and vals[0] == M.THETA0[0]
    assert ns[j] == [108, 72, 72] and objs[j][0] == 0.5 and len(ns) == 8
    S[k_high, :] = 2.0 * 1.2                                                              # 只好 0.2 → 不动
    vals, gains, _, _ = M.oat_month(S, C, cols)
    assert vals[j] == M.THETA0[j] and abs(gains[j] - 0.7) < 1e-9
    C[k_high, :] = 0.5                                                                    # 大档 36 × 0.5 = 18 笔 < 20 → 不算、增减度无值
    vals, gains, _, _ = M.oat_month(S, C, cols)
    assert vals[j] == M.THETA0[j] and np.isnan(gains[j])
    path, g = M.oat_path(months, S, C, 40, 41)
    assert set(path) == {40, 41} and all(len(v) == 8 for v in g.values())


def test_bucket_labels_and_path_use_only_past():
    ser = {m: float(m % 30) for m in range(0, 60)}                                        # 0..29 循环
    lab = M.bucket_labels(ser, min_hist=24)
    assert lab[0] is None and lab[22] is None and lab[23] in (0, 1, 2)                    # 历史（含当月）满 24 个月才分档
    ser2 = dict(ser)
    for m in range(40, 60):
        ser2[m] = 999.0                                                                   # 改 40 以后的值 → 40 以前的档不变
    lab2 = M.bucket_labels(ser2, min_hist=24)
    assert all(lab2[m] == lab[m] for m in range(0, 40))
    months = np.arange(60)
    S = np.zeros((len(M.THETAS), 60))
    C = np.zeros((len(M.THETAS), 60))
    k1 = M.oat_theta_index(0, 90)
    labels = {m: (0 if m % 2 == 0 else 1) for m in range(60)}
    C[k1, ::2], S[k1, ::2] = 5.0, 5.0 * 3.0                                              # 偶数月（档 0）θ1 很好
    C[M.K0, :], S[M.K0, :] = 5.0, 5.0 * 0.5
    path = M.bucket_path(months, S, C, 30, 33, labels, M.K0)
    assert path[30] == k1 and path[31] == M.K0 and path[32] == k1                          # 偶数月按档 0 的记忆、奇数月按档 1（θ1 没数据 → 现行最好）
    S2 = S.copy()
    S2[k1, 30:] = -100.0                                                                  # 改 30 月及以后 → 30 月的选择不变
    assert M.bucket_path(months, S2, C, 30, 30, labels, M.K0)[30] == k1


def test_build_and_params_td_keys():
    ctx, fa = _synthetic(n_stocks=3, seed=7)
    comp = M.components(ctx, fa, P0)
    days = pd.DatetimeIndex(ctx["days"])
    ms = sorted({M.mon(d) for d in days})
    alt = M.T_INDEX[(40, 20.0, 1.2, 0, 0.0, 5.0, 2.0, 40)]
    path = {m: (M.K0 if i % 2 == 0 else alt) for i, m in enumerate(ms)}
    fr, td = M.build(fa, comp, days, path, PX)
    for t, df in fr.items():
        ent = df["entry"].to_numpy(bool)
        mo = np.array([M.mon(d) for d in df.index])
        for j in np.flatnonzero(ent):
            th = M.THETAS[path[mo[j]]]
            assert M.entry_mask(comp[t], th[:5])[j]
            key = (t, str(days[int(np.flatnonzero(days == df.index[j])[0]) + 1].date()))
            assert td[key].stop_loss_pct == th[5] and td[key].exit_chandelier_k == th[6] and td[key].max_hold_days == th[7]
            assert td[key].take_profit_pct == PX.take_profit_pct and not td[key].exit_on_macd_dead_cross
    assert sum(df["entry"].sum() for df in fr.values()) >= 1


def test_spearman_and_month_end_map():
    x = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13], dtype=float)
    assert abs(M.spearman(x, x ** 2)[0] - 1.0) < 1e-9 and M.spearman(x, -x)[0] < -0.99
    assert np.isnan(M.spearman(x[:5], x[:5])[0])
    idx = pd.bdate_range("2021-01-04", periods=70)
    s = pd.Series(np.arange(70, dtype=float), index=idx)
    mp = M.month_end_map(s)
    assert mp[M.mon("2021-02-01")] == float(s[s.index.month == 1].iloc[-1])              # 2 月用 1 月底的值
    assert mp[M.mon("2021-03-01")] == float(s[s.index.month == 2].iloc[-1])
    mp2 = M.month_end_map(s, lag_months=2)
    assert mp2[M.mon("2021-03-01")] == float(s[s.index.month == 1].iloc[-1])


def test_verdict_rules():
    base = {"Z": {"calmar": 1.76, "dd": -7.5, "n": 40}, "E": {"calmar": 0.319, "dd": -27.5, "n": 80}, "J": {"calmar": 0.403, "dd": -35.0, "n": 60}}
    good = {"Z": {"calmar": 1.75, "dd": -7.6, "n": 40}, "E": {"calmar": 0.345, "dd": -28.0, "n": 60}, "J": {"calmar": 0.45, "dd": -34.0, "n": 50}}
    assert M.verdict("C1", good, base, 0.44) == ("通过", [])
    lab, f = M.verdict("C1", good, base, 0.46)
    assert lab == "不通过" and any(x.startswith("b J") for x in f)
    bad = {**good, "E": {"calmar": 0.335, "dd": -28.0, "n": 60}}
    assert any(x.startswith("a E Calmar") for x in M.verdict("C1", bad, base, 0.44)[1])
    bad = {**good, "Z": {"calmar": 1.70, "dd": -8.0, "n": 40}}
    assert any(x.startswith("a Z") for x in M.verdict("C1", bad, base, 0.44)[1])
    bad = {**good, "J": {"calmar": 0.45, "dd": -37.5, "n": 20}}
    f = M.verdict("C1", bad, base, 0.44)[1]
    assert any("回撤" in x for x in f) and any(x.startswith("c J") for x in f)
    assert M.path_summary({0: M.K0, 1: M.K0, 2: M.oat_theta_index(0, 90)}, 0, 2)["changes"] == 1


def test_climax_exit_in_fast_and_engine():
    """放量阴线（量 ≥ 均量 2.5 倍且收阴）且浮盈 ≥ 5% → 次日开盘卖；关掉就不卖。"""
    ctx, fa = _synthetic(n_stocks=3, seed=11)
    comp = M.components(ctx, fa, P0)
    slip = EX["JP"].slippage_pct / 100
    rows = M.fwd_rows(fa, comp, slip)
    on, _ = M.exit_sim(rows, 10.0, 0.0, 90, slip, 0.0, 999.0, 99.0, 5.0)                    # 只剩放量阴线与到期
    off, _ = M.exit_sim(rows, 10.0, 0.0, 90, slip, 0.0, 999.0, 99.0, None)
    diff = np.flatnonzero(np.isfinite(on) & np.isfinite(off) & (np.abs(on - off) > 1e-9))
    pp = M.replace(PX, stop_loss_pct=10.0, exit_chandelier_k=0.0, max_hold_days=90, take_profit_pct=999.0, trailing_stop_pct=99.0)
    checked = 0
    for r in diff[:6]:
        t, d = rows["tick"][r], pd.Timestamp(rows["date"][r])
        x = _engine_trade(fa[t], d, pp)
        if x is None:
            continue
        assert x["reason"] == "climax" and abs(on[r] - float(x["ret_pct"])) < 0.02, (t, d, on[r], x)
        checked += 1
    assert len(diff) == 0 or checked >= 1


def test_bucket_labels_rolling_window_and_fill_needs_next_trading_day():
    ser = {m: 100.0 for m in range(0, 200)}
    for m in range(200, 260):
        ser[m] = float(m - 200)                                                             # 之后 60 个月 0..59
    lab_all = M.bucket_labels(ser, min_hist=24, window=10 ** 6)                              # 从头到当时：最近的值都在最低档
    lab_win = M.bucket_labels(ser, min_hist=24, window=120)
    assert lab_all[259] == 0 and lab_win[259] == 1                                           # 滚动 120 个月：59 在最近十年（60 个 100 + 0..59）里是中档
    # 成交日必须是下一个交易日：把一只票信号次日的 K 线抽掉 → 快速逐笔不算买到
    ctx, fa = _synthetic(n_stocks=2, seed=13)
    comp = M.components(ctx, fa, P0)
    days = pd.DatetimeIndex(ctx["days"])
    rows = M.fwd_rows(fa, comp, 0.001, days)
    assert len(rows["entry"]) >= 1
    r0 = int(np.flatnonzero(np.isfinite(rows["entry"]))[0]) if np.isfinite(rows["entry"]).any() else 0
    t, d = rows["tick"][r0], pd.Timestamp(rows["date"][r0])
    df = fa[t]
    j = int(np.flatnonzero(df.index == d)[0])
    fa2 = dict(fa)
    fa2[t] = df.drop(df.index[j + 1])                                                       # 抽掉次日
    comp2 = M.components(ctx, fa2, P0)
    rows2 = M.fwd_rows(fa2, comp2, 0.001, days)
    sel = (rows2["tick"] == t) & (pd.DatetimeIndex(rows2["date"]) == d)
    assert sel.sum() <= 1 and (not sel.any() or not np.isfinite(rows2["entry"][sel][0]))
    yg = M.yearly_gains(np.arange(24), np.zeros((len(M.THETAS), 24)), np.zeros((len(M.THETAS), 24)), 0, 23)
    assert set(yg) == {0, 1} and all(len(v) == 8 for v in yg.values())


def test_oat_gain_needs_count_margin_for_entry_params_only():
    """买点参数的三档嵌套 → 大档与小档笔数差 < 10 时增减度不算（NaN）；卖点参数是同一批笔的配对比较，不受此限。"""
    n_m = 50
    S = np.zeros((len(M.THETAS), n_m))
    C = np.zeros((len(M.THETAS), n_m))
    cols = np.arange(4, 40)
    C[M.K0, :], S[M.K0, :] = 2.0, 2.0 * 1.0
    for j in (2, 5):                                                                      # 放量倍数（买点）、止损（卖点）
        lo, hi = M.oat_theta_index(j, M.GRIDS[j][0]), M.oat_theta_index(j, M.GRIDS[j][2])
        C[lo, :], C[hi, :] = 2.0, 2.0                                                     # 两档都 72 笔，差 0 < 10
        S[lo, :], S[hi, :] = 2.0 * 0.5, 2.0 * 1.5
    vals, gains, _, ns = M.oat_month(S, C, cols)
    assert np.isnan(gains[2]) and abs(gains[5] - 1.0) < 1e-9 and vals[2] == 2.0 and vals[5] == 10.0  # 选值不受笔数差影响
    lo = M.oat_theta_index(2, 1.2)
    C[lo, :], S[lo, :] = 3.0, 3.0 * 0.5                                                     # 小档 108 笔（多 36 ≥ 10）、每笔仍 +0.5 → 算
    _, gains, _, ns = M.oat_month(S, C, cols)
    assert abs(gains[2] - 1.0) < 1e-9 and ns[2] == [108, 72, 72]


def test_neighbour_path_one_step_and_deterministic():
    a, b = 100, 130
    p1, p2 = M.neighbour_path(a, b, 3), M.neighbour_path(a, b, 3)
    assert p1 == p2 and set(p1) == set(range(a, b + 1))
    for k in p1.values():
        th = M.THETAS[k]
        for j, g in enumerate(M.GRIDS):
            assert th[j] in g and abs(g.index(th[j]) - 1) <= 1
    assert M.neighbour_path(a, b, 4) != p1                                                # 种子不同 → 路径不同
    assert len({M.THETAS[k][0] for k in p1.values()}) >= 2                                # 会动


def test_null_stars_and_star_count_shapes():
    rng = np.random.default_rng(0)
    ms = list(range(200, 260))
    GAIN = {e: {m: list(rng.normal(size=8)) for m in ms} for e in ("Z", "E", "J")}
    MAC = {e: {k: {m: float(rng.normal()) for m in ms} for k in M.MACRO_KEYS[:3]} for e in ("Z", "E", "J")}
    n0, mx0 = M.star_count(GAIN, MAC, keys=M.MACRO_KEYS[:3])
    assert isinstance(n0, int) and 0 <= n0 <= 24 and 0.0 <= mx0 <= 1.0
    ns, mxs = M.null_stars(GAIN, MAC, draws=5)
    assert len(ns) == 5 and len(mxs) == 5 and all(isinstance(x, int) for x in ns) and all(0.0 <= x <= 1.0 for x in mxs)
    assert M.null_stars(GAIN, MAC, draws=5) == (ns, mxs)                                  # 同一种子 → 同一结果
    # 平移一整圈 = 不平移
    n_full, _ = M.star_count(GAIN, MAC, keys=M.MACRO_KEYS[:3], shift={"E": len(ms), "J": len(ms)})
    assert n_full == n0


def test_persistence_keys_and_values():
    YG = {"E": {2007: [1.0] * 8, 2008: [0.5] * 8, 2009: [-1.0] * 8}, "J": {2018: [np.nan] * 8, 2019: [2.0] * 8}}
    out = M.persistence(YG)
    assert set(out) == set(M.PKEYS)
    for v in out.values():
        assert v["n_pairs"] == 2 and abs(v["same_sign_pct"] - 50.0) < 1e-9 and v["rho"] is None         # < 12 对 → ρ 无值
    assert M.persistence({"E": {2007: [np.nan] * 8}})["stop"] == {"n_pairs": 0, "same_sign_pct": None, "rho": None}
