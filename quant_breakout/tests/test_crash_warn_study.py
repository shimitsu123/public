"""scripts/crash_warn_study.py 的纯函数：因子不偷看、目标、AUC、逐年前推只用之前的数据、预警门槛、读法、回撤段的预警。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import crash_warn_study as S  # noqa: E402


def _px(n, seed, start="1990-01-01", vol=0.012):
    rng = np.random.default_rng(seed)
    d = pd.bdate_range(start, periods=n)
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, vol, n))), index=d)


def _inputs(n=900):
    nd = _px(n, 0)
    d = nd.index
    mon = pd.date_range(d[0] - pd.offsets.MonthBegin(24), d[-1], freq="MS")
    return dict(days=d, ndx=nd, spx=_px(n, 1), rut=_px(n, 2), vix=_px(n, 3) / 5, skew=_px(n, 4), baa10y=_px(n, 5) / 50,
                dgs10=_px(n, 6) / 25, dgs3m=_px(n, 7) / 40, wti=_px(n, 8) / 3, unrate=pd.Series(np.linspace(4, 6, len(mon)), index=mon),
                usdjpy=_px(n, 9), jp_short=pd.Series(0.1, index=mon))


def test_features_do_not_peek():
    I = _inputs()
    full = S.features(**I)
    assert list(full.columns) == S.FEATS and len(S.FEATS) == 23
    for i in (400, 650, 899):
        cut = {k: (v[v.index <= I["days"][i]] if isinstance(v, pd.Series) else v[:i + 1]) for k, v in I.items()}
        part = S.features(**cut)
        assert np.allclose(full.iloc[i].to_numpy(float), part.iloc[-1].to_numpy(float), equal_nan=True), i


def test_lagged_inputs():
    I = _inputs()
    f = S.features(**I)
    i = 500
    t10, t3 = I["dgs10"], I["dgs3m"]
    assert np.isclose(f["curve"].iloc[i], t10.iloc[i - 1] - t3.iloc[i - 1])                    # FRED 滞后 1 天
    fx = I["usdjpy"]
    assert np.isclose(f["yen20"].iloc[i], -(fx.iloc[i - 1] / fx.iloc[i - 21] - 1) * 100)
    assert np.isclose(f["vix"].iloc[i], I["vix"].iloc[i])                                       # VIX 当天收盘


def test_crash_label():
    j = pd.Series([100, 99, 95, 91, 93, 100, 101, 102], index=pd.bdate_range("2020-01-06", periods=8), dtype=float)
    y = S.crash_label(j, h=3, thr=-8.0)
    assert y.iloc[0] == 1.0 and y.iloc[1] == 1.0 and y.iloc[2] == 0.0                         # 91/100 = −9%、91/99 = −8.08%、91/95 = −4.2%
    assert np.isnan(y.iloc[-3:]).all()


def test_auc():
    assert S.auc([1, 2, 3, 4], [0, 0, 1, 1]) == 1.0 and S.auc([4, 3, 2, 1], [0, 0, 1, 1]) == 0.0
    assert S.auc([1, 1, 1, 1], [0, 1, 0, 1]) == 0.5 and S.auc([1, 2], [0, 0]) is None


def test_fwd_uses_only_past_rows(monkeypatch):
    d = pd.bdate_range("1995-01-02", "2003-12-31")
    F = pd.DataFrame({c: np.random.default_rng(0).normal(size=len(d)) for c in S.FEATS}, index=d)
    y = pd.Series((np.random.default_rng(1).random(len(d)) < 0.1).astype(float), index=d)
    bull = pd.Series(True, index=d)
    seen = []

    def fake(kind, Xtr, ytr, Xs):
        seen.append(len(Xtr))
        return [np.full(len(x), float(len(Xtr))) for x in Xs]
    monkeypatch.setattr(S, "fit_predict", fake)
    s, w = S.fwd_signal("gbm", S.FEATS, F, y, bull, years=range(2001, 2004))
    for k, Y in enumerate(range(2001, 2004)):
        n = int(((d >= pd.Timestamp(S.TRAIN_FROM)) & (d <= S.fwd_cutoff(Y))).sum())
        assert seen[k] == n
        assert np.allclose(s[d.year == Y].iloc[S.SMOOTH:], n)                                 # 每年用当年的模型
    assert s[d.year < 2001].isna().all() and not w[d.year < 2001].any()
    assert S.fwd_cutoff(2001) == pd.Timestamp("2000-09-03")


def test_threshold_is_in_sample_q85():
    d = pd.bdate_range("2000-01-03", periods=400)
    F = pd.DataFrame({"rv20": np.arange(400, dtype=float)}, index=d)
    y = (F["rv20"] > 250).astype(float)
    bull = pd.Series(True, index=d)
    m_tr = np.r_[np.ones(300, bool), np.zeros(100, bool)]
    s, thr = S.score_block("ridge", ["rv20"], F, y, bull, m_tr, ~m_tr)
    assert len(s) == 100 and np.isfinite(thr) and (s >= thr).all()                             # 线性外推：之后都比门槛高


def test_a1_and_verdict_and_constants():
    r = S.a1_reading({"O": 0.70, "Z": 0.66, "E": 0.62, "J": 0.60}, {"O": 0.65, "Z": 0.64, "E": 0.63, "J": 0.55})
    assert r["pos"] == 3 and np.isclose(r["mean"], 0.0275) and not r["ok"]
    assert S.a1_reading({"O": 0.7, "Z": 0.7, "E": 0.7, "J": 0.6}, {"O": 0.6, "Z": 0.6, "E": 0.6, "J": 0.61})["ok"]
    assert S.verdict({"ok": False}, None) == "第一关不过" and S.verdict({"ok": True}, {"pass": False}) == "第二关不过"
    assert S.verdict({"ok": True}, {"pass": True}).startswith("更好候选")
    assert S.H == 20 and S.CRASH == -8.0 and S.Q_WARN == 0.85 and S.SMOOTH == 5 and S.GBM["n_trees"] == 200 and S.GBM["loss"] == "logloss"
    assert S.CANDS == ("MFW", "MFL") and S.MODELS["MFV"][1] == ["rv20"] and S.PLACEBO_N == 400


def test_episode_warn():
    d = pd.bdate_range("2020-01-01", periods=60)
    sig = pd.Series(False, index=d)
    sig.iloc[25:28] = True
    x = S.episode_warn(sig, d[20], d[40])
    assert x["warned"] and x["lead"] == 15 and np.isclose(x["share"], 3 / 21 * 100, atol=0.05)
    assert not S.episode_warn(sig, d[45], d[55])["warned"]
    assert S.episode_warn(sig, d[30], d[40], lead_days=10)["warned"]                          # 前高之前 10 天里的预警也算
