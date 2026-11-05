"""季度决算的轨迹（scripts/earn_traj_data.py / earn_traj_study.py）：形态的定义、单季化、连续性、信号日之前的标签、
事件收益的买卖时点、聚类自助法、判定规则。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import earn_traj_data as ET                                                   # noqa: E402
import earn_traj_study as ES                                                  # noqa: E402


def test_classify_each_state():
    c = lambda *q: ET.classify(np.array(q, float))                            # noqa: E731  q0 在前
    assert c(-4, -10, -9, 1, -6, 1) == "T1"                                  # 亏损 ≤ 最差的一半、比去年同季好
    assert c(-6, -10, -9, 1, -7, 1) == "N"                                   # 亏损还是一半以上 → 不算收窄
    assert c(-4, -10, -9, 1, -3, 1) == "N"                                   # 比去年同季差 → 不算
    assert c(5, -10, -9, 1, -6, 1) == "T2"
    assert c(-5, 10, 9, 1, 6, 1) == "T3"
    assert c(-12, -10, 3, 1, -6, 1) == "T4"
    assert c(7, 8, 3, 1, 10, 11) == "T5"                                     # 7 ≤ 0.8×10、8 ≤ 0.8×11
    assert c(15, 11, 3, 1, 10, 10) == "T6"                                   # 1.5 ≥ 1.2 且 1.5 > 1.1 > 1
    assert c(15, 13, 3, 1, 10, 10) == "T6" and c(12, 13, 3, 1, 10, 10) == "N"  # 这一季的同比要比上一季快
    assert ET.classify(np.array([1, 2, np.nan, 1, 1, 1], float)) is None


def _fins(rows):
    cols = ET.COLS
    return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols).astype(str).replace("nan", np.nan)


def test_jp_quarters_diff_first_disclosure_and_consolidated_only():
    base = ("72030", "{per}FinancialStatements_Consolidated_JP", "{p}", "2024-04-01", "{en}", "2024-04-01", "2025-03-31")
    rows = []
    for p, en, dd, op in (("1Q", "2024-06-30", "2024-08-01", 10), ("2Q", "2024-09-30", "2024-11-01", 25),
                          ("3Q", "2024-12-31", "2025-02-01", 30), ("FY", "2025-03-31", "2025-05-10", 50)):
        rows.append((dd, "15:00", "72030", base[1].format(per=p if p != "FY" else "FY"), p, "2024-04-01", en, "2024-04-01", "2025-03-31", 100, op))
    rows.append(("2024-11-20", "15:00", "72030", "2QFinancialStatements_Consolidated_JP", "2Q", "2024-04-01", "2024-09-30",
                 "2024-04-01", "2025-03-31", 100, 999))                        # 订正 → 不用
    rows.append(("2024-11-01", "15:00", "72030", "2QFinancialStatements_NonConsolidated_JP", "2Q", "2024-04-01", "2024-09-30",
                 "2024-04-01", "2025-03-31", 100, 5))                          # 单体 → 不用
    Q = ET.jp_quarters(_fins(rows))
    assert Q["v"].tolist() == [10, 15, 5, 20] and Q["ticker"].iloc[0] == "7203.T"
    assert Q["disc"].tolist() == [pd.Timestamp(x) for x in ("2024-08-01", "2024-11-01", "2025-02-01", "2025-05-10")]


def test_states_need_six_consecutive_quarters():
    q_end = pd.to_datetime(["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31", "2024-03-31", "2024-06-30", "2024-12-31"])
    Q = pd.DataFrame({"ticker": "A", "q_end": q_end, "disc": q_end + pd.Timedelta(days=40), "v": [1, 1, 1, 1, 1, 5, 5.0]})
    Q["ord"] = Q["q_end"].dt.year * 12 + Q["q_end"].dt.month
    S = ET.states(Q, "JP")
    assert len(S) == 1 and S["disc"].iloc[0] == q_end[5] + pd.Timedelta(days=40)   # 最后一季前面断开了 → 不算


def test_latest_state_strictly_before_and_max_age():
    S = pd.DataFrame({"ticker": ["A", "A"], "disc": pd.to_datetime(["2024-01-10", "2024-05-10"]), "state": ["T2", "T3"]})
    sig = pd.DataFrame({"ticker": ["A", "A", "A", "A", "B"], "sig_date": pd.to_datetime(["2024-01-10", "2024-01-11", "2024-05-11", "2024-09-30", "2024-05-11"])})
    out = ET.latest_state(S, sig, max_age_days=100).tolist()
    assert pd.isna(out[0]) and out[1] == "T2" and out[2] == "T3" and pd.isna(out[3]) and pd.isna(out[4])


def test_event_returns_timing_and_excess():
    days = pd.bdate_range("2024-01-01", periods=10)
    O = np.arange(10, 20, dtype=float)[:, None]
    C = O + 0.5
    mo, mc = np.full(10, 100.0), np.full(10, 101.0)
    ev = pd.DataFrame({"ticker": ["A"], "disc": [days[2]], "state": ["T2"]})
    E = ES.event_returns(ev, days, ["A"], O, C, mo, mc, h=3)
    r = E.iloc[0]
    assert r["t0"] == days[3]                                                   # 开示日之后第一个交易日
    assert abs(r["x"] - ((C[5, 0] / O[3, 0] - 1) - 0.01) * 100) < 1e-9       # 第 3 个交易日收盘卖、减大盘
    assert abs(r["gap"] - (O[3, 0] / C[2, 0] - 1) * 100) < 1e-9
    listed = np.ones((10, 1), bool)
    listed[3, 0] = False
    assert ES.event_returns(ev, days, ["A"], O, C, mo, mc, h=3, listed=listed).empty
    assert ES.event_returns(ev.assign(disc=[days[8]]), days, ["A"], O, C, mo, mc, h=3).empty   # 到不了第 h 天 → 不算


def test_joint_boot_and_verdicts():
    wa = np.array(["w1", "w2", "w3"] * 10)
    lo, hi = ES.joint_boot_diff(np.full(30, 2.0), wa, np.full(30, 0.5), wa, n=200)
    assert abs(lo - 1.5) < 1e-12 and abs(hi - 1.5) < 1e-12
    good = {"T2": {"n": 150, "diff": 1.0, "lo": 0.2, "hi": 1.8}}
    bad = {"T2": {"n": 150, "diff": 1.0, "lo": -0.2, "hi": 1.8}}
    assert ES.verdict_a(good, good, good, "T2").startswith("影响成立；横展开也成立")
    assert ES.verdict_a(good, good, {"T2": {"n": 150, "diff": -0.3, "lo": -1, "hi": 0.4}}, "T2").endswith("美国相反")
    assert ES.verdict_a(good, bad, None, "T2").startswith("只在一个年代（2017")
    assert ES.verdict_a({"T2": {**good["T2"], "n": 50}}, good, None, "T2").startswith("只在一个年代（2022")
    neg = {"T3": {"n": 300, "diff": -1.0, "lo": -1.8, "hi": -0.2}}
    assert ES.verdict_a(neg, neg, None, "T3").startswith("影响成立") and "T6" in ES.ET.STATES
    blk = {"diff": 1.2, "lo": 0.1, "placebo_q": 0.5, "keep": {"n": 900, "mean": 0.8, "win": 40.0}, "rem": {"n": 120, "mean": -0.4, "win": 30.0}}
    assert ES.gate_s_minus(blk) and not ES.gate_s_minus({**blk, "rem": {"n": 90, "mean": -0.4, "win": 30.0}})
    assert ES.verdict_b(blk, blk) == "选股改进成立" and ES.verdict_b(blk, {**blk, "lo": -0.1}).startswith("时代依赖")
    assert ES.verdict_b({**blk, "diff": 0.9}, blk) == "不成立"


def test_strat_drop_keeps_year_counts():
    E = pd.DataFrame({"ticker": [f"T{i}" for i in range(20)], "sig_date": pd.to_datetime(["2020-03-02"] * 10 + ["2021-03-01"] * 10)})
    flag = np.array([True] * 3 + [False] * 7 + [True] * 1 + [False] * 9)
    kept = ES.strat_drop(E, flag, seed=1, keep_flag=False)
    yrs = pd.Series([d.year for ds in kept.values() for d in ds]).value_counts().to_dict()
    assert yrs == {2020: 7, 2021: 9}
    only = ES.strat_drop(E, flag, seed=1, keep_flag=True)
    assert sum(len(v) for v in only.values()) == 4
