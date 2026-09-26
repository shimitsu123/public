"""因子曲线左右平移对齐股价（qbreak/lagscan.py、scripts/lagscan_study.py；2026-09-26 事先登记）：平移方向、成对缺值、
发现 / 复现 / 对照、埋进去的「因子领先 3 周」被找到且对照里没有、水平的伪相关、预测分只用信号日以前完整的周。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak import lagscan as LG

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lagscan_study as LSD                                                   # noqa: E402

WEEKS = pd.date_range("2006-10-06", "2026-09-25", freq="W-FRI")               # 与研究相同的周（发现期到 2015-12，之后验证）


def _lead(f: np.ndarray, k: int, beta: float, rng) -> np.ndarray:
    """股票第 t 周 = beta × 因子第 t−k 周 + 噪音（因子领先 k 周）。"""
    y = rng.standard_normal(len(f))
    y[k:] += beta * f[:-k]
    return y


def test_weekly_last_and_changes():
    days = pd.bdate_range("2024-01-01", "2024-01-19").drop(pd.Timestamp("2024-01-12"))  # 第二周的周五没有数据
    lv = pd.DataFrame({"oil": np.log(np.arange(1, len(days) + 1, dtype=float)), "rate": np.arange(len(days), dtype=float)}, index=days)
    w = LG.weekly_last(lv)
    assert list(w.index) == list(pd.to_datetime(["2024-01-05", "2024-01-12", "2024-01-19"]))
    assert w["rate"].tolist() == [4.0, 8.0, 13.0]                              # 第二周取周四（那周最后一个有数据的日子）
    ch = LG.weekly_changes(w, {"oil"})
    assert ch["rate"].iloc[1] == 4.0 and ch["oil"].iloc[1] == pytest.approx((np.log(9) - np.log(5)) * 100)


def test_lag_direction():
    rng = np.random.default_rng(1)
    f = rng.standard_normal(600)
    y = _lead(f, 3, 0.8, rng)
    r, n = LG.lag_corr(f[:, None], y[:, None], [-3, 0, 3])
    assert r[2, 0, 0] > 0.5 and abs(r[0, 0, 0]) < 0.1 and abs(r[1, 0, 0]) < 0.1  # k = +3（因子领先）对上，k = −3 对不上
    assert n[2, 0, 0] == 597 and n[0, 0, 0] == 597 and n[1, 0, 0] == 600
    r2, _ = LG.lag_corr(f[:, None] * 5 + 100, y[:, None], [3])                # 上下平移、放大：相关不变
    assert r2[0, 0, 0] == pytest.approx(r[2, 0, 0])
    r3, _ = LG.lag_corr(y[:, None], f[:, None], [-3])                         # 股票领先 = 因子与股票对调后的负时间差
    assert r3[0, 0, 0] == pytest.approx(r[2, 0, 0])


def test_pairwise_missing_values():
    rng = np.random.default_rng(2)
    f = rng.standard_normal(600)
    y = 0.5 * f + rng.standard_normal(600)
    f[rng.random(600) < 0.1] = np.nan
    y[rng.random(600) < 0.1] = np.nan
    r, n = LG.lag_corr(f[:, None], y[:, None], [0])
    ok = np.isfinite(f) & np.isfinite(y)
    assert n[0, 0, 0] == ok.sum()
    assert r[0, 0, 0] == pytest.approx(np.corrcoef(f[ok], y[ok])[0, 1], abs=0.01)
    few = np.full(600, np.nan)
    few[:25] = rng.standard_normal(25)
    r, n = LG.lag_corr(few[:, None], y[:, None], [0])
    assert np.isnan(r[0, 0, 0]) and n[0, 0, 0] < 30                            # 成对的样本 < 30 → 缺值


def _panel(seed: int = 3):
    """3 个因子 × 4 只股票；只有 因子 1 → 股票 0 埋了「因子领先 3 周」，其余都是噪音。"""
    rng = np.random.default_rng(seed)
    F = rng.standard_normal((len(WEEKS), 3))
    R = rng.standard_normal((len(WEEKS), 4))
    R[:, 0] = _lead(F[:, 1], 3, 0.5, rng)
    return (pd.DataFrame(F, index=WEEKS, columns=["oil", "fx", "gold"]),
            pd.DataFrame(R, index=WEEKS, columns=["1111.T", "2222.T", "3333.T", "4444.T"]))


def test_planted_lead_found_replicated_and_not_in_placebo():
    F, R = _panel()
    A = LSD.scan(F, R)
    assert A["sel"]["found"][1, 0] and A["sel"]["k"][1, 0] == 3 and A["sel"]["r"][1, 0] > 0
    assert A["rep"][1, 0] and int(A["rep"].sum()) == 1                         # 只有埋进去的那一对复现
    assert A["best_d"][1, 0] == 3 and A["best_v"][1, 0] == 3
    T = len(F)
    shifts = [52 + k * (T - 104) // (LSD.N_PLACEBO - 1) for k in range(LSD.N_PLACEBO)]
    assert min(shifts) == 52 and max(shifts) == T - 52
    pl = [int(LSD.scan(pd.DataFrame(LG.roll_rows(F.to_numpy(), s), index=F.index, columns=F.columns), R)["rep"].sum()) for s in shifts]
    assert int(A["rep"].sum()) > max(pl)                                        # 判定：实际复现 > 对照的最大值


def test_discovery_only_pair_is_not_replicated():
    """只在发现期存在的关系（验证期消失）→ 发现但不复现。"""
    F, R = _panel()
    v = F.index >= pd.Timestamp(LSD.SPLIT)
    R.loc[v, "1111.T"] = np.random.default_rng(9).standard_normal(int(v.sum()))
    A = LSD.scan(F, R)
    assert A["sel"]["found"][1, 0] and not A["rep"][1, 0]


def test_select_leading_ignores_lagging_and_empty():
    rng = np.random.default_rng(4)
    f = rng.standard_normal(600)
    y = rng.standard_normal(600)
    y[:-3] += 0.8 * f[3:]                                                      # 股票领先因子 3 周（k = −3）→ 不能用来预测
    lags = list(range(-6, 7))
    r, n = LG.lag_corr(np.c_[f, np.full(600, np.nan)], y[:, None], lags)
    sel = LG.select_leading(r, n, lags, 3.0)
    assert LG.best_any(r, lags)[0, 0] == -3
    assert not sel["found"][0, 0] and sel["k"][0, 0] >= 1                     # 只在 k ≥ 1 里找
    assert not sel["found"][1, 0] and np.isnan(sel["t"][1, 0])                 # 整列缺值 → 不发现


def test_spurious_levels():
    idx = WEEKS
    t = np.arange(len(idx), dtype=float)
    d = idx < pd.Timestamp(LSD.SPLIT)
    rng = np.random.default_rng(5)
    L = pd.DataFrame({"updown": np.where(d, t, 2 * d.sum() - t) + rng.standard_normal(len(t)),       # 前半涨、后半跌
                      "up": t + rng.standard_normal(len(t))}, index=idx)
    S = pd.DataFrame({"s_up": 0.5 * t + rng.standard_normal(len(t)), "s_noise": rng.standard_normal(len(t))}, index=idx)
    z = LG.spurious_levels(L, S, pd.Timestamp(LSD.SPLIT))
    assert z == {"pairs": 4, "hi": 2, "hi_share": 50.0, "kept": 1, "kept_share": 50.0}  # 两条都在涨 → 很像；换一段时间只剩一半


def test_pair_score_uses_completed_weeks_only():
    Fw = pd.DataFrame({"oil": np.arange(len(WEEKS), dtype=float), "fx": np.ones(len(WEEKS))}, index=WEEKS)
    j = 500
    fri = WEEKS[j]
    dates = [fri - pd.Timedelta(days=1), fri, fri + pd.Timedelta(days=3), WEEKS[0] - pd.Timedelta(days=1)]
    s1 = LG.pair_score(Fw, [("oil", "7203.T", 1, 1.0)], {"oil": (0.0, 1.0)}, "7203.T", dates)
    assert s1[:3].tolist() == [j - 1, j, j] and np.isnan(s1[3])                # 周四信号用上一周；周五收盘这一周已完整
    s3 = LG.pair_score(Fw, [("oil", "7203.T", 3, -1.0)], {"oil": (10.0, 2.0)}, "7203.T", dates[:3])
    assert s3.tolist() == [-(j - 3 - 10) / 2, -(j - 2 - 10) / 2, -(j - 2 - 10) / 2]  # 领先 3 周 = 第 w − 2 周（w = 已完整的周）
    both = LG.pair_score(Fw, [("oil", "7203.T", 1, 1.0), ("oil", "7203.T", 3, -1.0), ("oil", "9984.T", 1, 1.0)],
                         {"oil": (0.0, 1.0)}, "7203.T", [fri])
    assert both.tolist() == [j - (j - 2)]                                      # 同一只票的几对相加；别的票的对不算
    assert np.isnan(LG.pair_score(Fw, [("oil", "9984.T", 1, 1.0)], {"oil": (0.0, 1.0)}, "7203.T", [fri])).all()
    assert LG.pair_score(Fw, [("fx", "7203.T", 1, 1.0)], {"fx": (1.0, 0.0)}, "7203.T", [fri]).tolist() == [0.0]  # 标准差 0 → 0
    later = Fw.copy()
    later.iloc[j + 1:] = 1e9                                                   # 改掉信号日以后的周 → 分数不变（不看未来）
    assert LG.pair_score(later, [("oil", "7203.T", 1, 1.0)], {"oil": (0.0, 1.0)}, "7203.T", dates[:3]).tolist() == s1[:3].tolist()


def test_lag_hist_bins_and_registered_constants():
    h = LSD.lag_hist(np.array([[0, 1, 4, 5, 13, 14, 26], [-1, -4, -5, -26, 0, 2, 3]]))
    assert h == {"0": 2, "因子领先 1〜4 周": 4, "因子领先 5〜13 周": 2, "因子领先 14〜26 周": 2, "股票领先 1〜4 周": 2, "股票领先 5〜26 周": 2}
    assert LSD.LAGS == list(range(-26, 27)) and (LSD.T_FIND, LSD.T_REP, LSD.N_PLACEBO) == (3.0, 2.0, 9)
    assert LSD.SPLIT == LSD.OOS0 == "2016-01-01"
