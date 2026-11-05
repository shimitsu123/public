"""买点信号质量「新角度」一轮（scripts/buyq_common.py / buyq_study.py）：特征不看未来、数值正确；统计、入选、确认的规则。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import buyq_common as BQ                                                     # noqa: E402
import buyq_study as BS                                                      # noqa: E402


def _walk(n, phi=0.0, seed=1, sd=0.01):
    rng = np.random.default_rng(seed)
    e = rng.normal(0, sd, n)
    r = np.zeros(n)
    for t in range(1, n):
        r[t] = phi * r[t - 1] + e[t]
    return 100 * np.exp(np.cumsum(r))


def _frame(n=400, seed=3):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    h, lo = c * (1 + rng.uniform(0, 0.01, n)), c * (1 - rng.uniform(0, 0.01, n))
    v = rng.uniform(5e5, 2e6, n)
    idx = pd.bdate_range("2015-01-05", periods=n)
    df = pd.DataFrame({"Open": c, "High": h, "Low": lo, "Close": c, "Volume": v}, index=idx)
    df["vol_ratio"] = df["Volume"] / df["Volume"].rolling(20).mean()
    return df


# ───────────────────────── 特征 ─────────────────────────
def test_variance_ratio_random_walk_trend_and_reversion():
    assert abs(BQ.variance_ratio(_walk(2000, 0.0)) - 1) < 0.25
    assert BQ.variance_ratio(_walk(2000, 0.3)) > 1.3
    assert BQ.variance_ratio(_walk(2000, -0.3)) < 0.75
    assert np.isnan(BQ.variance_ratio(_walk(150)))                          # 日收益 < 200 个


def test_follow_through_only_known_events_and_value():
    n = 300
    c = np.full(n, 100.0)
    vr = np.ones(n)
    m = np.ones(n)
    ev = [50, 80, 110, 140, 170, 200]
    for e in ev:                                                             # 事件日涨 2%、量比 2；之后 10 日再涨 5%（大盘不动）
        c[e:] *= 1.02
        vr[e] = 2.0
        c[e + 10:] *= 1.05
    i = 215                                                                  # 最后一个事件 200 + 10 ≤ 215 → 6 个都算
    assert BQ.follow_through(c, vr, m, i) == pytest.approx(0.05, abs=1e-9)
    assert np.isnan(BQ.follow_through(c, vr, m, 205))                        # 200 + 10 > 205 → 只有 5 个 → NaN
    c2 = c.copy()
    c2[i + 1:] *= 3                                                          # 改信号日之后的价格 → 不变
    assert BQ.follow_through(c2, vr, m, i) == BQ.follow_through(c, vr, m, i)
    m2 = m.copy()
    m2[60:] *= 1.05                                                          # 第一个事件之后 10 日里大盘也涨 5% → 那个事件 0
    assert BQ.follow_through(c, vr, m2, i) == pytest.approx(0.05 * 5 / 6, abs=1e-9)


def test_down_rel():
    n = 200
    r = np.zeros(n)
    rm = np.zeros(n)
    rm[[150, 160, 170, 180, 190]] = -0.02
    r[[150, 160, 170, 180, 190]] = -0.01                                     # 大盘跌 2% 的日子只跌 1% → +1%
    assert BQ.down_rel(r, rm, 199) == pytest.approx(0.01)
    assert np.isnan(BQ.down_rel(r, rm, 185))                                 # 只有 4 天
    rm[100] = -0.03                                                          # 第 100 天在窗口（80〜199）里、跌得和大盘一样
    r[100] = -0.03
    assert BQ.down_rel(r, rm, 199) == pytest.approx(0.05 / 6)                # 5 × 1% / 6 天


def test_box_features():
    n = 80
    i = 70
    c = np.full(n, 100.0)
    h = np.full(n, 101.0)
    lo = np.full(n, 99.0)
    lo[15] = 95.0                                                            # 前段（i−60〜i−21）最低 95；后 20 日最低 99 → 抬高
    h[[20, 21, 35, 60]] = 110.0                                              # 箱顶 110：20〜21 算一次、35、60 → 3 次
    c[i - 20:i] = 106.0                                                      # 箱体中点 (110 + 95) / 2 = 102.5 → 后 20 日全在上半部
    x = BQ.box_features(h, lo, c, i)
    assert x["hlow"] == pytest.approx(99 / 95 - 1)
    assert x["touch"] == 3
    assert x["upper"] == 1.0
    h2, c2 = h.copy(), c.copy()
    h2[i:] = 500.0                                                           # 信号日本身与之后不进箱体
    c2[i:] = 1.0
    assert BQ.box_features(h2, lo, c2, i) == x
    assert np.isnan(BQ.box_features(h, lo, c, 59)["touch"])


def test_vol_pct():
    vr = np.r_[np.linspace(0.5, 1.5, 200), 1.4]
    assert BQ.vol_pct(vr, 200) == pytest.approx(np.mean(np.linspace(0.5, 1.5, 200) < 1.4))
    assert np.isnan(BQ.vol_pct(vr[-100:], 99))                               # 过去不到 120 个


def test_stock_features_do_not_look_ahead():
    df = _frame()
    mret, mcum = BQ.market_proxy(df[["Close"]].to_numpy(), df.index)
    i = 320
    a = BQ.stock_features(df, i, mret.to_numpy(), mcum.to_numpy())
    d2 = df.copy()
    d2.iloc[i + 1:, :] = d2.iloc[i + 1:, :] * 7
    b = BQ.stock_features(d2, i, mret.to_numpy(), mcum.to_numpy())
    assert set(a) == {"vr10", "follow", "downrel", "hlow", "touch", "upper", "vpct"}
    for k in a:
        assert (np.isnan(a[k]) and np.isnan(b[k])) or a[k] == b[k]


def test_market_proxy_equal_weight_skips_missing():
    C = np.array([[100, 50.0, np.nan], [110, 50.0, 10.0], [110, 55.0, 11.0]])
    ret, cum = BQ.market_proxy(C, pd.bdate_range("2020-01-06", periods=3))
    assert np.isnan(ret.iloc[0])
    assert ret.iloc[1] == pytest.approx(0.05)                                # (10% + 0%) / 2（第三只前一天没有收盘）
    assert ret.iloc[2] == pytest.approx(0.2 / 3)                             # (0% + 10% + 10%) / 3
    assert cum.iloc[-1] == pytest.approx(1.05 * (1 + 0.2 / 3))


def test_peer_counts_same_sector_past_window_only():
    days = pd.bdate_range("2020-01-06", periods=40)
    S = pd.DataFrame({"ticker": ["1111.T", "2222.T", "3333.T", "2222.T", "4444.T", "1111.T"],
                      "date": [days[0], days[5], days[9], days[20], days[5], days[30]]})
    sector = {"1111": "A", "2222": "A", "3333": "A", "4444": "B"}
    pc = BQ.peer_counts(S, days, sector)
    assert list(pc) == [0, 1, 2, 0, 0, 0]                                    # 3333（第 9 天）：1111（第 0 天）与 2222（第 5 天）都在 10 天内
    pc2 = BQ.peer_counts(S.assign(ticker=["1111.T", "9999.T", "3333.T", "2222.T", "4444.T", "1111.T"]), days, sector)
    assert np.isnan(pc2[1]) and pc2[2] == 1                                  # 业种不明 → NaN、也不算别人的同业


def test_keep_of_missing_is_kept():
    F = pd.DataFrame({c: [np.nan, 0.5, 2.0] for c in BQ.FEATURES})
    assert list(BQ.keep_of(F, "Q1")) == [True, False, True]
    assert list(BQ.keep_of(F, "Q4")) == [True, True, True]
    assert list(BQ.keep_of(F, "Q8")) == [True, False, False]


# ───────────────────────── 统计 ─────────────────────────
def test_delta_boot_and_placebo():
    net = np.array([5.0, -2, 3, -1, 4, -3, 2, -2])
    keep = np.array([True, False, True, False, True, True, True, False])
    d = BQ.delta(net, keep)
    assert d["n"] == 8 and d["kept"] == 5 and d["frac"] == pytest.approx(5 / 8)
    assert d["win_all"] == pytest.approx(50.0) and d["win"] == pytest.approx(80.0) and d["dwin"] == pytest.approx(30.0)
    assert d["dmean"] == pytest.approx(net[keep].mean() - net.mean())
    assert d["mean_rm"] == pytest.approx(net[~keep].mean())
    months = np.array(["a", "a", "b", "b", "c", "c", "d", "d"])
    b1 = BQ.boot_delta(net, keep, months, n=300)
    assert b1 == BQ.boot_delta(net, keep, months, n=300)                    # 种子固定 → 可重现
    assert b1["dmean_lo"] <= d["dmean"] <= b1["dmean_hi"]
    rng = np.random.default_rng(0)
    big = rng.normal(0.5, 5, 3000)
    pl = BQ.placebo(big, np.array([f"t{i % 300}" for i in range(3000)]), np.array([f"w{i % 97}" for i in range(3000)]), 0.6, n=200)
    assert 0 < pl["dmean_q95"] < 0.5 and 0 < pl["dwin_q95"] < 5


def test_spearman():
    x = np.arange(20.0)
    assert BQ.spearman(x, x ** 3) == pytest.approx(1.0)
    assert np.isnan(BQ.spearman(x[:5], x[:5]))


# ───────────────────────── 入选与确认 ─────────────────────────
def _good():
    j2 = {"frac": 0.6, "dwin": 2.5, "dmean": 0.3, "dmean_q95": 0.2}
    e = {"frac": 0.5, "dwin": 0.1, "dmean": 0.0}
    base = {"E": {"calmar": 0.30, "dd": -30.0}, "J": {"calmar": 0.40, "dd": -35.0}}
    port = {"E": {"calmar": 0.285, "dd": -31.5}, "J": {"calmar": 0.39, "dd": -36.9}}
    return j2, e, port, base


def test_qualifies_each_condition():
    j2, e, port, base = _good()
    assert BQ.qualifies(j2, e, port, base) == []
    assert BQ.qualifies({**j2, "frac": 0.95}, e, port, base)
    assert BQ.qualifies(j2, {**e, "frac": 0.2}, port, base)
    assert BQ.qualifies({**j2, "dwin": 1.9}, e, port, base)
    assert BQ.qualifies({**j2, "dmean": 0.19, "dmean_q95": 0.1}, e, port, base)
    assert BQ.qualifies({**j2, "dmean_q95": 0.3}, e, port, base)             # 没超过随机 95 分位
    assert BQ.qualifies(j2, {**e, "dmean": -0.01}, port, base)
    assert BQ.qualifies(j2, e, {**port, "E": {"calmar": 0.279, "dd": -30.0}}, base)
    assert BQ.qualifies(j2, e, {**port, "J": {"calmar": 0.40, "dd": -37.1}}, base)
    assert BQ.qualifies({}, e, port, base)                                   # 缺数据 → 不入选


def test_pick_rank_family_cap_and_max():
    res = {k: {"fails": [], "j2": {"dmean": v}} for k, v in
           {"Q1": 0.5, "Q2": 0.6, "Q3": 0.7, "Q4": 0.4, "Q7": 0.3, "Q8": 0.9, "Q5": 0.8}.items()}
    res["Q6"] = {"fails": ["x"], "j2": {"dmean": 5.0}}
    assert BQ.pick(res) == ["Q8", "Q5", "Q3"]
    res["Q8"]["fails"] = ["x"]
    res["Q5"]["fails"] = ["x"]
    assert BQ.pick(res) == ["Q3", "Q2", "Q4"]                               # A 族（Q3、Q2）最多 2 个 → Q1 让给 Q4


def test_verdict():
    c = {"dmean_lo": 0.01, "dwin": 1.2, "dmean": 0.4}
    assert BQ.verdict(c, {"dmean": 0.0}, {"dmean": 0.3}) == "确认"
    assert BQ.verdict(c, {"dmean": -0.1}, {"dmean": 0.3}) == "方向一致"
    assert BQ.verdict({**c, "dmean_lo": -0.01}, {"dmean": 0.1}, {"dmean": 0.3}) == "方向一致"
    assert BQ.verdict({**c, "dwin": 0.9}, {"dmean": 0.1}, {"dmean": 0.3}) == "方向一致"
    assert BQ.verdict({**c, "dmean_lo": -0.5, "dwin": -0.1}, {}, {}) == "不通过"
    assert BQ.verdict({}, {}, {}) == "不通过"


def test_study_masks_and_per_set():
    days = pd.bdate_range("2020-01-06", periods=10)
    fa = {"1111.T": pd.DataFrame(index=days), "2222.T": pd.DataFrame(index=days)}
    Sall = pd.DataFrame({"ticker": ["1111.T", "2222.T"], "date": [days[2], days[4]], **{c: [np.nan, np.nan] for c in BQ.FEATURES}})
    Sall.loc[0, "vr10"] = 0.5                                                # Q1 不通过 → 那天 False
    m = BS.masks(fa, Sall, "Q1")
    assert m["1111.T"].sum() == 9 and not m["1111.T"][2] and m["2222.T"].all()
    S = Sall.assign(net=[1.0, -1.0], week=["w1", "w2"])
    st = BS.per_set(S)
    assert st["Q1"]["kept"] == 1 and st["Q1"]["dmean"] == pytest.approx(-1.0) and st["Q2"]["frac"] == 1.0
