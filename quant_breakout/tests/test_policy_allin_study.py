"""scripts/policy_allin_study.py（2026-10-06 登记）：业种分类、12-1 个月动量与业种前 3、政策窗口（信号日前 1〜365 天）、
与主线篮子的相关（不含自己）与当天百分位、em_tick 与安慰剂、判定 a〜d。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import policy_allin_study as PA  # noqa: E402


def test_registered_constants():
    assert PA.IDS == ("A1", "A2", "A3", "A4", "A5") and PA.REL == {"A1": "M", "A2": "P", "A3": "MP", "A4": "R", "A5": "MorP"}
    assert PA.OTHERS_F == {"A1": 0.25, "A2": 0.25, "A3": 0.25, "A4": 0.25, "A5": 0.0}
    assert (PA.TOP_IND, PA.MIN_MEMBERS, PA.MOM_FAR, PA.MOM_NEAR, PA.POLICY_DAYS) == (7, 3, 252, 21, 365)
    assert (PA.CORR_N, PA.CORR_MIN, PA.CORR_TOP) == (250, 200, 0.90) and PA.CFG_FREE == {"position_pct": 1.0, "max_position_pct": 1.0}
    assert (PA.CAL_UP, PA.DD_TOL, PA.Z_TOL, PA.MIN_TRADES, PA.MIN_ALLIN, PA.POOL_MIN, PA.ACTIVE_MIN) == (0.02, 2.0, 0.02, 20, 5, 10, 10)
    assert PA.FP == "1241753c8f2529c6" and PA.PLACEBO == {"Z": 100, "E": 200, "J": 200} and PA.JX_FROM == "2022-01-01"


def test_s33_map_latest_snapshot_wins(tmp_path):
    pd.DataFrame({"Code": ["72030", "13010", "13060", "94320"], "S33Nm": ["輸送用機器", "水産・農林業", "その他", "情報\uff65通信業"]}).to_csv(
        tmp_path / "2016-10-31.csv", index=False)
    pd.DataFrame({"Code": ["72030"], "S33Nm": ["電気機器"]}).to_csv(tmp_path / "2016-11-30.csv", index=False)
    m = PA.s33_map(tmp_path)
    assert m == {"7203.T": "電気機器", "1301.T": "水産・農林業", "9432.T": "情報・通信業"}   # ETF 的「その他」不算；后面的快照覆盖前面的；中点统一
    assert PA.norm_s33("電気\uff65ガス業 ") == "電気・ガス業"


def test_policy_table_focus_and_names():
    t = PA.load_policy(ROOT / "var" / PA.POLICY_FILE)
    w = PA.load_policy(ROOT / "var" / PA.POLICY_FILE, focus_only=False)
    assert len(w) == 48 and len(t) == 22 and t["date"].is_monotonic_increasing
    master = {"電気機器", "情報・通信業", "機械", "輸送用機器", "電気・ガス業", "医薬品", "精密機器", "化学", "非鉄金属", "鉱業", "建設業", "食料品",
              "水産・農林業", "サービス業", "鉄鋼", "パルプ・紙", "ガラス・土石製品", "倉庫・運輸関連業"}
    assert {x for lst in w["s33_list"] for x in lst} <= master                       # 都是东证 33 业种的名字（统一成全角中点）
    assert all(len(lst) for lst in t["s33_list"]) and set(t["date"].dt.year) >= {2001, 2015, 2021, 2025, 2026}


def test_momentum_scores_and_top3():
    days = pd.bdate_range("2020-01-01", periods=300)
    n = len(days)
    rates = {"A1.T": 0.002, "A2.T": 0.002, "A3.T": 0.002, "B1.T": 0.001, "B2.T": 0.001, "B3.T": 0.001,
             "C1.T": -0.001, "C2.T": -0.001, "C3.T": -0.001, "D1.T": 0.003, "D2.T": 0.003}
    C = pd.DataFrame({t: 100 * np.exp(r * np.arange(n)) for t, r in rates.items()}, index=days)
    ind = {t: t[0] for t in rates}
    R = PA.mom_12_1(C)
    assert np.isnan(R.iloc[251]).all() and np.isfinite(R.iloc[252]).all()
    assert abs(R.iloc[-1]["A1.T"] - (np.exp(0.002 * (252 - 21)) - 1)) < 1e-9
    sc = PA.industry_scores(R, ind)
    assert list(sc.columns) == ["A", "B", "C", "D"] and sc["D"].isna().all()           # D 只有 2 只 → 不算
    top = PA.top_industries(sc)
    assert top.iloc[-1] == frozenset({"A", "B", "C"}) and top.iloc[0] == frozenset()
    mem = pd.DataFrame(True, index=days, columns=C.columns)
    mem.loc[:, "A3.T"] = False                                                         # 成员只剩 2 只 → A 不算
    sc2 = PA.industry_scores(R, ind, mem)
    assert sc2["A"].isna().all() and PA.top_industries(sc2).iloc[-1] == frozenset({"B", "C"})


def test_policy_window_excludes_signal_day():
    tb = pd.DataFrame({"date": ["2024-01-10", "2023-01-01"], "s33": ["電気機器;機械", "医薬品"]}).assign(
        date=lambda x: pd.to_datetime(x["date"]))
    tb["s33_list"] = [s.split(";") for s in tb["s33"]]
    assert not PA.policy_active(tb, "電気機器", "2024-01-10")                         # 当天不算
    assert PA.policy_active(tb, "機械", "2024-01-11")
    assert PA.policy_active(tb, "電気機器", pd.Timestamp("2024-01-10") + pd.Timedelta(days=365))
    assert not PA.policy_active(tb, "電気機器", pd.Timestamp("2024-01-10") + pd.Timedelta(days=366))
    assert not PA.policy_active(tb, None, "2024-02-01") and not PA.policy_active(tb, "医薬品", "2024-02-01")
    assert PA.policy_industries(tb, "2024-02-01") == ["機械", "電気機器"]


def test_corr_pct_excludes_self_and_ranks():
    rng = np.random.default_rng(0)
    days = pd.bdate_range("2020-01-01", periods=260)
    f = rng.normal(0, 0.01, len(days))
    Rd = pd.DataFrame({"B1.T": f + rng.normal(0, 0.002, len(days)), "B2.T": f + rng.normal(0, 0.002, len(days)),
                       "X.T": f + rng.normal(0, 0.004, len(days)), "Y.T": rng.normal(0, 0.01, len(days)),
                       "Z.T": -f + rng.normal(0, 0.004, len(days))}, index=days)
    p = PA.corr_pct(Rd, days[-1], ["B1.T", "B2.T"], ["B1.T", "X.T", "Y.T", "Z.T"])
    assert p["Z.T"] == 0.25 and p["Y.T"] == 0.5 and set(p[["B1.T", "X.T"]]) == {0.75, 1.0}
    one = PA.corr_pct(Rd, days[-1], ["B1.T"], ["B1.T", "X.T"])                          # 篮子只有自己 → 不含自己之后没有篮子
    assert np.isnan(one["B1.T"]) and one["X.T"] == 1.0
    short = PA.corr_pct(Rd.iloc[:150], days[149], ["B1.T", "B2.T"], ["X.T", "Y.T"])     # 不满 200 天 → 不算
    assert short.isna().all()
    g = rng.normal(0, 0.01, len(days))                                                 # 不含自己：N 与篮子里另一只 G 无关 → 排在 Q（与 G 相关约 0.3）后面
    R2 = pd.DataFrame({"N.T": rng.normal(0, 0.01, len(days)), "G.T": g, "Q.T": 0.3 * g + rng.normal(0, 0.0095, len(days))}, index=days)
    q = PA.corr_pct(R2, days[-1], ["N.T", "G.T"], ["N.T", "Q.T"])
    assert q["N.T"] == 0.5 and q["Q.T"] == 1.0                                         # 含自己的话 N 与篮子相关约 0.7，会排第一


def test_flag_rows_em_and_placebo():
    days = pd.bdate_range("2024-01-01", periods=5)
    top = pd.Series([frozenset({"電気機器"})] * 5, index=days)
    tb = pd.DataFrame({"date": [pd.Timestamp("2023-12-01")], "s33": ["機械"]})
    tb["s33_list"] = [["機械"]]
    ind = {"A.T": "電気機器", "B.T": "機械", "C.T": "医薬品"}
    fl = PA.flag_rows(["A.T", "B.T", "C.T", "D.T"], [days[1]] * 4, ind, top, tb, lambda t, d: {"C.T": 0.95}.get(t, 0.5))
    assert fl["M"].tolist() == [True, False, False, False] and fl["P"].tolist() == [False, True, False, False]
    assert fl["R"].tolist() == [False, False, True, False] and fl["MorP"].tolist() == [True, True, False, False] and not fl["MP"].any()
    S = pd.DataFrame({"ticker": ["A.T", "B.T", "C.T", "D.T"], "date": [days[1]] * 4})
    em = PA.em_for(S, np.array([False, False, True, False]), fl["MorP"].to_numpy(), 0.25)
    assert em == {("A.T", days[1]): 1.0, ("B.T", days[1]): 1.0, ("C.T", days[1]): 0.0, ("D.T", days[1]): 0.25}
    assert PA.em_for(S, np.zeros(4, bool), np.zeros(4, bool), 0.0)[("D.T", days[1])] == 0.0
    rng = np.random.default_rng(1)
    tbf = np.array([True, False, False, False, True, False])
    for _ in range(20):
        p = PA.placebo_rel(tbf, 2, rng)
        assert p.sum() == 2 and not (p & tbf).any()
    assert PA.placebo_rel(tbf, 10, rng).sum() == 4 and PA.placebo_rel(tbf, 0, rng).sum() == 0


def test_judge_and_group_stats():
    base = {"Z": {"calmar": 1.2, "dd": -14.0, "cagr": 16.0, "n": 28}, "E": {"calmar": 0.627, "dd": -23.0, "cagr": 14.5, "n": 34},
            "J": {"calmar": 0.677, "dd": -29.6, "cagr": 20.0, "n": 52}}
    good = {"Z": {"calmar": 1.19, "dd": -14.0, "cagr": 16.0, "n": 28}, "E": {"calmar": 0.66, "dd": -24.0, "cagr": 17.0, "n": 30},
            "J": {"calmar": 0.70, "dd": -30.0, "cagr": 23.0, "n": 50}}
    pools = {"W": {"n_rel": 20, "n_not": 100, "diff": 0.5}, "Jx": {"n_rel": 15, "n_not": 90, "diff": 0.1}}
    pl = {"E": 0.65, "J": 0.69}
    allin = {"E": 6, "J": 9}
    both = {"Z": False, "E": True, "J": True}
    j = PA.judge(good, base, pl, allin, pools, both)
    assert j["ok"] and abs(j["gain"] - 0.023) < 1e-9 and j["active"] == ["E", "J"]
    assert not PA.judge(good, base, {"E": 0.67, "J": 0.69}, allin, pools, both)["ok"]                       # b：E 不比安慰剂好
    assert not PA.judge(good, base, pl, {"E": 4, "J": 9}, pools, both)["ok"]                                  # c：全仓太少
    assert not PA.judge(good, base, pl, allin, {**pools, "Jx": {"n_rel": 15, "n_not": 90, "diff": -0.1}}, both)["ok"]   # d
    assert not PA.judge(good, base, pl, allin, {**pools, "W": {"n_rel": 9, "n_not": 90, "diff": 1.0}}, both)["ok"]       # d：样本不够
    deep = {**good, "J": {**good["J"], "dd": -32.0}}
    assert any(s.startswith("a J 回撤") for s in PA.judge(deep, base, pl, allin, pools, both)["fails"])
    zbad = {**good, "Z": {**good["Z"], "calmar": 1.17}}
    assert any(s.startswith("a Z") for s in PA.judge(zbad, base, pl, allin, pools, both)["fails"])
    j_only = {"Z": False, "E": False, "J": True}                                                             # 只有 J 能检验：E 只要求不差、W 不看
    flat_e = {**good, "E": {**base["E"]}}
    jj = PA.judge(flat_e, base, {"J": 0.69}, {"J": 9}, {"Jx": pools["Jx"]}, j_only)
    assert jj["ok"] and jj["active"] == ["J"] and abs(jj["gain"] - 0.023) < 1e-9
    worse_e = {**good, "E": {**base["E"], "calmar": 0.60}}
    assert not PA.judge(worse_e, base, {"J": 0.69}, {"J": 9}, {"Jx": pools["Jx"]}, j_only)["ok"]
    none = PA.judge(good, base, pl, allin, pools, {"Z": True, "E": False, "J": False})
    assert not none["ok"] and "无法检验" in none["fails"][0]
    assert PA.ret_reading({**good, "E": {**good["E"], "cagr": 16.0}}, base)["ok"] is False and PA.ret_reading(
        {**good, "E": {**good["E"], "cagr": 16.6}, "J": {**good["J"], "cagr": 22.1}}, base)["ok"]
    g = PA.group_stats(np.array([1.0, -1.0, 2.0, np.nan, 3.0]), np.array([True, True, False, True, False]))
    assert g == {"n_rel": 2, "n_not": 2, "win_rel": 50.0, "win_not": 100.0, "mean_rel": 0.0, "mean_not": 2.5, "diff": -2.5}
