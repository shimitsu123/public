"""第四个研究循环第 4 轮 XSM（scripts/loop4_r04_xsmodel.py，2026-10-03 登记）：登记值与第四个循环的规则、核心同期与 xs、
fit_c_y(…, "net") 与 fit_c 逐项相同、逐年前推的学习集（离场日 < y 年 1 月 1 日 − 120 天、去重）、按年学按年用、掩码、S5 的集合差、接线与命令行。"""
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import combo_all_common as CA  # noqa: E402
import loop4_r04_xsmodel as T  # noqa: E402
import research_loop4 as R4  # noqa: E402


def test_registered_constants_and_loop4_rules():
    assert (T.ROUND, T.IDS, T.POSTHOC, T.KIND, T.CORE, T.FWD_LAG_DAYS) == (4, ("XSM",), False, "stock", "1545.T", 120)
    assert T.FAMILY == {"XSM": "选股·学习目标"} and all(f.startswith(R4.FAMILY_PREFIX) for f in T.FAMILY.values())
    assert not set(T.IDS) & R4.previous_ids(ROOT / "var")
    st = R4.load_state(ROOT / "var")
    mine = [r for r in st.get("rounds") or [] if r.get("round") == T.ROUND]
    if mine:
        assert [a["id"] for a in mine[0]["approaches"]] == list(T.IDS)
    else:
        R4.check_new_approaches(st, [{"id": k, "family": T.FAMILY[k], "posthoc": T.POSTHOC, "kind": T.KIND} for k in T.IDS], R4.previous_ids(ROOT / "var"))


def test_with_xs_exit_and_excess_keep_other_columns():
    days = pd.bdate_range("2024-01-01", periods=30)
    core = pd.Series(np.linspace(100, 129, 30), index=days)
    P = pd.DataFrame({"ticker": ["A.T", "B.T"], "date": [days[0], days[25]], "net": [5.0, 2.0], "hold": [10, 10], "vexp": [1.1, 0.9]})
    X = T.with_xs(P, days, core)
    assert list(X["exit"]) == [days[10], days[29]] and list(X["vexp"]) == [1.1, 0.9]
    assert X["xs"].iloc[0] == pytest.approx(5.0 - 10.0) and X["xs"].iloc[1] == pytest.approx(2.0 - (129 / 125 - 1) * 100)
    late = pd.Series([100.0, 101.0], index=[days[5], days[6]])
    assert np.isnan(T.with_xs(P.iloc[:1], days, late)["xs"].iloc[0])     # 信号日之前没有核心收盘 → NaN


def _train(seed, n=480):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({f: rng.normal(size=n) for f in CA.STOCK_FEATS})
    X["n225_ma200"] = np.where(np.arange(n) % 2 == 0, 0.05, -0.05)
    X["vix"] = np.where(np.arange(n) % 4 < 2, 15.0, 25.0)
    X["net"] = 2.0 * X[CA.STOCK_FEATS[0]] - 1.5 * X[CA.STOCK_FEATS[1]] + rng.normal(size=n)
    X["xs"] = -2.0 * X[CA.STOCK_FEATS[2]] + rng.normal(size=n)
    return X


def test_fit_c_y_net_equals_fit_c_and_xs_differs():
    tr = [_train(1), _train(2)]
    a, b = CA.fit_c(tr), T.fit_c_y(tr, "net")
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    x = T.fit_c_y(tr, "xs")
    sel_x = {k: v["sel"] for k, v in x.items() if v}
    assert sel_x and all(CA.STOCK_FEATS[2] in s and s[CA.STOCK_FEATS[2]] == -1 for s in sel_x.values())
    t2 = [t.assign(xs=np.where(np.arange(len(t)) < 470, t["xs"], np.nan)) for t in tr]   # 目标缺值的行不用
    assert T.fit_c_y(t2, "xs")[0]["n"] == [len(t[(CA.cell_of(t) == 0) & np.isfinite(t["xs"])]) for t in t2]


def test_fwd_pool_cutoff_and_dedupe():
    P1 = pd.DataFrame({"ticker": ["A.T", "B.T", "C.T"], "date": pd.to_datetime(["2010-01-04", "2010-06-01", "2010-07-01"]),
                       "exit": pd.to_datetime(["2010-03-01", "2010-09-01", "2010-09-03"]), "net": [1.0, 2.0, 3.0]})
    P2 = pd.DataFrame({"ticker": ["A.T"], "date": pd.to_datetime(["2010-01-04"]), "exit": pd.to_datetime(["2010-05-01"]), "net": [9.0]})
    pool = T.fwd_pool([P1, P2], 2011)                                        # 截止 2011-01-01 − 120 天 = 2010-09-03（不含）
    assert sorted(pool["ticker"]) == ["A.T", "B.T"] and float(pool.loc[pool["ticker"] == "A.T", "net"].iloc[0]) == 1.0
    assert len(T.fwd_pool([P1], 2010)) == 0


def test_keep_fwd_learns_per_year_and_keeps_when_no_pool():
    tr = _train(3, n=960)
    tr["date"] = pd.Timestamp("2005-01-04")
    tr["exit"] = pd.Timestamp("2005-03-01")
    tr["ticker"] = [f"S{i}.T" for i in range(len(tr))]
    A = _train(4, n=40).assign(date=[pd.Timestamp("2005-06-01")] * 20 + [pd.Timestamp("2007-06-01")] * 20, ticker="Q.T")
    k = T.keep_fwd([tr], A, "net")
    assert k[:20].all()                                                      # 2005 年：学习集是空的（3 月离场 > 2004-09-03）→ 不动
    rule = T.fit_c_y([T.fwd_pool([tr], 2007)], "net")
    assert list(k[20:]) == list(CA.apply_c(rule, A.iloc[20:]))              # 2007 年：用 2006-09-03 之前离场的学


def test_masks_from_keep_turns_off_skipped_signal_days():
    idx = pd.bdate_range("2024-01-01", periods=5)
    fa = {"A.T": pd.DataFrame({"Close": range(5)}, index=idx), "B.T": pd.DataFrame({"Close": range(5)}, index=idx)}
    w2 = {"A.T": np.array([1, 1, 0, 1, 1], bool), "B.T": np.ones(5, bool)}
    A = pd.DataFrame({"ticker": ["A.T", "B.T", "A.T"], "date": [idx[1], idx[3], idx[4]]})
    m = T.masks_from_keep(fa, w2, A, np.array([False, True, False]))
    assert list(m["A.T"]) == [True, False, False, True, False] and m["B.T"].all() and w2["A.T"][1]   # 原掩码不被改


def test_set_delta():
    net = np.array([5.0, -1.0, 2.0, -3.0])
    d = T.set_delta(net, np.array([1, 1, 0, 1], bool), np.array([1, 0, 1, 0], bool))
    assert d["kept_c"] == 3 and d["kept_x"] == 2 and d["only_x"] == 1 and d["only_c"] == 2
    assert d["dmean"] == pytest.approx(3.5 - 1.0 / 3) and d["dwin"] == pytest.approx(100.0 - 100.0 / 3)
    assert np.isnan(T.set_delta(net, np.zeros(4, bool), np.ones(4, bool))["dwin"])


def test_wiring_and_cli():
    s1 = inspect.getsource(T.stage_one)
    assert "rb = L2.run(W, e)" in s1 and 'rc = L2.run(W, e, fr=frames(W, e, kp[e]["XSM"]))' in s1
    assert 'lenses={"loeo": (cand, base), "fwd": (fc, fb)}' in s1 and "posthoc=None" in s1
    w = inspect.getsource(T.wiring)
    assert 'fit_c_y(tr, "net")' in w and 'frames(W, "J", kp["J"]["C"])' in w and "sum(ndiff.values()) > 0" in w
    k = inspect.getsource(T.keeps)
    assert 'CA.apply_c(CA.fit_c([W["D"][x] for x in L2.ERAS if x != e]), A)' in k     # B1 的 C 同一个算法
    with pytest.raises(SystemExit):
        T.main(["--nope"])
