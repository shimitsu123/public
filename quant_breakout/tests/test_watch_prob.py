"""观察中的买入优先级（qbreak/watch_prob.py + scripts/watch_prob_study.py）：情况的划分、三层收缩、查表、
研究里一行的特征 = 面板（scan + suggest.proximity）同一个结果、成对一致率与前 k 只的算法。"""
import importlib.util
import itertools
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qbreak import watch_prob as WP
from qbreak.config import StrategyParams
from qbreak.scan import scan
from qbreak.strategy import compute_indicators
from qbreak.suggest import MAX_DAYS, proximity

ROOT = Path(__file__).resolve().parent.parent


def _study():
    spec = importlib.util.spec_from_file_location("watch_prob_study", ROOT / "scripts" / "watch_prob_study.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P_JP = StrategyParams(max_distribution_days=6, max_upper_shadow_ratio=3.0, min_weekly_vol_ratio=1.0)


def _frame(seed: int, n: int = 420, vol: float = 0.006) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    r = rng.normal(0, vol, n)
    c = 1000 * np.exp(np.cumsum(r))
    o = c * (1 + rng.normal(0, vol / 3, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, vol / 2, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, vol / 2, n)))
    v = rng.lognormal(12, 0.35, n) * np.where(rng.random(n) < 0.12, 2.6, 1.0)
    idx = pd.bdate_range("2021-01-04", periods=n)
    return pd.DataFrame({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": v}, index=idx)


# ───────────── 情况的划分 ─────────────
def test_cells_map_like_the_panel_words():
    assert WP.wb_of("below_up", 1, -0.3) == "up_d1"
    assert WP.wb_of("below_up", 2, -0.3) == "up_d2"
    assert [WP.wb_of("below_up", d, None) for d in (3, 4, 5, 9, 10, 30)] == ["up_d3_4", "up_d3_4", "up_d5_9", "up_d5_9", "up_d10", "up_d10"]
    assert WP.wb_of("below_down", None, -0.149) == "down_near"
    assert WP.wb_of("below_down", None, -0.15) == "down_far"            # 与 scan「快要出」同一个界线（< 0.15%）
    assert WP.wb_of("above", None, 0.05) == "above_near" and WP.wb_of("above", None, 0.4) == "above_far"
    assert WP.wb_of("above", None, None) == "above_far"                  # 算不出离得多远 → 远
    assert WP.wb_of("unknown", None, 0.0) == "unknown" and WP.wb_of(None, None, None) == "unknown"
    assert [WP.mb_of(x) for x in (0, None, 1, 2, 5)] == ["m0", "m0", "m1", "m2", "m2"]
    assert [WP.vb_of(x) for x in (None, "x", float("nan"), 0.99, 1.0, 3.2)] == ["v_lo", "v_lo", "v_lo", "v_lo", "v_hi", "v_hi"]
    near = {"where": "below_up", "days": 3, "miss": ["周线量比（0.8，要 ≥ 1）"], "vol": 1.2}
    assert WP.cell_of(near, -0.08, 1.2) == ("up_d3_4", "m1", "v_hi")
    assert set(WP.WB) == set(WP.WB_TEXT)


# ───────────── 三层收缩 / 查表 ─────────────
def test_fit_shrinks_three_levels_and_unseen_cells_fall_back():
    rows = [("up_d1", "m0", "v_hi", 1)] * 30 + [("up_d1", "m0", "v_hi", 0)] * 70 \
        + [("up_d1", "m1", "v_lo", 0)] * 20 + [("above_far", "m0", "v_lo", 0)] * 380 + [("above_far", "m0", "v_lo", 1)] * 20
    t = WP.fit(rows, m=50)
    g = t["global"]
    assert (g["n"], g["y"]) == (520, 50) and g["p"] == pytest.approx(50 / 520)
    p1 = (30 + 50 * g["p"]) / (120 + 50)
    assert t["l1"]["up_d1"]["p"] == pytest.approx(p1)
    p2 = (30 + 50 * p1) / (100 + 50)
    assert t["l2"]["up_d1|m0"]["p"] == pytest.approx(p2)
    p3 = (30 + 50 * p2) / (100 + 50)
    assert t["l3"]["up_d1|m0|v_hi"]["p"] == pytest.approx(p3)
    r = WP.prob(t, "up_d1", "m0", "v_hi")
    assert r == {"p": pytest.approx(p3), "n": 100, "y": 30}
    # 没见过的情况 = 上一层（n = 0 时收缩公式给的也是上一层）
    assert WP.prob(t, "up_d1", "m0", "v_lo")["p"] == pytest.approx(p2) and WP.prob(t, "up_d1", "m0", "v_lo")["n"] == 0
    assert WP.prob(t, "up_d1", "m2", "v_lo")["p"] == pytest.approx(p1)
    assert WP.prob(t, "down_far", "m0", "v_lo")["p"] == pytest.approx(g["p"])
    # 样本多的情况几乎就是它自己的比例；样本少的往上一层靠
    assert abs(t["l3"]["above_far|m0|v_lo"]["p"] - 20 / 400) < 0.01
    assert t["l3"]["up_d1|m1|v_lo"]["p"] > 0.05                         # 20 次 0 次出信号，但只有 20 次 → 不是 0
    with pytest.raises(ValueError):
        WP.fit([])
    json.dumps(t)                                                        # 能写成 JSON


def test_load_and_for_row(tmp_path):
    fp = tmp_path / "wp.json"
    assert WP.load(fp) is None                                           # 没有文件 = 照旧
    fp.write_text("not json", encoding="utf-8")
    assert WP.load(fp) is None
    fp.write_text(json.dumps({"x": 1}), encoding="utf-8")
    os.utime(fp, (1, 1))
    assert WP.load(fp) is None                                           # 不是表
    t = WP.fit([("up_d1", "m0", "v_hi", 1), ("up_d1", "m0", "v_hi", 0), ("down_far", "m1", "v_lo", 0)], extra={"show_pct": False})
    fp.write_text(json.dumps(t), encoding="utf-8")
    os.utime(fp, (2, 2))
    got = WP.load(fp)
    assert got and got["l3"]["up_d1|m0|v_hi"]["n"] == 2
    row = {"status": "watch", "near": {"where": "below_up", "days": 1, "miss": [], "vol": 1.4}, "macd_gap_pct": -0.02, "vol_ratio": 1.4}
    r = WP.for_row(row, got)
    assert r["cell"] == "up_d1|m0|v_hi" and r["n"] == 2 and r["h"] == 10 and r["show"] is False
    assert WP.for_row({**row, "status": "triggered"}, got) is None
    assert WP.for_row({"status": "watch"}, got) is None
    assert WP.for_row(row, None) is None


def test_repo_table_if_present_is_valid():
    t = WP.load()
    if t is None:
        pytest.skip("研究判定没写表（或还没运行）")
    assert t["h"] == 10 and t["m"] == 50 and "show_pct" in t
    for k, v in t["l3"].items():
        wb, mb, vb = k.split("|")
        assert wb in WP.WB and mb in WP.MB and vb in WP.VB and 0 <= v["p"] <= 1 and v["n"] >= v["y"] >= 0


# ───────────── 研究的一行 = 面板的同一个结果 ─────────────
def test_study_rows_equal_the_panel_path():
    S = _study()
    seen = {"imminent": 0, "watch": 0, "y1": 0}
    for seed in range(6):
        ind = compute_indicators(_frame(seed), P_JP)
        rows = S.ticker_rows(ind, P_JP)
        assert len(rows)
        pos = {d: i for i, d in enumerate(ind.index)}
        e = ind["entry"].to_numpy(bool)
        for _, r in rows.iterrows():
            t = pos[r["date"]]
            sub = ind.iloc[:t + 1]
            sc = scan({"X.T": sub}, P_JP, "JP", budget=1e15, top=1).iloc[0]
            assert sc["status"] == r["status"]
            nr = proximity(sub, P_JP)
            assert WP.cell_of(nr, round(float(sc["macd_gap_pct"]), 3), round(float(sc["vol_ratio"]), 2)) == (r["wb"], r["mb"], r["vb"])
            w = nr["where"]
            dk = int(nr.get("days") or MAX_DAYS) if w == "below_up" else {"below_down": MAX_DAYS + 1, "above": MAX_DAYS + 2}.get(w, MAX_DAYS + 3)
            assert (len(nr["miss"]), dk) == (r["n_miss"], r["dkey"])
            assert round(float(sc["score"]), 1) == r["score1"] and round(float(sc["vol_ratio"]), 2) == r["vol2"]
            for h in (5, 10, 20):
                if t + h <= len(ind) - 1:
                    assert r[f"y{h}"] == float(e[t + 1:t + h + 1].any()) and r[f"d{h}"] == ind.index[t + h]
                else:
                    assert np.isnan(r[f"y{h}"]) and pd.isna(r[f"d{h}"])
            seen[r["status"]] += 1
            seen["y1"] += int(r["y10"] == 1.0)
        # 被排除的行：出了信号 / far / 预热里的 → 都不在
        st = set(rows["date"])
        for t in range(len(ind)):
            if ind.index[t] in st:
                continue
            if t >= P_JP.warmup_bars + 1:
                s = scan({"X.T": ind.iloc[:t + 1]}, P_JP, "JP", budget=1e15, top=1)
                assert s.empty or s.iloc[0]["status"] in ("triggered", "far")
    assert seen["imminent"] > 0 and seen["watch"] > 0 and seen["y1"] > 0     # 合成行情里三种都有


def test_study_rows_do_not_look_ahead():
    S = _study()
    ind_full = compute_indicators(_frame(3), P_JP)
    cut = 300
    a = S.ticker_rows(ind_full, P_JP)
    b = S.ticker_rows(compute_indicators(_frame(3).iloc[:cut], P_JP), P_JP)
    a = a[a["date"] <= ind_full.index[cut - 1]].reset_index(drop=True)
    cols = ["date", "status", "wb", "mb", "vb", "n_miss", "dkey", "vol2", "score1"]
    pd.testing.assert_frame_equal(a[cols], b[cols])                        # 特征只用到 t 为止


# ───────────── 评估的算法 ─────────────
def _brute(day, key, y):
    conc = pairs = 0.0
    for d in set(day):
        ix = [i for i in range(len(day)) if day[i] == d]
        for i, j in itertools.product(ix, ix):
            if y[i] == 1 and y[j] == 0:
                pairs += 1
                conc += 1.0 if key[i] < key[j] else 0.5 if key[i] == key[j] else 0.0
    return conc, pairs


def test_pair_concordance_matches_brute_force_with_ties():
    S = _study()
    rng = np.random.default_rng(7)
    for _ in range(20):
        n = int(rng.integers(5, 40))
        day = rng.integers(0, 4, n)
        a, b = rng.integers(0, 3, n), rng.integers(0, 3, n)
        y = (rng.random(n) < 0.3).astype(int)
        key = S.dense_key([a, -b])
        g = S.day_pairs(day, key, y)
        conc, pairs = _brute(list(day), list(key), list(y))
        assert float(g["pairs"].sum()) == pairs and float(g["conc"].sum()) == pytest.approx(conc)
        # dense_key = 字典序
        for i, j in itertools.product(range(n), range(n)):
            assert (key[i] < key[j]) == ((a[i], -b[i]) < (a[j], -b[j]))
    assert S.conc_of(pd.DataFrame({"pairs": [0], "conc": [0]})) is None


def test_top_k_and_decision():
    S = _study()
    day = [1, 1, 1, 2, 2, 3]
    key = [2, 1, 3, 1, 2, 1]
    y = [1, 0, 1, 1, 0, 1]
    tie = [0, 1, 2, 3, 4, 5]
    assert S.top_k(day, key, tie, y, 1) == pytest.approx((0 + 1 + 1) / 3)
    assert S.top_k(day, key, tie, y, 2) == pytest.approx((0.5 + 0.5) / 2)   # 第 3 天只有 1 只 → 不算
    assert S.decide(0.0, 0.03) == "A" and S.decide(-0.010, 0.05) == "A"
    assert S.decide(0.02, 0.0501) == "B" and S.decide(-0.0101, 0.01) == "C" and S.decide(float("nan"), 0.01) == "C"
