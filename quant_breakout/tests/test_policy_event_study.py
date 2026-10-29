"""scripts/policy_event_study.py：判定 J1〜J8、Holm、置换 p、名单（P1 / P2 / P3、可得性、对照池套上一次变更）、向量化价差 = 逐个 spread、
GAP / 截断、探索阶段不读确认窗口、确认阶段守门。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import policy_event_data as PD  # noqa: E402
import policy_event_study as ST  # noqa: E402
from qbreak import policy_events as PEV  # noqa: E402


def test_judge_rules():
    good = {"n": 60, "mean": 1.2, "hit": 65.0, "lo": 0.3, "hi": 2.0}
    ok = {"C1": True, "C2": True}
    assert ST.judge(good, "W5", "explore", 58.0, ok, {"BOJ_CHANGE": {"tighten": (0.5, 10), "ease": (0.8, 20)}}, {"A": 0.8, "B1": 1.5}, {"mean": 0.2, "n": 60}, 0.1) == []
    f = ST.judge({"n": 30, "mean": 0.4, "hit": 55.0, "lo": -0.2, "hi": 1.0}, "W5", "explore", 58.0, {"C1": False, "C2": False},
                 {"BOJ_CHANGE": {"tighten": (-0.5, 10), "ease": (0.8, 20)}}, {"A": 0.8, "B1": -0.5}, {"mean": 0.5, "n": 30}, 0.6)
    assert [x[:2] for x in f] == ["J1", "J2", "J3", "J4", "J4", "J5", "J6", "J7", "J8"]
    assert ST.judge({"n": 0, "mean": None, "hit": None}, "W5", "explore", None, {}, {}, {}, {}, None) == ["无样本"]
    assert ST.judge(good, "W20", "explore", None, ok, {}, {"A": 0.8}, {"mean": 0.2}, None) == []                       # W20 要 +1.0 pp：1.2 过
    assert ST.judge({"n": 60, "mean": 0.9, "hit": 65.0, "lo": 0.3, "hi": 2.0}, "W20", "explore", None, ok, {}, {"A": 0.8}, {"mean": 0.2}, None)[0].startswith("J2")
    assert ST.judge(dict(good, n=30), "W5", "confirm", None, ok, {}, {}, {}, None) == []                             # C 阶段 n ≥ 25
    assert ST.judge(dict(good, n=30), "W5", "explore", None, ok, {}, {}, {}, None) == ["J3 事件数 30 < 40"]
    assert ST.judge(good, "W5", "explore", 66.0, ok, {}, {}, {}, None)[0].startswith("J1")                             # 命中未超过 C1 95 分位
    assert ST.judge(good, "W5", "explore", None, ok, {"MOF_FX": {"yen_buy": (-1.0, 3), "yen_sell": (1.0, 30)}}, {}, {}, None) == []   # 子类 n < 5 不判


def test_holm_and_perm_p():
    pv = {"a": 0.001, "b": 0.03, "c": 0.04, "d": None}
    h = ST.holm(pv)
    assert h["a"] and not h["b"] and not h["c"] and not h["d"]                    # 3 个检验：0.001 ≤ 0.05/3 过；0.03 > 0.05/2 → 之后都不过
    assert ST.holm({"a": 0.01, "b": 0.02}) == {"a": True, "b": True}
    null = np.r_[np.linspace(-1, 1, 999), 5.0]
    assert ST.perm_p(2.0, null) == round(2 / 1001, 4) and ST.perm_p(-2.0, null) == 1.0 and ST.perm_p(None, null) is None and ST.perm_p(1.0, np.array([np.nan])) is None
    assert ST.MAIN == [("P2", "W5"), ("P1", "W5")] and ST.N_PERM == 1000 and ST.J3_N == {"X": 40, "C": 25}


def test_lists_spreads_gap_and_truncation_synthetic():
    row = pd.Series({"category": "BOJ_CHANGE", "subtype": "tighten"})
    B = pd.DataFrame({"rate_jp": [5.0, -5.0, 1.0, 0.0, -1.0, 2.0, -2.0, 3.0, -3.0], "fx": [0.0] * 9},
                     index=["銀行業", "不動産業", "保険業", "食料品", "小売業", "機械", "電気機器", "その他金融業", "情報・通信業"])
    L = ST.lists_for(row, B)
    assert L["P1"] == (["銀行業", "保険業", "その他金融業", "食料品"], ["不動産業", "電気・ガス業", "情報・通信業", "輸送用機器"])
    assert set(L["P2"][0]) == {"銀行業", "その他金融業", "機械", "保険業"} and set(L["P2"][1]) == {"不動産業", "情報・通信業", "電気機器", "小売業"}
    assert L["P3"] == (["銀行業", "保険業", "その他金融業"], ["不動産業", "情報・通信業"])
    ease = ST.lists_for(pd.Series({"category": "BOJ_CHANGE", "subtype": "ease"}), B)
    assert ease["P1"][0] == L["P1"][1] and set(ease["P2"][0]) == set(L["P2"][1])                     # sign −1：冲击反号 → 名单互换
    assert ST.lists_for(pd.Series({"category": "ELECTION", "subtype": "lower"}), B)["P1"] == ([], [])
    avail = [s for s in PEV.S33_ALL if s != "その他金融業"]
    assert ST.lists_for(row, B, avail)["P1"][0] == ["銀行業", "保険業", "食料品", "小売業"] and "subst" in ST.lists_for(row, B, avail)["note"]
    # 对照池：套用上一次变更的名单
    days = pd.bdate_range("2024-01-01", periods=60)
    E = pd.DataFrame([{"category": "BOJ_CHANGE", "subtype": "tighten", "excluded": 0, "r": days[5]}, {"category": "CTRL_BOJ_NOCHG", "subtype": "no_change", "excluded": 0, "r": days[20]}])
    Lc = ST.lists_for(E.iloc[1], None, None, E)
    assert Lc["P1"] == L["P1"] and Lc["note"].startswith("ctrl:BOJ_CHANGE/tighten")
    assert ST.lists_for(E.iloc[1], None, None, E[E["category"] == "CTRL_BOJ_NOCHG"])["P1"] == ([], [])   # 之前没有变更 → 空
    # 向量化价差 = 逐个 spread；GAP；截断
    secs = ["銀行業", "不動産業", "保険業", "その他金融業", "食料品", "電気・ガス業", "情報・通信業", "輸送用機器", "小売業"]
    cc = pd.DataFrame(0.0, index=days, columns=secs); oc = cc.copy()
    cc.loc[days[12], "銀行業"] = 2.0; cc.loc[days[12], "不動産業"] = -2.0; cc.loc[days[11], "小売業"] = 1.0; oc.loc[days[11], "小売業"] = 0.5
    bcc = pd.DataFrame({"N225": [0.0] * 60}, index=days); boc = bcc.copy()
    W, WB = PD.WindowCache(cc, oc), PD.WindowCache(bcc, boc)
    X, bench = ST.window_x(W, WB, "W5", [days[10]], [days[11]])
    xs = pd.Series(X[0], index=secs)
    Bm, Vm = ST.masks_for({0: L}, [0], secs, "P1")
    v = ST.spread_matrix(X, Bm, Vm, Bm.any(1), Vm.any(1))
    assert np.isclose(v[0], PD.spread(xs, *L["P1"])) and np.isclose(v[0], (2.0 / 4) - (-2.0 / 4))
    v3 = ST.spread_matrix(X, *ST.masks_for({0: L}, [0], secs, "P3"), np.array([True]), np.array([True]))
    assert np.isclose(v3[0], PD.spread(xs, *L["P3"]))
    one = ST.spread_matrix(X, *ST.masks_for({0: {"P1": (["銀行業", "保険業"], [])}}, [0], secs, "P1"), np.array([True]), np.array([False]))
    assert np.isclose(one[0], PD.spread(xs, ["銀行業", "保険業"], []))
    small = ST.spread_matrix(X, *ST.masks_for({0: {"P1": (["銀行業"], ["不動産業"])}}, [0], secs, "P1"), np.array([True]), np.array([True]))
    assert np.isnan(small[0])                                                                        # 一侧 < 2 → 缺值
    G, gb = ST.gap_vec(W, WB, [days[11]], [days[11]])                                               # t0 = r：GAP = open_t0 / close_{t0−1} − 1 = (1+cc)/(1+oc) − 1
    assert np.isclose(G[0][secs.index("小売業")], ((1.01 / 1.005) - 1) * 100) and np.isclose(gb[0], 0.0)
    G2, _ = ST.gap_vec(W, WB, [days[11]], [days[12]])                                               # t0 = r+1：加上 r 当天
    assert np.isclose(G2[0][secs.index("小売業")], (1.01 - 1) * 100)
    E2 = pd.DataFrame([{"category": "TARIFF", "sign": 1, "in_judgment": True, "r": days[10], "t0": days[11]},
                       {"category": "TARIFF", "sign": -1, "in_judgment": True, "r": days[14], "t0": days[15]},
                       {"category": "TARIFF", "sign": 1, "in_judgment": True, "r": days[40], "t0": days[41]}])
    assert list(ST.trunc_h(E2, days, [0, 1, 2], 20)) == [3, 20, 20]                                  # 下一反向事件 r = 14 → h_eff = 14 − 11


def test_events_for_study_stage_gating(tmp_path, monkeypatch):
    days = pd.bdate_range("2000-01-03", "2026-12-31")
    rows = []
    for d, cat, sub, sign in (("2010-10-05", "BOJ_CHANGE", "ease", -1), ("2023-07-28", "BOJ_CHANGE", "tighten", 1), ("2010-10-05", "BOJ_ETF", "expand", 1)):
        rows.append({c: "" for c in PEV.EVENT_COLS} | dict(id=f"{cat}-{d}", category=cat, subtype=sub, sign=str(sign), date=d, time_local="12:00", date_jst=d, time_jst="12:00",
                                                          time_src="class_default", home="JP", known_on=d, covert="0", pre_announced="0", market_dir=str(PEV.market_dir_of(cat, sub)),
                                                          source_url="https://www.boj.or.jp/x.htm", verified="2026-09-27", checked_hash="12345678", excluded="0"))
    fp = tmp_path / "ev.csv"
    pd.DataFrame(rows)[PEV.EVENT_COLS].to_csv(fp, index=False)
    monkeypatch.setattr(PD, "EVENTS_PATH", fp)
    Ex = ST.events_for_study(days, "explore")
    assert len(Ex) == 2 and set(Ex["category"]) == {"BOJ_CHANGE", "BOJ_ETF"}                          # 2023 的行不读
    assert int(Ex[Ex["category"] == "BOJ_CHANGE"]["in_judgment"].iloc[0]) == 1 and int(Ex[Ex["category"] == "BOJ_ETF"]["dedup_drop"].iloc[0]) == 1   # 同日：强类别优先
    Ec = ST.events_for_study(days, "confirm")
    assert len(Ec) == 3 and dict(zip(Ec["id"], Ec["era"])) == {"BOJ_CHANGE-2010-10-05": "A", "BOJ_CHANGE-2023-07-28": "B2", "BOJ_ETF-2010-10-05": "A"}
    assert str(Ec[Ec["id"] == "BOJ_CHANGE-2010-10-05"]["t0"].iloc[0].date()) == "2010-10-06"          # 12:00 盘中 → t0 次日


def test_confirm_guard(monkeypatch):
    import pytest
    monkeypatch.setattr(ST, "CONFIRM_IDS", ())
    with pytest.raises(SystemExit):
        ST.main(["--stage", "confirm"])
