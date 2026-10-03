"""scripts/mid_vthrust_study.py：保留规则（缺值）、两个样本的窗口（都在以前看过的范围之外）、主判定 G1〜G5 与同号检查。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hx_select_study as HX  # noqa: E402
import mid_vthrust_study as MV  # noqa: E402


def _T(n=3000, seed=0, lift=0.0, start="1995-01-02", end="2015-12-31"):
    rng = np.random.default_rng(seed)
    d = pd.bdate_range(start, end)
    T = pd.DataFrame({"ticker": [f"T{rng.integers(0, 80)}" for _ in range(n)], "sig_date": pd.to_datetime(rng.choice(d, n))})
    T["vr1"] = rng.uniform(0.5, 5.0, n)
    T["w5v"] = rng.uniform(0.3, 2.5, n)
    T["net"] = rng.normal(0.3, 6.0, n)
    T["sector"] = rng.choice(["IT", "Fin", "Util", "HC"], n)
    T = T.sort_values("sig_date").reset_index(drop=True)
    T["year"] = T["sig_date"].dt.year
    T["week"] = T["sig_date"].dt.to_period("W-FRI").astype(str)
    T["month"] = T["sig_date"].dt.to_period("M").astype(str)
    M = MV.keep_masks(T)
    T.loc[M["M1"], "net"] += lift
    T["win"] = T["net"] > 0
    return T


def test_keep_masks_missing_values():
    T = pd.DataFrame({"vr1": [np.nan, 3.0, 2.5, 3.5, 1.0], "w5v": [1.2, np.nan, 1.1, 0.8, 2.0]})
    M = MV.keep_masks(T)
    assert M["W2"].tolist() == [True, True, True, False, True]                   # W2 缺值 → 保留（同现行）
    assert M["M1"].tolist() == [False, True, False, True, False]                 # vr1 缺值 → 不满足
    assert M["M2"].tolist() == [False, True, False, False, False]
    assert M["M3"].tolist() == [False, True, True, True, False]


def test_windows_are_outside_seen_ranges():
    a0, a1, ah = MV.WIN["A"]
    assert a1 < HX.S400_START and a0 == HX.WIN0 and ah == pd.Timestamp("2006-01-01")    # H1 的 S&P 400 从 2016 年起才看过
    b0, b1, _ = MV.WIN["B"]
    assert (str(b0.date()), str(b1.date())) == ("2001-01-04", "2006-09-30")               # = leap_common 的 Z 窗口


def test_gate_a_null_and_strong_lift():
    T0 = _T(lift=0.0, seed=1)
    M0 = MV.keep_masks(T0)
    g0 = MV.gate_a(T0, M0, "M1")
    assert not g0["pass"] and any(f.startswith("G1") for f in g0["fails"])
    T1 = _T(lift=4.0, seed=2)
    M1 = MV.keep_masks(T1)
    g1 = MV.gate_a(T1, M1, "M1")
    assert g1["pass"], g1["fails"]
    g2 = MV.gate_a(T1, M1, "M2")                                                  # M2 的基准 = W2 保留组
    assert g2["base"] == "W2"


def test_gate_a_min_counts():
    T = _T(n=400, lift=6.0, seed=3)
    M = MV.keep_masks(T)
    M["M1"] = M["M1"] & (np.arange(len(T)) < 60)                                  # 候选只剩前面几十笔
    g = MV.gate_a(T, M, "M1")
    assert any(f.startswith("G5") for f in g["fails"])


def test_sign_b():
    T = _T(n=800, lift=3.0, seed=4, start="2001-01-04", end="2006-09-30")
    M = MV.keep_masks(T)
    assert MV.sign_b(T, M, "M1")["pass"]
    T2 = _T(n=800, lift=-3.0, seed=5, start="2001-01-04", end="2006-09-30")
    s = MV.sign_b(T2, MV.keep_masks(T2), "M1")
    assert not s["pass"] and any(f.startswith("每笔") for f in s["fails"])


def test_report_blocks_smoke(monkeypatch):
    """判定块与另报的输出（合成数据），不出错。"""
    monkeypatch.setattr(MV, "LINES", [])
    T = _T(n=1500, lift=1.0, seed=6)
    M = MV.keep_masks(T)
    for cid in MV.CANDS:
        MV.show_block("A 判定", MV.gate_a(T, M, cid), MV.HALF_NAME["A"])
        MV.show_block("B 同号", MV.sign_b(T, M, cid), MV.HALF_NAME["B"])
    MV.show_describe(MV.describe(T, M))
    text = "\n".join(MV.LINES)
    assert "抽签对照 95 分位" in text and "突破日量比分档" in text and "按年" in text


def test_clean_drops_zero_volume_rows():
    idx = pd.bdate_range("2001-01-01", periods=400)
    df = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 100.0}, index=idx)
    df.iloc[[0, 5, 6], df.columns.get_loc("Volume")] = 0.0                       # 休市假行（成交量 0）
    df.iloc[7, df.columns.get_loc("Volume")] = np.nan
    data, cl = MV.clean({"X.T": df, "Y.T": df}, {"X.T": "s"}, "B")
    assert list(data) == ["X.T"] and len(data["X.T"]) == 396 and (data["X.T"]["Volume"] > 0).all()
    w0, w1, _ = MV.WIN["B"]
    assert cl["rows_window"] == int(((idx >= w0) & (idx <= w1)).sum()) and cl["dropped_window"] == 3   # 1-01 在窗口之前


def test_always_drawn_and_quarter_boot():
    base = np.ones(6, bool)
    keep = np.array([True, True, False, True, False, False])
    strata = np.array(["a", "a", "b", "b", "c", "c"])
    assert MV.always_drawn(base, keep, strata) == round(2 / 3, 3)                # 层 a 全是候选 → 那 2 笔每次必中
    T = _T(n=1200, seed=7)
    M = MV.keep_masks(T)
    assert abs(MV.boot_q(T, M["P"], M["P"]) or 0.0) < 1e-12                      # 候选 = 基准 → 差 0
