"""scripts/turn_shape_study.py（2026-10-05 登记）：登记值、周 / 月线只用已完成的 K 线（与 qbreak/mtf.bars 一致、不偷看）、
特征只用 t 收盘为止、起涨 / 起跌点与先到哪边的标注、RSI 与 qbreak/strategy.rsi 一致、连涨连跌、逻辑回归 / AUC / 当天分十组、判定方向。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import turn_shape_study as S  # noqa: E402
from qbreak import mtf  # noqa: E402
from qbreak.strategy import rsi  # noqa: E402


def test_registered_constants():
    assert (S.START, S.X_END, S.C_START) == ("2017-10-02", "2021-12-30", "2022-01-04")
    assert (S.STEP, S.HIST_MIN, S.VA_MIN, S.VA_N) == (5, 250, 1e7, 20)
    assert (S.H_LAB, S.EXT_WIN, S.SIG_N, S.M_K, S.M_LO, S.M_HI) == (40, 10, 60, 2.0, 0.10, 0.40)
    assert S.H_RET == (20, 40) and S.FWD_NEED == 41 and (S.L2, S.WINSOR) == (1.0, (1.0, 99.0))
    assert (S.AUC_MIN, S.AUC_INC, S.SPREAD_PP, S.TOP_INC_PP, S.YEARS_MIN, S.LARGE_N, S.N_DEC) == (0.55, 0.01, 1.0, 0.5, 4, 500, 10)
    assert (S.BOOT_N, S.SEED) == (2000, 20261005)
    assert len(S.DAILY) == 18 and len(S.WEEKLY) == 14 and len(S.MONTHLY) == 11 and len(S.FEATS) == 46 and len(set(S.FEATS)) == 46
    assert S.BASELINE == ["sig60", "lmc", "mom12", "d_r20"] and set(S.BASELINE) <= set(S.FEATS)
    assert S.MODELS == {"rise": ("RS", 1), "fall": ("FS", -1)}


def _panel(T=320, N=3, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2021-01-04", periods=T)
    C = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, size=(T, N)), axis=0))
    O = C * np.exp(rng.normal(0, 0.005, size=(T, N)))
    H = np.fmax(O, C) * (1 + np.abs(rng.normal(0, 0.01, size=(T, N))))
    L = np.fmin(O, C) * (1 - np.abs(rng.normal(0, 0.01, size=(T, N))))
    V = rng.integers(1000, 5000, size=(T, N)).astype(float)
    C[50:55, 1] = np.nan                                                       # 停牌
    O[50:55, 1] = H[50:55, 1] = L[50:55, 1] = V[50:55, 1] = np.nan
    return days, {"O": O, "H": H, "L": L, "C": C, "V": V}


def test_bar_panels_match_mtf_and_completed_only():
    days, P = _panel()
    for freq in ("W", "M"):
        B, cdays, pos = S.bar_panels(P, days, freq)
        for j in range(3):
            df = pd.DataFrame({"Open": P["O"][:, j], "High": P["H"][:, j], "Low": P["L"][:, j], "Close": P["C"][:, j], "Volume": P["V"][:, j]}, index=days)
            ref = mtf.bars(df, days, freq)
            got = pd.DataFrame({k: B[k[0]][:, j] for k in ("Open", "High", "Low", "Close", "Volume")}, index=cdays).dropna(subset=["Close"])
            assert np.allclose(got.loc[ref.index].to_numpy(), ref.to_numpy())
        assert cdays[-1] < days[-1] or freq == "W" and days[-1].weekday() < 4    # 最后一段（没完成）不算
        for t in range(len(days)):
            if pos[t] >= 0:
                assert cdays[pos[t]] <= days[t]                                # 只用当天收盘时已完成的
            if pos[t] + 1 < len(cdays):
                assert cdays[pos[t] + 1] > days[t]


def test_features_do_not_peek():
    days, P = _panel(seed=1)
    MC = np.full(P["C"].shape, 1000.0)
    t = 260
    P2 = {k: v.copy() for k, v in P.items()}
    for k in P2:
        P2[k][t + 1:] = P2[k][t + 1:] * 1.7 + 3                                  # 改 t 之后的数据
    f1 = dict(S.daily_features(P, MC))
    f2 = dict(S.daily_features(P2, MC))
    for k in f1:
        assert np.allclose(f1[k][t], f2[k][t], equal_nan=True), k
    for freq, prefix in (("W", "w"), ("M", "m")):
        B1, c1, p1 = S.bar_panels(P, days, freq)
        B2, c2, p2 = S.bar_panels(P2, days, freq)
        g1, g2 = S.bar_features(B1, prefix), S.bar_features(B2, prefix)
        for k in g1:
            assert np.allclose(S.on_days(g1[k], p1)[t], S.on_days(g2[k], p2)[t], equal_nan=True), k


def test_wilder_rsi_matches_strategy_and_run_len():
    days, P = _panel(seed=2)
    r = S.wilder_rsi(P["C"], 14)
    ref = rsi(pd.Series(P["C"][:, 0]), 14).to_numpy()
    assert np.allclose(r[:, 0], ref, equal_nan=True)
    C = np.array([[1.0], [2.0], [3.0], [3.0], [2.0], [1.0], [np.nan], [5.0]])
    assert S.run_len(C)[:, 0].tolist()[1:] == [1, 2, 0, -1, -2, 0, 0]
    up = np.arange(1.0, 20.0)[:, None]
    assert S.run_len(up)[-1, 0] == 7                                           # 封顶


def test_first_pass_and_labels():
    Cf = np.array([[100.0], [104.0], [96.0], [111.0], [80.0]])
    hu, hd = S.first_pass(Cf, np.full_like(Cf, 100.0), np.full_like(Cf, 1.10), np.full_like(Cf, 0.95), h=4)
    assert hu[0, 0] == 3 and hd[0, 0] == 4                                    # 第 3 天先到 +10%、第 4 天才到 −5%
    T = 200
    C = np.r_[np.linspace(100, 90, 100), np.linspace(90, 160, 100)][:, None]
    C = C * (1 + 0.004 * np.sin(np.arange(T)))[:, None]                        # 有一点波动（σ > 0）
    O = C.copy()
    L_ = S.labels({"O": O, "C": C})
    k0 = int(np.nanargmin(C[:, 0]))
    assert L_["RS"][k0, 0] and not L_["FS"][k0, 0]                            # 最低点 = 起涨点
    assert np.isfinite(L_["M"][k0, 0]) and S.M_LO <= L_["M"][k0, 0] <= S.M_HI
    assert not L_["RS"][-5:, 0].any()                                          # 后面不够 40 日 → 不标
    C2 = np.r_[np.linspace(100, 160, 100), np.linspace(160, 90, 100)][:, None] * (1 + 0.004 * np.sin(np.arange(T)))[:, None]
    L2 = S.labels({"O": C2, "C": C2})
    k1 = int(np.nanargmax(C2[:, 0]))
    assert L2["FS"][k1, 0] and not L2["RS"][k1, 0]                            # 最高点（之后大跌）= 起跌点
    assert not L2["FS"][:60, 0].any()                                          # 前面波动还算不出来（σ 要 60 日）→ 不标


def test_logit_auc_deciles():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(20000, 2))
    y = (rng.random(20000) < 1 / (1 + np.exp(-(-1.0 + 1.5 * X[:, 0])))).astype(float)
    w = S.fit_logit(X, y)
    assert abs(w[1] - 1.5) < 0.1 and abs(w[2]) < 0.1 and abs(w[0] + 1.0) < 0.1
    assert S.auc(np.array([0.1, 0.4, 0.35, 0.8]), np.array([0, 0, 1, 1])) == 0.75
    assert S.auc(np.array([1.0, 2.0]), np.array([0, 0])) is None
    day = np.repeat(np.arange(3), 20)
    dec = S.deciles_by_day(np.tile(np.arange(20.0), 3), day)
    assert dec[:20].tolist() == [i // 2 for i in range(20)] and dec.max() == 9
    Xs, st = S.winsor_std(X, X)
    assert np.allclose(Xs.mean(0), 0, atol=0.02) and np.allclose(S.apply_std(X, st), Xs)


def test_judge_direction():
    top, bot, base = {"R20x": 1.6}, {"R20x": -0.2}, {"R20x": 0.9}
    yrs = {2022: {"n": 10, "R20x": 1.0}, 2023: {"n": 10, "R20x": 0.5}, 2024: {"n": 10, "R20x": -0.1}, 2025: {"n": 10, "R20x": 2.0}, 2026: {"n": 5, "R20x": 0.3}}
    j = S.judge(1, 0.62, 0.60, top, bot, (0.004, 0.028), base, yrs, {"top": 0.8, "bottom": 0.1})
    assert all(j["gates"].values()) and j["tier"].startswith("图形有用")
    j2 = S.judge(1, 0.62, 0.615, top, bot, (0.004, 0.028), base, yrs, {"top": 0.8, "bottom": 0.1})   # AUC 只多 0.005
    assert not j2["gates"]["G2"] and j2["tier"].startswith("有信息")
    jf = S.judge(-1, 0.6, 0.58, {"R20x": -1.5}, {"R20x": 0.2}, (-0.025, -0.006), {"R20x": -0.8},
                 {y: {"n": 10, "R20x": -v["R20x"]} for y, v in yrs.items()}, {"top": -0.6, "bottom": 0.3})
    assert all(jf["gates"].values()) and jf["s_ci_lo_pp"] == 0.6
    jx = S.judge(1, 0.5, 0.5, {"R20x": 0.1}, {"R20x": 0.0}, (-0.01, 0.01), {"R20x": 0.1}, yrs, {})
    assert jx["tier"] == "没有用"
