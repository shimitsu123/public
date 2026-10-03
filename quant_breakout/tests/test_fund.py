"""更多数据的研究（qbreak/tankan.py、qbreak/adaptive.py、scripts/fund_study.py）：短観的代码与日期、保守的公布日、
业种对照、顾客加权、设备投资修正率的季节调整（只用当时已有的年份）、公布后收益从下一个交易日起算、
最近 5 年 vs 全期 能发现「关系变了」、登记的列表前后一致。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak import adaptive as AD
from qbreak import tankan as TK
from qbreak import themes as TH

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fund_study as FS                                                     # noqa: E402


def test_codes_and_available_dates():
    assert TK.code("1060", "biz") == "TK99F1060601GCQ01000"                        # 大企業・化学・業況・実績（BOJ 的实际代码）
    assert TK.code("1060", "sell") == "TK99F1060614GCQ01000" and TK.code("1060", "biz", True) == "TK99F1060601GCQ11000"
    assert TK.capex_code("1150", 4) == "TK99G11501092FY41000"
    assert TK.available(pd.Timestamp("2026-06-30")) == pd.Timestamp("2026-07-05")
    assert TK.available(pd.Timestamp("2025-12-31")) == pd.Timestamp("2025-12-20")  # 12 月调查 12 月中旬公布
    assert TK.available(pd.Timestamp("2026-03-31")) == pd.Timestamp("2026-04-05")


def _fake_fetch(values: dict):
    def f(c):
        if c not in values:
            raise RuntimeError("HTTP 400")
        return values[c]
    return f


def test_load_signals_forecast_alignment_and_missing():
    q = pd.to_datetime(["2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"])
    act = pd.Series([10.0, 12.0, 20.0, np.nan], index=q).dropna()
    fc = pd.Series([11.0, 15.0, 18.0, 25.0], index=q)                             # 6 月调查对 9 月的预测挂在 2026-09-30
    vals = {TK.code("1150", "biz"): act, TK.code("1150", "biz", True): fc,
            TK.code("1150", "sell"): pd.Series([5.0, 8.0, 14.0], index=q[:3]), TK.code("1150", "buy"): pd.Series([20.0, 20.0, 22.0], index=q[:3]),
            TK.code("1150", "dom"): pd.Series([0.0, 2.0, 1.0], index=q[:3])}
    TK.MISSING.clear()
    T = TK.load(_fake_fetch(vals))
    assert TK.code("1060", "biz") in TK.MISSING and T["biz"]["1060"].isna().all()   # 取不到的系列 → 缺值并记下
    S = TK.signals(T)
    assert S["S1"].loc["2026-06-30", "1150"] == 8.0                                # 20 − 12
    assert S["S2"].loc["2026-06-30", "1150"] == 25.0 - 20.0                        # 下季（9 月）的予測 − 6 月的実績
    assert S["S3"].loc["2026-06-30", "1150"] == (14 - 22) - (8 - 20)               # Δ(販売 − 仕入)
    assert S["S4"].loc["2026-06-30", "1150"] == -1.0
    G = TK.to_groups(S["S1"], ["電気機器", "T4", "T11", "サービス業"])
    assert G.loc["2026-06-30", "電気機器"] == 8.0 and G.loc["2026-06-30", "T4"] == 8.0 and G["サービス業"].isna().all()


def test_customer_weighted_renormalizes_available():
    idx = pd.to_datetime(["2026-03-31", "2026-06-30"])
    sig = pd.DataFrame({"甲": [1.0, 2.0], "乙": [3.0, np.nan]}, index=idx)
    cw = TK.customer_weighted(sig, {"丙": {"甲": 0.25, "乙": 0.75}, "丁": {"戊": 1.0}})
    assert cw.loc[idx[0], "丙"] == pytest.approx(0.25 * 1 + 0.75 * 3)
    assert cw.loc[idx[1], "丙"] == pytest.approx(2.0)                              # 乙缺值 → 只剩甲，重新归一
    assert "丁" not in cw.columns


def test_seasonal_adjust_uses_only_prior_years():
    dates = pd.to_datetime([f"{y}-{m:02d}-05" for y in range(2000, 2012) for m in (4, 7, 10)])
    vals = [(10.0 if d.month == 7 else 0.0) + (d.year - 2000) * 0.1 for d in dates]
    C = pd.DataFrame({"全産業": vals}, index=dates)
    A = TK.seasonal_adjust(C, min_years=5)
    jul = A["全産業"][A.index.month == 7]
    assert jul.iloc[:5].isna().all()                                                # 前 5 年不够 → 缺值
    assert jul.iloc[5] == pytest.approx(10.5 - np.mean([10 + k * 0.1 for k in range(5)]))   # 只减之前各年的 7 月平均
    C2 = C.copy()
    C2.iloc[-1] = 999.0                                                            # 以后的值变了，之前的调整值不变
    assert TK.seasonal_adjust(C2, 5).iloc[:-1].equals(A.iloc[:-1])


def test_release_targets_start_next_trading_day():
    idx = pd.bdate_range("2026-07-01", periods=10)
    D = pd.DataFrame({"a": np.arange(1, 11, dtype=float)}, index=idx)
    Y = TK.release_targets(D, [pd.Timestamp("2026-07-05")], 3)                      # 7/5 是周日 → 从 7/6（周一）起
    assert Y.iloc[0, 0] == 4 + 5 + 6
    Y2 = TK.release_targets(D, [pd.Timestamp("2026-07-06")], 3)                     # 公布日当天收盘后才用 → 从 7/7 起
    assert Y2.iloc[0, 0] == 5 + 6 + 7
    assert np.isnan(TK.release_targets(D, [pd.Timestamp("2026-07-13")], 3).iloc[0, 0])   # 不够 3 天 → 缺值


def test_adaptive_detects_changing_relation():
    rng = np.random.default_rng(3)
    idx = pd.date_range("2000-01-31", periods=312, freq="ME")
    X = pd.DataFrame({f"s{k}": rng.normal(0, 1, len(idx)) for k in range(5)}, index=idx)
    beta = np.where(idx.year < 2015, 1.0, -1.0)                                    # 关系在 2015 年反转
    Y = pd.DataFrame({f"t{k}": beta * X[f"s{k}"].to_numpy() + rng.normal(0, 1, len(idx)) for k in range(5)}, index=idx)   # 行 t = 信号 t 之后的收益
    pairs = [(f"s{k}", f"t{k}") for k in range(5)]
    R = AD.compare(X, Y, pairs, list(range(2017, 2026)), window=2, min_obs=18, h=1)
    assert len(R) == 9 and (R["diff"] > 0).all()                                   # 全期估计还停在反转前 → 最近 2 年的估计更准
    assert AD.verdict(R)["better"]
    Ys = pd.DataFrame({f"t{k}": 1.0 * X[f"s{k}"].to_numpy() + rng.normal(0, 1, len(idx)) for k in range(5)}, index=idx)
    R2 = AD.compare(X, Ys, pairs, list(range(2017, 2026)), window=2, min_obs=18, h=1)
    assert not AD.verdict(R2)["better"]                                            # 关系不变 → 最近 2 年的估计并不更准


def test_registered_lists_are_consistent():
    assert len(FS.CAPEX_PAIRS) == 10 and len(FS.DEMAND_PAIRS) == 25 and len(FS.DEMAND) == 9
    for src, tgt in FS.CAPEX_PAIRS:
        assert src in TK.CAPEX_IND.values() and (tgt in TH.THEMES or tgt in TK.TSE)
    for src, tgt in FS.DEMAND_PAIRS:
        assert src in FS.DEMAND and (tgt in TH.THEMES or tgt in TK.TSE)
    assert set(FS.SIGS) == {"S1", "S2", "S3", "S4", "S5", "S6"} and FS.SIGS["S6"][1] == -1
    for g, inds in TK.TSE.items():
        assert all(i in TK.IND for i in inds)


def test_nw_t_small_sample_and_ts_pair():
    rng = np.random.default_rng(4)
    idx = pd.date_range("2006-10-05", periods=80, freq="QS")
    x = pd.Series(rng.normal(0, 1, 80), index=idx)
    y = pd.Series(0.8 * x.to_numpy() + rng.normal(0, 0.5, 80), index=idx)
    r = FS.ts_pair(x, y, FS.halves_idx(idx), 1, 8, 1)
    assert r["t"] > 5 and r["ok"] and r["p"] < 0.05 and r["t_H1"] > 0 and r["t_H2"] > 0
    r2 = FS.ts_pair(x, -y, FS.halves_idx(idx), 1, 8, 1)
    assert not r2["ok"] and r2["p"] > 0.9
    assert np.isnan(FS.nw_t(x.to_numpy()[:20], y.to_numpy()[:20], 1)[1])            # 少于 30 个点 → 不算
