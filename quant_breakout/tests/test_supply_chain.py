"""跨行业上下游（qbreak/supply_chain.py、scripts/supply_chain_study.py）：产业连关表的读取、投入 / 销售份额与業種对照、
兄弟业种与运输的排除、物价的发布滞后、之后 h 个月的对齐、四种信号的计算、月度 IC 与三分组、信号日 → 月末的查找。"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak import supply_chain as SC

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import supply_chain_study as SCS                                               # noqa: E402

CODES = ["01", "06", "11", "15", "16", "20", "21", "22", "25", "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "39",
         "41", "46", "47", "48", "51", "53", "55", "57", "59", "61", "63", "64", "65", "66", "67", "68", "69"]


def _io(flows: dict, prod: dict | None = None) -> tuple[pd.DataFrame, pd.Series]:
    x = pd.DataFrame(0.0, index=CODES, columns=CODES)
    for (i, j), v in flows.items():
        x.loc[i, j] = v
    X = pd.Series(1000.0, index=CODES)
    for k, v in (prod or {}).items():
        X[k] = v
    return x, X


@pytest.mark.parametrize("numeric", [False, True])
def test_read_io_layout(tmp_path, numeric):
    x0, X0 = _io({("21", "20"): 100.0, ("20", "22"): 300.0, ("32", "35"): 7.5}, {"20": 1200.0})
    n = len(CODES)
    cd = (lambda c: int(c)) if numeric else (lambda c: c)                        # 表里是文字「01」；数字的代码也要能读
    g = pd.DataFrame(np.nan, index=range(3 + n + 1), columns=range(2 + n + 2), dtype=object)
    g.iloc[0, 0] = "令和２年(2020年)産業連関表 取引基本表"
    for k, c in enumerate(CODES):
        g.iloc[1, 2 + k], g.iloc[2, 2 + k] = cd(c), f"部門{c}"
        g.iloc[3 + k, 0], g.iloc[3 + k, 1] = cd(c), f"部門{c}"
        for m, d in enumerate(CODES):
            g.iloc[3 + k, 2 + m] = x0.loc[c, d]
    g.iloc[1, 2 + n], g.iloc[1, 2 + n + 1] = cd("70"), cd("97")                  # 最终需求的一列、国内生产额（97）
    if not numeric:
        g.iloc[2, 2 + n], g.iloc[2, 2 + n + 1] = "消費", "国内生産額"            # 没有名称的一列会被读成数字（97.0）
    for k, c in enumerate(CODES):
        g.iloc[3 + k, 2 + n], g.iloc[3 + k, 2 + n + 1] = 5.0, X0[c]
    g.iloc[3 + n, 0] = "97"
    f = tmp_path / "io.xlsx"
    g.to_excel(f, header=False, index=False)
    x, X = SC.read_io(f)
    assert list(x.index) == CODES and list(x.columns) == CODES
    assert x.loc["21", "20"] == 100.0 and x.loc["20", "22"] == 300.0 and x.loc["32", "35"] == 7.5
    assert X["20"] == 1200.0 and X["01"] == 1000.0


def test_tse_links_shares_siblings_partner_and_semi():
    flows = {("21", "20"): 100.0, ("57", "20"): 50.0, ("20", "20"): 200.0, ("51", "20"): 60.0,     # 化学的投入
             ("20", "22"): 300.0, ("20", "35"): 100.0, ("20", "57"): 100.0,                     # 化学的销售
             ("26", "29"): 100.0, ("26", "30"): 300.0,                                           # 機械 = 29 + 30
             ("20", "32"): 50.0, ("32", "35"): 100.0}
    x, X = _io(flows, {"29": 1000.0, "30": 3000.0, "32": 500.0})
    inds = ["化学", "医薬品", "石油・石炭製品", "ゴム製品", "輸送用機器", "海運業", "卸売業", "小売業", "機械", "鉄鋼", "電気機器", SC.SEMI]
    L = SC.tse_links(x, X, inds, {SC.SEMI: SC.SEMI_IO})
    ins = L["ins"]["化学"]
    assert ins["21"] == pytest.approx(0.10) and ins["57"] == pytest.approx(0.05) and ins["20"] == pytest.approx(0.20)
    sup = L["sup"]["化学"]                                                             # 石油 0.10、卸売 / 小売 各 0.03 → 归一
    assert sup == pytest.approx({"石油・石炭製品": 0.625, "卸売業": 0.1875, "小売業": 0.1875})
    assert "医薬品" not in sup and "化学" not in sup and "海運業" not in sup                 # 兄弟业种、自己、运输都不算
    assert L["sup"]["医薬品"] == pytest.approx(sup)                                       # 共用 20 部门 → 同样的上游
    assert L["cus"]["化学"] == pytest.approx({"ゴム製品": 300 / 450, "輸送用機器": 100 / 450, "電気機器": 50 / 450})  # 卖给运输的不算
    assert L["ins"]["機械"]["26"] == pytest.approx(400 / 4000)                            # 两个部门合并
    assert L["tse_io"]["機械"] == ["29", "30"]
    assert L["ins"][SC.SEMI] == pytest.approx({"20": 0.1}) and L["sup"][SC.SEMI] == {} and L["cus"][SC.SEMI] == {}
    assert "電気機器" in L["sup"]["輸送用機器"]
    assert all(SC.SEMI not in L[k][j] for k in ("sup", "cus") for j in L[k])             # 半导体组不当别人的上下游
    for k in ("sup", "cus"):
        for j, d in L[k].items():
            assert not d or sum(d.values()) == pytest.approx(1.0)


def test_committed_links_file_matches_rules():
    L = json.loads((ROOT / "var" / "io_links_2020.json").read_text(encoding="utf-8"))
    inds = set(json.loads((ROOT / "var" / "industry_s33.json").read_text(encoding="utf-8"))["s33"].values())
    assert inds <= set(L["ins"]) and SC.SEMI in L["ins"]
    for j in inds:
        assert L["tse_io"][j] == [io for io, ts in SC.IO_TSE.items() if j in ts]
        for k in ("sup", "cus"):
            d = L[k][j]
            assert sum(d.values()) == pytest.approx(1.0, abs=1e-4)
            assert "海運業" not in d and SC.SEMI not in d
            assert not set(L["tse_io"][j]) & {io for u in d for io in L["tse_io"][u]}      # 不含自己与共用部门的业种
    assert L["sup"][SC.SEMI] == {} and L["cus"][SC.SEMI] == {}
    goods = sum(v for i, v in L["ins"]["輸送用機器"].items() if i in SC.CGPI)
    assert 0.5 < goods < 0.8                                                             # 结构检查：输送机械大半是商品投入


def test_monthly_past_and_ahead_alignment():
    idx = pd.to_datetime(["2020-01-06", "2020-01-31", "2020-02-03", "2020-03-02"])
    M = SC.monthly(pd.DataFrame({"a": [1.0, 2.0, 3.0, np.nan]}, index=idx))
    assert list(M.index) == list(pd.to_datetime(["2020-01-31", "2020-02-29", "2020-03-31"]))
    assert M["a"].iloc[0] == 3.0 and M["a"].iloc[1] == 3.0 and np.isnan(M["a"].iloc[2])    # 全是缺值的月份 = 缺值
    M = pd.DataFrame({"a": np.arange(1, 11, dtype=float)}, index=pd.date_range("2020-01-31", periods=10, freq="ME"))
    A = SC.ahead(M, 3)
    assert A["a"].iloc[0] == 2 + 3 + 4 and A["a"].iloc[6] == 8 + 9 + 10                  # 之后 1〜3 个月，不含当月
    assert np.isnan(A["a"].iloc[7])
    assert SC.ahead(M, 1)["a"].iloc[0] == 2
    assert SC.past(M, 3)["a"].iloc[2] == 1 + 2 + 3 and np.isnan(SC.past(M, 3)["a"].iloc[1])


def test_price_change_uses_only_published_months():
    P = pd.DataFrame({"a": [100.0, 110.0, 121.0, 100.0]}, index=pd.date_range("2020-01-01", periods=4, freq="MS"))
    months = pd.date_range("2020-01-31", periods=4, freq="ME")
    ch = SC.price_change(P, months, 1)
    assert np.isnan(ch["a"].iloc[0]) and np.isnan(ch["a"].iloc[1])                       # 2 月末只知道 1 月的物价 → 还没有变化
    assert ch.loc[pd.Timestamp("2020-03-31"), "a"] == pytest.approx(math.log(1.1) * 100)  # 3 月末：1→2 月的变化（2 月的物价 3 月中旬公布）
    assert ch.loc[pd.Timestamp("2020-04-30"), "a"] == pytest.approx(math.log(1.1) * 100)
    ch2 = SC.price_change(P, SC.monthly(pd.DataFrame({"a": [0.0] * 4}, index=months)).index, 2)
    assert ch2.loc[pd.Timestamp("2020-04-30"), "a"] == pytest.approx(math.log(1.21) * 100)
    assert SC.price_change(P, months, 1, lag=0).loc[pd.Timestamp("2020-02-29"), "a"] == pytest.approx(math.log(1.1) * 100)


def test_signals_cost_margin_and_partners():
    months = pd.date_range("2020-01-31", periods=6, freq="ME")
    Mret = pd.DataFrame({"A": [1, 2, 3, 4, 5, 6.0], "B": [0, 1, 0, 1, 0, 1.0], "C": [2.0] * 6}, index=months)
    P = pd.DataFrame({"i1": [100 * 1.1 ** k for k in range(7)], "i2": [100.0] * 7},
                     index=pd.date_range("2019-12-01", periods=7, freq="MS"))
    links = {"ins": {"A": {"i1": 0.2, "i2": 0.1, "x9": 0.3}, "B": {"i2": 0.5}, "C": {}},
             "tse_io": {"A": ["i1"], "B": ["zz"], "C": []},
             "sup": {"A": {"B": 0.75, "C": 0.25}, "B": {}, "C": {"A": 1.0}},
             "cus": {"A": {"C": 1.0}, "B": {"A": 0.5, "Q": 0.5}, "C": {}}}
    sg = SC.signals(Mret, P, links, 1)
    t, g = pd.Timestamp("2020-02-29"), math.log(1.1) * 100
    assert np.isnan(sg["C"].loc[pd.Timestamp("2020-01-31"), "A"])                        # 12 月的变化要 11 月的物价 → 没有
    assert sg["C"].loc[t, "A"] == pytest.approx(0.2 * g)                                 # 没有物价的投入（x9）不算，也不归一
    assert sg["Mg"].loc[t, "A"] == pytest.approx(g - 0.2 * g)
    assert sg["C"].loc[t, "B"] == pytest.approx(0.0) and np.isnan(sg["Mg"].loc[t, "B"])   # 自己的产品没有物价 → 没有利润空间
    assert np.isnan(sg["C"].loc[t, "C"])
    assert sg["S"].loc[t, "A"] == pytest.approx(0.75 * 1 + 0.25 * 2)
    assert np.isnan(sg["S"].loc[t, "B"]) and sg["S"].loc[t, "C"] == pytest.approx(2.0)
    assert sg["K"].loc[t, "B"] == pytest.approx(2.0)                                     # 不在收益表里的伙伴（Q）去掉后再归一
    assert sg["K"].loc[t, "A"] == pytest.approx(2.0)
    assert sg["O"].loc[t, "A"] == 2.0


def test_ic_and_tercile_detect_planted_effect_and_null():
    rng = np.random.default_rng(0)
    months = pd.date_range("2010-01-31", periods=60, freq="ME")
    X = pd.DataFrame(rng.normal(size=(60, 20)), index=months)
    Y = X * 0.5 + pd.DataFrame(rng.normal(size=(60, 20)), index=months)
    st = SC.ic_stats(SC.fm_ic(X, Y, 0), 0)
    assert st["n"] == 60 and st["ic"] > 0.2 and st["t"] > 5
    tc = SC.tercile(X, Y, 1, 1)
    assert tc["n"] == 60 and tc["spread"] > 0 and tc["hit"] > 80
    assert SC.tercile(X, Y, -1, 1)["spread"] < 0
    assert SC.tercile(X, Y, 1, 3)["n"] == 20                                            # 每 3 个月一次（不重叠）
    assert SC.fm_ic(X.iloc[:, :5], Y.iloc[:, :5], 0).empty                                 # 行业太少的月份不算
    Z = pd.DataFrame(rng.normal(size=(60, 20)), index=months)
    null = SC.ic_stats(SC.fm_ic(X, Z, 0), 0)
    assert abs(null["ic"]) < 0.1 and abs(null["t"]) < 3


def test_nw_se_matches_iid_and_grows_with_autocorrelation():
    rng = np.random.default_rng(1)
    e = rng.normal(size=2000)
    assert SC._nw_se(e, 0) == pytest.approx(np.std(e) / math.sqrt(len(e)))
    ma = np.convolve(e, np.ones(3), mode="valid")                                       # 重叠的 3 期和 → 正自相关
    assert SC._nw_se(ma, 2) > 1.4 * SC._nw_se(ma, 0)
    assert np.isnan(SC._nw_se(e[:5], 0))


def test_study_lookup_uses_latest_month_end_on_or_before_signal():
    F = SC.monthly(pd.DataFrame({"a": [1.0, 2.0], "b": [10.0, 20.0]}, index=pd.to_datetime(["2020-01-15", "2020-02-14"])))
    dates = pd.Series(pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-15", "2020-03-05", "2020-03-05"]))
    v = SCS.daily_lookup(F, dates, ["a", "a", "b", "b", None])
    assert np.isnan(v[0]) and v[1] == 1.0 and v[2] == 10.0 and v[3] == 20.0 and np.isnan(v[4])


def test_study_zmean_and_halves():
    idx = pd.date_range("2020-01-31", periods=2, freq="ME")
    a = pd.DataFrame({"x": [1.0, 1.0], "y": [3.0, 2.0], "z": [5.0, np.nan]}, index=idx)
    b = pd.DataFrame({"x": [np.nan, 0.0], "y": [np.nan, 1.0], "z": [np.nan, 2.0]}, index=idx)
    z = SCS.zmean([a, b])
    assert z.loc[idx[0]].tolist() == pytest.approx([-1.0, 0.0, 1.0])                   # 只有 a 的那个月 = a 的 z 值
    assert z.loc[idx[1], "z"] == pytest.approx(1.0) and z.loc[idx[1], "x"] == pytest.approx((-0.7071068 - 1.0) / 2)
    H = SCS.month_halves(pd.date_range("2005-10-31", "2026-08-31", freq="ME"))
    assert H["H1"][0] == pd.Timestamp("2006-10-31") and H["H2"][0] == pd.Timestamp("2016-09-30")   # 与登记的两半一致
    assert H["H2"][1] == pd.Timestamp("2026-08-31")


def test_study_decide_needs_every_threshold():
    base = {"w20_calmar_exact": 0.363, "w20_dd_exact": -35.02}
    ok = {"auc": {"all": 0.58, "lo": 0.53, "hi": 0.62},
          "kept": {"O1": {"n": 50, "win": 60.0, "exp": 1.2}, "O2": {"n": 50, "win": 58.0, "exp": 1.0}},
          "all_half": {"O1": {"n": 80, "win": 55.0, "exp": 0.8}, "O2": {"n": 80, "win": 54.0, "exp": 0.7}},
          "s0c2_skip": {"w20_calmar_exact": 0.40, "w20_dd_exact": -30.0, "w20_cagr": 13.0},
          "s0c2_prio": {"w20_calmar_exact": 0.37, "w20_dd_exact": -33.0, "w20_cagr": 12.0},
          "dauc": {"d": 0.03, "lo": 0.005, "hi": 0.05}}
    bad = json.loads(json.dumps(ok))
    bad["dauc"] = {"d": 0.03, "lo": -0.001, "hi": 0.05}
    bad["kept"]["O2"]["win"] = 56.0
    V = SCS.decide({"V1": ok, "V2": bad}, base)
    assert V["passed"] == ["V1"]
    assert len(V["per"]["V2"]["fails"]) == 2


def test_fm_ic_matches_pandas_rank_corr_with_ties_and_gaps():
    rng = np.random.default_rng(3)
    months = pd.date_range("2015-01-31", periods=12, freq="ME")
    X = pd.DataFrame(rng.integers(0, 4, size=(12, 10)).astype(float), index=months)      # 很多相同的值（例 化学 / 医薬品 的 C 一样）
    Y = pd.DataFrame(rng.normal(size=(12, 10)), index=months)
    X.iloc[2, :4] = np.nan
    Y.iloc[5, 1:] = np.nan                                                                # 这个月只剩 1 个行业 → 不算
    ic = SC.fm_ic(X, Y.iloc[:-1], 0)                                                     # 最后一个月没有之后的收益 → 不算
    ref = {}
    for t in months[:-1]:
        m = X.loc[t].notna() & Y.loc[t].notna()
        if m.sum() >= 8:
            ref[t] = X.loc[t][m].rank().corr(Y.loc[t][m].rank())
    assert list(ic.index) == list(ref) and months[5] not in ic.index
    assert np.allclose(ic.to_numpy(), np.array(list(ref.values())))


def test_roll_and_placebo_p():
    idx = pd.date_range("2020-01-31", periods=5, freq="ME")
    s = pd.Series([1.0, 2, 3, 4, 5], index=idx, name="a")
    r = SC.roll(s, 2)
    assert list(r.index) == list(idx) and r.tolist() == [4.0, 5, 1, 2, 3] and r.name == "a"
    F = SC.roll(pd.DataFrame({"x": [1.0, 2, 3], "y": [4.0, 5, 6]}, index=idx[:3]), 1)
    assert F["x"].tolist() == [3.0, 1, 2] and F["y"].tolist() == [6.0, 4, 5]
    pl = np.array([0.5, 1.0, 1.5, 2.5, np.nan])
    assert SC.placebo_p(2.0, pl) == pytest.approx((1 + 1) / (1 + 4))                    # 对照里 ≥ 2.0 的只有 2.5
    assert SC.placebo_p(-2.0, -pl, -1) == pytest.approx(2 / 5)                             # 事先方向为负：看 ≤
    assert SC.placebo_p(9.0, pl) == pytest.approx(1 / 5) and SC.placebo_p(np.nan, pl) is None
