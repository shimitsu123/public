"""趋势线质地特征 → 选股研究（scripts/trendline_select_study.py，登记版）：特征没有用到未来的 K 线（含周中截断）、特征的定义、三分位 / 整数 / bool 分组、
只挡两端、重排组标签的随机对照、入围规则（族上限）、横截面的差与秩相关、自助法可重现、界线核对、U0 的时点名单。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import trendline_select_study as T                                           # noqa: E402
from qbreak import trendline as TL                                           # noqa: E402


def _df(n=700, seed=3):
    rng = np.random.default_rng(seed)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.018, n)))
    idx = pd.bdate_range("2018-01-01", periods=n)
    return pd.DataFrame({"Open": c * (1 + rng.normal(0, 0.003, n)), "High": c * (1 + rng.random(n) * 0.012),
                         "Low": c * (1 - rng.random(n) * 0.012), "Close": c}, index=idx)


def test_features_use_no_future_bars_including_midweek_cuts():
    df = _df()
    full = T.ticker_features(df)
    assert list(full.columns) == ["fwd"] + T.COLS
    cols = T.COLS
    for cut in (300, 452, 453, 454, 455, 640, 642):                          # 含周一〜周四的截断点（周线用「上一根走完的周K」）
        part = T.ticker_features(df.iloc[:cut + 1])
        a, b = full.loc[part.index, cols], part[cols]
        for c in cols:
            x = np.nan_to_num(a[c].to_numpy(float), nan=-1e9)
            y = np.nan_to_num(b[c].to_numpy(float), nan=-1e9)
            assert np.allclose(x, y, atol=1e-5), (cut, c)
    fwd = full["fwd"].to_numpy(float)
    c, o = df["Close"].to_numpy(), df["Open"].to_numpy()
    assert abs(fwd[100] - (c[100 + T.H] / o[101] - 1) * 100) < 1e-3 and np.isnan(fwd[-1])


def test_feature_definitions_match_the_scan():
    x = np.arange(400)
    c = 100 + 0.5 * x + 10 * np.sin(2 * np.pi * (x % 20) / 20)                 # 上升通道
    df = pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1, "Close": c}, index=pd.bdate_range("2020-01-01", periods=400))
    f = T.ticker_features(df)
    s = TL.scan(df, "D")
    t = 300
    atr = s["tol"][t] / TL.TOL_ATR
    assert abs(f["d_res_atr"].iloc[t] - (s["res"][t] - c[t]) / atr) < 1e-4
    assert abs(f["d_sup_atr"].iloc[t] - (c[t] - s["sup"][t]) / atr) < 1e-4
    assert abs(f["d_pos"].iloc[t] - (c[t] - s["sup"][t]) / (s["res"][t] - s["sup"][t])) < 1e-5 and 0 <= f["d_pos"].iloc[t] <= 1
    assert f["d_sup_touch"].iloc[t] == s["sup_touch"][t] >= 2 and f["d_sup_len"].iloc[t] == t - s["sup_a1"][t]
    assert abs(f["d_sup_slope"].iloc[t] - s["sup_slope"][t]) < 1e-5
    assert not f["d_rb5"].iloc[t] and not f["d_sb20"].iloc[t]
    assert np.isnan(f["d_res_atr"].iloc[0]) and np.isnan(f["d_sup_touch"].iloc[0]) and not f["d_rb5"].iloc[0]
    ev = np.zeros(30, bool)
    ev[10] = True
    r5, r20 = T._recent(ev, 5), T._recent(ev, 20)
    assert not r5[9] and r5[10] and r5[14] and not r5[15]
    assert r20[29] and not r20[9]
    g = T.ticker_features(_df(900, seed=8))                                  # 随机行情才会有周线
    assert g["w_sup_touch"].dropna().min() >= 2 and g["w_res_atr"].notna().sum() > 100
    for _, wk in g.groupby(g.index.to_period("W")):
        for col in ("w_sup_slope", "w_res_slope", "w_sup_touch", "w_res_touch"):
            assert wk[col].dropna().nunique() <= 1, col                      # 一周里用同一根（上一根走完的）周K
    assert (g["w_res_atr"].isna() == g["w_res_slope"].isna()).all()
    assert g["d_res_atr"].min() >= -TL.TOL_ATR - 1e-6                        # 收盘最多在压力线上方一个容差


def test_bounds_groups_ends_and_degenerate():
    V = pd.DataFrame({c: np.nan for c in T.COLS}, index=range(9))
    V["d_res_atr"] = [1, 2, 3, 4, 5, 6, np.nan, 7, 8]
    V["d_sup_touch"] = [2, 2, 3, 4, 5, np.nan, 2, 3, 9]
    V["w_pos"] = [0.5] * 9                                                    # 并列 → q1 == q2 → 退化
    tb = T.tercile_bounds(V)
    b = tb["bounds"]
    assert b["F01"][0] < b["F01"][1] and tb["n"]["F01"] == 8 and "F06" not in b and "F10" not in b
    assert T.degenerate("F14", b) and not T.degenerate("F01", b) and not T.degenerate("F06", b) and not T.degenerate("F10", b)
    g = T.groups_of(V["d_res_atr"].to_numpy(), "F01", b)
    assert g[6] == 0 and set(g[[0, 1]]) == {1} and set(g[[7, 8]]) == {3}
    gi = T.groups_of(V["d_sup_touch"].to_numpy(), "F06", b)
    assert gi.tolist() == [1, 1, 2, 3, 3, 0, 1, 2, 3]
    gb = T.groups_of(np.array([1, 0, 1, 0], float), "F10", b, has=np.array([True, True, False, False]))
    assert gb.tolist() == [2, 1, 0, 0]                                        # 没有特征行 → G0（bool 也是）
    assert T.ends_of("F01") == (1, 3) and T.ends_of("F06") == (1, 3) and T.ends_of("F10") == (1, 2)
    net = np.array([5.0, -5.0, 1.0, 1.0, 1.0, 1.0, -9.0, -9.0, 2.0, 2.0])
    grp = np.array([1, 1, 2, 2, 2, 2, 3, 3, 0, 0], np.int8)
    assert T.choose_group(net, grp, "F01") == 3                                # 只在 G1 / G3 两端里选，中间组再差也不挡
    assert T.choose_group(net, np.where(grp == 3, 1, grp).astype(np.int8), "F01") is None


def test_placebo_permutes_labels_and_repeats_the_selection():
    rng = np.random.default_rng(0)
    net = rng.normal(0, 5, 150)
    g = np.array([0] * 30 + [1] * 40 + [2] * 40 + [3] * 40, np.int8)
    a = T.placebo_pct(net, g, "F01", 2, 0.3)
    b = T.placebo_pct(net, g, "F01", 2, 0.3)
    assert a == b and a["n"] == T.PLACEBO_N and 0 <= a["pct"] <= 100
    # 对照里每一次重排都保留各组个数、G0 不动，并且挡掉的是重排后两端里平均更低的一端（与候选同一条规则）
    import combo_all_common as CA
    pos = np.flatnonzero(g != 0)
    vals = []
    for s in range(T.PLACEBO_N):
        r = np.random.default_rng([*T.PLACEBO_SEED, 2, s])
        gp = g.copy()
        gp[pos] = g[pos][r.permutation(len(pos))]
        assert (gp[g == 0] == 0).all() and np.array_equal(np.bincount(gp), np.bincount(g))
        k = T.choose_group(net, gp, "F01")
        assert k in (1, 3) and net[gp == k].mean() <= net[gp == (4 - k)].mean()
        vals.append(CA.delta(net, gp != k)["dmean"])
    assert abs(a["p95"] - float(np.quantile(vals, 0.95))) < 1e-9                  # 与脚本里的对照逐次相同（不四舍五入）


def test_selection_rule_family_cap_and_no_cand():
    def cand(fid, dj, dw, frac_j=0.3, frac_w=0.3, p95=0.1):
        return {"id": T.CAND[fid], "group": 1, "cand": fid in T.CAND_IDS,
                "delta": {"Jx": {"frac": frac_j, "dwin": dj[0], "dmean": dj[1], "changed": 10, "n": 30},
                          "W": {"frac": frac_w, "dwin": dw[0], "dmean": dw[1], "changed": 5, "n": 15}}, "placebo": {"p95": p95}}
    expl = {f: cand(f, (3.0, 0.5), (1.0, 0.1)) for f in T.FIDS}
    expl["F02"] = cand("F02", (3.0, 0.9), (1.0, 0.1))                        # 最好（族 ②）
    expl["F13"] = cand("F13", (3.0, 0.8), (1.0, 0.1))                        # 同族 ② → 让位
    expl["F03"] = cand("F03", (1.0, 0.9), (1.0, 0.1))                        # b 不过（胜率差 < 2）
    expl["F04"] = cand("F04", (3.0, 0.9), (0.0, 0.1))                        # c 不过（W 胜率差要 > 0）
    expl["F05"] = cand("F05", (3.0, 0.9), (1.0, 0.1), frac_j=0.05)           # a 不过
    expl["F06"] = cand("F06", (3.0, 0.9), (1.0, 0.1), p95=0.95)              # d 不过
    expl["F12"] = cand("F12", (9.0, 9.0), (9.0, 9.0))                        # 不是候选（上一轮 TLB2 的变体）
    for f in T.FIDS:
        r = expl[f]
        dj, dw = r["delta"]["Jx"], r["delta"]["W"]
        r["a"] = T.BLOCK_LO <= dj["frac"] <= T.BLOCK_HI and T.BLOCK_LO <= dw["frac"] <= T.BLOCK_HI
        r["b"] = dj["dwin"] >= T.WIN_MIN and dj["dmean"] >= T.MEAN_MIN
        r["c"] = dw["dwin"] > 0 and dw["dmean"] >= 0
        r["d"] = dj["dmean"] > r["placebo"]["p95"]
        r["selected"] = r["cand"] and r["a"] and r["b"] and r["c"] and r["d"]
    fin = T.finalists(expl)
    assert len(fin) == T.MAX_FINAL == 3 and fin[0] == "F02" and "F13" not in fin and "F12" not in fin
    assert not {"F03", "F04", "F05", "F06"} & set(fin)
    assert len({T.FAM_OF[f] for f in fin}) == len(fin)                        # 同族最多 1 个
    assert T.CAND["F01"] == "TQ01" and T.CAND["F18"] == "TQ18" and set(T.NO_CAND) == {"F12", "F14"}
    assert set(T.FAM_OF) == set(T.FIDS)


def test_xsec_spread_and_rank_correlation_by_hand():
    d1, d2 = pd.Timestamp("2024-01-05"), pd.Timestamp("2024-01-12")
    rows = []
    for d in (d1, d2):
        for i in range(15):
            rows.append({"date": d, "ticker": f"{i}.T", "ex": float(i) if d == d1 else float(-i), "d_res_atr": float(i), "d_rb5": i >= 9,
                         "d_sup_touch": 2.0 if i < 5 else (3.0 if i < 9 else 4.0 + i % 3)})
    P = pd.DataFrame(rows)
    days = pd.bdate_range(d1, periods=6)                                     # 每 5 个交易日取一天 → d1（第 0 天）与 d2（第 5 天）
    assert days[5] == d2
    X = T.xsec(P, days, "F01")
    assert len(X) == 2
    r1 = X[X["date"] == d1].iloc[0]
    assert abs(r1["spread"] - (np.mean([10, 11, 12, 13, 14]) - np.mean([0, 1, 2, 3, 4]))) < 1e-9 and r1["n_hi"] == 5 and r1["n_lo"] == 5
    assert abs(r1["rho"] - 1.0) < 1e-9 and abs(X[X["date"] == d2].iloc[0]["rho"] + 1.0) < 1e-9
    B = T.xsec(P, days, "F10")
    b1 = B[B["date"] == d1].iloc[0]
    assert abs(b1["spread"] - (np.mean(range(9, 15)) - np.mean(range(9)))) < 1e-9 and b1["n_hi"] == 6 and b1["n_lo"] == 9
    I = T.xsec(P, days, "F06")                                                # 整数：{≥ 4} − {2}
    i1 = I[I["date"] == d1].iloc[0]
    assert abs(i1["spread"] - (np.mean(range(9, 15)) - np.mean(range(5)))) < 1e-9 and i1["n_hi"] == 6 and i1["n_lo"] == 5
    small = P[P["ticker"].isin([f"{i}.T" for i in range(8)])]
    assert len(T.xsec(small, days, "F01")) == 0
    j = T.judge_a({"by": {f: {s: {"mean": 0.5} for s in T.SAMPLES} for f in T.FIDS},
                   "pooled": {f: {"mean": 0.5, "lo": 0.1, "hi": 0.9} for f in T.FIDS}})
    assert all(j[f]["info"] for f in T.FIDS)
    a = {"by": {f: {s: {"mean": -0.5} for s in T.SAMPLES} for f in T.FIDS}, "pooled": {f: {"mean": -0.5, "lo": -0.9, "hi": -0.1} for f in T.FIDS}}
    a["by"]["F01"]["Zx"] = {"mean": 0.1}                                     # 一个样本反号 → 不算
    a["pooled"]["F02"] = {"mean": -0.2, "lo": -0.3, "hi": -0.1}              # 不到 0.3 pp
    j = T.judge_a(a)
    assert not j["F01"]["info"] and not j["F02"]["info"] and j["F03"]["info"] and j["F03"]["sign"] == "−"


def test_gates_values_at_and_report_smoke():
    import json
    import research_loop11 as R11
    # a〜d 的边界（门槛比较用没有四舍五入的值）
    dj = {"frac": 0.10, "dwin": 2.0, "dmean": 0.20}
    dw = {"frac": 0.70, "dwin": 1e-6, "dmean": 0.0}
    g = T.gates(dj, dw, {"p95": 0.1999})
    assert g == {"a": True, "b": True, "c": True, "d": True}
    assert not T.gates({**dj, "frac": 0.0999}, dw, {"p95": 0.1})["a"] and not T.gates({**dj, "dwin": 1.9999}, dw, {"p95": 0.1})["b"]
    assert not T.gates(dj, {**dw, "dwin": 0.0}, {"p95": 0.1})["c"] and not T.gates(dj, dw, {"p95": 0.20})["d"] and not T.gates(dj, dw, None)["d"]
    # values_at：找不到的（票, 日）→ NaN / _has False；单列路径（era_groups 用）
    idx = pd.bdate_range("2024-01-01", periods=5)
    FL = {"A.T": pd.DataFrame({c: np.float32(1.0) for c in T.COLS}, index=idx).assign(d_rb5=True, d_sb20=False)}
    V = T.values_at(FL, ["A.T", "A.T", "B.T"], [idx[1], pd.Timestamp("2024-02-01"), idx[1]])
    assert V["_has"].tolist() == [True, False, False] and V["d_res_atr"].iloc[0] == 1.0 and np.isnan(V["d_res_atr"].iloc[1])
    V1 = T.values_at(FL, ["A.T"], [idx[2]], ["d_rb5"])
    assert list(V1.columns) == ["d_rb5", "_has"] and V1["d_rb5"].iloc[0] == 1.0
    # _delta 的字典满足 research_loop11.pool_ok（V4 / V6 用）
    net = np.array([3.0, -1.0, 2.0, -2.0, 5.0, 1.0])
    d = T._delta(net, np.array([False, True, False, True, False, False]))
    assert d["changed"] == 2 and R11.pool_ok(d, "A") and R11.pool_ok(d, "B") and not R11.pool_ok({**d, "changed": 0}, "B")
    # report()：没有入围 / 有入围 / 有 U0 的合成结果都能写出来，而且输出里没有个股代码
    def cm(v):
        return {"n": 10, "mean": v, "se": 0.1, "lo": v - 0.2, "hi": v + 0.2, "clusters": 5, "days": 10, "rho": 0.01, "n_hi": 30.0, "n_lo": 30.0}
    cols = list(T.SAMPLES) + [T.U0]
    A = {"by": {f: {s: cm(0.05) for s in cols} for f in T.FIDS}, "pooled": {f: cm(0.05) for f in T.FIDS},
         "coverage": {s: {f: 90.0 for f in T.FIDS} for s in cols}, "raw": {s: {"sample_rows": 100, "tickers": 10, "sample_days": 10} for s in cols}}
    A["judge"] = T.judge_a(A)
    for f in T.FIDS:
        A["judge"][f]["u0_same_sign"] = True
    tab = {s: {0: {"n": 3, "win": 50.0, "mean": 0.1}, 1: {"n": 5, "win": 40.0, "mean": -1.0}, 2: {"n": 5, "win": 50.0, "mean": 0.5}, 3: {"n": 5, "win": 60.0, "mean": 1.0}} for s in T.EXPLORE}
    dl = {"n": 18, "kept": 13, "changed": 5, "frac": 0.2778, "dwin": 3.0, "dmean": 0.5}
    expl = {}
    for f in T.FIDS:
        cand = f in T.CAND_IDS
        expl[f] = {"id": T.CAND[f], "col": T.FEATS[f][0], "family": T.FAM_OF[f], "cand": cand, "tables": tab, "group": 1 if cand else None,
                   "group_name": T.names_of(f).get(1) if cand else None, "delta": {s: dict(dl) for s in T.EXPLORE} if cand else {},
                   "halves": {s: {"前一半": dict(dl), "后一半": None} for s in T.EXPLORE} if cand else {},
                   "placebo": {"p95": 0.3, "pct": 99.0, "n": 200} if cand else None, "a": cand, "b": cand, "c": cand, "d": cand, "selected": cand}
    base = {e: {"cagr": 5.0, "dd": 10.0, "calmar": 0.5, "h1": 0.4, "h2": 0.6, "n": 30, "mean": 3.0, "win": 55.0} for e in T.N225_ERAS}
    res = {"git": {"rev": "abc", "dirty": False}, "prereq": {"fingerprint": "x"}, "base": base, "bounds": {"F01": [0.1, 0.2]}, "bounds_n": {"F01": 100},
           "A": A, "explore": expl, "explore_extra": {"n_pool": {s: 18 for s in T.EXPLORE}, "competition": {s: {"days": 9, "days_ge2": 2, "signals_on_ge2": 5} for s in T.EXPLORE}},
           "finalists": [], "confirm": {}, "describe": {e: {"n": 30} for e in T.N225_ERAS},
           "counts": {"n225": {e: {"days": 9, "days_ge2": 1} for e in T.N225_ERAS}}, "success_base": {}, "elapsed_s": 1}
    md0 = T.report(res)
    assert "没有" in md0 and "非投资建议" in md0
    fin = T.finalists(expl)
    assert len(fin) == 3
    cand = {e: {**base[e], "calmar": 0.55, "blocked": 4} for e in T.N225_ERAS}
    other = {s: dict(dl) for s in T.POOLS}
    s1 = R11.stage1(cand, base, other, lenses=None, posthoc=True)
    res["finalists"] = fin
    res["confirm"] = {f: {"id": T.CAND[f], "group": 1, "cand": cand, "other": other, "stage1": s1,
                          "scale": {e: {"blocked": 4, "signals": 30, "share": 0.13, "ok": True} for e in T.N225_ERAS},
                          "cross": {"z_dwin": 0.0, "zx_dmean": 0.5, "ok": True}, "zx_ci": {"lo": -0.1, "hi": 0.9, "n": 2000},
                          "zx_table": tab["W"], "candidate": bool(s1["ok"])} for f in fin}
    res["describe"] = {e: {"n": 30, **{f: tab["W"] for f in fin}} for e in T.N225_ERAS}
    md1 = T.report(res)
    assert "确认" in md1 and all(T.CAND[f] in md1 for f in fin)
    assert ".T" not in json.dumps(res, ensure_ascii=False, default=str) and ".T" not in md1


def test_bootstrap_bounds_check_and_u0_frame():
    rng = np.random.default_rng(0)
    net = rng.normal(0, 5, 120)
    months = np.array([f"2020-{m:02d}" for m in np.repeat(np.arange(1, 13), 10)])
    blocked = np.zeros(120, bool)
    blocked[::3] = True
    c1, c2 = T.boot_ci(net, blocked, months), T.boot_ci(net, blocked, months)
    assert c1 == c2 and c1["lo"] <= c1["hi"] and c1["n"] == T.BOOT_N
    comp = T.slot_competition(pd.DataFrame({"date": ["2024-01-05", "2024-01-05", "2024-01-09"], "ticker": ["a", "b", "c"]}))
    assert comp == {"days": 2, "days_ge2": 1, "signals_on_ge2": 2}
    # 界线核对：登记的 BOUNDS 为空 → 停；不同 → 停；相同 → 过
    tb = {"bounds": {"F01": [0.1, 0.2]}, "n": {"F01": 10}}
    saved = T.BOUNDS
    try:
        T.BOUNDS = {}
        with pytest.raises(SystemExit):
            T.check_bounds(tb)
        T.BOUNDS = {"F01": [0.1, 0.3]}
        with pytest.raises(SystemExit):
            T.check_bounds(tb)
        T.BOUNDS = {"F01": [0.1, 0.2]}
        T.check_bounds(tb)
    finally:
        T.BOUNDS = saved
    # U0：不在时点名单上的日子 fwd = NaN（样本里不算），特征照算
    n = 300
    days = pd.bdate_range("2017-01-04", periods=n)
    c = 1000 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    listed = np.ones((n, 1), bool)
    listed[:100, 0] = False
    A = {"days": days, "names": ["1.T"], "O": c[:, None], "H": c[:, None] * 1.01, "L": c[:, None] * 0.99, "C": c[:, None], "listed": listed}
    df = T.u0_frame(A, 0)
    _, f = T._u0_job(("1.T", df))
    assert f["fwd"].iloc[:100].isna().all() and f["fwd"].iloc[100:200].notna().all()
    assert f[T.COLS].notna().any().any()
