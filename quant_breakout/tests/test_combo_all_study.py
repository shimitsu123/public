"""全部研究的关联搭配（scripts/combo_all_common.py / combo_all_study.py）：特征清单、留一年代的四种搭配、两两格子、随机对照、判定、样本与账户掩码。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import combo_all_common as CA                                                # noqa: E402
import combo_all_study as CS                                                 # noqa: E402


def _era(n=600, seed=0, beta=1.0, noise=1.0):
    """f1 与 net 正相关（beta）、f2 纯噪声、f3 与 net 负相关；其余特征 = 噪声。"""
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, len(CA.FEATS))), columns=CA.FEATS)
    z = rng.normal(size=n)
    X["vr1"] = z + rng.normal(scale=0.5, size=n)
    X["dist"] = -z + rng.normal(scale=0.5, size=n)
    X["net"] = beta * z + rng.normal(scale=noise, size=n)
    X["ticker"] = [f"{1000 + i % 50}.T" for i in range(n)]
    X["week"] = [f"2020-W{i % 30}" for i in range(n)]
    X["n225_ma200"] = rng.normal(size=n)
    X["vix"] = rng.uniform(10, 30, n)
    return X


# ───────────────────────── 清单 ─────────────────────────
def test_feature_list():
    assert len(CA.FEATS) == 53 and len(set(CA.FEATS)) == 53
    fam = [v[0] for v in CA.FEATURES.values()]
    assert {f: fam.count(f) for f in "ABCDEF"} == {"A": 7, "B": 13, "C": 10, "D": 6, "E": 7, "F": 10}
    assert all(CA.FEATURES[f][0] != "F" for f in CA.STOCK_FEATS) and len(CA.STOCK_FEATS) == 43
    assert set(CA.P_RULES) == {"K2", "USW", "X2", "V3", "Q2", "Q3", "Q5"}
    assert set(CA.VARIANTS) == {"V", "C", "R", "P"} and CA.ERAS == ("Z", "E", "J") and CA.OTHER == {"W": "E", "Jx": "J"}


# ───────────────────────── V ─────────────────────────
def test_select_needs_same_sign_and_size():
    a, b = _era(seed=1), _era(seed=2)
    sel = CA.select([a, b], ["vr1", "dist", "r20"], 0.03)
    assert sel.get("vr1") == 1 and sel.get("dist") == -1 and "r20" not in sel
    c = _era(seed=3, beta=-1.0)                                              # 另一个年代方向反了 → 不选
    assert "vr1" not in CA.select([a, c], ["vr1"], 0.03)
    assert CA.select([a, b], ["vr1"], 0.99) == {}                            # 门槛太高 → 不选


def test_score_votes_and_missing():
    X = pd.DataFrame({"f": [0.0, 1.0, 2.0, np.nan], "g": [5.0, 5.0, 5.0, 5.0]})
    cut = {"f": (0.5, 1.5), "g": (5.0, 5.0)}
    assert CA.score(X, {"f": 1}, cut).tolist() == [-1.0, 0.0, 1.0, 0.0]
    assert CA.score(X, {"f": -1}, cut).tolist() == [1.0, 0.0, -1.0, 0.0]
    assert CA.score(X, {"g": 1}, cut).tolist() == [0.0, 0.0, 0.0, 0.0]       # 切点相同 → 不投票
    assert CA.score(X, {"f": 1, "g": 1}, cut).tolist() == [-1.0, 0.0, 1.0, 0.0]


def test_threshold_and_keep():
    sc = np.array([-2, -1, 0, 0, 1, 2], float)
    thr = CA.threshold(sc)
    assert thr == pytest.approx(np.quantile(sc, 1 / 3))
    k = CA.keep_by(sc, thr)
    assert k.tolist() == [False, False, True, True, True, True]
    assert CA.keep_by(sc, np.nan).all()


def test_fit_apply_v_out_of_era():
    a, b, c = _era(seed=4), _era(seed=5), _era(seed=6)
    rule = CA.fit_v([a, b])
    assert rule["sel"].get("vr1") == 1 and rule["sel"].get("dist") == -1
    keep = CA.apply_v(rule, c)
    d = CA.delta(c["net"].to_numpy(), keep)
    assert 0.5 < d["frac"] < 0.8 and d["dmean"] > 0.2 and d["dwin"] > 2


# ───────────────────────── C ─────────────────────────
def test_cell_of():
    X = pd.DataFrame({"n225_ma200": [-0.1, -0.1, 0.1, 0.1, np.nan], "vix": [15, 25, 15, 25, 20]})
    assert CA.cell_of(X).tolist() == [0, 1, 2, 3, -1]


def test_fit_c_small_cells_untouched():
    a, b = _era(seed=7), _era(seed=8)
    a["vix"], b["vix"] = 15.0, 15.0                                          # VIX ≥ 20 的格子没有样本
    rules = CA.fit_c([a, b])
    assert rules[1] is None and rules[3] is None and rules[0] is not None and rules[2] is not None
    c = _era(seed=9)
    keep = CA.apply_c(rules, c)
    cell = CA.cell_of(c)
    assert keep[np.isin(cell, [1, 3])].all()                                 # 没有规则的格子全部保留
    assert not keep[np.isin(cell, [0, 2])].all()


# ───────────────────────── R ─────────────────────────
def _bad_cell(seed, bad=True):
    rng = np.random.default_rng(seed)
    n = 800
    X = pd.DataFrame(rng.normal(size=(n, len(CA.FEATS))), columns=CA.FEATS)
    X["net"] = rng.normal(1.0, 1.0, n)
    if bad:
        m = (X["vr1"] >= 0) & (X["dist"] < 0)
        X.loc[m, "net"] = rng.normal(-3.0, 1.0, int(m.sum()))
    return X


def test_fit_r_finds_consistently_bad_cell():
    rule = CA.fit_r([_bad_cell(1), _bad_cell(2)], feats=["vr1", "dist", "r20"])
    assert rule is not None and {rule["f"], rule["g"]} == {"vr1", "dist"}
    hi = {rule["f"]: rule["f_hi"], rule["g"]: rule["g_hi"]}
    assert hi == {"vr1": True, "dist": False}
    T = _bad_cell(3)
    keep = CA.apply_r(rule, T)
    m = (T["vr1"] >= rule["med_f" if rule["f"] == "vr1" else "med_g"]) & (T["dist"] < rule["med_g" if rule["g"] == "dist" else "med_f"])
    assert not keep[m.to_numpy()].any() and keep[~m.to_numpy()].all()


def test_fit_r_none_when_nothing_bad():
    assert CA.fit_r([_bad_cell(4, bad=False), _bad_cell(5, bad=False)], feats=["vr1", "dist", "r20"]) is None
    assert CA.apply_r(None, _bad_cell(6)).all()


def test_pair_consistency_counts():
    sets = [_bad_cell(s) for s in (7, 8, 9)]
    pc = CA.pair_consistency(sets, feats=["vr1", "dist"])
    assert pc["cells"] == 4 and pc["all_down"] >= 1 and pc["all_up"] >= 1   # 坏格 + 与它互补、因此更好的格


# ───────────────────────── P ─────────────────────────
def test_p_flags_and_threshold():
    X = pd.DataFrame({"vr1": [3.5, 2.5, 1.0, np.nan], "b_n225": [0.5, 0.9, 0.5, 0.5], "us12": [0.2, 0.5, np.nan, 0.1],
                      "x2": [1.0, -1.0, np.nan, 0.0], "follow": [0.01, -0.01, 0.0, np.nan], "downrel": [0.0, -0.1, 0.1, np.nan],
                      "touch": [2, 1, 3, np.nan]})
    F = CA.p_flags(X)
    assert F.loc[0].to_dict() == {"K2": 1, "USW": 1, "X2": 1, "V3": 1, "Q2": 1, "Q3": 1, "Q5": 1}
    assert F.loc[1].to_dict() == {"K2": 0, "USW": 0, "X2": 0, "V3": 0, "Q2": 0, "Q3": 0, "Q5": 0}
    assert CA.p_score(X).tolist() == [7.0, 0.0, 3.0, 1.0]
    rule = CA.fit_p([X, X])
    assert CA.apply_p(rule, X).tolist() == (CA.p_score(X) >= rule["thr"]).tolist()


# ───────────────────────── 随机对照 ─────────────────────────
def test_lottery_keeps_ticker_week_together():
    rng = np.random.default_rng(0)
    tk = np.array(["A", "A", "B", "B", "A"])
    wk = np.array(["w1", "w1", "w1", "w2", "w2"])
    for _ in range(20):
        k = CA.lottery(tk, wk, 0.5, rng)
        assert k[0] == k[1]
    k = CA.lottery(np.repeat(np.arange(2000).astype(str), 2), np.repeat(["w"], 4000), 0.3, rng)
    assert 0.25 < k.mean() < 0.35


def test_pooled_placebo_finite():
    rng = np.random.default_rng(1)
    parts = [(rng.normal(size=300), np.repeat(np.arange(60).astype(str), 5), np.tile(np.arange(5).astype(str), 60), 0.6) for _ in range(3)]
    pl = CA.pooled_placebo(parts, n=50)
    assert np.isfinite(pl["dmean_q95"]) and np.isfinite(pl["dwin_q95"]) and pl["dmean_q95"] > 0


# ───────────────────────── 判定 ─────────────────────────
def _st(dw, dm, frac=0.7):
    return {"dwin": dw, "dmean": dm, "frac": frac}


def test_decisions():
    good = {e: _st(1.0, 0.1) for e in ("Z", "E", "J", "W", "Jx")}
    assert CA.d1(good) and CA.d3(good)
    bad = dict(good, E=_st(-0.1, 0.5))
    assert not CA.d1(bad)
    assert not CA.d3(dict(good, Jx=_st(0.5, -0.01)))
    pl = {"dmean_q95": 0.25}
    assert CA.d2(_st(2.0, 0.30), pl) and not CA.d2(_st(1.9, 0.30), pl) and not CA.d2(_st(2.5, 0.2), pl)
    assert not CA.d2(_st(2.5, 0.19), {"dmean_q95": 0.0})
    base = {e: {"calmar": 0.30, "dd": -25.0} for e in CA.ERAS}
    acct = {"Z": {"calmar": 0.31, "dd": -26.0}, "E": {"calmar": 0.30, "dd": -25.0}, "J": {"calmar": 0.33, "dd": -24.0}}
    assert CA.d4a(acct, base) and CA.calmar_sum(acct, base) == pytest.approx(0.04)
    assert not CA.d4a(dict(acct, E={"calmar": 0.27, "dd": -25.0}), base)    # 一个年代低 0.03
    assert not CA.d4a(dict(acct, Z={"calmar": 0.31, "dd": -27.5}), base)    # 回撤深 2.5 pp
    assert not CA.d4a(dict(acct, J={"calmar": 0.31, "dd": -24.0}), base)    # 合计只 +0.02
    assert CA.verdict(True, True, True, True, True) == "通过"
    assert CA.verdict(True, True, False, True, False) == "方向一致"
    assert CA.verdict(True, False, True, True, True) == "不通过"


# ───────────────────────── 样本、账户掩码、β、单笔 ─────────────────────────
def _fa():
    idx = pd.bdate_range("2016-12-01", periods=60)
    e = np.zeros(60, bool)
    e[[5, 30, 45]] = True
    return {"1111.T": pd.DataFrame({"entry": e, "Open": 1.0}, index=idx), "2222.T": pd.DataFrame({"entry": e, "Open": 1.0}, index=idx)}


def test_signals_window_keep_member_exclude():
    fa = _fa()
    keep = {t: np.ones(60, bool) for t in fa}
    keep["1111.T"][30] = False
    mem = {"2222.T": np.r_[np.zeros(40, bool), np.ones(20, bool)]}
    S = CS.signals(fa, keep, mem, "2017-01-01", "2017-12-31")
    got = sorted((t, d.strftime("%m-%d")) for t, d in zip(S["ticker"], S["date"]))
    d30, d45 = fa["1111.T"].index[30].strftime("%m-%d"), fa["1111.T"].index[45].strftime("%m-%d")
    assert got == sorted([("1111.T", d45), ("2222.T", d45)]) and d30 not in [x[1] for x in got]   # 30 = W2 挡掉 / 不是成员
    assert fa["1111.T"].index[5] < pd.Timestamp("2017-01-01")                 # 窗口外的不算
    S2 = CS.signals(fa, keep, mem, "2016-01-01", "2017-12-31", exclude={"2222.T"})
    assert set(S2["ticker"]) == {"1111.T"} and len(S2) == 2


def test_account_masks_skip_only_skipped_signals():
    fa = _fa()
    A = pd.DataFrame({"ticker": ["1111.T", "2222.T"], "date": [fa["1111.T"].index[30], fa["2222.T"].index[45]]})
    m = CS.account_masks(fa, A, np.array([False, True]))
    assert (~m["1111.T"]).sum() == 1 and not m["1111.T"][30] and m["2222.T"].all()


def test_beta2_slope():
    idx = pd.date_range("2018-01-05", periods=150, freq="W-FRI")
    rng = np.random.default_rng(3)
    X = pd.DataFrame({"n225": rng.normal(0, 0.02, 150), "fx": rng.normal(0, 0.01, 150)}, index=idx)
    y = 0.8 * X["n225"] + 1.5 * X["fx"] + rng.normal(0, 0.001, 150)
    asof = idx[-1] + pd.Timedelta(days=3)
    assert CS._beta2(y, X, "n225", asof) == pytest.approx(0.8, abs=0.3)
    assert CS._beta2(y, X, "fx", asof) == pytest.approx(1.5, abs=0.05)
    assert np.isnan(CS._beta2(y.iloc[:50], X, "fx", asof))                    # 周数不够


def test_outcomes_uses_x6_rerun_and_drops_open(monkeypatch):
    from qbreak import exit_forward as XF
    idx = pd.bdate_range("2020-01-01", periods=120)
    df = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "atr": 1.0, "entry": False, "dead_cross": False}, index=idx)
    fa = {"1111.T": df, "2222.T": df}
    calls = []

    def fake_one(t, f, p, bt, start, end):
        x6 = bool(f["dead_cross"].any())
        calls.append((t, x6))
        if t == "2222.T":
            return {"reason": "end", "entry_date": idx[11], "ret_pct": 1.0, "hold_days": 3}
        return {"reason": "stop", "entry_date": idx[11], "ret_pct": 5.0 if x6 else 2.0, "hold_days": 7 if x6 else 4}

    monkeypatch.setattr(XF, "_one", fake_one)
    monkeypatch.setattr(XF, "chandelier_flags", lambda f, k, px: np.r_[np.zeros(len(f) - 1, bool), True])

    class _Ex:
        slippage_pct = 0.1

    class _Bt:
        exec_cfg = _Ex()

    S = pd.DataFrame({"ticker": ["1111.T", "2222.T"], "date": [idx[10], idx[10]]})
    out = CS.outcomes(S, fa, None, _Bt(), 0.5)
    assert len(out) == 1 and out.loc[0, "ticker"] == "1111.T"
    assert out.loc[0, "net"] == pytest.approx(4.5) and out.loc[0, "net_dc"] == pytest.approx(1.5) and out.loc[0, "hold"] == 7
    assert ("1111.T", True) in calls and ("1111.T", False) in calls


def test_rule_text_all_variants():
    assert "vr1+" in CS.rule_text("V", {"sel": {"vr1": 1, "dist": -1}})
    assert "不动" in CS.rule_text("V", {"sel": {}})
    assert "样本不够" in CS.rule_text("C", {0: None, 1: {"sel": {"vr1": 1}}, 2: {"sel": {}}, 3: None})
    assert "不动" in CS.rule_text("R", None)
    r = {"f": "vr1", "g": "dist", "f_hi": True, "g_hi": False, "med_f": 1.2, "med_g": 3.0, "dmean": -1.0, "dwin": -5.0}
    assert "跳过 vr1 高" in CS.rule_text("R", r) and "dist 低" in CS.rule_text("R", r)
    assert "< 1" in CS.rule_text("P", {"thr": 1.0})
