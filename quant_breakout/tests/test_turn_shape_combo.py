"""scripts/turn_shape_combo.py（2026-10-06 登记）：事件日、当天百分位的「最像」、两种条件与四个做法、（票, 日期）查表、exit_tick、系数核对、
宽表打分（单个系数时 = 手算）、成交日 / 窗口计数、第一关加 V7。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import turn_shape_combo as TC  # noqa: E402
import turn_shape_study as S  # noqa: E402


def test_registered_constants():
    assert TC.IDS == ("TBF", "TBR", "TXF", "TXR") and TC.TOP == 0.90 and TC.OOS_FROM == "2022-01-01" and TC.J2_TOL == -0.02
    assert TC.KIND == {"TBF": "buy", "TBR": "buy", "TXF": "sell", "TXR": "sell"}
    assert TC.COND == {"TBF": "fall2", "TBR": "rise_wm", "TXF": "fall2", "TXR": "rise_wm"}
    assert all(TC.POSTHOC.values()) and TC.FP == "3b2e8757be7b4a74"
    assert len(TC.FEATS_SCORED) == 45 and "lmc" not in TC.FEATS_SCORED


def test_fresh_and_top_flags():
    c = np.array([[0, 1], [1, 1], [1, 0], [0, 1]], bool)
    assert TC.fresh(c).tolist() == [[False, True], [True, False], [False, False], [False, True]]
    sc = np.tile(np.arange(20, dtype=float), (2, 1))
    ok = np.ones_like(sc, bool)
    ok[1, 19] = False                                                         # 第二天最高的那只不算
    f = TC.top_flags(sc, ok)
    assert f[0].sum() == 2 and f[0, 18] and f[0, 19] and not f[0, 17]         # 20 只：19 → 1.0、18 → 0.95 > 0.9；17 → 0.90 不算
    assert not f[1, 19] and f[1, 18] and f[1, 17] and f[1].sum() == 2         # 19 只：18 → 1.0、17 → 18 / 19 ≈ 0.947；16 → 0.895 不算
    p = TC.pct_rank(sc, ok)
    assert np.isnan(p[1, 19]) and p[0, 19] == 1.0


def test_conditions_and_rules():
    z = np.zeros((3, 2), bool)
    fl = {(sc, mk): z.copy() for sc in TC.SCALES3 for mk in TC.MODELS}
    fl[("D", "fall")][1, 0] = fl[("W", "fall")][1, 0] = True                  # 两个尺度 → fall2
    fl[("M", "fall")][2, 1] = True                                            # 只有一个 → 不算
    fl[("W", "rise")][0, 1] = True
    fl[("M", "rise")][1, 1] = True
    c = TC.conditions(fl)
    assert c["fall2"].tolist() == [[False, False], [True, False], [False, False]]
    assert c["rise_wm"].tolist() == [[False, True], [False, True], [False, False]]
    r = TC.rule_arrays(c)
    assert r["TBF"].tolist() == c["fall2"].tolist() and r["TBR"].tolist() == c["rise_wm"].tolist()
    assert r["TXR"].tolist() == [[False, True], [False, False], [False, False]]   # 连续两天成立 → 只有第一天是事件日
    assert r["TXF"].tolist() == c["fall2"].tolist()


def test_lookup_exit_tick_and_windows():
    days = pd.bdate_range("2024-01-01", periods=6)
    names = ["A", "B"]
    arr = np.zeros((6, 2), bool)
    arr[2, 1] = arr[4, 0] = True
    got = TC.lookup(arr, days, names, ["B", "A", "C", "A"], [days[2], days[2], days[2], pd.Timestamp("2030-01-01")])
    assert got.tolist() == [True, False, False, False]
    tk = TC.exit_tick(arr, days, names)
    assert tk == {"A": frozenset({days[4]}), "B": frozenset({days[2]})}
    assert TC.exit_tick(arr, days, names, only={"A"}) == {"A": frozenset({days[4]})}
    fills = TC.next_day(days, [days[1], days[5]])
    assert list(fills) == [days[2], days[5]]                                  # 最后一天 → 留在最后一天
    assert TC.window_has(arr, days, names, ["A", "A", "B"], [days[0], days[5], days[3]], n=5).tolist() == [True, False, False]


def test_coef_match():
    w = np.zeros(len(S.FEATS) + 1)
    w[1 + S.FEATS.index("d_rsi14")] = -0.78661
    w[1 + S.FEATS.index("d_body")] = 0.5
    stored = [{"f": "d_rsi14", "b": -0.7866}, {"f": "d_body", "b": 0.5}]
    assert TC.coef_match(w, stored, n=2)["same"]
    assert not TC.coef_match(w, [{"f": "d_body", "b": 0.5}, {"f": "d_rsi14", "b": -0.7866}], n=2)["same"]


def test_score_panel_single_coefficient():
    n, m = 420, 3
    rng = np.random.default_rng(1)
    C = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, (n, m)), axis=0))
    P = {"O": C * 0.999, "H": C * 1.01, "L": C * 0.99, "C": C, "V": np.full((n, m), 1e5)}
    days = pd.bdate_range("2015-01-01", periods=n)
    k = len(S.FEATS)
    st = {"lo": np.full(k, -1e9), "hi": np.full(k, 1e9), "mu": np.zeros(k), "sd": np.ones(k)}
    i = S.FEATS.index("d_r5")
    st["mu"][i], st["sd"][i] = 0.01, 0.02
    wv = np.zeros(k + 1)
    wv[0], wv[1 + i] = 0.3, 2.0
    fits = {"D": {"st": st, "w": {"rise": wv, "fall": -wv}}}
    sc, comp = TC.score_panel(P, days, fits)
    exp = 0.3 + 2.0 * ((C[5:] / C[:-5] - 1) - 0.01) / 0.02
    assert np.allclose(sc[("D", "rise")][5:], exp, atol=1e-4)
    assert np.allclose(sc[("D", "fall")][5:], -exp, atol=1e-4)                 # 截距、系数都取负
    assert np.allclose(sc[("D", "rise")][:5], 0.3, atol=1e-6)                 # d_r5 缺 → 0 → 只剩截距
    assert not comp[:300].any() and comp[-1].all()                             # 月线 12 个月线的 3 个月斜率要 15 根月线；最后一天齐


def test_judge_adds_v7(monkeypatch):
    import research_loop11 as R11
    monkeypatch.setattr(R11, "stage1", lambda cand, base, other, lenses=None, posthoc=False: {"ok": True, "routes": {}})
    base = {"J": {"h2": 0.79}}
    ok = TC.judge({"J": {"h2": 0.78}}, base, {}, True)
    bad = TC.judge({"J": {"h2": 0.75}}, base, {}, True)
    assert ok["V7"] and ok["ok"] and abs(ok["d_j2"] + 0.01) < 1e-9
    assert not bad["V7"] and not bad["ok"]
