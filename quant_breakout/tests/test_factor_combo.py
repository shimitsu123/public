"""qbreak/factor_combo.py + scripts/factor_combo_study.py（全部因子的组合网罗）：组合个数、AUC 与平局、平衡准确率、方向只在发现期定、
经验 p 值、BH、同一偏移的随机对照、剔除跨时段的样本、门槛；再用合成数据走一遍「真实 + 对照」：有信息的因子能过、纯随机的几乎过不了。"""
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qbreak import factor_combo as FC                                        # noqa: E402
import factor_combo_study as FS                                              # noqa: E402


def test_combo_counts_match_registration():
    tot = {n: sum(FC.n_combos(n, 3).values()) for n in (47, 29, 30)}
    assert tot == {47: 17_343, 29: 4_089, 30: 4_525}
    assert tot[47] + 4 * tot[29] + 2 * tot[30] == 42_749                    # 登记写的总数
    assert len(FS.MARKET) == 30 and len(FS.STOCK) + len(FS.EXTRA) == 17 and len(FS.TARGETS) == 7
    c = FC.enumerate_combos(5, 3)
    assert len(c) == 5 + 10 + 10 and len(set(c)) == len(c) and all(list(x) == sorted(x) for x in c)


def _auc_brute(s, y):
    pos, neg = s[y == 1], s[y == 0]
    gt = (pos[:, None] > neg[None, :]).sum()
    eq = (pos[:, None] == neg[None, :]).sum()
    return (gt + 0.5 * eq) / (len(pos) * len(neg))


def test_auc_matches_pairwise_count_with_ties_and_skips_nan():
    rng = np.random.default_rng(1)
    s = rng.integers(0, 6, 300).astype(float)                                # 很多平局
    y = (rng.random(300) < 0.3 + 0.05 * s).astype(float)
    a, n1, n0 = FC.auc(s, y)
    assert abs(a - _auc_brute(s, y)) < 1e-12 and n1 + n0 == 300
    s2, y2 = s.copy(), y.copy()
    s2[:10], y2[10:20] = np.nan, np.nan
    a2, n1b, n0b = FC.auc(s2, y2)
    keep = np.isfinite(s2) & np.isfinite(y2)
    assert abs(a2 - _auc_brute(s2[keep], y2[keep])) < 1e-12 and n1b + n0b == 280
    assert np.isnan(FC.auc(np.arange(5.0), np.ones(5))[0])                   # 只有一类 → NaN
    assert FC.auc(np.array([1.0, 2, 3, 4]), np.array([0.0, 0, 1, 1]))[0] == 1.0


def test_balanced_accuracy_and_threshold():
    s = np.array([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    y = np.array([0, 0, 0, 1, 0, 1, 1, 1], float)
    assert FC.balanced_accuracy(s, y, 0.5) == (3 / 4 + 3 / 4) / 2
    rng = np.random.default_rng(2)
    sd = rng.normal(size=2000)
    yd = (rng.random(2000) < 0.2).astype(float)
    thr = FC.ba_threshold(sd, yd)
    assert abs((sd >= thr).mean() - yd.mean()) < 0.01                       # 判为正的比例 ≈ 发现期正例比例
    assert np.isnan(FC.ba_threshold(sd[:10], yd[:10]))                       # 样本太少
    assert np.isnan(FC.ba_threshold(sd, np.zeros(2000)))


def test_directions_use_discovery_only_and_signed():
    rng = np.random.default_rng(3)
    n = 1000
    y = (rng.random(n) < 0.3).astype(float)
    P = pd.DataFrame({"up": y + rng.normal(0, 1, n), "down": -y + rng.normal(0, 1, n)})
    P = P.rank(pct=True)
    disc = np.arange(n) < 500
    sg = FC.directions(P, pd.Series(y), disc)
    assert sg == {"up": 1, "down": -1}
    P2 = P.copy()
    P2.loc[500:, "up"] = 1 - P2.loc[500:, "up"]                              # 只改验证期 → 方向不变
    assert FC.directions(P2, pd.Series(y), disc) == sg
    A = FC.signed(P, sg)
    assert np.allclose(A[:, 1], 1 - P["down"].to_numpy()) and np.allclose(A[:, 0], P["up"].to_numpy())
    A[3, 0] = np.nan
    s = FC.combo_score(A, (0, 1))
    assert np.isnan(s[3]) and np.isfinite(s[4])                              # 任一因子缺值 → 没有分数


def test_empirical_p_and_bh():
    null = np.arange(1, 101, dtype=float)                                    # 1〜100
    p = FC.empirical_p(np.array([200.0, 100.0, 50.5, 0.0, np.nan]), null)
    assert np.allclose(p, [1 / 101, 2 / 101, 51 / 101, 101 / 101, 1.0])
    assert FC.bh(np.array([0.01, 0.04, 0.03, 0.2]), 0.05).tolist() == [True, False, False, False]
    assert FC.bh(np.array([0.001, 0.03, 0.035, 0.04]), 0.05).all()           # step-up：后面的过了，前面的也算
    assert FC.bh(np.array([0.2, 0.5]), 0.05).tolist() == [False, False] and FC.bh(np.array([]), 0.05).size == 0


def test_shift_rows_moves_all_factors_together():
    rng = np.random.default_rng(4)
    A = rng.normal(size=(50, 3))
    A[:, 2] = A[:, 0] * 2 + 1                                               # 因子之间的关系
    B = FC.shift_rows(A, 7)
    assert np.allclose(B[7:], A[:-7]) and np.allclose(B[:7], A[-7:])
    assert np.allclose(B[:, 2], B[:, 0] * 2 + 1)                             # 同一偏移 → 因子之间的结构不变


def test_purge_mask_drops_windows_crossing_the_boundary():
    d = pd.DatetimeIndex(["2015-12-01", "2015-12-20", "2016-01-05", "2016-02-01"])
    he = pd.DatetimeIndex(["2015-12-28", "2016-01-10", "2016-02-01", pd.NaT])
    assert FC.purge_mask(d, "2006-10-01", "2015-12-31", he).tolist() == [True, False, False, False]
    assert FC.purge_mask(d, "2016-01-01", "2023-09-30", he).tolist() == [False, False, True, False]   # 结果还没出来（NaT）也剔除
    assert FC.purge_mask(d, "2016-01-01", "2023-09-30").tolist() == [False, False, True, True]


def test_gate_stats():
    R = pd.DataFrame({"p": [0.0001, 0.0001, 0.0001, 0.5], "disc_auc": [0.6, 0.45, 0.7, 0.7],
                      "val_auc": [0.62, 0.62, 0.56, 0.7], "val_ba": [0.56, 0.6, 0.6, 0.6]})
    G = FC.gate_stats(R, 0.5, 0.10, 0.60, 0.55, 0.05)
    assert G["g1"].tolist() == [True, True, True, False]
    assert G["g2"].tolist() == [True, False, True, True]
    assert G["g3"].tolist() == [True, True, False, True]
    assert G["g123"].tolist() == [True, False, False, False]
    G3 = FC.gate_stats(R, 0.66, 0.03, None, 0.58, 0.05)                      # ③：现行 + 0.03、平衡准确率 ≥ 现行
    assert G3["g3"].tolist() == [False, False, False, True]


def test_horizon_end_and_row_lookup():
    days = pd.bdate_range("2020-01-01", periods=FS.H + 5)
    he = FS.horizon_end(days)
    assert he[0] == days[FS.H] and he[4] == days[FS.H + 4] and pd.isna(he[5]) and len(he) == len(days)
    R = pd.DataFrame({"combo": [(0,), (1,), (0, 1)], "x": [1, 2, 3]})
    assert FS._row(R, (0, 1))["x"].tolist() == [3] and FS._row(R, (1,))["x"].tolist() == [2]


def test_asof_uses_only_values_known_by_that_day():
    s = pd.Series([1.0, 2.0, np.nan, 4.0], index=pd.to_datetime(["2020-01-01", "2020-01-03", "2020-01-06", "2020-01-08"]))
    days = pd.bdate_range("2020-01-01", "2020-01-09")
    a = FS._asof(s, days)
    assert a.loc["2020-01-02"] == 1.0 and a.loc["2020-01-06"] == 2.0 and a.loc["2020-01-07"] == 2.0 and a.loc["2020-01-08"] == 4.0
    assert FS._asof(s, days, 1).loc["2020-01-08"] == 2.0                     # 滞后一天


def test_synthetic_real_vs_placebo_pipeline():
    """合成数据：1 个有信息的因子 + 5 个纯随机因子；真实数据里含有信息因子的组合能过 G1，打乱时间关系的对照几乎不过。"""
    rng = np.random.default_rng(5)
    n = 3000
    y = (rng.random(n) < 0.25).astype(float)
    X = rng.normal(size=(n, 6))
    X[:, 0] += 0.9 * y                                                       # 只有第 0 个有信息
    P = pd.DataFrame(X).rank(pct=True).to_numpy()
    cols = [f"F{i}" for i in range(6)]
    masks = {"disc": np.arange(n) < 1500, "val": np.arange(n) >= 1500}
    combos = FC.enumerate_combos(6, 3)
    R = FS.run_search(P, y, masks, cols, combos)
    shifts = [300, 700, 1100, 1900, 2400]
    nulls = [FS._placebo_job((P, y, masks, cols, combos, k)) for k in shifts]
    R["p"] = FC.empirical_p(R["val_auc"].to_numpy(float), np.concatenate([z[:, 1] for z in nulls]))
    G = FC.gate_stats(R, 0.5, 0.05, 0.55, None, 0.05)
    has0 = np.array([0 in c for c in R["combo"]])
    assert G.loc[has0, "g123"].mean() > 0.5 and G.loc[~has0, "g1"].sum() == 0
    assert all(sg == 1 for c, sgs in zip(R["combo"], R["signs"]) for j, sg in zip(c, sgs) if j == 0)
    pc = []
    for i, z in enumerate(nulls):                                            # 对照当作真实数据走同样的门槛
        other = np.concatenate([nulls[k][:, 1] for k in range(len(nulls)) if k != i])
        Z = pd.DataFrame({"disc_auc": z[:, 0], "val_auc": z[:, 1], "val_ba": z[:, 2]})
        Z["p"] = FC.empirical_p(Z["val_auc"].to_numpy(float), other)
        pc.append(int(FC.gate_stats(Z, 0.5, 0.05, 0.55, None, 0.05)["g123"].sum()))
    assert max(pc) <= 2


def test_placebo_is_same_pipeline_with_shift():
    rng = np.random.default_rng(6)
    n = 800
    y = (rng.random(n) < 0.3).astype(float)
    P = rng.random((n, 4))
    masks = {"disc": np.arange(n) < 400, "val": np.arange(n) >= 400}
    combos = FC.enumerate_combos(4, 2)
    z = FS._placebo_job((P, y, masks, list("abcd"), combos, 123))
    R = FS.run_search(np.roll(P, 123, axis=0), y, masks, list("abcd"), combos)
    assert np.allclose(z[:, 1], R["val_auc"].to_numpy(float), equal_nan=True) and z.shape == (len(combos), 3)


def test_run_all_and_report_smoke(tmp_path, monkeypatch):
    """合成数据（少量因子）走一遍 run_all → report：真实 + 对照、留出期、S0C2（假的 runner）、输出文件；只确认流程不出错、文件齐全。"""
    import json
    import time
    import types
    from qbreak import threat as TH
    rng = np.random.default_rng(7)
    monkeypatch.setattr(FS, "MARKET", {"Q1": "a", "B1": "b", "T1": "c", "M4": "d"})
    monkeypatch.setattr(FS, "STOCK", {"S01": "vol"})
    monkeypatch.setattr(FS, "EXTRA", {"E5": "e"})
    monkeypatch.setattr(FS, "LINES", [])
    monkeypatch.setattr(FS.paths, "out_dir", lambda: tmp_path)
    src = Path(__file__).resolve().parents[1] / "var" / "bullbear.json"           # 现行牛熊分界（测试的 QBREAK_HOME 是临时目录）
    (FS.paths.home() / "bullbear.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    days = pd.bdate_range("1990-01-01", "2026-09-25")
    n = len(days)
    drift = 0.0012 * np.sign(np.sin(2 * np.pi * np.arange(n) / 900))              # 牛熊交替
    close = pd.Series(100 * np.exp(np.cumsum(drift + rng.normal(0, 0.008, n))), index=days)
    fdd = TH.forward_drawdown(close, FS.H).to_numpy(float)
    panel = pd.DataFrame({"Q1": rng.random(n), "B1": (rng.random(n) < 0.6).astype(float), "T1": rng.random(n),
                          "M4": -fdd + rng.normal(0, 0.02, n)}, index=days)             # M4 看得到未来（只为走到后面的分支）
    panels, closes = {"JP": panel, "US": panel.copy()}, {"JP": close, "US": close.copy()}
    tick = [f"{1000 + i}.T" for i in range(12)]
    cand = pd.bdate_range("2006-01-02", "2026-06-30")
    pairs = sorted({(tick[int(rng.integers(0, 12))], cand[int(rng.integers(0, len(cand)))]) for _ in range(700)}, key=lambda x: (x[1], x[0]))
    rows = pd.DataFrame({"ticker": [t for t, _ in pairs], "date": pd.DatetimeIndex([d for _, d in pairs])})
    win = rng.random(len(rows)) < 0.45
    rows["S01"] = win + rng.normal(0, 0.5, len(rows))
    rows["E5"] = np.where(rng.random(len(rows)) < 0.5, rng.normal(size=len(rows)), np.nan)
    keep = rows["date"] >= "2006-10-01"
    T = pd.DataFrame({"ticker": rows.loc[keep, "ticker"].to_numpy(), "sig_date": rows.loc[keep, "date"].to_numpy(),
                      "exit_date": (rows.loc[keep, "date"] + pd.offsets.BDay(20)).to_numpy(), "win": win[keep.to_numpy()]})
    idx = pd.bdate_range("2005-01-03", "2026-09-25")
    ind = {t: pd.DataFrame({"entry": idx.isin(rows.loc[rows["ticker"] == t, "date"])}, index=idx) for t in tick}
    base_n = sum(int(df["entry"].sum()) for df in ind.values())
    eqi = pd.bdate_range("2006-10-02", "2026-09-25")
    noise = np.random.default_rng(8).normal(0, 0.01, len(eqi))

    def fake_run(ind2, p, prio=None, start=None, scale=None, layers=(True, True, True)):
        better = scale is not None or sum(int(df["entry"].sum()) for df in ind2.values()) < base_n
        return {"equity": pd.Series(1e6 * np.exp(np.cumsum(noise + (0.0006 if better else 0.0003))), index=eqi), "trades": 0, "win": None}

    monkeypatch.setitem(sys.modules, "adaptive_study", types.SimpleNamespace(make_runner=lambda data_n: fake_run))
    assert FS.run_all(panels, closes, rows, T, {"ind": ind, "data_n": {}}, None, "test", time.time(), 20) == 0
    js = json.loads((tmp_path / "factor_combo_study.json").read_text(encoding="utf-8"))
    wl = json.loads((tmp_path / "factor_combo_watchlist.json").read_text(encoding="utf-8"))
    md = (tmp_path / "factor_combo_study.md").read_text(encoding="utf-8")
    assert set(js["targets"]) == set(FS.TARGETS) and js["total"] == 41 + 4 * 7 + 2 * 14
    assert len(pd.read_csv(tmp_path / "factor_combo_study.csv")) == js["total"] and "随机对照" in md
    assert all(len(js["targets"][k]["summary"]["placebo_g123"]) == 20 for k in js["targets"])
    got = {w["target"] for w in wl["watch"]}
    assert "T1_breakout" in got and "T3_JP" in got                           # 走到了留出期与 S0C2 两种分支
    assert all(w["s0c2"] is not None for w in wl["watch"] if not w["target"].endswith("bottom"))
