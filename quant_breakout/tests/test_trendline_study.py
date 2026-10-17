"""趋势线研究（scripts/trendline_study.py，登记版）：每只票的旗子没有用到未来的 K 线（日线 / 周线）、按月聚类的标准误、A 部分的判定、
事件日 → exit_tick 的格式。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import trendline_study as T                                                  # noqa: E402


def _df(n=700, seed=3):
    rng = np.random.default_rng(seed)
    c = 1000 * np.exp(np.cumsum(rng.normal(0.0003, 0.018, n)))
    idx = pd.bdate_range("2018-01-01", periods=n)
    return pd.DataFrame({"Open": c * (1 + rng.normal(0, 0.003, n)), "High": c * (1 + rng.random(n) * 0.012),
                         "Low": c * (1 - rng.random(n) * 0.012), "Close": c}, index=idx)


def test_ticker_flags_use_no_future_bars():
    df = _df()
    full = T.ticker_flags(df)
    cols = [c for c in full.columns if c != "fwd"]
    for cut in (300, 452, 640):
        end = df.index[cut]
        while end.weekday() != 4:                                            # 截到星期五（最后一周是完整的）
            cut += 1
            end = df.index[cut]
        part = T.ticker_flags(df.iloc[:cut + 1])
        a, b = full.loc[part.index, cols], part[cols]
        for c in cols:
            x = np.nan_to_num(a[c].to_numpy(float), nan=-1e9)
            y = np.nan_to_num(b[c].to_numpy(float), nan=-1e9)
            assert np.allclose(x, y, atol=1e-6), (cut, c)
    fwd = full["fwd"].to_numpy(float)
    c, o = df["Close"].to_numpy(), df["Open"].to_numpy()
    assert abs(fwd[100] - (c[100 + T.H] / o[101] - 1) * 100) < 1e-3 and np.isnan(fwd[-1])


def test_weekly_events_sit_on_the_last_trading_day_of_the_week():
    f = T.ticker_flags(_df(900, seed=8))
    for col in ("w_sb_evt", "w_sb_evt_new", "w_rb_evt_new"):
        d = f.index[f[col].to_numpy(bool)]
        assert len(d) == 0 or all(x.weekday() == 4 for x in d)              # 合成行情没有休市：每周最后一天 = 星期五
    assert (f["w_sb_evt_new"] <= f["w_sb_evt"]).all()


def test_cluster_mean_matches_hand_calculation():
    x = np.array([1.0, 2.0, 3.0, 4.0, np.nan])
    m = np.array(["a", "a", "b", "b", "b"])
    r = T.cluster_mean(x, m)
    mu = 2.5
    g = np.array([(1 - mu) + (2 - mu), (3 - mu) + (4 - mu)])
    se = np.sqrt((g ** 2).sum()) / 4
    assert r["n"] == 4 and r["clusters"] == 2 and abs(r["mean"] - mu) < 1e-9 and abs(r["se"] - round(se, 4)) < 1e-9
    assert abs(r["lo"] - round(mu - 1.96 * se, 4)) < 1e-9


def test_judge_a_needs_every_sample_and_the_pooled_bound():
    def block(v, lo=0.1, hi=0.9):
        return {"mean": v, "lo": lo, "hi": hi, "n": 100}
    a = {"A1": {s: {"tl": block(0.4), "diff": block(0.1)} for s in T.SAMPLES},
         "A2": {s: {k: block(0.5) for k in T.EVENTS_BUY} for s in T.SAMPLES},
         "A3": {s: {k: block(-0.5, -0.9, -0.1) for k in T.EVENTS_SELL} for s in T.SAMPLES},
         "pooled": {"tl": block(0.4), "diff": block(0.1, 0.01, 0.2), **{k: block(0.5) for k in T.EVENTS_BUY},
                    **{k: block(-0.5, -0.9, -0.1) for k in T.EVENTS_SELL}}}
    j = T.judge_a(a)
    assert j["A1_predict"] and j["A1_beats_ma"] and all(j[k] for k in (*T.EVENTS_BUY, *T.EVENTS_SELL))
    a["A1"]["Zx"]["tl"] = block(-0.01)                                       # 有一个样本 ≤ 0 → ① 不过
    a["pooled"]["TU"] = block(0.2)                                           # 合起来不到 0.3 pp → 不过
    a["A1"]["Z"]["diff"] = block(-0.1)
    a["A1"]["E"]["diff"] = block(-0.1)                                       # 只有 4 个样本 > 0 → ② 不过
    j = T.judge_a(a)
    assert not j["A1_predict"] and not j["TU"] and j["TR"] and not j["A1_beats_ma"]


def test_event_ticks_and_lookup():
    idx = pd.bdate_range("2024-01-01", periods=5)
    FL = {"A.T": pd.DataFrame({"d_sb": [False, True, False, True, False]}, index=idx),
          "B.T": pd.DataFrame({"d_sb": [False] * 5}, index=idx)}
    tk = T.event_ticks(FL, "d_sb")
    assert set(tk) == {"A.T"} and tk["A.T"] == frozenset([idx[1], idx[3]])
    assert T.lookup(FL, "d_sb", ["A.T", "A.T", "C.T"], [idx[1], idx[2], idx[1]]).tolist() == [True, False, False]
    assert T.event_ticks(FL, "d_sb", only={"B.T"}) == {}


def test_same_b4_tolerates_tiny_data_drift_only():
    ref = {"n": 34, "win": 50.0, "calmar": 0.627}
    assert T.same_b4({"n": 34, "win": 50.0, "calmar": 0.628}, ref)
    assert not T.same_b4({"n": 35, "win": 50.0, "calmar": 0.627}, ref)
    assert not T.same_b4({"n": 34, "win": 51.0, "calmar": 0.627}, ref)
    assert not T.same_b4({"n": 34, "win": 50.0, "calmar": 0.64}, ref)
