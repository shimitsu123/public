"""scripts/transmit_study.py：Leontief 的直接 / 间接分解（原材料行外生）、東証业种的暴露、信号（不偷看）、去季节的冲击 z、
T4 / T5 的保留规则、传导时间的回归（含 h < 0）。"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import transmit_study as TS  # noqa: E402

SHOCK_CODES = [r for rows in TS.SHOCK_ROWS.values() for r in rows]


def test_io_matrices_indirect_excludes_shocked_rows_own_loop():
    codes = ["061", "211", "205", "221"]                                             # 原油 → 石油製品 → 合成樹脂 → 塑料製品
    x = pd.DataFrame(0.0, index=codes, columns=codes)
    x.loc["061", "061"], x.loc["061", "211"] = 10, 40                                # 原油自己的循环 10%
    x.loc["211", "211"], x.loc["211", "205"], x.loc["205", "221"] = 10, 30, 20
    X = pd.Series(100.0, index=codes)
    A, M = TS.io_matrices(x, X, ["061"])
    assert np.isclose(A.loc["061", "211"], 0.4) and np.isclose(A.loc["061", "205"], 0.0)
    ind = A.loc["061"].to_numpy() @ M.to_numpy()
    k = {c: i for i, c in enumerate(codes)}
    # 合成樹脂没有直接买原油，经过石油製品（它自己的循环 1 / (1 − 0.1)）间接用了；原油自己的循环不再乘进来
    assert np.isclose(ind[k["205"]], 0.4 * 0.3 / 0.9)
    assert np.isclose(ind[k["221"]], 0.4 * 0.3 / 0.9 * 0.2)
    assert np.allclose(M.loc["061"], 0.0)                                          # 外生行：L_S 的那一行只剩自己
    As = A.to_numpy().copy()
    As[k["061"], :] = 0
    assert np.allclose(M.to_numpy(), np.linalg.inv(np.eye(4) - As) - np.eye(4))
    _, M_all = TS.io_matrices(x, X, [])                                              # 不设外生：会把原油自己的循环重复算
    assert A.loc["061"].to_numpy() @ M_all.to_numpy()[:, k["205"]] > ind[k["205"]] + 1e-6


def _A_for_exposures():
    codes = SHOCK_CODES + ["291", "301", "281"]
    A = pd.DataFrame(0.0, index=codes, columns=codes)
    A.loc["262", "291"], A.loc["262", "301"], A.loc["261", "291"] = 0.2, 0.1, 0.05
    A.loc["262", "281"], A.loc["061", "262"] = 0.1, 0.07
    M = pd.DataFrame(0.0, index=codes, columns=codes)
    M.loc["281", "291"] = 0.5                                                      # 金属製品 → 一般机械 的高阶路径
    X = pd.Series(1.0, index=codes)
    X["291"], X["301"] = 300.0, 100.0
    return A, M, X


def test_exposures_weighting_and_source_excluded():
    A, M, X = _A_for_exposures()
    ex = TS.exposures(A, M, X, ["機械", "鉄鋼", "金属製品", "空運業"])
    assert np.isclose(ex["direct"]["S"]["機械"], (0.2 + 0.05) * 0.75 + 0.1 * 0.25)   # 两个鉄鋼行相加，按国内生产额加权
    assert np.isclose(ex["indirect"]["S"]["機械"], 0.1 * 0.5 * 0.75)
    assert np.isclose(ex["direct"]["S"]["金属製品"], 0.1) and np.isclose(ex["indirect"]["S"]["金属製品"], 0.0)
    assert "鉄鋼" not in ex["direct"]["S"] and "鉄鋼" not in ex["indirect"]["S"]     # 产出业种对自己那一种不算成本
    assert np.isclose(ex["direct"]["E"]["鉄鋼"], 0.07 / 4)                          # 对能源来说鉄鋼是使用方（4 个鉄鋼部门平均）
    assert "空運業" not in ex["direct"]["E"]                                        # 没有对应部门的业种不出现
    assert set(ex["direct"]) == set(TS.SHOCKS) == set(ex["indirect"])


def test_tse_of_overrides():
    assert TS.tse_of("207") == ["医薬品"] and TS.tse_of("205") == ["化学"] and TS.tse_of("221") == ["化学"]
    assert TS.tse_of("222") == ["ゴム製品"] and TS.tse_of("191") == ["その他製品"] and TS.tse_of("231") == ["その他製品"]
    assert TS.tse_of("574") == ["海運業"] and TS.tse_of("571") == [] and TS.tse_of("553") == []
    assert TS.tse_of("262") == ["鉄鋼"] and TS.tse_of("291") == ["機械"]


def test_hit_sets_source_plus_direct_users():
    ex = {"direct": {"E": {"電気・ガス業": 0.2, "化学": 0.049, "石油・石炭製品": 0.7}, "S": {"金属製品": 0.3}, "N": {}, "F": {"食料品": 0.05}},
          "indirect": {k: {} for k in TS.SHOCKS}}
    h = TS.hit_sets(ex)
    assert h["E"] == sorted(["鉱業", "電気・ガス業", "石油・石炭製品"])                # 化学 4.9% < 5% → 不算直接
    assert h["S"] == ["金属製品", "鉄鋼"] and h["N"] == ["非鉄金属"] and h["F"] == sorted(["水産・農林業", "食料品"])


def _ex():
    d = {"E": {"a": 0.5, "b": 0.0, "c": 0.02, "鉄鋼": 0.3}, "S": {"b": 0.1}, "N": {}, "F": {}}
    n = {"E": {"a": 0.1, "b": 0.3, "c": 0.0, "鉄鋼": 0.1}, "S": {"b": 0.2}, "N": {}, "F": {}}
    return {"direct": d, "indirect": n}


def test_signals_weighted_split_and_prop_excludes_self_and_benefit():
    months = pd.date_range("2000-01-31", periods=12, freq="ME")
    Mret = pd.DataFrame({"a": 1.0, "b": 2.0, "c": 3.0, "鉄鋼": 50.0}, index=months)
    P = pd.DataFrame({k: 100.0 for k in TS.SHOCKS}, index=pd.date_range("2000-01-01", periods=12, freq="MS"))
    P["E"] = 100 * np.exp(np.arange(12) * 0.01)                                      # 每个月 +1%
    P["S"] = 100 * np.exp(np.arange(12) * 0.02)                                      # 每个月 +2%
    s = TS.signals(Mret, P, _ex(), 1)
    t = months[5]
    assert np.isclose(s["DIR"].loc[t, "a"], 0.5) and np.isclose(s["DIR"].loc[t, "b"], 0.1 * 2)
    assert np.isclose(s["IND"].loc[t, "b"], 0.3 + 0.2 * 2)
    assert np.isclose(s["IND_E"].loc[t, "b"], 0.3) and np.isclose(s["IND_O"].loc[t, "b"], 0.4)
    # PROP_b = 间接_b × 直接受影响的使用方（a 0.5、c 0.02；不含 b 自己、不含收入受益的鉄鋼）按直接份额加权的过去收益
    assert np.isclose(s["PROP"].loc[t, "b"], 0.3 * (0.5 * 1.0 + 0.02 * 3.0) / 0.52)
    assert np.isclose(s["PROP"].loc[t, "a"], 0.1 * (0.02 * 3.0) / 0.02)             # a 的 PROP 不含 a 自己；S 的使用方只有 b，a 的间接 S 为 0
    assert s["DIR"].iloc[:2].isna().all().all()                                      # 发布滞后：头两个月没有值
    P.loc[P.index[6], "N"] = np.nan                                                  # 任一种原材料缺 → 那个月整行不用
    s2 = TS.signals(Mret, P, _ex(), 1)
    assert s2["IND"].loc[months[7]].isna().all() and s2["IND"].loc[months[9]].notna().all()


def test_shock_z_deseasonalized_uses_only_past():
    n = 72
    rng = np.random.default_rng(0)
    idx = pd.date_range("2000-01-01", periods=n, freq="MS")
    P = pd.DataFrame({k: 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n))) for k in TS.SHOCKS}, index=idx)
    seas = np.where(idx.month == 1, -0.03, 0.0) + rng.normal(0, 0.001, n)           # 每年 1 月 −3% 的季节性
    P["F"] = 100 * np.exp(np.cumsum(seas))
    months = pd.date_range("2000-01-31", periods=n, freq="ME")
    z = TS.shock_z(P, months)
    d1 = TS.SC.price_change(P, months, 1)
    k = 50
    same = [d1["E"].iloc[i] for i in range(k - 12, -1, -12) if np.isfinite(d1["E"].iloc[i])]
    assert np.isclose(z["E"].iloc[k], (d1["E"].iloc[k] - np.mean(same)) / d1["E"].iloc[:k].std())
    assert z["E"].iloc[: TS.Z_MIN_HIST].isna().all()
    # 已知的季节性不算冲击：1 月的变化（公布在 2 月末）去掉同月份的历史平均后很小
    feb = [i for i in range(40, n) if months[i].month == 2]
    assert feb and (z["F"].iloc[feb].abs() < 0.2).all()
    assert (d1["F"].iloc[feb] < -2.5).all()


def test_daily_from_monthly_uses_previous_month_end():
    M = pd.Series([1.0, 2.0, 3.0], index=pd.DatetimeIndex(["2020-01-31", "2020-02-29", "2020-03-31"]))
    days = pd.DatetimeIndex(["2020-02-03", "2020-02-28", "2020-03-02"])
    assert TS.daily_from_monthly(M, days).tolist() == [1.0, 1.0, 2.0]


def test_t4_keep_uses_abs_z_and_direct_hit_sets():
    days = pd.bdate_range("2020-02-03", "2020-03-31")
    fr = {t: pd.DataFrame({"Close": 1.0}, index=days) for t in ("X.T", "Y.T", "W.T")}
    s33 = {"X.T": "a", "Y.T": "b", "W.T": "c"}
    Z = pd.DataFrame({k: 0.0 for k in TS.SHOCKS}, index=pd.DatetimeIndex(["2020-01-31", "2020-02-29"]))
    Z.loc["2020-01-31", "E"] = 2.0                                                   # 1 月末：能源大涨
    Z.loc["2020-02-29", "S"] = -1.5                                                  # 2 月末：钢铁大跌（|z| 也算）
    Z.loc["2020-02-29", "N"] = 1.2                                                   # 不到 1.28
    hits = {"E": ["a"], "S": ["b"], "N": ["c"], "F": []}
    k4 = TS.t4_keep(fr, s33, Z, hits)
    feb = days.month == 2
    assert (~k4["X.T"][feb]).all() and k4["X.T"][~feb].all()
    assert k4["Y.T"][feb].all() and (~k4["Y.T"][~feb]).all()
    assert k4["W.T"].all()


def test_t5_keep_top_third_and_positive_only():
    days = pd.bdate_range("2020-02-03", "2020-03-31")
    fr = {t: pd.DataFrame({"Close": 1.0}, index=days) for t in ("X.T", "Y.T", "V.T")}
    s33 = {"X.T": "a", "Y.T": "b", "V.T": "鉄鋼"}                                   # 鉄鋼 不在横截面里 → 照做
    idx = pd.DatetimeIndex(["2020-01-31", "2020-02-29"])
    IND3 = pd.DataFrame({"a": [0.1, -0.1], "b": [0.9, -0.5], "c": [0.5, -0.3]}, index=idx)
    k5 = TS.t5_keep(fr, s33, IND3)
    feb = days.month == 2
    assert (~k5["Y.T"][feb]).all() and k5["Y.T"][~feb].all()                         # 1 月末 b 最高且 > 0 → 2 月不做
    assert k5["X.T"].all()                                                           # 2 月末 a 最高但 ≤ 0 → 3 月照做
    assert k5["V.T"].all()


def test_fm_lag_coefs_delayed_effect_negative_h_and_t2_stat():
    rng = np.random.default_rng(1)
    n = 240
    months = pd.date_range("2006-10-31", periods=n, freq="ME")
    cols = [f"i{j}" for j in range(24)]
    D = pd.DataFrame(rng.normal(size=(n, 24)), index=months, columns=cols)
    I = pd.DataFrame(rng.normal(size=(n, 24)), index=months, columns=cols)
    R = pd.DataFrame(rng.normal(scale=0.5, size=(n, 24)), index=months, columns=cols)
    R.iloc[3:] -= 1.0 * I.iloc[:-3].to_numpy()                                       # 间接压力 3 个月后才反映
    R.iloc[:-1] += 0.8 * D.iloc[1:].to_numpy()                                       # 直接的在信号之前一个月（h = −1）就反映了
    c = TS.fm_lag_coefs(D, I, R)
    assert set(c) == set(TS.T2_H)
    st = TS.t2_stat(c, months[0])
    assert st["profile"]["ind"][3] < -0.8 and abs(st["profile"]["ind"][1]) < 0.15 and abs(st["profile"]["ind"][-1]) < 0.15
    assert st["profile"]["dir"][-1] > 0.6 and abs(st["profile"]["dir"][3]) < 0.15
    assert st["ind"]["sum"] < -0.8 and st["ind"]["t"] < -5 and st["ind"]["H1"] < 0 and st["ind"]["H2"] < 0
    assert st["pair"]["diff"] < -0.5 and st["pair"]["t"] < -2
    h1 = TS.halves(TS.H1_END_T2)["H1"][1]
    assert h1 == pd.Timestamp("2016-02-29")                                          # 前半只到 2016-02：h = 6 的收益不跨进后半


def test_ic_effective_and_paired():
    assert TS.ic_effective({"t": 2.5, "ic_H1": 0.1, "ic_H2": 0.05, "hit": 60.0, "placebo_p": 0.01}) == []
    assert len(TS.ic_effective({"t": 1.5, "ic_H1": 0.1, "ic_H2": -0.05, "hit": 50.0, "placebo_p": 0.2})) == 4
    idx = pd.date_range("2010-01-31", periods=40, freq="ME")
    a = pd.Series(np.linspace(0.1, 0.2, 40), index=idx)
    b = pd.Series(0.05, index=idx)
    p = TS.paired(a, b, 4)
    assert np.isclose(p["diff"], 0.1, atol=1e-4) and p["n"] == 40 and p["t"] > 5


def _write_io_xlsx(fp: Path, codes: list[str], x: pd.DataFrame, X: pd.Series) -> None:
    """取引基本表的版式：第 2 行 = 部门代码（前两列空；内生部门之后是 700…、970 = 国内生产额），第 3 行 = 名称，第 4 行起 = 数据。"""
    hdr = ["", ""] + codes + ["700", "970"]
    rows = [["表"] + [""] * (len(hdr) - 1), hdr, ["", ""] + [f"n{c}" for c in codes] + ["最終需要", "国内生産額"]]
    for r in codes:
        rows.append([r, f"n{r}"] + [x.loc[r, c] for c in codes] + [0.0, X[r]])
    rows.append(["700", "付加価値"] + [0.0] * len(codes) + [0.0, 0.0])
    pd.DataFrame(rows).to_excel(fp, header=False, index=False)


def test_read_io108_and_load_exposures_regenerates_on_method_change(tmp_path, monkeypatch):
    codes = SHOCK_CODES + ["291", "281"]
    x = pd.DataFrame(0.0, index=codes, columns=codes)
    x.loc["262", "291"], x.loc["262", "281"], x.loc["281", "291"] = 20.0, 10.0, 30.0
    X = pd.Series(100.0, index=codes)
    monkeypatch.setenv("QBREAK_HOME", str(tmp_path))
    xl = tmp_path / "cache" / "io" / TS.IO_FILE
    xl.parent.mkdir(parents=True)
    _write_io_xlsx(xl, codes, x, X)
    x2, X2 = TS.read_io108(xl)
    assert list(x2.index) == codes and np.isclose(x2.loc["262", "291"], 20.0) and np.isclose(X2["291"], 100.0)
    (tmp_path / "io_indirect_2020.json").write_text(json.dumps({"method": "旧的 37 部门", "industries": ["機械"]}), encoding="utf-8")
    doc = TS.load_exposures(["機械", "金属製品"])
    assert doc["method"] == TS.METHOD                                                # 旧方法的缓存不用，重新导出
    assert np.isclose(doc["direct"]["S"]["機械"], 0.2) and np.isclose(doc["indirect"]["S"]["機械"], 0.1 * 0.3)
    saved = json.loads((tmp_path / "io_indirect_2020.json").read_text(encoding="utf-8"))
    assert saved["method"] == TS.METHOD and "x" not in saved                         # 只存份额，不存原表
    assert TS.load_exposures(["機械"]) == saved                                      # 同一方法 → 直接读
