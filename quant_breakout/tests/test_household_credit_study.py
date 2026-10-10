"""scripts/household_credit_study.py（家庭信贷加进威胁指数）：因素清单与公布时滞（日本 / 欧亚再晚 1 天）、变换、领域分 ≥ 3 个、
K2 = A0 的因素 + D_H 等权（D_H 没有值时不给值）、同一批日子比较、自助法可重现、事先写定的判定 a〜e。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import household_credit_study as HC                                          # noqa: E402


def test_constants_and_specs():
    assert (HC.EVAL0, HC.SPLIT, HC.HORIZON) == (pd.Timestamp("1995-01-01"), pd.Timestamp("2011-01-01"), 60)
    assert (HC.A_MIN, HC.ALPHA, HC.BOOT_REPS, HC.BOOT_BLOCK, HC.BOOT_SEED) == (0.03, 0.05, 2000, 250, 20260929)
    assert HC.HH == ["cc_delinq", "cc_chargeoff", "cons_delinq", "mort_delinq", "cc_std", "mort_rate"] and HC.DH_MIN == 3
    assert {k: (v[0], v[1], v[2]) for k, v in HC.SERIES.items()} == {
        "cc_delinq": ("DRCCLACBS", "q_chg4", 160), "cc_chargeoff": ("CORCCACBS", "q_chg4", 160), "cons_delinq": ("DRCLACBS", "q_chg4", 160),
        "mort_delinq": ("DRSFRMACBS", "q_chg4", 160), "cc_std": ("DRTSCLCC", "level", 45), "mort_rate": ("MORTGAGE30US", "w_chg26", 1)}
    assert HC.EXTRA["dsr"][:3] == ("TDSP", "q_chg4", 180) and "dsr" not in HC.HH           # 偿债比率只描述，不进领域分
    assert list(HC.CANDS) == ["K1", "K2", "K3"]


def test_native_transforms():
    q = pd.Series(np.arange(10, dtype=float), index=pd.date_range("2000-01-01", periods=10, freq="QS"))
    assert HC.native("q_chg4", q).iloc[-1] == 4.0 and np.isnan(HC.native("q_chg4", q).iloc[3])
    w = pd.Series(np.arange(60, dtype=float), index=pd.date_range("2000-01-06", periods=60, freq="7D"))
    assert HC.native("w_chg26", w).iloc[-1] == 26.0 and HC.native("w_chg52", w).iloc[-1] == 52.0
    assert HC.native("level", q).equals(q)


def test_hh_features_publication_lag_and_late_market():
    q = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 9.0], index=pd.date_range("2000-01-01", periods=6, freq="QS"))
    raw = {"cc_delinq": q}
    days = pd.date_range("2000-01-01", "2002-01-31", freq="D")
    f = HC.hh_features(days, raw, late=False, keys=["cc_delinq"])["cc_delinq"]
    idx4 = q.index[4]                                                        # 第一个有 4 季变化的季度（2001-01-01）
    first = idx4 + pd.Timedelta(days=160)
    assert np.isnan(f.loc[first - pd.Timedelta(days=1)]) and f.loc[first] == 4.0   # 160 天后才可用
    g = HC.hh_features(days, raw, late=True, keys=["cc_delinq"])["cc_delinq"]
    assert np.isnan(g.loc[first]) and g.loc[first + pd.Timedelta(days=1)] == 4.0   # 日本 / 欧亚再晚 1 天
    assert HC.hh_features(days, {}, late=False, keys=["cc_delinq"]).shape[1] == 0


def test_eqw_and_candidates():
    idx = pd.RangeIndex(3)
    a0p = pd.DataFrame({f"a{i}": [0.5, 0.5, np.nan] for i in range(8)}, index=idx)
    hp = pd.DataFrame({k: [0.8, np.nan, 0.8] for k in HC.HH}, index=idx)
    hp.loc[0, "mort_rate"] = np.nan                                          # 第 0 行：5 个有值
    C = HC.candidates(a0p, hp)
    assert np.isclose(C["A0"][0], 50.0) and np.isclose(C["K1"][0], 80.0)
    assert np.isclose(C["K2"][0], (8 * 50 + 80) / 9)                          # D_H 作为一个因素加进 A0
    assert np.isclose(C["K3"][0], 65.0)
    assert np.isnan(C["K1"][1]) and np.isnan(C["K2"][1]) and np.isnan(C["K3"][1])   # D_H 没有值 → K2 也不给值
    assert np.isnan(C["A0"][2]) and np.isnan(C["K2"][2])                      # A0 的因素都没有 → K2 也没有
    few = hp.copy()
    few.loc[0, ["cc_delinq", "cc_chargeoff", "cons_delinq"]] = np.nan         # 只剩 2 个 → D_H 不算
    assert np.isnan(HC.candidates(a0p, few)["K1"][0])
    one_of_four = pd.DataFrame({"x": [0.5], "y": [np.nan], "z": [np.nan], "w": [np.nan]})
    assert np.isnan(HC.eqw(one_of_four)[0])                                  # 默认要一半（4 个里 ≥ 2 个）
    assert HC.eqw(one_of_four, min_n=1)[0] == 50.0


def _series(n=6000, seed=3):
    days = pd.bdate_range("1995-01-02", periods=n)
    rng = np.random.default_rng(seed)
    y = pd.Series((rng.uniform(size=n) < 0.15).astype(float), index=days)
    base = pd.Series(rng.normal(size=n), index=days)
    return days, y, base


def test_halves_same_days_and_boot_reproducible():
    days, y, base = _series()
    better = base + 2.0 * y
    s = better.copy()
    s.iloc[:100] = np.nan                                                    # 候选缺值的日子 A0 也不比
    h = HC.halves(s, base, y)
    assert h["n"][0] == int(((days >= HC.EVAL0) & (days < HC.SPLIT)).sum()) - 100
    assert h["d"][0] > 0.2 and h["d"][1] > 0.2
    p1 = HC.boot_p(better, base, y, reps=40)
    assert p1 == HC.boot_p(better, base, y, reps=40) == 0.0
    assert HC.boot_p(base - 2.0 * y, base, y, reps=40) == 1.0
    assert HC.boot_p(better.iloc[:100], base.iloc[:100], y.iloc[:100], reps=10) is None   # 样本不够


def test_judge_rules():
    def cand(a1, a2, b1, b2, f15, a15, p):
        return {"auc": [a1, a2], "a0": [b1, b2], "d": [a1 - b1, a2 - b2], "auc15": f15, "a0_15": a15, "d15": f15 - a15, "p": p}
    good = cand(0.72, 0.70, 0.70, 0.65, 0.66, 0.64, 0.001)
    home = {"US": {"cand": {"K1": cand(0.60, 0.60, 0.70, 0.65, 0.5, 0.64, 0.9), "K2": good, "K3": cand(0.71, 0.67, 0.70, 0.65, 0.7, 0.64, 0.001)}},
            "JP": {"cand": {k: cand(0.60, 0.60, 0.61, 0.62, 0.5, 0.6, 0.5) for k in HC.CANDS}}}
    glob = {m: {"cand": {k: {"d": [0.0, 0.01]} for k in HC.CANDS}} for m in HC.TI.MARKETS}
    dev = [k for k, v in HC.TI.MARKETS.items() if v[2] == "dev"]
    J = HC.judge(home, glob, dev)
    assert J["US"]["cands"]["K2"]["pass"] and J["US"]["adopted"] == "K2"
    assert not J["US"]["cands"]["K3"]["pass"] and not J["US"]["cands"]["K3"]["checks"]["a 后半 ≥ A0 + 0.03"]
    assert not J["US"]["cands"]["K1"]["checks"]["b 前半 ≥ A0"] and J["JP"]["adopted"] is None
    glob_bad = {m: {"cand": {k: {"d": [0.0, -0.01]} for k in HC.CANDS}} for m in HC.TI.MARKETS}
    J2 = HC.judge(home, glob_bad, dev)
    assert not J2["US"]["cands"]["K2"]["checks"]["e 发达 15 市场后半 ≥ 0"] and J2["US"]["adopted"] is None


def test_press_hh_direction_and_lag():
    q = pd.Series([2.0, 2.0, 2.0, 2.0, 1.0], index=pd.date_range("2000-01-01", periods=5, freq="QS"))
    std = pd.Series([10.0, -5.0], index=pd.to_datetime(["2000-10-01", "2001-01-01"]))
    w = pd.Series(np.r_[np.full(52, 6.0), 7.0], index=pd.date_range("2000-01-06", periods=53, freq="7D"))
    raw = {"cc_delinq": q, "cc_std": std, "mort_rate": w}
    d = pd.DatetimeIndex(["2001-12-31"])
    P = HC.press_hh(raw, d)
    assert P["hh_easy"].iloc[0] == 1.0                                       # 拖欠率下降 → 宽松 = 加压（正）
    assert P["hh_std"].iloc[0] == 5.0                                        # 放贷标准放松（净收紧 −5）→ +5
    assert P["mort_up"].iloc[0] == 1.0                                       # 房贷利率 52 周上升 1 个百分点
    edge = pd.DatetimeIndex([q.index[4] + pd.Timedelta(days=160)])
    assert HC.press_hh(raw, edge)["hh_easy"].iloc[0] == 1.0 and np.isnan(HC.press_hh(raw, edge, late=True)["hh_easy"].iloc[0])
